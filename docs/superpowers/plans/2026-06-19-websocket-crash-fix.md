# WebSocket 统一重构 + 浏览器崩溃修复 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复所有页面打开即卡顿和浏览器崩溃的问题，统一 WebSocket 实现，限制重连次数，减少冗余连接。

**Architecture:** 增强 `ws.ts` 的 `createWebSocket` 工厂（重连上限、抖动、致命码、Page Visibility API），重写 `useWebSocket` hook（ref 化回调、精简 Effect 依赖），删除 Dashboard 原生 WebSocket 代码，延迟 SupportWidget 挂载。

**Tech Stack:** React 19, TypeScript, Vite, Vitest

**Spec:** `docs/superpowers/specs/2026-06-19-websocket-crash-fix-design.md`

---

### Task 1: 删除死代码 `services/websocket.ts`

**Files:**
- Delete: `src/services/websocket.ts`

- [ ] **Step 1: 确认无引用**

Run: `cd "c:\Users\Yum\Desktop\Aureon-test" && npx grep -r "services/websocket" src/ --include="*.ts" --include="*.tsx" | grep -v "node_modules"`

Expected: 0 matches (该文件无任何导入)

- [ ] **Step 2: 删除文件**

删除 `src/services/websocket.ts`

- [ ] **Step 3: 验证构建**

Run: `cd "c:\Users\Yum\Desktop\Aureon-test" && npx tsc -b --noEmit`

Expected: 无编译错误

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "refactor: remove dead AureonWebSocket class (services/websocket.ts)"
```

---

### Task 2: 增强 `ws.ts` — 重连策略 + 回调 setter + Page Visibility

**Files:**
- Modify: `src/services/ws.ts`

- [ ] **Step 1: 增强 WSConfig 接口**

在 `src/services/ws.ts` 的 `WSConfig` 接口中添加：

```ts
interface WSConfig {
  heartbeatInterval?: number;       // 默认 30_000
  initialReconnectDelay?: number;   // 默认 1_000
  maxReconnectDelay?: number;       // 默认 30_000
  maxReconnectAttempts?: number;    // 默认 10（不再是 Infinity）
  reconnectJitter?: boolean;        // 新增：随机 0-1000ms 抖动
  fatalCloseCodes?: number[];       // 新增：不重连的状态码
}
```

默认值变更：
```ts
const {
  heartbeatInterval = 30_000,
  initialReconnectDelay = 1_000,
  maxReconnectDelay = 30_000,
  maxReconnectAttempts = 10,        // 从 Infinity → 10
  reconnectJitter = false,          // 新增
  fatalCloseCodes = [4001, 1013],   // 新增
} = config;
```

- [ ] **Step 2: 添加回调 setter**

在 `createWebSocket` 函数内部添加回调变量和 setter，与 `onStateChange` 模式一致：

```ts
let onMessageHandler: ((data: unknown) => void) | undefined;
let onOpenHandler: (() => void) | undefined;
let onCloseHandler: (() => void) | undefined;
```

在返回对象中添加 setter：

```ts
return {
  // ...existing...
  get onMessage() { return onMessageHandler; },
  set onMessage(handler: ((data: unknown) => void) | undefined) { onMessageHandler = handler; },
  get onOpen() { return onOpenHandler; },
  set onOpen(handler: (() => void) | undefined) { onOpenHandler = handler; },
  get onClose() { return onCloseHandler; },
  set onClose(handler: (() => void) | undefined) { onCloseHandler = handler; },
};
```

- [ ] **Step 3: 在 `connect()` 内部绑定消息解析**

在 `ws.onopen` 之后添加 `ws.onmessage` 内部处理：

```ts
ws.onopen = () => {
  reconnectAttempts = 0;
  setState('connected');
  startHeartbeat();
  onOpenHandler?.();
};

ws.onmessage = (event: MessageEvent) => {
  try {
    const data = JSON.parse(event.data);
    if (data.type === 'pong' || data.type === 'heartbeat_ack') return;
    onMessageHandler?.(data);
  } catch {
    onMessageHandler?.(event.data);
  }
};
```

- [ ] **Step 4: 增强重连逻辑 — 抖动 + 致命码检测**

修改 `getReconnectDelay` 添加抖动：

```ts
function getReconnectDelay(): number {
  const base = initialReconnectDelay * Math.pow(2, reconnectAttempts);
  const jitter = reconnectJitter ? Math.random() * 1000 : 0;
  return Math.min(base + jitter, maxReconnectDelay);
}
```

修改 `ws.onclose` 添加致命码检测：

```ts
ws.onclose = (event: CloseEvent) => {
  stopHeartbeat();
  onCloseHandler?.();
  if (!intentionalClose && !fatalCloseCodes.includes(event.code)) {
    setState('disconnected');
    tryReconnect();
  } else {
    setState('disconnected');
  }
};
```

- [ ] **Step 5: 添加 Page Visibility API**

在 `connect()` 函数的 `ws.onopen` 之前添加 visibility listener：

```ts
// Page Visibility — 标签页隐藏时暂停重连，可见时恢复
const handleVisibility = () => {
  if (document.hidden) {
    // 暂停重连定时器
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  } else if (!intentionalClose && ws?.readyState !== WebSocket.OPEN) {
    // 可见时立即尝试重连
    if (reconnectAttempts < maxReconnectAttempts) {
      connect();
    }
  }
};
document.addEventListener('visibilitychange', handleVisibility);
```

在 `disconnect()` 中清理：

```ts
function disconnect(): void {
  intentionalClose = true;
  stopHeartbeat();
  document.removeEventListener('visibilitychange', handleVisibility);
  // ...rest...
}
```

注意：`handleVisibility` 需要在 `connect()` 内部定义才能访问闭包变量，或者将 visibility 处理提取为模块级函数。推荐在 `connect()` 内定义并通过 `disconnect()` 清理。

- [ ] **Step 6: 验证构建**

Run: `cd "c:\Users\Yum\Desktop\Aureon-test" && npx tsc -b --noEmit`

Expected: 无编译错误

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat: enhance ws.ts — reconnect limit, jitter, fatal codes, visibility API"
```

---

### Task 3: 重写 `useWebSocket.ts` — ref 化回调 + 精简依赖

**Files:**
- Rewrite: `src/hooks/useWebSocket.ts`

- [ ] **Step 1: 完整重写 useWebSocket.ts**

```ts
import { useState, useEffect, useRef, useCallback } from 'react';
import { createWebSocket, type WSConnectionState } from '../services/ws';

interface UseWebSocketOptions {
  onMessage?: (data: unknown) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
  autoReconnect?: boolean;
}

interface UseWebSocketReturn {
  isConnected: boolean;
  send: (data: string | object) => void;
  lastMessage: unknown;
  connect: () => void;
  disconnect: () => void;
  connectionState: WSConnectionState;
}

export function useWebSocket(
  path: string,
  options: UseWebSocketOptions = {},
): UseWebSocketReturn {
  const { autoReconnect = true } = options;

  // 回调通过 ref 持有，不触发 Effect 重建
  const onMessageRef = useRef(options.onMessage);
  const onOpenRef = useRef(options.onOpen);
  const onCloseRef = useRef(options.onClose);
  const onErrorRef = useRef(options.onError);

  useEffect(() => { onMessageRef.current = options.onMessage; }, [options.onMessage]);
  useEffect(() => { onOpenRef.current = options.onOpen; }, [options.onOpen]);
  useEffect(() => { onCloseRef.current = options.onClose; }, [options.onClose]);
  useEffect(() => { onErrorRef.current = options.onError; }, [options.onError]);

  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<unknown>(null);
  const [connectionState, setConnectionState] = useState<WSConnectionState>('disconnected');
  const clientRef = useRef<ReturnType<typeof createWebSocket> | null>(null);

  // Effect 仅依赖 path 和 autoReconnect
  useEffect(() => {
    if (!path) return;  // 空路径 = 延迟挂载，跳过连接

    const client = createWebSocket(path, {
      maxReconnectAttempts: autoReconnect ? 10 : 0,
      reconnectJitter: true,
      fatalCloseCodes: [4001, 1013],
    });

    clientRef.current = client;

    // 回调通过 ref 间接调用 — 不进入 Effect 依赖
    client.onMessage = (data) => {
      setLastMessage(data);
      onMessageRef.current?.(data);
    };

    client.onOpen = () => {
      onOpenRef.current?.();
    };

    client.onClose = () => {
      onCloseRef.current?.();
    };

    client.onStateChange = (state) => {
      setConnectionState(state);
      setIsConnected(state === 'connected');
    };

    client.connect();

    return () => {
      client.disconnect();
      clientRef.current = null;
    };
  }, [path, autoReconnect]);

  const send = useCallback((data: string | object) => {
    clientRef.current?.send(data);
  }, []);

  const connect = useCallback(() => {
    clientRef.current?.connect();
  }, []);

  const disconnect = useCallback(() => {
    clientRef.current?.disconnect();
  }, []);

  return { isConnected, send, lastMessage, connect, disconnect, connectionState };
}
```

- [ ] **Step 2: 验证构建**

Run: `cd "c:\Users\Yum\Desktop\Aureon-test" && npx tsc -b --noEmit`

Expected: 无编译错误（返回类型不变，消费者无需修改）

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "refactor: rewrite useWebSocket — ref-based callbacks, stable Effect deps"
```

---

### Task 4: 重构 Dashboard — 删除原生 WebSocket，使用 useRealtimeMetrics

**Files:**
- Modify: `src/pages/Dashboard.tsx`

- [ ] **Step 1: 删除原生 WebSocket 代码**

从 `Dashboard.tsx` 中删除以下代码块：
1. 删除 `RealtimeMetrics` 接口定义（L14-24）
2. 删除 `AlertMessage` 接口定义（L27-33）
3. 删除 `wsRef`、`reconnectTimerRef`、`connectRef` state/ref（L263-265）
4. 删除 `connectWebSocket` callback 和关联 useEffect（L268-310）
5. 删除 `realtimeData` 和 `wsConnected` useState（L258-259）
6. 删除 `alerts` useState（L260）

替换为：

```tsx
import { useRealtimeMetrics } from '../hooks/useRealtimeMetrics';

// 在 Dashboard 组件内部
const { metrics: realtimeMetrics, isConnected: wsConnected, alerts: realtimeAlerts } = useRealtimeMetrics();
```

- [ ] **Step 2: 更新 metrics 和 alerts 引用**

更新组件中使用 `realtimeData` 和 `alerts` 的地方：

```tsx
// 旧: const metrics = realtimeData || (stats ? { ... } : null);
// 新:
const metrics = realtimeMetrics ?? (stats ? {
  ttft_p50: stats.avg_retrieval_latency_ms || 590,
  ttft_p95: 1677,
  qps: Math.round((stats.query_count_24h || 0) / 86400 * 100) / 100,
  error_rate: 0.5,
  saturation: 65,
  alert_count: 0,
  latency_trend: [],
  tpot_trend: [],
  e2e_trend: [],
} : null);

// alerts 引用替换
// 旧: alerts.length, alerts.filter(...)
// 新: realtimeAlerts.length, realtimeAlerts.filter(...)
```

注意：`useRealtimeMetrics` 的 `RealtimeMetrics` 接口与 Dashboard 的旧接口字段略有不同（如 `saturation` 不在 realtime 接口中）。需要在合并 metrics 时保留 fallback 值。

- [ ] **Step 3: 更新 AlertRow 组件使用 realtimeAlerts 的类型**

`useRealtimeMetrics` 返回 `MetricAlert` 类型（含 `id`, `level`, `message`, `timestamp`），而旧 `AlertMessage` 用 `severity`。需要适配：

```tsx
// MetricAlert.level → severity 映射
const severity = alert.level === 'critical' ? 'critical' : alert.level === 'warning' ? 'warning' : 'info';
```

或者在 `AlertRow` 中直接使用 `level` 字段。

- [ ] **Step 4: 验证构建**

Run: `cd "c:\Users\Yum\Desktop\Aureon-test" && npx tsc -b --noEmit`

Expected: 无编译错误

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "refactor: Dashboard — remove native WebSocket, use useRealtimeMetrics hook"
```

---

### Task 5: SupportWidget 延迟挂载

**Files:**
- Modify: `src/components/SupportWidget.tsx`

- [ ] **Step 1: 添加延迟挂载逻辑**

在 `SupportWidget` 组件开头添加：

```tsx
const [deferred, setDeferred] = useState(false);
useEffect(() => {
  const timer = setTimeout(() => setDeferred(true), 3000);
  return () => clearTimeout(timer);
}, []);
```

修改 `useWebSocket` 调用，传入条件路径：

```tsx
const {
  isConnected,
  send,
} = useWebSocket(deferred ? `/ws/chat/${SUPPORT_CLIENT_ID}` : '', {
  autoReconnect: true,
  onMessage: (data) => { /* ...不变... */ },
  onError: () => { /* ...不变... */ },
});
```

当 `path` 为空字符串时，`useWebSocket` 的 Effect 会 early return，不创建 WebSocket。

- [ ] **Step 2: 验证构建**

Run: `cd "c:\Users\Yum\Desktop\Aureon-test" && npx tsc -b --noEmit`

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "perf: defer SupportWidget WebSocket mount by 3 seconds"
```

---

### Task 6: 字体预加载优化

**Files:**
- Modify: `index.html`

- [ ] **Step 1: 添加 font preload link**

在 `index.html` 的 `<head>` 中，Google Fonts `<link>` 标签之前添加：

```html
<link rel="preload" href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800&family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" as="style" />
```

- [ ] **Step 2: Commit**

```bash
git add -A && git commit -m "perf: preload Google Fonts CSS to reduce render blocking"
```

---

### Task 7: 运行前端测试 + 修复

**Files:**
- Test: 运行全量前端测试

- [ ] **Step 1: 运行 Vitest**

Run: `cd "c:\Users\Yum\Desktop\Aureon-test" && npm test -- --run`

Expected: 所有测试通过。如有失败，根据错误信息修复。

**可能需要的修复**：
- `SupportWidget.test.tsx` 中的 mock 可能需要更新以匹配新的 `useWebSocket` 返回类型（但类型未变，应无需修改）
- 如果 Dashboard 相关测试引用了旧的 `realtimeData` state，需要更新

- [ ] **Step 2: 运行 ESLint**

Run: `cd "c:\Users\Yum\Desktop\Aureon-test" && npx eslint src/ --max-warnings 0`

Expected: 无 lint 错误

- [ ] **Step 3: 运行 TypeScript 构建**

Run: `cd "c:\Users\Yum\Desktop\Aureon-test" && npm run build`

Expected: 构建成功

- [ ] **Step 4: 修复所有失败的测试和 lint 错误**

根据 Task 7 Step 1-3 的输出，修复所有问题。常见问题：
- 类型不匹配 → 调整类型定义
- mock 数据不完整 → 补充 mock 字段
- import 路径错误 → 更新 import

- [ ] **Step 5: 最终 Commit**

```bash
git add -A && git commit -m "test: fix tests after WebSocket refactor"
```

---

### Task 8: 手动验证

- [ ] **Step 1: 启动开发服务器**

Run: `cd "c:\Users\Yum\Desktop\Aureon-test" && npm run dev`

- [ ] **Step 2: 验证首页不卡顿**

在浏览器打开 `http://localhost:5173`，确认：
- 页面在 3 秒内完全加载
- 无卡顿或卡死现象
- DevTools Console 无 WebSocket 错误洪水

- [ ] **Step 3: 验证 Dashboard WebSocket 数量**

打开 `http://localhost:5173/dashboard`，在 DevTools Network → WS 标签确认：
- 最多 1 个活跃 WebSocket 连接（`/ws/dashboard`）
- 无重复连接

- [ ] **Step 4: 验证重连上限**

停止后端（或不启动后端），观察 DevTools Console：
- WebSocket 尝试重连，次数有限（约 10 次）
- 重连停止后不再创建新连接
- 无内存泄漏（DevTools Memory 标签）

- [ ] **Step 5: Commit all remaining changes**

```bash
git add -A && git commit -m "chore: final cleanup after WebSocket refactor"
```
