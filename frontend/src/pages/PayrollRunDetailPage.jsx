import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import {
  AlertTriangle,
  ArrowLeft,
  BadgeCheck,
  Banknote,
  Calculator,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  Loader2,
  Plus,
  Receipt,
  Send,
  SlidersHorizontal,
  Trash2,
  X,
  XCircle,
} from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatCurrency, formatDate, formatDateTime } from "@/lib/format";
import { downloadFile } from "@/lib/download";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import EmptyState from "@/components/common/EmptyState";
import { RunStatusBadge } from "@/pages/PayrollRunsPage";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const ACTION_LABELS = {
  submit: "Diajukan",
  submitted: "Diajukan",
  approve: "Disetujui",
  approved: "Disetujui",
  reject: "Ditolak",
  rejected: "Ditolak",
  "mark-paid": "Ditandai dibayar",
  mark_paid: "Ditandai dibayar",
  paid: "Ditandai dibayar",
};

const StatTile = ({ label, value, hint, tone = "default", testId }) => {
  const tones = {
    default: "text-foreground",
    positive: "text-emerald-700",
    warning: "text-amber-700",
  };
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className={`mt-1 text-lg font-semibold tabular-nums ${tones[tone]}`} data-testid={testId}>
          {value}
        </p>
        {hint ? <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p> : null}
      </CardContent>
    </Card>
  );
};

const LineRow = ({ label, value, muted, strong }) => (
  <div className="flex items-baseline justify-between gap-4 py-1 text-sm">
    <span className={muted ? "text-muted-foreground" : ""}>{label}</span>
    <span className={`tabular-nums ${strong ? "font-semibold" : ""}`}>{formatCurrency(value)}</span>
  </div>
);

const emptyLine = () => ({ code: "", name: "", amount: "", taxable: true });

const AdjustmentDialog = ({ runId, item, open, onClose, onSaved, defaultWorkingDays }) => {
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!item) {
      setForm(null);
      return;
    }
    const adj = item.adjustments || {};
    setForm({
      working_days: String(adj.working_days ?? item.attendance?.working_days ?? defaultWorkingDays ?? 22),
      unpaid_days: String(adj.unpaid_days ?? 0),
      overtime_hours: String(adj.overtime_hours ?? 0),
      extra_earnings: (adj.extra_earnings || []).map((row) => ({
        code: row.code || "",
        name: row.name || "",
        amount: String(row.amount ?? ""),
        taxable: row.taxable !== false,
      })),
      extra_deductions: (adj.extra_deductions || []).map((row) => ({
        code: row.code || "",
        name: row.name || "",
        amount: String(row.amount ?? ""),
        taxable: false,
      })),
      notes: adj.notes || "",
    });
  }, [item, defaultWorkingDays]);

  const setLine = (key, index, patch) =>
    setForm((prev) => ({
      ...prev,
      [key]: prev[key].map((row, i) => (i === index ? { ...row, ...patch } : row)),
    }));

  const addLine = (key) => setForm((prev) => ({ ...prev, [key]: [...prev[key], emptyLine()] }));
  const removeLine = (key, index) =>
    setForm((prev) => ({ ...prev, [key]: prev[key].filter((_, i) => i !== index) }));

  const submit = async () => {
    const clean = (rows) =>
      rows
        .filter((row) => row.name.trim() && Number(row.amount) > 0)
        .map((row) => ({
          code: (row.code || row.name).trim().toUpperCase().replace(/\s+/g, "_").slice(0, 24),
          name: row.name.trim(),
          amount: Number(row.amount),
          taxable: !!row.taxable,
        }));
    setSaving(true);
    try {
      const { data } = await api.put(`/payroll/runs/${runId}/items/${item.id}/adjustments`, {
        working_days: Number(form.working_days) || undefined,
        unpaid_days: Number(form.unpaid_days) || 0,
        overtime_hours: Number(form.overtime_hours) || 0,
        extra_earnings: clean(form.extra_earnings),
        extra_deductions: clean(form.extra_deductions),
        notes: form.notes || null,
      });
      toast.success(`Slip ${item.full_name} dihitung ulang.`);
      onSaved(data);
      onClose();
    } catch (error) {
      toast.error(errorMessage(error, "Penyesuaian gagal disimpan."));
    } finally {
      setSaving(false);
    }
  };

  const renderLines = (key, title, description, testPrefix) => (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">{title}</p>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => addLine(key)}
          data-testid={`${testPrefix}-add`}
        >
          <Plus className="mr-1 h-3.5 w-3.5" /> Baris
        </Button>
      </div>
      {form[key].length === 0 ? (
        <p className="rounded-md border border-dashed border-border px-3 py-2 text-xs text-muted-foreground">
          Belum ada baris.
        </p>
      ) : (
        <div className="space-y-2">
          {form[key].map((row, index) => (
            <div key={index} className="flex flex-wrap items-end gap-2">
              <div className="min-w-[160px] flex-1">
                <Label className="text-xs">Keterangan</Label>
                <Input
                  value={row.name}
                  onChange={(e) => setLine(key, index, { name: e.target.value })}
                  placeholder="Contoh: Insentif proyek"
                  data-testid={`${testPrefix}-name-${index}`}
                />
              </div>
              <div className="w-40">
                <Label className="text-xs">Nominal (Rp)</Label>
                <Input
                  type="number"
                  min="0"
                  value={row.amount}
                  onChange={(e) => setLine(key, index, { amount: e.target.value })}
                  data-testid={`${testPrefix}-amount-${index}`}
                />
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="text-muted-foreground"
                onClick={() => removeLine(key, index)}
                data-testid={`${testPrefix}-remove-${index}`}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Penyesuaian — {item?.full_name}</DialogTitle>
          <DialogDescription>
            Isi hanya jika ada pengecualian. Kehadiran default satu bulan penuh.
          </DialogDescription>
        </DialogHeader>
        {form ? (
          <div className="space-y-4">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div>
                <Label htmlFor="adj-working-days">Hari kerja</Label>
                <Input
                  id="adj-working-days"
                  type="number"
                  min="1"
                  max="31"
                  value={form.working_days}
                  onChange={(e) => setForm({ ...form, working_days: e.target.value })}
                  data-testid="adjust-working-days"
                />
              </div>
              <div>
                <Label htmlFor="adj-unpaid-days">Hari tanpa upah</Label>
                <Input
                  id="adj-unpaid-days"
                  type="number"
                  min="0"
                  value={form.unpaid_days}
                  onChange={(e) => setForm({ ...form, unpaid_days: e.target.value })}
                  data-testid="adjust-unpaid-days"
                />
              </div>
              <div>
                <Label htmlFor="adj-overtime">Jam lembur</Label>
                <Input
                  id="adj-overtime"
                  type="number"
                  min="0"
                  step="0.5"
                  value={form.overtime_hours}
                  onChange={(e) => setForm({ ...form, overtime_hours: e.target.value })}
                  data-testid="adjust-overtime-hours"
                />
              </div>
            </div>
            <Separator />
            {renderLines(
              "extra_earnings",
              "Tambahan penghasilan",
              "Insentif, bonus, atau tunjangan sekali bayar.",
              "adjust-earning"
            )}
            <Separator />
            {renderLines(
              "extra_deductions",
              "Tambahan potongan",
              "Kasbon, denda, atau potongan lain di periode ini.",
              "adjust-deduction"
            )}
            <div>
              <Label htmlFor="adj-notes">Catatan</Label>
              <Textarea
                id="adj-notes"
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                placeholder="Alasan penyesuaian (tercatat di audit log)"
                data-testid="adjust-notes"
              />
            </div>
          </div>
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={onClose} data-testid="adjust-cancel">
            Batal
          </Button>
          <Button onClick={submit} disabled={saving || !form} data-testid="adjust-save">
            {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Simpan & hitung ulang
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const PayslipDialog = ({ item, open, onClose, onDownload, downloading }) => (
  <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
    <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
      <DialogHeader>
        <DialogTitle>{item?.full_name}</DialogTitle>
        <DialogDescription>
          {item?.job_title || "-"} · {item?.employee_number || "-"} · {item?.period?.label}
        </DialogDescription>
      </DialogHeader>
      {item ? (
        <div className="space-y-4" data-testid="payslip-detail">
          <div className="grid grid-cols-2 gap-3 text-xs text-muted-foreground sm:grid-cols-4">
            <div>
              <p>Hari kerja</p>
              <p className="text-sm font-medium text-foreground">{item.attendance?.working_days}</p>
            </div>
            <div>
              <p>Tanpa upah</p>
              <p className="text-sm font-medium text-foreground">{item.attendance?.unpaid_days}</p>
            </div>
            <div>
              <p>Jam lembur</p>
              <p className="text-sm font-medium text-foreground">{item.attendance?.overtime_hours}</p>
            </div>
            <div>
              <p>Status PTKP</p>
              <p className="text-sm font-medium text-foreground">
                {item.tax?.ptkp_status} (TER {item.tax?.ter_category})
              </p>
            </div>
          </div>

          <div className="rounded-lg border border-border p-3">
            <p className="mb-1 text-sm font-semibold">Penghasilan</p>
            {(item.earnings || []).map((row) => (
              <LineRow key={row.code} label={row.name} value={row.amount} />
            ))}
            <Separator className="my-2" />
            <LineRow label="Bruto" value={item.totals?.gross} strong />
          </div>

          <div className="rounded-lg border border-border p-3">
            <p className="mb-1 text-sm font-semibold">Potongan</p>
            {(item.deductions || []).map((row) => (
              <LineRow key={row.code} label={row.name} value={row.amount} />
            ))}
            <Separator className="my-2" />
            <LineRow label="Total potongan" value={item.totals?.total_deductions} strong />
          </div>

          <div className="rounded-lg border border-border p-3">
            <p className="mb-1 text-sm font-semibold">Pajak & BPJS</p>
            <p className="mb-2 text-xs text-muted-foreground">{item.tax?.method_label}</p>
            <LineRow label="Bruto kena pajak" value={item.tax?.taxable_gross} />
            {item.tax?.ter_rate_percent !== undefined ? (
              <div className="flex items-baseline justify-between gap-4 py-1 text-sm">
                <span>Tarif TER</span>
                <span className="tabular-nums">{item.tax.ter_rate_percent}%</span>
              </div>
            ) : null}
            <LineRow label="PPh 21" value={item.totals?.pph21} />
            <Separator className="my-2" />
            <LineRow label="BPJS dibayar pekerja" value={item.totals?.bpjs_employee} />
            <LineRow label="BPJS dibayar perusahaan" value={item.totals?.bpjs_employer} muted />
          </div>

          <div className="rounded-lg border border-primary/30 bg-primary/5 p-3">
            <LineRow label="Take home pay" value={item.totals?.net_pay} strong />
          </div>
          {item.adjustments?.notes ? (
            <p className="text-xs text-muted-foreground">Catatan: {item.adjustments.notes}</p>
          ) : null}
        </div>
      ) : null}
      <DialogFooter>
        <Button variant="outline" onClick={onClose} data-testid="payslip-detail-close">
          Tutup
        </Button>
        <Button onClick={() => onDownload(item)} disabled={downloading} data-testid="payslip-detail-download">
          {downloading ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Download className="mr-2 h-4 w-4" />
          )}
          Unduh slip PDF
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
);

const DecisionDialog = ({ config, open, onClose, onConfirm }) => {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) setNote("");
  }, [open]);

  if (!config) return null;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{config.title}</DialogTitle>
          <DialogDescription>{config.description}</DialogDescription>
        </DialogHeader>
        <div>
          <Label htmlFor="decision-note">
            Catatan {config.noteRequired ? "(wajib)" : "(opsional)"}
          </Label>
          <Textarea
            id="decision-note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder={config.placeholder}
            data-testid="decision-note"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} data-testid="decision-cancel">
            Batal
          </Button>
          <Button
            variant={config.destructive ? "destructive" : "default"}
            disabled={busy || (config.noteRequired && !note.trim())}
            onClick={async () => {
              setBusy(true);
              try {
                await onConfirm(note.trim());
              } finally {
                setBusy(false);
              }
            }}
            data-testid="decision-confirm"
          >
            {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            {config.confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const PayrollRunDetailPage = () => {
  const { runId } = useParams();
  const navigate = useNavigate();
  const { can } = useAuth();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [catalog, setCatalog] = useState(null);
  const [busy, setBusy] = useState(false);
  const [adjustItem, setAdjustItem] = useState(null);
  const [detailItem, setDetailItem] = useState(null);
  const [downloadingId, setDownloadingId] = useState(null);
  const [decision, setDecision] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [runRes, catRes] = await Promise.all([
        api.get(`/payroll/runs/${runId}`),
        api.get("/payroll/catalog"),
      ]);
      setData(runRes.data);
      setCatalog(catRes.data);
    } catch (error) {
      toast.error(errorMessage(error, "Payroll tidak dapat dimuat."));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    load();
  }, [load]);

  const run = data?.run;
  const items = useMemo(() => data?.items || [], [data]);
  const totals = run?.totals || {};
  const skipped = run?.skipped || [];

  useEffect(() => {
    if (run?.period_label) document.title = `Payroll ${run.period_label} · HRIS Suite`;
  }, [run?.period_label]);

  const runAction = async (path, payload, successMessage) => {
    setBusy(true);
    try {
      await api.post(`/payroll/runs/${runId}/${path}`, payload || {});
      toast.success(successMessage);
      await load();
      return true;
    } catch (error) {
      toast.error(errorMessage(error, "Aksi payroll gagal."));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const downloadPayslip = async (item) => {
    setDownloadingId(item.id);
    try {
      await downloadFile(
        `/payroll/runs/${runId}/items/${item.id}/payslip`,
        `Slip-Gaji-${item.full_name}.pdf`
      );
      toast.success("Slip gaji diunduh.");
    } catch (error) {
      toast.error(errorMessage(error, "Slip gaji tidak dapat diunduh."));
    } finally {
      setDownloadingId(null);
    }
  };

  const exportRecap = async () => {
    setBusy(true);
    try {
      await downloadFile(`/payroll/runs/${runId}/export`, `Payroll-${run?.period_label}.xlsx`);
      toast.success("Rekap payroll diunduh.");
    } catch (error) {
      toast.error(errorMessage(error, "Rekap tidak dapat diunduh."));
    } finally {
      setBusy(false);
    }
  };

  const removeRun = async () => {
    setBusy(true);
    try {
      await api.delete(`/payroll/runs/${runId}`);
      toast.success("Payroll dihapus.");
      navigate("/payroll/runs");
    } catch (error) {
      toast.error(errorMessage(error, "Payroll tidak dapat dihapus."));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <>
        <PageHeader title="Payroll" subtitle="Memuat detail periode…" />
        <PageBody>
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-64 w-full" />
        </PageBody>
      </>
    );
  }

  if (!run) {
    return (
      <>
        <PageHeader title="Payroll" subtitle="Periode tidak ditemukan." />
        <PageBody>
          <EmptyState
            icon={AlertTriangle}
            title="Periode payroll tidak ditemukan"
            description="Periode mungkin sudah dihapus atau milik perusahaan lain."
            actionLabel="Kembali ke daftar payroll"
            onAction={() => navigate("/payroll/runs")}
            testId="run-not-found"
          />
        </PageBody>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title={`Payroll ${run.period_label}`}
        subtitle={[
          run.status_label || run.run_status,
          `${run.employee_count || 0} karyawan`,
          run.payment_date ? `dibayar ${formatDate(run.payment_date)}` : null,
          run.calculated_at ? `dihitung ${formatDateTime(run.calculated_at)}` : null,
        ]
          .filter(Boolean)
          .join(" · ")}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <RunStatusBadge
              status={run.run_status}
              label={run.status_label}
              testId="run-detail-status"
            />
            <Button variant="ghost" onClick={() => navigate("/payroll/runs")} data-testid="run-back">
              <ArrowLeft className="mr-2 h-4 w-4" /> Daftar
            </Button>
            {can("payroll", "export") && (
              <Button variant="outline" onClick={exportRecap} disabled={busy} data-testid="run-export">
                <FileSpreadsheet className="mr-2 h-4 w-4" /> Rekap Excel
              </Button>
            )}
            {data.can_edit && can("payroll", "edit") && (
              <Button
                variant="outline"
                onClick={() => runAction("recalculate", {}, "Payroll dihitung ulang.")}
                disabled={busy}
                data-testid="run-recalculate"
              >
                <Calculator className="mr-2 h-4 w-4" /> Hitung ulang
              </Button>
            )}
            {data.can_submit && can("payroll", "edit") && (
              <Button
                onClick={() =>
                  setDecision({
                    title: "Ajukan persetujuan payroll",
                    description: `Payroll ${run.period_label} akan dikirim ke penyetuju.`,
                    confirmLabel: "Ajukan",
                    placeholder: "Catatan untuk penyetuju",
                    action: (note) => runAction("submit", { note }, "Payroll diajukan untuk persetujuan."),
                  })
                }
                disabled={busy}
                data-testid="run-submit"
              >
                <Send className="mr-2 h-4 w-4" /> Ajukan persetujuan
              </Button>
            )}
            {data.can_approve && (
              <>
                <Button
                  variant="outline"
                  className="border-destructive/40 text-destructive hover:bg-destructive/10"
                  onClick={() =>
                    setDecision({
                      title: "Tolak payroll",
                      description: "Jelaskan alasan penolakan agar HR dapat memperbaiki.",
                      confirmLabel: "Tolak payroll",
                      placeholder: "Alasan penolakan",
                      noteRequired: true,
                      destructive: true,
                      action: (note) => runAction("reject", { note }, "Payroll ditolak."),
                    })
                  }
                  disabled={busy}
                  data-testid="run-reject"
                >
                  <XCircle className="mr-2 h-4 w-4" /> Tolak
                </Button>
                <Button
                  onClick={() =>
                    setDecision({
                      title: "Setujui payroll",
                      description: `Total take home pay ${formatCurrency(totals.net_pay)} akan disetujui.`,
                      confirmLabel: "Setujui",
                      placeholder: "Catatan persetujuan",
                      action: (note) => runAction("approve", { note }, "Payroll disetujui."),
                    })
                  }
                  disabled={busy}
                  data-testid="run-approve"
                >
                  <CheckCircle2 className="mr-2 h-4 w-4" /> Setujui
                </Button>
              </>
            )}
            {data.can_mark_paid && (
              <Button
                onClick={() =>
                  setDecision({
                    title: "Tandai sudah dibayar",
                    description: "Gunakan setelah transfer bank dilakukan.",
                    confirmLabel: "Tandai dibayar",
                    placeholder: "Nomor referensi transfer (opsional)",
                    action: (note) => runAction("mark-paid", { note }, "Payroll ditandai sudah dibayar."),
                  })
                }
                disabled={busy}
                data-testid="run-mark-paid"
              >
                <Banknote className="mr-2 h-4 w-4" /> Tandai dibayar
              </Button>
            )}
            {can("payroll", "delete") && !["approved", "paid"].includes(run.run_status) && (
              <Button
                variant="ghost"
                className="text-destructive"
                onClick={() =>
                  setDecision({
                    title: "Hapus payroll",
                    description: `Payroll ${run.period_label} beserta seluruh slip gajinya akan dihapus.`,
                    confirmLabel: "Hapus",
                    destructive: true,
                    action: () => removeRun(),
                  })
                }
                disabled={busy}
                data-testid="run-delete"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            )}
          </div>
        }
      />
      <PageBody>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <StatTile label="Bruto" value={formatCurrency(totals.gross)} testId="run-total-gross" />
          <StatTile
            label="BPJS pekerja"
            value={formatCurrency(totals.bpjs_employee)}
            hint={`Perusahaan ${formatCurrency(totals.bpjs_employer)}`}
            testId="run-total-bpjs"
          />
          <StatTile label="PPh 21" value={formatCurrency(totals.pph21)} testId="run-total-pph21" />
          <StatTile
            label="Total potongan"
            value={formatCurrency(totals.total_deductions)}
            tone="warning"
            testId="run-total-deductions"
          />
          <StatTile
            label="Take home pay"
            value={formatCurrency(totals.net_pay)}
            hint={`Beban perusahaan ${formatCurrency(totals.employer_cost)}`}
            tone="positive"
            testId="run-total-net"
          />
        </div>

        {skipped.length > 0 && (
          <div
            className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
            data-testid="run-skipped"
          >
            <p className="flex items-center gap-2 font-medium">
              <AlertTriangle className="h-4 w-4" /> {skipped.length} karyawan belum dihitung
            </p>
            <ul className="mt-1 list-inside list-disc text-xs">
              {skipped.slice(0, 8).map((row) => (
                <li key={row.employee_id}>
                  {row.full_name} — {row.reason}
                </li>
              ))}
            </ul>
            <Button
              variant="outline"
              size="sm"
              className="mt-2 bg-card"
              onClick={() => navigate("/payroll/salaries")}
              data-testid="run-skipped-fix"
            >
              <SlidersHorizontal className="mr-2 h-3.5 w-3.5" /> Atur struktur gaji
            </Button>
          </div>
        )}

        {(run.history || []).length > 0 && (
          <div className="rounded-lg border border-border bg-card p-3" data-testid="run-history">
            <p className="text-sm font-semibold">Riwayat persetujuan</p>
            <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
              {(run.history || []).map((entry, index) => (
                <li key={index} className="flex flex-wrap items-center gap-2">
                  <BadgeCheck className="h-3.5 w-3.5 text-primary" />
                  <span className="font-medium text-foreground">
                    {ACTION_LABELS[entry.action] || ACTION_LABELS[entry.status] || entry.action}
                  </span>
                  <span>oleh {entry.user_name || "-"}</span>
                  <span>{formatDateTime(entry.at)}</span>
                  {entry.note ? <span>— {entry.note}</span> : null}
                </li>
              ))}
            </ul>
          </div>
        )}

        {items.length === 0 ? (
          <EmptyState
            icon={Receipt}
            title="Belum ada slip gaji pada periode ini"
            description="Pastikan karyawan aktif sudah memiliki gaji pokok, lalu hitung ulang payroll."
            actionLabel="Atur struktur gaji"
            onAction={() => navigate("/payroll/salaries")}
            testId="run-items-empty"
          />
        ) : (
          <div className="overflow-hidden rounded-lg border border-border bg-card">
            <Table data-testid="run-items-table">
              <TableHeader>
                <TableRow>
                  <TableHead>Karyawan</TableHead>
                  <TableHead className="text-right">Gaji pokok</TableHead>
                  <TableHead className="text-right">Bruto</TableHead>
                  <TableHead className="text-right">BPJS pekerja</TableHead>
                  <TableHead className="text-right">PPh 21</TableHead>
                  <TableHead className="text-right">Take home</TableHead>
                  <TableHead className="text-right">Aksi</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow key={item.id} data-testid={`run-item-${item.id}`}>
                    <TableCell>
                      <button
                        type="button"
                        className="text-left font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        onClick={() => setDetailItem(item)}
                        data-testid={`run-item-open-${item.id}`}
                      >
                        {item.full_name}
                      </button>
                      <p className="text-xs text-muted-foreground">
                        {item.employee_number || "-"}
                        {item.job_title ? ` · ${item.job_title}` : ""}
                      </p>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatCurrency(item.basic_salary)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatCurrency(item.totals?.gross)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatCurrency(item.totals?.bpjs_employee)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      <span className="block">{formatCurrency(item.totals?.pph21)}</span>
                      <Badge variant="outline" className="mt-0.5 font-normal">
                        {item.tax?.ter_rate_percent !== undefined
                          ? `TER ${item.tax.ter_category} · ${item.tax.ter_rate_percent}%`
                          : "Pasal 17"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right font-semibold tabular-nums">
                      {formatCurrency(item.totals?.net_pay)}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        {data.can_edit && can("payroll", "edit") && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setAdjustItem(item)}
                            data-testid={`run-item-adjust-${item.id}`}
                          >
                            <SlidersHorizontal className="mr-1 h-3.5 w-3.5" /> Sesuaikan
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => downloadPayslip(item)}
                          disabled={downloadingId === item.id}
                          data-testid={`run-item-payslip-${item.id}`}
                        >
                          {downloadingId === item.id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Download className="h-3.5 w-3.5" />
                          )}
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </PageBody>

      <AdjustmentDialog
        runId={runId}
        item={adjustItem}
        open={!!adjustItem}
        onClose={() => setAdjustItem(null)}
        onSaved={() => load()}
        defaultWorkingDays={catalog?.statutory?.default_working_days}
      />
      <PayslipDialog
        item={detailItem}
        open={!!detailItem}
        onClose={() => setDetailItem(null)}
        onDownload={downloadPayslip}
        downloading={downloadingId === detailItem?.id}
      />
      <DecisionDialog
        config={decision}
        open={!!decision}
        onClose={() => setDecision(null)}
        onConfirm={async (note) => {
          const action = decision?.action;
          setDecision(null);
          if (action) await action(note);
        }}
      />
    </>
  );
};

export default PayrollRunDetailPage;
