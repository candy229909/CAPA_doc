# backend/app/database.py
import os
from motor.motor_asyncio import AsyncIOMotorClient
from neo4j import AsyncGraphDatabase
from datetime import datetime
from typing import List, Dict, Any

class MongoDB:
    def __init__(self):
        self.client = None
        self.db = None
        self.conversations_collection = None
        self.messages_collection = None

    async def connect(self):
        """連接到 MongoDB"""
        mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017/chatdb")
        self.client = AsyncIOMotorClient(mongodb_url)
        self.db = self.client.chatdb
        self.conversations_collection = self.db.conversations
        self.messages_collection = self.db.messages
        
        # 建立索引
        await self.conversations_collection.create_index("id", unique=True)
        await self.messages_collection.create_index("conversation_id")
        await self.messages_collection.create_index("timestamp")

    async def close(self):
        """關閉 MongoDB 連接"""
        if self.client:
            self.client.close()

    async def ping(self) -> bool:
        """檢查 MongoDB 連接狀態"""
        try:
            await self.client.admin.command('ping')
            return True
        except Exception:
            return False

    async def create_conversation(self, conversation_data: Dict[str, Any]) -> Dict[str, Any]:
        """建立新對話"""
        await self.conversations_collection.insert_one(conversation_data)
        return conversation_data

    async def get_conversations(self) -> List[Dict[str, Any]]:
        """獲取所有對話，按更新時間排序"""
        cursor = self.conversations_collection.find({}).sort("updated_at", -1)
        conversations = await cursor.to_list(length=100)
        
        # 移除 MongoDB 的 _id 欄位
        for conv in conversations:
            conv.pop('_id', None)
            # 確保日期格式正確
            if isinstance(conv.get('created_at'), datetime):
                conv['created_at'] = conv['created_at'].isoformat()
            if isinstance(conv.get('updated_at'), datetime):
                conv['updated_at'] = conv['updated_at'].isoformat()
        
        return conversations

    async def update_conversation_title(self, conversation_id: str, title: str):
        """更新對話標題"""
        await self.conversations_collection.update_one(
            {"id": conversation_id},
            {
                "$set": {
                    "title": title,
                    "updated_at": datetime.utcnow()
                }
            }
        )

    async def delete_conversation(self, conversation_id: str):
        """刪除對話及其所有訊息"""
        await self.conversations_collection.delete_one({"id": conversation_id})
        await self.messages_collection.delete_many({"conversation_id": conversation_id})

    async def save_message(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """儲存訊息"""
        await self.messages_collection.insert_one(message_data)
        return message_data

    async def get_messages(self, conversation_id: str) -> List[Dict[str, Any]]:
        """獲取對話中的所有訊息"""
        cursor = self.messages_collection.find(
            {"conversation_id": conversation_id}
        ).sort("timestamp", 1)
        
        messages = await cursor.to_list(length=1000)
        
        # 移除 MongoDB 的 _id 欄位並格式化日期
        for msg in messages:
            msg.pop('_id', None)
            if isinstance(msg.get('timestamp'), datetime):
                msg['timestamp'] = msg['timestamp'].isoformat()
        
        return messages

    async def count_messages(self, conversation_id: str) -> int:
        """計算對話中的訊息數量"""
        return await self.messages_collection.count_documents({"conversation_id": conversation_id})


class Neo4jDB:
    def __init__(self):
        self.driver = None

    async def connect(self):
        """連接到 Neo4j"""
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "password123")
        
        self.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def close(self):
        """關閉 Neo4j 連接"""
        if self.driver:
            await self.driver.close()

    async def ping(self) -> bool:
        """檢查 Neo4j 連接狀態"""
        try:
            async with self.driver.session() as session:
                await session.run("RETURN 1")
            return True
        except Exception:
            return False

    async def save_interaction(self, conversation_id: str, user_message: str, ai_response: str):
        """儲存對話互動到圖形資料庫"""
        try:
            async with self.driver.session() as session:
                await session.run("""
                    MERGE (c:Conversation {id: $conversation_id})
                    CREATE (u:Message {content: $user_message, role: 'user', timestamp: datetime()})
                    CREATE (a:Message {content: $ai_response, role: 'assistant', timestamp: datetime()})
                    CREATE (c)-[:CONTAINS]->(u)
                    CREATE (c)-[:CONTAINS]->(a)
                    CREATE (u)-[:FOLLOWED_BY]->(a)
                """, conversation_id=conversation_id, user_message=user_message, ai_response=ai_response)
        except Exception as e:
            print(f"Neo4j error: {e}")