# Aureon 仪表盘性能与持久化优化 — 实施计划总索引

> **创建日期**：2026-06-21
> **诊断依据**：[仪表盘性能与持久化诊断报告](../../reports/dashboard-performance-diagnosis.md)（上一轮调研产出）
> **计划总数**：6 份独立实施计划，覆盖 P0/P1/P2 三个优先级
> **编写工具**：superpowers:writing-plans 技能

---

## 一、背景

用户反馈仪表盘存在三类问题：
1. **加载缓慢**：页面加载耗时长，需等待才能看到完整数据
2. **重复加载**：每次切换回仪表盘都重新建立连接、重新获取数据
3. **不合理过渡**：每次切换都经历"演示数据 → 实时数据"，已加载的数据未被保持

基于桌面调研（Vercel Dashboard 51→94 案例、NN/g 骨架屏研究、SWR/TanStack Query 官方文档）与项目代码反查，产出诊断报告，识别出 5 条核心根因。本索引文档汇总针对这些根因的 6 份实施计划。

---

## 二、计划清单与执行顺序

### 推荐执行顺序（依赖关系驱动）

```
P0-1 (持久层) ──┐
               ├─→ P1-1 (占位策略) ──┐
P0-2 (WS 全局化) ┘                    ├─→ P2-1 (性能监控)
                                      │
                                      └─→ P2-2 (版本管理) ←── 依赖 P0-1 的 buster
P1-2 (渐进渲染) ─────────────────────────→ (独立，可并行)
```

| 序号 | 优先级 | 计划文件 | 解决的核心问题 | 依赖 | 预期感知改善 |
|------|--------|---------|---------------|------|------------|
| 1 | 🔴 P0 | [dashboard-persistence-layer.md](./2026-06-21-dashboard-persistence-layer.md) | 刷新/切换页面秒开，消除"演示数据→实时数据"过渡 | 无 | **最显著**：二次访问首屏 < 200ms |
| 2 | 🔴 P0 | [dashboard-websocket-globalization.md](./2026-06-21-dashboard-websocket-globalization.md) | 路由切换不重建 WS 连接 | 无 | 消除每次进入的握手延迟（200-500ms）+ 首 tick 等待 |
| 3 | 🟠 P1 | [dashboard-placeholder-strategy.md](./2026-06-21-dashboard-placeholder-strategy.md) | 加载态用骨架屏替代全零"假数据" | 建议 P0-1 先行 | 消除"假数据"观感 |
| 4 | 🟠 P1 | [dashboard-progressive-rendering.md](./2026-06-21-dashboard-progressive-rendering.md) | 各区块独立加载，不"等齐再渲染" | 无（建议 P0-1 后） | 首屏可交互时间降低 30-50% |
| 5 | 🟡 P2 | [dashboard-performance-monitoring.md](./2026-06-21-dashboard-performance-monitoring.md) | 建立 LCP/FCP/INP/CLS 采集与缓存命中率监控 | 无 | 建立可持续量化基线 |
| 6 | 🟡 P2 | [dashboard-state-versioning.md](./2026-06-21-dashboard-state-versioning.md) | 状态结构变更的平滑迁移与缓存失效 | Task 3 依赖 P0-1 | 避免线上旧缓存导致渲染异常 |

### 执行顺序说明

- **P0-1 与 P0-2 可并行**：两者解决不同问题（持久层 vs 连接层），文件交集仅在 `QueryProvider.tsx`（P2-2 才改它），无冲突。
- **P1-1 建议在 P0-1 之后**：P1-1 移除 `placeholderData` 全零值后，若没有 P0-1 的持久化层兜底，二次访问仍会触发骨架屏。P0-1 落地后，二次访问直接显示缓存数据，骨架屏仅首访出现。
- **P1-2 独立可并行**：渐进式渲染的改动（拆分 isLoading）不依赖其他计划，但与 P0-1/P1-1 叠加效果最佳。
- **P2-2 的 Task 3 依赖 P0-1**：只有 P0-1 落地后 QueryProvider 才有 `buster` 配置；若 P0-1 未实施，跳过 P2-2 Task 3，仅做 appVersion + migrate。

---

## 三、每份计划的关键产出

### P0-1 跨会话持久层
- **新增**：`src/providers/queryPersister.ts`（SafeStorage 适配的 persister）
- **重写**：`src/providers/QueryProvider.tsx`（PersistQueryClientProvider 替换 QueryClientProvider）
- **效果**：查询缓存序列化到 localStorage，刷新/路由切换后秒开，后台静默校验

### P0-2 WebSocket 全局化
- **新增**：`src/providers/RealtimeMetricsProvider.tsx`（全局 Context）
- **重写**：`src/hooks/useRealtimeMetrics.ts`（改为读 Context 的薄封装）
- **修改**：`src/App.tsx`（应用根挂载 Provider）
- **效果**：`/ws/dashboard` 全生命周期唯一连接，路由切换零重建

### P1-1 占位策略优化
- **修改**：`src/hooks/useDashboardData.ts`（移除 EMPTY_STATS，改用 keepPreviousData）
- **修改**：`src/pages/Dashboard.tsx`（移除假 trend 值，收紧水印条件）
- **效果**：加载态显示骨架屏而非全零"假数据"，趋势箭头不再出现假值

### P1-2 渐进式渲染
- **修改**：`useDashboardData`/`useAnalyticsData`/`useCostDataQuery`（暴露分项 isLoading）
- **修改**：`Dashboard`/`Analytics`/`CostGovernance` 三个页面（局部骨架）
- **效果**：stats 到达即渲染主结构，未到的子区块用局部占位，不再"等齐再渲染"

### P2-1 性能监控
- **新增**：`src/lib/performance.ts`（Web Vitals 采集）、`src/lib/cacheMetrics.ts`（缓存命中率）、`src/hooks/useWebVitals.ts`
- **可选**：`lighthouserc.cjs` + CI 性能门禁
- **效果**：开发环境 console 输出 LCP/FCP/INP/CLS，缓存命中率可量化，CI 可阻断性能回归

### P2-2 状态版本管理
- **新增**：`src/lib/appVersion.ts`（版本号统一来源 + cache buster）
- **修改**：`src/stores/useViewStore.ts`（补充 migrateViewState 函数）
- **效果**：数据结构变更时旧状态平滑迁移，构建版本变更时查询缓存自动失效

---

## 四、执行方式选择

完成全部 6 份计划后，按 superpowers:writing-plans 技能规范，提供两种执行方式：

### 方式 1：Subagent-Driven（推荐）
- 每个 Task 派发独立 subagent 执行
- 两阶段 review（subagent 自检 + 主会话复核）
- 适合：希望逐步验证、每步可控的团队

### 方式 2：Inline Execution
- 在当前会话内批量执行，检查点 review
- 适合：希望快速推进、信任计划质量的场景

---

## 五、风险与回滚

- **所有改动均向后兼容**：`useRealtimeMetrics` 改为薄封装保持 import 不变；`isLoading` 聚合字段保留；`useViewStore` migrate 对 v1 数据透传。
- **持久化层降级安全**：复用 `safeStorage` 三级降级（localStorage → sessionStorage → 内存），隐私模式不崩溃。
- **回滚方式**：每份计划都以独立 commit 提交，任何一份出问题可单独 `git revert`，不影响其他。
- **测试覆盖**：每份计划都含 TDD 流程（先写失败测试 → 实现 → 验证），确保改动有测试守护。

---

## 六、自检结论（对照诊断报告 5 条根因）

| 诊断根因 | 对应计划 | 覆盖状态 |
|---------|---------|---------|
| 缺少跨会话持久层 | P0-1 | ✅ 完整覆盖 |
| WebSocket 未跨页面保持 | P0-2 | ✅ 完整覆盖 |
| 占位数据与演示数据语义混淆 | P1-1 | ✅ 完整覆盖 |
| 缺少请求去重层 | P0-1（persistQueryClient 内存去重）+ P1-2 | ✅ 间接覆盖 |
| 融合层缺少缓存优先渲染 | P1-2 | ✅ 完整覆盖 |

所有 5 条根因均有对应计划，无遗漏。
