/**
 * Toast compatibility shim — bridges imperative toast.success/error/info calls
 * to the React-context-based ToastProvider.
 *
 * Drop-in replacement for `import { toast } from 'sonner'`.
 */
import type { ToastData, ToastType } from '../hooks/toastContext';

type ToastFn = (data: Omit<ToastData, 'id'>) => void;

/* Internal ref — set by ToastProvider on mount */
let _dispatch: ToastFn | null = null;

export function __setToastDispatcher(fn: ToastFn) {
  _dispatch = fn;
}

function fire(type: ToastType, message: string) {
  if (_dispatch) {
    _dispatch({ type, title: message });
  } else {
    // Fallback: log to console if provider isn't mounted
    console.warn('[toast]', type, message);
  }
}

/** Imperative toast API — matches sonner's toast.success / toast.error pattern */
export const toast = {
  success: (msg: string) => fire('success', msg),
  error: (msg: string) => fire('error', msg),
  warning: (msg: string) => fire('warning', msg),
  info: (msg: string) => fire('info', msg),
};
