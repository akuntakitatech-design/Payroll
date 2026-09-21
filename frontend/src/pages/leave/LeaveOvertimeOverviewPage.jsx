import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { AlertTriangle, CalendarCheck, CalendarDays, Clock, Timer, TrendingUp } from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { PageBody, SectionHeader } from "@/components/common/PageHeader";
import { DataTable, TableCard } from "@/components/common/DataTable";
import StatTile from "@/components/time/StatTile";
import ToneBadge from "@/components/time/ToneBadge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { dayLabel, minutesToLabel } from "@/lib/timeCatalog";

const LeaveOvertimeOverviewPage = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data: res } = await api.get("/leave/dashboard");
      setData(res);
    } catch (error) {
      toast.error(errorMessage(error, "Ringkasan cuti & lembur tidak dapat dimuat."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const c = data?.counters || {};

  return (
    <PageBody>
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="outline" asChild data-testid="lo-goto-leave">
          <Link to="/modules/leave_overtime/cuti">Ajukan Cuti</Link>
        </Button>
        <Button variant="outline" asChild data-testid="lo-goto-overtime">
          <Link to="/modules/leave_overtime/lembur">Ajukan Lembur</Link>
        </Button>
      </div>

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="leave-counters">
          <StatTile label="Cuti Menunggu Persetujuan" value={c.pending_leave} icon={Clock} tone="warning" testId="tile-pending-leave" />
          <StatTile label="Sedang Cuti Hari Ini" value={c.on_leave_today} icon={CalendarDays} tone="info" testId="tile-onleave-today" />
          <StatTile label="Cuti Akan Datang" value={c.upcoming_leave} icon={CalendarCheck} tone="primary" testId="tile-upcoming-leave" />
          <StatTile label="Saldo Bermasalah" value={c.balance_problems} icon={AlertTriangle} tone="danger" testId="tile-balance-problem" />
          <StatTile label="Lembur Menunggu Persetujuan" value={c.pending_overtime} icon={Timer} tone="warning" testId="tile-pending-overtime" />
          <StatTile
            label="Lembur Disetujui"
            value={c.approved_overtime}
            hint={`Total ${minutesToLabel(c.approved_overtime_minutes)} pada ${data?.period_label || "-"}`}
            icon={TrendingUp}
            tone="success"
            testId="tile-approved-overtime"
          />
        </div>
      )}

      <SectionHeader title="Cuti Menunggu Persetujuan" description="Pengajuan terbaru yang belum diputuskan." />
      <TableCard>
        <DataTable
          loading={loading}
          rows={data?.pending_leave || []}
          testId="pending-leave-table"
          columns={[
            {
              key: "employee",
              header: "Karyawan",
              render: (r) => (
                <div className="min-w-0">
                  <p className="truncate text-[13px] font-medium text-foreground">{r.employee_name}</p>
                  <p className="text-[12px] text-muted-foreground">{r.leave_type_name}</p>
                </div>
              ),
            },
            { key: "range", header: "Tanggal", render: (r) => `${dayLabel(r.start_date)} s/d ${dayLabel(r.end_date)}` },
            { key: "working_days", header: "Hari Kerja", align: "right" },
            { key: "day_part_label", header: "Bagian Hari", hideOnMobile: true },
            {
              key: "status",
              header: "Status",
              render: (r) => <ToneBadge tone={r.request_status_tone} label={r.request_status_label} />,
            },
          ]}
          emptyProps={{ title: "Tidak ada cuti yang menunggu persetujuan." }}
        />
      </TableCard>

      <SectionHeader title="Lembur Menunggu Persetujuan" description="Rencana lembur yang belum diputuskan." />
      <TableCard>
        <DataTable
          loading={loading}
          rows={data?.pending_overtime || []}
          testId="pending-overtime-table"
          columns={[
            { key: "employee_name", header: "Karyawan" },
            { key: "work_date", header: "Tanggal", render: (r) => dayLabel(r.work_date) },
            {
              key: "planned",
              header: "Rencana",
              render: (r) => `${r.planned_start_time || "-"} - ${r.planned_end_time || "-"}`,
            },
            { key: "requested_minutes", header: "Diajukan", align: "right", render: (r) => minutesToLabel(r.requested_minutes) },
            {
              key: "status",
              header: "Status",
              render: (r) => <ToneBadge tone={r.request_status_tone} label={r.request_status_label} />,
            },
          ]}
          emptyProps={{ title: "Tidak ada lembur yang menunggu persetujuan." }}
        />
      </TableCard>

      {(data?.balance_problems || []).length > 0 && (
        <>
          <SectionHeader title="Saldo Cuti Bermasalah" description="Saldo minus atau melebihi hak cuti." />
          <TableCard>
            <DataTable
              rows={data.balance_problems}
              testId="balance-problem-table"
              columns={[
                { key: "employee_name", header: "Karyawan" },
                { key: "leave_type_code", header: "Jenis Cuti" },
                { key: "entitlement_days", header: "Hak", align: "right" },
                { key: "used_days", header: "Terpakai", align: "right" },
                { key: "available_days", header: "Tersisa", align: "right" },
              ]}
              emptyProps={{ title: "Tidak ada saldo bermasalah." }}
            />
          </TableCard>
        </>
      )}
    </PageBody>
  );
};

export default LeaveOvertimeOverviewPage;
