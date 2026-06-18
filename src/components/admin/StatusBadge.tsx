/**
 * 状态徽章组件
 * 映射状态到 Design Token 颜色
 */

import type { ReactNode } from 'react';

/** 状态类型 */
export type StatusType = 'healthy' | 'warning' | 'error' | 'disabled' | 'active' | 'suspended';

/** 徽章尺寸 */
export type BadgeSize = 'sm' | 'md';

interface StatusBadgeProps {
  /** 状态 */
  status: StatusType;
  /** 自定义标签（默认使用状态名） */
  label?: string;
  /** 尺寸 */
  size?: BadgeSize;
}

/** 状态到颜色映射 */
const STATUS_STYLES: Record<StatusType, { dot: string; bg: string; text: string }> = {
  healthy: { dot: 'bg-emerald-400', bg: 'bg-emerald-500/10', text: 'text-emerald-400' },
  active: { dot: 'bg-emerald-400', bg: 'bg-emerald-500/10', text: 'text-emerald-400' },
  warning: { dot: 'bg-amber-400', bg: 'bg-amber-500/10', text: 'text-amber-400' },
  error: { dot: 'bg-red-400', bg: 'bg-red-500/10', text: 'text-red-400' },
  disabled: { dot: 'bg-gray-500', bg: 'bg-white/[0.04]', text: 'text-[var(--text-tertiary)]' },
  suspended: { dot: 'bg-gray-500', bg: 'bg-white/[0.04]', text: 'text-[var(--text-tertiary)]' },
};

/** 默认状态标签 */
const DEFAULT_LABELS: Record<StatusType, string> = {
  healthy: 'Healthy',
  active: 'Active',
  warning: 'Warning',
  error: 'Error',
  disabled: 'Disabled',
  suspended: 'Suspended',
};

export function StatusBadge({ status, label, size = 'md' }: StatusBadgeProps): ReactNode {
  const styles = STATUS_STYLES[status];
  const displayLabel = label ?? DEFAULT_LABELS[status];

  const sizeClasses = size === 'sm'
    ? 'px-1.5 py-0.5 text-[10px] gap-1'
    : 'px-2 py-0.5 text-xs gap-1.5';

  const dotSize = size === 'sm' ? 'w-1.5 h-1.5' : 'w-2 h-2';

  return (
    <span
      className={`inline-flex items-center rounded-full font-medium ${styles.bg} ${styles.text} ${sizeClasses}`}
    >
      <span className={`rounded-full ${styles.dot} ${dotSize} shrink-0`} />
      {displayLabel}
    </span>
  );
}
