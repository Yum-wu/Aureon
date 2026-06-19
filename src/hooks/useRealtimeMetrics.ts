/**
 * 实时指标 Hook
 * 连接 /ws/dashboard，解析 metrics.tick 消息
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useWebSocket } from './useWebSocket';
import type { WSConnectionState } from '../services/ws';

/** 实时指标数据 */
export interface RealtimeMetrics {
  /** 每秒查询数 */
  qps: number;
  /** TTFT P50（毫秒） */
  ttft_p50: number;
  /** TTFT P95（毫秒） */
  ttft_p95: number;
  /** 每个 Token 延迟（毫秒） */
  tpot: number;
  /** 错误率（0-1） */
  error_rate: number;
  /** 缓存命中率（0-1） */
  cache_hit_rate: number;
  /** Token 使用量 */
  token_usage: number;
  /** 活跃连接数 */
  active_connections: number;
}

/** 告警信息 */
export interface MetricAlert {
  id: string;
  level: 'warning' | 'critical';
  message: string;
  timestamp: number;
}

interface UseRealtimeMetricsReturn {
  /** 当前指标 */
  metrics: RealtimeMetrics | null;
  /** 告警列表 */
  alerts: MetricAlert[];
  /** 是否已连接 */
  isConnected: boolean;
  /** 连接状态 */
  connectionState: WSConnectionState;
  /** 最后更新时间 */
  lastUpdated: number | null;
}

/** 默认指标值 */
const DEFAULT_METRICS: RealtimeMetrics = {
  qps: 0,
  ttft_p50: 0,
  ttft_p95: 0,
  tpot: 0,
  error_rate: 0,
  cache_hit_rate: 0,
  token_usage: 0,
  active_connections: 0,
};

export function useRealtimeMetrics(): UseRealtimeMetricsReturn {
  const [metrics, setMetrics] = useState<RealtimeMetrics | null>(null);
  const [alerts, setAlerts] = useState<MetricAlert[]>([]);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const alertsRef = useRef(alerts);

  // 在 effect 中同步 ref，避免 render 中更新
  useEffect(() => { alertsRef.current = alerts; }, [alerts]);

  const handleMessage = useCallback((data: unknown) => {
    if (!data || typeof data !== 'object') return;
    const msg = data as Record<string, unknown>;

    // 处理 metrics.tick 消息
    if (msg.type === 'metrics.tick' && msg.data) {
      const tickData = msg.data as Record<string, unknown>;
      setMetrics({
        qps: Number(tickData.qps ?? 0),
        ttft_p50: Number(tickData.ttft_p50 ?? 0),
        ttft_p95: Number(tickData.ttft_p95 ?? 0),
        tpot: Number(tickData.tpot ?? 0),
        error_rate: Number(tickData.error_rate ?? 0),
        cache_hit_rate: Number(tickData.cache_hit_rate ?? 0),
        token_usage: Number(tickData.token_usage ?? 0),
        active_connections: Number(tickData.active_connections ?? 0),
      });
      setLastUpdated(Date.now());
    }

    // 处理 alert 消息
    if (msg.type === 'alert' && msg.data) {
      const alertData = msg.data as MetricAlert;
      setAlerts((prev) => [alertData, ...prev].slice(0, 50));
    }
  }, []);

  const { isConnected, connectionState } = useWebSocket('/ws/dashboard', {
    onMessage: handleMessage,
    autoReconnect: true,
  });

  return {
    metrics: metrics ?? DEFAULT_METRICS,
    alerts,
    isConnected,
    connectionState,
    lastUpdated,
  };
}
