import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
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
  i18nKey: string;
}

/* ── 角色权限矩阵 ── */
const ROLES = ['super_admin', 'admin', 'editor', 'viewer'] as const;
type Role = (typeof ROLES)[number];

// i18n keys for permission labels — actual labels resolved via t() in RolesTab
const PERMISSION_KEYS = [
  'users.read', 'users.write', 'users.delete',
  'workspaces.read', 'workspaces.write', 'workspaces.delete',
  'audit.read', 'audit.export',
  'flags.read', 'flags.write',
  'sso.read', 'sso.write',
  'cost.read', 'cost.budget',
] as const;

interface Permission {
  key: string;
  i18nKey: string;
}

function usePermissions(): Permission[] {
  const { t } = useTranslation();
  return PERMISSION_KEYS.map((key) => ({
    key,
    i18nKey: t(`admin.permissions.${key}`, { defaultValue: key }),
  }));
}

// 默认权限映射
const DEFAULT_PERMISSIONS: Record<Role, string[]> = {
  super_admin: [...PERMISSION_KEYS],
  admin: PERMISSION_KEYS.filter((k) => !k.startsWith('sso.write')),
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

    async function fetchData() {
      try {
        const [statsRes, usersRes] = await Promise.all([
          authFetch('/api/rag/stats', { signal: controller.signal }),
          authFetch('/api/security/users', { signal: controller.signal }),
        ]);

        const statsData = statsRes.ok ? await statsRes.json() : null;
        const usersData = usersRes.ok ? await usersRes.json() : [];
        const activeUsers = Array.isArray(usersData)
          ? usersData.filter((u: { status?: string }) => u.status === 'active').length
          : 0;

        setOverviewData({
          active_users: activeUsers,
          today_queries: statsData?.query_count_24h || 0,
          storage_usage: '2.4 GB',
          uptime: '99.9%',
        });
      } catch {
        // 静默失败
      } finally {
        setLoading(false);
      }
    }

    fetchData();
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

  if (!overviewData) {
    return (
      <div className="text-center py-12 text-[var(--text-tertiary)]">
        <p className="text-lg mb-2">{t('admin.overview.no_data')}</p>
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
        toast.success(t('admin.users.role_updated'));
      } else {
        toast.error(t('admin.users.role_update_failed'));
      }
    } catch {
      toast.error(t('admin.users.role_update_failed'));
    }
  }, [t]);

  const handleSuspend = useCallback(async (userId: string) => {
    try {
      const res = await authFetch(`/api/security/users/${userId}/suspend`, { method: 'POST' });
      if (res.ok) {
        setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, status: 'suspended' as const } : u)));
        toast.success(t('admin.users.suspended'));
      } else {
        toast.error(t('admin.users.suspend_failed'));
      }
    } catch {
      toast.error(t('admin.users.suspend_failed'));
    }
    setConfirmAction(null);
  }, [t]);

  const handleDelete = useCallback(async (userId: string) => {
    try {
      const res = await authFetch(`/api/security/users/${userId}`, { method: 'DELETE' });
      if (res.ok) {
        setUsers((prev) => prev.filter((u) => u.id !== userId));
        toast.success(t('admin.users.deleted'));
      } else {
        toast.error(t('admin.users.delete_failed'));
      }
    } catch {
      toast.error(t('admin.users.delete_failed'));
    }
    setConfirmAction(null);
  }, [t]);

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
      render: (user: UserRecord) => {
        const userStatusMap: Record<string, import('../components/admin/StatusBadge').StatusType> = {
          active: 'active',
          suspended: 'suspended',
          invited: 'disabled',
        };
        return <StatusBadge status={userStatusMap[user.status] ?? 'disabled'} />;
      },
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
        loading={loading}
      />

      {!loading && filteredUsers.length === 0 && (
        <div className="text-center py-12 text-[var(--text-tertiary)]">
          <p className="text-lg mb-2">{t('admin.users.no_users')}</p>
          <p className="text-sm">{t('admin.users.no_users_desc')}</p>
        </div>
      )}

      {/* 邀请用户弹窗 */}
      {showInviteForm && (
        <AdminForm
          title={t('admin.users.invite')}
          fields={[
            { name: 'email', label: t('admin.users.columns.email'), type: 'email', required: true },
            { name: 'display_name', label: t('admin.users.columns.user'), type: 'text', required: true },
            { name: 'role', label: t('admin.users.columns.role'), type: 'select', options: ROLES.map((r) => ({ value: r, label: t(`admin.roles.${r}`) })) },
          ]}
          onSubmit={async (values) => {
            try {
              const res = await authFetch('/api/security/users/invite', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(values),
              });
              if (res.ok) {
                toast.success(t('admin.users.invite_sent'));
                setShowInviteForm(false);
              } else {
                toast.error(t('admin.users.invite_failed'));
              }
            } catch {
              toast.error(t('admin.users.invite_failed'));
            }
          }}
        />
      )}

      {/* 确认弹窗 */}
      {confirmAction && (
        <ConfirmDialog
          open={!!confirmAction}
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
  const permissions = usePermissions();
  const [permState, setPermState] = useState<Record<Role, string[]>>(DEFAULT_PERMISSIONS);

  const togglePermission = (role: Role, permKey: string) => {
    setPermState((prev) => {
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
          {permissions.map((perm) => (
            <tr key={perm.key} className="border-b border-[var(--border-subtle)] hover:bg-white/[0.02]">
              <td className="py-3 px-4 text-[var(--text-primary)]">{perm.i18nKey}</td>
              {ROLES.map((role) => (
                <td key={role} className="text-center py-3 px-4">
                  <button
                    onClick={() => togglePermission(role, perm.key)}
                    className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                      permState[role]?.includes(perm.key) ? 'bg-[var(--accent)]' : 'bg-[var(--bg-tertiary)]'
                    }`}
                    role="switch"
                    aria-checked={permState[role]?.includes(perm.key) ?? false}
                    aria-label={`${perm.i18nKey} - ${t(`admin.roles.${role}`)}`}
                  >
                    <span
                      className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                        permState[role]?.includes(perm.key) ? 'translate-x-4' : 'translate-x-0.5'
                      }`}
                    />
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
      render: (ws: WorkspaceRecord) => {
        const wsStatusMap: Record<string, import('../components/admin/StatusBadge').StatusType> = {
          active: 'active',
          archived: 'disabled',
        };
        return <StatusBadge status={wsStatusMap[ws.status] ?? 'disabled'} />;
      },
    },
    {
      key: 'actions',
      label: t('admin.workspaces.columns.actions'),
      render: () => (
        <button className="text-xs text-[var(--accent)] hover:underline">{t('admin.workspaces.edit')}</button>
      ),
    },
  ];

  return (
    <div>
      <AdminTable<WorkspaceRecord>
        data={workspaces}
        columns={columns}
        loading={loading}
      />
      {!loading && workspaces.length === 0 && (
        <div className="text-center py-12 text-[var(--text-tertiary)]">
          <p className="text-lg mb-2">{t('admin.workspaces.empty')}</p>
          <p className="text-sm">{t('admin.workspaces.empty_desc')}</p>
        </div>
      )}
    </div>
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
      toast.success(t('admin.audit.export_success'));
    }).catch(() => {
      toast.error(t('admin.audit.export_failed'));
    });
  }, [t]);

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
      render: (entry: AuditEntry) => {
        const severityMap: Record<string, import('../components/admin/StatusBadge').StatusType> = {
          critical: 'error',
          warning: 'warning',
          info: 'active',
        };
        return <StatusBadge status={severityMap[entry.severity] ?? 'active'} />;
      },
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
        loading={loading}
        onRowClick={(entry: AuditEntry) => setExpandedRow(expandedRow === entry.id ? null : entry.id)}
      />
      {!loading && auditLogs.length === 0 && (
        <div className="text-center py-12 text-[var(--text-tertiary)]">
          <p className="text-lg mb-2">{t('admin.audit.empty')}</p>
          <p className="text-sm">{t('admin.audit.empty_desc')}</p>
        </div>
      )}
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
    const prevEnabled = flags.find(f => f.key === flagKey)?.enabled ?? false;
    setFlags((prev) => prev.map((f) => (f.key === flagKey ? { ...f, enabled: !f.enabled } : f)));
    try {
      await authFetch(`/api/feature-flags/${flagKey}/toggle`, { method: 'POST' });
      toast.success(t('admin.flags.toggled'));
    } catch {
      setFlags((prev) => prev.map((f) => (f.key === flagKey ? { ...f, enabled: prevEnabled } : f)));
      toast.error(t('admin.flags.toggle_failed'));
    }
  }, [flags, t]);

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
  const [activeTab, setActiveTab] = useState<AdminTab>('overview');

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
      activeTab={activeTab}
      onTabChange={setActiveTab}
    >
      {renderTab()}
    </AdminLayout>
  );
};

export default Admin;
