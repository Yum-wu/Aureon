import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import React from 'react';

// ── ResizeObserver mock（Nivo 图表依赖）──
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// ── WebSocket mock ──
class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  readyState = MockWebSocket.OPEN;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  send = vi.fn();
  close = vi.fn();
  addEventListener = vi.fn();
  removeEventListener = vi.fn();
}
vi.stubGlobal('WebSocket', MockWebSocket);

// ── Nivo 图表 mock ──
vi.mock('@nivo/line', () => ({
  ResponsiveLine: () => <div data-testid="mock-line-chart" />,
}));
vi.mock('@nivo/bar', () => ({
  ResponsiveBar: () => <div data-testid="mock-bar-chart" />,
}));

// ── ChartContainer mock（避免 ResizeObserver 和 render props）──
vi.mock('../../components/charts/ChartContainer', () => ({
  ChartContainer: ({ children, title }: { children: React.ReactNode | ((dims: { width: number; height: number }) => React.ReactNode); title: string }) => (
    <div data-testid="mock-chart-container">
      <span>{title}</span>
      {typeof children === 'function' ? children({ width: 600, height: 300 }) : children}
    </div>
  ),
}));

// ── LineChart / BarChart mock ──
vi.mock('../../components/charts/LineChart', () => ({
  LineChart: ({ title }: { title: string }) => <div data-testid="mock-line-chart-wrapper">{title}</div>,
}));
vi.mock('../../components/charts/BarChart', () => ({
  BarChart: ({ title }: { title: string }) => <div data-testid="mock-bar-chart-wrapper">{title}</div>,
}));

// ── Card mock ──
vi.mock('../../components/ui/Card', () => ({
  Card: ({ children, ...props }: { children: React.ReactNode; className?: string }) => (
    <div data-testid="mock-card" {...props}>{children}</div>
  ),
}));

// ── Hooks mock ──
const mockUseDashboardStats = vi.fn();
vi.mock('../../hooks/useDashboardStats', () => ({
  useDashboardStats: () => mockUseDashboardStats(),
}));

vi.mock('../../hooks/useSystemHealth', () => ({
  useSystemHealth: () => ({ health: null, loading: true, error: null }),
}));

vi.mock('../../hooks/useBenchmark', () => ({
  useBenchmark: () => ({ data: null, loading: true, error: null }),
}));

// ── i18n mock ──
let mockT = (key: string, opts?: Record<string, unknown>) => {
  if (opts && typeof opts === 'object') {
    return Object.entries(opts).reduce(
      (str, [k, v]) => str.replace(`{{${k}}}`, String(v)),
      key,
    );
  }
  return key;
};

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string, opts?: Record<string, unknown>) => mockT(key, opts) }),
}));

import { Dashboard } from '../Dashboard';

describe('Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockT = (key: string) => key;
  });

  it('renders loading state', () => {
    mockUseDashboardStats.mockReturnValue({
      stats: null,
      recentQueries: [],
      queryVolume: [],
      loading: true,
      error: null,
      refetch: vi.fn(),
    });

    act(() => {
      render(<Dashboard />);
    });

    expect(screen.getByTestId('dashboard-loading')).toBeInTheDocument();
  });

  it('renders error state', () => {
    mockUseDashboardStats.mockReturnValue({
      stats: null,
      recentQueries: [],
      queryVolume: [],
      loading: false,
      error: 'Network error',
      refetch: vi.fn(),
    });

    act(() => {
      render(<Dashboard />);
    });

    expect(screen.getByText('dashboard.error_loading')).toBeInTheDocument();
    expect(screen.getByText('Network error')).toBeInTheDocument();
    expect(screen.getByText('dashboard.retry')).toBeInTheDocument();
  });

  it('renders Golden Signals and charts with real data', () => {
    mockUseDashboardStats.mockReturnValue({
      stats: {
        cache_hit_rate: 0.92,
        query_count_24h: 1234,
        avg_retrieval_latency_ms: 310.5,
        total_indexed_docs: 42,
        total_chunks: 1800,
      },
      recentQueries: [],
      queryVolume: [
        { date: '2026-06-17', count: 180 },
        { date: '2026-06-18', count: 210 },
      ],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    act(() => {
      render(<Dashboard />);
    });

    // Header
    expect(screen.getByText('dashboard.golden_signals.title')).toBeInTheDocument();
    expect(screen.getByText('dashboard.subtitle')).toBeInTheDocument();

    // Golden Signals labels
    expect(screen.getByText('dashboard.golden_signals.latency')).toBeInTheDocument();
    expect(screen.getByText('dashboard.golden_signals.traffic')).toBeInTheDocument();
    expect(screen.getByText('dashboard.golden_signals.errors')).toBeInTheDocument();
    expect(screen.getByText('dashboard.golden_signals.saturation')).toBeInTheDocument();
    expect(screen.getByText('dashboard.golden_signals.alerts')).toBeInTheDocument();

    // Chart containers: latency chart shows empty state (no realtime trend data),
    // query volume chart renders normally (has data)
    expect(screen.getByText('dashboard.charts.query_volume')).toBeInTheDocument();
    // latency trend has no data (fallback empty arrays), so empty state is shown
    expect(screen.queryByText('dashboard.charts.latency_trend')).not.toBeInTheDocument();
    // 至少有 2 个空状态占位（latency 趋势 + 质量趋势）
    expect(screen.getAllByText('dashboard.no_data').length).toBeGreaterThanOrEqual(2);

    // Pipeline section
    expect(screen.getByText('dashboard.pipeline.title')).toBeInTheDocument();
    expect(screen.getByText('dashboard.pipeline.retrieval')).toBeInTheDocument();
    expect(screen.getByText('dashboard.pipeline.rerank')).toBeInTheDocument();
    expect(screen.getByText('dashboard.pipeline.crag')).toBeInTheDocument();
    expect(screen.getByText('dashboard.pipeline.generation')).toBeInTheDocument();

    // Health section
    expect(screen.getByText('dashboard.system_health')).toBeInTheDocument();

    // Alerts section
    expect(screen.getByText('dashboard.alerts.title')).toBeInTheDocument();
    expect(screen.getByText('dashboard.alerts.empty')).toBeInTheDocument();

    // Live indicator — mock WS never fires onopen, so shows "connecting"
    expect(screen.getByText('dashboard.connecting')).toBeInTheDocument();
  });

  it('renders Chinese translation', () => {
    mockT = (key: string) => {
      const zhMap: Record<string, string> = {
        'dashboard.golden_signals.title': '黄金信号',
        'dashboard.subtitle': '实时指标与系统健康监控',
        'dashboard.golden_signals.latency': '延迟',
        'dashboard.golden_signals.traffic': '流量',
        'dashboard.golden_signals.errors': '错误率',
        'dashboard.golden_signals.saturation': '饱和度',
        'dashboard.golden_signals.alerts': '告警',
        'dashboard.golden_signals.critical': '严重',
        'dashboard.charts.latency_trend': '延迟趋势',
        'dashboard.charts.query_volume': '查询量',
        'dashboard.charts.quality_trend': '检索质量趋势',
        'dashboard.pipeline.title': 'RAG Pipeline',
        'dashboard.pipeline.retrieval': '检索',
        'dashboard.pipeline.rerank': '重排序',
        'dashboard.pipeline.crag': 'CRAG',
        'dashboard.pipeline.generation': '生成',
        'dashboard.system_health': '系统健康',
        'dashboard.health.redis': 'Redis',
        'dashboard.health.qdrant': 'Qdrant',
        'dashboard.health.llm_api': 'LLM API',
        'dashboard.alerts.title': '告警',
        'dashboard.alerts.empty': '暂无告警',
        'dashboard.no_data': '暂无数据',
        'dashboard.error_loading': '加载失败',
        'dashboard.retry': '重试',
        'dashboard.live': '实时',
        'dashboard.offline': '离线',
        'dashboard.time_range.1h': '1小时',
        'dashboard.time_range.6h': '6小时',
        'dashboard.time_range.24h': '24小时',
        'dashboard.time_range.7d': '7天',
      };
      return zhMap[key] ?? key;
    };

    mockUseDashboardStats.mockReturnValue({
      stats: {
        cache_hit_rate: 0.92,
        query_count_24h: 1234,
        avg_retrieval_latency_ms: 310.5,
        total_indexed_docs: 42,
        total_chunks: 1800,
      },
      recentQueries: [],
      queryVolume: [],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    act(() => {
      render(<Dashboard />);
    });

    expect(screen.getByText('黄金信号')).toBeInTheDocument();
    expect(screen.getByText('实时指标与系统健康监控')).toBeInTheDocument();
    expect(screen.getByText('延迟')).toBeInTheDocument();
    expect(screen.getByText('流量')).toBeInTheDocument();
    expect(screen.getByText('错误率')).toBeInTheDocument();
    expect(screen.getByText('饱和度')).toBeInTheDocument();
    // "告警" 出现两次：Golden Signals 卡片标签 + Alerts 区域标题
    expect(screen.getAllByText('告警').length).toBeGreaterThanOrEqual(2);
    // 图表无数据时显示空状态（queryVolume 为空，无 realtime 数据）
    expect(screen.queryByText('延迟趋势')).not.toBeInTheDocument();
    expect(screen.queryByText('查询量')).not.toBeInTheDocument();
    // 至少有 2 个空状态占位（latency 趋势 + 质量趋势 + 查询量）
    expect(screen.getAllByText('暂无数据').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('RAG Pipeline')).toBeInTheDocument();
    expect(screen.getByText('检索')).toBeInTheDocument();
    expect(screen.getByText('重排序')).toBeInTheDocument();
    expect(screen.getByText('CRAG')).toBeInTheDocument();
    expect(screen.getByText('生成')).toBeInTheDocument();
    expect(screen.getByText('系统健康')).toBeInTheDocument();
    expect(screen.getByText('暂无告警')).toBeInTheDocument();
  });

  it('renders English translation', () => {
    mockT = (key: string) => {
      const enMap: Record<string, string> = {
        'dashboard.golden_signals.title': 'Golden Signals',
        'dashboard.subtitle': 'Real-time metrics and system health monitoring',
        'dashboard.golden_signals.latency': 'Latency',
        'dashboard.golden_signals.traffic': 'Traffic',
        'dashboard.golden_signals.errors': 'Errors',
        'dashboard.golden_signals.saturation': 'Saturation',
        'dashboard.golden_signals.alerts': 'Alerts',
        'dashboard.golden_signals.critical': 'Critical',
        'dashboard.charts.latency_trend': 'Latency Trend',
        'dashboard.charts.query_volume': 'Query Volume',
        'dashboard.charts.quality_trend': 'Quality Trend',
        'dashboard.pipeline.title': 'RAG Pipeline',
        'dashboard.pipeline.retrieval': 'Retrieval',
        'dashboard.pipeline.rerank': 'Rerank',
        'dashboard.pipeline.crag': 'CRAG',
        'dashboard.pipeline.generation': 'Generation',
        'dashboard.system_health': 'System Health',
        'dashboard.health.redis': 'Redis',
        'dashboard.health.qdrant': 'Qdrant',
        'dashboard.health.llm_api': 'LLM API',
        'dashboard.alerts.title': 'Alerts',
        'dashboard.alerts.empty': 'No alerts',
        'dashboard.no_data': 'No data',
        'dashboard.error_loading': 'Failed to load',
        'dashboard.retry': 'Retry',
        'dashboard.live': 'Live',
        'dashboard.offline': 'Offline',
        'dashboard.time_range.1h': '1h',
        'dashboard.time_range.6h': '6h',
        'dashboard.time_range.24h': '24h',
        'dashboard.time_range.7d': '7d',
      };
      return enMap[key] ?? key;
    };

    mockUseDashboardStats.mockReturnValue({
      stats: {
        cache_hit_rate: 0.92,
        query_count_24h: 1234,
        avg_retrieval_latency_ms: 310.5,
        total_indexed_docs: 42,
        total_chunks: 1800,
      },
      recentQueries: [],
      queryVolume: [],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    act(() => {
      render(<Dashboard />);
    });

    expect(screen.getByText('Golden Signals')).toBeInTheDocument();
    expect(screen.getByText('Real-time metrics and system health monitoring')).toBeInTheDocument();
    expect(screen.getByText('Latency')).toBeInTheDocument();
    expect(screen.getByText('Traffic')).toBeInTheDocument();
    expect(screen.getByText('Errors')).toBeInTheDocument();
    expect(screen.getByText('Saturation')).toBeInTheDocument();
    // "Alerts" appears twice: Golden Signals card label + Alerts section title
    expect(screen.getAllByText('Alerts').length).toBeGreaterThanOrEqual(2);
    // 图表无数据时显示空状态（queryVolume 为空，无 realtime 数据）
    expect(screen.queryByText('Latency Trend')).not.toBeInTheDocument();
    expect(screen.queryByText('Query Volume')).not.toBeInTheDocument();
    // 至少有 2 个空状态占位（latency 趋势 + 质量趋势 + 查询量）
    expect(screen.getAllByText('No data').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('RAG Pipeline')).toBeInTheDocument();
    expect(screen.getByText('Retrieval')).toBeInTheDocument();
    expect(screen.getByText('Rerank')).toBeInTheDocument();
    expect(screen.getByText('CRAG')).toBeInTheDocument();
    expect(screen.getByText('Generation')).toBeInTheDocument();
    expect(screen.getByText('System Health')).toBeInTheDocument();
    expect(screen.getByText('No alerts')).toBeInTheDocument();
  });
});
