import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import React from 'react';

let mockOnMessage: ((data: unknown) => void) | null = null;
let mockIsConnected = false;
let mockConnectionState = 'disconnected';

vi.mock('../../hooks/useWebSocket', () => ({
  useWebSocket: (_path: string, opts: { onMessage?: (data: unknown) => void }) => {
    mockOnMessage = opts.onMessage ?? null;
    return {
      isConnected: mockIsConnected,
      connectionState: mockConnectionState,
    };
  },
}));

import {
  RealtimeMetricsProvider,
  useRealtimeMetricsContext,
} from '../RealtimeMetricsProvider';

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <RealtimeMetricsProvider>{children}</RealtimeMetricsProvider>
);

const SAMPLE_TICK = {
  qps: 1.5,
  ttft_p50: 120,
  ttft_p95: 250,
  tpot: 40,
  error_rate: 0.01,
  cache_hit_rate: 0.85,
  token_usage: 2000,
  active_connections: 5,
  pipeline: { retrieval_ms: 80, generation_ms: 200 },
};

describe('RealtimeMetricsProvider', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    mockOnMessage = null;
    mockIsConnected = false;
    mockConnectionState = 'disconnected';
  });

  afterEach(() => vi.useRealTimers());

  it('provides default metrics before any tick', () => {
    const { result } = renderHook(() => useRealtimeMetricsContext(), { wrapper });
    expect(result.current.metrics.qps).toBe(0);
    expect(result.current.lastUpdated).toBeNull();
  });

  it('updates metrics when tick arrives', () => {
    const { result } = renderHook(() => useRealtimeMetricsContext(), { wrapper });
    act(() => {
      mockOnMessage?.({ type: 'metrics.tick', data: SAMPLE_TICK });
    });
    expect(result.current.metrics.qps).toBe(1.5);
    expect(result.current.metrics.pipeline.retrieval_ms).toBe(80);
    expect(result.current.lastUpdated).not.toBeNull();
  });

  it('exposes connection state', () => {
    mockIsConnected = true;
    mockConnectionState = 'connected';
    const { result } = renderHook(() => useRealtimeMetricsContext(), { wrapper });
    expect(result.current.isConnected).toBe(true);
  });

  it('collects alerts', () => {
    const { result } = renderHook(() => useRealtimeMetricsContext(), { wrapper });
    act(() => {
      mockOnMessage?.({
        type: 'alert',
        data: { id: 'a1', level: 'critical', message: 'High error rate', timestamp: 1700000000000 },
      });
    });
    expect(result.current.alerts).toHaveLength(1);
  });

  it('shares state across multiple consumers', () => {
    // Both consumers must be inside the same Provider instance
    function usePair() {
      const a = useRealtimeMetricsContext();
      const b = useRealtimeMetricsContext();
      return { a, b };
    }
    const { result } = renderHook(() => usePair(), { wrapper });
    act(() => {
      mockOnMessage?.({ type: 'metrics.tick', data: SAMPLE_TICK });
    });
    expect(result.current.a.metrics.qps).toBe(1.5);
    expect(result.current.b.metrics.qps).toBe(1.5);
  });

  it('throws when used outside provider', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => renderHook(() => useRealtimeMetricsContext())).toThrow();
    spy.mockRestore();
  });
});
