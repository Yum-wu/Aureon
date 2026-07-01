/**
 * Nivo Line 图表封装
 * 支持多系列、响应式、统一主题
 *
 * 使用 React.memo 优化：只在 data/height/animate 真正变化时重渲染，
 * 避免父组件频繁更新（如 Dashboard metrics 轮询）触发 Nivo 完整重绘动画。
 */

import { memo } from 'react';
import { Line, type LineSvgProps, type LineSeries } from '@nivo/line';
import { ChartContainer } from './ChartContainer';
import { useChartTheme, CHART_COLORS, DEFAULT_MARGIN, CHART_DEFAULTS, type TimeRange } from './chartTheme';

interface LineChartProps {
  /** 图表数据（Nivo Line Serie 格式） */
  data: LineSeries[];
  /** 图表标题 */
  title: string;
  /** 副标题 */
  subtitle?: string;
  /** 系列颜色（按顺序，默认使用 CHART_COLORS） */
  colors?: string[];
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
  /** 空数据时显示的提示文字，默认"暂无数据" */
  emptyDescription?: string;
  /** X 轴格式化 */
  xFormat?: LineSvgProps<LineSeries>['xFormat'];
  /** Y 轴格式化 */
  yFormat?: LineSvgProps<LineSeries>['yFormat'];
  /** X 轴标签 */
  xAxisLabel?: string;
  /** Y 轴标签 */
  yAxisLabel?: string;
  /** Y 轴刻度范围（默认 auto/auto） */
  yScale?: { type: 'linear'; min?: number | 'auto'; max?: number | 'auto'; stacked?: boolean; reverse?: boolean };
  /** 额外类名 */
  className?: string;
}

function LineChartInner({
  data,
  title,
  subtitle,
  colors = [...CHART_COLORS],
  showGrid = true,
  showLegend = true,
  animate = true,
  height = 300,
  timeRangeSelector = false,
  onTimeRangeChange,
  loading = false,
  emptyDescription,
  xFormat,
  yFormat,
  xAxisLabel,
  yAxisLabel,
  yScale: yScaleProp,
  className,
}: LineChartProps) {
  const theme = useChartTheme();
  // 安全检查：如果所有系列都没有有效数据点，直接显示空状态，避免 Nivo 生成 d="null" SVG 路径导致浏览器崩溃
  const hasData = data.some(series => series.data.length > 0);

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
            {emptyDescription ?? '暂无数据'}
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
        <Line<LineSeries>
          data={data}
          width={width}
          height={containerHeight}
          margin={DEFAULT_MARGIN}
          colors={colors}
          theme={theme}
          animate={animate}
          motionConfig={CHART_DEFAULTS.motionConfig}
          enableGridX={showGrid && CHART_DEFAULTS.enableGridX}
          enableGridY={showGrid && CHART_DEFAULTS.enableGridY}
          xScale={{ type: 'point' }}
          yScale={yScaleProp ?? { type: 'linear', min: 'auto', max: 'auto', stacked: false, reverse: false }}
          xFormat={xFormat}
          yFormat={yFormat}
          axisBottom={{
            tickSize: 4,
            tickPadding: 8,
            tickRotation: 0,
            legend: xAxisLabel,
            legendOffset: 36,
            legendPosition: 'middle',
          }}
          axisLeft={{
            tickSize: 4,
            tickPadding: 6,
            legend: yAxisLabel,
            legendOffset: -40,
            legendPosition: 'middle',
          }}
          enablePoints={true}
          pointSize={4}
          pointColor={{ theme: 'background' }}
          pointBorderWidth={2}
          pointBorderColor={{ from: 'serieColor' }}
          pointLabelYOffset={-12}
          useMesh={CHART_DEFAULTS.useMesh}
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
                    symbolShape: 'circle' as const,
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
export const LineChart = memo(LineChartInner, (prev, next) => {
  return (
    prev.data === next.data &&
    prev.height === next.height &&
    prev.animate === next.animate
  );
});
