import React, { useEffect, useRef } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { CalendarDays, CalendarRange, ClipboardList, Plane, Undo2 } from "lucide-react";

import PageHeader from "@/components/common/PageHeader";
import EmptyState from "@/components/common/EmptyState";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

export const rosterTabs = (can) =>
  [
    can("roster", "view") && { to: "/modules/mobilization", label: "Ringkasan", icon: ClipboardList },
    can("roster", "view") && { to: "/modules/mobilization/kalender", label: "Kalender Roster", shortLabel: "Kalender", icon: CalendarRange },
    can("roster", "view") && { to: "/modules/mobilization/rencana", label: "Rencana Cuti (H-30/H-10)", shortLabel: "Rencana Cuti", icon: CalendarDays },
    can("roster", "view") && { to: "/modules/mobilization/mobilisasi", label: "Mobilisasi GA", shortLabel: "Mobilisasi", icon: Plane },
    can("roster", "view") && { to: "/modules/mobilization/kembali", label: "Karyawan Akan Kembali", shortLabel: "Akan Kembali", icon: Undo2 },
  ].filter(Boolean);

export const RosterModuleTabs = ({ items }) => {
  const navRef = useRef(null);
  const location = useLocation();
  useEffect(() => {
    const el = navRef.current?.querySelector('[aria-current="page"]');
    if (el && typeof el.scrollIntoView === "function") el.scrollIntoView({ block: "nearest", inline: "center" });
  }, [location.pathname]);
  return (
    <div className="relative max-w-full border-b border-border bg-card">
      <nav ref={navRef} data-testid="roster-module-tabs" aria-label="Navigasi Roster & Mobilisasi"
        className="flex max-w-full snap-x gap-1.5 overflow-x-auto overscroll-x-contain px-4 py-2 [scrollbar-width:none] sm:px-6 [&::-webkit-scrollbar]:hidden">
        {items.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.to === "/modules/mobilization"}
            data-testid={`roster-tab-${item.to.split("/").pop()}`}
            className={({ isActive }) => cn(
              "inline-flex shrink-0 snap-start items-center gap-1.5 whitespace-nowrap rounded-lg border border-transparent px-3 py-1.5 text-[13px] font-semibold",
              "transition-[background-color,color,box-shadow,border-color] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
              isActive ? "border-[hsl(var(--primary-active))] bg-[image:var(--gradient-primary)] text-white shadow-[var(--shadow-button-primary)]" : "text-ink-2 hover:bg-[hsl(var(--surface-2))] hover:text-ink-1",
            )}>
            {item.icon && <item.icon className="h-4 w-4 shrink-0" strokeWidth={1.75} />}
            {item.shortLabel ? (
              <>
                <span className="sm:hidden">{item.shortLabel}</span>
                <span className="hidden sm:inline">{item.label}</span>
              </>
            ) : item.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
};

const RosterModuleLayout = () => {
  const { can, hasModule } = useAuth();
  useEffect(() => { document.title = "Roster & Mobilisasi · HRIS Suite"; }, []);
  const tabs = rosterTabs(can);
  const moduleOn = hasModule("mobilization");

  if (!moduleOn || !tabs.length) {
    return (
      <>
        <PageHeader title="Roster & Mobilisasi" />
        <EmptyState
          testId="roster-module-unavailable"
          title={moduleOn ? "Anda belum memiliki akses Roster" : "Modul Roster & Mobilisasi belum aktif"}
          description={moduleOn
            ? "Minta administrator menambahkan hak akses roster pada peran Anda."
            : "Modul Roster & Mobilisasi belum diaktifkan untuk perusahaan ini. Hubungi Platform Admin untuk mengaktifkannya."}
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Roster & Mobilisasi"
        subtitle="Pola roster per project, kalender kerja/off, rencana cuti H-30/H-10, mobilisasi GA, dan karyawan yang akan kembali."
      />
      <RosterModuleTabs items={tabs} />
      <Outlet />
    </>
  );
};

export default RosterModuleLayout;
