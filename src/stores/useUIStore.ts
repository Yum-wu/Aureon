/** UI 状态 Store */

import { create } from "zustand";
import type { UIState } from "./types";

const AI_DISCLAIMER_KEY = "aureon_ai_disclaimer";

export const useUIStore = create<UIState>((set) => ({
  mobileMenuOpen: false,
  aiDisclaimerEnabled: localStorage.getItem(AI_DISCLAIMER_KEY) !== "false",

  setMobileMenuOpen: (open: boolean) => {
    set({ mobileMenuOpen: open });
  },

  toggleAiDisclaimer: () => {
    set((state) => {
      const newValue = !state.aiDisclaimerEnabled;
      localStorage.setItem(AI_DISCLAIMER_KEY, String(newValue));
      return { aiDisclaimerEnabled: newValue };
    });
  },
}));
