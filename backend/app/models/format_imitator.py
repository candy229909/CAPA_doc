
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple
import re

@dataclass
class DocInput:
    filename: str
    filepath: str
    filetype: str
    markdown: str
    metadata: Dict[str, Any]

class FormatImitator:
    PATTERNS = [
        (re.compile(r"^\s*\*\*\s*(?P<key>[^*]+?)\s*\*\*\s*(?P<value>.+?)\s*$"), "** {key} ** {value}"),
        (re.compile(r"^\s*\*\s*(?P<key>[^*]+?)\s*\*\s*:\s*\*\s*(?P<value>[^*]+?)\s*\*\s*$"), "* {key} *: * {value} *"),
        (re.compile(r"^\s*\*\s*(?P<key>[^*]+?)\s*\*\s*:\s*(?P<value>.+?)\s*$"), "* {key} *: {value}"),
        (re.compile(r"^\s*(?P<key>[^:*]+?)\s*:\s*\*\s*(?P<value>[^*]+?)\s*\*\s*$"), "{key}: * {value} *"),
        (re.compile(r"^\s*(?P<key>[^:*#\-\|]+?)\s*:\s*(?P<value>.+?)\s*$"), "{key}: {value}"),
        (re.compile(r"^\s*[-*+]\s+(?P<key>[^:]+?)\s*:\s*(?P<value>.+?)\s*$"), "- {key}: {value}"),
        (re.compile(r"^\s*\|\s*(?P<key>[^|]+?)\s*\|\s*(?P<value>[^|]+?)\s*\|\s*$"), "| {key} | {value} |"),
    ]
    TABLE_SEPARATOR_RE = re.compile(r"^\s*\|\s*:?-{3,}\s*\|\s*:?-{3,}\s*\|\s*$")

    def __init__(self, doc: Dict[str, Any]):
        self.doc = self._validate_and_make(doc)

    def _validate_and_make(self, d: Dict[str, Any]):
        required = ["filename", "filepath", "filetype", "markdown", "metadata"]
        for k in required:
            if k not in d:
                raise ValueError(f"Missing required field: {k}")
        return DocInput(
            filename=d["filename"],
            filepath=d["filepath"],
            filetype=d["filetype"],
            markdown=d["markdown"],
            metadata=d["metadata"]
        )

    def _extract_table_rows(self, lines: List[str]) -> List[Tuple[str, str]]:
        rows = []
        header_seen = False
        for i in range(len(lines) - 1):
            if "|" in lines[i] and "|" in lines[i+1] and self.TABLE_SEPARATOR_RE.match(lines[i+1]):
                header_seen = True
                continue
            if header_seen and "|" in lines[i]:
                m = re.match(r"^\s*\|\s*(?P<key>[^|]+?)\s*\|\s*(?P<value>[^|]+?)\s*\|\s*$", lines[i])
                if m:
                    k = m.group("key").strip()
                    v = m.group("value").strip()
                    if k and v:
                        rows.append((k, v))
                else:
                    break
        return rows

    def _extract_pairs(self, text: str):
        pairs: List[Tuple[str, str]] = []
        detected_tpl: Optional[str] = None
        lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]

        table_pairs = self._extract_table_rows(lines)
        if table_pairs:
            pairs.extend(table_pairs)
            detected_tpl = "| {key} | {value} |"

        for ln in lines:
            if re.match(r"^\s{0,3}#{1,6}\s+", ln):
                continue
            if self.TABLE_SEPARATOR_RE.match(ln):
                continue
            for pattern, tpl in self.PATTERNS:
                m = pattern.match(ln)
                if m:
                    key = m.group("key").strip()
                    value = m.group("value").strip()
                    if key and value:
                        pairs.append((key, value))
                        if detected_tpl is None:
                            detected_tpl = tpl
                    break
        return pairs, detected_tpl

    def imitate(self) -> Dict[str, Any]:
        pairs, detected_tpl = self._extract_pairs(self.doc.markdown)
        if not pairs:
            fallback_lines = [ln.strip() for ln in self.doc.markdown.splitlines() if ln.strip() and not ln.strip().startswith("#")]
            for i in range(0, len(fallback_lines) - 1, 2):
                pairs.append((fallback_lines[i], fallback_lines[i+1]))
            if pairs:
                detected_tpl = "{key}: {value}"

        if not pairs:
            return {{"structure": "{key1}: {value1}", "data": []}}

        structure_lines = []
        for idx, (k, v) in enumerate(pairs, start=1):
            key_ph = f"{{{{key{idx}}}}}"
            val_ph = f"{{{{value{idx}}}}}"
            ln = (detected_tpl or "{key}: {value}").replace("{key}", key_ph).replace("{value}", val_ph)
            structure_lines.append(ln)

        structure = "\n\n".join(structure_lines)
        data = [{{"key": k, "value": v}} for (k, v) in pairs]
        return {{"structure": structure, "data": data}}

    @staticmethod
    def render(structure: str, mapping: Dict[str, str]) -> str:
        def repl(m):
            ph = m.group(0)[1:-1]
            return str(mapping.get(ph, m.group(0)))
        return re.sub(r"\{{[a-zA-Z0-9_]+\}}", repl, structure)

    @staticmethod
    def build_llm_prompt(structure: str, scenario: str) -> str:
        prompt = (
            "你是文件小幫手。請依照下述文件模板，基於給定情境，自行擬定合理的 key/value 並完整輸出。\n\n"
            "【文件模板】\n"
            f"{structure}\n\n"
            "【情境】\n"
            f"{scenario}\n\n"
            "【要求】\n"
            "1. 只輸出文件內容（不要解釋）。\n"
            "2. 所有 {{keyN}}/{{valueN}} 都要填入，不要留空。\n"
            "3. 保持與模板相同的 Markdown 樣式與換行。\n"
        )
        return prompt
