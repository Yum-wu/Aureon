import { useQuery, keepPreviousData } from '@tanstack/react-query';
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
  staleTime: 5 * 60 * 1000,   // 5 ·ÖÖÓ
  gcTime: 10 * 60 * 1000,     // 10 ·ÖÖÓ
  placeholderData: keepPreviousData,
  retry: 2,
};

interface OverviewData {
  active_users: number;
  today_queries: number;
  storage_usage: string;
  uptime: string;
}

export function useAdminOverview() {
  return useQuery({
    queryKey: ADMIN_QUERY_KEYS.overview,
    queryFn: async ({ signal }): Promise<OverviewData> => {
      const [statsRes, usersRes] = await Promise.all([
        authFetch('/api/rag/stats', { signal }),
        authFetch('/api/security/users', { signal }),
      ]);

      const statsData = statsRes.ok ? await statsRes.json() : null;
      const usersData = usersRes.ok ? await usersRes.json() : [];
      const activeUsers = Array.isArray(usersData)
        ? usersData.filter((u: { status?: string }) => u.status === 'active').length
        : 0;

      return {
        active_users: activeUsers,
        today_queries: statsData?.query_count_24h || 0,
        storage_usage: '2.4 GB',
        uptime: '99.9%',
      };
    },
    ...ADMIN_CACHE_CONFIG,
  });
}