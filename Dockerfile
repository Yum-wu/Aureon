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

# 系统依赖：nginx + sqlite（Chroma 需要）+ gosu（进程降权）
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    sqlite3 \
    gosu \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /dev/stdout /var/log/nginx/access.log \
    && ln -sf /dev/stderr /var/log/nginx/error.log

# Python 依赖
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Force rebuild: 2026-06-09 monkey-patch CrossEncoder
RUN echo "Rebuild triggered at $(date +%s)" && rm -f /app/.env /app/backend/.env && echo "Cleaned .env files"

# 默认跳过本地 BGE 模型（Railway CPU-only 加载 1.3GB large 模型太慢，且索引用 DashScope 1024d）
# 如需本地嵌入，在 Railway 环境变量中设置 SKIP_LOCAL_EMBED=false
ENV SKIP_LOCAL_EMBED=true

# 后端代码
COPY backend/ .

# 强制删除 .env 文件（.dockerignore 可能未正确排除）
RUN rm -f /app/.env /app/backend/.env

# GPU disabled on Railway (no CUDA); rerank via remote API to avoid OOM
# Set COHERE_API_KEY in Railway dashboard to enable API reranking
ENV GPU_ENABLED=false
ENV RERANK_ENABLED=true
ENV RERANK_BACKEND=api
ENV RERANK_PROVIDER=dashscope

# Chroma 向量库持久化目录
RUN mkdir -p /app/data/vectors /app/offloads

# 创建非 root 用户
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser \
    && chown -R appuser:appuser /app /usr/share/nginx /var/log/nginx /run

# 从前端构建阶段复制静态文件
COPY --from=frontend-builder /app/dist /usr/share/nginx/html

# nginx 配置（含 /api/ 反向代理）
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 启动脚本（JSON 数组 CMD 确保信号正确传递）
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 80

CMD ["/docker-entrypoint.sh"]