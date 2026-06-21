# Dashboard 渐进式渲染（拆分 loading 聚合）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpages:subagent-driven-development (recommended) or superpages:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 拆分仪表盘的"任一查询未完成即整体显示骨架屏"的阻塞式渲染，改为各区块独立管理加载态、用最快可用的数据层先渲染，降低首屏可交互时间。

**Architecture:** 将 `useDashboardData` 的聚合 `isLoading`（`||` 短路）改为**按查询暴露独立状态**，Dashboard 各区块独立判断渲染时机。对 `useAnalyticsData` 和 `useCostDataQuery` 同样从 `results.some(r => r.isLoading)` 改为暴露各查询独立状态。配合 P0-1 持久化层，缓存命中的区块直接渲染数据，仅未命中的区块显示局部骨架。

**Tech Stack:** TanStack Query v5（`useQuery`/`useQueries` 的独立返回值）、React 19、Vitest + Testing Library。

---

## 背景与诊断

**问题现象**：仪表盘加载缓慢，需等待多层数据齐备后才渲染完整内容。

**根因**（见诊断报告结论 5）：`useDashboardData.ts:99` 的 `isLoading = statsQuery.isLoading || recentQuery.isLoading || volumeQuery.isLoading` 用 `||` 聚合，任一未完成即整体骨架；`Dashboard.tsx:381` 用此聚合 `loading` 决定整页渲染。`useAnalyticsData.ts:106` 和 `useCostDataQuery` 同样的 `results.some(r => r.isLoading)` 模式。

**业界依据**：SWR stale-while-revalidate 与 Vercel 热路径优化理念——"先用最快的可用数据层渲染骨架，后续数据到达后增量更新"，而非"等齐了再渲染"。

---

## File Structure

| 文件 | 职责 | 操作 |
|------|------|------|
| `src/hooks/useDashboardData.ts` | 暴露各查询独立 isLoading/isFetching | **修改** |
| `src/pages/Dashboard.tsx` | 各区块独立判断加载态，局部骨架 | **修改** |
| `src/hooks/useAnalyticsData.ts` | 暴露各查询独立 isLoading | **修改** |
| `src/pages/Analytics.tsx` | 局部骨架替代整页骨架 | **修改** |
| `src/hooks/useCostDataQuery.ts` | 暴露各查询独立 isLoading | **修改** |
| `src/pages/CostGovernance.tsx` | 局部骨架替代整页骨架 | **修改** |
| 对应 `__tests__/` | 适配独立状态语义 | **修改** |

---

## Task 1: useDashboardData 暴露独立加载态

**Files:**
- Modify: `src/hooks/useDashboardData.ts`

- [ ] **Step 1: 修改返回类型，增加分项状态**

Modify `src/hooks/useDashboardData.ts`。更新 `DashboardData` 接口（第 31-38 行）和返回值。

Replace `DashboardData` 接口：
```typescript
interface DashboardData {
  stats: StatsResponse | undefined;
  recentQueries: RecentQuery[];
  queryVolume: QueryVolumePoint[];
  /** 整体加载态（保留向后兼容，任一首次加载中即为 true） */
  isLoading: boolean;
  /** 各查询的独立首次加载态，供区块级渐进渲染 */
  isLoadingStats: boolean;
  isLoadingVolume: boolean;
  error: Error | null;
  refetch: () => void;
}
```

更新 hook 返回值（函数末尾，原第 102-113 行）：
```typescript
  return {
    stats: statsQuery.data,
    recentQueries: recentQuery.data?.queries ?? [],
    queryVolume: volumeQuery.data?.data ?? [],
    isLoading,
    isLoadingStats: statsQuery.isLoading,
    isLoadingVolume: volumeQuery.isLoading,
    error: error as Error | null,
    refetch: () => {
      statsQuery.refetch();
      recentQuery.refetch();
      volumeQuery.refetch();
    },
  };
```

（`isLoading` 聚合逻辑保留，向后兼容；新增 `isLoadingStats`/`isLoadingVolume` 供渐进渲染。`recentQueries` 不在首屏关键路径，不单独暴露。）

- [ ] **Step 2: 运行现有测试确认无回归**

Run: `npx vitest run src/hooks/__tests__/useDashboardData.test.tsx`
Expected: PASS（现有测试不断言新字段，仅检查已有字段）。

- [ ] **Step 3: Commit**

```bash
git add src/hooks/useDashboardData.ts
git commit -m "feat(dashboard): expose per-query loading states for progressive rendering"
```

---

## Task 2: Dashboard 各区块渐进渲染

**Files:**
- Modify: `src/pages/Dashboard.tsx`

**当前逻辑**（第 381-384 行）：`{loading && <LoadingSkeleton />}` 整页阻塞。改为：Golden Signals 区块用 `isLoadingStats`，查询量图表用 `isLoadingVolume`，各自局部骨架。

- [ ] **Step 1: 解构新的加载态字段**

Modify `src/pages/Dashboard.tsx` 第 243 行，解构新字段：
```typescript
  const { stats, queryVolume, isLoading: loading, isLoadingStats, isLoadingVolume, error, refetch } = useDashboardData();
```

- [ ] **Step 2: 改造整页骨架判断**

**关键改动**：整页骨架仅在"完全无数据且首次加载"时显示；一旦 stats 到达，立即渲染主结构，未到达的子区块用局部占位。

Modify `src/pages/Dashboard.tsx` 第 381-384 行：
```tsx
        {/* 整页骨架仅在最冷启动（无任何数据）时显示 */}
        {loading && !stats && <LoadingSkeleton />}
        {error && !stats && <ErrorState message={error instanceof Error ? error.message : String(error)} onRetry={refetch} />}

        {(stats || !loading) && !error && (
```

（原 `{!loading && !error && (` 改为 `(stats || !loading) && !error && (`，这样 stats 一到就渲染，不等 volume。）

- [ ] **Step 3: 查询量图表局部骨架**

Modify 查询量图表区块（约第 465-471 行），增加 `isLoadingVolume` 时的局部占位：
```tsx
              {isLoadingVolume && queryVolumeChartData.length === 0 ? (
                <div className="rounded-lg border bg-[var(--bg-secondary)] border-[var(--border)] flex items-center justify-center h-[300px]">
                  <div className="animate-pulse h-4 w-24 bg-[var(--bg-tertiary)] rounded" />
                </div>
              ) : queryVolumeChartData.length > 0 ? (
                <BarChart data={queryVolumeChartData} keys={['value']} indexBy="label" title={t('dashboard.charts.query_volume')} />
              ) : (
                <div className="rounded-lg border bg-[var(--bg-secondary)] border-[var(--border)] flex items-center justify-center h-[300px] text-[var(--text-tertiary)] text-sm">
                  {t('dashboard.no_data', '暂无数据')}
                </div>
              )}
```

- [ ] **Step 4: 运行 Dashboard 测试**

Run: `npx vitest run src/pages/__tests__/Dashboard.test.tsx`
Expected: PASS。若失败，检查测试中 `mockUseDashboardData` 是否返回了新字段——现有测试（第 64-67 行 mock `useDashboardData`）可能需要补充返回值。

检查 `src/pages/__tests__/Dashboard.test.tsx`，在每个 `mockUseDashboardData.mockReturnValue({...})` 调用中补充：
```typescript
      isLoadingStats: false,
      isLoadingVolume: false,
```

- [ ] **Step 5: Commit**

```bash
git add src/pages/Dashboard.tsx src/pages/__tests__/Dashboard.test.tsx
git commit -m "feat(dashboard): progressive rendering with per-section skeletons"
```

---

## Task 3: useAnalyticsData 暴露独立加载态

**Files:**
- Modify: `src/hooks/useAnalyticsData.ts:53-61, 105-119`

- [ ] **Step 1: 修改返回类型与实现**

Modify `src/hooks/useAnalyticsData.ts`。

更新 `AnalyticsResult` 接口（第 53-61 行）：
```typescript
interface AnalyticsResult {
  usage: UsageData | null;
  latency: LatencyData | null;
  tokens: TokenData | null;
  cache: CacheData | null;
  /** 整体加载态（向后兼容） */
  isLoading: boolean;
  /** 各查询独立加载态 */
  isLoadingUsage: boolean;
  isLoadingLatency: boolean;
  isLoadingTokens: boolean;
  isLoadingCache: boolean;
  error: Error | null;
  refetch: () => void;
}
```

更新返回值（第 109-119 行）：
```typescript
  return {
    usage: usageQ.data ?? null,
    latency: latencyQ.data ?? null,
    tokens: tokensQ.data ?? null,
    cache: cacheQ.data ?? null,
    isLoading,
    isLoadingUsage: usageQ.isLoading,
    isLoadingLatency: latencyQ.isLoading,
    isLoadingTokens: tokensQ.isLoading,
    isLoadingCache: cacheQ.isLoading,
    error,
    refetch: () => {
      results.forEach((r) => r.refetch());
    },
  };
```

- [ ] **Step 2: 运行测试**

Run: `npx vitest run src/hooks/__tests__/useAnalyticsData.test.tsx`
Expected: PASS。

- [ ] **Step 3: Commit**

```bash
git add src/hooks/useAnalyticsData.ts
git commit -m "feat(analytics): expose per-query loading states"
```

---

## Task 4: Analytics 页面局部骨架

**Files:**
- Modify: `src/pages/Analytics.tsx`

- [ ] **Step 1: 读取 Analytics.tsx 当前结构**

Read `src/pages/Analytics.tsx`，定位整页 `isLoading` 判断与各区块渲染。

- [ ] **Step 2: 解构新字段并改造渲染**

在 Analytics.tsx 顶部解构处添加新字段：
```typescript
const {
  usage, latency, tokens, cache,
  isLoading, isLoadingUsage, isLoadingLatency, isLoadingTokens, isLoadingCache,
  error, refetch
} = useAnalyticsData(timeRange);
```

将整页 `{isLoading ? <Skeleton/> : <Content/>}` 改为：保留整体 error 处理，但各数据卡片用独立 `isLoadingXxx` 显示局部骨架。具体改动取决于 Analytics.tsx 现有结构——若它是单一 `<Card>` 列表，则每个 Card 内部判断 `isLoadingXxx`。

**示例模式**（根据实际结构适配）：
```tsx
< MetricCard
  title={t('analytics.usage')}
  value={usage?.total ?? '—'}
  loading={isLoadingUsage}
/>
```

- [ ] **Step 3: 运行 Analytics 测试**

Run: `npx vitest run src/pages/__tests__/Analytics.test.tsx`
Expected: PASS。若测试断言整页 loading，需适配。

- [ ] **Step 4: Commit**

```bash
git add src/pages/Analytics.tsx src/pages/__tests__/Analytics.test.tsx
git commit -m "feat(analytics): per-section skeleton rendering"
```

---

## Task 5: useCostDataQuery 暴露独立加载态

**Files:**
- Modify: `src/hooks/useCostDataQuery.ts:46-54, 56+`

- [ ] **Step 1: 修改返回类型与实现**

Modify `src/hooks/useCostDataQuery.ts`。

更新 `CostDataResult` 接口：
```typescript
interface CostDataResult {
  summary: CostSummary | null;
  trends: CostTrendPoint[];
  breakdown: CostBreakdown[];
  topConsumers: TopConsumer[];
  isLoading: boolean;
  isLoadingSummary: boolean;
  isLoadingTrends: boolean;
  isLoadingBreakdown: boolean;
  isLoadingConsumers: boolean;
  error: Error | null;
  refetch: () => void;
}
```

在返回值中补充各独立加载态（参照现有 `results` 解构，逐个映射）：
```typescript
  const [summaryQ, trendsQ, breakdownQ, consumersQ] = results;
  // ...
  return {
    summary: summaryQ.data ?? null,
    trends: trendsQ.data ?? [],
    breakdown: breakdownQ.data ?? [],
    topConsumers: consumersQ.data ?? [],
    isLoading,
    isLoadingSummary: summaryQ.isLoading,
    isLoadingTrends: trendsQ.isLoading,
    isLoadingBreakdown: breakdownQ.isLoading,
    isLoadingConsumers: consumersQ.isLoading,
    error,
    refetch: () => { results.forEach((r) => r.refetch()); },
  };
```

- [ ] **Step 2: 运行测试**

Run: `npx vitest run src/hooks/__tests__/useCostDataQuery.test.tsx`
Expected: PASS。

- [ ] **Step 3: Commit**

```bash
git add src/hooks/useCostDataQuery.ts
git commit -m "feat(cost): expose per-query loading states"
```

---

## Task 6: CostGovernance 页面局部骨架

**Files:**
- Modify: `src/pages/CostGovernance.tsx`

- [ ] **Step 1: 读取并改造 CostGovernance.tsx**

Read `src/pages/CostGovernance.tsx`，按 Task 4 Analytics 的同样模式：解构新字段，各区块用独立 `isLoadingXxx` 显示局部骨架。

- [ ] **Step 2: 运行测试**

Run: `npx vitest run src/pages/__tests__/CostGovernance.test.tsx`（若存在）
Expected: PASS。

- [ ] **Step 3: Commit**

```bash
git add src/pages/CostGovernance.tsx
git commit -m "feat(cost): per-section skeleton rendering"
```

---

## Task 7: 全量回归与手动验证

- [ ] **Step 1: 全量测试**

Run: `npm test -- --run`
Expected: 全部 PASS。

- [ ] **Step 2: lint**

Run: `npm run lint`
Expected: 无 error。

- [ ] **Step 3: 手动验证渐进渲染**

1. `npm run dev`，清空 localStorage 缓存
2. 访问 `/dashboard`，用 Performance 面板录制
3. **期望**：stats 到达后 Golden Signals 立即渲染，查询量图表若未到则显示局部骨架（灰色小块），数据到达后填充
4. 对比改造前后：首屏可交互时间应明显提前

- [ ] **Step 4: DevTools Profiler 对比**

1. React DevTools Profiler 录制首次加载
2. 检查首次 commit 时间是否早于"所有查询完成"时间
3. 理想情况：stats 到达即首次 commit，volume/recent 后续增量更新

- [ ] **Step 5: Commit**

```bash
git commit --allow-empty -m "test: progressive rendering verified across dashboard/analytics/cost"
```

---

## Self-Review 自检

**1. Spec coverage（对照诊断报告 P1-2）**
- ✅ 拆分 `loading` 聚合逻辑 — Task 1
- ✅ 各查询独立管理 isLoading — Task 1/3/5
- ✅ 优先用最快可用层渲染 — Task 2/4/6
- ✅ 引入 keepPreviousData 切换数据保留旧值 — P1-1 计划已覆盖，本计划聚焦独立加载态
- ✅ 测试覆盖 — 各 Task 含测试步骤

**2. Placeholder scan**：Task 4/6 对 Analytics.tsx/CostGovernance.tsx 的改动标注"根据实际结构适配"，这是因为未读取这两个文件全文。**执行时需先 Read 文件确认结构再改**，不可照搬示例代码。这是合理的——计划已明确指出"Read 文件"为第一步。

**3. Type consistency**：
- 所有新增字段命名一致：`isLoadingXxx`（Xxx 为分项名）✓
- `useDashboardData` 的 `isLoadingStats`/`isLoadingVolume` 与 Dashboard.tsx 解构一致 ✓
- 三个 hook 都保留 `isLoading` 聚合字段（向后兼容）✓

**4. 执行顺序依赖**：本计划独立于 P0-1/P0-2，但若三者都落地，效果叠加（缓存秒开 + 连接保持 + 渐进渲染）。建议顺序：P0-1 → P0-2 → P1-1 → P1-2。

**5. 风险点**：
- Analytics.tsx/CostGovernance.tsx 未读取全文，改动需先 Read — Task 4/6 已强调
- 局部骨架需与现有设计 token 一致（用 `animate-pulse` + `bg-[var(--bg-tertiary)]`）✓
- 测试 mock 需补充新字段，否则解构得 undefined，`isLoadingStats` 为 falsy 不会触发骨架 — Task 2 Step 4 已说明
