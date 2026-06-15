import { useRef, useCallback, useEffect } from "react";

const DEFAULT_FLUSH_INTERVAL = 60;

/**
 * Reusable SSE text-stream buffer hook.
 *
 * Accumulates text chunks and flushes them in batches to reduce
 * React re-render frequency during streaming responses.
 *
 * @param onFlush - Callback invoked with accumulated text on each flush
 * @param interval - Flush debounce interval in ms (default: 60)
 */
export function useSSEBuffer(
  onFlush: (text: string) => void,
  interval: number = DEFAULT_FLUSH_INTERVAL,
) {
  const bufferRef = useRef("");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onFlushRef = useRef(onFlush);
  onFlushRef.current = onFlush;

  const flushNow = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    const text = bufferRef.current;
    if (!text) return;
    bufferRef.current = "";
    onFlushRef.current(text);
  }, []);

  const scheduleFlush = useCallback(() => {
    if (timerRef.current) return;
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      const text = bufferRef.current;
      if (!text) return;
      bufferRef.current = "";
      onFlushRef.current(text);
    }, interval);
  }, [interval]);

  const append = useCallback(
    (chunk: string) => {
      bufferRef.current += chunk;
      scheduleFlush();
    },
    [scheduleFlush],
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

  return { append, flushNow, scheduleFlush };
}
