import { HeroSection } from '../components/landing/HeroSection';
import { FeatureGrid } from '../components/landing/FeatureGrid';
import { BenchmarkSection } from '../components/landing/BenchmarkSection';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

export function Landing() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  return (
    <div className="min-h-screen bg-[var(--bg-primary)]">
      {/* Minimal top bar */}
      <header className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 h-12 border-b border-white/[0.06] bg-[#0A0A0A]/80 backdrop-blur-sm">
        <span className="text-sm font-semibold text-white/90 tracking-tight">Aureon</span>
        <div className="flex items-center gap-3">
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

      <div className="linear-divider" />
      <FeatureGrid />

      <div className="linear-divider" />
      <BenchmarkSection />

      {/* Footer */}
      <footer className="py-10 px-6 border-t border-white/[0.06]">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <span className="text-xs text-white/20">Aureon</span>
          <span className="text-xs text-white/20">Built by Enterprise AI Systems Studio</span>
        </div>
      </footer>
    </div>
  );
}
