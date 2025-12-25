from __future__ import annotations

import sys
from pathlib import Path

import uvicorn

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    # 兼容 `python backend/run.py`
    sys.path.insert(0, str(_ROOT))

from backend.app.core.config import settings


def main() -> None:
    uvicorn.run(
        "backend.app.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=settings.env == "dev",
    )


if __name__ == "__main__":
    main()

