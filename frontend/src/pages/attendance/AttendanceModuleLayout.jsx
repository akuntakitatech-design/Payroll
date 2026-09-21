import React, { useEffect } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import {
  CalendarRange,
  ClipboardCheck,
  Clock,
  FileSpreadsheet,
  LayoutDashboard,
  ListChecks,
  Settings2,
  UserCheck,
} from "lucide-react";

import PageHeader from "@/components/common/PageHeader";
import TimeTabs from "@/components/time/TimeTabs";
import { useAuth } from "@/lib/auth";
import { useAttendanceScope } from "@/lib/attendanceScope";

const AttendanceModuleLayout = () => {
  const { can } = useAuth();
  const { hrScope, selfOnly } = useAttendanceScope();
  const location = useLocation();

  useEffect(() => {
    document.title = "Absensi · HRIS Suite";
  }, []);

  const tabs = [
    hrScope && { to: "/modules/attendance", label: "Ringkasan", icon: LayoutDashboard },
    { to: "/modules/attendance/saya", label: "Absensi Saya", icon: UserCheck },
    hrScope && { to: "/modules/attendance/data", label: "Data Absensi", icon: ListChecks },
    { to: "/modules/attendance/jadwal", label: selfOnly ? "Jadwal Saya" : "Jadwal Kerja", icon: CalendarRange },
    hrScope && { to: "/modules/attendance/rekap", label: "Rekap & Pengecualian", icon: Clock },
    hrScope && { to: "/modules/attendance/persetujuan", label: "Persetujuan", icon: ClipboardCheck },
    hrScope &&
      can("attendance", "create") && {
        to: "/modules/attendance/impor",
        label: "Impor Excel",
        icon: FileSpreadsheet,
      },
    hrScope && { to: "/modules/attendance/pengaturan", label: "Pengaturan", icon: Settings2 },
  ];

  // Karyawan self-service: halaman utama modul langsung ke Absensi Saya.
  if (selfOnly && location.pathname.replace(/\/$/, "") === "/modules/attendance") {
    return <Navigate to="/modules/attendance/saya" replace />;
  }

  return (
    <>
      <PageHeader
        title="Absensi"
        subtitle={
          selfOnly
            ? "Absen Masuk dan Absen Pulang berbasis GPS, jadwal kerja, dan riwayat kehadiran Anda."
            : "Jadwal kerja, absensi harian berbasis GPS, koreksi, rekap, dan persetujuan dalam satu modul."
        }
      />
      <TimeTabs items={tabs} />
      <Outlet />
    </>
  );
};

export default AttendanceModuleLayout;
