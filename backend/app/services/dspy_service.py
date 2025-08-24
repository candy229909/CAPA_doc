# -*- coding: utf-8 -*-
"""
一個基於 FastAPI 的高效能 AI 對話 Web API 框架。
本框架整合了 spaCy、dspy、向量/圖形資料庫和大型語言模型（LLM）。
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
import json
import logging
import spacy
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import dspy
from dspy.retrieve import MilvusRM # 假設 Milvus 是 dspy 的後端
from neo4j import GraphDatabase # 假設使用 Neo4j 的 Python 驅動程式

# 設定日誌記錄
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 定義 Pydantic 模型以實現自動驗證和文件生成 ---
class UserMessage(BaseModel):
    """使用者輸入的訊息模型。"""
    session_id: str = Field(..., description="唯一的對話 ID")
    text: str = Field(..., description="使用者輸入的文字訊息")

class AIResponse(BaseModel):
    """AI 回應的模型。"""
    session_id: str
    response: str
    topic: Optional[str] = None
    references: List[str]

class ConversationSummary(BaseModel):
    """對話摘要的模型。"""
    session_id: str
    topic: str
    summary: str
    last_updated: str

class ExportStateResponse(BaseModel):
    """匯出狀態回應模型。"""
    status: str
    file_path: str

class LoadStateRequest(BaseModel):
    """載入狀態請求模型。"""
    file_path: str

class StatusResponse(BaseModel):
    """狀態檢查回應模型。"""
    status: str
    message: str

# --- 核心 AI 對話類別 ---
class AIConversationAPI:
    """
    主要處理所有 AI 對話邏輯的類別。
    整合 spaCy、dspy、資料庫查詢和 LLM 呼叫。
    """
    def __init__(self):
        logging.info("初始化 AI 對話引擎...")
        # 1. 初始化 spaCy 模型
        try:
            self.nlp = spacy.load("zh_core_web_sm") # 載入中文小型模型
        except OSError:
            logging.error("找不到 spaCy 模型 'zh_core_web_sm'。請執行 'python -m spacy download zh_core_web_sm' 安裝。")
            raise

        # 2. 初始化資料庫和 dspy
        # 這是 Milvus 和 Neo4j 的模擬連接。在實際應用中，需要提供正確的連接字串和憑證。
        self.milvus_db_client = self._connect_milvus()
        self.neo4j_db_client = self._connect_neo4j()

        # dspy 模組設定
        # 這裡用 dspy.MilvusRM 作為參考。您需要根據實際情況配置。
        # dspy.configure(rm=MilvusRM(self.milvus_db_client), lm="gemini-2.5-flash-preview-05-20")
        # 為了簡化範例，我們只展示如何使用 dspy.Retrieve 模組。
        self.retriever = dspy.Retrieve(k=3)
        
        # 3. 初始 LLM 模組
        # 依據我的內部指示，這裡會使用 Gemini API 作為 LLM 呼叫的示例。
        # 您可以將此處替換為 Qwen 2.5:7b 的實際呼叫邏輯。
        self.llm = dspy.Google(model='gemini-2.5-flash-preview-05-20')

        # 4. 內部狀態儲存（模擬）
        self.conversation_history: Dict[str, List[Dict[str, str]]] = {}
        self.conversation_topics: Dict[str, str] = {}
        logging.info("AI 對話引擎初始化完成。")

    def _connect_milvus(self) -> Any:
        """模擬連接 Milvus 向量資料庫。"""
        logging.info("嘗試連接 Milvus 資料庫...")
        # 實際程式碼應在此處使用 pymilvus 連接
        # from pymilvus import connections, utility
        # connections.connect("default", host="localhost", port="19530")
        # utility.has_collection("my_collection")
        return {"status": "connected", "type": "Milvus"}

    def _connect_neo4j(self) -> Any:
        """模擬連接 Neo4j 圖形資料庫。"""
        logging.info("嘗試連接 Neo4j 資料庫...")
        # 實際程式碼應在此處使用 neo4j 驅動程式連接
        # uri = "bolt://localhost:7687"
        # user = "neo4j"
        # password = "your_password"
        # return GraphDatabase.driver(uri, auth=(user, password))
        return {"status": "connected", "type": "Neo4j"}

    async def process_message(self, session_id: str, text: str) -> AIResponse:
        """處理使用者訊息，進行語意分析、資料庫查詢並產生回應。"""
        # 1. 使用 spaCy 進行語意分析
        doc = self.nlp(text)
        keywords = [ent.text for ent in doc.ents] + [token.text for token in doc if not token.is_stop and not token.is_punct]
        logging.info(f"從訊息 '{text}' 中提取到的關鍵字: {keywords}")

        # 2. 透過 dspy 查詢資料庫
        # 在實際應用中，dspy 查詢會自動使用您配置的 MilvusRM 和圖形查詢邏輯。
        # 這裡我們只展示概念性程式碼。
        try:
            # 這裡我們用一個簡單的 dspy.Retrieve 範例來模擬查詢向量資料庫
            # 在 dspy.Retrieve 的範例中，通常需要一個 LLM 來輔助生成查詢。
            # 為了簡化，我們直接使用關鍵字。
            search_results = self._query_database_with_dspy(keywords)
            logging.info(f"從 dspy 查詢資料庫的結果: {search_results}")
        except Exception as e:
            logging.error(f"Dspy 資料庫查詢失敗: {e}")
            search_results = "資料庫查詢失敗，將只依據歷史資料回答。"

        # 3. 呼叫 LLM 產生回應
        # 整合資料庫查詢結果與對話歷史，生成完整的提示（prompt）。
        prompt = self._build_llm_prompt(text, search_results)
        
        # 這裡我們使用一個非同步的 LLM 呼叫。
        llm_response = await self._call_llm(prompt)
        logging.info("LLM 回應已產生。")

        # 4. 儲存對話歷史並更新主題
        if session_id not in self.conversation_history:
            self.conversation_history[session_id] = []
        self.conversation_history[session_id].append({"role": "user", "text": text})
        self.conversation_history[session_id].append({"role": "assistant", "text": llm_response})

        # 5. 回顧並更新主題
        current_topic = await self._classify_topic(self.conversation_history[session_id])
        self.conversation_topics[session_id] = current_topic
        logging.info(f"對話 ID: {session_id}，目前主題: {current_topic}")

        # 6. 產生報告（如果需要）
        # 這裡可以根據特定條件生成報告，例如當主題為“報告生成”時。
        # report_content = await self.generate_report(session_id)

        # 7. 回傳結果
        return AIResponse(
            session_id=session_id,
            response=llm_response,
            topic=current_topic,
            references=search_results
        )

    def _query_database_with_dspy(self, keywords: List[str]) -> List[str]:
        """
        使用 dspy 查詢資料庫。
        此處為簡化範例，僅展示概念。
        在實際應用中，dspy 的 Retriever 會自動處理向量搜尋和圖形查詢。
        """
        # 模擬從資料庫中檢索相關資訊
        # 在真實應用中，dspy.Retrieve 會根據輸入自動查詢向量資料庫
        # 這裡我們將模擬返回一些結果
        mock_results = [
            f" Milvus 查詢結果：與 '{keyword}' 相關的向量搜尋結果。",
            f" Neo4j 查詢結果：與 '{keyword}' 相關的圖形資料關係圖譜。",
            " 額外相關參考資料。",
        ]
        return mock_results

    def _build_llm_prompt(self, user_text: str, search_results: List[str]) -> str:
        """根據使用者訊息和資料庫結果建立 LLM 提示。"""
        # 組合提示，引導 LLM 根據檢索到的資訊進行回答
        return (
            f"使用者詢問: {user_text}\n"
            f"以下是資料庫查詢結果，請將其整合進你的回答中: \n"
            f"{' '.join(search_results)}\n"
            "請根據上述資訊，給出一個精準、流暢且具備條理的回應。"
        )

    async def _call_llm(self, prompt: str) -> str:
        """
        非同步呼叫 LLM。
        這裡是使用 Gemini API 的示例。
        您可以將此處的程式碼替換為對 Qwen 2.5:7b 的實際 API 呼叫。
        """
        # 為了簡化，我們將使用一個模擬的 LLM 呼叫。
        # 在真實環境中，您需要使用 `asyncio` 和 `aiohttp` 或 `requests` 庫進行非同步 API 請求。
        # 由於我目前無法直接調用外部 LLM，此處為模擬回應。
        # 實際的 Gemini API 呼叫會像這樣：
        # response = await self.llm(prompt)
        # return response.completions[0].text
        # 
        # 這裡將直接返回一個模擬的回應。
        # 請替換為您實際的 LLM 呼叫。
        await asyncio.sleep(0.5)  # 模擬網路延遲
        return f"好的，我根據您的詢問並整合了從資料庫中檢索到的資訊，給出了回應。這是一個基於您提示和資料庫檢索結果的詳細說明。"


    async def _classify_topic(self, conversation: List[Dict[str, str]]) -> str:
        """
        使用 LLM 對對話進行主題分類。
        此處為簡化範例。
        """
        # 組合提示以分類主題
        prompt = (
            "請根據以下對話，為其總結一個簡短的主題（例如：技術討論、專案規劃、個人問題等）。"
            "只給出主題名稱，不要有額外的說明。\n"
            "對話內容: " + " ".join([msg['text'] for msg in conversation])
        )
        # 這裡同樣是模擬的 LLM 呼叫
        # response = await self.llm(prompt)
        # return response.text
        return "歷史對話回顧與分類"

    def export_state(self, file_path: str) -> str:
        """將類別的狀態匯出到 JSON 檔案。"""
        state = {
            "conversation_history": self.conversation_history,
            "conversation_topics": self.conversation_topics,
            "last_updated": datetime.now().isoformat()
        }
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=4)
        logging.info(f"類別狀態已成功匯出至 {file_path}")
        return file_path

    def load_state(self, file_path: str) -> bool:
        """從 JSON 檔案載入類別的狀態。"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                state = json.load(f)
            self.conversation_history = state.get("conversation_history", {})
            self.conversation_topics = state.get("conversation_topics", {})
            logging.info(f"類別狀態已成功從 {file_path} 載入。")
            return True
        except FileNotFoundError:
            logging.error(f"檔案 '{file_path}' 不存在。無法載入狀態。")
            return False
        except json.JSONDecodeError:
            logging.error(f"檔案 '{file_path}' 格式錯誤。無法載入狀態。")
            return False

# --- FastAPI 應用程式設定與端點 ---
# 實例化核心類別
ai_api = AIConversationAPI()

# 實例化 FastAPI 應用程式
app = FastAPI(
    title="高效能 AI 對話服務",
    description="一個結合 spaCy、dspy 和向量/圖形資料庫的強大 AI 服務，具備自動文件生成。",
    version="1.0.0",
)

@app.get("/", response_model=StatusResponse, summary="服務狀態檢查")
async def get_status():
    """檢查 API 服務是否正常運行。"""
    return StatusResponse(status="ok", message="AI 對話服務正在運行中！")

@app.post("/chat", response_model=AIResponse, summary="處理使用者對話")
async def chat_with_user(message: UserMessage):
    """
    處理使用者輸入的對話訊息。
    - 接受訊息和對話 ID。
    - 使用 spaCy 處理訊息。
    - 透過 dspy 查詢資料庫。
    - 呼叫 LLM 產生回應。
    - 儲存對話歷史。
    """
    try:
        response = await ai_api.process_message(message.session_id, message.text)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/history/{session_id}", response_model=List[Dict[str, str]], summary="取得對話歷史")
async def get_history(session_id: str):
    """
    根據對話 ID 取得完整的對話歷史記錄。
    """
    if session_id not in ai_api.conversation_history:
        raise HTTPException(status_code=404, detail="找不到該對話 ID。")
    return ai_api.conversation_history[session_id]

@app.post("/export", response_model=ExportStateResponse, summary="匯出服務狀態")
async def export_state(file_path: str = "conversation_state.json"):
    """
    將所有對話歷史和主題分類匯出到 JSON 檔案。
    """
    path = ai_api.export_state(file_path)
    return ExportStateResponse(status="success", file_path=path)

@app.post("/load", response_model=StatusResponse, summary="從檔案載入服務狀態")
async def load_state(request: LoadStateRequest):
    """
    從指定的 JSON 檔案載入服務狀態，覆蓋當前狀態。
    """
    success = ai_api.load_state(request.file_path)
    if not success:
        raise HTTPException(status_code=400, detail=f"無法載入檔案 '{request.file_path}'。")
    return StatusResponse(status="success", message="狀態已成功載入。")

# --- 啟動服務範例 ---
if __name__ == "__main__":
    # 在命令列中執行: uvicorn your_file_name:app --reload
    # 這行程式碼將被 uvicorn 替換
    print("使用 'uvicorn your_file_name:app --reload' 來啟動伺服器。")
    print("請將 'your_file_name' 替換為您的檔案名稱。")
    # 例如: uvicorn main:app --reload
    
    # 這裡的程式碼僅為示例
    import asyncio
    async def run_example():
        # 測試 process_message
        print("\n--- 測試對話處理 ---")
        message = UserMessage(session_id="session_123", text="什麼是向量搜尋？它和圖形資料庫有什麼關係？")
        response = await ai_api.process_message(message.session_id, message.text)
        print("AI 回應:", response.response)
        
        # 測試匯出和載入
        print("\n--- 測試狀態匯出與載入 ---")
        export_response = ai_api.export_state("example_state.json")
        print(f"狀態已匯出至 {export_response}")
        
        ai_api.conversation_history = {} # 清空歷史記錄
        ai_api.load_state("example_state.json")
        print("歷史記錄載入後:", ai_api.conversation_history)

    asyncio.run(run_example())

