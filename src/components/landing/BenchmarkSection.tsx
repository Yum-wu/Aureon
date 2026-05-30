import { useTranslation } from 'react-i18next';
import { Card } from '../ui/Card';
import { MetricCard } from '../ui/MetricCard';

export function BenchmarkSection() {
  const { t } = useTranslation();

  return (
    <section className="py-16 px-4 bg-[var(--bg-secondary)]">
      <h2 className="text-3xl font-bold text-center mb-4">{t('landing.benchmark.title')}</h2>
      <p className="text-[var(--text-secondary)] text-center mb-12">
        {t('landing.benchmark.subtitle')}
      </p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-4xl mx-auto">
        <MetricCard
          label="Recall@3"
          value="96.08%"
          change={12}
          changeLabel={t('landing.benchmark.vs_baseline')}
        />
        <MetricCard
          label="Full RAG Latency"
          value="400"
          suffix="ms"
          change={-61}
          changeLabel={t('landing.benchmark.optimized')}
        />
        <MetricCard
          label="Cost per Query"
          value="$0.001"
          change={-90}
          changeLabel={t('landing.benchmark.reduced')}
        />
      </div>

      <div className="mt-12 max-w-4xl mx-auto">
        <Card>
          <h3 className="text-lg font-semibold mb-4">{t('landing.benchmark.optimization_story')}</h3>
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-[var(--text-secondary)]">TTFT</span>
              <div>
                <span className="text-[var(--error)] line-through mr-2">800ms</span>
                <span className="text-[var(--success)]">310ms</span>
              </div>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-[var(--text-secondary)]">{t('landing.benchmark.cache_hit_rate')}</span>
              <div>
                <span className="text-[var(--error)] line-through mr-2">0%</span>
                <span className="text-[var(--success)]">92%</span>
              </div>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-[var(--text-secondary)]">{t('landing.benchmark.cost_per_query')}</span>
              <div>
                <span className="text-[var(--error)] line-through mr-2">$0.01</span>
                <span className="text-[var(--success)]">$0.001</span>
              </div>
            </div>
          </div>
        </Card>
      </div>
    </section>
  );
}
