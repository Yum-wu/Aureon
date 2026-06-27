import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ThemeToggle } from './ThemeToggle';
import { LanguageSwitcher } from '../i18n/LanguageSwitcher';

/* ── Anchor links for landing page sections ── */
const ANCHOR_LINKS = [
  { id: 'features', labelKey: 'landing.features_title' },
  { id: 'benchmark', labelKey: 'landing.benchmark.title' },
  { id: 'roi', labelKey: 'landing.roi.title' },
  { id: 'trust', labelKey: 'landing.trust.title' },
] as const;

/* ── Landing page navigation — Canvas design system style ── */
export function LandingNavBar() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [activeSection, setActiveSection] = useState<string | null>(null);

  /* Intersection observer for active section tracking */
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveSection(entry.target.id);
          }
        }
      },
      { rootMargin: '-20% 0px -70% 0px', threshold: 0 }
    );

    ANCHOR_LINKS.forEach(({ id }) => {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    });

    return () => observer.disconnect();
  }, []);

  const scrollTo = useCallback((id: string) => {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, []);

  return (
    <nav className="landing-nav" role="navigation" aria-label="Landing navigation">
      {/* Brand */}
      <button
        onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
        className="landing-nav-brand"
      >
        Aureon
      </button>

      {/* Center anchor links */}
      <ul className="landing-nav-links">
        {ANCHOR_LINKS.map(({ id, labelKey }) => (
          <li key={id}>
            <button
              onClick={() => scrollTo(id)}
              className={`landing-nav-link ${activeSection === id ? 'landing-nav-link-active' : ''}`}
            >
              {t(labelKey, { defaultValue: id })}
            </button>
          </li>
        ))}
      </ul>

      {/* Right actions */}
      <div className="landing-nav-actions">
        <ThemeToggle />
        <LanguageSwitcher />
        <button
          onClick={() => navigate('/search')}
          className="glow-btn-outline !py-1.5 !px-4 !text-xs"
        >
          {t('landing.hero.cta_search')}
        </button>
        <button
          onClick={() => navigate('/login')}
          className="glow-btn !py-1.5 !px-4 !text-xs"
        >
          {t('app.nav.admin')}
        </button>
      </div>
    </nav>
  );
}
