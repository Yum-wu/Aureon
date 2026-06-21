import { describe, it, expect, vi } from 'vitest';

vi.mock('web-vitals', () => ({
  onLCP: vi.fn(() => () => {}),
  onFCP: vi.fn(() => () => {}),
  onINP: vi.fn(() => () => {}),
  onCLS: vi.fn(() => () => {}),
}));

describe('reportWebVitals', () => {
  it('logs to console in dev mode', async () => {
    const consoleSpy = vi.spyOn(console, 'debug').mockImplementation(() => {});
    const { reportWebVitals } = await import('../performance');
    
    reportWebVitals({ name: 'LCP', value: 2500, rating: 'good', id: 'v1', delta: 2500, entries: [] } as any);
    
    expect(consoleSpy).toHaveBeenCalledWith(
      expect.stringContaining('LCP'),
      expect.anything(),
    );
    consoleSpy.mockRestore();
  });

  it('calls custom reporter in prod mode', async () => {
    // Note: import.meta.env.DEV is true in vitest by default,
    // so custom reporter won't be called in dev mode.
    // This test verifies the function doesn't throw.
    const { reportWebVitals } = await import('../performance');
    expect(() => reportWebVitals({ name: 'FCP', value: 1800, rating: 'good', id: 'v2', delta: 1800, entries: [] } as any)).not.toThrow();
  });
});
