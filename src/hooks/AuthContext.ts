import { createContext, useContext } from "react";

export interface AuthState {
  isAuthenticated: boolean;
  apiKey: string;
  token: string;
  role: string | null;
  login: (key: string) => Promise<boolean>;
  loginWithJWT: (email: string, password: string) => Promise<boolean>;
  logout: () => void;
}

export const AuthContext = createContext<AuthState>({
  isAuthenticated: false,
  apiKey: "",
  token: "",
  role: null,
  login: async () => false,
  loginWithJWT: async () => false,
  logout: () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}
