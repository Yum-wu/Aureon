import { useTranslation } from 'react-i18next';
import { Card } from '../ui/Card';

export function FeatureGrid() {
  const { t } = useTranslation();

  const features = [
    {
      icon: '🔍',
      title: t('landing.features.0.title'),
      description: t('landing.features.0.desc'),
      metric: '96.08% recall',
    },
    {
      icon: '⚡',
      title: t('landing.features.1.title'),
      description: t('landing.features.1.desc'),
      metric: '310ms TTFT',
    },
    {
      icon: '📚',
      title: t('landing.features.2.title'),
      description: t('landing.features.2.desc'),
      metric: '3 sources avg',
    },
    {
      icon: '📊',
      title: t('landing.features.3.title'),
      description: t('landing.features.3.desc'),
      metric: 'Real-time',
    },
    {
      icon: '📄',
      title: t('landing.features.4.title'),
      description: t('landing.features.4.desc'),
      metric: 'Multi-format',
    },
    {
      icon: '🚀',
      title: t('landing.features.5.title'),
      description: t('landing.features.5.desc'),
      metric: '24h setup',
    },
  ];

  return (
    <section className="py-16 px-4">
      <h2 className="text-3xl font-bold text-center mb-12">{t('landing.features_title')}</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 max-w-6xl mx-auto">
        {features.map((feature) => (
          <Card key={feature.title} hover>
            <div className="text-3xl mb-4">{feature.icon}</div>
            <h3 className="text-xl font-semibold mb-2">{feature.title}</h3>
            <p className="text-[var(--text-secondary)] mb-4">{feature.description}</p>
            <p className="text-sm text-[var(--accent)]">{feature.metric}</p>
          </Card>
        ))}
      </div>
    </section>
  );
}
