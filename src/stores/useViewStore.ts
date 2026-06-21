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

/** Default view state for migration fallback */
const DEFAULT_VIEW_STATE: Pick<ViewState, 'dashboardTimeRange' | 'analyticsTimeRange' | 'costTimeRange' | 'onboardingCompleted'> = {
  dashboardTimeRange: '24h',
  analyticsTimeRange: '24h',
  costTimeRange: '30d',
  onboardingCompleted: false,
};

/**
 * State migration function — handles incompatible version changes.
 *
 * Migration history:
 * - v0 → v1: old timeRange single field → split dashboardTimeRange
 */
export function migrateViewState(
  persistedState: unknown,
  version: number,
): Partial<ViewState> {
  const base = { ...DEFAULT_VIEW_STATE };

  if (!persistedState || typeof persistedState !== 'object') return base;

  const old = persistedState as Record<string, unknown>;

  // Future version: downgrade to defaults
  if (version > 1) return base;

  // v0 → v1: timeRange → dashboardTimeRange
  if (version < 1) {
    if (typeof old.timeRange === 'string') {
      base.dashboardTimeRange = old.timeRange as ViewState['dashboardTimeRange'];
    }
  }

  // Whitelist copy of known fields
  if (typeof old.dashboardTimeRange === 'string') base.dashboardTimeRange = old.dashboardTimeRange as ViewState['dashboardTimeRange'];
  if (typeof old.analyticsTimeRange === 'string') base.analyticsTimeRange = old.analyticsTimeRange as ViewState['analyticsTimeRange'];
  if (typeof old.costTimeRange === 'string') base.costTimeRange = old.costTimeRange as ViewState['costTimeRange'];
  if (typeof old.onboardingCompleted === 'boolean') base.onboardingCompleted = old.onboardingCompleted;

  return base;
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
      migrate: migrateViewState,
    }
  )
);
