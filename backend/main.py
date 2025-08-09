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
import tempfile

# 檔案解析相關套件
import docx2txt
from docx import Document

# 導入擴充路由與相關模型/函式
from main_extension import (
    router as extension_router,
    ChatEnhancedRequest,
    chat_with_context,
    law_query,
    LawQuery,            # 新增: 法律查詢請求模型
    analyze_intent,
    NLURequest,
    NLUResponse,
    ethics_check,        # 新增: 倫理檢查函式
    EthicsRequest,       # 新增: 倫理檢查請求模型
    EthicsResult,        # 新增: 倫理檢查結果模型
)

from app.database import MongoDB, Neo4jDB
from app.models import ConversationCreate, EnhancedChatRequest

# 檔案上傳回應模型
class FileUploadResponse(BaseModel):
    success: bool
    message: str
    file_content: Optional[str] = None
    filename: Optional[str] = None

# 對話重新命名請求模型
class ConversationRename(BaseModel):
    title: str

# 全域資料庫連接實例（啟動時初始化）
mongodb: MongoDB = None
neo4j_db: Neo4jDB = None

# 上傳檔案目錄初始化
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用啟動與關閉時執行：連接/關閉資料庫等"""
    global mongodb, neo4j_db
    mongodb = MongoDB()
    neo4j_db = Neo4jDB()
    await mongodb.connect()
    await neo4j_db.connect()
    print("資料庫連接成功")
    yield   # 在此期間應用正常運行
    await mongodb.close()
    await neo4j_db.close()
    print("資料庫連接已關閉")

app = FastAPI(title="AI Chat API", version="1.0.0", lifespan=lifespan)

# 註冊擴充路由 (包含 NLU/知識庫 查詢等進階功能)
app.include_router(extension_router, prefix="", tags=["extensions"])

# CORS 設定（允許前端 localhost 呼叫）
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
    """取得所有對話清單"""
    try:
        return await mongodb.get_conversations()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/conversations")
async def create_conversation(conversation: ConversationCreate):
    """建立新對話"""
    try:
        conv_id = str(uuid.uuid4())
        data = {
            "id": conv_id,
            "title": conversation.title,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        # 插入資料庫並返回
        await mongodb.create_conversation(data)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/conversations/{conversation_id}/title")
async def rename_conversation(conversation_id: str, req: ConversationRename):
    """重新命名對話標題"""
    try:
        convs = await mongodb.get_conversations()
        if not any(c["id"] == conversation_id for c in convs):
            raise HTTPException(status_code=404, detail="對話不存在")
        await mongodb.update_conversation_title(conversation_id, req.title)
        return {"message": "對話標題更新成功", "title": req.title}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload-document")
async def upload_document(
    file: UploadFile = File(...),
    conversation_id: Optional[str] = Form(None)
) -> FileUploadResponse:
    """接收並解析上傳的 Word 文件內容，將文字內容以使用者訊息加入對話。"""
    try:
        # 1) 基本檢查
        if not file.filename:
            raise HTTPException(status_code=400, detail="檔案名稱不能為空")
        ext = Path(file.filename).suffix.lower()
        allowed_exts = {".doc", ".docx"}
        if ext not in allowed_exts:
            raise HTTPException(status_code=400, detail=f"不支援格式，僅支援：{', '.join(allowed_exts)}")
        content = await file.read()
        size = len(content)
        if size == 0:
            raise HTTPException(status_code=400, detail="檔案內容為空")
        if size > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="檔案大小不能超過 10MB")
        # 2) 解析檔案文字內容
        extracted = ""
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp_path = Path(tmp.name)
            async with aiofiles.open(tmp_path, "wb") as f:
                await f.write(content)
            try:
                if ext == ".docx":
                    try:
                        doc = Document(str(tmp_path))
                        paras = [p.text for p in doc.paragraphs if p.text.strip()]
                        extracted = "\n".join(paras)
                    except Exception:
                        # .docx 解析若失敗，退回使用 docx2txt
                        extracted = docx2txt.process(str(tmp_path))
                else:
                    # .doc 檔直接用 docx2txt 處理
                    extracted = docx2txt.process(str(tmp_path))
                extracted = extracted.strip()
                if not extracted:
                    raise HTTPException(status_code=400, detail="無法從檔案中提取文字內容")
            finally:
                tmp_path.unlink()  # 刪除臨時檔案
        # 3) 將解析出的文字作為使用者訊息存入指定對話（如果有提供 conversation_id）
        if conversation_id:
            convs = await mongodb.get_conversations()
            if not any(c["id"] == conversation_id for c in convs):
                raise HTTPException(status_code=404, detail="指定的對話不存在")
            msg = {
                "id": str(uuid.uuid4()),
                "conversation_id": conversation_id,
                "content": f"📎 已上傳檔案: {file.filename}\n\n檔案內容:\n{extracted}",
                "role": "user",
                "timestamp": datetime.utcnow(),
                "file_info": {
                    "filename": file.filename,
                    "file_type": "document",
                    "file_size": size,
                    "extension": ext
                }
            }
            await mongodb.save_message(msg)
            await mongodb.update_conversation_timestamp(conversation_id)
        # 4) 回傳解析結果
        return FileUploadResponse(success=True, message="檔案上傳並解析成功", 
                                   file_content=extracted, filename=file.filename)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"檔案處理失敗: {e}")

@app.get("/api/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: str):
    """取得指定對話的所有訊息"""
    try:
        return await mongodb.get_messages(conversation_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """刪除指定對話及其訊息"""
    try:
        await mongodb.delete_conversation(conversation_id)
        return {"message": "Conversation deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def chat(request: EnhancedChatRequest):
    """
    主要聊天 API：
    - 自動用 NLU 判斷是否為「法律查詢」→ 走 NLU+Neo4j 增強流程
    - 其他情境 → 走一般 LLM（Ollama）
    - 所有模式均將訊息記錄於 MongoDB，互動關係記錄於 Neo4j
    """
    try:
        # 1) 確保對話 ID 存在，如無則建立新對話
        if not request.conversation_id:
            conv_id = str(uuid.uuid4())
            title = request.message[:50] + ("..." if len(request.message) > 50 else "")
            await mongodb.create_conversation({
                "id": conv_id,
                "title": title,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            })
            request.conversation_id = conv_id

        # 2) 保存使用者訊息到資料庫
        user_msg = {
            "id": str(uuid.uuid4()),
            "conversation_id": request.conversation_id,
            "content": request.message,
            "role": "user",
            "timestamp": datetime.utcnow(),
        }
        await mongodb.save_message(user_msg)
        await mongodb.update_conversation_timestamp(request.conversation_id)

        # 3) 判斷是否進入 NLU 增強模式（法律模式）
        use_nlu_decision = False
        if request.use_nlu is True:
            # 前端要求強制法律模式
            use_nlu_decision = True
            nlu_result = None
        else:
            # 調用 NLU 模組分析使用者意圖
            nlu_dict = await analyze_intent(NLURequest(query=request.message))
            nlu_result = NLUResponse.parse_obj(nlu_dict)
            use_nlu_decision = (nlu_result.intent != "unknown")
            print(f"[Chat] NLU 決策：intent={nlu_result.intent} -> use_nlu={use_nlu_decision}")

        # 4) 根據判斷走對應路徑產生 AI 回覆
        if use_nlu_decision:
            # —— 法律增強模式：透過法律知識庫輔助回答 ——
            enh_req = ChatEnhancedRequest(message=request.message)
            enh_res = await chat_with_context(enh_req)  # 調用增強聊天模組，返回 ChatEnhancedResponse
            ai_text = enh_res.final_answer

            # 如果增強模組返回了 Cypher 查詢字串，則實際查詢 Neo4j 取得條文內容
            if getattr(enh_res, "cypher", None):
                rows = await neo4j_db.run_read_query(enh_res.cypher)
                if rows:
                    # 取第一筆查詢結果，構造回覆內容
                    top = rows[0]
                    law = top.get("law", "") or ""
                    statute_id = top.get("statute_id", "") or ""
                    title = top.get("title", "") or ""
                    excerpt = (top.get("text", "") or "")[:400]  # 截取部分條文內容
                    ai_text = (
                        "⚖️ 法律查詢模式（已檢索到條文）\n"
                        f"來源法規：{law} {statute_id}《{title}》\n"
                        f"條文節選：{excerpt}\n\n"
                        "➡️ 如需更完整條文內容或不同條文，請告知我關鍵資訊。"
                    )
                else:
                    # 查詢結果為空，返回建議訊息
                    ai_text = (
                        "我沒有從法規知識圖譜找到明確相關條文。"
                        "建議提供更多相關關鍵詞或換個方式詢問，以便我協助查找。"
                    )

            # 將來源（若有）附加在答案末尾，方便用戶了解出處
            source_bits = []
            if getattr(enh_res, "source_law", None):
                source_bits.append(str(enh_res.source_law))
            if getattr(enh_res, "source_statute", None):
                source_bits.append(str(enh_res.source_statute))
            if getattr(enh_res, "source_title", None):
                source_bits.append(str(enh_res.source_title))
            if source_bits:
                ai_text += "\n\n— 資料來源：" + " · ".join(source_bits)
        else:
            # —— 一般對話模式：直接由 LLM 產生回答 ——
            # 檢查是否需要附加上傳文件內容作為輔助
            async def extract_file_context_from_messages(conversation_id: str,
                                                         max_chars: int = 1500,
                                                         max_files: int = 3) -> str:
                raw_msgs = await mongodb.get_messages(conversation_id)
                # 過濾出包含檔案內容的訊息
                file_msgs = [m for m in raw_msgs if isinstance(m, dict) and m.get("file_info")]
                if not file_msgs:
                    return ""
                recent = file_msgs[-max_files:]
                chunks = []
                for m in recent:
                    content = (m.get("content") or "")
                    # 消息格式範例: "📎 已上傳檔案: XXX\n\n檔案內容:\n{這裡是文件文字}"
                    # 取出 "檔案內容:" 後的部分作為上下文
                    for key in ("檔案內容:", "文件內容:", "內容:"):
                        if key in content:
                            content = content.split(key, 1)[-1]
                            break
                    chunks.append(content.strip()[:max_chars])
                return "\n\n".join(chunks).strip()

            def looks_like_doc_question(text: str) -> bool:
                # 判斷用戶提問是否提及上傳的文件
                keywords = ["這份文件", "本文件", "上傳", "合約", "報告", "檔案", "附件", "條文內容", "依據文件", "文件"]
                return any(k in text for k in keywords)

            file_context_text = ""
            if request.use_file_context != "never" and request.conversation_id:
                file_context_text = await extract_file_context_from_messages(request.conversation_id)

            if request.use_file_context == "always":
                include_files = bool(file_context_text)
            elif request.use_file_context == "auto":
                include_files = bool(file_context_text) and looks_like_doc_question(request.message)
            else:
                include_files = False

            # 根據策略決定是否將文件內容加入 prompt
            if include_files:
                prompt = (
                    "你是一位法律助理。請根據以下『文件節選』內容優先回答使用者問題。"
                    "若文件內容不足以回答，請據實說明無法完整回答的原因。\n\n"
                    f"文件節選：\n{file_context_text}\n\n"
                    f"使用者問題：\n{request.message}\n"
                )
            else:
                prompt = request.message

            # 調用本地 Ollama API 產生回答
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{OLLAMA_HOST}/api/generate",
                    json={"model": request.model, "prompt": prompt, "stream": False}
                )
                if resp.status_code == 404:
                    # 模型未找到，嘗試使用後備模型
                    fallback_model = os.getenv("OLLAMA_FALLBACK_MODEL", "gemma3n:e2b")
                    tags = await client.get(f"{OLLAMA_HOST}/api/tags")
                    models = []
                    if tags.status_code == 200:
                        data = tags.json()
                        # 新舊版本 Ollama 的模型列表鍵不同，皆作兼容
                        models = [m.get("model") or m.get("name") for m in data.get("models", [])]
                    if fallback_model in models:
                        resp = await client.post(
                            f"{OLLAMA_HOST}/api/generate",
                            json={"model": fallback_model, "prompt": prompt, "stream": False}
                        )
                    else:
                        raise HTTPException(
                            status_code=502,
                            detail=(
                                f"Ollama 模型 '{request.model}' 不存在 (404)。"
                                f"請先在 Ollama 主機執行：`ollama pull {request.model}`，"
                                f"或將環境變數 OLLAMA_FALLBACK_MODEL 設為已存在的模型名稱（當前嘗試 '{fallback_model}' 亦未找到）。"
                            )
                        )
            if resp.status_code != 200:
                raise HTTPException(status_code=500, detail=f"Ollama API error ({resp.status_code})")
            ai_text = resp.json().get("response", "")

        # **在保存 AI 回覆前進行倫理檢查**
        ethics_result = await ethics_check(EthicsRequest(response=ai_text))
        # ethics_check 回傳可能是 dict 或 Pydantic 模型，統一取值
        if ethics_result.get("flagged") if isinstance(ethics_result, dict) else ethics_result.flagged:
            reason = ethics_result["reason"] if isinstance(ethics_result, dict) else ethics_result.reason
            ai_text = f"⚠️ 回應被標記為不當：{reason}"

        # 5) 將 AI 回覆保存至資料庫
        ai_msg = {
            "id": str(uuid.uuid4()),
            "conversation_id": request.conversation_id,
            "content": ai_text,
            "role": "assistant",
            "timestamp": datetime.utcnow(),
        }
        await mongodb.save_message(ai_msg)
        await mongodb.update_conversation_timestamp(request.conversation_id)

        # 6) 如為首輪對話，使用使用者問題更新對話標題
        msg_count = await mongodb.count_messages(request.conversation_id)
        if msg_count <= 2:
            new_title = request.message[:50] + ("..." if len(request.message) > 50 else "")
            await mongodb.update_conversation_title(request.conversation_id, new_title)

        # 7) 在 Neo4j 知識圖譜中記錄此次問答關係（Conversation包含Messages）
        await neo4j_db.save_interaction(
            conversation_id=request.conversation_id,
            user_message=request.message,
            ai_response=ai_text,
        )

        # 回傳 AI 回覆內容與 conversation_id，前端據此顯示
        return {
            "response": ai_text,
            "conversation_id": request.conversation_id,
        }
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Ollama 回應逾時")
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print("[Chat] 未捕捉的例外:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def health_check():
    """簡易健康檢查：確認本地 LLM、MongoDB、Neo4j 等服務狀態"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            tag_resp = await client.get(f"{OLLAMA_HOST}/api/tags")
        ollama_status = "ok" if tag_resp.status_code == 200 else "error"
        mongo_ok = await mongodb.ping()
        neo4j_ok = await neo4j_db.ping()
        return {
            "status": "healthy",
            "services": {
                "ollama": "ok" if ollama_status == "ok" else "error",
                "mongodb": "ok" if mongo_ok else "error",
                "neo4j": "ok" if neo4j_ok else "error"
            }
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
