import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { LogOut, Menu, User, KeyRound, ChevronDown, Gauge } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { initials } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import CompanySwitcher from "./CompanySwitcher";
import { SidebarContent, usePlatformMode } from "./Sidebar";
import GlobalSearch from "./GlobalSearch";
import NotificationBell from "./NotificationBell";
import ReadOnlyPill from "./ReadOnlyPill";

const ROLE_LABELS = {
  super_admin: "Platform Admin",
  tenant_admin: "Tenant Admin",
  company_owner: "Pemilik Perusahaan",
  hr_admin: "HR Admin",
  hr_manager: "HR Manager",
  finance: "Finance",
  manager: "Manager",
  supervisor: "Supervisor",
  employee: "Karyawan",
};

const Topbar = () => {
  const { user, roleKeys, logout, isSuperAdmin } = useAuth();
  const navigate = useNavigate();
  const platformMode = usePlatformMode();
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  const roleText = roleKeys.slice(0, 2).map((r) => ROLE_LABELS[r] || r).join(" · ");

  return (
    <header
      data-testid="app-topbar"
      className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-2 border-b border-border bg-card px-3 sm:gap-3 sm:px-4"
    >
      {/* Menu navigasi untuk layar kecil */}
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            aria-label="Buka menu navigasi"
            data-testid="mobile-nav-trigger"
          >
            <Menu className="h-5 w-5" />
          </Button>
        </SheetTrigger>
        <SheetContent side="left" className="w-[17rem] p-0" data-testid="mobile-nav-drawer">
          <SidebarContent onNavigate={() => setMobileOpen(false)} />
        </SheetContent>
      </Sheet>

      {platformMode ? (
        <div className="flex min-w-0 flex-1 items-center gap-2" data-testid="topbar-platform-context">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-primary-border bg-primary-soft px-2.5 py-1 text-[12px] font-semibold text-primary">
            <Gauge className="h-3.5 w-3.5" /> Konsol Platform
          </span>
          <span className="hidden truncate text-[12px] text-ink-3 md:inline">Pengelolaan tenant, masa layanan, dan branding platform</span>
        </div>
      ) : (
        <>
          <div className="shrink-0" data-testid="topbar-company-selector">
            <CompanySwitcher />
          </div>

          <span className="hidden h-6 w-px bg-border lg:inline-block" aria-hidden="true" />

          {/* Pencarian global mengambil sisa ruang */}
          <div className="flex min-w-0 flex-1 items-center justify-end md:justify-start">
            <GlobalSearch />
          </div>
        </>
      )}

      <div className="ml-auto flex shrink-0 items-center gap-1.5 sm:gap-2">
        <ReadOnlyPill />
        {!platformMode && <NotificationBell />}

        <span className="hidden h-6 w-px bg-border sm:inline-block" aria-hidden="true" />

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              data-testid="topbar-user-menu"
              aria-label="Menu pengguna"
              className="flex h-9 items-center gap-2 rounded-lg px-1.5 transition-colors duration-150 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-primary-border bg-primary-soft text-[11px] font-bold text-primary">
                {initials(user?.full_name)}
              </span>
              <span className="hidden min-w-0 text-left sm:block">
                <span className="block max-w-[9rem] truncate text-[12.5px] font-semibold leading-tight text-ink-1">
                  {user?.full_name}
                </span>
                {roleText && (
                  <span className="block max-w-[9rem] truncate text-[11px] leading-tight text-ink-3">
                    {roleText}
                  </span>
                )}
              </span>
              <ChevronDown className="hidden h-3.5 w-3.5 shrink-0 text-ink-3 sm:block" strokeWidth={2} />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-60">
            <DropdownMenuLabel className="space-y-0.5">
              <p className="text-sm font-semibold">{user?.full_name}</p>
              <p className="truncate text-xs font-normal text-muted-foreground">{user?.email}</p>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            {isSuperAdmin && (
              <DropdownMenuItem asChild data-testid="user-menu-platform">
                <Link to="/platform" className="flex items-center gap-2">
                  <Gauge className="h-4 w-4" /> Konsol Platform
                </Link>
              </DropdownMenuItem>
            )}
            <DropdownMenuItem asChild data-testid="user-menu-profile">
              <Link to="/profile" className="flex items-center gap-2">
                <User className="h-4 w-4" /> Profil Saya
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild data-testid="user-menu-password">
              <Link to="/profile#password" className="flex items-center gap-2">
                <KeyRound className="h-4 w-4" /> Ubah Kata Sandi
              </Link>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={handleLogout}
              className="flex items-center gap-2 text-destructive focus:text-destructive"
              data-testid="user-menu-logout"
            >
              <LogOut className="h-4 w-4" /> Keluar
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
};

export default Topbar;
