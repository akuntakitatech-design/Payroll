import React, { useState } from "react";
import { Link, Outlet } from "react-router-dom";
import { KeyRound } from "lucide-react";
import { DashboardDataProvider } from "@/lib/dashboardData";
import { useAuth } from "@/lib/auth";
import Sidebar, { usePlatformMode } from "./Sidebar";
import Topbar from "./Topbar";
import TenantSubscriptionBanner from "./TenantSubscriptionBanner";

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
            <Outlet />
          </main>
        </div>
      </div>
    </DashboardDataProvider>
  );
};

export default AppShell;
