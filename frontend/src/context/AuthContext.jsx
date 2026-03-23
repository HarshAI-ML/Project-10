import { createContext, useContext, useMemo, useState } from "react";
import { loginUser, registerUser } from "../api/auth";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem("auth_token") || "");
  const [user, setUser] = useState(() => {
    const username = localStorage.getItem("auth_username") || "";
    return username ? { username } : null;
  });
  const [loading, setLoading] = useState(false);

  const login = async (payload) => {
    setLoading(true);
    try {
      const data = await loginUser(payload);
      localStorage.setItem("auth_token", data.token);
      localStorage.setItem("auth_username", data.username);
      setToken(data.token);
      setUser({ username: data.username, email: data.email, id: data.id });
      return data;
    } finally {
      setLoading(false);
    }
  };

  const register = async (payload) => {
    setLoading(true);
    try {
      const data = await registerUser(payload);
      localStorage.setItem("auth_token", data.token);
      localStorage.setItem("auth_username", data.username);
      setToken(data.token);
      setUser({ username: data.username, email: data.email, id: data.id });
      return data;
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    localStorage.removeItem("auth_token");
    localStorage.removeItem("auth_username");
    setToken("");
    setUser(null);
  };

  const value = useMemo(
    () => ({ token, user, loading, isAuthenticated: Boolean(token), login, register, logout }),
    [token, user, loading]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
