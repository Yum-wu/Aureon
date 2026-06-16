import { useTranslation } from 'react-i18next';
import { useBenchmark } from '../../hooks/useBenchmark';

const fmtVal = (v: string | number | null, fallback: string) => {
  if (v === null) return fallback;
  const s = String(v);
  return s.includes('ms') || s.includes('%') || s.includes('$') ? s : s;
};

export function BenchmarkSection() {
  const { t } = useTranslation();
  const { data: benchmark } = useBenchmark();

  const findMetric = (pat: string) =>
    benchmark?.metrics?.find((m: { label: string; value: string | number }) => m.label.includes(pat))?.value ?? null;

  const ttftVal = findMetric('TTFT');
  const costVal = findMetric('Cost');

  const metrics = [
    {
      label: 'Faithfulness',
      value: fmtVal(findMetric('Faithfulness'), '98.1%'),
      change: 'DeepEval',
      sub: '>=70%',
    },
    {
      label: 'Answer Relevancy',
      value: fmtVal(findMetric('Answer Relevancy'), '92.4%'),
      change: '192 QA pairs',
      sub: '>=75%',
    },
    {
      label: 'Negative Detection',
      value: '90%',
      change: '18/20',
      sub: '>=80%',
    },
  ];

  const optimizations = [
    { label: 'TTFT', before: '~825ms', after: fmtVal(ttftVal, '~586ms') },
    { label: 'E2E Latency', before: '12,076ms', after: '~853ms' },
    { label: t('landing.benchmark.cost_per_query'), before: '$0.01', after: fmtVal(costVal, '~$0.001') },
  ];

  return (
    <section className="relative py-20 px-6" style={{ background: 'var(--bg-primary)' }}>
      <div
        className="absolute inset-0 pointer-events-none"
        style={{ background: 'var(--gradient-glow)' }}
      />

      <div className="relative max-w-5xl mx-auto">
        <h2 className="text-2xl font-bold tracking-[-0.02em] mb-2 text-white animate-fade-up">
          {t('landing.benchmark.title')}
        </h2>
        <p className="text-sm text-[var(--text-tertiary)] mb-12 animate-fade-up delay-100">
          {t('landing.benchmark.subtitle')}
        </p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          {metrics.map((m, idx) => (
            <div key={m.label} className="metric-card animate-slide-up" style={{ animationDelay: `${idx * 0.1 + 0.2}s` }}>
              <p className="text-xs text-[var(--text-tertiary)] uppercase tracking-wider mb-4">
                {m.label}
              </p>
              <p className="metric-value text-3xl mb-1">{m.value}</p>
              <p className="text-xs text-[var(--success)]">
                {m.change}
                <span className="text-[var(--text-tertiary)] ml-1">{m.sub}</span>
              </p>
            </div>
          ))}
        </div>

        <div className="linear-card p-6">
          <h3 className="text-sm font-semibold text-white mb-6">
            {t('landing.benchmark.optimization_story')}
          </h3>
          <div className="space-y-4">
            {optimizations.map((item) => (
              <div key={item.label} className="flex justify-between items-center py-2 border-b border-[var(--border-subtle)] last:border-0">
                <span className="text-sm text-[var(--text-secondary)]">{item.label}</span>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-[var(--error)] line-through opacity-60 font-mono">{item.before}</span>
                  <span className="text-[var(--text-tertiary)]">→</span>
                  <span className="text-xs text-[var(--success)] font-mono font-medium">{item.after}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
