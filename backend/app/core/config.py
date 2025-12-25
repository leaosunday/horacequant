from __future__ import annotations

from typing import Annotated

import getpass
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """
    线上风格配置：全部来自环境变量，默认值尽量安全。
    """

    model_config = SettingsConfigDict(env_prefix="HQ_", case_sensitive=False)

    app_name: str = "horacequant-backend"
    env: str = Field(default="prod", description="运行环境标识：prod/staging/dev")

    host: str = Field(default="0.0.0.0", description="服务监听地址")
    port: int = Field(default=8000, description="服务监听端口")

    log_level: str = Field(default="INFO", description="日志级别：DEBUG/INFO/WARNING/ERROR")
    log_to_file: bool = Field(default=True, description="是否输出到日志文件")
    log_dir: str = Field(default="logs", description="日志目录（相对或绝对路径）")
    log_retention_days: int = Field(default=14, description="日志保留天数（按天滚动）")

    # 安全：默认只允许本机/容器健康检查；线上请显式配置域名或网关
    allowed_hosts: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])

    # ---------- CORS ----------
    # 供前端联调：默认允许常见本地 dev server（按需通过环境变量覆盖）
    cors_enabled: bool = Field(default=True, description="是否启用 CORS（给浏览器前端调用）")
    cors_allow_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        description="允许的前端 Origin 列表（逗号分隔或 JSON 数组）",
    )
    cors_allow_credentials: bool = Field(default=True, description="是否允许携带 cookie/credentials（若 allow_origins 含 '*' 则必须为 false）")
    cors_allow_methods: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])
    cors_allow_headers: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])

    # ---------- Postgres ----------
    pg_host: str = Field(default="127.0.0.1")
    pg_port: int = Field(default=5432)
    pg_user: str = Field(default_factory=getpass.getuser)
    pg_password: str = Field(default="")
    pg_db: str = Field(default="horace_quant")
    pg_ssl: str = Field(default="", description="例如 require；空字符串表示不启用")
    pg_pool_min: int = Field(default=1)
    pg_pool_max: int = Field(default=10)
    pg_command_timeout: float = Field(default=30.0)

    # ---------- Scheduler / Jobs ----------
    # 通过 Postgres advisory lock 防止重复执行的锁 key（全局唯一即可）
    scheduler_lock_key: int = Field(default=42424242)
    scheduler_enabled: bool = Field(default=True, description="是否启用定时任务调度器")
    scheduler_timezone: str = Field(default="Asia/Shanghai", description="调度时区")
    scheduler_hour: int = Field(default=16, description="每日任务小时（0-23）")
    scheduler_minute: int = Field(default=0, description="每日任务分钟（0-59）")
    scheduler_misfire_grace_seconds: int = Field(default=60 * 30, description="错过触发后的最大补跑窗口（秒）")
    scheduler_run_on_start: bool = Field(default=False, description="worker 启动时立刻跑一次（用于验证/补数据）")

    # 策略列表：逗号分隔（或 JSON 数组），例如 HQ_STRATEGIES="b1,b2"
    strategies: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["b1"])

    @field_validator("strategies", mode="before")
    @classmethod
    def _parse_strategies(cls, v):
        if v is None:
            return v
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str):
            s = v.strip()
            if s == "":
                return []
            if s.startswith("["):
                # 允许 JSON 数组：交由 pydantic 解码
                return v
            return [x.strip() for x in s.split(",") if x.strip()]
        return v

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def _parse_allowed_hosts(cls, v):
        """
        允许使用两种方式配置：
        - HQ_ALLOWED_HOSTS='["example.com","api.example.com"]'  (JSON)
        - HQ_ALLOWED_HOSTS='example.com,api.example.com'        (逗号分隔)
        - HQ_ALLOWED_HOSTS='*'                                  (允许任意 Host，不建议线上使用)
        """
        if v is None:
            return v
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            s = v.strip()
            if s == "":
                return []
            if s == "*":
                return ["*"]
            # JSON 形式交给 pydantic 自己 decode 也可，但这里做兼容
            if s.startswith("["):
                return v
            return [x.strip() for x in s.split(",") if x.strip()]
        return v

    @field_validator("cors_allow_origins", "cors_allow_methods", "cors_allow_headers", mode="before")
    @classmethod
    def _parse_cors_list(cls, v):
        """
        允许使用两种方式配置：
        - HQ_CORS_ALLOW_ORIGINS='["http://a.com","http://b.com"]'  (JSON)
        - HQ_CORS_ALLOW_ORIGINS='http://a.com,http://b.com'        (逗号分隔)
        - HQ_CORS_ALLOW_ORIGINS='*'                                (允许任意 Origin；若如此则 credentials 必须为 false)
        """
        if v is None:
            return v
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str):
            s = v.strip()
            if s == "":
                return []
            if s == "*":
                return ["*"]
            if s.startswith("["):
                return v
            return [x.strip() for x in s.split(",") if x.strip()]
        return v

    @field_validator("cors_allow_credentials")
    @classmethod
    def _validate_cors_credentials(cls, v, info):
        # 若 allow_origins 为 '*'，Starlette 要求 allow_credentials=False
        origins = (info.data or {}).get("cors_allow_origins") or []
        if isinstance(origins, list) and "*" in origins and v:
            raise ValueError("cors_allow_credentials must be false when cors_allow_origins contains '*'")
        return v


settings = Settings()

