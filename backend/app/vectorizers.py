import os
from typing import List
from sentence_transformers import SentenceTransformer

_EMB_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")

_model = None
def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(_EMB_MODEL_NAME, device="cpu")
    return _model

def embed_text(text: str) -> List[float]:
    text = (text or "").strip()
    if not text:
        return []
    if os.getenv("E5_PROMPT_PREFIX", "1") == "1":
        text = f"query: {text}"
    v = _get_model().encode(text, normalize_embeddings=os.getenv("EMB_NORMALIZE","1")=="1")
    return v.tolist()
