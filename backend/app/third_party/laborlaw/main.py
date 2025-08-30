from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from pathlib import Path
import uuid
import json
from loguru import logger

from .config import settings
from .extractors import UnifiedFileTextExtractor, SUPPORTED
from .chunker import make_chunks
from .llm_5w2h import ask_ollama_5w2h, ask_ollama_svo, ensemble_keywords, ask_ollama_qa
from .neo4j_io import Neo4jClient

app = FastAPI(title="Labor Law Cleaner (FastAPI)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PipelineResult(BaseModel):
    doc_id: str
    filename: str
    processed_txt: str
    chunks: int
    json_dir: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
def home_page():
    return """<!doctype html>
<html>
  <body>
    <h2>勞基法文本清洗（5W2H + SVO） & 問答測試</h2>
    <form action="/pipeline" method="post" enctype="multipart/form-data">
      <p>選擇檔案（可多選）：<input name="files" type="file" multiple></p>
      <label><input type="checkbox" name="to_neo4j" value="1" checked> 同步寫入 Neo4j</label>
      <button type="submit">執行整條管線</button>
    </form>
    <hr>
    <h3>快速問答</h3>
    <input id="q" style="width:60%" placeholder="例如：休息日加班怎麼算？引勞基法條文" />
    <button onclick="ask()">提問</button>
    <pre id="ans"></pre>
    <script>
    async function ask(){
      const q = document.getElementById('q').value;
      const r = await fetch('/ask', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({question:q, top_k:6})});
      const j = await r.json();
      document.getElementById('ans').textContent = JSON.stringify(j, null, 2);
    }
    </script>
    <p>或改用 <a href="/docs">Swagger UI</a></p>
  </body>
</html>"""

@app.post("/upload-extract", response_model=PipelineResult)
async def upload_and_extract(files: List[UploadFile] = File(...)):
    ext = UnifiedFileTextExtractor()
    file = files[0]
    filename = (file.filename or "uploaded.bin")
    safe_name = Path(filename).name
    raw_path = Path(settings.INPUT_DIR) / safe_name
    with raw_path.open("wb") as w:
        w.write(await file.read())

    text = ext.extract(raw_path)
    doc_id = uuid.uuid4().hex[:16]
    txt_path = Path(settings.PROCESSED_DIR) / f"{doc_id}.txt"
    txt_path.write_text(text, encoding="utf-8")

    chs = make_chunks(text)
    json_dir = Path(settings.OUTPUT_JSON_DIR) / doc_id
    json_dir.mkdir(parents=True, exist_ok=True)
    for i, ch in enumerate(chs):
        (json_dir / f"chunk_{i:04d}.json").write_text(json.dumps({"text": ch}, ensure_ascii=False), "utf-8")

    return PipelineResult(
        doc_id=doc_id,
        filename=safe_name,
        processed_txt=str(txt_path),
        chunks=len(chs),
        json_dir=str(json_dir)
    )

class Run5W2HReq(BaseModel):
    doc_id: str
    max_chunks: Optional[int] = None

@app.post("/run-5w2h")
async def run_5w2h(req: Run5W2HReq):
    json_dir = Path(settings.OUTPUT_JSON_DIR) / req.doc_id
    if not json_dir.exists():
        return {"error": f"JSON dir not found: {json_dir}"}

    items = []
    for p in sorted(json_dir.glob("chunk_*.json")):
        d = json.loads(p.read_text("utf-8"))
        items.append((p, d.get("text", "")))

    if req.max_chunks is not None:
        items = items[: req.max_chunks]

    results: List[Dict[str, Any]] = []

    for i, (path, text) in enumerate(items):
        data_5w2h = await ask_ollama_5w2h(text)
        data_svo  = await ask_ollama_svo(text)
        # 多模型集成關鍵字
        best_kws  = await ensemble_keywords(text, data_5w2h.get("keywords", []))
        out = {
            "chunk_id": f"{req.doc_id}_{i:04d}",
            "idx": i,
            "text": text,
            **data_5w2h,
            "keywords": best_kws,
            "svo": data_svo.get("triples", []),
        }
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), "utf-8")
        results.append(out)

    return {"doc_id": req.doc_id, "chunks": len(results)}

class ImportNeo4jReq(BaseModel):
    doc_id: str
    name: Optional[str] = None
    doc_type: Optional[str] = None

@app.post("/neo4j/import")
async def neo4j_import(req: ImportNeo4jReq):
    json_dir = Path(settings.OUTPUT_JSON_DIR) / req.doc_id
    if not json_dir.exists():
        return {"error": f"JSON dir not found: {json_dir}"}

    chunks = []
    for i, p in enumerate(sorted(json_dir.glob("chunk_*.json"))):
        d = json.loads(p.read_text("utf-8"))
        if "chunk_id" not in d:
            d = {
                "chunk_id": f"{req.doc_id}_{i:04d}",
                "idx": i,
                "text": d.get("text", ""),
                "who": [],
                "what": "",
                "when": "",
                "where": "",
                "why": "",
                "how": "",
                "how_much": "",
                "law_refs": [],
                "keywords": [],
                "svo": [],
                "confidence": 0.0,
            }
        chunks.append(d)

    nc = Neo4jClient()
    try:
        nc.import_doc(req.doc_id, req.name or req.doc_id, chunks, doc_type=req.doc_type)
    except Exception as e:
        logger.exception(f"[IMPORT] failed doc_id={req.doc_id}")
        try:
            nc.close()
        finally:
            pass
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        try:
            nc.close()
        except Exception:
            pass

    return {"doc_id": req.doc_id, "imported_chunks": len(chunks)}

class AskReq(BaseModel):
    question: str
    top_k: int = 6

@app.post("/ask")
async def ask(req: AskReq):
    nc = Neo4jClient()
    try:
        chunks, used_kws = nc.search_chunks(req.question, top_k=req.top_k)
    finally:
        nc.close()

    qa = await ask_ollama_qa(req.question, chunks)
    return {
        "question": req.question,
        "used_keywords": used_kws,
        "answer": qa["answer"],
        "sources": qa["sources"],
        "retrieved": [{"chunk_id": c["chunk_id"], "score": c.get("score", 0)} for c in chunks]
    }

# 便捷表單（整條管線）
@app.post("/pipeline", response_class=HTMLResponse)
async def pipeline(files: List[UploadFile] = File(...), to_neo4j: Optional[str] = Form(None)):
    up = await upload_and_extract(files)
    await run_5w2h(Run5W2HReq(doc_id=up.doc_id))
    if to_neo4j == "1":
        await neo4j_import(ImportNeo4jReq(doc_id=up.doc_id, name=up.filename, doc_type="案例"))
    html = f"""<!doctype html>
<html><body>
  <h3>完成：{up.filename}</h3>
  <ul>
    <li>doc_id：{up.doc_id}</li>
    <li>純文字：{up.processed_txt}</li>
    <li>chunks：{up.chunks}</li>
    <li>JSON 目錄：{up.json_dir}</li>
  </ul>
  <p><a href='/'>'回首頁進行問答測試</a> ｜ <a href='/docs'>Swagger UI</a></p>
</body></html>"""
    return HTMLResponse(content=html, status_code=200)