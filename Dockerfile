# ── Stage 1：构建前端 ──
FROM node:22-alpine AS frontend-builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

ARG VITE_API_URL
ARG VITE_CREW_API_URL
ENV VITE_API_URL=/api/chat/stream
ENV VITE_CREW_API_URL=/api/crew
RUN npm run build

# ── Stage 2：后端 + nginx（精简版，无 PyTorch）──
FROM python:3.12-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx sqlite3 curl \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /dev/stdout /var/log/nginx/access.log \
    && ln -sf /dev/stderr /var/log/nginx/error.log \
    && rm -f /etc/nginx/sites-enabled/default

# Python 依赖 — 去掉 sentence-transformers（PyTorch ~3GB）
COPY backend/requirements.txt .
RUN grep -v "sentence-transformers" requirements.txt > requirements-lite.txt \
    && pip install -r requirements-lite.txt

# 后端代码
COPY backend/ .

# Chroma 向量库持久化目录
RUN mkdir -p /app/data/vectors

# 前端静态文件
COPY --from=frontend-builder /app/dist /usr/share/nginx/html

# nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 启动脚本
ARG CACHE_BUST=3
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN sed -i 's/\r$//' /docker-entrypoint.sh && chmod +x /docker-entrypoint.sh

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-80}/api/health || exit 1

CMD ["sh", "-c", "sed -i 's/listen 80;/listen ${PORT:-80};/' /etc/nginx/conf.d/default.conf && nginx && exec uvicorn app.main:app --host 127.0.0.1 --port 8000"]
