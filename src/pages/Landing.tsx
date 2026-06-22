import { HeroSection } from '../components/landing/HeroSection';
import { FeatureGrid } from '../components/landing/FeatureGrid';
import { BenchmarkSection } from '../components/landing/BenchmarkSection';
import { useTranslation } from 'react-i18next';
import { LandingNavBar } from '../components/LandingNavBar';

export function Landing() {
  const { t } = useTranslation();

  return (
    <div className="min-h-screen">
      <LandingNavBar />

      <HeroSection />

      {/* Gradient divider between sections */}
      <div className="gradient-divider" />
      <div id="features">
        <FeatureGrid />
      </div>

      <div className="gradient-divider" />
      <div id="benchmark">
        <BenchmarkSection />
      </div>

      {/* Trust bar */}
      <section id="trust" className="py-16 px-6">
        <div className="max-w-5xl mx-auto text-center">
          <p className="text-sm text-[var(--text-secondary)] uppercase tracking-widest mb-8 font-medium">
            {t('landing.trust.title')}
          </p>
          <div className="flex items-center justify-center gap-10 flex-wrap opacity-60">
            {(t('landing.trust.badges', { returnObjects: true }) as string[]).map((badge) => (
              <span key={badge} className="text-base font-medium text-[var(--text-primary)] tracking-wide">
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
                <p className="text-3xl font-bold text-[var(--text-primary)] tabular-nums">{item.value}</p>
                <p className="text-sm text-[var(--text-secondary)] mt-2 font-medium">{item.label}</p>
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
