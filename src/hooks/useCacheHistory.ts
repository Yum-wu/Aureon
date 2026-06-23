/**
 * useCacheHistory — accumulates cache_hit_rate data from WebSocket metrics
 * Persists to localStorage for trend visualization in Dashboard.
 *
 * 后端无 cache 历史序列数据(已验证),所以前端通过 WebSocket 实时
 * tick 累积历史,作为"缓存命中率趋势"图的数据源。
 *
 * 写入 debounce：避免每次 WebSocket tick 都触发 localStorage 写入。
 */

import { useState, useEffect, useRef } from 'react';
import { useRealtimeMetrics } from './useRealtimeMetrics';

interface CachePoint {
  ts: number;
  hitRate: number;
}

const STORAGE_KEY = 'aureon:cache:history';
const MAX_POINTS = 60;
const PERSIST_DEBOUNCE_MS = 2000;

export function useCacheHistory(): CachePoint[] {
  const { metrics } = useRealtimeMetrics();

  const [history, setHistory] = useState<CachePoint[]>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });

  useEffect(() => {
    if (metrics.cache_hit_rate > 0) {
      setHistory((prev) => {
        const next = [
          ...prev,
          {
            ts: Date.now(),
            hitRate: metrics.cache_hit_rate,
          },
        ];
        return next.slice(-MAX_POINTS);
      });
    }
  }, [metrics.cache_hit_rate]);

  // Debounced persist：高频 tick 下避免持续 localStorage 写入
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (flushTimerRef.current) clearTimeout(flushTimerRef.current);
    flushTimerRef.current = setTimeout(() => {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
      } catch {
        // Silently fail when localStorage is full
      }
    }, PERSIST_DEBOUNCE_MS);
    return () => {
      if (flushTimerRef.current) clearTimeout(flushTimerRef.current);
    };
  }, [history]);

  return history;
}
