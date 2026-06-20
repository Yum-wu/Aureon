import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

import { useAnalyticsData } from '../useAnalyticsData';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('useAnalyticsData', () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.restoreAllMocks());

  it('starts with loading state', () => {
    mockFetch.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useAnalyticsData('24h'), {
      wrapper: createWrapper(),
    });
    expect(result.current.isLoading).toBe(true);
    expect(result.current.usage).toBeNull();
  });

  it('fetches all four endpoints in parallel', async () => {
    const usage = { timeRange: '24h', total: 100, perHour: 4.2, byIntent: {}, trend: { change: 0, period: '' } };
    const latency = { timeRange: '24h', avg: 250, p95: 500, p99: 800, breakdown: { retrieval: 0, llm_first_token: 0, llm_generation: 0 }, trend: { avg_change: 0, period: '' } };
    const tokens = { timeRange: '24h', input: 5000, output: 3000, total: 8000, cost: 0.5, costPerQuery: 0.005, model: 'qwen', trend: { input_change: 0, output_change: 0, period: '' } };
    const cache = { hitRate: 0.85, saves: 50, latencyReduction: 120, memoryUsage: '128MB' };

    mockFetch
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(usage) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(latency) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(tokens) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(cache) });

    const { result } = renderHook(() => useAnalyticsData('24h'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.usage?.total).toBe(100);
    expect(result.current.latency?.avg).toBe(250);
    expect(result.current.tokens?.total).toBe(8000);
    expect(result.current.cache?.hitRate).toBe(0.85);
    expect(result.current.error).toBeFalsy();
  });

  it('handles 401 auth error', async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: false, status: 401 })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({}) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({}) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({}) });

    const { result } = renderHook(() => useAnalyticsData('24h'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.error).toBeTruthy();
  });

  it('refetches when timeRange changes', async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });

    const { rerender } = renderHook(({ tr }) => useAnalyticsData(tr), {
      wrapper: createWrapper(),
      initialProps: { tr: '24h' as string },
    });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });

    const callCount1 = mockFetch.mock.calls.length;
    rerender({ tr: '7d' });

    await waitFor(() => {
      expect(mockFetch.mock.calls.length).toBeGreaterThan(callCount1);
    });
  });
});
