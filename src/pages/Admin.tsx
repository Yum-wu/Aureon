import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { authFetch } from '../services/authFetch';
import { AdminLayout } from '../components/admin/AdminLayout';
import { AdminTable } from '../components/admin/AdminTable';
import { AdminForm } from '../components/admin/AdminForm';
import { StatusBadge } from '../components/admin/StatusBadge';
import { ConfirmDialog } from '../components/admin/ConfirmDialog';
import { Card } from '../components/ui/Card';

/* ── 类型定义 ── */

interface SSOProvider {
  id: number;
  name: string;
  provider_type: string;
  client_id: string;
  enabled: boolean;
  created_at: string;
}

interface UserRecord {
  id: string;
  email: string;
  display_name: string;
  role: 'super_admin' | 'admin' | 'editor' | 'viewer';
  status: 'active' | 'suspended' | 'invited';
  last_login: string | null;
}

interface AuditEntry {
  id: number;
  timestamp: string;
  user: string;
  action: string;
  resource: string;
  severity: 'info' | 'warning' | 'critical';
  details: string;
}

interface WorkspaceRecord {
  id: string;
  name: string;
  member_count: number;
  quota: string;
  status: 'active' | 'archived';
}

interface FeatureFlag {
  key: string;
  name: string;
  description: string;
  enabled: boolean;
  rules: string;
}

interface Permission {
  key: string;
  label: string;
}

/* ── 角色权限矩阵 ── */
const ROLES = ['super_admin', 'admin', 'editor', 'viewer'] as const;
type Role = (typeof ROLES)[number];

const PERMISSIONS: Permission[] = [
  { key: 'users.read', label: '查看用户' },
  { key: 'users.write', label: '编辑用户' },
  { key: 'users.delete', label: '删除用户' },
  { key: 'workspaces.read', label: '查看工作区' },
  { key: 'workspaces.write', label: '编辑工作区' },
  { key: 'workspaces.delete', label: '删除工作区' },
  { key: 'audit.read', label: '查看审计日志' },
  { key: 'audit.export', label: '导出审计日志' },
  { key: 'flags.read', label: '查看 Feature Flags' },
  { key: 'flags.write', label: '编辑 Feature Flags' },
  { key: 'sso.read', label: '查看 SSO 配置' },
  { key: 'sso.write', label: '编辑 SSO 配置' },
  { key: 'cost.read', label: '查看成本数据' },
  { key: 'cost.budget', label: '管理预算' },
];

// 默认权限映射
const DEFAULT_PERMISSIONS: Record<Role, string[]> = {
  super_admin: PERMISSIONS.map((p) => p.key),
  admin: PERMISSIONS.filter((p) => !p.key.startsWith('sso.write')).map((p) => p.key),
  editor: ['workspaces.read', 'workspaces.write', 'audit.read', 'cost.read', 'flags.read'],
  viewer: ['workspaces.read', 'audit.read', 'cost.read', 'flags.read'],
};

/* ── Tab 类型 ── */
type AdminTab = 'overview' | 'users' | 'roles' | 'workspaces' | 'audit' | 'flags' | 'sso';

/* ── 概览 Tab ── */
function OverviewTab() {
  const { t } = useTranslation();
  const [overviewData, setOverviewData] = useState<{
    active_users: number;
    today_queries: number;
    storage_usage: string;
    uptime: string;
  } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    authFetch('/api/rag/stats', { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) {
          setOverviewData({
            active_users: 12,
            today_queries: data.query_count_24h || 0,
            storage_usage: '2.4 GB',
            uptime: '99.9%',
          });
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  if (loading) {
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

  const cards = overviewData
    ? [
        { label: t('admin.overview.active_users'), value: overviewData.active_users },
        { label: t('admin.overview.today_queries'), value: overviewData.today_queries },
        { label: t('admin.overview.storage_usage'), value: overviewData.storage_usage },
        { label: t('admin.overview.uptime'), value: overviewData.uptime },
      ]
    : [];

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

/* ── 用户管理 Tab ── */
function UsersTab() {
  const { t } = useTranslation();
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [showInviteForm, setShowInviteForm] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{ type: 'suspend' | 'delete'; user: UserRecord } | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    authFetch('/api/security/users', { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => setUsers(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  const filteredUsers = users.filter(
    (u) => u.email.toLowerCase().includes(searchQuery.toLowerCase()) || u.display_name.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  const handleRoleChange = useCallback(async (userId: string, newRole: string) => {
    try {
      const res = await authFetch(`/api/security/users/${userId}/role`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: newRole }),
      });
      if (res.ok) {
        setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, role: newRole as UserRecord['role'] } : u)));
      }
    } catch {
      // 角色更新失败
    }
  }, []);

  const handleSuspend = useCallback(async (userId: string) => {
    try {
      const res = await authFetch(`/api/security/users/${userId}/suspend`, { method: 'POST' });
      if (res.ok) {
        setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, status: 'suspended' as const } : u)));
      }
    } catch {
      // 暂停失败
    }
    setConfirmAction(null);
  }, []);

  const handleDelete = useCallback(async (userId: string) => {
    try {
      const res = await authFetch(`/api/security/users/${userId}`, { method: 'DELETE' });
      if (res.ok) {
        setUsers((prev) => prev.filter((u) => u.id !== userId));
      }
    } catch {
      // 删除失败
    }
    setConfirmAction(null);
  }, []);

  const columns = [
    { key: 'email', label: t('admin.users.columns.email'), sortable: true },
    { key: 'display_name', label: t('admin.users.columns.user'), sortable: true },
    {
      key: 'role',
      label: t('admin.users.columns.role'),
      sortable: true,
      render: (user: UserRecord) => (
        <select
          value={user.role}
          onChange={(e) => handleRoleChange(user.id, e.target.value)}
          className="px-2 py-1 text-xs rounded border border-[var(--border)] bg-[var(--bg-tertiary)] text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
        >
          {ROLES.map((role) => (
            <option key={role} value={role}>{t(`admin.roles.${role}`)}</option>
          ))}
        </select>
      ),
    },
    {
      key: 'status',
      label: t('admin.users.columns.status'),
      render: (user: UserRecord) => <StatusBadge status={user.status} />,
    },
    {
      key: 'last_login',
      label: t('admin.users.columns.last_active'),
      sortable: true,
      render: (user: UserRecord) => (
        <span className="text-xs text-[var(--text-tertiary)]">
          {user.last_login ? new Date(user.last_login).toLocaleDateString() : '—'}
        </span>
      ),
    },
    {
      key: 'actions',
      label: t('admin.users.columns.actions'),
      render: (user: UserRecord) => (
        <div className="flex items-center gap-2">
          <button
            onClick={() => setConfirmAction({ type: 'suspend', user })}
            className="text-xs text-[var(--warning)] hover:underline"
          >
            {t('admin.users.suspend')}
          </button>
          <button
            onClick={() => setConfirmAction({ type: 'delete', user })}
            className="text-xs text-[var(--error)] hover:underline"
          >
            {t('admin.users.delete')}
          </button>
        </div>
      ),
    },
  ];

  return (
    <div>
      {/* 搜索栏 + 邀请按钮 */}
      <div className="flex items-center gap-3 mb-4">
        <input
          type="text"
          placeholder={t('admin.users.search_placeholder')}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="flex-1 px-3 py-2 text-sm rounded-lg border border-[var(--border)] bg-[var(--bg-tertiary)] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
        />
        <button
          onClick={() => setShowInviteForm(true)}
          className="px-4 py-2 text-sm font-medium bg-[var(--accent)] text-white rounded-lg hover:bg-[var(--accent-hover)] transition-colors"
        >
          {t('admin.users.invite_button')}
        </button>
      </div>

      <AdminTable<UserRecord>
        data={filteredUsers}
        columns={columns}
        keyField="id"
        loading={loading}
        emptyMessage={t('admin.users.empty')}
      />

      {/* 邀请用户弹窗 */}
      {showInviteForm && (
        <AdminForm
          title={t('admin.users.invite')}
          fields={[
            { key: 'email', label: t('admin.users.columns.email'), type: 'email', required: true },
            { key: 'display_name', label: t('admin.users.columns.user'), type: 'text', required: true },
            { key: 'role', label: t('admin.users.columns.role'), type: 'select', options: ROLES.map((r) => ({ value: r, label: t(`admin.roles.${r}`) })) },
          ]}
          onSubmit={async (values) => {
            await authFetch('/api/security/users/invite', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(values),
            });
            setShowInviteForm(false);
          }}
          onCancel={() => setShowInviteForm(false)}
        />
      )}

      {/* 确认弹窗 */}
      {confirmAction && (
        <ConfirmDialog
          title={confirmAction.type === 'suspend' ? t('admin.users.confirm_suspend') : t('admin.users.confirm_delete')}
          message={t(
            confirmAction.type === 'suspend' ? 'admin.users.confirm_suspend_msg' : 'admin.users.confirm_delete_msg',
            { name: confirmAction.user.display_name || confirmAction.user.email },
          )}
          confirmLabel={confirmAction.type === 'suspend' ? t('admin.users.suspend') : t('admin.users.delete')}
          variant={confirmAction.type === 'delete' ? 'danger' : 'warning'}
          onConfirm={() => {
            if (confirmAction.type === 'suspend') handleSuspend(confirmAction.user.id);
            else handleDelete(confirmAction.user.id);
          }}
          onCancel={() => setConfirmAction(null)}
        />
      )}
    </div>
  );
}

/* ── 角色权限 Tab ── */
function RolesTab() {
  const { t } = useTranslation();
  const [permissions, setPermissions] = useState<Record<Role, string[]>>(DEFAULT_PERMISSIONS);

  const togglePermission = (role: Role, permKey: string) => {
    setPermissions((prev) => {
      const current = prev[role];
      const updated = current.includes(permKey) ? current.filter((k) => k !== permKey) : [...current, permKey];
      return { ...prev, [role]: updated };
    });
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[var(--border)]">
            <th className="text-left py-3 px-4 text-[var(--text-tertiary)] font-medium">{t('admin.roles.permission')}</th>
            {ROLES.map((role) => (
              <th key={role} className="text-center py-3 px-4 text-[var(--text-tertiary)] font-medium">
                {t(`admin.roles.${role}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {PERMISSIONS.map((perm) => (
            <tr key={perm.key} className="border-b border-[var(--border-subtle)] hover:bg-white/[0.02]">
              <td className="py-3 px-4 text-[var(--text-primary)]">{perm.label}</td>
              {ROLES.map((role) => (
                <td key={role} className="text-center py-3 px-4">
                  <button
                    onClick={() => togglePermission(role, perm.key)}
                    className={`inline-flex items-center justify-center w-6 h-6 rounded text-sm ${
                      permissions[role]?.includes(perm.key)
                        ? 'text-emerald-400'
                        : 'text-[var(--text-tertiary)]'
                    }`}
                  >
                    {permissions[role]?.includes(perm.key) ? '✅' : '❌'}
                  </button>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── 工作区 Tab ── */
function WorkspacesTab() {
  const { t } = useTranslation();
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    authFetch('/api/security/workspaces', { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => setWorkspaces(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  const columns = [
    { key: 'name', label: t('admin.workspaces.columns.name'), sortable: true },
    { key: 'member_count', label: t('admin.workspaces.columns.members'), sortable: true },
    { key: 'quota', label: t('admin.workspaces.columns.quota') },
    {
      key: 'status',
      label: t('admin.workspaces.columns.status'),
      render: (ws: WorkspaceRecord) => <StatusBadge status={ws.status} />,
    },
    {
      key: 'actions',
      label: t('admin.workspaces.columns.actions'),
      render: (_ws: WorkspaceRecord) => (
        <button className="text-xs text-[var(--accent)] hover:underline">{t('admin.workspaces.edit')}</button>
      ),
    },
  ];

  return (
    <AdminTable<WorkspaceRecord>
      data={workspaces}
      columns={columns}
      keyField="id"
      loading={loading}
      emptyMessage={t('admin.workspaces.empty')}
    />
  );
}

/* ── 审计日志 Tab ── */
function AuditTab() {
  const { t } = useTranslation();
  const [auditLogs, setAuditLogs] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedRow, setExpandedRow] = useState<number | null>(null);
  const [filters, setFilters] = useState({
    dateFrom: '',
    dateTo: '',
    user: '',
    actionType: '',
    severity: '',
  });

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams();
    if (filters.user) params.set('user', filters.user);
    if (filters.actionType) params.set('action', filters.actionType);
    if (filters.severity) params.set('severity', filters.severity);
    if (filters.dateFrom) params.set('from', filters.dateFrom);
    if (filters.dateTo) params.set('to', filters.dateTo);

    authFetch(`/api/audit/logs?${params.toString()}`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => setAuditLogs(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [filters]);

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
    }).catch(() => {});
  }, []);

  const columns = [
    {
      key: 'timestamp',
      label: t('admin.audit.columns.timestamp'),
      sortable: true,
      render: (entry: AuditEntry) => (
        <span className="text-xs text-[var(--text-tertiary)] tabular-nums">
          {new Date(entry.timestamp).toLocaleString()}
        </span>
      ),
    },
    { key: 'user', label: t('admin.audit.columns.user'), sortable: true },
    { key: 'action', label: t('admin.audit.columns.action'), sortable: true },
    { key: 'resource', label: t('admin.audit.columns.resource') },
    {
      key: 'severity',
      label: t('admin.audit.columns.severity'),
      render: (entry: AuditEntry) => <StatusBadge status={entry.severity} />,
    },
  ];

  return (
    <div>
      {/* 筛选栏 */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <input
          type="date"
          value={filters.dateFrom}
          onChange={(e) => setFilters((f) => ({ ...f, dateFrom: e.target.value }))}
          className="px-3 py-1.5 text-xs rounded-lg border border-[var(--border)] bg-[var(--bg-tertiary)] text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
        />
        <input
          type="date"
          value={filters.dateTo}
          onChange={(e) => setFilters((f) => ({ ...f, dateTo: e.target.value }))}
          className="px-3 py-1.5 text-xs rounded-lg border border-[var(--border)] bg-[var(--bg-tertiary)] text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
        />
        <input
          type="text"
          placeholder={t('admin.audit.filter_user')}
          value={filters.user}
          onChange={(e) => setFilters((f) => ({ ...f, user: e.target.value }))}
          className="px-3 py-1.5 text-xs rounded-lg border border-[var(--border)] bg-[var(--bg-tertiary)] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
        />
        <select
          value={filters.actionType}
          onChange={(e) => setFilters((f) => ({ ...f, actionType: e.target.value }))}
          className="px-3 py-1.5 text-xs rounded-lg border border-[var(--border)] bg-[var(--bg-tertiary)] text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
        >
          <option value="">{t('admin.audit.all_actions')}</option>
          <option value="login">{t('admin.audit.action_login')}</option>
          <option value="query">{t('admin.audit.action_query')}</option>
          <option value="upload">{t('admin.audit.action_upload')}</option>
          <option value="config">{t('admin.audit.action_config')}</option>
        </select>
        <select
          value={filters.severity}
          onChange={(e) => setFilters((f) => ({ ...f, severity: e.target.value }))}
          className="px-3 py-1.5 text-xs rounded-lg border border-[var(--border)] bg-[var(--bg-tertiary)] text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
        >
          <option value="">{t('admin.audit.all_severity')}</option>
          <option value="info">{t('admin.audit.severity_info')}</option>
          <option value="warning">{t('admin.audit.severity_warning')}</option>
          <option value="critical">{t('admin.audit.severity_critical')}</option>
        </select>
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => handleExport('csv')}
            className="px-3 py-1.5 text-xs font-medium rounded-lg border border-[var(--border)] text-[var(--text-secondary)] hover:bg-white/[0.03] transition-colors"
          >
            {t('admin.audit.export_csv')}
          </button>
          <button
            onClick={() => handleExport('json')}
            className="px-3 py-1.5 text-xs font-medium rounded-lg border border-[var(--border)] text-[var(--text-secondary)] hover:bg-white/[0.03] transition-colors"
          >
            {t('admin.audit.export_json')}
          </button>
        </div>
      </div>

      <AdminTable<AuditEntry>
        data={auditLogs}
        columns={columns}
        keyField="id"
        loading={loading}
        emptyMessage={t('admin.audit.empty')}
        onRowClick={(entry) => setExpandedRow(expandedRow === entry.id ? null : entry.id)}
        expandRow={(entry) =>
          expandedRow === entry.id ? (
            <div className="px-4 py-3 bg-[var(--bg-tertiary)] text-sm text-[var(--text-secondary)]">
              <p><strong>{t('admin.audit.columns.details')}:</strong> {entry.details}</p>
            </div>
          ) : null
        }
      />
    </div>
  );
}

/* ── Feature Flags Tab ── */
function FlagsTab() {
  const { t } = useTranslation();
  const [flags, setFlags] = useState<FeatureFlag[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    authFetch('/api/feature-flags/', { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => setFlags(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  const toggleFlag = useCallback(async (flagKey: string) => {
    setFlags((prev) => prev.map((f) => (f.key === flagKey ? { ...f, enabled: !f.enabled } : f)));
    try {
      await authFetch(`/api/feature-flags/${flagKey}/toggle`, { method: 'POST' });
    } catch {
      // 回滚
      setFlags((prev) => prev.map((f) => (f.key === flagKey ? { ...f, enabled: !f.enabled } : f)));
    }
  }, []);

  if (loading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-4 animate-pulse">
            <div className="h-4 bg-[var(--bg-tertiary)] rounded w-32 mb-2" />
            <div className="h-3 bg-[var(--bg-tertiary)] rounded w-64" />
          </div>
        ))}
      </div>
    );
  }

  if (flags.length === 0) {
    return (
      <div className="text-center py-12 text-[var(--text-tertiary)]">
        <p className="text-lg mb-2">{t('admin.flags.empty')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {flags.map((flag) => (
        <div key={flag.key} className="flex items-center gap-4 p-4 rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)]">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-[var(--text-primary)]">{flag.name}</p>
            <p className="text-xs text-[var(--text-tertiary)] mt-0.5">{flag.description}</p>
            {flag.rules && (
              <p className="text-xs text-[var(--text-tertiary)] mt-1 font-mono">{flag.rules}</p>
            )}
          </div>
          <button
            onClick={() => toggleFlag(flag.key)}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
              flag.enabled ? 'bg-[var(--accent)]' : 'bg-[var(--bg-tertiary)]'
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                flag.enabled ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
          </button>
        </div>
      ))}
    </div>
  );
}

/* ── SSO Tab ── */
function SSOTab() {
  const { t } = useTranslation();
  const [providers, setProviders] = useState<SSOProvider[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    authFetch('/api/security/sso/providers', { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => setProviders(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  if (loading) {
    return <div className="p-8 text-center text-[var(--text-tertiary)]">{t('admin.loading')}</div>;
  }

  if (providers.length === 0) {
    return (
      <div className="text-center py-12 text-[var(--text-tertiary)]">
        <p className="text-lg mb-2">{t('admin.no_providers')}</p>
        <p className="text-sm">{t('admin.no_providers_desc')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {providers.map((p) => (
        <div key={p.id} className="flex items-center gap-4 p-4 bg-[var(--bg-tertiary)] rounded-lg">
          <div className="w-10 h-10 rounded-lg bg-[var(--accent-soft)] flex items-center justify-center text-[var(--accent)] font-bold text-sm">
            {p.provider_type?.slice(0, 2).toUpperCase() || 'SS'}
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-medium text-[var(--text-primary)] truncate">{p.name}</div>
            <div className="text-sm text-[var(--text-tertiary)]">{p.provider_type} | Client ID: {p.client_id?.slice(0, 20)}...</div>
          </div>
          <span className={`px-2 py-1 text-xs font-medium rounded-full ${p.enabled ? 'bg-emerald-500/10 text-emerald-400' : 'bg-[var(--bg-secondary)] text-[var(--text-tertiary)]'}`}>
            {p.enabled ? t('admin.active') : t('admin.disabled')}
          </span>
        </div>
      ))}
    </div>
  );
}

/* ── 主组件 ── */

const Admin = () => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<AdminTab>('overview');

  const tabs: { id: AdminTab; label: string; icon: string }[] = [
    { id: 'overview', label: t('admin.tabs.overview'), icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
    { id: 'users', label: t('admin.tabs.users'), icon: 'M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z' },
    { id: 'roles', label: t('admin.tabs.roles'), icon: 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z' },
    { id: 'workspaces', label: t('admin.tabs.workspaces'), icon: 'M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4' },
    { id: 'audit', label: t('admin.tabs.audit'), icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2' },
    { id: 'flags', label: t('admin.tabs.flags'), icon: 'M3 4h13M3 8h9m-9 4h6m4 0l4-4m0 0l4 4m-4-4v12' },
    { id: 'sso', label: t('admin.tabs.sso'), icon: 'M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z' },
  ];

  const renderTab = () => {
    switch (activeTab) {
      case 'overview': return <OverviewTab />;
      case 'users': return <UsersTab />;
      case 'roles': return <RolesTab />;
      case 'workspaces': return <WorkspacesTab />;
      case 'audit': return <AuditTab />;
      case 'flags': return <FlagsTab />;
      case 'sso': return <SSOTab />;
    }
  };

  return (
    <AdminLayout
      title={t('admin.title')}
      subtitle={t('admin.subtitle')}
      tabs={tabs}
      activeTab={activeTab}
      onTabChange={setActiveTab}
    >
      {renderTab()}
    </AdminLayout>
  );
};

export default Admin;
