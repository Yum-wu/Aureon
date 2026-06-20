import { useTranslation } from 'react-i18next';
import { useBenchmark } from '../../hooks/useBenchmark';

const fmtVal = (v: string | number | null, fallback: string) => {
  if (v === null) return fallback;
  const s = String(v);
  return s.includes('ms') || s.includes('%') || s.includes('$') ? s : s;
};

export function FeatureGrid() {
  const { t } = useTranslation();
  const { data: benchmark } = useBenchmark();

  const findMetric = (pat: string) =>
    benchmark?.metrics?.find((m: { label: string; value: string | number }) => m.label.includes(pat))?.value ?? null;

  const recallVal = findMetric('Recall@3');
  const latencyVal = findMetric('Retrieval Latency');
  const ttftVal = findMetric('TTFT');

  // 从 i18n 获取完整的 features 数组，避免 title/desc 索引错位
  const i18nFeatures = t('landing.features', { returnObjects: true }) as Array<{ title: string; desc: string }>;

  const metrics = [
    `${fmtVal(recallVal, '96.5%')} recall`,
    `${fmtVal(ttftVal, '~310ms')} TTFT`,
    '100% detection',
    '192 QA pairs',
    '99 articles / 1214 chunks',
    `${fmtVal(latencyVal, '156ms')} latency`,
  ];

  const features = (i18nFeatures || []).map((f, idx) => ({
    icon: String(idx + 1).padStart(2, '0'),
    title: f.title,
    description: f.desc,
    metric: metrics[idx] || '',
  }));

  return (
    <section className="section-alt relative py-20 px-6">
      <div className="max-w-5xl mx-auto">
        <h2 className="text-2xl font-bold tracking-[-0.02em] mb-2 text-white animate-fade-up">
          {t('landing.features_title')}
        </h2>
        <p className="text-sm text-[var(--text-tertiary)] mb-12 animate-fade-up delay-100">
          {t('landing.features_subtitle')}
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {features.map((feature, idx) => (
            <div key={feature.title} className="feature-card animate-slide-up" style={{ animationDelay: `${idx * 0.1}s` }}>
              <div className="text-xs font-mono text-[var(--accent)] mb-4 opacity-60">
                {feature.icon}
              </div>
              <h3 className="text-sm font-semibold text-white mb-2 tracking-tight">
                {feature.title}
              </h3>
              <p className="text-xs text-[var(--text-secondary)] leading-relaxed mb-4">
                {feature.description}
              </p>
              <div className="pt-3 border-t border-[var(--border-subtle)]">
                <span className="text-xs font-mono text-[var(--accent)]">
                  {feature.metric}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
