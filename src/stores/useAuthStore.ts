/** 认证状态 Store */

import { create } from "zustand";
import type { AuthState } from "./types";

const API_KEY_STORAGE = "aureon_api_key";
const JWT_TOKEN_STORAGE = "aureon_jwt_token";

export const useAuthStore = create<AuthState>((set) => ({
  apiKey: sessionStorage.getItem(API_KEY_STORAGE) || "",
  token: sessionStorage.getItem(JWT_TOKEN_STORAGE) || "",
  isAuthenticated: !!sessionStorage.getItem(API_KEY_STORAGE) || !!sessionStorage.getItem(JWT_TOKEN_STORAGE),
  role: (() => {
    try { return sessionStorage.getItem("aureon_role"); } catch { return null; }
  })(),

  login: async (key: string): Promise<boolean> => {
    try {
      const res = await fetch("/api/rag/stats", {
        headers: { "X-API-Key": key },
      });
      if (res.ok) {
        sessionStorage.setItem(API_KEY_STORAGE, key);
        // API Key 模式默认 admin 角色
        sessionStorage.setItem("aureon_role", "admin");
        set({ apiKey: key, isAuthenticated: true, role: "admin" });
        return true;
      }
      return false;
    } catch {
      return false;
    }
  },

  loginWithJWT: async (email: string, password: string): Promise<boolean> => {
    try {
      const res = await fetch("/api/security/sso/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      if (res.ok) {
        const data = await res.json();
        const jwt = data.access_token;
        const role = data.role || "viewer";
        if (jwt) {
          sessionStorage.setItem(JWT_TOKEN_STORAGE, jwt);
          sessionStorage.setItem("aureon_role", role);
          set({ token: jwt, isAuthenticated: true, role });
          return true;
        }
      }
      return false;
    } catch {
      return false;
    }
  },

  logout: () => {
    sessionStorage.removeItem(API_KEY_STORAGE);
    sessionStorage.removeItem(JWT_TOKEN_STORAGE);
    sessionStorage.removeItem("aureon_role");
    set({ apiKey: "", token: "", isAuthenticated: false, role: null });
  },
}));
