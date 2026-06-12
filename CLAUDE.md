# CLAUDE.md

Aureon 全栈 AI 应用开发指南。

## 项目信息

| 属性 | 值 |
|------|-----|
| 项目名 | Aureon |
| 类型 | 全栈 AI 应用 |
| 前端 | React 19 + Vite + TypeScript + Tailwind CSS |
| 后端 | Python FastAPI + LangChain + LangGraph |
| 端口 | 前端 5173 / 后端 8000 |
| 数据库 | SQLite（记忆）+ Qdrant（向量库）|
| AI API | DeepSeek / 智谱 AI / DashScope (embedding + rerank) |
| 安全 | API Key Auth, Prompt Injection Guard, Fernet Encryption |

## 核心概念

- **RAG**：检索增强生成，基于文档的知识问答
- **Agent**：LangChain Agent，具备 Tool Calling 能力的对话代理
- **Memory**：四层记忆（L0 对话 / L1 原子记忆 / L2 场景总结 / L3 人格）
- **LangGraph**：状态图编排，支持流式输出的 Agent 工作流
- **Semantic Cache**：两层缓存架构（Exact + Semantic），延迟降低 97%
- **Adaptive Re-ranking**：Query-aware 策略选择，精度提升 22%
- **WebSocket Streaming**：双向实时通信，支持 200+ 并发连接

## 构建命令

### 前端
```bash
npm install && npm run dev    # 开发
npm run build                 # 构建
npm test                      # 测试
npm run lint                  # 检查
```

### 后端
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000   # 开发
pytest                                          # 测试
```

### Docker
```bash
docker-compose up --build
docker-compose up -d
docker-compose logs -f
docker-compose down
```

## 测试策略

- 前端：`npm test`，关注组件渲染和 hooks 行为（74 tests）
- 后端：`pytest`，750+ 测试覆盖各模块
- **修改代码后必须跑对应测试**，推送前全量通过
- CI 用 GitHub Actions，部署用 Railway

## API 端点

- `POST /api/chat/enhanced/stream` — Chat + RAG，LangGraph 流式
- `POST /api/chat/stream` — Chat Agent
- `POST /api/rag/query` / `query/stream` — RAG 查询（同步/流式）
- `GET /api/rag/analytics/{usage|latency|tokens|cache}` — 分析
- `POST /api/rag/index` — 重建索引
- `GET /api/rag/analytics/cache` — 缓存分析（Semantic Cache 命中率、延迟）
- `WS /ws/chat/{client_id}` — WebSocket 实时聊天（多轮对话、Tool Calling）
- `GET /api/health` — 健康检查
- `GET /health/ready` — 就绪探针（Redis/Qdrant/索引状态）
- `GET /metrics` — Prometheus 指标
- `POST /api/langgraph/run` — LangGraph 工作流

## 项目结构

```
Aureon/
├── src/components/  hooks/  services/  i18n/  types/
├── backend/app/{agent,tools,memory,rag,features,observability,security,evaluation,cost,reliability,knowledge,ai_platform,integration,langgraph,api,cache,multi_tenant,audit}/
├── backend/tests/   (753 tests)
└── docker-compose.yml
```

## 代码探索规则

- **优先用 SearchCodebase + memories/knowledge** 探索代码结构和依赖关系
- LSP：查定义、引用、调用链
- Grep/Glob：兜底搜索

## 代码规范

- 前端 TypeScript + Tailwind CSS + React hooks
- 后端 Python + FastAPI + async
- 代码注释英文
- 详见 `.claude/rules/code-quality.md`

## 部署

- GitHub Pages：`main` 分支 GitHub Actions 自动构建部署前端
- Railway：一键部署后端（`railway.json`）
- Docker：容器化部署（`Dockerfile` + `docker-compose.yml`）
- Redis：缓存层（`redis:7-alpine`）
- Qdrant：向量搜索（Qdrant Cloud / 本地 `qdrant/qdrant`）
- nginx：反向代理（SPA + API + WebSocket + Health）

MIT License
