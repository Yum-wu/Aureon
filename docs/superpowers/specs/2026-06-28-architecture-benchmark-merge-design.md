# 架构与基准测试页合并设计

## 背景

- `/architecture` 页面：侧边栏已有入口，受 AdminGate 保护，展示 RAG 流水线 + 优化历程 + 运行时指标
- `/benchmark` 页面：新页面（无侧边栏入口），展示性能基准 Hero 卡片 + 架构图 + TTFT 进度条 + 检索准确率 + 内部指标
- 两者数据源相同（`useBenchmark` hook → `backend/data/benchmark_results.json`），内容高度重叠

## 目标

合并为一个页面，保留 `/architecture` 路由并更新侧边栏标题，删除 `/benchmark` 路由和 `/portfolio` 重定向。

## 数据源

`backend/data/benchmark_results.json` 已有完整的 R19 真实评估数据（23 个指标、12 个 customer_facing），直接使用，不引入硬编码 fallback。

## 页面结构

| # | 区块 | 来源 | 数据 |
|---|------|------|------|
| 1 | Hero 指标卡片 ×4 | Benchmark 页 | `priority 0-3` 的 customer_facing 指标：Recall@3, Faithfulness, Answer Relevancy, Negative Detection |
| 2 | RAG 流水线 | ArchitectureFlow 组件 | 8 步编号卡片 + 各步延迟时间 |
| 3 | TTFT 优化进度条 | Benchmark 页 | TTFT P50/P95 + E2E P50/P99 进度条 |
| 4 | 检索准确率进度条 | Benchmark 页 | Recall@3 + MRR |
| 5 | 优化历程 | OptimizationStory 组件 | Before→After 对比卡（TTFT / Recall / Cost / Cache） |
| 6 | 技术栈详情 | Benchmark 页 | Embedding / Vector DB / Retrieval / Cache 从 `services` 字段读取 |

### 删除内容

- Benchmark 页的内联架构图（SVG 箭头）→ 被 ArchitectureFlow 替代
- Architecture 页的 MetricGrid → 被 Hero 卡片替代
- Benchmark 页的折叠"内部评估指标"→ 用户不可见

## 路由变更

- 保留 `/architecture`，受 AdminGate 保护
- 删除 `/benchmark` 路由
- 删除 `/portfolio → /benchmark` 重定向
- 侧边栏标题从 `app.nav.architecture` → 改用 `app.sidebar:benchmark`（即"架构与性能"）

## 组件变更

- `Benchmark.tsx` → 删除
- `Architecture.tsx` → 重写为合并版本，引入 Benchmark 页的 Hero 卡片、进度条、技术栈区块
- `app.nav.architecture` i18n 键保留，不改侧边栏 ID，只改显示文字

## 不需要 HERO_COLORS 等样式常量

直接用 `Architecture.tsx` 已有的 CSS 变量体系，不引入 Benchmark 页的多彩渐变风格，保持一致的 Design Token 视觉语言。
