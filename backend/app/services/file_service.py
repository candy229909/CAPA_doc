# app/services/file_service.py
from fastapi import HTTPException, UploadFile
from pathlib import Path
from typing import Optional
from datetime import datetime
import uuid, os, tempfile

from app.database.db_mongo import MongoDB
from app.file_to_markdown_json import FileToMarkdownJSON

class FileService:
    def __init__(self, mongo):
        self.mongo = mongo
        self.converter = FileToMarkdownJSON()

    async def handle_upload(self, file: UploadFile, conversation_id: Optional[str]) -> dict:
        if not file.filename:
            raise HTTPException(status_code=400, detail="檔案名稱不能為空")

        ext = Path(file.filename).suffix.lower()
        allowed_exts = {".doc", ".docx", ".pdf", ".txt", ".md", ".csv"}
        if ext not in allowed_exts:
            raise HTTPException(status_code=400, detail=f"不支援格式，僅支援：{', '.join(sorted(allowed_exts))}")

        content = await file.read()
        size = len(content)
        if size == 0:
            raise HTTPException(status_code=400, detail="檔案內容為空")
        if size > 20 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="檔案大小不能超過 20MB")
        
        # 儲存原始檔案以供下載
        file_id = str(uuid.uuid4())
        upload_dir = Path("uploaded_files")
        upload_dir.mkdir(exist_ok=True)
        stored_path = upload_dir / f"{file_id}__{file.filename}"
        with open(stored_path, "wb") as f:
            f.write(content)

         # 先確認或建立對話 ID
        if conversation_id:
            convs = await self.mongo.get_conversations()
            if not any(c.get("id") == conversation_id for c in convs):
                raise HTTPException(status_code=404, detail="指定的對話不存在")
        else:
            conversation_id = str(uuid.uuid4())
            await self.mongo.create_conversation({
                "id": conversation_id,
                "title": (file.filename or "New Chat")[:50],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            })

        # 傳入 content
        extracted = await self._extract_text(content, ext)

        chunks = self._chunk_text(extracted, max_chunk_chars=900, overlap=120)

        meta = {"filename": file.filename, "extension": ext, "size": size}
        await self.mongo.save_document_chunks(
            conversation_id=conversation_id or "default",
            title=file.filename,
            content=extracted,
            chunks=chunks,
            meta=meta
        )

        msg = {
                "id": str(uuid.uuid4()),
                "conversation_id": conversation_id,
                "content": f"📎 已上傳檔案: {file.filename}\n\n檔案內容:\n{extracted}",
                "role": "user",
                "timestamp": datetime.utcnow(),
                "file_info": {
                    "file_id": file_id,
                    "filename": file.filename,
                    "file_type": "document",
                    "file_size": size,
                    "extension": ext
                }
              }
        await self.mongo.save_message(msg)
        await self.mongo.update_conversation_timestamp(conversation_id)

        return {
            "success": True,
            "message": "檔案上傳並解析成功",
            "file_content": extracted,
            "filename": file.filename,
            "conversation_id": conversation_id,
            "file_id": file_id,
        }

    async def _extract_text(self, content_bytes: bytes, ext: str) -> str:
        if ext in (".txt", ".md"):
            return content_bytes.decode("utf-8", errors="ignore")

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(content_bytes)
                tmp.flush()
                tmp_path = tmp.name
            data = self.converter.convert(tmp_path)
            return data.get("markdown", "").strip()
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
    
    def _chunk_text(self, text: str, max_chunk_chars: int = 900, overlap: int = 120) -> list[dict]:
        """
        將長文本切成多個片段（支援中英文），每段長度約 max_chunk_chars，段與段之間重疊 overlap 字元。
        回傳格式: [{"idx": int, "text": str, "start": int, "end": int}, ...]
        """
        text = (text or "").strip()
        if not text:
            return []

        # 先以空行當作段落切割；若抓不到，再用句號/換行切
        paras = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paras:
            import re
            paras = re.split(r"[。！？!?．\.]+\s*|\n+", text)
            paras = [p.strip() for p in paras if p.strip()]

        chunks: list[dict] = []
        buf = ""
        idx = 0
        start = 0

        for p in paras:
            # 若加上這段不會超過上限，就先暫存在緩衝
            if len(buf) + len(p) + 1 <= max_chunk_chars:
                buf = (buf + "\n" + p).strip() if buf else p
                continue

            # flush 目前緩衝為一個 chunk
            if buf:
                chunks.append({"idx": idx, "text": buf, "start": start, "end": start + len(buf)})
                idx += 1
                # 下一段從 overlapped 區開始，避免斷點失聯
                start = max(0, start + len(buf) - overlap)
                # 把當前段落尾端截取一段接續（避免單一大段太長）
                buf = p[-(max_chunk_chars - overlap):] if len(p) > max_chunk_chars else p
            else:
                # 如果第一個段落就超長，直接硬切
                buf = p[:max_chunk_chars]

        # 收尾
        if buf.strip():
            chunks.append({"idx": idx, "text": buf, "start": start, "end": start + len(buf)})

        return chunks