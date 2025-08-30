from pathlib import Path
from typing import List, Any
import os
from pypdf import PdfReader
from docx import Document as DocxDocument
from pptx import Presentation

SUPPORTED = {".pdf", ".docx", ".txt", ".pptx", ".json"}

class UnifiedFileTextExtractor:
    def extract(self, in_path: Path) -> str:
        ext = in_path.suffix.lower()
        if ext == ".pdf":
            return self._pdf_to_text(in_path)
        elif ext == ".docx":
            return self._docx_to_text(in_path)
        elif ext == ".pptx":
            return self._pptx_to_text(in_path)
        elif ext == ".txt":
            return in_path.read_text(encoding="utf-8", errors="ignore")
        elif ext == ".json":
            # 若你未來 JSON 有 text 欄位，可視需求載入解析；此處先直接回傳原文
            return in_path.read_text(encoding="utf-8", errors="ignore")
        else:
            raise ValueError(f"Unsupported file type: {ext}")

    def _pdf_to_text(self, in_path: Path) -> str:
        reader = PdfReader(str(in_path))
        texts: List[str] = []
        for page in reader.pages:
            try:
                t = page.extract_text() or ""
            except Exception:
                t = ""
            if t:
                texts.append(t)
        return os.linesep.join(texts)

    def _docx_to_text(self, in_path: Path) -> str:
        doc = DocxDocument(str(in_path))
        return os.linesep.join(p.text for p in doc.paragraphs)

    def _pptx_to_text(self, in_path: Path) -> str:
        prs = Presentation(str(in_path))
        lines: List[str] = []
        for slide in prs.slides:
            for shape in slide.shapes:
                # 只有含文字框的圖形才會有 text_frame；避免直接讀取 shape.text 造成型別檢查錯誤
                has_tf = getattr(shape, "has_text_frame", False)
                if has_tf:
                    tf: Any = getattr(shape, "text_frame", None)
                    if tf is not None:
                        lines.append(getattr(tf, "text", "") or "")
                        continue
                # 也處理簡單表格文字
                has_tbl = getattr(shape, "has_table", False)
                if has_tbl:
                    tbl: Any = getattr(shape, "table", None)
                    if tbl is not None:
                        for row in tbl.rows:
                            cells = [cell.text for cell in row.cells]
                            lines.append(" | ".join(cells))
        # 過濾空行
        return os.linesep.join([s for s in lines if s and s.strip()])