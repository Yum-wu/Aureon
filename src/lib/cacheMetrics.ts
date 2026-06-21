/**
 * cacheMetrics.ts — TanStack Query cache hit rate statistics
 */

import type { QueryClient } from '@tanstack/react-query';

interface CacheStats {
  hits: number;
  misses: number;
  hitRate: number;
}

let hits = 0;
let misses = 0;
let unsubscribe: (() => void) | null = null;

export function attachCacheMetrics(queryClient: QueryClient): () => void {
  if (unsubscribe) unsubscribe();

  const cache = queryClient.getQueryCache();

  unsubscribe = cache.subscribe((event) => {
    const query = event.query;
    const state = query.state;

    if (event.type === 'added') {
      misses++;
    } else if (event.type === 'updated' && state.fetchStatus === 'idle' && state.status === 'success') {
      hits++;
    }
  });

  return () => {
    if (unsubscribe) { unsubscribe(); unsubscribe = null; }
  };
}

export function getCacheStats(): CacheStats {
  const total = hits + misses;
  return { hits, misses, hitRate: total === 0 ? 0 : hits / total };
}

export function resetCacheStats(): void {
  hits = 0;
  misses = 0;
}
