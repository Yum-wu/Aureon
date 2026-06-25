/**
 * CoachMark — 聚光灯引导组件
 * 遮罩 + 高亮目标元素 + 浮动说明卡
 * 使用 Floating UI 定位说明卡
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import {
  useFloating,
  offset,
  flip,
  shift,
  autoUpdate,
} from '@floating-ui/react';
import { useTranslation } from 'react-i18next';
import type { OnboardingStep } from './steps';

interface CoachMarkProps {
  step: OnboardingStep;
  current: number;
  total: number;
  onNext: () => void;
  onPrev: () => void;
  onSkip: () => void;
  onFinish: () => void;
}

export function CoachMark({
  step,
  current,
  total,
  onNext,
  onPrev,
  onSkip,
  onFinish,
}: CoachMarkProps) {
  const { t } = useTranslation();
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);

  const isLast = current === total - 1;
  const isFirst = current === 0;

  // 定位说明卡
  const { refs, floatingStyles } = useFloating({
    placement: 'top',
    middleware: [
      offset(12),
      flip({ fallbackPlacements: ['bottom', 'right', 'left'], padding: 8 }),
      shift({ padding: 8 }),
    ],
    whileElementsMounted: autoUpdate,
  });

  // 监听目标元素位置
  useEffect(() => {
    // 等待 DOM 渲染（目标元素可能延迟出现）
    const timer = setTimeout(() => {
      const found = document.querySelector(step.anchor);
      if (found) {
        found.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // 再等滚动完成后计算位置
        setTimeout(() => {
          const rect = found.getBoundingClientRect();
          setTargetRect(rect);
          refs.setReference({
            getBoundingClientRect: () => rect,
            contextElement: found as Element,
          });
        }, 300);
      } else {
        // 目标元素不存在（如后端不可用时的错误状态）→ 居中显示卡片
        const fallback = {
          top: window.innerHeight * 0.3,
          left: window.innerWidth * 0.5,
          width: 0,
          height: 0,
          right: window.innerWidth * 0.5,
          bottom: window.innerHeight * 0.3,
          x: window.innerWidth * 0.5,
          y: window.innerHeight * 0.3,
          toJSON: () => {},
        } as DOMRect;
        setTargetRect(fallback);
        refs.setReference({
          getBoundingClientRect: () => fallback,
          contextElement: document.body,
        });
      }
    }, 200);

    return () => clearTimeout(timer);
  }, [step.anchor, refs]);

  // ESC 键关闭 + 箭头键导航
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onSkip();
      } else if (e.key === 'ArrowRight' && !isLast) {
        onNext();
      } else if (e.key === 'ArrowLeft' && !isFirst) {
        onPrev();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onSkip, onNext, onPrev, isLast, isFirst]);

  const handleNext = useCallback(() => {
    if (isLast) {
      onFinish();
    } else {
      onNext();
    }
  }, [isLast, onFinish, onNext]);

  if (!targetRect) return null;

  const spotlightPadding = 4;
  const hasSpotlight = targetRect.width > 0;

  return createPortal(
    <div className="fixed inset-0 z-[9998]" style={{ pointerEvents: 'none' }}>
      {/* 遮罩层 */}
      <div
        className="absolute inset-0"
        style={{
          background: 'rgba(0,0,0,0.72)',
          clipPath: hasSpotlight ? `polygon(
            0% 0%, 100% 0%, 100% 100%, 0% 100%,
            0% ${targetRect.top - spotlightPadding}px,
            ${targetRect.left - spotlightPadding}px ${targetRect.top - spotlightPadding}px,
            ${targetRect.left - spotlightPadding}px ${targetRect.bottom + spotlightPadding}px,
            ${targetRect.right + spotlightPadding}px ${targetRect.bottom + spotlightPadding}px,
            ${targetRect.right + spotlightPadding}px ${targetRect.top - spotlightPadding}px,
            0% ${targetRect.top - spotlightPadding}px
          )` : undefined,
        }}
      />

      {/* 聚光灯高亮边框（仅目标元素存在时显示） */}
      {hasSpotlight && (
        <div
          className="absolute border-2 rounded-lg pointer-events-none"
          style={{
            top: targetRect.top - spotlightPadding,
            left: targetRect.left - spotlightPadding,
            width: targetRect.width + spotlightPadding * 2,
          height: targetRect.height + spotlightPadding * 2,
          borderColor: 'var(--accent-500)',
          boxShadow: '0 0 0 4px rgba(94,106,210,0.2)',
        }}
      />
      )}

      {/* 说明卡 */}
      <div
        ref={(node) => {
          cardRef.current = node;
          refs.setFloating(node);
        }}
        className="z-[9999] rounded-xl p-5 max-w-xs"
        style={{
          ...floatingStyles,
          pointerEvents: 'auto',
          background: 'var(--bg-secondary)',
          border: '1px solid var(--border)',
          boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
        }}
      >
        {/* 步骤标签 */}
        <div
          className="text-[10px] font-bold uppercase tracking-widest mb-2"
          style={{ color: 'var(--accent)' }}
        >
          {t('onboarding.step_label', {
            current: current + 1,
            total,
            title: t(step.titleKey),
          })}
        </div>

        {/* 描述 */}
        <p className="text-sm leading-relaxed mb-4" style={{ color: 'var(--text-primary)' }}>
          {t(step.descriptionKey)}
        </p>

        {/* 导航栏 */}
        <div className="flex items-center justify-between">
          {/* 跳过 */}
          <button
            onClick={onSkip}
            className="text-xs font-medium transition-colors hover:opacity-80"
            style={{ color: 'var(--text-tertiary)' }}
          >
            {t('onboarding.skip')}
          </button>

          {/* 进度点 */}
          <div className="flex gap-1.5">
            {Array.from({ length: total }).map((_, i) => (
              <div
                key={i}
                className="w-1.5 h-1.5 rounded-full transition-colors"
                style={{
                  background: i === current ? 'var(--accent)' : 'var(--bg-tertiary)',
                }}
              />
            ))}
          </div>

          {/* 下一步/完成 */}
          <button
            onClick={handleNext}
            className="text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors hover:opacity-90"
            style={{
              background: 'var(--accent)',
              color: '#fff',
            }}
          >
            {isLast ? t('onboarding.finish') : t('onboarding.next')}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
