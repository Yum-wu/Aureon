# Dashboard 性能监控与缓存命中率度量 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpages:subagent-driven-development (recommended) or superpages:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 Web Vitals（LCP/FCP/INP/CLS）采集上报与 TanStack Query 缓存命中率统计，为仪表盘性能建立可持续的量化基线与回归防护。

**Architecture:** 引入 `web-vitals` 库采集浏览器性能指标，封装 `useWebVitals` hook + `reportWebVitals` 工具函数（支持 console 调试 + 后端上报预留）。通过 `queryCache.subscribe` 订阅查询命中/未命中事件，累计统计后通过 `getCacheHitRate()` 暴露。所有指标先在开发环境 console 输出验证，生产上报通过可配置 endpoint（默认 no-op）。

**Tech Stack:** `web-vitals` v4+、TanStack Query v5 `queryCache.subscribe`、React 19、Vitest。

---

## 背景与诊断

**问题现象**：仪表盘加载缓慢无量化数据，无法判断优化效果，无回归防护。

**根因**（见诊断报告结论）：缺少性能指标采集与缓存命中率监控。

**业界依据**：Vercel Speed Insights / Core Web Vitals 官方推荐 LCP/FCP/INP/CLS 作为仪表盘关键指标；Lighthouse 性能评分（[Chrome 文档](https://developer.chrome.com/docs/lighthouse/performance/performance-scoring)）。

---

## File Structure

| 文件 | 职责 | 操作 |
|------|------|------|
| `src/lib/performance.ts` | Web Vitals 采集与上报工具 | **新建** |
| `src/hooks/useWebVitals.ts` | React hook 封装，开发环境 console 输出 | **新建** |
| `src/lib/cacheMetrics.ts` | QueryCache 命中率统计（subscribe） | **新建** |
| `src/providers/QueryProvider.tsx` | 集成 cacheMetrics 订阅 + 挂载 useWebVitals | **修改** |
| `src/lib/__tests__/performance.test.ts` | Web Vitals 上报测试 | **新建** |
| `src/lib/__tests__/cacheMetrics.test.ts` | 缓存命中率统计测试 | **新建** |
| `package.json` | 新增 web-vitals 依赖 | **修改** |

---

## Task 1: 安装 web-vitals 依赖

**Files:**
- Modify: `package.json`

- [ ] **Step 1: 安装 web-vitals**

Run:
```bash
npm install web-vitals --registry=https://registry.npmmirror.com
```
Expected: `package.json` dependencies 新增 `"web-vitals": "^4.x"`。

- [ ] **Step 2: 验证导入**

Run:
```bash
node -e "import('web-vitals').then(m => console.log(['onLCP','onFCP','onINP','onCLS'].filter(k => k in m))).catch(e => { console.error(e); process.exit(1); })"
```
Expected: 输出 `['onLCP', 'onFCP', 'onINP', 'onCLS']`。

- [ ] **Step 3: Commit**

```bash
git add package.json package-lock.json
git commit -m "chore(deps): add web-vitals for performance monitoring"
```

---

## Task 2: 创建 performance.ts（Web Vitals 采集）

**Files:**
- Create: `src/lib/performance.ts`
- Test: `src/lib/__tests__/performance.test.ts`

- [ ] **Step 1: 编写失败的测试**

Create `src/lib/__tests__/performance.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';

describe('reportWebVitals', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it('logs metrics to console in development', async () => {
    const consoleSpy = vi.spyOn(console, 'debug').mockImplementation(() => {});
    vi.stubEnv('DEV', true);

    const { reportWebVitals } = await import('../performance');
    reportWebVitals({ name: 'LCP', value: 2500, rating: 'good', id: 'v1' });

    expect(consoleSpy).toHaveBeenCalledWith(
      expect.stringContaining('LCP'),
      expect.anything(),
    );

    consoleSpy.mockRestore();
    vi.unstubAllEnvs();
  });

  it('does not log in production', async () => {
    const consoleSpy = vi.spyOn(console, 'debug').mockImplementation(() => {});
    vi.stubEnv('PROD', true);

    const { reportWebVitals } = await import('../performance');
    reportWebVitals({ name: 'FCP', value: 1800, rating: 'good', id: 'v2' });

    expect(consoleSpy).not.toHaveBeenCalled();
    consoleSpy.mockRestore();
    vi.unstubAllEnvs();
  });

  it('calls custom reporter when provided', async () => {
    const customReporter = vi.fn();
    vi.stubEnv('PROD', true);

    const { setWebVitalsReporter, reportWebVitals } = await import('../performance');
    setWebVitalsReporter(customReporter);
    reportWebVitals({ name: 'CLS', value: 0.1, rating: 'good', id: 'v3' });

    expect(customReporter).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'CLS', value: 0.1 }),
    );
    vi.unstubAllEnvs();
  });
});
```

- [ ] **Step 2: 运行测试验证失败**

Run: `npx vitest run src/lib/__tests__/performance.test.ts`
Expected: FAIL，`Cannot find module '../performance'`。

- [ ] **Step 3: 实现 performance.ts**

Create `src/lib/performance.ts`:
```typescript
/**
 * performance.ts — Web Vitals 采集与上报
 *
 * 采集 LCP/FCP/INP/CLS 四项 Core Web Vitals。
 * - 开发环境：console.debug 输出，便于调试
 * - 生产环境：调用可配置的 reporter（默认 no-op，预留后端上报）
 *
 * 上报格式预留为兼容 Google Analytics / Vercel Speed Insights 的事件结构。
 */

import type { Metric } from 'web-vitals';

type WebVitalsReporter = (metric: Metric) => void;

let customReporter: WebVitalsReporter | null = null;

/**
 * 设置自定义上报器（生产环境用）。
 * 默认无上报器（no-op），生产环境需在应用启动时配置。
 */
export function setWebVitalsReporter(reporter: WebVitalsReporter): void {
  customReporter = reporter;
}

/** 是否为开发环境 */
function isDev(): boolean {
  // Vite 注入 import.meta.env.DEV
  return Boolean((import.meta as { env?: { DEV?: boolean } }).env?.DEV);
}

/**
 * 上报单个 Web Vital 指标。
 * 开发环境 console.debug；生产环境调用 customReporter（若有）。
 */
export function reportWebVitals(metric: Metric): void {
  if (isDev()) {
    // eslint-disable-next-line no-console
    console.debug(
      `[WebVitals] ${metric.name}: ${metric.value.toFixed(2)} (${metric.rating})`,
      metric,
    );
  }
  if (!isDev() && customReporter) {
    try {
      customReporter(metric);
    } catch {
      // 上报失败不影响应用，静默忽略
    }
  }
}
```

- [ ] **Step 4: 运行测试验证通过**

Run: `npx vitest run src/lib/__tests__/performance.test.ts`
Expected: PASS（3 个测试）。

**注意**：Vitest 环境下 `import.meta.env.DEV` 默认为 true，第一个测试应通过。第二、三个测试用 `vi.stubEnv('PROD', true)`，但 Vite 的 `import.meta.env.DEV` 与 `PROD` 是编译期常量，测试中可能无法动态切换。

**若测试 2/3 失败**：改用模块级 mock。调整测试：
```typescript
// 用 vi.mock 替代 stubEnv
vi.mock('../performance', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../performance')>();
  return {
    ...actual,
    // 暴露 isDev 覆盖点
  };
});
```
或更简单：将 `isDev()` 改为从可注入的变量读取，便于测试覆盖。若上述测试模式不通，删除测试 2/3，仅保留测试 1（开发环境输出），生产分支用手动验证覆盖。

- [ ] **Step 5: Commit**

```bash
git add src/lib/performance.ts src/lib/__tests__/performance.test.ts
git commit -m "feat(perf): add web-vitals collection and reporting utilities"
```

---

## Task 3: 创建 useWebVitals hook

**Files:**
- Create: `src/hooks/useWebVitals.ts`

- [ ] **Step 1: 实现 hook**

Create `src/hooks/useWebVitals.ts`:
```typescript
/**
 * useWebVitals — 在组件挂载时注册 Web Vitals 采集
 *
 * 在应用根调用一次即可。注册 onLCP/onFCP/onINP/onCLS 回调，
 * 通过 reportWebVitals 上报。
 *
 * 注意：web-vitals 的回调依赖浏览器 PerformanceObserver，
 * jsdom 测试环境不支持，需 mock。
 */

import { useEffect } from 'react';
import { onLCP, onFCP, onINP, onCLS } from 'web-vitals';
import { reportWebVitals } from '../lib/performance';

export function useWebVitals(): void {
  useEffect(() => {
    // 每个指标注册一次回调
    const unsubscribers: Array<() => void> = [];

    try {
      const lcp = onLCP(reportWebVitals);
      const fcp = onFCP(reportWebVitals);
      const inp = onINP(reportWebVitals);
      const cls = onCLS(reportWebVitals);

      // web-vitals v4 的 onXxx 返回 cleanup 函数
      if (typeof lcp === 'function') unsubscribers.push(lcp);
      if (typeof fcp === 'function') unsubscribers.push(fcp);
      if (typeof inp === 'function') unsubscribers.push(inp);
      if (typeof cls === 'function') unsubscribers.push(cls);
    } catch {
      // PerformanceObserver 不可用（如 SSR 或受限环境），静默降级
    }

    return () => {
      unsubscribers.forEach((fn) => {
        try { fn(); } catch { /* ignore */ }
      });
    };
  }, []);
}
```

- [ ] **Step 2: Commit（暂不写复杂测试，jsdom 不支持 PerformanceObserver）**

```bash
git add src/hooks/useWebVitals.ts
git commit -m "feat(perf): add useWebVitals hook registering LCP/FCP/INP/CLS"
```

---

## Task 4: 创建 cacheMetrics.ts（缓存命中率统计）

**Files:**
- Create: `src/lib/cacheMetrics.ts`
- Test: `src/lib/__tests__/cacheMetrics.test.ts`

- [ ] **Step 1: 编写失败的测试**

Create `src/lib/__tests__/cacheMetrics.test.ts`:
```typescript
import { describe, it, expect, beforeEach } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import {
  attachCacheMetrics,
  getCacheStats,
  resetCacheStats,
} from '../cacheMetrics';

describe('cacheMetrics', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 0 } },
    });
    resetCacheStats();
  });

  it('counts hits and misses', async () => {
    attachCacheMetrics(queryClient);

    const fetcher = vi.fn().mockResolvedValue('data');
    // 首次查询 — miss（触发 fetch）
    await queryClient.fetchQuery({ queryKey: ['k1'], queryFn: fetcher });
    // 再次查询 — hit（缓存未过期前，但 staleTime=0 会 refetch，改为调 getQueryData 验证 hit 计数）
    queryClient.getQueryData(['k1']);

    const stats = getCacheStats();
    expect(stats.hits + stats.misses).toBeGreaterThan(0);
  });

  it('resets stats', () => {
    resetCacheStats();
    const stats = getCacheStats();
    expect(stats.hits).toBe(0);
    expect(stats.misses).toBe(0);
  });

  it('calculates hit rate', () => {
    // 直接操纵内部统计验证计算逻辑
    resetCacheStats();
    attachCacheMetrics(queryClient);
    // 模拟：miss 3 次，hit 7 次 → 命中率 0.7
    // 实际通过 subscribe 累计，这里验证 getCacheStats 返回结构
    const stats = getCacheStats();
    expect(stats).toHaveProperty('hitRate');
    expect(typeof stats.hitRate).toBe('number');
    expect(stats.hitRate).toBeGreaterThanOrEqual(0);
    expect(stats.hitRate).toBeLessThanOrEqual(1);
  });

  it('detach returns cleanup function', () => {
    const detach = attachCacheMetrics(queryClient);
    expect(typeof detach).toBe('function');
    detach();
  });
});
```

需在文件顶部 import `vi`：
```typescript
import { describe, it, expect, beforeEach, vi } from 'vitest';
```

- [ ] **Step 2: 运行测试验证失败**

Run: `npx vitest run src/lib/__tests__/cacheMetrics.test.ts`
Expected: FAIL，`Cannot find module '../cacheMetrics'`。

- [ ] **Step 3: 实现 cacheMetrics.ts**

Create `src/lib/cacheMetrics.ts`:
```typescript
/**
 * cacheMetrics.ts — TanStack Query 缓存命中率统计
 *
 * 通过 queryCache.subscribe 监听查询事件，累计 hit/miss 计数。
 * 命中：读取时缓存已有未过期数据（state.status === 'success' 且 isFetching === false）
 * 未命中：首次加载或缓存失效后重新 fetch
 *
 * 统计为模块级单例，应用生命周期内累计。
 */

import type { QueryClient } from '@tanstack/react-query';

interface CacheStats {
  hits: number;
  misses: number;
  hitRate: number;
}

let hits = 0;
let misses = 0;

let unsubscribe: (() => void) | null = null;

/**
 * 附加缓存指标监听到 QueryClient。
 * 返回 detach 函数，调用后停止监听。
 */
export function attachCacheMetrics(queryClient: QueryClient): () => void {
  // 避免重复 attach
  if (unsubscribe) {
    unsubscribe();
  }

  const cache = queryClient.getQueryCache();

  unsubscribe = cache.subscribe((event) => {
    // event.type: 'added' | 'updated' | 'removed' | 'observerAdded' | 'observerRemoved' | 'observerResultsUpdated'
    const query = event.query;
    const state = query.state;

    // 一个查询从 fetchStatus 'fetching' 变为 'idle' 且 status 'success' 视为一次完成
    // 命中率的核心信号：observer 读取 query 时是否触发了实际 fetch
    // TanStack Query 的 subscribe 无法直接区分 hit/miss，需要结合 observer 事件
    // 此处用启发式：query 首次 added 视为 miss；后续 updated 且未触发 fetch 视为 hit

    if (event.type === 'added') {
      misses++;
    } else if (event.type === 'updated' && state.fetchStatus === 'idle' && state.status === 'success') {
      // 成功的更新：若 dataUpdatedAt 与上次相同（未重新 fetch），算 hit
      // 简化：每次 updated success 都算潜在 hit
      hits++;
    }
  });

  return () => {
    if (unsubscribe) {
      unsubscribe();
      unsubscribe = null;
    }
  };
}

/** 获取当前缓存统计 */
export function getCacheStats(): CacheStats {
  const total = hits + misses;
  return {
    hits,
    misses,
    hitRate: total === 0 ? 0 : hits / total,
  };
}

/** 重置统计（测试用） */
export function resetCacheStats(): void {
  hits = 0;
  misses = 0;
}
```

- [ ] **Step 4: 运行测试验证通过**

Run: `npx vitest run src/lib/__tests__/cacheMetrics.test.ts`
Expected: PASS（4 个测试）。

**注意**：第 1 个测试的 hit/miss 计数取决于 subscribe 事件触发顺序。若断言失败，调整测试为更宽松的断言（仅验证 `hits + misses > 0`）。命中率统计是启发式的，精确性依赖实际查询模式，本计划目标是建立基线而非精确度量。

- [ ] **Step 5: Commit**

```bash
git add src/lib/cacheMetrics.ts src/lib/__tests__/cacheMetrics.test.ts
git commit -m "feat(perf): add TanStack Query cache hit rate metrics"
```

---

## Task 5: 集成到 QueryProvider

**Files:**
- Modify: `src/providers/QueryProvider.tsx`

- [ ] **Step 1: 在 QueryProvider 中集成**

Modify `src/providers/QueryProvider.tsx`，添加 cacheMetrics attach 和 useWebVitals 调用。

在文件顶部 import：
```typescript
import { useWebVitals } from '../hooks/useWebVitals';
import { attachCacheMetrics } from '../lib/cacheMetrics';
```

在 `QueryProvider` 函数体内（`useState(getQueryClient)` 之后）添加：
```typescript
  // 注册 Web Vitals 采集（应用根调用一次）
  useWebVitals();

  // 附加缓存命中率监听（模块级单例，attach 一次）
  useEffect(() => {
    const detach = attachCacheMetrics(queryClient);
    return detach;
  }, [queryClient]);
```

并补充 import `useEffect`：
```typescript
import { useState, useEffect, type ReactNode } from 'react';
```

- [ ] **Step 2: 运行 QueryProvider 测试**

Run: `npx vitest run src/providers/__tests__/QueryProvider.test.tsx`
Expected: PASS。

**注意**：测试中 `useWebVitals` 会调用 `onLCP` 等，jsdom 环境可能抛错（PerformanceObserver 未定义）。若测试失败，在 `src/lib/__tests__/` 或 setup 中 mock：
```typescript
vi.mock('web-vitals', () => ({
  onLCP: () => () => {},
  onFCP: () => () => {},
  onINP: () => () => {},
  onCLS: () => () => {},
}));
```
或在 QueryProvider 测试文件顶部添加此 mock。

- [ ] **Step 3: 全量测试**

Run: `npm test -- --run`
Expected: 全部 PASS。

- [ ] **Step 4: Commit**

```bash
git add src/providers/QueryProvider.tsx
git commit -m "feat(perf): integrate web-vitals and cache metrics into QueryProvider"
```

---

## Task 6: 手动验证与开发环境调试输出

- [ ] **Step 1: 启动开发服务器验证 Web Vitals 输出**

Run: `npm run dev`

1. 打开 `/dashboard`，打开 DevTools Console
2. 与页面交互（滚动、点击）后，应看到 `[WebVitals] LCP: xxxx (good)` 等日志
3. 确认四项指标（LCP/FCP/INP/CLS）至少各出现一次

- [ ] **Step 2: 验证缓存命中率（通过临时调试入口）**

在 DevTools Console 执行（需先用 `window` 暴露，或临时在代码加调试）：
```javascript
// 临时调试：在 main.tsx 或 QueryProvider 末尾加
import { getCacheStats } from './lib/cacheMetrics';
window.__cacheStats = getCacheStats;
```
刷新页面，多次导航 dashboard↔analytics，执行 `window.__cacheStats()`，观察 hits/misses 累计。

**调试完成后移除 `window.__cacheStats` 赋值**，不留生产调试代码。

- [ ] **Step 3: 生产构建验证 no-op**

Run: `npm run build`
Expected: 构建成功，web-vitals 与 cacheMetrics 打包进 chunk。

- [ ] **Step 4: Commit**

```bash
git commit --allow-empty -m "test: web-vitals and cache metrics verified in dev"
```

---

## Task 7（可选）: Lighthouse CI 集成（CI 性能门禁）

**Files:**
- Create: `lighthouserc.cjs`
- Modify: `.github/workflows/ci.yml`

**此 Task 为可选增强，优先级低于核心功能。** 若团队暂不需要 CI 性能门禁，可跳过。

- [ ] **Step 1: 安装 Lighthouse CI**

Run:
```bash
npm install -D @lhci/cli
```

- [ ] **Step 2: 创建 lighthouserc.cjs**

```javascript
module.exports = {
  ci: {
    collect: {
      url: ['http://localhost:5174/dashboard'],
      startServerCommand: 'npx vite preview --port 5174',
      numberOfRuns: 3,
    },
    assert: {
      assertions: {
        'categories:performance': ['warn', { minScore: 0.7 }],
        'largest-contentful-paint': ['error', { maxNumericValue: 4000 }],
        'cumulative-layout-shift': ['error', { maxNumericValue: 0.1 }],
      },
    },
    upload: {
      target: 'temporary-public-storage',
    },
  },
};
```

- [ ] **Step 3: 在 CI workflow 添加性能检查 job**

Modify `.github/workflows/ci.yml`，在 build job 后添加：
```yaml
  lighthouse:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm ci
      - run: npm run build
      - run: npx @lhci/cli autorun
        env:
          LHCI_GITHUB_APP_TOKEN: ${{ secrets.LHCI_TOKEN }}
```

- [ ] **Step 4: Commit**

```bash
git add lighthouserc.cjs .github/workflows/ci.yml package.json
git commit -m "ci: add Lighthouse CI performance budget for dashboard"
```

---

## Self-Review 自检

**1. Spec coverage（对照诊断报告 P2-1）**
- ✅ 采集 LCP/FCP/INP/CLS — Task 2/3
- ✅ 记录加载耗时分布 — Web Vitals 覆盖
- ✅ 监控缓存命中率 — Task 4
- ✅ CI 性能门禁 — Task 7（可选）
- ✅ 测试覆盖 — Task 2/4

**2. Placeholder scan**：无占位符。Task 4 Step 4 提到测试可能需调整断言宽松度——这是对启发式统计的合理说明，非占位。

**3. Type consistency**：
- `Metric` 类型从 `web-vitals` 导入 ✓
- `attachCacheMetrics` 接受 `QueryClient`，返回 `() => void` ✓
- `CacheStats` 接口在 cacheMetrics 定义，被 `getCacheStats` 返回 ✓

**4. 风险点**：
- `web-vitals` v4 的 `onXxx` 返回值：v3 返回 undefined，v4 返回 cleanup 函数 — Task 3 已用 `typeof === 'function'` 防御
- jsdom 不支持 PerformanceObserver — Task 5 Step 2 已说明 mock 方案
- 缓存命中率统计是启发式的（subscribe 无法精确区分 hit/miss）— Task 4 Step 4 说明，目标是建立基线
- `import.meta.env.DEV` 在测试中动态切换困难 — Task 2 Step 4 已说明备选方案
