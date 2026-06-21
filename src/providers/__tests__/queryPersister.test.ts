import { describe, it, expect, beforeEach } from 'vitest';
import { createSafeStoragePersister } from '../queryPersister';

describe('createSafeStoragePersister', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it('creates a persister with required methods', () => {
    const persister = createSafeStoragePersister();
    expect(typeof persister.persistClient).toBe('function');
    expect(typeof persister.restoreClient).toBe('function');
    expect(typeof persister.removeClient).toBe('function');
  });

  it('persists and restores a serialized client', async () => {
    const persister = createSafeStoragePersister();
    const payload = {
      clientState: { queries: [], mutations: [] },
      timestamp: Date.now(),
      buster: 'v1',
    };
    await persister.persistClient(payload);
    await new Promise(r => setTimeout(r, 50));
    const restored = await persister.restoreClient();
    expect(restored).toEqual(payload);
  });

  it('removes persisted client', async () => {
    const persister = createSafeStoragePersister();
    await persister.persistClient({
      clientState: { queries: [], mutations: [] },
      timestamp: Date.now(),
      buster: 'v1',
    });
    await new Promise(r => setTimeout(r, 50));
    await persister.removeClient();
    const restored = await persister.restoreClient();
    expect(restored).toBeUndefined();
  });

  it('uses the configured storage key', async () => {
    const persister = createSafeStoragePersister({ key: 'aureon:custom-cache' });
    await persister.persistClient({
      clientState: { queries: [], mutations: [] },
      timestamp: Date.now(),
      buster: 'v1',
    });
    await new Promise(r => setTimeout(r, 50));
    expect(localStorage.getItem('aureon:custom-cache')).not.toBeNull();
  });

  it('returns undefined when storage is empty', async () => {
    const persister = createSafeStoragePersister();
    const restored = await persister.restoreClient();
    expect(restored).toBeUndefined();
  });
});
