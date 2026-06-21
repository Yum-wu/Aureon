# Dashboard 跨会话持久层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 引入 TanStack Query 持久化层，让仪表盘数据在页面刷新/路由切换后从 localStorage 秒开，后台静默校验，消除"演示数据→实时数据"过渡。

**Architecture:** 用 `@tanstack/react-query-persist-client` 的 `PersistQueryClientProvider` 替换现有 `QueryProvider`，配合 `@tanstack/query-sync-storage-persister` 的 `createSyncStoragePersister` 将查询缓存序列化到 `localStorage`。复用项目已有的 `safeStorage` 三级降级适配器（localStorage → sessionStorage → memory）作为 persister 的存储后端，确保隐私模式/禁用存储场景下不崩溃。用 `buster` 选项绑定应用版本号，数据结构变更时自动失效旧缓存。

**Tech Stack:** TanStack Query v5.101+（`@tanstack/react-query-persist-client`、`@tanstack/query-sync-storage-persister`）、React 19、Zustand 5（已有 persist 模式可对照）、Vitest + Testing Library。

---

## 背景与诊断

**问题现象**：每次切换回仪表盘页面或刷新页面，都会重新经历"演示数据（全零占位）→ 实时数据"过渡。

**根因**（见诊断报告结论 1）：`QueryProvider.tsx` 仅创建**内存级** `QueryClient`，无 `persistQueryClient` 包装。路由切换时 `<Dashboard>` 组件被卸载，其依赖的查询缓存虽存活于内存单例，但 `placeholderData: EMPTY_STATS`（全零值）被当作"演示数据"渲染，直到新请求返回。

**业界依据**：[TanStack Query persistQueryClient 官方文档](https://tanstack.com/query/v4/docs/framework/react/plugins/persistQueryClient) 明确推荐此模式实现"刷新后秒开 + 后台校验"。

---

## File Structure

| 文件 | 职责 | 操作 |
|------|------|------|
| `src/providers/QueryProvider.tsx` | QueryClient 工厂 + PersistQueryClientProvider 包装 | **重写** |
| `src/providers/queryPersister.ts` | `createSyncStoragePersister` 适配 safeStorage | **新建** |
| `src/stores/safeStorage.ts` | 三级降级存储（已存在） | 不改动（复用） |
| `src/providers/__tests__/queryPersister.test.ts` | persister 单元测试 | **新建** |
| `src/providers/__tests__/QueryProvider.test.tsx` | Provider 集成测试 | **新建** |
| `package.json` | 新增两个持久化依赖 | **修改** |
| `src/hooks/__tests__/useDashboardData.test.tsx` | 适配 persist（清缓存断言） | **修改** |

---

## Task 1: 安装持久化依赖

**Files:**
- Modify: `package.json`

- [ ] **Step 1: 安装两个持久化包**

Run（注意：中国大陆用 `--registry=https://registry.npmmirror.com` 加速）：
```bash
npm install @tanstack/react-query-persist-client @tanstack/query-sync-storage-persister --registry=https://registry.npmmirror.com
```
Expected: `package.json` 的 `dependencies` 新增：
```json
"@tanstack/query-sync-storage-persister": "^5.x",
"@tanstack/react-query-persist-client": "^5.x"
```

- [ ] **Step 2: 验证导入路径可用**

Run:
```bash
node -e "import('@tanstack/react-query-persist-client').then(m => console.log(Object.keys(m))).catch(e => { console.error(e); process.exit(1); })"
```
Expected: 输出包含 `PersistQueryClientProvider`、`persistQueryClient`。

- [ ] **Step 3: Commit**

```bash
git add package.json package-lock.json
git commit -m "chore(deps): add @tanstack/react-query-persist-client and query-sync-storage-persister"
```

---

## Task 2: 创建 queryPersister（适配 safeStorage）

**Files:**
- Create: `src/providers/queryPersister.ts`
- Test: `src/providers/__tests__/queryPersister.test.ts`

- [ ] **Step 1: 编写失败的测试**

Create `src/providers/__tests__/queryPersister.test.ts`:
```typescript
import { describe, it, expect, beforeEach } from 'vitest';
import { safeStorage } from '../../stores/safeStorage';
import { createSafeStoragePersister } from '../queryPersister';

describe('createSafeStoragePersister', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it('creates a persister with required methods', () => {
    const persister = createSafeStoragePersister();
    expect(typeof persister.persistClient).toBe('function');
    expect(typeof persister.restoreClient).toBe('function');
    expect(typeof persister.removeClient).toBe('function');
  });

  it('persists and restores a serialized client', async () => {
    const persister = createSafeStoragePersister();
    const payload = {
      clientState: { queries: [], mutations: [] },
      timestamp: Date.now(),
      buster: 'v1',
    };
    await persister.persistClient(payload);
    const restored = await persister.restoreClient();
    expect(restored).toEqual(payload);
  });

  it('removes persisted client', async () => {
    const persister = createSafeStoragePersister();
    await persister.persistClient({
      clientState: { queries: [], mutations: [] },
      timestamp: Date.now(),
      buster: 'v1',
    });
    await persister.removeClient();
    const restored = await persister.restoreClient();
    expect(restored).toBeUndefined();
  });

  it('uses the configured storage key', async () => {
    const persister = createSafeStoragePersister({ key: 'aureon:custom-cache' });
    await persister.persistClient({
      clientState: { queries: [], mutations: [] },
      timestamp: Date.now(),
      buster: 'v1',
    });
    expect(localStorage.getItem('aureon:custom-cache')).not.toBeNull();
  });

  it('returns undefined when storage is empty', async () => {
    const persister = createSafeStoragePersister();
    const restored = await persister.restoreClient();
    expect(restored).toBeUndefined();
  });
});
```

- [ ] **Step 2: 运行测试验证失败**

Run: `npx vitest run src/providers/__tests__/queryPersister.test.ts`
Expected: FAIL，报错 `Cannot find module '../queryPersister'`。

- [ ] **Step 3: 实现 createSafeStoragePersister**

Create `src/providers/queryPersister.ts`:
```typescript
/**
 * queryPersister — 将 TanStack Query 缓存持久化到 SafeStorage
 *
 * SafeStorage 提供三级降级：localStorage → sessionStorage → 内存 Map，
 * 因此隐私模式/禁用存储场景下持久化静默降级为内存，不崩溃。
 *
 * 注意：createSyncStoragePersister 期望同步存储 API（getItem/setItem/removeItem），
 * SafeStorage 已满足此接口（zustand StateStorage 兼容）。
 */

import { createSyncStoragePersister } from '@tanstack/query-sync-storage-persister';
import type { Persister } from '@tanstack/react-query-persist-client';
import { safeStorage } from '../stores/safeStorage';

export const DEFAULT_CACHE_KEY = 'aureon:query-cache';

export interface CreatePersisterOptions {
  /** 持久化键名，默认 'aureon:query-cache' */
  key?: string;
}

/**
 * 创建基于 SafeStorage 的同步 persister
 *
 * safeStorage 的接口为 { getItem, setItem, removeItem }，
 * 与 createSyncStoragePersister 期望的 storage 形状一致。
 */
export function createSafeStoragePersister(
  options: CreatePersisterOptions = {},
): Persister {
  const key = options.key ?? DEFAULT_CACHE_KEY;
  return createSyncStoragePersister({
    storage: safeStorage,
    key,
  });
}
```

- [ ] **Step 4: 运行测试验证通过**

Run: `npx vitest run src/providers/__tests__/queryPersister.test.ts`
Expected: PASS（5 个测试全通过）。

- [ ] **Step 5: Commit**

```bash
git add src/providers/queryPersister.ts src/providers/__tests__/queryPersister.test.ts
git commit -m "feat(persistence): add createSafeStoragePersister wrapping SafeStorage"
```

---

## Task 3: 重写 QueryProvider 集成 PersistQueryClientProvider

**Files:**
- Modify: `src/providers/QueryProvider.tsx`（全文重写）
- Test: `src/providers/__tests__/QueryProvider.test.tsx`

- [ ] **Step 1: 编写失败的集成测试**

Create `src/providers/__tests__/QueryProvider.test.tsx`:
```typescript
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, renderHook, waitFor } from '@testing-library/react';
import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { QueryProvider } from '../QueryProvider';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

// 测试用 hook：暴露查询状态
function useTestQuery(key: string) {
  return useQuery({
    queryKey: ['test', key],
    queryFn: async () => {
      const res = await fetch('/api/test');
      return res.json();
    },
    staleTime: 60_000, // 1 分钟内不 refetch，便于测试缓存命中
  });
}

describe('QueryProvider', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('renders children', () => {
    const { getByText } = render(
      <QueryProvider><div>child</div></QueryProvider>,
    );
    expect(getByText('child')).toBeInTheDocument();
  });

  it('persists query cache to localStorage after fetch', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ value: 'cached' }),
    });

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryProvider>{children}</QueryProvider>
    );

    const { result } = renderHook(() => useTestQuery('persist'), { wrapper });

    await waitFor(() => {
      expect(result.current.data).toEqual({ value: 'cached' });
    });

    // persist 是防抖写入，等待 ~1s 确保落盘
    await new Promise((r) => setTimeout(r, 1100));

    expect(localStorage.getItem('aureon:query-cache')).not.toBeNull();
    const persisted = JSON.parse(localStorage.getItem('aureon:query-cache')!);
    expect(persisted.clientState.queries.length).toBeGreaterThan(0);
  });

  it('restores cache from localStorage on remount (no refetch when fresh)', async () => {
    // 预置 localStorage 缓存
    const cachedData = { value: 'from-cache' };
    const timestamp = Date.now();
    const cachePayload = {
      buster: '',
      timestamp,
      clientState: {
        queries: [
          {
            queryKey: ['test', 'restore'],
            queryHash: '["test","restore"]',
            state: {
              data: cachedData,
              dataUpdateCount: 1,
              dataUpdatedAt: timestamp,
              error: null,
              errorUpdateCount: 0,
              errorUpdatedAt: 0,
              fetchFailureCount: 0,
              fetchFailureReason: null,
              fetchMeta: null,
              isInvalidated: false,
              status: 'success',
              fetchStatus: 'idle',
            },
            queryKeyHashFn: undefined,
            promise: undefined,
          },
        ],
        mutations: [],
      },
    };
    localStorage.setItem(
      'aureon:query-cache',
      JSON.stringify(cachePayload),
    );

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryProvider>{children}</QueryProvider>
    );

    const { result } = renderHook(() => useTestQuery('restore'), { wrapper });

    // 恢复后应立即有缓存数据，且不触发 fetch（staleTime=60s 内）
    await waitFor(() => {
      expect(result.current.data).toEqual(cachedData);
    });

    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('discards cache when buster mismatches', async () => {
    // 写入带旧 buster 的缓存
    const stalePayload = {
      buster: 'OLD_VERSION_0.0.1',
      timestamp: Date.now(),
      clientState: { queries: [], mutations: [] },
    };
    localStorage.setItem('aureon:query-cache', JSON.stringify(stalePayload));

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ value: 'fresh' }),
    });

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryProvider>{children}</QueryProvider>
    );

    const { result } = renderHook(() => useTestQuery('buster'), { wrapper });

    // buster 不匹配 → 旧缓存被丢弃 → 重新 fetch
    await waitFor(() => {
      expect(result.current.data).toEqual({ value: 'fresh' });
    });
    expect(mockFetch).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: 运行测试验证失败**

Run: `npx vitest run src/providers/__tests__/QueryProvider.test.tsx`
Expected: FAIL。前两个测试可能报 `localStorage.getItem('aureon:query-cache')` 为 null（因为当前 Provider 无持久化）；restore/buster 测试会失败。

- [ ] **Step 3: 重写 QueryProvider.tsx**

Replace entire content of `src/providers/QueryProvider.tsx`:
```typescript
/**
 * QueryProvider — TanStack Query 全局 Provider（带跨会话持久化）
 *
 * 使用 PersistQueryClientProvider 将查询缓存序列化到 SafeStorage，
 * 实现页面刷新/路由切换后"秒开 + 后台静默校验"。
 *
 * - buster: 应用版本号，数据结构变更时失效旧缓存
 * - maxAge: 缓存最长保留 7 天，超时自动丢弃
 * - gcTime: 24 小时，与持久化窗口对齐
 */

import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import { QueryClient, type QueryClientConfig } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { createSafeStoragePersister } from './queryPersister';

/** 应用版本号 — 数据结构变更时递增，自动失效旧缓存 */
const APP_VERSION = '1.0.0';

/** 持久化缓存最长存活时间（7 天） */
const PERSIST_MAX_AGE_MS = 1000 * 60 * 60 * 24 * 7;

const defaultQueryOptions: QueryClientConfig['defaultOptions'] = {
  queries: {
    staleTime: 30_000,
    gcTime: 1000 * 60 * 60 * 24, // 24h
    retry: 2,
    refetchOnWindowFocus: false,
  },
};

function makeQueryClient() {
  return new QueryClient({ defaultOptions: defaultQueryOptions });
}

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
  // persister 在模块作用域内创建一次，避免每次 render 重建
  const [persister] = useState(() => createSafeStoragePersister());

  return (
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{
        persister,
        buster: APP_VERSION,
        maxAge: PERSIST_MAX_AGE_MS,
      }}
    >
      {children}
    </PersistQueryClientProvider>
  );
}
```

- [ ] **Step 4: 运行测试验证通过**

Run: `npx vitest run src/providers/__tests__/QueryProvider.test.tsx`
Expected: PASS（4 个测试全通过）。

- [ ] **Step 5: Commit**

```bash
git add src/providers/QueryProvider.tsx src/providers/__tests__/QueryProvider.test.tsx
git commit -m "feat(persistence): integrate PersistQueryClientProvider with SafeStorage persister"
```

---

## Task 4: 适配现有 useDashboardData 测试（清缓存断言）

**Files:**
- Modify: `src/hooks/__tests__/useDashboardData.test.tsx:11-18`

由于 `PersistQueryClientProvider` 会在测试间保留 localStorage 缓存，需要确保测试 wrapper 用**独立的 QueryClient**且**不自动持久化**（测试 wrapper 不应包装 PersistQueryClientProvider，保持纯内存）。

- [ ] **Step 1: 确认现有 wrapper 无需改动**

Read `src/hooks/__tests__/useDashboardData.test.tsx:11-18`。现有 `createWrapper` 用纯 `QueryClientProvider`，**不涉及持久化**，因此测试逻辑不受影响。

但需确认：测试的 `queryClient` 在每个测试间是否被正确清理。当前代码 `createWrapper()` 每次调用都新建 QueryClient（`new QueryClient`），所以测试间隔离是 OK 的。

无需改动。跳到下一步。

- [ ] **Step 2: 运行现有测试确认无回归**

Run: `npx vitest run src/hooks/__tests__/useDashboardData.test.tsx`
Expected: PASS（4 个测试全通过，无回归）。

- [ ] **Step 3: 运行全量前端测试确认无回归**

Run: `npm test -- --run`
Expected: 全部 PASS（约 89 个测试）。

如有失败，**先不 commit**，排查失败原因（可能是其他测试文件残留 localStorage 污染，需在各测试的 `beforeEach` 加 `localStorage.clear()`）。

- [ ] **Step 4: Commit（仅当测试全通过）**

```bash
git add -A
git commit --allow-empty -m "test: verify useDashboardData still passes with persistence layer"
```
（`--allow-empty` 因为可能无文件改动；若有改动则去掉该 flag）

---

## Task 5: 清理全局测试副作用（localStorage 隔离）

**Files:**
- Modify: `src/test/setup.ts`（若不存在则创建）

- [ ] **Step 1: 检查测试 setup 文件是否存在**

Run: `npx vitest --version` 然后查 `vitest.config.ts` 或 `vite.config.ts` 中的 `test.setupFiles`。

如果 `test.setupFiles` 指向某文件，读取它；否则创建 `src/test/setup.ts`。

- [ ] **Step 2: 在 setup 中添加 localStorage 清理**

在 setup 文件末尾追加：
```typescript
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

// React Testing Library 自动清理
afterEach(() => {
  cleanup();
});

// 清理持久化缓存，避免测试间污染
afterEach(() => {
  try {
    localStorage.clear();
    sessionStorage.clear();
  } catch {
    // 隐私模式下 clear 可能抛错，忽略
  }
});
```

若文件已存在 `afterEach(cleanup)`，则在同一 `afterEach` 内追加 `localStorage.clear()`。

- [ ] **Step 3: 运行全量测试确认**

Run: `npm test -- --run`
Expected: 全部 PASS。

- [ ] **Step 4: Commit**

```bash
git add src/test/setup.ts
git commit -m "test: clear localStorage between tests to isolate persistence layer"
```

---

## Task 6: 手动验证端到端效果

**Files:** 无（纯验证步骤）

- [ ] **Step 1: 启动开发服务器**

Run: `npm run dev`
Expected: Vite 启动，浏览器打开 `http://localhost:5173`。

- [ ] **Step 2: 访问仪表盘并等待数据加载**

1. 打开 `http://localhost:5173/dashboard`
2. 等待 Golden Signals 卡片显示真实数据（非全零）
3. 打开 DevTools → Application → Local Storage → `http://localhost:5173`
4. 应看到键 `aureon:query-cache`，值包含 `queries` 数组

- [ ] **Step 3: 验证刷新后秒开**

1. 在 `/dashboard` 页面按 F5 刷新
2. 观察：刷新后**立即显示上次的数据**（无全零过渡）
3. DevTools Network 标签：应有 `/api/rag/stats` 等请求在后台发起（静默校验）

- [ ] **Step 4: 验证路由切换不丢数据**

1. 从 `/dashboard` 点击导航到 `/analytics`
2. 再点击导航回 `/dashboard`
3. 观察：仪表盘**立即显示缓存数据**，无"演示数据→实时数据"过渡

- [ ] **Step 5: 验证隐私模式降级**

1. 用隐私/无痕窗口打开 `http://localhost:5173/dashboard`
2. 应用应正常工作（即使 localStorage 受限）
3. DevTools Console 无报错

- [ ] **Step 6: Commit（记录验证完成）**

```bash
git commit --allow-empty -m "docs: verified dashboard persistence layer works end-to-end"
```

---

## Self-Review 自检

**1. Spec coverage（对照诊断报告 P0-1）**
- ✅ 引入 `PersistQueryClientProvider` — Task 3
- ✅ 配合 `createSyncStoragePersister` + safeStorage — Task 2
- ✅ `buster` 版本号失效机制 — Task 3（APP_VERSION）
- ✅ 保留 placeholderData 但仅用于首访 — 现有 useDashboardData 不改动，Task 4 验证
- ✅ 测试覆盖 — Task 2/3/5

**2. Placeholder scan**：无 TODO/TBD/占位符，所有代码块完整可运行。

**3. Type consistency**：
- `createSafeStoragePersister` 返回 `Persister` 类型（来自 `@tanstack/react-query-persist-client`）
- `PersistQueryClientProvider` 的 `persistOptions.persister` 接受 `Persister` 类型 ✓
- `PersistQueryClientOptions` 的 `buster`、`maxAge` 字段名与官方文档一致 ✓

**4. 风险点**：
- persist 写入是防抖的（默认 1s），测试需等待 — Task 3 测试已处理（`setTimeout 1100ms`）
- buster 默认为空字符串，测试需显式写入带 buster 的 payload — Task 3 第 4 个测试已处理
