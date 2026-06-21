# 设计文档：Dashboard & Admin 页面优化

> 日期：2026-06-21
> 状态：待实施
> 方案：B — 组件化重构 + 统一数据层

## 1. 背景与动机

当前 Dashboard 和 Admin 页面存在以下问题：

| 页面 | 现状 | 核心差距 |
|------|------|---------|
| Dashboard | Golden Signals 框架已实现，但延迟趋势、Pipeline 分解等区域显示"暂无数据" | 缺少数据派生策略和降级机制 |
| Admin | 7 个 Tab 全部使用 useEffect + useState，无缓存 | 每次切换 Tab 重新请求，用户体验差 |
| 审计日志 | i18n 已配置，但日期选择器中英文混合 | 需要统一 DatePicker 组件 |

## 2. 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 缓存策略 | Tab 级别 TanStack Query 缓存 | 平衡内存占用和用户体验 |
| staleTime | 5 分钟 | 管理数据变更频率适中 |
| gcTime | 10 分钟 | 保留足够长的缓存供 Tab 切换复用 |
| 路由预加载 | Hover + Focus 预加载 | 零成本提升页面切换流畅度 |
| i18n 修复 | 统一 DatePicker 组件 + lang 属性 | 解决原生控件语言不一致问题 |

## 3. Admin 数据层重构

### 3.1 新增 Hooks 文件结构

```
src/hooks/admin/
├── useAdminOverview.ts    # 概览数据
├── useAdminUsers.ts       # 用户管理
├── useAdminWorkspaces.ts  # 工作区
├── useAdminAudit.ts       # 审计日志
├── useAdminFlags.ts       # Feature Flags
└── useAdminSSO.ts         # SSO 配置
```

### 3.2 Hook 设计规范

**统一缓存参数：**
```typescript
const ADMIN_CACHE_CONFIG = {
  staleTime: 5 * 60 * 1000,   // 5 分钟
  gcTime: 10 * 60 * 1000,     // 10 分钟
  placeholderData: keepPreviousData,
  retry: 2,
};
```

**示例 Hook（useAdminAudit）：**
```typescript
export function useAdminAudit(filters: AuditFilters) {
  return useQuery({
    queryKey: ['admin', 'audit', filters],
    queryFn: async ({ signal }) => {
      const params = new URLSearchParams();
      if (filters.user) params.set('user', filters.user);
      if (filters.actionType) params.set('action', filters.actionType);
      if (filters.severity) params.set('severity', filters.severity);
      if (filters.dateFrom) params.set('from', filters.dateFrom);
      if (filters.dateTo) params.set('to', filters.dateTo);

      const res = await authFetch(`/api/audit/logs?${params}`, { signal });
      if (!res.ok) throw new Error(`Audit fetch failed: ${res.status}`);
      return res.json();
    },
    ...ADMIN_CACHE_CONFIG,
  });
}
```

### 3.3 Admin.tsx 改造

**改造前：**
```tsx
function AuditTab() {
  const [auditLogs, setAuditLogs] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    const controller = new AbortController();
    authFetch(`/api/audit/logs?${params}`, { signal: controller.signal })
      .then(...)
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [filters]);
}
```

**改造后：**
```tsx
function AuditTab() {
  const { t } = useTranslation();
  const [filters, setFilters] = useState<AuditFilters>({...});
  const { data, isLoading, error } = useAdminAudit(filters);
  
  const auditLogs = data?.logs ?? [];
  // ...
}
```

## 4. Dashboard 数据优化

### 4.1 现有 API 端点利用

| 数据类型 | 端点 | 状态 | 策略 |
|---------|------|------|------|
| 统计数据 | `/api/rag/stats` | ? 有数据 | 保持 |
| 查询量 | `/api/rag/query-volume` | ? 有数据 | 保持 |
| 健康状态 | `/api/rag/health` | ? 有数据 | 保持 |
| 延迟趋势 | 无专用端点 | ? 空白 | **前端累积** |
| Pipeline 分解 | WebSocket 实时 | ?? 依赖连接 | **降级策略** |
| 检索质量 | 无 | ? 空白 | **暂不实现** |

### 4.2 延迟趋势数据派生方案

**前端累积 + localStorage 持久化：**

```typescript
// src/hooks/useLatencyHistory.ts
export function useLatencyHistory() {
  const { metrics } = useRealtimeMetrics();
  
  const [history, setHistory] = useState<LatencyPoint[]>(() => {
    const saved = localStorage.getItem('aureon:latency:history');
    return saved ? JSON.parse(saved) : [];
  });
  
  useEffect(() => {
    if (metrics.ttft_p50 > 0) {
      setHistory(prev => {
        const next = [...prev, { ts: Date.now(), ttft: metrics.ttft_p50 }];
        return next.slice(-100);  // 保留最近 100 个点
      });
    }
  }, [metrics.ttft_p50]);
  
  useEffect(() => {
    localStorage.setItem('aureon:latency:history', JSON.stringify(history));
  }, [history]);
  
  return history;
}
```

### 4.3 Pipeline 分解降级策略

**优先级顺序：**
1. WebSocket 实时数据（`rtMetrics.pipeline`）
2. 最近一次缓存数据（localStorage）
3. 显示"等待数据"状态

### 4.4 Dashboard 最终布局

```
┌─────────────────────────────────────────────────┐
│  系统仪表盘                    [实时] [时间范围]  │
├────────┬────────┬────────┬────────┬─────────────┤
│ 延迟   │ 流量   │ 错误率  │ 饱和度  │  告警数     │
│ 590ms  │ 12/min │ 0.3%   │ 45%    │  ?? 2      │
├────────┴────────┴────────┴────────┴─────────────┤
│  [延迟趋势折线图]        │  [查询量柱状图]        │
│  TTFT / TPOT / E2E     │  按小时/按天           │
├─────────────────────────┼───────────────────────┤
│  [RAG Pipeline 分解]    │  [系统健康]            │
│  检索→Rerank→CRAG→生成  │  Redis/Qdrant/LLM     │
├─────────────────────────┴───────────────────────┤
│  [最近告警]                                      │
└─────────────────────────────────────────────────┘
```

**移除**：检索质量趋势（无数据源，避免空白区域）

## 5. i18n 修复

### 5.1 统一 DatePicker 组件

```typescript
// src/components/ui/DatePicker.tsx
interface DatePickerProps {
  value: string;
  onChange: (value: string) => void;
  placeholderKey: string;
  ariaLabelKey: string;
}

export function DatePicker({ value, onChange, placeholderKey, ariaLabelKey }: DatePickerProps) {
  const { t, i18n } = useTranslation();
  
  return (
    <div className="relative">
      <input
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label={t(ariaLabelKey)}
        lang={i18n.language}
        className="px-3 py-1.5 text-xs rounded-lg border border-[var(--border)] bg-[var(--bg-tertiary)] text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] [color-scheme:dark]"
      />
      {!value && (
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[10px] text-[var(--text-tertiary)] pointer-events-none">
          {t(placeholderKey)}
        </span>
      )}
    </div>
  );
}
```

### 5.2 CSS 语言适配

```css
/* src/index.css */
[lang="en"] input[type="date"]::-webkit-calendar-picker-indicator {
  filter: invert(1);  /* 深色模式适配 */
}
```

## 6. 路由预加载

### 6.1 Hover 预加载实现

```typescript
// src/App.tsx
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Admin = lazy(() => import('./pages/Admin'));

const preloadDashboard = () => import('./pages/Dashboard');
const preloadAdmin = () => import('./pages/Admin');

function NavLink({ to, preloadFn, children }: NavLinkProps) {
  return (
    <Link
      to={to}
      onMouseEnter={preloadFn}
      onFocus={preloadFn}
    >
      {children}
    </Link>
  );
}
```

### 6.2 QueryClient 全局配置

```typescript
// src/providers/QueryProvider.tsx
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 2 * 60 * 1000,
      gcTime: 5 * 60 * 1000,
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
});
```

## 7. 文件结构总览

### 新增文件

```
src/
├── hooks/admin/
│   ├── useAdminOverview.ts
│   ├── useAdminUsers.ts
│   ├── useAdminWorkspaces.ts
│   ├── useAdminAudit.ts
│   ├── useAdminFlags.ts
│   └── useAdminSSO.ts
├── hooks/
│   └── useLatencyHistory.ts
└── components/ui/
    └── DatePicker.tsx
```

### 修改文件

```
src/
├── pages/
│   ├── Admin.tsx          # 重构 Tab 组件使用 hooks
│   └── Dashboard.tsx      # 集成延迟趋势和降级策略
├── App.tsx                # 添加路由预加载
└── providers/
    └── QueryProvider.tsx   # 优化全局配置
```

## 8. 验收标准

### Admin 页面
- [ ] 切换 Tab 时不再出现 loading 闪烁
- [ ] 5 分钟内切换 Tab 使用缓存数据
- [ ] 审计日志日期选择器中英文一致

### Dashboard 页面
- [ ] 延迟趋势图表正常显示（有 WebSocket 数据时）
- [ ] Pipeline 分解在 WebSocket 断开时显示缓存数据
- [ ] 无数据区域显示友好的"等待数据"状态

### 路由预加载
- [ ] Hover 导航链接时预加载对应页面
- [ ] 页面切换延迟 < 100ms（有预加载时）

## 9. 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| localStorage 容量限制 | 限制延迟历史为 100 个点 |
| WebSocket 断开时数据丢失 | 实现 localStorage 缓存降级 |
| 缓存数据过期 | staleTime 5 分钟后自动刷新 |
| 预加载增加带宽 | 仅在 hover 时触发，非主动加载 |
