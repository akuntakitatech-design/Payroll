import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, BadgeCheck, ExternalLink, Loader2, UserRoundPlus } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatCurrency, formatDate, formatDateTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const SOURCE_LABEL = { kandidat: "dari kandidat", offering: "dari offering", lamaran: "dari lamaran", pelengkap: "diisi HR" };

const MappingCard = ({ title, rows, testId }) => (
  <div className="overflow-hidden rounded-lg border border-border bg-card" data-testid={testId}>
    <div className="border-b border-border px-3 py-2">
      <h3 className="text-[12px] font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
    </div>
    <div className="px-3 py-1">
      {rows.map((r) => (
        <div key={r.key} className="grid grid-cols-[9rem,1fr] gap-3 border-b border-border/60 py-1.5 last:border-0">
          <span className="text-[12px] text-muted-foreground">{r.label}</span>
          <span className="text-[13px]" data-testid={`convert-map-${r.key}`}>
            {r.value === null || r.value === undefined || r.value === "" ? (
              <span className="text-muted-foreground">-</span>
            ) : (
              <>
                {r.key === "join_date" || r.key === "birth_date" ? formatDate(r.value) : r.value}
                {r.source && <span className="ml-1.5 text-[11px] text-muted-foreground">({SOURCE_LABEL[r.source] || r.source})</span>}
              </>
            )}
          </span>
        </div>
      ))}
    </div>
  </div>
);

const FILL_FIELDS = {
  nik: { label: "NIK (KTP)", type: "text", placeholder: "16 digit" },
  join_date: { label: "Tanggal mulai kerja", type: "date" },
  employment_status_id: { label: "Status kepegawaian", type: "select" },
  gender: { label: "Jenis kelamin", type: "select" },
  birth_date: { label: "Tanggal lahir", type: "date" },
  phone: { label: "No. HP", type: "text" },
  email: { label: "Email", type: "email" },
};

/**
 * Dialog Preview Data Karyawan -> konversi kandidat menjadi karyawan.
 * Data yang sudah ada tidak diketik ulang; hanya field wajib yang kurang (dan
 * beberapa rekomendasi) yang dapat dilengkapi.
 */
export const ConvertEmployeeDialog = ({ open, onOpenChange, candidate, catalog, onConverted }) => {
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [fill, setFill] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [conflict, setConflict] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    setConflict(null);
    try {
      const res = await api.get(`/recruitment/candidates/${candidate.id}/convert-preview`);
      setPreview(res.data);
      setFill({});
    } catch (err) {
      setError(errorMessage(err, "Preview data karyawan tidak dapat dimuat."));
    } finally {
      setLoading(false);
    }
  }, [candidate.id]);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  const missingKeys = (preview?.required_missing || []).map((m) => m.key);
  const warningKeys = (preview?.warnings || []).map((w) => w.key).filter((k) => FILL_FIELDS[k]);
  const fillKeys = [...missingKeys, ...warningKeys.filter((k) => !missingKeys.includes(k))];

  const submit = async () => {
    const stillMissing = missingKeys.filter((k) => !fill[k]);
    if (stillMissing.length) {
      setError(`Lengkapi dahulu: ${stillMissing.map((k) => FILL_FIELDS[k]?.label || k).join(", ")}.`);
      return;
    }
    setSubmitting(true);
    setError("");
    setConflict(null);
    try {
      const body = {};
      Object.entries(fill).forEach(([k, v]) => {
        if (v !== "" && v !== null && v !== undefined) body[k] = v;
      });
      const res = await api.post(`/recruitment/candidates/${candidate.id}/convert`, body);
      toast.success(res.data.message);
      onOpenChange(false);
      onConverted?.(res.data);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      if (detail && typeof detail === "object" && detail.message) {
        setError(detail.message);
        setConflict(detail.existing_employee || null);
      } else {
        setError(errorMessage(err, "Konversi tidak dapat dilakukan."));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const blockers = preview?.blockers || [];
  const canConvert = preview?.can_convert && !loading;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto bg-card sm:max-w-3xl" data-testid="convert-dialog">
        <DialogHeader>
          <DialogTitle className="text-base font-semibold">Preview Data Karyawan</DialogTitle>
          <DialogDescription className="leading-relaxed">
            Data kandidat dan offering yang diterima akan menjadi Data Karyawan baru. Nomor karyawan dibuat otomatis oleh
            mekanisme penomoran existing. Gaji pada offering <strong>tidak</strong> disalin ke Payroll.
          </DialogDescription>
        </DialogHeader>

        {loading && !preview ? (
          <div className="space-y-3" data-testid="convert-loading">
            <Skeleton className="h-28 w-full" />
            <Skeleton className="h-28 w-full" />
          </div>
        ) : preview ? (
          <div className="space-y-3">
            {blockers.length > 0 && (
              <div className="flex items-start gap-2 rounded-lg border border-danger-border bg-danger-soft px-3 py-2 text-[13px] text-destructive" data-testid="convert-blockers">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <ul className="space-y-0.5">
                  {blockers.map((b, i) => (
                    <li key={i}>{b}</li>
                  ))}
                </ul>
              </div>
            )}
            {preview.nik_conflict && (
              <div className="rounded-lg border border-warning-border bg-warning-soft px-3 py-2 text-[13px]" data-testid="convert-nik-conflict">
                NIK sudah dipakai karyawan
                {preview.nik_conflict.employee_number ? (
                  <>
                    {" "}
                    <strong>{preview.nik_conflict.employee_number} · {preview.nik_conflict.full_name}</strong>.
                  </>
                ) : (
                  " lain (Anda tidak berhak melihat detailnya)."
                )}{" "}
                Karyawan existing tidak diubah otomatis.
              </div>
            )}

            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              <MappingCard title="Identitas" rows={preview.mapping.identity} testId="convert-map-identity" />
              <div className="space-y-3">
                <MappingCard title="Pekerjaan (dari Offering)" rows={preview.mapping.job} testId="convert-map-job" />
                <MappingCard title="Pendidikan" rows={preview.mapping.education} testId="convert-map-education" />
              </div>
            </div>

            {preview.offering && (
              <p className="text-[12px] text-muted-foreground" data-testid="convert-salary-note">
                Offering v{preview.offering.version}: gaji pokok {formatCurrency(preview.offering.basic_salary)}
                {preview.offering.total_allowances ? ` + tunjangan ${formatCurrency(preview.offering.total_allowances)}` : ""}. {preview.salary_note}
              </p>
            )}

            {fillKeys.length > 0 && !preview.is_hired && (
              <div className="space-y-3 rounded-lg border border-border p-3" data-testid="convert-fill-section">
                <div>
                  <p className="text-[13px] font-semibold">Lengkapi data</p>
                  <p className="text-[12px] text-muted-foreground">
                    {missingKeys.length ? "Field bertanda * wajib sebelum konversi. " : ""}
                    Field lain opsional dan dapat dilengkapi nanti di Data Karyawan.
                  </p>
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {fillKeys.map((k) => {
                    const f = FILL_FIELDS[k] || { label: k, type: "text" };
                    const required = missingKeys.includes(k);
                    const id = `convert-fill-${k}`;
                    let control;
                    if (f.type === "select") {
                      const options =
                        k === "employment_status_id"
                          ? (catalog?.employment_statuses || []).map((s) => ({ value: s.id, label: s.name }))
                          : (catalog?.genders || []).map((g) => ({ value: g.key, label: g.label }));
                      control = (
                        <Select value={fill[k] || ""} onValueChange={(v) => setFill((p) => ({ ...p, [k]: v }))}>
                          <SelectTrigger id={id} data-testid={id}>
                            <SelectValue placeholder="Pilih…" />
                          </SelectTrigger>
                          <SelectContent>
                            {options.map((o) => (
                              <SelectItem key={o.value} value={o.value}>
                                {o.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      );
                    } else {
                      control = (
                        <Input
                          id={id}
                          type={f.type}
                          placeholder={f.placeholder}
                          value={fill[k] || ""}
                          onChange={(e) => setFill((p) => ({ ...p, [k]: e.target.value }))}
                          data-testid={id}
                        />
                      );
                    }
                    return (
                      <div key={k} className="space-y-1.5">
                        <Label htmlFor={id} className="text-[13px]">
                          {f.label} {required && <span className="text-destructive">*</span>}
                        </Label>
                        {control}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {error && (
              <div className="rounded-lg border border-danger-border bg-danger-soft px-3 py-2 text-sm text-destructive" data-testid="convert-error">
                {error}
                {conflict?.id && (
                  <div className="mt-1">
                    Karyawan existing: <strong>{conflict.employee_number} · {conflict.full_name}</strong>
                  </div>
                )}
              </div>
            )}
          </div>
        ) : error ? (
          <div className="rounded-lg border border-danger-border bg-danger-soft px-3 py-2 text-sm text-destructive" data-testid="convert-error">
            {error}
          </div>
        ) : null}

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting} data-testid="convert-cancel">
            Batal
          </Button>
          <Button onClick={submit} disabled={!canConvert || submitting} data-testid="convert-confirm">
            {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <UserRoundPlus className="mr-2 h-4 w-4" />}
            Jadikan Karyawan
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

/** Panel ringkas setelah kandidat menjadi karyawan. */
export const HiredPanel = ({ conversion, loading = false }) => {
  const navigate = useNavigate();
  const { can } = useAuth();
  const emp = conversion?.employee;
  if (loading || !conversion?.is_hired) {
    return <Skeleton className="h-16 w-full" data-testid="hired-panel-loading" />;
  }
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-success-border bg-success-soft px-4 py-3 sm:flex-row sm:items-center sm:justify-between" data-testid="hired-panel">
      <div className="flex items-start gap-3">
        <BadgeCheck className="mt-0.5 h-5 w-5 shrink-0 text-success" />
        <div>
          <p className="text-sm font-semibold text-foreground">Sudah menjadi Karyawan</p>
          <p className="text-[12px] text-muted-foreground">
            {emp ? (
              <>
                <span data-testid="hired-employee-number">{emp.employee_number}</span> · <span data-testid="hired-employee-name">{emp.full_name}</span>
              </>
            ) : (
              "Data karyawan belum tertaut (hubungi administrator)."
            )}
            {conversion?.converted_at ? ` · dikonversi ${formatDateTime(conversion.converted_at)}` : ""}
            {conversion?.converted_by_name ? ` oleh ${conversion.converted_by_name}` : ""}
          </p>
          <p className="text-[11px] text-muted-foreground">Data inti kandidat kini read-only. Riwayat seleksi tetap dapat dilihat.</p>
        </div>
      </div>
      {emp && can("employee", "view") && (
        <Button variant="outline" onClick={() => navigate(conversion.employee_route || `/employees/${emp.id}`)} data-testid="hired-open-employee">
          <ExternalLink className="mr-2 h-4 w-4" /> Buka Data Karyawan
        </Button>
      )}
    </div>
  );
};

export default ConvertEmployeeDialog;
