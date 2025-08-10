# app/routes/health_router.py
from fastapi import APIRouter, Request
import httpx, os

router = APIRouter()

@router.get("/health")
async def health(request: Request):
    ok = {"ollama": "error", "mongodb": "error", "neo4j": "error"}
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(os.getenv("OLLAMA_HOST", "http://ollama:11434"))
            ok["ollama"] = "ok" if r.status_code < 500 else "error"
    except Exception:
        pass
    try:
        ok["mongodb"] = "ok" if await request.app.state.mongo.ping() else "error"
    except Exception:
        pass
    try:
        ok["neo4j"] = "ok" if await request.app.state.neo4j.ping() else "error"
    except Exception:
        pass
    return {"status": "healthy" if all(v=="ok" for v in ok.values()) else "unhealthy",
            "services": ok}
