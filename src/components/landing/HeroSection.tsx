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

      {/* Ambient glow decorations */}
      <div className="ambient-glow ambient-glow-accent w-[500px] h-[500px] top-[10%] left-[50%] -translate-x-1/2" />
      <div className="ambient-glow ambient-glow-purple w-[300px] h-[300px] top-[25%] left-[20%]" />

      {/* Subtle noise texture */}
      <div className="absolute inset-0 noise-overlay pointer-events-none" />

      {/* Grid pattern overlay */}
      <div
        className="absolute inset-0 pointer-events-none opacity-[0.03]"
        style={{
          backgroundImage: `linear-gradient(var(--border) 1px, transparent 1px), linear-gradient(90deg, var(--border) 1px, transparent 1px)`,
          backgroundSize: '60px 60px',
        }}
      />

      {/* Content */}
      <div className="relative z-10 text-center px-6 max-w-3xl mx-auto pt-12">
        {/* Badge */}
        <div className="inline-flex items-center gap-2 mb-8 animate-fade-up">
          <span className="linear-tag">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--success)] shadow-[0_0_6px_var(--success)]" />
            {t('landing.hero.badge')}
          </span>
        </div>

        {/* Title with gradient text */}
        <h1 className="hero-title text-5xl md:text-7xl font-bold tracking-[-0.03em] mb-6 leading-[1.05] text-balance"
            style={{ fontFamily: 'var(--font-display)' }}>
          {t('landing.hero.title')}
        </h1>

        {/* Subtitle */}
        <p className="text-base md:text-lg text-[var(--text-secondary)] max-w-xl mx-auto mb-10 leading-relaxed text-balance animate-fade-up delay-100">
          {t('landing.hero.subtitle')}
        </p>

        {/* CTA */}
        <div className="flex gap-3 justify-center mb-16 animate-fade-up delay-200">
          <button
            onClick={() => navigate('/search')}
            className="glow-btn px-7 py-3 text-sm"
          >
            {t('landing.hero.cta_search')}
          </button>
          <button
            onClick={() => navigate('/architecture')}
            className="glow-btn-outline px-7 py-3 text-sm"
          >
            {t('landing.hero.cta_architecture')}
          </button>
        </div>

        {/* Value props — checkmark row */}
        <div className="flex flex-wrap gap-x-8 gap-y-3 justify-center animate-fade-up delay-300">
          {(t('landing.hero.values', { returnObjects: true }) as string[]).map((v: string) => (
            <div key={v} className="flex items-center gap-2">
              <span className="w-4 h-4 rounded-full bg-[var(--success)]/20 flex items-center justify-center flex-shrink-0">
                <svg className="w-2.5 h-2.5 text-[var(--success)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </span>
              <span className="text-sm text-[var(--text-secondary)]">{v}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}