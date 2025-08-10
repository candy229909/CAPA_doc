# app/routes/nlu_router.py
from fastapi import APIRouter
from app.services.nlu_service import NLUService

router = APIRouter()

@router.post("/nlu")
async def analyze(payload: dict):
    return NLUService.analyze(payload.get("query", ""))
