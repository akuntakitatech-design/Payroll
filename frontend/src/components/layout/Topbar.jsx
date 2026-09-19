import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { LogOut, Menu, User, KeyRound } from "lucide-react";
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
import { SidebarContent } from "./Sidebar";

const ROLE_LABELS = {
  super_admin: "Super Admin",
  company_owner: "Pemilik Perusahaan",
  hr_admin: "HR Admin",
  hr_manager: "HR Manager",
  finance: "Finance",
  manager: "Manager",
  supervisor: "Supervisor",
  employee: "Karyawan",
};

const Topbar = () => {
  const { user, roleKeys, logout } = useAuth();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  const roleText = roleKeys.slice(0, 2).map((r) => ROLE_LABELS[r] || r).join(" · ");

  return (
    <header
      data-testid="app-topbar"
      className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-border bg-card px-3 sm:px-4"
    >
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

      <CompanySwitcher />

      <div className="ml-auto flex items-center gap-2">
        {/* Peran ditampilkan sebagai teks pendukung, bukan badge berwarna. */}
        {roleText && (
          <span className="hidden text-[13px] text-muted-foreground md:inline" data-testid="topbar-role-label">
            {roleText}
          </span>
        )}
        <span className="hidden h-5 w-px bg-border md:inline-block" aria-hidden="true" />

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              className="h-9 gap-2 px-2"
              data-testid="user-menu-trigger"
              aria-label="Menu pengguna"
            >
              <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary-soft text-[11px] font-semibold text-primary">
                {initials(user?.full_name)}
              </span>
              <span className="hidden max-w-[10rem] truncate text-sm font-medium text-foreground sm:inline">
                {user?.full_name}
              </span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-60">
            <DropdownMenuLabel className="space-y-0.5">
              <p className="text-sm font-semibold">{user?.full_name}</p>
              <p className="truncate text-xs font-normal text-muted-foreground">{user?.email}</p>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
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
