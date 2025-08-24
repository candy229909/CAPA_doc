# app/routes/file_router.py
from fastapi import APIRouter, UploadFile, File, Form, Request, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from app.services.file_service import FileService
from app.services.chat_service import ChatService
from app.models import EnhancedChatRequest

router = APIRouter()

@router.post("/upload-document")
async def upload_document(
    request: Request,
    conversation_id: str = Form(None),
    file: UploadFile = File(...),
    message: str = Form(None)
):
    svc = FileService(request.app.state.mongo)
    upload_res = await svc.handle_upload(file, conversation_id)
    if message:
        chat_svc = ChatService(request.app.state.mongo, request.app.state.neo4j)
        chat_req = EnhancedChatRequest(
            message=message,
            conversation_id=upload_res["conversation_id"],
            use_file_context="always",
        )
        chat_res = await chat_svc.chat(chat_req)
        return {
            **upload_res,
            "assistant_reply": chat_res.get("content"),
            "message_id": chat_res.get("message_id"),
            "need": chat_res.get("need"),
        }
    return upload_res

@router.get("/download-document/{file_id}")
async def download_document(file_id: str):
    upload_dir = Path("uploaded_files")
    matches = list(upload_dir.glob(f"{file_id}__*"))
    if not matches:
        raise HTTPException(status_code=404, detail="檔案不存在")
    file_path = matches[0]
    filename = file_path.name.split("__", 1)[1]
    return FileResponse(path=file_path, filename=filename, media_type="application/octet-stream")