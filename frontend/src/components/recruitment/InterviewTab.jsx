import React, { useMemo, useState } from "react";
import {
  CalendarClock,
  CheckCircle2,
  Loader2,
  MapPin,
  Pencil,
  Plus,
  Video,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import FormDialog from "@/components/common/FormDialog";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import EmptyState from "@/components/common/EmptyState";
import StageBadge from "@/components/recruitment/StageBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const emptyForm = () => ({
  interview_type: "hr",
  interview_type_label: "",
  scheduled_date: "",
  start_time: "",
  end_time: "",
  interviewer_user_id: "",
  interview_mode: "onsite",
  location: "",
  meeting_link: "",
  notes: "",
});

/**
 * Tab Interview: timeline seluruh interview kandidat + jadwalkan / reschedule /
 * batalkan / selesaikan. Keputusan stage kandidat sepenuhnya di backend.
 */
export const InterviewTab = ({ candidate, interviews, interviewers, catalog, canSchedule, onChanged }) => {
  const { can } = useAuth();
  const [dialog, setDialog] = useState(null); // {mode:'create'|'edit', row}
  const [values, setValues] = useState(emptyForm());
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [complete, setComplete] = useState(null); // row
  const [completeForm, setCompleteForm] = useState({ result: "", score: "", recommendation: "", interviewer_notes: "" });
  const [completeError, setCompleteError] = useState("");
  const [cancel, setCancel] = useState(null); // row
  const [cancelLoading, setCancelLoading] = useState(false);

  const interviewerOptions = (interviewers || []).map((u) => ({
    value: u.id,
    label: `${u.full_name}${u.job_title ? ` · ${u.job_title}` : ""}`,
  }));

  const fields = useMemo(
    () => [
      {
        name: "interview_type",
        label: "Jenis Interview",
        type: "select",
        required: true,
        options: (catalog?.interview_types || []).map((t) => ({ value: t.key, label: t.label })),
      },
      ...(values.interview_type === "other"
        ? [{ name: "interview_type_label", label: "Nama Jenis Interview", required: true, placeholder: "Mis. Psikotes" }]
        : []),
      { name: "interviewer_user_id", label: "Interviewer", type: "select", required: true, options: interviewerOptions },
      { name: "scheduled_date", label: "Tanggal", type: "date", required: true },
      {
        name: "interview_mode",
        label: "Metode",
        type: "select",
        required: true,
        options: (catalog?.interview_modes || []).map((m) => ({ value: m.key, label: m.label })),
      },
      { name: "start_time", label: "Jam Mulai", placeholder: "09:00" },
      { name: "end_time", label: "Jam Selesai", placeholder: "10:00" },
      ...(values.interview_mode === "online"
        ? [{ name: "meeting_link", label: "Tautan Meeting", placeholder: "https://…", colSpan: 2 }]
        : [{ name: "location", label: "Lokasi", placeholder: "Ruang rapat / alamat", colSpan: 2 }]),
      { name: "notes", label: "Catatan Jadwal", type: "textarea", colSpan: 2 },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [catalog, interviewers, values.interview_type, values.interview_mode]
  );

  const openCreate = () => {
    setValues({ ...emptyForm(), interviewer_user_id: interviewerOptions[0]?.value || "" });
    setErrors({});
    setDialog({ mode: "create" });
  };
  const openEdit = (row) => {
    const v = emptyForm();
    Object.keys(v).forEach((k) => {
      v[k] = row[k] ?? "";
    });
    setValues(v);
    setErrors({});
    setDialog({ mode: "edit", row });
  };

  const submit = async () => {
    const errs = {};
    if (!values.interviewer_user_id) errs.interviewer_user_id = "Interviewer wajib dipilih.";
    if (!values.scheduled_date) errs.scheduled_date = "Tanggal interview wajib diisi.";
    if (values.interview_type === "other" && !values.interview_type_label?.trim()) errs.interview_type_label = "Isi nama jenis interview.";
    if (Object.keys(errs).length) return setErrors(errs);
    setSubmitting(true);
    setErrors({});
    try {
      const payload = {};
      Object.entries(values).forEach(([k, v]) => {
        if (v !== "" && v !== null && v !== undefined) payload[k] = v;
      });
      if (dialog.mode === "create") {
        await api.post(`/recruitment/candidates/${candidate.id}/interviews`, payload);
        toast.success("Interview dijadwalkan.");
      } else {
        await api.put(`/recruitment/interviews/${dialog.row.id}`, payload);
        toast.success("Jadwal interview diperbarui.");
      }
      setDialog(null);
      onChanged?.();
    } catch (err) {
      setErrors({ __form__: errorMessage(err, "Interview tidak dapat disimpan.") });
    } finally {
      setSubmitting(false);
    }
    return undefined;
  };

  const submitComplete = async () => {
    setCompleteError("");
    if (!completeForm.result) return setCompleteError("Pilih hasil interview.");
    if (completeForm.score !== "" && (Number(completeForm.score) < 0 || Number(completeForm.score) > 100)) {
      return setCompleteError("Skor harus 0–100.");
    }
    setSubmitting(true);
    try {
      const payload = { result: completeForm.result };
      if (completeForm.score !== "") payload.score = Number(completeForm.score);
      if (completeForm.recommendation) payload.recommendation = completeForm.recommendation;
      if (completeForm.interviewer_notes.trim()) payload.interviewer_notes = completeForm.interviewer_notes.trim();
      await api.post(`/recruitment/interviews/${complete.id}/complete`, payload);
      toast.success("Interview diselesaikan.");
      setComplete(null);
      onChanged?.();
    } catch (err) {
      setCompleteError(errorMessage(err, "Hasil interview tidak dapat disimpan."));
    } finally {
      setSubmitting(false);
    }
    return undefined;
  };

  const runCancel = async () => {
    setCancelLoading(true);
    try {
      await api.post(`/recruitment/interviews/${cancel.id}/cancel`, { reason: cancel.reason || undefined });
      toast.success("Interview dibatalkan.");
      setCancel(null);
      onChanged?.();
    } catch (err) {
      toast.error(errorMessage(err, "Interview tidak dapat dibatalkan."));
      setCancel(null);
    } finally {
      setCancelLoading(false);
    }
  };

  const canEdit = can("recruitment", "edit");
  const scheduledCount = interviews.filter((i) => i.interview_status === "scheduled").length;
  const completedCount = interviews.filter((i) => i.interview_status === "completed").length;

  return (
    <div className="space-y-3" data-testid="interview-tab">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground" data-testid="interview-summary">
          {interviews.length === 0
            ? "Belum ada interview. Kandidat berpindah ke tahap Interview saat jadwal pertama dibuat."
            : `${completedCount} selesai · ${scheduledCount} terjadwal · ${interviews.length - completedCount - scheduledCount} dibatalkan. Approval baru dapat diajukan bila tidak ada interview terjadwal.`}
        </p>
        {canSchedule && (
          <Button onClick={openCreate} data-testid="interview-add-button">
            <Plus className="mr-2 h-4 w-4" /> Jadwalkan Interview
          </Button>
        )}
      </div>

      <div className="rounded-lg border border-border bg-card">
        {interviews.length === 0 ? (
          <EmptyState
            icon={CalendarClock}
            title="Belum ada interview."
            description={
              canSchedule
                ? "Jadwalkan Interview HR, User, Manager, atau Final. Satu kandidat boleh memiliki lebih dari satu interview."
                : `Interview hanya dapat dijadwalkan setelah kandidat lolos screening (status saat ini: ${candidate.stage_label}).`
            }
            actionLabel={canSchedule ? "Jadwalkan Interview" : undefined}
            onAction={openCreate}
          />
        ) : (
          <ol className="divide-y divide-border" data-testid="interview-list">
            {interviews.map((iv, idx) => (
              <li key={iv.id} className="flex gap-3 px-4 py-3" data-testid={`interview-item-${iv.id}`}>
                <div className="flex flex-col items-center">
                  <span
                    className={cn(
                      "flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-xs font-semibold",
                      iv.interview_status === "completed"
                        ? "border-success-border bg-success-soft text-success"
                        : iv.interview_status === "cancelled"
                        ? "border-border bg-muted text-muted-foreground line-through"
                        : "border-primary-border bg-primary-soft text-primary"
                    )}
                  >
                    {iv.sequence || idx + 1}
                  </span>
                  {idx < interviews.length - 1 && <span className="mt-1 w-px flex-1 bg-border" />}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-[13px] font-semibold">{iv.interview_type_label}</p>
                    <StageBadge stage={iv.interview_status} label={iv.interview_status_label} tone={iv.interview_status_tone} testId={`interview-status-${iv.id}`} />
                    {iv.result && (
                      <StageBadge stage={iv.result} label={`Hasil: ${iv.result_label}`} tone={iv.result_tone} testId={`interview-result-${iv.id}`} />
                    )}
                  </div>
                  <p className="mt-0.5 text-[12px] text-muted-foreground">
                    {formatDate(iv.scheduled_date)}
                    {iv.start_time ? ` · ${iv.start_time}${iv.end_time ? `–${iv.end_time}` : ""}` : ""}
                    {" · "}
                    {iv.interviewer_name}
                    {iv.interviewer_title ? ` (${iv.interviewer_title})` : ""}
                  </p>
                  <p className="mt-0.5 flex items-center gap-1 text-[12px] text-muted-foreground">
                    {iv.interview_mode === "online" ? <Video className="h-3.5 w-3.5" /> : <MapPin className="h-3.5 w-3.5" />}
                    {iv.interview_mode === "online"
                      ? iv.meeting_link
                        ? (
                          <a href={iv.meeting_link} target="_blank" rel="noreferrer" className="truncate text-primary underline-offset-2 hover:underline">
                            {iv.meeting_link}
                          </a>
                        )
                        : "Online"
                      : iv.location || "Tatap muka"}
                  </p>
                  {iv.interview_status === "completed" && (
                    <div className="mt-2 rounded-md border border-border bg-muted/40 px-3 py-2 text-[12px]">
                      <p>
                        <span className="text-muted-foreground">Skor:</span> {iv.score ?? "-"}
                        {" · "}
                        <span className="text-muted-foreground">Rekomendasi:</span> {iv.recommendation_label || "-"}
                        {" · "}
                        <span className="text-muted-foreground">Selesai:</span> {formatDateTime(iv.completed_at)}
                      </p>
                      {iv.interviewer_notes && <p className="mt-1 whitespace-pre-wrap">{iv.interviewer_notes}</p>}
                    </div>
                  )}
                  {iv.interview_status === "cancelled" && iv.cancel_reason && (
                    <p className="mt-1 text-[12px] text-muted-foreground">Alasan: {iv.cancel_reason}</p>
                  )}
                  {iv.notes && iv.interview_status !== "completed" && (
                    <p className="mt-1 text-[12px] text-muted-foreground">{iv.notes}</p>
                  )}
                </div>
                {canEdit && iv.interview_status === "scheduled" && (
                  <div className="flex shrink-0 flex-col gap-1.5 sm:flex-row">
                    <Button
                      size="sm"
                      onClick={() => {
                        setCompleteForm({ result: "", score: "", recommendation: "", interviewer_notes: "" });
                        setCompleteError("");
                        setComplete(iv);
                      }}
                      data-testid={`interview-complete-${iv.id}`}
                    >
                      <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" /> Selesaikan
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => openEdit(iv)} data-testid={`interview-edit-${iv.id}`}>
                      <Pencil className="mr-1.5 h-3.5 w-3.5" /> Reschedule
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      onClick={() => setCancel({ ...iv, reason: "" })}
                      data-testid={`interview-cancel-${iv.id}`}
                    >
                      <XCircle className="mr-1.5 h-3.5 w-3.5" /> Batalkan
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ol>
        )}
      </div>

      <FormDialog
        open={!!dialog}
        onOpenChange={(v) => !v && setDialog(null)}
        title={dialog?.mode === "edit" ? "Ubah / Reschedule Interview" : "Jadwalkan Interview"}
        description="Interviewer diambil dari pengguna perusahaan aktif. Kandidat otomatis berstatus Interview Dijadwalkan."
        fields={fields}
        values={values}
        errors={errors}
        onChange={(name, value) => setValues((p) => ({ ...p, [name]: value }))}
        onSubmit={submit}
        submitting={submitting}
        submitLabel={dialog?.mode === "edit" ? "Simpan Perubahan" : "Jadwalkan"}
      />

      <Dialog open={!!complete} onOpenChange={(v) => !v && setComplete(null)}>
        <DialogContent className="bg-card sm:max-w-lg" data-testid="interview-complete-dialog">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">Selesaikan Interview</DialogTitle>
            <DialogDescription className="leading-relaxed">
              {complete?.interview_type_label} · {complete?.interviewer_name}. Hasil tersimpan permanen dan tidak dapat diubah.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>
                Hasil <span className="text-destructive">*</span>
              </Label>
              <div className="grid grid-cols-3 gap-2">
                {(catalog?.interview_results || []).map((r) => (
                  <button
                    key={r.key}
                    type="button"
                    onClick={() => setCompleteForm((p) => ({ ...p, result: r.key }))}
                    aria-pressed={completeForm.result === r.key}
                    data-testid={`interview-result-${r.key}`}
                    className={cn(
                      "rounded-lg border px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      completeForm.result === r.key
                        ? r.tone === "success"
                          ? "border-success-border bg-success-soft text-success"
                          : r.tone === "danger"
                          ? "border-danger-border bg-danger-soft text-danger"
                          : "border-warning-border bg-warning-soft text-warning"
                        : "border-border bg-background hover:bg-muted/60"
                    )}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="iv-score">Skor (0–100)</Label>
                <Input id="iv-score" type="number" min={0} max={100} value={completeForm.score} onChange={(e) => setCompleteForm((p) => ({ ...p, score: e.target.value }))} data-testid="interview-score" />
              </div>
              <div className="space-y-1.5">
                <Label>Rekomendasi</Label>
                <Select value={completeForm.recommendation || "__empty__"} onValueChange={(v) => setCompleteForm((p) => ({ ...p, recommendation: v === "__empty__" ? "" : v }))}>
                  <SelectTrigger data-testid="interview-recommendation">
                    <SelectValue placeholder="Pilih…" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__empty__">— Tidak diisi —</SelectItem>
                    {(catalog?.interview_recommendations || []).map((r) => (
                      <SelectItem key={r.key} value={r.key}>{r.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="iv-notes">Catatan Interviewer</Label>
              <Textarea id="iv-notes" rows={4} value={completeForm.interviewer_notes} onChange={(e) => setCompleteForm((p) => ({ ...p, interviewer_notes: e.target.value }))} data-testid="interview-notes" />
            </div>
            {completeError && (
              <div className="rounded-lg border border-danger-border bg-danger-soft px-3 py-2 text-sm text-destructive" data-testid="interview-complete-error">
                {completeError}
              </div>
            )}
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setComplete(null)} disabled={submitting} data-testid="interview-complete-cancel">Batal</Button>
            <Button onClick={submitComplete} disabled={submitting} data-testid="interview-complete-submit">
              {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Simpan Hasil
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!cancel}
        onOpenChange={(v) => !v && setCancel(null)}
        title="Batalkan interview ini?"
        description={`${cancel?.interview_type_label || "Interview"} pada ${cancel?.scheduled_date ? formatDate(cancel.scheduled_date) : "-"} akan ditandai Dibatalkan. Status kandidat dihitung ulang dari interview yang tersisa.`}
        destructive
        confirmLabel="Batalkan Interview"
        loading={cancelLoading}
        onConfirm={runCancel}
      />
    </div>
  );
};

export default InterviewTab;
