import { createContext, useContext } from "react";

export interface AuthState {
  isAuthenticated: boolean;
  apiKey: string;
  token: string;
  login: (key: string) => Promise<boolean>;
  loginWithJWT: (email: string, password: string) => Promise<boolean>;
  logout: () => void;
}

export const AuthContext = createContext<AuthState>({
  isAuthenticated: false,
  apiKey: "",
  token: "",
  login: async () => false,
  loginWithJWT: async () => false,
  logout: () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}
