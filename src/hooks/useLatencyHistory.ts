/**
 * useLatencyHistory ¡ª accumulates latency data from WebSocket metrics
 * Persists to localStorage for trend visualization in Dashboard.
 */

import { useState, useEffect } from 'react';
import { useRealtimeMetrics } from './useRealtimeMetrics';

interface LatencyPoint {
  ts: number;
  ttft: number;
  tpot?: number;
  e2e?: number;
}

const STORAGE_KEY = 'aureon:latency:history';
const MAX_POINTS = 100;

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

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
    } catch {
      // Silently fail when localStorage is full
    }
  }, [history]);

  return history;
}
