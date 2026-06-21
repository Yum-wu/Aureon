import { describe, it, expect } from 'vitest';
import { migrateViewState } from '../useViewStore';

describe('migrateViewState', () => {
  it('returns defaults for null input', () => {
    const result = migrateViewState(null, 0);
    expect(result.dashboardTimeRange).toBe('24h');
    expect(result.onboardingCompleted).toBe(false);
  });

  it('returns defaults for non-object input', () => {
    const result = migrateViewState('garbage', 0);
    expect(result.dashboardTimeRange).toBe('24h');
  });

  it('migrates v0 timeRange to dashboardTimeRange', () => {
    const result = migrateViewState({ timeRange: '7d' }, 0);
    expect(result.dashboardTimeRange).toBe('7d');
  });

  it('preserves known fields from v1', () => {
    const result = migrateViewState(
      { dashboardTimeRange: '6h', onboardingCompleted: true },
      1,
    );
    expect(result.dashboardTimeRange).toBe('6h');
    expect(result.onboardingCompleted).toBe(true);
  });

  it('ignores unknown fields', () => {
    const result = migrateViewState(
      { dashboardTimeRange: '1h', unknownField: 'x' },
      1,
    );
    expect(result.dashboardTimeRange).toBe('1h');
    expect((result as Record<string, unknown>).unknownField).toBeUndefined();
  });

  it('downgrades future version to defaults', () => {
    const result = migrateViewState(
      { futureField: 'value', dashboardTimeRange: '1h' },
      99,
    );
    expect(result.dashboardTimeRange).toBe('24h');
  });

  it('includes all expected fields', () => {
    const result = migrateViewState({}, 0);
    expect(result).toHaveProperty('dashboardTimeRange');
    expect(result).toHaveProperty('analyticsTimeRange');
    expect(result).toHaveProperty('costTimeRange');
    expect(result).toHaveProperty('onboardingCompleted');
  });
});
