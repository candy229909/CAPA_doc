# backend/app/services/rag_service.py
from typing import Optional, List, Dict, Any
import logging

try:
    from pymilvus import MilvusClient  # 可選
except Exception:
    MilvusClient = None

# DSPy 可用就用，不可用就優雅退回
try:
    from dspy_service import dspy_service  # 你的根目錄 dspy_service.py
except Exception:
    dspy_service = None

from app.services.law_service import LawService  # LLM 產生 Cypher + Neo4j 查詢

logger = logging.getLogger(__name__)

class GraphRAGService:
    """
    Graph-RAG 流程：
      1) 透過 LawService 產生 Cypher 並查 Neo4j（法條/條文）
      2) （可選）DSPy 產生法律建議
      3) （可選）Milvus 向量檢索作為補強（需提供 milvus_uri 與 embedding_model）

    注意：milvus 與 embedding_model 都是「可選」，不提供時不會啟用向量檢索。
    """
    def __init__(self, neo4j, milvus_uri: Optional[str] = None, embedding_model=None):
        self.neo4j = neo4j
        self.law = LawService(neo4j)
        self.milvus_client = MilvusClient(milvus_uri) if milvus_uri else None
        self.embedding_model = embedding_model
    
    def retrieve_context(self, query: str, collection_name: str, version_tag: str):
        """
        使用 Milvus 進行檢索，並結合結構化過濾。
        """
        if not self.milvus_client or self.embedding_model is None:
            return ""
        query_vector = self.embedding_model.encode([query]).tolist()
        # 使用 Milvus 的過濾器來確保只搜尋最新版本的法規
        search_params = {
        "metric_type": "COSINE",
        "filter": f"version_tag == '{version_tag}'", # 使用版本標籤來過濾
        "params": {"nprobe": 10} # HNSW/IVF_FLAT 的參數
        }
        results = self.milvus_client.search(
        collection_name=collection_name,
        data=query_vector,
        limit=5, # 取得最相似的 5 條
        search_params=search_params,
        output_fields=["text", "article_no", "version_tag"]
        )

        retrieved_docs = []
        for result in results:
            for hit in result:
                retrieved_docs.append(hit.entity.get('text'))

        # 將檢索到的文本合併為一個上下文
        context = "\n---\n".join(retrieved_docs)
        return context

    async def _build_response(self, question: str, hits: List[Dict[str, Any]]) -> Dict[str, Any]:
        documents = [
            {
                "statute_id": h.get("statute_id", ""),
                "title": h.get("title", ""),
                "content": h.get("text", "") or "",
            }
            for h in hits
        ]

        context = "\n\n".join(d["content"][:1200] for d in documents[:3] if d["content"])

        advice = None
        if dspy_service and context:
            try:
                pred = dspy_service.generate_legal_advice(
                    question=question,
                    context=context,
                    retrieved_docs=[d["content"] for d in documents if d["content"]],
                )
                advice = (
                    pred.model_dump()
                    if hasattr(pred, "model_dump")
                    else pred.dict()
                    if hasattr(pred, "dict")
                    else pred
                )
                logger.info("DSPy generated legal advice for question=%s", question)
            except Exception:
                logger.exception("DSPy generation failed: %s", e)
                advice = None

        return {
            "cypher": cypher,       # ← 不再取未定義的 res
            "documents": documents,
            "context": context,     # ← 上層可直接使用
            "advice": advice,
        }

    async def search(self, question: str, history: Optional[List[str]] = None) -> Dict[str, Any]:
        logger.info("GraphRAGService search question=%s", question)
        res = await self.law.query(question)
        hits = res.get("hits") or []
        cypher = res.get("cypher", "")
        logger.info("LawService returned %d hits", len(hits))
        return await self._build_response(question, hits, cypher)

    async def summarize_hits(self, question: str, hits: List[Dict[str, Any]]) -> Dict[str, Any]:
        logger.info(
            "GraphRAGService summarize_hits question=%s hits=%d", question, len(hits)
        )
        return await self._build_response(question, hits)
