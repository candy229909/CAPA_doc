from pydantic import BaseModel
from typing import List, Optional

class LawQuery(BaseModel):
    query: str

class LawHit(BaseModel):
    law: str; statute_id: str; title: Optional[str] = None; text: Optional[str] = None

class LawQueryResponse(BaseModel):
    cypher: str; hits: List[LawHit] = []

class NLURequest(BaseModel):
    query: str

class NLUResponse(BaseModel):
    intent: str; entities: List[str] = []

class RAGRequest(BaseModel):
    question: str
class RAGResponse(BaseModel):
    context: str = ""; statute_id: Optional[str] = None; title: Optional[str] = None; source: Optional[str] = None

class EthicsRequest(BaseModel):
    text: str

class EthicsResult(BaseModel):
    flagged: bool; reasons: List[str] = []