# Aureon 全栈性能优化与架构重构设计

> 日期: 2026-06-21
> 状态: 已批准
> 范围: 前端性能 + 后端性能 + 架构整洁 + 监控增强

## 背景

Aureon 平台经过快速迭代，积累了以下技术债务：
- 前端存在 3 对重复实现（chat hook、analytics hook、cost hook）
- WebSocket `/ws/dashboard` 被多处重复连接
- 后端缓存模块膨胀（semantic_cache.py 707 行）
- SSE 流 analytics 在高频 chunk 场景下存在不必要的 JSON 解析开销
- Nginx 配置缺少压缩和缓存优化

本设计文档规划了一次全面重构，分 3 个阶段实施，目标是在保持所有功能不变的前提下提升性能和可维护性。

## Phase 1：快速胜利（低风险，可独立部署）

### Task 1.1：删除重复 Hooks，统一数据获取层

**删除文件：**
- `src/hooks/useChat.ts` → 统一使用 `src/stores/useChatStore.ts`
- `src/hooks/useAnalytics.ts` → 统一使用 `src/hooks/useAnalyticsData.ts`
- `src/hooks/useCostData.ts` → 统一使用 `src/hooks/useCostDataQuery.ts`

**修改文件：**
- `src/pages/Search.tsx`：从 `useChat` 迁移到 `useChatStore`
- `src/pages/Analytics.tsx`：从 `useAnalytics` 迁移到 `useAnalyticsData`
- `src/pages/CostGovernance.tsx`：从 `useCostData` 迁移到 `useCostDataQuery`
- 其他引用旧 hook 的组件

### Task 1.2：useChatStore 加入 SSE 缓冲

**问题**：当前 Zustand 版每个 SSE text chunk 都触发 `set()` → 全量重渲染。

**方案**：将 `useSSEBuffer` 的缓冲逻辑内置到 store 中：
- Store 内部持有 `bufferRef` + `timerRef`
- `text` 事件追加到 buffer，60ms debounce 后 flush
- `tool_start`/`tool_end`/`sources`/`done` 事件立即 flush
- 仅在 flush 时调用 `set({ messages })`

**文件**：`src/stores/useChatStore.ts`

### Task 1.3：WebSocket 连接去重

**问题**：`RealtimeMetricsProvider`（App 根级）和 `useCostData`（成本页面）各自独立创建 `/ws/dashboard` 连接。

**方案**：
- 从 `useCostData.ts` 中删除 WebSocket 连接代码
- `useCostDataQuery` 不需要 WS（TanStack Query 轮询已足够）
- 如需实时成本推送，从 `RealtimeMetricsContext` 获取

**目标**：全 App 最多 2 个 WS 连接（`/ws/dashboard` 全局 + `/ws/chat/{id}` 按需）

### Task 1.4：Nginx 压缩与缓存优化

**文件**：`nginx.conf`

**改动**：
```nginx
gzip_comp_level 6;
gzip_min_length 256;
gzip_vary on;

# 静态资源增强缓存
location /assets/ {
    expires 1y;
    add_header Cache-Control "public, immutable, stale-while-revalidate=86400";
}

# API 路由：移除非 WS 请求的 Connection: upgrade
location /api/ {
    proxy_set_header Connection '';
    proxy_http_version 1.1;
    proxy_buffering off;
    proxy_read_timeout 86400s;
}
```

### Task 1.5：Vite Bundle 拆分优化

**文件**：`vite.config.ts`

**改动**：在 `manualChunks` 中新增 TanStack Query 和 Zustand 独立 chunk：
```typescript
if (id.includes('@tanstack')) return 'vendor-query';
if (id.includes('zustand')) return 'vendor-zustand';
```

### Task 1.6：Vite Brotli 预压缩

**文件**：`vite.config.ts`

**改动**：在 `compression` 插件中添加 brotli：
```typescript
compression({ algorithm: 'gzip', threshold: 1024 }),
compression({ algorithm: 'brotliCompress', threshold: 1024 }),
```

### Task 1.7：CSS 瘦身

**文件**：`src/index.css`

**改动**：
- 删除重复的 `.linear-card` 定义（第 88-97 行 vs 第 405-411 行）
- 删除重复的 `.feature-card` hover 定义
- 合并重复的 `.metric-card` 定义

## Phase 2：架构重构（中风险，需测试回归）

### Task 2.1：缓存模块拆分

**目标**：将 `semantic_cache.py`（707 行）和 `redis_client.py`（545 行）拆分为职责清晰的模块。

**新结构**：
```
backend/app/cache/
├── __init__.py          # 公共 API (get_cached_with_semantic, set_cached_with_semantic)
├── connection.py        # Redis 连接管理 (async + sync, ~150 行)
├── exact_cache.py       # 精确匹配 (token bag hash + memory + Redis, ~150 行)
├── semantic_cache.py    # 语义缓存 (向量相似度, ~200 行)
└── metrics.py           # 缓存指标收集 (~80 行)
```

### Task 2.2：SSE Analytics 轻量化

**文件**：`backend/app/routers/chat.py`

**当前**：每个 SSE chunk 做 `json.loads` 解析。
**目标**：只在 `sources` 事件（低频）做 JSON 解析，text 事件只计字节数。

### Task 2.3：Repository 安全修复

**文件**：`backend/app/database/repositories.py`

**修复**：`UserRepository.update()` 中 f-string SQL 列名拼接 → 白名单验证。

```python
_ALLOWED_UPDATE_FIELDS = {"name", "email", "role", "is_active", "password_hash"}

async def update(user_id: int, **fields) -> bool:
    safe_fields = {k: v for k, v in fields.items() if k in _ALLOWED_UPDATE_FIELDS}
    if not safe_fields:
        return False
    # ... parameterized query with validated column names
```

### Task 2.4：fire_and_forget 增强

**新建文件**：`backend/app/common_tasks.py`

**方案**：创建 `resilient_task` 装饰器，支持瞬态错误重试：

```python
async def resilient_fire_and_forget(coro, max_retries=2, retry_delay=1.0, name="task"):
    """Execute async task with retry on transient failures."""
    async def _run():
        for attempt in range(max_retries + 1):
            try:
                await coro
                return
            except (ConnectionError, TimeoutError, OSError) as e:
                if attempt < max_retries:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                logger.warning("task_exhausted_retries", task=name, error=str(e))
            except Exception as e:
                logger.error("task_unexpected_error", task=name, error=str(e))
                return
    asyncio.create_task(_run())
```

**修改文件**：`chat.py`、`rag_stats.py`、`metrics_collector.py`（替换 `fire_and_forget` → `resilient_fire_and_forget`）

### Task 2.5：CSS 暗色主题迁移

**目标**：消除 `index.css` 中 ~50 行 `!important` 全局覆盖。

**方案**：
- 将 `bg-white`、`text-gray-*` 等 Tailwind 类的暗色覆盖迁移到 Tailwind CSS 4 的 `@theme` 指令
- 使用 Tailwind 的 `dark:` variant 或自定义 utility 类替代 `!important`

**影响范围**：需要检查所有使用了标准 Tailwind 色值类名的组件。

## Phase 3：性能深水区（中风险，需性能测试验证）

### Task 3.1：Prometheus 指标增强

**文件**：`backend/app/observability/` + `backend/app/cache/metrics.py`

**新增指标**：
- `cache_lookups_total` (Counter, labels: type=exact/semantic/miss)
- `cache_latency_seconds` (Histogram, labels: type)
- `db_pool_size` / `db_pool_idle` (Gauge)
- `sse_chunks_per_response` (Histogram)
- `ws_active_connections` (Gauge, labels: type=chat/dashboard)

### Task 3.2：DB 连接池监控与优化

**文件**：`backend/app/database/connection.py`

- 暴露 pool stats 到 Prometheus
- 添加 slow query 日志（`>1s` 的查询记录 warning）
- `command_timeout` 从 30s 调整为 60s（适应大 RAG 查询）

### Task 3.3：Schema 版本控制

**文件**：`backend/app/database/`

**方案**：添加 `schema_version` 表，migration 文件按版本号管理：
```sql
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT NOW()
);
```

每次启动检查当前版本，仅执行未应用的 migration。

### Task 3.4：docker-compose 精简

**评估**：如果 Elasticsearch 仅作为 BM25 后端且已被 Qdrant 稀疏向量替代，从 docker-compose.yml 中移除 ES 服务，节省 ~512MB 内存。

**前提**：确认 `BM25_BACKEND=elasticsearch` 是否仍在生产中使用。

## 成功标准

| 指标 | 当前 | 目标 |
|------|------|------|
| 首屏 gzip JS | ~164 KB | ~140 KB |
| WebSocket 连接数（全 App） | 3+ | ≤2 |
| 重复 hook 实现 | 3 对 | 0 |
| semantic_cache.py 行数 | 707 | ≤250/模块 |
| SSE analytics 开销 | json.loads/chunk | 仅 sources 解析 |
| Nginx gzip 压缩率 | level 1 | level 6 |

## 风险与回滚

- 每阶段独立 PR，独立部署
- 前端重构通过 793 个后端测试 + 74 个前端测试回归验证
- 缓存模块拆分后保持相同的公共 API（`get_cached_with_semantic` / `set_cached_with_semantic`）
- Nginx 配置变更可通过 `nginx -t` 预验证
- 回滚策略：git revert 单阶段 PR

## 依据来源

- FastAPI StreamingResponse: https://www.starlette.io/responses/#streamingresponse
- OWASP SQL Injection Prevention: https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html
- nginx gzip: https://nginx.org/en/docs/http/ngx_http_gzip_module.html
- React Server State: https://react.dev/learn/managing-state
- TanStack Query: https://tanstack.com/query/latest/docs/react/overview
- Zustand: https://github.com/pmndrs/zustand
- Google Python Style Guide (module size): https://google.github.io/styleguide/pyguide.html
