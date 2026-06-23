---
title: "Aureon 部署与配置 - 常见问题"
slug: "aureon-faq-deployment"
language: "zh"
source: "aureon-faq"
---

# Aureon 部署与配置 - 常见问题

## 如何部署 Aureon？

Aureon 支持多种部署方式：

### 方式一：Railway 一键部署（推荐）

1. Fork 本仓库到你的 GitHub
2. 在 Railway 创建新项目
3. 连接 GitHub 仓库
4. Railway 自动检测 Dockerfile 并部署
5. 配置环境变量（见下方）
6. 部署完成，访问分配的域名

**部署时间**：约 3-5 分钟（Docker 构建 + 健康检查）

### 方式二：Docker Compose 本地部署

```bash
# 克隆仓库
git clone <repository-url>
cd aureon

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Key

# 启动服务
docker-compose up -d

# 访问 http://localhost:3000
```

### 方式三：手动部署

```bash
# 后端
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 前端
npm install
npm run build
# 将 dist/ 复制到 backend/static/
```

## 需要哪些基础设施依赖？

**必需**：
- **Qdrant**：向量数据库（用于存储和检索文档向量）
  - 本地部署：Docker 运行 `qdrant/qdrant`
  - 云服务：Qdrant Cloud（推荐）

**可选**：
- **Redis**：缓存层（提升性能，语义缓存去重）
- **Elasticsearch**：BM25 后端（默认使用内存 BM25）
- **PostgreSQL**：异步连接池（默认使用 SQLite）

## 如何配置环境变量？

Aureon 使用 `.env` 文件配置，支持嵌套设置（分隔符 `__`）：

```bash
# LLM 配置
LLM__MODEL_NAME=qwen-max
LLM__BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM__API_KEY=your-api-key

# 向量数据库
VECTOR_STORE__QDRANT_URL=https://your-qdrant-url
VECTOR_STORE__QDRANT_API_KEY=your-qdrant-key

# Redis（可选）
REDIS_URL=redis://localhost:6379

# 认证
API_AUTH_KEY=your-api-auth-key
JWT_SECRET=your-jwt-secret

# 环境
AUTH__ENVIRONMENT=production
```

## 如何更新 Aureon？

### Railway 部署
推送代码到 main 分支，Railway 自动触发 CI/CD：
1. GitHub Actions 运行测试（前端 + 后端）
2. CI 通过后自动构建 Docker 镜像
3. 部署到生产环境（约 2-5 分钟）

### Docker 部署
```bash
git pull
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## 如何查看部署状态？

```bash
# Railway 部署
railway status
railway logs --latest

# 健康检查
curl https://your-domain/api/health

# 就绪检查
curl https://your-domain/health/ready
```

## 部署后如何验证？

1. 访问 `https://your-domain/api/health`，应返回 `{"status": "ok"}`
2. 访问 `https://your-domain/health/ready`，检查 Redis/Qdrant 连接
3. 使用演示账号登录测试
4. 上传测试文档，验证搜索功能

## 常见部署问题

### Q：部署后页面空白？
A：检查前端是否正确构建并复制到 `backend/static/`。Railway 部署会自动处理。

### Q：搜索没有结果？
A：确保已上传文档并建立索引。访问 `/api/rag/health` 检查索引状态。

### Q：LLM 响应超时？
A：检查 API Key 是否正确，网络是否可达。查看 `/metrics` 端点的延迟指标。

### Q：WebSocket 连接失败？
A：检查反向代理是否正确配置 WebSocket 支持（nginx 需要 `proxy_pass` 和 `Upgrade` header）。
