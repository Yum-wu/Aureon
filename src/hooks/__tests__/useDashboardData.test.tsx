import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

import { useDashboardData } from '../useDashboardData';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('useDashboardData', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('starts with loading state when no cache', () => {
    mockFetch.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useDashboardData(), {
      wrapper: createWrapper(),
    });
    expect(result.current.isLoading).toBe(true);
    expect(result.current.stats).toBeUndefined();
    expect(result.current.error).toBeNull();
  });

  it('fetches stats, recent queries, and volume successfully', async () => {
    const statsData = {
      cache_hit_rate: 0.85,
      query_count_24h: 100,
      avg_retrieval_latency_ms: 250,
      total_indexed_docs: 10,
      total_chunks: 500,
    };
    const recentData = {
      queries: [
        { query: 'What is RAG?', sources_count: 3, latency_ms: 200, timestamp: '2026-05-29T10:00:00Z' },
      ],
    };
    const volumeData = { data: [{ date: '2026-06-18', count: 42 }], total: 42 };

    mockFetch
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(statsData) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(recentData) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(volumeData) });

    const { result } = renderHook(() => useDashboardData(), {
      wrapper: createWrapper(),
    });

    // With placeholderData, isLoading is false immediately — wait for actual data
    await waitFor(() => {
      expect(result.current.stats?.query_count_24h).toBe(100);
    });

    expect(result.current.stats).toEqual(statsData);
    expect(result.current.recentQueries).toHaveLength(1);
    expect(result.current.queryVolume).toEqual([{ date: '2026-06-18', count: 42 }]);
  });

  it('handles fetch failure with error state', async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: false, status: 503, json: () => Promise.resolve({ detail: 'Redis down' }) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ queries: [] }) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ data: [] }) });

    const { result } = renderHook(() => useDashboardData(), {
      wrapper: createWrapper(),
    });

    // With placeholderData, wait for error to appear
    await waitFor(() => {
      expect(result.current.error).toBeTruthy();
    });
  });

  it('provides refetch function', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ cache_hit_rate: 0, query_count_24h: 0, avg_retrieval_latency_ms: 0, total_indexed_docs: 0, total_chunks: 0 }),
    });

    const { result } = renderHook(() => useDashboardData(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(typeof result.current.refetch).toBe('function');
  });
});
