import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { CalendarClock, Loader2 } from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

/**
 * Dialog perpanjangan kontrak satu klik.
 * Backend menyiapkan seluruh nilai default lewat /contracts/{id}/renew-preview.
 */
const ContractRenewDialog = ({ contractId, open, onClose, onRenewed }) => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState(null);
  const [form, setForm] = useState(null);

  const load = useCallback(async () => {
    if (!contractId) return;
    setLoading(true);
    try {
      const { data } = await api.get(`/contracts/${contractId}/renew-preview`);
      setPreview(data);
      const d = data?.defaults || {};
      setForm({
        contract_type_id: d.contract_type_id || "",
        contract_number: d.contract_number || "",
        start_date: d.start_date || "",
        end_date: d.end_date || "",
        basic_salary: d.basic_salary != null ? String(d.basic_salary) : "",
        allowance: d.allowance != null ? String(d.allowance) : "",
        notes: d.notes || "",
        archive_previous: true,
      });
    } catch (error) {
      toast.error(errorMessage(error, "Data perpanjangan kontrak tidak dapat dimuat."));
      onClose();
    } finally {
      setLoading(false);
    }
  }, [contractId, onClose]);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  const set = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  const submit = async () => {
    setSaving(true);
    try {
      const { data } = await api.post(`/contracts/${contractId}/renew`, {
        contract_type_id: form.contract_type_id || null,
        contract_number: form.contract_number || null,
        start_date: form.start_date,
        end_date: form.end_date || null,
        basic_salary: form.basic_salary === "" ? null : Number(form.basic_salary),
        allowance: form.allowance === "" ? null : Number(form.allowance),
        notes: form.notes || null,
        archive_previous: !!form.archive_previous,
      });
      toast.success(
        `Kontrak ${preview?.employee?.full_name || ""} diperpanjang sampai ${
          data?.contract?.end_date ? formatDate(data.contract.end_date) : "-"
        }.`
      );
      onRenewed?.(data);
      onClose();
    } catch (error) {
      toast.error(errorMessage(error, "Perpanjangan kontrak gagal."));
    } finally {
      setSaving(false);
    }
  };

  const alreadyRenewed = preview?.already_renewed;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CalendarClock className="h-4 w-4" /> Perpanjang Kontrak
          </DialogTitle>
          <DialogDescription>
            {preview?.employee
              ? `${preview.employee.full_name}${
                  preview.employee.employee_number ? ` · ${preview.employee.employee_number}` : ""
                }`
              : "Menyiapkan data kontrak…"}
          </DialogDescription>
        </DialogHeader>

        {loading || !form ? (
          <div className="space-y-3">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : alreadyRenewed ? (
          <div
            className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
            data-testid="renew-already"
          >
            Kontrak ini sudah diperpanjang dengan nomor{" "}
            <span className="font-medium">{alreadyRenewed.contract_number || "-"}</span> berlaku{" "}
            {formatDate(alreadyRenewed.start_date)} – {formatDate(alreadyRenewed.end_date)}.
          </div>
        ) : (
          <div className="space-y-4">
            <div className="rounded-lg border border-border bg-secondary/40 p-3 text-xs text-muted-foreground">
              Kontrak berjalan:{" "}
              <span className="font-medium text-foreground">
                {preview?.previous_contract?.contract_number || "-"}
              </span>{" "}
              berakhir {formatDate(preview?.previous_contract?.end_date)} · gaji pokok{" "}
              {formatCurrency(preview?.previous_contract?.basic_salary)}
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="renew-type">Tipe kontrak</Label>
                <Select
                  value={form.contract_type_id}
                  onValueChange={(v) => set("contract_type_id", v)}
                >
                  <SelectTrigger id="renew-type" data-testid="renew-contract-type">
                    <SelectValue placeholder="Pilih tipe kontrak" />
                  </SelectTrigger>
                  <SelectContent>
                    {(preview?.contract_types || []).map((type) => (
                      <SelectItem key={type.id} value={type.id}>
                        {type.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="renew-number">Nomor kontrak baru</Label>
                <Input
                  id="renew-number"
                  value={form.contract_number}
                  onChange={(e) => set("contract_number", e.target.value)}
                  data-testid="renew-contract-number"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="renew-start">Mulai</Label>
                <Input
                  id="renew-start"
                  type="date"
                  value={form.start_date}
                  onChange={(e) => set("start_date", e.target.value)}
                  data-testid="renew-start-date"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="renew-end">Berakhir</Label>
                <Input
                  id="renew-end"
                  type="date"
                  value={form.end_date}
                  onChange={(e) => set("end_date", e.target.value)}
                  data-testid="renew-end-date"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="renew-basic">Gaji pokok (Rp)</Label>
                <Input
                  id="renew-basic"
                  type="number"
                  min="0"
                  value={form.basic_salary}
                  onChange={(e) => set("basic_salary", e.target.value)}
                  data-testid="renew-basic-salary"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="renew-allowance">Tunjangan (Rp)</Label>
                <Input
                  id="renew-allowance"
                  type="number"
                  min="0"
                  value={form.allowance}
                  onChange={(e) => set("allowance", e.target.value)}
                  data-testid="renew-allowance"
                />
              </div>
              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="renew-notes">Catatan</Label>
                <Textarea
                  id="renew-notes"
                  value={form.notes}
                  onChange={(e) => set("notes", e.target.value)}
                  data-testid="renew-notes"
                />
              </div>
            </div>

            <div className="flex items-start justify-between gap-4 rounded-lg border border-border p-3">
              <div>
                <p className="text-sm font-medium">Arsipkan kontrak lama</p>
                <p className="text-xs text-muted-foreground">
                  Kontrak sebelumnya ditandai selesai agar tidak muncul lagi di pengingat.
                </p>
              </div>
              <Switch
                checked={form.archive_previous}
                onCheckedChange={(v) => set("archive_previous", v)}
                data-testid="renew-archive-previous"
              />
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} data-testid="renew-cancel">
            Tutup
          </Button>
          {!alreadyRenewed && (
            <Button
              onClick={submit}
              disabled={saving || loading || !form?.start_date}
              data-testid="renew-submit"
            >
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Perpanjang kontrak
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ContractRenewDialog;
