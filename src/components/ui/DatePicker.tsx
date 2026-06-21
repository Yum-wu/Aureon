import { useTranslation } from 'react-i18next';

interface DatePickerProps {
  value: string;
  onChange: (value: string) => void;
  placeholderKey: string;
  ariaLabelKey: string;
}

export function DatePicker({ value, onChange, placeholderKey, ariaLabelKey }: DatePickerProps) {
  const { t, i18n } = useTranslation();
  
  return (
    <div className="relative">
      <input
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label={t(ariaLabelKey)}
        lang={i18n.language}
        className="px-3 py-1.5 text-xs rounded-lg border border-[var(--border)] bg-[var(--bg-tertiary)] text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] [color-scheme:dark]"
      />
      {!value && (
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[10px] text-[var(--text-tertiary)] pointer-events-none">
          {t(placeholderKey)}
        </span>
      )}
    </div>
  );
}