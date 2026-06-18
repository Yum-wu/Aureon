/**
 * Nivo Pie 图表封装
 * 支持饼图/环形图模式
 */

import { ResponsivePie, type PieSvgProps, type PieDatum } from '@nivo/pie';
import { ChartContainer } from './ChartContainer';
import { chartTheme, CHART_COLORS, CHART_DEFAULTS, type TimeRange } from './chartTheme';

interface PieChartProps<T extends PieDatum = PieDatum> {
  /** 图表数据（Nivo PieDatum 格式：{ id, value, label? }） */
  data: T[];
  /** 图表标题 */
  title: string;
  /** 副标题 */
  subtitle?: string;
  /** 内圆半径（>0 时为环形图） */
  innerRadius?: number;
  /** 是否显示标签 */
  showLabels?: boolean;
  /** 是否启用动画 */
  animate?: boolean;
  /** 图表高度 */
  height?: number;
  /** 系列颜色 */
  colors?: string[];
  /** 是否显示时间范围选择器 */
  timeRangeSelector?: boolean;
  /** 时间范围变更回调 */
  onTimeRangeChange?: (range: TimeRange) => void;
  /** 加载状态 */
  loading?: boolean;
  /** 值格式化 */
  valueFormat?: PieSvgProps<T>['valueFormat'];
  /** 额外类名 */
  className?: string;
}

export function PieChart<T extends PieDatum = PieDatum>({
  data,
  title,
  subtitle,
  innerRadius = 0.5,
  showLabels = true,
  animate = true,
  height = 300,
  colors = [...CHART_COLORS],
  timeRangeSelector = false,
  onTimeRangeChange,
  loading = false,
  valueFormat,
  className,
}: PieChartProps<T>) {
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
        <ResponsivePie
          data={data}
          width={width}
          height={containerHeight}
          margin={{ top: 12, right: 80, bottom: 12, left: 12 }}
          innerRadius={innerRadius > 0 ? innerRadius : 0}
          colors={colors}
          theme={chartTheme}
          animate={animate}
          motionConfig={CHART_DEFAULTS.motionConfig}
          padAngle={0.7}
          cornerRadius={3}
          activeOuterRadiusOffset={8}
          borderWidth={1}
          borderColor={{ from: 'color', modifiers: [['darker', 0.2]] }}
          enableArcLabels={showLabels}
          arcLabel={(d) => `${d.id}`}
          arcLabelsSkipAngle={10}
          arcLabelsTextColor={{ from: 'color', modifiers: [['darker', 2]] }}
          valueFormat={valueFormat}
          isInteractive={CHART_DEFAULTS.isInteractive}
          legends={[
            {
              anchor: 'right',
              direction: 'column',
              justify: false,
              translateX: 60,
              translateY: 0,
              itemsSpacing: 6,
              itemWidth: 80,
              itemHeight: 16,
              itemOpacity: 0.85,
              symbolSize: 10,
              symbolShape: 'circle',
            },
          ]}
        />
      )}
    </ChartContainer>
  );
}
