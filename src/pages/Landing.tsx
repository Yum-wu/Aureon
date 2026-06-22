import { HeroSection } from '../components/landing/HeroSection';
import { FeatureGrid } from '../components/landing/FeatureGrid';
import { BenchmarkSection } from '../components/landing/BenchmarkSection';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { LanguageSwitcher } from '../i18n/LanguageSwitcher';
import { ThemeToggle } from '../components/ThemeToggle';

export function Landing() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  return (
    <div className="min-h-screen">
      {/* Minimal top bar */}
      <header className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 h-12 border-b border-[var(--border-subtle)] glass-strong">
        <span className="text-sm font-extrabold tracking-tight" style={{ color: 'var(--accent)' }}>Aureon</span>
        <div className="flex items-center gap-3">
          <ThemeToggle />
          <LanguageSwitcher />
          <button
            onClick={() => navigate('/search')}
            className="glow-btn-outline !py-1 !px-3 !text-xs"
          >
            {t('landing.hero.cta_search')}
          </button>
          <button
            onClick={() => navigate('/login')}
            className="glow-btn !py-1 !px-3 !text-xs"
          >
            {t('app.nav.admin')}
          </button>
        </div>
      </header>

      <HeroSection />

      {/* Gradient divider between sections */}
      <div className="gradient-divider" />
      <FeatureGrid />

      <div className="gradient-divider" />
      <BenchmarkSection />

      
      {/* Trust bar */}
      <section className="py-16 px-6">
        <div className="max-w-5xl mx-auto text-center">
          <p className="text-xs text-[var(--text-tertiary)] uppercase tracking-widest mb-8">
            {t('landing.trust.title')}
          </p>
          <div className="flex items-center justify-center gap-10 flex-wrap opacity-40">
            {(t('landing.trust.badges', { returnObjects: true }) as string[]).map((badge) => (
              <span key={badge} className="text-sm font-medium text-[var(--text-secondary)] tracking-wide">
                {badge}
              </span>
            ))}
          </div>
          <div className="mt-10 grid grid-cols-2 md:grid-cols-4 gap-6 max-w-2xl mx-auto">
            {[
              { value: '390+', label: t('landing.trust.tests', { defaultValue: 'Tests' }) },
              { value: '99', label: t('landing.trust.articles', { defaultValue: 'Articles' }) },
              { value: '1214', label: t('landing.trust.chunks', { defaultValue: 'Chunks Indexed' }) },
              { value: '24h', label: t('landing.trust.deploy', { defaultValue: 'Deploy Time' }) },
            ].map((item) => (
              <div key={item.label} className="text-center">
                <p className="text-xl font-bold text-[var(--text-primary)] tabular-nums">{item.value}</p>
                <p className="text-xs text-[var(--text-tertiary)] mt-1">{item.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
      {/* Footer */}
      <footer className="py-10 px-6 border-t border-[var(--border-subtle)]">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <span className="text-xs text-[var(--text-tertiary)]">Aureon</span>
          <span className="text-xs text-[var(--text-tertiary)]">Built by Enterprise AI Systems Studio</span>
        </div>
      </footer>
    </div>
  );
}
