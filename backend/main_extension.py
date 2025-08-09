from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import json, re, os, httpx
from neo4j import AsyncGraphDatabase

# 初始化擴充功能的 APIRouter
router = APIRouter()

# ---------- 法規查詢模組 (Neo4j 知識圖譜) ----------
class LawQuery(BaseModel):
    query: str

class LawHit(BaseModel):
    law: str
    statute_id: str
    title: Optional[str] = None
    text: Optional[str] = None

class LawQueryResponse(BaseModel):
    cypher: str
    hits: List[LawHit] = []

# 允許的節點標籤和關係（白名單）
ALLOWED_LABELS = {"Law", "Statute", "Article"}
ALLOWED_RELS   = {"HAS_ARTICLE"}

def _cypher_is_safe(cypher: str) -> bool:
    # 黑名單關鍵字：避免執行修改/刪除等危險操作
    disallowed = [" DELETE ", " MERGE ", " SET ", " CREATE ", " DROP ", ";", "//", "CALL dbms", "CALL apoc"]
    low = " " + cypher.lower() + " "
    if any(b in low for b in [w.lower() for w in disallowed]):
        return False
    # 僅允許特定標籤和關係（其餘一律視為不安全）
    for token in re.findall(r":[A-Za-z_]+", cypher):
        if token[1:] not in ALLOWED_LABELS:
            return False
    for token in re.findall(r"-\s*\[:([A-Za-z_]+)\]\s*-", cypher):
        if token not in ALLOWED_RELS:
            return False
    return True

async def _llm_generate_cypher(user_query: str) -> str:
    """向 LLM 請求生成只包含 Cypher 查詢的 JSON 字串。"""
    system_prompt = (
        "你是一個只輸出 JSON 的工具。"
        "根據使用者的法律查詢，產生一個安全的 Cypher 查詢，"
        "只能使用節點標籤 Law, Statute, Article 和關係 HAS_ARTICLE。"
        "回傳格式：{'cypher': '...'}，不要做多餘解釋。"
    )
    prompt = f"{system_prompt}\n使用者查詢：{user_query}\n請只輸出 JSON："
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                os.getenv("OLLAMA_HOST", "http://localhost:11434") + "/api/generate",
                json={"model": "gemma3n:e2b", "prompt": prompt, "stream": False}
            )
        if resp.status_code != 200:
            return ""
        txt = resp.json().get("response", "").strip()
        data = json.loads(txt) if txt else {}
        return data.get("cypher", "")
    except Exception:
        return ""

@router.post("/api/law/query", response_model=LawQueryResponse)
async def law_query(req: LawQuery):
    """LLM 產生 Cypher -> 安全檢查 -> 連接 Neo4j 執行查詢 -> 返回條文命中清單"""
    # 1) 透過 LLM 取得對應的 Cypher 查詢語句
    cypher = await _llm_generate_cypher(req.query)
    # 2) 檢查安全性；若不安全或無結果，用關鍵字模糊查詢作為保底
    if not cypher or not _cypher_is_safe(cypher):
        q = req.query.replace("'", " ")
        cypher = (
            "MATCH (l:Law)-[:HAS_ARTICLE]->(s:Statute) "
            f"WHERE toLower(s.title) CONTAINS toLower('{q}') "
            f"   OR toLower(s.text)  CONTAINS toLower('{q}') "
            "RETURN l.name AS law, s.id AS statute_id, s.title AS title, s.text AS text "
            "LIMIT 5"
        )
    # 3) 連接 Neo4j 執行查詢
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD", "password123")
    driver = AsyncGraphDatabase.driver(uri, auth=(user, pwd))
    hits: List[LawHit] = []
    try:
        async with driver.session() as session:
            result = await session.run(cypher)
            records = await result.to_list()
            for r in records:
                hits.append(LawHit(
                    law=r.get("law", "") or "",
                    statute_id=r.get("statute_id", "") or "",
                    title=r.get("title"),
                    text=r.get("text")
                ))
    except Exception as e:
        print(f"[law_query] Neo4j query error: {e}")
        raise HTTPException(status_code=500, detail="知識圖譜查詢失敗")
    finally:
        await driver.close()
    return LawQueryResponse(cypher=cypher, hits=hits)

# ---------- NLU 模組 (意圖與實體辨識) ----------
class NLURequest(BaseModel):
    query: str

class NLUResponse(BaseModel):
    intent: str
    entities: List[str]

# 常見法律相關關鍵詞及樣式，用於檢測一般法律查詢
LEGAL_KEYWORDS = [
    "勞基法", "勞動基準法", "民法", "刑法", "行政命令", "解釋令", "判決", "裁定",
    "工時", "加班", "特休", "請假", "資遣", "解雇", "停職", "薪資", "工資",
    "職災", "勞保", "勞退", "年資", "契約", "條文", "勞動",
]
LEGAL_PATTERNS = [
    r"第\s*\d+\s*條",         # e.g. "第 14 條"
    r"\d+\s*條",              # e.g. "14條"
    r"法第\s*\d+\s*條",       # e.g. "法第14條"
]

def _looks_like_legal(text: str) -> bool:
    t = text or ""
    if any(kw in t for kw in LEGAL_KEYWORDS):
        return True
    for pat in LEGAL_PATTERNS:
        if re.search(pat, t):
            return True
    return False

@router.post("/api/nlu", response_model=NLUResponse)
async def analyze_intent(req: NLURequest):
    """簡易自然語意圖分析：辨識是否為法律相關查詢"""
    text = (req.query or "").strip()
    print(f"[NLU] 收到輸入: {text}")
    # 直接匹配特殊關鍵詞的簡易規則
    if "育嬰" in text:
        return {"intent": "statute_query", "entities": ["育嬰"]}
    if "解雇" in text or "開除" in text:
        return {"intent": "termination_query", "entities": ["解雇"]}
    # 一般法律查詢：若包含法律術語或條文格式
    if _looks_like_legal(text):
        # 擷取可能的條號/法規做為實體（簡單去重）
        entities = []
        for pat in LEGAL_PATTERNS:
            entities += re.findall(pat, text)
        entities = list({e.strip() for e in entities})
        return {"intent": "legal_query", "entities": entities}
    # 其他皆視為未知意圖
    return {"intent": "unknown", "entities": []}

# ---------- （預留）RAG 知識檢索模組 ----------
class RAGRequest(BaseModel):
    question: str

class RAGResponse(BaseModel):
    context: str
    statute_id: str
    title: str

@router.post("/api/rag-search", response_model=RAGResponse)
async def rag_search(req: RAGRequest):
    """
    模擬 Retrieval-Augmented Generation 查詢：
    根據輸入問題返回相關法條的一段內容（示例），未來可接入實際向量資料庫。
    """
    print(f"[RAG] 收到問題: {req.question}")
    # TODO: 取得 question 的向量表示並查詢相似條文，這裡返回模擬結果
    return {
        "context": "（模擬法條內容節選）雇主不得無故終止契約…",
        "statute_id": "勞基法第14條",
        "title": "終止勞動契約"
    }

# ---------- Ethics 倫理檢查模組 ----------
class EthicsRequest(BaseModel):
    response: str

class EthicsResult(BaseModel):
    flagged: bool
    reason: str

@router.post("/api/ethics-check", response_model=EthicsResult)
async def ethics_check(req: EthicsRequest):
    """簡易內容審查：檢查回覆文字中是否包含不當詞彙"""
    print(f"[Ethics] 檢查回應: {req.response}")
    flagged_words = ["殺人", "毒品", "逃漏稅"]
    for word in flagged_words:
        if re.search(word, req.response):
            print(f"[Ethics] 偵測敏感詞: {word}")
            return {"flagged": True, "reason": f"敏感內容偵測：{word}"}
    return {"flagged": False, "reason": "OK"}

# ---------- 增強型聊天（NLU + 知識庫）模組 ----------
class ChatEnhancedRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    model: str = "gemma3n:e2b"
    use_rag: bool = False      # 是否使用向量檢索增強
    use_nlu: bool = False      # 是否強制使用 NLU 增強模式
    use_file_context: Optional[str] = "auto"  # 文件上下文使用策略

class ChatEnhancedResponse(BaseModel):
    final_answer: str
    # 相關法條來源資訊（可選）
    source_statute: Optional[str] = None
    source_title: Optional[str] = None
    source_law: Optional[str] = None
    # 回傳產生的 Cypher（主流程可用此查詢 Neo4j）
    cypher: Optional[str] = None
    # 除錯用：NLU 判斷的意圖與實體
    debug_intent: Optional[str] = None
    debug_entities: Optional[List[str]] = None

@router.post("/api/chat-enhanced", response_model=ChatEnhancedResponse)
async def chat_with_context(req: ChatEnhancedRequest):
    """
    增強型聊天接口：
    1) 進行 NLU 意圖分析，判斷是否需要法律知識庫增強
    2) 如需要，生成對應的 Cypher 查詢語句（示意）
    3) 返回初步回答文本（主流程會用實際查詢結果增強此回答）
    4) 執行倫理檢查並過濾不當回覆
    """
    text = (req.message or "").strip()
    print(f"[ChatEnhanced] 收到訊息: {text}")

    # Step 1: NLU 意圖判斷
    nlu_result = await analyze_intent(NLURequest(query=text))
    nlu = NLUResponse.parse_obj(nlu_result)
    print(f"[ChatEnhanced] 意圖: {nlu.intent}, 實體: {nlu.entities}")

    # 初始設置：假定無需知識查詢
    cypher: Optional[str] = None
    source_law = None
    source_statute = None
    source_title = None

    # Step 2: 根據意圖決定回覆模式
    if nlu.intent in {"legal_query", "statute_query", "termination_query"}:
        # 法律相關問題：生成對應 Cypher 查詢 (示範以第一個關鍵詞或整句為依據)
        q = (nlu.entities[0] if nlu.entities else text) or ""
        cypher = (
            "MATCH (l:Law)-[:HAS_ARTICLE]->(s:Statute)\n"
            f"WHERE toLower(s.title) CONTAINS toLower('{q}') OR toLower(s.text) CONTAINS toLower('{q}')\n"
            "RETURN l.name AS law, s.id AS statute_id, s.title AS title, s.text AS text\n"
            "LIMIT 5"
        )
        base_answer = (
            "我將根據下列查詢從法律知識圖譜檢索資訊：\n"
            "```\n" + cypher + "\n```\n\n"
            "（結果將提供相關法條節錄及來源）"
        )
        # 嘗試從關鍵字推斷法規名稱，以填充來源欄位（例如關鍵字含「勞基法」）
        if "勞基法" in q or "勞動基準法" in q:
            source_law = "勞動基準法"
        # 若有條文編號關鍵字，將第一個條文號做為 source_statute 示意
        if nlu.entities:
            source_statute = nlu.entities[0]
    else:
        # 非法律查詢問題的預設回答
        base_answer = "目前判斷這不是法律相關問題，我將以一般對話模式回答。"

    # Step 3: 對回答進行倫理檢查，過濾不當內容
    ethics_result = await ethics_check(EthicsRequest(response=base_answer))
    ethics = EthicsResult.parse_obj(ethics_result)
    if ethics.flagged:
        base_answer = f"⚠️ 回應被標記為不當：{ethics.reason}"

    # Step 4: 回傳結構化的回答（初步答案 + 來源標記 + 查詢語句等）
    return ChatEnhancedResponse(
        final_answer=base_answer,
        source_statute=source_statute or None,
        source_title=source_title or None,
        source_law=source_law or None,
        cypher=cypher,
        debug_intent=nlu.intent,
        debug_entities=nlu.entities,
    )
