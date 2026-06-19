import { useTranslation } from 'react-i18next';
import { useBenchmark } from '../hooks/useBenchmark';
import { ArchitectureFlow } from '../components/architecture/ArchitectureFlow';
import { OptimizationStory } from '../components/architecture/OptimizationStory';
import { MetricGrid } from '../components/dashboard/MetricGrid';

export function Architecture() {
  const { t } = useTranslation();
  const { data: benchmark } = useBenchmark();

  const findMetric = (pat: string) =>
    benchmark?.metrics?.find((m: { label: string; value: string | number }) => m.label.includes(pat))?.value ?? null;

  const recallVal = findMetric('Recall@3');
  const ttftVal = findMetric('TTFT');

  const fmtVal = (v: string | number | null, fallback: string) => {
    if (v === null) return fallback;
    const s = String(v);
    return s.includes('ms') || s.includes('%') || s.includes('$') ? s : `${s}`;
  };

  const metrics = [
    { label: 'Recall@3 (Hybrid)', value: fmtVal(recallVal, '96.5%') },
    { label: 'MRR', value: fmtVal(findMetric('MRR'), '0.968') },
    { label: 'Context Precision', value: fmtVal(findMetric('Context Precision'), '94.4%') },
    { label: 'Faithfulness', value: fmtVal(findMetric('Faithfulness'), '0.976') },
    { label: 'TTFT P50', value: fmtVal(ttftVal, '590ms') },
    { label: 'E2E P50', value: fmtVal(findMetric('E2E'), '856ms') },
  ];

  return (
    <div className="min-h-screen bg-[var(--bg-primary)]">
      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">{t('architecture.title')}</h1>
          <p className="text-[var(--text-secondary)]">
            {t('architecture.subtitle')}
          </p>
        </div>

        <div className="space-y-12">
          <section>
            <h2 className="text-2xl font-semibold mb-6">{t('architecture.runtime_metrics')}</h2>
            <MetricGrid metrics={metrics} columns={3} />
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-6">{t('architecture.rag_pipeline')}</h2>
            <ArchitectureFlow />
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-6">{t('architecture.optimization_story')}</h2>
            <OptimizationStory />
          </section>
        </div>
      </div>
    </div>
  );
}
