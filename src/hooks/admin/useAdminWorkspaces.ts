import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { authFetch } from '../../services/authFetch';
import { ADMIN_QUERY_KEYS, ADMIN_CACHE_CONFIG } from './useAdminOverview';

interface WorkspaceRecord {
  id: string;
  name: string;
  member_count: number;
  quota: string;
  status: 'active' | 'archived';
}

export function useAdminWorkspaces() {
  return useQuery<WorkspaceRecord[]>({
    queryKey: ADMIN_QUERY_KEYS.workspaces,
    queryFn: async ({ signal }) => {
      const res = await authFetch('/api/security/workspaces', { signal });
      if (!res.ok) return [];
      const data = await res.json();
      return Array.isArray(data) ? data : [];
    },
    ...ADMIN_CACHE_CONFIG,
    placeholderData: keepPreviousData,
  });
}
