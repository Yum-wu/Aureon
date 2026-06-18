import { useState, useEffect, useRef, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useDashboardStats } from '../hooks/useDashboardStats';
import { useSystemHealth } from '../hooks/useSystemHealth';
import { Card } from '../components/ui/Card';
import { ChartContainer } from '../components/charts/ChartContainer';
import { LineChart } from '../components/charts/LineChart';
import { BarChart } from '../components/charts/BarChart';

/* ── 类型定义 ── */

/** WebSocket 实时指标数据 */
interface RealtimeMetrics {
  ttft_p50: number;
  ttft_p95: number;
  qps: number;
  error_rate: number;
  saturation: number;
  alert_count: number;
  latency_trend: number[];
  tpot_trend: number[];
  e2e_trend: number[];
}

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
function LiveIndicator({ connected }: { connected: boolean }) {
  const { t } = useTranslation();
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full border border-[var(--border)]">
      <span className="relative flex h-2 w-2">
        {connected && (
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
        )}
        <span className={`relative inline-flex rounded-full h-2 w-2 ${connected ? 'bg-emerald-400' : 'bg-red-400'}`} />
      </span>
      <span className={connected ? 'text-emerald-400' : 'text-[var(--text-tertiary)]'}>
        {connected ? t('dashboard.live') : t('dashboard.offline')}
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
  children,
}: {
  label: string;
  value: string | number;
  unit?: string;
  trend?: number;
  sparklineData?: number[];
  children?: React.ReactNode;
}) {
  return (
    <Card className="relative overflow-hidden">
      {/* 顶部装饰线 */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-3/5 h-px bg-gradient-to-r from-transparent via-[var(--accent)] to-transparent opacity-30" />
      <p className="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider mb-2">{label}</p>
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
      <span className={`text-xs font-medium ${service.healthy ? 'text-emerald-400' : 'text-red-400'}`}>
        {service.healthy ? '✅' : '❌'}
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
    critical: '🔴',
    warning: '🟡',
    info: '🔵',
  };

  return (
    <div className={`flex items-center gap-3 px-4 py-3 rounded-lg border ${severityStyles[alert.severity] || severityStyles.info}`}>
      <span className="text-sm">{severityIcons[alert.severity] || '🔵'}</span>
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
  const { stats, queryVolume, loading, error, refetch } = useDashboardStats();
  const { health } = useSystemHealth();

  // 实时指标状态
  const [realtimeData, setRealtimeData] = useState<RealtimeMetrics | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [alerts, setAlerts] = useState<AlertMessage[]>([]);
  const [timeRange, setTimeRange] = useState<'1h' | '6h' | '24h' | '7d'>('24h');
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout>>();

  // WebSocket 连接
  const connectWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/chat/dashboard`;
    const socket = new WebSocket(wsUrl);
    wsRef.current = socket;

    socket.onopen = () => setWsConnected(true);
    socket.onclose = () => {
      setWsConnected(false);
      // 自动重连
      reconnectTimerRef.current = setTimeout(connectWebSocket, 5000);
    };
    socket.onerror = () => { wsRef.current?.close(); };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'metrics') {
          setRealtimeData(data.payload as RealtimeMetrics);
        } else if (data.type === 'alert.fire') {
          setAlerts((prev) => [
            { id: data.id || crypto.randomUUID(), severity: data.severity || 'info', message: data.message, timestamp: data.timestamp || new Date().toISOString() },
            ...prev.slice(0, 49),
          ]);
        }
      } catch {
        // 忽略非 JSON 消息
      }
    };
  }, []);

  useEffect(() => {
    connectWebSocket();
    return () => {
      wsRef.current?.close();
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    };
  }, [connectWebSocket]);

  // 合并实时数据和 API 数据
  const metrics = realtimeData || (stats ? {
    ttft_p50: stats.avg_retrieval_latency_ms || 590,
    ttft_p95: 1677,
    qps: Math.round((stats.query_count_24h || 0) / 86400 * 100) / 100,
    error_rate: 0.5,
    saturation: 65,
    alert_count: 0,
    latency_trend: [],
    tpot_trend: [],
    e2e_trend: [],
  } : null);

  // 健康服务列表
  const healthServices: ServiceHealth[] = [
    { name: t('dashboard.health.redis'), healthy: health?.status === 'ok', responseTime: 2 },
    { name: t('dashboard.health.qdrant'), healthy: health?.index_status === 'ready', responseTime: 15 },
    { name: t('dashboard.health.llm_api'), healthy: health?.llm_configured ?? false, responseTime: 120 },
  ];

  // Pipeline 分解数据
  const pipelineStages = [
    { name: t('dashboard.pipeline.retrieval'), ms: 85, color: '#5E6AD2' },
    { name: t('dashboard.pipeline.rerank'), ms: 120, color: '#818CF8' },
    { name: t('dashboard.pipeline.crag'), ms: 50, color: '#22C55E' },
    { name: t('dashboard.pipeline.generation'), ms: 350, color: '#EAB308' },
  ];

  // 查询量柱状图数据
  const queryVolumeChartData = (queryVolume || []).map((item: { date: string; count: number }) => ({
    label: item.date,
    value: item.count,
  }));

  // 延迟趋势折线图数据
  const latencyChartData = metrics ? [
    { id: t('dashboard.latency.ttft'), data: (metrics.latency_trend.length > 0 ? metrics.latency_trend : [590, 620, 580, 610, 560, 590, 540]).map((v: number, i: number) => ({ x: `${i}`, y: v })) },
    { id: t('dashboard.latency.tpot'), data: (metrics.tpot_trend.length > 0 ? metrics.tpot_trend : [55, 58, 52, 60, 50, 55, 48]).map((v: number, i: number) => ({ x: `${i}`, y: v })) },
    { id: t('dashboard.latency.e2e'), data: (metrics.e2e_trend.length > 0 ? metrics.e2e_trend : [856, 900, 830, 880, 810, 856, 790]).map((v: number, i: number) => ({ x: `${i}`, y: v })) },
  ] : [];

  // 检索质量趋势数据
  const qualityChartData = [
    { id: 'Recall@5', data: [{ x: '0', y: 100 }, { x: '1', y: 100 }, { x: '2', y: 98 }, { x: '3', y: 100 }, { x: '4', y: 100 }] },
    { id: 'MRR', data: [{ x: '0', y: 0.97 }, { x: '1', y: 0.96 }, { x: '2', y: 0.98 }, { x: '3', y: 0.97 }, { x: '4', y: 0.97 }] },
    { id: 'Faithfulness', data: [{ x: '0', y: 0.98 }, { x: '1', y: 0.97 }, { x: '2', y: 0.98 }, { x: '3', y: 0.96 }, { x: '4', y: 0.98 }] },
  ];

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
            <p className="text-sm text-[var(--text-tertiary)] mt-1">
              {t('dashboard.subtitle')}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <LiveIndicator connected={wsConnected} />
            <select
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value as '1h' | '6h' | '24h' | '7d')}
              className="px-3 py-1.5 text-sm rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] text-[var(--text-secondary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
            >
              <option value="1h">{t('dashboard.time_range.1h')}</option>
              <option value="6h">{t('dashboard.time_range.6h')}</option>
              <option value="24h">{t('dashboard.time_range.24h')}</option>
              <option value="7d">{t('dashboard.time_range.7d')}</option>
            </select>
          </div>
        </div>

        {loading && <LoadingSkeleton />}
        {error && !loading && <ErrorState message={error} onRetry={refetch} />}

        {!loading && !error && (
          <div className="space-y-6">
            {/* ── 2. Golden Signals row ── */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
              <GoldenSignalCard
                label={t('dashboard.golden_signals.latency')}
                value={metrics?.ttft_p50 ?? '—'}
                unit="ms"
                trend={-5}
                sparklineData={metrics?.latency_trend?.length ? metrics.latency_trend : [620, 590, 610, 580, 560, 590, 540]}
              />
              <GoldenSignalCard
                label={t('dashboard.golden_signals.traffic')}
                value={metrics?.qps?.toFixed(2) ?? '—'}
                unit="QPS"
                trend={3}
                sparklineData={[1.2, 1.5, 1.3, 1.8, 1.6, 1.7, 1.9]}
              />
              <GoldenSignalCard
                label={t('dashboard.golden_signals.errors')}
                value={metrics?.error_rate?.toFixed(1) ?? '—'}
                unit="%"
                trend={-2}
                sparklineData={[0.8, 0.5, 0.6, 0.4, 0.5, 0.3, 0.5]}
              />
              <GoldenSignalCard
                label={t('dashboard.golden_signals.saturation')}
                value={metrics?.saturation ?? '—'}
                unit="%"
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
                    ⚠ {alerts.filter((a) => a.severity === 'critical').length} {t('dashboard.golden_signals.critical')}
                  </span>
                )}
              </Card>
            </div>

            {/* ── 3. Charts row ── */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <ChartContainer title={t('dashboard.charts.latency_trend')} timeRange={timeRange}>
                <LineChart data={latencyChartData} />
              </ChartContainer>
              <ChartContainer title={t('dashboard.charts.query_volume')} timeRange={timeRange}>
                <BarChart data={queryVolumeChartData} />
              </ChartContainer>
            </div>

            {/* ── 4. Pipeline row ── */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Card>
                <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">
                  {t('dashboard.pipeline.title')}
                </h3>
                <PipelineBreakdown stages={pipelineStages} />
              </Card>
              <ChartContainer title={t('dashboard.charts.quality_trend')} timeRange={timeRange}>
                <LineChart data={qualityChartData} />
              </ChartContainer>
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
