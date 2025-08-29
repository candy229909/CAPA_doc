
import React, { useEffect, useMemo, useRef, useState } from "react";
import { Upload, Database, Send, FileText, CheckCircle2, Circle, AlertTriangle, Loader2, RefreshCw, FileDown, Bot, HelpCircle, ListChecks, MessageSquarePlus, PlugZap } from "lucide-react";

/**
 * Template-Filler UI (React)
 * -------------------------------------------------------------
 * 支援：
 * 1) 上傳文件 + 模組名 → POST /api/file_data → 建立模組
 * 2) 讀取現有模組、顯示 structure / data / 進度 → GET /api/modules, /api/modules/{id}
 * 3) 使用者輸入訊息 → WebSocket /ws/fill?moduleId= → 後端即時解析填空
 * 4) 一鍵逐題詢問：ask_next / ask_key
 * 5) 匯出 → GET /api/modules/{id}/export
 */

// The file name is TemplateFilterApp.jsx.  Export a component with a matching
// name for clarity.  Previously the function was named TemplateFillerApp,
// which could cause confusion.
export default function TemplateFilterApp() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white text-gray-900">
      <div className="mx-auto max-w-6xl px-4 py-8">
        <header className="mb-6 flex items-center justify-between">
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <FileText className="h-6 w-6" /> 模組填空助手
          </h1>
          <div className="text-sm text-gray-500 flex items-center gap-2">
            <PlugIndicator /> 支援 WebSocket 流式/逐題詢問 + 匯出
          </div>
        </header>

        <div className="grid gap-6 md:grid-cols-3">
          <section className="md:col-span-1 space-y-6">
            <ModuleUploader />
            <ModulePicker />
          </section>

          <section className="md:col-span-2 space-y-6">
            <TemplateOverview />
            <ChatFiller />
          </section>
        </div>
      </div>
    </div>
  );
}

/** --- 簡易全域狀態 bus --- */
const bus = {
  listeners: new Set(),
  state: {
    modules: [],
    selectedModuleId: null,
    moduleDetail: null,
    loadingModule: false,
    socket: null,
    socketReady: false,
    missingKeys: [],
  },
  subscribe(fn) {
    this.listeners.add(fn);
    fn(this.state);
    return () => this.listeners.delete(fn);
  },
  set(patch) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((fn) => fn(this.state));
  },
};

function useBusState() {
  const [s, setS] = useState(bus.state);
  useEffect(() => bus.subscribe(setS), []);
  return s;
}

/** 模組上傳 */
function ModuleUploader() {
  const [file, setFile] = useState(null);
  const [moduleName, setModuleName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const onFileChange = (e) => setFile(e.target.files?.[0] ?? null);

  const handleUpload = async () => {
    try {
      setError("");
      if (!file) throw new Error("請選擇檔案");
      if (!moduleName.trim()) throw new Error("請輸入模組名稱");
      setSubmitting(true);
      const fd = new FormData();
      fd.append("file", file);
      fd.append("moduleName", moduleName.trim());
      const res = await fetch("/api/file_data", { method: "POST", body: fd });
      if (!res.ok) {
        // Attempt to extract error details if available
        let msg = `上傳失敗：${res.status}`;
        try {
          const err = await res.json();
          if (err?.detail) msg = err.detail;
        } catch {}
        throw new Error(msg);
      }
      let json;
      try {
        json = await res.json();
      } catch {
        json = null;
      }
      if (json && json.moduleId) {
        await refreshModules(json.moduleId);
      } else {
        await refreshModules();
      }
      setFile(null);
      setModuleName("");
    } catch (e) {
      setError(e.message || "上傳失敗");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="rounded-2xl border bg-white p-4 shadow-sm">
      <h2 className="mb-2 text-lg font-medium flex items-center gap-2"><Upload className="h-5 w-5" /> 上傳文件並建立模組</h2>
      <input className="mb-2 w-full rounded-xl border px-3 py-2 text-sm" placeholder="模組名稱" value={moduleName} onChange={(e) => setModuleName(e.target.value)} />
      <input type="file" onChange={onFileChange} className="mb-2" />
      {error && <div className="text-red-500 text-sm mb-2">{error}</div>}
      <button onClick={handleUpload} disabled={submitting} className="rounded-xl bg-indigo-600 px-3 py-2 text-sm text-white">{submitting ? "處理中..." : "上傳並建立"}</button>
    </div>
  );
}

/** 模組選擇 */
function ModulePicker() {
  const { modules, selectedModuleId } = useBusState();
  useEffect(() => { refreshModules(); }, []);
  return (
    <div className="rounded-2xl border bg-white p-4 shadow-sm">
      <h2 className="mb-2 text-lg font-medium flex items-center gap-2"><Database className="h-5 w-5" /> 現有模組</h2>
      <div className="space-y-2 max-h-60 overflow-auto">
        {modules.map((m) => (
          <button
            key={m.id}
            onClick={() => loadModuleDetail(m.id)}
            className={`block w-full rounded-xl border px-3 py-2 text-sm text-left ${selectedModuleId === m.id ? "border-indigo-500 bg-indigo-50" : "hover:bg-gray-50"}`}
          >
            {m.name}
          </button>
        ))}
      </div>
    </div>
  );
}

/** 模組概覽 */
function TemplateOverview() {
  const { moduleDetail } = useBusState();
  if (!moduleDetail) return <div className="rounded-2xl border bg-white p-4 shadow-sm">請先選擇模組</div>;
  const fields = moduleDetail.data ?? [];
  const filled = fields.filter(f => (f.value ?? "").toString().trim()!=="").length;
  const pct = fields.length? Math.round(filled/fields.length*100):0;
  return (
    <div className="rounded-2xl border bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium flex items-center gap-2"><ListChecks className="h-5 w-5" /> 模組概覽</h2>
        <span className="text-sm text-gray-500">{filled}/{fields.length}（{pct}%）</span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        {fields.map((f,idx)=>{
          const ok = (f.value ?? "").toString().trim()!=="";
          return (
            <div key={idx} className="rounded-lg border px-3 py-2 text-sm flex items-center justify-between">
              <div className="truncate">{f.key}</div>
              {ok ? <CheckCircle2 className="h-4 w-4 text-green-600" /> : <AlertTriangle className="h-4 w-4 text-amber-600" />}
            </div>
          );
        })}
      </div>
      <div className="mt-3">
        <a
          className="inline-flex items-center gap-2 text-sm text-indigo-600 hover:underline"
          href={`/api/modules/${moduleDetail.moduleId}/export`}
        >
          <FileDown className="h-4 w-4" /> 匯出
        </a>
      </div>
    </div>
  );
}

/** 對話填空 */
function ChatFiller() {
  const listRef = useRef(null);
  const { selectedModuleId, moduleDetail, socketReady, missingKeys } = useBusState();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [asking, setAsking] = useState(false);
  const [autoAsk, setAutoAsk] = useState(true);

  // 計算尚未填欄位（前端 fallback）
  const computedMissing = useMemo(()=>{
    const fields = moduleDetail?.data ?? [];
    return fields.filter(f => (f.value ?? "").toString().trim()==="").map(f=>f.key);
  }, [moduleDetail]);

  useEffect(()=>{
    if (!selectedModuleId) return;
    // 建 ws url
    const loc = window.location;
    const wsProto = loc.protocol === "https:" ? "wss" : "ws";
    const wsUrl = `${wsProto}://${loc.host}/ws/fill?moduleId=${selectedModuleId}`;
    const ws = new WebSocket(wsUrl);
    bus.set({ socket: ws, socketReady: false });

    let keepAlive = null;
    ws.onopen = () => { 
      bus.set({ socketReady: true });
      keepAlive = setInterval(()=>{ try{ ws.send(JSON.stringify({type:"ping"})); }catch{} }, 20000);
      try { ws.send(JSON.stringify({ type:'status', moduleId: selectedModuleId })); } catch {}
    };
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        switch (msg.type) {
          case "message": setMessages(prev=>[...prev, { role: msg.role || "assistant", content: msg.content }]); break;
          case "module": bus.set({ moduleDetail: msg.moduleDetail }); break;
          case "missing": bus.set({ missingKeys: msg.keys || [] }); break;
          case "ask": {
            // If the server asks a specific key, show a message prompting the user to provide it.
            const prompt = msg.prompt || `請提供「${msg.key}」的資訊。`;
            setMessages((prev) => [
              ...prev,
              {
                role: 'assistant',
                content: `【待填欄位】${msg.key}\n${prompt}`,
              },
            ]);
            break;
          }
          default: break;
        }
      } catch {}
    };
    ws.onclose = () => {
      bus.set({ socket: null, socketReady: false });
      if (keepAlive) clearInterval(keepAlive);
    };
    return () => { try{ ws.close(); }catch{}; if (keepAlive) clearInterval(keepAlive); };
  }, [selectedModuleId]);

  // 自動追問模式
  useEffect(() => {
    if (!autoAsk || asking) return;
    const keys = (missingKeys.length? missingKeys : computedMissing);
    if (!keys.length) return;
    askNext(keys[0]);
  }, [autoAsk, missingKeys, computedMissing]);

  // 捲動到底
  useEffect(()=>{ listRef.current?.scrollTo({ top:listRef.current.scrollHeight, behavior:"smooth" }); }, [messages]);

  const sendMessage = () => {
    const text = input.trim();
    if (!text) return;
    setInput("");
    setMessages(prev=>[...prev, { role:'user', content: text }]);
    if (bus.state.socket) {
      try { bus.state.socket.send(JSON.stringify({ type:'user_message', content: text })); } catch {}
    }
  };

  const askNext = async (keyFromList) => {
    const nextKey = keyFromList ?? (missingKeys[0] || computedMissing[0]);
    if (!nextKey) return;
    setAsking(true);
    const payload = { type:'ask_key', moduleId: selectedModuleId, key: nextKey };
    try { bus.state.socket?.send(JSON.stringify(payload)); } catch {}
    setTimeout(()=> setAsking(false), 400); // 小延遲避免狂按
  };

  const rows = (moduleDetail?.data ?? []);
  return (
    <div className="rounded-2xl border bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-medium flex items-center gap-2"><Bot className="h-5 w-5" /> 填空對話</h2>
        <label className="text-sm flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={autoAsk} onChange={e=>setAutoAsk(e.target.checked)} />
          自動逐題詢問
        </label>
      </div>

      <div ref={listRef} className="h-60 overflow-auto rounded-xl border p-3 text-sm space-y-2 bg-gray-50">
        {messages.map((m,i)=>(
          <div key={i} className={m.role==='user'?'text-right':''}>
            <div
              className={`inline-block rounded-xl px-3 py-2 ${m.role === 'user' ? 'bg-indigo-600 text-white' : 'bg-white border'}`}
            >
              {m.content}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 flex gap-2">
        <input className="flex-1 rounded-xl border px-3 py-2 text-sm" placeholder="輸入訊息，例如：日期: 2025-08-30" value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>{ if(e.key==='Enter') sendMessage(); }} />
        <button onClick={sendMessage} className="rounded-xl bg-indigo-600 px-3 py-2 text-sm text-white inline-flex items-center gap-1"><Send className="h-4 w-4" /> 送出</button>
        <button onClick={()=>askNext()} disabled={asking} className="rounded-xl bg-amber-600 px-3 py-2 text-sm text-white inline-flex items-center gap-1"><HelpCircle className="h-4 w-4" /> 逐題詢問</button>
      </div>

      <div className="mt-4">
        <h3 className="text-sm font-medium text-gray-700 mb-2">目前欄位</h3>
        <div className="grid grid-cols-2 gap-2">
          {rows.map((kv, i)=>(
            <div key={i} className="rounded-lg border bg-white px-3 py-2 text-sm">
              <div className="font-medium">{kv.key}</div>
              <div className="text-gray-600 whitespace-pre-wrap">{kv.value || <span className="italic text-gray-400">（尚未填寫）</span>}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** 小圖示：顯示 WS 連線狀態 */
function PlugIndicator() {
  const { socketReady } = useBusState();
  return (
    <span className="inline-flex items-center gap-1">{socketReady ? <PlugZap className="h-4 w-4" /> : <Loader2 className="h-4 w-4 animate-spin" />} {socketReady ? "已連線" : "連線中…"}</span>
  );
}

// ---- helpers for API ----
async function refreshModules(selectId) {
  try {
    const res = await fetch("/api/modules");
    if (!res.ok) {
      // If the server returns a non‑2xx status, do not attempt to parse JSON.  It might be an HTML error page.
      console.error('Failed to load modules', res.status);
      bus.set({ modules: [] });
      return;
    }
    const items = await res.json();
    bus.set({ modules: Array.isArray(items) ? items : [] });
    if (selectId) {
      await loadModuleDetail(selectId);
    }
  } catch (e) {
    console.error('Error loading modules', e);
    bus.set({ modules: [] });
  }
}

async function loadModuleDetail(id) {
  try {
    const res = await fetch(`/api/modules/${id}`);
    if (!res.ok) {
      console.error('Failed to load module detail', res.status);
      bus.set({ selectedModuleId: id, moduleDetail: null });
      return;
    }
    const detail = await res.json();
    bus.set({ selectedModuleId: id, moduleDetail: detail });
  } catch (e) {
    console.error('Error loading module detail', e);
    bus.set({ selectedModuleId: id, moduleDetail: null });
  }
}
