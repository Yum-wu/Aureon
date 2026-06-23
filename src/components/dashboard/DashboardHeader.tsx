import { useTranslation } from 'react-i18next';
import { Tooltip } from '../ui/Tooltip';

interface DashboardHeaderProps {
  rtIsConnected: boolean;
  rtConnectionState?: string;
  rtLastUpdated: string | null;
  timeRange: '1h' | '6h' | '24h' | '7d';
  onTimeRangeChange: (range: '1h' | '6h' | '24h' | '7d') => void;
}

/** Real-time connection status indicator */
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

/** Dashboard page header with title, connection status, and time range selector */
export function DashboardHeader({ rtIsConnected, rtConnectionState, rtLastUpdated, timeRange, onTimeRangeChange }: DashboardHeaderProps) {
  const { t } = useTranslation();

  return (
    <div className="flex items-end justify-between mb-8 mt-4">
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
          onChange={(e) => onTimeRangeChange(e.target.value as '1h' | '6h' | '24h' | '7d')}
          className="px-3 py-1.5 text-sm rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] text-[var(--text-secondary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
        >
          <option value="1h">{t('dashboard.time_range.1h')}</option>
          <option value="6h">{t('dashboard.time_range.6h')}</option>
          <option value="24h">{t('dashboard.time_range.24h')}</option>
          <option value="7d">{t('dashboard.time_range.7d')}</option>
        </select>
      </div>
    </div>
  );
}
