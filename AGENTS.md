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
│   │   ├── vector_store.py  # 向量库（Qdrant 原生稀疏向量 + HNSW 量化，替代 jieba BM25）
│   │   ├── qa_chain.py      # RAG pipeline（HyDE→检索→轻量 CRAG→压缩→路由→生成→来源，已优化跳过冗余步骤）
│   │   ├── guardrails.py    # Prompt Injection 检测
│   │   ├── evaluator.py     # Recall + Faithfulness + 延迟
│   │   ├── models.py        # Pydantic 请求/响应
│   │   └── query_router.py  # Adaptive-RAG 查询路由（按复杂度分配检索策略）
│   ├── cache/        # Redis + 内存缓存、语义缓存去重
│   ├── routers/      # API 路由（chat.py, rag.py, crew.py, support.py）
│   ├── features/     # Feature Flag（灰度发布）
│   ├── observability/ # Query Trace、统计
│   │   ├── langfuse_integration.py  # LangFuse CallbackHandler 初始化/注入/关闭
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
│   ├── config.py     # pydantic_settings（所有环境变量统一在此）
│   ├── exceptions.py # AureonException 层级异常体系
│   └── main.py       # FastAPI 入口 + Auth Middleware + TenantMiddleware
├── backend/tests/     # 1008 passed (CI 2026-06-25)
├── src/               # React 前端
│   ├── components/ hooks/ pages/ services/ i18n/ types/
│   │   ├── shared/SourceCard.tsx     # 可展开来源引用
│   │   └── shared/MessageActions.tsx # 消息工具栏（复制/反馈/重新生成）
│   ├── support/quickReplyRoutes.ts   # 动态快捷回复（路由匹配）
│   ├── hooks/useSupportMessages.ts   # localStorage 持久化
│   ├── hooks/useSupportGreeting.ts   # 10s 延迟问候
│   ├── hooks/useUnreadCount.ts       # 未读计数（99+）
│   ├── hooks/AuthContext.ts          # Auth 状态定义
│   └── hooks/AuthProvider.tsx        # Auth Provider
└── docker-compose.yml
```

## 开发规范

### 运行时环境
- **Python**: 3.12（已固化，见 `.python-version`）
- **Node.js**: 20+（Docker 使用 node:22-alpine）
- **Docker**: 所有 Dockerfile 统一 `python:3.12-slim`
- **CI**: GitHub Actions 使用 `python-version: '3.12'`

### 后端
- 工具：`@tool` + 类型注解 + docstring → `ALL_TOOLS` 注册
- Agent：`create_agent(model, tools, prompt)` → `CompiledStateGraph`
- 输入：`{"messages": [HumanMessage(content=...)]}`
- 流式：`graph.astream_events(..., version="v2")`
- 测试：`tests/` + pytest + pytest-asyncio（793 passed, 5 skipped）
- API Key 仅存 `.env`，生产环境通过 `API_AUTH_KEY` 启用认证
- SSO/RBAC：JWT + Fernet 加密，`require_role(min_role)` FastAPI 依赖
- 敏感字段（SSO secret/LLM key）通过 `security/__init__.py` Fernet 加密存储
- Docker 非 root 运行（backend: USER 1001, root: gosu appuser）
- 多租户隔离：JWT 签名验证提取 tenant_id（纯 ASGI 中间件，SSE 零缓冲）
- 审计日志：user_id 从已验证 JWT 提取（不信任客户端 header）
- CORS 白名单：`allow_headers` 显式列出（不含 `*`）
- Dev 模式：生产平台硬阻断（启动时校验 + RBAC 旁路阻断）
- **Rerank 优化参数**（qa_chain.py）：
  - `RERANK_CANDIDATES`：rerank 候选数，默认 `12`
  - `ADAPTIVE_RERANK_THRESHOLD`：自适应跳过阈值，默认 `0.5`（top1/top2 分差比例）
  - `RETRIEVAL_MULTIPLIER`：检索乘数，默认 `7`
  - **R19 动态 rerank 阈值**（[qdrant_ops.py](file:///c:/Users/Yum/Desktop/Aureon-test/backend/app/rag/qdrant_ops.py)）：
    - `_RERANK_THRESHOLDS = {"simple": 0.55, "medium": 0.40, "complex": 0.30}`
    - 根据查询复杂度动态调整 rerank 过滤阈值
    - `query_complexity` 参数从 `generator.py` → `retriever.py` → `qdrant_ops.py` 传递
- **Embedding/Reranker API**（新加坡节点）：
  - Embedding: `dashscope-intl.aliyuncs.com/compatible-mode/v1`
  - Rerank: `dashscope-intl.aliyuncs.com/compatible-api/v1`（注意：`compatible-api` 不是 `compatible-mode`）
  - 向量后端: Qdrant Cloud（`VECTOR_BACKEND=qdrant`）
- **稀疏向量配置**：
  - `SPARSE_VECTOR_ENABLED=true` — 启用 Qdrant 原生稀疏向量
  - 使用 BGE-M3 模型生成 dense + sparse 联合向量
- **查询路由配置**（qa_chain.py）：
  - `QUERY_ROUTER_ENABLED=true` — 启用 Adaptive-RAG 查询路由
  - `SIMPLE_THRESHOLD` / `COMPLEX_THRESHOLD` — 路由决策阈值
- **Observability 配置**（[langfuse_integration.py](file:///c:/Users/Yum/Desktop/Aureon-test/backend/app/observability/langfuse_integration.py)）：
  - `LANGFUSE_ENABLED=true` — 启用 LangFuse 全链路追踪
  - `LANGFUSE_PUBLIC_KEY` — LangFuse 公钥（必填）
  - `LANGFUSE_SECRET_KEY` — LangFuse 密钥（必填）
  - `LANGFUSE_HOST` — LangFuse 端点（默认 `https://cloud.langfuse.com`，新加坡近端推荐用东京区域）
  - `LANGFUSE_RELEASE` — 部署版本标记（可选，用于 release 追踪）
- **LangFuse 集成架构**：
  - `init_langfuse()` — FastAPI lifespan startup 中调用，异步 check_connection 验证凭据
  - `get_langfuse_handler()` — 返回 `CallbackHandler` 单例，注入到 `astream_events` 的 `config={"callbacks": [...]}`
  - `shutdown_langfuse()` — lifespan shutdown 中调用，flush 所有待发送事件
  - `get_trace_url(trace_id)` — 生成 trace 链接，可直接跳转到 LangFuse 控制台
  - LangChain CallbackHandler 自动嵌套追踪：LLM 调用 → tool 调用 → chain 步骤 → RAG 查询
- **LangGraph 集成点**（[executor.py](file:///c:/Users/Yum/Desktop/Aureon-test/backend/app/agent/executor.py)）：
  - `stream_agent()` 中的 `astream_events` 通过 `config={"callbacks": [handler]}` 注入
  - session_id 自动映射到 LangFuse trace 的 session 标签

### 前端
- TypeScript + Tailwind CSS 4 + tailwindcss-animate
- Design Token 体系（index.css :root 变量，oklch 色阶）
- 组件：components/ui/ 通用 + components/landing/ 落地页 + components/search/ 搜索 + components/dashboard/ 仪表盘
- Chat：容器式输入框、消息 hover 工具栏（复制/重新生成/投票）、空状态快捷提问
- Support Widget：FAB 浮动按钮 → 聊天面板，含 localStorage 持久化、10s 延迟问候、打字状态、动态快捷回复、离线表单、未读徽章
- i18n：src/i18n/en.json + zh.json，useTranslation() hook，含 34 个 support 相关键
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

## 企业级 RAG 优化

### Qdrant 配置
- **HNSW 参数**: m=32, ef_construct=200, ef_search=128
- **标量量化**: INT8 量化向量常驻内存（always_ram=True），原始向量存磁盘
- **Payload 索引**: metadata.slug / metadata.language / metadata.source / metadata.tenant_id
- **稀疏向量**: BGE-M3 dense(1024d) + sparse，Qdrant 原生 hybrid search（RRF fusion）

### 检索 Pipeline
```
Query → Query Router（简单/中等/复杂）→
   ├── 简单 → 纯稀疏向量（<10ms）
   ├── 中等 → Hybrid（dense+sparse）→ 自适应重排序
   └── 复杂 → HyDE → Multi-Query → Hybrid → Ensemble Rerank → 轻量 CRAG
```

### 轻量 CRAG（替代 LLM CRAG）
- 基于 embedding 相似度的快速检索质量评估
- 三路动作：correct（直接输出）/ ambiguous（重写查询重试）/ incorrect（返回无结果）
- 评估延迟：~50ms（vs LLM CRAG 的 ~1s）
- 已在流式路径中启用

### 查询路由（Adaptive-RAG）
- **简单查询**（事实型，关键词匹配即可）→ 纯稀疏向量检索
- **中等查询**（分析型，需语义理解）→ hybrid retrieve + 自适应重排序
- **复杂查询**（推理型，需多角度）→ HyDE + multi_query + ensemble rerank + CRAG

### 负例检测（Negative Detection）
- **关键词快速路径**：`_NEGATIVE_KEYWORDS_ZH` 命中定价、团队、版本等商业敏感词
- **LLM 分类器**：关键词未命中时调用轻量模型二次判断
- **跳过阈值**：`high_score_skip_threshold=0.1`，高置信度检索结果跳过检测

### Embedding 统一
- 本地 BGE-large-zh-v1.5 和 API 统一输出 1024 维
- Embedding Fallback Chain: local BGE → DashScope → SiliconFlow → Zhipu
- 语义缓存复用 API fallback 链，支持 API-only 模式

### 可观测性
- **LangFuse**: 全链路追踪（每步延迟、token 使用、检索质量）
- structlog 结构化日志
- Prometheus /metrics 端点

### Contextual Retrieval 并发化
- `asyncio.gather` + `Semaphore(5)` 并发生成 chunk 上下文前缀
- 1000 文档索引构建时间从 ~1h 降至 ~10min

## 测试体系

> 详细 benchmark 结果、Judge 配置与优化历史见 `docs/benchmarks/recall-evaluation.md`。

### Marker 体系

| Marker | 用途 | 运行环境 | CI |
|--------|------|---------|-----|
| （无） | 单元测试（793 tests） | CI + 本地 | 自动跑 |
| `integration` | 需外部服务（Qdrant/LLM API） | 本地 | 默认跳过 |
| `benchmark` | 检索性能基准 | 本地 | 跳过 |
| `quality` | DeepEval 质量门禁 | 本地 | 跳过 |
| `smoke` | 生产冒烟 | 本地/部署后 | 跳过 |

### 关键命令

```bash
# CI 默认单元测试
cd backend && python -m pytest tests/ -v

# 统一 Benchmark（采集 → 评估 → 报告）
cd backend && python tests/run_full_benchmark.py

# 分层 pytest 基准
cd backend && python -m pytest tests/benchmark_enterprise.py -m benchmark -v
cd backend && python -m pytest tests/benchmark_enterprise.py -m quality -v
cd backend && python -m pytest tests/benchmark_enterprise.py -m smoke -v

# Lint
cd backend && python -m ruff check tests/
```

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
| GET | /health/ready | 就绪探针（Redis/Qdrant/索引） |
| POST | /api/v1/support/offline-message | Support 离线消息 |
| WS | /ws/chat/{client_id} | WebSocket 实时聊天 |
| GET | /metrics | Prometheus 指标 |
| * | /api/feature-flags/* | Feature Flags |
| * | /api/observability/* | 查询追踪 |
| * | /api/security/* | SSO/PKI 管理 |
| * | /api/evaluation/* | 评估指标 |
| * | /api/cost/* | 成本追踪 |
| * | /api/reliability/* | SLO/熔断器 |
| * | /api/knowledge/* | 文档版本 |
| * | /api/ai-platform/* | LLM Router |
| * | /api/integration/* | 企业连接器 |
| * | /api/audit/* | 审计日志 |

**认证**：配置 `API_AUTH_KEY` 后，所有 `/api/` 端点需 `X-API-Key` header（白名单：`/api/health`、`/api/crew/health`、`/metrics`）。SSO/RBAC 端点需 `Authorization: Bearer <JWT>` header，JWT 签名密钥由 `JWT_SECRET` 环境变量提供。

**端点认证要求**（2026-06-23 更新）：
| 端点 | 角色要求 | 说明 |
|------|----------|------|
| GET /api/rag/uploads | VIEWER | 列出上传文件 |
| DELETE /api/rag/upload/{fn} | EDITOR | 删除文档 |
| POST /api/rag/cache/clear | ADMIN | 清除缓存 |

**生产平台检测**：dev 模式绕过检查扩展到 Railway、Render、Fly.io、Heroku、Vercel、Netlify。

## 用户引导系统

**引导流程**（搜索优先，价值驱动）：
1. **搜索体验** → 展示核心价值（自动预填示例查询）
2. **上传文档** → 让知识库个人化
3. **搜索自己的数据** → Aha moment
4. **仪表盘** → 系统状态（仅管理员）
5. **分析** → 使用洞察（仅管理员）

**角色感知**：Viewer 看 3 步，Editor/Admin 看 5 步。

**相关文件**：
- `src/components/onboarding/steps.ts` — 步骤配置
- `src/components/onboarding/OnboardingProvider.tsx` — 引导状态管理
- `src/i18n/zh.json` / `en.json` — 引导文案

语言规则：所有回复必须使用简体中文回答

## CI/CD 部署流程

**触发条件**：推送代码到 main 分支

**完整流程**：
1. **本地测试** → 前端 `npm test -- --run` + 后端 `cd backend && python -m pytest tests/ -v`
2. **推送** → `git push` 触发 GitHub Actions CI
3. **CI 通过** → `gh run view` 确认前端 + 后端测试全部通过
4. **Railway 自动部署** → 推送到 main 后自动触发
5. **部署完成** → `railway status` 确认 deployment status = SUCCESS
6. **生产验证** → `curl https://aureon-production-659a.up.railway.app/api/health` 确认 `status: ok`

**关键点**：
- 只推送 main 分支才会触发部署
- CI 失败 → 立即修，不能跳过
- 部署后必须验证生产端点，不能假设 push = 已部署
- Railway 健康检查超时 120s，部署通常 2-5 分钟

**CI 安全扫描**（2026-06-18 新增）：
- `pip-audit`：Python 依赖漏洞扫描（严格模式）
- `Trivy`：Docker 镜像漏洞扫描（CRITICAL/HIGH）
- `hadolint`：Dockerfile 规范检查（强制，不可跳过）
- `mypy`：类型检查（渐进式，当前 `continue-on-error`）
- `Dependabot`：每周自动检查依赖更新

**pre-commit hooks**（2026-06-18 新增）：
- 安装：`pip install pre-commit && pre-commit install`
- 包含：ruff lint+format、trailing-whitespace、detect-private-key、detect-secrets
- mypy 手动触发：`pre-commit run mypy --all-files`

**耗时参考**（2026-06-11 实测）：
- CI 前端：~1m19s（74 tests + lint + build）
- CI 后端：~2m1s（793 tests + lint）
- Railway 构建：~3m（Dockerfile Docker build）
- Railway 部署：~4m（健康检查 + 流量切换）
- 全流程（push → 生产就绪）：~8-10 分钟

**生产环境**：
- URL: `https://aureon-production-659a.up.railway.app`
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
curl -s https://aureon-production-659a.up.railway.app/api/health | jq .
```

