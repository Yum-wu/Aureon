// Auth context for route guards.
// Supports two auth modes:
// 1. API Key (X-API-Key header) — legacy mode
// 2. JWT Bearer token — SSO login mode
// When API_AUTH_KEY is empty (dev mode), all routes are accessible.

// 兼容层：内部使用 useAuthStore，通过 Context 向外暴露
// 这样现有使用 useAuth() 的组件不需要改

import { type ReactNode } from "react";
import { AuthContext } from "./AuthContext";
import { useAuthStore } from "../stores/useAuthStore";

export function AuthProvider({ children }: { children: ReactNode }) {
  const store = useAuthStore();

  return (
    <AuthContext.Provider value={store}>
      {children}
    </AuthContext.Provider>
  );
}
