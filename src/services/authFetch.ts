/**
 * Auth-aware fetch wrapper.
 *
 * Automatically injects auth headers when the user is logged in.
 * Supports two auth modes:
 * 1. JWT Bearer token (Authorization: Bearer <jwt>) — SSO login
 * 2. API Key (X-API-Key header) — legacy mode
 *
 * JWT token takes priority over API key when both are present.
 */

const API_KEY_STORAGE = "aureon_api_key";
const JWT_TOKEN_STORAGE = "aureon_jwt_token";

function getApiKey(): string {
  try {
    return sessionStorage.getItem(API_KEY_STORAGE) || "";
  } catch {
    return "";
  }
}

function getJwtToken(): string {
  try {
    return sessionStorage.getItem(JWT_TOKEN_STORAGE) || "";
  } catch {
    return "";
  }
}

/**
 * Drop-in replacement for `fetch` that adds auth headers.
 * JWT Bearer token takes priority; falls back to X-API-Key.
 */
export function authFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const jwt = getJwtToken();
  const apiKey = getApiKey();

  if (jwt || apiKey) {
    const headers = new Headers(init?.headers);
    if (jwt) {
      headers.set("Authorization", `Bearer ${jwt}`);
    }
    if (apiKey) {
      headers.set("X-API-Key", apiKey);
    }
    return fetch(input, { ...init, headers });
  }

  return fetch(input, init);
}
