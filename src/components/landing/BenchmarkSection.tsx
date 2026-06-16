import { useTranslation } from 'react-i18next';
import { useBenchmark } from '../../hooks/useBenchmark';

const fmtVal = (v: string | number | null, fallback: string) => {
  if (v === null) return fallback;
  return String(v);
};

const ICONS: Record<string, string> = {
  Faithfulness: '🎯',
  'Answer Relevancy': '✓',
  'Negative Detection': '🛡️',
  'E2E P50': '⚡',
  'E2E P95': '⏱️',
  'TTFT P50': '📡',
  'TTFT P95': '📶',
  'Cost per Query': '💰',
};

export function BenchmarkSection() {
  const { t } = useTranslation();
  const { data: benchmark } = useBenchmark();

  const customerMetrics = (benchmark?.metrics ?? [])
    .filter((m) => m.customer_facing)
    .sort((a, b) => (a.priority ?? 99) - (b.priority ?? 99));

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

        {/* 客户核心指标 — 5 cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {customerMetrics.map((m, idx) => (
            <div
              key={m.label}
              className="metric-card animate-slide-up text-center"
              style={{ animationDelay: `${idx * 0.08 + 0.2}s` }}
            >
              <p className="text-2xl mb-2">{ICONS[m.label] ?? '📊'}</p>
              <p className="text-xs text-[var(--text-tertiary)] uppercase tracking-wider mb-3">
                {m.label}
              </p>
              <p className="metric-value text-2xl md:text-3xl mb-1">{fmtVal(m.value, '—')}</p>
            </div>
          ))}
        </div>

        {/* 测试规模说明 */}
        <div className="text-center text-xs text-[var(--text-tertiary)] animate-fade-up delay-200">
          {t('landing.benchmark.test_scale', '192 QA pairs · DeepEval LLM-as-Judge · 26 articles knowledge base')}
        </div>
      </div>
    </section>
  );
}
