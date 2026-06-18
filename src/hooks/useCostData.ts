/**
 * 成本治理数据 Hook
 * 从 API 获取成本数据，同时监听 cost.update WebSocket 消息
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
  /** 已用预算 */
  budgetUsed: number;
  /** 总预算 */
  budgetTotal: number;
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

  // 从 API 获取成本数据
  useEffect(() => {
    let cancelled = false;

    async function fetchCostData() {
      try {
        setLoading(true);
        setError(null);

        const res = await authFetch(`/api/cost/summary?range=${timeRange}`);
        if (!res.ok) {
          throw new Error(`请求失败: ${res.status}`);
        }
        const data = await res.json();

        if (!cancelled) {
          setSummary(data.summary ?? null);
          setTrends(data.trends ?? []);
          setBreakdown(data.breakdown ?? []);
          setTopConsumers(data.top_consumers ?? []);
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
      // 增量更新汇总数据
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
