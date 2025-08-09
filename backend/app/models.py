from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime
import os

class ConversationCreate(BaseModel):
    title: str

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
