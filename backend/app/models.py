# backend/app/models.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ConversationCreate(BaseModel):
    title: str

class MessageCreate(BaseModel):
    conversation_id: str
    content: str
    role: str  # "user" or "assistant"

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    model: Optional[str] = "gemma2:2b"

class Conversation(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime

class Message(BaseModel):
    id: str
    conversation_id: str
    content: str
    role: str
    timestamp: datetime