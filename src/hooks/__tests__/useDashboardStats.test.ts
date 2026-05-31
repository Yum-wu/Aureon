import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

import { useDashboardStats } from '../useDashboardStats';

describe('useDashboardStats', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('starts with loading state', () => {
    mockFetch.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useDashboardStats());
    expect(result.current.loading).toBe(true);
    expect(result.current.stats).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('fetches stats and recent queries successfully', async () => {
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

    mockFetch
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(statsData) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(recentData) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ data: [], total: 0 }) });

    const { result } = renderHook(() => useDashboardStats());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.stats).toEqual(statsData);
    expect(result.current.recentQueries).toHaveLength(1);
    expect(result.current.error).toBeNull();
  });

  it('handles stats fetch failure', async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: false, status: 503, json: () => Promise.resolve({ detail: 'Redis down' }) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ queries: [] }) });

    const { result } = renderHook(() => useDashboardStats());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('Redis down');
  });

  it('handles network error', async () => {
    mockFetch.mockRejectedValue(new Error('Network fail'));

    const { result } = renderHook(() => useDashboardStats());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('Network fail');
  });

  it('refetch triggers new fetch', async () => {
    mockFetch
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({ cache_hit_rate: 0, query_count_24h: 0, avg_retrieval_latency_ms: 0, total_indexed_docs: 0, total_chunks: 0 }) });

    const { result } = renderHook(() => useDashboardStats());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    mockFetch.mockClear();
    // Re-mock for refetch
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ cache_hit_rate: 0.9, query_count_24h: 50, avg_retrieval_latency_ms: 100, total_indexed_docs: 5, total_chunks: 200 }) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ queries: [] }) });

    result.current.refetch();

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });
});
