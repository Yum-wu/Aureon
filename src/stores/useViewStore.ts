/**
 * useViewStore — 用户意图快照
 * 持久化 timeRange + onboardingCompleted 到 SafeStorage
 * 按用户身份隔离：aureon:viewstate:{userId}
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { safeStorage } from './safeStorage';
import { useAuthStore } from './useAuthStore';
import type { ViewState } from './types';

/** 从 auth 状态派生用户标识 */
function getUserId(): string {
  try {
    const { token, apiKey } = useAuthStore.getState();
    if (token) {
      // JWT payload decode（base64url）
      const parts = token.split('.');
      if (parts.length === 3) {
        const payload = JSON.parse(
          atob(parts[1].replace(/-/g, '+').replace(/_/g, '/'))
        );
        return payload.sub || 'jwt_user';
      }
    }
    if (apiKey) {
      return `key_${apiKey.slice(0, 8)}`;
    }
  } catch {
    // decode 失败降级
  }
  return 'anonymous';
}

export const useViewStore = create<ViewState>()(
  persist(
    (set) => ({
      // 默认值
      dashboardTimeRange: '24h',
      analyticsTimeRange: '24h',
      costTimeRange: '30d',
      onboardingCompleted: false,

      // Actions
      setDashboardTimeRange: (range) => set({ dashboardTimeRange: range }),
      setAnalyticsTimeRange: (range) => set({ analyticsTimeRange: range }),
      setCostTimeRange: (range) => set({ costTimeRange: range }),
      completeOnboarding: () => set({ onboardingCompleted: true }),
      resetOnboarding: () => set({ onboardingCompleted: false }),
    }),
    {
      name: `aureon:viewstate:${getUserId()}`,
      storage: createJSONStorage(() => safeStorage),
      version: 1,
    }
  )
);
