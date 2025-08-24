import React, { useState, useRef, useEffect } from 'react';
import {
  Send, Plus, Menu, MessageSquare, Trash2, Edit3,
  Check, X, File as FileIcon, Upload, Download
} from 'lucide-react';

// ✅ 更新版本重點：
// 1) 使用 WebSocket 連線 FastAPI /ws/chat，支援訊息即時傳送與流式接收。
// 2) 訊息來源區分 user、assistant (AI)、RAG 模組（未來擴充）、system 系統提示，依來源套用不同樣式。
// 3) AI 回答產生時顯示 loading/輸入中 指示器。
// 4) 若 AI 回答內容包含特殊標籤 [RAG]，將其內容加註「強化檢索結果」說明。
// 5) 輸入區支援 Enter 發送、Shift+Enter 換行。
// 6) 簡潔易讀的對話 UI，清楚區分使用者與 AI 訊息泡泡。
// 7) 保留擴充性，可串接日後強化模組（如 RAG 資料流等）。

const ChatInterface = () => {
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [conversations, setConversations] = useState([]);
  const [currentConversationId, setCurrentConversationId] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [editingConversationId, setEditingConversationId] = useState(null);
  const [editTitle, setEditTitle] = useState('');
  const [uploadError, setUploadError] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState([]);

  const messagesEndRef = useRef(null);
  const editInputRef = useRef(null);
  const fileInputRef = useRef(null);
  const ws = useRef(null);
  const fileUrlMap = useRef({});

  const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

  // 讀取對話列表
  useEffect(() => { fetchConversations(); }, []);

  // 切換對話時讀取訊息
  useEffect(() => {
    if (currentConversationId) fetchMessages(currentConversationId);
    else setMessages([]);
  }, [currentConversationId]);

  // 自動滾到底
  useEffect(() => {
    // Jest 的 JSDOM 環境不支援 scrollIntoView，需先確認函式存在
    const el = messagesEndRef.current;
    if (el && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isLoading]);

  // 編輯標題時自動聚焦
  useEffect(() => {
    if (editingConversationId && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingConversationId]);

  // 建立 WebSocket 連線並監聽訊息
  useEffect(() => {
    // 構造 WebSocket 連結 URL
    const baseUrl = API_URL.replace(/\/+$/, '');
    const wsProtocol = baseUrl.startsWith('https') ? 'wss' : 'ws';
    const wsUrl = wsProtocol + '://' + baseUrl.replace(/^https?:\/\//, '') + '/api/chat/ws/chat';
    ws.current = new WebSocket(wsUrl);
    ws.current.onopen = () => {
      console.log('WebSocket 連線已建立');
    };
    ws.current.onerror = (err) => {
      console.error('WebSocket 錯誤:', err);
    };
    ws.current.onclose = () => {
      console.log('WebSocket 連線已關閉');
      // 若回應尚未完成就中斷，將占位訊息替換為錯誤
      setStatusMessage('');
      setMessages(prev => prev.map(m =>
        m.isThinking ? { ...m, content: '連線中斷，請稍後重試。', isThinking: false } : m
      ));
      setIsLoading(false);
    };
    ws.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      const status = data.status;
      const msgText = data.message;
      const payload = data.payload;
      switch (status) {
        case 'nlu': // NLU 分析中
        case 'rag': // RAG 強化模組進行中
        case 'llm': // LLM 回答生成中
        case 'ethics': // 倫理檢查中
          // 更新處理進度提示
          setStatusMessage(msgText || '處理中...');
          break;
        case 'final':
          // 最終結果
          setStatusMessage('');
          if (payload && payload.conversation_id && !currentConversationId) {
            setCurrentConversationId(payload.conversation_id);
          }
          const aiMsg = {
            id: Date.now(),
            content: msgText || '抱歉，目前無法提供回應。',
            role: 'assistant',
            timestamp: new Date().toISOString(),
          };
          // 用 AI 回覆替換思考中占位
          setMessages(prev => prev.map(m => m.isThinking ? aiMsg : m));
          // 更新對話列表
          fetchConversations();
          // 標記處理完成
          setIsLoading(false);
          break;
        default:
          console.warn('收到未預期的訊息狀態:', status, msgText);
      }
    };
    return () => {
      if (ws.current) {
        ws.current.close();
      }
    };
  }, []);

  // 取得對話列表
  const fetchConversations = async () => {
    try {
      const res = await fetch(`${API_URL}/api/conversations`);
      const data = await res.json();
      const list = Array.isArray(data) ? data : [];
      setConversations(list);
      if (!currentConversationId && list.length > 0) {
        setCurrentConversationId(list[0].id);
      }
    } catch (err) {
      console.error('載入對話列表失敗:', err);
      setConversations([]);
    }
  };

  // 取得訊息
  const fetchMessages = async (convId) => {
    try {
      const res = await fetch(`${API_URL}/api/conversations/${convId}/messages`);
      const data = await res.json();
      setMessages(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('載入訊息失敗:', err);
      setMessages([]);
    }
  };

  // 上傳檔案（暫存到前端清單）
  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!['.doc', '.docx'].includes(ext)) {
      setUploadError('僅支援 .doc / .docx');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setUploadError('檔案大小不可超過 10MB');
      return;
    }
    setUploadError('');
    const url = URL.createObjectURL(file);
    const fileInfo = { id: Date.now(), file, name: file.name, size: file.size, url };
    setUploadedFiles(prev => [...prev, fileInfo]);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removeUploadedFile = (fileId) => {
    setUploadedFiles(prev => {
      const target = prev.find(f => f.id === fileId);
      if (target) URL.revokeObjectURL(target.url);
      return prev.filter(f => f.id !== fileId);
    });
  };

  // 實際丟到後端 /api/upload-document
  const uploadFileToServer = async (fileInfo, conversationId) => {
    const formData = new FormData();
    formData.append('file', fileInfo.file);
    if (conversationId) formData.append('conversation_id', conversationId);
    const response = await fetch(`${API_URL}/api/upload-document`, {
      method: 'POST',
      body: formData,
    });
    if (!response.ok) {
      let msg = '檔案上傳失敗';
      try {
        const error = await response.json();
        if (error?.detail) msg = error.detail;
      } catch {}
      throw new Error(msg);
    }
    return await response.json();
  };

  // 送出訊息
  const sendMessage = async () => {
    const content = inputMessage.trim();
    if ((!content && uploadedFiles.length === 0) || isLoading) return;
    setIsLoading(true);
    setUploadError('');
    // 有輸入文字則先插入「使用者訊息 + 思考中」占位
    let thinkingId = null;
    if (content) {
      const userMsg = {
        id: Date.now(),
        content,
        role: 'user',
        timestamp: new Date().toISOString(),
      };
      thinkingId = userMsg.id + 1;
      const thinkingMsg = {
        id: thinkingId,
        content: '🤖 思考中…',
        role: 'assistant',
        timestamp: new Date().toISOString(),
        isThinking: true,
      };
      setMessages(prev => [...prev, userMsg, thinkingMsg]);
      setInputMessage('');
    }
    try {
      // 確保有對話 ID
      let convId = currentConversationId;
      if (!convId) {
        const title = content
          ? content.substring(0, 50) + (content.length > 50 ? '…' : '')
          : uploadedFiles.length > 0
          ? `文件分析: ${uploadedFiles[0].name}`
          : '新對話';
        const res = await fetch(`${API_URL}/api/conversations`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title }),
        });
        if (!res.ok) throw new Error('建立新對話失敗');
        const newConv = await res.json();
        setConversations(prev => [newConv, ...prev]);
        setCurrentConversationId(newConv.id);
        convId = newConv.id;
      }
      // 先把暫存檔案全數丟後端
      for (const fileInfo of uploadedFiles) {
        try {
          setIsUploading(true);
          await uploadFileToServer(fileInfo, convId);
          fileUrlMap.current[fileInfo.name] = fileInfo.url;
        } catch (error) {
          console.error(`檔案 ${fileInfo.name} 上傳失敗:`, error);
          setUploadError(`檔案 ${fileInfo.name} 上傳失敗: ${error.message}`);
        } finally {
          setIsUploading(false);
        }
      }
      setUploadedFiles([]);
      // 若有文字，透過 WebSocket 發送訊息
      if (content) {
        const outgoing = { content: content, conversation_id: convId };
        try {
          ws.current.send(JSON.stringify(outgoing));
        } catch (err) {
          console.error('發送訊息錯誤:', err);
          // 傳送失敗則將「思考中」占位替換為錯誤訊息
          setMessages(prev => prev.map(m =>
            m.isThinking ? { ...m, content: '連接錯誤，無法送出訊息。', isThinking: false } : m
          ));
          throw err;
        }
      } else {
        // 僅檔案無文字提問 → 重新取得訊息（顯示已上傳的檔案訊息）
        await fetchMessages(convId);
      }
      // 更新側欄對話列表排序
      if (!content) {
        fetchConversations();
      }
    } catch (err) {
      console.error('發送訊息錯誤:', err);
      // 將占位替換成錯誤訊息
      setMessages(prev => prev.map(m =>
        m.isThinking ? { ...m, content: '連接錯誤，請稍後再試。', isThinking: false } : m
      ));
    } finally {
      setIsLoading(false);
    }
  };

  // 建立新對話
  const createNewConversation = async () => {
    try {
      const res = await fetch(`${API_URL}/api/conversations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: '新對話' }),
      });
      if (!res.ok) throw new Error(res.status);
      const newConv = await res.json();
      setConversations(prev => [newConv, ...prev]);
      setCurrentConversationId(newConv.id);
      setMessages([]);
      setUploadedFiles([]);
      setUploadError('');
    } catch (err) {
      console.error('建立新對話失敗:', err);
    }
  };

  // 刪除對話
  const deleteConversation = async (convId) => {
    if (!Array.isArray(conversations) || conversations.length <= 1) return;
    try {
      const res = await fetch(`${API_URL}/api/conversations/${convId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(res.status);
      setConversations(prev => prev.filter(c => c.id !== convId));
      if (currentConversationId === convId) {
        const remain = conversations.filter(c => c.id !== convId);
        setCurrentConversationId(remain[0]?.id || null);
        setUploadedFiles([]);
        setMessages([]);
      }
    } catch (err) {
      console.error('刪除對話失敗:', err);
    }
  };

  // 重新命名
  const startEditingTitle = (convId, currentTitle) => {
    setEditingConversationId(convId);
    setEditTitle(currentTitle);
  };
  const cancelEditingTitle = () => {
    setEditingConversationId(null);
    setEditTitle('');
  };
  const saveEditedTitle = async (convId) => {
    if (!editTitle.trim()) { cancelEditingTitle(); return; }
    try {
      const response = await fetch(`${API_URL}/api/conversations/${convId}/title`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: editTitle.trim() }),
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      setConversations(prev => prev.map(conv => (
        conv.id === convId
          ? { ...conv, title: editTitle.trim(), updated_at: new Date().toISOString() }
          : conv
      )));
      setEditingConversationId(null);
      setEditTitle('');
    } catch (error) {
      console.error('更新對話標題失敗:', error);
    }
  };

  // 小工具
  const formatTimestamp = (ts) => {
    if (!ts) return '';
    try {
      return new Date(ts).toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  const formatFileSize = (bytes) => {
    if (!bytes && bytes !== 0) return '';
    if (bytes === 0) return '0 Bytes';
    const k = 1024; const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const extractFileName = (content) => {
    const m = /^📎\s*已上傳檔案:\s*([^\n]+)/.exec(content || '');
    return m ? m[1].trim() : (content || '').replace(/^📎\s*/, '').split('\n')[0];
  };
  const getDownloadUrl = (msg) => {
    const name = msg.file_info?.filename || extractFileName(msg.content);
    if (fileUrlMap.current[name]) return fileUrlMap.current[name];
    const fileId = msg.file_info?.file_id;
    if (fileId) return `${API_URL}/api/download-document/${fileId}`;
    const parts = (msg.content || '').split('檔案內容:\n');
    if (parts.length > 1) {
      const blobUrl = URL.createObjectURL(new Blob([parts[1]], { type: 'text/plain' }));
      fileUrlMap.current[name] = blobUrl;
      return blobUrl;
    }
    return null;
  };
  const isFileMessage = (msg) => !!msg?.file_info || (typeof msg?.content === 'string' && msg.content.startsWith('📎'));

  return (
    <div className="flex h-screen bg-gray-900 text-white">
      {/* 側邊欄 */}
      <div className={`${sidebarOpen ? 'w-64' : 'w-0'} transition-all duration-300 bg-gray-800 flex flex-col overflow-hidden`}>
        <div className="p-4 border-b border-gray-700">
          <button onClick={createNewConversation} className="w-full flex items-center gap-2 px-4 py-3 bg-gray-700 hover:bg-gray-600 rounded-lg">
            <Plus size={16} /> 新對話
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {(Array.isArray(conversations) ? conversations : []).map(conv => (
            <div
              key={conv.id}
              onClick={() => editingConversationId !== conv.id && setCurrentConversationId(conv.id)}
              className={`group flex items-center gap-2 p-3 rounded-lg cursor-pointer transition-colors ${currentConversationId === conv.id ? 'bg-gray-700' : 'hover:bg-gray-700/50'}`}
            >
              <MessageSquare size={16} />
              <div className="flex-1 min-w-0">
                {editingConversationId === conv.id ? (
                  <input
                    ref={editInputRef}
                    value={editTitle}
                    onChange={e => setEditTitle(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') saveEditedTitle(conv.id); else if (e.key === 'Escape') cancelEditingTitle(); }}
                    onBlur={() => saveEditedTitle(conv.id)}
                    className="w-full bg-gray-600 text-sm px-2 py-1 rounded border border-gray-500 focus:outline-none"
                    onClick={e => e.stopPropagation()}
                  />
                ) : (
                  <>
                    <div className="truncate text-sm">{conv.title}</div>
                    <div className="text-xs text-gray-400">{formatTimestamp(conv.updated_at)}</div>
                  </>
                )}
              </div>
              {editingConversationId === conv.id ? (
                <div className="flex gap-1">
                  <button onClick={e => { e.stopPropagation(); saveEditedTitle(conv.id); }} className="p-1 text-green-400 hover:bg-gray-600 rounded"><Check size={12} /></button>
                  <button onClick={e => { e.stopPropagation(); cancelEditingTitle(); }} className="p-1 text-red-400 hover:bg-gray-600 rounded"><X size={12} /></button>
                </div>
              ) : (
                <div className="opacity-0 group-hover:opacity-100 flex gap-1">
                  <button onClick={e => { e.stopPropagation(); startEditingTitle(conv.id, conv.title); }} className="p-1 hover:bg-gray-600 rounded"><Edit3 size={12} /></button>
                  <button onClick={e => { e.stopPropagation(); deleteConversation(conv.id); }} className="p-1 text-red-400 hover:bg-gray-600 rounded"><Trash2 size={12} /></button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* 主區域 */}
      <div className="flex-1 flex flex-col">
        {/* 頂部工具列 */}
        <div className="flex items-center justify-between px-4 py-2 bg-gray-800 border-b border-gray-700">
          <button onClick={() => setSidebarOpen(o => !o)} className="p-2 hover:bg-gray-700 rounded"><Menu size={20} /></button>
          <div className="text-lg font-semibold">AI 對話系統</div>
          <div className="flex items-center gap-2">
            <input type="file" ref={fileInputRef} onChange={handleFileUpload} className="hidden" accept=".doc,.docx" />
            <button onClick={() => fileInputRef.current?.click()} disabled={isUploading || isLoading} className="p-2 hover:bg-gray-700 rounded flex-shrink-0" title="上傳檔案">
              <Upload size={18} />
            </button>
          </div>
        </div>

        {/* 準備上傳的檔案列表 */}
        {uploadedFiles.length > 0 && (
          <div className="bg-blue-900/50 p-3 border-b border-gray-700">
            <div className="text-sm text-blue-200 mb-2">準備上傳的檔案：</div>
            {uploadedFiles.map(fileInfo => (
              <div key={fileInfo.id} className="flex items-center gap-2 bg-blue-800/50 p-2 rounded mb-1">
                <FileIcon size={16} />
                <span className="flex-1 text-sm">{fileInfo.name}</span>
                <span className="text-xs text-gray-400">{formatFileSize(fileInfo.size)}</span>
                <a href={fileInfo.url} download={fileInfo.name} className="text-green-400 hover:text-green-300"><Download size={14} /></a>
                <button onClick={() => removeUploadedFile(fileInfo.id)} className="text-red-400 hover:text-red-300"><X size={14} /></button>
              </div>
            ))}
          </div>
        )}

        {/* 訊息列表 */}
        <div className="flex-1 overflow-y-auto p-4">
          <div className="space-y-4">
            {messages.map(msg => {
              // 根據訊息角色決定樣式
              if (msg.role === 'system') {
                return (
                  <div key={msg.id} className="flex justify-center">
                    <div className="text-xs text-gray-400 italic text-center">{msg.content}</div>
                  </div>
                );
              }
              const alignClass = msg.role === 'user' ? 'justify-end' : 'justify-start';
              let bubbleBgClass = '';
              if (msg.role === 'user') {
                bubbleBgClass = 'bg-blue-600 text-white';
              } else if (msg.role === 'assistant') {
                bubbleBgClass = 'bg-gray-700 text-white';
              } else if (msg.role === 'rag') { // RAG 模組訊息（未來擴充）
                bubbleBgClass = 'bg-green-700 text-white';
              } else {
                bubbleBgClass = 'bg-gray-600 text-white';
              }
              // 處理訊息內容，包括特殊 [RAG] 標註
              let contentElement;
              if (isFileMessage(msg)) {
                const fileName = msg.file_info?.filename || extractFileName(msg.content);
                const url = getDownloadUrl(msg);
                contentElement = (
                  <div className="flex items-center gap-2">
                    <FileIcon size={16} />
                    {url ? (
                      <a href={url} download={fileName} className="underline">{fileName}</a>
                    ) : (
                      <span className="underline">{fileName}</span>
                    )}
                  </div>
                );
              } else if (typeof msg.content === 'string' && msg.content.includes('[RAG]')) {
                const parts = [];
                let lastIndex = 0;
                let idx = 0;
                const ragRegex = /\[RAG\](.*?)\[RAG\]/g;
                let match;
                while ((match = ragRegex.exec(msg.content)) !== null) {
                  parts.push(msg.content.slice(lastIndex, match.index));
                  parts.push(
                    <span key={`rag-${msg.id}-${idx++}`} className="italic bg-gray-600/50 px-1 rounded">
                      {match[1]}
                      <span className="text-xs text-green-400 ml-1">(強化檢索結果)</span>
                    </span>
                  );
                  lastIndex = ragRegex.lastIndex;
                }
                parts.push(msg.content.slice(lastIndex));
                contentElement = <div className="whitespace-pre-wrap text-sm">{parts}</div>;
              } else {
                contentElement = <div className="whitespace-pre-wrap text-sm">{msg.content}</div>;
              }
              return (
                <div key={msg.id} className={`flex ${alignClass}`}>
                  <div className={`max-w-3xl p-3 rounded-lg ${bubbleBgClass} text-left`}>
                    {contentElement}
                    {msg.role !== 'system' && (
                      <div className="text-xs text-gray-300 mt-1 text-right">{formatTimestamp(msg.timestamp)}</div>
                    )}
                  </div>
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* 狀態訊息顯示區 */}
        {statusMessage && (
          <div className="px-4 py-2 text-sm text-gray-400 bg-gray-800 border-t border-b border-gray-700">
            {statusMessage}
          </div>
        )}

        {/* 輸入區 */}
        <div className={`flex items-end gap-2 px-4 py-3 ${statusMessage ? '' : 'border-t border-gray-700'} bg-gray-800`}>
          <button onClick={() => fileInputRef.current?.click()} disabled={isUploading || isLoading} className="p-2 hover:bg-gray-700 rounded flex-shrink-0" title="上傳檔案">
            <Upload size={18} />
          </button>
          <div className="flex-1 flex flex-col">
            <textarea
              rows={1}
              value={inputMessage}
              onChange={e => setInputMessage(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
              placeholder="輸入訊息，按 Enter 發送"
              className="flex-1 resize-none bg-gray-700 text-white px-3 py-2 rounded-lg focus:outline-none min-h-[40px]"
              style={{ maxHeight: '120px', height: 'auto' }}
            />
          </div>
          <button onClick={sendMessage} disabled={isLoading || (!inputMessage.trim() && uploadedFiles.length === 0)} className="p-3 bg-blue-600 hover:bg-blue-500 rounded-full disabled:opacity-50 flex-shrink-0" title="發送">
            <Send size={18} />
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatInterface;
