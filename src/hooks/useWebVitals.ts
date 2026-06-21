/**
 * useWebVitals — register Web Vitals collection at app root
 */

import { useEffect } from 'react';
import { onLCP, onFCP, onINP, onCLS } from 'web-vitals';
import { reportWebVitals } from '../lib/performance';

export function useWebVitals(): void {
  useEffect(() => {
    const cleanups: Array<() => void> = [];

    try {
      const lcp = onLCP(reportWebVitals);
      const fcp = onFCP(reportWebVitals);
      const inp = onINP(reportWebVitals);
      const cls = onCLS(reportWebVitals);

      if (typeof lcp === 'function') cleanups.push(lcp);
      if (typeof fcp === 'function') cleanups.push(fcp);
      if (typeof inp === 'function') cleanups.push(inp);
      if (typeof cls === 'function') cleanups.push(cls);
    } catch {
      // PerformanceObserver not available
    }

    return () => {
      cleanups.forEach((fn) => { try { fn(); } catch { /* ignore */ } });
    };
  }, []);
}
