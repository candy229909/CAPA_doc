# app/routes/file_router.py
from fastapi import APIRouter, UploadFile, File, Form, Request
from app.services.file_service import FileService

router = APIRouter()

@router.post("/upload-document")
async def upload_document(
    request: Request,
    conversation_id: str = Form(None),
    file: UploadFile = File(...)
):
    svc = FileService(request.app.state.mongo)
    return await svc.handle_upload(file, conversation_id)
