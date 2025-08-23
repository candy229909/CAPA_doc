# app/models/law_article.py
from pydantic import BaseModel, Field, validator
from datetime import date
from typing import Optional, List, Dict, Any
import uuid

class LawArticle(BaseModel):
"""
台灣法規條文的 Pydantic 資料模型，用於資料驗證與 Milvus 匯入。
"""
id: str = Field(..., description="主鍵，條文的唯一識別碼", default_factory=lambda: str(uuid.uuid4()))

law_name: str = Field(..., description="法規名稱，如：勞動基準法")
article_no: str = Field(..., description="條號，如：第38條、第38條之一")

paragraph_no: int = Field(0, description="項，無則為 0")
subitem_no: int = Field(0, description="款，無則為 0")

text: str = Field(..., description="條文段落內容")

version_tag: str = Field(..., description="版本識別，如：2024-12-31修正")

effective_from: date = Field(..., description="生效期間起始日期")
effective_to: Optional[date] = Field(None, description="失效期間截止日期")

source_url: Optional[str] = Field(None, description="資料來源網址")

tags: List[str] = Field(default_factory=list, description="關鍵主題標籤，如：['特休', '年假']")

# 我們不直接在 Pydantic 中定義向量，因為向量通常是在匯入前由模型計算的
# 但可以在另一個模型中包含它，或在匯入邏輯中處理

@validator('effective_from', 'effective_to', pre=True)
def parse_date_strings(cls, v):
"""
將 YYYY-MM-DD 格式的字串轉換為 date 物件
"""
if isinstance(v, str):
try:
return date.fromisoformat(v)
except ValueError:
raise ValueError("日期格式必須為 YYYY-MM-DD")
return v

class Config:
schema_extra = {
"example": {
"id": str(uuid.uuid4()),
"law_name": "勞動基準法",
"article_no": "第38條",
"paragraph_no": 1,
"subitem_no": 0,
"text": "勞工在同一雇主或事業單位，繼續工作滿一定期間者，每年應依左列規定給予特別休假...",
"version_tag": "2024-12-31修正",
"effective_from": "2025-01-01",
"effective_to": None,
"source_url": "https://law.moj.gov.tw/LawClass/LawAll.aspx?PCode=N0030001",
"tags": ["特休", "特別休假", "年資"]
}
}