# ── Aureon Backend: FastAPI + Chroma ──
# Stage: Python 3.12 slim
FROM python:3.12-slim AS backend

WORKDIR /app

# 系统依赖：Chroma 需要 sqlite 较新版本
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖（利用缓存层）
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 预下载 BGE-small-zh embedding 模型（~130MB，消除冷启动延迟）
RUN python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')" \
    || HF_ENDPOINT=https://hf-mirror.com python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')"

# 复制后端代码
COPY backend/ .

# Chroma 向量库持久化目录
RUN mkdir -p /app/data/vectors

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
