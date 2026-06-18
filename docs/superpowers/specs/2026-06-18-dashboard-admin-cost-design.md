# 设计文档：系统仪表盘 / 企业后台 / 成本治理 全面升级

> 日期：2026-06-18
> 状态：已批准，待实施
> 方案：B — 组件化重构 + 统一数据层

## 1. 背景与动机

当前三个子系统均有基础实现，但停留在"能展示数据"阶段：

| 子系统 | 现状 | 核心差距 |
|--------|------|---------|
| 系统仪表盘 | 4 指标卡 + CSS 柱状图 + 最近查询 + 3 个健康状态点 | 缺少时间序列图、告警、RAG Pipeline 分解、实时刷新 |
| 企业后台 | 2 Tab（SSO Provider 列表 + 审计日志列表） | 缺少 RBAC UI、用户管理、Workspace 管理、审计筛选/导出 |
| 成本治理 | 后端 7 个 CRUD 端点，无前端页面 | 缺少成本可视化、Token 趋势、预算告警、burn rate |

额外问题：Dashboard.tsx 用 CSS 变量，Analytics.tsx 硬编码颜色，风格不统一。

## 2. 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 方案 | B — 组件化重构 + 统一数据层 | 平衡改动量和架构质量 |
| 图表库 | Nivo（@nivo/core + @nivo/line + @nivo/bar + @nivo/pie） | 基于 D3、功能强大、动画精美、React 原生 |
| 实时性 | WebSocket 实时推送 | 复用现有 /ws/chat 基础设施，延迟最低 |
| 优先级 | 均衡推进 | 三个子系统同步开发核心功能 |
| 设计系统 | 统一 Design Token（CSS 变量） | 消除 Analytics.tsx 硬编码颜色问题 |

## 3. 统一基础设施层

### 3.1 WebSocket 实时通道

复用现有 `/ws/chat/{client_id}` 基础设施，新增仪表盘专用通道：

```
后端新增:
  /ws/dashboard → WebSocket 端点 (backend/app/api/ws_dashboard.py)

消息协议:
  metrics.tick    → 每 5s 推送核心指标（查询数/延迟/缓存命中率/Token 用量）
  alert.fire     → 告警触发（预算超限/延迟飙升/服务异常）
  cost.update    → 成本变化推送

前端新增:
  src/hooks/useWebSocket.ts          → 通用 WebSocket hook（自动重连 + 心跳 + 消息分发）
  src/hooks/useRealtimeMetrics.ts    → 订阅 metrics.tick，返回实时指标
```

### 3.2 Nivo 图表统一配置

```
src/components/charts/
├── ChartContainer.tsx   → 统一容器（标题 + 时间范围选择 + 全屏切换）
├── LineChart.tsx        → Nivo Line（时间序列：延迟/Token/成本趋势）
├── BarChart.tsx         → Nivo Bar（对比：按模型/按用户/按工作区）
├── PieChart.tsx         → Nivo Pie（分布：查询类型/Token 构成）
└── chartTheme.ts        → 统一主题（Design Token → Nivo 配色映射）
```

### 3.3 管理后台共享组件

```
src/components/admin/
├── AdminLayout.tsx    → 统一管理后台布局（侧边栏 + 面包屑）
├── AdminTable.tsx     → 通用表格（排序/筛选/分页/批量操作）
├── AdminForm.tsx      → 通用表单（验证 + 提交状态）
├── StatusBadge.tsx    → 状态标签（healthy/warning/error/disabled）
└── ConfirmDialog.tsx  → 确认对话框（危险操作二次确认）
```

## 4. 系统仪表盘

### 4.1 指标体系

基于 Google SRE **4 Golden Signals** + **RED Method**：

| 层级 | 指标 | 数据来源 | 展示方式 |
|------|------|---------|---------|
| Golden Signals | 延迟（TTFT/TPOT/E2E）、流量（QPS）、错误率、饱和度 | metrics_collector | 4 个顶部指标卡 |
| RAG Pipeline | 检索延迟、Rerank 延迟、生成延迟、CRAG 命中率 | qa_chain.py | Pipeline 分解瀑布图 |
| 检索质量 | Recall@5、MRR、Citation@1、Faithfulness 趋势 | evaluator.py | 折线图（每日采样） |
| 资源健康 | Redis 连接数、Qdrant 索引大小、内存使用 | /health/ready | 状态卡 + 进度条 |
| 告警 | TTFT > 2s、缓存命中率 < 50%、错误率 > 5% | 自定义阈值 | 告警横幅 + 历史列表 |

### 4.2 页面布局

```
┌─────────────────────────────────────────────────┐
│  系统仪表盘                    [实时] [时间范围]  │
├────────┬────────┬────────┬────────┬─────────────┤
│ 延迟   │ 流量   │ 错误率  │ 饱和度  │  告警数     │
│ 590ms  │ 12/min │ 0.3%   │ 45%    │  ⚠️ 2      │
├────────┴────────┴────────┴────────┴─────────────┤
│  [延迟趋势折线图]        │  [查询量柱状图]        │
│  TTFT / TPOT / E2E     │  按小时/按天           │
├─────────────────────────┼───────────────────────┤
│  [RAG Pipeline 分解]    │  [检索质量趋势]        │
│  检索→Rerank→CRAG→生成  │  Recall/MRR/Faithfulness│
├─────────────────────────┴───────────────────────┤
│  [系统健康]  Redis ✅  Qdrant ✅  LLM API ✅    │
│  [最近告警]  ⚠️ TTFT P95 超阈值  2min ago       │
└─────────────────────────────────────────────────┘
```

### 4.3 后端新增

- `backend/app/api/ws_dashboard.py` — WebSocket 端点，5s 间隔推送 metrics.tick
- `backend/app/observability/metrics_collector.py` — 指标聚合器，从 Redis/Qdrant/LLM 收集实时指标

## 5. 企业后台

### 5.1 模块划分

| Tab | 功能 | 后端端点 | 状态 |
|-----|------|---------|------|
| 概览 | 系统状态摘要、活跃用户数、今日查询数 | 聚合现有 API | 新增 |
| 用户管理 | 用户列表、角色分配、邀请/禁用/删除 | `/api/security/users` | 新增 |
| 角色权限 | RBAC 角色定义、权限矩阵可视化 | `/api/security/roles` | 新增 |
| 工作区 | Workspace CRUD、成员管理、配额设置 | `/api/security/workspaces` | 新增 |
| 审计日志 | 可筛选/可导出/可钻取的操作日志 | `/api/audit/*` | 增强 |
| Feature Flags | Flag 列表、开关、灰度规则 | `/api/feature-flags/*` | 现有 |
| SSO | Identity Provider 管理 | `/api/security/sso/*` | 现有 |

### 5.2 审计日志增强

- **筛选器**：时间范围、用户、操作类型、工作区、严重级别
- **导出**：CSV / JSON 导出
- **详情钻取**：点击条目展开完整请求/响应上下文
- **实时推送**：新审计事件通过 WebSocket 推送到管理员

### 5.3 RBAC 权限矩阵可视化

```
         │ 查询 │ 上传 │ 管理 │ 审计 │ 配置
─────────┼──────┼──────┼──────┼──────┼──────
viewer   │  ✅  │  ❌  │  ❌  │  ✅  │  ❌
editor   │  ✅  │  ✅  │  ❌  │  ✅  │  ❌
admin    │  ✅  │  ✅  │  ✅  │  ✅  │  ✅
```

### 5.4 页面布局

```
┌──────────┬──────────────────────────────────┐
│ 侧边栏   │  用户管理                        │
│          │  ┌────────────────────────────┐  │
│ 概览     │  │ 搜索 [___] [+ 邀请用户]    │  │
│ 用户     │  ├────────────────────────────┤  │
│ 角色     │  │ 用户  │ 角色   │ 状态 │ 操作│  │
│ 工作区   │  │ alice │ admin  │ ✅  │ ... │  │
│ 审计     │  │ bob   │ editor │ ✅  │ ... │  │
│ Flags    │  │ carol │ viewer │ ⏸️  │ ... │  │
│ SSO      │  └────────────────────────────┘  │
└──────────┴──────────────────────────────────┘
```

## 6. 成本治理

### 6.1 指标体系

基于 **FinOps 框架** + **OpenAI Usage Dashboard** 模式：

| 指标 | 说明 | 展示方式 |
|------|------|---------|
| 总成本 | 当期累计花费 | 大数字卡 + 环比变化 |
| Burn Rate | 日均消耗速度 | 折线图 + 预测线 |
| Token 用量 | Input/Output Token 分解 | 堆叠面积图 |
| 按模型分解 | qwen3.5-flash vs DeepSeek vs Claude | 饼图 + 表格 |
| 按工作区分解 | 各 Workspace 成本占比 | 柱状图 |
| 预算状态 | 已用/剩余/预测超支 | 进度条 + 告警 |
| 成本趋势 | 7d/30d/90d 趋势 | 折线图 |
| Top 消费者 | 用户/查询排行 | 表格 |

### 6.2 预算告警

```
预算规则:
  - 警告阈值: 80% 已用 → 黄色告警
  - 临界阈值: 95% 已用 → 红色告警 + 审计日志
  - 硬限制: 100% 已用 → 阻止新查询（可选开关）

告警通道:
  - WebSocket 实时推送（alert.fire 消息）
  - 审计日志记录
  - (未来) 邮件/Webhook 通知
```

### 6.3 页面布局

```
┌─────────────────────────────────────────────────┐
│  成本治理                    [时间范围] [导出]    │
├────────┬────────┬────────┬──────────────────────┤
│ 总成本  │ Burn   │ Token  │ 预算状态             │
│ $12.50 │ Rate   │ 1.2M   │ ██████░░ 78%         │
│ ↑15%   │ $0.42/d│ ↑8%   │ ⚠️ 接近阈值          │
├────────┴────────┴────────┴──────────────────────┤
│  [成本趋势折线图]          │  [Token 用量面积图]  │
│  7d/30d/90d + 预测线      │  Input vs Output     │
├───────────────────────────┼─────────────────────┤
│  [按模型分解饼图]          │  [按工作区柱状图]    │
│  qwen/DeepSeek/Claude     │  Workspace A/B/C     │
├───────────────────────────┴─────────────────────┤
│  [Top 消费者表格]                                │
│  用户 │ Token │ 成本 │ 查询数 │ 趋势            │
└─────────────────────────────────────────────────┘
```

### 6.4 后端增强

```
backend/app/cost/
├── router.py          → 现有，增强端点（聚合/趋势/导出）
├── models.py          → 新增 CostAggregation/BudgetAlert/TokenUsage 模型
├── service.py         → 新增成本聚合/预测/告警逻辑
└── budget_engine.py   → 新增预算引擎（阈值检测 + 告警触发）
```

## 7. 文件结构总览

### 前端新增/修改

```
src/
├── hooks/
│   ├── useWebSocket.ts              → 通用 WebSocket hook
│   ├── useRealtimeMetrics.ts        → 实时指标订阅
│   └── useCostData.ts               → 成本数据 hook
├── components/
│   ├── charts/                      → Nivo 图表组件（5 个）
│   │   ├── ChartContainer.tsx
│   │   ├── LineChart.tsx
│   │   ├── BarChart.tsx
│   │   ├── PieChart.tsx
│   │   └── chartTheme.ts
│   └── admin/                       → 管理后台共享组件（5 个）
│       ├── AdminLayout.tsx
│       ├── AdminTable.tsx
│       ├── AdminForm.tsx
│       ├── StatusBadge.tsx
│       └── ConfirmDialog.tsx
├── pages/
│   ├── Dashboard.tsx                → 重写（6 个区域）
│   ├── Admin.tsx                    → 重写（7 个 Tab）
│   └── CostGovernance.tsx           → 新增页面
└── services/
    └── ws.ts                        → WebSocket 客户端
```

### 后端新增/修改

```
backend/app/
├── api/
│   └── ws_dashboard.py              → 新增 WebSocket 端点
├── cost/
│   ├── router.py                    → 增强
│   ├── models.py                    → 新增
│   ├── service.py                   → 新增
│   └── budget_engine.py             → 新增
├── observability/
│   └── metrics_collector.py         → 新增指标聚合器
└── security/
    ├── users_router.py              → 新增用户管理端点
    └── roles_router.py              → 新增角色管理端点
```

## 8. 依赖

### 前端新增 npm 包

```json
{
  "@nivo/core": "^0.87",
  "@nivo/line": "^0.87",
  "@nivo/bar": "^0.87",
  "@nivo/pie": "^0.87",
  "@nivo/tooltip": "^0.87"
}
```

### 后端无新增依赖

使用现有 FastAPI WebSocket + Redis + SQLite 基础设施。

## 9. 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| Nivo 包体积大（~200KB+） | 使用 tree-shaking + 按需加载（React.lazy） |
| WebSocket 连接数限制 | 复用现有连接管理，限制仪表盘连接 1 个/用户 |
| 成本数据聚合性能 | 使用 Redis 缓存聚合结果，5s TTL |
| RBAC 端点安全 | 复用现有 `require_role(min_role="admin")` 依赖 |
| 审计日志数据量 | 默认分页 20 条/页，筛选器减少查询范围 |
