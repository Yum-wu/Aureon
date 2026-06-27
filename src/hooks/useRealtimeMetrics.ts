export {
  useRealtimeMetricsContext as useRealtimeMetrics,
  REALTIME_STALE_THRESHOLD_MS,
} from '../providers/RealtimeMetricsProvider';

export type {
  RealtimeMetrics,
  PipelineStages,
  MetricAlert,
} from '../providers/RealtimeMetricsProvider';

export interface UseRealtimeMetricsReturn {
  metrics: import('../providers/RealtimeMetricsProvider').RealtimeMetrics;
  alerts: import('../providers/RealtimeMetricsProvider').MetricAlert[];
  isConnected: boolean;
  connectionState: import('../services/ws').WSConnectionState;
  lastUpdated: number | null;
}
