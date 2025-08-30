import regex as re
from typing import List

# 1) 先用段落與中文標點做粗切，再做長度控管
ZH_SENT_SPLIT = re.compile(r"(?<=[。！？；;])\s*")

def split_zh_sentences(text: str) -> List[str]:
    parts = []
    for para in text.splitlines():
        para = para.strip()
        if not para:
            continue
        parts.extend([s.strip() for s in ZH_SENT_SPLIT.split(para) if s.strip()])
    return parts

def make_chunks(text: str, target_size: int = 800, overlap: int = 80) -> List[str]:
    sents = split_zh_sentences(text)
    chunks = []
    cur = []
    cur_len = 0
    for s in sents:
        if cur_len + len(s) > target_size and cur:
            chunks.append("".join(cur))
            # 建立重疊
            tail = ("".join(cur))[-overlap:]
            cur = [tail, s]
            cur_len = len(tail) + len(s)
        else:
            cur.append(s)
            cur_len += len(s)
    if cur:
        chunks.append("".join(cur))
    return chunks