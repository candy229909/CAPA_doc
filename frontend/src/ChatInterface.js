import React, { useState, useRef, useEffect } from 'react';
import {
  Send, Plus, Menu, MessageSquare, Trash2, Edit3,
  Check, X, AlertCircle,
  File
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

  const messagesEndRef = useRef(null);
  const editInputRef = useRef(null);
  const fileInputRef = useRef(null);

  const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

  // 載入對話列表
  useEffect(() => {
    fetchConversations();
  }, []);

  // 載入當前對話訊息
  useEffect(() => {
    if (currentConversationId) {
      fetchMessages(currentConversationId);
    } else {
      setMessages([]);
    }
  }, [currentConversationId]);

  // 自動滾動到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 編輯標題時聚焦
  useEffect(() => {
    if (editingConversationId && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingConversationId]);

  // Fetch：對話列表
  const fetchConversations = async () => {
    try {
      const res = await fetch(`${API_URL}/api/conversations`);
      const data = await res.json();
      setConversations(data);
      if (!currentConversationId && data.length) {
        setCurrentConversationId(data[0].id);
      }
    } catch (err) {
      console.error('載入對話列表失敗:', err);
    }
  };

  // Fetch：取得訊息
  const fetchMessages = async (convId) => {
    try {
      const res = await fetch(`${API_URL}/api/conversations/${convId}/messages`);
      const data = await res.json();
      setMessages(data);
    } catch (err) {
      console.error('載入訊息失敗:', err);
      setMessages([]);
    }
  };

  // 傳送文字訊息
  const sendMessage = async () => {
    if (!inputMessage.trim() || isLoading) return;

    const userMsg = {
      id: Date.now(),
      content: inputMessage,
      role: 'user',
      timestamp: new Date().toISOString()
    };
    setMessages(prev => [...prev, userMsg]);
    setInputMessage('');
    setIsLoading(true);

    try {
      const res = await fetch(`${API_URL}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMsg.content,
          conversation_id: currentConversationId,
          model: 'gemma2:2b'
        }),
      });
      if (!res.ok) throw new Error(res.status);

      const { response } = await res.json();
      const aiMsg = {
        id: Date.now() + 1,
        content: response || '抱歉，我現在無法回應。請稍後再試。',
        role: 'assistant',
        timestamp: new Date().toISOString()
      };
      setMessages(prev => [...prev, aiMsg]);
      fetchConversations();
    } catch (err) {
      console.error('發送訊息錯誤:', err);
      const errorMsg = {
        id: Date.now() + 1,
        content: '連接錯誤，請檢查服務是否正常。',
        role: 'assistant',
        timestamp: new Date().toISOString()
      };
      setMessages(prev => [...prev, errorMsg]);
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
    } catch (err) {
      console.error('建立新對話失敗:', err);
    }
  };

  // 刪除對話
  const deleteConversation = async (convId) => {
    if (conversations.length <= 1) return;
    try {
      const res = await fetch(`${API_URL}/api/conversations/${convId}`, {
        method: 'DELETE',
      });
      if (!res.ok) throw new Error(res.status);

      setConversations(prev => prev.filter(c => c.id !== convId));
      if (currentConversationId === convId) {
        const remain = conversations.filter(c => c.id !== convId);
        setCurrentConversationId(remain[0]?.id || null);
      }
    } catch (err) {
      console.error('刪除對話失敗:', err);
    }
  };

  // 檔案上傳：整合到訊息中
  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // 檔案類型 & 大小檢查
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
    setIsUploading(true);

    // 先顯示上傳中的檔案訊息
    const placeholder = {
      id: Date.now(),
      content: `📎 上傳檔案：${file.name}`,
      role: 'user',
      timestamp: new Date().toISOString()
    };
    setMessages(prev => [...prev, placeholder]);

    try {
      // 若無對話，先建立
      let convId = currentConversationId;
      if (!convId) {
        const res = await fetch(`${API_URL}/api/conversations`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: `文件分析: ${file.name}` }),
        });
        if (!res.ok) throw new Error('建立對話失敗');
        const newConv = await res.json();
        setConversations(prev => [newConv, ...prev]);
        setCurrentConversationId(newConv.id);
        convId = newConv.id;
      }

      // 上傳 FormData
      const form = new FormData();
      form.append('file', file);
      form.append('conversation_id', convId);

      const upRes = await fetch(`${API_URL}/api/upload-document`, {
        method: 'POST',
        body: form
      });
      if (!upRes.ok) {
        const err = await upRes.json();
        throw new Error(err.detail || '檔案上傳失敗');
      }
      const result = await upRes.json();
      if (!result.success) {
        throw new Error(result.message || '檔案處理錯誤');
      }

      // 完成後重新載入
      await fetchMessages(convId);
      fetchConversations();
      fileInputRef.current.value = '';
    } catch (err) {
      console.error('檔案上傳錯誤:', err);
      setUploadError(err.message || '上傳失敗，請重試');
    } finally {
      setIsUploading(false);
    }
  };

  // 開始編輯對話標題
  const startEditingTitle = (convId, currentTitle) => {
    setEditingConversationId(convId);
    setEditTitle(currentTitle);
  };

  // 取消編輯
  const cancelEditingTitle = () => {
    setEditingConversationId(null);
    setEditTitle('');
  };

  // 保存編輯後的標題
  const saveEditedTitle = async (convId) => {
    if (!editTitle.trim()) {
      cancelEditingTitle();
      return;
    }

    try {
      const response = await fetch(`${API_URL}/api/conversations/${convId}/title`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title: editTitle.trim()
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      // 更新本地狀態
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
      // 可以在這裡添加錯誤提示
    }
  };

  // 處理編輯輸入框的鍵盤事件
  const handleEditKeyPress = (e, convId) => {
    if (e.key === 'Enter') {
      saveEditedTitle(convId);
    } else if (e.key === 'Escape') {
      cancelEditingTitle();
    }
  };

  // 格式化時間
  const formatTimestamp = (ts) =>
    new Date(ts).toLocaleTimeString('zh-TW', {
      hour: '2-digit', minute: '2-digit'
    });

  // 判斷檔案訊息
  const isFileMessage = (msg) => msg.content.startsWith('📎');

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
          {conversations.map(conv => (
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
                    <div className="text-xs text-gray-400">
                      {formatTimestamp(conv.updated_at)}
                    </div>
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
          {/* 隱藏檔案輸入，只接受 doc/docx */}
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileUpload}
            className="hidden"
            accept=".doc,.docx"
          />
        </div>

        {/* 上傳錯誤提示 */}
        {uploadError && (
          <div className="bg-red-700 text-sm px-4 py-2 flex items-center gap-2">
            <AlertCircle size={16} />
            {uploadError}
          </div>
        )}

        {/* 訊息列表 */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map(msg => (
            <div
              key={msg.id}
              className={`
                max-w-3xl p-3 rounded-lg 
                ${msg.role === 'user' ? 'bg-blue-600 self-end ml-auto' : 'bg-gray-700 self-start mr-auto'}
              `}
            >
              {isFileMessage(msg) ? (
                <div className="flex items-center gap-2">
                  <File size={16} />
                  <span className="underline">{msg.content.replace('📎 上傳檔案：', '')}</span>
                </div>
              ) : (
                <div className="whitespace-pre-wrap text-sm">{msg.content}</div>
              )}
              <div className="text-xs text-gray-300 mt-1 text-right">
                {formatTimestamp(msg.timestamp)}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* 輸入列 */}
        <div className="flex items-center gap-2 px-4 py-3 border-t border-gray-700 bg-gray-800">
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className="p-2 hover:bg-gray-700 rounded"
          >
            <Plus size={18} />
          </button>
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
            className="flex-1 resize-none bg-gray-700 text-white px-3 py-2 rounded-lg focus:outline-none"
          />
          <button
            onClick={sendMessage}
            disabled={isLoading}
            className="p-3 bg-blue-600 hover:bg-blue-500 rounded-full disabled:opacity-50"
          >
            <Send size={18} />
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatInterface;