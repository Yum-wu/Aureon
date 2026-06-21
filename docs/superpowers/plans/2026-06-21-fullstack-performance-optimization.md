# Aureon 全栈性能优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除前端重复实现、优化构建产物、重构后端缓存模块、修复安全隐患、增强可观测性。

**Architecture:** 分 3 阶段推进：Phase 1 快速胜利（前端去重 + nginx + Vite），Phase 2 架构重构（缓存拆分 + SSE 优化 + SQL 安全），Phase 3 性能深水区（Prometheus + DB 连接池 + Schema 版本控制）。每阶段独立可部署，独立回归测试。

**Tech Stack:** React 19 + Zustand + TanStack Query + Vite 8 + FastAPI + asyncpg + Redis + nginx

---

## File Structure

### Phase 1 — 删除的文件
| 文件 | 原因 |
|------|------|
| `src/hooks/useChat.ts` | 与 `useChatStore.ts` 重复，唯一消费者 `ChatWindow.tsx` 迁移到 store |
| `src/components/ChatWindow.tsx` | 唯一消费者是 `Search.tsx`，但 `Search.tsx` 已使用独立 RAG 流（`streamRAGQuery`），不再需要 ChatWindow |
| `src/hooks/useAnalytics.ts` | 死代码：唯一 import 来自自身测试文件，页面已使用 `useAnalyticsData` |
| `src/hooks/__tests__/useAnalytics.test.ts` | 随旧 hook 一起删除 |
| `src/hooks/useCostData.ts` | 死代码：无页面 import，CostGovernance 已使用 `useCostDataQuery`；且包含重复 `/ws/dashboard` WS 连接 |

### Phase 1 — 修改的文件
| 文件 | 改动 |
|------|------|
| `src/stores/useChatStore.ts` | 内置 SSE buffer（60ms debounce） |
| `src/stores/index.ts` | 移除 `useChat` 相关 export（如有） |
| `src/hooks/useSSEBuffer.ts` | 保留（其他组件可能复用），从 useChatStore 内部复制逻辑 |
| `nginx.conf` | gzip_comp_level, stale-while-revalidate, API Connection header |
| `vite.config.ts` | manualChunks 新增 vendor-query + vendor-zustand，Brotli 预压缩 |
| `src/index.css` | 删除重复 `.linear-card`、`.feature-card` 定义 |

### Phase 2 — 新建/修改的文件
| 文件 | 说明 |
|------|------|
| `backend/app/cache/connection.py` | 新建：Redis 连接管理（async + sync） |
| `backend/app/cache/exact_cache.py` | 新建：精确匹配缓存 |
| `backend/app/cache/metrics.py` | 新建：缓存指标收集 |
| `backend/app/cache/redis_client.py` | 精简：仅保留公共 API 代理 |
| `backend/app/cache/semantic_cache.py` | 精简：仅语义缓存逻辑 |
| `backend/app/routers/chat.py` | SSE analytics 轻量化 |
| `backend/app/database/repositories.py` | SQL 列名白名单 |
| `backend/app/common.py` | 新增 `resilient_fire_and_forget` |

---

## Phase 1：快速胜利

### Task 1: 删除死代码 Hooks + ChatWindow 迁移

**Files:**
- Delete: `src/hooks/useAnalytics.ts`
- Delete: `src/hooks/__tests__/useAnalytics.test.ts`
- Delete: `src/hooks/useCostData.ts`
- Delete: `src/hooks/useChat.ts`
- Delete: `src/components/ChatWindow.tsx`
- Modify: `src/stores/index.ts`

- [ ] **Step 1: 确认死代码 — 验证无外部 import**

Run:
```bash
cd c:/Users/Yum/Desktop/Aureon-test
grep -r "from.*useAnalytics['\"]" src/ --include="*.ts" --include="*.tsx" | grep -v "useAnalyticsData" | grep -v "__tests__"
grep -r "from.*useCostData['\"]" src/ --include="*.ts" --include="*.tsx" | grep -v "useCostDataQuery"
grep -r "from.*useChat['\"]" src/ --include="*.ts" --include="*.tsx" | grep -v "useChatStore"
grep -r "from.*ChatWindow" src/ --include="*.ts" --include="*.tsx"
```
Expected: 所有 grep 返回空（无结果）

- [ ] **Step 2: 检查 stores/index.ts 中是否有旧 hook 的 re-export**

```bash
grep -n "useChat\b" src/stores/index.ts
```
如果有 re-export，移除相关行。

- [ ] **Step 3: 删除文件**

```bash
git rm src/hooks/useAnalytics.ts
git rm src/hooks/__tests__/useAnalytics.test.ts
git rm src/hooks/useCostData.ts
git rm src/hooks/useChat.ts
git rm src/components/ChatWindow.tsx
```

- [ ] **Step 4: 修复 stores/index.ts（如需要）**

如果 `src/stores/index.ts` 中有 `useChat` 的 re-export，删除该行。

- [ ] **Step 5: 运行前端测试验证无破坏**

```bash
npm test -- --run
```
Expected: 所有测试 PASS

- [ ] **Step 6: 运行前端构建验证**

```bash
npm run build
```
Expected: 构建成功，无 import 错误

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: remove dead hooks (useChat, useAnalytics, useCostData) and ChatWindow"
```

---

### Task 2: useChatStore 内置 SSE 缓冲

**Files:**
- Modify: `src/stores/useChatStore.ts`

- [ ] **Step 1: 在 useChatStore 中添加 SSE 缓冲逻辑**

将以下 SSE buffer 逻辑内置到 store 内部（从 `useSSEBuffer.ts` 提取核心算法，但脱离 React hook 环境）：

在 `useChatStore.ts` 顶部（`create()` 之前）添加：

```typescript
// ── SSE Text Buffer (60ms debounce, 减少高频 set() 调用) ──
const SSE_FLUSH_INTERVAL = 60;
let _textBuffer = "";
let _flushTimer: ReturnType<typeof setTimeout> | null = null;
let _currentAssistantId = "";

function _flushBuffer(set: (fn: (state: ChatState) => Partial<ChatState>) => void) {
  if (_flushTimer) {
    clearTimeout(_flushTimer);
    _flushTimer = null;
  }
  if (!_textBuffer) return;
  const text = _textBuffer;
  _textBuffer = "";
  const aid = _currentAssistantId;
  set((state) => {
    const messages = [...state.messages];
    const last = messages[messages.length - 1];
    if (last && last.role === "assistant" && last.id === aid) {
      messages[messages.length - 1] = { ...last, content: last.content + text };
    }
    return { messages };
  });
}

function _scheduleFlush(set: (fn: (state: ChatState) => Partial<ChatState>) => void) {
  if (_flushTimer) return;
  _flushTimer = setTimeout(() => {
    _flushTimer = null;
    _flushBuffer(set);
  }, SSE_FLUSH_INTERVAL);
}

function _appendText(chunk: string, set: (fn: (state: ChatState) => Partial<ChatState>) => void) {
  _textBuffer += chunk;
  _scheduleFlush(set);
}
```

- [ ] **Step 2: 修改 handleEvent 中的 text 事件处理**

将 `case "text"` 中的直接 `set()` 替换为 `_appendText(chunk, set)`：

```typescript
case "text": {
  const chunk = event.content as string;
  _appendText(chunk, set);
  break;
}
```

- [ ] **Step 3: 在 tool_start/tool_end/sources/intent/error 事件处理前添加 flushNow**

在每个非 text 事件 case 的开头添加 `_flushBuffer(set);`，确保缓冲区内容在状态变化前被提交：

```typescript
case "tool_start":
case "tool_end": {
  _flushBuffer(set);
  // ... 原有逻辑
}

case "sources": {
  _flushBuffer(set);
  // ... 原有逻辑
}

case "intent": {
  _flushBuffer(set);
  // ... 原有逻辑
}

case "error": {
  _flushBuffer(set);
  // ... 原有逻辑
}
```

- [ ] **Step 4: 在 sendMessage 结束和 stopGeneration/clearChat 中 flush**

在 `sendMessage` 的 `streamEnhancedChat` 调用后：
```typescript
_flushBuffer(set);
```

在 `stopGeneration` 和 `clearChat` 开头也添加 `_flushBuffer(set);`。

- [ ] **Step 5: 运行前端测试**

```bash
npm test -- --run
```
Expected: 所有测试 PASS

- [ ] **Step 6: Commit**

```bash
git add src/stores/useChatStore.ts
git commit -m "perf: add 60ms SSE debounce buffer to useChatStore"
```

---

### Task 3: Nginx 压缩与缓存优化

**Files:**
- Modify: `nginx.conf`

- [ ] **Step 1: 更新 gzip 配置**

将 `nginx.conf` 中第 17-19 行的 gzip 配置替换为：

```nginx
    # Gzip 压缩优化
    gzip on;
    gzip_comp_level 6;
    gzip_min_length 256;
    gzip_vary on;
    gzip_proxied any;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript application/xml+rss image/svg+xml;
```

- [ ] **Step 2: 更新静态资源缓存 — 添加 stale-while-revalidate**

将 `location /assets/` 块替换为：

```nginx
    # 静态资源缓存（1 年不可变 + stale-while-revalidate 容错）
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable, stale-while-revalidate=86400";
    }
```

- [ ] **Step 3: 修复 API 路由的 Connection header**

将 `location /api/` 块中的：
```nginx
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_cache_bypass $http_upgrade;
```

替换为：
```nginx
        proxy_set_header Connection '';
```

说明：API 路由主要是 HTTP/SSE 请求，不是 WebSocket。`Connection: upgrade` 只对 WS 有意义，对普通 HTTP 请求设置它会违反 RFC 7230。WS 连接由独立的 `/ws/` location 块处理。

- [ ] **Step 4: 验证 nginx 配置语法（需要 nginx 环境，可选）**

```bash
# 如果有 Docker 环境
docker run --rm -v $(pwd)/nginx.conf:/etc/nginx/conf.d/default.conf:ro nginx:alpine nginx -t
```

- [ ] **Step 5: Commit**

```bash
git add nginx.conf
git commit -m "perf(nginx): gzip level 6, stale-while-revalidate, fix API Connection header"
```

---

### Task 4: Vite Bundle 拆分优化 + Brotli 预压缩

**Files:**
- Modify: `vite.config.ts`

- [ ] **Step 1: 安装 vite-plugin-compression2 的 brotli 支持（已在 deps 中）**

确认 `vite-plugin-compression2` 已安装（当前已使用 gzip）。

- [ ] **Step 2: 更新 vite.config.ts**

将 `vite.config.ts` 完整替换为：

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { compression } from 'vite-plugin-compression2'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    compression({
      algorithm: 'gzip',
      threshold: 1024,
      deleteOriginalAssets: false,
    }),
    compression({
      algorithm: 'brotliCompress',
      threshold: 1024,
      deleteOriginalAssets: false,
    }),
  ],
  server: {
    host: '0.0.0.0',
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes('node_modules/react-dom') || id.includes('node_modules/react/')) {
            return 'vendor-react';
          }
          if (id.includes('node_modules/react-router-dom')) {
            return 'vendor-router';
          }
          if (id.includes('node_modules/i18next') || id.includes('node_modules/react-i18next')) {
            return 'vendor-i18n';
          }
          if (id.includes('node_modules/react-markdown') || id.includes('node_modules/remark-gfm') || id.includes('node_modules/react-syntax-highlighter') || id.includes('node_modules/unified') || id.includes('node_modules/remark-') || id.includes('node_modules/rehype-') || id.includes('node_modules/mdast-') || id.includes('node_modules/hast-')) {
            return 'vendor-md';
          }
          if (id.includes('node_modules/@nivo')) {
            return 'vendor-nivo';
          }
          if (id.includes('node_modules/@tanstack')) {
            return 'vendor-query';
          }
          if (id.includes('node_modules/zustand')) {
            return 'vendor-zustand';
          }
        },
      },
    },
    cssCodeSplit: true,
    chunkSizeWarningLimit: 100,
  },
})
```

- [ ] **Step 3: 运行构建并比较 chunk 大小**

```bash
npx vite build --mode production 2>&1 | grep -E "dist/assets/.*\.(js|css)"
```

验证新增 `vendor-query.*.js` 和 `vendor-zustand.*.js` chunk，且 `index.js` 大小减小。

- [ ] **Step 4: Commit**

```bash
git add vite.config.ts
git commit -m "perf(vite): add TanStack Query + Zustand chunks, enable Brotli precompress"
```

---

### Task 5: CSS 瘦身 — 删除重复定义

**Files:**
- Modify: `src/index.css`

- [ ] **Step 1: 合并重复的 .linear-card 定义**

`index.css` 中有两处 `.linear-card` 定义：
- 第 88-97 行：基础定义（完整样式）
- 第 405-411 行：覆盖定义（部分样式覆盖）

将第 401-411 行的 "Enhanced Card Hover" section 删除，因为第 88-97 行已包含完整的 `.linear-card` 定义。

删除以下代码块（第 401-411 行）：
```css
/* ══════════════════════════════════════
   Enhanced Card Hover
   ══════════════════════════════════════ */

.linear-card {
  transition: border-color 0.25s ease, box-shadow 0.25s ease, transform 0.25s ease, background 0.25s ease;
}
.linear-card:hover {
  border-color: rgba(94, 106, 210, 0.15);
  box-shadow: 0 0 0 1px rgba(94, 106, 210, 0.08), 0 8px 32px rgba(0, 0, 0, 0.3), 0 0 60px rgba(94, 106, 210, 0.04);
}
```

然后更新第 88-97 行的 `.linear-card` 基础定义，合并增强 hover 效果：

```css
/* ── Card — with visible elevation ── */
.linear-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  transition: border-color 0.25s ease, box-shadow 0.25s ease, transform 0.25s ease, background 0.25s ease;
}
.linear-card:hover {
  border-color: rgba(94, 106, 210, 0.15);
  box-shadow: 0 0 0 1px rgba(94, 106, 210, 0.08), 0 8px 32px rgba(0, 0, 0, 0.3), 0 0 60px rgba(94, 106, 210, 0.04);
}
```

- [ ] **Step 2: 删除重复的 .feature-card hover 定义**

同样，第 100-119 行有基础 `.feature-card` 定义，第 413-420 行有覆盖定义。合并到第 100-119 行，删除第 413-420 行。

更新第 100-119 行的 `.feature-card`：

```css
.feature-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 24px;
  transition: border-color 0.25s ease, transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.25s ease;
  position: relative;
  overflow: hidden;
}
.feature-card:hover {
  border-color: var(--accent-200);
  transform: translateY(-3px);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.35), 0 0 48px var(--accent-50);
}
```

注意：保留 `.feature-card::before` 定义（它在第 109-119 行左右）。

- [ ] **Step 3: 运行前端测试和构建验证**

```bash
npm test -- --run && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add src/index.css
git commit -m "style: consolidate duplicate card CSS definitions"
```

---

## Phase 2：架构重构

### Task 6: 缓存模块拆分 — Redis 连接管理

**Files:**
- Create: `backend/app/cache/connection.py`
- Modify: `backend/app/cache/redis_client.py`（后续 Task 中精简）

- [ ] **Step 1: 创建 connection.py**

从 `redis_client.py` 中提取 Redis 连接管理逻辑到 `backend/app/cache/connection.py`：

```python
"""Redis connection management — async + sync clients with reconnection.

Extracted from redis_client.py for single-responsibility.
"""
import structlog
from typing import Optional

logger = structlog.get_logger()

# ── Async Redis client singleton ──
_redis = None

# ── Sync Redis connection pool ──
_sync_redis_pool = None
_sync_redis_fail_count = 0
_SYNC_RECONNECT_AFTER = 5


def get_async_redis():
    """Return async Redis client singleton, or None if unavailable.

    Retries on every call when previously unavailable (Redis may start
    after app, e.g. Railway deploy).
    """
    global _redis
    if _redis is not None:
        return _redis
    from app.config import settings
    if not settings.redis_url:
        return None
    try:
        import redis.asyncio as aioredis
        _redis = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        logger.info("Async Redis connected")
    except Exception as e:
        logger.warning("Async Redis unavailable (non-fatal): %s", e)
        _redis = None
    return _redis


def get_sync_redis():
    """Return sync Redis client singleton for background threads.

    Uses ConnectionPool for TCP connection reuse.
    Thread-safe: redis-py's Redis + ConnectionPool is thread-safe.
    """
    global _sync_redis_pool, _sync_redis_fail_count
    if _sync_redis_pool is not None:
        return _sync_redis_pool
    if _sync_redis_fail_count >= _SYNC_RECONNECT_AFTER:
        return None
    from app.config import settings
    if not settings.redis_url:
        _sync_redis_fail_count += 1
        return None
    try:
        import redis as redis_sync
        pool = redis_sync.ConnectionPool.from_url(
            settings.redis_url,
            decode_responses=False,
            socket_connect_timeout=2,
            socket_timeout=2,
            max_connections=10,
        )
        _sync_redis_pool = redis_sync.Redis(connection_pool=pool)
        _sync_redis_fail_count = 0
        logger.info("Sync Redis connected (connection pool, max_connections=10)")
    except Exception as e:
        _sync_redis_fail_count += 1
        if _sync_redis_fail_count <= 3 or _sync_redis_fail_count % 100 == 0:
            logger.warning("Sync Redis unavailable (fail #%d): %s", _sync_redis_fail_count, e)
    return _sync_redis_pool


def close_sync_redis():
    """Close sync Redis pool, called during app shutdown."""
    global _sync_redis_pool
    if _sync_redis_pool is not None:
        try:
            _sync_redis_pool.connection_pool.disconnect()
        except Exception as e:
            logger.debug("redis_pool_disconnect_failed", error=str(e))
        _sync_redis_pool = None


def close_async_redis():
    """Reset async Redis client, called during app shutdown."""
    global _redis
    _redis = None
```

- [ ] **Step 2: 运行后端测试验证 import 兼容**

```bash
cd backend && python -m pytest tests/ -v -k "cache or redis" --timeout=30
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/cache/connection.py
git commit -m "refactor(cache): extract Redis connection management to connection.py"
```

---

### Task 7: 缓存模块拆分 — 精确缓存 + 指标

**Files:**
- Create: `backend/app/cache/exact_cache.py`
- Create: `backend/app/cache/metrics.py`

- [ ] **Step 1: 创建 metrics.py**

从 `redis_client.py` 提取缓存指标收集到 `backend/app/cache/metrics.py`：

```python
"""Cache metrics collection — hit rates, latencies, counters."""
from collections import deque
import structlog

logger = structlog.get_logger()

_cache_metrics = {
    "exact_hits": 0,
    "semantic_hits": 0,
    "misses": 0,
    "sets": 0,
    "errors": 0,
    "latencies": deque(maxlen=1000),
    "total_lookups": 0,
}


def record_hit(hit_type: str, latency_ms: float) -> None:
    """Record cache hit (exact or semantic)."""
    _cache_metrics[f"{hit_type}_hits"] += 1
    _cache_metrics["total_lookups"] += 1
    _cache_metrics["latencies"].append(latency_ms)


def record_miss(latency_ms: float) -> None:
    """Record cache miss."""
    _cache_metrics["misses"] += 1
    _cache_metrics["total_lookups"] += 1
    _cache_metrics["latencies"].append(latency_ms)


def record_set() -> None:
    """Record cache set."""
    _cache_metrics["sets"] += 1


def record_error() -> None:
    """Record cache error."""
    _cache_metrics["errors"] += 1


def get_metrics() -> dict:
    """Return snapshot of current cache metrics."""
    latencies = list(_cache_metrics["latencies"])
    return {
        "exact_hits": _cache_metrics["exact_hits"],
        "semantic_hits": _cache_metrics["semantic_hits"],
        "misses": _cache_metrics["misses"],
        "sets": _cache_metrics["sets"],
        "errors": _cache_metrics["errors"],
        "total_lookups": _cache_metrics["total_lookups"],
        "hit_rate": (
            (_cache_metrics["exact_hits"] + _cache_metrics["semantic_hits"])
            / max(_cache_metrics["total_lookups"], 1)
        ),
        "avg_latency_ms": sum(latencies) / max(len(latencies), 1),
        "p95_latency_ms": sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0,
    }
```

- [ ] **Step 2: 创建 exact_cache.py**

从 `redis_client.py` 提取精确匹配缓存逻辑到 `backend/app/cache/exact_cache.py`：

```python
"""Exact-match cache — token-bag dedup, memory fallback, Redis TTL.

Extracted from redis_client.py for single-responsibility.
"""
import hashlib
import random
import re
import time
from typing import Optional
import structlog

from app.cache.connection import get_async_redis, get_sync_redis
from app.cache.metrics import record_hit, record_miss, record_set, record_error
from app.multi_tenant.middleware import get_current_tenant_id

logger = structlog.get_logger()

# ── In-memory fallback cache ──
_mem_cache: dict = {}
_MEM_TTL = 3600
_MEM_MAX_VALUE_BYTES = 512 * 1024
_CACHE_VERSION = "v16"


def _mem_cache_key(query: str, tenant_id: str = "default") -> str:
    raw = query.strip().lower()
    tokens = sorted(set(re.findall(r'[\w\u4e00-\u9fff]+', raw)))
    return f"llm_cache:{_CACHE_VERSION}:{tenant_id}:{hashlib.md5(' '.join(tokens).encode()).hexdigest()}"


def mem_get(query: str, tenant_id: str = "default") -> Optional[str]:
    """In-memory cache lookup with expiry check."""
    full_key = _mem_cache_key(query, tenant_id)
    entry = _mem_cache.get(full_key)
    if entry is None:
        return None
    value, expires_at = entry
    if time.monotonic() > expires_at:
        del _mem_cache[full_key]
        return None
    return value


def mem_set(query: str, response: str, ttl: int = _MEM_TTL, tenant_id: str = "default") -> None:
    """In-memory cache set with TTL jitter to prevent stampede."""
    if len(response) > _MEM_MAX_VALUE_BYTES:
        return
    jittered_ttl = ttl + (random.randint(0, 300) if ttl > 0 else 0)
    full_key = _mem_cache_key(query, tenant_id)
    _mem_cache[full_key] = (response, time.monotonic() + jittered_ttl)
    if len(_mem_cache) > 500:
        now = time.monotonic()
        expired = [k for k, (_, exp) in _mem_cache.items() if now > exp]
        for k in expired:
            del _mem_cache[k]
        if len(_mem_cache) > 500:
            oldest = sorted(_mem_cache.keys(), key=lambda k: _mem_cache[k][1])[:50]
            for k in oldest:
                del _mem_cache[k]


async def get_cached(query: str, tenant_id: str = "default") -> Optional[str]:
    """Async exact-match cache lookup: Redis → memory fallback."""
    start = time.monotonic()
    try:
        r = get_async_redis()
        if r:
            key = _mem_cache_key(query, tenant_id)
            val = await r.get(key)
            if val:
                record_hit("exact", (time.monotonic() - start) * 1000)
                return val
    except Exception as e:
        record_error()
        logger.debug("exact_cache_get_error", error=str(e))

    # Memory fallback
    val = mem_get(query, tenant_id)
    if val:
        record_hit("exact", (time.monotonic() - start) * 1000)
        return val

    record_miss((time.monotonic() - start) * 1000)
    return None


async def set_cached(query: str, response: str, ttl: int = 3600, tenant_id: str = "default") -> None:
    """Async exact-match cache set: Redis + memory."""
    mem_set(query, response, ttl, tenant_id)
    record_set()
    try:
        r = get_async_redis()
        if r:
            key = _mem_cache_key(query, tenant_id)
            jittered_ttl = ttl + random.randint(0, 300)
            await r.set(key, response, ex=jittered_ttl)
    except Exception as e:
        logger.debug("exact_cache_set_error", error=str(e))
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/cache/exact_cache.py backend/app/cache/metrics.py
git commit -m "refactor(cache): extract exact_cache and metrics modules"
```

---

### Task 8: 缓存模块拆分 — 更新 redis_client.py 为代理层

**Files:**
- Modify: `backend/app/cache/redis_client.py`
- Modify: `backend/app/cache/__init__.py`

- [ ] **Step 1: 精简 redis_client.py 为公共 API 代理**

将 `redis_client.py` 重写为一个薄代理层，所有实际逻辑委托到子模块：

```python
"""Cache public API — delegates to exact_cache, semantic_cache, metrics.

This module preserves backward compatibility: all existing imports from
redis_client continue to work.
"""
from typing import Optional
import structlog

from app.cache.connection import get_async_redis, get_sync_redis, close_sync_redis
from app.cache.exact_cache import (
    get_cached,
    set_cached,
    mem_get,
    mem_set,
    _mem_cache_key,
)
from app.cache.metrics import get_metrics, record_hit, record_miss, record_set, record_error

logger = structlog.get_logger()


# Re-export for backward compatibility
__all__ = [
    "get_async_redis",
    "get_sync_redis",
    "close_sync_redis",
    "get_cached",
    "set_cached",
    "mem_get",
    "mem_set",
    "get_metrics",
    "record_hit",
    "record_miss",
    "record_set",
    "record_error",
]
```

- [ ] **Step 2: 更新 cache/__init__.py**

确保 `__init__.py` 的公共 API 指向新位置：

```python
"""Cache module — exact match + semantic + metrics."""
from app.cache.redis_client import (
    get_cached,
    set_cached,
    get_async_redis,
    get_sync_redis,
    close_sync_redis,
    get_metrics,
)

__all__ = [
    "get_cached",
    "set_cached",
    "get_async_redis",
    "get_sync_redis",
    "close_sync_redis",
    "get_metrics",
]
```

- [ ] **Step 3: 运行后端缓存相关测试**

```bash
cd backend && python -m pytest tests/ -v -k "cache" --timeout=30
```
Expected: 所有测试 PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/cache/
git commit -m "refactor(cache): slim redis_client to proxy, update __init__ exports"
```

---

### Task 9: SSE Analytics 轻量化

**Files:**
- Modify: `backend/app/routers/chat.py:42-67`

- [ ] **Step 1: 替换 _record_stream_analytics 中的 SSE 解析逻辑**

将 `chat.py` 第 52-64 行的 SSE 解析循环替换为轻量版本：

```python
    try:
        async for raw_event in stream_gen:
            # Lightweight analytics — only parse sources events (low frequency)
            if raw_event.startswith("data: ") and '"type": "sources"' in raw_event:
                try:
                    payload = json.loads(raw_event[6:].rstrip())
                    sources_count = len(payload.get("sources", []))
                except (json.JSONDecodeError, AttributeError):
                    pass
            elif raw_event.startswith("data: "):
                # Count output bytes without JSON parsing
                full_text_len += len(raw_event) - 6
            yield raw_event
```

同时在函数顶部将 `full_text = ""` 替换为 `full_text_len = 0`，并在 `finally` 块中将：
```python
output_tokens = max(len(full_text) // 2, 1) if full_text else 0
```
替换为：
```python
output_tokens = max(full_text_len // 2, 1) if full_text_len else 0
```

- [ ] **Step 2: 运行后端测试**

```bash
cd backend && python -m pytest tests/ -v -k "chat" --timeout=30
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/chat.py
git commit -m "perf(sse): skip json.loads for text chunks, only parse sources events"
```

---

### Task 10: Repository 安全修复 — SQL 列名白名单

**Files:**
- Modify: `backend/app/database/repositories.py:125-141`

- [ ] **Step 1: 添加白名单并修复 update 方法**

在 `UserRepository` 类之前添加白名单常量：

```python
_ALLOWED_UPDATE_FIELDS = frozenset({"name", "email", "role", "is_active", "password_hash"})
```

将 `update` 方法替换为安全版本：

```python
    @staticmethod
    async def update(user_id: int, **fields) -> bool:
        """Update user fields — only whitelisted column names allowed."""
        pool = get_db_pool()
        if not pool:
            return False
        safe_fields = {k: v for k, v in fields.items() if k in _ALLOWED_UPDATE_FIELDS}
        if not safe_fields:
            logger.warning("user_update_no_safe_fields", user_id=user_id, requested=list(fields.keys()))
            return False
        set_parts = []
        values = []
        for i, (k, v) in enumerate(safe_fields.items(), 1):
            set_parts.append(f"{k} = ${i}")
            values.append(v)
        values.append(user_id)
        async with pool.acquire() as conn:
            result = await conn.execute(
                f"UPDATE users SET {', '.join(set_parts)}, updated_at = NOW() WHERE id = ${len(values)}",
                *values
            )
            return result != "UPDATE 0"
```

- [ ] **Step 2: 运行后端测试**

```bash
cd backend && python -m pytest tests/ -v -k "user or repository" --timeout=30
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/database/repositories.py
git commit -m "security(db): add column whitelist to UserRepository.update()"
```

---

### Task 11: fire_and_forget 增强 — resilient_task

**Files:**
- Modify: `backend/app/common.py`

- [ ] **Step 1: 在 common.py 末尾添加 resilient_fire_and_forget**

```python
def resilient_fire_and_forget(
    coro,
    *,
    name: str = "",
    max_retries: int = 2,
    retry_delay: float = 1.0,
) -> None:
    """Fire-and-forget with retry on transient errors (ConnectionError, TimeoutError, OSError).

    Non-transient errors are logged but not retried.
    Per Python docs: save task reference to avoid disappearing mid-execution.
    """
    async def _run():
        for attempt in range(max_retries + 1):
            try:
                await coro
                return
            except (ConnectionError, TimeoutError, OSError) as e:
                if attempt < max_retries:
                    await _asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                _bg_logger.warning(
                    "resilient_task_exhausted_retries",
                    task_name=name,
                    attempts=attempt + 1,
                    error=str(e),
                )
            except Exception as e:
                _bg_logger.error(
                    "resilient_task_unexpected_error",
                    task_name=name,
                    error_type=type(e).__name__,
                    error=str(e),
                )
                return

    try:
        task = _asyncio.create_task(_run(), name=f"resilient:{name}")
    except RuntimeError:
        _bg_logger.warning("resilient_fire_and_forget_no_loop", task_name=name)
        coro.close()
        return

    _background_tasks.add(task)

    def _on_done(t: _asyncio.Task) -> None:
        _background_tasks.discard(t)

    task.add_done_callback(_on_done)
```

- [ ] **Step 2: 在 chat.py 中使用 resilient_fire_and_forget 替换 analytics 记录**

在 `chat.py` 的 import 中添加：
```python
from app.common import SSE_HEADERS, sse_event, fire_and_forget, resilient_fire_and_forget
```

将 `_record_stream_analytics` 中 3 处 `fire_and_forget(...)` 替换为 `resilient_fire_and_forget(...)`：
```python
resilient_fire_and_forget(
    record_query(...),
    name="chat_record_query",
)
# ...
resilient_fire_and_forget(
    collector.record_query_metrics(...),
    name="chat_dashboard_metrics",
)
# ...
resilient_fire_and_forget(
    cost_service.record_usage(...),
    name="chat_cost_record",
)
```

- [ ] **Step 3: 运行后端测试**

```bash
cd backend && python -m pytest tests/ -v --timeout=60
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/common.py backend/app/routers/chat.py
git commit -m "feat: add resilient_fire_and_forget with retry, use in chat analytics"
```

---

### Task 12: CSS 暗色主题迁移 — 消除 !important 覆盖

**Files:**
- Modify: `src/index.css:478-576`
- Modify: `src/pages/Documents.tsx`
- Modify: `src/pages/Admin/FeatureFlags.tsx`

**背景**：`index.css` 第 478-576 行的 "Global Dark Theme Overrides" 使用 `!important` 将标准 Tailwind 亮色类（`bg-white`、`text-gray-*` 等）强制覆盖为暗色。这种做法有 3 个问题：
1. `!important` 导致样式优先级混乱
2. 新组件可能意外触发覆盖
3. Tailwind CSS 4 的 JIT 编译器无法优化被覆盖的类

**方案**：将使用了标准 Tailwind 亮色类的组件替换为 CSS 变量类名，然后删除 `!important` 覆盖块。

- [ ] **Step 1: 替换 Documents.tsx 中的标准 Tailwind 色值类**

将以下类名替换为 CSS 变量版本：

| 原始类名 | 替换为 |
|---------|-------|
| `bg-white` | `bg-[var(--bg-secondary)]` |
| `bg-gray-50` | `bg-[var(--bg-elevated)]` |
| `bg-gray-100` | `bg-[var(--bg-tertiary)]` |
| `bg-gray-200` | `bg-[var(--bg-tertiary)]` |
| `text-gray-900` | `text-[var(--text-primary)]` |
| `text-gray-700` | `text-[var(--text-secondary)]` |
| `text-gray-600` | `text-[var(--text-secondary)]` |
| `text-gray-500` | `text-[var(--text-tertiary)]` |
| `border-gray-100` | `border-[var(--border)]` |
| `border-gray-200` | `border-[var(--border)]` |
| `hover:bg-gray-50` | `hover:bg-[var(--bg-tertiary)]` |
| `hover:bg-gray-200` | `hover:bg-[var(--bg-tertiary)]` |

- [ ] **Step 2: 替换 Admin/FeatureFlags.tsx 中的标准 Tailwind 色值类**

同 Step 1 的映射表，将 `bg-white`、`bg-gray-50`、`text-gray-900`、`text-gray-800`、`divide-gray-200`、`hover:bg-gray-50` 替换为对应的 CSS 变量版本。

- [ ] **Step 3: 删除 index.css 的 Global Dark Theme Overrides 块**

删除第 478-576 行的 `!important` 覆盖块（从 `/* ═══ Global Dark Theme Overrides ═══ */` 到 `/* ── Prose */` 之前）。

保留 `@media (prefers-reduced-motion)` 块中的 `!important`（这是 W3C 规范推荐的无障碍做法）。

保留 Prose 块（第 578-590 行）— 这些不使用 `!important`。

- [ ] **Step 4: 运行前端测试和构建验证**

```bash
npm test -- --run && npm run build
```

- [ ] **Step 5: 视觉验证（需要 dev server）**

```bash
npm run dev
```

在浏览器中打开 Documents 和 FeatureFlags 页面，确认暗色主题显示正确（卡片背景暗色、文字亮色、边框可见）。

- [ ] **Step 6: Commit**

```bash
git add src/index.css src/pages/Documents.tsx src/pages/Admin/FeatureFlags.tsx
git commit -m "style: migrate dark theme overrides to CSS variables, remove !important"
```

---

## Phase 3：性能深水区

### Task 13: Prometheus 指标增强

**Files:**
- Modify: `backend/app/observability/` — 添加自定义 Prometheus 指标
- Modify: `backend/app/cache/metrics.py` — 导出 Prometheus 指标

- [ ] **Step 1: 在 observability 中注册自定义 Prometheus 指标**

在 `backend/app/observability/` 下创建 `custom_metrics.py`：

```python
"""Custom Prometheus metrics for Aureon platform."""
from prometheus_client import Counter, Histogram, Gauge

# Cache metrics
cache_lookups_total = Counter(
    "cache_lookups_total",
    "Total cache lookups",
    ["type"],  # exact, semantic, miss
)
cache_latency_seconds = Histogram(
    "cache_latency_seconds",
    "Cache lookup latency",
    ["type"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.5],
)

# Database pool metrics
db_pool_size = Gauge("db_pool_size", "DB connection pool total size")
db_pool_idle = Gauge("db_pool_idle", "DB connection pool idle connections")

# SSE streaming metrics
sse_chunks_per_response = Histogram(
    "sse_chunks_per_response",
    "Number of SSE chunks per streaming response",
    buckets=[10, 50, 100, 200, 500, 1000, 5000],
)

# WebSocket metrics
ws_active_connections = Gauge(
    "ws_active_connections",
    "Active WebSocket connections",
    ["type"],  # chat, dashboard
)
```

- [ ] **Step 2: 在 cache/metrics.py 中桥接到 Prometheus**

在 `get_metrics()` 函数中添加 Prometheus 指标上报：

```python
def export_prometheus_metrics() -> None:
    """Push current cache metrics to Prometheus counters/histograms."""
    from app.observability.custom_metrics import cache_lookups_total, cache_latency_seconds
    m = get_metrics()
    # Note: These are cumulative counters, only set on startup delta
    cache_lookups_total.labels(type="exact").inc(m["exact_hits"])
    cache_lookups_total.labels(type="semantic").inc(m["semantic_hits"])
    cache_lookups_total.labels(type="miss").inc(m["misses"])
```

- [ ] **Step 3: 运行后端测试验证 Prometheus 注册不冲突**

```bash
cd backend && python -m pytest tests/ -v -k "prometheus or metrics" --timeout=30
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/observability/custom_metrics.py backend/app/cache/metrics.py
git commit -m "feat(observability): add cache/db/sse/ws Prometheus metrics"
```

---

### Task 14: DB 连接池监控与优化

**Files:**
- Modify: `backend/app/database/connection.py`

- [ ] **Step 1: 添加 pool stats 暴露函数**

在 `connection.py` 中添加：

```python
def get_pool_stats() -> dict | None:
    """Return asyncpg pool statistics for monitoring."""
    pool = get_db_pool()
    if not pool:
        return None
    return {
        "size": pool.get_size(),
        "idle_size": pool.get_idle_size(),
        "min_size": pool.get_min_size(),
        "max_size": pool.get_max_size(),
    }


def update_prometheus_pool_stats() -> None:
    """Push DB pool stats to Prometheus gauges."""
    stats = get_pool_stats()
    if stats:
        try:
            from app.observability.custom_metrics import db_pool_size, db_pool_idle
            db_pool_size.set(stats["size"])
            db_pool_idle.set(stats["idle_size"])
        except Exception:
            pass
```

- [ ] **Step 2: 在 main.py lifespan 中添加定期上报**

在 FastAPI lifespan 的 startup 中添加后台任务（每 30s）上报 pool stats：

```python
async def _pool_monitor():
    """Periodically report DB pool stats to Prometheus."""
    from app.database.connection import update_prometheus_pool_stats
    while True:
        update_prometheus_pool_stats()
        await asyncio.sleep(30)

# In lifespan startup:
asyncio.create_task(_pool_monitor())
```

- [ ] **Step 3: 调整 command_timeout 从 30s → 60s**

在 `connection.py` 的 `create_pool` 调用中将 `command_timeout=30` 改为 `command_timeout=60`。

- [ ] **Step 4: Commit**

```bash
git add backend/app/database/connection.py backend/app/main.py
git commit -m "feat(db): pool monitoring via Prometheus, increase command_timeout to 60s"
```

---

### Task 15: Schema 版本控制

**Files:**
- Create: `backend/app/database/schema.py`
- Create: `backend/app/database/migrations/001_initial.sql`

- [ ] **Step 1: 创建 schema.py**

```python
"""Database schema versioning — applies pending migrations on startup."""
import structlog
from pathlib import Path

logger = structlog.get_logger()

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def ensure_schema_version_table(pool) -> None:
    """Create schema_version table if not exists."""
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT NOW(),
                description TEXT
            )
        """)


async def get_current_version(pool) -> int:
    """Return the latest applied migration version, or 0 if none."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COALESCE(MAX(version), 0) AS v FROM schema_version"
        )
        return row["v"]


async def get_pending_migrations(current_version: int) -> list[tuple[int, Path]]:
    """Return list of (version, path) for unapplied migrations."""
    pending = []
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        try:
            version = int(f.stem.split("_")[0])
            if version > current_version:
                pending.append((version, f))
        except ValueError:
            logger.warning("migration_invalid_filename", file=f.name)
    return pending


async def apply_migrations(pool) -> None:
    """Apply all pending migrations in order."""
    await ensure_schema_version_table(pool)
    current = await get_current_version(pool)
    pending = await get_pending_migrations(current)

    for version, path in pending:
        sql = path.read_text(encoding="utf-8")
        logger.info("migration_applying", version=version, file=path.name)
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_version (version, description) VALUES ($1, $2)",
                    version, path.name,
                )
        logger.info("migration_applied", version=version)
```

- [ ] **Step 2: 创建初始 migration 文件**

创建 `backend/app/database/migrations/` 目录和 `001_initial.sql`：

```sql
-- 001_initial: Base schema for users and audit_logs
-- This is idempotent — uses IF NOT EXISTS

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    password_hash VARCHAR(255),
    role VARCHAR(50) DEFAULT 'user',
    is_active BOOLEAN DEFAULT TRUE,
    tenant_id VARCHAR(100) DEFAULT 'default',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100),
    action VARCHAR(100) NOT NULL,
    resource VARCHAR(255),
    detail TEXT,
    ip_address VARCHAR(50),
    tenant_id VARCHAR(100) DEFAULT 'default',
    created_at TIMESTAMP DEFAULT NOW()
);
```

- [ ] **Step 3: 在 main.py lifespan 中调用 apply_migrations**

在 DB pool 创建后添加：

```python
from app.database.schema import apply_migrations
# ...
pool = get_db_pool()
if pool:
    await apply_migrations(pool)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/database/schema.py backend/app/database/migrations/
git commit -m "feat(db): add schema versioning with migration support"
```

---

### Task 16: docker-compose 精简评估

**Files:**
- Modify: `docker-compose.yml`（条件性）

- [ ] **Step 1: 检查 Elasticsearch 使用情况**

```bash
cd backend && grep -r "elasticsearch\|ELASTICSEARCH\|BM25_BACKEND" app/ --include="*.py" | head -20
```

根据输出决定：
- 如果 `BM25_BACKEND` 默认不是 `elasticsearch`，且无代码硬依赖 ES → 从 docker-compose.yml 移除 ES 服务
- 如果仍有依赖 → 跳过此 Task，添加注释说明保留原因

- [ ] **Step 2: （条件）移除 ES 服务并验证**

如果确认无依赖，从 `docker-compose.yml` 中删除 `elasticsearch` 服务块和相关环境变量。

```bash
docker compose up -d && docker compose ps
```

- [ ] **Step 3: Commit（条件性）**

```bash
git add docker-compose.yml
git commit -m "chore(docker): remove unused Elasticsearch service"
```

---

## Final Verification

- [ ] **Step 1: 全量前端测试**

```bash
npm test -- --run
```

- [ ] **Step 2: 全量后端测试**

```bash
cd backend && python -m pytest tests/ -v --timeout=120
```

- [ ] **Step 3: 前端构建产物对比**

```bash
npx vite build --mode production 2>&1 | grep -E "dist/assets/.*\.(js|css)"
```

比较优化前后的 chunk 大小。

- [ ] **Step 4: 全 App WebSocket 连接验证**

打开浏览器 DevTools → Network → WS，确认全 App 最多 2 个 WS 连接（`/ws/dashboard` + `/ws/chat/{id}`）。
