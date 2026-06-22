/**
 * Nivo Bar 图表封装
 * 支持分组/堆叠模式、水平/垂直布局
 *
 * 使用 React.memo 优化：只在 data/height/animate 真正变化时重渲染，
 * 避免父组件频繁更新（如 Dashboard metrics 轮询）触发 Nivo 完整重绘动画。
 */

import { memo } from 'react';
import { Bar, type BarSvgProps, type BarDatum } from '@nivo/bar';
import { ChartContainer } from './ChartContainer';
import { useChartTheme, CHART_COLORS, DEFAULT_MARGIN, CHART_DEFAULTS, type TimeRange } from './chartTheme';

interface BarChartProps<T extends BarDatum = BarDatum> {
  /** 图表数据 */
  data: T[];
  /** 分组键名数组 */
  keys: string[];
  /** 索引字段名 */
  indexBy: keyof T & string;
  /** 图表标题 */
  title: string;
  /** 副标题 */
  subtitle?: string;
  /** 系列颜色 */
  colors?: string[];
  /** 布局方向 */
  layout?: 'vertical' | 'horizontal';
  /** 分组模式：分组或堆叠 */
  groupMode?: 'grouped' | 'stacked';
  /** 是否显示网格 */
  showGrid?: boolean;
  /** 是否显示图例 */
  showLegend?: boolean;
  /** 是否启用动画 */
  animate?: boolean;
  /** 图表高度 */
  height?: number;
  /** 是否显示时间范围选择器 */
  timeRangeSelector?: boolean;
  /** 时间范围变更回调 */
  onTimeRangeChange?: (range: TimeRange) => void;
  /** 加载状态 */
  loading?: boolean;
  /** 值格式化 */
  valueFormat?: BarSvgProps<T>['valueFormat'];
  /** 额外类名 */
  className?: string;
}

function BarChartInner<T extends BarDatum = BarDatum>({
  data,
  keys,
  indexBy,
  title,
  subtitle,
  colors = [...CHART_COLORS],
  layout = 'vertical',
  groupMode = 'grouped',
  showGrid = true,
  showLegend = true,
  animate = true,
  height = 300,
  timeRangeSelector = false,
  onTimeRangeChange,
  loading = false,
  valueFormat,
  className,
}: BarChartProps<T>) {
  const theme = useChartTheme();
  // 安全检查：如果数据为空，直接显示空状态，避免 Nivo 生成 d="null" SVG 路径导致浏览器崩溃
  const hasData = data.length > 0;

  if (!hasData && !loading) {
    return (
      <ChartContainer
        title={title}
        subtitle={subtitle}
        timeRangeSelector={timeRangeSelector}
        onTimeRangeChange={onTimeRangeChange}
        loading={false}
        height={height}
        className={className}
      >
        {() => (
          <div className="flex items-center justify-center h-full text-[var(--text-tertiary)] text-sm">
            暂无数据
          </div>
        )}
      </ChartContainer>
    );
  }

  return (
    <ChartContainer
      title={title}
      subtitle={subtitle}
      timeRangeSelector={timeRangeSelector}
      onTimeRangeChange={onTimeRangeChange}
      loading={loading}
      height={height}
      className={className}
    >
      {({ width, height: containerHeight }) => (
        <Bar<T>
          data={data}
          keys={keys}
          indexBy={indexBy}
          width={width}
          height={containerHeight}
          margin={DEFAULT_MARGIN}
          colors={colors}
          theme={theme}
          layout={layout}
          groupMode={groupMode}
          animate={animate}
          motionConfig={CHART_DEFAULTS.motionConfig}
          enableGridX={showGrid && layout === 'horizontal'}
          enableGridY={showGrid && layout === 'vertical'}
          valueScale={{ type: 'linear' }}
          indexScale={{ type: 'band', round: true }}
          valueFormat={valueFormat}
          axisBottom={
            layout === 'vertical'
              ? {
                  tickSize: 4,
                  tickPadding: 6,
                  tickRotation: -30,
                }
              : null
          }
          axisLeft={
            layout === 'vertical'
              ? {
                  tickSize: 4,
                  tickPadding: 6,
                }
              : {
                  tickSize: 4,
                  tickPadding: 6,
                }
          }
          labelSkipWidth={12}
          labelSkipHeight={12}
          labelTextColor={{ from: 'color', modifiers: [['darker', 1.6]] }}
          isInteractive={CHART_DEFAULTS.isInteractive}
          legends={
            showLegend
              ? [
                  {
                    anchor: 'bottom-right' as const,
                    direction: 'column' as const,
                    justify: false,
                    translateX: 0,
                    translateY: 0,
                    itemsSpacing: 4,
                    itemDirection: 'left-to-right' as const,
                    itemWidth: 80,
                    itemHeight: 16,
                    itemOpacity: 0.85,
                    symbolSize: 10,
                    symbolShape: 'square' as const,
                    dataFrom: 'keys' as const,
                  },
                ]
              : undefined
          }
        />
      )}
    </ChartContainer>
  );
}

/**
 * Memo 优化：只在影响图表渲染的核心 prop 变化时重渲染
 * - data: 图表数据（引用相等性）
 * - height: 图表高度
 * - animate: 是否启用动画
 */
export const BarChart = memo(BarChartInner) as typeof BarChartInner;
