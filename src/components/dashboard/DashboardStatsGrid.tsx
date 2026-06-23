import { useTranslation } from 'react-i18next';
import { Card } from '../ui/Card';
import { Tooltip } from '../ui/Tooltip';
import { AlertTriangle } from 'lucide-react';

/* ── Types ── */

interface AlertMessage {
  id: string;
  severity: 'critical' | 'warning' | 'info';
  message: string;
  timestamp: string;
}

interface DashboardMetrics {
  ttft_p50?: number;
  qps?: number;
  error_rate?: number;
  saturation?: number;
  alert_count?: number;
  latency_trend?: number[];
}

interface DashboardStatsGridProps {
  metrics: DashboardMetrics | null;
  alerts: AlertMessage[];
}

/* ── Helper components ── */

function TrendArrow({ value }: { value: number }) {
  if (value > 0) {
    return <span className="text-emerald-400 text-xs font-semibold">↑ {Math.abs(value)}%</span>;
  }
  if (value < 0) {
    return <span className="text-red-400 text-xs font-semibold">↓ {Math.abs(value)}%</span>;
  }
  return <span className="text-[var(--text-tertiary)] text-xs">—</span>;
}

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
    <Card data-testid="golden-signal-card" className="relative overflow-hidden">
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

/* ── Main component ── */

/** Golden Signals stats card grid */
export function DashboardStatsGrid({ metrics, alerts }: DashboardStatsGridProps) {
  const { t } = useTranslation();

  return (
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
  );
}
