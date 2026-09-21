import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, Download, FileBarChart } from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { downloadFile } from "@/lib/download";
import { PageBody, SectionHeader } from "@/components/common/PageHeader";
import { DataTable, FilterSelect, TableCard } from "@/components/common/DataTable";
import EmptyState from "@/components/common/EmptyState";
import { Button } from "@/components/ui/button";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/auth";
import { currentPeriodKey, dayLabel, minutesToLabel, periodOptions, useTimeCatalog } from "@/lib/timeCatalog";

const AttendanceRecapPage = () => {
  const { can } = useAuth();
  const { catalog } = useTimeCatalog();
  const [period, setPeriod] = useState(currentPeriodKey());
  const [locationFilter, setLocationFilter] = useState("");
  const [recap, setRecap] = useState(null);
  const [exceptions, setExceptions] = useState(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [a, b] = await Promise.all([
        api.get("/attendance/recap", {
          params: { period, work_location_id: locationFilter || undefined },
        }),
        api.get("/attendance/exceptions", { params: { period } }),
      ]);
      setRecap(a.data);
      setExceptions(b.data);
    } catch (error) {
      toast.error(errorMessage(error, "Rekap kehadiran tidak dapat dimuat."));
    } finally {
      setLoading(false);
    }
  }, [period, locationFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const exportRecap = async () => {
    setExporting(true);
    try {
      await downloadFile(
        `/attendance/recap/export?period=${period}${locationFilter ? `&work_location_id=${locationFilter}` : ""}`,
        `Rekap-Kehadiran-${period}.xlsx`
      );
      toast.success("Rekap kehadiran berhasil diunduh.");
    } catch (error) {
      toast.error(errorMessage(error, "Rekap tidak dapat diunduh."));
    } finally {
      setExporting(false);
    }
  };

  const columns = [
    {
      key: "employee",
      header: "Karyawan",
      render: (row) => (
        <div className="min-w-0">
          <p className="truncate text-[13px] font-medium text-foreground">{row.employee_name}</p>
          <p className="text-[12px] text-muted-foreground">
            {row.employee_number} · {row.department_name || "-"}
          </p>
        </div>
      ),
    },
    { key: "scheduled_days", header: "Terjadwal", align: "right" },
    { key: "present_days", header: "Hadir", align: "right" },
    {
      key: "late_days",
      header: "Terlambat",
      align: "right",
      render: (row) => `${row.late_days} (${minutesToLabel(row.late_minutes)})`,
    },
    {
      key: "early_leave_days",
      header: "Pulang Cepat",
      align: "right",
      hideOnMobile: true,
      render: (row) => `${row.early_leave_days} (${minutesToLabel(row.early_leave_minutes)})`,
    },
    { key: "absent_days", header: "Tidak Hadir", align: "right" },
    { key: "leave_days", header: "Cuti", align: "right", hideOnMobile: true },
    { key: "sick_days", header: "Sakit", align: "right", hideOnMobile: true },
    { key: "permission_days", header: "Izin", align: "right", hideOnMobile: true },
    {
      key: "actual_work_minutes",
      header: "Jam Kerja",
      align: "right",
      render: (row) => row.actual_work_label || minutesToLabel(row.actual_work_minutes),
    },
    {
      key: "approved_overtime_minutes",
      header: "Lembur Disetujui",
      align: "right",
      render: (row) => row.approved_overtime_label || minutesToLabel(row.approved_overtime_minutes),
    },
  ];

  return (
    <PageBody>
      <SectionHeader
        title="Rekap Kehadiran"
        description="Ringkasan bulanan siap dipakai sebagai dasar perhitungan payroll."
        actions={
          can("attendance", "export") ? (
            <Button variant="outline" onClick={exportRecap} disabled={exporting} data-testid="recap-export-button">
              <Download className="mr-2 h-4 w-4" /> Ekspor Excel
            </Button>
          ) : null
        }
      />

      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-border bg-card p-3">
        <FilterSelect
          label="Periode"
          value={period}
          onChange={(v) => setPeriod(v || currentPeriodKey())}
          options={periodOptions()}
          allLabel="Periode"
          testId="recap-filter-period"
        />
        <FilterSelect
          label="Lokasi Kerja"
          value={locationFilter}
          onChange={setLocationFilter}
          options={(catalog?.work_locations || []).map((l) => ({ value: l.id, label: l.name }))}
          testId="recap-filter-location"
        />
      </div>

      <TableCard>
        <DataTable
          columns={columns}
          rows={recap?.items || []}
          loading={loading}
          rowKey={(r) => r.employee_id}
          testId="recap-table"
          emptyProps={{
            icon: FileBarChart,
            title: "Belum ada data rekap pada periode ini.",
            description: "Pastikan jadwal kerja dan absensi sudah tercatat pada periode terpilih.",
          }}
        />
      </TableCard>

      <SectionHeader
        title="Pengecualian"
        description="Hanya hal yang perlu ditindak: belum absen pulang, di luar radius, konflik cuti/lembur, dan lainnya."
      />
      {(exceptions?.groups || []).filter((g) => g.count > 0).length === 0 ? (
        <EmptyState
          icon={AlertTriangle}
          title="Tidak ada pengecualian pada periode ini."
          description="Semua data absensi pada periode ini sudah wajar."
          testId="exceptions-empty"
        />
      ) : (
        <Accordion type="multiple" className="space-y-2" data-testid="exceptions-accordion">
          {(exceptions?.groups || [])
            .filter((g) => g.count > 0)
            .map((group) => (
              <AccordionItem
                key={group.kind}
                value={group.kind}
                className="rounded-lg border border-border bg-card px-3"
              >
                <AccordionTrigger className="hover:no-underline" data-testid={`exception-group-${group.kind}`}>
                  <span className="flex items-center gap-2 text-[13px] font-medium">
                    {group.label}
                    <Badge variant="outline" className="border-warning-border bg-warning-soft text-warning">
                      {group.count}
                    </Badge>
                  </span>
                </AccordionTrigger>
                <AccordionContent>
                  <ul className="space-y-1.5 pb-2">
                    {(group.items || []).slice(0, 100).map((item, index) => (
                      <li
                        key={`${group.kind}-${index}`}
                        className="rounded-md border border-border px-2.5 py-2 text-[13px]"
                      >
                        <span className="font-medium">{item.employee_name || "-"}</span>
                        {item.work_date ? ` · ${dayLabel(item.work_date)}` : ""}
                        <span className="block text-[12px] text-muted-foreground">{item.note}</span>
                      </li>
                    ))}
                  </ul>
                </AccordionContent>
              </AccordionItem>
            ))}
        </Accordion>
      )}
    </PageBody>
  );
};

export default AttendanceRecapPage;
