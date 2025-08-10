# app/services/law_service.py
import re, json, os, httpx
from app.database.db_neo4j import Neo4jDB

ALLOWED_LABELS = {"Law", "Statute", "Article"}
ALLOWED_RELS = {"HAS_ARTICLE"}

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

    async def query(self, user_query: str) -> dict:
        cypher = await _llm_generate_cypher(user_query)
        if not cypher or not _cypher_is_safe(cypher):
            q = (user_query or "").replace("'", " ")
            cypher = (
                "MATCH (l:Law)-[:HAS_ARTICLE]->(s:Statute) "
                f"WHERE toLower(s.title) CONTAINS toLower('{q}') OR toLower(s.text) CONTAINS toLower('{q}') "
                "RETURN l.name AS law, s.id AS statute_id, s.title AS title, s.text AS text "
                "LIMIT 5"
            )
        rows = await self.neo4j.run_read_query(cypher)
        return {"cypher": cypher, "hits": rows or []}
