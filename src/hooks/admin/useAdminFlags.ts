import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query';
import { authFetch } from '../../services/authFetch';
import { ADMIN_QUERY_KEYS, ADMIN_CACHE_CONFIG } from './useAdminOverview';
import { toast } from '../../utils/toast';

interface FeatureFlag {
  key: string;
  name: string;
  description: string;
  enabled: boolean;
  rules: string;
}

export function useAdminFlags() {
  return useQuery<FeatureFlag[]>({
    queryKey: ADMIN_QUERY_KEYS.flags,
    queryFn: async ({ signal }) => {
      const res = await authFetch('/api/feature-flags/', { signal });
      if (!res.ok) return [];
      const data = await res.json();
      return Array.isArray(data) ? data : [];
    },
    ...ADMIN_CACHE_CONFIG,
    placeholderData: keepPreviousData,
  });
}

export function useToggleFlag() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async (flagKey: string) => {
      const res = await authFetch(`/api/feature-flags/${flagKey}/toggle`, { method: 'POST' });
      if (!res.ok) throw new Error('Toggle failed');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ADMIN_QUERY_KEYS.flags });
      toast.success('Feature flag toggled');
    },
    onError: () => {
      toast.error('Failed to toggle feature flag');
    },
  });
}
