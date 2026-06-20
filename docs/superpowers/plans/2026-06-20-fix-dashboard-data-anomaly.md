# Fix Dashboard Data Anomaly — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 RAG 查询后仪表盘归零、分析/成本页面无数据的异常，引入 TanStack Query 统一数据获取层，消除 WebSocket 指标门闩缺陷。

**Architecture:** 三管齐下——(1) 将三个手写 `useEffect + cancelled flag` 数据获取钩子迁移为 TanStack Query `useQuery`，获得自动 AbortSignal 竞态防护、缓存、轮询能力；(2) 将 `useRealtimeMetrics` 的 `lastUpdated` 从不可逆锁存改为带超时的活性信号，使 Dashboard 在 WebSocket 断开/全零时自动回退 HTTP 数据；(3) 后端聚合 API 增加 `data_available` 布尔字段，前端基于三态模型（loading/empty/ready）渲染。

**Tech Stack:** React 19, Zustand 5, TanStack Query v5, Vitest, FastAPI, Redis

**Diagnosis Reference:** `docs/superpowers/plans/` 同目录下诊断报告

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `src/providers/QueryProvider.tsx` | TanStack QueryClient 创建 + Provider 包裹 |
| `src/hooks/useDashboardData.ts` | 替代 `useDashboardStats`，基于 `useQuery` |
| `src/hooks/useAnalyticsData.ts` | 替代 `useAnalytics`，基于 `useQuery` |
| `src/hooks/useCostDataQuery.ts` | 替代 `useCostData`，基于 `useQuery` |
| `src/hooks/__tests__/useDashboardData.test.ts` | useDashboardData 测试 |
| `src/hooks/__tests__/useAnalyticsData.test.ts` | useAnalyticsData 测试 |
| `src/hooks/__tests__/useCostDataQuery.test.ts` | useCostDataQuery 测试 |
| `src/hooks/__tests__/useRealtimeMetrics.test.ts` | useRealtimeMetrics 活性检测测试 |
| `backend/tests/test_analytics_data_available.py` | 后端 `data_available` 字段测试 |

### Modified Files
| File | Change |
|------|--------|
| `package.json` | 添加 `@tanstack/react-query` 依赖 |
| `src/main.tsx` | 包裹 `QueryProvider` |
| `src/hooks/useRealtimeMetrics.ts` | `lastUpdated` 加超时降级逻辑 |
| `src/pages/Dashboard.tsx` | 切换到新钩子 + 修复合并逻辑 |
| `src/pages/Analytics.tsx` | 切换到 `useAnalyticsData` |
| `src/pages/CostGovernance.tsx` | 切换到 `useCostDataQuery` |
| `src/pages/__tests__/Dashboard.test.tsx` | 更新 mock |
| `backend/app/api/analytics.py` | 响应增加 `data_available` 字段 |
| `backend/app/cost/service.py` | `get_summary` 增加 `data_available` 字段 |

---

## Task 1: Install TanStack Query & Create QueryProvider

**Files:**
- Modify: `package.json`
- Create: `src/providers/QueryProvider.tsx`
- Modify: `src/main.tsx`

- [ ] **Step 1: Install TanStack Query**

```bash
cd C:\Users\Yum\Desktop\Aureon-test && npm install @tanstack/react-query
```

Expected: `@tanstack/react-query` appears in `package.json` dependencies.

- [ ] **Step 2: Create QueryProvider**

Create `src/providers/QueryProvider.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';

/**
 * 创建 QueryClient 实例，配置适合 Aureon 的默认值：
 * - staleTime: 30s（30 秒内不重复请求同一数据）
 * - gcTime: 5 分钟（TanStack Query v5 默认）
 * - retry: 2 次（指数退避）
 * - refetchOnWindowFocus: false（避免切换 tab 后大量重请求）
 */
function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: 2,
        refetchOnWindowFocus: false,
      },
    },
  });
}

/** 全局 QueryClient 单例（SSR 安全：避免跨请求共享） */
let browserQueryClient: QueryClient | undefined;

function getQueryClient() {
  if (typeof window === 'undefined') {
    return makeQueryClient();
  }
  if (!browserQueryClient) {
    browserQueryClient = makeQueryClient();
  }
  return browserQueryClient;
}

export function QueryProvider({ children }: { children: ReactNode }) {
  const [queryClient] = useState(getQueryClient);

  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
}
```

- [ ] **Step 3: Wrap App with QueryProvider**

Read `src/main.tsx`, find the `<App />` render, wrap it:

```tsx
// src/main.tsx — 在已有 import 区添加：
import { QueryProvider } from './providers/QueryProvider';

// 找到 createRoot(...) 渲染处，包裹 QueryProvider：
// Before:
//   <App />
// After:
//   <QueryProvider><App /></QueryProvider>
```

- [ ] **Step 4: Verify build**

```bash
cd C:\Users\Yum\Desktop\Aureon-test && npm run build 2>&1 | tail -5
```

Expected: Build succeeds with no errors.

- [ ] **Step 5: Commit**

```bash
git add package.json package-lock.json src/providers/QueryProvider.tsx src/main.tsx
git commit -m "feat: add TanStack Query provider with default config"
```

---

## Task 2: Create useDashboardData (TanStack Query) with Tests

**Files:**
- Create: `src/hooks/useDashboardData.ts`
- Create: `src/hooks/__tests__/useDashboardData.test.ts`

- [ ] **Step 1: Write failing tests**

Create `src/hooks/__tests__/useDashboardData.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

import { useDashboardData, DASHBOARD_QUERY_KEYS } from '../useDashboardData';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('useDashboardData', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('starts with loading state', () => {
    mockFetch.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useDashboardData(), {
      wrapper: createWrapper(),
    });
    expect(result.current.isLoading).toBe(true);
    expect(result.current.stats).toBeUndefined();
    expect(result.current.error).toBeNull();
  });

  it('fetches stats, recent queries, and volume successfully', async () => {
    const statsData = {
      cache_hit_rate: 0.85,
      query_count_24h: 100,
      avg_retrieval_latency_ms: 250,
      total_indexed_docs: 10,
      total_chunks: 500,
    };
    const recentData = {
      queries: [
        { query: 'What is RAG?', sources_count: 3, latency_ms: 200, timestamp: '2026-05-29T10:00:00Z' },
      ],
    };
    const volumeData = { data: [{ date: '2026-06-18', count: 42 }], total: 42 };

    mockFetch
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(statsData) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(recentData) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(volumeData) });

    const { result } = renderHook(() => useDashboardData(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.stats).toEqual(statsData);
    expect(result.current.recentQueries).toHaveLength(1);
    expect(result.current.queryVolume).toEqual([{ date: '2026-06-18', count: 42 }]);
    expect(result.current.error).toBeNull();
  });

  it('handles fetch failure with error state', async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: false, status: 503, json: () => Promise.resolve({ detail: 'Redis down' }) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ queries: [] }) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ data: [] }) });

    const { result } = renderHook(() => useDashboardData(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.error).toBeTruthy();
  });

  it('provides refetch function', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ cache_hit_rate: 0, query_count_24h: 0, avg_retrieval_latency_ms: 0, total_indexed_docs: 0, total_chunks: 0 }),
    });

    const { result } = renderHook(() => useDashboardData(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(typeof result.current.refetch).toBe('function');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:\Users\Yum\Desktop\Aureon-test && npx vitest run src/hooks/__tests__/useDashboardData.test.ts 2>&1 | tail -15
```

Expected: FAIL — `Cannot find module '../useDashboardData'`

- [ ] **Step 3: Implement useDashboardData**

Create `src/hooks/useDashboardData.ts`:

```ts
/**
 * useDashboardData — TanStack Query 版 Dashboard 数据钩子
 * 替代原 useDashboardStats（useEffect + cancelled flag 模式）
 *
 * 改进：
 * - 自动 AbortSignal 竞态防护（查询键变化时取消旧请求）
 * - 内置缓存与 staleTime 控制
 * - 统一错误处理
 */

import { useQuery } from '@tanstack/react-query';
import { authFetch } from '../services/authFetch';
import type { StatsResponse, RecentQuery } from '../types/dashboard';

const STATS_URL = '/api/rag/stats';
const RECENT_URL = '/api/rag/queries/recent?limit=5';
const VOLUME_URL = '/api/rag/query-volume?days=7';

/** 查询键常量，供外部做缓存失效时引用 */
export const DASHBOARD_QUERY_KEYS = {
  stats: ['dashboard', 'stats'] as const,
  recent: ['dashboard', 'recent'] as const,
  volume: ['dashboard', 'volume'] as const,
} as const;

interface QueryVolumePoint {
  date: string;
  count: number;
}

interface DashboardData {
  stats: StatsResponse | undefined;
  recentQueries: RecentQuery[];
  queryVolume: QueryVolumePoint[];
  isLoading: boolean;
  error: Error | null;
  refetch: () => void;
}

/**
 * 获取 Dashboard 统计数据
 * 使用 TanStack Query 管理请求生命周期：
 * - staleTime: 20s（20 秒内切换页面不重新请求）
 * - refetchInterval: 30s（轮询替代原 setTimeout 递归）
 */
export function useDashboardData(): DashboardData {
  const statsQuery = useQuery<StatsResponse>({
    queryKey: DASHBOARD_QUERY_KEYS.stats,
    queryFn: async ({ signal }) => {
      const res = await authFetch(STATS_URL, { signal });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `Stats request failed: ${res.status}`);
      }
      return res.json();
    },
    staleTime: 20_000,
    refetchInterval: 30_000,
  });

  const recentQuery = useQuery<{ queries: RecentQuery[] }>({
    queryKey: DASHBOARD_QUERY_KEYS.recent,
    queryFn: async ({ signal }) => {
      const res = await authFetch(RECENT_URL, { signal });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `Recent queries failed: ${res.status}`);
      }
      return res.json();
    },
    staleTime: 20_000,
    refetchInterval: 30_000,
  });

  const volumeQuery = useQuery<{ data: QueryVolumePoint[] }>({
    queryKey: DASHBOARD_QUERY_KEYS.volume,
    queryFn: async ({ signal }) => {
      const res = await authFetch(VOLUME_URL, { signal });
      if (!res.ok) return { data: [] };
      return res.json();
    },
    staleTime: 20_000,
    refetchInterval: 30_000,
  });

  const isLoading = statsQuery.isLoading || recentQuery.isLoading || volumeQuery.isLoading;
  const error = statsQuery.error || recentQuery.error || volumeQuery.error;

  return {
    stats: statsQuery.data,
    recentQueries: recentQuery.data?.queries ?? [],
    queryVolume: volumeQuery.data?.data ?? [],
    isLoading,
    error: error as Error | null,
    refetch: () => {
      statsQuery.refetch();
      recentQuery.refetch();
      volumeQuery.refetch();
    },
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd C:\Users\Yum\Desktop\Aureon-test && npx vitest run src/hooks/__tests__/useDashboardData.test.ts 2>&1 | tail -15
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hooks/useDashboardData.ts src/hooks/__tests__/useDashboardData.test.ts
git commit -m "feat(dashboard): add useDashboardData hook with TanStack Query"
```

---

## Task 3: Create useAnalyticsData (TanStack Query) with Tests

**Files:**
- Create: `src/hooks/useAnalyticsData.ts`
- Create: `src/hooks/__tests__/useAnalyticsData.test.ts`

- [ ] **Step 1: Write failing tests**

Create `src/hooks/__tests__/useAnalyticsData.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

import { useAnalyticsData } from '../useAnalyticsData';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('useAnalyticsData', () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.restoreAllMocks());

  it('starts with loading state', () => {
    mockFetch.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useAnalyticsData('24h'), {
      wrapper: createWrapper(),
    });
    expect(result.current.isLoading).toBe(true);
    expect(result.current.usage).toBeNull();
  });

  it('fetches all four endpoints in parallel', async () => {
    const usage = { timeRange: '24h', total: 100, perHour: 4.2, byIntent: {}, trend: { change: 0, period: '' } };
    const latency = { timeRange: '24h', avg: 250, p95: 500, p99: 800, breakdown: { retrieval: 0, llm_first_token: 0, llm_generation: 0 }, trend: { avg_change: 0, period: '' } };
    const tokens = { timeRange: '24h', input: 5000, output: 3000, total: 8000, cost: 0.5, costPerQuery: 0.005, model: 'qwen', trend: { input_change: 0, output_change: 0, period: '' } };
    const cache = { hitRate: 0.85, saves: 50, latencyReduction: 120, memoryUsage: '128MB' };

    mockFetch
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(usage) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(latency) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(tokens) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(cache) });

    const { result } = renderHook(() => useAnalyticsData('24h'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.usage?.total).toBe(100);
    expect(result.current.latency?.avg).toBe(250);
    expect(result.current.tokens?.total).toBe(8000);
    expect(result.current.cache?.hitRate).toBe(0.85);
    expect(result.current.error).toBeNull();
  });

  it('handles 401 auth error', async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: false, status: 401 })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({}) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({}) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({}) });

    const { result } = renderHook(() => useAnalyticsData('24h'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.error).toBeTruthy();
  });

  it('refetches when timeRange changes', async () => {
    const data = { ok: true, json: () => Promise.resolve({}) };
    mockFetch.mockResolvedValue(data);

    const { rerender } = renderHook(({ tr }) => useAnalyticsData(tr), {
      wrapper: createWrapper(),
      initialProps: { tr: '24h' as string },
    });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });

    const callCount1 = mockFetch.mock.calls.length;
    rerender({ tr: '7d' });

    await waitFor(() => {
      expect(mockFetch.mock.calls.length).toBeGreaterThan(callCount1);
    });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:\Users\Yum\Desktop\Aureon-test && npx vitest run src/hooks/__tests__/useAnalyticsData.test.ts 2>&1 | tail -10
```

Expected: FAIL — `Cannot find module '../useAnalyticsData'`

- [ ] **Step 3: Implement useAnalyticsData**

Create `src/hooks/useAnalyticsData.ts`:

```ts
/**
 * useAnalyticsData — TanStack Query 版分析数据钩子
 * 替代原 useAnalytics（useEffect + Promise.all 无 AbortSignal）
 *
 * 改进：
 * - 4 个请求各自独立 useQuery，一个失败不影响其他
 * - timeRange 变化时自动取消旧请求（AbortSignal）
 * - staleTime: 60s（分析数据不需要高频刷新）
 */

import { useQueries } from '@tanstack/react-query';
import { authFetch } from '../services/authFetch';

interface UsageData {
  timeRange: string;
  total: number;
  perHour: number;
  byIntent: Record<string, number>;
  trend: { change: number; period: string };
  data_available?: boolean;
}

interface LatencyData {
  timeRange: string;
  avg: number;
  p95: number;
  p99: number;
  breakdown: { retrieval: number; llm_first_token: number; llm_generation: number };
  trend: { avg_change: number; period: string };
  data_available?: boolean;
}

interface TokenData {
  timeRange: string;
  input: number;
  output: number;
  total: number;
  cost: number;
  costPerQuery: number;
  model: string;
  trend: { input_change: number; output_change: number; period: string };
  data_available?: boolean;
}

interface CacheData {
  hitRate: number;
  saves: number;
  latencyReduction: number;
  memoryUsage: string;
  data_available?: boolean;
}

interface AnalyticsResult {
  usage: UsageData | null;
  latency: LatencyData | null;
  tokens: TokenData | null;
  cache: CacheData | null;
  isLoading: boolean;
  error: Error | null;
  refetch: () => void;
}

export function useAnalyticsData(timeRange: string = '24h'): AnalyticsResult {
  const results = useQueries({
    queries: [
      {
        queryKey: ['analytics', 'usage', timeRange],
        queryFn: async ({ signal }: { signal: AbortSignal }) => {
          const res = await authFetch(`/api/rag/analytics/usage?time_range=${timeRange}`, { signal });
          if (!res.ok) throw new Error(`Usage fetch failed: ${res.status}`);
          return res.json() as Promise<UsageData>;
        },
        staleTime: 60_000,
      },
      {
        queryKey: ['analytics', 'latency', timeRange],
        queryFn: async ({ signal }: { signal: AbortSignal }) => {
          const res = await authFetch(`/api/rag/analytics/latency?time_range=${timeRange}`, { signal });
          if (!res.ok) throw new Error(`Latency fetch failed: ${res.status}`);
          return res.json() as Promise<LatencyData>;
        },
        staleTime: 60_000,
      },
      {
        queryKey: ['analytics', 'tokens', timeRange],
        queryFn: async ({ signal }: { signal: AbortSignal }) => {
          const res = await authFetch(`/api/rag/analytics/tokens?time_range=${timeRange}`, { signal });
          if (!res.ok) throw new Error(`Tokens fetch failed: ${res.status}`);
          return res.json() as Promise<TokenData>;
        },
        staleTime: 60_000,
      },
      {
        queryKey: ['analytics', 'cache'],
        queryFn: async ({ signal }: { signal: AbortSignal }) => {
          const res = await authFetch('/api/rag/analytics/cache', { signal });
          if (!res.ok) throw new Error(`Cache fetch failed: ${res.status}`);
          return res.json() as Promise<CacheData>;
        },
        staleTime: 60_000,
      },
    ],
  });

  const [usageQ, latencyQ, tokensQ, cacheQ] = results;
  const isLoading = results.some((r) => r.isLoading);
  const error = results.find((r) => r.error)?.error as Error | null;

  return {
    usage: usageQ.data ?? null,
    latency: latencyQ.data ?? null,
    tokens: tokensQ.data ?? null,
    cache: cacheQ.data ?? null,
    isLoading,
    error,
    refetch: () => {
      results.forEach((r) => r.refetch());
    },
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd C:\Users\Yum\Desktop\Aureon-test && npx vitest run src/hooks/__tests__/useAnalyticsData.test.ts 2>&1 | tail -10
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hooks/useAnalyticsData.ts src/hooks/__tests__/useAnalyticsData.test.ts
git commit -m "feat(analytics): add useAnalyticsData hook with TanStack Query"
```

---

## Task 4: Create useCostDataQuery (TanStack Query) with Tests

**Files:**
- Create: `src/hooks/useCostDataQuery.ts`
- Create: `src/hooks/__tests__/useCostDataQuery.test.ts`

- [ ] **Step 1: Write failing tests**

Create `src/hooks/__tests__/useCostDataQuery.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

import { useCostDataQuery } from '../useCostDataQuery';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('useCostDataQuery', () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.restoreAllMocks());

  it('starts with loading state', () => {
    mockFetch.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useCostDataQuery('30d'), {
      wrapper: createWrapper(),
    });
    expect(result.current.isLoading).toBe(true);
    expect(result.current.summary).toBeNull();
  });

  it('fetches summary, trend, breakdown, consumers', async () => {
    const summary = { total_cost: 12.5, burn_rate: 0.5, total_tokens: 50000, budget_used_pct: 25, budget_total: 50, trend_direction: 'stable' };
    const trend = [{ date: '2026-06-18', cost: 0.5, tokens: 5000 }];
    const breakdown = { breakdown: { 'qwen3.6-flash': 10, 'bge-m3': 2.5 }, period: '30d' };
    const consumers = [{ workspace_id: 'ws-1', cost_usd: 8, tokens: 30000 }];

    mockFetch
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(summary) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(trend) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(breakdown) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(consumers) });

    const { result } = renderHook(() => useCostDataQuery('30d'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.summary?.totalCost).toBe(12.5);
    expect(result.current.trends).toHaveLength(1);
    expect(result.current.breakdown.length).toBeGreaterThan(0);
    expect(result.current.topConsumers).toHaveLength(1);
    expect(result.current.error).toBeNull();
  });

  it('handles 403 auth error', async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: false, status: 403 })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve([]) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({}) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve([]) });

    const { result } = renderHook(() => useCostDataQuery('30d'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.error).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:\Users\Yum\Desktop\Aureon-test && npx vitest run src/hooks/__tests__/useCostDataQuery.test.ts 2>&1 | tail -10
```

Expected: FAIL — `Cannot find module '../useCostDataQuery'`

- [ ] **Step 3: Implement useCostDataQuery**

Create `src/hooks/useCostDataQuery.ts`:

```ts
/**
 * useCostDataQuery — TanStack Query 版成本数据钩子
 * 替代原 useCostData（useEffect + cancelled flag 模式）
 *
 * 改进：
 * - 4 个请求各自独立 useQuery，一个失败不阻塞其他
 * - timeRange 变化时自动取消旧请求
 * - staleTime: 60s
 */

import { useQueries } from '@tanstack/react-query';
import { authFetch } from '../services/authFetch';

export type CostTimeRange = '7d' | '30d' | '90d';

export interface CostSummary {
  totalCost: number;
  burnRate: number;
  totalTokens: number;
  budgetUsed: number;
  budgetTotal: number;
  costChange?: number;
  burnTrend?: 'up' | 'down' | 'stable';
  data_available?: boolean;
}

export interface CostTrendPoint {
  date: string;
  cost: number;
  tokens: number;
}

export interface CostBreakdown {
  category: string;
  cost: number;
  percentage: number;
}

export interface TopConsumer {
  name: string;
  cost: number;
  tokens: number;
  percentage: number;
}

interface CostDataResult {
  summary: CostSummary | null;
  trends: CostTrendPoint[];
  breakdown: CostBreakdown[];
  topConsumers: TopConsumer[];
  isLoading: boolean;
  error: Error | null;
  refetch: () => void;
}

export function useCostDataQuery(timeRange: CostTimeRange = '30d'): CostDataResult {
  const days = timeRange === '7d' ? 7 : timeRange === '30d' ? 30 : 90;

  const results = useQueries({
    queries: [
      {
        queryKey: ['cost', 'summary', timeRange],
        queryFn: async ({ signal }: { signal: AbortSignal }) => {
          const res = await authFetch(`/api/cost/summary?period=${timeRange}`, { signal });
          if (res.status === 401 || res.status === 403) {
            throw new Error('需要管理员权限才能查看成本数据');
          }
          if (!res.ok) throw new Error(`Cost summary failed: ${res.status}`);
          const json = await res.json();
          return {
            totalCost: json.total_cost ?? 0,
            burnRate: json.burn_rate ?? 0,
            totalTokens: json.total_tokens ?? 0,
            budgetUsed: json.budget_used_pct ?? 0,
            budgetTotal: json.budget_total ?? 0,
            burnTrend: json.trend_direction ?? 'stable',
            data_available: json.data_available,
          } as CostSummary;
        },
        staleTime: 60_000,
      },
      {
        queryKey: ['cost', 'trend', days],
        queryFn: async ({ signal }: { signal: AbortSignal }) => {
          const res = await authFetch(`/api/cost/trend?days=${days}`, { signal });
          if (!res.ok) return [] as CostTrendPoint[];
          const json = await res.json();
          return (Array.isArray(json) ? json : []).map((t: Record<string, unknown>) => ({
            date: String(t.date ?? ''),
            cost: Number(t.cost ?? 0),
            tokens: Number(t.tokens ?? 0),
          })) as CostTrendPoint[];
        },
        staleTime: 60_000,
      },
      {
        queryKey: ['cost', 'breakdown', timeRange],
        queryFn: async ({ signal }: { signal: AbortSignal }) => {
          const res = await authFetch(`/api/cost/breakdown?by=model&period=${timeRange}`, { signal });
          if (!res.ok) return [] as CostBreakdown[];
          const json = await res.json();
          const raw = json.breakdown;
          if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
            const total = Object.values(raw as Record<string, number>).reduce((s, v) => s + (Number(v) || 0), 0);
            return Object.entries(raw as Record<string, number>).map(([cat, cost]) => ({
              category: cat,
              cost: Number(cost) || 0,
              percentage: total > 0 ? ((Number(cost) || 0) / total) * 100 : 0,
            })) as CostBreakdown[];
          }
          return Array.isArray(raw) ? raw.map((b: Record<string, unknown>) => ({
            category: String(b.category ?? b.model ?? ''),
            cost: Number(b.cost ?? 0),
            percentage: Number(b.percentage ?? 0),
          })) as CostBreakdown[] : [] as CostBreakdown[];
        },
        staleTime: 60_000,
      },
      {
        queryKey: ['cost', 'consumers'],
        queryFn: async ({ signal }: { signal: AbortSignal }) => {
          const res = await authFetch('/api/cost/top-consumers?limit=10', { signal });
          if (!res.ok) return [] as TopConsumer[];
          const json = await res.json();
          const arr = Array.isArray(json) ? json : [];
          const total = arr.reduce((s: number, c: Record<string, unknown>) => s + (Number(c.cost_usd ?? 0)), 0);
          return arr.map((c: Record<string, unknown>) => ({
            name: String(c.workspace_id ?? c.name ?? 'Unknown'),
            cost: Number(c.cost_usd ?? c.cost ?? 0),
            tokens: Number(c.tokens ?? 0),
            percentage: total > 0 ? (Number(c.cost_usd ?? 0) / total) * 100 : 0,
          })) as TopConsumer[];
        },
        staleTime: 60_000,
      },
    ],
  });

  const [summaryQ, trendQ, breakdownQ, consumersQ] = results;
  const isLoading = results.some((r) => r.isLoading);
  const error = results.find((r) => r.error)?.error as Error | null;

  return {
    summary: summaryQ.data ?? null,
    trends: trendQ.data ?? [],
    breakdown: breakdownQ.data ?? [],
    topConsumers: consumersQ.data ?? [],
    isLoading,
    error,
    refetch: () => {
      results.forEach((r) => r.refetch());
    },
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd C:\Users\Yum\Desktop\Aureon-test && npx vitest run src/hooks/__tests__/useCostDataQuery.test.ts 2>&1 | tail -10
```

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hooks/useCostDataQuery.ts src/hooks/__tests__/useCostDataQuery.test.ts
git commit -m "feat(cost): add useCostDataQuery hook with TanStack Query"
```

---

## Task 5: Fix useRealtimeMetrics — Add Stale Timeout to lastUpdated

**Files:**
- Modify: `src/hooks/useRealtimeMetrics.ts`
- Create: `src/hooks/__tests__/useRealtimeMetrics.test.ts`

这是本次修复的**核心根因**：`lastUpdated` 一旦设为非 null 就永不回退，导致 `hasRealtimeData` 门闩永久锁存。

- [ ] **Step 1: Write failing tests**

Create `src/hooks/__tests__/useRealtimeMetrics.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// Mock useWebSocket — 我们手动控制消息回调
const mockOnMessage = vi.fn();
let mockIsConnected = true;
let mockConnectionState = 'connected' as string;

vi.mock('../useWebSocket', () => ({
  useWebSocket: (_path: string, opts: { onMessage?: (data: unknown) => void }) => {
    mockOnMessage.mockImplementation(opts.onMessage ?? (() => {}));
    return {
      isConnected: mockIsConnected,
      connectionState: mockConnectionState,
    };
  },
}));

import { useRealtimeMetrics, REALTIME_STALE_THRESHOLD_MS } from '../useRealtimeMetrics';

describe('useRealtimeMetrics stale timeout', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    mockIsConnected = true;
    mockConnectionState = 'connected';
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('hasRealtimeData is false initially', () => {
    const { result } = renderHook(() => useRealtimeMetrics());
    expect(result.current.lastUpdated).toBeNull();
  });

  it('sets lastUpdated when metrics.tick arrives', () => {
    const { result } = renderHook(() => useRealtimeMetrics());

    act(() => {
      mockOnMessage({
        type: 'metrics.tick',
        data: { qps: 1, ttft_p50: 100, ttft_p95: 200, tpot: 50, error_rate: 0, cache_hit_rate: 80, token_usage: 1000, active_connections: 3 },
      });
    });

    expect(result.current.lastUpdated).not.toBeNull();
    expect(result.current.metrics.qps).toBe(1);
  });

  it('resets lastUpdated to null after stale timeout', () => {
    const { result } = renderHook(() => useRealtimeMetrics());

    // 收到一条消息
    act(() => {
      mockOnMessage({
        type: 'metrics.tick',
        data: { qps: 1, ttft_p50: 100, ttft_p95: 200, tpot: 50, error_rate: 0, cache_hit_rate: 80, token_usage: 1000, active_connections: 3 },
      });
    });

    expect(result.current.lastUpdated).not.toBeNull();

    // 快进到超时阈值之后
    act(() => {
      vi.advanceTimersByTime(REALTIME_STALE_THRESHOLD_MS + 1000);
    });

    expect(result.current.lastUpdated).toBeNull();
  });

  it('resets lastUpdated when WebSocket disconnects', () => {
    mockIsConnected = true;
    const { result, rerender } = renderHook(() => useRealtimeMetrics());

    act(() => {
      mockOnMessage({
        type: 'metrics.tick',
        data: { qps: 1, ttft_p50: 100, ttft_p95: 200, tpot: 50, error_rate: 0, cache_hit_rate: 80, token_usage: 1000, active_connections: 3 },
      });
    });

    expect(result.current.lastUpdated).not.toBeNull();

    // 模拟断开
    mockIsConnected = false;
    mockConnectionState = 'disconnected';
    rerender();

    expect(result.current.lastUpdated).toBeNull();
  });

  it('refreshes timeout when new tick arrives before expiry', () => {
    const { result } = renderHook(() => useRealtimeMetrics());

    act(() => {
      mockOnMessage({
        type: 'metrics.tick',
        data: { qps: 1, ttft_p50: 100, ttft_p95: 200, tpot: 50, error_rate: 0, cache_hit_rate: 80, token_usage: 1000, active_connections: 3 },
      });
    });

    // 快进到阈值的一半
    act(() => {
      vi.advanceTimersByTime(REALTIME_STALE_THRESHOLD_MS / 2);
    });

    // 收到新消息 — 重置计时器
    act(() => {
      mockOnMessage({
        type: 'metrics.tick',
        data: { qps: 2, ttft_p50: 90, ttft_p95: 180, tpot: 45, error_rate: 0, cache_hit_rate: 85, token_usage: 2000, active_connections: 4 },
      });
    });

    expect(result.current.lastUpdated).not.toBeNull();

    // 再快进到原阈值（从第一次消息算起已超时，但从第二次算起未超时）
    act(() => {
      vi.advanceTimersByTime(REALTIME_STALE_THRESHOLD_MS / 2 + 1000);
    });

    // 仍未超时
    expect(result.current.lastUpdated).not.toBeNull();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:\Users\Yum\Desktop\Aureon-test && npx vitest run src/hooks/__tests__/useRealtimeMetrics.test.ts 2>&1 | tail -15
```

Expected: FAIL — tests for stale timeout and disconnect reset fail (current code never resets `lastUpdated`).

- [ ] **Step 3: Fix useRealtimeMetrics**

Read `src/hooks/useRealtimeMetrics.ts` and apply the following changes:

```ts
// 在文件顶部添加常量导出：
/** WebSocket 指标数据过期阈值（毫秒）。超过此时间未收到新 tick 则视为数据不可用。 */
export const REALTIME_STALE_THRESHOLD_MS = 15_000; // 15 秒 = 3 个 tick 周期

// 在 useRealtimeMetrics 函数内部，添加 staleTimerRef：
const staleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

// 重置 lastUpdated 的辅助函数：
const resetLastUpdated = useCallback(() => {
  setLastUpdated(null);
}, []);

// 替换 handleMessage 中的 setLastUpdated(Date.now()) 为带计时器的版本：
const handleMessage = useCallback((data: unknown) => {
  if (!data || typeof data !== 'object') return;
  const msg = data as Record<string, unknown>;

  if (msg.type === 'metrics.tick' && msg.data) {
    const tickData = msg.data as Record<string, unknown>;
    setMetrics({
      qps: Number(tickData.qps ?? 0),
      ttft_p50: Number(tickData.ttft_p50 ?? 0),
      ttft_p95: Number(tickData.ttft_p95 ?? 0),
      tpot: Number(tickData.tpot ?? 0),
      error_rate: Number(tickData.error_rate ?? 0),
      cache_hit_rate: Number(tickData.cache_hit_rate ?? 0),
      token_usage: Number(tickData.token_usage ?? 0),
      active_connections: Number(tickData.active_connections ?? 0),
    });
    setLastUpdated(Date.now());

    // 重置过期计时器：每次收到新 tick 都重新计时
    if (staleTimerRef.current) clearTimeout(staleTimerRef.current);
    staleTimerRef.current = setTimeout(resetLastUpdated, REALTIME_STALE_THRESHOLD_MS);
  }

  if (msg.type === 'alert' && msg.data) {
    const alertData = msg.data as MetricAlert;
    setAlerts((prev) => [alertData, ...prev].slice(0, 50));
  }
}, [resetLastUpdated]);

// 在 return 之前，添加 WebSocket 断开时重置 lastUpdated 的 Effect：
useEffect(() => {
  if (!isConnected) {
    // WebSocket 断开 → 立即将数据源标记为不可用
    resetLastUpdated();
    if (staleTimerRef.current) {
      clearTimeout(staleTimerRef.current);
      staleTimerRef.current = null;
    }
  }
}, [isConnected, resetLastUpdated]);

// 在组件卸载时清理计时器（可选，已有 WebSocket cleanup）：
useEffect(() => {
  return () => {
    if (staleTimerRef.current) clearTimeout(staleTimerRef.current);
  };
}, []);
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd C:\Users\Yum\Desktop\Aureon-test && npx vitest run src/hooks/__tests__/useRealtimeMetrics.test.ts 2>&1 | tail -15
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hooks/useRealtimeMetrics.ts src/hooks/__tests__/useRealtimeMetrics.test.ts
git commit -m "fix(realtime): add stale timeout and disconnect reset to lastUpdated latch"
```

---

## Task 6: Migrate Dashboard.tsx to New Hooks

**Files:**
- Modify: `src/pages/Dashboard.tsx`
- Modify: `src/pages/__tests__/Dashboard.test.tsx`

- [ ] **Step 1: Update Dashboard.tsx imports and hook calls**

Replace the old hook imports and calls:

```tsx
// ── 替换 import ──
// Before:
//   import { useDashboardStats } from '../hooks/useDashboardStats';
// After:
import { useDashboardData } from '../hooks/useDashboardData';

// ── 替换组件内部 hook 调用 ──
// Before:
//   const { stats, queryVolume, loading, error, refetch } = useDashboardStats();
// After:
const { stats, queryVolume, isLoading: loading, error, refetch } = useDashboardData();
```

- [ ] **Step 2: Fix Dashboard data merging logic**

Replace the existing merging logic (around line 259-280) with the new "overlay" pattern:

```tsx
// ── 替换合并逻辑 ──
// Before (有缺陷的二选一):
//   const hasRealtimeData = rtLastUpdated !== null;
//   const metrics = (hasRealtimeData && rtMetrics) ? { ... websocketData } : (stats ? { ... httpData } : null);

// After (增强叠加模式):
const hasRealtimeData = rtLastUpdated !== null;

// 基准层：始终使用 HTTP 轮询数据（兜底）
const baseMetrics = stats ? {
  ttft_p50: stats.avg_retrieval_latency_ms || 0,
  ttft_p95: 0,
  qps: Math.round((stats.query_count_24h || 0) / 86400 * 100) / 100,
  error_rate: 0,
  saturation: 0,
  alert_count: 0,
  latency_trend: [] as number[],
  tpot_trend: [] as number[],
  e2e_trend: [] as number[],
} : null;

// 增强层：WebSocket 实时数据（可选叠加）
const realtimeOverlay = hasRealtimeData ? {
  ttft_p50: rtMetrics.ttft_p50,
  ttft_p95: rtMetrics.ttft_p95,
  qps: rtMetrics.qps,
  error_rate: rtMetrics.error_rate * 100,
  alert_count: rtAlerts.length,
} : null;

// 融合：增强层覆盖基准层
const metrics = baseMetrics
  ? { ...baseMetrics, ...realtimeOverlay }
  : null;
```

- [ ] **Step 3: Remove hardcoded fallback values**

```tsx
// Before:
//   ttft_p50: stats.avg_retrieval_latency_ms || 590,
//   ttft_p95: 1677,
//   error_rate: 0.5,
//   saturation: 65,
// After:
//   ttft_p50: stats.avg_retrieval_latency_ms || 0,
//   ttft_p95: 0,
//   error_rate: 0,
//   saturation: 0,
```

These hardcoded values (`590`, `1677`, `0.5`, `65`) mask the real issue — when data is missing, they show fake numbers instead of honest zeros or "no data" states.

- [ ] **Step 4: Update Dashboard test mocks**

Update `src/pages/__tests__/Dashboard.test.tsx` to mock the new hook:

```tsx
// ── 替换 mock ──
// Before:
//   const mockUseDashboardStats = vi.fn();
//   vi.mock('../../hooks/useDashboardStats', () => ({
//     useDashboardStats: () => mockUseDashboardStats(),
//   }));

// After:
const mockUseDashboardData = vi.fn();
vi.mock('../../hooks/useDashboardData', () => ({
  useDashboardData: () => mockUseDashboardData(),
}));

// ── 替换所有 mockUseDashboardStats 调用 ──
// mockUseDashboardStats.mockReturnValue({ ... })
// → mockUseDashboardData.mockReturnValue({ ... })
```

Also update the mock return shape — `loading` → `isLoading`:

```tsx
// Before:
//   mockUseDashboardStats.mockReturnValue({ loading: true, ... });
// After:
mockUseDashboardData.mockReturnValue({ isLoading: true, ... });
```

- [ ] **Step 5: Run all existing tests**

```bash
cd C:\Users\Yum\Desktop\Aureon-test && npx vitest run src/pages/__tests__/Dashboard.test.tsx 2>&1 | tail -15
```

Expected: All existing Dashboard tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pages/Dashboard.tsx src/pages/__tests__/Dashboard.test.tsx
git commit -m "fix(dashboard): migrate to useDashboardData + fix data merging to overlay pattern"
```

---

## Task 7: Migrate Analytics.tsx and CostGovernance.tsx to New Hooks

**Files:**
- Modify: `src/pages/Analytics.tsx`
- Modify: `src/pages/CostGovernance.tsx`

- [ ] **Step 1: Migrate Analytics.tsx**

```tsx
// ── 替换 import ──
// Before:
//   import { useAnalytics } from '../hooks/useAnalytics';
// After:
import { useAnalyticsData } from '../hooks/useAnalyticsData';

// ── 替换 hook 调用 ──
// Before:
//   const { usage, latency, tokens, cache, loading, error, refresh } = useAnalytics(timeRange);
// After:
const { usage, latency, tokens, cache, isLoading: loading, error, refetch: refresh } = useAnalyticsData(timeRange);
```

- [ ] **Step 2: Migrate CostGovernance.tsx**

```tsx
// ── 替换 import ──
// Before:
//   import { useCostData } from '../hooks/useCostData';
// After:
import { useCostDataQuery } from '../hooks/useCostDataQuery';

// ── 替换 hook 调用 ──
// Before:
//   const { summary, trends, breakdown, topConsumers, loading, error, refetch } = useCostData(timeRange);
// After:
const { summary, trends, breakdown, topConsumers, isLoading: loading, error, refetch } = useCostDataQuery(timeRange);
```

- [ ] **Step 3: Run full frontend test suite**

```bash
cd C:\Users\Yum\Desktop\Aureon-test && npx vitest run 2>&1 | tail -20
```

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add src/pages/Analytics.tsx src/pages/CostGovernance.tsx
git commit -m "feat: migrate Analytics and CostGovernance to TanStack Query hooks"
```

---

## Task 8: Backend — Add `data_available` Signal to Analytics API

**Files:**
- Modify: `backend/app/api/analytics.py`
- Create: `backend/tests/test_analytics_data_available.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_analytics_data_available.py`:

```python
"""验证 analytics 端点返回 data_available 字段。"""

import pytest
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_redis_empty():
    """模拟空 Redis（无历史数据）。"""
    mock = AsyncMock()
    mock.get.return_value = None
    mock.hgetall.return_value = {}
    mock.zrange.return_value = []
    return mock


@pytest.fixture
def mock_redis_with_data():
    """模拟有数据的 Redis。"""
    mock = AsyncMock()
    mock.get.return_value = "42"
    mock.hgetall.return_value = {"general_qa": "30", "code_search": "12"}
    mock.zrange.return_value = [(b'{"ttft_ms": 100}', 100.0), (b'{"ttft_ms": 200}', 200.0)]
    return mock


async def test_usage_returns_data_available_false_when_empty(mock_redis_empty):
    """Redis 无数据时，data_available 应为 False。"""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    with patch("app.api.analytics.get_redis_or_none", return_value=mock_redis_empty), \
         patch("app.api.analytics_store.get_usage_from_pg", return_value={"total": 0, "perHour": 0, "byIntent": {}}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/rag/analytics/usage")

    assert resp.status_code == 200
    data = resp.json()
    assert data["data_available"] is False
    assert data["total"] == 0


async def test_usage_returns_data_available_true_when_has_data(mock_redis_with_data):
    """Redis 有数据时，data_available 应为 True。"""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    with patch("app.api.analytics.get_redis_or_none", return_value=mock_redis_with_data):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/rag/analytics/usage")

    assert resp.status_code == 200
    data = resp.json()
    assert data["data_available"] is True
    assert data["total"] > 0


async def test_latency_returns_data_available(mock_redis_empty):
    """延迟端点同样需要 data_available 字段。"""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    with patch("app.api.analytics.get_redis_or_none", return_value=mock_redis_empty), \
         patch("app.api.analytics_store.get_latency_from_pg", return_value={"avg": 0, "p95": 0, "p99": 0}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/rag/analytics/latency")

    assert resp.status_code == 200
    data = resp.json()
    assert "data_available" in data
    assert data["data_available"] is False


async def test_tokens_returns_data_available(mock_redis_empty):
    """Token 端点同样需要 data_available 字段。"""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    with patch("app.api.analytics.get_redis_or_none", return_value=mock_redis_empty), \
         patch("app.api.analytics_store.get_tokens_from_pg", return_value={"input": 0, "output": 0, "total": 0, "cost": 0, "costPerQuery": 0}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/rag/analytics/tokens")

    assert resp.status_code == 200
    data = resp.json()
    assert "data_available" in data


async def test_cache_returns_data_available(mock_redis_empty):
    """缓存端点同样需要 data_available 字段。"""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    with patch("app.api.analytics.get_redis_or_none", return_value=mock_redis_empty):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/rag/analytics/cache")

    assert resp.status_code == 200
    data = resp.json()
    assert "data_available" in data
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:\Users\Yum\Desktop\Aureon-test\backend && python -m pytest tests/test_analytics_data_available.py -v 2>&1 | tail -15
```

Expected: FAIL — `data_available` key not found in response.

- [ ] **Step 3: Add `data_available` to all analytics endpoints**

Modify `backend/app/api/analytics.py` — for each endpoint (`/usage`, `/latency`, `/tokens`, `/cache`), add `data_available` to the return dict:

```python
# /usage 端点 — 在所有 return 语句中添加 data_available:
# 判断逻辑：total > 0 表示有数据
return {
    "timeRange": time_range,
    "total": total,
    "perHour": per_hour,
    "byIntent": by_intent,
    "trend": {"change": 0, "period": "vs previous period"},
    "data_available": total > 0,  # ← 新增
}

# /latency 端点 — avg > 0 表示有数据:
return {
    "timeRange": time_range,
    "avg": avg_lat,
    # ... 其他字段 ...
    "data_available": avg_lat > 0,  # ← 新增
}

# /tokens 端点 — input + output > 0 表示有数据:
return {
    "timeRange": time_range,
    # ... 其他字段 ...
    "data_available": (input_tokens + output_tokens) > 0,  # ← 新增
}

# /cache 端点 — hitRate > 0 表示有数据:
return {
    "hitRate": ...,
    # ... 其他字段 ...
    "data_available": hit_rate > 0,  # ← 新增
}
```

每个端点有多个 `return` 语句（Redis 路径、PG 回退路径、异常路径），**每个都需要加**。

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd C:\Users\Yum\Desktop\Aureon-test\backend && python -m pytest tests/test_analytics_data_available.py -v 2>&1 | tail -15
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Run full backend test suite to ensure no regressions**

```bash
cd C:\Users\Yum\Desktop\Aureon-test\backend && python -m pytest tests/ -v --timeout=60 2>&1 | tail -10
```

Expected: All tests PASS (no regressions).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/analytics.py backend/tests/test_analytics_data_available.py
git commit -m "feat(analytics): add data_available signal to all analytics endpoints"
```

---

## Task 9: Backend — Add `data_available` to Cost Summary Endpoint

**Files:**
- Modify: `backend/app/cost/service.py`
- Modify: `backend/app/cost/models.py`

- [ ] **Step 1: Add `data_available` to CostSummary model**

Read `backend/app/cost/models.py`, find the `CostSummary` class, add:

```python
class CostSummary(BaseModel):
    total_cost: float = 0
    burn_rate: float = 0
    total_tokens: int = 0
    budget_used_pct: float = 0
    budget_total: float = 0
    trend_direction: str = "stable"
    data_available: bool = True  # ← 新增，默认 True（有数据时）
```

- [ ] **Step 2: Set `data_available` based on actual data in service**

Read `backend/app/cost/service.py`, find the `get_summary` method. After building the summary dict, set `data_available` based on whether Redis had any data:

```python
# 在 get_summary 的 return 语句中：
summary = CostSummary(
    total_cost=total_cost,
    burn_rate=burn_rate,
    total_tokens=total_tokens,
    budget_used_pct=budget_pct,
    budget_total=budget_total,
    trend_direction=trend,
    data_available=total_cost > 0 or total_tokens > 0,  # ← 新增
)
return summary
```

- [ ] **Step 3: Run backend tests**

```bash
cd C:\Users\Yum\Desktop\Aureon-test\backend && python -m pytest tests/test_cost.py -v 2>&1 | tail -10
```

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/cost/models.py backend/app/cost/service.py
git commit -m "feat(cost): add data_available signal to CostSummary"
```

---

## Task 10: Final Integration — Run Full Test Suite & Verify Build

**Files:**
- No new files

- [ ] **Step 1: Run full frontend test suite**

```bash
cd C:\Users\Yum\Desktop\Aureon-test && npx vitest run 2>&1 | tail -20
```

Expected: All tests PASS.

- [ ] **Step 2: Run full backend test suite**

```bash
cd C:\Users\Yum\Desktop\Aureon-test\backend && python -m pytest tests/ -v --timeout=60 2>&1 | tail -10
```

Expected: All tests PASS.

- [ ] **Step 3: Verify production build**

```bash
cd C:\Users\Yum\Desktop\Aureon-test && npm run build 2>&1 | tail -10
```

Expected: Build succeeds with no errors.

- [ ] **Step 4: Verify TypeScript types**

```bash
cd C:\Users\Yum\Desktop\Aureon-test && npx tsc --noEmit 2>&1 | tail -10
```

Expected: No type errors.

- [ ] **Step 5: Final commit (if any lint fixes needed)**

```bash
git add -A && git commit -m "chore: final integration — all tests pass, build clean"
```

---

## Verification Checklist

完成所有 Task 后，按以下清单验证修复有效：

- [ ] 执行 RAG 查询后，Dashboard 实时指标**持续更新**，不归零，不闪现演示数据
- [ ] 执行 RAG 查询后，Analytics 页面**正常展示数据**（若有历史数据）或展示"暂无数据"引导
- [ ] 执行 RAG 查询后，Cost 页面**正常展示数据**或展示权限/空数据提示
- [ ] WebSocket 断开后 15 秒内，Dashboard **自动回退**到 HTTP 轮询数据
- [ ] WebSocket 重连后，Dashboard **自动叠加**实时数据
- [ ] 快速切换时间范围 3 次，最终数据**严格对应**最后一次选择
- [ ] 全新部署（Redis 为空）下，各页面展示**"暂无数据"引导**而非零值
- [ ] `npm run build` 无错误
- [ ] `npx vitest run` 全部通过
- [ ] `cd backend && python -m pytest tests/ -v` 全部通过
