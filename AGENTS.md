# AI 聊天助手 — Agent 开发指令

## 项目概述

**Python FastAPI + React 19 Agent 架构**：
- 后端：FastAPI + LangChain Agent（Tool Calling + 四层记忆）
- 前端：React 19 + TypeScript + Vite + Tailwind CSS 4

## 项目结构

```
Aureon/
├── backend/app/
│   ├── agent/        # LLM 工厂、Agent 工厂、流式执行器
│   ├── tools/        # @tool 装饰器，__init__.py 统一注册 ALL_TOOLS
│   ├── memory/       # L0-L3 四层记忆 + 上下文卸载
│   ├── rag/          # Qdrant + Hybrid Search + Context Compression + Adaptive Re-ranking
│   │   ├── vector_store.py  # 向量库 + BM25 检索
│   │   ├── qa_chain.py      # RAG pipeline（检索→CRAG→压缩→生成→来源）
│   │   ├── guardrails.py    # Prompt Injection 检测
│   │   ├── evaluator.py     # Recall + Faithfulness + 延迟
│   │   └── models.py        # Pydantic 请求/响应
│   ├── cache/        # Redis + 内存缓存、语义缓存去重
│   ├── routers/      # API 路由（chat.py, rag.py, crew.py）
│   ├── features/     # Feature Flag（灰度发布）
│   ├── observability/ # Query Trace、统计
│   ├── security/     # PII、SSO（Fernet 加密）、Rate Limiting
│   ├── evaluation/   # 评估指标、基准测试
│   ├── cost/         # 成本追踪、Budget
│   ├── reliability/  # 备份、事件、SLO、熔断器
│   ├── knowledge/    # 文档版本、导出
│   ├── ai_platform/  # LLM Router、置信度、会话记忆
│   ├── integration/  # 企业连接器、IM Bot
│   ├── langgraph/    # 工作流引擎 + MCP
│   ├── api/          # 模型 + Analytics
│   ├── common.py     # SSE_HEADERS, sse_event(), mask_secret
│   ├── config.py     # pydantic_settings
│   └── main.py       # FastAPI 入口 + Auth Middleware
├── backend/tests/     # 600+ tests
├── src/               # React 前端
│   ├── components/ hooks/ pages/ services/ i18n/ types/
│   ├── hooks/AuthContext.ts    # Auth 状态定义
│   └── hooks/AuthProvider.tsx  # Auth Provider
├── crew/              # CrewAI 文章生成
└── docker-compose.yml
```

## 开发规范

### 运行时环境
- **Python**: 3.12（已固化，见 `.python-version`）
- **Node.js**: 20 LTS
- **Docker**: 所有 Dockerfile 统一 `python:3.12-slim`
- **CI**: GitHub Actions 使用 `python-version: '3.12'`

### 后端
- 工具：`@tool` + 类型注解 + docstring → `ALL_TOOLS` 注册
- Agent：`create_agent(model, tools, prompt)` → `CompiledStateGraph`
- 输入：`{"messages": [HumanMessage(content=...)]}`
- 流式：`graph.astream_events(..., version="v2")`
- 测试：`tests/` + pytest + pytest-asyncio
- API Key 仅存 `.env`，生产环境通过 `API_AUTH_KEY` 启用认证
- 敏感字段（SSO secret/LLM key）通过 `security/__init__.py` Fernet 加密存储
- Docker 非 root 运行（gosu appuser）
- **Rerank 优化参数**（qa_chain.py）：
  - `RERANK_CANDIDATES`：rerank 候选数，默认 `12`
  - `ADAPTIVE_RERANK_THRESHOLD`：自适应跳过阈值，默认 `0.5`（top1/top2 分差比例）
  - `RETRIEVAL_MULTIPLIER`：检索乘数，默认 `7`
- **Embedding/Reranker API**（新加坡节点）：
  - Embedding: `dashscope-intl.aliyuncs.com/compatible-mode/v1`
  - Rerank: `dashscope-intl.aliyuncs.com/compatible-api/v1`（注意：`compatible-api` 不是 `compatible-mode`）
  - 向量后端: Qdrant Cloud（`VECTOR_BACKEND=qdrant`）

### 前端
- TypeScript + Tailwind CSS 4 + tailwindcss-animate
- Design Token 体系（index.css :root 变量，oklch 色阶）
- 组件：components/ui/ 通用 + components/landing/ 落地页 + components/search/ 搜索 + components/dashboard/ 仪表盘
- Chat：容器式输入框、消息 hover 工具栏（复制/重新生成/投票）、空状态快捷提问
- i18n：src/i18n/en.json + zh.json，useTranslation() hook
- SSE 事件：session/text/tool_start/tool_end/done/error
- Toast：sonner（App.tsx 根级 Toaster）
- API Key 从后端读取
- 字体：Plus Jakarta Sans（display）+ Inter（body）+ JetBrains Mono（code）

### 代码质量
- 类型注解完整：`def foo(x: int) -> str:`
- 异步优先：`async def` + `asyncio`
- 异常处理：禁裸 `except`，至少 `logger.exception()`
- 路径安全：`.resolve()` + 前缀检查
- 日志：`structlog.get_logger(__name__)`，禁 `print`，禁 `logging.getLogger`
- SSE 输出：`json.dumps(..., ensure_ascii=False)`，使用 `sse_event()` + `SSE_HEADERS`

## 记忆系统

| 层 | 存储 | 职责 |
|---|------|------|
| L0 | SQLite conversations | 原始对话 |
| L1 | SQLite atoms | 原子事实三元组 |
| L2 | offloads/scenarios/*.md | 场景总结 |
| L3 | offloads/persona.md | 用户画像 (≤2KB) |
| 卸载 | offloads/refs/*.md | 长工具输出外存 |

## 构建

```bash
# 后端
cd backend && uvicorn app.main:app --reload --port 8000
cd backend && python -m pytest tests/ -v

# 前端
npm install && npm run dev
npm test -- --run
npm run build

# 预览构建产物
npx vite preview --port 5174 --host 127.0.0.1
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/chat/stream | Agent SSE |
| POST | /api/chat/enhanced/stream | Chat + RAG |
| POST | /api/rag/query[/stream] | RAG 查询 |
| POST | /api/rag/upload | 上传并索引 |
| POST | /api/rag/index | 重建索引 |
| POST | /api/rag/evaluate | RAG 评估 |
| POST | /api/rag/experiment | Prompt 实验 |
| GET | /api/rag/{stats,uploads,documents,health,benchmark} | RAG 管理 |
| GET | /api/rag/analytics/{usage,latency,tokens,cache} | 分析 |
| POST | /api/langgraph/run | LangGraph |
| POST | /api/crew/generate[/stream] | CrewAI |
| GET | /api/crew/health | Crew 健康检查 |
| GET | /api/health | 健康检查 |

**认证**：配置 `API_AUTH_KEY` 后，所有 `/api/` 端点需 `X-API-Key` header（白名单：`/api/health`、`/api/crew/health`、`/metrics`）

语言规则：所有回复必须使用中文

## CI/CD 部署流程

**触发条件**：推送代码到 main 分支

**完整流程**：
1. **本地测试** → 前端 `npm test -- --run` + 后端 `cd backend && python -m pytest tests/ -v`
2. **推送** → `git push` 触发 GitHub Actions CI
3. **CI 通过** → `gh run view` 确认前端 + 后端测试全部通过
4. **Railway 自动部署** → 推送到 main 后自动触发
5. **部署完成** → `railway status` 确认 deployment status = SUCCESS
6. **生产验证** → `curl https://aureon-production-1247.up.railway.app/api/health` 确认 `status: ok`

**关键点**：
- 只推送 main 分支才会触发部署
- CI 失败 → 立即修，不能跳过
- 部署后必须验证生产端点，不能假设 push = 已部署
- Railway 健康检查超时 120s，部署通常 2-5 分钟

**耗时参考**（2026-06-04 实测）：
- CI 前端：~1m19s（49 tests + lint + build）
- CI 后端：~2m1s（426 tests）
- Railway 构建：~3m（Dockerfile Docker build）
- Railway 部署：~4m（健康检查 + 流量切换）
- 全流程（push → 生产就绪）：~8-10 分钟

**生产环境**：
- URL: `https://aureon-production-1247.up.railway.app`
- 健康检查: `GET /api/health`
- 服务: Aureon (Dockerfile) + Redis
- 区域: Southeast Asia

**监控命令**：
```bash
# CI 状态
gh run list --limit 3
gh run view <run-id>

# Railway 部署状态
railway status
railway logs --latest

# 生产端点验证
curl -s https://aureon-production-1247.up.railway.app/api/health | jq .
```

