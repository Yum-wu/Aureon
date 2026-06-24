/**
 * OnboardingProvider — 引导状态 Context Provider
 * 管理当前步骤、跨页面导航、完成/跳过标记
 *
 * 支持角色感知：根据用户角色过滤引导步骤
 * 支持自动预填：搜索步骤可自动填入查询文本
 *
 * 理想用户流程：
 * 1. 搜索体验 → 展示核心价值
 * 2. 上传文档 → 让知识库个人化
 * 3. 搜索自己的数据 → Aha moment
 * 4. 仪表盘 → 系统状态（管理员）
 * 5. 分析 → 使用洞察（管理员）
 */

import {
  useState,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  type ReactNode,
} from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { toast } from '../../utils/toast';
import { useTranslation } from 'react-i18next';
import { useViewStore } from '../../stores/useViewStore';
import { useAuth } from '../../hooks/AuthContext';
import { CoachMark } from './CoachMark';
import { ONBOARDING_STEPS } from './steps';
import { OnboardingContext } from './useOnboarding';

interface OnboardingProviderProps {
  children: ReactNode;
}

export function OnboardingProvider({ children }: OnboardingProviderProps) {
  const { t } = useTranslation();
  const { role } = useAuth();
  const [currentStep, setCurrentStep] = useState(-1);
  const [isActive, setIsActive] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  const onboardingCompleted = useViewStore((s) => s.onboardingCompleted);
  const completeOnboarding = useViewStore((s) => s.completeOnboarding);
  const resetOnboarding = useViewStore((s) => s.resetOnboarding);
  const triggeredRef = useRef(false);

  // 根据用户角色过滤步骤
  const filteredSteps = useMemo(() => {
    const userRole = (role || 'VIEWER').toUpperCase();
    return ONBOARDING_STEPS.filter((step) => {
      // 如果没有指定角色限制，所有角色都可见
      if (!step.roles || step.roles.length === 0) return true;
      // 检查用户角色是否在允许列表中
      return step.roles.includes(userRole);
    });
  }, [role]);

  // 自动触发：首次访问 Dashboard 或 Search（仅触发一次）
  useEffect(() => {
    if (triggeredRef.current) return;
    if (onboardingCompleted) return;
    if (isActive) return;
    if (location.pathname !== '/dashboard' && location.pathname !== '/search') return;

    triggeredRef.current = true;
    setIsActive(true);
    setCurrentStep(0);
    if (filteredSteps[0]?.page === '/search' && location.pathname !== '/search') {
      navigate('/search');
    }
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  // 处理自动预填查询
  useEffect(() => {
    if (!isActive || currentStep < 0) return;
    const step = filteredSteps[currentStep];
    if (!step) return;

    // 如果当前步骤有自动预填查询，填入搜索框
    if (step.autoFillQuery && step.page === '/search' && location.pathname === '/search') {
      const timer = setTimeout(() => {
        const searchInput = document.querySelector('input[placeholder*="搜索"]') as HTMLInputElement;
        if (searchInput && !searchInput.value) {
          // 使用 React 的 onChange 事件触发
          const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value'
          )?.set;
          if (nativeInputValueSetter) {
            nativeInputValueSetter.call(searchInput, step.autoFillQuery);
            searchInput.dispatchEvent(new Event('input', { bubbles: true }));
            searchInput.dispatchEvent(new Event('change', { bubbles: true }));
          }
        }
      }, 300);
      return () => clearTimeout(timer);
    }
  }, [isActive, currentStep, location.pathname, filteredSteps]);

  // 被动处理：用户被重定向到登录页 → 跳过当前步骤
  useEffect(() => {
    if (!isActive || currentStep < 0) return;
    if (location.pathname === '/login') {
      setCurrentStep((prev) => prev + 1);
    }
  }, [isActive, currentStep, location.pathname]);

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
    if (isActive && currentStep >= filteredSteps.length) {
      handleFinish();
    }
  }, [isActive, currentStep, handleFinish, filteredSteps.length]);

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
    isActive && currentStep >= 0 && currentStep < filteredSteps.length
      ? filteredSteps[currentStep]
      : null;

  return (
    <OnboardingContext.Provider value={{ isActive, currentStep, start, reset }}>
      {children}
      {currentStepData && location.pathname === currentStepData.page && (
        <CoachMark
          step={currentStepData}
          current={currentStep}
          total={filteredSteps.length}
          onNext={handleNext}
          onPrev={handlePrev}
          onSkip={handleSkip}
          onFinish={handleFinish}
        />
      )}
    </OnboardingContext.Provider>
  );
}
