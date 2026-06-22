import {
  useState,
  useCallback,
  useEffect,
  useRef,
  type ReactNode,
} from 'react';
import { ToastContext, type ToastData, type ToastType } from './toastContext';
import { __setToastDispatcher } from '../utils/toast';

/* ── Unique ID generator ── */
let counter = 0;
function uid(): string {
  return `toast-${++counter}-${Date.now()}`;
}

/* ── Provider ── */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastData[]>([]);

  const toast = useCallback((data: Omit<ToastData, 'id'>) => {
    const id = uid();
    setToasts((prev) => [...prev, { ...data, id }]);
  }, []);

  /* Register global dispatcher for imperative toast.success/error calls */
  useEffect(() => {
    __setToastDispatcher(toast);
    return () => __setToastDispatcher(null as unknown as typeof toast);
  }, [toast]);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const clearAll = useCallback(() => {
    setToasts([]);
  }, []);

  return (
    <ToastContext.Provider value={{ toasts, toast, dismiss, clearAll }}>
      {children}
      <ToastContainer toasts={toasts} dismiss={dismiss} />
    </ToastContext.Provider>
  );
}

/* ── Toast Container (top-center positioned) ── */
function ToastContainer({
  toasts,
  dismiss,
}: {
  toasts: ToastData[];
  dismiss: (id: string) => void;
}) {
  if (toasts.length === 0) return null;

  return (
    <div className="toast-container" role="status" aria-live="polite">
      {toasts.map((t) => (
        <ToastItem key={t.id} data={t} onDismiss={() => dismiss(t.id)} />
      ))}
    </div>
  );
}

/* ── Individual Toast Item ── */
function ToastItem({
  data,
  onDismiss,
}: {
  data: ToastData;
  onDismiss: () => void;
}) {
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    const duration = data.duration ?? 5000;
    timerRef.current = setTimeout(onDismiss, duration);
    return () => clearTimeout(timerRef.current);
  }, [data.duration, onDismiss]);

  const colorMap: Record<ToastType, string> = {
    success: 'var(--success)',
    error: 'var(--error)',
    warning: 'var(--warning)',
    info: 'var(--info)',
  };

  return (
    <div className="toast" role="alert">
      <div
        className="toast-icon"
        style={{ background: colorMap[data.type] }}
      />
      <div className="toast-content">
        <div className="toast-title">{data.title}</div>
        {data.description && (
          <div className="toast-desc">{data.description}</div>
        )}
      </div>
      <button
        className="toast-close"
        onClick={() => {
          clearTimeout(timerRef.current);
          onDismiss();
        }}
        aria-label="关闭"
      >
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
          <path d="M3 3l8 8M11 3l-8 8" />
        </svg>
      </button>
    </div>
  );
}
