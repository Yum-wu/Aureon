import type { AlertMessage } from './types';

interface AlertRowProps {
  alert: AlertMessage;
}

/** Alert severity row */
export function AlertRow({ alert }: AlertRowProps) {
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
