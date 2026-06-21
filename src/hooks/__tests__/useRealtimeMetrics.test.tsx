import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import React from 'react';

const mockOnMessage = vi.fn();
let mockIsConnected = true;
let mockConnectionState = 'connected' as string;

vi.mock('../../hooks/useWebSocket', () => ({
  useWebSocket: (_path: string, opts: { onMessage?: (data: unknown) => void }) => {
    mockOnMessage.mockImplementation(opts.onMessage ?? (() => {}));
    return {
      isConnected: mockIsConnected,
      connectionState: mockConnectionState,
    };
  },
}));

import { useRealtimeMetrics, REALTIME_STALE_THRESHOLD_MS } from '../useRealtimeMetrics';
import { RealtimeMetricsProvider } from '../../providers/RealtimeMetricsProvider';

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <RealtimeMetricsProvider>{children}</RealtimeMetricsProvider>
);

function emitTick(data: Record<string, unknown>) {
  mockOnMessage({ type: 'metrics.tick', data });
}

const SAMPLE_TICK = {
  qps: 1, ttft_p50: 100, ttft_p95: 200, tpot: 50,
  error_rate: 0, cache_hit_rate: 80, token_usage: 1000, active_connections: 3,
};

describe('useRealtimeMetrics (via Context) stale timeout', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    mockIsConnected = true;
    mockConnectionState = 'connected';
  });
  afterEach(() => vi.useRealTimers());

  it('lastUpdated is null initially', () => {
    const { result } = renderHook(() => useRealtimeMetrics(), { wrapper });
    expect(result.current.lastUpdated).toBeNull();
  });

  it('sets lastUpdated when metrics.tick arrives', () => {
    const { result } = renderHook(() => useRealtimeMetrics(), { wrapper });
    act(() => { emitTick(SAMPLE_TICK); });
    expect(result.current.lastUpdated).not.toBeNull();
    expect(result.current.metrics?.qps).toBe(1);
  });

  it('resets lastUpdated to null after stale timeout', () => {
    const { result } = renderHook(() => useRealtimeMetrics(), { wrapper });
    act(() => { emitTick(SAMPLE_TICK); });
    expect(result.current.lastUpdated).not.toBeNull();
    act(() => { vi.advanceTimersByTime(REALTIME_STALE_THRESHOLD_MS + 1000); });
    expect(result.current.lastUpdated).toBeNull();
  });

  it('resets lastUpdated when WebSocket disconnects', () => {
    mockIsConnected = true;
    const { result, rerender } = renderHook(() => useRealtimeMetrics(), { wrapper });
    act(() => { emitTick(SAMPLE_TICK); });
    expect(result.current.lastUpdated).not.toBeNull();
    mockIsConnected = false;
    mockConnectionState = 'disconnected';
    rerender();
    expect(result.current.lastUpdated).toBeNull();
  });

  it('refreshes timeout when new tick arrives before expiry', () => {
    const { result } = renderHook(() => useRealtimeMetrics(), { wrapper });
    act(() => { emitTick(SAMPLE_TICK); });
    act(() => { vi.advanceTimersByTime(REALTIME_STALE_THRESHOLD_MS / 2); });
    act(() => { emitTick({ ...SAMPLE_TICK, qps: 2 }); });
    expect(result.current.lastUpdated).not.toBeNull();
    act(() => { vi.advanceTimersByTime(REALTIME_STALE_THRESHOLD_MS / 2 + 1000); });
    expect(result.current.lastUpdated).not.toBeNull();
  });
});
