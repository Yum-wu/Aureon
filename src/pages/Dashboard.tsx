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
    <div data-testid="dashboard-loading" className="space-y-8">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-6 animate-pulse">
            <div className="h-4 bg-[var(--bg-tertiary)] rounded w-24 mb-3" />
            <div className="h-10 bg-[var(--bg-tertiary)] rounded w-20" />
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-6 animate-pulse h-72" />
        <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-6 animate-pulse h-72" />
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
        className="px-4 py-2 bg-[var(--accent)] text-white rounded-lg hover:opacity-90 transition-opacity"
      >
        {t('dashboard.retry')}
      </button>
    </div>
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
      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="mb-8">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold mb-2">{t('dashboard.title')}</h1>
              <p className="text-[var(--text-secondary)]">
                {t('dashboard.subtitle')}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {recallVal && (
                <span className="text-xs px-2.5 py-1 rounded-full bg-green-100 text-green-700 font-medium">{String(recallVal)}</span>
              )}
              {latencyVal && (
                <span className="text-xs px-2.5 py-1 rounded-full bg-blue-100 text-blue-700 font-medium">{String(latencyVal)}</span>
              )}
            </div>
          </div>
        </div>

        {loading && <LoadingSkeleton />}

        {error && !loading && (
          <ErrorState message={error} onRetry={refetch} />
        )}

        {!loading && !error && stats && (
          <div className="space-y-8">
            <MetricGrid metrics={metrics} columns={4} />

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              <QueryVolumeChart data={queryVolume} />
              <RecentQueries queries={recentQueries} />
            </div>

            <Card>
              <h3 className="text-lg font-semibold mb-4">{t('dashboard.system_health')}</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="flex items-center gap-3 p-3 bg-[var(--bg-tertiary)] rounded-lg">
                  <div className="w-3 h-3 rounded-full bg-[var(--success)]" />
                  <div>
                    <p className="text-sm font-medium">{t('dashboard.api_server')}</p>
                    <p className="text-xs text-[var(--text-tertiary)]">{t('dashboard.healthy')}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 p-3 bg-[var(--bg-tertiary)] rounded-lg">
                  <div className="w-3 h-3 rounded-full bg-[var(--success)]" />
                  <div>
                    <p className="text-sm font-medium">{t('dashboard.database')}</p>
                    <p className="text-xs text-[var(--text-tertiary)]">{t('dashboard.connected')}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 p-3 bg-[var(--bg-tertiary)] rounded-lg">
                  <div className="w-3 h-3 rounded-full bg-[var(--success)]" />
                  <div>
                    <p className="text-sm font-medium">{t('dashboard.cache')}</p>
                    <p className="text-xs text-[var(--text-tertiary)]">{t('dashboard.active')}</p>
                  </div>
                </div>
              </div>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
