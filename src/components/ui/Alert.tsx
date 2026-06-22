import type { ReactNode } from 'react';
import type { ToastType } from '../../hooks/toastContext';

/* ── Semantic color map ── */
const COLOR_MAP: Record<ToastType, string> = {
  info: 'var(--info)',
  success: 'var(--success)',
  warning: 'var(--warning)',
  error: 'var(--error)',
};

const BG_MAP: Record<ToastType, string> = {
  info: 'var(--info-bg)',
  success: 'var(--success-bg)',
  warning: 'var(--warning-bg)',
  error: 'var(--error-bg)',
};

/* ── Inline Alert (non-dismissable, for embedding in pages) ── */
export function Alert({
  type = 'info',
  children,
  className = '',
}: {
  type?: ToastType;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`alert alert-${type} ${className}`}
      role="alert"
      style={{
        background: BG_MAP[type],
        borderColor: `color-mix(in srgb, ${COLOR_MAP[type]} 25%, transparent)`,
      }}
    >
      <div
        className="alert-dot"
        style={{ background: COLOR_MAP[type] }}
      />
      <div className="alert-text">{children}</div>
    </div>
  );
}
