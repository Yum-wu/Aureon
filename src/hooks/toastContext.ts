import { createContext, useContext } from 'react';

/* ── Types ── */
export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface ToastData {
  id: string;
  type: ToastType;
  title: string;
  description?: string;
  duration?: number;
}

export interface ToastContextValue {
  toasts: ToastData[];
  toast: (t: Omit<ToastData, 'id'>) => void;
  dismiss: (id: string) => void;
  clearAll: () => void;
}

/* ── Context ── */
export const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
}
