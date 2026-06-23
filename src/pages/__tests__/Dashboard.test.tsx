import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// ── Hooks mock ──
const mockUseDashboardData = vi.fn();
vi.mock('../../hooks/useDashboardData', () => ({
  useDashboardData: () => mockUseDashboardData(),
}));

vi.mock('../../hooks/useSystemHealth', () => ({
  useSystemHealth: () => ({ health: null, loading: true, error: null }),
}));

vi.mock('../../hooks/useRealtimeMetrics', () => ({
  useRealtimeMetrics: () => ({
    metrics: { qps: 0, ttft_p50: 0, ttft_p95: 0, tpot: 0, error_rate: 0, cache_hit_rate: 0, token_usage: 0, active_connections: 0, pipeline: {} },
    alerts: [],
    isConnected: false,
    connectionState: 'connecting',
    lastUpdated: null,
  }),
  REALTIME_STALE_THRESHOLD_MS: 15000,
}));

vi.mock('../../hooks/useLatencyHistory', () => ({
  useLatencyHistory: () => [],
}));

vi.mock('../../hooks/useCacheHistory', () => ({
  useCacheHistory: () => [],
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
  useLocation: () => ({ pathname: '/dashboard', search: '', hash: '', state: null, key: 'default' }),
}));

vi.mock('../../hooks/AuthContext', () => ({
  useAuth: () => ({
    login: vi.fn(),
    loginWithJWT: vi.fn(),
    logout: vi.fn(),
    isAuthenticated: false,
    apiKey: '',
    token: '',
    role: null,
  }),
}));

vi.mock('../../stores/useViewStore', () => ({
  useViewStore: (selector: (s: Record<string, unknown>) => unknown) => {
    const state: Record<string, unknown> = {
      dashboardTimeRange: '24h',
      setDashboardTimeRange: vi.fn(),
    };
    return selector(state);
  },
}));

// ── UI component mock ──
vi.mock('../../components/ui/Tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('../../components/ui/Card', () => ({
  Card: ({ children, ...props }: { children: React.ReactNode; className?: string }) => (
    <div data-testid="mock-card" {...props}>{children}</div>
  ),
}));
vi.mock('../../components/ui/Breadcrumb', () => ({
  Breadcrumb: () => null,
}));
vi.mock('../../components/charts/LineChart', () => ({
  LineChart: ({ title }: { title: string }) => <div>{title}</div>,
}));
vi.mock('../../components/charts/BarChart', () => ({
  BarChart: ({ title }: { title: string }) => <div>{title}</div>,
}));

// ── i18n mock ──
const mockT = (key: string) => key;

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => mockT(key) }),
}));

import { Dashboard } from '../Dashboard';

afterEach(() => {
  cleanup();
});

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

describe('Dashboard – loading state', () => {
  it('renders loading skeleton', () => {
    mockUseDashboardData.mockReturnValue({
      stats: null,
      recentQueries: [],
      queryVolume: [],
      isLoading: true,
      isLoadingStats: true,
      isLoadingVolume: true,
      error: null,
      refetch: vi.fn(),
    });

    renderWithQueryClient(<Dashboard />);
    expect(screen.getByTestId('dashboard-loading')).toBeInTheDocument();
  });
});

describe('Dashboard – error state', () => {
  it('renders error with retry', () => {
    mockUseDashboardData.mockReturnValue({
      stats: null,
      recentQueries: [],
      queryVolume: [],
      isLoading: false,
      isLoadingStats: false,
      isLoadingVolume: false,
      error: new Error('Network error'),
      refetch: vi.fn(),
    });

    renderWithQueryClient(<Dashboard />);
    expect(screen.getByText('dashboard.error_loading')).toBeInTheDocument();
    expect(screen.getByText('Network error')).toBeInTheDocument();
    expect(screen.getByText('dashboard.retry')).toBeInTheDocument();
  });
});
