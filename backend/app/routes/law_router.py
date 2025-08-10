# app/routes/law_router.py
from fastapi import APIRouter, Request
from app.services.law_service import LawService

router = APIRouter()

@router.post("/law/query")
async def law_query(request: Request, payload: dict):
    svc = LawService(request.app.state.neo4j)
    return await svc.query(payload)
