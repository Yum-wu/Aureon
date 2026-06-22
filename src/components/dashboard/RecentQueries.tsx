import { useTranslation } from 'react-i18next';
import { Card } from '../ui/Card';
import type { RecentQuery } from '../../types/dashboard';

interface RecentQueriesProps {
  queries: RecentQuery[];
}

export function RecentQueries({ queries }: RecentQueriesProps) {
  const { t } = useTranslation();

  return (
    <Card>
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">
          {t('dashboard.recent_queries.title')}
        </h3>
        <span className="text-xs text-[var(--text-tertiary)]">
          {queries.length} {t('dashboard.recent_queries.total')}
        </span>
      </div>
      {queries.length === 0 ? (
        <p className="text-sm text-[var(--text-tertiary)] py-8 text-center">
          {t('dashboard.recent_queries.empty')}
        </p>
      ) : (
        <div role="list" aria-label={t('dashboard.recent_queries.title')} className="space-y-1">
          {queries.map((q, i) => (
            <div
              key={`${q.timestamp}-${q.query}-${i}`}
              role="button"
              tabIndex={0}
              className="flex items-center justify-between px-3 py-2.5 rounded-md hover:bg-[var(--surface-inset)] transition-colors focus-visible:outline-2 focus-visible:outline-[var(--accent)] focus-visible:outline-offset-2"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm text-[var(--text-primary)] truncate">
                  {q.query}
                </p>
                <p className="text-[11px] text-[var(--text-tertiary)] mt-0.5">
                  {new Date(q.timestamp).toLocaleString()}
                </p>
              </div>
              <div className="flex items-center gap-3 ml-4 shrink-0">
                <span className="text-[11px] text-[var(--text-tertiary)]">
                  {q.sources_count} {t('dashboard.recent_queries.sources')}
                </span>
                <span className="text-xs font-mono text-[var(--text-secondary)] tabular-nums">
                  {Math.round(q.latency_ms)}ms
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
