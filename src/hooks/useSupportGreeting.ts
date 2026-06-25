import { useState, useEffect } from 'react';

const SESSION_KEY = 'aureon_support_greeted';
const GREET_DELAY_MS = 10_000;

export function useSupportGreeting(isOpen: boolean) {
  const [showGreeting, setShowGreeting] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setShowGreeting(false);
      return;
    }
    const alreadyGreeted = sessionStorage.getItem(SESSION_KEY);
    if (alreadyGreeted) return;

    const timer = setTimeout(() => {
      setShowGreeting(true);
      sessionStorage.setItem(SESSION_KEY, '1');
    }, GREET_DELAY_MS);

    return () => clearTimeout(timer);
  }, [isOpen]);

  const dismissGreeting = () => setShowGreeting(false);

  return { showGreeting, dismissGreeting };
}
