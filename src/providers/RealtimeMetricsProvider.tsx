/**
 * RealtimeMetricsProvider — global realtime metrics Context
 * Mounts the single /ws/dashboard connection at app root.
 */
/* eslint-disable react-refresh/only-export-components -- Context provider + hook is a standard pattern */

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
  type ReactNode,
} from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import type { WSConnectionState } from '../services/ws';

export const REALTIME_STALE_THRESHOLD_MS = 15_000;

export interface PipelineStages {
  retrieval_ms?: number;
  rerank_ms?: number;
  crag_ms?: number;
  generation_ms?: number;
}

export interface RealtimeMetrics {
  qps: number;
  ttft_p50: number;
  ttft_p95: number;
  tpot: number;
  error_rate: number;
  cache_hit_rate: number;
  token_usage: number;
  active_connections: number;
  pipeline: PipelineStages;
  /** Dashboard-only extended fields (set by baseMetrics from HTTP stats) */
  saturation?: number;
  alert_count?: number;
  latency_trend?: number[];
  tpot_trend?: number[];
  e2e_trend?: number[];
}

export interface MetricAlert {
  id: string;
  level: 'warning' | 'critical';
  message: string;
  timestamp: number;
}

interface RealtimeMetricsContextValue {
  metrics: RealtimeMetrics;
  alerts: MetricAlert[];
  isConnected: boolean;
  connectionState: WSConnectionState;
  lastUpdated: number | null;
}

const DEFAULT_METRICS: RealtimeMetrics = {
  qps: 0,
  ttft_p50: 0,
  ttft_p95: 0,
  tpot: 0,
  error_rate: 0,
  cache_hit_rate: 0,
  token_usage: 0,
  active_connections: 0,
  pipeline: {},
};

const RealtimeMetricsContext = createContext<RealtimeMetricsContextValue | null>(null);

export function RealtimeMetricsProvider({ children }: { children: ReactNode }) {
  const [metrics, setMetrics] = useState<RealtimeMetrics>(DEFAULT_METRICS);
  const [alerts, setAlerts] = useState<MetricAlert[]>([]);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const staleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const resetLastUpdated = useCallback(() => {
    setLastUpdated(null);
  }, []);

  const handleMessage = useCallback((data: unknown) => {
    if (!data || typeof data !== 'object') return;
    const msg = data as Record<string, unknown>;

    if (msg.type === 'metrics.tick' && msg.data) {
      const tickData = msg.data as Record<string, unknown>;
      const rawPipeline = tickData.pipeline as Record<string, number> | undefined;
      setMetrics({
        qps: Number(tickData.qps ?? 0),
        ttft_p50: Number(tickData.ttft_p50 ?? 0),
        ttft_p95: Number(tickData.ttft_p95 ?? 0),
        tpot: Number(tickData.tpot ?? 0),
        error_rate: Number(tickData.error_rate ?? 0),
        cache_hit_rate: Number(tickData.cache_hit_rate ?? 0),
        token_usage: Number(tickData.token_usage ?? 0),
        active_connections: Number(tickData.active_connections ?? 0),
        pipeline: rawPipeline ? {
          retrieval_ms: rawPipeline.retrieval_ms,
          rerank_ms: rawPipeline.rerank_ms,
          crag_ms: rawPipeline.crag_ms,
          generation_ms: rawPipeline.generation_ms,
        } : {},
      });
      setLastUpdated(Date.now());

      if (staleTimerRef.current) clearTimeout(staleTimerRef.current);
      staleTimerRef.current = setTimeout(resetLastUpdated, REALTIME_STALE_THRESHOLD_MS);
    }

    if (msg.type === 'alert' && msg.data) {
      const alertData = msg.data as MetricAlert;
      setAlerts((prev) => [alertData, ...prev].slice(0, 50));
    }
  }, [resetLastUpdated]);

  const { isConnected, connectionState } = useWebSocket('/ws/dashboard', {
    onMessage: handleMessage,
    autoReconnect: true,
  });

  useEffect(() => {
    if (!isConnected) {
      resetLastUpdated();
      if (staleTimerRef.current) {
        clearTimeout(staleTimerRef.current);
        staleTimerRef.current = null;
      }
    }
  }, [isConnected, resetLastUpdated]);

  useEffect(() => {
    return () => {
      if (staleTimerRef.current) clearTimeout(staleTimerRef.current);
    };
  }, []);

  const value: RealtimeMetricsContextValue = {
    metrics,
    alerts,
    isConnected,
    connectionState,
    lastUpdated,
  };

  return (
    <RealtimeMetricsContext.Provider value={value}>
      {children}
    </RealtimeMetricsContext.Provider>
  );
}

export function useRealtimeMetricsContext(): RealtimeMetricsContextValue {
  const ctx = useContext(RealtimeMetricsContext);
  if (!ctx) {
    throw new Error('useRealtimeMetricsContext must be used within RealtimeMetricsProvider');
  }
  return ctx;
}
