import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import {
  AlertTriangle,
  CalendarOff,
  CheckCircle2,
  Clock,
  LogOut,
  MapPinOff,
  UserCheck,
  Users,
} from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { PageBody, SectionHeader } from "@/components/common/PageHeader";
import { DataTable, TableCard, FilterSelect } from "@/components/common/DataTable";
import StatTile from "@/components/time/StatTile";
import ToneBadge from "@/components/time/ToneBadge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { dayLabel, timeInZone, todayIso } from "@/lib/timeCatalog";

const AttendanceOverviewPage = () => {
  const [workDate, setWorkDate] = useState(todayIso());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (date) => {
    setLoading(true);
    try {
      const { data: res } = await api.get("/attendance/dashboard", { params: { work_date: date } });
      setData(res);
    } catch (error) {
      toast.error(errorMessage(error, "Ringkasan absensi tidak dapat dimuat."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(workDate);
  }, [load, workDate]);

  const c = data?.counters || {};

  const columns = [
    {
      key: "employee",
      header: "Karyawan",
      render: (row) => (
        <div className="min-w-0">
          <p className="truncate text-[13px] font-medium text-foreground">{row.employee_name}</p>
          <p className="text-[12px] text-muted-foreground">{row.employee_number || "-"}</p>
        </div>
      ),
    },
    { key: "shift_name", header: "Shift", render: (row) => row.shift_name || "-" },
    { key: "check_in", header: "Masuk", render: (row) => timeInZone(row.check_in_at, row.timezone) },
    { key: "check_out", header: "Pulang", render: (row) => timeInZone(row.check_out_at, row.timezone) },
    {
      key: "status",
      header: "Status",
      render: (row) => (
        <ToneBadge
          tone={row.attendance_status_tone}
          label={row.attendance_status_label}
          testId={`attendance-status-${row.id}`}
        />
      ),
    },
  ];

  return (
    <PageBody>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="w-full max-w-[14rem]">
          <label className="mb-1 block text-[12px] font-medium text-muted-foreground" htmlFor="overview-date">
            Tanggal Kerja
          </label>
          <input
            id="overview-date"
            type="date"
            value={workDate}
            onChange={(e) => setWorkDate(e.target.value || todayIso())}
            className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            data-testid="overview-date-input"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" asChild data-testid="overview-goto-me">
            <Link to="/modules/attendance/saya">
              <UserCheck className="mr-2 h-4 w-4" /> Absensi Saya
            </Link>
          </Button>
          <Button variant="outline" asChild data-testid="overview-goto-approvals">
            <Link to="/modules/attendance/persetujuan">Persetujuan</Link>
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" data-testid="overview-loading">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" data-testid="attendance-counters">
          <StatTile label="Terjadwal Hari Ini" value={c.scheduled_today} icon={Users} tone="info" testId="tile-scheduled" />
          <StatTile label="Hadir" value={c.present_today} icon={CheckCircle2} tone="success" testId="tile-present" />
          <StatTile label="Terlambat" value={c.late_today} icon={Clock} tone="warning" testId="tile-late" />
          <StatTile label="Sedang Bekerja" value={c.working_now} icon={Clock} tone="primary" testId="tile-working" />
          <StatTile label="Belum Absen Pulang" value={c.no_check_out} icon={LogOut} tone="warning" testId="tile-no-checkout" />
          <StatTile
            label="Menunggu Persetujuan Lokasi"
            value={c.awaiting_location_approval}
            icon={MapPinOff}
            tone="warning"
            testId="tile-awaiting-location"
          />
          <StatTile label="Tidak Hadir" value={c.absent_today} icon={AlertTriangle} tone="danger" testId="tile-absent" />
          <StatTile label="Cuti / Izin / Sakit" value={c.on_leave_today} icon={CalendarOff} tone="info" testId="tile-on-leave" />
        </div>
      )}

      <div className="space-y-3">
        <SectionHeader
          title={`Absensi ${dayLabel(data?.work_date || workDate)}`}
          description="Daftar kehadiran karyawan pada tanggal terpilih."
        />
        <TableCard>
          <DataTable
            columns={columns}
            rows={data?.today_rows || []}
            loading={loading}
            testId="attendance-today-table"
            emptyProps={{
              icon: Clock,
              title: "Belum ada absensi pada tanggal ini.",
              description:
                "Pastikan jadwal kerja sudah dibuat, lalu karyawan melakukan absen masuk, atau impor data absensi dari Excel.",
            }}
          />
        </TableCard>
      </div>

      {(data?.on_leave_rows || []).length > 0 && (
        <div className="space-y-3">
          <SectionHeader title="Sedang Cuti / Izin / Sakit" description="Karyawan dengan pengajuan disetujui pada tanggal ini." />
          <TableCard>
            <DataTable
              columns={[
                { key: "employee_name", header: "Karyawan" },
                { key: "leave_type_name", header: "Jenis" },
                {
                  key: "range",
                  header: "Tanggal",
                  render: (row) => `${dayLabel(row.start_date)} s/d ${dayLabel(row.end_date)}`,
                },
                { key: "day_part_label", header: "Bagian Hari" },
              ]}
              rows={data.on_leave_rows}
              testId="attendance-onleave-table"
              emptyProps={{ title: "Tidak ada karyawan yang cuti." }}
            />
          </TableCard>
        </div>
      )}
    </PageBody>
  );
};

export default AttendanceOverviewPage;
