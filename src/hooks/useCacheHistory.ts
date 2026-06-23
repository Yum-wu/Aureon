/**
 * useCacheHistory — accumulates cache_hit_rate data from WebSocket metrics
 * Persists to localStorage for trend visualization in Dashboard.
 *
 * 后端无 cache 历史序列数据(已验证),所以前端通过 WebSocket 实时
 * tick 累积历史,作为"缓存命中率趋势"图的数据源。
 *
 * 双数据源:
 * 1. WebSocket 实时推送 (primary)
 * 2. API /analytics/cache 轮询 (fallback, 每60秒)
 *
 * 写入 debounce：避免每次 WebSocket tick 都触发 localStorage 写入。
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRealtimeMetrics } from './useRealtimeMetrics';
import { authFetch } from '../services/authFetch';

interface CachePoint {
  ts: number;
  hitRate: number;
}

const STORAGE_KEY = 'aureon:cache:history';
const MAX_POINTS = 60;
const PERSIST_DEBOUNCE_MS = 2000;
const API_POLL_INTERVAL_MS = 60_000; // 60秒轮询一次 API

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

  // 追加数据点（去重：避免同一秒内重复添加）
  const appendPoint = useCallback((hitRate: number) => {
    if (hitRate <= 0) return;
    setHistory((prev) => {
      const last = prev[prev.length - 1];
      // 去重：1秒内的相同值不重复添加
      if (last && last.hitRate === hitRate && Date.now() - last.ts < 1000) {
        return prev;
      }
      const next = [...prev, { ts: Date.now(), hitRate }];
      return next.slice(-MAX_POINTS);
    });
  }, []);

  // 数据源1: WebSocket 实时推送
  useEffect(() => {
    if (metrics.cache_hit_rate > 0) {
      appendPoint(metrics.cache_hit_rate);
    }
  }, [metrics.cache_hit_rate, appendPoint]);

  // 数据源2: API 轮询（WebSocket 数据为 0 时的 fallback）
  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;

    const pollCacheHitRate = async () => {
      try {
        const res = await authFetch('/api/rag/analytics/cache');
        if (res.ok) {
          const data = await res.json();
          if (data.hitRate > 0) {
            appendPoint(data.hitRate);
          }
        }
      } catch {
        // 静默失败
      }
    };

    // 立即轮询一次
    pollCacheHitRate();

    // 定时轮询
    timer = setInterval(pollCacheHitRate, API_POLL_INTERVAL_MS);

    return () => {
      if (timer) clearInterval(timer);
    };
  }, [appendPoint]);

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
