import { useState, useEffect, useCallback, useRef } from "react";
import { authFetch } from "../services/authFetch";
import type { StatsResponse, RecentQuery } from "../types/dashboard";

interface DashboardData {
  stats: StatsResponse | null;
  recentQueries: RecentQuery[];
  queryVolume: { date: string; count: number }[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

const STATS_URL = "/api/rag/stats";
const RECENT_URL = "/api/rag/queries/recent?limit=5";
const VOLUME_URL = "/api/rag/query-volume?days=7";
const BASE_INTERVAL = 30_000;
const MAX_INTERVAL = 300_000;

export function useDashboardStats(): DashboardData {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [recentQueries, setRecentQueries] = useState<RecentQuery[]>([]);
  const [queryVolume, setQueryVolume] = useState<{ date: string; count: number }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const retryCountRef = useRef(0);
  const [trigger, setTrigger] = useState(0);

  const refetch = useCallback(() => {
    setTrigger((prev) => prev + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout>;

    async function fetchAll() {
      try {
        const [statsRes, recentRes, volumeRes] = await Promise.all([
          authFetch(STATS_URL),
          authFetch(RECENT_URL),
          authFetch(VOLUME_URL),
        ]);

        if (!statsRes.ok) {
          const errBody = await statsRes.json().catch(() => null);
          const msg = errBody?.detail || `Stats request failed: ${statsRes.status}`;
          throw new Error(msg);
        }

        if (!recentRes.ok) {
          const errBody = await recentRes.json().catch(() => null);
          const msg = errBody?.detail || `Recent queries request failed: ${recentRes.status}`;
          throw new Error(msg);
        }

        const statsData: StatsResponse = await statsRes.json();
        const recentData = await recentRes.json();
        const volumeData = volumeRes.ok ? await volumeRes.json() : { data: [] };

        if (!cancelled) {
          setStats(statsData);
          setRecentQueries(recentData.queries ?? []);
          setQueryVolume(volumeData.data ?? []);
          setError(null);
          retryCountRef.current = 0;
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
          retryCountRef.current += 1;
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
          // Exponential backoff on failure, fixed interval on success
          const delay =
            retryCountRef.current > 0
              ? Math.min(BASE_INTERVAL * Math.pow(2, retryCountRef.current), MAX_INTERVAL)
              : BASE_INTERVAL;
          timeoutId = setTimeout(fetchAll, delay);
        }
      }
    }

    fetchAll();
    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  }, [trigger]);

  return { stats, recentQueries, queryVolume, loading, error, refetch };
}
