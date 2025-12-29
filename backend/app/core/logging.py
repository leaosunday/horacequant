from __future__ import annotations

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional


class _IncludePrefixFilter(logging.Filter):
    def __init__(self, prefixes: tuple[str, ...]):
        super().__init__()
        self.prefixes = prefixes

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 (filter)
        return record.name.startswith(self.prefixes)


class _ExcludePrefixFilter(logging.Filter):
    def __init__(self, prefixes: tuple[str, ...]):
        super().__init__()
        self.prefixes = prefixes

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 (filter)
        return not record.name.startswith(self.prefixes)


def _fmt() -> logging.Formatter:
    return logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )


class _SafeTimedRotatingFileHandler(TimedRotatingFileHandler):
    """
    TimedRotatingFileHandler 在滚动/清理旧文件时会 os.listdir(日志目录)；
    若目录不存在（被删/未创建），会抛 FileNotFoundError 并导致 emit 失败（甚至影响 uvicorn.access）。
    这里兜底：每次 emit/rollover 前确保目录存在。
    """

    def _ensure_dir(self) -> None:
        try:
            Path(self.baseFilename).parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            return

    def emit(self, record: logging.LogRecord) -> None:
        self._ensure_dir()
        try:
            super().emit(record)
        except FileNotFoundError:
            self._ensure_dir()
            super().emit(record)

    def doRollover(self) -> None:
        self._ensure_dir()
        try:
            super().doRollover()
        except FileNotFoundError:
            self._ensure_dir()
            super().doRollover()


def _file_handler(path: Path, level: int, retention_days: int) -> TimedRotatingFileHandler:
    # 按天滚动；backupCount=保留天数（自动清理旧文件）
    path.parent.mkdir(parents=True, exist_ok=True)
    h = _SafeTimedRotatingFileHandler(
        filename=str(path),
        when="midnight",
        interval=1,
        backupCount=max(1, int(retention_days)),
        encoding="utf-8",
        delay=True,
        utc=False,
    )
    h.setLevel(level)
    h.setFormatter(_fmt())
    return h


def configure_logging(
    level: str = "INFO",
    *,
    to_file: bool = False,
    log_dir: str = "logs",
    retention_days: int = 14,
) -> None:
    """
    统一日志格式，兼容 uvicorn 日志体系。
    输出：
      - 控制台：所有日志
      - 文件（可选）：按类型拆分 + rotate + 过期清理
        - app.log：业务日志（排除 access/jobs）
        - jobs.log：定时任务日志
        - access.log：HTTP access 日志（uvicorn.access）
        - error.log：ERROR+ 汇总
    """
    lvl = getattr(logging, level.upper(), logging.INFO)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(lvl)
    console.setFormatter(_fmt())

    app_handler = None
    jobs_handler = None
    access_handler = None
    error_handler = None

    if to_file:
        d = Path(log_dir).expanduser().resolve()
        d.mkdir(parents=True, exist_ok=True)

        app_handler = _file_handler(d / "app.log", lvl, retention_days)
        # app.log 不记录 access 与 jobs（避免重复、便于区分）
        app_handler.addFilter(_ExcludePrefixFilter(("uvicorn.access", "backend.app.jobs", "backend.worker")))

        jobs_handler = _file_handler(d / "jobs.log", lvl, retention_days)
        jobs_handler.addFilter(_IncludePrefixFilter(("backend.app.jobs", "backend.worker")))

        access_handler = _file_handler(d / "access.log", lvl, retention_days)
        access_handler.addFilter(_IncludePrefixFilter(("uvicorn.access",)))

        error_handler = _file_handler(d / "error.log", logging.ERROR, retention_days)

    # ---------- root ----------
    root = logging.getLogger()
    root.setLevel(lvl)
    handlers = [console]
    if app_handler:
        handlers.append(app_handler)
    if error_handler:
        handlers.append(error_handler)
    root.handlers = handlers

    # ---------- uvicorn access: 独立到 access.log，避免写进 app.log ----------
    uv_access = logging.getLogger("uvicorn.access")
    uv_access.setLevel(lvl)
    uv_access.handlers = [console] + ([access_handler] if access_handler else [])
    uv_access.propagate = False

    # ---------- jobs: 独立到 jobs.log（同时写 error.log） ----------
    for name in ("backend.app.jobs", "backend.worker"):
        lg = logging.getLogger(name)
        lg.setLevel(lvl)
        lg.handlers = [console] + ([jobs_handler] if jobs_handler else []) + ([error_handler] if error_handler else [])
        lg.propagate = False

    # ---------- uvicorn error: 交给 root（app/error） ----------
    uv_err = logging.getLogger("uvicorn.error")
    uv_err.setLevel(lvl)
    uv_err.handlers = []
    uv_err.propagate = True


def get_logger(name: Optional[str] = None) -> logging.Logger:
    return logging.getLogger(name or "horacequant")

