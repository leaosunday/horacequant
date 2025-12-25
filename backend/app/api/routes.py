from __future__ import annotations

from fastapi import APIRouter

from backend.app.db.deps import DbDep
from backend.app.api.picks import router as picks_router
from backend.app.api.schemas import ApiResponse

router = APIRouter()
v1 = APIRouter(prefix="/api/v1")


@router.get("/hello", tags=["public"])
def hello() -> dict:
    return {"message": "hello world"}


@router.get("/healthz", tags=["ops"])
async def healthz(db: DbDep) -> dict:
    ok = await db.healthcheck()
    return {"status": "ok" if ok else "degraded", "db": "ok" if ok else "down"}


@v1.get("/hello", tags=["public"], response_model=ApiResponse[dict])
def hello_v1() -> ApiResponse[dict]:
    return ApiResponse(request_id=None, data={"message": "hello world"})


@v1.get("/healthz", tags=["ops"], response_model=ApiResponse[dict])
async def healthz_v1(db: DbDep) -> ApiResponse[dict]:
    ok = await db.healthcheck()
    return ApiResponse(request_id=None, data={"status": "ok" if ok else "degraded", "db": "ok" if ok else "down"})


router.include_router(v1)
router.include_router(picks_router)

