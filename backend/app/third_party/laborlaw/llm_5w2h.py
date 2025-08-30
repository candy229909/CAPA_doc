import json
import httpx
from typing import Dict, Any, List
from loguru import logger
from .config import settings

# =====================
# Prompts
# =====================
PROMPT_5W2H = (
    "你是一位法律文本助理。請從以下文本提取 5W2H 與關鍵詞與法條參照，只輸出 JSON，不要多餘說明。"
    "JSON 結構：{"
    "  \"who\": [\"主體或角色\"],"
    "  \"what\": \"發生了什麼重點事件\","
    "  \"when\": \"關鍵時間（可保留原文格式）\","
    "  \"where\": \"主要地點（可空）\","
    "  \"why\": \"原因與爭點（可空）\","
    "  \"how\": \"處理方式/流程（可空）\","
    "  \"how_much\": \"金額/數量（若無留空）\","
    "  \"law_refs\": [\"可能引用之法條或條號（如 勞基法第XX條）\"],"
    "  \"keywords\": [\"3-10 個關鍵詞\"],"
    "  \"confidence\": 0.0-1.0"
    "}。務必輸出有效 JSON。"
)

PROMPT_SVO = (
    "請從以下文本抽取主詞-動詞-受詞三元組（SVO），僅輸出 JSON。"
    "結構：{"
    "  \"triples\": ["
    "    {\"subj\": [\"主詞1\", \"主詞2?\"], \"verb\": \"動詞\", \"obj\": [\"受詞1\", \"受詞2?\"]},"
    "    ..."
    "  ]"
    "}。若無可留空陣列。"
)

PROMPT_KEYWORDS = (
    "僅從以下文本提取 5-12 個關鍵詞（降噪、用繁中、不要重複），只輸出 JSON：{"
    "  \"keywords\": [\"關鍵詞1\", \"關鍵詞2\", ...]"
    "}"
)

# =====================
# Helpers
# =====================
async def _ollama_call(prompt: str, text: str, *, model: str, expect_json: bool = True) -> Dict[str, Any]:
    payload = {
        "model": model,
        "prompt": prompt + "文本如下：" + text,
        "stream": False,
        "options": {"temperature": 0},
    }
    if expect_json:
        payload["format"] = "json"
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(f"{settings.OLLAMA_HOST}/api/generate", json=payload)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Ollama API error: {e}")
        return {}
    except Exception as e:
        logger.error(f"Ollama call failed: {e}")
        return {}
    resp = data.get("response", "{}")
    if expect_json:
        try:
            return json.loads(resp)
        except Exception:
            s = resp
            l = s.find('{'); r = s.rfind('}')
            if l != -1 and r != -1 and l < r:
                try:
                    return json.loads(s[l:r+1])
                except Exception:
                    logger.warning("JSON slice parse failed")
            return {}
    else:
        return {"text": resp}

def _norm_list(val) -> List[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    return [str(val).strip()] if str(val).strip() else []

# =====================
# Public APIs
# =====================
async def ask_ollama_5w2h(text: str) -> Dict[str, Any]:
    data = await _ollama_call(PROMPT_5W2H, text, model=settings.OLLAMA_MODEL, expect_json=True)
    return {
        "who": _norm_list(data.get("who")),
        "what": data.get("what", "") or "",
        "when": data.get("when", "") or "",
        "where": data.get("where", "") or "",
        "why": data.get("why", "") or "",
        "how": data.get("how", "") or "",
        "how_much": data.get("how_much", "") or "",
        "law_refs": _norm_list(data.get("law_refs")),
        "keywords": _norm_list(data.get("keywords")),
        "confidence": float(data.get("confidence", 0.0) or 0.0),
    }

async def ask_ollama_svo(text: str) -> Dict[str, Any]:
    data = await _ollama_call(PROMPT_SVO, text, model=settings.OLLAMA_MODEL, expect_json=True)
    triples = data.get("triples", [])
    out: List[Dict[str, Any]] = []
    if isinstance(triples, list):
        for t in triples:
            if not isinstance(t, dict):
                continue
            subj = _norm_list(t.get("subj"))
            obj  = _norm_list(t.get("obj"))
            verb = (t.get("verb") or "").strip()
            if subj and obj and verb:
                out.append({"subj": subj, "verb": verb, "obj": obj})
    return {"triples": out}

async def ensemble_keywords(text: str, base: List[str]) -> List[str]:
    # 多模型投票排序關鍵字
    models = getattr(settings, "MODELS", [settings.OLLAMA_MODEL])
    votes: Dict[str, int] = {}
    for kw in base:
        k = kw.strip()
        if not k:
            continue
        votes[k] = votes.get(k, 0) + 2  # 基準模型給 2 票
    for m in models:
        try:
            data = await _ollama_call(PROMPT_KEYWORDS, text, model=m, expect_json=True)
            for kw in _norm_list(data.get("keywords")):
                votes[kw] = votes.get(kw, 0) + 1
        except Exception as e:
            logger.warning(f"keywords from {m} failed: {e}")
            continue
    ranked = sorted(votes.items(), key=lambda x: (-x[1], x[0]))
    return [k for k, _ in ranked][:12]

async def ask_ollama_qa(question: str, contexts: List[Dict[str, Any]]) -> Dict[str, Any]:
    # 將最相關的 chunk 摘要成 context
    ctx_blocks = []
    for i, c in enumerate(contexts):
        txt = (c.get("text") or "")[:800]
        cid = c.get("chunk_id")
        ctx_blocks.append(f"[來源{i+1} chunk_id={cid}]\n{txt}")
    context_str = "".join(ctx_blocks) if ctx_blocks else "（無）"

    qa_prompt = (
        "你是一位熟悉臺灣《勞動基準法》的助理。根據下列【已檢索到的相關內容】，"
        "以繁體中文回答使用者的問題。若無法在內容中找到答案，請誠實說明並給出查找方向。"
        "務必在答案結尾列出你使用到的來源 chunk_id（例如：來源：#1, #3）。"
        f"【問題】{question}\n"
        f"【已檢索到的相關內容】{context_str}\n"
        "【回答】"
    )

    payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": qa_prompt,
        "stream": False,
        "options": {"temperature": 0.2},
    }
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{settings.OLLAMA_HOST}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
            answer = (data.get("response") or "").strip()
    except Exception as e:
        logger.warning(f"Ollama QA failed: {e}")
        answer = ""
    sources = [{"chunk_id": c.get("chunk_id"), "snippet": (c.get("text") or "")[:120]} for c in contexts]
    return {"answer": answer, "sources": sources}