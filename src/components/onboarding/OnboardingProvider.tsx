/**
 * OnboardingProvider — 引导状态 Context Provider
 * 管理当前步骤、跨页面导航、完成/跳过标记
 */

import {
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { toast } from '../../utils/toast';
import { useTranslation } from 'react-i18next';
import { useViewStore } from '../../stores/useViewStore';
import { CoachMark } from './CoachMark';
import { ONBOARDING_STEPS } from './steps';
import { OnboardingContext } from './useOnboarding';

interface OnboardingProviderProps {
  children: ReactNode;
}

export function OnboardingProvider({ children }: OnboardingProviderProps) {
  const { t } = useTranslation();
  const [currentStep, setCurrentStep] = useState(-1);
  const [isActive, setIsActive] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  const onboardingCompleted = useViewStore((s) => s.onboardingCompleted);
  const completeOnboarding = useViewStore((s) => s.completeOnboarding);
  const resetOnboarding = useViewStore((s) => s.resetOnboarding);

  // 自动触发：首次访问 Dashboard
  useEffect(() => {
    if (!onboardingCompleted && location.pathname === '/dashboard' && !isActive) {
      // 延迟启动，等待页面渲染完成
      const timer = setTimeout(() => {
        setIsActive(true);
        setCurrentStep(0);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  // 跨页面导航
  useEffect(() => {
    if (!isActive || currentStep < 0) return;
    const step = ONBOARDING_STEPS[currentStep];
    if (!step) return;

    // 被重定向到登录页（受保护路由）→ 跳过当前步骤
    if (location.pathname === '/login') {
      setCurrentStep((prev) => prev + 1);
      return;
    }

    // 如果当前步骤在另一个页面，自动导航
    if (step.page !== location.pathname) {
      navigate(step.page);
    }
  }, [isActive, currentStep, location.pathname, navigate]);

  const handleNext = useCallback(() => {
    setCurrentStep((prev) => prev + 1);
  }, []);

  const handlePrev = useCallback(() => {
    setCurrentStep((prev) => Math.max(0, prev - 1));
  }, []);

  const finishGuide = useCallback(() => {
    setIsActive(false);
    setCurrentStep(-1);
    completeOnboarding();
    // 双重保险：直接写 localStorage（防止 zustand persist 异步时序问题）
    try {
      const key = Object.keys(localStorage).find((k) => k.startsWith('aureon:viewstate:'));
      if (key) {
        const data = JSON.parse(localStorage.getItem(key) || '{}');
        data.state = { ...data.state, onboardingCompleted: true };
        localStorage.setItem(key, JSON.stringify(data));
      }
    } catch { /* silent */ }
  }, [completeOnboarding]);

  const handleSkip = useCallback(() => {
    finishGuide();
    toast.info(t('onboarding.toast_skip'));
  }, [finishGuide, t]);

  const handleFinish = useCallback(() => {
    finishGuide();
    toast.success(t('onboarding.toast_finish'));
  }, [finishGuide, t]);

  // 当 currentStep 越界（被跳过或自然走完）→ 自动完成引导
  useEffect(() => {
    if (isActive && currentStep >= ONBOARDING_STEPS.length) {
      handleFinish();
    }
  }, [isActive, currentStep, handleFinish]);

  const start = useCallback(() => {
    resetOnboarding();
    setIsActive(true);
    setCurrentStep(0);
  }, [resetOnboarding]);

  const reset = useCallback(() => {
    resetOnboarding();
    setIsActive(true);
    setCurrentStep(0);
  }, [resetOnboarding]);

  const currentStepData =
    isActive && currentStep >= 0 && currentStep < ONBOARDING_STEPS.length
      ? ONBOARDING_STEPS[currentStep]
      : null;

  return (
    <OnboardingContext.Provider value={{ isActive, currentStep, start, reset }}>
      {children}
      {currentStepData && location.pathname === currentStepData.page && (
        <CoachMark
          step={currentStepData}
          current={currentStep}
          total={ONBOARDING_STEPS.length}
          onNext={handleNext}
          onPrev={handlePrev}
          onSkip={handleSkip}
          onFinish={handleFinish}
        />
      )}
    </OnboardingContext.Provider>
  );
}
