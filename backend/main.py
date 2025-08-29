# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database.db_mongo import MongoDB
from app.database.db_neo4j import Neo4jDB
import logging, os

from app.routes.conversation_router import router as conversation_router
from app.routes.file_router import router as file_router
from app.routes.chat_router import router as chat_router
from app.routes.health_router import router as health_router
from app.routes.law_router import router as law_router
from app.routes.nlu_router import router as nlu_router
from app.routes.rag_router import router as rag_router
from app.routes.ethics_router import router as ethics_router
from app.routes.template_filter_router import router as template_filter_router
from app.routes.filter_public_router import router as filter_public_router
from app.third_party.laborlaw.main import app as laborlaw_app
from app.milvus_setup import connect_auto, ensure_collection, connect_server
from contextlib import asynccontextmanager

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

MONGODB_URL = "mongodb://mongo:27017/chatdb"
MONGODB_DB = "chatdb"
NEO4J_URI = "bolt://neo4j:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password123"

MILVUS_COLL = os.getenv("MILVUS_COLLECTION", "docs")
VECTOR_DIM  = int(os.getenv("VECTOR_DIM", "768"))
METRIC      = os.getenv("MILVUS_METRIC", "COSINE")

@asynccontextmanager
async def lifespan(app: FastAPI):
    connect_server()  # 這裡面會用 MilvusClient(DB 路徑) 啟動 Lite
    ensure_collection(
        name=MILVUS_COLL,
        dim=VECTOR_DIM,
        metric=METRIC,
        text_field="text",
        meta_field="meta",
        emb_field="vector",
        auto_id=True,
    )
    yield
    
def create_app() -> FastAPI:
    app = FastAPI(title="CAPA_DOC API", version="1.0.0", lifespan=lifespan)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # DB instances on app.state
    app.state.mongo = MongoDB(MONGODB_URL, MONGODB_DB)
    app.state.neo4j = Neo4jDB(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    @app.on_event("startup")
    async def _startup():
        logger.info("Starting up backend service")
        await app.state.mongo.connect()
        await app.state.neo4j.connect()
        if hasattr(app.state.neo4j, "ensure_constraints"):
            await app.state.neo4j.ensure_constraints()

    @app.on_event("shutdown")
    async def _shutdown():
        logger.info("Shutting down backend service")
        await app.state.mongo.close()
        await app.state.neo4j.close()

    # Register blueprints (routers)
    app.include_router(conversation_router, prefix="/api/conversations", tags=["conversations"])
    # File upload router: expose '/api/upload-document' instead of '/api/file_uploads/upload-document'
    app.include_router(file_router,         prefix="/api", tags=["files"])
    app.include_router(chat_router,         prefix="/api/chat", tags=["chat"])
    app.include_router(health_router,       prefix="/api/health", tags=["health"])
    app.include_router(law_router,          prefix="/api/law_advice", tags=["law"])
    app.include_router(nlu_router,          prefix="/api/nlu", tags=["nlu"])
    app.include_router(rag_router,          prefix="/api/rag", tags=["rag"])
    app.include_router(ethics_router,       prefix="/api/ethics", tags=["ethics"])
    app.include_router(filter_public_router)
    app.include_router(template_filter_router, prefix="/api/template_filter", tags=["template"])

    @app.get("/")
    async def root():
        return {"message": "CAPA_DOC backend is running"}

    # === RAG-Lite integration (inline) start ===
    # 以 APIRouter 方式在 /rag-lite 底下提供 Milvus Lite + 本機 OpenAI 相容 LLM 的 RAG 端點
    # 不新增檔案、避免與現有路由衝突；若要改掛載路徑，設環境變數 RAG_PREFIX=""。
    import os
    from typing import List, Optional, Dict, Any
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel, Field
    from pymilvus import Collection

    from app.milvus_setup import connect_auto
    from app.vectorizers import embed_text
    from app.openai_local import openai_chat_llm

    RAG_PREFIX = os.getenv("RAG_PREFIX", "/rag-lite")
    COLLECTION_NAME = os.getenv("MILVUS_COLLECTION", "docs")
    VECTOR_DIM = int(os.getenv("VECTOR_DIM", "768"))
    MILVUS_METRIC = os.getenv("MILVUS_METRIC", "COSINE")

    connect_auto()
    _collection: Collection = ensure_collection(
        name=COLLECTION_NAME,
        dim=VECTOR_DIM,
        metric=MILVUS_METRIC,
        text_field="text",
        meta_field="meta",
        emb_field="embedding",
        auto_id=True
    )

    class IngestItem(BaseModel):
        text: str = Field(..., description="本文")
        meta: Dict[str, Any] = Field(default_factory=dict, description="任意 JSON metadata")

    class IngestReq(BaseModel):
        items: List[IngestItem]

    class ChatReq(BaseModel):
        message: str
        model: Optional[str] = Field(default=None, description="模型名（覆寫 OPENAI_MODEL）")
        top_k: int = Field(default=6, description="合併後送入 LLM 的段落數上限")
        use_milvus: bool = True
        use_neo4j: bool = False
        system_prompt: Optional[str] = None

    class _SimpleRAG:
        def __init__(self, collection: Collection):
            self.collection = collection
            self.llm_fn = lambda sys, hist, content, rag_chunks, model: openai_chat_llm(
                sys, hist, content, rag_chunks, model or os.getenv("OPENAI_MODEL","llama3.1:8b")
            )
            self.openai_model_default = os.getenv("OPENAI_MODEL","llama3.1:8b")

        def _search(self, query: str, top_k: int = 5):
            qemb = embed_text(query)
            if len(qemb) != VECTOR_DIM:
                raise ValueError(f"查詢向量維度={len(qemb)} 不等於設定的 VECTOR_DIM={VECTOR_DIM}")
            res = self.collection.search(
                data=[qemb],
                anns_field="embedding",
                param={"metric_type": MILVUS_METRIC, "params": {"nprobe": 10}},
                limit=top_k,
                output_fields=["text", "meta"]
            )
            out = []
            if res:
                for hit in res[0]:
                    out.append({"text": hit.entity.get("text"), "meta": hit.entity.get("meta"), "score": float(hit.distance)})
            return out

        def execute(self, content: str, model: Optional[str], system_prompt: Optional[str], use_milvus: bool, use_neo4j: bool, top_k_merge: int, append_to_history: bool):
            rag_chunks = []
            if use_milvus:
                rag_chunks = self._search(content, top_k=top_k_merge)
            sys_msg = system_prompt or "You are a helpful RAG assistant."
            history = []
            answer = self.llm_fn(sys_msg, history, content, rag_chunks, model or self.openai_model_default)
            return {"answer": answer, "chunks": rag_chunks}

    _rag = _SimpleRAG(_collection)
    _router_rl = APIRouter(prefix=RAG_PREFIX, tags=["rag-lite"])

    @_router_rl.get("/health")
    def rag_health():
        return {
            "ok": True,
            "collection": _collection.name,
            "dim": VECTOR_DIM,
            "metric": MILVUS_METRIC,
            "openai_base_url": os.getenv("OPENAI_BASE_URL"),
            "openai_model": os.getenv("OPENAI_MODEL")
        }

    @_router_rl.post("/ingest")
    def rag_ingest(req: IngestReq):
        try:
            texts = [it.text for it in req.items]
            metas = [it.meta for it in req.items]
            embs = [embed_text(t) for t in texts]
            for i, e in enumerate(embs):
                if len(e) != VECTOR_DIM:
                    raise HTTPException(status_code=400, detail=f"第 {i} 筆向量維度={len(e)}, 需為 {VECTOR_DIM}")
            mr = _collection.insert([texts, metas, embs])
            _collection.flush()
            return {"ok": True, "inserted": mr.insert_count, "pks": list(mr.primary_keys)}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Ingest 失敗: {e}")

    @_router_rl.post("/chat")
    def rag_chat(req: ChatReq):
        try:
            out = _rag.execute(
                content=req.message,
                model=req.model,
                system_prompt=req.system_prompt,
                use_milvus=req.use_milvus,
                use_neo4j=req.use_neo4j,
                top_k_merge=req.top_k,
                append_to_history=True,
            )
            return out
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Chat 失敗: {e}")

    app.include_router(_router_rl)
    # === RAG-Lite integration (inline) end ===
    app.mount("/laborlaw", laborlaw_app)

    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
