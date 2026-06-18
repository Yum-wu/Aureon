# ── Aureon Backend: FastAPI + Qdrant ──
# Supports both single-worker (uvicorn) and multi-worker (gunicorn) modes.
# Build with: docker build -f backend/Dockerfile .
# Multi-worker: docker build --build-arg SERVER_MODE=gunicorn -f backend/Dockerfile .

FROM python:3.12-slim AS backend

WORKDIR /app

# System dependencies (pinned versions for reproducibility)
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3=3.45.1-1 \
    curl=8.5.0-2 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (UID/GID fixed for volume permission management)
RUN groupadd -r -g 1001 appuser \
    && useradd -r -u 1001 -g appuser -d /app -s /sbin/nologin appuser

# Python dependencies (leverage Docker layer caching)
COPY --chown=appuser:appuser backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Optional: Gunicorn for multi-worker mode
ARG SERVER_MODE=uvicorn
RUN if [ "$SERVER_MODE" = "gunicorn" ]; then pip install --no-cache-dir gunicorn; fi

# Pre-download BGE embedding model (then remove torch to save ~2GB)
COPY --chown=appuser:appuser backend/requirements-build.txt .
RUN pip install --no-cache-dir -r requirements-build.txt \
    && python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')" \
        || HF_ENDPOINT=https://hf-mirror.com python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')" \
    && pip uninstall -y torch accelerate 2>/dev/null; \
       rm -rf /root/.cache/huggingface /root/.cache/torch

# Copy backend code
COPY --chown=appuser:appuser backend/ .

# Data directory
RUN mkdir -p /app/data/vectors && chown -R appuser:appuser /app/data

# Switch to non-root user
USER 1001:1001

EXPOSE ${PORT:-8000}

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:${PORT:-8000}/api/health || exit 1

# Server mode: uvicorn (default) or gunicorn
ENV SERVER_MODE=${SERVER_MODE}
CMD sh -c 'if [ "$SERVER_MODE" = "gunicorn" ]; then \
    exec gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker \
      --bind 0.0.0.0:${PORT:-8000} --timeout 120 --graceful-timeout 30 \
      --max-requests 1000 --max-requests-jitter 50; \
  else \
    exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}; \
  fi'
