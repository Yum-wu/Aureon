import { useTranslation } from 'react-i18next';

export function BenchmarkSection() {
  const { t } = useTranslation();

  return (
    <section className="py-20 px-6 bg-[var(--bg-primary)]">
      <div className="max-w-5xl mx-auto">
        <h2 className="text-2xl font-bold tracking-[-0.02em] mb-2 text-white">
          {t('landing.benchmark.title')}
        </h2>
        <p className="text-sm text-[var(--text-tertiary)] mb-12">
          {t('landing.benchmark.subtitle')}
        </p>

        {/* Metric cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-px bg-white/[0.06] mb-8">
          {[
            { label: 'Recall@3', value: '96.08%', change: '+12%', sub: t('landing.benchmark.vs_baseline') },
            { label: 'Full RAG Latency', value: '400ms', change: '-61%', sub: t('landing.benchmark.optimized') },
            { label: 'Cost per Query', value: '.001', change: '-90%', sub: t('landing.benchmark.reduced') },
          ].map((m) => (
            <div key={m.label} className="bg-[var(--bg-primary)] p-6">
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

        {/* Optimization story */}
        <div className="linear-card p-6">
          <h3 className="text-sm font-semibold text-white mb-6">
            {t('landing.benchmark.optimization_story')}
          </h3>
          <div className="space-y-4">
            {[
              { label: 'TTFT', before: '800ms', after: '310ms' },
              { label: t('landing.benchmark.cache_hit_rate'), before: '0%', after: '92%' },
              { label: t('landing.benchmark.cost_per_query'), before: '.01', after: '.001' },
            ].map((item) => (
              <div key={item.label} className="flex justify-between items-center py-2 border-b border-white/[0.04] last:border-0">
                <span className="text-sm text-[var(--text-secondary)]">{item.label}</span>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-[var(--error)] line-through opacity-60 font-mono">{item.before}</span>
                  <span className="text-[var(--text-tertiary)]">&#8594;</span>
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
