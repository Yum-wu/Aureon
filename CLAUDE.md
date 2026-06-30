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
│   ├── rag/          # Qdrant + Hybrid Search + Adaptive Re-ranking
│   │   ├── ingestion/       # 文档摄取管线（extractor → normalizer → chunk → quality gate）
│   │   │   ├── extractors.py/normalizer.py/models.py/policy.py/quality.py/pipeline.py
│   │   ├── indexer.py       # run_incremental_index / run_index_pipeline
│   │   ├── index_manager.py # Qdrant add_to_index / delete_from_index
│   │   ├── qa_chain.py      # RAG pipeline（HyDE→检索→CRAG→生成+来源）
│   │   ├── qdrant_ops.py    # Qdrant 操作（hybrid_search + sparse + dense）
│   │   ├── guardrails.py    # Prompt Injection 检测
│   │   ├── evaluator.py     # Recall + Faithfulness + 延迟
│   │   ├── query_router.py  # Adaptive-RAG 查询路由
│   │   └── loader.py        # 文档加载（load_single_document + 遗留包装函数）
│   ├── cache/        # Redis + 内存缓存、语义缓存去重
│   ├── routers/      # API 路由（chat.py, rag.py, crew.py, support.py）
│   ├── observability/ # LangFuse 全链路追踪
│   ├── security/     # PII、SSO（Fernet 加密）、Rate Limiting
│   ├── cost/         # 成本追踪、Budget（Redis 时间序列）
│   ├── reliability/  # 备份、事件、SLO、熔断器
│   ├── langgraph/    # 工作流引擎 + MCP
│   ├── config.py     # pydantic_settings（所有环境变量）
│   ├── common.py     # SSE_HEADERS, sse_event(), mask_secret
│   └── main.py       # FastAPI 入口 + Auth Middleware + TenantMiddleware
├── backend/tests/     # 958 passed (2026-06-30)
├── src/               # React 前端
│   ├── components/ hooks/ pages/ services/ i18n/ types/
│   ├── support/quickReplyRoutes.ts   # 动态快捷回复
│   ├── hooks/useSupportMessages.ts   # localStorage 持久化
│   ├── hooks/useSupportGreeting.ts   # 10s 延迟问候
│   └── hooks/useUnreadCount.ts       # 未读计数（99+）
└── docker-compose.yml
```

## 前置要求

- **改动前必读 `CONTEXT.md`**：领域术语、系统边界、RAG 迭代历史
- **MVP 模式 + 架构精简（2026-06-29）**：禁止过度工程化。加功能前问：不加会怎样？
- **已删除模块禁止重新添加**（-5719 行）：ai_platform、features、integration、knowledge、evaluation 路由、bulkhead、chaos、timeouts、post_generation_reflection、threshold_tuner、reranking_ab_test、vector_store_interface、analytics_store、旧 SQLite cost CRUD。新需求先在 CONTEXT.md 提 issue。

## 开发规范

### 运行时
- **Python**: 3.12（`.python-version`），**Node.js**: 20+，**Docker**: `python:3.12-slim`

### 后端
- 工具：`@tool` + 类型注解 + docstring → `ALL_TOOLS`
- Agent：`create_agent(model, tools, prompt)` → `CompiledStateGraph`，输入 `{"messages": [HumanMessage(...)]}`
- 流式：`graph.astream_events(..., version="v2")`，SSE 输出：`json.dumps(..., ensure_ascii=False)` + `sse_event()` + `SSE_HEADERS`
- API Key 仅存 `.env`，生产通过 `API_AUTH_KEY` 启用
- **数据库**：PostgreSQL（`DATABASE_URL` 设时自动启用 `PGStorageBackend`），否则降级 SQLite
- SSO/RBAC：JWT + Fernet 加密 + `require_role(min_role)`
- 多租户：JWT 签名验证 tenant_id（纯 ASGI 中间件，SSE 零缓冲）
- 审计：user_id 从已验证 JWT 提取（不信任客户端 header）
- CORS：`allow_headers` 显式列出（不含 `*`），Docker 非 root 运行
- Dev 模式：生产平台硬阻断（Railway/Render/Fly.io/Heroku/Vercel/Netlify）
- **R19 动态 rerank 阈值**（qdrant_ops.py）：`{"simple": 0.55, "medium": 0.40, "complex": 0.30}`
- **Embedding/Reranker API**（新加坡 DashScope intl）：embedding `compatible-mode/v1`，rerank `compatible-api/v1`
- **向量后端**: Qdrant Cloud，BGE-M3 dense(1024d) + sparse hybrid (RRF)
- **LangFuse**: `init_langfuse()` → `get_langfuse_handler()` → 注入 `astream_events` → `shutdown_langfuse()`

### 前端
- React 19 + TypeScript + Vite + Tailwind CSS 4 + tailwindcss-animate
- Design Token 体系（oklch），字体 Plus Jakarta Sans + Inter + JetBrains Mono
- 组件：ui/ + landing/ + search/ + dashboard/，Toast：sonner
- Chat：容器式输入框 + hover 工具栏（复制/重新生成/投票）
- Support Widget：FAB → 聊天面板，含持久化、问候、快捷回复、离线表单、未读徽章
- i18n：en.json + zh.json，34 support 键，SSE：session/text/tool_start/tool_end/done/error
- Onboarding：搜索优先，Viewer 3 步 / Editor+ 5 步，`src/components/onboarding/`

### 代码质量
- 类型注解完整、异步优先、禁裸 `except`、`structlog.get_logger(__name__)` 禁 `print`
- 路径安全 `.resolve()` + 前缀检查

## 记忆系统

| 层 | 存储 | 职责 |
|---|------|------|
| L0 | PostgreSQL conversations（`memory/pg.py`） | 原始对话 |
| L1 | PostgreSQL atoms（`memory/pg.py`） | 原子事实三元组 |
| L2 | offloads/scenarios/*.md | 场景总结 |
| L3 | offloads/persona.md | 用户画像 (≤2KB) |
| 卸载 | offloads/refs/*.md | 长工具输出外存 |

## RAG 系统（详见 CONTEXT.md）

| 配置项 | 值 |
|--------|-----|
| HNSW | m=32, ef_construct=200, ef_search=128 |
| 量化 | INT8（always_ram=True） |
| Payload 索引 | slug, language, source, tenant_id |
| Chunking | ParentChildSplitter: parent=1500, child=512, overlap=80 |
| 检索 Pipeline | 简单→sparse(<10ms), 中等→hybrid+rerank, 复杂→HyDE+multi_query+CRAG |
| 轻量 CRAG | embedding 相似度评估，~50ms |
| 负例检测 | 关键词快速路径 + LLM 分类器 |
| Embedding Fallback | local BGE → DashScope → SiliconFlow → Zhipu |
| Contextual Retrieval | Semaphore(5) 并发，~10min/1000 docs |

## 测试体系

| Marker | 用途 | CI |
|--------|------|-----|
| （无） | 单元测试（958 tests） | 自动跑 |
| `integration` | 需外部服务 | 默认跳过 |
| `benchmark` | 检索性能基准 | 跳过 |
| `quality` | DeepEval 质量门禁 | 跳过 |
| `smoke` | 生产冒烟 | 跳过 |

```bash
cd backend && python -m pytest tests/ -v          # CI 默认
cd backend && python tests/run_full_benchmark.py  # 采集→评估→报告
cd backend && python -m pytest tests/benchmark_enterprise.py -m benchmark/quality/smoke -v
cd backend && python -m ruff check tests/         # Lint
```

## 构建

```bash
cd backend && uvicorn app.main:app --reload --port 8000
npm install && npm run dev          # 前端
npm test -- --run && npm run build  # 测试+构建
npx vite preview --port 5174 --host 127.0.0.1  # 预览
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
| GET | /health/ready | 就绪探针 |
| POST | /api/v1/support/offline-message | Support 离线 |
| WS | /ws/chat/{client_id} | WebSocket |
| GET | /metrics | Prometheus |
| * | /api/{observability,security,cost,reliability,audit}/* | 管理 |

**认证**：`API_AUTH_KEY` → `X-API-Key` header（白名单：`/api/health`, `/api/crew/health`, `/metrics`）。
SSO/RBAC：`Authorization: Bearer <JWT>`，`JWT_SECRET` 签名。
**RBAC 端点**：`GET /api/rag/uploads`(VIEWER), `DELETE /api/rag/upload/{fn}`(EDITOR), `POST /api/rag/cache/clear`(ADMIN)。

## CI/CD 部署流程

1. 本地测试 → 2. `git push` → 3. CI（前端 ~1m19s + 后端 ~2m1s）→ 4. Railway 自动部署（~4m）
生产：`https://aureon-production-659a.up.railway.app`，Southeast Asia，Aureon + Redis

```bash
gh run list --limit 3 && gh run view <run-id>    # CI
railway status && railway logs --latest          # 部署
curl -s https://aureon-production-659a.up.railway.app/api/health | jq .  # 验证
```

**CI 安全**：pip-audit, Trivy, hadolint, mypy (continue-on-error), Dependabot
**pre-commit**：ruff lint+format, trailing-whitespace, detect-private-key, detect-secrets

语言规则：所有回复必须使用简体中文回答
