# WebSocket 统一重构 + 浏览器崩溃修复

## 背景

Railway 重新部署后，所有页面打开即卡顿，最终浏览器 tab 崩溃。根因分析发现 5 个核心问题：

1. **WebSocket 无限重连风暴** — `maxReconnectAttempts: Infinity` + 多组件同时重连
2. **useWebSocket Effect 依赖不稳定** — 内联回调每次 render 都是新引用，导致 Effect 不断清理/重建连接
3. **2 秒 interval patchMessageHandler** — 轮询覆盖 `ws.onmessage`，造成 handler 丢失和 GC 压力
4. **两套 WebSocket 实现并存** — `services/websocket.ts`（死代码）和 `services/ws.ts`
5. **Dashboard 3 个并发 WebSocket** — 原生 WS + useRealtimeMetrics + useCostData

## 目标

- 消除浏览器崩溃和卡顿
- 统一为单一 WebSocket 实现
- 限制重连次数，添加智能退避
- 减少 Dashboard 页面 WebSocket 数量（3 → 1）
- 延迟非必要 WebSocket 初始化

## 设计

### 1. 统一 WebSocket 实现

**删除** `src/services/websocket.ts`（`AureonWebSocket` 类）— 无任何文件导入，是死代码。

**增强** `src/services/ws.ts` 的 `createWebSocket`：

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

**重连策略变更**：
- `maxReconnectAttempts` 默认 10（可配置）
- 指数退避 + 随机抖动：`delay = min(initial * 2^attempt + random(0,1000), maxDelay)`
- **致命状态码不重连**：4001 (Unauthorized)、1013 (Too Many Connections)
- **Page Visibility API**（在 `ws.ts` 中实现）：标签页隐藏时暂停重连定时器，可见时立即尝试重连

### 2. 重写 useWebSocket Hook

**核心变更**：回调函数不再出现在 Effect 依赖数组中。

```ts
// 回调通过 ref 持有
const onMessageRef = useRef(options.onMessage);
const onOpenRef = useRef(options.onOpen);
const onCloseRef = useRef(options.onClose);
const onErrorRef = useRef(options.onError);

// 每次 render 更新 ref
useEffect(() => { onMessageRef.current = options.onMessage; }, [options.onMessage]);
// ...

// Effect 仅依赖 path 和 autoReconnect
useEffect(() => {
  // 空路径 = 延迟挂载，跳过连接
  if (!path) return;

  const client = createWebSocket(path, {
    maxReconnectAttempts: autoReconnect ? 10 : 0,
    reconnectJitter: true,
  });

  // 内部回调通过 ref 间接调用
  client.onStateChange = (state) => {
    setConnectionState(state);
    setIsConnected(state === 'connected');
  };

  // 直接在 ws 层绑定 message handler，不再需要 interval 轮询
  // ...

  client.connect();

  return () => {
    client.disconnect();
    clientRef.current = null;
  };
}, [path, autoReconnect]);  // ← 仅这两个依赖
```

**删除** 2 秒 `setInterval` 的 `patchMessageHandler`：改为在 `ws.ts` 的 `onopen` 回调中直接绑定 `onmessage`。

### 3. Dashboard WebSocket 统一

**删除** `Dashboard.tsx` 中的原生 WebSocket 代码（L268-L310）：
- `connectWebSocket` 函数
- `wsRef`、`reconnectTimerRef`、`connectRef`
- 手动重连逻辑

**改为** 直接使用 `useRealtimeMetrics()` hook：
```tsx
const { metrics: realtimeMetrics, isConnected: wsConnected, alerts: realtimeAlerts } = useRealtimeMetrics();
```

**结果**：Dashboard 页面从 3 个 WebSocket 连接减少到 1 个。

### 4. SupportWidget 延迟挂载

SupportWidget 在所有非 login 页面渲染，立即创建 WebSocket 连接会增加首屏压力。

**方案**：
```tsx
// 延迟 3 秒后再挂载 WebSocket 连接
const [deferred, setDeferred] = useState(false);
useEffect(() => {
  const timer = setTimeout(() => setDeferred(true), 3000);
  return () => clearTimeout(timer);
}, []);

// WebSocket 仅在 deferred=true 后初始化
const { isConnected, send } = useWebSocket(
  deferred ? `/ws/chat/${SUPPORT_CLIENT_ID}` : '',
  { autoReconnect: true, onMessage: ... }
);
```

### 5. 字体加载优化

`index.html` 添加 `font-display` 预加载提示：
```html
<link rel="preload" href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800&family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" as="style" />
```

## 影响范围

| 文件 | 操作 | 风险 |
|------|------|------|
| `src/services/websocket.ts` | 删除 | 低（无引用） |
| `src/services/ws.ts` | 增强 | 中（需测试重连逻辑） |
| `src/hooks/useWebSocket.ts` | 重写 | 中（核心 hook） |
| `src/hooks/useRealtimeMetrics.ts` | 微调 | 低 |
| `src/hooks/useCostData.ts` | 微调 | 低 |
| `src/pages/Dashboard.tsx` | 删除原生 WS | 中 |
| `src/components/SupportWidget.tsx` | 延迟挂载 | 低 |
| `index.html` | 字体预加载 | 低 |

## 验证方案

1. **单元测试**：`useWebSocket` hook 的 ref 稳定性、重连上限
2. **前端冒烟测试**：`npm test -- --run` 确保所有测试通过
3. **手动验证**：
   - 打开首页 → 不再卡顿
   - 打开 Dashboard → 仅 1 个 WebSocket 连接（DevTools Network 面板确认）
   - 断开后端 → 重连 10 次后停止（不再无限循环）
   - 隐藏标签页 → 重连暂停
4. **Railway 部署后验证**：`curl /api/health` + 浏览器打开确认不崩溃

## 非目标

- 不修改后端 WebSocket 端点
- 不修改 SSE 流式处理（`useChat.ts` 使用 SSE 不受影响）
- 不修改 Nivo 图表（已在上一提交中修复）
- 不修改认证流程
