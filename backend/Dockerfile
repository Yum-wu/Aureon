# ── Aureon Backend: FastAPI + Qdrant ──
# Stage: Python 3.12 slim (Railway-optimized: no torch in final image)
FROM python:3.12-slim AS backend

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖（利用缓存层）
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 临时安装 torch + sentence-transformers 用于下载 BGE 模型
# 下载完成后立即卸载，最终镜像不含这些包（节省 ~2GB 内存）
COPY backend/requirements-build.txt .
RUN pip install --no-cache-dir -r requirements-build.txt \
    && python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')" \
        || HF_ENDPOINT=https://hf-mirror.com python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')" \
    && pip uninstall -y torch accelerate 2>/dev/null; \
       rm -rf /root/.cache/huggingface /root/.cache/torch

# 复制后端代码
COPY backend/ .

# 向量数据目录
RUN mkdir -p /app/data/vectors

EXPOSE ${PORT:-8000}

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request, os; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", \"8000\")}/api/health')" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
