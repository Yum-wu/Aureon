import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

// Mock useDashboardStats hook
const mockUseDashboardStats = vi.fn();
vi.mock('../../hooks/useDashboardStats', () => ({
  useDashboardStats: () => mockUseDashboardStats(),
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
  useTranslation: () => ({ t: (key: string, opts?: Record<string, unknown>) => mockT(key, opts) }),
}));

import { Dashboard } from '../Dashboard';

describe('Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset to default key-returning mock
    mockT = (key: string) => key;
  });

  it('renders loading state', () => {
    mockUseDashboardStats.mockReturnValue({
      stats: null,
      recentQueries: [],
      loading: true,
      error: null,
      refetch: vi.fn(),
    });

    render(<Dashboard />);

    expect(screen.getByTestId('dashboard-loading')).toBeInTheDocument();
    expect(screen.queryByText('dashboard.total_queries')).not.toBeInTheDocument();
  });

  it('renders error state', () => {
    mockUseDashboardStats.mockReturnValue({
      stats: null,
      recentQueries: [],
      loading: false,
      error: 'Network error',
      refetch: vi.fn(),
    });

    render(<Dashboard />);

    expect(screen.getByText('dashboard.error_loading')).toBeInTheDocument();
    expect(screen.getByText('Network error')).toBeInTheDocument();
    expect(screen.getByText('dashboard.retry')).toBeInTheDocument();
  });

  it('renders real data from API', () => {
    mockUseDashboardStats.mockReturnValue({
      stats: {
        cache_hit_rate: 0.92,
        query_count_24h: 1234,
        avg_retrieval_latency_ms: 310.5,
        total_indexed_docs: 42,
        total_chunks: 1800,
      },
      recentQueries: [
        { query: 'How to configure RBAC?', sources_count: 3, latency_ms: 285, timestamp: '2026-05-29T10:30:00Z' },
        { query: 'Explain hybrid retrieval', sources_count: 5, latency_ms: 312, timestamp: '2026-05-29T10:28:00Z' },
      ],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<Dashboard />);

    // Metrics rendered via i18n keys (mock returns key as-is)
    expect(screen.getByText('dashboard.total_queries')).toBeInTheDocument();
    expect(screen.getByText('1234')).toBeInTheDocument();
    expect(screen.getByText('dashboard.avg_latency')).toBeInTheDocument();
    expect(screen.getByText('310.5')).toBeInTheDocument();
    expect(screen.getByText('dashboard.cache_hit_rate')).toBeInTheDocument();
    expect(screen.getByText('92')).toBeInTheDocument();
    expect(screen.getByText('dashboard.indexed_docs')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();

    // Recent queries
    expect(screen.getByText('How to configure RBAC?')).toBeInTheDocument();
    expect(screen.getByText('Explain hybrid retrieval')).toBeInTheDocument();
  });

  it('renders Chinese translation', () => {
    mockT = (key: string) => {
      const zhMap: Record<string, string> = {
        'dashboard.title': '系统总览',
        'dashboard.subtitle': '实时指标与系统健康监控',
        'dashboard.total_queries': '查询总量',
        'dashboard.avg_latency': '平均延迟',
        'dashboard.cache_hit_rate': '缓存命中率',
        'dashboard.indexed_docs': '已索引文档',
        'dashboard.system_health': '系统健康',
        'dashboard.api_server': 'API 服务',
        'dashboard.database': '数据库',
        'dashboard.cache': '缓存',
        'dashboard.healthy': '正常',
        'dashboard.connected': '已连接',
        'dashboard.active': '活跃',
        'dashboard.error_loading': '加载失败',
        'dashboard.retry': '重试',
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
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<Dashboard />);

    expect(screen.getByText('系统总览')).toBeInTheDocument();
    expect(screen.getByText('实时指标与系统健康监控')).toBeInTheDocument();
    expect(screen.getByText('查询总量')).toBeInTheDocument();
    expect(screen.getByText('平均延迟')).toBeInTheDocument();
    expect(screen.getByText('缓存命中率')).toBeInTheDocument();
    expect(screen.getByText('已索引文档')).toBeInTheDocument();
    expect(screen.getByText('系统健康')).toBeInTheDocument();
    expect(screen.getByText('API 服务')).toBeInTheDocument();
    expect(screen.getByText('数据库')).toBeInTheDocument();
    expect(screen.getByText('正常')).toBeInTheDocument();
    expect(screen.getByText('已连接')).toBeInTheDocument();
    expect(screen.getByText('活跃')).toBeInTheDocument();
  });

  it('renders English translation', () => {
    mockT = (key: string) => {
      const enMap: Record<string, string> = {
        'dashboard.title': 'System Dashboard',
        'dashboard.subtitle': 'Real-time metrics and system health monitoring',
        'dashboard.total_queries': 'Total Queries',
        'dashboard.avg_latency': 'Avg Latency',
        'dashboard.cache_hit_rate': 'Cache Hit Rate',
        'dashboard.indexed_docs': 'Indexed Docs',
        'dashboard.system_health': 'System Health',
        'dashboard.api_server': 'API Server',
        'dashboard.database': 'Database',
        'dashboard.cache': 'Cache',
        'dashboard.healthy': 'Healthy',
        'dashboard.connected': 'Connected',
        'dashboard.active': 'Active',
        'dashboard.error_loading': 'Failed to load',
        'dashboard.retry': 'Retry',
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
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<Dashboard />);

    expect(screen.getByText('System Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Real-time metrics and system health monitoring')).toBeInTheDocument();
    expect(screen.getByText('Total Queries')).toBeInTheDocument();
    expect(screen.getByText('Avg Latency')).toBeInTheDocument();
    expect(screen.getByText('Cache Hit Rate')).toBeInTheDocument();
    expect(screen.getByText('Indexed Docs')).toBeInTheDocument();
    expect(screen.getByText('System Health')).toBeInTheDocument();
    expect(screen.getByText('API Server')).toBeInTheDocument();
    expect(screen.getByText('Database')).toBeInTheDocument();
    expect(screen.getByText('Healthy')).toBeInTheDocument();
    expect(screen.getByText('Connected')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
  });
});
