import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

const fmt = (n: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n);

const fmtPct = (n: number) => `${Math.round(n)}%`;

export function ROICalculator() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  const fmtMonths = (n: number) => {
    if (n < 1) return t('landing.roi.payback_less_than_month');
    return t('landing.roi.payback_month', { count: Math.round(n) });
  };
  const [teamSize, setTeamSize] = useState(50);
  const [searchHours, setSearchHours] = useState(5);
  const [hourlyRate, setHourlyRate] = useState(75);

  // ponytail: 50% savings rate is conservative (industry reports 26-55%)
  // ponytail: $15/user/mo is an estimate; real pricing depends on volume
  const workWeeks = 50;
  const savingsRate = 0.5;
  const annualHoursWasted = teamSize * searchHours * workWeeks;
  const annualCostWasted = annualHoursWasted * hourlyRate;
  const annualSavings = annualCostWasted * savingsRate;
  const aureonCost = teamSize * 15 * 12;
  const netSavings = annualSavings - aureonCost;
  const roi = aureonCost > 0 ? (netSavings / aureonCost) * 100 : 0;
  const payback = annualSavings > 0 ? aureonCost / (annualSavings / 12) : 0;

  return (
    <section id="roi" className="relative py-20 px-6 section-glow">
      <div className="relative max-w-5xl mx-auto">
        <h2 className="hero-title text-2xl md:text-3xl font-bold tracking-[-0.02em] mb-2 text-center animate-fade-up">
          {t('landing.roi.title')}
        </h2>
        <p className="text-base text-[var(--text-secondary)] text-center mb-12 max-w-xl mx-auto animate-fade-up delay-100">
          {t('landing.roi.subtitle')}
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 animate-fade-up delay-200">
          {/* Sliders */}
          <div className="metric-card p-6 md:p-8 space-y-8">
            <SliderField
              id="roi-team-size"
              label={t('landing.roi.team_size')}
              value={teamSize}
              min={10}
              max={1000}
              step={10}
              format={(v) => `${v}`}
              onChange={setTeamSize}
            />
            <SliderField
              id="roi-search-hours"
              label={t('landing.roi.search_hours')}
              value={searchHours}
              min={1}
              max={20}
              step={1}
              format={(v) => `${v}h`}
              onChange={setSearchHours}
            />
            <SliderField
              id="roi-hourly-rate"
              label={t('landing.roi.hourly_rate')}
              value={hourlyRate}
              min={20}
              max={200}
              step={5}
              format={(v) => fmt(v)}
              onChange={setHourlyRate}
            />
          </div>

          {/* Results */}
          <div className="metric-card p-6 md:p-8 flex flex-col justify-center">
            <p className="text-xs text-[var(--text-tertiary)] uppercase tracking-widest mb-1">
              {t('landing.roi.annual_savings')}
            </p>
            <p className="text-4xl md:text-5xl font-bold tracking-[-0.03em] text-[var(--text-primary)] mb-6"
               style={{ fontFamily: 'var(--font-display)' }}>
              {fmt(Math.max(0, netSavings))}
            </p>

            <div className="grid grid-cols-2 gap-4 mb-6 text-sm">
              <div>
                <p className="text-[var(--text-tertiary)]">{t('landing.roi.roi')}</p>
                <p className="text-lg font-semibold text-[var(--text-primary)]">{roi > 0 ? fmtPct(roi) : '—'}</p>
              </div>
              <div>
                <p className="text-[var(--text-tertiary)]">{t('landing.roi.payback')}</p>
                <p className="text-lg font-semibold text-[var(--text-primary)]">{payback > 0 ? fmtMonths(payback) : '—'}</p>
              </div>
            </div>

            <div className="flex items-center gap-3 text-xs text-[var(--text-tertiary)] mb-6">
              <span className="w-2 h-2 rounded-full bg-[var(--success)]" />
              {t('landing.roi.disclaimer')}
            </div>

            <button
              onClick={() => navigate('/search')}
              className="glow-btn w-full text-sm justify-center"
            >
              {t('landing.roi.cta')}
            </button>
          </div>
        </div>

        {/* Before/After */}
        <div className="grid grid-cols-2 gap-4 max-w-lg mx-auto mt-8 animate-fade-up delay-300">
          <div className="text-center p-4 rounded-lg" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
            <p className="text-xs text-[var(--text-tertiary)] uppercase tracking-widest mb-1">{t('landing.roi.without')}</p>
            <p className="text-xl font-bold text-[var(--text-secondary)]">{fmt(annualCostWasted)}</p>
            <p className="text-xs text-[var(--text-tertiary)]">{annualHoursWasted.toLocaleString()} {t('landing.roi.hours_per_year')}</p>
          </div>
          <div className="text-center p-4 rounded-lg" style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderColor: 'color-mix(in srgb, var(--success) 40%, var(--border))' }}>
            <p className="text-xs text-[var(--text-tertiary)] uppercase tracking-widest mb-1">{t('landing.roi.with')}</p>
            <p className="text-xl font-bold text-[var(--success)]">{fmt(Math.max(0, netSavings))}</p>
            <p className="text-xs text-[var(--text-tertiary)]">{t('landing.roi.savings_per_year')}</p>
          </div>
        </div>
      </div>
    </section>
  );
}

function SliderField({
  id, label, value, min, max, step, format, onChange,
}: {
  id: string;
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format: (v: number) => string;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <label htmlFor={id} className="text-sm text-[var(--text-primary)] font-medium">{label}</label>
        <span className="text-sm font-semibold text-[var(--seed-accent)] tabular-nums">{format(value)}</span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="roi-slider w-full"
      />
      <div className="flex justify-between text-xs text-[var(--text-tertiary)] mt-1">
        <span>{format(min)}</span>
        <span>{format(max)}</span>
      </div>
    </div>
  );
}
