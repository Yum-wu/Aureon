import { useState, useRef } from 'react';
import { SearchBar } from '../components/search/SearchBar';
import { StreamingAnswer } from '../components/search/StreamingAnswer';
import { CitationList } from '../components/search/CitationList';
import { streamRAGQuery, type Citation } from '../services/rag';

export function Search() {
  const [query, setQuery] = useState('');
  const [answer, setAnswer] = useState('');
  const [citations, setCitations] = useState<Citation[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const handleSearch = async () => {
    if (!query.trim()) return;

    // 取消上一次未完成的请求
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsLoading(true);
    setIsStreaming(false);
    setAnswer('');
    setCitations([]);
    setError(null);

    await streamRAGQuery(query, {
      signal: controller.signal,
      onToken: (token) => {
        setIsStreaming(true);
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
            onChange={setQuery}
            onSearch={handleSearch}
            isLoading={isLoading}
          />
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-sm">
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
