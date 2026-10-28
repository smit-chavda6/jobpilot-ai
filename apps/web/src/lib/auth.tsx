import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";
import { api, ApiError } from "@/api/client";
import type { User } from "@/api/types";

interface AuthApi {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  setUser: (u: User | null) => void;
  resetData: () => void;
}

const Ctx = createContext<AuthApi | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const me = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await api.get<User>("/api/auth/me");
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
    retry: false,
  });

  const setUser = useCallback((u: User | null) => qc.setQueryData(["me"], u), [qc]);
  // Drop every cached query except the session itself: clearing "me" would detach this provider's observer.
  const resetData = useCallback(() => qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" }), [qc]);

  const value = useMemo<AuthApi>(
    () => ({
      user: me.data ?? null,
      loading: me.isLoading,
      setUser,
      resetData,
      login: async (email, password) => {
        const u = await api.post<User>("/api/auth/login", { email, password });
        resetData();
        setUser(u);
        return u;
      },
      register: async (email, password) => {
        const u = await api.post<User>("/api/auth/register", { email, password });
        resetData();
        setUser(u);
        return u;
      },
      logout: async () => {
        try {
          await api.post("/api/auth/logout");
        } finally {
          resetData();
          setUser(null);
        }
      },
    }),
    [me.data, me.isLoading, resetData, setUser],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthApi {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
