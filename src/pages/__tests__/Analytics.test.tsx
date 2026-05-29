import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';

// Mock useAnalytics before importing Analytics
const mockUseAnalytics = vi.fn();
vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: (...args: unknown[]) => mockUseAnalytics(...args),
}));

// Default mock: return i18n key as-is
let mockT = (key: string, opts?: Record<string, unknown>) => {
  if (opts && typeof opts === 'object') {
    return Object.entries(opts).reduce(
      (str, [k, v]) => str.replace(`{{${k}}}`, String(v)),
      key
    );
  }
  return key;
};

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => mockT(key, opts),
  }),
}));

import Analytics from '../Analytics';

describe('Analytics Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockT = (key: string) => key;
  });

  it('should show loading state initially', () => {
    mockUseAnalytics.mockReturnValue({
      usage: null,
      latency: null,
      tokens: null,
      cache: null,
      loading: true,
      error: null,
      refresh: vi.fn(),
    });

    render(
      <BrowserRouter>
        <Analytics />
      </BrowserRouter>
    );

    expect(screen.getByText('analytics.title')).toBeInTheDocument();
  });

  it('should show error state when data load fails', () => {
    const mockRefresh = vi.fn();
    mockUseAnalytics.mockReturnValue({
      usage: null,
      latency: null,
      tokens: null,
      cache: null,
      loading: false,
      error: 'Failed to fetch',
      refresh: mockRefresh,
    });

    render(
      <BrowserRouter>
        <Analytics />
      </BrowserRouter>
    );

    expect(screen.getByText('analytics.error_loading')).toBeInTheDocument();
    expect(screen.getByText('analytics.retry')).toBeInTheDocument();
  });

  it('should display data when loaded successfully', () => {
    mockUseAnalytics.mockReturnValue({
      usage: { total: 100, perHour: 5, byIntent: { general_qa: 60 }, trend: { change: 10, period: 'vs prev' } },
      latency: { avg: 15, p95: 30, p99: 50, breakdown: { retrieval: 10, llm_first_token: 300, llm_generation: 700 }, trend: { avg_change: -5, period: 'vs prev' } },
      tokens: { input: 50000, output: 30000, total: 80000, cost: 25, costPerQuery: 0.001, model: 'gpt-4o-mini', trend: { input_change: 5, output_change: 3, period: 'vs prev' } },
      cache: { hitRate: 75, saves: 200, latencyReduction: 40, memoryUsage: '128MB' },
      loading: false,
      error: null,
      refresh: vi.fn(),
    });

    render(
      <BrowserRouter>
        <Analytics />
      </BrowserRouter>
    );

    expect(screen.getByText('15')).toBeInTheDocument();
    expect(screen.getByText('100')).toBeInTheDocument();
    expect(screen.getByText('75%')).toBeInTheDocument();
  });

  it('renders Chinese translation', () => {
    mockT = (key: string) => {
      const zhMap: Record<string, string> = {
        'analytics.title': '分析',
        'analytics.subtitle': '系统性能与使用分析',
        'analytics.refresh': '刷新数据',
        'analytics.retry': '重试',
        'analytics.error_loading': '加载分析数据失败',
        'analytics.avg_latency': '平均延迟',
        'analytics.token_usage': 'Token 消耗',
        'analytics.total_queries': '查询总量',
        'analytics.cache_hit_rate': '缓存命中率',
        'analytics.output': '输出',
        'analytics.cost': '成本',
        'analytics.avg_per_hour': '平均 5/小时',
        'analytics.saves': '节省 200 次查询',
        'analytics.no_data': '暂无数据',
        'analytics.latency.title': '延迟分布',
        'analytics.latency.avg': '平均',
        'analytics.latency.p95': 'P95',
        'analytics.latency.p99': 'P99',
        'analytics.tokens.title': 'Token 使用详情',
        'analytics.tokens.input': '输入 Token',
        'analytics.tokens.output': '输出 Token',
        'analytics.tokens.cost': '预估成本',
        'analytics.tokens.per_query': '~$0.001/查询',
        'analytics.queries.title': '查询分布',
        'analytics.intent.general_qa': '通用问答',
        'analytics.time_range.24h': '最近 24 小时',
        'analytics.time_range.7d': '最近 7 天',
        'analytics.time_range.30d': '最近 30 天',
      };
      return zhMap[key] ?? key;
    };

    mockUseAnalytics.mockReturnValue({
      usage: { total: 100, perHour: 5, byIntent: { general_qa: 60 } },
      latency: { avg: 15, p95: 30, p99: 50 },
      tokens: { input: 50000, output: 30000, total: 80000, cost: 25, costPerQuery: 0.001 },
      cache: { hitRate: 75, saves: 200 },
      loading: false,
      error: null,
      refresh: vi.fn(),
    });

    render(
      <BrowserRouter>
        <Analytics />
      </BrowserRouter>
    );

    expect(screen.getByText('分析')).toBeInTheDocument();
    expect(screen.getByText('系统性能与使用分析')).toBeInTheDocument();
    expect(screen.getByText('平均延迟')).toBeInTheDocument();
    expect(screen.getByText('Token 消耗')).toBeInTheDocument();
    expect(screen.getByText('查询总量')).toBeInTheDocument();
    expect(screen.getByText('缓存命中率')).toBeInTheDocument();
    expect(screen.getByText('延迟分布')).toBeInTheDocument();
    expect(screen.getByText('Token 使用详情')).toBeInTheDocument();
    expect(screen.getByText('输入 Token')).toBeInTheDocument();
    expect(screen.getByText('输出 Token')).toBeInTheDocument();
    expect(screen.getByText('预估成本')).toBeInTheDocument();
    expect(screen.getByText('查询分布')).toBeInTheDocument();
    expect(screen.getByText('通用问答')).toBeInTheDocument();
  });

  it('renders English translation', () => {
    mockT = (key: string) => {
      const enMap: Record<string, string> = {
        'analytics.title': 'Analytics',
        'analytics.subtitle': 'System performance and usage analytics',
        'analytics.refresh': 'Refresh data',
        'analytics.retry': 'Retry',
        'analytics.error_loading': 'Failed to load analytics data',
        'analytics.avg_latency': 'Avg Latency',
        'analytics.token_usage': 'Token Usage',
        'analytics.total_queries': 'Total Queries',
        'analytics.cache_hit_rate': 'Cache Hit Rate',
        'analytics.output': 'Output',
        'analytics.cost': 'Cost',
        'analytics.avg_per_hour': 'avg 5/hour',
        'analytics.saves': '200 queries saved',
        'analytics.no_data': 'No data available',
        'analytics.latency.title': 'Latency Distribution',
        'analytics.latency.avg': 'Avg',
        'analytics.latency.p95': 'P95',
        'analytics.latency.p99': 'P99',
        'analytics.tokens.title': 'Token Usage Details',
        'analytics.tokens.input': 'Input Tokens',
        'analytics.tokens.output': 'Output Tokens',
        'analytics.tokens.cost': 'Estimated Cost',
        'analytics.tokens.per_query': '~$0.001/query',
        'analytics.queries.title': 'Query Distribution',
        'analytics.intent.general_qa': 'General Q&A',
        'analytics.time_range.24h': 'Last 24 hours',
        'analytics.time_range.7d': 'Last 7 days',
        'analytics.time_range.30d': 'Last 30 days',
      };
      return enMap[key] ?? key;
    };

    mockUseAnalytics.mockReturnValue({
      usage: { total: 100, perHour: 5, byIntent: { general_qa: 60 } },
      latency: { avg: 15, p95: 30, p99: 50 },
      tokens: { input: 50000, output: 30000, total: 80000, cost: 25, costPerQuery: 0.001 },
      cache: { hitRate: 75, saves: 200 },
      loading: false,
      error: null,
      refresh: vi.fn(),
    });

    render(
      <BrowserRouter>
        <Analytics />
      </BrowserRouter>
    );

    expect(screen.getByText('Analytics')).toBeInTheDocument();
    expect(screen.getByText('System performance and usage analytics')).toBeInTheDocument();
    expect(screen.getByText('Avg Latency')).toBeInTheDocument();
    expect(screen.getByText('Token Usage')).toBeInTheDocument();
    expect(screen.getByText('Total Queries')).toBeInTheDocument();
    expect(screen.getByText('Cache Hit Rate')).toBeInTheDocument();
    expect(screen.getByText('Latency Distribution')).toBeInTheDocument();
    expect(screen.getByText('Token Usage Details')).toBeInTheDocument();
    expect(screen.getByText('Input Tokens')).toBeInTheDocument();
    expect(screen.getByText('Output Tokens')).toBeInTheDocument();
    expect(screen.getByText('Estimated Cost')).toBeInTheDocument();
    expect(screen.getByText('Query Distribution')).toBeInTheDocument();
    expect(screen.getByText('General Q&A')).toBeInTheDocument();
  });
});
