import React, { useEffect } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { PackageSearch, Settings2 } from "lucide-react";

import PageHeader from "@/components/common/PageHeader";
import EmptyState from "@/components/common/EmptyState";
import TimeTabs from "@/components/time/TimeTabs";
import { useAuth } from "@/lib/auth";

// Phase 2A CP1 - Manajemen Aset. Hanya Daftar Aset + Pengaturan (submenu CP2+ belum ditampilkan).
// Visibilitas: modul `asset` aktif + permission (tanpa cek nama role).
export const assetTabs = (can) =>
  [
    can("asset", "view") && { to: "/modules/asset/assets", label: "Daftar Aset", icon: PackageSearch },
    can("asset_master", "view") && { to: "/modules/asset/settings", label: "Pengaturan", icon: Settings2 },
  ].filter(Boolean);

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
        subtitle="Master aset per unit fisik: kode, serial number, project, lokasi, kondisi, dan status."
      />
      <TimeTabs items={tabs} testId="asset-module-tabs" />
      <Outlet />
    </>
  );
};

export default AssetModuleLayout;
