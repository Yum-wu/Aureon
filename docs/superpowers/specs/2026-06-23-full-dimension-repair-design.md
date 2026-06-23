# Aureon 全维度修复方案设计文档

> 日期：2026-06-23
> 状态：待审批
> 策略：全面并行、分阶段实施
> 目标：综合评分从 6.51 提升到 8.5+

---

## 一、目标与约束

### 评分目标

| 维度 | 当前 | Phase 1 目标 | Phase 2 目标 | Phase 3 目标 | Phase 4 目标 |
|------|------|-------------|-------------|-------------|-------------|
| 安全性 | 5.5 | 7.5 | 8.5 | 9.5 | 10 |
| 代码健壮性 | 6.0 | 7.5 | 8.5 | 9.0 | 9.5 |
| 可测试性 | 6.0 | 6.5 | 8.0 | 9.0 | 10 |
| 可维护性 | 6.5 | 7.0 | 8.5 | 9.0 | 9.5 |
| 鲁棒性 | 6.5 | 7.0 | 8.5 | 9.0 | 10 |
| 资源效率 | 6.5 | 8.0 | 9.0 | 9.5 | 10 |
| 性能 | 7.0 | 8.0 | 9.0 | 9.5 | 10 |
| 可观测性 | 7.0 | 7.5 | 8.5 | 9.5 | 10 |
| 可移植性 | 7.0 | 8.0 | 8.5 | 9.5 | 10 |
| 可扩展性 | 7.5 | 8.0 | 9.0 | 9.5 | 10 |
| **加权平均** | **6.51** | **7.5** | **8.5** | **9.3** | **9.8** |

### 约束条件

- 不破坏现有 793 个后端测试
- 每个 Phase 可独立部署验证
- 安全修复不引入 breaking change
- 前端修改保持 API 兼容

---

## 二、Phase 1：Quick Wins（1-2 周）

**目标**：所有维度高 ROI 快速修复，加权分从 6.51 → 7.5

### 2.1 安全性 [S] — 预期 5.5 → 7.5

#### S1: RBAC API Key 常量时间比较
- **文件**: `backend/app/security/rbac.py:149`
- **修改**: `api_key == settings.api_auth_key` → `hmac.compare_digest(api_key.encode(), settings.api_auth_key.encode())`
- **来源**: Python `hmac` 官方文档

#### S2: LangGraph 端点添加认证
- **文件**: `backend/app/main.py:168-174`
- **修改**: 添加 `dependencies=[Depends(require_role(UserRole.VIEWER))]`
- **来源**: FastAPI Security 文档

#### S3: 移除前端硬编码 API Key
- **文件**: `src/pages/Dashboard.tsx:73`, `src/pages/Login.tsx:206`
- **修改**: 删除硬编码 key，改为从 `/api/config` 端点获取运行时配置
- **方案**: 新增后端 `/api/config` 端点返回公开配置值

#### S4: PII mask 端点移除 original 字段
- **文件**: `backend/app/security/router.py:98-105`
- **修改**: 响应从 `{"original": text, "masked": masked}` 改为 `{"masked": masked}`

#### S5: 错误消息脱敏
- **文件**: `backend/app/langgraph/graph.py:138`
- **修改**: `f"处理出错：{e}"` → `f"处理出错，请稍后重试"` + 结构化日志记录原始错误

### 2.2 代码健壮性 [R] — 预期 6.0 → 7.5

#### R1: 全局单例线程安全（8 处）
需要添加 `threading.Lock` 的文件和全局变量：

| 文件 | 全局变量 | 修复方式 |
|------|---------|---------|
| `rag/qdrant_ops.py:26` | `_qdrant_client` | 双重检查锁定 |
| `memory/manager.py:25` | `_sessions` | `threading.Lock` 保护 |
| `cache/redis_client.py:69` | `get_semantic_cache_instance` | `threading.Lock` |
| `cache/semantic_cache.py:145` | `_mem_semantic_cache` | `TTLCache` + `Lock` |
| `rag/embedding.py` | `_embed_cache` | `TTLCache` + `Lock` |
| `agent/llm.py:30` | `_llm_pool` | `collections.OrderedDict` + `Lock` |
| `rag/reranker.py` | `_reranker_instance` | 双重检查锁定 |
| `rag/ensemble_reranker.py:99` | `EnsembleReranker` | `threading.Lock` |

**标准模式**：
```python
import threading

_lock = threading.Lock()
_instance = None

def get_instance():
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:  # 双重检查
                _instance = create_instance()
    return _instance
```

#### R2: useChatStore sending 标志 try-finally
- **文件**: `src/stores/useChatStore.ts:61`
- **修改**: `sending` 状态更新移入 `finally` 块

#### R3: stream_agent error 后不 yield done
- **文件**: `backend/app/agent/executor.py:64-70`
- **修改**: `except` 块中 yield error 后直接 `return`，不 yield done

### 2.3 性能 [P] — 预期 7.0 → 8.0

#### P1: `_cosine_similarity` 改用 NumPy
- **文件**: `backend/app/cache/semantic_cache.py:269-285`
- **修改**:
```python
import numpy as np

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    return float(np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb) + 1e-8))
```
- **来源**: NumPy 官方文档，BLAS 级矩阵运算

#### P2: `_mem_semantic_cache` 改为 LRU + TTL 有界缓存
- **文件**: `backend/app/cache/semantic_cache.py:145`
- **修改**: 替换 `cachetools.TTLCache(maxsize=5000, ttl=3600)` + `threading.Lock`
- **来源**: cachetools 官方文档

#### P3: httpx.AsyncClient 单例（Lifespan 级别）
- **文件**: `backend/app/startup/lifespan.py`（新增）或 `backend/app/main.py`
- **修改**: 在 FastAPI lifespan 中创建 httpx.AsyncClient 单例，注入到 `app.state.http_client`
- **影响**: `rag/embedding.py`, `rag/reranker.py`, `langgraph/mcp/client.py` 全部改用注入的 client
- **来源**: httpx 官方文档 — "Top-level API 不复用连接"

#### P4: queryPersister throttleTime 优化
- **文件**: `src/providers/queryPersister.ts:18`
- **修改**: `throttleTime: 0` → `throttleTime: 1000`

### 2.4 可测试性 [T] — 预期 6.0 → 6.5

#### T1: Vitest coverage 阈值配置
- **文件**: `vitest.config.ts`
- **修改**: 添加 `coverage.thresholds: { lines: 60, functions: 60, branches: 60 }`
- **策略**: 从 60% 起步，逐步提升到 80%

#### T2: Zustand store 基础测试
- **新增文件**: `src/stores/__tests__/useChatStore.test.ts`
- **内容**: 测试 addMessage、clearMessages、sending 状态管理

### 2.5 可维护性 [M] — 预期 6.5 → 7.0

#### M1: pyproject.toml 迁移
- **新增**: `backend/pyproject.toml`（PEP 621 格式）
- **修改**: 生产依赖和开发依赖分离（`[project.optional-dependencies] dev = [...]`）
- **来源**: PEP 621

#### M2: .env.example 生成
- **新增**: `backend/.env.example`
- **方式**: 从 `config.py` 的 Pydantic Settings 自动生成

#### M3: 生产平台检测统一
- **修改**: 提取 `backend/app/utils/platform.py` — `is_production_platform()` 共享函数
- **影响**: `security/rbac.py`, `security/router.py` 统一调用

### 2.6 鲁棒性 [RB] — 预期 6.5 → 7.0

#### RB1: Redis 重连指数退避
- **文件**: `backend/app/cache/connection.py:12`
- **修改**: 移除硬编码 `_SYNC_RECONNECT_AFTER=5`，改为带时间窗口的指数退避
- **模式**: 失败后 0.1s → 0.2s → 0.4s → ... → 30s max，60s 无失败重置计数
- **来源**: Microsoft Cloud Design Patterns — Retry Pattern

#### RB2: 异常链保留
- **全局搜索**: 所有 bare `raise RuntimeError(...)` 改为 `raise ... from e`
- **关键文件**: `rag/qdrant_ops.py`, `rag/embedding.py`, `rag/reranker.py`

### 2.7 可观测性 [OB] — 预期 7.0 → 7.5

#### OB1: LangFuse 客户端复用
- **文件**: `backend/app/observability/langfuse_integration.py`
- **修改**: 使用 `langfuse.get_client()` 替代手动 `Langfuse()` 构造
- **文件**: `backend/app/observability/prompt_manager.py:53`
- **修改**: 复用 `langfuse_integration.py` 的客户端实例
- **来源**: LangFuse Python SDK 文档

#### OB2: Prometheus Histogram 替代 Summary
- **文件**: `backend/app/observability/custom_metrics.py`
- **修改**: 请求延迟指标从 Summary 改为 Histogram，配置合理 bucket
- **来源**: Prometheus 官方文档 — Histogram 可跨实例聚合

### 2.8 可移植性 [PO] — 预期 7.0 → 8.0

#### PO1: 测试依赖分离
- **文件**: `backend/requirements.txt` + 新增 `backend/requirements-dev.txt`
- **修改**: pytest/pytest-asyncio/pytest-xdist 等移到 dev 依赖
- **Dockerfile**: 仅安装 `requirements.txt`（生产依赖）

#### PO2: Docker COPY 优化
- **文件**: `Dockerfile`
- **修改**: Stage 1 的 `COPY . .` → 仅复制 `package.json`, `vite.config.ts`, `src/`, `index.html`, `public/`

### 2.9 可扩展性 [EX] — 预期 7.5 → 8.0

#### EX1: Point ID 改用 UUID
- **文件**: `backend/app/rag/index_manager.py:82-87`
- **修改**: `existing_count + idx` → `uuid.uuid4().hex`
- **来源**: RFC 9562, Qdrant 官方文档

#### EX2: app.state 统一全局状态
- **文件**: `backend/app/main.py` lifespan
- **修改**: 将 `_qdrant_client`, `_redis`, `_llm_pool` 等注册到 `app.state`
- **收益**: 便于测试重置、依赖注入、生命周期管理

### 2.10 资源效率 [RE] — 预期 6.5 → 8.0

#### RE1: `_qdrant_search` 过期检查
- **文件**: `backend/app/cache/semantic_cache.py:210-225`
- **修改**: 返回前检查 `expires_at` 字段

#### RE2: 过期缓存定期清理
- **新增**: lifespan 中启动 `asyncio.create_task(cleanup_loop())`
- **功能**: 每 5 分钟调用 `cache.expire()` 清理过期条目

---

## 三、Phase 2：Medium Effort（3-4 周）

**目标**：中等工作量改造，加权分从 7.5 → 8.5

### 3.1 安全性 [S] — 7.5 → 8.5

#### S6: Content Security Policy
- **文件**: `backend/app/main.py`（新增中间件）
- **修改**: 添加 `SecurityHeadersMiddleware`，设置 CSP、HSTS、Referrer-Policy
- **CSP 策略**: `default-src 'self'; script-src 'self'; connect-src 'self' https://aureon-production-659a.up.railway.app; frame-ancestors 'none'`
- **来源**: OWASP CSP Cheat Sheet

#### S7: ReactMarkdown rehype-sanitize
- **文件**: `src/components/MessageItem.tsx:66-68`
- **修改**: 添加 `rehypePlugins={[[rehypeSanitize, strictSchema]]}`
- **Schema**: 仅允许 `p, br, strong, em, code, pre, ul, ol, li, h1-h3, a, blockquote`
- **来源**: OWASP XSS Prevention

#### S8: WebSocket token 安全传输
- **文件**: `src/services/ws.ts:83`
- **修改**: token 从 URL 参数 → WebSocket 握手第一条消息或 subprotocol
- **来源**: OWASP API Security

#### S9: `/metrics` 端点认证
- **文件**: `backend/app/main.py:140`
- **修改**: 添加 `X-Metrics-Key` header 验证（可选，通过环境变量启用）

### 3.2 代码健壮性 [R] — 7.5 → 8.5

#### R4: SSE 协议规范化
- **文件**: `backend/app/common.py`
- **修改**: `sse_event()` 函数添加 `id:` 和 `event:` 字段，确保符合 WHATWG SSE 规范
- **前端**: `src/services/api.ts` 添加 `done` 事件处理 + 错误事件处理
- **来源**: WHATWG SSE 规范

#### R5: LLM 输出 JSON 解析鲁棒性
- **文件**: `backend/app/memory/manager.py:79-85`
- **修改**: `extract_atoms()` 处理 markdown 代码块语言标记（` ```json ` vs ` ``` `）
- **新增**: `parse_llm_json()` 通用工具函数（处理尾部逗号、代码块提取、Pydantic 验证）

#### R6: bare except 消除
- **全局搜索**: `except Exception:` without logging
- **修改**: 至少添加 `logger.exception()`，关键路径改为精确异常类型

### 3.3 性能 [P] — 8.0 → 9.0

#### P5: 分布式锁重写
- **文件**: `backend/app/rag/qdrant_ops.py:108-116`
- **修改**: `sleep(10) * 30` 轮询 → Redis `SET NX PX` + Lua 脚本释放
- **模式**: 单实例锁（Railway 单节点足够）
- **来源**: Redis 官方 Distributed Locks 文档

#### P6: Redis Pipeline 批处理
- **文件**: `backend/app/cost/budget_engine.py:197-206`
- **修改**: 30 次 `hgetall` → `redis.pipeline(transaction=False)` 批量读取
- **文件**: `backend/app/cost/service.py:79-90`
- **修改**: 7+ 次 Redis 写入 → pipeline 批量写入
- **来源**: redis-py 官方文档

#### P7: Embedding 缓存去重
- **文件**: `backend/app/rag/embedding.py`
- **修改**: 批量 embed 前先查缓存，仅对未缓存文本调用 API

### 3.4 可测试性 [T] — 6.5 → 8.0

#### T3: Chat 页面核心测试
- **新增**: `src/pages/__tests__/Chat.test.tsx`（或 `src/components/__tests__/ChatWidget.test.tsx`）
- **内容**: 发送消息、SSE 流式接收、错误状态、空状态

#### T4: query_router 单元测试
- **新增**: `backend/tests/test_query_router.py`
- **内容**: 规则分类路径、LLM 分类路径、超时降级路径

#### T5: E2E 对话流测试
- **修改**: `tests/e2e/chat.spec.ts`
- **内容**: Mock SSE 响应，测试完整对话流程（输入 → 发送 → 流式显示 → 完成）
- **来源**: Playwright Mock APIs 文档

#### T6: 后端 coverage 阈值
- **文件**: `backend/pyproject.toml`
- **修改**: `[tool.coverage.report] fail_under = 80`

### 3.5 可维护性 [M] — 7.0 → 8.5

#### M4: Dashboard.tsx 拆分
- **文件**: `src/pages/Dashboard.tsx`（722 行 → ~100 行容器 + 4-5 子组件）
- **拆分**:
  - `DashboardStatsGrid.tsx` — 统计卡片网格
  - `DashboardRecentActivity.tsx` — 最近活动
  - `DashboardCharts.tsx` — 图表区域
  - `DashboardHeader.tsx` — 标题和操作
- **来源**: React "Thinking in React" — 单一职责

#### M5: useDebouncedLocalStorage Hook 提取
- **新增**: `src/hooks/useDebouncedLocalStorage.ts`
- **替换**: Dashboard.tsx 中 3 处重复的 debounce 模式

#### M6: System Prompt 模板化
- **文件**: `backend/app/agent/agent.py:16-76`
- **修改**: 中英文提示词提取为 `backend/app/prompts/` 模块
- **模式**: `ChatPromptTemplate` + 语言变量替代硬编码
- **来源**: LangChain PromptTemplate 文档

### 3.6 鲁棒性 [RB] — 7.0 → 8.5

#### RB3: 熔断器重写
- **文件**: `backend/app/reliability/circuit_breaker.py`
- **修改要点**:
  1. HALF_OPEN 使用 `asyncio.Semaphore(3)` 限制并发探针
  2. 连续 `success_threshold=3` 次成功后才切换到 CLOSED
  3. `state` 属性改为纯读取，状态转换移入显式 `transition()` 方法
  4. 添加时间窗口重置失败计数器
- **来源**: Microsoft Circuit Breaker Pattern

#### RB4: Redis 连接健康检查
- **文件**: `backend/app/cache/connection.py`
- **修改**: `ConnectionPool.from_url()` 添加 `health_check_interval=30`

### 3.7 可扩展性 [EX] — 8.0 → 9.0

#### EX3: FastAPI 依赖注入升级
- **修改**: 关键服务通过 `Annotated[Service, Depends(get_service)]` 注入
- **模式**: `@lru_cache` Settings 单例 + `app.state` 服务注册 + 层级依赖链
- **来源**: FastAPI Dependencies 官方文档

#### EX4: 权限边界强制
- **文件**: `backend/app/security/roles_router.py:115`
- **修改**: `update_role_permissions` 添加上限约束 — `new_role <= requesting_user.role`

---

## 四、Phase 3：Architecture（2-3 月）

**目标**：架构级改造，加权分从 8.5 → 9.3

### 4.1 安全性 [S] — 8.5 → 9.5

#### S10: Fernet 密钥轮换（MultiFernet）
- **文件**: `backend/app/security/encryption.py`
- **修改**: `Fernet(key)` → `MultiFernet([Fernet(new_key), Fernet(old_key)])`
- **新增**: `rotate_token()` 方法批量迁移历史数据
- **来源**: cryptography.io 官方文档

#### S11: JWT Token 吊销（Redis denylist）
- **新增**: `backend/app/security/token_revocation.py`
- **模式**: `jti` claim + Redis `SET revoked:{jti} EX {ttl}`
- **来源**: OWASP REST Security Cheat Sheet

#### S12: CSP Nonce-based Strict Policy
- **修改**: 每个请求生成随机 nonce，注入到 CSP header 和 script 标签
- **来源**: Google Web.dev Strict CSP 指南

### 4.2 代码健壮性 [R] — 8.5 → 9.0

#### R7: asyncio.TaskGroup 替代 gather
- **全局搜索**: `asyncio.gather(*tasks)`
- **修改**: 有依赖的用 `asyncio.TaskGroup()`，无依赖的保留 `gather`
- **来源**: Python 3.11+ 官方文档

### 4.3 可测试性 [T] — 8.0 → 9.0

#### T7: Qdrant 集成测试
- **新增**: `backend/tests/integration/test_qdrant_integration.py`
- **方式**: `testcontainers.QdrantContainer("qdrant/qdrant:v1.12.0")`
- **覆盖**: 向量索引、hybrid search、scroll、payload 过滤
- **来源**: Testcontainers 官方文档

#### T8: 前端组件库测试
- **目录**: `src/components/ui/__tests__/`
- **覆盖**: Button, Card, Badge, Tabs, DataTable, MetricCard, ProgressBar

### 4.4 可维护性 [M] — 8.5 → 9.0

#### M7: 事件总线
- **新增**: `backend/app/events/bus.py`
- **模式**: `EventBus.on(event, handler)` + `EventBus.emit(event, data)`
- **事件**: `chat.completed`, `document.indexed`, `user.login`

#### M8: API 版本管理
- **修改**: `backend/app/main.py` — `/api/v1/` 前缀路由
- **策略**: URL 路径版本控制（最清晰）

### 4.5 鲁棒性 [RB] — 8.5 → 9.0

#### RB5: Bulkhead 隔舱模式
- **新增**: `backend/app/reliability/bulkhead.py`
- **模式**: 每个外部依赖（Redis/Qdrant/LLM）独立 Semaphore 池
- **来源**: Microsoft Bulkhead Pattern

#### RB6: 超时级联
- **新增**: `backend/app/reliability/timeouts.py`
- **配置**: API 60s > Agent 45s > LLM 30s > RAG 10s > Qdrant 5s

### 4.6 可观测性 [OB] — 8.5 → 9.5

#### OB3: OpenTelemetry 集成
- **新增**: `backend/app/observability/otel.py`
- **自动插桩**: `FastAPIInstrumentor`, `RedisInstrumentor`
- **LangFuse 作为 OTel 后端**: 通过 `LangfuseSpanProcessor`
- **来源**: OpenTelemetry Python SDK 文档

#### OB4: SLO 基于告警
- **新增**: `prometheus/alert_rules.yml`
- **SLI**: 请求成功率 99.9%, P99 延迟 < 2s
- **告警**: Burn Rate 多窗口告警
- **来源**: Google SRE Book

### 4.7 可移植性 [PO] — 8.5 → 9.5

#### PO3: Gunicorn + Uvicorn Workers
- **修改**: Dockerfile CMD 改为 `gunicorn app.main:app --worker-class uvicorn.workers.UvicornWorker --workers 2`
- **来源**: uvicorn 生产部署文档

#### PO4: Distroless Docker 镜像
- **修改**: 运行时阶段从 `python:3.12-slim` → `gcr.io/distroless/python3-debian12`
- **收益**: 基础层从 ~150MB → ~50MB

---

## 五、Phase 4：Polish（3-6 月）

**目标**：深度优化和打磨，加权分从 9.3 → 9.8

### 5.1 可测试性 [T] — 9.0 → 10

#### T9: Contract Testing（Pact）
- **新增**: `tests/contract/`
- **覆盖**: 前后端 API 契约验证

#### T10: Visual Regression Testing
- **修改**: Playwright 配置添加 `toHaveScreenshot()` 视觉对比
- **覆盖**: Landing, Dashboard, Chat, Search 关键页面

### 5.2 性能 [P] — 9.5 → 10

#### P8: Vite 6 Rolldown 优化
- **修改**: `vite.config.ts` 使用 `rolldownOptions` 精细控制 chunk splitting
- **来源**: Vite 6 官方文档

#### P9: React Compiler 集成
- **修改**: 安装 `vite-plugin-react-compiler`，自动记忆化优化
- **来源**: React 19 官方文档

### 5.3 鲁棒性 [RB] — 9.0 → 10

#### RB7: Chaos Engineering
- **新增**: `backend/app/reliability/chaos.py`
- **模式**: 测试环境注入随机延迟和失败
- **来源**: Netflix Chaos Monkey 原则

### 5.4 可观测性 [OB] — 9.5 → 10

#### OB5: 全链路 Trace 传播
- **修改**: `trace_id` 贯穿前端 → Nginx → uvicorn → LLM API → Redis → Qdrant
- **方式**: W3C Trace Context header 传播

---

## 六、验证计划

每个 Phase 完成后的验证步骤：

### 后端验证
```bash
cd backend && python -m pytest tests/ -v          # 全量单元测试
cd backend && python -m ruff check tests/ app/    # Lint
cd backend && python -m pytest tests/ --cov=app --cov-report=term-missing  # Coverage
```

### 前端验证
```bash
npm test -- --run                                  # Vitest
npm run build                                      # Build 验证
npx playwright test                                # E2E
```

### 安全验证
```bash
cd backend && pip-audit --strict                   # 依赖漏洞
trivy image aureon:latest                          # 镜像漏洞
```

### 生产验证
```bash
curl -s https://aureon-production-659a.up.railway.app/api/health | jq .
```

---

## 七、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| httpx 迁移破坏现有 API 调用 | 高 | 先写集成测试，再迁移 |
| 线程安全改动引入死锁 | 中 | 使用 `asyncio.Lock`（非 `threading.Lock`）在 async 路径 |
| 前端组件拆分破坏样式 | 中 | 每个拆分单独 PR，视觉回归测试 |
| CSP 过于严格阻断功能 | 中 | 先用 `Content-Security-Policy-Report-Only` 观察 |
| Qdrant 集成测试 Docker 依赖 | 低 | CI 环境需要 Docker，用 Testcontainers |

---

## 八、参考文献

### 安全性
- OWASP Top 10 (2025): https://owasp.org/Top10/
- OWASP LLM Top 10: https://genai.owasp.org/llm-top-10/
- OWASP CSP Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html
- Python hmac: https://docs.python.org/3/library/hmac.html
- cryptography.io Fernet: https://cryptography.io/en/latest/fernet/

### 性能
- Redis Distributed Locks: https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/
- httpx Clients: https://www.python-httpx.org/advanced/clients/
- cachetools: https://cachetools.readthedocs.io/en/latest/
- NumPy: https://numpy.org/doc/

### 鲁棒性
- Microsoft Circuit Breaker: https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker
- Microsoft Bulkhead: https://learn.microsoft.com/en-us/azure/architecture/patterns/bulkhead
- Microsoft Retry: https://learn.microsoft.com/en-us/azure/architecture/patterns/retry

### 可观测性
- LangFuse SDK: https://langfuse.com/integrations/frameworks/langchain
- OpenTelemetry Python: https://opentelemetry.io/docs/languages/python/
- Prometheus Histogram: https://prometheus.io/docs/practices/histograms/
- Google SRE: https://sre.google/workbook/alerting-on-slos/

### 可测试性
- pytest-asyncio: https://pytest-asyncio.readthedocs.io/
- Testcontainers: https://testcontainers.com/
- Playwright Mock: https://playwright.dev/docs/mock
- Zustand Testing: https://zustand.docs.pmnd.rs/guides/testing

### 可维护性
- PEP 621: https://peps.python.org/pep-0621/
- FastAPI Dependencies: https://fastapi.tiangolo.com/tutorial/dependencies/
- LangChain PromptTemplate: https://docs.langchain.com/
- React "Thinking in React": https://react.dev/learn/thinking-in-react

### 可移植性
- FastAPI Docker: https://fastapi.tiangolo.com/deployment/docker/
- 12-Factor App: https://12factor.net/
- uvicorn Deployment: https://uvicorn.dev/
