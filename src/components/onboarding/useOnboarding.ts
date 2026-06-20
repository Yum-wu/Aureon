/**
 * useOnboarding hook — 引导状态消费
 */

import { createContext, useContext } from 'react';

export interface OnboardingContextValue {
  /** 是否正在进行引导 */
  isActive: boolean;
  /** 当前步骤索引 */
  currentStep: number;
  /** 启动引导 */
  start: () => void;
  /** 重置引导（用于手动召回） */
  reset: () => void;
}

export const OnboardingContext = createContext<OnboardingContextValue | null>(null);

export function useOnboarding(): OnboardingContextValue {
  const ctx = useContext(OnboardingContext);
  if (!ctx) {
    return { isActive: false, currentStep: -1, start: () => {}, reset: () => {} };
  }
  return ctx;
}
