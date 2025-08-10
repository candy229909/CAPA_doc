# app/services/chat_service.py
import os, httpx, uuid
from datetime import datetime
from typing import Dict, Any, Optional
from app.services.nlu_service import NLUService
from app.services.ethics_service import EthicsService
from app.services.law_service import LawService
from app.services.rag_service import GraphRAGService
from app.database.db_mongo import MongoDB
from app.database.db_neo4j import Neo4jDB


class ChatService:
    def __init__(self, mongo: MongoDB, neo4j: Neo4jDB):
        self.mongo = mongo
        self.neo4j = neo4j

    async def _ensure_conversation(self, conversation_id: Optional[str], title_seed: str) -> str:
        if conversation_id:
            return conversation_id
        conv_id = str(uuid.uuid4())
        title = (title_seed or "New Chat")[:50]
        await self.mongo.create_conversation({
            "id": conv_id,
            "title": title,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })
        return conv_id

    async def _save_message(self, conversation_id: str, role: str, content: str) -> str:
        msg_id = str(uuid.uuid4())
        await self.mongo.save_message({
            "id": msg_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow(),
        })
        await self.mongo.update_conversation_timestamp(conversation_id)
        return msg_id

    async def _call_ollama(self, model: str, prompt: str) -> str:
        host = os.getenv("OLLAMA_HOST", "http://ollama:11434")
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{host}/api/generate", json={"model": model, "prompt": prompt, "stream": False})
            if resp.status_code == 404:
                # try fallback
                try_model = os.getenv("OLLAMA_FALLBACK_MODEL", "gemma3n:e2b")
                # list models
                ms = await client.get(f"{host}/api/tags")
                models = [m.get("model") for m in (ms.json().get("models", []) if ms.status_code==200 else [])]
                if try_model in models:
                    resp = await client.post(f"{host}/api/generate", json={"model": try_model, "prompt": prompt, "stream": False})
                else:
                    raise RuntimeError(f"Ollama 模型 '{model}' 不存在且找不到 fallback 模型 '{try_model}'")
            resp.raise_for_status()
            return resp.json().get("response","").strip()

    async def chat(self, request) -> Dict[str, Any]:
        # request: EnhancedChatRequest
        conv_id = await self._ensure_conversation(request.conversation_id, request.message)
        # save user message
        await self._save_message(conv_id, "user", request.message)

        # decide NLU
        use_nlu = request.use_nlu if request.use_nlu is not None else (NLUService.analyze(request.message)["intent"] != "general")

        if use_nlu:
            # Use law service + optional RAG
            law = LawService(self.neo4j)
            law_res = await law.query(request.message)
            context = ""
            if law_res.get("hits"):
                top = law_res["hits"][0]
                context = f"《{top.get('title','')}》\n{(top.get('text','') or '')[:800]}"
            prompt = f"以下為使用者問題與相關法條內容，請用繁體中文回答，並在需要時引用法條：\n\n[問題]\n{request.message}\n\n[法條內容]\n{context}"
            reply = await self._call_ollama(request.model, prompt)
        else:
            prompt = f"使用者：{request.message}\n助理："
            reply = await self._call_ollama(request.model, prompt)

        # ethics
        ethics = EthicsService.check(reply)
        if ethics.get("flagged"):
            reply = "⚠️ 回覆內容包含敏感字詞，已過濾。"

        # save assistant message
        msg_id = await self._save_message(conv_id, "assistant", reply)

        # graph logging
        if hasattr(self.neo4j, "save_interaction"):
            try:
                await self.neo4j.save_interaction(conv_id, request.message, reply)
            except Exception:
                pass

        return {"conversation_id": conv_id, "message_id": msg_id, "content": reply}
