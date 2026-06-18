/**
 * 图表容器组件
 * 提供标题栏、时间范围选择器、加载状态和响应式容器
 */

import { useState, useRef, useEffect, useCallback, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { TIME_RANGES, type TimeRange } from './chartTheme';

interface ChartContainerProps {
  /** 图表标题 */
  title: string;
  /** 副标题 */
  subtitle?: string;
  /** 是否显示时间范围选择器 */
  timeRangeSelector?: boolean;
  /** 时间范围变更回调 */
  onTimeRangeChange?: (range: TimeRange) => void;
  /** 默认选中时间范围 */
  defaultTimeRange?: TimeRange;
  /** 加载状态 */
  loading?: boolean;
  /** 额外类名 */
  className?: string;
  /** 图表内容 */
  children: (dimensions: { width: number; height: number }) => ReactNode;
  /** 图表高度（px） */
  height?: number;
}

/** 使用 ResizeObserver 监听容器尺寸变化 */
function useResizeObserver(elementRef: React.RefObject<HTMLElement | null>): {
  width: number;
  height: number;
} {
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = elementRef.current;
    if (!el) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        setSize({ width: Math.floor(width), height: Math.floor(height) });
      }
    });

    observer.observe(el);
    return () => observer.disconnect();
  }, [elementRef]);

  return size;
}

export function ChartContainer({
  title,
  subtitle,
  timeRangeSelector = false,
  onTimeRangeChange,
  defaultTimeRange = '24h',
  loading = false,
  className = '',
  children,
  height = 300,
}: ChartContainerProps) {
  const { t } = useTranslation();
  const [selectedRange, setSelectedRange] = useState<TimeRange>(defaultTimeRange);
  const containerRef = useRef<HTMLDivElement>(null);
  const dimensions = useResizeObserver(containerRef);

  const handleRangeChange = useCallback(
    (range: TimeRange) => {
      setSelectedRange(range);
      onTimeRangeChange?.(range);
    },
    [onTimeRangeChange],
  );

  return (
    <div
      role="img"
      aria-label={title}
      className={`relative rounded-lg border bg-[var(--bg-secondary)] border-[var(--border)] ${className}`}
    >
      {/* 标题栏 */}
      <div className="flex items-center justify-between px-5 pt-4 pb-2">
        <div>
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
          {subtitle && (
            <p className="text-xs text-[var(--text-tertiary)] mt-0.5">{subtitle}</p>
          )}
        </div>
        {timeRangeSelector && (
          <div className="flex items-center gap-1 rounded-md bg-[var(--bg-tertiary)] p-0.5">
            {TIME_RANGES.map((range) => (
              <button
                key={range}
                onClick={() => handleRangeChange(range)}
                className={`px-2 py-1 text-[11px] font-medium rounded transition-colors ${
                  selectedRange === range
                    ? 'bg-[var(--accent)] text-white'
                    : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'
                }`}
              >
                {t(`analytics.time_range.${range}`, range)}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 图表区域 */}
      <div ref={containerRef} className="px-2 pb-3" style={{ height }}>
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <div className="flex flex-col items-center gap-2">
              <div className="w-6 h-6 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
              <span className="text-xs text-[var(--text-tertiary)]">{t('dashboard.loading')}</span>
            </div>
          </div>
        ) : dimensions.width > 0 ? (
          children({ width: dimensions.width, height: dimensions.height || height })
        ) : null}
      </div>
    </div>
  );
}
