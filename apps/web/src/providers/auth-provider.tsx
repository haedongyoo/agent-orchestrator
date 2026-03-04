"use client";

import { createContext, useContext, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api-client";
import type { UserResponse, TokenResponse } from "@/lib/types";

interface AuthContextValue {
  user: UserResponse | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  loginWithToken: (token: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();

  const fetchUser = useCallback(async () => {
    try {
      const u = await api.get<UserResponse>("/api/auth/me");
      setUser(u);
    } catch {
      localStorage.removeItem("token");
      setUser(null);
    }
  }, []);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (token) {
      fetchUser().finally(() => setIsLoading(false));
    } else {
      setIsLoading(false);
    }
  }, [fetchUser]);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await api.postForm<TokenResponse>("/api/auth/login", {
        username: email,
        password,
      });
      localStorage.setItem("token", res.access_token);
      await fetchUser();
      router.push("/dashboard");
    },
    [fetchUser, router],
  );

  const register = useCallback(
    async (email: string, password: string) => {
      const res = await api.post<TokenResponse>("/api/auth/register", {
        email,
        password,
      });
      localStorage.setItem("token", res.access_token);
      await fetchUser();
      router.push("/dashboard");
    },
    [fetchUser, router],
  );

  const loginWithToken = useCallback(
    async (token: string) => {
      localStorage.setItem("token", token);
      await fetchUser();
      router.push("/dashboard");
    },
    [fetchUser, router],
  );

  const logout = useCallback(() => {
    localStorage.removeItem("token");
    localStorage.removeItem("workspace_id");
    setUser(null);
    router.push("/login");
  }, [router]);

  return (
    <AuthContext.Provider
      value={{ user, isLoading, login, register, loginWithToken, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
