import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useBenchmark } from '../../hooks/useBenchmark';

export function BenchmarkSection() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { data: benchmark } = useBenchmark();

  const headlineMetrics = (benchmark?.metrics ?? [])
    .filter((m) => m.customer_facing)
    .sort((a, b) => (a.priority ?? 99) - (b.priority ?? 99))
    .slice(0, 3);

  return (
    <section className="relative py-20 px-6" style={{ background: 'var(--bg-primary)' }}>
      <div
        className="absolute inset-0 pointer-events-none"
        style={{ background: 'var(--gradient-glow)' }}
      />

      <div className="relative max-w-5xl mx-auto text-center">
        <h2 className="text-2xl font-bold tracking-[-0.02em] mb-2 text-[var(--text-primary)] animate-fade-up">
          {t('landing.benchmark.title')}
        </h2>
        <p className="text-base text-[var(--text-secondary)] mb-12 animate-fade-up delay-100">
          {t('landing.benchmark.subtitle')}
        </p>

        {/* Headline stats */}
        <div className="grid grid-cols-3 gap-6 max-w-xl mx-auto mb-12">
          {headlineMetrics.map((m, idx) => (
            <div key={m.label} className="animate-slide-up" style={{ animationDelay: `${idx * 0.08 + 0.2}s` }}>
              <p className="metric-value text-3xl md:text-4xl mb-1">{m.value ?? '—'}</p>
              <p className="text-sm text-[var(--text-secondary)] font-medium">{m.label}</p>
            </div>
          ))}
        </div>

        {/* CTA */}
        <button
          onClick={() => navigate('/architecture')}
          className="glow-btn-outline px-7 py-3 text-sm"
        >
          {t('landing.benchmark.view_full')}
        </button>
      </div>
    </section>
  );
}
