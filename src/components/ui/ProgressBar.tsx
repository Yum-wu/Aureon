/**
 * ProgressBar — 进度条组件
 * Canvas 设计系统 .progress/.progress-fill 模式
 */

interface ProgressBarProps {
  value: number; // 0-100
  variant?: 'brand' | 'accent' | 'success' | 'warning' | 'error';
  label?: string;
  showPercentage?: boolean;
  height?: number;
}

const VARIANT_COLORS: Record<string, string> = {
  brand: 'var(--seed-primary)',
  accent: 'var(--seed-accent)',
  success: 'var(--success)',
  warning: 'var(--warning)',
  error: 'var(--error)',
};

export function ProgressBar({
  value,
  variant = 'brand',
  label,
  showPercentage = false,
  height = 6,
}: ProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, value));
  const color = VARIANT_COLORS[variant] || VARIANT_COLORS.brand;

  return (
    <div>
      {(label || showPercentage) && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-1)' }}>
          {label && (
            <span style={{ fontSize: 13, color: 'var(--fg-secondary)' }}>{label}</span>
          )}
          {showPercentage && (
            <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--fg)' }}>
              {Math.round(clamped)}%
            </span>
          )}
        </div>
      )}
      <div
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
        style={{
          width: '100%',
          height,
          background: 'var(--bg-alt)',
          borderRadius: 'var(--radius-full)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            height: '100%',
            width: `${clamped}%`,
            borderRadius: 'var(--radius-full)',
            background: color,
            transition: `width var(--duration-slow) var(--ease-out)`,
          }}
        />
      </div>
    </div>
  );
}
