import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useAuthStore } from '../useAuthStore';

// Mock sessionStorage
const store: Record<string, string> = {};
beforeEach(() => {
  Object.keys(store).forEach((k) => delete store[k]);
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation((key: string) => store[key] ?? null);
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation((key: string, value: string) => { store[key] = value; });
  vi.spyOn(Storage.prototype, 'removeItem').mockImplementation((key: string) => { delete store[key]; });

  // Reset store
  useAuthStore.setState({
    apiKey: '',
    token: '',
    isAuthenticated: false,
    role: null,
  });
});

describe('useAuthStore', () => {
  describe('loginAsDemo', () => {
    it('returns true on success and stores JWT token', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => ({ access_token: 'demo.jwt.token', role: 'viewer' }),
      } as Response);

      const result = await useAuthStore.getState().loginAsDemo();
      expect(result).toBe(true);

      const state = useAuthStore.getState();
      expect(state.token).toBe('demo.jwt.token');
      expect(state.isAuthenticated).toBe(true);
      expect(state.role).toBe('viewer');
      expect(store['aureon_jwt_token']).toBe('demo.jwt.token');
      expect(store['aureon_role']).toBe('viewer');
    });

    it('returns false on API error', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: false,
        status: 429,
      } as Response);

      const result = await useAuthStore.getState().loginAsDemo();
      expect(result).toBe(false);

      const state = useAuthStore.getState();
      expect(state.isAuthenticated).toBe(false);
    });

    it('returns false on network error', async () => {
      vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('Network error'));

      const result = await useAuthStore.getState().loginAsDemo();
      expect(result).toBe(false);
    });

    it('calls the correct endpoint', async () => {
      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => ({ access_token: 'test', role: 'viewer' }),
      } as Response);

      await useAuthStore.getState().loginAsDemo();
      expect(fetchSpy).toHaveBeenCalledWith('/api/v1/security/demo-token', {
        method: 'POST',
      });
    });

    it('sets role to viewer (not admin)', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => ({ access_token: 'demo.jwt', role: 'viewer' }),
      } as Response);

      await useAuthStore.getState().loginAsDemo();
      expect(useAuthStore.getState().role).toBe('viewer');
    });
  });
});
