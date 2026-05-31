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
    { id: 'providers' as const, label: t('admin.users.title', 'Identity Providers'), icon: 'M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z' },
    { id: 'audit' as const, label: t('admin.audit.title', 'Query Audit Log'), icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2' },
  ];

  return (
    <div className="h-full overflow-y-auto p-4 md:p-6 max-w-7xl mx-auto">
      <div className="mb-6 md:mb-8">
        <h1 className="text-xl md:text-2xl font-bold text-gray-900">{t('admin.title')}</h1>
        <p className="text-gray-500 text-sm">{t('admin.subtitle')}</p>
      </div>

      <div className="flex gap-1 mb-4 md:mb-6 border-b border-gray-200 overflow-x-auto">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-3 md:px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              activeTab === tab.id
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={tab.icon} />
            </svg>
            <span className="hidden sm:inline">{tab.label}</span>
          </button>
        ))}
      </div>

      <div className="bg-white rounded-xl border border-gray-200">
        {loading && (
          <div className="p-8 text-center text-gray-400">Loading...</div>
        )}

        {!loading && activeTab === 'providers' && (
          <div className="p-4 md:p-6">
            <div className="flex items-center justify-between mb-4 md:mb-6">
              <h3 className="font-semibold text-gray-900">SSO Identity Providers</h3>
              <span className="text-sm text-gray-500">{providers.length} configured</span>
            </div>
            {providers.length === 0 ? (
              <div className="text-center py-12 text-gray-400">
                <p className="text-lg mb-2">No identity providers configured</p>
                <p className="text-sm">Configure SSO via the API or security settings</p>
              </div>
            ) : (
              <div className="space-y-3">
                {providers.map((p) => (
                  <div key={p.id} className="flex items-center gap-4 p-4 bg-gray-50 rounded-lg">
                    <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center text-blue-600 font-bold text-sm">
                      {p.provider_type?.slice(0, 2).toUpperCase() || 'SS'}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-gray-900 truncate">{p.name}</div>
                      <div className="text-sm text-gray-500">{p.provider_type} | Client ID: {p.client_id?.slice(0, 20)}...</div>
                    </div>
                    <span className={`px-2 py-1 text-xs font-medium rounded-full ${p.enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                      {p.enabled ? 'Active' : 'Disabled'}
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
              <h3 className="font-semibold text-gray-900">Query Audit Log</h3>
              <span className="text-sm text-gray-500">{auditLogs.length} recent traces</span>
            </div>
            {auditLogs.length === 0 ? (
              <div className="text-center py-12 text-gray-400">
                <p className="text-lg mb-2">No query traces yet</p>
                <p className="text-sm">Traces will appear here as users interact with the system</p>
              </div>
            ) : (
              <div className="space-y-3">
                {auditLogs.map((log) => (
                  <div key={log.id} className="flex items-start gap-3 md:gap-4 p-3 md:p-4 bg-gray-50 rounded-lg">
                    <div className="text-xs text-gray-400 w-16 shrink-0">
                      {log.created_at ? new Date(log.created_at).toLocaleTimeString() : '-'}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                          log.intent === 'rag' ? 'bg-blue-100 text-blue-700' :
                          log.intent === 'chat' ? 'bg-green-100 text-green-700' :
                          'bg-gray-100 text-gray-600'
                        }`}>
                          {log.intent || 'unknown'}
                        </span>
                        <span className="text-sm text-gray-600 truncate">{log.query?.slice(0, 80)}</span>
                      </div>
                      <div className="text-xs text-gray-400 mt-1">
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
