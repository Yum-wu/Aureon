import { HeroSection } from '../components/landing/HeroSection';
import { FeatureGrid } from '../components/landing/FeatureGrid';
import { BenchmarkSection } from '../components/landing/BenchmarkSection';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { LanguageSwitcher } from '../i18n/LanguageSwitcher';

export function Landing() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  return (
    <div className="min-h-screen">
      {/* Minimal top bar */}
      <header className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 h-12 border-b border-[var(--border)] bg-[var(--bg-primary)]/80 backdrop-blur-sm">
        <span className="text-sm font-semibold text-white/90 tracking-tight">Aureon</span>
        <div className="flex items-center gap-3">
          <LanguageSwitcher />
          <button
            onClick={() => navigate('/search')}
            className="linear-btn linear-btn-secondary !py-1 !px-3 !text-xs"
          >
            {t('landing.hero.cta_search')}
          </button>
          <button
            onClick={() => navigate('/login')}
            className="linear-btn linear-btn-primary !py-1 !px-3 !text-xs"
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
