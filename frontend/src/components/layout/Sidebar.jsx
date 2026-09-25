import React from "react";
import { NavLink, useLocation } from "react-router-dom";
import { ArrowLeftRight, ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { filterNav, PLATFORM_NAV } from "@/lib/nav";
import { PlatformLogo, useBranding } from "@/lib/branding";
import { logoVersion, TenantLogo } from "@/components/common/TenantLogo";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { ScrollArea } from "@/components/ui/scroll-area";

/**
 * Menu aktif ditandai latar primary sangat tipis + garis indikator kiri
 * (bukan pill besar) agar sidebar tetap tenang saat banyak modul aktif.
 */
const NavItem = ({ item, collapsed, onNavigate }) => {
  const Icon = item.icon;
  const content = (
    <NavLink
      to={item.to}
      end={item.end || item.to === "/" || item.to === "/setup"}
      onClick={onNavigate}
      data-testid={`sidebar-nav-item-${item.key}`}
      className={({ isActive }) =>
        cn(
          "group relative flex items-center gap-2.5 rounded-lg py-2 pl-3 pr-2 text-[13px] font-normal text-ink-2",
          "transition-[background-color,color] duration-150",
          "hover:bg-accent hover:text-ink-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
          collapsed && "justify-center px-0",
          isActive &&
            "bg-primary-soft font-semibold text-primary before:absolute before:left-0 before:top-1.5 before:bottom-1.5 before:w-[3px] before:rounded-full before:bg-primary"
        )
      }
    >
      {({ isActive }) => (
        <>
          <Icon
            className={cn(
              "h-4 w-4 shrink-0 transition-transform duration-150",
              !isActive && "group-hover:translate-x-px"
            )}
            strokeWidth={isActive ? 2.1 : 1.75}
          />
          {!collapsed && <span className="truncate">{item.label}</span>}
        </>
      )}
    </NavLink>
  );
  if (!collapsed) return content;
  return (
    <Tooltip delayDuration={120}>
      <TooltipTrigger asChild>{content}</TooltipTrigger>
      <TooltipContent side="right">{item.label}</TooltipContent>
    </Tooltip>
  );
};

export const usePlatformMode = () => {
  const { isSuperAdmin } = useAuth();
  const { pathname } = useLocation();
  return isSuperAdmin && pathname.startsWith("/platform");
};

export const SidebarContent = ({ collapsed = false, onNavigate }) => {
  const { can, hasModule, company, isSuperAdmin } = useAuth();
  const { branding } = useBranding();
  const platformMode = usePlatformMode();
  const groups = platformMode ? PLATFORM_NAV : filterNav({ can, hasModule, isPlatformAdmin: isSuperAdmin });

  return (
    <TooltipProvider>
      <div className="flex h-full flex-col bg-card" data-testid={platformMode ? "sidebar-platform-mode" : "sidebar-tenant-mode"}>
        {/* Identitas: mode platform = logo PLATFORM; mode tenant = logo & nama TENANT */}
        <div
          className={cn(
            "flex h-14 shrink-0 items-center gap-2.5 border-b border-border px-4",
            collapsed && "justify-center px-2"
          )}
          data-testid="sidebar-identity"
        >
          {platformMode ? (
            <PlatformLogo variant={collapsed ? "mark" : "full"} size="sm" testId="sidebar-platform-logo" />
          ) : (
            <>
              <TenantLogo
                size="sm"
                hasLogo={!!company?.logo_path}
                version={logoVersion(company)}
                name={company?.name}
                testId="sidebar-tenant-logo"
              />
              {!collapsed && (
                <div className="min-w-0">
                  <p className="truncate text-[13px] font-bold leading-tight tracking-[-0.01em] text-ink-1" data-testid="sidebar-tenant-name">
                    {company?.name || branding.app_name}
                  </p>
                  <p className="truncate text-[11px] leading-tight text-ink-3" data-testid="sidebar-tenant-code">
                    {company?.code ? `Kode ${company.code}` : branding.subtitle}
                  </p>
                </div>
              )}
            </>
          )}
        </div>

        <ScrollArea className="min-h-0 flex-1">
          <nav className="space-y-5 px-2.5 py-4" data-testid="app-sidebar-nav">
            {groups.map((group) => (
              <div key={group.key} className="space-y-0.5">
                {!collapsed ? (
                  <p className="px-3 pb-1.5 text-[10.5px] font-bold uppercase tracking-[0.1em] text-ink-3/85">
                    {group.label}
                  </p>
                ) : (
                  <div className="mx-auto mb-1.5 h-px w-6 bg-border" aria-hidden="true" />
                )}
                {group.items.map((item) => (
                  <NavItem key={item.key} item={item} collapsed={collapsed} onNavigate={onNavigate} />
                ))}
              </div>
            ))}
          </nav>
        </ScrollArea>

        {!collapsed && (
          <div className="shrink-0 border-t border-border px-4 py-3">
            {platformMode ? (
              company ? (
                <NavLink
                  to="/"
                  onClick={onNavigate}
                  className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-[12px] text-ink-2 transition-colors duration-150 hover:bg-accent hover:text-ink-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  data-testid="sidebar-open-tenant-context"
                >
                  <ArrowLeftRight className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">Buka konteks tenant: {company.code}</span>
                </NavLink>
              ) : null
            ) : (
              <p className="flex items-center gap-1.5 text-[11px] text-ink-3" data-testid="sidebar-powered-by">
                Powered by <span className="font-semibold text-ink-2">{branding.app_name}</span>
              </p>
            )}
          </div>
        )}
      </div>
    </TooltipProvider>
  );
};

const Sidebar = ({ collapsed, setCollapsed }) => (
  <aside
    data-testid="app-sidebar"
    className={cn(
      "relative hidden shrink-0 border-r border-border bg-card lg:block",
      collapsed ? "w-16" : "w-64"
    )}
  >
    <div className="sticky top-0 h-screen">
      <SidebarContent collapsed={collapsed} />
      <button
        type="button"
        data-testid="sidebar-collapse-button"
        onClick={() => setCollapsed(!collapsed)}
        aria-label={collapsed ? "Perlebar menu" : "Perkecil menu"}
        className="absolute -right-3 top-[68px] z-20 flex h-6 w-6 items-center justify-center rounded-full border border-border bg-card text-ink-3 shadow-card transition-colors duration-150 hover:bg-accent hover:text-ink-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {collapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronLeft className="h-3.5 w-3.5" />}
      </button>
    </div>
  </aside>
);

export default Sidebar;
