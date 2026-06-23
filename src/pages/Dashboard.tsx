import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useDashboardData } from '../hooks/useDashboardData';
import { useSystemHealthQuery } from '../hooks/useSystemHealthQuery';
import { useRealtimeMetrics } from '../hooks/useRealtimeMetrics';
import { useLatencyHistory } from '../hooks/useLatencyHistory';
import { useCacheHistory } from '../hooks/useCacheHistory';
import { useMemo, useState, useEffect } from 'react';
import { useViewStore } from '../stores/useViewStore';
import { useAuth } from '../hooks/AuthContext';
import { useDebouncedLocalStorage } from '../hooks/useDebouncedLocalStorage';
import { Card } from '../components/ui/Card';
import { AlertTriangle, LogIn, Sparkles } from 'lucide-react';
import { Breadcrumb } from '../components/ui/Breadcrumb';
import { StatusDot } from '../components/ui/StatusDot';
import { DashboardHeader } from '../components/dashboard/DashboardHeader';
import { DashboardStatsGrid } from '../components/dashboard/DashboardStatsGrid';
import { DashboardCharts } from '../components/dashboard/DashboardCharts';

/* ── Types ── */

interface AlertMessage {
  id: string;
  severity: 'critical' | 'warning' | 'info';
  message: string;
  timestamp: string;
}

interface ServiceHealth {
  name: string;
  healthy: boolean;
  responseTime: number;
}

/* ── Inline sub-components ── */

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
  const navigate = useNavigate();
  const { login } = useAuth();
  const [isDemoLoading, setIsDemoLoading] = useState(false);

  const isAuthError = /401|403|unauthor|forbidden|认证|权限|未登录|auth/i.test(message);

  const handleDemoLogin = async () => {
    setIsDemoLoading(true);
    try {
      const DEMO_API_KEY = '7c249a3dd6b893e04ac5a42ef338f62c73d26bcb0b8ec6655ed6aedf6f07e129';
      const success = await login(DEMO_API_KEY);
      if (success) {
        window.location.reload();
      }
    } finally {
      setIsDemoLoading(false);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center py-16">
      {isAuthError ? (
        <>
          <AlertTriangle size={40} className="text-[var(--warning)] mb-4" />
          <p className="text-[var(--text-primary)] text-lg font-semibold mb-2">
            {t('dashboard.auth_failed_title', '认证已失效')}
          </p>
          <p className="text-[var(--text-tertiary)] text-sm mb-6 max-w-md text-center">
            {t('dashboard.auth_failed_desc', 'API Key 或登录凭证无效,请使用演示账号登录后查看数据。')}
          </p>
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/login')}
              className="px-4 py-2 bg-[var(--accent)] text-white rounded-lg hover:bg-[var(--accent-hover)] transition-colors text-sm font-medium inline-flex items-center gap-2"
            >
              <LogIn size={16} /> {t('dashboard.go_login', '去登录')}
            </button>
            <button
              onClick={handleDemoLogin}
              disabled={isDemoLoading}
              className="px-4 py-2 bg-[var(--accent-soft)] border border-[var(--accent)]/30 text-[var(--accent)] rounded-lg hover:bg-[var(--accent)]/20 transition-colors text-sm font-medium inline-flex items-center gap-2 disabled:opacity-50"
            >
              <Sparkles size={16} /> {isDemoLoading ? t('login.logging_in') : t('login.demo_account')}
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="text-[var(--error)] text-lg mb-2">{t('dashboard.error_loading')}</p>
          <p className="text-[var(--text-tertiary)] text-sm mb-4">{message}</p>
          <button
            onClick={onRetry}
            className="px-4 py-2 bg-[var(--accent)] text-white rounded-lg hover:bg-[var(--accent-hover)] transition-colors text-sm font-medium"
          >
            {t('dashboard.retry')}
          </button>
        </>
      )}
    </div>
  );
}

function HealthServiceCard({ service }: { service: ServiceHealth }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-3 px-4 py-3 rounded-lg border" style={{ background: 'var(--surface-inset)', borderColor: 'var(--border-subtle)' }}>
      <StatusDot status={service.healthy ? 'success' : 'error'} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-[var(--fg)]">{service.name}</p>
        <p className="text-xs text-[var(--fg-tertiary)]">
          {service.healthy ? `${service.responseTime}ms` : '—'}
        </p>
      </div>
      <span className={`text-xs font-medium ${service.healthy ? 'text-[var(--success)]' : 'text-[var(--error)]'}`} aria-label={service.healthy ? t('dashboard.health.healthy') : t('dashboard.health.unhealthy')}>
        {service.healthy ? t('dashboard.health.healthy') : t('dashboard.health.unhealthy')}
      </span>
    </div>
  );
}

function AlertRow({ alert }: { alert: AlertMessage }) {
  const severityStyles: Record<string, string> = {
    critical: 'text-red-400 bg-red-500/10 border-red-500/20',
    warning: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/20',
    info: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
  };
  const severityIcons: Record<string, string> = {
    critical: '●',
    warning: '●',
    info: '●',
  };

  return (
    <div className={`flex items-center gap-3 px-4 py-3 rounded-lg border ${severityStyles[alert.severity] || severityStyles.info}`}>
      <span className="text-sm">{severityIcons[alert.severity] || '●'}</span>
      <p className="flex-1 text-sm text-[var(--text-primary)]">{alert.message}</p>
      <span className="text-xs text-[var(--text-tertiary)] shrink-0">
        {new Date(alert.timestamp).toLocaleTimeString()}
      </span>
    </div>
  );
}

/* ── Main container ── */

export function Dashboard() {
  const { t } = useTranslation();
  const { stats, queryVolume, isLoading: loading, isLoadingVolume, error, refetch } = useDashboardData();
  const { data: healthData } = useSystemHealthQuery();

  const {
    metrics: rtMetrics,
    alerts: rtAlerts,
    isConnected: rtIsConnected,
    connectionState: rtConnectionState,
    lastUpdated: rtLastUpdated,
  } = useRealtimeMetrics();

  const latencyHistory = useLatencyHistory();
  const cacheHistory = useCacheHistory();

  const timeRange = useViewStore((s) => s.dashboardTimeRange);
  const setDashboardTimeRange = useViewStore((s) => s.setDashboardTimeRange);
  const hasRealtimeData = rtLastUpdated !== null;

  // Debounced localStorage for metrics, pipeline, and volume
  const [cachedMetrics, setCachedMetrics] = useDebouncedLocalStorage<Record<string, number> | null>('aureon:metrics:last', null, 2000);
  const [cachedPipeline, setCachedPipeline] = useDebouncedLocalStorage<Record<string, number> | null>('aureon:pipeline:last', null, 2000);
  const [cachedVolume, setCachedVolume] = useDebouncedLocalStorage<{ date: string; count: number }[] | null>('aureon:volume:last', null, 2000);

  // Base layer: HTTP polling data (fallback), use cache if no stats
  const baseMetrics = useMemo(() => {
    if (stats) {
      return {
        ttft_p50: stats.avg_retrieval_latency_ms || 0,
        ttft_p95: 0,
        qps: Math.round((stats.query_count_24h || 0) / 86400 * 100) / 100,
        error_rate: 0,
        saturation: 0,
        alert_count: 0,
        latency_trend: [] as number[],
        tpot_trend: [] as number[],
        e2e_trend: [] as number[],
      };
    }
    return cachedMetrics ?? null;
  }, [stats, cachedMetrics]);

  // Enhancement layer: WebSocket realtime data (overlay only when non-zero)
  const rtHasData = hasRealtimeData && (rtMetrics.qps > 0 || rtMetrics.ttft_p50 > 0 || rtMetrics.token_usage > 0);
  const realtimeOverlay = useMemo(() => rtHasData ? {
    ttft_p50: rtMetrics.ttft_p50,
    ttft_p95: rtMetrics.ttft_p95,
    qps: rtMetrics.qps,
    error_rate: rtMetrics.error_rate * 100,
    alert_count: rtAlerts.length,
  } : null, [rtHasData, rtMetrics.ttft_p50, rtMetrics.ttft_p95, rtMetrics.qps, rtMetrics.error_rate, rtAlerts.length]);

  const metrics = useMemo(() => baseMetrics
    ? { ...baseMetrics, ...realtimeOverlay }
    : null, [baseMetrics, realtimeOverlay]);

  // Persist metrics to localStorage (debounced via hook)
  useEffect(() => {
    if (metrics && ((metrics.ttft_p50 ?? 0) > 0 || (metrics.qps ?? 0) > 0)) {
      setCachedMetrics({
        ttft_p50: metrics.ttft_p50 ?? 0,
        qps: metrics.qps ?? 0,
        error_rate: metrics.error_rate ?? 0,
        ...('saturation' in metrics ? { saturation: (metrics as Record<string, unknown>).saturation as number ?? 0 } : {}),
        alert_count: metrics.alert_count ?? 0,
      });
    }
  }, [metrics]);

  // Map hook alerts to AlertMessage format
  const alerts: AlertMessage[] = rtAlerts.map((a) => ({
    id: a.id,
    severity: a.level === 'critical' ? 'critical' as const : 'warning' as const,
    message: a.message,
    timestamp: new Date(a.timestamp).toISOString(),
  }));

  // Health services from /api/health
  const healthServices: ServiceHealth[] = healthData?.services || [
    { name: t('dashboard.health.api_server'), healthy: false, responseTime: 0 },
    { name: t('dashboard.health.index'), healthy: false, responseTime: 0 },
    { name: t('dashboard.health.tools'), healthy: false, responseTime: 0 },
  ];

  // Pipeline data with localStorage fallback
  const hasPipelineData = rtMetrics.pipeline && (rtMetrics.pipeline.retrieval_ms ?? 0) > 0;
  useEffect(() => {
    if (hasPipelineData) {
      setCachedPipeline(rtMetrics.pipeline as Record<string, number>);
    }
  }, [hasPipelineData, rtMetrics.pipeline]);
  const pipelineData = hasPipelineData ? rtMetrics.pipeline : cachedPipeline;
  const pipelineStages = pipelineData ? [
    { name: t('dashboard.pipeline.retrieval'), ms: pipelineData.retrieval_ms ?? 0, color: '#5E6AD2' },
    { name: t('dashboard.pipeline.generation'), ms: pipelineData.generation_ms ?? 0, color: '#EAB308' },
  ] : [];

  // Query volume localStorage fallback
  useEffect(() => {
    if (queryVolume && queryVolume.length > 0) {
      setCachedVolume(queryVolume);
    }
  }, [queryVolume]);
  const effectiveQueryVolume = (queryVolume && queryVolume.length > 0) ? queryVolume : (cachedVolume ?? []);

  const queryVolumeChartData = effectiveQueryVolume
    .filter((item: { date: string; count: number } | null | undefined): item is { date: string; count: number } => item != null && item.count > 0)
    .map((item: { date: string; count: number }) => ({
      label: item.date,
      value: item.count,
    }));

  // Latency trend chart data
  const latencyChartData = useMemo(() => {
    if (latencyHistory.length > 5) {
      return [
        {
          id: t('dashboard.latency.ttft'),
          data: latencyHistory.map((p, i) => ({ x: `${i}`, y: p.ttft }))
        },
      ];
    }

    if (!metrics || !('latency_trend' in metrics)) return [];
    const m = metrics as { latency_trend?: number[]; tpot_trend?: number[]; e2e_trend?: number[] };
    return [
      { id: t('dashboard.latency.ttft'), data: (m.latency_trend ?? []).filter((v: number): v is number => v != null && v > 0).map((v: number, i: number) => ({ x: `${i}`, y: v })) },
      { id: t('dashboard.latency.tpot'), data: (m.tpot_trend ?? []).filter((v: number): v is number => v != null && v > 0).map((v: number, i: number) => ({ x: `${i}`, y: v })) },
      { id: t('dashboard.latency.e2e'), data: (m.e2e_trend ?? []).filter((v: number): v is number => v != null && v > 0).map((v: number, i: number) => ({ x: `${i}`, y: v })) },
    ];
  }, [latencyHistory, metrics, t]);

  // Cache hit rate trend data
  const cacheTrendData: { id: string; data: { x: string; y: number }[] }[] = useMemo(() => {
    if (cacheHistory.length > 0) {
      return [
        {
          id: t('dashboard.charts.cache_hit_rate', '缓存命中率'),
          data: cacheHistory.map((p, i) => ({ x: `${i}`, y: p.hitRate })),
        },
      ];
    }
    if (rtMetrics.cache_hit_rate > 0) {
      return [
        {
          id: t('dashboard.charts.cache_hit_rate', '缓存命中率'),
          data: [{ x: '0', y: rtMetrics.cache_hit_rate }],
        },
      ];
    }
    return [];
  }, [cacheHistory, rtMetrics.cache_hit_rate, t]);

  return (
    <div className="min-h-screen">
      <div className="px-6 py-8">
        <Breadcrumb auto />

        <DashboardHeader
          rtIsConnected={rtIsConnected}
          rtConnectionState={rtConnectionState}
          rtLastUpdated={rtLastUpdated != null ? String(rtLastUpdated) : null}
          timeRange={timeRange}
          onTimeRangeChange={setDashboardTimeRange}
        />

        {loading && !stats && <LoadingSkeleton />}
        {error && !loading && <ErrorState message={error instanceof Error ? error.message : String(error)} onRetry={refetch} />}

        {(stats || !loading) && !error && (
          <div className="space-y-6">
            {/* Demo mode watermark */}
            {!hasRealtimeData && !stats?.query_count_24h && !loading && !error && (
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-center">
                <p className="text-sm font-medium text-amber-400">
                  <span className="inline-flex items-center gap-1"><AlertTriangle size={14} /> {t('dashboard.demo_mode')}</span>
                </p>
              </div>
            )}

            <DashboardStatsGrid metrics={metrics} alerts={alerts} />

            <DashboardCharts
              latencyChartData={latencyChartData}
              queryVolumeChartData={queryVolumeChartData}
              isLoadingVolume={isLoadingVolume}
              pipelineStages={pipelineStages}
              cacheTrendData={cacheTrendData}
            />

            {/* Health row */}
            <Card>
              <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">
                {t('dashboard.system_health')}
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {healthServices.map((service) => (
                  <HealthServiceCard key={service.name} service={service} />
                ))}
              </div>
            </Card>

            {/* Alerts row */}
            <Card>
              <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">
                {t('dashboard.alerts.title')}
              </h3>
              {alerts.length === 0 ? (
                <div className="text-center py-8">
                  <p className="text-[var(--text-tertiary)] text-sm">{t('dashboard.alerts.empty')}</p>
                </div>
              ) : (
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {alerts.map((alert) => (
                    <AlertRow key={alert.id} alert={alert} />
                  ))}
                </div>
              )}
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
