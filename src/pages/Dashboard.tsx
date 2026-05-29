import { useDashboardStats } from '../hooks/useDashboardStats';
import { MetricGrid } from '../components/dashboard/MetricGrid';
import { QueryVolumeChart } from '../components/dashboard/QueryVolumeChart';
import { RecentQueries } from '../components/dashboard/RecentQueries';
import { Card } from '../components/ui/Card';

// QueryVolumeChart still uses mock data (no volume endpoint yet)
const queryVolume = [
  { date: '2026-05-23', count: 45 },
  { date: '2026-05-24', count: 52 },
  { date: '2026-05-25', count: 38 },
  { date: '2026-05-26', count: 61 },
  { date: '2026-05-27', count: 55 },
  { date: '2026-05-28', count: 48 },
  { date: '2026-05-29', count: 67 },
];

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
  return (
    <div className="flex flex-col items-center justify-center py-16">
      <p className="text-[var(--error)] text-lg mb-2">加载失败</p>
      <p className="text-[var(--text-tertiary)] text-sm mb-4">{message}</p>
      <button
        onClick={onRetry}
        className="px-4 py-2 bg-[var(--accent)] text-white rounded-lg hover:opacity-90 transition-opacity"
      >
        重试
      </button>
    </div>
  );
}

export function Dashboard() {
  const { stats, recentQueries, loading, error, refetch } = useDashboardStats();

  const metrics = stats
    ? [
        { label: 'Total Queries', value: stats.query_count_24h },
        { label: 'Avg Latency', value: stats.avg_retrieval_latency_ms, suffix: 'ms' },
        { label: 'Cache Hit Rate', value: Math.round(stats.cache_hit_rate * 100), suffix: '%' },
        { label: 'Indexed Docs', value: stats.total_indexed_docs },
      ]
    : [];

  return (
    <div className="min-h-screen bg-[var(--bg-primary)]">
      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">System Dashboard</h1>
          <p className="text-[var(--text-secondary)]">
            Real-time metrics and system health monitoring
          </p>
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
              <h3 className="text-lg font-semibold mb-4">System Health</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="flex items-center gap-3 p-3 bg-[var(--bg-tertiary)] rounded-lg">
                  <div className="w-3 h-3 rounded-full bg-[var(--success)]" />
                  <div>
                    <p className="text-sm font-medium">API Server</p>
                    <p className="text-xs text-[var(--text-tertiary)]">Healthy</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 p-3 bg-[var(--bg-tertiary)] rounded-lg">
                  <div className="w-3 h-3 rounded-full bg-[var(--success)]" />
                  <div>
                    <p className="text-sm font-medium">Database</p>
                    <p className="text-xs text-[var(--text-tertiary)]">Connected</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 p-3 bg-[var(--bg-tertiary)] rounded-lg">
                  <div className="w-3 h-3 rounded-full bg-[var(--success)]" />
                  <div>
                    <p className="text-sm font-medium">Cache</p>
                    <p className="text-xs text-[var(--text-tertiary)]">Active</p>
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
