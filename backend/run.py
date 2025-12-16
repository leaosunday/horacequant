from __future__ import annotations

import uvicorn

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

