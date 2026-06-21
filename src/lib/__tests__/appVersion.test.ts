import { describe, it, expect } from 'vitest';
import { getAppVersion, getCacheBuster } from '../appVersion';

describe('appVersion', () => {
  it('returns a non-empty version string', () => {
    const v = getAppVersion();
    expect(typeof v).toBe('string');
    expect(v.length).toBeGreaterThan(0);
  });

  it('cache buster is derived from version', () => {
    const v = getAppVersion();
    const b = getCacheBuster();
    expect(b).toContain(v);
  });

  it('cache buster is deterministic', () => {
    expect(getCacheBuster()).toBe(getCacheBuster());
  });
});
