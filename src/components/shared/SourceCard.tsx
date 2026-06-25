import { useState } from 'react';

export interface Source {
  title: string;
  score?: number;
  snippet?: string;
  url?: string;
}

interface SourceCardProps {
  sources: Source[];
  maxVisible?: number;
  t: (key: string) => string;
}

export function SourceCard({ sources, maxVisible = 2, t }: SourceCardProps) {
  const [expanded, setExpanded] = useState(false);

  if (!sources || sources.length === 0) return null;

  const visible = expanded ? sources : sources.slice(0, maxVisible);

  return (
    <div className="mt-3 pt-2 border-t border-[var(--border)]">
      <p className="text-xs font-medium text-[var(--text-tertiary)] mb-1 inline-flex items-center gap-1">
        {t('support.sources')}:
      </p>
      <div className="space-y-1">
        {visible.map((source, idx) => (
          <div key={idx} className="flex items-center gap-2 text-xs">
            <span className="text-[var(--accent)] font-medium truncate max-w-[200px]">{source.title}</span>
            {source.score !== undefined && (
              <span className="text-[var(--text-tertiary)] shrink-0">
                ({(source.score * 100).toFixed(0)}%)
              </span>
            )}
          </div>
        ))}
      </div>
      {sources.length > maxVisible && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-[var(--accent)] mt-1 hover:underline"
        >
          {expanded ? t('support.sources_toggle') : `${t('support.sources_toggle')} (${sources.length - maxVisible})`}
        </button>
      )}
    </div>
  );
}
