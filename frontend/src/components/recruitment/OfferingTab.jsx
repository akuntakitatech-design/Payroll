import React, { useMemo, useState } from "react";
import {
  Ban,
  CheckCircle2,
  FileSignature,
  Loader2,
  Pencil,
  Plus,
  Send,
  ThumbsDown,
  ThumbsUp,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatCurrency, formatDate, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Field } from "@/components/common/FormDialog";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import EmptyState from "@/components/common/EmptyState";
import StageBadge from "@/components/recruitment/StageBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const emptyForm = (candidate) => ({
  position_id: candidate?.position_id || "",
  department_id: candidate?.department_id || "",
  work_location_id: candidate?.work_location_id || "",
  project_id: candidate?.project_id || "",
  employment_status_id: "",
  start_date: candidate?.available_from || "",
  basic_salary: "",
  probation_months: "3",
  notes: "",
});

const toOptions = (rows) => (rows || []).map((r) => ({ value: r.id, label: r.code ? `${r.name} (${r.code})` : r.name }));

const InfoRow = ({ label, value, testId }) => (
  <div className="grid grid-cols-1 gap-0.5 border-b border-border/60 py-1.5 last:border-0 sm:grid-cols-[11rem,1fr] sm:gap-4">
    <span className="text-[12px] text-muted-foreground">{label}</span>
    <span className="text-[13px] text-foreground" data-testid={testId}>
      {value || "-"}
    </span>
  </div>
);

/**
 * Tab Offering: satu offering aktif per kandidat (draft -> terkirim ->
 * diterima/ditolak/dibatalkan). Respons dicatat oleh HR. Tidak menyentuh Payroll.
 */
export const OfferingTab = ({ candidate, offerings, catalog, onChanged }) => {
  const { can } = useAuth();
  const [dialog, setDialog] = useState(null); // {mode:'create'|'edit', row}
  const [values, setValues] = useState(emptyForm(candidate));
  const [allowances, setAllowances] = useState([]);
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [respond, setRespond] = useState(null); // {row, response}
  const [respondForm, setRespondForm] = useState({ responded_at: "", response_notes: "" });
  const [respondError, setRespondError] = useState("");
  const [cancel, setCancel] = useState(null); // row
  const [cancelReason, setCancelReason] = useState("");
  const [send, setSend] = useState(null); // row
  const [busy, setBusy] = useState(false);

  const items = offerings?.items || [];
  const active = offerings?.active || null;
  const history = items.filter((o) => !active || o.id !== active.id);
  const canEdit = can("recruitment", "edit");
  const canCreate = !!offerings?.can_create;

  const fields = useMemo(
    () => [
      { name: "position_id", label: "Jabatan", type: "select", required: true, options: toOptions(catalog?.positions) },
      { name: "department_id", label: "Departemen", type: "select", options: toOptions(catalog?.departments) },
      { name: "work_location_id", label: "Lokasi Kerja", type: "select", options: toOptions(catalog?.work_locations) },
      { name: "project_id", label: "Proyek", type: "select", options: toOptions(catalog?.projects) },
      {
        name: "employment_status_id",
        label: "Status Kepegawaian",
        type: "select",
        options: toOptions(catalog?.employment_statuses),
        hint: "Mis. Kontrak / Tetap — dari master Status Kepegawaian.",
      },
      { name: "start_date", label: "Tanggal Mulai Kerja", type: "date", required: true },
      { name: "basic_salary", label: "Gaji Pokok (Rp)", type: "number", required: true, placeholder: "0" },
      { name: "probation_months", label: "Masa Percobaan (bulan)", type: "number", placeholder: "3" },
      { name: "notes", label: "Catatan Offering", type: "textarea", colSpan: 2, placeholder: "Benefit tambahan, syarat, dsb." },
    ],
    [catalog]
  );

  const openCreate = () => {
    setValues(emptyForm(candidate));
    setAllowances([]);
    setErrors({});
    setDialog({ mode: "create" });
  };

  const openEdit = (row) => {
    const v = emptyForm(candidate);
    Object.keys(v).forEach((k) => {
      v[k] = row[k] ?? "";
    });
    v.basic_salary = row.basic_salary ?? "";
    v.probation_months = row.probation_months ?? "";
    setValues(v);
    setAllowances((row.allowances || []).map((a) => ({ name: a.name, amount: String(a.amount ?? "") })));
    setErrors({});
    setDialog({ mode: "edit", row });
  };

  const buildPayload = () => {
    const errs = {};
    if (!values.position_id) errs.position_id = "Jabatan wajib dipilih.";
    if (!values.start_date) errs.start_date = "Tanggal mulai kerja wajib diisi.";
    const salary = Number(values.basic_salary);
    if (values.basic_salary === "" || Number.isNaN(salary) || salary <= 0) errs.basic_salary = "Gaji pokok harus lebih dari 0.";
    const probation = values.probation_months === "" ? undefined : Number(values.probation_months);
    if (probation !== undefined && (Number.isNaN(probation) || probation < 0 || probation > 24)) {
      errs.probation_months = "Masa percobaan 0–24 bulan.";
    }
    const cleanAllowances = [];
    allowances.forEach((a, idx) => {
      const name = (a.name || "").trim();
      const amount = Number(a.amount);
      if (!name && (a.amount === "" || a.amount === undefined)) return;
      if (!name) errs[`allowance_${idx}`] = "Nama tunjangan wajib diisi.";
      else if (Number.isNaN(amount) || amount < 0) errs[`allowance_${idx}`] = "Nominal tunjangan tidak valid.";
      else cleanAllowances.push({ name, amount });
    });
    if (Object.keys(errs).length) {
      setErrors(errs);
      return null;
    }
    const payload = {
      position_id: values.position_id,
      department_id: values.department_id || undefined,
      work_location_id: values.work_location_id || undefined,
      project_id: values.project_id || undefined,
      employment_status_id: values.employment_status_id || undefined,
      start_date: values.start_date,
      basic_salary: salary,
      probation_months: probation,
      notes: values.notes?.trim() || undefined,
      allowances: cleanAllowances,
    };
    return payload;
  };

  const submit = async () => {
    const payload = buildPayload();
    if (!payload) return;
    setSubmitting(true);
    setErrors({});
    try {
      if (dialog.mode === "create") {
        await api.post(`/recruitment/candidates/${candidate.id}/offering`, payload);
        toast.success("Draft offering dibuat. Periksa lalu kirim ke kandidat.");
      } else {
        await api.put(`/recruitment/offerings/${dialog.row.id}`, payload);
        toast.success("Draft offering diperbarui.");
      }
      setDialog(null);
      onChanged?.();
    } catch (err) {
      setErrors({ __form__: errorMessage(err, "Offering tidak dapat disimpan.") });
    } finally {
      setSubmitting(false);
    }
  };

  const runSend = async () => {
    setBusy(true);
    try {
      await api.post(`/recruitment/offerings/${send.id}/send`);
      toast.success("Offering dikirim. Status kandidat menjadi Offering.");
      setSend(null);
      onChanged?.();
    } catch (err) {
      toast.error(errorMessage(err, "Offering tidak dapat dikirim."));
      setSend(null);
    } finally {
      setBusy(false);
    }
  };

  const runRespond = async () => {
    setBusy(true);
    setRespondError("");
    try {
      await api.post(`/recruitment/offerings/${respond.row.id}/respond`, {
        response: respond.response,
        response_notes: respondForm.response_notes || undefined,
        responded_at: respondForm.responded_at || undefined,
      });
      toast.success(
        respond.response === "accepted"
          ? "Offering diterima. Kandidat siap untuk onboarding (Tahap C)."
          : "Offering ditolak kandidat. Anda dapat membuat versi offering baru."
      );
      setRespond(null);
      onChanged?.();
    } catch (err) {
      setRespondError(errorMessage(err, "Respons tidak dapat disimpan."));
    } finally {
      setBusy(false);
    }
  };

  const runCancel = async () => {
    setBusy(true);
    try {
      await api.post(`/recruitment/offerings/${cancel.id}/cancel`, { reason: cancelReason || undefined });
      toast.success("Offering dibatalkan.");
      setCancel(null);
      setCancelReason("");
      onChanged?.();
    } catch (err) {
      toast.error(errorMessage(err, "Offering tidak dapat dibatalkan."));
      setCancel(null);
    } finally {
      setBusy(false);
    }
  };

  const OfferingCard = ({ row, highlight }) => (
    <div
      className={cn("overflow-hidden rounded-lg border bg-card", highlight ? "border-primary/40" : "border-border")}
      data-testid={`offering-card-${row.id}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-section-title">Offering v{row.version}</h3>
          <StageBadge stage={row.offer_status} label={row.offer_status_label} tone={row.offer_status_tone} testId={`offering-status-${row.id}`} />
          {highlight && <span className="text-[11px] text-muted-foreground">Aktif</span>}
        </div>
        {canEdit && (
          <div className="flex flex-wrap gap-1.5">
            {row.can_edit && (
              <Button size="sm" variant="outline" onClick={() => openEdit(row)} data-testid={`offering-edit-${row.id}`}>
                <Pencil className="mr-1.5 h-3.5 w-3.5" /> Ubah
              </Button>
            )}
            {row.can_send && (
              <Button size="sm" onClick={() => setSend(row)} data-testid={`offering-send-${row.id}`}>
                <Send className="mr-1.5 h-3.5 w-3.5" /> Kirim
              </Button>
            )}
            {row.can_respond && (
              <>
                <Button
                  size="sm"
                  onClick={() => {
                    setRespondForm({ responded_at: "", response_notes: "" });
                    setRespondError("");
                    setRespond({ row, response: "accepted" });
                  }}
                  data-testid={`offering-accept-${row.id}`}
                >
                  <ThumbsUp className="mr-1.5 h-3.5 w-3.5" /> Diterima
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="text-destructive hover:text-destructive"
                  onClick={() => {
                    setRespondForm({ responded_at: "", response_notes: "" });
                    setRespondError("");
                    setRespond({ row, response: "declined" });
                  }}
                  data-testid={`offering-decline-${row.id}`}
                >
                  <ThumbsDown className="mr-1.5 h-3.5 w-3.5" /> Ditolak
                </Button>
              </>
            )}
            {row.can_cancel && (
              <Button
                size="sm"
                variant="ghost"
                className="text-destructive hover:text-destructive"
                onClick={() => {
                  setCancelReason("");
                  setCancel(row);
                }}
                data-testid={`offering-cancel-${row.id}`}
              >
                <Ban className="mr-1.5 h-3.5 w-3.5" /> Batalkan
              </Button>
            )}
          </div>
        )}
      </div>
      <div className="grid grid-cols-1 gap-x-6 px-4 py-2 lg:grid-cols-2">
        <div>
          <InfoRow label="Jabatan" value={row.position_name} testId={`offering-position-${row.id}`} />
          <InfoRow label="Departemen" value={row.department_name} />
          <InfoRow label="Lokasi Kerja" value={row.work_location_name} />
          <InfoRow label="Proyek" value={row.project_name} />
          <InfoRow label="Status Kepegawaian" value={row.employment_status_name} />
        </div>
        <div>
          <InfoRow label="Tanggal Mulai Kerja" value={row.start_date ? formatDate(row.start_date) : null} />
          <InfoRow label="Gaji Pokok" value={row.basic_salary ? formatCurrency(row.basic_salary) : null} testId={`offering-salary-${row.id}`} />
          <InfoRow
            label="Tunjangan"
            value={
              (row.allowances || []).length ? (
                <ul className="space-y-0.5">
                  {row.allowances.map((a, i) => (
                    <li key={`${a.name}-${i}`} className="flex justify-between gap-3">
                      <span>{a.name}</span>
                      <span data-numeric="true">{formatCurrency(a.amount)}</span>
                    </li>
                  ))}
                  <li className="flex justify-between gap-3 border-t border-border/60 pt-0.5 font-medium">
                    <span>Total Tunjangan</span>
                    <span data-numeric="true">{formatCurrency(row.total_allowances)}</span>
                  </li>
                </ul>
              ) : null
            }
          />
          <InfoRow
            label="Masa Percobaan"
            value={row.probation_months !== null && row.probation_months !== undefined ? `${row.probation_months} bulan` : null}
          />
          <InfoRow label="Catatan" value={row.notes} />
        </div>
      </div>
      <div className="border-t border-border px-4 py-2 text-[11px] text-muted-foreground">
        Dibuat {formatDateTime(row.created_at)}
        {row.offered_at ? ` · Dikirim ${formatDateTime(row.offered_at)}` : ""}
        {row.responded_at ? ` · Respons ${formatDateTime(row.responded_at)}${row.response_date ? ` (tgl. ${formatDate(row.response_date)})` : ""}` : ""}
        {row.response_notes ? ` · ${row.response_notes}` : ""}
        {row.cancelled_at ? ` · Dibatalkan ${formatDateTime(row.cancelled_at)}${row.cancel_reason ? ` (${row.cancel_reason})` : ""}` : ""}
      </div>
    </div>
  );

  return (
    <div className="space-y-3" data-testid="offering-tab">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          Offering dibuat setelah kandidat disetujui. Nilai gaji di sini hanya untuk penawaran — tidak ditulis ke Payroll.
        </p>
        {can("recruitment", "create") && canCreate && (
          <Button onClick={openCreate} data-testid="offering-create-button">
            <Plus className="mr-2 h-4 w-4" /> Buat Offering
          </Button>
        )}
      </div>

      {!canCreate && !active && offerings?.create_blockers?.length > 0 && candidate.stage_status !== "offering_accepted" && (
        <div className="rounded-lg border border-border bg-muted/40 px-4 py-2.5 text-[12px] text-muted-foreground" data-testid="offering-blockers">
          {offerings.create_blockers.join(" ")}
        </div>
      )}

      {candidate.stage_status === "offering_accepted" && (
        <div className="flex items-start gap-3 rounded-lg border border-success-border bg-success-soft px-4 py-3" data-testid="offering-accepted-banner">
          <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-success" />
          <div>
            <p className="text-sm font-semibold text-foreground">Offering diterima — kandidat siap onboarding.</p>
            <p className="text-[12px] text-muted-foreground">Konversi menjadi karyawan tersedia pada Tahap C. Belum ada data karyawan yang dibuat.</p>
          </div>
        </div>
      )}

      {active ? (
        <OfferingCard row={active} highlight />
      ) : items.length === 0 ? (
        <div className="rounded-lg border border-border bg-card" data-testid="offering-empty">
          <EmptyState
            icon={FileSignature}
            title="Belum ada offering."
            description={
              offerings?.create_blockers?.length
                ? offerings.create_blockers.join(" ")
                : "Buat draft offering, lengkapi gaji dan tanggal mulai, lalu kirim ke kandidat."
            }
            actionLabel={can("recruitment", "create") && canCreate ? "Buat Offering" : undefined}
            onAction={openCreate}
          />
        </div>
      ) : null}

      {history.length > 0 && (
        <div className="space-y-2" data-testid="offering-history">
          <h3 className="text-[12px] font-semibold uppercase tracking-wide text-muted-foreground">Riwayat Offering</h3>
          {history.map((row) => (
            <OfferingCard key={row.id} row={row} />
          ))}
        </div>
      )}

      {/* Dialog buat / ubah */}
      <Dialog open={!!dialog} onOpenChange={(v) => !v && setDialog(null)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto bg-card sm:max-w-2xl" data-testid="offering-form-dialog">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">{dialog?.mode === "create" ? "Buat Draft Offering" : `Ubah Offering v${dialog?.row?.version}`}</DialogTitle>
            <DialogDescription className="leading-relaxed">
              Posisi diambil dari data lamaran kandidat dan dapat diubah. Offering tersimpan sebagai draft sampai dikirim.
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
            className="space-y-4"
          >
            <div className="grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2">
              {fields.map((f) => (
                <Field key={f.name} field={f} value={values[f.name]} error={errors[f.name]} onChange={(n, v) => setValues((p) => ({ ...p, [n]: v }))} />
              ))}
            </div>

            <div className="space-y-2 rounded-lg border border-border p-3">
              <div className="flex items-center justify-between">
                <Label className="text-[13px] font-medium">Tunjangan</Label>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setAllowances((p) => [...p, { name: "", amount: "" }])}
                  data-testid="offering-add-allowance"
                >
                  <Plus className="mr-1.5 h-3.5 w-3.5" /> Tambah
                </Button>
              </div>
              {allowances.length === 0 && <p className="text-[12px] text-muted-foreground">Belum ada tunjangan. Opsional.</p>}
              {allowances.map((a, idx) => (
                <div key={idx} className="space-y-1">
                  <div className="grid grid-cols-[1fr,10rem,2.25rem] gap-2">
                    <Input
                      placeholder="Nama tunjangan (mis. Transport)"
                      value={a.name}
                      onChange={(e) => setAllowances((p) => p.map((x, i) => (i === idx ? { ...x, name: e.target.value } : x)))}
                      data-testid={`offering-allowance-name-${idx}`}
                    />
                    <Input
                      type="number"
                      placeholder="Nominal"
                      value={a.amount}
                      onChange={(e) => setAllowances((p) => p.map((x, i) => (i === idx ? { ...x, amount: e.target.value } : x)))}
                      data-testid={`offering-allowance-amount-${idx}`}
                    />
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="h-9 w-9 text-destructive"
                      onClick={() => setAllowances((p) => p.filter((_x, i) => i !== idx))}
                      data-testid={`offering-allowance-remove-${idx}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                  {errors[`allowance_${idx}`] && <p className="text-xs font-medium text-destructive">{errors[`allowance_${idx}`]}</p>}
                </div>
              ))}
            </div>

            {errors.__form__ && (
              <div className="rounded-md border border-danger-border bg-danger-soft px-3 py-2 text-[13px] text-danger" data-testid="offering-form-error">
                {errors.__form__}
              </div>
            )}
            <DialogFooter className="gap-2">
              <Button type="button" variant="outline" onClick={() => setDialog(null)} disabled={submitting} data-testid="offering-form-cancel">
                Batal
              </Button>
              <Button type="submit" disabled={submitting} data-testid="offering-form-submit">
                {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {dialog?.mode === "create" ? "Simpan Draft" : "Simpan"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Dialog respons */}
      <Dialog open={!!respond} onOpenChange={(v) => !v && setRespond(null)}>
        <DialogContent className="bg-card sm:max-w-md" data-testid="offering-respond-dialog">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">
              {respond?.response === "accepted" ? "Catat offering diterima?" : "Catat offering ditolak?"}
            </DialogTitle>
            <DialogDescription className="leading-relaxed">
              Offering v{respond?.row?.version} · {candidate.full_name}.{" "}
              {respond?.response === "accepted"
                ? "Kandidat menjadi Offering Diterima dan siap onboarding. Belum membuat data karyawan."
                : "Kandidat menjadi Offering Ditolak; slot offering aktif dilepas sehingga versi baru dapat dibuat."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="offering-responded-at">Tanggal respons kandidat</Label>
              <Input
                id="offering-responded-at"
                type="date"
                value={respondForm.responded_at}
                onChange={(e) => setRespondForm((p) => ({ ...p, responded_at: e.target.value }))}
                data-testid="offering-respond-date"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="offering-response-notes">Catatan {respond?.response === "declined" ? "/ alasan penolakan" : ""}</Label>
              <Textarea
                id="offering-response-notes"
                rows={3}
                value={respondForm.response_notes}
                onChange={(e) => setRespondForm((p) => ({ ...p, response_notes: e.target.value }))}
                data-testid="offering-respond-notes"
              />
            </div>
            {respondError && (
              <div className="rounded-lg border border-danger-border bg-danger-soft px-3 py-2 text-sm text-destructive" data-testid="offering-respond-error">
                {respondError}
              </div>
            )}
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setRespond(null)} disabled={busy} data-testid="offering-respond-cancel">
              Batal
            </Button>
            <Button onClick={runRespond} disabled={busy} variant={respond?.response === "declined" ? "destructive" : "default"} data-testid="offering-respond-confirm">
              {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {respond?.response === "accepted" ? "Catat Diterima" : "Catat Ditolak"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog batalkan */}
      <Dialog open={!!cancel} onOpenChange={(v) => !v && setCancel(null)}>
        <DialogContent className="bg-card sm:max-w-md" data-testid="offering-cancel-dialog">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">Batalkan offering v{cancel?.version}?</DialogTitle>
            <DialogDescription className="leading-relaxed">
              {cancel?.offer_status === "sent"
                ? "Offering yang sudah terkirim dibatalkan; kandidat kembali ke status Disetujui."
                : "Draft offering dibatalkan dan tercatat di riwayat offering."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="offering-cancel-reason">Alasan</Label>
            <Textarea id="offering-cancel-reason" rows={3} value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} data-testid="offering-cancel-reason" />
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setCancel(null)} disabled={busy} data-testid="offering-cancel-dismiss">
              Batal
            </Button>
            <Button variant="destructive" onClick={runCancel} disabled={busy} data-testid="offering-cancel-confirm">
              {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Batalkan Offering
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!send}
        onOpenChange={(v) => !v && setSend(null)}
        title={`Kirim offering v${send?.version} ke kandidat?`}
        description={`${candidate.full_name} akan berstatus Offering. Pastikan gaji pokok dan tanggal mulai kerja sudah benar; setelah dikirim, draft tidak dapat diubah.`}
        confirmLabel="Kirim Offering"
        loading={busy}
        onConfirm={runSend}
      />
    </div>
  );
};

export default OfferingTab;
