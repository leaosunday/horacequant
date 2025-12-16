from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/hello", tags=["public"])
def hello() -> dict:
    return {"message": "hello world"}


@router.get("/healthz", tags=["ops"])
def healthz() -> dict:
    return {"status": "ok"}

