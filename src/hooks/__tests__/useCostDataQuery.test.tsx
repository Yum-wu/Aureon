import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

import { useCostDataQuery } from '../useCostDataQuery';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('useCostDataQuery', () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.restoreAllMocks());

  it('starts with loading state', () => {
    mockFetch.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useCostDataQuery('30d'), {
      wrapper: createWrapper(),
    });
    expect(result.current.isLoading).toBe(true);
    expect(result.current.summary).toBeNull();
  });

  it('fetches summary, trend, breakdown, consumers', async () => {
    const summary = { total_cost: 12.5, burn_rate: 0.5, total_tokens: 50000, budget_used_pct: 25, budget_total: 50, trend_direction: 'stable' };
    const trend = [{ date: '2026-06-18', cost: 0.5, tokens: 5000 }];
    const breakdown = { breakdown: { 'qwen3.6-flash': 10, 'bge-m3': 2.5 }, period: '30d' };
    const consumers = [{ workspace_id: 'ws-1', cost_usd: 8, tokens: 30000 }];

    mockFetch
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(summary) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(trend) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(breakdown) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(consumers) });

    const { result } = renderHook(() => useCostDataQuery('30d'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.summary?.totalCost).toBe(12.5);
    expect(result.current.trends).toHaveLength(1);
    expect(result.current.breakdown.length).toBeGreaterThan(0);
    expect(result.current.topConsumers).toHaveLength(1);
    expect(result.current.error).toBeFalsy();
  });

  it('handles 403 auth error', async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: false, status: 403 })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve([]) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({}) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve([]) });

    const { result } = renderHook(() => useCostDataQuery('30d'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.error).toBeTruthy();
  });
});
