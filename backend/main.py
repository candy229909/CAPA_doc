from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Optional
import httpx
import os
from datetime import datetime
import uuid
import aiofiles
from pathlib import Path

# 如果要支援 .doc 解析，請先安裝：pip install docx2txt
import docx2txt
from docx import Document

from app.database import MongoDB, Neo4jDB
from app.models import ConversationCreate, ChatRequest

# 檔案上傳回應模型
class FileUploadResponse(BaseModel):
    success: bool
    message: str
    file_content: Optional[str] = None
    filename: Optional[str] = None

# 重新命名對話模型
class ConversationRename(BaseModel):
    title: str

# 全域資料庫實例
mongodb: MongoDB = None
neo4j_db: Neo4jDB = None

# 上傳目錄
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global mongodb, neo4j_db
    mongodb = MongoDB()
    neo4j_db = Neo4jDB()

    await mongodb.connect()
    await neo4j_db.connect()
    print("資料庫連接成功")

    yield

    await mongodb.close()
    await neo4j_db.close()
    print("資料庫連接已關閉")

app = FastAPI(title="AI Chat API", version="1.0.0", lifespan=lifespan)

# CORS 設定（可加入其他前端位址）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

@app.get("/")
async def root():
    return {"message": "AI Chat API is running"}

@app.get("/api/conversations")
async def get_conversations():
    try:
        return await mongodb.get_conversations()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/conversations")
async def create_conversation(conversation: ConversationCreate):
    try:
        conv_id = str(uuid.uuid4())
        data = {
            "id": conv_id,
            "title": conversation.title,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        await mongodb.create_conversation(data)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/conversations/{conversation_id}/title")
async def rename_conversation(conversation_id: str, req: ConversationRename):
    # 檢查是否存在
    convs = await mongodb.get_conversations()
    if not any(c["id"] == conversation_id for c in convs):
        raise HTTPException(status_code=404, detail="對話不存在")
    await mongodb.update_conversation_title(conversation_id, req.title)
    return {"message": "對話標題更新成功", "title": req.title}

@app.post("/api/upload-document")
async def upload_document(
    file: UploadFile = File(...),
    conversation_id: Optional[str] = Form(None)
) -> FileUploadResponse:
    # 1. 讀取檔案內容到 memory
    content = await file.read()
    size = len(content)
    ext = Path(file.filename).suffix.lower()
    allowed = {".doc", ".docx"}

    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"不支援格式，僅限：{', '.join(allowed)}"
        )
    if size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="檔案大小不能超過 10MB")

    # 2. 寫入唯一檔名到上傳資料夾
    unique_name = f"{uuid.uuid4()}{ext}"
    dest_path = UPLOAD_DIR / unique_name
    async with aiofiles.open(dest_path, "wb") as f:
        await f.write(content)

    # 3. 提取文字
    try:
        if ext == ".docx":
            text = docx2txt.process(str(dest_path))
        else:  # .doc
            # docx2txt 也能處理部分 .doc
            text = docx2txt.process(str(dest_path))

        text = text.strip()
        if not text:
            raise Exception("未擷取到任何文字內容")

    except Exception as e:
        # 清理暫存檔再拋出
        await dest_path.unlink()
        raise HTTPException(status_code=400, detail=f"解析失敗：{e}")

    # 4. 如果有 conversation_id，儲存為用戶訊息
    if conversation_id:
        msg = {
            "id": str(uuid.uuid4()),
            "conversation_id": conversation_id,
            "content": f"📎 已上傳檔案: {file.filename}\n\n檔案內容:\n{text}",
            "role": "user",
            "timestamp": datetime.utcnow(),
            "file_info": {
                "filename": file.filename,
                "file_type": "document",
                "file_size": size
            }
        }
        await mongodb.save_message(msg)

    # 5. 刪除暫存檔
    await dest_path.unlink()

    return FileUploadResponse(
        success=True,
        message="檔案上傳並解析成功",
        file_content=text,
        filename=file.filename
    )

@app.get("/api/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: str):
    try:
        return await mongodb.get_messages(conversation_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    try:
        await mongodb.delete_conversation(conversation_id)
        return {"message": "Conversation deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def chat(request: ChatRequest):
    try:
        # 若無 conversation_id，就先建一個
        if not request.conversation_id:
            conv_id = str(uuid.uuid4())
            title = request.message[:50] + ("..." if len(request.message)>50 else "")
            await mongodb.create_conversation({
                "id": conv_id,
                "title": title,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            })
            request.conversation_id = conv_id

        # 儲存用戶訊息
        await mongodb.save_message({
            "id": str(uuid.uuid4()),
            "conversation_id": request.conversation_id,
            "content": request.message,
            "role": "user",
            "timestamp": datetime.utcnow()
        })

        # 呼叫 Ollama
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{OLLAMA_HOST}/api/generate",
                json={
                    "model": request.model or "gemma2:2b",
                    "prompt": request.message,
                    "stream": False
                }
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=500, detail="Ollama API error")
        ai_text = resp.json().get("response", "")

        # 儲存 AI 回應
        await mongodb.save_message({
            "id": str(uuid.uuid4()),
            "conversation_id": request.conversation_id,
            "content": ai_text,
            "role": "assistant",
            "timestamp": datetime.utcnow()
        })

        # 更新標題（若首輪對話）
        cnt = await mongodb.count_messages(request.conversation_id)
        if cnt <= 2:
            new_title = request.message[:50] + ("..." if len(request.message)>50 else "")
            await mongodb.update_conversation_title(request.conversation_id, new_title)

        # 選擇性儲存到 Neo4j
        await neo4j_db.save_interaction(
            conversation_id=request.conversation_id,
            user_message=request.message,
            ai_response=ai_text
        )

        return {"response": ai_text, "conversation_id": request.conversation_id}

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Ollama timeout")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def health_check():
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            tag_resp = await client.get(f"{OLLAMA_HOST}/api/tags")
        ollama_status = "ok" if tag_resp.status_code == 200 else "error"
        mongo_ok = await mongodb.ping()
        neo4j_ok = await neo4j_db.ping()
        return {
            "status": "healthy",
            "services": {
                "ollama": ollama_status,
                "mongodb": "ok" if mongo_ok else "error",
                "neo4j": "ok" if neo4j_ok else "error"
            }
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)