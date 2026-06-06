import { createContext, useContext } from "react";

export interface AuthState {
  isAuthenticated: boolean;
  apiKey: string;
  login: (key: string) => Promise<boolean>;
  logout: () => void;
}

export const AuthContext = createContext<AuthState>({
  isAuthenticated: false,
  apiKey: "",
  login: async () => false,
  logout: () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}
