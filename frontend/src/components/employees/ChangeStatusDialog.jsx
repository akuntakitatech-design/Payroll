import React, { useEffect, useMemo, useState } from "react";
import { ArrowRight, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { CATEGORY_LABELS, todayISO } from "@/lib/employeeStatus";
import { formatDate } from "@/lib/format";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import { EmployeeStatusBadge } from "@/components/employees/EmployeeStatusBadge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

const EMPTY = { new_status_id: "", effective_date: "", reason: "", notes: "" };

/**
 * Modal Ubah Status Karyawan (Upgrade 01B).
 * employee: { id, full_name, current_employee_status_id, current_employee_status_name,
 *             current_employee_status_category }
 */
export const ChangeStatusDialog = ({ open, onOpenChange, employee, onChanged }) => {
  const [statuses, setStatuses] = useState([]);
  const [loadingOptions, setLoadingOptions] = useState(false);
  const [values, setValues] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const today = todayISO();

  useEffect(() => {
    if (!open) return;
    setValues({ ...EMPTY, effective_date: today });
    setErrors({});
    setLoadingOptions(true);
    api
      .get("/employee-statuses", { params: { active: true } })
      .then((res) => setStatuses(res.data.items || []))
      .catch((err) => toast.error(errorMessage(err, "Gagal memuat daftar status.")))
      .finally(() => setLoadingOptions(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const options = useMemo(
    () => statuses.filter((s) => s.id !== employee?.current_employee_status_id),
    [statuses, employee]
  );
  const selected = statuses.find((s) => s.id === values.new_status_id);

  const set = (name, value) => {
    setValues((p) => ({ ...p, [name]: value }));
    setErrors((p) => ({ ...p, [name]: undefined }));
  };

  const validate = () => {
    const e = {};
    if (!values.new_status_id) e.new_status_id = "Pilih status baru.";
    if (!values.effective_date) e.effective_date = "Tanggal efektif wajib diisi.";
    else if (values.effective_date > today) e.effective_date = "Tanggal efektif tidak boleh melebihi hari ini.";
    if ((values.reason || "").trim().length < 3) e.reason = "Alasan wajib diisi (minimal 3 karakter).";
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const submit = async () => {
    setSaving(true);
    try {
      const res = await api.post(`/employees/${employee.id}/status-change`, {
        new_status_id: values.new_status_id,
        effective_date: values.effective_date,
        reason: values.reason.trim(),
        notes: values.notes.trim() || null,
      });
      toast.success(res.data?.message || "Status karyawan berhasil diubah.", {
        description: `Efektif ${formatDate(values.effective_date)}. Riwayat status dan audit log telah dicatat.`,
      });
      setConfirmOpen(false);
      onOpenChange(false);
      onChanged?.(res.data);
    } catch (err) {
      setConfirmOpen(false);
      toast.error(errorMessage(err, "Status karyawan gagal diubah."), { duration: 9000 });
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-lg" data-testid="change-status-dialog">
          <DialogHeader>
            <DialogTitle>Ubah Status Karyawan</DialogTitle>
            <DialogDescription>
              {employee?.full_name}. Perubahan tercatat di riwayat status dan audit log.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="rounded-lg border border-border bg-muted/40 p-3" data-testid="change-status-current">
              <p className="mb-1 text-[12px] font-medium text-muted-foreground">Status Saat Ini</p>
              <EmployeeStatusBadge
                name={employee?.current_employee_status_name}
                category={employee?.current_employee_status_category}
                testId="change-status-current-badge"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="change-status-new" className="text-[13px] font-medium">
                Status Baru<span className="ml-0.5 text-destructive">*</span>
              </Label>
              <Select value={values.new_status_id} onValueChange={(v) => set("new_status_id", v)}>
                <SelectTrigger id="change-status-new" data-testid="change-status-new-select" aria-invalid={!!errors.new_status_id}>
                  <SelectValue placeholder={loadingOptions ? "Memuat…" : "Pilih status baru"} />
                </SelectTrigger>
                <SelectContent>
                  {options.map((s) => (
                    <SelectItem key={s.id} value={s.id} data-testid={`change-status-option-${s.code}`}>
                      {s.name} · {CATEGORY_LABELS[s.system_category]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {errors.new_status_id && (
                <p className="text-xs font-medium text-destructive" data-testid="change-status-error-status">
                  {errors.new_status_id}
                </p>
              )}
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="change-status-date" className="text-[13px] font-medium">
                  Tanggal Efektif<span className="ml-0.5 text-destructive">*</span>
                </Label>
                <Input
                  id="change-status-date"
                  type="date"
                  max={today}
                  value={values.effective_date}
                  onChange={(e) => set("effective_date", e.target.value)}
                  aria-invalid={!!errors.effective_date}
                  data-testid="change-status-date-input"
                />
                {errors.effective_date ? (
                  <p className="text-xs font-medium text-destructive" data-testid="change-status-error-date">
                    {errors.effective_date}
                  </p>
                ) : (
                  <p className="text-[12px] text-muted-foreground">Hari ini atau tanggal sebelumnya.</p>
                )}
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="change-status-reason" className="text-[13px] font-medium">
                  Alasan<span className="ml-0.5 text-destructive">*</span>
                </Label>
                <Input
                  id="change-status-reason"
                  value={values.reason}
                  maxLength={255}
                  placeholder="Mis. Project selesai"
                  onChange={(e) => set("reason", e.target.value)}
                  aria-invalid={!!errors.reason}
                  data-testid="change-status-reason-input"
                />
                {errors.reason && (
                  <p className="text-xs font-medium text-destructive" data-testid="change-status-error-reason">
                    {errors.reason}
                  </p>
                )}
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="change-status-notes" className="text-[13px] font-medium">
                Catatan <span className="font-normal text-muted-foreground">(opsional)</span>
              </Label>
              <Textarea
                id="change-status-notes"
                rows={3}
                maxLength={1000}
                value={values.notes}
                placeholder="Mis. Menunggu penempatan project berikutnya"
                onChange={(e) => set("notes", e.target.value)}
                data-testid="change-status-notes-input"
              />
            </div>
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="change-status-cancel-button">
              Batal
            </Button>
            <Button
              onClick={() => validate() && setConfirmOpen(true)}
              disabled={saving || loadingOptions}
              data-testid="change-status-save-button"
            >
              {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Simpan Perubahan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={(v) => !saving && setConfirmOpen(v)}
        title="Konfirmasi perubahan status"
        description={
          <span className="block space-y-2" data-testid="change-status-confirm-summary">
            <span className="flex flex-wrap items-center gap-2 font-medium text-foreground">
              {employee?.current_employee_status_name || "Belum diatur"}
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
              {selected?.name} ({CATEGORY_LABELS[selected?.system_category]})
            </span>
            <span className="block">
              Efektif {formatDate(values.effective_date)} · Alasan: {values.reason}
            </span>
          </span>
        }
        confirmLabel="Ya, ubah status"
        loading={saving}
        onConfirm={submit}
      />
    </>
  );
};

export default ChangeStatusDialog;
