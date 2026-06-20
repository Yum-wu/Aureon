/**
 * useDashboardData — TanStack Query 版 Dashboard 数据钩子
 * 替代原 useDashboardStats（useEffect + cancelled flag 模式）
 *
 * 改进：
 * - 自动 AbortSignal 竞态防护（查询键变化时取消旧请求）
 * - 内置缓存与 staleTime 控制
 * - 统一错误处理
 */

import { useQuery } from '@tanstack/react-query';
import { authFetch } from '../services/authFetch';
import type { StatsResponse, RecentQuery } from '../types/dashboard';

const STATS_URL = '/api/rag/stats';
const RECENT_URL = '/api/rag/queries/recent?limit=5';
const VOLUME_URL = '/api/rag/query-volume?days=7';

/** 查询键常量，供外部做缓存失效时引用 */
export const DASHBOARD_QUERY_KEYS = {
  stats: ['dashboard', 'stats'] as const,
  recent: ['dashboard', 'recent'] as const,
  volume: ['dashboard', 'volume'] as const,
} as const;

interface QueryVolumePoint {
  date: string;
  count: number;
}

interface DashboardData {
  stats: StatsResponse | undefined;
  recentQueries: RecentQuery[];
  queryVolume: QueryVolumePoint[];
  isLoading: boolean;
  error: Error | null;
  refetch: () => void;
}

/**
 * 获取 Dashboard 统计数据
 * 使用 TanStack Query 管理请求生命周期：
 * - staleTime: 20s（20 秒内切换页面不重新请求）
 * - refetchInterval: 30s（轮询替代原 setTimeout 递归）
 */
export function useDashboardData(): DashboardData {
  const statsQuery = useQuery<StatsResponse>({
    queryKey: DASHBOARD_QUERY_KEYS.stats,
    queryFn: async ({ signal }) => {
      const res = await authFetch(STATS_URL, { signal });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `Stats request failed: ${res.status}`);
      }
      return res.json();
    },
    staleTime: 20_000,
    refetchInterval: 30_000,
  });

  const recentQuery = useQuery<{ queries: RecentQuery[] }>({
    queryKey: DASHBOARD_QUERY_KEYS.recent,
    queryFn: async ({ signal }) => {
      const res = await authFetch(RECENT_URL, { signal });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `Recent queries failed: ${res.status}`);
      }
      return res.json();
    },
    staleTime: 20_000,
    refetchInterval: 30_000,
  });

  const volumeQuery = useQuery<{ data: QueryVolumePoint[] }>({
    queryKey: DASHBOARD_QUERY_KEYS.volume,
    queryFn: async ({ signal }) => {
      const res = await authFetch(VOLUME_URL, { signal });
      if (!res.ok) return { data: [] };
      return res.json();
    },
    staleTime: 20_000,
    refetchInterval: 30_000,
  });

  const isLoading = statsQuery.isLoading || recentQuery.isLoading || volumeQuery.isLoading;
  const error = statsQuery.error || recentQuery.error || volumeQuery.error;

  return {
    stats: statsQuery.data,
    recentQueries: recentQuery.data?.queries ?? [],
    queryVolume: volumeQuery.data?.data ?? [],
    isLoading,
    error: error as Error | null,
    refetch: () => {
      statsQuery.refetch();
      recentQuery.refetch();
      volumeQuery.refetch();
    },
  };
}
