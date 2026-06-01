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

# ── Stage 2：后端 + nginx ──
FROM python:3.12-slim

WORKDIR /app

# 系统依赖：nginx + sqlite（Chroma 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    sqlite3 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /dev/stdout /var/log/nginx/access.log \
    && ln -sf /dev/stderr /var/log/nginx/error.log

# Python 依赖（先复制 requirements.txt 加速缓存）
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

# 预下载 BGE-small-zh embedding 模型（~130MB，消除冷启动延迟）
RUN python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')" \
    || HF_ENDPOINT=https://hf-mirror.com python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')"

# 后端代码
COPY backend/ .

# Chroma 向量库持久化目录
RUN mkdir -p /app/data/vectors

# 从前端构建阶段复制静态文件
COPY --from=frontend-builder /app/dist /usr/share/nginx/html

# nginx 配置（含 /api/ 反向代理）
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 启动脚本（JSON 数组 CMD 确保信号正确传递）
ARG CACHE_BUST=2
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN sed -i 's/\r$//' /docker-entrypoint.sh && chmod +x /docker-entrypoint.sh

# 非 root 用户运行 —— Railway 容器已隔离，且非 root 无法绑定 <1024 端口
# RUN groupadd -r aureon && useradd -r -g aureon -d /app -s /sbin/nologin aureon \
#     && chown -R aureon:aureon /app /usr/share/nginx/html /etc/nginx
# USER aureon

EXPOSE ${PORT:-80}

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-80}/api/health || exit 1

# 直接启动 uvicorn（绕过 entrypoint，避免 CRLF 问题）
CMD ["sh", "-c", "sed -i 's/listen 80;/listen ${PORT:-80};/' /etc/nginx/conf.d/default.conf && nginx && exec uvicorn app.main:app --host 127.0.0.1 --port 8000"]