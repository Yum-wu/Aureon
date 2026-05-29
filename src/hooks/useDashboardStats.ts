import { useState, useEffect, useCallback } from "react";
import type { StatsResponse, RecentQuery } from "../types/dashboard";

interface DashboardData {
  stats: StatsResponse | null;
  recentQueries: RecentQuery[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

const STATS_URL = "/api/rag/stats";
const RECENT_URL = "/api/rag/queries/recent?limit=5";
const BASE_INTERVAL = 30_000;
const MAX_INTERVAL = 300_000;

export function useDashboardStats(): DashboardData {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [recentQueries, setRecentQueries] = useState<RecentQuery[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const [trigger, setTrigger] = useState(0);

  const refetch = useCallback(() => {
    setTrigger((prev) => prev + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout>;

    async function fetchAll() {
      try {
        const [statsRes, recentRes] = await Promise.all([
          fetch(STATS_URL),
          fetch(RECENT_URL),
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

        if (!cancelled) {
          setStats(statsData);
          setRecentQueries(recentData.queries ?? []);
          setError(null);
          setRetryCount(0);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
          setRetryCount((prev) => prev + 1);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
          // Exponential backoff on failure, fixed interval on success
          const delay =
            retryCount > 0
              ? Math.min(BASE_INTERVAL * Math.pow(2, retryCount), MAX_INTERVAL)
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
  }, [trigger, retryCount]);

  return { stats, recentQueries, loading, error, refetch };
}
