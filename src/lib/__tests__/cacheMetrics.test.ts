import { describe, it, expect, beforeEach, vi } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import { attachCacheMetrics, getCacheStats, resetCacheStats } from '../cacheMetrics';

describe('cacheMetrics', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 0 } },
    });
    resetCacheStats();
  });

  it('counts hits and misses', async () => {
    attachCacheMetrics(queryClient);
    const fetcher = vi.fn().mockResolvedValue('data');
    await queryClient.fetchQuery({ queryKey: ['k1'], queryFn: fetcher });
    queryClient.getQueryData(['k1']);
    const stats = getCacheStats();
    expect(stats.hits + stats.misses).toBeGreaterThan(0);
  });

  it('resets stats', () => {
    resetCacheStats();
    const stats = getCacheStats();
    expect(stats.hits).toBe(0);
    expect(stats.misses).toBe(0);
  });

  it('calculates hit rate', () => {
    resetCacheStats();
    attachCacheMetrics(queryClient);
    const stats = getCacheStats();
    expect(stats).toHaveProperty('hitRate');
    expect(typeof stats.hitRate).toBe('number');
    expect(stats.hitRate).toBeGreaterThanOrEqual(0);
    expect(stats.hitRate).toBeLessThanOrEqual(1);
  });

  it('detach returns cleanup function', () => {
    const detach = attachCacheMetrics(queryClient);
    expect(typeof detach).toBe('function');
    detach();
  });
});
