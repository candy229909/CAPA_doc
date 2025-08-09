import os
from motor.motor_asyncio import AsyncIOMotorClient
from neo4j import AsyncGraphDatabase
from datetime import datetime
from typing import List, Dict, Any
from bson import ObjectId

def clean_mongo_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """遞迴地將 MongoDB 文件中的 ObjectId 和 datetime 轉換為字串"""
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            doc[k] = str(v)
        elif isinstance(v, datetime):
            doc[k] = v.isoformat()
        elif isinstance(v, dict):
            doc[k] = clean_mongo_document(v)
        elif isinstance(v, list):
            doc[k] = [clean_mongo_document(i) if isinstance(i, dict) else i for i in v]
    return doc

def to_plain(obj: Any) -> Any:
    """將物件中所有 ObjectId 和 datetime 轉為基本類型"""
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, list):
        return [to_plain(x) for x in obj]
    if isinstance(obj, dict):
        return {k: to_plain(v) for k, v in obj.items()}
    return obj

class MongoDB:
    def __init__(self):
        self.client = None
        self.db = None
        self.conversations_collection = None
        self.messages_collection = None
        self.prompts_collection = None
        self.documents_collection = None

    async def connect(self):
        """連接到 MongoDB 資料庫"""
        mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017/chatdb")
        self.client = AsyncIOMotorClient(mongodb_url)
        # 可從環境變數設定 DB 名稱，否則預設使用 chatdb
        self.db = self.client.get_default_database() if os.getenv("MONGODB_DB") else self.client.chatdb
        self.conversations_collection = self.db.conversations
        self.messages_collection = self.db.messages
        # 建立必要索引（加速查詢和保持唯一性）
        await self.conversations_collection.create_index("id", unique=True)
        await self.messages_collection.create_index("conversation_id")
        await self.messages_collection.create_index("timestamp")

        self.prompts_collection = self.db.prompts
        self.documents_collection = self.db.documents

        await self.prompts_collection.create_index("id", unique=True)
        await self.prompts_collection.create_index("conversation_id")
        await self.prompts_collection.create_index("message_id")
        await self.prompts_collection.create_index([("created_at", -1)])

        await self.documents_collection.create_index("id", unique=True)
        await self.documents_collection.create_index("conversation_id")
        await self.documents_collection.create_index("prompt_id")
        await self.documents_collection.create_index([("created_at", -1)])


    async def close(self):
        """關閉 MongoDB 連接"""
        if self.client:
            self.client.close()

    async def ping(self) -> bool:
        """檢查 MongoDB 連接狀態"""
        try:
            await self.client.admin.command("ping")
            return True
        except Exception:
            return False

    async def create_conversation(self, conversation_data: Dict[str, Any]) -> Dict[str, Any]:
        """新增對話記錄，傳入 {'id', 'title', 'created_at', 'updated_at'}"""
        # 複製資料，避免 PyMongo 寫入 _id 污染原 dict
        doc = dict(conversation_data)
        await self.conversations_collection.insert_one(doc)
        return to_plain(doc)

    async def get_conversations(self) -> List[Dict[str, Any]]:
        """取得所有對話列表，按更新時間逆序排序，不含內部 _id 欄位"""
        cursor = self.conversations_collection.find({}, {"_id": 0}).sort("updated_at", -1)
        conversations = await cursor.to_list(length=None)
        return to_plain(conversations)

    async def update_conversation_title(self, conversation_id: str, title: str):
        """更新指定對話的標題（同時刷新 updated_at）"""
        await self.conversations_collection.update_one(
            {"id": conversation_id},
            {"$set": {"title": title, "updated_at": datetime.utcnow()}}
        )

    async def delete_conversation(self, conversation_id: str):
        """刪除指定對話及其所有訊息"""
        await self.conversations_collection.delete_one({"id": conversation_id})
        await self.messages_collection.delete_many({"conversation_id": conversation_id})

    async def save_message(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """儲存單則訊息"""
        # 複製資料，避免 _id 影響原物件
        doc = dict(message_data)
        await self.messages_collection.insert_one(doc)
        return to_plain(doc)

    async def get_messages(self, conversation_id: str) -> List[Dict[str, Any]]:
        """取得指定對話的所有訊息（按時間順序），不含 _id 欄位"""
        cursor = self.messages_collection.find({"conversation_id": conversation_id}, {"_id": 0}).sort("timestamp", 1)
        messages = await cursor.to_list(length=None)
        return to_plain(messages)

    async def count_messages(self, conversation_id: str) -> int:
        """計算指定對話中的訊息數量"""
        return await self.messages_collection.count_documents({"conversation_id": conversation_id})

    async def update_conversation_timestamp(self, conversation_id: str):
        """更新對話的最近更新時間為現在"""
        await self.conversations_collection.update_one(
            {"id": conversation_id},
            {"$set": {"updated_at": datetime.utcnow()}}
        )
    
    async def save_prompt(self, conversation_id: str, message_id: str, prompt_json: dict) -> dict:
        doc = {
            "id": str(uuid.uuid4()),
            "conversation_id": conversation_id,
            "message_id": message_id,
            "prompt_json": prompt_json,
            "created_at": datetime.utcnow(),
        }
        await self.prompts_collection.insert_one(doc)
        return to_plain(doc)

    async def save_document(self, conversation_id: str, prompt_id: str, type_: str,
                            content: str, title: str | None = None, meta: dict | None = None) -> dict:
        doc = {
            "id": str(uuid.uuid4()),
            "conversation_id": conversation_id,
            "prompt_id": prompt_id,
            "type": type_,
            "title": title,
            "content": content,
            "meta": meta or {},
            "created_at": datetime.utcnow(),
        }
        await self.documents_collection.insert_one(doc)
        return to_plain(doc)

    async def get_prompt(self, prompt_id: str) -> dict | None:
        return await self.prompts_collection.find_one({"id": prompt_id}, {"_id": 0})

    async def list_documents_by_conv(self, conversation_id: str) -> list[dict]:
        cur = self.documents_collection.find({"conversation_id": conversation_id}, {"_id": 0}).sort("created_at", -1)
        return await cur.to_list(None)

class Neo4jDB:
    def __init__(self):
        self.driver = None

    async def connect(self):
        """連接到 Neo4j 資料庫"""
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
        """儲存一次對話問答到 Neo4j 圖形資料庫"""
        try:
            async with self.driver.session() as session:
                await session.run(
                    """
                    MERGE (c:Conversation {id: $conversation_id})
                    CREATE (u:Message {content: $user_message, role: 'user', timestamp: datetime()})
                    CREATE (a:Message {content: $ai_response, role: 'assistant', timestamp: datetime()})
                    CREATE (c)-[:CONTAINS]->(u)
                    CREATE (c)-[:CONTAINS]->(a)
                    CREATE (u)-[:FOLLOWED_BY]->(a)
                    """,
                    conversation_id=conversation_id, user_message=user_message, ai_response=ai_response
                )
        except Exception as e:
            print(f"Neo4j error: {e}")

    async def run_read_query(self, cypher: str, params: Dict[str, Any] | None = None):
        """執行讀取類型的 Cypher 查詢並返回結果資料"""
        try:
            async with self.driver.session() as session:
                result = await session.run(cypher, parameters=params or {})
                records = await result.to_list()
                return [r.data() for r in records]
        except Exception as e:
            print("[Neo4j] run_read_query error:", e)
            return []
