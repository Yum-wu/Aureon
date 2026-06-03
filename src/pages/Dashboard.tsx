import { useTranslation } from 'react-i18next';
import { useDashboardStats } from '../hooks/useDashboardStats';
import { useSystemHealth } from '../hooks/useSystemHealth';
import { useBenchmark } from '../hooks/useBenchmark';
import { MetricGrid } from '../components/dashboard/MetricGrid';
import { QueryVolumeChart } from '../components/dashboard/QueryVolumeChart';
import { RecentQueries } from '../components/dashboard/RecentQueries';
import { Card } from '../components/ui/Card';

function LoadingSkeleton() {
  return (
    <div data-testid="dashboard-loading" className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-6 animate-pulse">
            <div className="h-3 bg-[var(--bg-tertiary)] rounded w-20 mb-4" />
            <div className="h-8 bg-[var(--bg-tertiary)] rounded w-16" />
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-6 animate-pulse h-64" />
        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-6 animate-pulse h-64" />
      </div>
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center justify-center py-16">
      <p className="text-[var(--error)] text-lg mb-2">{t('dashboard.error_loading')}</p>
      <p className="text-[var(--text-tertiary)] text-sm mb-4">{message}</p>
      <button
        onClick={onRetry}
        className="px-4 py-2 bg-[var(--accent)] text-white rounded-lg hover:bg-[var(--accent-hover)] transition-colors text-sm font-medium"
      >
        {t('dashboard.retry')}
      </button>
    </div>
  );
}

function StatusDot({ active }: { active: boolean }) {
  return (
    <span className="relative flex h-2 w-2">
      {active && (
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
      )}
      <span className={`relative inline-flex rounded-full h-2 w-2 ${active ? 'bg-emerald-400' : 'bg-red-400'}`} />
    </span>
  );
}

export function Dashboard() {
  const { t } = useTranslation();
  const { stats, recentQueries, queryVolume, loading, error, refetch } = useDashboardStats();
  useSystemHealth();
  const { data: benchmark } = useBenchmark();

  const findMetric = (pat: string) =>
    benchmark?.metrics?.find((m: { label: string; value: string | number }) => m.label.includes(pat))?.value ?? null;
  const recallVal = findMetric("Recall@3 (Hybrid)");
  const latencyVal = findMetric("Retrieval Latency");

  const metrics = stats
    ? [
        { label: t('dashboard.total_queries'), value: stats.query_count_24h },
        { label: t('dashboard.avg_latency'), value: stats.avg_retrieval_latency_ms, suffix: 'ms' },
        { label: t('dashboard.cache_hit_rate'), value: Math.round(stats.cache_hit_rate * 100), suffix: '%' },
        { label: t('dashboard.indexed_docs'), value: stats.total_indexed_docs },
      ]
    : [];

  return (
    <div className="min-h-screen bg-[var(--bg-primary)]">
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex items-end justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-[var(--text-primary)] tracking-tight">
              {t('dashboard.title')}
            </h1>
            <p className="text-sm text-[var(--text-tertiary)] mt-1">
              {t('dashboard.subtitle')}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {recallVal && (
              <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                <StatusDot active={true} />
                Recall {String(recallVal)}
              </span>
            )}
            {latencyVal && (
              <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
                <StatusDot active={true} />
                {String(latencyVal)}
              </span>
            )}
          </div>
        </div>

        {loading && <LoadingSkeleton />}

        {error && !loading && (
          <ErrorState message={error} onRetry={refetch} />
        )}

        {!loading && !error && stats && (
          <div className="space-y-4">
            {/* Metrics Row */}
            <MetricGrid metrics={metrics} columns={4} />

            {/* Charts Row */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <QueryVolumeChart data={queryVolume} />
              <RecentQueries queries={recentQueries} />
            </div>

            {/* System Health */}
            <Card>
              <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">
                {t('dashboard.system_health')}
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {[
                  { name: t('dashboard.api_server'), status: t('dashboard.healthy') },
                  { name: t('dashboard.database'), status: t('dashboard.connected') },
                  { name: t('dashboard.cache'), status: t('dashboard.active') },
                ].map((item) => (
                  <div key={item.name} className="flex items-center gap-3 px-4 py-3 rounded-lg bg-white/[0.02] border border-[var(--border-subtle)]">
                    <StatusDot active={true} />
                    <div>
                      <p className="text-sm font-medium text-[var(--text-primary)]">{item.name}</p>
                      <p className="text-xs text-[var(--text-tertiary)]">{item.status}</p>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
