# app/services/file_service.py
from fastapi import HTTPException, UploadFile
from pathlib import Path
from typing import Optional
from datetime import datetime
import uuid, os, aiofiles, tempfile

try:
    from docx import Document
except Exception:
    Document = None
import docx2txt

class FileService:
    def __init__(self, mongo):
        self.mongo = mongo

    async def handle_upload(self, file: UploadFile, conversation_id: Optional[str]) -> dict:
        # (1) Basic validations
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

        # (2) Extract text to 'extracted'
        extracted = ""
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp_path = Path(tmp.name)
            async with aiofiles.open(tmp_path, "wb") as f:
                await f.write(content)
            try:
                if ext == ".docx":
                    # Prefer python-docx, fallback to docx2txt
                    if Document is not None:
                        try:
                            doc = Document(str(tmp_path))
                            paras = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
                            extracted = "\n".join(paras)
                        except Exception:
                            extracted = docx2txt.process(str(tmp_path))
                    else:
                        extracted = docx2txt.process(str(tmp_path))
                else:
                    # .doc: best-effort with docx2txt (may fail)
                    try:
                        extracted = docx2txt.process(str(tmp_path))
                    except Exception:
                        extracted = ""
                if not extracted:
                    raise HTTPException(status_code=400, detail="無法從檔案中提取文字內容")
            finally:
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

        # (3) If conversation_id provided, save as a user message
        if conversation_id:
            convs = await self.mongo.get_conversations()
            if not any(c.get("id") == conversation_id for c in convs):
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
            await self.mongo.save_message(msg)
            await self.mongo.update_conversation_timestamp(conversation_id)

        return {"success": True, "message": "檔案上傳並解析成功", "file_content": extracted, "filename": file.filename}
