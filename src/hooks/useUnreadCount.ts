import { useState, useCallback, useRef, useEffect } from 'react';

export function useUnreadCount(isOpen: boolean) {
  const [count, setCount] = useState(0);
  const panelWasOpen = useRef(isOpen);

  useEffect(() => {
    if (isOpen) {
      setCount(0);
    }
    panelWasOpen.current = isOpen;
  }, [isOpen]);

  const increment = useCallback(() => {
    if (!panelWasOpen.current) {
      setCount(c => Math.min(c + 1, 100));
    }
  }, []);

  const display = count > 99 ? '99+' : count > 0 ? String(count) : null;

  return { count, increment, display, reset: () => setCount(0) };
}
