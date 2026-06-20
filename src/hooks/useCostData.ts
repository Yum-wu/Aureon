/**
 * 成本治理数据 Hook
 * 从多个独立 API 端点获取成本数据，同时监听 cost.update WebSocket 消息
 *
 * 端点映射:
 *   /api/cost/summary       → CostSummary (snake_case → camelCase)
 *   /api/cost/trend         → CostTrendPoint[]
 *   /api/cost/breakdown     → CostBreakdown[]
 *   /api/cost/top-consumers → TopConsumer[]
 */

import { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../services/authFetch';
import { useWebSocket } from './useWebSocket';

/** 时间范围 */
export type CostTimeRange = '7d' | '30d' | '90d';

/** 成本汇总 */
export interface CostSummary {
  /** 总成本 */
  totalCost: number;
  /** 燃烧速率（$/day） */
  burnRate: number;
  /** 总 Token 数 */
  totalTokens: number;
  /** 已用预算百分比 */
  budgetUsed: number;
  /** 总预算 */
  budgetTotal: number;
  /** 成本变化百分比（环比） */
  costChange?: number;
  /** 燃烧速率趋势 */
  burnTrend?: 'up' | 'down' | 'stable';
}

/** 成本趋势数据点 */
export interface CostTrendPoint {
  date: string;
  cost: number;
  tokens: number;
}

/** 成本分项 */
export interface CostBreakdown {
  category: string;
  cost: number;
  percentage: number;
}

/** Top 消费者 */
export interface TopConsumer {
  name: string;
  cost: number;
  tokens: number;
  percentage: number;
}

interface UseCostDataReturn {
  /** 成本汇总 */
  summary: CostSummary | null;
  /** 成本趋势 */
  trends: CostTrendPoint[];
  /** 成本分项 */
  breakdown: CostBreakdown[];
  /** Top 消费者 */
  topConsumers: TopConsumer[];
  /** 加载状态 */
  loading: boolean;
  /** 错误信息 */
  error: string | null;
  /** 手动刷新 */
  refetch: () => void;
}

export function useCostData(timeRange: CostTimeRange = '30d'): UseCostDataReturn {
  const [summary, setSummary] = useState<CostSummary | null>(null);
  const [trends, setTrends] = useState<CostTrendPoint[]>([]);
  const [breakdown, setBreakdown] = useState<CostBreakdown[]>([]);
  const [topConsumers, setTopConsumers] = useState<TopConsumer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [trigger, setTrigger] = useState(0);

  const refetch = useCallback(() => {
    setTrigger((prev) => prev + 1);
  }, []);

  // 从多个独立 API 端点获取成本数据
  useEffect(() => {
    let cancelled = false;

    async function fetchCostData() {
      try {
        setLoading(true);
        setError(null);

        // 并行请求 4 个独立端点
        const [summaryRes, trendRes, breakdownRes, consumersRes] = await Promise.all([
          authFetch(`/api/cost/summary?period=${timeRange}`),
          authFetch(`/api/cost/trend?days=${timeRange === '7d' ? 7 : timeRange === '30d' ? 30 : 90}`),
          authFetch(`/api/cost/breakdown?by=model&period=${timeRange}`),
          authFetch(`/api/cost/top-consumers?limit=10`),
        ]);

        // 任一端点返回 401/403 → 提示需要认证
        const anyAuth = [summaryRes, trendRes, breakdownRes, consumersRes]
          .some((r) => r.status === 401 || r.status === 403);
        if (anyAuth) {
          if (!cancelled) {
            setError('需要管理员权限才能查看成本数据。请使用 X-API-Key 或管理员账户登录。');
            setSummary(null);
            setTrends([]);
            setBreakdown([]);
            setTopConsumers([]);
          }
          return;
        }

        // 任一关键端点失败 → 报错
        if (!summaryRes.ok) {
          throw new Error(`请求失败: ${summaryRes.status}`);
        }

        // ── 1. Summary: snake_case → camelCase ──
        const summaryJson = await summaryRes.json();
        const mappedSummary: CostSummary = {
          totalCost: summaryJson.total_cost ?? 0,
          burnRate: summaryJson.burn_rate ?? 0,
          totalTokens: summaryJson.total_tokens ?? 0,
          budgetUsed: summaryJson.budget_used_pct ?? 0,
          budgetTotal: summaryJson.budget_total ?? 0,
          burnTrend: summaryJson.trend_direction ?? 'stable',
        };

        // ── 2. Trend ──
        let mappedTrends: CostTrendPoint[] = [];
        if (trendRes.ok) {
          const trendJson = await trendRes.json();
          const rawTrends = Array.isArray(trendJson) ? trendJson : [];
          mappedTrends = rawTrends.map((t: Record<string, unknown>) => ({
            date: String(t.date ?? ''),
            cost: Number(t.cost ?? 0),
            tokens: Number(t.tokens ?? 0),
          }));
        }

        // ── 3. Breakdown: { breakdown: [{model, cost}], period } → CostBreakdown[] ──
        let mappedBreakdown: CostBreakdown[] = [];
        if (breakdownRes.ok) {
          const breakdownJson = await breakdownRes.json();
          const rawBreakdown = breakdownJson.breakdown;
          if (typeof rawBreakdown === 'object' && rawBreakdown !== null && !Array.isArray(rawBreakdown)) {
            // Backend returns { model_name: cost_value } dict
            const totalCost = Object.values(rawBreakdown as Record<string, number>).reduce(
              (sum, v) => sum + (Number(v) || 0), 0,
            );
            mappedBreakdown = Object.entries(rawBreakdown as Record<string, number>).map(
              ([category, cost]) => ({
                category,
                cost: Number(cost) || 0,
                percentage: totalCost > 0 ? ((Number(cost) || 0) / totalCost) * 100 : 0,
              }),
            );
          } else if (Array.isArray(rawBreakdown)) {
            mappedBreakdown = rawBreakdown.map((b: Record<string, unknown>) => ({
              category: String(b.category ?? b.model ?? ''),
              cost: Number(b.cost ?? 0),
              percentage: Number(b.percentage ?? 0),
            }));
          }
        }

        // ── 4. Top Consumers: [{workspace_id, cost_usd}] → TopConsumer[] ──
        let mappedConsumers: TopConsumer[] = [];
        if (consumersRes.ok) {
          const consumersJson = await consumersRes.json();
          const rawConsumers = Array.isArray(consumersJson) ? consumersJson : [];
          const totalConsumerCost = rawConsumers.reduce(
            (sum, c: Record<string, unknown>) => sum + (Number(c.cost_usd ?? 0)), 0,
          );
          mappedConsumers = rawConsumers.map((c: Record<string, unknown>) => ({
            name: String(c.workspace_id ?? c.name ?? 'Unknown'),
            cost: Number(c.cost_usd ?? c.cost ?? 0),
            tokens: Number(c.tokens ?? 0),
            percentage: totalConsumerCost > 0
              ? (Number(c.cost_usd ?? 0) / totalConsumerCost) * 100
              : 0,
          }));
        }

        if (!cancelled) {
          setSummary(mappedSummary);
          setTrends(mappedTrends);
          setBreakdown(mappedBreakdown);
          setTopConsumers(mappedConsumers);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '加载成本数据失败');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    fetchCostData();
    return () => {
      cancelled = true;
    };
  }, [timeRange, trigger]);

  // 监听 WebSocket cost.update 消息
  const handleWSMessage = useCallback((data: unknown) => {
    if (!data || typeof data !== 'object') return;
    const msg = data as Record<string, unknown>;

    if (msg.type === 'cost.update' && msg.data) {
      const updateData = msg.data as Record<string, unknown>;
      if (updateData.summary) {
        setSummary(updateData.summary as CostSummary);
      }
    }
  }, []);

  useWebSocket('/ws/dashboard', {
    onMessage: handleWSMessage,
    autoReconnect: true,
  });

  return { summary, trends, breakdown, topConsumers, loading, error, refetch };
}
