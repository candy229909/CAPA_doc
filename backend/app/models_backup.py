from pydantic import BaseModel
from typing import Optional, Literal, List, Dict
from datetime import datetime
import os

class ConversationCreate(BaseModel):
    title: str

class PromptRecord(BaseModel):
    id: str               # uuid4
    conversation_id: str
    message_id: str       # 與哪一則 user message 綁定
    prompt_json: Dict     # 你要保存的 JSON（RAG 用的 prompt/vars）
    created_at: datetime

class GeneratedDocument(BaseModel):
    id: str               # uuid4
    conversation_id: str
    prompt_id: str        # 由哪個 prompt 生成
    type: str             # "chunk" | "final" | "citation" 等
    title: Optional[str] = None
    content: str          # 產出文字（或上傳後的路徑）
    meta: Optional[Dict] = None
    created_at: datetime

# 請求/回應用（如果你要提供 API）
class SavePromptRequest(BaseModel):
    conversation_id: str
    message_id: str
    prompt_json: Dict

class SaveGenerationRequest(BaseModel):
    conversation_id: str
    prompt_id: str
    type: str
    title: Optional[str] = None
    content: str
    meta: Optional[Dict] = None

class MessageCreate(BaseModel):
    conversation_id: str
    content: str
    role: str          # "user" 或 "assistant"

class EnhancedChatRequest(BaseModel):
    # ---- 基本聊天請求欄位 ----
    message: str
    conversation_id: Optional[str] = None
    model: str = os.getenv("DEFAULT_OLLAMA_MODEL", "gemma:2b")
    # ---- 是否使用 NLU 法律增強 ----
    use_nlu: Optional[bool] = None
    # ---- 上傳文件內容使用策略 ----
    #    "auto": 後端自動判斷
    #    "always": 強制加入文件內容
    #    "never": 完全不使用文件內容
    use_file_context: Literal['auto', 'always', 'never'] = 'auto'

class Conversation(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime

class Message(BaseModel):
    id: str
    conversation_id: str
    content: str
    role: str
    timestamp: datetime
