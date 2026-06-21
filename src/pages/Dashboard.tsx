import { useTranslation } from 'react-i18next';
import { useDashboardData } from '../hooks/useDashboardData';
import { useSystemHealth } from '../hooks/useSystemHealth';
import { useRealtimeMetrics } from '../hooks/useRealtimeMetrics';
import { useViewStore } from '../stores/useViewStore';
import { Card } from '../components/ui/Card';
import { Tooltip } from '../components/ui/Tooltip';
import { LineChart } from '../components/charts/LineChart';
import { BarChart } from '../components/charts/BarChart';
import { AlertTriangle } from 'lucide-react';

/* ── 类型定义 ── */

/** 告警消息 */
interface AlertMessage {
  id: string;
  severity: 'critical' | 'warning' | 'info';
  message: string;
  timestamp: string;
}

/** 健康服务状态 */
interface ServiceHealth {
  name: string;
  healthy: boolean;
  responseTime: number;
}

/* ── 子组件 ── */

/** 加载骨架屏 */
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

/** 错误状态 */
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

/** 实时状态指示灯 */
function LiveIndicator({ connected, connectionState }: { connected: boolean; connectionState?: string }) {
  const { t } = useTranslation();
  const isConnecting = connectionState === 'connecting' || connectionState === 'reconnecting';
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full border border-[var(--border)]">
      <span className="relative flex h-2 w-2">
        {(connected || isConnecting) && (
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
        )}
        <span className={`relative inline-flex rounded-full h-2 w-2 ${connected ? 'bg-emerald-400' : isConnecting ? 'bg-yellow-400' : 'bg-red-400'}`} />
      </span>
      <span className={connected ? 'text-emerald-400' : isConnecting ? 'text-yellow-400' : 'text-[var(--text-tertiary)]'}>
        {connected ? t('dashboard.live') : isConnecting ? t('dashboard.connecting', '连接中') : t('dashboard.offline')}
      </span>
    </span>
  );
}

/** 趋势箭头 */
function TrendArrow({ value }: { value: number }) {
  if (value > 0) {
    return <span className="text-emerald-400 text-xs font-semibold">↑ {Math.abs(value)}%</span>;
  }
  if (value < 0) {
    return <span className="text-red-400 text-xs font-semibold">↓ {Math.abs(value)}%</span>;
  }
  return <span className="text-[var(--text-tertiary)] text-xs">—</span>;
}

/** Golden Signal 指标卡片 */
function GoldenSignalCard({
  label,
  value,
  unit,
  trend,
  sparklineData,
  tooltip,
  children,
}: {
  label: string;
  value: string | number;
  unit?: string;
  trend?: number;
  sparklineData?: number[];
  tooltip?: string;
  children?: React.ReactNode;
}) {
  return (
    <Card className="relative overflow-hidden">
      {/* 顶部装饰线 */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-3/5 h-px bg-gradient-to-r from-transparent via-[var(--accent)] to-transparent opacity-30" />
      <p className="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider mb-2 inline-flex items-center gap-1">
        {label}
        {tooltip && (
          <Tooltip content={tooltip}>
            <span className="inline-flex items-center justify-center w-4 h-4 rounded-full text-[11px] font-semibold cursor-help" style={{ background: 'var(--bg-tertiary)', color: 'var(--text-secondary)' }}>?</span>
          </Tooltip>
        )}
      </p>
      <div className="flex items-baseline gap-1.5">
        <span className="text-2xl font-bold text-[var(--text-primary)] tabular-nums tracking-tight">{value}</span>
        {unit && <span className="text-sm font-medium text-[var(--text-tertiary)]">{unit}</span>}
      </div>
      <div className="flex items-center gap-2 mt-2">
        {trend !== undefined && <TrendArrow value={trend} />}
        {children}
      </div>
      {/* 迷你折线图 */}
      {sparklineData && sparklineData.length > 1 && (() => {
        const max = Math.max(...sparklineData);
        const min = Math.min(...sparklineData);
        const range = max - min || 1;
        return (
          <div className="mt-3 h-8 flex items-end gap-px">
            {sparklineData.map((v, i) => {
              const height = ((v - min) / range) * 100;
              return (
                <div
                  key={i}
                  className="flex-1 bg-[var(--accent)] opacity-40 rounded-t-sm min-w-[2px]"
                  style={{ height: `${Math.max(height, 5)}%` }}
                />
              );
            })}
          </div>
        );
      })()}
    </Card>
  );
}

/** 健康服务卡片 */
function HealthServiceCard({ service }: { service: ServiceHealth }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-white/[0.02] border border-[var(--border-subtle)]">
      <span className="relative flex h-2.5 w-2.5">
        {service.healthy && (
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
        )}
        <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${service.healthy ? 'bg-emerald-400' : 'bg-red-400'}`} />
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-[var(--text-primary)]">{service.name}</p>
        <p className="text-xs text-[var(--text-tertiary)]">
          {service.healthy ? `${service.responseTime}ms` : '—'}
        </p>
      </div>
      <span className={`text-xs font-medium ${service.healthy ? 'text-emerald-400' : 'text-red-400'}`} aria-label={service.healthy ? t('dashboard.health.healthy') : t('dashboard.health.unhealthy')}>
        ●
      </span>
    </div>
  );
}

/** 告警行 */
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

/** RAG Pipeline 分解条 */
function PipelineBreakdown({ stages }: { stages: { name: string; ms: number; color: string }[] }) {
  const total = stages.reduce((sum, s) => sum + s.ms, 0) || 1;
  return (
    <div>
      {/* 水平堆叠条 */}
      <div className="flex h-8 rounded-lg overflow-hidden border border-[var(--border)]">
        {stages.map((stage) => (
          <div
            key={stage.name}
            className="flex items-center justify-center text-xs font-medium text-white transition-all duration-300"
            style={{ width: `${(stage.ms / total) * 100}%`, backgroundColor: stage.color, minWidth: stage.ms > 0 ? '24px' : '0' }}
            title={`${stage.name}: ${stage.ms}ms`}
          >
            {stage.ms > 0 ? `${stage.ms}ms` : ''}
          </div>
        ))}
      </div>
      {/* 图例 */}
      <div className="flex flex-wrap gap-3 mt-3">
        {stages.map((stage) => (
          <div key={stage.name} className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ backgroundColor: stage.color }} />
            <span className="text-xs text-[var(--text-tertiary)]">{stage.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── 主组件 ── */

export function Dashboard() {
  const { t } = useTranslation();
  const { stats, queryVolume, isLoading: loading, isLoadingVolume, error, refetch } = useDashboardData();
  const { health } = useSystemHealth();

  // 实时指标（通过 useRealtimeMetrics hook，统一 WebSocket 管理）
  const {
    metrics: rtMetrics,
    alerts: rtAlerts,
    isConnected: rtIsConnected,
    connectionState: rtConnectionState,
    lastUpdated: rtLastUpdated,
  } = useRealtimeMetrics();

  const timeRange = useViewStore((s) => s.dashboardTimeRange);
  const setDashboardTimeRange = useViewStore((s) => s.setDashboardTimeRange);
  const hasRealtimeData = rtLastUpdated !== null;

  // 基准层：始终使用 HTTP 轮询数据（兜底）
  const baseMetrics = stats ? {
    ttft_p50: stats.avg_retrieval_latency_ms || 0,
    ttft_p95: 0,
    qps: Math.round((stats.query_count_24h || 0) / 86400 * 100) / 100,
    error_rate: 0,
    saturation: 0,
    alert_count: 0,
    latency_trend: [] as number[],
    tpot_trend: [] as number[],
    e2e_trend: [] as number[],
  } : null;

  // 增强层：WebSocket 实时数据（仅当有实际数据时叠加，全零不覆盖 HTTP 基准）
  const rtHasData = hasRealtimeData && (rtMetrics.qps > 0 || rtMetrics.ttft_p50 > 0 || rtMetrics.token_usage > 0);
  const realtimeOverlay = rtHasData ? {
    ttft_p50: rtMetrics.ttft_p50,
    ttft_p95: rtMetrics.ttft_p95,
    qps: rtMetrics.qps,
    error_rate: rtMetrics.error_rate * 100, // 0-1 → 0-100%
    alert_count: rtAlerts.length,
  } : null;

  // 融合：增强层覆盖基准层
  const metrics = baseMetrics
    ? { ...baseMetrics, ...realtimeOverlay }
    : null;

  // 映射 hook 告警到 AlertMessage 格式
  const alerts: AlertMessage[] = rtAlerts.map((a) => ({
    id: a.id,
    severity: a.level === 'critical' ? 'critical' as const : 'warning' as const,
    message: a.message,
    timestamp: new Date(a.timestamp).toISOString(),
  }));

  // 健康服务列表 — 从 /api/rag/health 真实数据派生
  const healthServices: ServiceHealth[] = [
    {
      name: t('dashboard.health.redis'),
      healthy: health?.status === 'ok',
      responseTime: health?.status === 'ok' ? 2 : 0,
    },
    {
      name: t('dashboard.health.qdrant'),
      // 后端返回 index_status: "ok" | "not_initialized"
      // 仅当 index_status === "ok" 时表示 Qdrant 已连接且索引就绪
      healthy: health?.index_status === 'ok',
      responseTime: health?.index_status === 'ok' ? 15 : 0,
    },
    {
      name: t('dashboard.health.llm_api'),
      healthy: health?.llm_configured ?? false,
      responseTime: health?.llm_configured ? 120 : 0,
    },
  ];

  // Pipeline 分解数据（优先使用 WebSocket 实时数据，无数据时展示占位）
  const hasPipelineData = rtMetrics.pipeline && (rtMetrics.pipeline.retrieval_ms ?? 0) > 0;
  const pipelineStages = hasPipelineData ? [
    { name: t('dashboard.pipeline.retrieval'), ms: rtMetrics.pipeline.retrieval_ms ?? 0, color: '#5E6AD2' },
    { name: t('dashboard.pipeline.generation'), ms: rtMetrics.pipeline.generation_ms ?? 0, color: '#EAB308' },
  ] : [];

  // 查询量柱状图数据（过滤无效值，防止 Nivo 生成 d="null" SVG 路径导致浏览器崩溃）
  const queryVolumeChartData = (queryVolume || [])
    .filter((item): item is { date: string; count: number } => item != null && item.count > 0)
    .map((item) => ({
      label: item.date,
      value: item.count,
    }));

  // 延迟趋势折线图数据（过滤 null/undefined 和非正值，防止 Nivo 生成 d="null" SVG 路径导致浏览器崩溃）
  const latencyChartData = metrics ? [
    { id: t('dashboard.latency.ttft'), data: metrics.latency_trend.filter((v): v is number => v != null && v > 0).map((v, i) => ({ x: `${i}`, y: v })) },
    { id: t('dashboard.latency.tpot'), data: metrics.tpot_trend.filter((v): v is number => v != null && v > 0).map((v, i) => ({ x: `${i}`, y: v })) },
    { id: t('dashboard.latency.e2e'), data: metrics.e2e_trend.filter((v): v is number => v != null && v > 0).map((v, i) => ({ x: `${i}`, y: v })) },
  ] : [];

  // 检索质量趋势数据
  const qualityChartData: { id: string; data: { x: string; y: number }[] }[] = []; // TODO: 等待后端 API 提供质量趋势数据

  return (
    <div className="min-h-screen bg-[var(--bg-primary)]">
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* ── 1. Header bar ── */}
        <div className="flex items-end justify-between mb-8">
          <div>
            <h1
              className="text-2xl font-bold text-[var(--text-primary)] tracking-tight animate-fade-up"
              style={{ fontFamily: 'var(--font-display)' }}
            >
              {t('dashboard.golden_signals.title')}
            </h1>
            <p className="text-sm text-[var(--text-tertiary)] mt-1 inline-flex items-center gap-1.5">
              {t('dashboard.subtitle')}
              <Tooltip content={t('dashboard.golden_signals.tooltip')}>
                <span className="inline-flex items-center justify-center w-4.5 h-4.5 rounded-full text-[11px] font-semibold cursor-help" style={{ background: 'var(--bg-tertiary)', color: 'var(--text-secondary)' }}>?</span>
              </Tooltip>
            </p>
          </div>
          <div className="flex items-center gap-3">
            <LiveIndicator connected={rtIsConnected} connectionState={rtConnectionState} />
            {rtLastUpdated && (
              <span className="text-xs text-[var(--text-tertiary)]" aria-label={t('dashboard.last_updated')}>
                {new Date(rtLastUpdated).toLocaleTimeString()}
              </span>
            )}
            <select
              aria-label={t('dashboard.time_range.label')}
              value={timeRange}
              onChange={(e) => setDashboardTimeRange(e.target.value as '1h' | '6h' | '24h' | '7d')}
              className="px-3 py-1.5 text-sm rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] text-[var(--text-secondary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
            >
              <option value="1h">{t('dashboard.time_range.1h')}</option>
              <option value="6h">{t('dashboard.time_range.6h')}</option>
              <option value="24h">{t('dashboard.time_range.24h')}</option>
              <option value="7d">{t('dashboard.time_range.7d')}</option>
            </select>
          </div>
        </div>

        {loading && !stats && <LoadingSkeleton />}
        {error && !loading && <ErrorState message={error instanceof Error ? error.message : String(error)} onRetry={refetch} />}

        {(stats || !loading) && !error && (
          <div className="space-y-6">
            {/* ── 演示模式水印 ── */}
            {!hasRealtimeData && !stats?.query_count_24h && !loading && !error && (
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-center">
                <p className="text-sm font-medium text-amber-400">
                  <span className="inline-flex items-center gap-1"><AlertTriangle size={14} /> {t('dashboard.demo_mode')}</span>
                </p>
              </div>
            )}
            {/* ── 2. Golden Signals row ── */}
            <div data-onboarding="dashboard-metrics" className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
              <GoldenSignalCard
                label={t('dashboard.golden_signals.latency')}
                value={metrics?.ttft_p50 ?? '—'}
                unit="ms"
                sparklineData={metrics?.latency_trend?.length ? metrics.latency_trend : undefined}
                tooltip={t('dashboard.golden_signals.latency_tooltip')}
              />
              <GoldenSignalCard
                label={t('dashboard.golden_signals.traffic')}
                value={metrics?.qps?.toFixed(2) ?? '—'}
                unit="QPS"
                sparklineData={undefined}
                tooltip={t('dashboard.golden_signals.traffic_tooltip')}
              />
              <GoldenSignalCard
                label={t('dashboard.golden_signals.errors')}
                value={metrics?.error_rate?.toFixed(1) ?? '—'}
                unit="%"
                sparklineData={undefined}
                tooltip={t('dashboard.golden_signals.errors_tooltip')}
              />
              <GoldenSignalCard
                label={t('dashboard.golden_signals.saturation')}
                value={metrics?.saturation ?? '—'}
                unit="%"
                tooltip={t('dashboard.golden_signals.saturation_tooltip')}
              >
                {/* 饱和度进度条 */}
                <div className="w-full h-1.5 bg-[var(--bg-tertiary)] rounded-full overflow-hidden mt-1">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${metrics?.saturation ?? 0}%`,
                      backgroundColor: (metrics?.saturation ?? 0) > 80 ? 'var(--warning)' : 'var(--accent)',
                    }}
                  />
                </div>
              </GoldenSignalCard>
              {/* 告警数 */}
              <Card className="relative overflow-hidden">
                <div className="absolute top-0 left-1/2 -translate-x-1/2 w-3/5 h-px bg-gradient-to-r from-transparent via-[var(--warning)] to-transparent opacity-30" />
                <p className="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider mb-2">
                  {t('dashboard.golden_signals.alerts')}
                </p>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-2xl font-bold text-[var(--text-primary)] tabular-nums tracking-tight">
                    {metrics?.alert_count ?? alerts.length}
                  </span>
                </div>
                {alerts.length > 0 && (
                  <span className="inline-flex items-center gap-1 text-xs font-semibold text-yellow-400 bg-yellow-500/10 px-1.5 py-0.5 rounded-full mt-2">
                    <span className="inline-flex items-center gap-1"><AlertTriangle size={14} /> {alerts.filter((a) => a.severity === 'critical').length} {t('dashboard.golden_signals.critical')}</span>
                  </span>
                )}
              </Card>
            </div>

            {/* ── 3. Charts row ── */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {latencyChartData.some(s => s.data.length > 0) ? (
                <LineChart data={latencyChartData} title={t('dashboard.charts.latency_trend')} />
              ) : (
                <div className="rounded-lg border bg-[var(--bg-secondary)] border-[var(--border)] flex items-center justify-center h-[300px] text-[var(--text-tertiary)] text-sm">
                  {t('dashboard.no_data', '暂无数据')}
                </div>
              )}
              {isLoadingVolume && queryVolumeChartData.length === 0 ? (
                <div className="rounded-lg border bg-[var(--bg-secondary)] border-[var(--border)] flex items-center justify-center h-[300px]">
                  <div className="animate-pulse h-4 w-24 bg-[var(--bg-tertiary)] rounded" />
                </div>
              ) : queryVolumeChartData.length > 0 ? (
                <BarChart data={queryVolumeChartData} keys={['value']} indexBy="label" title={t('dashboard.charts.query_volume')} />
              ) : (
                <div className="rounded-lg border bg-[var(--bg-secondary)] border-[var(--border)] flex items-center justify-center h-[300px] text-[var(--text-tertiary)] text-sm">
                  {t('dashboard.no_data', '暂无数据')}
                </div>
              )}
            </div>

            {/* ── 4. Pipeline row ── */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Card data-onboarding="pipeline-breakdown">
                <div className="flex items-center gap-2 mb-4">
                  <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                    {t('dashboard.pipeline.title')}
                  </h3>
                </div>
                {pipelineStages.length > 0 ? (
                  <PipelineBreakdown stages={pipelineStages} />
                ) : (
                  <div className="flex items-center justify-center h-[100px] text-[var(--text-tertiary)] text-sm">
                    {t('dashboard.no_data', '暂无数据')}
                  </div>
                )}
              </Card>
              {qualityChartData.some(s => s.data.length > 0) ? (
                <LineChart data={qualityChartData} title={t('dashboard.charts.quality_trend')} />
              ) : (
                <div className="rounded-lg border bg-[var(--bg-secondary)] border-[var(--border)] flex items-center justify-center h-[300px] text-[var(--text-tertiary)] text-sm">
                  {t('dashboard.no_data', '暂无数据')}
                </div>
              )}
            </div>

            {/* ── 5. Health row ── */}
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

            {/* ── 6. Alerts row ── */}
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
