/**
 * performance.ts — Web Vitals collection and reporting
 */

import type { Metric } from 'web-vitals';

type WebVitalsReporter = (metric: Metric) => void;

let customReporter: WebVitalsReporter | null = null;

export function setWebVitalsReporter(reporter: WebVitalsReporter): void {
  customReporter = reporter;
}

function isDev(): boolean {
  try {
    return Boolean((import.meta as { env?: { DEV?: boolean } }).env?.DEV);
  } catch {
    return true;
  }
}

export function reportWebVitals(metric: Metric): void {
  if (isDev()) {
    console.debug(
      `[WebVitals] ${metric.name}: ${metric.value.toFixed(2)} (${metric.rating})`,
      metric,
    );
  }
  if (!isDev() && customReporter) {
    try {
      customReporter(metric);
    } catch {
      // silently ignore
    }
  }
}
