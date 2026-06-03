import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

export function HeroSection() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden">
      {/* Multi-layer gradient background */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{ background: 'var(--gradient-hero-bg)' }}
      />

      {/* Subtle noise texture */}
      <div className="absolute inset-0 noise-overlay pointer-events-none" />

      {/* Content */}
      <div className="relative z-10 text-center px-6 max-w-3xl mx-auto pt-12">
        {/* Badge */}
        <div className="inline-flex items-center gap-2 mb-8">
          <span className="linear-tag">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--success)] shadow-[0_0_6px_var(--success)]" />
            {t('landing.hero.badge')}
          </span>
        </div>

        {/* Title with gradient text */}
        <h1 className="hero-title text-5xl md:text-6xl font-bold tracking-[-0.03em] mb-5 leading-[1.1] text-balance">
          {t('landing.hero.title')}
        </h1>

        {/* Subtitle */}
        <p className="text-base md:text-lg text-[var(--text-secondary)] max-w-xl mx-auto mb-10 leading-relaxed text-balance">
          {t('landing.hero.subtitle')}
        </p>

        {/* CTA */}
        <div className="flex gap-3 justify-center mb-16">
          <button
            onClick={() => navigate('/search')}
            className="linear-btn linear-btn-primary px-6 py-2.5"
          >
            {t('landing.hero.cta_search')}
          </button>
          <button
            onClick={() => navigate('/architecture')}
            className="linear-btn linear-btn-secondary px-6 py-2.5"
          >
            {t('landing.hero.cta_architecture')}
          </button>
        </div>

        {/* Metrics row — elevated cards */}
        <div className="flex gap-6 justify-center">
          {[
            { value: t('landing.metrics.recall.value'), label: t('landing.metrics.recall.label') },
            { value: t('landing.metrics.ttft.value'), label: t('landing.metrics.ttft.label') },
            { value: t('landing.metrics.cost.value'), label: t('landing.metrics.cost.label') },
          ].map((m) => (
            <div key={m.label} className="metric-card text-center px-8 py-5">
              <p className="metric-value text-2xl">{m.value}</p>
              <p className="metric-label">{m.label}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
