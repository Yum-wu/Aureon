import { useTranslation } from 'react-i18next';

export function FeatureGrid() {
  const { t } = useTranslation();

  const features = [
    {
      icon: '01',
      title: t('landing.features.0.title'),
      description: t('landing.features.0.desc'),
      metric: '96.08% recall',
    },
    {
      icon: '02',
      title: t('landing.features.1.title'),
      description: t('landing.features.1.desc'),
      metric: '310ms TTFT',
    },
    {
      icon: '03',
      title: t('landing.features.2.title'),
      description: t('landing.features.2.desc'),
      metric: '3 sources avg',
    },
    {
      icon: '04',
      title: t('landing.features.3.title'),
      description: t('landing.features.3.desc'),
      metric: 'Real-time',
    },
    {
      icon: '05',
      title: t('landing.features.4.title'),
      description: t('landing.features.4.desc'),
      metric: 'Multi-format',
    },
    {
      icon: '06',
      title: t('landing.features.5.title'),
      description: t('landing.features.5.desc'),
      metric: '24h setup',
    },
  ];

  return (
    <section className="py-20 px-6 bg-[var(--bg-primary)]">
      <div className="max-w-5xl mx-auto">
        <h2 className="text-2xl font-bold tracking-[-0.02em] mb-2 text-white">
          {t('landing.features_title')}
        </h2>
        <p className="text-sm text-[var(--text-tertiary)] mb-12">
          {t('landing.features_title')}
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-px bg-white/[0.06]">
          {features.map((feature) => (
            <div
              key={feature.title}
              className="bg-[var(--bg-primary)] p-6 group"
            >
              <div className="text-xs font-mono text-[var(--text-tertiary)] mb-4">
                {feature.icon}
              </div>
              <h3 className="text-sm font-semibold text-white mb-2 tracking-tight">
                {feature.title}
              </h3>
              <p className="text-xs text-[var(--text-secondary)] leading-relaxed mb-4">
                {feature.description}
              </p>
              <div className="pt-3 border-t border-white/[0.06]">
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
