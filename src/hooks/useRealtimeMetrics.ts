/**
 * useRealtimeMetrics — backward-compatible thin wrapper
 * Now reads from RealtimeMetricsContext instead of directly calling useWebSocket.
 * New code should use useRealtimeMetricsContext() directly.
 */

import { useRealtimeMetricsContext } from '../providers/RealtimeMetricsProvider';

export type {
  RealtimeMetrics,
  PipelineStages,
  MetricAlert,
} from '../providers/RealtimeMetricsProvider';

export const REALTIME_STALE_THRESHOLD_MS = 15_000;

export interface UseRealtimeMetricsReturn {
  metrics: import('../providers/RealtimeMetricsProvider').RealtimeMetrics;
  alerts: import('../providers/RealtimeMetricsProvider').MetricAlert[];
  isConnected: boolean;
  connectionState: import('../services/ws').WSConnectionState;
  lastUpdated: number | null;
}

export function useRealtimeMetrics(): UseRealtimeMetricsReturn {
  return useRealtimeMetricsContext();
}
