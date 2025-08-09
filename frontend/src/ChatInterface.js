import React, { useState, useRef, useEffect } from 'react';
import {
  Send, Plus, Menu, MessageSquare, Trash2, Edit3,
  Check, X, File as FileIcon, Upload
} from 'lucide-react';

const ChatInterface = () => {
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
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

  const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

  useEffect(() => { fetchConversations(); }, []);

  useEffect(() => {
    if (currentConversationId) {
      fetchMessages(currentConversationId);
    } else {
      setMessages([]);
    }
  }, [currentConversationId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  useEffect(() => {
    if (editingConversationId && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingConversationId]);

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
    const fileInfo = { id: Date.now(), file, name: file.name, size: file.size };
    setUploadedFiles(prev => [...prev, fileInfo]);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removeUploadedFile = (fileId) => {
    setUploadedFiles(prev => prev.filter(f => f.id !== fileId));
  };

  const uploadFileToServer = async (fileInfo, conversationId) => {
    const formData = new FormData();
    formData.append('file', fileInfo.file);
    if (conversationId) formData.append('conversation_id', conversationId);

    const response = await fetch(`${API_URL}/api/upload-document`, {
      method: 'POST',
      body: formData
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

  // --- 自動判斷是否用 NLU：先調 /api/nlu，並結合關鍵字後援 ---
  const decideUseNLU = async (content) => {
    const kwHit = /育嬰|解雇|開除|加班|工時|資遣|懲戒|勞保|職災|契約|資方|勞方|工資|勞基法|勞動契約/.test(content);
    try {
      const res = await fetch(`${API_URL}/api/nlu`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: content })
      });
      if (!res.ok) return kwHit;
      const data = await res.json();
      const intent = (data?.intent || '').toLowerCase();
      // 你可在此加入更多 intent 類別
      const nluHit = ['statute_query', 'termination_query'].includes(intent);
      return nluHit || kwHit;
    } catch {
      return kwHit; // 後援
    }
  };

  const sendMessage = async () => {
    const content = inputMessage.trim();
    if ((!content && uploadedFiles.length === 0) || isLoading) return;

    setIsLoading(true);
    setUploadError('');

    // 有文字就先加到畫面 & 放思考中占位
    let thinkingId = null;
    if (content) {
      const userMsg = {
        id: Date.now(),
        content,
        role: 'user',
        timestamp: new Date().toISOString()
      };
      thinkingId = userMsg.id + 1;
      const thinkingMsg = {
        id: thinkingId,
        content: '🤖 思考中…',
        role: 'assistant',
        timestamp: new Date().toISOString(),
        isThinking: true
      };
      setMessages(prev => [...prev, userMsg, thinkingMsg]);
      setInputMessage('');
    }

    try {
      // 確保有對話 ID
      let convId = currentConversationId;
      if (!convId) {
        const title = content
          ? content.substring(0, 50) + (content.length > 50 ? '...' : '')
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

      // 先把暫存檔案全部丟上後端
      for (const fileInfo of uploadedFiles) {
        try {
          await uploadFileToServer(fileInfo, convId);
        } catch (error) {
          console.error(`檔案 ${fileInfo.name} 上傳失敗:`, error);
          setUploadError(`檔案 ${fileInfo.name} 上傳失敗: ${error.message}`);
        }
      }
      setUploadedFiles([]);

      // 有文字才打 /api/chat
      if (content) {
        const use_nlu = await decideUseNLU(content);

        const res = await fetch(`${API_URL}/api/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: content,
            conversation_id: convId,
            model: 'gemma3n:e2b',
            use_nlu,                     // ✅ 自動判斷
            use_file_context: 'auto'     // ✅ 交給後端自動決定要不要用檔案內容
          }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const result = await res.json();

        if (!currentConversationId && result?.conversation_id) {
          setCurrentConversationId(result.conversation_id);
        }

        const aiMsg = {
          id: Date.now() + 1,
          content: result?.response || '抱歉，我現在無法回應，請稍後再試。',
          role: 'assistant',
          timestamp: new Date().toISOString()
        };

        // 用回覆替換「思考中…」
        setMessages(prev =>
          prev.map(m => (m.id === thinkingId ? aiMsg : m))
        );
      } else {
        // 只有檔案
        await fetchMessages(convId);
      }

      fetchConversations();
    } catch (err) {
      console.error('發送訊息錯誤:', err);
      setMessages(prev => prev.map(m =>
        m.isThinking
          ? { ...m, content: '連接錯誤，請檢查服務是否正常。', isThinking: false }
          : m
      ));
    } finally {
      setIsLoading(false);
    }
  };

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
    } catch (err) {
      console.error('建立新對話失敗:', err);
    }
  };

  const deleteConversation = async (convId) => {
    if (!Array.isArray(conversations) || conversations.length <= 1) return;
    try {
      const res = await fetch(`${API_URL}/api/conversations/${convId}`, {
        method: 'DELETE',
      });
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

  const startEditingTitle = (convId, currentTitle) => {
    setEditingConversationId(convId);
    setEditTitle(currentTitle);
  };

  const cancelEditingTitle = () => {
    setEditingConversationId(null);
    setEditTitle('');
  };

  const saveEditedTitle = async (convId) => {
    if (!editTitle.trim()) {
      cancelEditingTitle();
      return;
    }
    try {
      const response = await fetch(`${API_URL}/api/conversations/${convId}/title`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: editTitle.trim() }),
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      setConversations(prev =>
        prev.map(conv =>
          conv.id === convId
            ? { ...conv, title: editTitle.trim(), updated_at: new Date().toISOString() }
            : conv
        )
      );
      setEditingConversationId(null);
      setEditTitle('');
    } catch (error) {
      console.error('更新對話標題失敗:', error);
    }
  };

  const formatTimestamp = (ts) => {
    if (!ts) return '';
    try {
      return new Date(ts).toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  const formatFileSize = (bytes) => {
    if (!bytes || bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const isFileMessage = (msg) => typeof msg?.content === 'string' && msg.content.startsWith('📎');

  return (
    <div className="flex h-screen bg-gray-900 text-white">
      {/* 側邊欄 */}
      <div className={`${sidebarOpen ? 'w-64' : 'w-0'} transition-all duration-300 bg-gray-800 flex flex-col overflow-hidden`}>
        <div className="p-4 border-b border-gray-700">
          <button
            onClick={createNewConversation}
            className="w-full flex items-center gap-2 px-4 py-3 bg-gray-700 hover:bg-gray-600 rounded-lg"
          >
            <Plus size={16} />
            新對話
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-2">
          {(Array.isArray(conversations) ? conversations : []).map(conv => (
            <div
              key={conv.id}
              onClick={() => editingConversationId !== conv.id && setCurrentConversationId(conv.id)}
              className={`group flex items-center gap-2 p-3 rounded-lg cursor-pointer transition-colors ${
                currentConversationId === conv.id ? 'bg-gray-700' : 'hover:bg-gray-700/50'
              }`}
            >
              <MessageSquare size={16} />
              <div className="flex-1 min-w-0">
                {editingConversationId === conv.id ? (
                  <input
                    ref={editInputRef}
                    value={editTitle}
                    onChange={e => setEditTitle(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') saveEditedTitle(conv.id);
                      else if (e.key === 'Escape') cancelEditingTitle();
                    }}
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
                  <button
                    onClick={e => { e.stopPropagation(); saveEditedTitle(conv.id); }}
                    className="p-1 text-green-400 hover:bg-gray-600 rounded"
                  >
                    <Check size={12} />
                  </button>
                  <button
                    onClick={e => { e.stopPropagation(); cancelEditingTitle(); }}
                    className="p-1 text-red-400 hover:bg-gray-600 rounded"
                  >
                    <X size={12} />
                  </button>
                </div>
              ) : (
                <div className="opacity-0 group-hover:opacity-100 flex gap-1">
                  <button
                    onClick={e => { e.stopPropagation(); startEditingTitle(conv.id, conv.title); }}
                    className="p-1 hover:bg-gray-600 rounded"
                  >
                    <Edit3 size={12} />
                  </button>
                  <button
                    onClick={e => { e.stopPropagation(); deleteConversation(conv.id); }}
                    className="p-1 text-red-400 hover:bg-gray-600 rounded"
                  >
                    <Trash2 size={12} />
                  </button>
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
          <button onClick={() => setSidebarOpen(o => !o)} className="p-2 hover:bg-gray-700 rounded">
            <Menu size={20} />
          </button>
          <div className="text-lg font-semibold">AI 對話系統</div>

          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileUpload}
            className="hidden"
            accept=".doc,.docx"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className="p-2 hover:bg-gray-700 rounded flex-shrink-0"
            title="上傳檔案"
          >
            <Upload size={18} />
          </button>
        </div>

        {/* 不顯示 uploadError 區塊（保留功能即可） */}

        {/* 準備上傳的檔案列表 */}
        {uploadedFiles.length > 0 && (
          <div className="bg-blue-900/50 p-3 border-b border-gray-700">
            <div className="text-sm text-blue-200 mb-2">準備上傳的檔案：</div>
            {uploadedFiles.map(fileInfo => (
              <div key={fileInfo.id} className="flex items-center gap-2 bg-blue-800/50 p-2 rounded mb-1">
                <FileIcon size={16} />
                <span className="flex-1 text-sm">{fileInfo.name}</span>
                <span className="text-xs text-gray-400">{formatFileSize(fileInfo.size)}</span>
                <button
                  onClick={() => removeUploadedFile(fileInfo.id)}
                  className="text-red-400 hover:text-red-300"
                >
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* 訊息列表 */}
        <div className="flex-1 overflow-y-auto p-4">
          <div className="space-y-4">
            {messages.map(msg => (
              <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`
                  max-w-3xl p-3 rounded-lg
                  ${msg.role === 'user' ? 'bg-blue-600 text-white' : 'bg-gray-700 text-white'}
                  text-left
                `}>
                  {isFileMessage(msg) ? (
                    <div className="flex items-center gap-2">
                      <FileIcon size={16} />
                      <span className="underline">{msg.content.replace('📎 上傳檔案：', '')}</span>
                    </div>
                  ) : (
                    <div className="whitespace-pre-wrap text-sm">{msg.content}</div>
                  )}
                  <div className="text-xs text-gray-300 mt-1 text-right">
                    {formatTimestamp(msg.timestamp)}
                  </div>
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* 輸入列 */}
        <div className="flex items-end gap-2 px-4 py-3 border-t border-gray-700 bg-gray-800">
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading || isLoading}
            className="p-2 hover:bg-gray-700 rounded flex-shrink-0"
            title="上傳檔案"
          >
            <Upload size={18} />
          </button>

          <div className="flex-1 flex flex-col">
            <textarea
              rows={1}
              value={inputMessage}
              onChange={e => setInputMessage(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  sendMessage();
                }
              }}
              placeholder="輸入訊息，按 Enter 發送"
              className="flex-1 resize-none bg-gray-700 text-white px-3 py-2 rounded-lg focus:outline-none min-h-[40px]"
              style={{ maxHeight: '120px', height: 'auto' }}
            />
          </div>

          <button
            onClick={sendMessage}
            disabled={isLoading || (!inputMessage.trim() && uploadedFiles.length === 0)}
            className="p-3 bg-blue-600 hover:bg-blue-500 rounded-full disabled:opacity-50 flex-shrink-0"
            title="發送"
          >
            <Send size={18} />
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatInterface;
