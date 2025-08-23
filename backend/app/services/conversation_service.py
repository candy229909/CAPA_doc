# app/services/conversation_service.py
import uuid
from datetime import datetime
from typing import Dict, Any, List
from app.database.db_mongo import MongoDB

class ConversationService:
    def __init__(self, mongo: MongoDB):
        self.mongo = mongo

    async def list_conversations(self) -> List[Dict[str, Any]]:
        return await self.mongo.get_conversations()

    async def create_conversation(self, title: str = "New Chat"):
        conv_id = str(uuid.uuid4())
        data = {
            "id": conv_id,
            "title": title or "New Chat",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        await self.mongo.create_conversation(data)
        return data

    async def rename_conversation(self, conversation_id: str, title: str):
        convs = await self.mongo.get_conversations()
        if not any(c.get("id") == conversation_id for c in convs):
            raise ValueError("對話不存在")
        await self.mongo.update_conversation_title(conversation_id, title)

    async def get_messages(self, conversation_id: str):
        return await self.mongo.get_messages(conversation_id)

    async def delete_conversation(self, conversation_id: str):
        await self.mongo.delete_conversation(conversation_id)

