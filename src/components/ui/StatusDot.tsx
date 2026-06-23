/**
 * StatusDot — 状态指示器组件
 * Canvas 设计系统 .status-dot 模式
 * 8px 圆点 + 3px 语义色光晕
 */

interface StatusDotProps {
  status: 'success' | 'warning' | 'error' | 'muted';
  label?: string;
  size?: number;
}

const STATUS_COLORS: Record<string, { dot: string; glow: string }> = {
  success: { dot: 'var(--success)', glow: 'var(--success-bg)' },
  warning: { dot: 'var(--warning)', glow: 'var(--warning-bg)' },
  error: { dot: 'var(--error)', glow: 'var(--error-bg)' },
  muted: { dot: 'var(--fg-muted)', glow: 'var(--border)' },
};

export function StatusDot({ status, label, size = 8 }: StatusDotProps) {
  const colors = STATUS_COLORS[status] || STATUS_COLORS.muted;

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--space-2)' }}>
      <span
        style={{
          width: size,
          height: size,
          borderRadius: '50%',
          display: 'inline-block',
          flexShrink: 0,
          background: colors.dot,
          boxShadow: `0 0 0 3px ${colors.glow}`,
        }}
        aria-label={status}
      />
      {label && (
        <span style={{ fontSize: 13, color: 'var(--fg-secondary)' }}>{label}</span>
      )}
    </span>
  );
}
