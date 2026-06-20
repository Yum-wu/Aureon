import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useBenchmark } from '../hooks/useBenchmark';

const HERO_COLORS = [
  'from-blue-500 to-cyan-400',
  'from-purple-500 to-pink-400',
  'from-green-500 to-emerald-400',
  'from-amber-500 to-orange-400',
  'from-rose-500 to-red-400',
];

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
  const [showInternal, setShowInternal] = useState(false);

  if (loading) return <div className="flex items-center justify-center h-full text-[var(--text-tertiary)]">{t('benchmark.loading')}</div>;

  const customerMetrics = (benchmark?.metrics ?? [])
    .filter((m) => m.customer_facing)
    .sort((a, b) => (a.priority ?? 99) - (b.priority ?? 99));

  const internalMetrics = (benchmark?.metrics ?? []).filter((m) => !m.customer_facing);

  return (
    <div className="overflow-y-auto p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">{t('benchmark.title')}</h1>
        <p className="text-[var(--text-tertiary)] text-sm">{t('benchmark.subtitle')}</p>
      </div>

      {/* ═══ 客户核心指标 Hero ═══ */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        {customerMetrics.map((m, i) => (
          <div key={m.label} className={`bg-gradient-to-br ${HERO_COLORS[i % HERO_COLORS.length]} rounded-xl p-5 text-white shadow-lg`}>
            <div className="text-3xl font-bold">{m.value}</div>
            <div className="text-sm mt-1">
              {m.label}
              {m.status === 'optimizing' && (
                <span className="ml-2 text-xs bg-white/20 px-2 py-0.5 rounded-full">优化中</span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* ═══ Architecture Diagram ═══ */}
      <div className="bg-[var(--bg-secondary)] rounded-xl border border-[var(--border)] p-4 md:p-6 mb-8">
        <h3 className="font-semibold text-[var(--text-primary)] mb-4 md:mb-6">{t('benchmark.system_architecture')}</h3>
        <div className="hidden md:flex items-center justify-center gap-3 lg:gap-4 flex-wrap text-sm">
          {[
            { name: t('benchmark.document_input'), detail: 'PDF / MD / TXT', color: 'blue' },
            { name: 'BGE-M3 Embedding', detail: '1024d dense + sparse', color: 'purple' },
            { name: 'Qdrant Cloud', detail: t('benchmark.vector_database'), color: 'cyan' },
            { name: 'Hybrid Search', detail: 'BM25 + Dense + Reranker', color: 'green' },
            { name: 'LLM', detail: benchmark?.services?.llm || 'LLM', color: 'amber' },
            { name: 'SSE Streaming', detail: t('benchmark.realtime_output'), color: 'rose' },
          ].map((item, i) => (
            <div key={i} className="contents">
              {i > 0 && (
                <svg className="w-6 h-6 text-[var(--text-tertiary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              )}
              <div className={`${colorMap[item.color]} px-4 py-3 rounded-lg border-2 ${borderMap[item.color]}`}>
                <div className="font-semibold">{item.name}</div>
                <div className="text-xs text-[var(--text-tertiary)]">{item.detail}</div>
              </div>
            </div>
          ))}
        </div>
        <div className="md:hidden space-y-2">
          {[{ name: t('benchmark.document_input'), detail: 'PDF / MD / TXT', color: 'blue' }, { name: 'BGE-M3 Embedding', detail: '1024d dense + sparse', color: 'purple' }, { name: 'Qdrant Cloud', detail: t('benchmark.vector_database'), color: 'cyan' }, { name: 'Hybrid Search', detail: 'BM25 + Dense + Reranker', color: 'green' }, { name: 'LLM', detail: benchmark?.services?.llm || 'LLM', color: 'amber' }, { name: 'SSE Streaming', detail: t('benchmark.realtime_output'), color: 'rose' }].map((item, i) => (
            <div key={i} className={`${colorMap[item.color]} px-4 py-3 rounded-lg border-2 ${borderMap[item.color]}`}>
              <div className="font-semibold">{item.name}</div>
              <div className="text-xs text-[var(--text-tertiary)]">{item.detail}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ═══ Optimization Story ═══ */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        <div className="bg-[var(--bg-secondary)] rounded-xl border border-[var(--border)] p-6">
          <h3 className="font-semibold text-[var(--text-primary)] mb-4">{t('benchmark.ttft_optimization')}</h3>
          <div className="space-y-4">
            {[{ label: 'TTFT P50', mLabel: 'TTFT P50', color: 'green', div: 20 },
              { label: 'TTFT P95', mLabel: 'TTFT P95', color: 'amber', div: 20 },
              { label: 'E2E P50', mLabel: 'E2E P50', color: 'green', div: 50 },
              { label: 'E2E P95', mLabel: 'E2E P95', color: 'amber', div: 50 },
            ].map((item) => {
              const val = benchmark?.metrics?.find(m => m.label === item.mLabel)?.value ?? '0';
              const num = parseFloat(String(val).replace(/[^0-9.]/g, ''));
              return (
                <div key={item.label}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-[var(--text-secondary)]">{item.label}</span>
                    <span className={`${item.color === 'green' ? 'text-[var(--success)]' : 'text-amber-500'} font-medium`}>{val}</span>
                  </div>
                  <div className="h-3 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
                    <div className={`h-full ${item.color === 'green' ? 'bg-green-500' : 'bg-amber-400'} rounded-full`} style={{ width: `${Math.min(100, num / item.div)}%` }} />
                  </div>
                </div>
              );
            })}
            <div className="text-xs text-[var(--text-tertiary)] mt-3">
              {t('benchmark.ttft_improvement_detail')}
            </div>
          </div>
        </div>

        <div className="bg-[var(--bg-secondary)] rounded-xl border border-[var(--border)] p-6">
          <h3 className="font-semibold text-[var(--text-primary)] mb-4">{t('benchmark.retrieval_accuracy')}</h3>
          <div className="space-y-4">
            {[{ label: 'Recall@5', mLabel: 'Recall@5', color: 'blue', mul: 1 },
              { label: 'MRR', mLabel: 'MRR', color: 'green', mul: 100 },
            ].map((item) => {
              const val = benchmark?.metrics?.find(m => m.label === item.mLabel)?.value ?? '0';
              const num = parseFloat(String(val).replace(/[^0-9.]/g, ''));
              return (
                <div key={item.label}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-[var(--text-secondary)]">{item.label}</span>
                    <span className={`${item.color === 'blue' ? 'text-blue-500' : 'text-[var(--success)]'} font-medium`}>{val}</span>
                  </div>
                  <div className="h-3 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
                    <div className={`h-full ${item.color === 'blue' ? 'bg-blue-400' : 'bg-green-500'} rounded-full`} style={{ width: `${num * item.mul}%` }} />
                  </div>
                </div>
              );
            })}
            <div className="text-xs text-[var(--text-tertiary)] mt-3">
              {t('benchmark.qa_benchmark_detail')}
            </div>
          </div>
        </div>
      </div>

      {/* ═══ 内部评估指标（折叠） ═══ */}
      <div className="bg-[var(--bg-secondary)] rounded-xl border border-[var(--border)] mb-8">
        <button
          onClick={() => setShowInternal(!showInternal)}
          className="w-full flex items-center justify-between p-6 text-left hover:bg-[var(--bg-tertiary)] transition-colors rounded-xl"
        >
          <h3 className="font-semibold text-[var(--text-primary)]">{t('benchmark.internal_metrics', 'Internal Evaluation Metrics')}</h3>
          <span className="text-[var(--text-tertiary)] text-sm">{showInternal ? '▲' : '▼'}</span>
        </button>
        {showInternal && (
          <div className="px-6 pb-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {internalMetrics.map((m) => (
                <div key={m.label} className="p-3 bg-[var(--bg-tertiary)] rounded-lg">
                  <div className="text-xs text-[var(--text-tertiary)] mb-1">{m.label}</div>
                  <div className="text-lg font-semibold text-[var(--text-primary)]">{m.value}</div>
                  <div className="text-xs text-[var(--text-tertiary)] mt-1">{m.detail}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ═══ Technical Details ═══ */}
      <div className="bg-[var(--bg-secondary)] rounded-xl border border-[var(--border)] p-6">
        <h3 className="font-semibold text-[var(--text-primary)] mb-4">{t('architecture.tech_stack')}</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          {[{ label: 'Embedding', value: benchmark?.services?.embedding?.split('+')[0]?.trim() ?? '—', sub: '1024d · DashScope API' },
            { label: t('benchmark.vector_database'), value: benchmark?.services?.vector_db?.split('(')[0]?.trim() ?? '—', sub: benchmark?.services?.vector_db?.includes('HNSW') ? 'HNSW + Sparse Vectors' : '' },
            { label: t('benchmark.retrieval_strategy'), value: 'Hybrid Search', sub: benchmark?.services?.hybrid_search?.split('→')[0]?.trim() ?? '—' },
            { label: t('benchmark.caching'), value: benchmark?.services?.cache?.split('+')[0]?.trim() ?? '—', sub: benchmark?.services?.cache?.includes('semantic') ? 'Semantic Cache' : '' },
          ].map((item) => (
            <div key={item.label} className="p-3 bg-[var(--bg-tertiary)] rounded-lg">
              <div className="font-medium text-[var(--text-primary)] mb-1">{item.label}</div>
              <div className="text-[var(--text-secondary)]">{item.value}</div>
              <div className="text-xs text-[var(--text-tertiary)]">{item.sub}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default Benchmark;
