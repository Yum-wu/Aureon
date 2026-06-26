/**
 * Tooltip — Floating UI Portal 版本
 * 渲染到 document.body，脱离父容器 overflow:hidden
 * 内置碰撞检测 + 方位翻转 + 热区桥接
 */

import { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import {
  useFloating,
  useInteractions,
  useHover,
  useFocus,
  useDismiss,
  offset,
  flip,
  shift,
  size,
  arrow,
  FloatingArrow,
  autoUpdate,
} from '@floating-ui/react';
import type { Placement } from '@floating-ui/react';

interface TooltipProps {
  content: string;
  children: React.ReactNode;
  placement?: Placement;
}

export function Tooltip({ content, children, placement = 'top' }: TooltipProps) {
  const [open, setOpen] = useState(false);
  const [positioned, setPositioned] = useState(false);
  const arrowRef = useRef<SVGSVGElement>(null);

  const { refs, context, floatingStyles } = useFloating({
    open,
    onOpenChange: setOpen,
    placement,
    middleware: [
      offset(8),
      flip({
        fallbackPlacements: ['bottom', 'right', 'left'],
        padding: 8,
      }),
      shift({
        padding: 8,
      }),
      size({
        apply({ availableWidth, elements }) {
          const maxWidth = Math.min(availableWidth - 16, window.innerWidth * 0.8);
          elements.floating.style.maxWidth = `${maxWidth}px`;
        },
      }),
      // eslint-disable-next-line react-hooks/refs -- Floating UI callback ref pattern
      arrow({ element: arrowRef }),
    ],
    whileElementsMounted: autoUpdate,
  });

  const hover = useHover(context, {
    delay: { open: 200, close: 150 },
    move: false,
  });
  const focus = useFocus(context);
  const dismiss = useDismiss(context);

  const { getReferenceProps, getFloatingProps } = useInteractions([
    hover,
    focus,
    dismiss,
  ]);

  // Wait for Floating UI to compute position before showing
  useEffect(() => {
    if (open) {
      const raf = requestAnimationFrame(() => setPositioned(true));
      return () => cancelAnimationFrame(raf);
    } else {
      setPositioned(false);
    }
  }, [open]);

  // ESC 键关闭
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open]);

  return (
    <>
      <span
        ref={refs.setReference}
        className="inline-flex items-center"
        {...getReferenceProps()}
      >
        {children}
      </span>
      {open &&
        createPortal(
          <div
            ref={refs.setFloating} // eslint-disable-line react-hooks/refs -- Floating UI callback ref
            role="tooltip"
            className="z-[9999] px-3 py-2 text-sm font-medium rounded-lg leading-snug"
            style={{
              ...floatingStyles,
              background: 'var(--bg-tertiary)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border)',
              boxShadow: 'var(--shadow-lg)',
              width: 'max-content',
              opacity: positioned ? 1 : 0,
              pointerEvents: positioned ? 'auto' : 'none',
              transition: 'opacity 100ms ease-out',
            }}
            {...getFloatingProps()}
          >
            {content}
            <FloatingArrow
              ref={arrowRef}
              context={context}
              fill="var(--border)"
              stroke="var(--border)"
              strokeWidth={1}
              width={10}
              height={5}
            />
          </div>,
          document.body
        )}
    </>
  );
}
