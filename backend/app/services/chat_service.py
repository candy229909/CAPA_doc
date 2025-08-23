# app/services/chat_service.py
import os, httpx, uuid, logging, json
from datetime import datetime
from typing import Dict, Any, Optional
from app.services.nlu_service import NLUService
from app.services.ethics_service import EthicsService
from app.services.rag_service import GraphRAGService
from app.services.law_service import LawService
from app.database.db_mongo import MongoDB
from app.database.db_neo4j import Neo4jDB

logger = logging.getLogger(__name__)

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
        # Parse timeout from environment, falling back to a sensible default
        try:
            timeout_value = float(os.getenv("OLLAMA_TIMEOUT", "600"))
        except ValueError:
            timeout_value = 600.0
        # Use a single total timeout value; httpx requires a default or all four values
        http_timeout = httpx.Timeout(timeout_value)
        logger.info("Calling Ollama host=%s model=%s timeout=%s", host, model, timeout_value)
        try:
            async with httpx.AsyncClient(timeout=http_timeout) as client:
                # First attempt using the requested model
                async with client.stream(
                    "POST",
                    f"{host}/api/generate",
                    json={"model": model, "prompt": prompt, "stream": True},
                ) as resp:
                    # If the requested model is not found, attempt to fall back
                    if resp.status_code == 404:
                        try_model = os.getenv("OLLAMA_FALLBACK_MODEL", "gemma3n:e2b")
                        ms = await client.get(f"{host}/api/tags")
                        models = [
                            m.get("model")
                            for m in (ms.json().get("models", []) if ms.status_code == 200 else [])
                        ]
                        if try_model in models:
                            logger.warning(
                                "Model %s not found, falling back to %s", model, try_model
                            )
                            async with client.stream(
                                "POST",
                                f"{host}/api/generate",
                                json={"model": try_model, "prompt": prompt, "stream": True},
                            ) as fallback_resp:
                                fallback_resp.raise_for_status()
                                return await self._consume_stream(fallback_resp)
                        raise RuntimeError(
                            f"Ollama 模型 '{model}' 不存在且找不到 fallback 模型 '{try_model}'"
                        )
                    # Raise for any non-success status codes
                    resp.raise_for_status()
                    return await self._consume_stream(resp)
        except httpx.TimeoutException:
            logger.exception("Ollama request timeout")
            raise RuntimeError("與 Ollama 服務通訊逾時，請稍後再試")
        except httpx.HTTPError as e:
            logger.exception("Ollama HTTP error: %s", e)
            raise RuntimeError(f"呼叫 Ollama 服務失敗: {e}") from e

    async def _consume_stream(self, resp: httpx.Response) -> str:
        text = ""
        async for line in resp.aiter_lines():
            if not line:
                continue
            try:
                data = json.loads(line)
            except ValueError:
                continue
            text += data.get("response", "")
        return text.strip()
    
    async def _build_file_context(self, conversation_id: str, user_query: str,
                                  max_chars: int = 1200, top_k: int = 3) -> str:
        """
        從 MongoDB.documents 檢索最相關的切塊，合併成文件 context。
        依你先前的 mongo 方法：search_doc_chunks()
        """
        try:
            hits = await self.mongo.search_doc_chunks(conversation_id, user_query, top_k=top_k)
        except Exception:
            hits = []

        if not hits:
            return ""

        per = max_chars // max(1, len(hits))
        parts = []
        for h in hits:
            snippet = (h.get("text") or "")[:per]
            title = h.get("title") or "上傳文件"
            idx = h.get("idx", 0)
            parts.append(f"[來源: {title}｜段落#{idx}]\n{snippet}")
        return "\n---\n".join(parts)

    async def chat(self, request) -> Dict[str, Any]:
        conv_id = await self._ensure_conversation(request.conversation_id, request.message)
        await self._save_message(conv_id, "user", request.message)
        logger.info("Processing chat conversation_id=%s use_nlu=%s", conv_id, request.use_nlu)

        # NLU
        nlu_res = NLUService.analyze(request.message)
        intent = nlu_res.get("intent", "general")
        use_nlu = request.use_nlu if request.use_nlu is not None else (intent != "general")
        logger.info("NLU intent=%s", intent)

        law_context = ""
        need_flag = False

        # 法律問題 → 先查 Neo4j，再用 RAG 摘要
        if use_nlu:
            try:
                law = LawService(self.neo4j)
                law_res = await law.query(request.message)
                hits = law_res.get("hits") or []
                if hits:
                    rag = GraphRAGService(self.neo4j)  # 可選：改成 GraphRAGService(self.neo4j, MILVUS_URI, EMBEDDING_MODEL)
                    rag_res = await rag.summarize_hits(request.message, hits)
                    docs = rag_res.get("documents") or []
                    law_context = "\n\n".join(
                        d.get("content","")[:1200] for d in docs[:3] if d.get("content")
                    )
                else:
                    need_flag = True  # 查不到法條，標記提示
            except Exception as e:
                logger.exception("Law retrieval failed: %s", e)

        # 文件上下文（auto/always/never）
        try:
            use_fc = getattr(request, "use_file_context", "auto")
        except Exception:
            use_fc = "auto"
        # 文件片段（可選）
        file_context = ""
        if use_fc != "never":
            try:
                file_context = await self._build_file_context(conv_id, request.message)
            except Exception:
                file_context = ""

        # 組 Prompt（單一路徑，不要覆蓋 reply）
        base = "以下為使用者問題與相關內容，請優先根據提供的內容回答；若內容不足，再以一般常識補充並標註不確定性。請使用繁體中文。"
        sections = [f"[問題]\n{request.message}"]
        if law_context:
            sections.append(f"[法條內容]\n{law_context}")
        if file_context:
            sections.append(f"[文件內容]\n{file_context}")
        prompt = base + "\n\n" + "\n\n".join(sections)

        # 若完全沒有 context 且 use_nlu 為真但查無法條，可給提示性回覆或直接一般回答
        if not law_context and not file_context and use_nlu and need:
            prompt = (
                "查無可引用的法條內容，請根據一般常識先給出初步方向，並明確告知仍需確認相關條文；"
                "回答使用繁體中文。\n\n" + prompt
            )

        try:
            reply = await self._call_ollama(request.model, prompt)
        except RuntimeError as e:
            logger.error("Chat generation failed: %s", e)
            reply = str(e)

        ethics = EthicsService.check(reply)
        if ethics.get("flagged"):
            reply = "⚠️ 回覆內容包含敏感字詞，已過濾。"

        msg_id = await self._save_message(conv_id, "assistant", reply)

        if hasattr(self.neo4j, "save_interaction"):
            try:
                await self.neo4j.save_interaction(conv_id, request.message, reply)
            except Exception:
                pass

        return {
            "conversation_id": conv_id,
            "message_id": msg_id,
            "content": reply,
            "need": need,
        }

