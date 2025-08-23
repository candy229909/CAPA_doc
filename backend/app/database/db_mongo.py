# app/database/db_mongo.py
from __future__ import annotations

# ⬇️ 保留你原本用到的 import（motor、pydantic、datetime、uuid…）
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Any, Dict, Optional, List
from datetime import datetime
import uuid
import asyncio, re

def strip_id(obj):
    if isinstance(obj, list):
        return [strip_id(x) for x in obj]
    if isinstance(obj, dict):
        d = dict(obj); d.pop("_id", None); return d
    return obj

class MongoDB:
    def __init__(self, uri: str, db_name: str = "app"):
        self.uri = uri
        self.db_name = db_name
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None

        # 依你原本的集合命名初始化（範例）
        self.conversations = None
        self.messages = None
        self.prompts = None
        self.documents = None
    
    async def connect(self):
        # 讓選擇伺服器超時短一點，方便重試
        self.client = AsyncIOMotorClient(self.uri, serverSelectionTimeoutMS=3000)

        # 等 Mongo 就緒（最多 ~30 秒）
        for _ in range(30):
            try:
                await self.client.admin.command("ping")
                break
            except Exception:
                await asyncio.sleep(1)
        else:
            raise RuntimeError(f"MongoDB not reachable at URI: {self.uri}")

        self.db = self.client[self.db_name]

        self.conversations = self.db.conversations
        self.messages = self.db.messages
        self.prompts = self.db.prompts
        self.documents = self.db.documents

        # 真的連上了再建索引
        await self.conversations.create_index("id", unique=True)
        await self.messages.create_index("id", unique=True)
        await self.messages.create_index("conversation_id")
        await self.prompts.create_index("id", unique=True)
        await self.prompts.create_index("conversation_id")
        await self.prompts.create_index("message_id")
        await self.documents.create_index("id", unique=True)
        await self.documents.create_index("conversation_id")
        await self.documents.create_index("prompt_id")
        await self.documents.create_index(
            [("title", "text"), ("content", "text"), ("chunks.text", "text")],
            name="documents_text_index"
        )

    async def close(self):
        if self.client:
            self.client.close()

    async def ping(self) -> bool:
        """檢查 MongoDB 連接狀態"""
        try:
            await self.client.admin.command("ping")
            return True
        except Exception:
            return False

    # 會話清單
    async def list_conversations(self) -> List[Dict[str, Any]]:
        cur = self.conversations.find({}, {"_id": 0}).sort("updated_at", -1)
        return await cur.to_list(None)
    
    # 取會話訊息
    async def list_messages(self, conversation_id: str) -> List[Dict[str, Any]]:
        cur = self.messages.find(
            {"conversation_id": conversation_id}, {"_id": 0}
        ).sort("created_at", 1)
        return await cur.to_list(None)

    async def create_conversation(self, conversation_data: Dict[str, Any]) -> Dict[str, Any]:
        """新增對話記錄，傳入 {'id', 'title', 'created_at', 'updated_at'}"""
        # 複製資料，避免 PyMongo 寫入 _id 污染原 dict
        doc = dict(conversation_data)
        await self.conversations.insert_one(doc)
        return strip_id(doc)

    async def get_conversations(self) -> List[Dict[str, Any]]:
        """取得所有對話列表，按更新時間逆序排序，不含內部 _id 欄位"""
        cursor = self.conversations.find({}, {"_id": 0}).sort("updated_at", -1)
        conversations = await cursor.to_list(length=None)
        return strip_id(conversations)

    async def update_conversation_title(self, conversation_id: str, title: str):
        """更新指定對話的標題（同時刷新 updated_at）"""
        await self.conversations.update_one(
            {"id": conversation_id},
            {"$set": {"title": title, "updated_at": datetime.utcnow()}}
        )

    async def delete_conversation(self, conversation_id: str):
        """刪除指定對話及其所有訊息"""
        await self.conversations.delete_one({"id": conversation_id})
        await self.messages.delete_many({"conversation_id": conversation_id})

    async def save_message(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """儲存單則訊息"""
        # 複製資料，避免 _id 影響原物件
        doc = dict(message_data)
        await self.messages.insert_one(doc)
        return strip_id(doc)

    async def get_messages(self, conversation_id: str) -> List[Dict[str, Any]]:
        """取得指定對話的所有訊息（按時間順序），不含 _id 欄位"""
        cursor = self.messages.find({"conversation_id": conversation_id}, {"_id": 0}).sort("timestamp", 1)
        messages = await cursor.to_list(length=None)
        return strip_id(messages)

    async def count_messages(self, conversation_id: str) -> int:
        """計算指定對話中的訊息數量"""
        return await self.messages.count_documents({"conversation_id": conversation_id})

    async def update_conversation_timestamp(self, conversation_id: str):
        """更新對話的最近更新時間為現在"""
        await self.conversations.update_one(
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
        # Use self.prompts instead of the undefined prompts_collection
        await self.prompts.insert_one(doc)
        return strip_id(doc)

    async def save_document_chunks(self, conversation_id: str, title: str, content: str,
        chunks: list[dict],
        meta: dict | None = None) -> dict:
        
        doc = {
            "id": str(uuid.uuid4()),
            "conversation_id": conversation_id,
            "prompt_id": "file_upload:" + str(uuid.uuid4()),
            "type": "upload",
            "title": title,
            "content": content,
            "chunks": chunks,     # <== 讓 search_doc_chunks() 能命中
            "meta": meta or {},
            "created_at": datetime.utcnow(),
        }
        await self.documents.insert_one(doc)
        return strip_id(doc)
    
    def _simple_tokens(self, s: str) -> list[str]:
        # 中英混合字詞切割；移除太短的 token
        return [t for t in re.findall(r"[\w\u4e00-\u9fff]{2,}", (s or "").lower())]
    
    # ✅ 依查詢關鍵詞，回傳最相關的「切塊」片段
    async def search_doc_chunks(self, conversation_id: str, query: str, top_k: int = 3) -> list[dict]:
        # 先用 $text 找到最接近的文件（不需 Atlas Search）
        cur = self.documents.find(
            {"conversation_id": conversation_id, "$text": {"$search": query}},
            {"_id": 0, "title": 1, "content": 1, "chunks": 1, "score": {"$meta": "textScore"}}
        ).sort([("score", {"$meta": "textScore"})]).limit(8)
        docs = await cur.to_list(length=None)

        tokens = set(self._simple_tokens(query))
        results: list[dict] = []

        for d in docs:
            chunks = d.get("chunks") or [{"idx": 0, "text": d.get("content", "")}]
            best = None
            best_score = -1
            for ch in chunks:
                txt = (ch.get("text") if isinstance(ch, dict) else str(ch)) or ""
                score = sum(1 for t in tokens if t in txt.lower())
                if score > best_score:
                    best_score = score
                    best = {
                        "title": d.get("title") or (d.get("meta", {}) or {}).get("filename", ""),
                        "idx": ch.get("idx", 0),
                        "text": txt
                    }
            if best and (best.get("text") or "").strip():
                results.append(best)

        return results[:top_k]

    async def get_prompt(self, prompt_id: str) -> dict | None:
        return await self.prompts.find_one({"id": prompt_id}, {"_id": 0})

    async def list_documents_by_conv(self, conversation_id: str) -> list[dict]:
        cur = self.documents.find({"conversation_id": conversation_id}, {"_id": 0}).sort("created_at", -1)
        return await cur.to_list(None)
