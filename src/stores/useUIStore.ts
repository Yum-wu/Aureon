/** UI 状态 Store（SafeStorage 持久化） */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { safeStorage } from './safeStorage';
import type { UIState } from './types';

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      mobileMenuOpen: false,
      aiDisclaimerEnabled: true,
      sidebarCollapsed: false,
      mobileSidebarOpen: false,

      setMobileMenuOpen: (open: boolean) => {
        set({ mobileMenuOpen: open });
      },

      toggleAiDisclaimer: () => {
        set((state) => ({ aiDisclaimerEnabled: !state.aiDisclaimerEnabled }));
      },

      setSidebarCollapsed: (collapsed: boolean) => {
        set({ sidebarCollapsed: collapsed });
      },

      toggleSidebarCollapsed: () => {
        set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed }));
      },

      setMobileSidebarOpen: (open: boolean) => {
        set({ mobileSidebarOpen: open });
      },
    }),
    {
      name: 'aureon:ui',
      storage: createJSONStorage(() => safeStorage),
      // 持久化 aiDisclaimerEnabled + sidebarCollapsed，mobileMenuOpen/mobileSidebarOpen 是会话级状态
      partialize: (state) => ({
        aiDisclaimerEnabled: state.aiDisclaimerEnabled,
        sidebarCollapsed: state.sidebarCollapsed,
      }),
    }
  )
);
