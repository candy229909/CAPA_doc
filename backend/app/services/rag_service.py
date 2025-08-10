# backend/app/services/rag_service.py
from typing import Optional, List, Dict, Any

# DSPy 可用就用，不可用就優雅退回
try:
    from dspy_service import dspy_service  # 你的根目錄 dspy_service.py
except Exception:
    dspy_service = None

from app.services.law_service import LawService  # LLM 產生 Cypher + Neo4j 查詢

class GraphRAGService:
    """
    Graph-RAG 流程：
      1) 用 LLM 產生安全的 Cypher
      2) 查 Neo4j 取得條文
      3) （可選）把條文傳給 DSPy 產生法律建議/總結
    完全不使用向量或 sentence_transformers。
    """
    def __init__(self, neo4j):
        self.law = LawService(neo4j)

    async def search(self, question: str, history: Optional[List[str]] = None) -> Dict[str, Any]:
        # 1) 產生 Cypher 並查 Neo4j
        res = await self.law.query(question)
        hits = res.get("hits") or []

        # 2) 整理文件與 context
        documents = [{
            "statute_id": h.get("statute_id", ""),
            "title": h.get("title", ""),
            "content": h.get("text", "") or ""
        } for h in hits]

        context = "\n\n".join(d["content"][:1200] for d in documents[:3] if d["content"])

        # 3) DSPy 建議（若可用）
        advice = None
        if dspy_service:
            try:
                pred = dspy_service.generate_legal_advice(
                    question=question,
                    context=context,
                    retrieved_docs=[d["content"] for d in documents if d["content"]],
                )
                advice = (
                    pred.model_dump() if hasattr(pred, "model_dump")
                    else pred.dict() if hasattr(pred, "dict")
                    else pred
                )
            except Exception:
                advice = None

        return {
            "cypher": res.get("cypher", ""),
            "documents": documents,
            "advice": advice,      # 可選：前端要顯示的結構（由 DSPy 回傳）
        }
