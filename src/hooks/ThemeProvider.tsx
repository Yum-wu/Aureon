import { useState, useEffect, useCallback, type ReactNode } from 'react';
import { ThemeContext, type Theme } from './useTheme';

/* ── Dark theme variable overrides (cssText batch) ── */
const DARK_VARS = `
--seed-bg: #0F1011;
--seed-fg: #EDEDF0;
--seed-primary: #E0A820;
--seed-accent: #7170FF;
--seed-surface: #191A1B;
--seed-radius: 10px;
--brand-50: oklch(0.20 0.03 78);
--brand-100: oklch(0.25 0.06 76);
--brand-200: oklch(0.32 0.10 72);
--brand-300: oklch(0.40 0.14 68);
--brand-400: oklch(0.50 0.16 65);
--brand-500: oklch(0.62 0.17 65);
--brand-600: oklch(0.72 0.16 68);
--brand-700: oklch(0.80 0.13 72);
--brand-800: oklch(0.87 0.10 75);
--brand-900: oklch(0.93 0.06 78);
--accent-50: oklch(0.20 0.04 270);
--accent-100: oklch(0.28 0.08 270);
--accent-200: oklch(0.38 0.13 270);
--accent-300: oklch(0.50 0.17 270);
--accent-400: oklch(0.62 0.19 270);
--accent-500: oklch(0.70 0.18 270);
--accent-600: oklch(0.78 0.15 270);
--accent-700: oklch(0.85 0.10 270);
--bg: #0F1011;
--bg-alt: #141516;
--surface: #191A1B;
--surface-raised: #1F2022;
--surface-inset: #0A0A0B;
--fg: #EDEDF0;
--fg-secondary: #B0B0BA;
--fg-tertiary: #82828E;
--fg-muted: #5C5C68;
--fg-subtle: #3A3A44;
--border: rgba(237, 237, 240, 0.08);
--border-hover: rgba(237, 237, 240, 0.15);
--border-subtle: rgba(237, 237, 240, 0.04);
--border-strong: rgba(237, 237, 240, 0.20);
--success: #22C55E;
--success-bg: oklch(0.20 0.06 145);
--warning: #F59E0B;
--warning-bg: oklch(0.20 0.06 80);
--error: #EF4444;
--error-bg: oklch(0.20 0.06 25);
--info: #7170FF;
--info-bg: oklch(0.20 0.04 270);
--shadow-xs: 0 1px 2px rgba(0,0,0,0.20);
--shadow-sm: 0 1px 3px rgba(0,0,0,0.30), 0 1px 2px rgba(0,0,0,0.20);
--shadow-md: 0 4px 6px -1px rgba(0,0,0,0.30), 0 2px 4px -2px rgba(0,0,0,0.20);
--shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.30), 0 4px 6px -4px rgba(0,0,0,0.20);
--shadow-xl: 0 20px 25px -5px rgba(0,0,0,0.40), 0 8px 10px -6px rgba(0,0,0,0.20);
--is-dark: 1;
--text-primary: #EDEDF0;
--text-secondary: #B0B0BA;
--text-tertiary: #82828E;
--bg-primary: #0F1011;
--bg-secondary: #191A1B;
--bg-tertiary: #1F2022;
--bg-elevated: #1A1B1D;
--bg-surface: #0A0A0B;
--accent: #7170FF;
--accent-soft: rgba(113, 112, 255, 0.10);
--accent-glow: rgba(113, 112, 255, 0.05);
--accent-hover: #8180FF;
--gradient-glow: radial-gradient(ellipse 60% 40% at 50% 0%, rgba(113,112,255,0.07) 0%, transparent 70%);
--gradient-glow-strong: radial-gradient(ellipse 50% 50% at 50% 0%, rgba(113,112,255,0.12) 0%, transparent 70%);
--gradient-section: linear-gradient(180deg, #0F1011 0%, #141416 50%, #0F1011 100%);
--gradient-card: linear-gradient(180deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%);
--gradient-hero-bg: radial-gradient(ellipse 80% 50% at 50% -10%, rgba(113,112,255,0.08) 0%, transparent 60%),
                    radial-gradient(ellipse 40% 30% at 20% 20%, rgba(167,139,250,0.04) 0%, transparent 50%),
                    radial-gradient(ellipse 40% 30% at 80% 20%, rgba(96,165,250,0.03) 0%, transparent 50%);
`;

/* ── Light theme: clear all inline overrides ── */
const LIGHT_VARS = '';

/* ── Apply theme to DOM ── */
function applyTheme(theme: Theme) {
  const el = document.documentElement;
  el.setAttribute('data-theme', theme);
  el.style.cssText = theme === 'dark' ? DARK_VARS : LIGHT_VARS;
  el.style.colorScheme = theme;
}

/* ── Get initial theme from localStorage or system preference ── */
function getInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'light';
  try {
    const stored = localStorage.getItem('aureon-theme');
    if (stored === 'dark' || stored === 'light') return stored;
  } catch { /* localStorage unavailable */ }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/* ── Provider ── */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(getInitialTheme);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    applyTheme(t);
    try { localStorage.setItem('aureon-theme', t); } catch { /* ignore */ }
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(theme === 'light' ? 'dark' : 'light');
  }, [theme, setTheme]);

  /* Apply on mount */
  useEffect(() => {
    applyTheme(theme);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /* Listen for system preference changes */
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => {
      if (!localStorage.getItem('aureon-theme')) {
        setTheme(e.matches ? 'dark' : 'light');
      }
    };
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [setTheme]);

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}
