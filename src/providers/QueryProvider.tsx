import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import { QueryClient, type QueryClientConfig } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { createSafeStoragePersister } from './queryPersister';

const APP_VERSION = '1.0.0';
const PERSIST_MAX_AGE_MS = 1000 * 60 * 60 * 24 * 7;

const defaultQueryOptions: QueryClientConfig['defaultOptions'] = {
  queries: {
    staleTime: 30_000,
    gcTime: 1000 * 60 * 60 * 24,
    retry: 2,
    refetchOnWindowFocus: false,
  },
};

function makeQueryClient() {
  return new QueryClient({ defaultOptions: defaultQueryOptions });
}

let browserQueryClient: QueryClient | undefined;

function getQueryClient() {
  if (typeof window === 'undefined') return makeQueryClient();
  if (!browserQueryClient) browserQueryClient = makeQueryClient();
  return browserQueryClient;
}

export function QueryProvider({ children }: { children: ReactNode }) {
  const [queryClient] = useState(getQueryClient);
  const [persister] = useState(() => createSafeStoragePersister());

  return (
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{
        persister,
        buster: APP_VERSION,
        maxAge: PERSIST_MAX_AGE_MS,
      }}
    >
      {children}
    </PersistQueryClientProvider>
  );
}
