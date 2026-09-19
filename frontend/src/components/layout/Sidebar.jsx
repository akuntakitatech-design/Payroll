import React from "react";
import { NavLink } from "react-router-dom";
import { ChevronLeft, ChevronRight, Building2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { filterNav } from "@/lib/nav";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { ScrollArea } from "@/components/ui/scroll-area";

/**
 * Menu aktif ditandai garis indikator kiri + latar primary sangat tipis
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
          "relative flex items-center gap-2.5 rounded-md py-2 pl-3 pr-2 text-sm font-normal text-foreground/75",
          "transition-[background-color,color] duration-150",
          "hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          collapsed && "justify-center px-0",
          isActive &&
            "bg-primary-soft font-medium text-primary before:absolute before:left-0 before:top-1.5 before:bottom-1.5 before:w-[3px] before:rounded-full before:bg-primary"
        )
      }
    >
      <Icon className="h-4 w-4 shrink-0" strokeWidth={1.75} />
      {!collapsed && <span className="truncate">{item.label}</span>}
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
        <div
          className={cn(
            "flex h-14 shrink-0 items-center gap-2.5 border-b border-border px-4",
            collapsed && "justify-center px-2"
          )}
        >
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Building2 className="h-4 w-4" strokeWidth={1.75} />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <p className="text-sm font-semibold leading-tight">HRIS Suite</p>
              <p className="truncate text-xs text-muted-foreground">{company?.code || "Multi Perusahaan"}</p>
            </div>
          )}
        </div>

        <ScrollArea className="min-h-0 flex-1">
          <nav className="space-y-4 px-2 py-3" data-testid="app-sidebar-nav">
            {groups.map((group) => (
              <div key={group.key} className="space-y-0.5">
                {!collapsed && (
                  <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground/80">
                    {group.label}
                  </p>
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
      collapsed ? "w-16" : "w-60"
    )}
  >
    <div className="sticky top-0 h-screen">
      <SidebarContent collapsed={collapsed} />
      <button
        type="button"
        data-testid="sidebar-collapse-toggle"
        onClick={() => setCollapsed(!collapsed)}
        aria-label={collapsed ? "Perlebar menu" : "Perkecil menu"}
        className="absolute -right-3 top-[68px] z-20 flex h-6 w-6 items-center justify-center rounded-full border border-border bg-card text-muted-foreground shadow-card transition-colors duration-150 hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {collapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronLeft className="h-3.5 w-3.5" />}
      </button>
    </div>
  </aside>
);

export default Sidebar;
