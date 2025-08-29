# app/routes/conversation_router.py
from fastapi import APIRouter, Depends, Request, Request, HTTPException
from app.services.conversation_service import ConversationService
from app.models import ConversationCreate

async def _ensure_mongo(request: Request):
    """Guarantee Mongo is connected/initialized before handling the endpoint."""
    mongo = request.app.state.mongo
    # connect() is idempotent; if already connected it returns quickly
    await mongo.connect()



router = APIRouter(dependencies=[Depends(_ensure_mongo)])

@router.get("/")
async def list_conversations(request: Request):
    svc = ConversationService(request.app.state.mongo)
    return await svc.list_conversations()

@router.post("/")
async def create_conversation(request: Request, conversation: ConversationCreate):
    svc = ConversationService(request.app.state.mongo)
    try:
        return await svc.create_conversation(conversation.title)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{conversation_id}/title")
async def rename_conversation(conversation_id: str, request: Request, conversation: ConversationCreate):
    svc = ConversationService(request.app.state.mongo)
    try:
        await svc.rename_conversation(conversation_id, conversation.title)
        return {"message": "對話標題更新成功", "title": conversation.title}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{conversation_id}/messages")
async def get_messages(conversation_id: str, request: Request):
    svc = ConversationService(request.app.state.mongo)
    return await svc.get_messages(conversation_id)

@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str, request: Request):
    svc = ConversationService(request.app.state.mongo)
    await svc.delete_conversation(conversation_id)
    return {"message": "Conversation deleted successfully"}