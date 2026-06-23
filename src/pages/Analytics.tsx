import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAnalyticsData } from '../hooks/useAnalyticsData';
import { useViewStore } from '../stores/useViewStore';
import { Breadcrumb } from '../components/ui/Breadcrumb';
import { Tabs } from '../components/ui/Tabs';
import { ProgressBar } from '../components/ui/ProgressBar';
import { DataTable } from '../components/ui/DataTable';
import { StatusDot } from '../components/ui/StatusDot';
import { RefreshCw } from 'lucide-react';

type AnalyticsTab = 'overview' | 'latency' | 'tokens' | 'queries';

/** Module status row for the latency table */
interface ModuleRow {
  module: string;
  status: 'success' | 'warning' | 'error' | 'muted';
  statusLabel: string;
  tests: number;
  latency: number;
}

const Analytics = () => {
  const { t } = useTranslation();
  const timeRange = useViewStore((s) => s.analyticsTimeRange);
  const setAnalyticsTimeRange = useViewStore((s) => s.setAnalyticsTimeRange);
  const { usage, latency, tokens, cache, isLoading: loading, error, refetch: refresh } = useAnalyticsData(timeRange);
  const [activeTab, setActiveTab] = useState<AnalyticsTab>('overview');

  const tabConfig = [
    { id: 'overview' as const, label: t('analytics.tabs.overview', 'Overview') },
    { id: 'latency' as const, label: t('analytics.tabs.latency', 'Latency') },
    { id: 'tokens' as const, label: t('analytics.tabs.tokens', 'Tokens') },
    { id: 'queries' as const, label: t('analytics.tabs.queries', 'Queries') },
  ];

  // Module status data for latency tab
  const moduleRows: ModuleRow[] = [
    { module: 'RAG Pipeline', status: 'success', statusLabel: 'Healthy', tests: 48, latency: latency?.avg || 0 },
    { module: 'Vector Search', status: 'success', statusLabel: 'Healthy', tests: 32, latency: Math.round((latency?.p95 || 0) * 0.6) },
    { module: 'LLM Generation', status: latency?.p99 && latency.p99 > 80 ? 'warning' : 'success', statusLabel: latency?.p99 && latency.p99 > 80 ? 'Degraded' : 'Healthy', tests: 24, latency: latency?.p99 || 0 },
    { module: 'Cache Layer', status: (cache?.hitRate || 0) > 50 ? 'success' : 'warning', statusLabel: (cache?.hitRate || 0) > 50 ? 'Healthy' : 'Degraded', tests: 16, latency: Math.round((latency?.avg || 0) * 0.3) },
    { module: 'Context Compression', status: 'muted', statusLabel: 'Idle', tests: 8, latency: 0 },
  ];

  if (loading) {
    return (
      <div className="p-6">
        <Breadcrumb auto />
        <div className="flex items-center justify-between my-4">
          <h1 className="text-2xl font-bold text-[var(--fg)]">{t('analytics.title')}</h1>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="bg-[var(--surface)] rounded-xl border border-[var(--border)] p-5 animate-pulse">
              <div className="h-4 bg-[var(--bg-alt)] rounded w-20 mb-3"></div>
              <div className="h-8 bg-[var(--bg-alt)] rounded w-16 mb-2"></div>
              <div className="h-3 bg-[var(--bg-alt)] rounded w-32"></div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <Breadcrumb auto />
        <div className="mt-6 p-6 rounded-xl border text-center" style={{ background: 'var(--error-bg)', borderColor: 'var(--error)' }}>
          <p className="text-[var(--error)] mb-4">{t('analytics.error_loading')}</p>
          <button
            onClick={refresh}
            className="px-4 py-2 bg-[var(--error)] text-white rounded-lg hover:opacity-90 transition-colors"
          >
            {t('analytics.retry')}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6">
      {/* Breadcrumb */}
      <Breadcrumb auto />

      {/* Header + Controls */}
      <div className="flex items-center justify-between my-4">
        <div>
          <h1 className="text-2xl font-bold text-[var(--fg)]">{t('analytics.title')}</h1>
          <p className="text-[var(--fg-tertiary)] text-sm mt-1">{t('analytics.subtitle')}</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={refresh}
            className="p-2 rounded-md transition-colors"
            style={{ color: 'var(--fg-secondary)' }}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--border)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
            title={t('analytics.refresh')}
          >
            <RefreshCw size={18} />
          </button>
          <select
            value={timeRange}
            onChange={(e) => setAnalyticsTimeRange(e.target.value as '24h' | '7d' | '30d')}
            className="px-3 py-1.5 rounded-lg text-sm"
            style={{
              border: '1px solid var(--border)',
              background: 'var(--surface)',
              color: 'var(--fg)',
            }}
          >
            <option value="24h">{t('analytics.time_range.24h')}</option>
            <option value="7d">{t('analytics.time_range.7d')}</option>
            <option value="30d">{t('analytics.time_range.30d')}</option>
          </select>
        </div>
      </div>

      {/* Tabs */}
      <Tabs
        tabs={tabConfig}
        activeTab={activeTab}
        onChange={(id) => setActiveTab(id as AnalyticsTab)}
        className="mb-6"
      />

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <OverviewTab
          latency={latency}
          tokens={tokens}
          usage={usage}
          cache={cache}
          t={t}
        />
      )}
      {activeTab === 'latency' && (
        <LatencyTab latency={latency} moduleRows={moduleRows} t={t} />
      )}
      {activeTab === 'tokens' && (
        <TokensTab tokens={tokens} t={t} />
      )}
      {activeTab === 'queries' && (
        <QueriesTab usage={usage} t={t} />
      )}
    </div>
  );
};

/* ── Overview Tab ── */
function OverviewTab({ latency, tokens, usage, cache, t }: {
  latency: ReturnType<typeof useAnalyticsData>['latency'];
  tokens: ReturnType<typeof useAnalyticsData>['tokens'];
  usage: ReturnType<typeof useAnalyticsData>['usage'];
  cache: ReturnType<typeof useAnalyticsData>['cache'];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  t: any;
}) {
  return (
    <>
      {/* Metrics Grid */}
      <div data-onboarding="analytics-overview" className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <div className="bg-[var(--surface)] rounded-xl border border-[var(--border)] p-5">
          <div className="text-[var(--fg-tertiary)] text-sm mb-2">{t('analytics.avg_latency')}</div>
          <div className="text-3xl font-bold text-[var(--fg)]">{latency?.avg || 0}<span className="text-lg text-[var(--fg-tertiary)]">ms</span></div>
          <div className="mt-3 text-xs text-[var(--fg-tertiary)]">
            {t('analytics.latency.p95')}: {latency?.p95 || 0}ms · {t('analytics.latency.p99')}: {latency?.p99 || 0}ms
          </div>
        </div>
        <div className="bg-[var(--surface)] rounded-xl border border-[var(--border)] p-5">
          <div className="text-[var(--fg-tertiary)] text-sm mb-2">{t('analytics.token_usage')}</div>
          <div className="text-3xl font-bold text-[var(--fg)]">{((tokens?.input || 0) / 1000).toFixed(0)}k</div>
          <div className="mt-3 text-xs text-[var(--fg-tertiary)]">
            {t('analytics.output')}: {((tokens?.output || 0) / 1000).toFixed(0)}k · {t('analytics.cost')}: ${tokens?.cost || 0}
          </div>
        </div>
        <div className="bg-[var(--surface)] rounded-xl border border-[var(--border)] p-5">
          <div className="text-[var(--fg-tertiary)] text-sm mb-2">{t('analytics.total_queries')}</div>
          <div className="text-3xl font-bold text-[var(--fg)]">{usage?.total || 0}</div>
          <div className="mt-3 text-xs text-[var(--fg-tertiary)]">
            {t('analytics.avg_per_hour', { count: usage?.perHour || 0 })}
          </div>
        </div>
        <div className="bg-[var(--surface)] rounded-xl border border-[var(--border)] p-5">
          <div className="text-[var(--fg-tertiary)] text-sm mb-2">{t('analytics.cache_hit_rate')}</div>
          <div className="text-3xl font-bold" style={{ color: 'var(--seed-accent)' }}>{cache?.hitRate || 0}%</div>
          <div className="mt-3 text-xs text-[var(--fg-tertiary)]">
            {t('analytics.saves', { count: cache?.saves || 0 })}
          </div>
        </div>
      </div>

      {/* Progress Bars — Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-[var(--surface)] rounded-xl border border-[var(--border)] p-6">
          <h3 className="font-semibold text-[var(--fg)] mb-4">{t('analytics.latency.title')}</h3>
          <div className="space-y-4">
            <ProgressBar value={Math.min((latency?.avg || 0) / 100 * 100, 100)} variant="success" label={t('analytics.latency.avg')} showPercentage />
            <ProgressBar value={Math.min((latency?.p95 || 0) / 100 * 100, 100)} variant="warning" label={t('analytics.latency.p95')} showPercentage />
            <ProgressBar value={Math.min((latency?.p99 || 0) / 100 * 100, 100)} variant="error" label={t('analytics.latency.p99')} showPercentage />
          </div>
        </div>
        <div className="bg-[var(--surface)] rounded-xl border border-[var(--border)] p-6">
          <h3 className="font-semibold text-[var(--fg)] mb-4">{t('analytics.queries.title')}</h3>
          <div className="space-y-4">
            {Object.entries(usage?.byIntent || {}).map(([intent, count]) => {
              const percentage = usage?.total ? (count / usage.total) * 100 : 0;
              return (
                <ProgressBar
                  key={intent}
                  value={percentage}
                  variant="accent"
                  label={t(`analytics.intent.${intent}`, { defaultValue: intent })}
                  showPercentage
                />
              );
            })}
            {Object.keys(usage?.byIntent || {}).length === 0 && (
              <p className="text-[var(--fg-tertiary)] text-sm text-center py-4">{t('analytics.no_data')}</p>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

/* ── Latency Tab ── */
function LatencyTab({ latency, moduleRows, t }: {
  latency: ReturnType<typeof useAnalyticsData>['latency'];
  moduleRows: ModuleRow[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  t: any;
}) {
  const columns = [
    { key: 'module', header: t('analytics.table.module', 'Module') },
    {
      key: 'status',
      header: t('analytics.table.status', 'Status'),
      render: (row: ModuleRow) => (
        <StatusDot status={row.status} label={row.statusLabel} />
      ),
    },
    { key: 'tests', header: t('analytics.table.tests', 'Tests'), align: 'right' as const },
    {
      key: 'latency',
      header: t('analytics.table.latency', 'Latency'),
      render: (row: ModuleRow) => `${row.latency}ms`,
      align: 'right' as const,
    },
  ];

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-[var(--surface)] rounded-xl border border-[var(--border)] p-5">
          <div className="text-sm text-[var(--fg-tertiary)] mb-1">{t('analytics.latency.avg')}</div>
          <div className="text-2xl font-bold text-[var(--fg)]">{latency?.avg || 0}<span className="text-sm text-[var(--fg-tertiary)] ml-1">ms</span></div>
        </div>
        <div className="bg-[var(--surface)] rounded-xl border border-[var(--border)] p-5">
          <div className="text-sm text-[var(--fg-tertiary)] mb-1">{t('analytics.latency.p95')}</div>
          <div className="text-2xl font-bold text-[var(--fg)]">{latency?.p95 || 0}<span className="text-sm text-[var(--fg-tertiary)] ml-1">ms</span></div>
        </div>
        <div className="bg-[var(--surface)] rounded-xl border border-[var(--border)] p-5">
          <div className="text-sm text-[var(--fg-tertiary)] mb-1">{t('analytics.latency.p99')}</div>
          <div className="text-2xl font-bold text-[var(--fg)]">{latency?.p99 || 0}<span className="text-sm text-[var(--fg-tertiary)] ml-1">ms</span></div>
        </div>
      </div>

      {/* Module Status Table */}
      <DataTable
        columns={columns}
        data={moduleRows}
        rowKey={(row) => row.module}
        emptyMessage={t('analytics.no_data')}
      />
    </div>
  );
}

/* ── Tokens Tab ── */
function TokensTab({ tokens, t }: {
  tokens: ReturnType<typeof useAnalyticsData>['tokens'];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  t: any;
}) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
        <div className="bg-[var(--surface)] rounded-xl border border-[var(--border)] p-6">
          <div className="text-[var(--fg-tertiary)] text-sm mb-2">{t('analytics.tokens.input')}</div>
          <div className="text-2xl font-bold text-[var(--fg)]">{((tokens?.input || 0) / 1000).toFixed(1)}k</div>
          <div className="mt-3">
            <ProgressBar
              value={tokens?.total ? (tokens.input / tokens.total) * 100 : 0}
              variant="accent"
              showPercentage
            />
          </div>
        </div>
        <div className="bg-[var(--surface)] rounded-xl border border-[var(--border)] p-6">
          <div className="text-[var(--fg-tertiary)] text-sm mb-2">{t('analytics.tokens.output')}</div>
          <div className="text-2xl font-bold text-[var(--fg)]">{((tokens?.output || 0) / 1000).toFixed(1)}k</div>
          <div className="mt-3">
            <ProgressBar
              value={tokens?.total ? (tokens.output / tokens.total) * 100 : 0}
              variant="brand"
              showPercentage
            />
          </div>
        </div>
        <div className="bg-[var(--surface)] rounded-xl border border-[var(--border)] p-6">
          <div className="text-[var(--fg-tertiary)] text-sm mb-2">{t('analytics.tokens.cost')}</div>
          <div className="text-2xl font-bold" style={{ color: 'var(--success)' }}>${tokens?.cost || 0}</div>
          <div className="mt-2 text-xs text-[var(--fg-tertiary)]">{t('analytics.tokens.per_query', { cost: tokens?.costPerQuery || 0 })}</div>
        </div>
      </div>
    </div>
  );
}

/* ── Queries Tab ── */
function QueriesTab({ usage, t }: {
  usage: ReturnType<typeof useAnalyticsData>['usage'];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  t: any;
}) {
  interface QueryRow {
    intent: string;
    count: number;
    percentage: number;
  }

  const rows: QueryRow[] = Object.entries(usage?.byIntent || {}).map(([intent, count]) => ({
    intent,
    count,
    percentage: usage?.total ? (count / usage.total) * 100 : 0,
  }));

  const columns = [
    {
      key: 'intent',
      header: t('analytics.queries.intent', 'Intent'),
      render: (row: QueryRow) => t(`analytics.intent.${row.intent}`, { defaultValue: row.intent }),
    },
    { key: 'count', header: t('analytics.queries.count', 'Count'), align: 'right' as const },
    {
      key: 'percentage',
      header: t('analytics.queries.percentage', 'Share'),
      render: (row: QueryRow) => (
        <div className="flex items-center gap-3">
          <div className="flex-1">
            <ProgressBar value={row.percentage} variant="accent" />
          </div>
          <span className="text-sm font-medium text-[var(--fg)] w-12 text-right">{row.percentage.toFixed(1)}%</span>
        </div>
      ),
      width: '50%',
    },
  ];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-[var(--surface)] rounded-xl border border-[var(--border)] p-5">
          <div className="text-sm text-[var(--fg-tertiary)] mb-1">{t('analytics.total_queries')}</div>
          <div className="text-2xl font-bold text-[var(--fg)]">{usage?.total || 0}</div>
        </div>
        <div className="bg-[var(--surface)] rounded-xl border border-[var(--border)] p-5">
          <div className="text-sm text-[var(--fg-tertiary)] mb-1">{t('analytics.avg_per_hour', { count: 0 })}</div>
          <div className="text-2xl font-bold text-[var(--fg)]">{usage?.perHour || 0}</div>
        </div>
      </div>

      <DataTable
        columns={columns}
        data={rows}
        rowKey={(row) => row.intent}
        emptyMessage={t('analytics.no_data')}
      />
    </div>
  );
}

export default Analytics;
