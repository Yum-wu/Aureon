/**
 * Auth-aware fetch wrapper.
 *
 * Automatically injects X-API-Key header when the user is logged in
 * (key stored in sessionStorage by AuthProvider).
 *
 * Usage: `import { authFetch } from '../services/authFetch';`
 * Then replace all `fetch(...)` calls with `authFetch(...)`.
 */

const API_KEY_STORAGE = "aureon_api_key";

function getApiKey(): string {
  try {
    return sessionStorage.getItem(API_KEY_STORAGE) || "";
  } catch {
    return "";
  }
}

/**
 * Drop-in replacement for `fetch` that adds X-API-Key header.
 * Merges with any existing headers the caller provides.
 */
export function authFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const apiKey = getApiKey();

  if (apiKey) {
    const headers = new Headers(init?.headers);
    headers.set("X-API-Key", apiKey);
    return fetch(input, { ...init, headers });
  }

  return fetch(input, init);
}
