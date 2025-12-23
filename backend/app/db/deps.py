from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from backend.app.db.database import Database
from backend.app.services.market_cap import MarketCapService
from backend.app.repos.indicators_repo import IndicatorsRepo


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


def get_indicators_repo(request: Request) -> IndicatorsRepo:
    repo = getattr(request.app.state, "indicators_repo", None)
    if repo is None:
        raise RuntimeError("IndicatorsRepo is not initialized on app.state")
    return repo


IndicatorsRepoDep = Annotated[IndicatorsRepo, Depends(get_indicators_repo)]

