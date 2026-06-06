// Auth context for route guards.
// Checks if API_AUTH_KEY is configured on backend.
// When API_AUTH_KEY is empty (dev mode), all routes are accessible.

import { useState, useCallback, type ReactNode } from "react";
import { AuthContext } from "./AuthContext";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [apiKey, setApiKey] = useState(() => sessionStorage.getItem("aureon_api_key") || "");

  const login = useCallback(async (key: string): Promise<boolean> => {
    // Verify key against backend endpoint that requires auth
    // /api/rag/stats requires X-API-Key when API_AUTH_KEY is configured
    try {
      const res = await fetch("/api/rag/stats", {
        headers: { "X-API-Key": key },
      });
      if (res.ok) {
        setApiKey(key);
        sessionStorage.setItem("aureon_api_key", key);
        return true;
      }
      // 401/403 = invalid key
      return false;
    } catch {
      // Network error - don't allow login
      return false;
    }
  }, []);

  const logout = useCallback(() => {
    setApiKey("");
    sessionStorage.removeItem("aureon_api_key");
  }, []);

  return (
    <AuthContext.Provider value={{ isAuthenticated: !!apiKey, apiKey, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
