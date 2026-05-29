import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

import { useDocuments } from '../useDocuments';

describe('useDocuments', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('starts with loading state', () => {
    mockFetch.mockReturnValue(new Promise(() => {})); // never resolves
    const { result } = renderHook(() => useDocuments());
    expect(result.current.loading).toBe(true);
    expect(result.current.documents).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  it('fetches documents successfully', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        documents: [
          { title: 'Guide', source: 'guide.md', file_type: 'md', chunk_count: 10, status: 'ready' },
        ],
        total_docs: 1,
        total_chunks: 10,
      }),
    });

    const { result } = renderHook(() => useDocuments());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.documents).toHaveLength(1);
    expect(result.current.totalDocs).toBe(1);
    expect(result.current.totalChunks).toBe(10);
    expect(result.current.error).toBeNull();
  });

  it('handles fetch error', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
    });

    const { result } = renderHook(() => useDocuments());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('HTTP 500');
    expect(result.current.documents).toEqual([]);
  });

  it('handles network error', async () => {
    mockFetch.mockRejectedValue(new Error('Network fail'));

    const { result } = renderHook(() => useDocuments());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('Network fail');
  });

  it('refetch triggers new fetch', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ documents: [], total_docs: 0, total_chunks: 0 }),
    });

    const { result } = renderHook(() => useDocuments());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    mockFetch.mockClear();
    result.current.refetch();

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });
});
