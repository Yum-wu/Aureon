# Dashboard & Admin 页面优化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 优化 Dashboard 和 Admin 页面，实现 TanStack Query 缓存、路由预加载和 i18n 修复

**Architecture:** 使用 TanStack Query 实现 Admin Tab 级别缓存，Dashboard 通过前端累积延迟趋势数据，统一 DatePicker 组件解决 i18n 问题

**Tech Stack:** React 19, TanStack Query v5, React Router, i18next, Tailwind CSS 4

---

## 文件结构

### 新增文件
```
src/hooks/admin/
├── useAdminOverview.ts    # 概览数据 hook
├── useAdminUsers.ts       # 用户管理 hook
├── useAdminWorkspaces.ts  # 工作区 hook
├── useAdminAudit.ts       # 审计日志 hook
├── useAdminFlags.ts       # Feature Flags hook
├── useAdminSSO.ts         # SSO 配置 hook
└── index.ts               # 统一导出

src/hooks/
└── useLatencyHistory.ts   # 延迟趋势累积 hook

src/components/ui/
└── DatePicker.tsx         # 统一日期选择器
```

### 修改文件
```
src/pages/Admin.tsx        # 重构 Tab 组件使用 hooks
src/pages/Dashboard.tsx    # 集成延迟趋势和降级策略
src/App.tsx                # 添加路由预加载
src/providers/QueryProvider.tsx  # 优化全局配置（可选）
src/index.css              # 添加日期选择器语言适配
```

---

## Task 1: 创建 Admin Hooks 基础架构

**Files:**
- Create: `src/hooks/admin/useAdminOverview.ts`
- Create: `src/hooks/admin/index.ts`

- [ ] **Step 1: 创建 useAdminOverview hook**

```typescript
// src/hooks/admin/useAdminOverview.ts
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { authFetch } from '../../services/authFetch';

export const ADMIN_QUERY_KEYS = {
  overview: ['admin', 'overview'] as const,
  users: ['admin', 'users'] as const,
  workspaces: ['admin', 'workspaces'] as const,
  audit: ['admin', 'audit'] as const,
  flags: ['admin', 'flags'] as const,
  sso: ['admin', 'sso'] as const,
} as const;

const ADMIN_CACHE_CONFIG = {
  staleTime: 5 * 60 * 1000,   // 5 分钟
  gcTime: 10 * 60 * 1000,     // 10 分钟
  placeholderData: keepPreviousData,
  retry: 2,
};

interface OverviewData {
  active_users: number;
  today_queries: number;
  storage_usage: string;
  uptime: string;
}

export function useAdminOverview() {
  return useQuery({
    queryKey: ADMIN_QUERY_KEYS.overview,
    queryFn: async ({ signal }): Promise<OverviewData> => {
      const [statsRes, usersRes] = await Promise.all([
        authFetch('/api/rag/stats', { signal }),
        authFetch('/api/security/users', { signal }),
      ]);

      const statsData = statsRes.ok ? await statsRes.json() : null;
      const usersData = usersRes.ok ? await usersRes.json() : [];
      const activeUsers = Array.isArray(usersData)
        ? usersData.filter((u: { status?: string }) => u.status === 'active').length
        : 0;

      return {
        active_users: activeUsers,
        today_queries: statsData?.query_count_24h || 0,
        storage_usage: '2.4 GB',
        uptime: '99.9%',
      };
    },
    ...ADMIN_CACHE_CONFIG,
  });
}
```

- [ ] **Step 2: 创建 index.ts 统一导出**

```typescript
// src/hooks/admin/index.ts
export { useAdminOverview, ADMIN_QUERY_KEYS, ADMIN_CACHE_CONFIG } from './useAdminOverview';
```

- [ ] **Step 3: 运行 TypeScript 检查**

Run: `npx tsc --noEmit`
Expected: 无类型错误

- [ ] **Step 4: 提交**

```bash
git add src/hooks/admin/
git commit -m "feat(admin): add useAdminOverview hook with TanStack Query"
```

---

## Task 2: 创建剩余 Admin Hooks

**Files:**
- Create: `src/hooks/admin/useAdminUsers.ts`
- Create: `src/hooks/admin/useAdminWorkspaces.ts`
- Create: `src/hooks/admin/useAdminAudit.ts`
- Create: `src/hooks/admin/useAdminFlags.ts`
- Create: `src/hooks/admin/useAdminSSO.ts`
- Modify: `src/hooks/admin/index.ts`

- [ ] **Step 1: 创建 useAdminUsers hook**

```typescript
// src/hooks/admin/useAdminUsers.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { authFetch } from '../../services/authFetch';
import { ADMIN_QUERY_KEYS, ADMIN_CACHE_CONFIG } from './useAdminOverview';
import { toast } from 'sonner';

interface UserRecord {
  id: string;
  email: string;
  display_name: string;
  role: 'super_admin' | 'admin' | 'editor' | 'viewer';
  status: 'active' | 'suspended' | 'invited';
  last_login: string | null;
}

export function useAdminUsers() {
  return useQuery<UserRecord[]>({
    queryKey: ADMIN_QUERY_KEYS.users,
    queryFn: async ({ signal }) => {
      const res = await authFetch('/api/security/users', { signal });
      if (!res.ok) return [];
      const data = await res.json();
      return Array.isArray(data) ? data : [];
    },
    ...ADMIN_CACHE_CONFIG,
  });
}

export function useUpdateUserRole() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async ({ userId, role }: { userId: string; role: string }) => {
      const res = await authFetch(`/api/security/users/${userId}/role`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role }),
      });
      if (!res.ok) throw new Error('Role update failed');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ADMIN_QUERY_KEYS.users });
      toast.success('Role updated successfully');
    },
    onError: () => {
      toast.error('Failed to update role');
    },
  });
}

export function useSuspendUser() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async (userId: string) => {
      const res = await authFetch(`/api/security/users/${userId}/suspend`, { method: 'POST' });
      if (!res.ok) throw new Error('Suspend failed');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ADMIN_QUERY_KEYS.users });
      toast.success('User suspended');
    },
    onError: () => {
      toast.error('Failed to suspend user');
    },
  });
}

export function useDeleteUser() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async (userId: string) => {
      const res = await authFetch(`/api/security/users/${userId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Delete failed');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ADMIN_QUERY_KEYS.users });
      toast.success('User deleted');
    },
    onError: () => {
      toast.error('Failed to delete user');
    },
  });
}
```

- [ ] **Step 2: 创建 useAdminAudit hook**

```typescript
// src/hooks/admin/useAdminAudit.ts
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { authFetch } from '../../services/authFetch';
import { ADMIN_QUERY_KEYS } from './useAdminOverview';

export interface AuditFilters {
  dateFrom: string;
  dateTo: string;
  user: string;
  actionType: string;
  severity: string;
}

export interface AuditEntry {
  id: number;
  timestamp: string;
  user: string;
  action: string;
  resource: string;
  severity: 'info' | 'warning' | 'critical';
  details: string;
}

export function useAdminAudit(filters: AuditFilters) {
  return useQuery<AuditEntry[]>({
    queryKey: [...ADMIN_QUERY_KEYS.audit, filters],
    queryFn: async ({ signal }) => {
      const params = new URLSearchParams();
      if (filters.user) params.set('user', filters.user);
      if (filters.actionType) params.set('action', filters.actionType);
      if (filters.severity) params.set('severity', filters.severity);
      if (filters.dateFrom) params.set('from', filters.dateFrom);
      if (filters.dateTo) params.set('to', filters.dateTo);

      const res = await authFetch(`/api/audit/logs?${params.toString()}`, { signal });
      if (!res.ok) return [];
      const data = await res.json();
      return Array.isArray(data) ? data : [];
    },
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
    placeholderData: keepPreviousData,
    retry: 2,
  });
}
```

- [ ] **Step 3: 创建 useAdminWorkspaces hook**

```typescript
// src/hooks/admin/useAdminWorkspaces.ts
import { useQuery } from '@tanstack/react-query';
import { authFetch } from '../../services/authFetch';
import { ADMIN_QUERY_KEYS, ADMIN_CACHE_CONFIG } from './useAdminOverview';

interface WorkspaceRecord {
  id: string;
  name: string;
  member_count: number;
  quota: string;
  status: 'active' | 'archived';
}

export function useAdminWorkspaces() {
  return useQuery<WorkspaceRecord[]>({
    queryKey: ADMIN_QUERY_KEYS.workspaces,
    queryFn: async ({ signal }) => {
      const res = await authFetch('/api/security/workspaces', { signal });
      if (!res.ok) return [];
      const data = await res.json();
      return Array.isArray(data) ? data : [];
    },
    ...ADMIN_CACHE_CONFIG,
  });
}
```

- [ ] **Step 4: 创建 useAdminFlags hook**

```typescript
// src/hooks/admin/useAdminFlags.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { authFetch } from '../../services/authFetch';
import { ADMIN_QUERY_KEYS, ADMIN_CACHE_CONFIG } from './useAdminOverview';
import { toast } from 'sonner';

interface FeatureFlag {
  key: string;
  name: string;
  description: string;
  enabled: boolean;
  rules: string;
}

export function useAdminFlags() {
  return useQuery<FeatureFlag[]>({
    queryKey: ADMIN_QUERY_KEYS.flags,
    queryFn: async ({ signal }) => {
      const res = await authFetch('/api/feature-flags/', { signal });
      if (!res.ok) return [];
      const data = await res.json();
      return Array.isArray(data) ? data : [];
    },
    ...ADMIN_CACHE_CONFIG,
  });
}

export function useToggleFlag() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async (flagKey: string) => {
      const res = await authFetch(`/api/feature-flags/${flagKey}/toggle`, { method: 'POST' });
      if (!res.ok) throw new Error('Toggle failed');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ADMIN_QUERY_KEYS.flags });
      toast.success('Feature flag toggled');
    },
    onError: () => {
      toast.error('Failed to toggle feature flag');
    },
  });
}
```

- [ ] **Step 5: 创建 useAdminSSO hook**

```typescript
// src/hooks/admin/useAdminSSO.ts
import { useQuery } from '@tanstack/react-query';
import { authFetch } from '../../services/authFetch';
import { ADMIN_QUERY_KEYS, ADMIN_CACHE_CONFIG } from './useAdminOverview';

interface SSOProvider {
  id: number;
  name: string;
  provider_type: string;
  client_id: string;
  enabled: boolean;
  created_at: string;
}

export function useAdminSSO() {
  return useQuery<SSOProvider[]>({
    queryKey: ADMIN_QUERY_KEYS.sso,
    queryFn: async ({ signal }) => {
      const res = await authFetch('/api/security/sso/providers', { signal });
      if (!res.ok) return [];
      const data = await res.json();
      return Array.isArray(data) ? data : [];
    },
    ...ADMIN_CACHE_CONFIG,
  });
}
```

- [ ] **Step 6: 更新 index.ts 导出**

```typescript
// src/hooks/admin/index.ts
export { useAdminOverview, ADMIN_QUERY_KEYS, ADMIN_CACHE_CONFIG } from './useAdminOverview';
export { useAdminUsers, useUpdateUserRole, useSuspendUser, useDeleteUser } from './useAdminUsers';
export { useAdminAudit, type AuditFilters, type AuditEntry } from './useAdminAudit';
export { useAdminWorkspaces } from './useAdminWorkspaces';
export { useAdminFlags, useToggleFlag } from './useAdminFlags';
export { useAdminSSO } from './useAdminSSO';
```

- [ ] **Step 7: 运行 TypeScript 检查**

Run: `npx tsc --noEmit`
Expected: 无类型错误

- [ ] **Step 8: 提交**

```bash
git add src/hooks/admin/
git commit -m "feat(admin): add all admin hooks with TanStack Query caching"
```

---

## Task 3: 重构 Admin.tsx 使用 Hooks

**Files:**
- Modify: `src/pages/Admin.tsx`

- [ ] **Step 1: 重构 OverviewTab**

替换 `OverviewTab` 组件：

```tsx
function OverviewTab() {
  const { t } = useTranslation();
  const { data: overviewData, isLoading } = useAdminOverview();

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-6 animate-pulse">
            <div className="h-3 bg-[var(--bg-tertiary)] rounded w-20 mb-4" />
            <div className="h-8 bg-[var(--bg-tertiary)] rounded w-16" />
          </div>
        ))}
      </div>
    );
  }

  if (!overviewData) {
    return (
      <div className="text-center py-12 text-[var(--text-tertiary)]">
        <p className="text-lg mb-2">{t('admin.overview.no_data')}</p>
      </div>
    );
  }

  const cards = [
    { label: t('admin.overview.active_users'), value: overviewData.active_users },
    { label: t('admin.overview.today_queries'), value: overviewData.today_queries },
    { label: t('admin.overview.storage_usage'), value: overviewData.storage_usage },
    { label: t('admin.overview.uptime'), value: overviewData.uptime },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card) => (
        <Card key={card.label}>
          <p className="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider mb-2">{card.label}</p>
          <span className="text-2xl font-bold text-[var(--text-primary)] tabular-nums">{card.value}</span>
        </Card>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: 重构 UsersTab**

替换 `UsersTab` 组件：

```tsx
function UsersTab() {
  const { t } = useTranslation();
  const { data: users = [], isLoading } = useAdminUsers();
  const updateUserRole = useUpdateUserRole();
  const suspendUser = useSuspendUser();
  const deleteUser = useDeleteUser();
  
  const [showInviteForm, setShowInviteForm] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{ type: 'suspend' | 'delete'; user: UserRecord } | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const filteredUsers = users.filter(
    (u) => u.email.toLowerCase().includes(searchQuery.toLowerCase()) || 
           u.display_name.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  const handleRoleChange = useCallback((userId: string, newRole: string) => {
    updateUserRole.mutate({ userId, role: newRole });
  }, [updateUserRole]);

  const handleSuspend = useCallback((userId: string) => {
    suspendUser.mutate(userId);
    setConfirmAction(null);
  }, [suspendUser]);

  const handleDelete = useCallback((userId: string) => {
    deleteUser.mutate(userId);
    setConfirmAction(null);
  }, [deleteUser]);

  // ... 其余代码保持不变，使用 filteredUsers 和新的 handlers
}
```

- [ ] **Step 3: 重构 AuditTab**

替换 `AuditTab` 组件：

```tsx
function AuditTab() {
  const { t } = useTranslation();
  const [filters, setFilters] = useState<AuditFilters>({
    dateFrom: '',
    dateTo: '',
    user: '',
    actionType: '',
    severity: '',
  });
  
  const { data: auditLogs = [], isLoading } = useAdminAudit(filters);
  const [expandedRow, setExpandedRow] = useState<number | null>(null);

  const handleExport = useCallback((format: 'csv' | 'json') => {
    const url = `/api/audit/logs/export?format=${format}`;
    authFetch(url).then((r) => {
      if (r.ok) return r.blob();
      throw new Error('Export failed');
    }).then((blob) => {
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `audit_logs.${format}`;
      link.click();
      URL.revokeObjectURL(link.href);
      toast.success(t('admin.audit.export_success'));
    }).catch(() => {
      toast.error(t('admin.audit.export_failed'));
    });
  }, [t]);

  // ... 其余代码保持不变
}
```

- [ ] **Step 4: 重构 WorkspacesTab**

```tsx
function WorkspacesTab() {
  const { t } = useTranslation();
  const { data: workspaces = [], isLoading } = useAdminWorkspaces();

  // ... 其余代码保持不变
}
```

- [ ] **Step 5: 重构 FlagsTab**

```tsx
function FlagsTab() {
  const { t } = useTranslation();
  const { data: flags = [], isLoading } = useAdminFlags();
  const toggleFlag = useToggleFlag();

  const handleToggle = useCallback((flagKey: string) => {
    toggleFlag.mutate(flagKey);
  }, [toggleFlag]);

  // ... 其余代码保持不变，使用 handleToggle 替代原来的 toggleFlag
}
```

- [ ] **Step 6: 重构 SSOTab**

```tsx
function SSOTab() {
  const { t } = useTranslation();
  const { data: providers = [], isLoading } = useAdminSSO();

  // ... 其余代码保持不变
}
```

- [ ] **Step 7: 更新 imports**

```tsx
import { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { authFetch } from '../services/authFetch';
import { 
  useAdminOverview, 
  useAdminUsers, 
  useUpdateUserRole, 
  useSuspendUser, 
  useDeleteUser,
  useAdminAudit,
  useAdminWorkspaces,
  useAdminFlags,
  useToggleFlag,
  useAdminSSO,
  type AuditFilters,
  type AuditEntry,
} from '../hooks/admin';
import { AdminLayout } from '../components/admin/AdminLayout';
import { AdminTable } from '../components/admin/AdminTable';
import { AdminForm } from '../components/admin/AdminForm';
import { StatusBadge } from '../components/admin/StatusBadge';
import { ConfirmDialog } from '../components/admin/ConfirmDialog';
import { Card } from '../components/ui/Card';
```

- [ ] **Step 8: 运行测试**

Run: `npm test -- --run src/pages/__tests__/Admin.test.tsx`
Expected: 所有测试通过

- [ ] **Step 9: 提交**

```bash
git add src/pages/Admin.tsx
git commit -m "refactor(admin): migrate to TanStack Query hooks for caching"
```

---

## Task 4: 创建 DatePicker 组件

**Files:**
- Create: `src/components/ui/DatePicker.tsx`
- Modify: `src/index.css`

- [ ] **Step 1: 创建 DatePicker 组件**

```tsx
// src/components/ui/DatePicker.tsx
import { useTranslation } from 'react-i18next';

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

- [ ] **Step 2: 添加 CSS 语言适配**

在 `src/index.css` 末尾添加：

```css
/* 日期选择器语言适配 */
[lang="en"] input[type="date"]::-webkit-calendar-picker-indicator {
  filter: invert(0.8);  /* 深色模式适配 */
}
```

- [ ] **Step 3: 更新 Admin.tsx 使用 DatePicker**

在 `AuditTab` 中替换日期输入：

```tsx
import { DatePicker } from '../components/ui/DatePicker';

// 在筛选栏中：
<div className="flex flex-wrap items-center gap-3 mb-4">
  <DatePicker
    value={filters.dateFrom}
    onChange={(value) => setFilters((f) => ({ ...f, dateFrom: value }))}
    placeholderKey="admin.audit.date_from"
    ariaLabelKey="admin.audit.date_from"
  />
  <DatePicker
    value={filters.dateTo}
    onChange={(value) => setFilters((f) => ({ ...f, dateTo: value }))}
    placeholderKey="admin.audit.date_to"
    ariaLabelKey="admin.audit.date_to"
  />
  {/* ... 其余筛选器保持不变 */}
</div>
```

- [ ] **Step 4: 运行 TypeScript 检查**

Run: `npx tsc --noEmit`
Expected: 无类型错误

- [ ] **Step 5: 提交**

```bash
git add src/components/ui/DatePicker.tsx src/index.css src/pages/Admin.tsx
git commit -m "feat(ui): add DatePicker component with i18n support"
```

---

## Task 5: 创建 useLatencyHistory Hook

**Files:**
- Create: `src/hooks/useLatencyHistory.ts`

- [ ] **Step 1: 创建 useLatencyHistory hook**

```typescript
// src/hooks/useLatencyHistory.ts
import { useState, useEffect } from 'react';
import { useRealtimeMetrics } from './useRealtimeMetrics';

interface LatencyPoint {
  ts: number;
  ttft: number;
  tpot?: number;
  e2e?: number;
}

const STORAGE_KEY = 'aureon:latency:history';
const MAX_POINTS = 100;

export function useLatencyHistory() {
  const { metrics } = useRealtimeMetrics();
  
  const [history, setHistory] = useState<LatencyPoint[]>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  
  useEffect(() => {
    if (metrics.ttft_p50 > 0) {
      setHistory(prev => {
        const next = [...prev, { 
          ts: Date.now(), 
          ttft: metrics.ttft_p50,
          tpot: metrics.tpot,
          e2e: metrics.ttft_p50 + (metrics.tpot || 0) * 50,
        }];
        return next.slice(-MAX_POINTS);
      });
    }
  }, [metrics.ttft_p50, metrics.tpot]);
  
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
    } catch {
      // localStorage 满时静默失败
    }
  }, [history]);
  
  return history;
}
```

- [ ] **Step 2: 运行 TypeScript 检查**

Run: `npx tsc --noEmit`
Expected: 无类型错误

- [ ] **Step 3: 提交**

```bash
git add src/hooks/useLatencyHistory.ts
git commit -m "feat(dashboard): add useLatencyHistory hook for trend data"
```

---

## Task 6: 优化 Dashboard 使用延迟趋势数据

**Files:**
- Modify: `src/pages/Dashboard.tsx`

- [ ] **Step 1: 添加 import**

```tsx
import { useLatencyHistory } from '../hooks/useLatencyHistory';
```

- [ ] **Step 2: 在 Dashboard 组件中使用**

```tsx
export function Dashboard() {
  // ... 现有代码
  
  const latencyHistory = useLatencyHistory();
  
  // 延迟趋势图表数据（优先使用累积历史，降级到实时指标）
  const latencyChartData = useMemo(() => {
    if (latencyHistory.length > 5) {
      // 使用累积的历史数据
      return [
        { 
          id: t('dashboard.latency.ttft'), 
          data: latencyHistory.map((p, i) => ({ x: `${i}`, y: p.ttft }))
        },
      ];
    }
    
    // 降级到原有的实时指标
    return metrics ? [
      { id: t('dashboard.latency.ttft'), data: metrics.latency_trend.filter(...).map(...) },
      // ...
    ] : [];
  }, [latencyHistory, metrics, t]);
  
  // ... 其余代码
}
```

- [ ] **Step 3: 更新 Pipeline 分解降级策略**

```tsx
// Pipeline 分解数据（优先使用 WebSocket 实时数据，降级到 localStorage 缓存）
const hasPipelineData = rtMetrics.pipeline && (rtMetrics.pipeline.retrieval_ms ?? 0) > 0;

const [cachedPipeline, setCachedPipeline] = useState(() => {
  try {
    const saved = localStorage.getItem('aureon:pipeline:last');
    return saved ? JSON.parse(saved) : null;
  } catch {
    return null;
  }
});

useEffect(() => {
  if (hasPipelineData) {
    try {
      localStorage.setItem('aureon:pipeline:last', JSON.stringify(rtMetrics.pipeline));
      setCachedPipeline(rtMetrics.pipeline);
    } catch {
      // 静默失败
    }
  }
}, [hasPipelineData, rtMetrics.pipeline]);

const pipelineData = hasPipelineData ? rtMetrics.pipeline : cachedPipeline;

const pipelineStages = pipelineData ? [
  { name: t('dashboard.pipeline.retrieval'), ms: pipelineData.retrieval_ms ?? 0, color: '#5E6AD2' },
  { name: t('dashboard.pipeline.generation'), ms: pipelineData.generation_ms ?? 0, color: '#EAB308' },
] : [];
```

- [ ] **Step 4: 更新"暂无数据"显示**

```tsx
// Pipeline 区域
{pipelineStages.length > 0 ? (
  <PipelineBreakdown stages={pipelineStages} />
) : (
  <div className="flex flex-col items-center justify-center h-[100px] text-[var(--text-tertiary)] text-sm">
    <p>{t('dashboard.no_data')}</p>
    <p className="text-xs mt-1">{t('dashboard.waiting_for_data', '等待 WebSocket 数据...')}</p>
  </div>
)}
```

- [ ] **Step 5: 添加 i18n key**

在 `src/i18n/zh.json` 的 `dashboard` 部分添加：
```json
"waiting_for_data": "等待 WebSocket 数据..."
```

在 `src/i18n/en.json` 的 `dashboard` 部分添加：
```json
"waiting_for_data": "Waiting for WebSocket data..."
```

- [ ] **Step 6: 运行测试**

Run: `npm test -- --run src/pages/__tests__/Dashboard.test.tsx`
Expected: 所有测试通过

- [ ] **Step 7: 提交**

```bash
git add src/pages/Dashboard.tsx src/i18n/zh.json src/i18n/en.json
git commit -m "feat(dashboard): integrate latency history and pipeline fallback"
```

---

## Task 7: 添加路由预加载

**Files:**
- Modify: `src/App.tsx`

- [ ] **Step 1: 添加预加载函数**

在 `App.tsx` 中添加：

```tsx
// 预加载函数
const preloadDashboard = () => import('./pages/Dashboard');
const preloadAdmin = () => import('./pages/Admin');
const preloadSearch = () => import('./pages/Search');
const preloadDocuments = () => import('./pages/Documents');
const preloadAnalytics = () => import('./pages/Analytics');
const preloadCost = () => import('./pages/CostGovernance');
```

- [ ] **Step 2: 创建带预加载的 NavLink 组件**

```tsx
interface NavLinkWithPreloadProps {
  to: string;
  preloadFn?: () => Promise<unknown>;
  children: React.ReactNode;
  className?: string;
}

function NavLinkWithPreload({ to, preloadFn, children, className }: NavLinkWithPreloadProps) {
  return (
    <Link
      to={to}
      onMouseEnter={preloadFn}
      onFocus={preloadFn}
      className={className}
    >
      {children}
    </Link>
  );
}
```

- [ ] **Step 3: 在导航中使用预加载**

替换现有的导航链接：

```tsx
<NavLinkWithPreload to="/dashboard" preloadFn={preloadDashboard}>
  {t('app.nav.dashboard')}
</NavLinkWithPreload>

<NavLinkWithPreload to="/admin" preloadFn={preloadAdmin}>
  {t('app.nav.admin')}
</NavLinkWithPreload>
```

- [ ] **Step 4: 运行测试**

Run: `npm test -- --run`
Expected: 所有测试通过

- [ ] **Step 5: 提交**

```bash
git add src/App.tsx
git commit -m "feat(routing): add hover-based route preloading"
```

---

## Task 8: 集成测试与验收

- [ ] **Step 1: 运行完整测试套件**

Run: `npm test -- --run`
Expected: 所有测试通过

- [ ] **Step 2: 运行 TypeScript 检查**

Run: `npx tsc --noEmit`
Expected: 无类型错误

- [ ] **Step 3: 运行 lint**

Run: `npm run lint`
Expected: 无错误

- [ ] **Step 4: 启动开发服务器验证**

Run: `npm run dev`

验证：
1. Admin 页面切换 Tab 时无 loading 闪烁
2. 5 分钟内切换 Tab 使用缓存数据
3. 审计日志日期选择器中英文一致
4. Dashboard 延迟趋势图表正常显示
5. Hover 导航链接时预加载对应页面

- [ ] **Step 5: 最终提交**

```bash
git add -A
git commit -m "feat: complete dashboard and admin optimization"
```

---

## 验收标准检查清单

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
