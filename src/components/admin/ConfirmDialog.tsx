/**
 * 确认对话框组件
 * 用于危险操作的二次确认，支持焦点陷阱和 Escape 关闭
 */

import { useEffect, useRef, useCallback, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

/** 对话框变体 */
export type ConfirmVariant = 'danger' | 'warning' | 'info';

interface ConfirmDialogProps {
  /** 是否打开 */
  open: boolean;
  /** 标题 */
  title: string;
  /** 消息内容 */
  message: string | ReactNode;
  /** 确认按钮标签 */
  confirmLabel?: string;
  /** 取消按钮标签 */
  cancelLabel?: string;
  /** 变体 */
  variant?: ConfirmVariant;
  /** 确认回调 */
  onConfirm: () => void;
  /** 取消回调 */
  onCancel: () => void;
}

/** 变体样式映射 */
const VARIANT_STYLES: Record<ConfirmVariant, { confirm: string; icon: string }> = {
  danger: {
    confirm: 'bg-red-500 hover:bg-red-600 text-white',
    icon: '⚠',
  },
  warning: {
    confirm: 'bg-amber-500 hover:bg-amber-600 text-white',
    icon: '⚡',
  },
  info: {
    confirm: 'glow-btn text-white',
    icon: 'ℹ',
  },
};

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  cancelLabel,
  variant = 'danger',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const { t } = useTranslation();
  const dialogRef = useRef<HTMLDivElement>(null);
  const confirmBtnRef = useRef<HTMLButtonElement>(null);
  const styles = VARIANT_STYLES[variant];

  /** Escape 关闭 */
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onCancel();
      }
      // 焦点陷阱
      if (e.key === 'Tab' && dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    },
    [onCancel],
  );

  useEffect(() => {
    if (open) {
      document.addEventListener('keydown', handleKeyDown);
      // 自动聚焦确认按钮
      setTimeout(() => confirmBtnRef.current?.focus(), 50);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }
  }, [open, handleKeyDown]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* 遮罩 */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onCancel}
      />

      {/* 对话框 */}
      <div
        ref={dialogRef}
        role="alertdialog"
        aria-modal="true"
        className="relative w-full max-w-md mx-4 rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-6 shadow-2xl animate-fade-up"
      >
        {/* 图标 + 标题 */}
        <div className="flex items-start gap-3 mb-4">
          <span className="text-xl leading-none shrink-0">{styles.icon}</span>
          <div>
            <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
            <div className="mt-2 text-sm text-[var(--text-secondary)] leading-relaxed">
              {message}
            </div>
          </div>
        </div>

        {/* 操作按钮 */}
        <div className="flex items-center justify-end gap-2 mt-6">
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded-md text-sm font-medium text-[var(--text-secondary)] border border-[var(--border)] hover:bg-white/[0.03] hover:text-[var(--text-primary)] transition-colors"
          >
            {cancelLabel ?? t('admin.confirm.cancel', '取消')}
          </button>
          <button
            ref={confirmBtnRef}
            onClick={onConfirm}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${styles.confirm}`}
          >
            {confirmLabel ?? t('admin.confirm.ok', '确认')}
          </button>
        </div>
      </div>
    </div>
  );
}
