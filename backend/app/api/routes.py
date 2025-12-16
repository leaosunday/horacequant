from __future__ import annotations

from fastapi import APIRouter

from backend.app.db.deps import DbDep

router = APIRouter()


@router.get("/hello", tags=["public"])
def hello() -> dict:
    return {"message": "hello world"}


@router.get("/healthz", tags=["ops"])
async def healthz(db: DbDep) -> dict:
    ok = await db.healthcheck()
    return {"status": "ok" if ok else "degraded", "db": "ok" if ok else "down"}

