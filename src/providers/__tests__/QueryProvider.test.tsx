import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, renderHook, waitFor } from '@testing-library/react';
import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { QueryProvider } from '../QueryProvider';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

function useTestQuery(key: string) {
  return useQuery({
    queryKey: ['test', key],
    queryFn: async () => {
      const res = await fetch('/api/test');
      return res.json();
    },
    staleTime: 60_000,
  });
}

describe('QueryProvider', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });
  afterEach(() => localStorage.clear());

  it('renders children', () => {
    const { getByText } = render(
      <QueryProvider><div>child</div></QueryProvider>,
    );
    expect(getByText('child')).toBeInTheDocument();
  });

  it('persists query cache to localStorage after fetch', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ value: 'cached' }),
    });

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryProvider>{children}</QueryProvider>
    );
    const { result } = renderHook(() => useTestQuery('persist'), { wrapper });

    await waitFor(() => expect(result.current.data).toEqual({ value: 'cached' }));
    await new Promise((r) => setTimeout(r, 1100));

    expect(localStorage.getItem('aureon:query-cache')).not.toBeNull();
    const persisted = JSON.parse(localStorage.getItem('aureon:query-cache')!);
    expect(persisted.clientState.queries.length).toBeGreaterThan(0);
  });

  it('restores cache from localStorage on remount (no refetch when fresh)', async () => {
    const cachedData = { value: 'from-cache' };
    const timestamp = Date.now();
    const cachePayload = {
      buster: '1.0.0',
      timestamp,
      clientState: {
        queries: [{
          queryKey: ['test', 'restore'],
          queryHash: JSON.stringify(['test', 'restore']),
          state: {
            data: cachedData, dataUpdateCount: 1, dataUpdatedAt: timestamp,
            error: null, errorUpdateCount: 0, errorUpdatedAt: 0,
            fetchFailureCount: 0, fetchFailureReason: null, fetchMeta: null,
            isInvalidated: false, status: 'success', fetchStatus: 'idle',
          },
        }],
        mutations: [],
      },
    };
    localStorage.setItem('aureon:query-cache', JSON.stringify(cachePayload));

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryProvider>{children}</QueryProvider>
    );
    const { result } = renderHook(() => useTestQuery('restore'), { wrapper });

    await waitFor(() => expect(result.current.data).toEqual(cachedData));
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('discards cache when buster mismatches', async () => {
    const stalePayload = {
      buster: 'OLD_VERSION_0.0.1', timestamp: Date.now(),
      clientState: { queries: [], mutations: [] },
    };
    localStorage.setItem('aureon:query-cache', JSON.stringify(stalePayload));

    mockFetch.mockResolvedValueOnce({
      ok: true, json: () => Promise.resolve({ value: 'fresh' }),
    });

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryProvider>{children}</QueryProvider>
    );
    const { result } = renderHook(() => useTestQuery('buster'), { wrapper });

    await waitFor(() => expect(result.current.data).toEqual({ value: 'fresh' }));
    expect(mockFetch).toHaveBeenCalled();
  });
});
