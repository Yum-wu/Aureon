# ── Aureon Backend: FastAPI + Gunicorn (Distroless 多阶段构建) ──
# Phase 3 可移植性改造（PO3 + PO4）
# 构建：docker build -f backend/Dockerfile .
#
# 特性：
#   - 运行时基于 gcr.io/distroless/python3-debian12:nonroot（无 shell、无包管理器）
#   - 非 root 运行（distroless nonroot UID=65532）
#   - gunicorn + uvicorn.workers.UvicornWorker（生产级进程管理）
#   - Python urllib 健康检查（distroless 无 curl/wget）
#   - 跳过本地 BGE 模型（使用 API embedding：DashScope）

# ── Stage 1：构建阶段（python:3.12-slim 作为构建器）──
FROM python:3.12-slim AS builder

# 安装编译依赖（部分 Python 包如 cryptography/lxml 需要 build-essential）
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 创建虚拟环境
# --copies 确保 Python 可执行文件是真实副本（非符号链接），便于复制到 distroless
RUN python -m venv --copies /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 升级 pip
RUN pip install --no-cache-dir --upgrade pip

# 安装 Python 依赖（含 gunicorn>=22.0,<24.0，见 requirements.txt）
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# 创建数据目录（distroless 无 shell，无法在运行时用 RUN mkdir，需在 builder 阶段创建）
# .gitkeep 占位确保空目录能被 COPY 复制
RUN mkdir -p /app/data/vectors /app/offloads \
    && touch /app/data/vectors/.gitkeep /app/offloads/.gitkeep

# ── Stage 2：运行时阶段（distroless，无 shell）──
# 使用 python3-debian12:nonroot（自带 Debian 12 基础库 + nonroot 用户）
# 注意：distroless python3-debian12 自带 Python 3.11，但我们用 venv 中的 Python 3.12 运行
FROM gcr.io/distroless/python3-debian12:nonroot

# 从构建阶段复制虚拟环境（Python 3.12 副本 + site-packages）
COPY --from=builder /opt/venv /opt/venv

# 复制 Python 3.12 标准库（venv 不包含标准库，需单独复制）
# venv 的 pyvenv.cfg 中 home=/usr/local/bin，Python 会从 /usr/local/lib/python3.12 查找标准库
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12

# 复制 libpython3.12.so.1.0（venv 中的 Python 可执行文件动态链接此库）
COPY --from=builder /usr/local/lib/libpython3.12.so.1.0 /usr/local/lib/

# ── 环境变量配置 ──
ENV PATH="/opt/venv/bin:$PATH"
# libpython3.12.so 搜索路径
ENV LD_LIBRARY_PATH="/usr/local/lib"
# Python 模块搜索路径（确保 import app.main 能找到 /app/app/main.py）
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
# 默认跳过本地 BGE 模型（distroless 无 torch/sentence-transformers，使用 API embedding）
ENV SKIP_LOCAL_EMBED=true
# GPU 在 Railway 不可用，rerank 走远程 API（DashScope）
ENV GPU_ENABLED=false
ENV RERANK_ENABLED=true
ENV RERANK_BACKEND=api
ENV RERANK_PROVIDER=dashscope
# 固定端口 8000（distroless 无 shell，不支持 ${PORT} 变量替换）
# Railway 部署时需在仪表板设置 PORT=8000
ENV PORT=8000

WORKDIR /app

# 复制应用代码（仅 app 目录，不含 tests/requirements）
COPY --chown=nonroot:nonroot backend/app /app/app

# 复制数据目录（含 .gitkeep 占位，确保目录存在且 nonroot 可写）
COPY --from=builder --chown=nonroot:nonroot /app/data /app/data
COPY --from=builder --chown=nonroot:nonroot /app/offloads /app/offloads

# 非 root 运行（distroless :nonroot 默认 UID=65532，显式声明以明确意图）
USER nonroot

EXPOSE 8000

# 健康检查（distroless 无 curl/wget，使用 Python urllib 检查 /api/health）
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD ["/opt/venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]

# ── 启动命令：gunicorn + uvicorn workers ──
# 不使用 --preload：FastAPI lifespan 事件（LangFuse 初始化、Redis 连接池等）
# 在 --preload 模式下会在 master 进程执行一次，worker fork 后可能导致连接池状态不一致
ENTRYPOINT ["/opt/venv/bin/python"]
CMD ["-m", "gunicorn", "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "2", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "100", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
