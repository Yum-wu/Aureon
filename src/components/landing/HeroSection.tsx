import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Badge';

export function HeroSection() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  return (
    <section className="py-24 px-4 text-center">
      <Badge variant="success">{t('landing.hero.badge')}</Badge>

      <h1 className="text-5xl font-bold mt-6 mb-4">
        {t('landing.hero.title')}
      </h1>

      <p className="text-[var(--text-secondary)] text-xl max-w-2xl mx-auto mb-8">
        {t('landing.hero.subtitle')}
      </p>

      <div className="flex gap-8 justify-center mb-10">
        <div>
          <p className="text-4xl font-bold text-[var(--accent)]">{t('landing.metrics.recall.value')}</p>
          <p className="text-[var(--text-secondary)] text-sm">{t('landing.metrics.recall.label')}</p>
        </div>
        <div>
          <p className="text-4xl font-bold text-[var(--accent)]">{t('landing.metrics.ttft.value')}</p>
          <p className="text-[var(--text-secondary)] text-sm">{t('landing.metrics.ttft.label')}</p>
        </div>
        <div>
          <p className="text-4xl font-bold text-[var(--accent)]">{t('landing.metrics.cost.value')}</p>
          <p className="text-[var(--text-secondary)] text-sm">{t('landing.metrics.cost.label')}</p>
        </div>
      </div>

      <div className="flex gap-4 justify-center">
        <Button size="lg" onClick={() => navigate('/search')}>
          {t('landing.hero.cta_search')}
        </Button>
        <Button variant="secondary" size="lg" onClick={() => navigate('/architecture')}>
          {t('landing.hero.cta_architecture')}
        </Button>
      </div>
    </section>
  );
}
