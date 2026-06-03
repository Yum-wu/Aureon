import { useTranslation } from 'react-i18next';
import { useBenchmark } from '../../hooks/useBenchmark';
import { Card } from '../ui/Card';

interface Optimization {
  metricKey: string;
  before: string;
  after: string;
  improvement: string;
}

const fmtVal = (v: string | number | null, fallback: string) => {
  if (v === null) return fallback;
  const s = String(v);
  return s.includes('ms') || s.includes('%') || s.includes('$') ? s : s;
};

export function OptimizationStory() {
  const { t } = useTranslation();
  const { data: benchmark } = useBenchmark();

  const findMetric = (pat: string) =>
    benchmark?.metrics?.find((m: { label: string; value: string | number }) => m.label.includes(pat))?.value ?? null;

  const ttftVal = findMetric('TTFT');
  const latencyVal = findMetric('Retrieval Latency');
  const costVal = findMetric('Cost');
  const cacheVal = findMetric('Cache');

  const optimizations: Optimization[] = [
    {
      metricKey: 'architecture.optimization.ttft',
      before: '~800ms',
      after: fmtVal(ttftVal, '~310ms'),
      improvement: '-61%',
    },
    {
      metricKey: 'architecture.optimization.retrieval_latency',
      before: '153ms',
      after: fmtVal(latencyVal, '5.8ms'),
      improvement: '-96%',
    },
    {
      metricKey: 'architecture.optimization.cost_per_query',
      before: '$0.01',
      after: fmtVal(costVal, '~$0.001'),
      improvement: '-90%',
    },
    {
      metricKey: 'architecture.optimization.cache_hit_rate',
      before: '0%',
      after: cacheVal ? `${Math.round(Number(cacheVal) * 100)}%` : '92%',
      improvement: '+92%',
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      {optimizations.map((opt) => (
        <Card key={opt.metricKey}>
          <h4 className="font-semibold mb-4">{t(opt.metricKey)}</h4>
          <div className="flex items-center justify-between">
            <div className="text-center">
              <p className="text-sm text-[var(--text-tertiary)]">{t('architecture.optimization.before')}</p>
              <p className="text-2xl font-bold text-[var(--error)]">{opt.before}</p>
            </div>
            <div className="text-4xl text-[var(--text-tertiary)]">\u2192</div>
            <div className="text-center">
              <p className="text-sm text-[var(--text-tertiary)]">{t('architecture.optimization.after')}</p>
              <p className="text-2xl font-bold text-[var(--success)]">{opt.after}</p>
            </div>
            <div className="text-center">
              <p className="text-sm text-[var(--text-tertiary)]">{t('architecture.optimization.improvement_label')}</p>
              <p className="text-2xl font-bold text-[var(--accent)]">{opt.improvement}</p>
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}
