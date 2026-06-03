import { Card } from './Card';

interface MetricCardProps {
  label: string;
  value: string | number;
  suffix?: string;
  change?: number;
  changeLabel?: string;
}

export function MetricCard({ label, value, suffix, change, changeLabel }: MetricCardProps) {
  return (
    <Card>
      <p className="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider mb-2">
        {label}
      </p>
      <div className="flex items-baseline gap-1">
        <span className="text-3xl font-bold text-[var(--text-primary)] tabular-nums tracking-tight">
          {value}
        </span>
        {suffix && (
          <span className="text-sm font-medium text-[var(--text-tertiary)]">
            {suffix}
          </span>
        )}
      </div>
      {change !== undefined && (
        <div className="flex items-center gap-1 mt-3">
          <span
            className={`inline-flex items-center gap-0.5 text-xs font-semibold px-1.5 py-0.5 rounded-full ${
              change >= 0
                ? 'text-emerald-400 bg-emerald-500/10'
                : 'text-red-400 bg-red-500/10'
            }`}
          >
            {change >= 0 ? '\u2191' : '\u2193'} {Math.abs(change)}%
          </span>
          {changeLabel && (
            <span className="text-xs text-[var(--text-tertiary)]">
              {changeLabel}
            </span>
          )}
        </div>
      )}
    </Card>
  );
}
