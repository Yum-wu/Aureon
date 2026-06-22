/**
 * useLatencyHistory — accumulates latency data from WebSocket metrics
 * Persists to localStorage for trend visualization in Dashboard.
 *
 * 写入 debounce：避免每次 WebSocket tick（最高每秒数次）都触发 localStorage 写入，
 * 防止主线程阻塞。最多 2 秒刷一次。
 */

import { useState, useEffect, useRef } from 'react';
import { useRealtimeMetrics } from './useRealtimeMetrics';

interface LatencyPoint {
  ts: number;
  ttft: number;
  tpot?: number;
  e2e?: number;
}

const STORAGE_KEY = 'aureon:latency:history';
const MAX_POINTS = 100;
const PERSIST_DEBOUNCE_MS = 2000;

export function useLatencyHistory(): LatencyPoint[] {
  const { metrics } = useRealtimeMetrics();

  const [history, setHistory] = useState<LatencyPoint[]>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });

  useEffect(() => {
    if (metrics.ttft_p50 > 0) {
      setHistory((prev) => {
        const next = [
          ...prev,
          {
            ts: Date.now(),
            ttft: metrics.ttft_p50,
            tpot: metrics.tpot,
            e2e: metrics.ttft_p50 + (metrics.tpot || 0) * 50,
          },
        ];
        return next.slice(-MAX_POINTS);
      });
    }
  }, [metrics.ttft_p50, metrics.tpot]);

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
