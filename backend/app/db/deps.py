from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from backend.app.db.database import Database
from backend.app.services.market_cap import MarketCapService


def get_db(request: Request) -> Database:
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise RuntimeError("DB is not initialized on app.state")
    return db


DbDep = Annotated[Database, Depends(get_db)]


def get_market_cap_service(request: Request) -> MarketCapService:
    svc = getattr(request.app.state, "market_cap", None)
    if svc is None:
        raise RuntimeError("MarketCapService is not initialized on app.state")
    return svc


MarketCapDep = Annotated[MarketCapService, Depends(get_market_cap_service)]

