import React from 'react';
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import ChatInterface from './ChatInterface';
import TemplateFilterApp from "./pages/TemplateFilterApp";
import './App.css';

function App() {
  return (
    <BrowserRouter>
      <div className="App">
        <nav style={{padding:"8px 12px", borderBottom:"1px solid #eee", display:"flex", gap:"12px"}}>
          <Link to="/">聊天</Link>
          <Link to="/template-filler">模組填空</Link>
        </nav>
        <Routes>
          <Route path="/" element={<ChatInterface />} />
          <Route path="/template-filler" element={<TemplateFilterApp />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
