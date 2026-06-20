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

      setMobileMenuOpen: (open: boolean) => {
        set({ mobileMenuOpen: open });
      },

      toggleAiDisclaimer: () => {
        set((state) => ({ aiDisclaimerEnabled: !state.aiDisclaimerEnabled }));
      },
    }),
    {
      name: 'aureon:ui',
      storage: createJSONStorage(() => safeStorage),
      // 只持久化 aiDisclaimerEnabled，mobileMenuOpen 是会话级状态
      partialize: (state) => ({
        aiDisclaimerEnabled: state.aiDisclaimerEnabled,
      }),
    }
  )
);
