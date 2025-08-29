import React, { useEffect, useRef, useState } from "react";
import { Upload, Send, HelpCircle, Database, FileDown, Wifi } from "lucide-react";

/** 從環境變數取得後端 API 位址（例：http://localhost:8000） */
const API_BASE = (process.env.REACT_APP_API_URL || "http://localhost:8000").replace(/\/+$/, "");
const api = (p) => `${API_BASE}${p.startsWith("/") ? p : "/" + p}`;
const wsBase = API_BASE.replace(/^http/i, "ws"); // http->ws, https->wss

/** 依 moduleId 組兩個可用的 WS URL（主/備援） */
const wsUrlsFor = (moduleId) => [
  `${wsBase}/ws/fill?moduleId=${encodeURIComponent(moduleId)}`,                 // 主要（你後端 txt）
  `${wsBase}/api/template_filter/ws/fill?moduleId=${encodeURIComponent(moduleId)}`, // 備援（若你有掛）
];

export default function TemplateFilterApp() {
  // 左側：上傳/列表
  const [moduleName, setModuleName] = useState("");
  const [file, setFile] = useState(null);
  const [modules, setModules] = useState([]);
  const [selectedModuleId, setSelectedModuleId] = useState(null);

  // 右側：目前模組細節 + 對話
  const [current, setCurrent] = useState(null); // {id,name,progress,...}
  const [messages, setMessages] = useState([]); // [{id,role,content}]
  const [input, setInput] = useState("");
  const [banner, setBanner] = useState(null);

  // WS
  const wsRef = useRef(null);
  const [socketReady, setSocketReady] = useState(false);
  const keepAliveRef = useRef(null);

  const pushMsg = (role, content) =>
    setMessages((prev) => [...prev, { id: Date.now() + Math.random(), role, content }]);

  /** 讀取模組列表 */
  const refreshModules = async () => {
    try {
      const res = await fetch(api("/api/modules"));
      if (!res.ok) throw new Error(`載入模組失敗 (${res.status})`);
      const data = await res.json();
      setModules(Array.isArray(data) ? data : []);
    } catch (e) {
      setModules([]);
      setBanner({ type: "error", text: e.message || "載入模組失敗" });
    }
  };
  useEffect(() => { refreshModules(); }, []);

  /** 讀取單一模組細節，並連線 WS */
  const loadModuleDetail = async (moduleId) => {
    try {
      const res = await fetch(api(`/api/modules/${moduleId}`));
      if (!res.ok) throw new Error(`讀取模組失敗 (${res.status})`);
      const info = await res.json();
      setCurrent(info);
      setSelectedModuleId(moduleId);
    } catch (e) {
      setBanner({ type: "error", text: e.message || "讀取模組失敗" });
    }
  };

  /** 連線 WS（主要路徑失敗→自動改用備援） */
  const connectWS = (moduleId) => {
    // 關閉舊連線
    try { wsRef.current?.close(); } catch {}
    setSocketReady(false);
    if (!moduleId) return;

    const urls = wsUrlsFor(moduleId);
    let i = 0;
    const open = () => {
      const ws = new WebSocket(urls[i]);
      wsRef.current = ws;

      ws.onopen = () => {
        setSocketReady(true);
        // 保活，避免閒置被關
        keepAliveRef.current = setInterval(() => {
          try { ws.send(JSON.stringify({ type: "ping" })); } catch {}
        }, 15000);
        // 要求後端推送缺漏鍵狀態（若有支援）
        try { ws.send(JSON.stringify({ type: "status" })); } catch {}
      };

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          switch (msg.type) {
            case "message":
              if (msg.role && msg.content) pushMsg(msg.role, msg.content);
              break;
            case "ask":
              // 後端逐題詢問提示
              pushMsg("assistant", `【待填欄位】${msg.key}\n${msg.prompt || `請提供「${msg.key}」的資訊。`}`);
              break;
            case "module":
              if (msg.moduleDetail) setCurrent(msg.moduleDetail);
              break;
            case "missing":
              // 可在 UI 顯示缺漏鍵清單（如果你要）
              break;
            default:
              // 靜默忽略其他型別
              break;
          }
        } catch {
          // 有些情況後端可能傳純文字
          pushMsg("assistant", ev.data);
        }
      };

      ws.onclose = () => {
        setSocketReady(false);
        if (keepAliveRef.current) { clearInterval(keepAliveRef.current); keepAliveRef.current = null; }
        // 第一次失敗嘗試備援
        if (i === 0) { i = 1; open(); }
      };

      ws.onerror = () => { /* 交給 onclose 做 fallback */ };
    };

    open();
  };

  /** 當選擇模組改變 → 重新連線 WS */
  useEffect(() => {
    if (!selectedModuleId) return;
    connectWS(selectedModuleId);
    return () => {
      try { wsRef.current?.close(); } catch {}
      if (keepAliveRef.current) { clearInterval(keepAliveRef.current); keepAliveRef.current = null; }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedModuleId]);

  /** 上傳並建立模組 */
  const handleUpload = async () => {
    if (!moduleName.trim()) return setBanner({ type: "error", text: "請輸入模組名稱" });
    if (!file) return setBanner({ type: "error", text: "請選擇檔案（.txt / .docx）" });

    const fd = new FormData();
    fd.append("moduleName", moduleName.trim());
    fd.append("file", file);

    try {
      const res = await fetch(api("/api/file_data"), { method: "POST", body: fd });
      if (!res.ok) {
        let msg = `上傳失敗 (${res.status})`;
        try { const j = await res.json(); if (j?.detail) msg = j.detail; } catch {}
        throw new Error(msg);
      }
      const json = await res.json(); // { moduleId, structure, data }
      setModuleName(""); setFile(null);
      pushMsg("system", "✅ 模組建立完成");

      await refreshModules();
      if (json?.moduleId) {
        await loadModuleDetail(json.moduleId); // 會觸發 selectedModuleId → connectWS
      }
    } catch (e) {
      setBanner({ type: "error", text: e.message || "上傳失敗" });
    }
  };

  /** 送出（自由輸入，後端會嘗試抽取 key:value） */
  const sendMessage = async () => {
    if (!socketReady || !wsRef.current || !selectedModuleId) return;
    const content = (input || "").trim();
    if (!content) return;
    try {
      wsRef.current.send(JSON.stringify({ type: "user_message", content }));
      pushMsg("user", content);
      setInput("");
    } catch (e) {
      setBanner({ type: "error", text: "WS 發送失敗" });
    }
  };

  /** 逐題詢問（請後端詢問下一個缺漏鍵） */
  const askNext = async () => {
    if (!socketReady || !wsRef.current || !selectedModuleId) return;
    pushMsg("system", "🔎 逐題詢問…");
    try {
      wsRef.current.send(JSON.stringify({ type: "ask_next" }));
    } catch (e) {
      setBanner({ type: "error", text: "WS 發送失敗" });
    }
  };

  return (
    <div className="p-4">
      <div className="text-xl font-semibold mb-4 flex items-center gap-2">
        <span role="img" aria-label="doc">📄</span> 模組填空助手
        <div className="ml-auto text-sm text-gray-500 flex items-center gap-2">
          <Wifi size={14} />
          {socketReady ? "已連線 WebSocket" : "未連線"}
        </div>
      </div>

      {banner && (
        <div className={`mb-3 rounded px-3 py-2 text-sm ${banner.type === "error" ? "bg-red-100 text-red-700" : "bg-blue-100 text-blue-700"}`}>
          {banner.text}
        </div>
      )}

      <div className="grid grid-cols-12 gap-4">
        {/* 左：上傳 + 模組列表 */}
        <div className="col-span-4 space-y-4">
          <div className="border rounded-lg p-4">
            <div className="font-medium mb-2">上傳文件並建立模組</div>
            <input
              placeholder="模組名稱"
              value={moduleName}
              onChange={(e) => setModuleName(e.target.value)}
              className="w-full border rounded px-2 py-1 mb-2"
            />
            <div className="flex items-center gap-2 mb-2">
              <label className="border rounded px-2 py-1 cursor-pointer bg-gray-50">
                選擇檔案
                <input
                  type="file"
                  className="hidden"
                  accept=".txt,.doc,.docx"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                />
              </label>
              <div className="text-sm text-gray-600 truncate">{file?.name || "尚未選擇"}</div>
            </div>
            <button onClick={handleUpload} className="px-3 py-2 rounded bg-indigo-600 text-white inline-flex items-center gap-1">
              <Upload size={16} /> 上傳並建立
            </button>
          </div>

          <div className="border rounded-lg p-4">
            <div className="font-medium mb-2 flex items-center gap-2">
              <Database size={16} /> 現有模組
            </div>
            <div className="space-y-2 max-h-[360px] overflow-auto">
              {modules.length === 0 && <div className="text-sm text-gray-500">尚無模組</div>}
              {modules.map((m) => (
                <div
                  key={m.id}
                  className={`p-2 border rounded cursor-pointer ${selectedModuleId === m.id ? "bg-indigo-50 border-indigo-300" : "hover:bg-gray-50"}`}
                  onClick={() => loadModuleDetail(m.id)}
                >
                  <div className="text-sm font-medium truncate">{m.name || m.title || m.id}</div>
                  {typeof m.progress === "number" && (
                    <div className="text-xs text-gray-500">完成度：{Math.round(m.progress * 100)}%</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 右：對話區 */}
        <div className="col-span-8 space-y-4">
          <div className="border rounded-lg p-4">
            <div className="font-medium mb-2">{current ? `模組：${current.name || current.id}` : "請先選擇模組"}</div>
            {current && (
              <div className="mb-2 text-sm text-gray-600">
                {typeof current.progress === "number" && <>完成度：{Math.round(current.progress * 100)}%</>}
                <button
                  onClick={async () => {
                    try {
                      const res = await fetch(api(`/api/modules/${current.id}/export`));
                      if (!res.ok) throw new Error(`匯出失敗 (${res.status})`);
                      const blob = await res.blob();
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement("a");
                      a.href = url; a.download = `${current?.name || "module"}.txt`; a.click();
                      URL.revokeObjectURL(url);
                    } catch (e) {
                      setBanner({ type: "error", text: e.message || "匯出失敗" });
                    }
                  }}
                  className="ml-2 px-2 py-1 text-sm rounded bg-gray-200 hover:bg-gray-300 inline-flex items-center gap-1"
                >
                  <FileDown size={14} /> 匯出
                </button>
              </div>
            )}

            <div className="h-64 border rounded p-2 overflow-auto bg-white">
              {messages.length === 0 && (
                <div className="text-gray-400 text-sm">（等待操作… 可按「逐題詢問」或直接輸入「欄位: 值」）</div>
              )}
              {messages.map((m) => (
                <div key={m.id} className={`mb-1 text-sm ${m.role === "user" ? "text-right" : "text-left"}`}>
                  <span className={`inline-block px-2 py-1 rounded ${m.role === "user" ? "bg-indigo-600 text-white" : "bg-gray-100"}`}>
                    {m.content}
                  </span>
                </div>
              ))}
            </div>

            <div className="mt-2 flex items-center gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
                placeholder="輸入：『欄位名: 值』或一般描述"
                className="flex-1 border rounded px-2 py-2"
              />
              <button onClick={sendMessage} disabled={!socketReady || !selectedModuleId || !input.trim()} className="px-3 py-2 rounded bg-indigo-600 text-white inline-flex items-center gap-1">
                <Send size={16} /> 送出
              </button>
              <button onClick={askNext} disabled={!socketReady || !selectedModuleId} className="px-3 py-2 rounded bg-orange-500 text-white inline-flex items-center gap-1">
                <HelpCircle size={16} /> 逐題詢問
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
