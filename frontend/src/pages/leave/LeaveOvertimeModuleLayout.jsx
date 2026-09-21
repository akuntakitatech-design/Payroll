import React, { useEffect } from "react";
import { Outlet } from "react-router-dom";
import { CalendarDays, ClipboardCheck, LayoutDashboard, Timer, Wallet } from "lucide-react";

import PageHeader from "@/components/common/PageHeader";
import TimeTabs from "@/components/time/TimeTabs";

const LeaveOvertimeModuleLayout = () => {
  useEffect(() => {
    document.title = "Cuti & Lembur · HRIS Suite";
  }, []);

  const tabs = [
    { to: "/modules/leave_overtime", label: "Ringkasan", icon: LayoutDashboard },
    { to: "/modules/leave_overtime/cuti", label: "Cuti / Izin / Sakit", icon: CalendarDays },
    { to: "/modules/leave_overtime/lembur", label: "Lembur", icon: Timer },
    { to: "/modules/leave_overtime/saldo", label: "Saldo Cuti", icon: Wallet },
    { to: "/modules/leave_overtime/persetujuan", label: "Persetujuan", icon: ClipboardCheck },
  ];

  return (
    <>
      <PageHeader
        title="Cuti & Lembur"
        subtitle="Pengajuan cuti, izin, sakit, dan lembur dengan saldo berbasis buku besar serta persetujuan berjenjang."
      />
      <TimeTabs items={tabs} />
      <Outlet />
    </>
  );
};

export default LeaveOvertimeModuleLayout;
