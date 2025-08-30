
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
import asyncio, io, json, uuid, datetime, re

from app.models.format_imitator import FormatImitator

router = APIRouter()

# ===== Models =====
class KV(BaseModel):
    key: str
    value: Optional[str] = ""

class Module(BaseModel):
    moduleId: str
    name: str
    structure: str
    data: List[KV]
    createdAt: float = datetime.datetime.utcnow().timestamp()

# ===== In-memory stores =====
MODULES: Dict[str, Module] = {}
CONNS: Dict[str, set] = {}
LOCKS: Dict[str, asyncio.Lock] = {}

def ensure_lock(mid: str):
    LOCKS.setdefault(mid, asyncio.Lock())

async def ws_broadcast(mid: str, payload: Dict[str, Any]):
    conns = CONNS.get(mid) or set()
    for ws in list(conns):
        try:
            await ws.send_json(payload)
        except Exception:
            try:
                await ws.close()
            except Exception:
                pass
            conns.discard(ws)

async def broadcast_module(mid: str):
    mod = MODULES.get(mid); 
    if not mod: 
        return
    await ws_broadcast(mid, {"type":"module","moduleDetail": json.loads(mod.model_dump_json())})

def get_missing(mod: Module) -> List[str]:
    return [kv.key for kv in mod.data if not (kv.value or "").strip()]

async def broadcast_missing(mid: str):
    mod = MODULES.get(mid); 
    if not mod: 
        return
    await ws_broadcast(mid, {"type":"missing","keys": get_missing(mod)})

async def send_ask(ws: WebSocket, key: str, prompt: Optional[str]=None):
    await ws.send_json({"type":"ask","key": key, "prompt": prompt or f"請提供「{key}」的資訊。"})

async def send_msg(ws: WebSocket, content: str, role="assistant"):
    await ws.send_json({"type":"message","role": role,"content": content})

# ---------- Helpers ----------
def bytes_to_markdown_guess(b: bytes, filename: str) -> str:
    """示範：直接當作 UTF-8 純文字/Markdown。實務上可在這裡做 PDF/DOCX 轉 Markdown。"""
    try:
        return b.decode("utf-8", errors="ignore")
    except Exception:
        return ""

def build_placeholder_mapping(data: List[KV]) -> Dict[str, str]:
    """把 data 依序映射成 key1/value1、key2/value2…"""
    mapping: Dict[str, str] = {}
    for i, kv in enumerate(data, start=1):
        mapping[f"key{i}"] = kv.key
        mapping[f"value{i}"] = kv.value or ""
    return mapping

def extract_kv_from_text_simple(text: str, allowed: List[str]) -> Dict[str, str]:
    """極簡 key:value 解析（可換成 LLM）。支援 '欄位: 值' / '欄位=值' / '欄位 值' 等。"""
    found: Dict[str, str] = {}
    for key in allowed:
        for sep in [":", "：", "=", "-"]:
            token = f"{key}{sep}"
            if token in text:
                after = text.split(token, 1)[1].strip()
                val = after.split("\n", 1)[0].strip()
                if val: 
                    found[key] = val
                    break
        if key not in found:
            needle = key + " "
            if needle in text:
                after = text.split(needle, 1)[1].strip()
                val = after.split("\n", 1)[0].strip()
                if val: 
                    found[key] = val
    return found

# ---------- REST ----------
@router.post("/api/file_data")
async def file_data(file: UploadFile = File(...), moduleName: str = Form(...)):
    raw = await file.read()
    mk = bytes_to_markdown_guess(raw, file.filename)
    doc = {
        "filename": file.filename,
        "filepath": f"/tmp/{file.filename}",
        "filetype": (file.filename.split(".")[-1].lower() if "." in file.filename else "txt"),
        "markdown": mk,
        "metadata": {"converted_at": datetime.datetime.utcnow().isoformat() + "Z"}
    }
    imitator = FormatImitator(doc)
    result = imitator.imitate()  # {"structure","data":[{"key","value"}]}
    module_id = str(uuid.uuid4())
    MODULES[module_id] = Module(
        moduleId=module_id,
        name=moduleName,
        structure=result["structure"],
        data=[KV(**kv) for kv in result["data"]],
    )
    ensure_lock(module_id)
    return JSONResponse({"moduleId": module_id, "structure": result["structure"], "data": [kv for kv in result["data"]]})

@router.get("/api/modules")
async def list_modules():
    items = [{"id": m.moduleId, "name": m.name, "createdAt": m.createdAt} for m in MODULES.values()]
    items.sort(key=lambda x: x["createdAt"], reverse=True)
    return JSONResponse(items)

@router.get("/api/modules/{module_id}")
async def get_module(module_id: str):
    mod = MODULES.get(module_id)
    if not mod: 
        raise HTTPException(404, "Module not found")
    return JSONResponse(json.loads(mod.model_dump_json()))

@router.get("/api/modules/{module_id}/export")
async def export_module(module_id: str, type: str = "word"):
    mod = MODULES.get(module_id)
    if not mod: 
        raise HTTPException(404, "Module not found")
    mapping = build_placeholder_mapping(mod.data)
    content = FormatImitator.render(mod.structure, mapping)
    payload = f"# {mod.name}\n\n{content}\n"
    stream = io.BytesIO(payload.encode("utf-8"))
    # Currently we generate .txt content; media_type use text/plain for clarity.
    filename = f"module-{module_id}.txt"
    return StreamingResponse(stream, media_type="text/plain", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

class BuildPromptIn(BaseModel):
    moduleId: str
    scenario: str

@router.post("/api/build_prompt")
async def build_prompt(inp: BuildPromptIn):
    mod = MODULES.get(inp.moduleId)
    if not mod: 
        raise HTTPException(404, "Module not found")
    prompt = FormatImitator.build_llm_prompt(mod.structure, inp.scenario)
    return JSONResponse({"prompt": prompt})

# ---------- WebSocket ----------

@router.delete("/api/modules/{module_id}")
async def delete_module(module_id: str):
    """刪除模組：關閉所有連線、移除記憶體資料。"""
    if module_id not in MODULES:
        raise HTTPException(status_code=404, detail="Module not found")
    # 關閉所有 WebSocket 連線
    for ws in list(CONNS.get(module_id, set())):
        try:
            await ws.close(code=1000, reason="module_deleted")
        except Exception:
            pass
    CONNS.pop(module_id, None)
    LOCKS.pop(module_id, None)
    MODULES.pop(module_id, None)
    return JSONResponse({"ok": True})
@router.websocket("/ws/fill")
async def ws_fill(ws: WebSocket, moduleId: str):
    await ws.accept()
    if moduleId not in MODULES:
        await send_msg(ws, "未知的 moduleId", role="system")
        await ws.close(); 
        return

    CONNS.setdefault(moduleId, set()).add(ws)
    ensure_lock(moduleId)

    await send_msg(ws, f"已連線到模組 {moduleId}。")
    await broadcast_module(moduleId)
    await broadcast_missing(moduleId)

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                await send_msg(ws, "需要 JSON 格式。", role="system"); 
                continue

            t = msg.get("type")
            mod = MODULES.get(moduleId)

            if t == "ping":
                continue

            elif t == "status":
                await broadcast_missing(moduleId)

            elif t == "ask_next":
                miss = get_missing(mod)
                if not miss: 
                    await send_msg(ws, "所有欄位都已填寫完成！"); 
                    continue
                await send_ask(ws, miss[0], prompt=f"請提供「{miss[0]}」的資訊。")

            elif t == "ask_key":
                key = msg.get("key")
                if not key:
                    await send_msg(ws, "缺少 key。", role="system"); 
                    continue
                if key not in [kv.key for kv in mod.data]:
                    await send_msg(ws, f"未知欄位：{key}", role="system"); 
                    continue
                await send_ask(ws, key, prompt=msg.get("prompt"))

            elif t == "user_message":
                content = (msg.get("content") or "").strip()
                if not content:
                    continue
                # echo back
                await ws.send_json({"type":"message","role":"user","content": content})

                async with LOCKS[moduleId]:
                    allowed = [kv.key for kv in mod.data]
                    parsed = extract_kv_from_text_simple(content, allowed)
                    filled = []
                    if parsed:
                        m = {kv.key: kv for kv in mod.data}
                        for k, v in parsed.items():
                            m[k].value = v
                            filled.append(k)
                        if filled:
                            await send_msg(ws, f"✅ 已填入：{', '.join(filled)}")
                        else:
                            await send_msg(ws, "偵測到格式但無有效欄位可填，請用「欄位名: 值」。")
                    else:
                        await send_msg(ws, "未解析到 key:value，請用「欄位名: 值」。")

                await broadcast_module(moduleId)
                await broadcast_missing(moduleId)

            else:
                await send_msg(ws, f"未知的操作：{t}", role="system")
    except WebSocketDisconnect:
        pass
    finally:
        try:
            CONNS.get(moduleId, set()).discard(ws)
        except Exception:
            pass
