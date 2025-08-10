# app/routes/chat_router.py
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from app.models import EnhancedChatRequest
from app.services.chat_service import ChatService

router = APIRouter()

@router.post("/chat")
async def chat(request: Request, payload: EnhancedChatRequest):
    svc = ChatService(request.app.state.mongo, request.app.state.neo4j)
    return await svc.chat(payload)

@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()
    try:
        # simple bridge: receive JSON with {conversation_id, content, model?, use_nlu?}
        from pydantic import BaseModel
        class WSReq(BaseModel):
            conversation_id: str | None = None
            content: str
            model: str | None = None
            use_nlu: bool | None = None

        data = await websocket.receive_json()
        req = WSReq(**data)
        from app.models import EnhancedChatRequest
        payload = EnhancedChatRequest(message=req.content, conversation_id=req.conversation_id, model=req.model or "gemma3n:e2b", use_nlu=req.use_nlu)
        # Build service using application state
        svc = ChatService(websocket.app.state.mongo, websocket.app.state.neo4j)
        result = await svc.chat(payload)
        await websocket.send_json({"status":"final","message": result.get("content"), "payload": {"conversation_id": result.get("conversation_id")}})
    except WebSocketDisconnect:
        return