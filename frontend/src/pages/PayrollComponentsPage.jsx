import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2, Plus, Save, Trash2, Wallet } from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatCurrency } from "@/lib/format";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import EmptyState from "@/components/common/EmptyState";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const BLANK = {
  code: "",
  name: "",
  kind: "earning",
  calc: "fixed",
  default_amount: 0,
  percent: 0,
  taxable: true,
  prorate: false,
  include_in_bpjs_base: false,
  sort_order: 100,
  description: "",
};

const PayrollComponentsPage = () => {
  const { can } = useAuth();
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState([]);
  const [dialog, setDialog] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/payroll/components");
      setItems(data?.items || []);
    } catch (error) {
      toast.error(errorMessage(error, "Gagal memuat komponen gaji."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    const form = dialog.form;
    if (!form.code?.trim() || !form.name?.trim()) {
      toast.error("Kode dan nama komponen wajib diisi.");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        ...form,
        default_amount: Number(form.default_amount) || 0,
        percent: Number(form.percent) || 0,
        sort_order: Number(form.sort_order) || 100,
      };
      if (dialog.id) {
        await api.put(`/payroll/components/${dialog.id}`, payload);
        toast.success("Komponen gaji diperbarui.");
      } else {
        await api.post("/payroll/components", payload);
        toast.success("Komponen gaji ditambahkan.");
      }
      setDialog(null);
      load();
    } catch (error) {
      toast.error(errorMessage(error, "Gagal menyimpan komponen gaji."));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (item) => {
    if (!window.confirm(`Hapus komponen "${item.name}"?`)) return;
    try {
      await api.delete(`/payroll/components/${item.id}`);
      toast.success("Komponen gaji dihapus.");
      load();
    } catch (error) {
      toast.error(errorMessage(error, "Gagal menghapus komponen gaji."));
    }
  };

  const form = dialog?.form || BLANK;
  const setForm = (patch) =>
    setDialog((d) => ({ ...d, form: { ...d.form, ...patch } }));

  return (
    <>
      <PageHeader
        title="Komponen Gaji"
        subtitle="Tunjangan dan potongan yang dipakai saat menghitung payroll bulanan."
        actions={
          can("payroll_component", "create") ? (
            <Button
              onClick={() => setDialog({ id: null, form: { ...BLANK } })}
              data-testid="component-create"
            >
              <Plus className="mr-1.5 h-4 w-4" /> Tambah Komponen
            </Button>
          ) : null
        }
      />

      <PageBody>
        <Card>
          <CardContent className="p-0">
            {loading ? (
              <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> Memuat komponen…
              </div>
            ) : items.length === 0 ? (
              <EmptyState
                icon={Wallet}
                title="Belum ada komponen gaji"
                description="Tambahkan tunjangan dan potongan agar bisa dipasang ke struktur gaji karyawan."
                testId="components-empty"
              />
            ) : (
              <Table data-testid="components-table">
                <TableHeader>
                  <TableRow>
                    <TableHead>Kode</TableHead>
                    <TableHead>Nama Komponen</TableHead>
                    <TableHead>Jenis</TableHead>
                    <TableHead className="text-right">Nominal Default</TableHead>
                    <TableHead>Sifat</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((item) => (
                    <TableRow key={item.id} data-testid={`component-row-${item.code}`}>
                      <TableCell className="font-mono text-xs">{item.code}</TableCell>
                      <TableCell>
                        <p className="font-medium">{item.name}</p>
                        {item.description ? (
                          <p className="text-xs text-muted-foreground">{item.description}</p>
                        ) : null}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={
                            item.kind === "earning"
                              ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                              : "border-red-200 bg-red-50 text-red-800"
                          }
                        >
                          {item.kind === "earning" ? "Penghasilan" : "Potongan"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {item.calc === "percent_of_basic"
                          ? `${item.percent || 0}% gaji pokok`
                          : formatCurrency(item.default_amount)}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {item.taxable ? (
                            <Badge variant="outline" className="text-xs">
                              Kena pajak
                            </Badge>
                          ) : null}
                          {item.prorate ? (
                            <Badge variant="outline" className="text-xs">
                              Prorata
                            </Badge>
                          ) : null}
                          {item.include_in_bpjs_base ? (
                            <Badge variant="outline" className="text-xs">
                              Dasar BPJS
                            </Badge>
                          ) : null}
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          {can("payroll_component", "edit") ? (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setDialog({ id: item.id, form: { ...BLANK, ...item } })}
                              data-testid={`component-edit-${item.code}`}
                            >
                              Ubah
                            </Button>
                          ) : null}
                          {can("payroll_component", "delete") ? (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => remove(item)}
                              data-testid={`component-delete-${item.code}`}
                            >
                              <Trash2 className="h-4 w-4 text-red-600" />
                            </Button>
                          ) : null}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </PageBody>

      <Dialog open={!!dialog} onOpenChange={(o) => !o && setDialog(null)}>
        <DialogContent className="bg-card sm:max-w-lg" data-testid="component-dialog">
          <DialogHeader>
            <DialogTitle>{dialog?.id ? "Ubah Komponen Gaji" : "Tambah Komponen Gaji"}</DialogTitle>
            <DialogDescription>
              Komponen kena pajak ikut menambah dasar PPh 21. Komponen prorata dipotong bila
              karyawan tidak hadir tanpa upah.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Kode *</Label>
                <Input
                  value={form.code}
                  onChange={(e) => setForm({ code: e.target.value.toUpperCase() })}
                  placeholder="TJ-JAB"
                  data-testid="component-code"
                />
              </div>
              <div className="space-y-1.5">
                <Label>Jenis</Label>
                <Select value={form.kind} onValueChange={(v) => setForm({ kind: v })}>
                  <SelectTrigger data-testid="component-kind">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="earning">Penghasilan</SelectItem>
                    <SelectItem value="deduction">Potongan</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label>Nama Komponen *</Label>
              <Input
                value={form.name}
                onChange={(e) => setForm({ name: e.target.value })}
                placeholder="Tunjangan Jabatan"
                data-testid="component-name"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Cara hitung</Label>
                <Select value={form.calc} onValueChange={(v) => setForm({ calc: v })}>
                  <SelectTrigger data-testid="component-calc">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="fixed">Nominal tetap</SelectItem>
                    <SelectItem value="percent_of_basic">Persentase gaji pokok</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>
                  {form.calc === "percent_of_basic" ? "Persentase (%)" : "Nominal default (Rp)"}
                </Label>
                <Input
                  type="number"
                  min={0}
                  value={
                    form.calc === "percent_of_basic" ? form.percent : form.default_amount
                  }
                  onChange={(e) =>
                    setForm(
                      form.calc === "percent_of_basic"
                        ? { percent: e.target.value }
                        : { default_amount: e.target.value }
                    )
                  }
                  data-testid="component-amount"
                />
              </div>
            </div>

            <div className="space-y-2 rounded-md border border-border bg-muted/40 p-3">
              {[
                ["taxable", "Objek PPh 21", "Ikut menambah penghasilan bruto kena pajak."],
                ["prorate", "Prorata kehadiran", "Dipotong bila ada hari tidak dibayar."],
                [
                  "include_in_bpjs_base",
                  "Masuk dasar upah BPJS",
                  "Menambah dasar perhitungan iuran BPJS.",
                ],
              ].map(([key, label, hint]) => (
                <div key={key} className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium">{label}</p>
                    <p className="text-xs text-muted-foreground">{hint}</p>
                  </div>
                  <Switch
                    checked={!!form[key]}
                    onCheckedChange={(v) => setForm({ [key]: v })}
                    data-testid={`component-${key}`}
                  />
                </div>
              ))}
            </div>

            <div className="space-y-1.5">
              <Label>Keterangan</Label>
              <Textarea
                rows={2}
                value={form.description || ""}
                onChange={(e) => setForm({ description: e.target.value })}
                data-testid="component-description"
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setDialog(null)} disabled={saving}>
              Batal
            </Button>
            <Button onClick={save} disabled={saving} data-testid="component-save">
              {saving ? (
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
              ) : (
                <Save className="mr-1.5 h-4 w-4" />
              )}
              Simpan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default PayrollComponentsPage;
