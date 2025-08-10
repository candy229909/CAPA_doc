# pdf_text_extractor.py
from __future__ import annotations
import io
import os
import tempfile
from typing import Optional, Tuple
import asyncio
import json

class PDFTextExtractor:
    """
    PDF → Text 抽取器
    - 先以 pdfplumber 嘗試抽文字
    - 失敗或抽到的字太少時，啟用 OCR 後援（pdf2image + pytesseract）

    Args:
        use_ocr_fallback: 抽不到文字時是否啟用 OCR
        tesseract_cmd: Tesseract 可執行檔完整路徑（Windows 常見：C:\\Program Files\\Tesseract-OCR\\tesseract.exe）
        ocr_lang: OCR 語言（例如 "eng", "chi_tra", 或 "eng+chi_tra"）
        dpi: 影像轉換 DPI（OCR 效果與速度的折衷，常見 300）
        poppler_path: Windows 下 pdf2image 需要 Poppler，填其 bin 路徑（例如 r"C:\\poppler\\Library\\bin"）
        min_text_len_for_plumber: 若 pdfplumber 文字長度小於此值，視為抽不到→啟動 OCR
    """
    def __init__(
        self,
        use_ocr_fallback: bool = True,
        tesseract_cmd: Optional[str] = None,
        ocr_lang: str = "eng+chi_tra",
        dpi: int = 300,
        poppler_path: Optional[str] = None,
        min_text_len_for_plumber: int = 20,
    ) -> None:
        self.use_ocr_fallback = use_ocr_fallback
        self.tesseract_cmd = tesseract_cmd
        self.ocr_lang = ocr_lang
        self.dpi = dpi
        self.poppler_path = poppler_path
        self.min_text_len_for_plumber = min_text_len_for_plumber

        # 可延後載入的第三方套件（lazy import）在方法裡處理，避免無 OCR 也能用純文字抽取

    def extract_from_bytes(self, file_bytes: bytes) -> str:
        """
        傳入整份 PDF 的 bytes，回傳抽取到的文字（可能為空字串）。
        """
        text = ""
        try:
            text = self._extract_with_pdfplumber(file_bytes)
        except Exception:
            # pdfplumber 可能遇到損壞/加密 PDF 直接失敗，先忽略錯誤
            text = ""

        if self.use_ocr_fallback:
            if not text or len(text.strip()) < self.min_text_len_for_plumber:
                try:
                    text = self._extract_with_ocr(file_bytes)
                except Exception:
                    # OCR 也失敗就回傳目前結果（可能是空字串）
                    text = text or ""

        return text or ""

    def extract_from_streamlit_uploader(self, uploaded_file) -> str:
        """
        直接吃 Streamlit 的 UploadedFile，回傳抽取文字。
        """
        file_bytes = uploaded_file.getvalue()
        return self.extract_from_bytes(file_bytes)

    def save_text(self, text: str, base_name: str = "output", dirpath: Optional[str] = None) -> str:
        """儲存文字成結構化 5W2H JSON 檔，回傳檔案完整路徑。"""
        if dirpath is None:
            dirpath = tempfile.mkdtemp(prefix="pdf2json_")
        os.makedirs(dirpath, exist_ok=True)
        
        # 建立基本 5W2H 結構
        data = {
            "who": [],    
            "what": [],   
            "when": [],   
            "where": [],  
            "why": [],    
            "how": [],    
            "how_much": []
        }
        
        try:
            # 初步規則萃取
            import re
            
            # WHO: 找出人物/組織
            who_patterns = [
                r"(勞工|雇主|事業主|負責人|工會|企業|公司|機關)",
                r"([^，。；：\s]{2,4}(股份有限)?公司)",
                r"([^，。；：\s]{2,4}(企業|工會))",
            ]
            who = []
            for pattern in who_patterns:
                who.extend(re.findall(pattern, text))
            who = [w[0] if isinstance(w, tuple) else w for w in who]  # 取第一個匹配組
            who = list(set(who))  # 去重
            
            # WHAT: 找出行為/事件
            what_patterns = [
                r"法規名稱[:：]\s*(.*?)(?=\n|$)",
                r"(第\d+條.*?(?=第\d+條|$))",
                r"([^，。；：]+(?:規定|辦法|要點))",
            ]
            what = []
            for pattern in what_patterns:
                what.extend(re.findall(pattern, text))
            what = [w[0] if isinstance(w, tuple) else w for w in what]
            what = [w.strip() for w in what if len(w.strip()) > 0]
            
            # WHEN: 找出時間
            when_patterns = [
                r"(?:民國|中華民國)?(\d{2,3}年\d{1,2}月\d{1,2}日)",
                r"修正日期[:：]\s*(.*?)(?=\n|$)",
                r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
            ]
            when = []
            for pattern in when_patterns:
                when.extend(re.findall(pattern, text))
            when = [w[0] if isinstance(w, tuple) else w for w in when]
            when = list(set(when))
            
            # 轉換成三元組並存入結構
            for w in who:
                if w.strip():
                    data["who"].append([w.strip(), "角色", "主體"])
            
            for w in what:
                if w.strip():
                    # 將長文本分段
                    parts = w.strip().split("。")
                    for part in parts:
                        if part and len(part) > 5:  # 忽略太短的片段
                            data["what"].append(["規定", "內容", part[:100].strip()])  # 限制長度
            
            for w in when:
                if w.strip():
                    data["when"].append(["時間", "發生於", w.strip()])
            
            # 確保輸出合法 JSON
            json_path = os.path.join(dirpath, f"{base_name}.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 驗證是否為合法 JSON
            with open(json_path, "r", encoding="utf-8") as f:
                json.load(f)  # 測試能否正確讀取
                
            return json_path
            
        except Exception as e:
            print(f"⚠️ 生成 JSON 時發生錯誤：{str(e)}")
            # 發生錯誤時生成空結構
            fallback_data = {key: [] for key in data.keys()}
            json_path = os.path.join(dirpath, f"{base_name}.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(fallback_data, f, ensure_ascii=False, indent=2)
            return json_path

    def process_streamlit_file(self, uploaded_file) -> Tuple[str, str]:
        """
        專給 Streamlit 使用的便捷方法：
        傳入 UploadedFile → 抽文字 → 存成 json → 回傳 (text, json_path)
        """
        base = os.path.splitext(uploaded_file.name)[0] or "output"
        text = self.extract_from_streamlit_uploader(uploaded_file)
        json_path = self.save_text(text, base_name=base)
        return text, json_path

    # ---------------- internal helpers ----------------

    def _extract_with_pdfplumber(self, file_bytes: bytes) -> str:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                text_parts.append(t)
        return "\n".join(text_parts).strip()

    def _extract_with_ocr(self, file_bytes: bytes) -> str:
        # 設定 tesseract 路徑（若有提供）
        import pytesseract
        if self.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

        from pdf2image import convert_from_bytes

        # Windows 若無全域 Poppler，可傳 poppler_path
        images = convert_from_bytes(
            file_bytes,
            dpi=self.dpi,
            poppler_path=self.poppler_path  # 非 Windows 可忽略
        )
        text_parts = []
        for img in images:
            json = pytesseract.image_to_string(img, lang=self.ocr_lang)
            text_parts.append(json)
        return "\n".join(text_parts).strip()

    def debug_print_extraction_results(self, text: str, who: list, what: list, when: list) -> None:
        """
        除錯用：印出抽取結果
        """
        print(f"Input text length: {len(text)}")
        print(f"Extracted WHO: {who}")
        print(f"Extracted WHAT: {what}")
        print(f"Extracted WHEN: {when}")
