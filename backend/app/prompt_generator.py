import json
import re
from typing import Dict, List, Callable, Optional

class PromptGenerator:
    def __init__(self, filepath: str, expected_keys: Optional[List[str]] = None, llm_fn: Optional[Callable[[str], str]] = None):
        """
        expected_keys: 你想抽的欄位名（中文可）。例如 ["產品來源","商品內容","營養成分標示"]
        llm_fn: 形如 llm_fn(prompt:str) -> str 的函式，回傳 LLM 的「文字」輸出
        """
        self.filepath = filepath
        self.data: Dict[str, str] = {}
        self.expected_keys = expected_keys or []
        self.llm_fn = llm_fn

    # --- 你的其他 load_file 邏輯略，重點是 txt 解析 ---

    def _parse_txt(self, lines: List[str]) -> Dict[str, str]:
        """
        先嘗試用 LLM 解析；如果失敗或無 llm_fn，就用傳統 "key: value" 解析做後援。
        """
        raw_text = "".join(lines).strip()
        # 1) 有 llm_fn 且有期望欄位就先走 LLM
        if self.llm_fn and self.expected_keys:
            parsed = self._parse_with_llm(raw_text, self.expected_keys)
            if parsed:  # 成功拿到字典
                return parsed

        # 2) 後援：傳統 "key: value" 行為
        return self._parse_fallback_key_value(lines)

    # ------------------ LLM 路徑 ------------------

    def _parse_with_llm(self, raw_text: str, expected_keys: List[str]) -> Dict[str, str]:
        """
        用 LLM 把自由文字/半結構文字，對齊到 expected_keys。
        期望 LLM 回傳「純 JSON 物件字串」，key 為 expected_keys 中的其中一個，沒找到請給空字串。
        """
        prompt = self._build_extraction_prompt(raw_text, expected_keys)
        try:
            llm_output = self.llm_fn(prompt)  # 取得模型回覆文字
            json_str = self._strip_to_json(llm_output)
            data = json.loads(json_str)

            # 只保留 expected_keys，並轉成字串
            clean = {}
            for k in expected_keys:
                v = data.get(k, "")
                # 若 value 是 list/obj，壓平成字串（例如營養成分標示可能是清單）
                if isinstance(v, (list, dict)):
                    v = ", ".join(map(str, v)) if isinstance(v, list) else json.dumps(v, ensure_ascii=False)
                clean[k] = str(v)
            return clean
        except Exception:
            return {}

    def _build_extraction_prompt(self, raw_text: str, expected_keys: List[str]) -> str:
        """
        提示詞：要求 LLM 僅輸出 JSON，不要多話。
        """
        keys_lines = "\n".join([f'- "{k}"' for k in expected_keys])
        return f"""你是一個資訊抽取器。請從以下文字中抽取欄位，務必對齊「期望欄位名稱」，若找不到給空字串 ""。
只允許輸出一個 JSON 物件，**不要**輸出任何解釋或多餘文字。

期望欄位：
{keys_lines}

範例輸出（僅示意）：
{{
  "產品來源": "台灣/Taiwan",
  "商品內容": "牛乳",
  "營養成分標示": "乳蛋白, 脂肪"
}}

待解析文字：
\"\"\"{raw_text}\"\"\"
請輸出 JSON：
"""

    def _strip_to_json(self, llm_output: str) -> str:
        """
        有些模型會在 JSON 外多包一點字，這裡盡量萃取最外層 JSON。
        """
        # 先嘗試直接 parse
        try:
            json.loads(llm_output)
            return llm_output
        except Exception:
            pass

        # 用簡單括號配對抓第一段 {...}
        m = re.search(r"\{.*\}", llm_output, flags=re.S)
        if not m:
            raise ValueError("LLM 未輸出 JSON 物件")
        candidate = m.group(0)
        # 再驗一次
        json.loads(candidate)
        return candidate

    # ------------------ 後援規則 ------------------

    def _parse_fallback_key_value(self, lines: List[str]) -> Dict[str, str]:
        """
        後援解析：偵測 "key: value" 或 "key：value"（全形冒號）
        """
        parsed: Dict[str, str] = {}
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if ":" in line or "：" in line:
                key, value = re.split(r"[:：]", line, maxsplit=1)
                parsed[key.strip()] = value.strip()
        return parsed

    # ------------------ 產出 prompt ------------------

    def generate_prompt(self, template: str = None) -> str:
        if not self.data:
            raise ValueError("尚未讀取檔案資料")
        if template:
            # 若模板中有沒填到的 key，format 會噴錯，改成用 get 保底
            return template.format(**{k: self.data.get(k, "") for k in self.data})
        # 預設
        prompt = "請根據以下資料撰寫一份完整的文件：\n"
        for key, value in self.data.items():
            prompt += f"- {key}: {value}\n"
        return prompt


#使用範例
# import requests
# import json

# def ollama_chat_fn(prompt: str,
#                    model: str = "qwen2.5:7b",
#                    url: str = "http://localhost:11434/api/chat") -> str:
#     payload = {
#         "model": model,
#         "messages": [{"role": "user", "content": prompt}],
#         "options": {"temperature": 0.1}
#     }
#     r = requests.post(url, json=payload, timeout=120)
#     r.raise_for_status()
#     data = r.json()
#     # 取最後一個訊息的 content
#     return data["message"]["content"]

# # 使用示例
# pg = PromptGenerator(
#     filepath="sample.txt",
#     expected_keys=["產品來源", "商品內容", "營養成分標示"],
#     llm_fn=ollama_chat_fn
# )
# with open("sample.txt", "r", encoding="utf-8") as f:
#     pg.data = pg._parse_txt(f.readlines())  # 觸發 LLM 解析
# print(pg.generate_prompt())
