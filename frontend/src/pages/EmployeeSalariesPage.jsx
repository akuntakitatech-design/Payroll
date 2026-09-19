import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, Loader2, Save, Search, Users } from "lucide-react";

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

export const SalaryEditorDialog = ({ employeeId, employeeName, open, onClose, onSaved }) => {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [catalog, setCatalog] = useState(null);
  const [components, setComponents] = useState([]);
  const [form, setForm] = useState(null);

  useEffect(() => {
    if (!open || !employeeId) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const [salRes, catRes, compRes] = await Promise.all([
          api.get(`/payroll/salaries/${employeeId}`),
          api.get("/payroll/catalog"),
          api.get("/payroll/components"),
        ]);
        if (cancelled) return;
        const sal = salRes.data?.salary || {};
        setCatalog(catRes.data || null);
        setComponents(compRes.data?.items || []);
        setForm({
          basic_salary: sal.basic_salary ?? 0,
          ptkp_status: sal.ptkp_status || "TK/0",
          has_npwp: sal.has_npwp ?? !!salRes.data?.employee?.npwp,
          bpjs_kesehatan_enrolled: sal.bpjs_kesehatan_enrolled ?? true,
          bpjs_jht_enrolled: sal.bpjs_jht_enrolled ?? true,
          bpjs_jp_enrolled: sal.bpjs_jp_enrolled ?? true,
          effective_date: sal.effective_date || "",
          notes: sal.notes || "",
          components: (sal.components || []).map((c) => ({
            component_id: c.component_id,
            amount: c.amount,
          })),
        });
      } catch (error) {
        toast.error(errorMessage(error, "Gagal memuat struktur gaji."));
        onClose?.();
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, employeeId, onClose]);

  const toggleComponent = (id, checked) => {
    setForm((f) => ({
      ...f,
      components: checked
        ? [...f.components, { component_id: id, amount: null }]
        : f.components.filter((c) => c.component_id !== id),
    }));
  };

  const setComponentAmount = (id, amount) =>
    setForm((f) => ({
      ...f,
      components: f.components.map((c) =>
        c.component_id === id ? { ...c, amount: amount === "" ? null : Number(amount) } : c
      ),
    }));

  const save = async () => {
    if (Number(form.basic_salary) <= 0) {
      toast.error("Gaji pokok harus lebih dari nol agar karyawan ikut dihitung di payroll.");
      return;
    }
    setSaving(true);
    try {
      await api.put(`/payroll/salaries/${employeeId}`, {
        ...form,
        basic_salary: Number(form.basic_salary),
        effective_date: form.effective_date || null,
      });
      toast.success(`Struktur gaji ${employeeName || "karyawan"} disimpan.`);
      onSaved?.();
      onClose?.();
    } catch (error) {
      toast.error(errorMessage(error, "Gagal menyimpan struktur gaji."));
    } finally {
      setSaving(false);
    }
  };

  const selectedPtkp = catalog?.ptkp_statuses?.find((p) => p.value === form?.ptkp_status);

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose?.()}>
      <DialogContent
        className="max-h-[88vh] overflow-y-auto bg-card sm:max-w-2xl"
        data-testid="salary-dialog"
      >
        <DialogHeader>
          <DialogTitle>Gaji &amp; Pajak — {employeeName || "Karyawan"}</DialogTitle>
          <DialogDescription>
            Gaji pokok, status PTKP dan kepesertaan BPJS menjadi dasar perhitungan payroll
            bulanan serta PPh 21 metode TER.
          </DialogDescription>
        </DialogHeader>

        {loading || !form ? (
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Memuat…
          </div>
        ) : (
          <div className="grid gap-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label>Gaji Pokok (Rp) *</Label>
                <Input
                  type="number"
                  min={0}
                  value={form.basic_salary}
                  onChange={(e) => setForm((f) => ({ ...f, basic_salary: e.target.value }))}
                  data-testid="salary-basic"
                />
              </div>
              <div className="space-y-1.5">
                <Label>Status PTKP *</Label>
                <Select
                  value={form.ptkp_status}
                  onValueChange={(v) => setForm((f) => ({ ...f, ptkp_status: v }))}
                >
                  <SelectTrigger data-testid="salary-ptkp">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(catalog?.ptkp_statuses || []).map((p) => (
                      <SelectItem key={p.value} value={p.value}>
                        {p.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {selectedPtkp ? (
                  <p className="text-xs text-muted-foreground">
                    Kategori TER <b>{selectedPtkp.ter_category}</b> · PTKP{" "}
                    {formatCurrency(selectedPtkp.ptkp_annual)}/tahun
                  </p>
                ) : null}
              </div>
              <div className="space-y-1.5">
                <Label>Berlaku dari</Label>
                <Input
                  type="date"
                  value={form.effective_date || ""}
                  onChange={(e) => setForm((f) => ({ ...f, effective_date: e.target.value }))}
                  data-testid="salary-effective-date"
                />
              </div>
              <div className="flex items-end justify-between gap-3 rounded-md border border-border bg-muted/40 px-3 py-2">
                <div>
                  <p className="text-sm font-medium">Punya NPWP</p>
                  <p className="text-xs text-muted-foreground">Dipakai bila kebijakan 20% aktif.</p>
                </div>
                <Switch
                  checked={!!form.has_npwp}
                  onCheckedChange={(v) => setForm((f) => ({ ...f, has_npwp: v }))}
                  data-testid="salary-has-npwp"
                />
              </div>
            </div>

            <div className="space-y-2 rounded-md border border-border bg-muted/40 p-3">
              <p className="text-sm font-semibold">Kepesertaan BPJS</p>
              {[
                ["bpjs_kesehatan_enrolled", "BPJS Kesehatan", "Pekerja 1%, perusahaan 4% (batas upah Rp12.000.000)"],
                ["bpjs_jht_enrolled", "BPJS JHT", "Pekerja 2%, perusahaan 3,7% (tanpa batas upah)"],
                ["bpjs_jp_enrolled", "BPJS Jaminan Pensiun", "Pekerja 1%, perusahaan 2% (batas upah Rp11.086.300)"],
              ].map(([key, label, hint]) => (
                <div key={key} className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm">{label}</p>
                    <p className="text-xs text-muted-foreground">{hint}</p>
                  </div>
                  <Switch
                    checked={!!form[key]}
                    onCheckedChange={(v) => setForm((f) => ({ ...f, [key]: v }))}
                    data-testid={`salary-${key}`}
                  />
                </div>
              ))}
            </div>

            <div className="space-y-2">
              <p className="text-sm font-semibold">Komponen tetap</p>
              {components.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  Belum ada komponen gaji. Tambahkan di menu Komponen Gaji.
                </p>
              ) : (
                <div className="divide-y divide-border rounded-md border border-border">
                  {components.map((c) => {
                    const picked = form.components.find((x) => x.component_id === c.id);
                    return (
                      <div key={c.id} className="flex items-center gap-3 px-3 py-2">
                        <Switch
                          checked={!!picked}
                          onCheckedChange={(v) => toggleComponent(c.id, v)}
                          data-testid={`salary-component-${c.code}`}
                        />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium">{c.name}</p>
                          <p className="text-xs text-muted-foreground">
                            {c.kind === "earning" ? "Penghasilan" : "Potongan"} · default{" "}
                            {c.calc === "percent_of_basic"
                              ? `${c.percent}% gaji pokok`
                              : formatCurrency(c.default_amount)}
                          </p>
                        </div>
                        {picked && c.calc !== "percent_of_basic" ? (
                          <Input
                            className="w-40"
                            type="number"
                            min={0}
                            placeholder={String(c.default_amount || 0)}
                            value={picked.amount ?? ""}
                            onChange={(e) => setComponentAmount(c.id, e.target.value)}
                            data-testid={`salary-component-amount-${c.code}`}
                          />
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Batal
          </Button>
          <Button onClick={save} disabled={saving || loading} data-testid="salary-save">
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
  );
};

const EmployeeSalariesPage = () => {
  const { can } = useAuth();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [query, setQuery] = useState("");
  const [onlyUnset, setOnlyUnset] = useState(false);
  const [editing, setEditing] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data: res } = await api.get("/payroll/salaries", {
        params: { q: query || undefined, only_unset: onlyUnset || undefined },
      });
      setData(res);
    } catch (error) {
      toast.error(errorMessage(error, "Gagal memuat struktur gaji."));
    } finally {
      setLoading(false);
    }
  }, [query, onlyUnset]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  const items = data?.items || [];

  return (
    <>
      <PageHeader
        title="Struktur Gaji Karyawan"
        subtitle="Gaji pokok, status PTKP, kepesertaan BPJS dan komponen tetap per karyawan."
      />

      <PageBody>
        {data?.unset_count > 0 ? (
          <Card className="border-amber-200 bg-amber-50">
            <CardContent className="flex items-start gap-2.5 p-4">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
              <p className="text-sm text-amber-900">
                <b>{data.unset_count} karyawan</b> belum memiliki gaji pokok. Karyawan ini akan
                dilewati ketika payroll dihitung.
              </p>
            </CardContent>
          </Card>
        ) : null}

        <Card>
          <CardContent className="space-y-3 p-4">
            <div className="flex flex-wrap items-end gap-3">
              <div className="min-w-[240px] flex-1 space-y-1.5">
                <Label>Pencarian</Label>
                <div className="relative">
                  <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input
                    className="pl-8"
                    placeholder="Cari nama atau NIK karyawan…"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    data-testid="salaries-search"
                  />
                </div>
              </div>
              <div className="flex items-center gap-2 pb-2">
                <Switch
                  checked={onlyUnset}
                  onCheckedChange={setOnlyUnset}
                  data-testid="salaries-only-unset"
                />
                <span className="text-sm">Hanya yang belum diatur</span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-0">
            {loading ? (
              <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> Memuat…
              </div>
            ) : items.length === 0 ? (
              <EmptyState
                icon={Users}
                title="Tidak ada karyawan"
                description="Ubah pencarian atau tambahkan karyawan terlebih dahulu."
                testId="salaries-empty"
              />
            ) : (
              <Table data-testid="salaries-table">
                <TableHeader>
                  <TableRow>
                    <TableHead>Karyawan</TableHead>
                    <TableHead className="text-right">Gaji Pokok</TableHead>
                    <TableHead>PTKP / TER</TableHead>
                    <TableHead>BPJS</TableHead>
                    <TableHead>Komponen</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((row) => (
                    <TableRow key={row.employee_id} data-testid={`salary-row-${row.employee_id}`}>
                      <TableCell>
                        <p className="font-medium">{row.full_name}</p>
                        <p className="text-xs text-muted-foreground">
                          {row.employee_number} · {row.job_title || "-"}
                        </p>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {row.has_salary ? (
                          formatCurrency(row.basic_salary)
                        ) : (
                          <Badge
                            variant="outline"
                            className="border-amber-200 bg-amber-50 text-amber-800"
                          >
                            Belum diatur
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        <span className="font-medium">{row.ptkp_status}</span>{" "}
                        <Badge variant="outline" className="ml-1 text-xs">
                          TER {row.ter_category}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {[
                          row.bpjs_kesehatan_enrolled && "Kes",
                          row.bpjs_jht_enrolled && "JHT",
                          row.bpjs_jp_enrolled && "JP",
                        ]
                          .filter(Boolean)
                          .join(" · ") || "Tidak ikut"}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {row.components?.length
                          ? `${row.components.length} komponen`
                          : "Tanpa komponen"}
                      </TableCell>
                      <TableCell className="text-right">
                        {can("employee_salary", "edit") ? (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() =>
                              setEditing({ id: row.employee_id, name: row.full_name })
                            }
                            data-testid={`salary-edit-${row.employee_id}`}
                          >
                            Atur Gaji
                          </Button>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </PageBody>

      <SalaryEditorDialog
        open={!!editing}
        employeeId={editing?.id}
        employeeName={editing?.name}
        onClose={() => setEditing(null)}
        onSaved={load}
      />
    </>
  );
};

export default EmployeeSalariesPage;
