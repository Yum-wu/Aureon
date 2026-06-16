import { useTranslation } from 'react-i18next';
import { useBenchmark } from '../hooks/useBenchmark';

const colorMap: Record<string, string> = {
  blue: 'bg-blue-100 text-blue-700',
  purple: 'bg-purple-100 text-purple-700',
  cyan: 'bg-cyan-100 text-cyan-700',
  green: 'bg-green-100 text-green-700',
  amber: 'bg-amber-100 text-amber-700',
  rose: 'bg-rose-100 text-rose-700',
};
const borderMap: Record<string, string> = {
  blue: 'border-blue-300',
  purple: 'border-purple-300',
  cyan: 'border-cyan-300',
  green: 'border-green-300',
  amber: 'border-amber-300',
  rose: 'border-rose-300',
};

const Benchmark = () => {
  const { t } = useTranslation();
  const { data: benchmark, loading } = useBenchmark();

  if (loading) return <div className="flex items-center justify-center h-full text-[var(--text-tertiary)]">{t('benchmark.loading')}</div>;

  return (
    <div className="overflow-y-auto p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">{t('benchmark.title')}</h1>
        <p className="text-[var(--text-tertiary)] text-sm">{t('benchmark.subtitle')}</p>
      </div>

      {/* Runtime Metrics Hero */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
        {benchmark?.metrics?.map((m: { value: string | number; label: string }, i: number) => {
          const colors = ['from-blue-500 to-cyan-400', 'from-purple-500 to-pink-400', 'from-green-500 to-emerald-400', 'from-amber-500 to-orange-400', 'from-red-500 to-rose-400'];
          return (
            <div key={i} className={`bg-gradient-to-br ${colors[i % colors.length]} rounded-xl p-5 text-white shadow-lg`}>
              <div className="text-3xl font-bold">{m.value}</div>
              <div className="text-sm opacity-90 mt-1">{m.label}</div>
            </div>
          );
        })}
      </div>

      {/* Architecture Diagram */}
      <div className="bg-[var(--bg-secondary)] rounded-xl border border-[var(--border)] p-4 md:p-6 mb-8">
        <h3 className="font-semibold text-[var(--text-primary)] mb-4 md:mb-6">{t('benchmark.system_architecture')}</h3>
        {/* Desktop: Horizontal */}
        <div className="hidden md:flex items-center justify-center gap-3 lg:gap-4 flex-wrap text-sm">
          <div className="bg-blue-100 text-blue-700 px-4 py-3 rounded-lg border-2 border-blue-300">
            <div className="font-semibold">{t('benchmark.document_input')}</div>
            <div className="text-xs opacity-75">PDF / MD / TXT</div>
          </div>
          <svg className="w-6 h-6 text-[var(--text-tertiary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          <div className="bg-purple-100 text-purple-700 px-4 py-3 rounded-lg border-2 border-purple-300">
            <div className="font-semibold">BGE Embedding</div>
            <div className="text-xs opacity-75">{t('benchmark.local_inference')}</div>
          </div>
          <svg className="w-6 h-6 text-[var(--text-tertiary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          <div className="bg-cyan-100 text-cyan-700 px-4 py-3 rounded-lg border-2 border-cyan-300">
            <div className="font-semibold">Qdrant Cloud</div>
            <div className="text-xs opacity-75">{t('benchmark.vector_database')}</div>
          </div>
          <svg className="w-6 h-6 text-[var(--text-tertiary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          <div className="bg-green-100 text-green-700 px-4 py-3 rounded-lg border-2 border-green-300">
            <div className="font-semibold">Hybrid Search</div>
            <div className="text-xs opacity-75">BM25 + Dense</div>
          </div>
          <svg className="w-6 h-6 text-[var(--text-tertiary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          <div className="bg-amber-100 text-amber-700 px-4 py-3 rounded-lg border-2 border-amber-300">
            <div className="font-semibold">LLM</div>
            <div className="text-xs opacity-75">{benchmark?.services?.llm || 'LLM'}</div>
          </div>
          <svg className="w-6 h-6 text-[var(--text-tertiary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          <div className="bg-rose-100 text-rose-700 px-4 py-3 rounded-lg border-2 border-rose-300">
            <div className="font-semibold">SSE Streaming</div>
            <div className="text-xs opacity-75">{t('benchmark.realtime_output')}</div>
          </div>
        </div>

        {/* Mobile: Vertical */}
        <div className="md:hidden space-y-2">
          {[
            { name: t('benchmark.document_input'), detail: 'PDF / MD / TXT', color: 'blue' },
            { name: 'BGE Embedding', detail: t('benchmark.local_inference'), color: 'purple' },
            { name: 'Qdrant Cloud', detail: t('benchmark.vector_database'), color: 'cyan' },
            { name: 'Hybrid Search', detail: 'BM25 + Dense', color: 'green' },
            { name: 'LLM', detail: benchmark?.services?.llm || 'LLM', color: 'amber' },
            { name: 'SSE Streaming', detail: t('benchmark.realtime_output'), color: 'rose' },
          ].map((item, i) => (
            <div key={i} className={`${colorMap[item.color]} px-4 py-3 rounded-lg border-2 ${borderMap[item.color]}`}>
              <div className="font-semibold">{item.name}</div>
              <div className="text-xs opacity-75">{item.detail}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Optimization Story */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        <div className="bg-[var(--bg-secondary)] rounded-xl border border-[var(--border)] p-6">
          <h3 className="font-semibold text-[var(--text-primary)] mb-4">{t('benchmark.ttft_optimization')}</h3>
          <div className="space-y-4">
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-[var(--text-secondary)]">TTFT P50</span>
                <span className="text-[var(--success)] font-medium">{benchmark?.metrics?.find(m => m.label.includes('TTFT'))?.value ?? '—'}</span>
              </div>
              <div className="h-3 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
                <div className="h-full bg-green-500 rounded-full" style={{ width: `${Math.min(100, parseFloat(String(benchmark?.metrics?.find(m => m.label.includes('TTFT'))?.value ?? '0').replace(/[^0-9.]/g, '')) / 20)}%` }} />
              </div>
            </div>
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-[var(--text-secondary)]">E2E P50</span>
                <span className="text-[var(--success)] font-medium">{benchmark?.metrics?.find(m => m.label.includes('E2E'))?.value ?? '—'}</span>
              </div>
              <div className="h-3 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
                <div className="h-full bg-green-500 rounded-full" style={{ width: `${Math.min(100, parseFloat(String(benchmark?.metrics?.find(m => m.label.includes('E2E'))?.value ?? '0').replace(/[^0-9.]/g, '')) / 50)}%` }} />
              </div>
            </div>
            <div className="text-xs text-[var(--text-tertiary)] mt-3">
              {t('benchmark.ttft_improvement_detail')}
            </div>
          </div>
        </div>

        <div className="bg-[var(--bg-secondary)] rounded-xl border border-[var(--border)] p-6">
          <h3 className="font-semibold text-[var(--text-primary)] mb-4">{t('benchmark.retrieval_accuracy')}</h3>
          <div className="space-y-4">
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-[var(--text-secondary)]">Recall@5</span>
                <span className="text-blue-500 font-medium">{benchmark?.metrics?.find(m => m.label.includes('Recall@5'))?.value ?? '—'}</span>
              </div>
              <div className="h-3 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
                <div className="h-full bg-blue-400 rounded-full" style={{ width: `${parseFloat(String(benchmark?.metrics?.find(m => m.label.includes('Recall@5'))?.value ?? '0'))}%` }} />
              </div>
            </div>
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-[var(--text-secondary)]">MRR</span>
                <span className="text-[var(--success)] font-medium">{benchmark?.metrics?.find(m => m.label.includes('MRR'))?.value ?? '—'}</span>
              </div>
              <div className="h-3 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
                <div className="h-full bg-green-500 rounded-full" style={{ width: `${parseFloat(String(benchmark?.metrics?.find(m => m.label.includes('MRR'))?.value ?? '0')) * 100}%` }} />
              </div>
            </div>
            <div className="text-xs text-[var(--text-tertiary)] mt-3">
              {t('benchmark.qa_benchmark_detail')}
            </div>
          </div>
        </div>
      </div>

      {/* Technical Details */}
      <div className="bg-[var(--bg-secondary)] rounded-xl border border-[var(--border)] p-6">
        <h3 className="font-semibold text-[var(--text-primary)] mb-4">{t('architecture.tech_stack')}</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div className="p-3 bg-[var(--bg-tertiary)] rounded-lg">
            <div className="font-medium text-[var(--text-primary)] mb-1">Embedding</div>
            <div className="text-[var(--text-secondary)]">{benchmark?.services?.embedding?.split('+')[0]?.trim() ?? '—'}</div>
            <div className="text-xs text-[var(--text-tertiary)]">1024d · DashScope API</div>
          </div>
          <div className="p-3 bg-[var(--bg-tertiary)] rounded-lg">
            <div className="font-medium text-[var(--text-primary)] mb-1">{t('benchmark.vector_database')}</div>
            <div className="text-[var(--text-secondary)]">{benchmark?.services?.vector_db?.split('(')[0]?.trim() ?? '—'}</div>
            <div className="text-xs text-[var(--text-tertiary)]">{benchmark?.services?.vector_db?.includes('HNSW') ? 'HNSW + Sparse Vectors' : ''}</div>
          </div>
          <div className="p-3 bg-[var(--bg-tertiary)] rounded-lg">
            <div className="font-medium text-[var(--text-primary)] mb-1">{t('benchmark.retrieval_strategy')}</div>
            <div className="text-[var(--text-secondary)]">Hybrid Search</div>
            <div className="text-xs text-[var(--text-tertiary)]">{benchmark?.services?.hybrid_search?.split('→')[0]?.trim() ?? '—'}</div>
          </div>
          <div className="p-3 bg-[var(--bg-tertiary)] rounded-lg">
            <div className="font-medium text-[var(--text-primary)] mb-1">{t('benchmark.caching')}</div>
            <div className="text-[var(--text-secondary)]">{benchmark?.services?.cache?.split('+')[0]?.trim() ?? '—'}</div>
            <div className="text-xs text-[var(--text-tertiary)]">{benchmark?.services?.cache?.includes('semantic') ? 'Semantic Cache' : ''}</div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Benchmark;
