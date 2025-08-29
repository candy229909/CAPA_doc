import os
from typing import List, Dict, Any, Optional
from openai import OpenAI

# 你可以指向：Ollama (http://localhost:11434/v1)、
# llama.cpp server (http://localhost:8000/v1)、
# LM Studio (http://localhost:1234/v1) 等
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:11434/v1")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "ollama")  # 本機 server 多數忽略，但 SDK 需要非空
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "llama3.1:8b")

# 初始化客戶端（指向本機 server）
_client = OpenAI(base_url=OPENAI_BASE_URL, api_key=OPENAI_API_KEY)

def openai_chat_llm(system_prompt: str,
                    history: List[Dict[str, str]],
                    content: str,
                    rag_chunks: List[Dict[str, Any]],
                    model: Optional[str]) -> str:
    # 拼 RAG 區塊
    lines = []
    for i, ch in enumerate(rag_chunks[:8], 1):
        lines.append(f"[{i}] ({ch.get('source','')}) s={round(float(ch.get('score',0.0)),3)}\n{(ch.get('text') or '').strip()}")
    rag_block = "\n\n".join(lines)
    sys = (system_prompt or "").strip()
    if rag_block:
        sys += "\n\n[RETRIEVED_CONTEXT]\n" + rag_block

    msgs = [{"role": "system", "content": sys}]
    for t in history[-20:]:
        r, c = t.get("role"), t.get("content")
        if r in {"user", "assistant"} and isinstance(c, str):
            msgs.append({"role": r, "content": c})
    msgs.append({"role": "user", "content": content})

    resp = _client.chat.completions.create(
        model=model or OPENAI_MODEL,
        messages=msgs,
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.3")),
        top_p=float(os.getenv("LLM_TOP_P", "0.9")),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "1024")),
        # 許多本機 server 支援 num_ctx / stop 等以 extra_params 傳遞：
        extra_body={"num_ctx": int(os.getenv("LLM_NUM_CTX", "4096"))}
    )
    return resp.choices[0].message.content or ""
