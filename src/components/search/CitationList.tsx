interface Citation {
  id: number;
  title: string;
  snippet: string;
  url?: string;
  score?: number;
}

interface CitationListProps {
  citations: Citation[];
}

export function CitationList({ citations }: CitationListProps) {
  if (citations.length === 0) return null;

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-medium text-[var(--text-secondary)]">Sources</h3>
      {citations.map((citation) => (
        <div
          key={citation.id}
          className="p-3 bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg
                     hover:border-[var(--border-hover)] transition-colors cursor-pointer"
        >
          <div className="flex items-start gap-2">
            <span className="flex-shrink-0 w-5 h-5 flex items-center justify-center
                           bg-[var(--accent-soft)] text-[var(--accent)] text-xs font-medium rounded">
              {citation.id}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-[var(--text-primary)] truncate">
                {citation.title}
              </p>
              <p className="text-xs text-[var(--text-tertiary)] mt-1 line-clamp-2">
                {citation.snippet}
              </p>
              {typeof citation.score === "number" && (
                <div className="mt-2 flex items-center gap-2">
                  <div className="flex-1 h-1.5 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-[var(--accent)] rounded-full transition-all"
                      style={{ width: `${Math.round(citation.score * 100)}%` }}
                    />
                  </div>
                  <span className="text-xs text-[var(--text-tertiary)] tabular-nums">
                    {Math.round(citation.score * 100)}%
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
