import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, Eye, Plus, RefreshCw, Timer, XCircle } from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { downloadFile } from "@/lib/download";
import { PageBody, SectionHeader } from "@/components/common/PageHeader";
import { DataTable, FilterSelect, TableCard } from "@/components/common/DataTable";
import ToneBadge from "@/components/time/ToneBadge";
import ApprovalTimeline from "@/components/time/ApprovalTimeline";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
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
import { asOptions, currentPeriodKey, dayLabel, minutesToLabel, periodOptions, useTimeCatalog } from "@/lib/timeCatalog";

const OvertimePage = () => {
  const { can } = useAuth();
  const { catalog } = useTimeCatalog();
  const [period, setPeriod] = useState(currentPeriodKey());
  const [statusFilter, setStatusFilter] = useState("");
  const [mineOnly, setMineOnly] = useState(false);
  const [items, setItems] = useState([]);
  const [policy, setPolicy] = useState(null);
  const [loading, setLoading] = useState(true);
  const [employees, setEmployees] = useState([]);
  const [detail, setDetail] = useState(null);
  const [exporting, setExporting] = useState(false);

  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    work_date: "",
    planned_start_time: "",
    planned_end_time: "",
    overtime_category: "operational",
    reason: "",
    employee_id: "",
    notes: "",
  });

  const [cancelRow, setCancelRow] = useState(null);
  const [cancelReason, setCancelReason] = useState("");
  const [cancelling, setCancelling] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/overtime/requests", {
        params: { period, request_status: statusFilter || undefined, mine: mineOnly || undefined },
      });
      setItems(data?.items || []);
      setPolicy(data?.policy || null);
    } catch (error) {
      toast.error(errorMessage(error, "Daftar lembur tidak dapat dimuat."));
    } finally {
      setLoading(false);
    }
  }, [period, statusFilter, mineOnly]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    api
      .get("/employees", { params: { limit: 200, status: "active" } })
      .then(({ data }) => setEmployees(data?.items || []))
      .catch(() => setEmployees([]));
  }, []);

  const submit = async () => {
    if (!form.work_date || !form.planned_start_time || !form.planned_end_time) {
      toast.error("Tanggal, Jam Mulai, dan Jam Selesai wajib diisi.");
      return;
    }
    if (form.reason.trim().length < 3) {
      toast.error("Alasan lembur wajib diisi minimal 3 karakter.");
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.post("/overtime/requests", {
        work_date: form.work_date,
        planned_start_time: form.planned_start_time,
        planned_end_time: form.planned_end_time,
        overtime_category: form.overtime_category,
        reason: form.reason.trim(),
        notes: form.notes || null,
        employee_id: form.employee_id || null,
      });
      toast.success(data?.message || "Pengajuan lembur terkirim dan menunggu persetujuan.");
      setOpen(false);
      setForm({
        work_date: "",
        planned_start_time: "",
        planned_end_time: "",
        overtime_category: "operational",
        reason: "",
        employee_id: "",
        notes: "",
      });
      load();
    } catch (error) {
      toast.error(errorMessage(error, "Pengajuan lembur tidak dapat dikirim."), { duration: 9000 });
    } finally {
      setSaving(false);
    }
  };

  const refreshActual = async (row) => {
    try {
      const { data } = await api.post(`/overtime/requests/${row.id}/refresh-actual`);
      toast.success(data?.message || "Menit aktual diperbarui dari data absensi.");
      load();
    } catch (error) {
      toast.error(errorMessage(error, "Menit aktual tidak dapat diperbarui."));
    }
  };

  const cancel = async () => {
    if (cancelReason.trim().length < 3) {
      toast.error("Alasan pembatalan wajib diisi minimal 3 karakter.");
      return;
    }
    setCancelling(true);
    try {
      const { data } = await api.post(`/overtime/requests/${cancelRow.id}/cancel`, { reason: cancelReason.trim() });
      toast.success(data?.message || "Pengajuan lembur dibatalkan.");
      setCancelRow(null);
      setCancelReason("");
      load();
    } catch (error) {
      toast.error(errorMessage(error, "Pengajuan lembur tidak dapat dibatalkan."), { duration: 9000 });
    } finally {
      setCancelling(false);
    }
  };

  const exportExcel = async () => {
    setExporting(true);
    try {
      await downloadFile(
        `/overtime/export?period=${period}${statusFilter ? `&request_status=${statusFilter}` : ""}`,
        `Lembur-${period}.xlsx`
      );
      toast.success("Data lembur berhasil diunduh.");
    } catch (error) {
      toast.error(errorMessage(error, "Data lembur tidak dapat diunduh."));
    } finally {
      setExporting(false);
    }
  };

  const columns = [
    {
      key: "employee",
      header: "Karyawan",
      render: (r) => (
        <div className="min-w-0">
          <p className="truncate text-[13px] font-medium text-foreground">{r.employee_name}</p>
          <p className="text-[12px] text-muted-foreground">
            {dayLabel(r.work_date)} · {r.day_category_label}
          </p>
        </div>
      ),
    },
    {
      key: "planned",
      header: "Rencana",
      render: (r) => `${r.planned_start_time || "-"} - ${r.planned_end_time || "-"}`,
    },
    { key: "requested_minutes", header: "Diajukan", align: "right", render: (r) => minutesToLabel(r.requested_minutes) },
    {
      key: "actual_minutes",
      header: "Aktual",
      align: "right",
      render: (r) => minutesToLabel(r.actual_preview?.actual_minutes ?? r.actual_minutes),
    },
    { key: "approved_minutes", header: "Disetujui", align: "right", render: (r) => minutesToLabel(r.approved_minutes) },
    {
      key: "status",
      header: "Status",
      render: (r) => <ToneBadge tone={r.request_status_tone} label={r.request_status_label} testId={`overtime-status-${r.id}`} />,
    },
    {
      key: "actions",
      header: "",
      render: (r) => (
        <div className="flex justify-end gap-1">
          <Button variant="ghost" size="sm" onClick={() => setDetail(r)} data-testid={`overtime-detail-${r.id}`}>
            <Eye className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="sm" onClick={() => refreshActual(r)} data-testid={`overtime-refresh-${r.id}`}>
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
          {["pending", "approved"].includes(r.request_status) && (
            <Button
              variant="ghost"
              size="sm"
              className="text-destructive hover:text-destructive"
              onClick={() => setCancelRow(r)}
              data-testid={`overtime-cancel-${r.id}`}
            >
              <XCircle className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      ),
    },
  ];

  return (
    <PageBody>
      <SectionHeader
        title="Lembur"
        description={
          policy
            ? `Minimal ${policy.minimum_minutes} menit · pembulatan ${policy.rounding_interval_minutes} menit · maksimal ${policy.max_minutes_per_day} menit per hari.`
            : "Rencana lembur diajukan, disetujui, lalu dibandingkan dengan absensi aktual."
        }
        actions={
          <div className="flex flex-wrap gap-2">
            {can("leave", "export") && (
              <Button variant="outline" onClick={exportExcel} disabled={exporting} data-testid="overtime-export-button">
                <Download className="mr-2 h-4 w-4" /> Ekspor Excel
              </Button>
            )}
            {can("leave", "create") && (
              <Button onClick={() => setOpen(true)} data-testid="overtime-create-button">
                <Plus className="mr-2 h-4 w-4" /> Ajukan Lembur
              </Button>
            )}
          </div>
        }
      />

      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-border bg-card p-3">
        <FilterSelect
          label="Periode"
          value={period}
          onChange={(v) => setPeriod(v || currentPeriodKey())}
          options={periodOptions()}
          allLabel="Periode"
          testId="overtime-filter-period"
        />
        <FilterSelect
          label="Status"
          value={statusFilter}
          onChange={setStatusFilter}
          options={asOptions(catalog?.request_statuses)}
          testId="overtime-filter-status"
        />
        <div className="flex items-center gap-2 self-end pb-1">
          <Switch id="ot-mine" checked={mineOnly} onCheckedChange={setMineOnly} data-testid="overtime-filter-mine" />
          <Label htmlFor="ot-mine" className="text-[13px]">
            Hanya pengajuan saya
          </Label>
        </div>
      </div>

      <TableCard>
        <DataTable
          columns={columns}
          rows={items}
          loading={loading}
          testId="overtime-table"
          emptyProps={{
            icon: Timer,
            title: "Belum ada pengajuan lembur pada periode ini.",
            description: "Ajukan rencana lembur agar dapat disetujui dan diperhitungkan pada payroll.",
            actionLabel: can("leave", "create") ? "Ajukan Lembur" : undefined,
            onAction: can("leave", "create") ? () => setOpen(true) : undefined,
          }}
        />
      </TableCard>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto bg-card sm:max-w-xl" data-testid="overtime-dialog">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">Ajukan Lembur</DialogTitle>
            <DialogDescription className="leading-relaxed">
              Menit lembur final mengikuti absensi aktual dan keputusan penyetuju.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            {can("leave", "edit") && (
              <div className="space-y-1.5 sm:col-span-2">
                <Label className="text-[13px] font-medium">Ajukan Untuk Karyawan (opsional)</Label>
                <Select value={form.employee_id} onValueChange={(v) => setForm((s) => ({ ...s, employee_id: v }))}>
                  <SelectTrigger data-testid="overtime-employee-select">
                    <SelectValue placeholder="Diri sendiri" />
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
            )}
            <div className="space-y-1.5">
              <Label htmlFor="ot-date" className="text-[13px] font-medium">
                Tanggal Lembur <span className="text-destructive">*</span>
              </Label>
              <Input
                id="ot-date"
                type="date"
                value={form.work_date}
                onChange={(e) => setForm((s) => ({ ...s, work_date: e.target.value }))}
                data-testid="overtime-work-date"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[13px] font-medium">Kategori</Label>
              <Select
                value={form.overtime_category}
                onValueChange={(v) => setForm((s) => ({ ...s, overtime_category: v }))}
              >
                <SelectTrigger data-testid="overtime-category">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(catalog?.overtime_categories || []).map((item) => (
                    <SelectItem key={item.key} value={item.key}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ot-start" className="text-[13px] font-medium">
                Jam Mulai <span className="text-destructive">*</span>
              </Label>
              <Input
                id="ot-start"
                type="time"
                value={form.planned_start_time}
                onChange={(e) => setForm((s) => ({ ...s, planned_start_time: e.target.value }))}
                data-testid="overtime-start-time"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ot-end" className="text-[13px] font-medium">
                Jam Selesai <span className="text-destructive">*</span>
              </Label>
              <Input
                id="ot-end"
                type="time"
                value={form.planned_end_time}
                onChange={(e) => setForm((s) => ({ ...s, planned_end_time: e.target.value }))}
                data-testid="overtime-end-time"
              />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="ot-reason" className="text-[13px] font-medium">
                Alasan <span className="text-destructive">*</span>
              </Label>
              <Textarea
                id="ot-reason"
                rows={3}
                value={form.reason}
                onChange={(e) => setForm((s) => ({ ...s, reason: e.target.value }))}
                placeholder="Contoh: menyelesaikan laporan tutup bulan."
                data-testid="overtime-reason"
              />
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setOpen(false)} disabled={saving}>
              Batal
            </Button>
            <Button onClick={submit} disabled={saving} data-testid="overtime-submit">
              Kirim Pengajuan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto bg-card sm:max-w-xl" data-testid="overtime-detail-dialog">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">
              Lembur {detail?.employee_name} · {dayLabel(detail?.work_date)}
            </DialogTitle>
            <DialogDescription>{detail?.day_category_label}</DialogDescription>
          </DialogHeader>
          {detail && (
            <div className="space-y-3">
              <dl className="grid grid-cols-2 gap-2 text-[13px]">
                <div>
                  <dt className="text-[12px] text-muted-foreground">Status</dt>
                  <dd>
                    <ToneBadge tone={detail.request_status_tone} label={detail.request_status_label} />
                  </dd>
                </div>
                <div>
                  <dt className="text-[12px] text-muted-foreground">Rencana</dt>
                  <dd className="font-medium">
                    {detail.planned_start_time} - {detail.planned_end_time}
                  </dd>
                </div>
                <div>
                  <dt className="text-[12px] text-muted-foreground">Menit Diajukan</dt>
                  <dd className="font-medium">{minutesToLabel(detail.requested_minutes)}</dd>
                </div>
                <div>
                  <dt className="text-[12px] text-muted-foreground">Menit Aktual</dt>
                  <dd className="font-medium">
                    {minutesToLabel(detail.actual_preview?.actual_minutes ?? detail.actual_minutes)}
                  </dd>
                </div>
                <div>
                  <dt className="text-[12px] text-muted-foreground">Menit Disetujui</dt>
                  <dd className="font-medium">{minutesToLabel(detail.approved_minutes)}</dd>
                </div>
                <div>
                  <dt className="text-[12px] text-muted-foreground">Kategori</dt>
                  <dd className="font-medium">{detail.overtime_category_label || detail.overtime_category}</dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-[12px] text-muted-foreground">Alasan</dt>
                  <dd className="font-medium">{detail.reason}</dd>
                </div>
                {detail.actual_preview?.note && (
                  <div className="col-span-2">
                    <dt className="text-[12px] text-muted-foreground">Catatan Sistem</dt>
                    <dd className="font-medium">{detail.actual_preview.note}</dd>
                  </div>
                )}
              </dl>
              <Separator />
              <ApprovalTimeline rows={detail.approval?.rows || []} testId="overtime-approval-timeline" />
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDetail(null)}>
              Tutup
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!cancelRow} onOpenChange={(o) => !o && setCancelRow(null)}>
        <DialogContent className="bg-card sm:max-w-lg" data-testid="overtime-cancel-dialog">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">Batalkan Pengajuan Lembur</DialogTitle>
            <DialogDescription className="leading-relaxed">
              Menit lembur disetujui akan dikembalikan menjadi 0 dan rekap kehadiran dihitung ulang.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="ot-cancel-reason" className="text-[13px] font-medium">
              Alasan Pembatalan <span className="text-destructive">*</span>
            </Label>
            <Textarea
              id="ot-cancel-reason"
              rows={3}
              value={cancelReason}
              onChange={(e) => setCancelReason(e.target.value)}
              data-testid="overtime-cancel-reason"
            />
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setCancelRow(null)} disabled={cancelling}>
              Tutup
            </Button>
            <Button variant="destructive" onClick={cancel} disabled={cancelling} data-testid="overtime-cancel-submit">
              Batalkan Pengajuan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageBody>
  );
};

export default OvertimePage;
