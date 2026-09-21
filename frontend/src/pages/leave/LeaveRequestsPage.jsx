import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { CalendarDays, Download, Eye, Plus, XCircle } from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { downloadFile } from "@/lib/download";
import { PageBody, SectionHeader } from "@/components/common/PageHeader";
import { DataTable, FilterSelect, TableCard } from "@/components/common/DataTable";
import ToneBadge from "@/components/time/ToneBadge";
import ApprovalTimeline from "@/components/time/ApprovalTimeline";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
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
import { asOptions, currentPeriodKey, dayLabel, periodOptions, useTimeCatalog } from "@/lib/timeCatalog";
import { formatDateTime } from "@/lib/format";

const LeaveRequestsPage = () => {
  const { can } = useAuth();
  const { catalog } = useTimeCatalog();
  const [period, setPeriod] = useState(currentPeriodKey());
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [mineOnly, setMineOnly] = useState(false);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [employees, setEmployees] = useState([]);
  const [detail, setDetail] = useState(null);
  const [exporting, setExporting] = useState(false);

  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    leave_type_id: "",
    start_date: "",
    end_date: "",
    day_part: "full_day",
    reason: "",
    contact_during_leave: "",
    employee_id: "",
  });

  const [cancelRow, setCancelRow] = useState(null);
  const [cancelReason, setCancelReason] = useState("");
  const [cancelling, setCancelling] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/leave/requests", {
        params: {
          period,
          request_status: statusFilter || undefined,
          leave_type_id: typeFilter || undefined,
          mine: mineOnly || undefined,
        },
      });
      setItems(data?.items || []);
    } catch (error) {
      toast.error(errorMessage(error, "Daftar pengajuan cuti tidak dapat dimuat."));
    } finally {
      setLoading(false);
    }
  }, [period, statusFilter, typeFilter, mineOnly]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    api
      .get("/employees", { params: { limit: 200, status: "active" } })
      .then(({ data }) => setEmployees(data?.items || []))
      .catch(() => setEmployees([]));
  }, []);

  const selectedType = (catalog?.leave_types || []).find((t) => t.id === form.leave_type_id);

  const submit = async () => {
    if (!form.leave_type_id) {
      toast.error("Jenis cuti wajib dipilih.");
      return;
    }
    if (!form.start_date || !form.end_date) {
      toast.error("Tanggal Mulai dan Tanggal Selesai wajib diisi.");
      return;
    }
    if (form.reason.trim().length < 3) {
      toast.error("Alasan wajib diisi minimal 3 karakter.");
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.post("/leave/requests", {
        leave_type_id: form.leave_type_id,
        start_date: form.start_date,
        end_date: form.end_date,
        day_part: form.day_part,
        reason: form.reason.trim(),
        contact_during_leave: form.contact_during_leave || null,
        employee_id: form.employee_id || null,
      });
      toast.success(data?.message || "Pengajuan cuti terkirim dan menunggu persetujuan.");
      setOpen(false);
      setForm({
        leave_type_id: "",
        start_date: "",
        end_date: "",
        day_part: "full_day",
        reason: "",
        contact_during_leave: "",
        employee_id: "",
      });
      load();
    } catch (error) {
      toast.error(errorMessage(error, "Pengajuan cuti tidak dapat dikirim."), { duration: 9000 });
    } finally {
      setSaving(false);
    }
  };

  const cancel = async () => {
    if (cancelReason.trim().length < 3) {
      toast.error("Alasan pembatalan wajib diisi minimal 3 karakter.");
      return;
    }
    setCancelling(true);
    try {
      const { data } = await api.post(`/leave/requests/${cancelRow.id}/cancel`, { reason: cancelReason.trim() });
      toast.success(data?.message || "Pengajuan cuti dibatalkan dan saldo dikembalikan.");
      setCancelRow(null);
      setCancelReason("");
      load();
    } catch (error) {
      toast.error(errorMessage(error, "Pengajuan tidak dapat dibatalkan."), { duration: 9000 });
    } finally {
      setCancelling(false);
    }
  };

  const exportExcel = async () => {
    setExporting(true);
    try {
      await downloadFile(
        `/leave/export?period=${period}${statusFilter ? `&request_status=${statusFilter}` : ""}`,
        `Cuti-Izin-Sakit-${period}.xlsx`
      );
      toast.success("Data cuti berhasil diunduh.");
    } catch (error) {
      toast.error(errorMessage(error, "Data cuti tidak dapat diunduh."));
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
            {r.leave_type_name} · {r.leave_category_label}
          </p>
        </div>
      ),
    },
    { key: "range", header: "Tanggal", render: (r) => `${dayLabel(r.start_date)} s/d ${dayLabel(r.end_date)}` },
    { key: "working_days", header: "Hari Kerja", align: "right" },
    { key: "day_part_label", header: "Bagian Hari", hideOnMobile: true },
    { key: "is_paid", header: "Dibayar", hideOnMobile: true, render: (r) => (r.is_paid ? "Ya" : "Tidak") },
    {
      key: "status",
      header: "Status",
      render: (r) => <ToneBadge tone={r.request_status_tone} label={r.request_status_label} testId={`leave-status-${r.id}`} />,
    },
    {
      key: "actions",
      header: "",
      render: (r) => (
        <div className="flex justify-end gap-1">
          <Button variant="ghost" size="sm" onClick={() => setDetail(r)} data-testid={`leave-detail-${r.id}`}>
            <Eye className="h-3.5 w-3.5" />
          </Button>
          {["pending", "approved"].includes(r.request_status) && (
            <Button
              variant="ghost"
              size="sm"
              className="text-destructive hover:text-destructive"
              onClick={() => setCancelRow(r)}
              data-testid={`leave-cancel-${r.id}`}
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
        title="Pengajuan Cuti / Izin / Sakit"
        description="Saldo cuti dihitung otomatis dari buku besar saat pengajuan disetujui atau dibatalkan."
        actions={
          <div className="flex flex-wrap gap-2">
            {can("leave", "export") && (
              <Button variant="outline" onClick={exportExcel} disabled={exporting} data-testid="leave-export-button">
                <Download className="mr-2 h-4 w-4" /> Ekspor Excel
              </Button>
            )}
            {can("leave", "create") && (
              <Button onClick={() => setOpen(true)} data-testid="leave-create-button">
                <Plus className="mr-2 h-4 w-4" /> Ajukan Cuti
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
          testId="leave-filter-period"
        />
        <FilterSelect
          label="Status"
          value={statusFilter}
          onChange={setStatusFilter}
          options={asOptions(catalog?.request_statuses)}
          testId="leave-filter-status"
        />
        <FilterSelect
          label="Jenis Cuti"
          value={typeFilter}
          onChange={setTypeFilter}
          options={(catalog?.leave_types || []).map((t) => ({ value: t.id, label: t.name }))}
          testId="leave-filter-type"
        />
        <div className="flex items-center gap-2 self-end pb-1">
          <Switch id="leave-mine" checked={mineOnly} onCheckedChange={setMineOnly} data-testid="leave-filter-mine" />
          <Label htmlFor="leave-mine" className="text-[13px]">
            Hanya pengajuan saya
          </Label>
        </div>
      </div>

      <TableCard>
        <DataTable
          columns={columns}
          rows={items}
          loading={loading}
          testId="leave-requests-table"
          emptyProps={{
            icon: CalendarDays,
            title: "Belum ada pengajuan pada periode ini.",
            description: "Ajukan cuti, izin, atau sakit, lalu pantau status persetujuannya di sini.",
            actionLabel: can("leave", "create") ? "Ajukan Cuti" : undefined,
            onAction: can("leave", "create") ? () => setOpen(true) : undefined,
          }}
        />
      </TableCard>

      {/* Form pengajuan */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto bg-card sm:max-w-xl" data-testid="leave-dialog">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">Ajukan Cuti / Izin / Sakit</DialogTitle>
            <DialogDescription className="leading-relaxed">
              Hari libur dan hari OFF tidak dihitung sebagai hari cuti sesuai kebijakan perusahaan.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5 sm:col-span-2">
              <Label className="text-[13px] font-medium">
                Jenis Cuti <span className="text-destructive">*</span>
              </Label>
              <Select value={form.leave_type_id} onValueChange={(v) => setForm((s) => ({ ...s, leave_type_id: v }))}>
                <SelectTrigger data-testid="leave-type-select">
                  <SelectValue placeholder="Pilih jenis cuti…" />
                </SelectTrigger>
                <SelectContent>
                  {(catalog?.leave_types || []).map((t) => (
                    <SelectItem key={t.id} value={t.id}>
                      {t.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {selectedType && (
                <p className="text-[12px] text-muted-foreground">
                  {selectedType.deduct_balance ? "Mengurangi saldo cuti" : "Tidak mengurangi saldo cuti"} ·{" "}
                  {selectedType.is_paid ? "dibayar" : "tidak dibayar"}
                  {selectedType.attachment_required ? " · lampiran wajib" : ""}
                  {selectedType.minimum_notice_days
                    ? ` · minimal ${selectedType.minimum_notice_days} hari sebelum`
                    : ""}
                </p>
              )}
            </div>

            {can("leave", "edit") && (
              <div className="space-y-1.5 sm:col-span-2">
                <Label className="text-[13px] font-medium">Ajukan Untuk Karyawan (opsional)</Label>
                <Select value={form.employee_id} onValueChange={(v) => setForm((s) => ({ ...s, employee_id: v }))}>
                  <SelectTrigger data-testid="leave-employee-select">
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
              <Label htmlFor="leave-start" className="text-[13px] font-medium">
                Tanggal Mulai <span className="text-destructive">*</span>
              </Label>
              <Input
                id="leave-start"
                type="date"
                value={form.start_date}
                onChange={(e) => setForm((s) => ({ ...s, start_date: e.target.value, end_date: s.end_date || e.target.value }))}
                data-testid="leave-start-date"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="leave-end" className="text-[13px] font-medium">
                Tanggal Selesai <span className="text-destructive">*</span>
              </Label>
              <Input
                id="leave-end"
                type="date"
                value={form.end_date}
                onChange={(e) => setForm((s) => ({ ...s, end_date: e.target.value }))}
                data-testid="leave-end-date"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[13px] font-medium">Bagian Hari</Label>
              <Select
                value={form.day_part}
                onValueChange={(v) => setForm((s) => ({ ...s, day_part: v }))}
                disabled={selectedType && !selectedType.allow_half_day}
              >
                <SelectTrigger data-testid="leave-day-part">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(catalog?.day_parts || []).map((item) => (
                    <SelectItem key={item.key} value={item.key}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {selectedType && !selectedType.allow_half_day && (
                <p className="text-[12px] text-muted-foreground">Jenis cuti ini tidak mengizinkan setengah hari.</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="leave-contact" className="text-[13px] font-medium">
                Kontak Saat Cuti
              </Label>
              <Input
                id="leave-contact"
                value={form.contact_during_leave}
                onChange={(e) => setForm((s) => ({ ...s, contact_during_leave: e.target.value }))}
                placeholder="0812xxxxxxx"
                data-testid="leave-contact"
              />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="leave-reason" className="text-[13px] font-medium">
                Alasan <span className="text-destructive">*</span>
              </Label>
              <Textarea
                id="leave-reason"
                rows={3}
                value={form.reason}
                onChange={(e) => setForm((s) => ({ ...s, reason: e.target.value }))}
                placeholder="Contoh: acara keluarga di luar kota."
                data-testid="leave-reason"
              />
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setOpen(false)} disabled={saving} data-testid="leave-cancel-dialog">
              Batal
            </Button>
            <Button onClick={submit} disabled={saving} data-testid="leave-submit">
              Kirim Pengajuan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail pengajuan */}
      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto bg-card sm:max-w-xl" data-testid="leave-detail-dialog">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">
              {detail?.leave_type_name} · {detail?.employee_name}
            </DialogTitle>
            <DialogDescription>
              {dayLabel(detail?.start_date)} s/d {dayLabel(detail?.end_date)} · {detail?.working_days} hari kerja
            </DialogDescription>
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
                  <dt className="text-[12px] text-muted-foreground">Bagian Hari</dt>
                  <dd className="font-medium">{detail.day_part_label}</dd>
                </div>
                <div>
                  <dt className="text-[12px] text-muted-foreground">Diajukan</dt>
                  <dd className="font-medium">{formatDateTime(detail.submitted_at)}</dd>
                </div>
                <div>
                  <dt className="text-[12px] text-muted-foreground">Kontak</dt>
                  <dd className="font-medium">{detail.contact_during_leave || "-"}</dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-[12px] text-muted-foreground">Alasan</dt>
                  <dd className="font-medium">{detail.reason}</dd>
                </div>
                {detail.cancel_reason && (
                  <div className="col-span-2">
                    <dt className="text-[12px] text-muted-foreground">Alasan Pembatalan</dt>
                    <dd className="font-medium">{detail.cancel_reason}</dd>
                  </div>
                )}
              </dl>
              {(detail.conflict_notes || []).length > 0 && (
                <ul className="space-y-1 rounded-md border border-warning-border bg-warning-soft px-3 py-2 text-[12px] text-warning">
                  {detail.conflict_notes.map((note, i) => (
                    <li key={i}>{typeof note === "string" ? note : note?.note || JSON.stringify(note)}</li>
                  ))}
                </ul>
              )}
              <Separator />
              <ApprovalTimeline rows={detail.approval?.rows || []} testId="leave-approval-timeline" />
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDetail(null)} data-testid="leave-detail-close">
              Tutup
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Pembatalan */}
      <Dialog open={!!cancelRow} onOpenChange={(o) => !o && setCancelRow(null)}>
        <DialogContent className="bg-card sm:max-w-lg" data-testid="leave-cancel-dialog-content">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">Batalkan Pengajuan Cuti</DialogTitle>
            <DialogDescription className="leading-relaxed">
              Bila pengajuan sudah disetujui dan mengurangi saldo, saldo akan dikembalikan melalui buku besar.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="leave-cancel-reason" className="text-[13px] font-medium">
              Alasan Pembatalan <span className="text-destructive">*</span>
            </Label>
            <Textarea
              id="leave-cancel-reason"
              rows={3}
              value={cancelReason}
              onChange={(e) => setCancelReason(e.target.value)}
              data-testid="leave-cancel-reason"
            />
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setCancelRow(null)} disabled={cancelling}>
              Tutup
            </Button>
            <Button variant="destructive" onClick={cancel} disabled={cancelling} data-testid="leave-cancel-submit">
              Batalkan Pengajuan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageBody>
  );
};

export default LeaveRequestsPage;
