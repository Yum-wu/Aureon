import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { authFetch } from '../../services/authFetch';
import { ADMIN_QUERY_KEYS } from './useAdminOverview';

export interface AuditFilters {
  dateFrom: string;
  dateTo: string;
  user: string;
  actionType: string;
  severity: string;
}

export interface AuditEntry {
  id: number;
  timestamp: string;
  user: string;
  action: string;
  resource: string;
  severity: 'info' | 'warning' | 'critical';
  details: string;
}

export function useAdminAudit(filters: AuditFilters) {
  return useQuery<AuditEntry[]>({
    queryKey: [...ADMIN_QUERY_KEYS.audit, filters],
    queryFn: async ({ signal }) => {
      const params = new URLSearchParams();
      if (filters.user) params.set('user', filters.user);
      if (filters.actionType) params.set('action', filters.actionType);
      if (filters.severity) params.set('severity', filters.severity);
      if (filters.dateFrom) params.set('from', filters.dateFrom);
      if (filters.dateTo) params.set('to', filters.dateTo);

      const res = await authFetch(`/api/audit/logs?${params.toString()}`, { signal });
      if (!res.ok) return [];
      const data = await res.json();
      return Array.isArray(data) ? data : [];
    },
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
    placeholderData: keepPreviousData,
    retry: 2,
  });
}
