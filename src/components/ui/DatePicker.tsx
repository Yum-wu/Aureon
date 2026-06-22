/**
 * DatePicker — i18n 友好的日期选择器
 *
 * 用 react-day-picker + date-fns 替代原生 <input type="date">，
 * 原生控件受操作系统语言控制，无法被应用 i18n 覆盖。
 *
 * 特性：
 * - 月份/周几/格式完全跟随 i18n.language
 * - 点击外部自动关闭
 * - 键盘可访问（Esc 关闭）
 * - 适配设计 token 暗色主题
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { DayPicker } from 'react-day-picker';
import {
  format,
  parseISO,
  isValid,
  type Locale,
} from 'date-fns';
import { enUS, zhCN } from 'date-fns/locale';
import { Calendar, X } from 'lucide-react';

interface DatePickerProps {
  value: string; // ISO 日期字符串 yyyy-MM-dd，空字符串表示未选
  onChange: (value: string) => void;
  /** i18n key，用作占位提示 */
  placeholderKey: string;
  /** i18n key，用作 aria-label */
  ariaLabelKey: string;
  /** 可选最大日期 */
  maxDate?: string;
  /** 可选最小日期 */
  minDate?: string;
}

/** 按 i18n.language 取 date-fns locale */
function pickLocale(lang: string): Locale {
  if (!lang) return enUS;
  return lang.toLowerCase().startsWith('zh') ? zhCN : enUS;
}

/** 安全解析 ISO 日期 */
function parseSafe(iso?: string): Date | undefined {
  if (!iso) return undefined;
  const d = parseISO(iso);
  return isValid(d) ? d : undefined;
}

export function DatePicker({
  value,
  onChange,
  placeholderKey,
  ariaLabelKey,
  maxDate,
  minDate,
}: DatePickerProps) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const locale = pickLocale(i18n.language);
  const selected = parseSafe(value);
  const maxD = parseSafe(maxDate);
  const minD = parseSafe(minDate);

  // 点击外部关闭
  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', handleClick);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handleClick);
      document.removeEventListener('keydown', handleKey);
    };
  }, [open]);

  const handleSelect = useCallback((date: Date | undefined) => {
    if (date) {
      // 统一输出 ISO yyyy-MM-dd（本地时区，避免 UTC 偏移）
      const y = date.getFullYear();
      const m = String(date.getMonth() + 1).padStart(2, '0');
      const d = String(date.getDate()).padStart(2, '0');
      onChange(`${y}-${m}-${d}`);
      setOpen(false);
    } else if (value) {
      // 清空：点已选日期会触发 undefined
      onChange('');
      setOpen(false);
    }
  }, [onChange, value]);

  // 展示文本：已选 → 本地化格式；未选 → placeholder
  const displayText = selected
    ? format(selected, 'P', { locale })
    : t(placeholderKey);

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={t(ariaLabelKey)}
        aria-expanded={open}
        aria-haspopup="dialog"
        className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-[var(--border)] bg-[var(--bg-tertiary)] text-[var(--text-primary)] hover:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] min-w-[160px] transition-colors"
      >
        <Calendar size={14} className="shrink-0 text-[var(--text-tertiary)]" />
        <span className={selected ? '' : 'text-[var(--text-tertiary)]'}>
          {displayText}
        </span>
        {value && (
          <span
            role="button"
            tabIndex={0}
            aria-label={t('common.clear', 'Clear')}
            onClick={(e) => {
              e.stopPropagation();
              onChange('');
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.stopPropagation();
                onChange('');
              }
            }}
            className="ml-auto -mr-1 p-0.5 rounded text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-inset)] transition-colors"
          >
            <X size={12} />
          </span>
        )}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label={t(ariaLabelKey)}
          className="absolute z-50 mt-1 p-3 rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] shadow-xl"
        >
          <DayPicker
            mode="single"
            selected={selected}
            onSelect={handleSelect}
            locale={locale}
            disabled={[
              ...(minD ? [{ before: minD }] : []),
              ...(maxD ? [{ after: maxD }] : []),
            ]}
            // 限制可选范围到今天（审计日志不会是未来）
            endMonth={maxD ?? new Date()}
            autoFocus
            classNames={{
              root: 'text-[var(--text-primary)]',
              months: 'flex flex-col',
              month_caption: 'flex justify-center py-2 text-sm font-medium',
              caption_label: 'text-[var(--text-primary)]',
              nav: 'flex items-center justify-between absolute top-3 left-2 right-2',
              button_previous: 'inline-flex items-center justify-center w-7 h-7 rounded text-[var(--text-tertiary)] hover:bg-[var(--surface-inset)] hover:text-[var(--text-primary)] transition-colors',
              button_next: 'order-2 inline-flex items-center justify-center w-7 h-7 rounded text-[var(--text-tertiary)] hover:bg-[var(--surface-inset)] hover:text-[var(--text-primary)] transition-colors',
              month_grid: 'w-full border-collapse',
              weekdays: 'flex',
              weekday: 'text-[var(--text-tertiary)] text-xs font-medium w-8 text-center py-1',
              week: 'flex w-full',
              day: 'p-0',
              day_button: 'w-8 h-8 rounded text-sm transition-colors hover:bg-[var(--surface-inset)]',
              selected: '!bg-[var(--accent)] !text-white hover:!bg-[var(--accent-hover)]',
              today: 'font-bold text-[var(--accent)]',
              disabled: 'text-[var(--text-tertiary)] opacity-40 cursor-not-allowed',
              outside: 'text-[var(--text-tertiary)] opacity-50',
              footer: 'text-xs text-[var(--text-tertiary)] mt-2',
            }}
          />
        </div>
      )}
    </div>
  );
}
