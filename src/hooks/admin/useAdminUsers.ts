import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { authFetch } from '../../services/authFetch';
import { ADMIN_QUERY_KEYS, ADMIN_CACHE_CONFIG } from './useAdminOverview';
import { toast } from '../../utils/toast';

interface UserRecord {
  id: string;
  email: string;
  display_name: string;
  role: 'super_admin' | 'admin' | 'editor' | 'viewer';
  status: 'active' | 'suspended' | 'invited';
  last_login: string | null;
}

export function useAdminUsers() {
  return useQuery<UserRecord[]>({
    queryKey: ADMIN_QUERY_KEYS.users,
    queryFn: async ({ signal }) => {
      const res = await authFetch('/api/security/users', { signal });
      if (!res.ok) return [];
      const data = await res.json();
      return Array.isArray(data) ? data : [];
    },
    ...ADMIN_CACHE_CONFIG,
  });
}

export function useUpdateUserRole() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async ({ userId, role }: { userId: string; role: string }) => {
      const res = await authFetch(`/api/security/users/${userId}/role`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role }),
      });
      if (!res.ok) throw new Error('Role update failed');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ADMIN_QUERY_KEYS.users });
      toast.success('Role updated successfully');
    },
    onError: () => {
      toast.error('Failed to update role');
    },
  });
}

export function useSuspendUser() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async (userId: string) => {
      const res = await authFetch(`/api/security/users/${userId}/suspend`, { method: 'POST' });
      if (!res.ok) throw new Error('Suspend failed');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ADMIN_QUERY_KEYS.users });
      toast.success('User suspended');
    },
    onError: () => {
      toast.error('Failed to suspend user');
    },
  });
}

export function useDeleteUser() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async (userId: string) => {
      const res = await authFetch(`/api/security/users/${userId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Delete failed');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ADMIN_QUERY_KEYS.users });
      toast.success('User deleted');
    },
    onError: () => {
      toast.error('Failed to delete user');
    },
  });
}
