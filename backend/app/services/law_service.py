# app/services/law_service.py
import re, json, os, httpx, logging
from app.database.db_neo4j import Neo4jDB

logger = logging.getLogger(__name__)

ALLOWED_LABELS = {"Law", "Statute", "Article"}
ALLOWED_RELS = {"HAS_ARTICLE"}

# --- Added: 解析「勞基法第三條」→（勞動基準法, 第3條） ---
CHINESE_NUM = {"零":0,"〇":0,"○":0,"一":1,"二":2,"兩":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10}
def zh_num_to_int(s: str) -> int:
    s = (s or "").strip()
    if not s:
        return 0
    if s.isdigit():
        return int(s)
    # 極簡中文數字（支援到數十）
    total, last = 0, 0
    for ch in reversed(s):
        if ch == "十":
            total += (last or 1) * 10
            last = 0
        else:
            last = CHINESE_NUM.get(ch, 0)
            total += last
            last = 0
    return total or 0

def parse_law_article_query(q: str):
    """輸入『勞基法第三條』『勞動基準法第3條』→ (law, '第3條', 3)"""
    if not q:
        return None
    q = q.strip()
    # 同義詞標準化
    if "勞基法" in q and "勞動基準法" not in q:
        q = q.replace("勞基法", "勞動基準法")
    m = re.search(r"(勞動基準法)(?:第\s*([0-9一二三四五六七八九十〇零○]+)\s*條)?", q)
    if m:
        law = m.group(1)
        num_s = (m.group(2) or "").strip()
        if num_s:
            n = zh_num_to_int(num_s)
            return law, f"第{n}條", n
        return law, None, 0
    return None


def _cypher_is_safe(cypher: str) -> bool:
    disallowed = [" DELETE ", " MERGE ", " SET ", " CREATE ", " DROP ", ";", "//", "CALL dbms", "CALL apoc"]
    low = " " + (cypher or "").upper() + " "
    if any(b in low for b in disallowed):
        return False
    for token in re.findall(r":[A-Za-z_]+", cypher or ""):
        if token[1:] not in ALLOWED_LABELS:
            return False
    for token in re.findall(r"-\s*\[:([A-Za-z_]+)\]\s*-", cypher or ""):
        if token not in ALLOWED_RELS:
            return False
    return True

async def _llm_generate_cypher(user_query: str) -> str:
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
                json={"model": os.getenv("DEFAULT_OLLAMA_MODEL", "gemma3n:e2b"), "prompt": prompt, "stream": False}
            )
        if resp.status_code != 200:
            return ""
        txt = resp.json().get("response", "").strip()
        data = json.loads(txt) if txt else {}
        return data.get("cypher", "")
    except Exception:
        return ""

class LawService:
    def __init__(self, neo4j: Neo4jDB):
        self.neo4j = neo4j

    async def query(self, payload):
        """智慧查詢：先直攻條號命中→再走 LLM 產生 Cypher→最後關鍵字 fallback"""
        user_query = payload.get("query") if isinstance(payload, dict) else str(payload)

        # 1) 解析條號（勞基法第三條）
        parsed = parse_law_article_query(user_query)
        if parsed:
            law, art_str, _ = parsed
            if art_str:
                # 1-1) 關聯路徑（相容多種關係/欄位/標籤）
                cypher = (
                    "MATCH (l:Law)-[r]->(a) "
                    "WHERE l.name CONTAINS $law "
                    "AND type(r) IN ['HAS_ARTICLE','HAS_STATUTE','CONTAINS','INCLUDES'] "
                    "AND ( (exists(a.article_no) AND a.article_no = $art) "
                    "   OR toString(a.id)    CONTAINS $art "
                    "   OR toString(a.title) CONTAINS $art "
                    "   OR toString(a.name)  CONTAINS $art ) "
                    "RETURN l.name AS law, "
                    "coalesce(a.article_no, toString(a.id)) AS article_no, "
                    "coalesce(a.title, a.name) AS title, "
                    "coalesce(a.text, a.content) AS text, "
                    "coalesce(toString(a.id), a.article_no) AS statute_id "
                    "LIMIT 5"
                )
                rows = await self.neo4j.run_read_query(cypher, {"law": law, "art": art_str})
                if rows:
                    return {"cypher": cypher, "hits": rows}

                # 1-2) 極寬鬆節點屬性 fallback（不依賴關係/標籤）
                cypher2 = (
                    "MATCH (a) "
                    "WHERE (toLower(toString(a.law_name)) CONTAINS toLower($law) "
                    "   OR toLower(toString(a.title))    CONTAINS toLower($law) "
                    "   OR toLower(toString(a.name))     CONTAINS toLower($law)) "
                    "AND ( (exists(a.article_no) AND a.article_no = $art) "
                    "   OR toLower(toString(a.title)) CONTAINS toLower($art) "
                    "   OR toLower(toString(a.name))  CONTAINS toLower($art) ) "
                    "RETURN coalesce(toString(a.law_name),'') AS law, "
                    "coalesce(a.article_no, toString(a.id)) AS article_no, "
                    "coalesce(a.title, a.name) AS title, "
                    "coalesce(a.text,  a.content) AS text, "
                    "coalesce(toString(a.id), a.article_no) AS statute_id "
                    "LIMIT 5"
                )
                rows2 = await self.neo4j.run_read_query(cypher2, {"law": law, "art": art_str})
                if rows2:
                    return {"cypher": cypher2, "hits": rows2}

        # 2) 走原本 LLM 產生 Cypher（若你有設定）
        try:
            cypher = await _llm_generate_cypher(user_query)  # 你檔案原本就有的函式
            logger.debug("Generated cypher: %s", cypher)
        except Exception:
            cypher = ""

        # 3) 關鍵字 fallback（也放寬 label/rel/欄位）
        if not cypher or not _cypher_is_safe(cypher):
            logger.warning("Using fallback keyword search for query: %s", user_query)
            q = (user_query or "").replace("'", " ")
            cypher = (
                "MATCH (l:Law)-[r]->(a) "
                "WHERE type(r) IN ['HAS_ARTICLE','HAS_STATUTE','CONTAINS','INCLUDES'] "
                "AND ( toLower(toString(a.title)) CONTAINS toLower('{q}') "
                "   OR toLower(toString(a.text))  CONTAINS toLower('{q}') "
                "   OR toLower(toString(a.name))  CONTAINS toLower('{q}') ) "
                "RETURN l.name AS law, "
                "coalesce(toString(a.id), a.article_no) AS statute_id, "
                "coalesce(a.title, a.name) AS title, "
                "coalesce(a.text, a.content) AS text "
                "LIMIT 5"
            )

        rows = await self.neo4j.run_read_query(cypher)
        logger.info("LawService hits=%d", len(rows) if rows else 0)
        return {"cypher": cypher, "hits": rows or []}
