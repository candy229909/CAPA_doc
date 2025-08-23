# app/routes/chat_router.py
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosed
from app.models import EnhancedChatRequest
from app.services.chat_service import ChatService
from app.services.nlu_service import NLUService
from app.services.ethics_service import EthicsService
from app.services.rag_service import GraphRAGService
import os
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# MILVUS_URI = os.getenv("MILVUS_URI")
# EMBEDDING_MODEL = websocket.app.state.embedding_model

# rag_service = GraphRAGService(websocket.app.state.neo4j, MILVUS_URI, EMBEDDING_MODEL)

router = APIRouter()

@router.post("/chat")
async def chat(request: Request, payload: EnhancedChatRequest):
    logger.info("HTTP chat request conversation_id=%s", payload.conversation_id)
    svc = ChatService(request.app.state.mongo, request.app.state.neo4j)
    return await svc.chat(payload)

@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection opened from %s", websocket.client)
    # Initialize services for this connection
    svc = ChatService(websocket.app.state.mongo, websocket.app.state.neo4j)
    # Pre-create a RAG service for potential knowledge retrieval
    rag_service = GraphRAGService(websocket.app.state.neo4j)
    try:
        while True:
            data = await websocket.receive_json()
            logger.debug("WebSocket received data: %s", data)

            # Extract fields from the incoming message
            user_message: str = data.get("content", "") or ""
            conv_id: Optional[str] = data.get("conversation_id")
            use_nlu_flag = data.get("use_nlu")
            model: str = data.get("model") or os.getenv("DEFAULT_OLLAMA_MODEL", "gemma3n:e2b")

            # Ensure there is a conversation and save the user's message
            conv_id = await svc._ensure_conversation(conv_id, user_message)
            await svc._save_message(conv_id, "user", user_message)

            # Step 1: NLU intent analysis
            try:
                nlu_result = NLUService.analyze(user_message)
                intent = nlu_result.get("intent", "general")
            except Exception as e:
                logger.exception("NLU analysis failed: %s", e)
                intent = "general"
                nlu_result = {"intent": intent}
            # Notify client of NLU stage
            await websocket.send_json({
                "status": "nlu",
                "message": f"intent={intent}",
                "payload": {},
            })

            # Decide whether to perform knowledge (law) augmentation
            use_knowledge = False
            if use_nlu_flag is True:
                use_knowledge = True
            elif use_nlu_flag is None:
                # Automatic decision based on NLU
                use_knowledge = intent != "general"

            context = ""
            if use_knowledge:
                # Step 2: Retrieve relevant legal context via LawService or RAG
                await websocket.send_json({
                    "status": "rag",
                    "message": "檢索相關法條中...",
                    "payload": {},
                })
                try:
                    rag_res = await rag_service.search(user_message)
                    docs = rag_res.get("documents") or []
                    if docs:
                        context = "\n\n".join(
                            d.get("content", "")[:800] for d in docs[:3] if d.get("content")
                        )
                    else:
                        await websocket.send_json({
                            "status": "need",
                            "message": "查無相關法條，請改寫問題或選擇一般回答。",
                            "payload": {},
                        })
                        fail_reply = "查無相關法條，請改寫問題或改用一般模式。"
                        await svc._save_message(conv_id, "assistant", fail_reply)
                        await websocket.send_json({
                            "status": "final",
                            "message": fail_reply,
                            "payload": {"conversation_id": conv_id},
                        })
                        continue
                except Exception as e:
                    logger.exception("Law retrieval failed: %s", e)
                    context = ""

            # Construct prompt for LLM
            if context:
                prompt = (
                    "以下為使用者問題與相關法條內容，請用繁體中文回答，並在需要時引用法條：\n\n[問題]\n"
                    + user_message
                    + "\n\n[法條內容]\n"
                    + context
                )
            else:
                prompt = f"使用者：{user_message}\n助理："

            # Step 3: LLM generation
            await websocket.send_json({
                "status": "llm",
                "message": "生成回答中...",
                "payload": {},
            })
            try:
                reply = await svc._call_ollama(model, prompt)
            except Exception as e:
                logger.exception("LLM generation failed: %s", e)
                reply = str(e)

            # Step 4: Ethics check
            await websocket.send_json({
                "status": "ethics",
                "message": "倫理檢查中...",
                "payload": {},
            })
            try:
                ethics_result = EthicsService.check(reply)
                if ethics_result.get("flagged"):
                    reply = "⚠️ 回覆內容包含敏感字詞，已過濾。"
            except Exception as e:
                logger.exception("Ethics check failed: %s", e)

            # Save assistant response to storage
            try:
                await svc._save_message(conv_id, "assistant", reply)
            except Exception as e:
                logger.exception("Failed to save assistant message: %s", e)

            # Log interaction to Neo4j if available
            if hasattr(svc.neo4j, "save_interaction"):
                try:
                    await svc.neo4j.save_interaction(conv_id, user_message, reply)
                except Exception:
                    pass

            # Step 5: Send final answer to client
            await websocket.send_json({
                "status": "final",
                "message": reply,
                "payload": {"conversation_id": conv_id},
            })
    except (WebSocketDisconnect, ConnectionClosed):
        logger.info("WebSocket disconnected from %s", websocket.client)
        return