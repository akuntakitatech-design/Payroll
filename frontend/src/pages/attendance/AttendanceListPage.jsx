import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Clock, Download, Eye, Plus } from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { PageBody } from "@/components/common/PageHeader";
import { DataTable, FilterBar, FilterSelect, Pagination, TableCard } from "@/components/common/DataTable";
import ToneBadge from "@/components/time/ToneBadge";
import ApprovalTimeline from "@/components/time/ApprovalTimeline";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/lib/auth";
import {
  asOptions,
  currentPeriodKey,
  dayLabel,
  minutesToLabel,
  periodOptions,
  timeInZone,
  useTimeCatalog,
} from "@/lib/timeCatalog";
import { formatDateTime } from "@/lib/format";

const AttendanceListPage = () => {
  const { can } = useAuth();
  const { catalog } = useTimeCatalog();
  const [period, setPeriod] = useState(currentPeriodKey());
  const [statusFilter, setStatusFilter] = useState("");
  const [locationFilter, setLocationFilter] = useState("");
  const [employeeFilter, setEmployeeFilter] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(20);
  const [data, setData] = useState({ items: [], total: 0, total_pages: 1 });
  const [loading, setLoading] = useState(true);
  const [employees, setEmployees] = useState([]);
  const [detail, setDetail] = useState(null);
  const [detailApproval, setDetailApproval] = useState(null);

  const [manualOpen, setManualOpen] = useState(false);
  const [manual, setManual] = useState({
    employee_id: "",
    work_date: "",
    check_in_at: "",
    check_out_at: "",
    reason: "",
  });
  const [savingManual, setSavingManual] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data: res } = await api.get("/attendance", {
        params: {
          period,
          attendance_status: statusFilter || undefined,
          work_location_id: locationFilter || undefined,
          employee_id: employeeFilter || undefined,
          page,
          limit,
        },
      });
      setData(res);
    } catch (error) {
      toast.error(errorMessage(error, "Data absensi tidak dapat dimuat."));
    } finally {
      setLoading(false);
    }
  }, [period, statusFilter, locationFilter, employeeFilter, page, limit]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    api
      .get("/employees", { params: { limit: 200, status: "active" } })
      .then(({ data: res }) => setEmployees(res?.items || []))
      .catch(() => setEmployees([]));
  }, []);

  const rows = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return data.items || [];
    return (data.items || []).filter(
      (r) =>
        String(r.employee_name || "").toLowerCase().includes(term) ||
        String(r.employee_number || "").toLowerCase().includes(term)
    );
  }, [data.items, search]);

  const openDetail = async (row) => {
    setDetail(row);
    setDetailApproval(null);
    try {
      const { data: res } = await api.get(`/attendance/${row.id}`);
      setDetail(res.attendance || res);
      setDetailApproval(res.approval || null);
    } catch (error) {
      toast.error(errorMessage(error, "Detail absensi tidak dapat dimuat."));
    }
  };

  const submitManual = async () => {
    if (!manual.employee_id || !manual.work_date) {
      toast.error("Karyawan dan Tanggal Kerja wajib dipilih.");
      return;
    }
    if (manual.reason.trim().length < 3) {
      toast.error("Alasan pencatatan manual wajib diisi minimal 3 karakter.");
      return;
    }
    setSavingManual(true);
    try {
      const toIso = (v) => (v ? new Date(v).toISOString() : null);
      await api.post("/attendance/manual", {
        employee_id: manual.employee_id,
        work_date: manual.work_date,
        check_in_at: toIso(manual.check_in_at),
        check_out_at: toIso(manual.check_out_at),
        reason: manual.reason.trim(),
      });
      toast.success("Absensi manual tersimpan.");
      setManualOpen(false);
      setManual({ employee_id: "", work_date: "", check_in_at: "", check_out_at: "", reason: "" });
      load();
    } catch (error) {
      toast.error(errorMessage(error, "Absensi manual tidak dapat disimpan."), { duration: 9000 });
    } finally {
      setSavingManual(false);
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
            {row.employee_number || "-"} · {dayLabel(row.work_date)}
          </p>
        </div>
      ),
    },
    { key: "shift", header: "Shift", hideOnMobile: true, render: (row) => row.shift_name || row.day_type_label || "-" },
    { key: "check_in", header: "Masuk", render: (row) => timeInZone(row.check_in_at, row.timezone) },
    { key: "check_out", header: "Pulang", render: (row) => timeInZone(row.check_out_at, row.timezone) },
    { key: "late", header: "Terlambat", align: "right", render: (row) => minutesToLabel(row.late_minutes) },
    { key: "work", header: "Jam Kerja", align: "right", render: (row) => minutesToLabel(row.actual_work_minutes) },
    {
      key: "status",
      header: "Status",
      render: (row) => <ToneBadge tone={row.attendance_status_tone} label={row.attendance_status_label} />,
    },
    {
      key: "actions",
      header: "",
      render: (row) => (
        <Button variant="ghost" size="sm" onClick={() => openDetail(row)} data-testid={`attendance-detail-${row.id}`}>
          <Eye className="mr-1.5 h-3.5 w-3.5" /> Detail
        </Button>
      ),
    },
  ];

  const activeFilters = [statusFilter, locationFilter, employeeFilter].filter(Boolean).length;

  return (
    <PageBody>
      <FilterBar
        search={search}
        onSearchChange={setSearch}
        searchPlaceholder="Cari nama atau nomor karyawan…"
        showReset
        activeFilterCount={activeFilters}
        onReset={() => {
          setStatusFilter("");
          setLocationFilter("");
          setEmployeeFilter("");
          setSearch("");
          setPage(1);
        }}
      >
        <FilterSelect
          label="Periode"
          value={period}
          onChange={(v) => {
            setPeriod(v || currentPeriodKey());
            setPage(1);
          }}
          options={periodOptions()}
          allLabel="Periode"
          testId="attendance-filter-period"
        />
        <FilterSelect
          label="Status"
          value={statusFilter}
          onChange={(v) => {
            setStatusFilter(v);
            setPage(1);
          }}
          options={asOptions(catalog?.attendance_statuses)}
          testId="attendance-filter-status"
        />
        <FilterSelect
          label="Lokasi Kerja"
          value={locationFilter}
          onChange={(v) => {
            setLocationFilter(v);
            setPage(1);
          }}
          options={(catalog?.work_locations || []).map((l) => ({ value: l.id, label: l.name }))}
          testId="attendance-filter-location"
        />
        <FilterSelect
          label="Karyawan"
          value={employeeFilter}
          onChange={(v) => {
            setEmployeeFilter(v);
            setPage(1);
          }}
          options={employees.map((e) => ({ value: e.id, label: e.full_name }))}
          testId="attendance-filter-employee"
        />
      </FilterBar>

      {can("attendance", "create") && (
        <div className="flex justify-end">
          <Button onClick={() => setManualOpen(true)} data-testid="manual-attendance-button">
            <Plus className="mr-2 h-4 w-4" /> Absensi Manual
          </Button>
        </div>
      )}

      <TableCard>
        <DataTable
          columns={columns}
          rows={rows}
          loading={loading}
          testId="attendance-table"
          emptyProps={{
            icon: Clock,
            title: "Belum ada data absensi.",
            description: "Ubah filter periode, atau catat absensi manual / impor dari Excel.",
          }}
        />
        <Pagination
          page={data.page || page}
          totalPages={data.total_pages || 1}
          total={data.total || 0}
          limit={limit}
          onPageChange={setPage}
          onLimitChange={(v) => {
            setLimit(v);
            setPage(1);
          }}
        />
      </TableCard>

      {/* Detail absensi */}
      <Dialog open={!!detail} onOpenChange={(open) => !open && setDetail(null)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto bg-card sm:max-w-2xl" data-testid="attendance-detail-dialog">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">
              {detail?.employee_name} · {dayLabel(detail?.work_date)}
            </DialogTitle>
            <DialogDescription>
              {detail?.shift_name || detail?.day_type_label || "-"} · {detail?.source_label || "-"}
            </DialogDescription>
          </DialogHeader>
          {detail && (
            <div className="space-y-4">
              <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <div>
                  <dt className="text-[12px] text-muted-foreground">Jam Masuk</dt>
                  <dd className="text-sm font-medium">{timeInZone(detail.check_in_at, detail.timezone)}</dd>
                </div>
                <div>
                  <dt className="text-[12px] text-muted-foreground">Jam Pulang</dt>
                  <dd className="text-sm font-medium">{timeInZone(detail.check_out_at, detail.timezone)}</dd>
                </div>
                <div>
                  <dt className="text-[12px] text-muted-foreground">Status</dt>
                  <dd>
                    <ToneBadge tone={detail.attendance_status_tone} label={detail.attendance_status_label} />
                  </dd>
                </div>
                <div>
                  <dt className="text-[12px] text-muted-foreground">Terlambat</dt>
                  <dd className="text-sm font-medium">{minutesToLabel(detail.late_minutes)}</dd>
                </div>
                <div>
                  <dt className="text-[12px] text-muted-foreground">Pulang Cepat</dt>
                  <dd className="text-sm font-medium">{minutesToLabel(detail.early_leave_minutes)}</dd>
                </div>
                <div>
                  <dt className="text-[12px] text-muted-foreground">Jam Kerja</dt>
                  <dd className="text-sm font-medium">{minutesToLabel(detail.actual_work_minutes)}</dd>
                </div>
                <div>
                  <dt className="text-[12px] text-muted-foreground">Lokasi Kerja</dt>
                  <dd className="text-sm font-medium">{detail.work_location_name || "-"}</dd>
                </div>
                <div>
                  <dt className="text-[12px] text-muted-foreground">Jarak Masuk</dt>
                  <dd className="text-sm font-medium">
                    {detail.check_in_distance_meter === null || detail.check_in_distance_meter === undefined
                      ? "-"
                      : `${Math.round(detail.check_in_distance_meter)} m`}
                  </dd>
                </div>
                <div>
                  <dt className="text-[12px] text-muted-foreground">Geofence Masuk</dt>
                  <dd className="text-sm font-medium">{detail.check_in_geofence_label || "-"}</dd>
                </div>
                <div>
                  <dt className="text-[12px] text-muted-foreground">Jarak Pulang</dt>
                  <dd className="text-sm font-medium">
                    {detail.check_out_distance_meter === null || detail.check_out_distance_meter === undefined
                      ? "-"
                      : `${Math.round(detail.check_out_distance_meter)} m`}
                  </dd>
                </div>
                <div>
                  <dt className="text-[12px] text-muted-foreground">Geofence Pulang</dt>
                  <dd className="text-sm font-medium">{detail.check_out_geofence_label || "-"}</dd>
                </div>
                <div>
                  <dt className="text-[12px] text-muted-foreground">Akurasi GPS (Masuk / Pulang)</dt>
                  <dd className="text-sm font-medium">
                    {detail.check_in_accuracy != null ? `${Math.round(detail.check_in_accuracy)} m` : "-"} /{" "}
                    {detail.check_out_accuracy != null ? `${Math.round(detail.check_out_accuracy)} m` : "-"}
                  </dd>
                </div>
              </dl>

              {(detail.check_in_latitude != null || detail.check_out_latitude != null) && (
                <div className="flex flex-wrap gap-3 text-[13px]">
                  {detail.check_in_latitude != null && (
                    <a
                      href={`https://www.google.com/maps?q=${detail.check_in_latitude},${detail.check_in_longitude}`}
                      target="_blank"
                      rel="noreferrer"
                      className="font-medium text-primary underline-offset-2 hover:underline"
                      data-testid="attendance-detail-map-in"
                    >
                      Titik Absen Masuk di peta
                    </a>
                  )}
                  {detail.check_out_latitude != null && (
                    <a
                      href={`https://www.google.com/maps?q=${detail.check_out_latitude},${detail.check_out_longitude}`}
                      target="_blank"
                      rel="noreferrer"
                      className="font-medium text-primary underline-offset-2 hover:underline"
                      data-testid="attendance-detail-map-out"
                    >
                      Titik Absen Pulang di peta
                    </a>
                  )}
                </div>
              )}

              {detail.location_approval_status && detail.location_approval_status !== "not_required" && (
                <div className="rounded-md border border-border bg-muted/40 p-3" data-testid="attendance-detail-location">
                  <p className="text-[13px] font-medium text-foreground">
                    Persetujuan Lokasi: {detail.location_approval_label}
                    {detail.location_approval_for_label ? ` · ${detail.location_approval_for_label}` : ""}
                  </p>
                  {detail.location_reason_label && (
                    <p className="text-[12px] text-muted-foreground">
                      Alasan masuk: {detail.location_reason_label} · {detail.location_reason || "-"}
                    </p>
                  )}
                  {detail.check_out_location_reason_label && (
                    <p className="text-[12px] text-muted-foreground">
                      Alasan pulang: {detail.check_out_location_reason_label} · {detail.check_out_location_reason || "-"}
                    </p>
                  )}
                  {detail.location_decision_notes && (
                    <p className="text-[12px] text-muted-foreground">Catatan penyetuju: {detail.location_decision_notes}</p>
                  )}
                </div>
              )}

              {detail.manual_reason && (
                <p className="text-[13px] text-muted-foreground">Alasan manual: {detail.manual_reason}</p>
              )}
              {detail.correction_reason && (
                <p className="text-[13px] text-muted-foreground">
                  Koreksi: {detail.correction_reason} · {formatDateTime(detail.corrected_at)}
                </p>
              )}

              {detailApproval?.steps?.length ? (
                <>
                  <Separator />
                  <ApprovalTimeline rows={detailApproval.steps} testId="attendance-detail-approval" />
                  {detailApproval.history?.length ? (
                    <details className="text-[12px] text-muted-foreground">
                      <summary className="cursor-pointer font-medium">Putaran persetujuan sebelumnya</summary>
                      <div className="mt-2">
                        <ApprovalTimeline rows={detailApproval.history} testId="attendance-detail-approval-history" />
                      </div>
                    </details>
                  ) : null}
                </>
              ) : null}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDetail(null)} data-testid="attendance-detail-close">
              Tutup
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Absensi manual */}
      <Dialog open={manualOpen} onOpenChange={setManualOpen}>
        <DialogContent className="bg-card sm:max-w-xl" data-testid="manual-attendance-dialog">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">Catat Absensi Manual</DialogTitle>
            <DialogDescription className="leading-relaxed">
              Dipakai untuk karyawan tanpa perangkat absensi. Semua perubahan tercatat pada audit log.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5 sm:col-span-2">
              <Label className="text-[13px] font-medium">
                Karyawan <span className="text-destructive">*</span>
              </Label>
              <Select value={manual.employee_id} onValueChange={(v) => setManual((s) => ({ ...s, employee_id: v }))}>
                <SelectTrigger data-testid="manual-employee">
                  <SelectValue placeholder="Pilih karyawan…" />
                </SelectTrigger>
                <SelectContent>
                  {employees.map((e) => (
                    <SelectItem key={e.id} value={e.id}>
                      {e.full_name} ({e.employee_number})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="manual-date" className="text-[13px] font-medium">
                Tanggal Kerja <span className="text-destructive">*</span>
              </Label>
              <Input
                id="manual-date"
                type="date"
                value={manual.work_date}
                onChange={(e) => setManual((s) => ({ ...s, work_date: e.target.value }))}
                data-testid="manual-work-date"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="manual-in" className="text-[13px] font-medium">
                Jam Masuk
              </Label>
              <Input
                id="manual-in"
                type="datetime-local"
                value={manual.check_in_at}
                onChange={(e) => setManual((s) => ({ ...s, check_in_at: e.target.value }))}
                data-testid="manual-check-in"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="manual-out" className="text-[13px] font-medium">
                Jam Pulang
              </Label>
              <Input
                id="manual-out"
                type="datetime-local"
                value={manual.check_out_at}
                onChange={(e) => setManual((s) => ({ ...s, check_out_at: e.target.value }))}
                data-testid="manual-check-out"
              />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="manual-reason" className="text-[13px] font-medium">
                Alasan <span className="text-destructive">*</span>
              </Label>
              <Textarea
                id="manual-reason"
                rows={3}
                value={manual.reason}
                onChange={(e) => setManual((s) => ({ ...s, reason: e.target.value }))}
                placeholder="Contoh: mesin absensi site sedang rusak."
                data-testid="manual-reason"
              />
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setManualOpen(false)} disabled={savingManual} data-testid="manual-cancel">
              Batal
            </Button>
            <Button onClick={submitManual} disabled={savingManual} data-testid="manual-submit">
              Simpan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageBody>
  );
};

export default AttendanceListPage;
