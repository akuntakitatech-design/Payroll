import React from "react";
import { NavLink } from "react-router-dom";
import { ChevronLeft, ChevronRight, Building2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { filterNav } from "@/lib/nav";
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
      end={item.to === "/" || item.to === "/setup"}
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

export const SidebarContent = ({ collapsed = false, onNavigate }) => {
  const { can, hasModule, company } = useAuth();
  const groups = filterNav({ can, hasModule });

  return (
    <TooltipProvider>
      <div className="flex h-full flex-col bg-card">
        {/* Identitas produk */}
        <div
          className={cn(
            "flex h-14 shrink-0 items-center gap-2.5 border-b border-border px-4",
            collapsed && "justify-center px-2"
          )}
        >
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-xs">
            <Building2 className="h-4 w-4" strokeWidth={2} />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <p className="text-[13.5px] font-bold leading-tight tracking-[-0.01em] text-ink-1">
                HRIS &amp; Payroll
              </p>
              <p className="truncate text-[11px] leading-tight text-ink-3">
                {company?.code ? `Perusahaan ${company.code}` : "Multi Perusahaan"}
              </p>
            </div>
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
