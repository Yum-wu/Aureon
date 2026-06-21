import { createSyncStoragePersister } from '@tanstack/query-sync-storage-persister';
import type { Persister } from '@tanstack/react-query-persist-client';
import { safeStorage } from '../stores/safeStorage';

export const DEFAULT_CACHE_KEY = 'aureon:query-cache';

export interface CreatePersisterOptions {
  key?: string;
}

export function createSafeStoragePersister(
  options: CreatePersisterOptions = {},
): Persister {
  const key = options.key ?? DEFAULT_CACHE_KEY;
  return createSyncStoragePersister({
    storage: safeStorage,
    key,
    throttleTime: 0,
  });
}
