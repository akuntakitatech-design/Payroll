import React, { useEffect, useRef } from "react";
import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { FileCheck2, HandCoins, PackageSearch, Settings2, Undo2 } from "lucide-react";

import PageHeader from "@/components/common/PageHeader";
import EmptyState from "@/components/common/EmptyState";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

// Phase 2A CP1 + CP2 - Manajemen Aset: Daftar Aset, Penyerahan, Pengembalian & Pemeriksaan, Dokumen BAST, Pengaturan.
// Visibilitas: modul `asset` aktif + permission (tanpa cek nama role).
export const assetTabs = (can) =>
  [
    can("asset", "view") && { to: "/modules/asset/assets", label: "Daftar Aset", icon: PackageSearch },
    can("asset_handover", "view") && { to: "/modules/asset/handovers", label: "Penyerahan Aset", icon: HandCoins },
    (can("asset_return", "view") || can("asset_inspection", "view")) &&
      { to: "/modules/asset/returns", label: "Pengembalian & Pemeriksaan", shortLabel: "Pengembalian", icon: Undo2 },
    can("asset_bast", "view") && { to: "/modules/asset/basts", label: "Dokumen BAST", icon: FileCheck2 },
    can("asset_master", "view") && { to: "/modules/asset/settings", label: "Pengaturan", icon: Settings2 },
  ].filter(Boolean);

/** Tab modul Aset (CP2.1, mobile-friendly): scroll horizontal di dalam bar (halaman tidak melebar), teks tidak
 * terpotong (whitespace-nowrap, label pendek di HP), dan tab aktif otomatis digulir ke area terlihat. */
export const AssetModuleTabs = ({ items }) => {
  const navRef = useRef(null);
  const location = useLocation();
  useEffect(() => {
    const el = navRef.current?.querySelector('[aria-current="page"]');
    if (el && typeof el.scrollIntoView === "function") el.scrollIntoView({ block: "nearest", inline: "center" });
  }, [location.pathname]);
  return (
    <div className="relative max-w-full border-b border-border bg-card">
      <nav ref={navRef} data-testid="asset-module-tabs" aria-label="Navigasi Manajemen Aset"
        className="flex max-w-full snap-x gap-1 overflow-x-auto overscroll-x-contain px-4 [scrollbar-width:none] sm:px-6 [&::-webkit-scrollbar]:hidden">
        {items.map((item) => (
          <NavLink key={item.to} to={item.to} end={false} data-testid={`asset-tab-${item.to.split("/").pop()}`}
            className={({ isActive }) => cn(
              "inline-flex shrink-0 snap-start items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2.5 text-[13px] font-medium",
              "transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
              isActive ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:border-border-strong hover:text-foreground",
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
      <div aria-hidden className="pointer-events-none absolute inset-y-0 right-0 w-6 bg-gradient-to-l from-card to-transparent sm:hidden" />
    </div>
  );
};

const AssetModuleLayout = () => {
  const { can, hasModule } = useAuth();
  const location = useLocation();

  useEffect(() => {
    document.title = "Manajemen Aset · HRIS Suite";
  }, []);

  const tabs = assetTabs(can);
  const moduleOn = hasModule("asset");

  if (!moduleOn || !tabs.length) {
    return (
      <>
        <PageHeader title="Manajemen Aset" />
        <EmptyState
          testId="asset-module-unavailable"
          title={moduleOn ? "Anda belum memiliki akses Manajemen Aset" : "Modul Manajemen Aset belum aktif"}
          description={
            moduleOn
              ? "Minta administrator menambahkan hak akses aset pada peran Anda."
              : "Aktifkan modul Manajemen Aset di menu Aktivasi Modul untuk mulai mengelola aset."
          }
        />
      </>
    );
  }

  // /modules/asset -> halaman pertama yang diizinkan (Daftar Aset bila ada).
  if (location.pathname.replace(/\/+$/, "") === "/modules/asset") {
    return <Navigate to={tabs[0].to} replace />;
  }

  return (
    <>
      <PageHeader
        title="Manajemen Aset"
        subtitle="Aset per unit fisik beserta siklus penyerahan, pengembalian, pemeriksaan, dan dokumen BAST."
      />
      <AssetModuleTabs items={tabs} />
      <Outlet />
    </>
  );
};

export default AssetModuleLayout;
