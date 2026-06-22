/**
 * Nivo 图表主题配置
 * 将项目 Design Token CSS 变量映射为 Nivo 主题格式
 */

import type { PartialTheme } from '@nivo/theming';
import { useTheme } from '../../hooks/ThemeProvider';

/** 图表系列配色（8 色，基于 oklch 色阶 + 项目 accent 色） */
export const CHART_COLORS = [
  '#5E6AD2', // accent 主色
  '#818CF8', // accent-200 / purple
  '#22C55E', // success 绿
  '#EAB308', // warning 黄
  '#EF4444', // error 红
  '#22D3EE', // cyan
  '#EC4899', // pink
  '#F97316', // orange
] as const;

/** 时间范围选项 */
export const TIME_RANGES = ['1h', '6h', '24h', '7d', '30d'] as const;
export type TimeRange = (typeof TIME_RANGES)[number];

/** 亮色主题（当前项目为深色主题为主，亮色预留） */
export const chartLightTheme: PartialTheme = {
  background: 'transparent',
  text: {
    fontSize: 12,
    fill: '#5C5C6A',
    fontFamily: 'var(--font-sans)',
  },
  axis: {
    domain: { line: { stroke: '#E5E7EB', strokeWidth: 1 } },
    ticks: {
      line: { stroke: '#D1D5DB', strokeWidth: 1 },
      text: { fill: '#6B7280', fontSize: 11 },
    },
  },
  grid: { line: { stroke: '#F3F4F6', strokeWidth: 1 } },
  legends: { text: { fill: '#374151', fontSize: 12 } },
  tooltip: {
    container: {
      background: '#FFFFFF',
      color: '#111827',
      fontSize: 12,
      borderRadius: 6,
      boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
      padding: '8px 12px',
    },
  },
};

/** 暗色主题（匹配项目 Design Token） */
export const chartDarkTheme: PartialTheme = {
  background: 'transparent',
  text: {
    fontSize: 12,
    fill: '#8B8B99',
    fontFamily: 'var(--font-sans)',
  },
  axis: {
    domain: { line: { stroke: 'rgba(255,255,255,0.07)', strokeWidth: 1 } },
    ticks: {
      line: { stroke: 'rgba(255,255,255,0.09)', strokeWidth: 1 },
      text: { fill: '#8B8B99', fontSize: 11 },
    },
  },
  grid: { line: { stroke: 'rgba(255,255,255,0.04)', strokeWidth: 1 } },
  legends: { text: { fill: '#8B8B99', fontSize: 12 } },
  tooltip: {
    container: {
      background: '#1A1B1D',
      color: '#EDEDF0',
      fontSize: 12,
      borderRadius: 6,
      boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
      padding: '8px 12px',
      border: '1px solid rgba(255,255,255,0.07)',
    },
  },
};

/** 默认使用暗色主题（项目主色调） */
export const chartTheme = chartDarkTheme;

/** 根据当前 DOM 主题属性返回对应图表主题 */
export function getChartTheme(): PartialTheme {
  if (typeof document !== 'undefined' && document.documentElement.getAttribute('data-theme') === 'dark') {
    return chartDarkTheme;
  }
  return chartLightTheme;
}

/** React hook: 响应式图表主题，跟随 ThemeProvider 切换 */
export function useChartTheme(): PartialTheme {
  const { theme } = useTheme();
  return theme === 'dark' ? chartDarkTheme : chartLightTheme;
}

/** 通用图表默认边距 */
export const DEFAULT_MARGIN = { top: 12, right: 16, bottom: 40, left: 48 };

/** 通用图表配置默认值 */
export const CHART_DEFAULTS = {
  animate: true,
  motionConfig: 'gentle' as const,
  enableGridX: false,
  enableGridY: true,
  isInteractive: true,
  useMesh: true,
} as const;
