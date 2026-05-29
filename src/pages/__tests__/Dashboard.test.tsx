import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

// Mock useDashboardStats hook
const mockUseDashboardStats = vi.fn();
vi.mock('../../hooks/useDashboardStats', () => ({
  useDashboardStats: () => mockUseDashboardStats(),
}));

// Mock i18n
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import { Dashboard } from '../Dashboard';

describe('Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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

    // Should show skeleton / loading indicator
    expect(screen.getByTestId('dashboard-loading')).toBeInTheDocument();
    // Should NOT show metrics
    expect(screen.queryByText('Total Queries')).not.toBeInTheDocument();
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

    expect(screen.getByText(/加载失败/)).toBeInTheDocument();
    expect(screen.getByText('Network error')).toBeInTheDocument();
    expect(screen.getByText('重试')).toBeInTheDocument();
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

    // Metrics from real API
    expect(screen.getByText('Total Queries')).toBeInTheDocument();
    expect(screen.getByText('1234')).toBeInTheDocument();
    expect(screen.getByText('Avg Latency')).toBeInTheDocument();
    expect(screen.getByText('310.5')).toBeInTheDocument();
    expect(screen.getByText('Cache Hit Rate')).toBeInTheDocument();
    expect(screen.getByText('92')).toBeInTheDocument();
    expect(screen.getByText('Indexed Docs')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();

    // Recent queries
    expect(screen.getByText('How to configure RBAC?')).toBeInTheDocument();
    expect(screen.getByText('Explain hybrid retrieval')).toBeInTheDocument();
  });
});
