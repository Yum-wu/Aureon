import { useState, useRef } from 'react';
import { SearchBar } from '../components/search/SearchBar';
import { StreamingAnswer } from '../components/search/StreamingAnswer';
import { CitationList } from '../components/search/CitationList';
import { streamRAGQuery, type Citation } from '../services/rag';

const MAX_QUERY_LENGTH = 1000;

export function Search() {
  const [query, setQuery] = useState('');
  const [answer, setAnswer] = useState('');
  const [citations, setCitations] = useState<Citation[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const handleSearch = async () => {
    const trimmed = query.trim();
    if (!trimmed) return;

    // Frontend input length validation
    if (trimmed.length > MAX_QUERY_LENGTH) {
      setError(`查询内容不能超过 ${MAX_QUERY_LENGTH} 个字符（当前 ${trimmed.length} 个）`);
      return;
    }

    // Cancel previous in-flight request
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsLoading(true);
    setIsStreaming(true);
    setAnswer('');
    setCitations([]);
    setError(null);

    await streamRAGQuery(trimmed, {
      signal: controller.signal,
      onToken: (token) => {
        setAnswer(prev => prev + token);
      },
      onCitations: (cits) => setCitations(cits),
      onError: (msg) => setError(msg),
    });

    setIsLoading(false);
    setIsStreaming(false);
  };

  return (
    <div className="min-h-screen bg-[var(--bg-primary)]">
      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold mb-2">Enterprise Search</h1>
          <p className="text-[var(--text-secondary)]">
            AI-powered search across your knowledge base
          </p>
        </div>

        <div className="mb-8">
          <SearchBar
            value={query}
            onChange={(val) => {
              setQuery(val);
              if (error) setError(null);
            }}
            onSearch={handleSearch}
            isLoading={isLoading}
          />
          <p className="mt-1 text-xs text-[var(--text-secondary)] text-center">
            {query.length}/{MAX_QUERY_LENGTH}
          </p>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-sm" role="alert">
            {error}
          </div>
        )}

        {(answer || isLoading) && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div className="lg:col-span-2">
              <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-6">
                <StreamingAnswer
                  content={answer}
                  citations={citations}
                  isStreaming={isStreaming}
                />
              </div>
            </div>

            <div className="lg:col-span-1">
              <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-6 sticky top-8">
                <CitationList citations={citations} />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
