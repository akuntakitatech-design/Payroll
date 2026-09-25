import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import {
  api,
  errorMessage,
  REFRESH_KEY,
  setPasswordChangeRequiredHandler,
  setTenantInactiveHandler,
  setUnauthorizedHandler,
  TOKEN_KEY,
} from "@/lib/api";

const AuthContext = createContext(null);

const SESSION_KEY = "hris_session";

export const AuthProvider = ({ children }) => {
  const [session, setSession] = useState(() => {
    try {
      const raw = localStorage.getItem(SESSION_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState(false);

  const persist = useCallback((data) => {
    if (!data) {
      localStorage.removeItem(SESSION_KEY);
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(REFRESH_KEY);
      setSession(null);
      return;
    }
    if (data.access_token) localStorage.setItem(TOKEN_KEY, data.access_token);
    if (data.refresh_token) localStorage.setItem(REFRESH_KEY, data.refresh_token);
    const stored = {
      user: data.user,
      active_company: data.active_company,
      companies: data.companies || [],
      role_keys: data.role_keys || [],
      permissions: data.permissions || [],
      is_super_admin: !!data.is_super_admin,
      modules: data.modules || [],
    };
    localStorage.setItem(SESSION_KEY, JSON.stringify(stored));
    setSession(stored);
  }, []);

  const logout = useCallback(
    async (silent = false) => {
      if (!silent) {
        try {
          await api.post("/auth/logout");
        } catch {
          /* ignore */
        }
      }
      persist(null);
    },
    [persist]
  );

  useEffect(() => {
    setUnauthorizedHandler(() => {
      persist(null);
    });
  }, [persist]);

  const refreshSession = useCallback(async () => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
      setLoading(false);
      return;
    }
    try {
      const { data } = await api.get("/auth/me");
      const stored = {
        user: data.user,
        active_company: data.active_company,
        companies: data.companies || [],
        role_keys: data.role_keys || [],
        permissions: data.permissions || [],
        is_super_admin: !!data.is_super_admin,
        modules: data.modules || [],
      };
      localStorage.setItem(SESSION_KEY, JSON.stringify(stored));
      setSession(stored);
    } catch (error) {
      persist(null);
    } finally {
      setLoading(false);
    }
  }, [persist]);

  useEffect(() => {
    refreshSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    // Tenant dinonaktifkan Platform Admin saat sesi berjalan -> akhiri sesi (pesan ditampilkan di halaman login).
    setTenantInactiveHandler(() => persist(null));
  }, [persist]);

  useEffect(() => {
    // Password direset Platform Admin saat sesi berjalan -> tandai sesi agar diarahkan ke /change-password.
    setPasswordChangeRequiredHandler(() => {
      setSession((prev) => {
        if (!prev || prev.user?.must_change_password) return prev;
        const next = { ...prev, user: { ...prev.user, must_change_password: true } };
        localStorage.setItem(SESSION_KEY, JSON.stringify(next));
        return next;
      });
    });
  }, []);

  const login = useCallback(
    async (email, password) => {
      const { data } = await api.post("/auth/login", { email, password });
      persist(data);
      return data;
    },
    [persist]
  );

  const switchCompany = useCallback(
    async (companyId) => {
      setSwitching(true);
      try {
        const { data } = await api.post("/auth/switch-company", { company_id: companyId });
        persist(data);
        return data;
      } finally {
        setSwitching(false);
      }
    },
    [persist]
  );

  const permissions = useMemo(() => new Set(session?.permissions || []), [session]);
  const modules = useMemo(() => new Set(session?.modules || []), [session]);

  const can = useCallback(
    (resource, action = "view") => {
      if (!session) return false;
      if (permissions.has("*:*")) return true;
      return permissions.has(`${resource}:${action}`);
    },
    [permissions, session]
  );

  const canAny = useCallback(
    (pairs = []) => pairs.some(([resource, action]) => can(resource, action)),
    [can]
  );

  const hasModule = useCallback((key) => !key || modules.has(key), [modules]);

  const value = useMemo(
    () => ({
      session,
      user: session?.user || null,
      company: session?.active_company || null,
      companies: session?.companies || [],
      roleKeys: session?.role_keys || [],
      isSuperAdmin: !!session?.is_super_admin,
      loading,
      switching,
      login,
      logout,
      switchCompany,
      refreshSession,
      can,
      canAny,
      hasModule,
      errorMessage,
    }),
    [session, loading, switching, login, logout, switchCompany, refreshSession, can, canAny, hasModule]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth harus dipakai di dalam AuthProvider");
  return ctx;
};
