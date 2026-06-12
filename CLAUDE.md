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
│   ├── config.py     # pydantic_settings（所有环境变量统一在此）
│   ├── exceptions.py # AureonException 层级异常体系
│   └── main.py       # FastAPI 入口 + Auth Middleware + TenantMiddleware
├── backend/tests/     # 753 passed, 18 skipped
├── src/               # React 前端
│   ├── components/ hooks/ pages/ services/ i18n/ types/
│   ├── hooks/AuthContext.ts    # Auth 状态定义
│   └── hooks/AuthProvider.tsx  # Auth Provider
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
- 测试：`tests/` + pytest + pytest-asyncio（753 passed, 18 skipped）
- API Key 仅存 `.env`，生产环境通过 `API_AUTH_KEY` 启用认证
- SSO/RBAC：JWT + Fernet 加密，`require_role(min_role)` FastAPI 依赖
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

## 测试体系

### 测试金字塔

```
                    ┌─────────────┐
                    │  生产冒烟    │  @pytest.mark.smoke
                    │  (3-5 测试)  │  每次部署后手动跑
                   ┌┴─────────────┴┐
                   │  质量门禁      │  @pytest.mark.quality
                   │  (DeepEval)   │  本地手动 / 合并前跑
                  ┌┴───────────────┴┐
                  │  性能基准        │  @pytest.mark.benchmark
                  │  (延迟/QPS/并发) │  本地手动跑
                 ┌┴─────────────────┴┐
                 │  单元测试          │  无 marker（CI 默认跑）
                 │  (753 tests)      │  每次 push 自动跑
                 └───────────────────┘
```

### Marker 体系

| Marker | 用途 | 运行环境 | CI |
|--------|------|---------|-----|
| （无） | 单元测试 | CI + 本地 | 自动跑 |
| `integration` | 需外部服务（Qdrant/LLM API） | 本地 | 默认跳过 |
| `benchmark` | 检索性能基准（延迟/Recall@K/MRR/QPS/并发） | 本地 | 跳过 |
| `quality` | DeepEval 质量门禁（走完整 rag_query pipeline） | 本地 | 跳过 |
| `smoke` | 生产冒烟（Railway 端点可达性） | 本地/部署后 | 跳过 |

### 测试文件结构

```
backend/tests/
├── benchmark_enterprise.py    # 统一基准测试（benchmark/quality/smoke 三层）
├── benchmark_config.yaml      # QA 数据集 + 阈值 + 端点配置
├── deepeval_eval.py           # DeepEval 评判逻辑（build_test_cases + run_deepeval_metrics）
├── test_data_golden.py        # 黄金数据集
├── conftest.py                # 全局 fixture（_bypass_rbac autouse）
└── test_*.py                  # 单元测试
```

### 运行命令

```bash
# CI 默认（仅单元测试，跳过所有 marker）
cd backend && python -m pytest tests/ -v

# 本地：仅检索性能基准
cd backend && python -m pytest tests/benchmark_enterprise.py -m benchmark -v

# 本地：仅 DeepEval 质量门禁
cd backend && python -m pytest tests/benchmark_enterprise.py -m quality -v

# 本地：仅生产冒烟
cd backend && python -m pytest tests/benchmark_enterprise.py -m smoke -v

# 本地：全量基准测试（性能 + 质量 + 冒烟）
cd backend && python -m pytest tests/benchmark_enterprise.py -m "benchmark or quality or smoke" -v

# 本地：所有测试（含集成）
cd backend && python -m pytest tests/ -m "" -v

# Lint 检查
cd backend && python -m ruff check tests/
```

### benchmark_config.yaml 结构

```yaml
qa_dataset:          # QA 数据集（1000+ 文档时扩展到 100+ 条）
  - question: "..."
    expected_answer: "..."
    source_article: "slug"
    is_negative: false

thresholds:          # 性能阈值（调参只改 YAML，不改代码）
  retrieval:         # 检索：P50≤200ms, P99≤1000ms, Recall@5≥0.95
  generation:        # 生成：P50≤2s, P99≤5s
  quality:           # 质量：Faithfulness≥0.7, AnswerRelevancy≥0.75
  cache:             # 缓存：命中率≥0.6
  smoke:             # 冒烟：health≤10s, rag_query≤30s

endpoints:           # 端点配置
  production: "https://aureon-production-1247.up.railway.app"
  local: "http://localhost:8000"

concurrency:         # 并发测试参数
  levels: [1, 5, 10]
```

### 质量门禁关键设计

- **走完整 rag_query() pipeline**：HyDE → 检索 → CRAG 自纠正 → 压缩 → 负例检测 → 生成
- **超时保护**：单次查询 60s + 整体评估 300s
- **并发数据准备**：`asyncio.gather` + `Semaphore(10)` 并发构建 test cases
- **DeepEval 配置**：`AsyncConfig(max_concurrent=15)` + `CacheConfig(use_cache=True)`

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

语言规则：所有回复必须使用简体中文回答

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

**耗时参考**（2026-06-11 实测）：
- CI 前端：~1m19s（74 tests + lint + build）
- CI 后端：~2m1s（753 tests + lint）
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
