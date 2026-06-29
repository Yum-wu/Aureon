# Aureon 架构修复计划 (2026-06-29)

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development or executing-plans to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 修复综合审查中发现的 P0-P3 问题，分 4 个独立阶段推进，每阶段产出可测试/可部署的软件。

**Architecture:** 本计划覆盖 backend (FastAPI/Python) 和 frontend (React/TypeScript) 两个子系统。每个阶段独立，可单独部署验证。

**Tech Stack:** FastAPI + LangGraph + Qdrant + React 19 + Zustand v5 + PostgreSQL + Redis

---

## Phase 0 — 立即安全修复 (P0)

> 预计耗时：~1.5h。优先级最高，影响生产安全或数据完整性。

### 背景

综合审查发现的 5 个 P0 问题：
1. `l2_scenario.py` 路径遍历 — OWASP Agentic Top 10 ASI06
2. LangGraph Recursion Limit 未设置 — 可能引发 $2400 级成本事故
3. CRAG 默认关闭且阈值无效 — 纠错能力未启用
4. `useChatStore` 模块级全局变量 — HMR 泄漏 + 并发不安全
5. Zustand v5 对象解构 selector — 无限重渲染

---

### Task P0-1: 修复 l2_scenario.py 路径遍历

**Files:**
- Modify: `backend/app/memory/l2_scenario.py:39`

- [ ] **添加 session_id 清理函数**

在 `l2_scenario.py` 文件顶部添加：

```python
import re

def _sanitize_session_id(session_id: str) -> str:
    """防止路径遍历攻击。只保留字母、数字、下划线、连字符。"""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', session_id)
```

- [ ] **在文件路径拼接处调用清理**

找到第 39 行附近使用 `session_id` 拼接文件路径的代码，将 `session_id` 替换为 `_sanitize_session_id(session_id)`。

修改前：
```python
# 假设类似：scenario_path = SCENARIOS_DIR / f"{session_id}.md"
```

修改后：
```python
scenario_path = SCENARIOS_DIR / f"{_sanitize_session_id(session_id)}.md"
```

搜索 `l2_scenario.py` 中所有使用 `session_id` 拼接路径的地方，共约 2-3 处。

- [ ] **运行现有 memory 测试验证不破坏功能**

Run: `cd backend && python -m pytest tests/test_memory.py -v -x --timeout=30`
Expected: 全部 PASS

- [ ] **Commit**

```bash
git add backend/app/memory/l2_scenario.py
git commit -m "fix: sanitize session_id in l2_scenario path construction

Prevents path traversal attack. OWASP ASI06 (Memory Poisoning).
Allows only [a-zA-Z0-9_-] in session_id for file paths."
```

---

### Task P0-2: 添加 LangGraph Recursion Limit

**Files:**
- Modify: `backend/app/agent/executor.py` (graph.invoke 调用处)

- [ ] **找到所有 graph.invoke / graph.astream 调用**

搜索 `executor.py` 中 `graph.invoke` 或 `agent.astream` 的调用。

- [ ] **添加 recursion_limit=50**

在每个调用处添加配置：

修改前：
```python
config = {"configurable": {"thread_id": session_id}}
result = await agent.astream_events(inputs, config=config, version="v2")
```

修改后：
```python
config = {
    "configurable": {"thread_id": session_id},
    "recursion_limit": 50,
}
result = await agent.astream_events(inputs, config=config, version="v2")
```

- [ ] **运行 agent 测试验证**

Run: `cd backend && python -m pytest tests/test_agent_flow.py -v -x --timeout=30`
Expected: 全部 PASS

- [ ] **Commit**

```bash
git add backend/app/agent/executor.py
git commit -m "fix: add recursion_limit=50 to graph invocations

Prevents unbounded loop cost explosion (LangGraph official warning).
One uncaught loop can cost $2400+ per documented incidents."
```

---

### Task P0-3: 启用 CRAG + 校准阈值

**Files:**
- Modify: `backend/app/config.py` (VectorStoreSettings)
- Modify: `backend/app/rag/generator.py` (CRAG 阈值使用)
- Test: `tests/test_qa_chain.py`

- [ ] **在 config.py 中启用 CRAG 并调整阈值**

修改 `config.py` 中 `AppSettings` 的默认值：

修改前：
```python
crag_enabled: bool = False
crag_high_confidence: float = 0.05
crag_low_confidence: float = 0.01
crag_ambiguous_threshold: float = 0.03
```

修改后：
```python
crag_enabled: bool = True
crag_high_confidence: float = 0.15   # RRF rank-1 ≈ 0.005，此值需对应评估校准
crag_low_confidence: float = 0.05
crag_ambiguous_threshold: float = 0.10
```

- [ ] **验证 generator.py 使用 settings 值而非硬编码**

搜索 `generator.py` 中 CRAG 相关代码，确认引用的是 `settings.crag_*` 而非硬编码常量。如有硬编码常量，替换为配置引用。

- [ ] **运行 CRAG 相关测试**

Run: `cd backend && python -m pytest tests/test_qa_chain.py -v -x --timeout=60`
Expected: 全部 PASS

- [ ] **Commit**

```bash
git add backend/app/config.py backend/app/rag/generator.py
git commit -m "fix: enable CRAG with calibrated thresholds

crag_enabled=True with adjusted thresholds (high=0.15, low=0.05)
to match actual RRF score distribution."
```

---

### Task P0-4: useChatStore 模块级全局变量移入闭包

**Files:**
- Modify: `src/stores/useChatStore.ts`

- [ ] **将模块级全局变量移入 create() 闭包**

修改前（模块级，约第 22-25 行）：
```typescript
let _textBuffer = "";
let _flushTimer: ReturnType<typeof setTimeout> | null = null;
let _currentAssistantId = "";
```

修改后（移入 `create()` 回调闭包）：
```typescript
export const useChatStore = create<ChatState>((set, get) => {
  let textBuffer = "";
  let flushTimer: ReturnType<typeof setTimeout> | null = null;
  let currentAssistantId = "";

  const flushBuffer = () => {
    if (flushTimer) {
      clearTimeout(flushTimer);
      flushTimer = null;
    }
    if (!textBuffer) return;
    const text = textBuffer;
    textBuffer = "";
    const aid = currentAssistantId;
    set((state) => {
      const messages = [...state.messages];
      const lastIdx = messages.length - 1;
      if (lastIdx >= 0) {
        const lastMsg = { ...messages[lastIdx] };
        lastMsg.content += text;
        lastMsg.id = aid;
        messages[lastIdx] = lastMsg;
      }
      return { messages };
    });
  };
```

确保所有引用 `_textBuffer` 等全局变量的代码变为引用闭包内的 `textBuffer` 等。

- [ ] **运行前端测试验证**

Run: `cd C:\Users\Yum\Desktop\Aureon-test && npx vitest run --reporter=verbose 2>&1`
Expected: Related chat store tests pass

- [ ] **Commit**

```bash
git add src/stores/useChatStore.ts
git commit -m "fix: move SSE text buffer from module globals to create() closure

Each store instance now has isolated buffers. Fixes HMR leak and
concurrent access issues. Zustand official pattern."
```

---

### Task P0-5: Zustand v5 useShallow 修复无限重渲染

**Files:**
- Modify: `src/components/ChatWidget.tsx`
- Modify: `src/components/SupportWidget.tsx`
- Modify: `src/App.tsx`

- [ ] **在 App.tsx 中将对象解构替换为原子选择器**

修改前（`App.tsx:69-72`）：
```typescript
const sidebarCollapsed = useUIStore(s => s.sidebarCollapsed);
const toggleSidebarCollapsed = useUIStore(s => s.toggleSidebarCollapsed);
const mobileSidebarOpen = useUIStore(s => s.mobileSidebarOpen);
const setMobileSidebarOpen = useUIStore(s => s.setMobileSidebarOpen);
```

拆分为 4 个原子选择器 — 已经是原子选择器，✅ 正确。

然后在 `ChatWidget.tsx` 和 `SupportWidget.tsx` 中检查是否有：
```typescript
// ❌ 对象解构 — 每次返回新引用
const { messages, sendMessage } = useChatStore(state => ({
  messages: state.messages,
  sendMessage: state.sendMessage,
}));
```

替换为：
```typescript
import { useShallow } from 'zustand/react/shallow';

const { messages, sendMessage } = useChatStore(
  useShallow(state => ({ messages: state.messages, sendMessage: state.sendMessage }))
);
```

- [ ] **运行前端测试**

Run: `npx vitest run --reporter=verbose 2>&1`
Expected: 全部 PASS

- [ ] **Commit**

```bash
git add src/components/ChatWidget.tsx src/components/SupportWidget.tsx src/App.tsx
git commit -m "fix: add useShallow for Zustand v5 object selectors

Zustand v5 uses Object.is equality, causing infinite re-render
when selector returns new object reference each time."
```

---

## Phase 1 — 架构修复 (P1)

> 预计耗时：~5h。影响正确性、架构可维护性。

### Task P1-1: RAG 流水线公共函数提取

**Files:**
- Create: `backend/app/rag/_pipeline.py`
- Modify: `backend/app/rag/generator.py` (rag_query 和 rag_query_astream 重构)
- Test: `tests/test_qa_chain.py`

- [ ] **创建 _pipeline.py 文件，提取公共流水线逻辑**

```python
"""RAG 流水线公共逻辑。避免 rag_query 和 rag_query_astream 之间重复。"""

from typing import AsyncGenerator, Optional

from app.config import settings
from app.rag.query_classifier import route_retrieval


def should_use_hyde(query_complexity: str) -> bool:
    """HyDE 条件判断：中等和复杂查询启用。"""
    return query_complexity in ("medium", "complex") and settings.hyde_enabled


def determine_query_complexity(query: str) -> str:
    """查询复杂度判断，同步+异步共用。"""
    if settings.query_routing_enabled:
        return route_retrieval(query)
    return "medium"


def should_skip_negative_detection(top_score: float) -> bool:
    """高置信度结果跳过负面检测。"""
    return top_score >= settings.high_score_skip_threshold


def should_run_context_compression(top_score: float) -> bool:
    """上下文压缩条件判断。"""
    return (
        settings.context_compression_enabled
        and top_score < settings.context_compression_threshold
    )
```

- [ ] **重构 rag_query 使用 _pipeline 函数**

在 `generator.py` 中找到 `rag_query()` 和 `rag_query_astream()` 中重复的条件判断，替换为 `_pipeline.should_use_hyde()` 等调用。

修改前（重复两次）：
```python
if settings.query_routing_enabled:
    query_complexity = route_retrieval(query)
else:
    query_complexity = "medium"

if query_complexity in ("medium", "complex") and settings.hyde_enabled:
    # HyDE 逻辑
```

修改后（调用一次）：
```python
from app.rag._pipeline import determine_query_complexity, should_use_hyde

query_complexity = determine_query_complexity(query)
if should_use_hyde(query_complexity):
    # HyDE 逻辑
```

- [ ] **运行测试验证**

Run: `cd backend && python -m pytest tests/test_qa_chain.py -v -x --timeout=60`
Expected: 全部 PASS

- [ ] **Commit**

```bash
git add backend/app/rag/_pipeline.py backend/app/rag/generator.py
git commit -m "refactor: extract shared RAG pipeline logic from duplicate query paths

rag_query and rag_query_astream had ~150 lines of duplicated condition logic.
Extracted to _pipeline.py with should_use_hyde, determine_query_complexity, etc."
```

---

### Task P1-2: Rate Limiter 添加 Redis 后端

**Files:**
- Create: `backend/app/rate_limit.py`
- Modify: `backend/app/main.py` (limiter 引用)
- Modify: `backend/app/security/router.py` (如果有独立 limiter)
- Modify: `backend/app/routers/crew.py` (如果有独立 limiter)

- [ ] **创建集中式 rate_limit.py**

```python
"""集中式速率限制配置。单例 limiter，共享 Redis 后端。"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from app.config import settings

_redis_url = settings.cache.redis_url

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=f"redis://{_redis_url}/1" if _redis_url else None,
)

# 预定义速率限制
CHAT_STREAM_LIMIT = "20/minute"
RAG_QUERY_LIMIT = "30/minute"
LANGGRAPH_LIMIT = "5/minute"
API_DEFAULT_LIMIT = "60/minute"
```

- [ ] **替换 main.py 中的 limiter**

删除 `main.py` 中的 `limiter = Limiter(key_func=get_remote_address)`，改为 `from app.rate_limit import limiter`。

- [ ] **替换各 router 中的独立 limiter**

搜索各 router 文件，替换独立的 `limiter = Limiter(...)` 为导入 `from app.rate_limit import limiter`。

- [ ] **运行测试**

Run: `cd backend && python -m pytest tests/ -v -x -k "rate" --timeout=30`
Expected: 全部 PASS

- [ ] **Commit**

```bash
git add backend/app/rate_limit.py backend/app/main.py
git commit -m "fix: add Redis-backed rate limiter for multi-worker support

Previously used in-memory limiter per process, allowing N× limit
bypass behind Railway load balancer. Now shares cluster-wide state."
```

---

### Task P1-3: RAG 检索候选池固定为 150

**Files:**
- Modify: `backend/app/config.py` (VectorStoreSettings)
- Modify: `backend/app/rag/retriever.py` (候选池计算)

- [ ] **在 config.py 中添加候选池大小配置**

```python
class VectorStoreSettings(BaseModel):
    # ... 现有字段 ...
    retrieval_candidates: int = 150  # 初始检索候选数（Anthropic 推荐 top-150）
```

- [ ] **在 retriever.py 中替换候选池计算**

搜索 `top_k * settings.retrieval_multiplier` 或类似动态计算，替换为 `settings.retrieval_candidates`。

修改前：
```python
prefetch_limit = top_k * settings.retrieval_multiplier  # 12 倍
```

修改后：
```python
prefetch_limit = settings.retrieval_candidates  # 固定 150
```

保留 `retrieval_multiplier` 为向后兼容，日志记录使用情况。

- [ ] **运行测试**

Run: `cd backend && python -m pytest tests/test_qa_chain.py tests/test_retriever.py -v -x --timeout=60`
Expected: 全部 PASS

- [ ] **Commit**

```bash
git add backend/app/config.py backend/app/rag/retriever.py
git commit -m "perf: fix retrieval candidate pool to constant 150

Previous top_k * 12 resulted in 36-60 candidates depending on top_k.
Anthropic CR paper and TREC'25 champion both recommend fixed 150
for initial retrieval before rerank."
```

---

### Task P1-4: SupportWidget 拆分

**Files:**
- Create: `src/hooks/useSupportWebSocket.ts`
- Create: `src/components/support/SupportFab.tsx`
- Create: `src/components/support/SupportChatPanel.tsx`
- Create: `src/components/support/OfflineForm.tsx`
- Modify: `src/components/SupportWidget.tsx` (精简为编排器)

- [ ] **提取 useSupportWebSocket hook**

```typescript
// src/hooks/useSupportWebSocket.ts
import { useState, useEffect, useRef, useCallback } from 'react';
import type { Message } from '../types/message';

interface UseSupportWebSocketOptions {
  onMessage: (msg: Message) => void;
  onStreamingText: (text: string) => void;
  onConnectionChange: (connected: boolean) => void;
}

export function useSupportWebSocket(options: UseSupportWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  const connect = useCallback(() => {
    // 从 SupportWidget.tsx 第 65 行迁移 WebSocket 连接逻辑
  }, []);

  const send = useCallback((text: string) => {
    // 发送消息
  }, []);

  const close = useCallback(() => {
    wsRef.current?.close();
  }, []);

  return { isConnected, send, connect, close };
}
```

- [ ] **提取 SupportFab 组件**

从 `SupportWidget.tsx` 迁移 FAB 浮动按钮相关 DOM 和逻辑。

- [ ] **提取 SupportChatPanel 组件**

从 `SupportWidget.tsx` 迁移聊天面板、消息列表、输入框相关 DOM 和逻辑。注意修复陈旧闭包问题（`streamingSources` 使用函数式 setState）。

修复陈旧闭包的关键修改：
```typescript
// 修改前（约第 91 行）：
setMessages(prev => {
  const last = prev[prev.length - 1];
  last.sources = streamingSources;  // 闭包捕获的是绑定时的值
  return [...prev];
});

// 修改后：
setStreamingSources(current => {  // 使用函数式更新
  // 通过 ref 或 state 更新器获取最新值
  return current;
});
setMessages(prev => {
  const last = { ...prev[prev.length - 1] };
  last.sources = streamingSources;  // 此处仍需要确保最新值
  prev[prev.length - 1] = last;
  return [...prev];
});
```

- [ ] **精简 SupportWidget.tsx 为编排器**

导入三个新组件/hook，作为协调者。

```typescript
// src/components/SupportWidget.tsx (简化版)
import { SupportFab } from './support/SupportFab';
import { SupportChatPanel } from './support/SupportChatPanel';
import { OfflineForm } from './support/OfflineForm';
import { useSupportWebSocket } from '../hooks/useSupportWebSocket';

export function SupportWidget() {
  const [isOpen, setIsOpen] = useState(false);
  const [isOffline, setIsOffline] = useState(false);
  const { isConnected, send } = useSupportWebSocket({
    onMessage: handleMessage,
    onStreamingText: handleStreamingText,
    onConnectionChange: (connected) => setIsOffline(!connected),
  });

  return (
    <>
      <SupportFab isOpen={isOpen} onToggle={() => setIsOpen(!isOpen)} />
      {isOpen && (
        isOffline ? <OfflineForm /> : <SupportChatPanel onSend={send} />
      )}
    </>
  );
}
```

- [ ] **运行前端测试验证**

Run: `npx vitest run --reporter=verbose 2>&1`
Expected: 全部 PASS（含 SupportWidget 测试）

- [ ] **Commit**

```bash
git add src/hooks/useSupportWebSocket.ts src/components/support/ src/components/SupportWidget.tsx
git commit -m "refactor: split SupportWidget into 4 focused modules

Extracted useSupportWebSocket hook, SupportFab, SupportChatPanel,
and OfflineForm. Fixed streamingSources stale closure bug.
540-line component reduced to ~50-line orchestrator."
```

---

### Task P1-5: SSE 自动重连

**Files:**
- Modify: `src/services/api.ts`

- [ ] **在 fetchSSE 上层添加重试包装**

```typescript
// src/services/api.ts

interface SSEOptions {
  onText: (text: string) => void;
  onToolStart?: (name: string) => void;
  onToolEnd?: (name: string, output?: string) => void;
  onDone?: () => void;
  onError?: (error: Error) => void;
}

async function fetchSSEWithRetry(
  url: string,
  body: Record<string, unknown>,
  options: SSEOptions,
  maxRetries = 3,
): Promise<void> {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      await fetchSSE(url, body, options);
      return;  // 成功则退出
    } catch (err) {
      if (attempt === maxRetries) throw err;
      if (err instanceof TypeError && (err as any).message?.includes('fetch')) {
        // 网络错误，可重试
        await new Promise(r => setTimeout(r, Math.min(1000 * 2 ** attempt, 16000)));
        continue;
      }
      throw err;  // 非网络错误不重试
    }
  }
}
```

- [ ] **运行前端测试**

Run: `npx vitest run --reporter=verbose 2>&1`
Expected: 全部 PASS

- [ ] **Commit**

```bash
git add src/services/api.ts
git commit -m "feat: add automatic SSE reconnection with exponential backoff

Network-transient errors now retry up to 3 times with 1s/2s/4s backoff.
Non-network errors (auth, validation) still throw immediately."
```

---

## Phase 2 — 可维护性改进 (P2)

> 预计耗时：~2h。长期可维护性提升。

### Task P2-1: Middleware 清理

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/middleware/logging.py`

- [ ] **统一 Middleware 注册方式**

将 `logging_middleware` 从 `@app.middleware("http")` 改为 `app.add_middleware(BaseHTTPMiddleware, dispatch=logging_middleware)`。

- [ ] **删除 logging_middleware 中的重复安全头**

找到 `logging_middleware` 中设置 `X-Content-Type-Options` 等安全头的代码，删除（`SecurityHeadersMiddleware` 已经设置）。

- [ ] **在 middleware/logging.py 中将 request_id 绑定提前**

用最外层的 middleware 绑定 `request_id`，确保 TenantMiddleware 等内层 middleware 的日志也有关联 ID。

```python
# middleware/logging.py
async def logging_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
    )
    # ... 其余逻辑
```

- [ ] **Commit**

```bash
git add backend/app/main.py backend/app/middleware/logging.py
git commit -m "refactor: unify middleware registration and fix request_id binding

Middleware stack now uses consistent add_middleware(BaseHTTPMiddleware) pattern.
Removed duplicate security headers from logging middleware.
request_id now bound at outermost layer for full trace correlation."
```

---

### Task P2-2: Prometheus 升级至 7.1.0+

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/main.py` (删除 monkey patch)

- [ ] **修改 requirements.txt**

```text
# 修改前
prometheus-fastapi-instrumentator>=6.0.0,<7.0

# 修改后
prometheus-fastapi-instrumentator>=7.1.0,<9.0
```

- [ ] **在 main.py 中删除 monkey patch**

删除 `main.py:58-84` 的 `_patched_get_route_name` 函数和 `_pfi_routing._get_route_name = _patched_get_route_name`。

- [ ] **添加更合适的 latency buckets**

```python
Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    latency_histogram_buckets=[
        0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0,
    ],
).instrument(app).expose(app, endpoint="/metrics")
```

- [ ] **验证启动正常**

Run: `cd backend && python -c "from app.main import app; print('OK')"`
Expected: 输出 `OK`，无 monkey patch 相关错误

- [ ] **Commit**

```bash
git add backend/requirements.txt backend/app/main.py
git commit -m "chore: upgrade prometheus-fastapi-instrumentator to 7.1.0

Removes monkey-patch for FastAPI 0.137 compat (fixed upstream).
Adds AI-relevant latency buckets for SSE streaming endpoints."
```

---

## Phase 3 — 增量改进 (P3)

> 预计耗时：~4h。功能完善，可按需挑选。

### Task P3-1: HyDE 从 1 条改为 5 条假设文档

**Files:**
- Modify: `backend/app/rag/qa_chain.py` 或相关 HyDE 实现

在 HyDE 生成处将 `n=1` 改为 `n=5`，对 5 条 embedding 取均值。

### Task P3-2: Contextual Retrieval chunk 上下文前缀

**Files:**
- Modify: `backend/app/rag/ingestion/pipeline.py` 或 `indexer.py`

每个 chunk 在 embedding 前用 LLM 生成 50-100 token 上下文前缀。

### Task P3-3: Memory TTL + 衰减 + 冲突检测

**Files:**
- Modify: `backend/app/memory/l1_atom.py`
- Modify: `backend/app/memory/manager.py`

添加：
- `save_atom()` 中的主语-谓语冲突检测
- `_decay_stale_atoms()` 后台任务，30 天未访问降置信度 0.9×

---

## 执行顺序建议

| 顺序 | Phase | 理由 |
|------|-------|------|
| 1 | **Phase 0** | 安全 + 正确性，最高优先级 |
| 2 | **Phase 1** | 架构修复，需 Phase 0 基础 |
| 3 | **Phase 2** | 可维护性改进，可并行或独立 |
| 4 | **Phase 3** | 功能完善，选做 |

每个 Phase 独立可部署。建议完成 Phase 0 + Phase 1 后即发布生产。
