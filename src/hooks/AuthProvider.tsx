// Auth context for route guards.
// Supports two auth modes:
// 1. API Key (X-API-Key header) — legacy mode
// 2. JWT Bearer token — SSO login mode
// When API_AUTH_KEY is empty (dev mode), all routes are accessible.

import { useState, useCallback, type ReactNode } from "react";
import { AuthContext } from "./AuthContext";

const API_KEY_STORAGE = "aureon_api_key";
const JWT_TOKEN_STORAGE = "aureon_jwt_token";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [apiKey, setApiKey] = useState(() => sessionStorage.getItem(API_KEY_STORAGE) || "");
  const [token, setToken] = useState(() => sessionStorage.getItem(JWT_TOKEN_STORAGE) || "");

  const login = useCallback(async (key: string): Promise<boolean> => {
    // Verify key against backend endpoint that requires auth
    // /api/rag/stats requires X-API-Key when API_AUTH_KEY is configured
    try {
      const res = await fetch("/api/rag/stats", {
        headers: { "X-API-Key": key },
      });
      if (res.ok) {
        setApiKey(key);
        sessionStorage.setItem(API_KEY_STORAGE, key);
        return true;
      }
      // 401/403 = invalid key
      return false;
    } catch {
      // Network error - don't allow login
      return false;
    }
  }, []);

  const loginWithJWT = useCallback(async (email: string, password: string): Promise<boolean> => {
    try {
      const res = await fetch("/api/security/sso/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      if (res.ok) {
        const data = await res.json();
        const jwt = data.access_token;
        if (jwt) {
          setToken(jwt);
          sessionStorage.setItem(JWT_TOKEN_STORAGE, jwt);
          return true;
        }
      }
      return false;
    } catch {
      // Network error
      return false;
    }
  }, []);

  const logout = useCallback(() => {
    setApiKey("");
    setToken("");
    sessionStorage.removeItem(API_KEY_STORAGE);
    sessionStorage.removeItem(JWT_TOKEN_STORAGE);
  }, []);

  const isAuthenticated = !!apiKey || !!token;

  return (
    <AuthContext.Provider value={{ isAuthenticated, apiKey, token, login, loginWithJWT, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
