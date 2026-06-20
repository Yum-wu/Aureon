import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// Mock useWebSocket — 手动控制消息回调
const mockOnMessage = vi.fn();
let mockIsConnected = true;
let mockConnectionState = 'connected' as string;

vi.mock('../useWebSocket', () => ({
  useWebSocket: (_path: string, opts: { onMessage?: (data: unknown) => void }) => {
    mockOnMessage.mockImplementation(opts.onMessage ?? (() => {}));
    return {
      isConnected: mockIsConnected,
      connectionState: mockConnectionState,
    };
  },
}));

import { useRealtimeMetrics, REALTIME_STALE_THRESHOLD_MS } from '../useRealtimeMetrics';

function emitTick(data: Record<string, number>) {
  mockOnMessage({ type: 'metrics.tick', data });
}

const SAMPLE_TICK = {
  qps: 1,
  ttft_p50: 100,
  ttft_p95: 200,
  tpot: 50,
  error_rate: 0,
  cache_hit_rate: 80,
  token_usage: 1000,
  active_connections: 3,
};

describe('useRealtimeMetrics stale timeout', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    mockIsConnected = true;
    mockConnectionState = 'connected';
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('lastUpdated is null initially', () => {
    const { result } = renderHook(() => useRealtimeMetrics());
    expect(result.current.lastUpdated).toBeNull();
  });

  it('sets lastUpdated when metrics.tick arrives', () => {
    const { result } = renderHook(() => useRealtimeMetrics());

    act(() => {
      emitTick(SAMPLE_TICK);
    });

    expect(result.current.lastUpdated).not.toBeNull();
    expect(result.current.metrics?.qps).toBe(1);
  });

  it('resets lastUpdated to null after stale timeout', () => {
    const { result } = renderHook(() => useRealtimeMetrics());

    act(() => {
      emitTick(SAMPLE_TICK);
    });

    expect(result.current.lastUpdated).not.toBeNull();

    // 快进到超时阈值之后
    act(() => {
      vi.advanceTimersByTime(REALTIME_STALE_THRESHOLD_MS + 1000);
    });

    expect(result.current.lastUpdated).toBeNull();
  });

  it('resets lastUpdated when WebSocket disconnects', () => {
    mockIsConnected = true;
    const { result, rerender } = renderHook(() => useRealtimeMetrics());

    act(() => {
      emitTick(SAMPLE_TICK);
    });

    expect(result.current.lastUpdated).not.toBeNull();

    // 模拟断开
    mockIsConnected = false;
    mockConnectionState = 'disconnected';
    rerender();

    expect(result.current.lastUpdated).toBeNull();
  });

  it('refreshes timeout when new tick arrives before expiry', () => {
    const { result } = renderHook(() => useRealtimeMetrics());

    act(() => {
      emitTick(SAMPLE_TICK);
    });

    // 快进到阈值的一半
    act(() => {
      vi.advanceTimersByTime(REALTIME_STALE_THRESHOLD_MS / 2);
    });

    // 收到新消息 — 重置计时器
    act(() => {
      emitTick({ ...SAMPLE_TICK, qps: 2 });
    });

    expect(result.current.lastUpdated).not.toBeNull();

    // 再快进到原阈值（从第一次消息算起已超时，但从第二次算起未超时）
    act(() => {
      vi.advanceTimersByTime(REALTIME_STALE_THRESHOLD_MS / 2 + 1000);
    });

    // 仍未超时
    expect(result.current.lastUpdated).not.toBeNull();
  });
});
