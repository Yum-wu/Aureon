/**
 * Nivo Line 图表封装
 * 支持多系列、响应式、统一主题
 */

import { ResponsiveLine, type LineSvgProps, type Serie as LineSerie } from '@nivo/line';
import { ChartContainer } from './ChartContainer';
import { chartTheme, CHART_COLORS, DEFAULT_MARGIN, CHART_DEFAULTS, type TimeRange } from './chartTheme';

interface LineChartProps {
  /** 图表数据（Nivo Line Serie 格式） */
  data: LineSerie[];
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
  /** X 轴格式化 */
  xFormat?: LineSvgProps['xFormat'];
  /** Y 轴格式化 */
  yFormat?: LineSvgProps['yFormat'];
  /** X 轴标签 */
  xAxisLabel?: string;
  /** Y 轴标签 */
  yAxisLabel?: string;
  /** 额外类名 */
  className?: string;
}

export function LineChart({
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
  xFormat,
  yFormat,
  xAxisLabel,
  yAxisLabel,
  className,
}: LineChartProps) {
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
        <ResponsiveLine
          data={data}
          width={width}
          height={containerHeight}
          margin={DEFAULT_MARGIN}
          colors={colors}
          theme={chartTheme}
          animate={animate}
          motionConfig={CHART_DEFAULTS.motionConfig}
          enableGridX={showGrid && CHART_DEFAULTS.enableGridX}
          enableGridY={showGrid && CHART_DEFAULTS.enableGridY}
          xScale={{ type: 'point' }}
          yScale={{ type: 'linear', min: 'auto', max: 'auto', stacked: false, reverse: false }}
          xFormat={xFormat}
          yFormat={yFormat}
          axisBottom={{
            tickSize: 4,
            tickPadding: 6,
            tickRotation: -30,
            legend: xAxisLabel,
            legendOffset: 32,
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
                    anchor: 'bottom-right',
                    direction: 'column',
                    justify: false,
                    translateX: 0,
                    translateY: 0,
                    itemsSpacing: 4,
                    itemDirection: 'left-to-right',
                    itemWidth: 80,
                    itemHeight: 16,
                    itemOpacity: 0.85,
                    symbolSize: 10,
                    symbolShape: 'circle',
                  },
                ]
              : undefined
          }
        />
      )}
    </ChartContainer>
  );
}
