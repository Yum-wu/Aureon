/**
 * useAnalyticsData — TanStack Query 版分析数据钩子
 * 替代原 useAnalytics（useEffect + Promise.all 无 AbortSignal）
 *
 * 改进：
 * - 4 个请求各自独立 useQuery，一个失败不影响其他
 * - timeRange 变化时自动取消旧请求（AbortSignal）
 * - staleTime: 60s（分析数据不需要高频刷新）
 */

import { useQueries } from '@tanstack/react-query';
import { authFetch } from '../services/authFetch';

export interface UsageData {
  timeRange: string;
  total: number;
  perHour: number;
  byIntent: Record<string, number>;
  trend: { change: number; period: string };
  data_available?: boolean;
}

export interface LatencyData {
  timeRange: string;
  avg: number;
  p95: number;
  p99: number;
  breakdown: { retrieval: number; llm_first_token: number; llm_generation: number };
  trend: { avg_change: number; period: string };
  data_available?: boolean;
}

export interface TokenData {
  timeRange: string;
  input: number;
  output: number;
  total: number;
  cost: number;
  costPerQuery: number;
  model: string;
  trend: { input_change: number; output_change: number; period: string };
  data_available?: boolean;
}

export interface CacheData {
  hitRate: number;
  saves: number;
  latencyReduction: number;
  memoryUsage: string;
  data_available?: boolean;
}

interface AnalyticsResult {
  usage: UsageData | null;
  latency: LatencyData | null;
  tokens: TokenData | null;
  cache: CacheData | null;
  isLoading: boolean;
  error: Error | null;
  refetch: () => void;
}

export function useAnalyticsData(timeRange: string = '24h'): AnalyticsResult {
  const results = useQueries({
    queries: [
      {
        queryKey: ['analytics', 'usage', timeRange],
        queryFn: async ({ signal }: { signal: AbortSignal }) => {
          const res = await authFetch(`/api/rag/analytics/usage?time_range=${timeRange}`, { signal });
          if (!res.ok) throw new Error(`Usage fetch failed: ${res.status}`);
          return res.json() as Promise<UsageData>;
        },
        staleTime: 60_000,
      },
      {
        queryKey: ['analytics', 'latency', timeRange],
        queryFn: async ({ signal }: { signal: AbortSignal }) => {
          const res = await authFetch(`/api/rag/analytics/latency?time_range=${timeRange}`, { signal });
          if (!res.ok) throw new Error(`Latency fetch failed: ${res.status}`);
          return res.json() as Promise<LatencyData>;
        },
        staleTime: 60_000,
      },
      {
        queryKey: ['analytics', 'tokens', timeRange],
        queryFn: async ({ signal }: { signal: AbortSignal }) => {
          const res = await authFetch(`/api/rag/analytics/tokens?time_range=${timeRange}`, { signal });
          if (!res.ok) throw new Error(`Tokens fetch failed: ${res.status}`);
          return res.json() as Promise<TokenData>;
        },
        staleTime: 60_000,
      },
      {
        queryKey: ['analytics', 'cache'],
        queryFn: async ({ signal }: { signal: AbortSignal }) => {
          const res = await authFetch('/api/rag/analytics/cache', { signal });
          if (!res.ok) throw new Error(`Cache fetch failed: ${res.status}`);
          return res.json() as Promise<CacheData>;
        },
        staleTime: 60_000,
      },
    ],
  });

  const [usageQ, latencyQ, tokensQ, cacheQ] = results;
  const isLoading = results.some((r) => r.isLoading);
  const error = results.find((r) => r.error)?.error as Error | null;

  return {
    usage: usageQ.data ?? null,
    latency: latencyQ.data ?? null,
    tokens: tokensQ.data ?? null,
    cache: cacheQ.data ?? null,
    isLoading,
    error,
    refetch: () => {
      results.forEach((r) => r.refetch());
    },
  };
}
