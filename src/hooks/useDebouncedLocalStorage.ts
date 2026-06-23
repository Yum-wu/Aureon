import { useState, useEffect } from 'react';

export function useDebouncedLocalStorage<T>(key: string, initialValue: T, delay = 500) {
  const [value, setValue] = useState<T>(() => {
    try {
      const stored = localStorage.getItem(key);
      return stored ? JSON.parse(stored) : initialValue;
    } catch {
      return initialValue;
    }
  });

  useEffect(() => {
    const timer = setTimeout(() => {
      try {
        localStorage.setItem(key, JSON.stringify(value));
      } catch {
        // localStorage unavailable
      }
    }, delay);
    return () => clearTimeout(timer);
  }, [key, value, delay]);

  return [value, setValue] as const;
}
