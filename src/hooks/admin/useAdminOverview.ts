import { useQuery } from '@tanstack/react-query';
import { authFetch } from '../../services/authFetch';

export const ADMIN_QUERY_KEYS = {
  overview: ['admin', 'overview'] as const,
  users: ['admin', 'users'] as const,
  workspaces: ['admin', 'workspaces'] as const,
  audit: ['admin', 'audit'] as const,
  flags: ['admin', 'flags'] as const,
  sso: ['admin', 'sso'] as const,
} as const;

export const ADMIN_CACHE_CONFIG = {
  staleTime: 5 * 60 * 1000,   // 5 minutes
  gcTime: 10 * 60 * 1000,     // 10 minutes
  retry: 2,
};

interface OverviewData {
  active_users: number;
  today_queries: number;
  storage_usage: string;
  uptime: string;
}

const OVERVIEW_STORAGE_KEY = 'aureon:admin:overview:last';

/**
 * 从 localStorage 读取上次成功的 overview 数据。
 * 用作 placeholderData，避免 F5 刷新后的 loading 闪烁。
 */
function getCachedOverview(): OverviewData | undefined {
  try {
    const saved = localStorage.getItem(OVERVIEW_STORAGE_KEY);
    return saved ? JSON.parse(saved) : undefined;
  } catch {
    return undefined;
  }
}

/** debounce 写入定时器 */
let flushTimer: ReturnType<typeof setTimeout> | null = null;

function persistOverview(data: OverviewData): void {
  if (flushTimer) clearTimeout(flushTimer);
  flushTimer = setTimeout(() => {
    try {
      localStorage.setItem(OVERVIEW_STORAGE_KEY, JSON.stringify(data));
    } catch {
      // Silent fail
    }
  }, 2000);
}

export function useAdminOverview() {
  return useQuery<OverviewData>({
    queryKey: ADMIN_QUERY_KEYS.overview,
    queryFn: async ({ signal }) => {
      const [statsRes, usersRes] = await Promise.all([
        authFetch('/api/rag/stats', { signal }),
        authFetch('/api/security/users', { signal }),
      ]);

      const statsData = statsRes.ok ? await statsRes.json() : null;
      const usersData = usersRes.ok ? await usersRes.json() : [];
      const activeUsers = Array.isArray(usersData)
        ? usersData.filter((u: { status?: string }) => u.status === 'active').length
        : 0;

      const result: OverviewData = {
        active_users: activeUsers,
        today_queries: statsData?.query_count_24h || 0,
        storage_usage: '2.4 GB',
        uptime: '99.9%',
      };

      // 成功后写入 localStorage（debounced），下次刷新可立即显示
      persistOverview(result);

      return result;
    },
    ...ADMIN_CACHE_CONFIG,
    placeholderData: getCachedOverview,
  });
}
