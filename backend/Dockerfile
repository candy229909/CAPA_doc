FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
        PYTHONUNBUFFERED=1
    
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 複製需求檔案
COPY requirements.txt .

# 安裝 Python 依賴
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式
COPY app ./app

# 預設：CPU 向量化（e5-small, 768 維）+ COSINE
# OpenAI 介面：可指向本機相容的 LLM 伺服器
ENV VECTOR_DIM=768 \
        MILVUS_COLLECTION=docs \
        MILVUS_METRIC=COSINE \
        EMBEDDING_MODEL=intfloat/multilingual-e5-small \
        EMB_NORMALIZE=1 \
        E5_PROMPT_PREFIX=1 \
        OPENAI_BASE_URL=http://host.docker.internal:11434/v1 \
        OPENAI_API_KEY=ollama  \
        OPENAI_MODEL=llama3.1:8b \
        LLM_TEMPERATURE=0.3 \
        LLM_TOP_P=0.9 \
        LLM_MAX_TOKENS=1024 \
        LLM_NUM_CTX=4096

# 暴露端口
EXPOSE 8000

# 啟動命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]