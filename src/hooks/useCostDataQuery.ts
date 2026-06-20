/**
 * useCostDataQuery — TanStack Query 版成本数据钩子
 * 替代原 useCostData（useEffect + cancelled flag 模式）
 *
 * 改进：
 * - 4 个请求各自独立 useQuery，一个失败不阻塞其他
 * - timeRange 变化时自动取消旧请求
 * - staleTime: 60s
 */

import { useQueries } from '@tanstack/react-query';
import { authFetch } from '../services/authFetch';

export type CostTimeRange = '7d' | '30d' | '90d';

export interface CostSummary {
  totalCost: number;
  burnRate: number;
  totalTokens: number;
  budgetUsed: number;
  budgetTotal: number;
  costChange?: number;
  burnTrend?: 'up' | 'down' | 'stable';
  data_available?: boolean;
}

export interface CostTrendPoint {
  date: string;
  cost: number;
  tokens: number;
}

export interface CostBreakdown {
  category: string;
  cost: number;
  percentage: number;
}

export interface TopConsumer {
  name: string;
  cost: number;
  tokens: number;
  percentage: number;
}

interface CostDataResult {
  summary: CostSummary | null;
  trends: CostTrendPoint[];
  breakdown: CostBreakdown[];
  topConsumers: TopConsumer[];
  isLoading: boolean;
  error: Error | null;
  refetch: () => void;
}

export function useCostDataQuery(timeRange: CostTimeRange = '30d'): CostDataResult {
  const days = timeRange === '7d' ? 7 : timeRange === '30d' ? 30 : 90;

  const results = useQueries({
    queries: [
      {
        queryKey: ['cost', 'summary', timeRange],
        queryFn: async ({ signal }: { signal: AbortSignal }) => {
          const res = await authFetch(`/api/cost/summary?period=${timeRange}`, { signal });
          if (res.status === 401 || res.status === 403) {
            throw new Error('需要管理员权限才能查看成本数据');
          }
          if (!res.ok) throw new Error(`Cost summary failed: ${res.status}`);
          const json = await res.json();
          return {
            totalCost: json.total_cost ?? 0,
            burnRate: json.burn_rate ?? 0,
            totalTokens: json.total_tokens ?? 0,
            budgetUsed: json.budget_used_pct ?? 0,
            budgetTotal: json.budget_total ?? 0,
            burnTrend: json.trend_direction ?? 'stable',
            data_available: json.data_available,
          } as CostSummary;
        },
        staleTime: 60_000,
      },
      {
        queryKey: ['cost', 'trend', days],
        queryFn: async ({ signal }: { signal: AbortSignal }) => {
          const res = await authFetch(`/api/cost/trend?days=${days}`, { signal });
          if (!res.ok) return [] as CostTrendPoint[];
          const json = await res.json();
          return (Array.isArray(json) ? json : []).map((t: Record<string, unknown>) => ({
            date: String(t.date ?? ''),
            cost: Number(t.cost ?? 0),
            tokens: Number(t.tokens ?? 0),
          })) as CostTrendPoint[];
        },
        staleTime: 60_000,
      },
      {
        queryKey: ['cost', 'breakdown', timeRange],
        queryFn: async ({ signal }: { signal: AbortSignal }) => {
          const res = await authFetch(`/api/cost/breakdown?by=model&period=${timeRange}`, { signal });
          if (!res.ok) return [] as CostBreakdown[];
          const json = await res.json();
          const raw = json.breakdown;
          if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
            const total = Object.values(raw as Record<string, number>).reduce(
              (s, v) => s + (Number(v) || 0), 0,
            );
            return Object.entries(raw as Record<string, number>).map(([cat, cost]) => ({
              category: cat,
              cost: Number(cost) || 0,
              percentage: total > 0 ? ((Number(cost) || 0) / total) * 100 : 0,
            })) as CostBreakdown[];
          }
          return Array.isArray(raw)
            ? raw.map((b: Record<string, unknown>) => ({
                category: String(b.category ?? b.model ?? ''),
                cost: Number(b.cost ?? 0),
                percentage: Number(b.percentage ?? 0),
              })) as CostBreakdown[]
            : ([] as CostBreakdown[]);
        },
        staleTime: 60_000,
      },
      {
        queryKey: ['cost', 'consumers'],
        queryFn: async ({ signal }: { signal: AbortSignal }) => {
          const res = await authFetch('/api/cost/top-consumers?limit=10', { signal });
          if (!res.ok) return [] as TopConsumer[];
          const json = await res.json();
          const arr = Array.isArray(json) ? json : [];
          const total = arr.reduce(
            (s: number, c: Record<string, unknown>) => s + (Number(c.cost_usd ?? 0)), 0,
          );
          return arr.map((c: Record<string, unknown>) => ({
            name: String(c.workspace_id ?? c.name ?? 'Unknown'),
            cost: Number(c.cost_usd ?? c.cost ?? 0),
            tokens: Number(c.tokens ?? 0),
            percentage: total > 0 ? (Number(c.cost_usd ?? 0) / total) * 100 : 0,
          })) as TopConsumer[];
        },
        staleTime: 60_000,
      },
    ],
  });

  const [summaryQ, trendQ, breakdownQ, consumersQ] = results;
  const isLoading = results.some((r) => r.isLoading);
  const error = results.find((r) => r.error)?.error as Error | null;

  return {
    summary: summaryQ.data ?? null,
    trends: trendQ.data ?? [],
    breakdown: breakdownQ.data ?? [],
    topConsumers: consumersQ.data ?? [],
    isLoading,
    error,
    refetch: () => {
      results.forEach((r) => r.refetch());
    },
  };
}
