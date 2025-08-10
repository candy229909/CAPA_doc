# app/routes/ethics_router.py
from fastapi import APIRouter
from app.services.ethics_service import EthicsService

router = APIRouter()

@router.post("/ethics-check")
async def ethics_check(payload: dict):
    return EthicsService.check(payload.get("text", ""))
