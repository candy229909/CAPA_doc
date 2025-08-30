from neo4j import GraphDatabase, Query
from typing import List, Dict, Any, Optional, Tuple
from loguru import logger
from .config import settings
import jieba
import regex as re

# 轉型工具：把 None/字串/清單 轉成乾淨的字串清單
def to_list_str(val) -> List[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        s = re.sub(r"[，,、;；]", " ", val)
        return [p for p in s.split() if p.strip()]
    return []

class Neo4jClient:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )

    def close(self):
        self.driver.close()

    def ensure_constraints(self):
        queries = [
            Query("CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.doc_id IS UNIQUE"),
            Query("CREATE CONSTRAINT IF NOT EXISTS FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE"),
            Query("CREATE CONSTRAINT IF NOT EXISTS FOR (k:Keyword) REQUIRE k.name IS UNIQUE"),
            Query("CREATE CONSTRAINT IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE"),
            Query("CREATE FULLTEXT INDEX chunkTextIndex IF NOT EXISTS FOR (c:Chunk) ON EACH [c.text]"),
        ]
        with self.driver.session(database=settings.NEO4J_DB) as s:
            for q in queries:
                s.run(q)

    def import_doc(self, doc_id: str, name: str, chunks: List[Dict[str, Any]], doc_type: Optional[str] = None):
        self.ensure_constraints()
        with self.driver.session(database=settings.NEO4J_DB) as s:
            s.run(
                Query("MERGE (d:Document {doc_id:$doc_id}) SET d.name=$name, d.doc_type=$doc_type, d.updated_at=timestamp()"),
                {"doc_id": doc_id, "name": name, "doc_type": doc_type}
            )

            upsert_chunk_q = Query(
                """
                MERGE (d:Document {doc_id:$doc_id})
                MERGE (c:Chunk {chunk_id:$chunk_id})
                SET c.doc_id=$doc_id, c.idx=$idx, c.text=$text,
                    c.who=$who, c.what=$what, c.when=$when, c.where=$where,
                    c.why=$why, c.how=$how, c.how_much=$how_much, c.law_refs=$law_refs, c.confidence=$confidence
                MERGE (d)-[:HAS_CHUNK]->(c)
                """
            )
            link_kw_q = Query(
                """
                MERGE (k:Keyword {name:$name})
                WITH k
                MATCH (c:Chunk {chunk_id:$chunk_id})
                MERGE (c)-[:HAS_KEYWORD]->(k)
                """
            )
            mention_entity_q = Query(
                """
                MERGE (e:Entity {name:$name})
                WITH e
                MATCH (c:Chunk {chunk_id:$chunk_id})
                MERGE (c)-[:MENTIONS]->(e)
                """
            )
            act_q = Query(
                """
                MERGE (s:Entity {name:$subj})
                MERGE (o:Entity {name:$obj})
                MERGE (s)-[r:ACTS_ON {verb:$verb, doc_id:$doc_id, chunk_id:$chunk_id}]->(o)
                ON CREATE SET r.count = 1
                ON MATCH SET r.count = coalesce(r.count,0) + 1
                """
            )

            for ch in chunks:
                who_list = to_list_str(ch.get("who"))
                law_list = to_list_str(ch.get("law_refs"))
                kw_list  = to_list_str(ch.get("keywords"))
                idx_val = int(ch.get("idx", 0) or 0)
                text_val = str(ch.get("text", "") or "")

                s.run(
                    upsert_chunk_q,
                    {
                        "doc_id": doc_id,
                        "chunk_id": ch["chunk_id"],
                        "idx": idx_val,
                        "text": text_val,
                        "who": ", ".join(who_list),
                        "what": str(ch.get("what", "") or ""),
                        "when": str(ch.get("when", "") or ""),
                        "where": str(ch.get("where", "") or ""),
                        "why": str(ch.get("why", "") or ""),
                        "how": str(ch.get("how", "") or ""),
                        "how_much": str(ch.get("how_much", "") or ""),
                        "law_refs": ", ".join(law_list),
                        "confidence": float(ch.get("confidence", 0.0) or 0.0),
                    }
                )
                # 關鍵字
                for kw in kw_list:
                    s.run(link_kw_q, {"name": kw, "chunk_id": ch["chunk_id"]})
                # SVO
                triples = ch.get("svo") or []
                if isinstance(triples, dict) and "triples" in triples:
                    triples = triples["triples"]
                if isinstance(triples, list):
                    for t in triples:
                        if not isinstance(t, dict):
                            continue
                        subj = to_list_str(t.get("subj"))
                        obj  = to_list_str(t.get("obj"))
                        verb = (t.get("verb") or "").strip()
                        if not verb:
                            continue
                        for ent in set(subj + obj):
                            s.run(mention_entity_q, {"name": ent, "chunk_id": ch["chunk_id"]})
                        for s_name in subj:
                            for o_name in obj:
                                s.run(act_q, {
                                    "subj": s_name,
                                    "obj": o_name,
                                    "verb": verb,
                                    "doc_id": doc_id,
                                    "chunk_id": ch["chunk_id"],
                                })
        logger.info(f"Imported document {doc_id} with {len(chunks)} chunks")

    def search_chunks(self, question: str, top_k: int = 6) -> Tuple[List[Dict[str, Any]], List[str]]:
        self.ensure_constraints()
        toks = [t.strip() for t in jieba.cut(question) if t.strip()]
        chunks: List[Dict[str, Any]] = []
        used_kws: List[str] = []
        with self.driver.session(database=settings.NEO4J_DB) as s:
            if toks:
                data = s.run(Query("MATCH (k:Keyword) WHERE k.name IN $names RETURN k.name AS name"), {"names": toks}).data()
                used_kws = [r["name"] for r in data]
            if used_kws:
                data = s.run(Query(
                    """
                    UNWIND $kws AS kw
                    MATCH (c:Chunk)-[:HAS_KEYWORD]->(k:Keyword {name:kw})
                    WITH c, count(*) AS score
                    ORDER BY score DESC
                    RETURN c{ .chunk_id, .idx, .text, score: toFloat(score) } AS item
                    LIMIT $top_k
                    """
                ), {"kws": used_kws, "top_k": top_k}).data()
                chunks = [d["item"] for d in data]
            if len(chunks) < top_k:
                more = s.run(Query(
                    """
                    CALL db.index.fulltext.queryNodes('chunkTextIndex', $q) YIELD node, score
                    RETURN node{ .chunk_id, .idx, .text, score: toFloat(score) } AS item
                    ORDER BY score DESC LIMIT $lim
                    """
                ), {"q": question, "lim": top_k}).data()
                seen = {c["chunk_id"] for c in chunks}
                for d in more:
                    it = d["item"]
                    if it["chunk_id"] not in seen:
                        chunks.append(it)
                        seen.add(it["chunk_id"])
        chunks = sorted(chunks, key=lambda x: x.get("score", 0.0), reverse=True)[:top_k]
        return chunks, used_kws