import { Card } from '../ui/Card';
import type { RecentQuery } from '../../types/dashboard';

interface RecentQueriesProps {
  queries: RecentQuery[];
}

export function RecentQueries({ queries }: RecentQueriesProps) {
  return (
    <Card>
      <h3 className="text-lg font-semibold mb-4">Recent Queries</h3>
      {queries.length === 0 ? (
        <p className="text-sm text-[var(--text-tertiary)]">No recent queries</p>
      ) : (
        <div className="space-y-3">
          {queries.map((q, i) => (
            <div key={`${q.timestamp}-${q.query}-${i}`}
                 className="flex items-center justify-between p-3 bg-[var(--bg-tertiary)] rounded-lg">
              <div className="flex-1 min-w-0">
                <p className="text-sm text-[var(--text-primary)] truncate">{q.query}</p>
                <p className="text-xs text-[var(--text-tertiary)]">
                  {new Date(q.timestamp).toLocaleString()}
                </p>
              </div>
              <div className="flex items-center gap-4 ml-4">
                <span className="text-xs text-[var(--text-secondary)]">
                  {q.sources_count} sources
                </span>
                <span className="text-sm font-mono">{Math.round(q.latency_ms)}ms</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
