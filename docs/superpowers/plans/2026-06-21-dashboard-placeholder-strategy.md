# Dashboard 占位策略优化（骨架屏替代数值占位）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将仪表盘加载态从"全零数值占位（被误认为演示数据）"改为"结构性骨架屏"，消除用户的"假数据"观感，让加载预期更合理。

**Architecture:** 移除 `useDashboardData` 三个查询的 `placeholderData` 全零值，让 `isLoading` 在真正无缓存时生效，触发已有的 `LoadingSkeleton` 组件渲染。同时清理 `Dashboard.tsx` 中硬编码的假趋势值（`trend={hasRealtimeData ? -5 : undefined}`）和条件过于宽松的"演示模式水印"。借助 P0-1 持久化层，二次访问将直接显示缓存数据（不触发骨架屏），骨架屏仅出现在首次访问或缓存失效时。

**Tech Stack:** TanStack Query v5（`placeholderData`/`keepPreviousData` 选项）、React 19、Vitest + Testing Library。

---

## 背景与诊断

**问题现象**：用户将加载态的全零卡片感知为"演示数据"。

**根因**（见诊断报告结论 3）：`useDashboardData.ts:41-47` 的 `EMPTY_STATS` 是全零数值；`Dashboard.tsx:401,408,416` 硬编码了假趋势值；`Dashboard.tsx:387-393` 的琥珀色"演示模式水印"条件 `!hasRealtimeData` 在 WS 未连接时长期为真。

**业界依据**：[Nielsen Norman Group Skeleton Screens 101](https://www.nngroup.com/articles/skeleton-screens/)——骨架屏承载布局结构而非数据值，避免用户误读为真实数据。

---

## File Structure

| 文件 | 职责 | 操作 |
|------|------|------|
| `src/hooks/useDashboardData.ts` | 移除 placeholderData 全零值，调整 isLoading 语义 | **修改** |
| `src/pages/Dashboard.tsx` | 移除假趋势值，收紧演示模式水印条件 | **修改** |
| `src/hooks/__tests__/useDashboardData.test.tsx` | 适配 isLoading 语义变化 | **修改** |
| `src/pages/__tests__/Dashboard.test.tsx` | 适配骨架屏触发条件 | **修改** |

---

## Task 1: 调整 useDashboardData 的占位策略

**Files:**
- Modify: `src/hooks/useDashboardData.ts:41-47, 56-114`

- [ ] **Step 1: 编写失败的新测试（验证无缓存时 isLoading=true）**

在 `src/hooks/__tests__/useDashboardData.test.tsx` 的第一个测试 `'starts with loading state'` 中，修改断言。当前测试（第 29-38 行）期望 `isLoading` 为 false（因为有 placeholderData）。改为期望无缓存时 isLoading=true：

Replace `src/hooks/__tests__/useDashboardData.test.tsx:29-38`:
```typescript
  it('starts with loading state when no cache', () => {
    mockFetch.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useDashboardData(), {
      wrapper: createWrapper(),
    });
    // 无 placeholderData 后，首次加载 isLoading 为 true，stats 为 undefined
    expect(result.current.isLoading).toBe(true);
    expect(result.current.stats).toBeUndefined();
    expect(result.current.error).toBeNull();
  });
```

- [ ] **Step 2: 运行测试验证失败**

Run: `npx vitest run src/hooks/__tests__/useDashboardData.test.tsx`
Expected: FAIL，`isLoading` 实际为 false（因为还有 placeholderData）。

- [ ] **Step 3: 移除 placeholderData，改用 keepPreviousData**

Modify `src/hooks/useDashboardData.ts`。

首先删除 `EMPTY_STATS` 常量（第 41-47 行）：
```typescript
// 删除这段：
// /** 空 StatsResponse 占位（避免加载闪烁） */
// const EMPTY_STATS: StatsResponse = { ... };
```

然后将三个 `useQuery` 调用中的 `placeholderData` 替换为 `placeholderData: keepPreviousData`（从 react-query 导入）。

更新 import（第 11 行）：
```typescript
import { useQuery, keepPreviousData } from '@tanstack/react-query';
```

修改 statsQuery（第 57-70 行），删除 `placeholderData: EMPTY_STATS`，改为：
```typescript
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
    staleTime: 10_000,
    refetchInterval: 15_000,
    placeholderData: keepPreviousData,
  });
```

修改 recentQuery（第 72-85 行），删除 `placeholderData: { queries: [] }`：
```typescript
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
    staleTime: 10_000,
    refetchInterval: 15_000,
    placeholderData: keepPreviousData,
  });
```

修改 volumeQuery（第 87-97 行），删除 `placeholderData: { data: [] }`：
```typescript
  const volumeQuery = useQuery<{ data: QueryVolumePoint[] }>({
    queryKey: DASHBOARD_QUERY_KEYS.volume,
    queryFn: async ({ signal }) => {
      const res = await authFetch(VOLUME_URL, { signal });
      if (!res.ok) return { data: [] };
      return res.json();
    },
    staleTime: 10_000,
    refetchInterval: 15_000,
    placeholderData: keepPreviousData,
  });
```

- [ ] **Step 4: 运行测试验证通过**

Run: `npx vitest run src/hooks/__tests__/useDashboardData.test.tsx`
Expected: PASS（4 个测试全通过）。

注意：第 90-105 行的 `'provides refetch function'` 测试用 `mockFetch.mockResolvedValue` 返回全零 stats，现在 `isLoading` 会先为 true 再变 false，`waitFor` 会等待——确认测试通过。

- [ ] **Step 5: Commit**

```bash
git add src/hooks/useDashboardData.ts src/hooks/__tests__/useDashboardData.test.tsx
git commit -m "refactor(dashboard): replace zero placeholders with keepPreviousData"
```

---

## Task 2: 清理 Dashboard.tsx 的假趋势值

**Files:**
- Modify: `src/pages/Dashboard.tsx:396-419`（三个 GoldenSignalCard 的 trend 属性）

- [ ] **Step 1: 移除硬编码的 trend 假值**

当前第 400-401 行 `trend={hasRealtimeData ? -5 : undefined}`、第 408 行 `trend={hasRealtimeData ? 3 : undefined}`、第 416 行 `trend={hasRealtimeData ? -2 : undefined}` 是硬编码假值。

修改 `src/pages/Dashboard.tsx`，将三处 `trend` 属性全部删除（让 `TrendArrow` 不渲染，因为没有趋势数据来源）：

Latency 卡片（约第 396-403 行）：
```tsx
              <GoldenSignalCard
                label={t('dashboard.golden_signals.latency')}
                value={metrics?.ttft_p50 ?? '—'}
                unit="ms"
                sparklineData={metrics?.latency_trend?.length ? metrics.latency_trend : undefined}
                tooltip={t('dashboard.golden_signals.latency_tooltip')}
              />
```

Traffic 卡片（约第 404-411 行）：
```tsx
              <GoldenSignalCard
                label={t('dashboard.golden_signals.traffic')}
                value={metrics?.qps?.toFixed(2) ?? '—'}
                unit="QPS"
                sparklineData={undefined}
                tooltip={t('dashboard.golden_signals.traffic_tooltip')}
              />
```

Errors 卡片（约第 412-419 行）：
```tsx
              <GoldenSignalCard
                label={t('dashboard.golden_signals.errors')}
                value={metrics?.error_rate?.toFixed(1) ?? '—'}
                unit="%"
                sparklineData={undefined}
                tooltip={t('dashboard.golden_signals.errors_tooltip')}
              />
```

- [ ] **Step 2: 运行 Dashboard 页面测试**

Run: `npx vitest run src/pages/__tests__/Dashboard.test.tsx`
Expected: PASS（现有测试不断言 trend 值，不受影响）。

- [ ] **Step 3: Commit**

```bash
git add src/pages/Dashboard.tsx
git commit -m "refactor(dashboard): remove hardcoded fake trend values"
```

---

## Task 3: 收紧"演示模式水印"条件

**Files:**
- Modify: `src/pages/Dashboard.tsx:387-393`

**当前问题**：`!hasRealtimeData` 在 WS 未连上时就为真，导致琥珀色"演示模式"水印频繁闪现。水印应仅在"既无实时数据、也无缓存数据"时才显示（真正的无数据状态）。

- [ ] **Step 1: 修改水印条件**

Modify `src/pages/Dashboard.tsx` 第 387-393 行。将条件从 `!hasRealtimeData` 改为"既无实时数据，也无任何 HTTP 统计数据"：

Replace:
```tsx
            {/* ── 演示模式水印 ── */}
            {!hasRealtimeData && !loading && !error && (
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-center">
                <p className="text-sm font-medium text-amber-400">
                  <span className="inline-flex items-center gap-1"><AlertTriangle size={14} /> {t('dashboard.demo_mode')}</span>
                </p>
              </div>
            )}
```
With:
```tsx
            {/* ── 无数据提示 ── 仅当 HTTP 与实时数据都为空时显示（真正的冷启动状态） */}
            {!hasRealtimeData && !stats?.query_count_24h && !loading && !error && (
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-center">
                <p className="text-sm font-medium text-amber-400">
                  <span className="inline-flex items-center gap-1"><AlertTriangle size={14} /> {t('dashboard.demo_mode')}</span>
                </p>
              </div>
            )}
```

- [ ] **Step 2: 更新 Dashboard.test.tsx 断言（若涉及）**

Read `src/pages/__tests__/Dashboard.test.tsx`，搜索 `demo_mode`。若现有测试不断言 `demo_mode` 出现，则无需改动。

若测试中 mock 的 `stats` 有 `query_count_24h: 1234`（第 140 行确有），则水印不会显示，符合预期。

Run: `npx vitest run src/pages/__tests__/Dashboard.test.tsx`
Expected: PASS。

- [ ] **Step 3: Commit**

```bash
git add src/pages/Dashboard.tsx
git commit -m "fix(dashboard): tighten demo-mode watermark to true cold-start state"
```

---

## Task 4: 全量回归测试与手动验证

- [ ] **Step 1: 运行全量前端测试**

Run: `npm test -- --run`
Expected: 全部 PASS（约 89 个测试）。

- [ ] **Step 2: 运行 lint**

Run: `npm run lint`
Expected: 无 error。

- [ ] **Step 3: 手动验证首访骨架屏**

1. `npm run dev`
2. 打开 DevTools → Application → Local Storage，删除 `aureon:query-cache`（模拟首访）
3. 刷新 `/dashboard`
4. **期望**：先看到骨架屏（`LoadingSkeleton`，灰色块），数据到达后平滑切换为真实卡片，**无全零"假数据"过渡**

- [ ] **Step 4: 手动验证二次访问秒开**

1. 数据加载完成后，F5 刷新
2. **期望**：立即显示上次的缓存数据（无骨架屏，无全零），后台静默校验

- [ ] **Step 5: 验证趋势箭头不再出现假值**

1. 在 `/dashboard`，观察 Golden Signals 卡片下方
2. **期望**：Latency/Traffic/Errors 卡片**无趋势箭头**（因为后端暂无趋势数据），Saturation 卡片仍显示进度条

- [ ] **Step 6: Commit**

```bash
git commit --allow-empty -m "test: skeleton loading verified for cold start, cache hit verified for revisit"
```

---

## Self-Review 自检

**1. Spec coverage（对照诊断报告 P1-1）**
- ✅ 移除 `EMPTY_STATS` 全零占位 — Task 1
- ✅ 改用骨架屏 — Task 1（移除 placeholderData 后 isLoading 触发 LoadingSkeleton）
- ✅ 移除硬编码 trend 假值 — Task 2
- ✅ 收紧演示模式水印 — Task 3
- ✅ 借助持久化层让二次访问秒开 — Task 4 验证

**2. Placeholder scan**：无占位符，所有代码块完整。

**3. Type consistency**：
- `keepPreviousData` 从 `@tanstack/react-query` 导入 ✓
- 移除 `EMPTY_STATS` 后，`stats: statsQuery.data` 类型为 `StatsResponse | undefined`，Dashboard 已用 `stats?.query_count_24h` 可选链处理 ✓
- `placeholderData: keepPreviousData` 接受任何值，与原 `EMPTY_STATS` 类型兼容 ✓

**4. 依赖说明**：本计划**假设 P0-1（持久化层）已落地**。若 P0-1 未实施，二次访问仍会触发骨架屏（因无缓存），但至少消除了"全零假数据"观感。建议执行顺序：P0-1 → 本计划。

**5. 风险点**：
- `keepPreviousData` 在切换查询键时保留旧数据，但 Dashboard 的查询键固定（无参数），所以效果等同于"首次 undefined，后续保留" ✓
- Task 1 测试 `'provides refetch function'`（第 90-105 行）原本依赖 placeholderData 让 isLoading 立即为 false，改动后需 waitFor——已在 Step 4 说明
