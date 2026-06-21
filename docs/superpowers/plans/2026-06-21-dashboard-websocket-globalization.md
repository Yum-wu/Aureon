# Dashboard WebSocket 全局化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `/ws/dashboard` 实时指标连接从页面组件上提到应用根 Provider，路由切换不再重建 WebSocket 连接，消除每次进入仪表盘的握手延迟与"首条 tick 等待"。

**Architecture:** 新建 `RealtimeMetricsProvider`（React Context），在应用根挂载**唯一一次** `useWebSocket('/ws/dashboard')`，内部维护 `metrics`/`alerts`/`lastUpdated` 状态并沿用现有 stale timeout 逻辑。Dashboard 和 CostGovernance 页面通过 `useRealtimeMetricsContext()` 消费，不再各自调用 WebSocket hook。保留 `useRealtimeMetrics` 导出作为**向后兼容的薄封装**（内部改为读 Context，便于现有 import 不必全改）。

**Tech Stack:** React 19 Context API、现有 `useWebSocket` hook、现有 `ws.ts` 客户端（不改）、Vitest + Testing Library。

---

## 背景与诊断

**问题现象**：每次切换回仪表盘页面，系统都会重新建立 WebSocket 连接。

**根因**（见诊断报告结论 2）：`useRealtimeMetrics.ts:130` 在组件内调用 `useWebSocket('/ws/dashboard')`，而 `useWebSocket.ts:97-100` 在组件卸载时 `disconnect()`。路由切换 → `<Dashboard>` 卸载 → WS 连接销毁 → 重新进入 → 重新握手 + 等待首条 tick（后端 5s 推送周期）。

**加剧因素**：`useCostData.ts:228` 也连接同一个 `/ws/dashboard`，意味着 `/cost` ↔ `/dashboard` 之间切换会有两个消费者各自重连。

**业界依据**：ServiceNow 多 Tab 懒加载案例——实时数据连接应"上提到应用层"，导航即重建连接会带来 200-500ms TLS+WS 握手 + 首条消息等待。

---

## File Structure

| 文件 | 职责 | 操作 |
|------|------|------|
| `src/providers/RealtimeMetricsProvider.tsx` | 全局 Context Provider，挂载唯一 WS | **新建** |
| `src/hooks/useRealtimeMetrics.ts` | 改为薄封装，读 Context（向后兼容） | **重写** |
| `src/App.tsx` | 在 Provider 树中挂载 RealtimeMetricsProvider | **修改** |
| `src/providers/__tests__/RealtimeMetricsProvider.test.tsx` | Provider 集成测试 | **新建** |
| `src/hooks/__tests__/useRealtimeMetrics.test.tsx` | 适配 Context（测试改为包装 Provider） | **修改** |

---

## Task 1: 编写 RealtimeMetricsProvider 测试

**Files:**
- Create: `src/providers/__tests__/RealtimeMetricsProvider.test.tsx`

- [ ] **Step 1: 编写失败的测试**

Create `src/providers/__tests__/RealtimeMetricsProvider.test.tsx`:
```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, renderHook, act } from '@testing-library/react';
import React from 'react';

// Mock useWebSocket — 捕获 onMessage 回调供测试主动触发
let mockOnMessage: ((data: unknown) => void) | null = null;
let mockIsConnected = false;
let mockConnectionState = 'disconnected';

vi.mock('../../hooks/useWebSocket', () => ({
  useWebSocket: (_path: string, opts: { onMessage?: (data: unknown) => void }) => {
    mockOnMessage = opts.onMessage ?? null;
    return {
      isConnected: mockIsConnected,
      connectionState: mockConnectionState,
    };
  },
}));

import {
  RealtimeMetricsProvider,
  useRealtimeMetricsContext,
} from '../RealtimeMetricsProvider';

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <RealtimeMetricsProvider>{children}</RealtimeMetricsProvider>
);

const SAMPLE_TICK = {
  qps: 1.5,
  ttft_p50: 120,
  ttft_p95: 250,
  tpot: 40,
  error_rate: 0.01,
  cache_hit_rate: 0.85,
  token_usage: 2000,
  active_connections: 5,
  pipeline: { retrieval_ms: 80, generation_ms: 200 },
};

describe('RealtimeMetricsProvider', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    mockOnMessage = null;
    mockIsConnected = false;
    mockConnectionState = 'disconnected';
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('provides default metrics before any tick', () => {
    const { result } = renderHook(() => useRealtimeMetricsContext(), { wrapper });
    expect(result.current.metrics.qps).toBe(0);
    expect(result.current.metrics.ttft_p50).toBe(0);
    expect(result.current.lastUpdated).toBeNull();
    expect(result.current.alerts).toEqual([]);
  });

  it('updates metrics when tick arrives', () => {
    const { result } = renderHook(() => useRealtimeMetricsContext(), { wrapper });

    act(() => {
      mockOnMessage?.({ type: 'metrics.tick', data: SAMPLE_TICK });
    });

    expect(result.current.metrics.qps).toBe(1.5);
    expect(result.current.metrics.ttft_p50).toBe(120);
    expect(result.current.metrics.pipeline.retrieval_ms).toBe(80);
    expect(result.current.lastUpdated).not.toBeNull();
  });

  it('exposes connection state', () => {
    mockIsConnected = true;
    mockConnectionState = 'connected';
    const { result } = renderHook(() => useRealtimeMetricsContext(), { wrapper });
    expect(result.current.isConnected).toBe(true);
    expect(result.current.connectionState).toBe('connected');
  });

  it('collects alerts', () => {
    const { result } = renderHook(() => useRealtimeMetricsContext(), { wrapper });

    act(() => {
      mockOnMessage?.({
        type: 'alert',
        data: { id: 'a1', level: 'critical', message: 'High error rate', timestamp: 1700000000000 },
      });
    });

    expect(result.current.alerts).toHaveLength(1);
    expect(result.current.alerts[0].message).toBe('High error rate');
  });

  it('shares state across multiple consumers (single WS connection)', () => {
    const { result: r1 } = renderHook(() => useRealtimeMetricsContext(), { wrapper });
    const { result: r2 } = renderHook(() => useRealtimeMetricsContext(), { wrapper });

    act(() => {
      mockOnMessage?.({ type: 'metrics.tick', data: SAMPLE_TICK });
    });

    // 两个消费者共享同一份状态
    expect(r1.current.metrics.qps).toBe(1.5);
    expect(r2.current.metrics.qps).toBe(1.5);
  });

  it('throws when used outside provider', () => {
    // 抑制 React error boundary 噪音
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => renderHook(() => useRealtimeMetricsContext())).toThrow();
    spy.mockRestore();
  });
});
```

- [ ] **Step 2: 运行测试验证失败**

Run: `npx vitest run src/providers/__tests__/RealtimeMetricsProvider.test.tsx`
Expected: FAIL，报错 `Cannot find module '../RealtimeMetricsProvider'`。

---

## Task 2: 实现 RealtimeMetricsProvider

**Files:**
- Create: `src/providers/RealtimeMetricsProvider.tsx`

- [ ] **Step 1: 实现 Provider 与 Context**

Create `src/providers/RealtimeMetricsProvider.tsx`:
```typescript
/**
 * RealtimeMetricsProvider — 全局实时指标 Context
 *
 * 在应用根挂载唯一一次 /ws/dashboard 连接，
 * 通过 Context 向所有页面共享 metrics/alerts/connectionState。
 *
 * 设计要点：
 * - WS 连接生命周期脱离页面组件，路由切换不重建连接
 * - 沿用 useRealtimeMetrics 的 stale timeout 逻辑（15s 无 tick 则标记不可用）
 * - 多个消费者共享同一份状态，避免重复连接
 */

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
  type ReactNode,
} from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import type { WSConnectionState } from '../services/ws';
import { REALTIME_STALE_THRESHOLD_MS } from '../hooks/useRealtimeMetrics';

/** 流水线阶段延迟 */
export interface PipelineStages {
  retrieval_ms?: number;
  rerank_ms?: number;
  crag_ms?: number;
  generation_ms?: number;
}

/** 实时指标数据 */
export interface RealtimeMetrics {
  qps: number;
  ttft_p50: number;
  ttft_p95: number;
  tpot: number;
  error_rate: number;
  cache_hit_rate: number;
  token_usage: number;
  active_connections: number;
  pipeline: PipelineStages;
}

/** 告警信息 */
export interface MetricAlert {
  id: string;
  level: 'warning' | 'critical';
  message: string;
  timestamp: number;
}

interface RealtimeMetricsContextValue {
  metrics: RealtimeMetrics;
  alerts: MetricAlert[];
  isConnected: boolean;
  connectionState: WSConnectionState;
  lastUpdated: number | null;
}

const DEFAULT_METRICS: RealtimeMetrics = {
  qps: 0,
  ttft_p50: 0,
  ttft_p95: 0,
  tpot: 0,
  error_rate: 0,
  cache_hit_rate: 0,
  token_usage: 0,
  active_connections: 0,
  pipeline: {},
};

const RealtimeMetricsContext = createContext<RealtimeMetricsContextValue | null>(null);

export function RealtimeMetricsProvider({ children }: { children: ReactNode }) {
  const [metrics, setMetrics] = useState<RealtimeMetrics>(DEFAULT_METRICS);
  const [alerts, setAlerts] = useState<MetricAlert[]>([]);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const staleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const resetLastUpdated = useCallback(() => {
    setLastUpdated(null);
  }, []);

  const handleMessage = useCallback((data: unknown) => {
    if (!data || typeof data !== 'object') return;
    const msg = data as Record<string, unknown>;

    if (msg.type === 'metrics.tick' && msg.data) {
      const tickData = msg.data as Record<string, unknown>;
      const rawPipeline = tickData.pipeline as Record<string, number> | undefined;
      setMetrics({
        qps: Number(tickData.qps ?? 0),
        ttft_p50: Number(tickData.ttft_p50 ?? 0),
        ttft_p95: Number(tickData.ttft_p95 ?? 0),
        tpot: Number(tickData.tpot ?? 0),
        error_rate: Number(tickData.error_rate ?? 0),
        cache_hit_rate: Number(tickData.cache_hit_rate ?? 0),
        token_usage: Number(tickData.token_usage ?? 0),
        active_connections: Number(tickData.active_connections ?? 0),
        pipeline: rawPipeline ? {
          retrieval_ms: rawPipeline.retrieval_ms,
          rerank_ms: rawPipeline.rerank_ms,
          crag_ms: rawPipeline.crag_ms,
          generation_ms: rawPipeline.generation_ms,
        } : {},
      });
      setLastUpdated(Date.now());

      if (staleTimerRef.current) clearTimeout(staleTimerRef.current);
      staleTimerRef.current = setTimeout(resetLastUpdated, REALTIME_STALE_THRESHOLD_MS);
    }

    if (msg.type === 'alert' && msg.data) {
      const alertData = msg.data as MetricAlert;
      setAlerts((prev) => [alertData, ...prev].slice(0, 50));
    }
  }, [resetLastUpdated]);

  const { isConnected, connectionState } = useWebSocket('/ws/dashboard', {
    onMessage: handleMessage,
    autoReconnect: true,
  });

  // WS 断开 → 立即标记不可用
  useEffect(() => {
    if (!isConnected) {
      resetLastUpdated();
      if (staleTimerRef.current) {
        clearTimeout(staleTimerRef.current);
        staleTimerRef.current = null;
      }
    }
  }, [isConnected, resetLastUpdated]);

  // 清理计时器
  useEffect(() => {
    return () => {
      if (staleTimerRef.current) clearTimeout(staleTimerRef.current);
    };
  }, []);

  const value: RealtimeMetricsContextValue = {
    metrics,
    alerts,
    isConnected,
    connectionState,
    lastUpdated,
  };

  return (
    <RealtimeMetricsContext.Provider value={value}>
      {children}
    </RealtimeMetricsContext.Provider>
  );
}

/**
 * 消费全局实时指标。
 * 必须在 RealtimeMetricsProvider 内使用，否则抛错（快速暴露误用）。
 */
export function useRealtimeMetricsContext(): RealtimeMetricsContextValue {
  const ctx = useContext(RealtimeMetricsContext);
  if (!ctx) {
    throw new Error('useRealtimeMetricsContext must be used within RealtimeMetricsProvider');
  }
  return ctx;
}
```

- [ ] **Step 2: 运行测试验证通过**

Run: `npx vitest run src/providers/__tests__/RealtimeMetricsProvider.test.tsx`
Expected: PASS（6 个测试全通过）。

- [ ] **Step 3: Commit**

```bash
git add src/providers/RealtimeMetricsProvider.tsx src/providers/__tests__/RealtimeMetricsProvider.test.tsx
git commit -m "feat(realtime): add RealtimeMetricsProvider with global WS connection"
```

---

## Task 3: 改造 useRealtimeMetrics 为薄封装（向后兼容）

**Files:**
- Modify: `src/hooks/useRealtimeMetrics.ts`（全文重写）

**目的**：Dashboard.tsx 当前 `import { useRealtimeMetrics } from '../hooks/useRealtimeMetrics'`。为最小化改动，将这个 hook 改为"读 Context 的薄封装"，保持原有返回类型签名不变。

- [ ] **Step 1: 重写 useRealtimeMetrics.ts**

Replace entire content of `src/hooks/useRealtimeMetrics.ts`:
```typescript
/**
 * useRealtimeMetrics — 向后兼容的薄封装
 *
 * 历史上此 hook 直接调用 useWebSocket。现已将 WS 连接上提到
 * RealtimeMetricsProvider（应用根），此 hook 仅做 Context 转发，
 * 保持现有 import 不必改动。
 *
 * 新代码请直接使用 useRealtimeMetricsContext()。
 */

import { useRealtimeMetricsContext } from '../providers/RealtimeMetricsProvider';

// Re-export 类型，保持现有 import 路径可用
export type {
  RealtimeMetrics,
  PipelineStages,
  MetricAlert,
} from '../providers/RealtimeMetricsProvider';

/** WebSocket 指标数据过期阈值（毫秒）。超过此时间未收到新 tick 则视为数据不可用。 */
export const REALTIME_STALE_THRESHOLD_MS = 15_000; // 15 秒 = 3 个 tick 周期

export interface UseRealtimeMetricsReturn {
  metrics: import('../providers/RealtimeMetricsProvider').RealtimeMetrics;
  alerts: import('../providers/RealtimeMetricsProvider').MetricAlert[];
  isConnected: boolean;
  connectionState: import('../services/ws').WSConnectionState;
  lastUpdated: number | null;
}

export function useRealtimeMetrics(): UseRealtimeMetricsReturn {
  return useRealtimeMetricsContext();
}
```

- [ ] **Step 2: 适配现有 useRealtimeMetrics 测试**

Modify `src/hooks/__tests__/useRealtimeMetrics.test.tsx`。由于现在 hook 依赖 Context，测试 wrapper 需要包装 `RealtimeMetricsProvider`，且 mock 目标改为 Context 内部使用的 `useWebSocket`。

Replace entire content of `src/hooks/__tests__/useRealtimeMetrics.test.tsx`:
```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import React from 'react';

// Mock useWebSocket（被 RealtimeMetricsProvider 内部调用）
const mockOnMessage = vi.fn();
let mockIsConnected = true;
let mockConnectionState = 'connected' as string;

vi.mock('../../hooks/useWebSocket', () => ({
  useWebSocket: (_path: string, opts: { onMessage?: (data: unknown) => void }) => {
    mockOnMessage.mockImplementation(opts.onMessage ?? (() => {}));
    return {
      isConnected: mockIsConnected,
      connectionState: mockConnectionState,
    };
  },
}));

import { useRealtimeMetrics, REALTIME_STALE_THRESHOLD_MS } from '../useRealtimeMetrics';
import { RealtimeMetricsProvider } from '../../providers/RealtimeMetricsProvider';

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <RealtimeMetricsProvider>{children}</RealtimeMetricsProvider>
);

function emitTick(data: Record<string, unknown>) {
  mockOnMessage({ type: 'metrics.tick', data });
}

const SAMPLE_TICK = {
  qps: 1,
  ttft_p50: 100,
  ttft_p95: 200,
  tpot: 50,
  error_rate: 0,
  cache_hit_rate: 80,
  token_usage: 1000,
  active_connections: 3,
};

describe('useRealtimeMetrics (via Context) stale timeout', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    mockIsConnected = true;
    mockConnectionState = 'connected';
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('lastUpdated is null initially', () => {
    const { result } = renderHook(() => useRealtimeMetrics(), { wrapper });
    expect(result.current.lastUpdated).toBeNull();
  });

  it('sets lastUpdated when metrics.tick arrives', () => {
    const { result } = renderHook(() => useRealtimeMetrics(), { wrapper });

    act(() => {
      emitTick(SAMPLE_TICK);
    });

    expect(result.current.lastUpdated).not.toBeNull();
    expect(result.current.metrics?.qps).toBe(1);
  });

  it('resets lastUpdated to null after stale timeout', () => {
    const { result } = renderHook(() => useRealtimeMetrics(), { wrapper });

    act(() => {
      emitTick(SAMPLE_TICK);
    });

    expect(result.current.lastUpdated).not.toBeNull();

    act(() => {
      vi.advanceTimersByTime(REALTIME_STALE_THRESHOLD_MS + 1000);
    });

    expect(result.current.lastUpdated).toBeNull();
  });

  it('resets lastUpdated when WebSocket disconnects', () => {
    mockIsConnected = true;
    const { result, rerender } = renderHook(() => useRealtimeMetrics(), { wrapper });

    act(() => {
      emitTick(SAMPLE_TICK);
    });

    expect(result.current.lastUpdated).not.toBeNull();

    mockIsConnected = false;
    mockConnectionState = 'disconnected';
    rerender();

    expect(result.current.lastUpdated).toBeNull();
  });

  it('refreshes timeout when new tick arrives before expiry', () => {
    const { result } = renderHook(() => useRealtimeMetrics(), { wrapper });

    act(() => {
      emitTick(SAMPLE_TICK);
    });

    act(() => {
      vi.advanceTimersByTime(REALTIME_STALE_THRESHOLD_MS / 2);
    });

    act(() => {
      emitTick({ ...SAMPLE_TICK, qps: 2 });
    });

    expect(result.current.lastUpdated).not.toBeNull();

    act(() => {
      vi.advanceTimersByTime(REALTIME_STALE_THRESHOLD_MS / 2 + 1000);
    });

    expect(result.current.lastUpdated).not.toBeNull();
  });
});
```

- [ ] **Step 3: 运行测试验证通过**

Run: `npx vitest run src/hooks/__tests__/useRealtimeMetrics.test.tsx`
Expected: PASS（5 个测试全通过）。

- [ ] **Step 4: Commit**

```bash
git add src/hooks/useRealtimeMetrics.ts src/hooks/__tests__/useRealtimeMetrics.test.tsx
git commit -m "refactor(realtime): convert useRealtimeMetrics to thin Context wrapper"
```

---

## Task 4: 在 App.tsx 挂载 RealtimeMetricsProvider

**Files:**
- Modify: `src/App.tsx:241-256`（App 函数）

**关键决策**：Provider 应放在 `AuthProvider` 内（因为 WS 鉴权依赖 token）、`BrowserRouter` 内（不依赖路由，但放在这里保持一致）。实际上 WS URL 在 `ws.ts:79` 直接从 `sessionStorage` 读 token，不依赖 AuthContext，因此放在最外层也可。为最小化风险，放在 `AppLayout` 外层、`AuthProvider` 内层。

- [ ] **Step 1: 添加 import**

在 `src/App.tsx` 第 11 行（AdminGate import 后）添加：
```typescript
import { RealtimeMetricsProvider } from "./providers/RealtimeMetricsProvider";
```

- [ ] **Step 2: 在 App 函数中包裹 Provider**

Modify `src/App.tsx` 的 `App()` 函数（第 241-254 行），将 `<AppLayout />` 用 `RealtimeMetricsProvider` 包裹：
```typescript
function App() {
  return (
    <ErrorBoundary>
      <Toaster theme="dark" position="top-center" richColors closeButton />
      <BrowserRouter>
        <AuthProvider>
          <RealtimeMetricsProvider>
            <OnboardingProvider>
              <AppLayout />
            </OnboardingProvider>
          </RealtimeMetricsProvider>
        </AuthProvider>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
```

- [ ] **Step 3: 运行 Dashboard 页面测试确认无回归**

Run: `npx vitest run src/pages/__tests__/Dashboard.test.tsx`
Expected: PASS。

**注意**：Dashboard.test.tsx 第 64-67 行 mock 了 `useDashboardData`，但 `useRealtimeMetrics` 现在 → Context。测试中 Dashboard 渲染时调用 `useRealtimeMetrics` → `useRealtimeMetricsContext`，若没有 Provider 会抛错。

**若测试失败（抛 "must be used within RealtimeMetricsProvider"）**，需在 Dashboard.test.tsx 中也 mock `useRealtimeMetrics`。检查第 64-67 行区域，添加：
```typescript
// 在现有 vi.mock 区域追加
const mockUseRealtimeMetrics = vi.fn();
vi.mock('../../hooks/useRealtimeMetrics', () => ({
  useRealtimeMetrics: () => mockUseRealtimeMetrics(),
  REALTIME_STALE_THRESHOLD_MS: 15000,
}));
```
并在 `beforeEach` 中设置默认返回值：
```typescript
mockUseRealtimeMetrics.mockReturnValue({
  metrics: { qps: 0, ttft_p50: 0, ttft_p95: 0, tpot: 0, error_rate: 0, cache_hit_rate: 0, token_usage: 0, active_connections: 0, pipeline: {} },
  alerts: [],
  isConnected: false,
  connectionState: 'connecting',
  lastUpdated: null,
});
```

- [ ] **Step 4: 运行全量前端测试**

Run: `npm test -- --run`
Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add src/App.tsx src/pages/__tests__/Dashboard.test.tsx
git commit -m "feat(realtime): mount RealtimeMetricsProvider at app root"
```

---

## Task 5: 验证 CostGovernance 也受益（可选优化）

**Files:**
- Read: `src/hooks/useCostData.ts:228`

- [ ] **Step 1: 检查 useCostData 的 WS 用法**

Read `src/hooks/useCostData.ts` 第 220-240 行，确认它连接 `/ws/dashboard` 的目的（订阅什么消息）。

**决策点**：
- 若 useCostData 只消费 `metrics.tick` 的成本字段 → 可改为读 `useRealtimeMetricsContext`，复用同一连接
- 若 useCostData 订阅不同的消息类型（如 `cost.update`）→ 暂不动，但记录为后续优化

**本 Task 默认不动 useCostData**（避免 scope 蔓延），仅验证它不会因为 RealtimeMetricsProvider 的存在而重复建连。

- [ ] **Step 2: 启动开发服务器验证连接数**

Run: `npm run dev`

1. 打开 `http://localhost:5173/dashboard`
2. DevTools → Network → WS（筛选 WebSocket）
3. 应只看到**一条** `/ws/dashboard` 连接
4. 导航到 `/cost`，再回到 `/dashboard`
5. 观察：`/ws/dashboard` 连接数应**保持为 1**，无新增 101 Switching Protocols

- [ ] **Step 3: Commit（记录验证）**

```bash
git commit --allow-empty -m "docs: verified single WS connection across navigation"
```

---

## Task 6: 手动验证端到端效果

**Files:** 无

- [ ] **Step 1: 验证路由切换不重连**

1. `npm run dev`，打开 `/dashboard`，等待实时数据（LiveIndicator 显示绿色"实时"）
2. 导航到 `/analytics`，停留 3 秒
3. 导航回 `/dashboard`
4. **期望**：LiveIndicator 几乎立即显示"实时"，Golden Signals 卡片不出现全零过渡（因为 WS 连接持续，tick 持续推送）

- [ ] **Step 2: 验证页面刷新后恢复**

1. 在 `/dashboard` 按 F5 刷新
2. **期望**：WS 重新建立（刷新是全新页面，这是合理的），但首个 tick 到达后立即显示数据

- [ ] **Step 3: DevTools Performance 录制对比**

1. 用 Performance 面板录制"导航到 dashboard → 数据显示"过程
2. 对比改造前后：改造后应无 `new WebSocket()` 在路由切换时触发（仅首次加载有）

- [ ] **Step 4: 运行 lint 确认无告警**

Run: `npm run lint`
Expected: 无 error（warning 可接受，但需检查是否引入新的）。

- [ ] **Step 5: 最终 commit**

```bash
git add -A
git commit -m "test: realtime metrics provider verified end-to-end"
```

---

## Self-Review 自检

**1. Spec coverage（对照诊断报告 P0-2）**
- ✅ 创建全局 `RealtimeMetricsProvider` — Task 2
- ✅ 在应用根挂载一次 `useWebSocket('/ws/dashboard')` — Task 2 + Task 4
- ✅ Dashboard 通过 Context 消费 — Task 3（薄封装保持 import 不变）
- ✅ 禁止页面组件直接调用 WS hook — Task 3 后 useRealtimeMetrics 仅转发 Context
- ✅ 测试覆盖 — Task 1（Provider）+ Task 3（兼容层）

**2. Placeholder scan**：无占位符。所有 mock 默认值、SAMPLE_TICK、断言均完整。

**3. Type consistency**：
- `RealtimeMetricsContextValue` 在 Provider 定义，被 `useRealtimeMetricsContext` 返回
- `useRealtimeMetrics` 的 `UseRealtimeMetricsReturn` 用 `import(...)` 类型引用，字段名（metrics/alerts/isConnected/connectionState/lastUpdated）与 Context 值一致 ✓
- `PipelineStages`、`MetricAlert` 类型从 Provider re-export，保持外部 import 路径稳定 ✓

**4. 风险点**：
- Dashboard.test.tsx 可能需要追加 `useRealtimeMetrics` 的 mock — Task 4 Step 3 已说明处理方式
- CostGovernance 仍各自连 WS（本计划不优化）— Task 5 说明，记录为后续
- Context 默认值 `null` + 消费时抛错，避免静默使用无 Provider 的 bug ✓
