# backend/app/routes/rag_router.py
from fastapi import APIRouter, Request
from app.models.extension import RAGRequest
from app.services.rag_service import GraphRAGService

router = APIRouter()

@router.post("/rag-search")
async def rag_search(req: RAGRequest, request: Request):
    svc = GraphRAGService(request.app.state.neo4j)
    return await svc.search(req.question)
