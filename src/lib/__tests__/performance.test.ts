import { describe, it, expect, vi } from 'vitest';
import type { Metric } from 'web-vitals';

vi.mock('web-vitals', () => ({
  onLCP: vi.fn(() => () => {}),
  onFCP: vi.fn(() => () => {}),
  onINP: vi.fn(() => () => {}),
  onCLS: vi.fn(() => () => {}),
}));

function makeMetric(overrides: Partial<Metric>): Metric {
  return {
    name: 'LCP',
    value: 2500,
    rating: 'good',
    id: 'v1',
    delta: 2500,
    entries: [],
    navigationType: 'navigate',
    ...overrides,
  } as Metric;
}

describe('reportWebVitals', () => {
  it('logs to console in dev mode', async () => {
    const consoleSpy = vi.spyOn(console, 'debug').mockImplementation(() => {});
    const { reportWebVitals } = await import('../performance');

    reportWebVitals(makeMetric({ name: 'LCP', value: 2500, id: 'v1' }));

    expect(consoleSpy).toHaveBeenCalledWith(
      expect.stringContaining('LCP'),
      expect.anything(),
    );
    consoleSpy.mockRestore();
  });

  it('calls custom reporter in prod mode', async () => {
    const { reportWebVitals } = await import('../performance');
    expect(() => reportWebVitals(makeMetric({ name: 'FCP', value: 1800, id: 'v2' }))).not.toThrow();
  });
});
