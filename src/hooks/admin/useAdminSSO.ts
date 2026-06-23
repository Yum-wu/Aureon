import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { authFetch } from '../../services/authFetch';
import { ADMIN_QUERY_KEYS, ADMIN_CACHE_CONFIG } from './useAdminOverview';

interface SSOProvider {
  id: number;
  name: string;
  provider_type: string;
  client_id: string;
  enabled: boolean;
  created_at: string;
}

export function useAdminSSO() {
  return useQuery<SSOProvider[]>({
    queryKey: ADMIN_QUERY_KEYS.sso,
    queryFn: async ({ signal }) => {
      const res = await authFetch('/api/security/sso/providers', { signal });
      if (!res.ok) return [];
      const data = await res.json();
      return Array.isArray(data) ? data : [];
    },
    ...ADMIN_CACHE_CONFIG,
    placeholderData: keepPreviousData,
  });
}
