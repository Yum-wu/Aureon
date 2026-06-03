import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';

interface SSOProvider {
  id: number;
  name: string;
  provider_type: string;
  client_id: string;
  enabled: boolean;
  created_at: string;
}

interface AuditEntry {
  id: number;
  request_id: string;
  query: string;
  intent: string;
  total_latency_ms: number;
  created_at: string;
}

const Admin = () => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'providers' | 'audit'>('providers');
  const [providers, setProviders] = useState<SSOProvider[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetch('/api/security/sso/providers', { signal: controller.signal }).then(r => r.ok ? r.json() : []),
      fetch('/api/observability/traces?limit=20', { signal: controller.signal }).then(r => r.ok ? r.json() : { traces: [] }),
    ]).then(([provs, traces]) => {
      setProviders(Array.isArray(provs) ? provs : []);
      setAuditLogs(traces.traces || []);
    }).catch(() => {}).finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  const tabs = [
    { id: 'providers' as const, label: t('admin.users.title'), icon: 'M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z' },
    { id: 'audit' as const, label: t('admin.audit.title'), icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2' },
  ];

  return (
    <div className="h-full overflow-y-auto p-4 md:p-6 max-w-7xl mx-auto">
      <div className="mb-6 md:mb-8">
        <h1 className="text-xl md:text-2xl font-bold text-[var(--text-primary)]">{t('admin.title')}</h1>
        <p className="text-[var(--text-tertiary)] text-sm">{t('admin.subtitle')}</p>
      </div>

      <div className="flex gap-1 mb-4 md:mb-6 border-b border-[var(--border)] overflow-x-auto">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-3 md:px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              activeTab === tab.id
                ? 'border-[var(--accent)] text-[var(--accent)]'
                : 'border-transparent text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:border-[var(--border-hover)]'
            }`}
          >
            <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={tab.icon} />
            </svg>
            <span className="hidden sm:inline">{tab.label}</span>
          </button>
        ))}
      </div>

      <div className="bg-[var(--bg-secondary)] rounded-xl border border-[var(--border)]">
        {loading && (
          <div className="p-8 text-center text-[var(--text-tertiary)]">{t('admin.loading')}</div>
        )}

        {!loading && activeTab === 'providers' && (
          <div className="p-4 md:p-6">
            <div className="flex items-center justify-between mb-4 md:mb-6">
              <h3 className="font-semibold text-[var(--text-primary)]">{t('admin.identity_providers')}</h3>
              <span className="text-sm text-[var(--text-tertiary)]">{providers.length} {t('admin.configured')}</span>
            </div>
            {providers.length === 0 ? (
              <div className="text-center py-12 text-[var(--text-tertiary)]">
                <p className="text-lg mb-2">{t('admin.no_providers')}</p>
                <p className="text-sm">{t('admin.no_providers_desc')}</p>
              </div>
            ) : (
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
            )}
          </div>
        )}

        {!loading && activeTab === 'audit' && (
          <div className="p-4 md:p-6">
            <div className="flex items-center justify-between mb-4 md:mb-6">
              <h3 className="font-semibold text-[var(--text-primary)]">{t('admin.query_audit_log')}</h3>
              <span className="text-sm text-[var(--text-tertiary)]">{auditLogs.length} {t('admin.recent_traces')}</span>
            </div>
            {auditLogs.length === 0 ? (
              <div className="text-center py-12 text-[var(--text-tertiary)]">
                <p className="text-lg mb-2">{t('admin.no_traces')}</p>
                <p className="text-sm">{t('admin.no_traces_desc')}</p>
              </div>
            ) : (
              <div className="space-y-3">
                {auditLogs.map((log) => (
                  <div key={log.id} className="flex items-start gap-3 md:gap-4 p-3 md:p-4 bg-[var(--bg-tertiary)] rounded-lg">
                    <div className="text-xs text-[var(--text-tertiary)] w-16 shrink-0">
                      {log.created_at ? new Date(log.created_at).toLocaleTimeString() : '-'}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                          log.intent === 'rag' ? 'bg-blue-500/10 text-blue-400' :
                          log.intent === 'chat' ? 'bg-emerald-500/10 text-emerald-400' :
                          'bg-[var(--bg-secondary)] text-[var(--text-tertiary)]'
                        }`}>
                          {log.intent || 'unknown'}
                        </span>
                        <span className="text-sm text-[var(--text-secondary)] truncate">{log.query?.slice(0, 80)}</span>
                      </div>
                      <div className="text-xs text-[var(--text-tertiary)] mt-1">
                        {log.total_latency_ms ? `${log.total_latency_ms}ms` : '-'} | {log.request_id}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default Admin;
