import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { KeyRound } from "lucide-react";
import { DashboardDataProvider } from "@/lib/dashboardData";
import { useAuth } from "@/lib/auth";
import Sidebar, { usePlatformMode } from "./Sidebar";
import Topbar from "./Topbar";
import TenantSubscriptionBanner from "./TenantSubscriptionBanner";
import ModuleGate from "@/components/common/ModuleGate";

/** Jeda minimum antar-refresh sesi agar tidak membanjiri API saat pengguna berpindah halaman. */
const SESSION_REFRESH_MS = 60000;

/** Akun dengan password sementara (dibuat Platform/Tenant Admin) diminta segera mengganti password. */
const MustChangePasswordBanner = () => {
  const { user } = useAuth();
  if (!user?.must_change_password) return null;
  return (
    <div
      className="flex flex-wrap items-center gap-2 border-b border-warning-border bg-warning-soft px-4 py-2 text-[13px] text-ink-1 sm:px-6"
      role="status"
      data-testid="must-change-password-banner"
    >
      <KeyRound className="h-4 w-4 shrink-0 text-warning" />
      <span>Anda masih memakai password sementara. Demi keamanan, segera ganti password Anda.</span>
      <Link
        to="/profile#password"
        className="font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        data-testid="must-change-password-link"
      >
        Ganti password
      </Link>
    </div>
  );
};

const AppShell = () => {
  const [collapsed, setCollapsed] = useState(false);
  const platformMode = usePlatformMode();
  const { refreshSession } = useAuth();
  const location = useLocation();
  const lastRefresh = useRef(Date.now());

  // Aktivasi modul / perubahan hak akses berlaku di backend per request. Supaya menu
  // dan guard route ikut berubah tanpa perlu login ulang, sesi disegarkan sesekali
  // (maksimal sekali per menit) saat berpindah halaman atau kembali ke tab ini.
  const maybeRefreshSession = useCallback(() => {
    if (Date.now() - lastRefresh.current < SESSION_REFRESH_MS) return;
    lastRefresh.current = Date.now();
    refreshSession();
  }, [refreshSession]);

  useEffect(() => {
    maybeRefreshSession();
  }, [location.pathname, maybeRefreshSession]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") maybeRefreshSession();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [maybeRefreshSession]);

  return (
    // Provider dipasang di shell agar ringkasan dashboard hanya diambil sekali
    // dan bisa dipakai bersama oleh lonceng notifikasi serta halaman Dashboard.
    <DashboardDataProvider>
      <div className="flex min-h-screen bg-background">
        <Sidebar collapsed={collapsed} setCollapsed={setCollapsed} />
        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar />
          <MustChangePasswordBanner />
          {!platformMode && <TenantSubscriptionBanner />}
          <main className="min-w-0 flex-1 pb-16" data-testid="app-main">
            <ModuleGate>
              <Outlet />
            </ModuleGate>
          </main>
        </div>
      </div>
    </DashboardDataProvider>
  );
};

export default AppShell;
