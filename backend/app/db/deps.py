from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from backend.app.db.database import Database


def get_db(request: Request) -> Database:
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise RuntimeError("DB is not initialized on app.state")
    return db


DbDep = Annotated[Database, Depends(get_db)]

