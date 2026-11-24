import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ClipboardList, History, Plus, RefreshCw, Search, UserMinus } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { PageBody } from "@/components/common/PageHeader";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const selectClass = "h-9 w-full rounded-lg border border-input bg-card px-3 text-sm text-ink-1 shadow-[var(--shadow-input)] transition-[border-color,box-shadow] duration-150 hover:border-border-strong focus-visible:outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/25";

const STATES = {
  DRAFT: { label: "Draft", variant: "secondary" },
  PENDING_APPROVAL: { label: "Menunggu Persetujuan", variant: "info" },
  COMPLETED: { label: "Selesai", variant: "success" },
  CANCELLED: { label: "Dibatalkan", variant: "destructive" },
};

const EXIT_TYPES = [
  { value: "RESIGN", label: "Resign / mengundurkan diri" },
  { value: "END_OF_CONTRACT", label: "Berakhirnya kontrak" },
  { value: "TERMINATION", label: "PHK" },
  { value: "RETIREMENT", label: "Pensiun" },
  { value: "OTHER", label: "Lainnya" },
];

const Stat = ({ label, value, tone = "default", testId }) => (
  <Card className="border-border bg-card p-3" data-testid={testId}>
    <p className="text-[12px] text-muted-foreground">{label}</p>
    <p className={`mt-1 text-2xl font-semibold tabular-nums ${tone === "warning" ? "text-warning" : ""}`}>{value ?? 0}</p>
  </Card>
);

const emptyForm = {
  employee_id: "", exit_type: "RESIGN", last_working_date: "", reason: "", notes: "",
};

const EmployeeExitClearancePage = () => {
  const { can } = useAuth();
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [stateFilter, setStateFilter] = useState("");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [candidates, setCandidates] = useState([]);
  const [candLoading, setCandLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = {};
      if (stateFilter) params.state = stateFilter;
      if (q.trim()) params.q = q.trim();
      const [{ data: list }, { data: sum }] = await Promise.all([
        api.get("/exit-clearance", { params }),
        api.get("/exit-clearance/summary"),
      ]);
      setItems(list.items || []);
      setSummary(sum);
    } catch (err) {
      setError(errorMessage(err, "Daftar exit clearance tidak dapat dimuat."));
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [stateFilter, q]);

  useEffect(() => { load(); }, [load]);

  const loadCandidates = useCallback(async (needle = "") => {
    setCandLoading(true);
    try {
      const { data } = await api.get("/exit-clearance/candidates", { params: needle ? { q: needle } : {} });
      setCandidates(data.items || []);
    } catch (err) {
      toast.error(errorMessage(err, "Daftar karyawan tidak dapat dimuat."));
      setCandidates([]);
    } finally {
      setCandLoading(false);
    }
  }, []);

  const openDialog = () => {
    setForm(emptyForm);
    setCandidates([]);
    setOpen(true);
    loadCandidates("");
  };

  const submit = async () => {
    if (!form.employee_id) {
      toast.error("Pilih karyawan terlebih dahulu.");
      return;
    }
    if (!form.last_working_date) {
      toast.error("Tanggal kerja terakhir wajib diisi.");
      return;
    }
    if (form.reason.trim().length < 3) {
      toast.error("Alasan keluar wajib diisi (minimal 3 karakter).");
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.post("/exit-clearance", {
        employee_id: form.employee_id,
        exit_type: form.exit_type,
        last_working_date: form.last_working_date,
        reason: form.reason.trim(),
        notes: form.notes.trim() || null,
      });
      toast.success(data.message || "Kasus exit clearance dibuat.");
      setOpen(false);
      navigate(`/employees/exit-clearance/${data.item.id}`);
    } catch (err) {
      toast.error(errorMessage(err, "Kasus exit clearance gagal dibuat."));
    } finally {
      setSaving(false);
    }
  };

  const counts = summary?.counts || {};
  const openTotal = (counts.DRAFT || 0) + (counts.PENDING_APPROVAL || 0);

  const selectedEmployee = useMemo(
    () => candidates.find((c) => c.id === form.employee_id) || null,
    [candidates, form.employee_id],
  );

  return (
    <PageBody>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Draft" value={counts.DRAFT} testId="exit-stat-draft" />
        <Stat label="Menunggu Persetujuan" value={counts.PENDING_APPROVAL} tone="warning"
          testId="exit-stat-pending" />
        <Stat label="Selesai" value={counts.COMPLETED} testId="exit-stat-completed" />
        <Stat label="Dibatalkan" value={counts.CANCELLED} testId="exit-stat-cancelled" />
      </div>

      <Card className="border-border bg-card p-4" data-testid="exit-controls">
        <div className="grid gap-3 lg:grid-cols-[1fr_220px_auto] lg:items-end">
          <div>
            <Label htmlFor="exit-search" className="text-[13px]">Cari</Label>
            <div className="relative mt-1">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input id="exit-search" className="pl-8" placeholder="No. kasus, nama, atau NIK karyawan"
                value={q} onChange={(e) => setQ(e.target.value)} data-testid="exit-search" />
            </div>
          </div>
          <div>
            <Label htmlFor="exit-state" className="text-[13px]">Status</Label>
            <select id="exit-state" className={`${selectClass} mt-1`} value={stateFilter}
              onChange={(e) => setStateFilter(e.target.value)} data-testid="exit-state-filter">
              <option value="">Semua status</option>
              {Object.entries(STATES).map(([value, st]) => (
                <option key={value} value={value}>{st.label}</option>
              ))}
            </select>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={load} disabled={loading} data-testid="exit-refresh">
              <RefreshCw className="mr-1.5 h-4 w-4" />Muat ulang
            </Button>
            <Button asChild variant="outline" data-testid="exit-history-link">
              <Link to="/employees/exit-clearance/history">
                <History className="mr-1.5 h-4 w-4" />Histori
              </Link>
            </Button>
            {can("exit_clearance", "create") && (
              <Button onClick={openDialog} data-testid="exit-create-open">
                <Plus className="mr-1.5 h-4 w-4" />Buat Kasus
              </Button>
            )}
          </div>
        </div>
        <p className="mt-2 text-[11px] text-muted-foreground">
          Exit clearance memastikan seluruh serah terima (dokumen, pekerjaan, aset, keuangan, akses) selesai
          sebelum status karyawan menjadi Tidak Aktif. Terdapat {openTotal} kasus berjalan.
        </p>
      </Card>

      {loading ? (
        <Skeleton className="h-64 w-full rounded-xl" />
      ) : error ? (
        <Card className="space-y-3 p-4" role="alert" data-testid="exit-error">
          <p className="text-sm">{error}</p>
          <Button variant="outline" onClick={load}>Coba lagi</Button>
        </Card>
      ) : items.length === 0 ? (
        <Card className="flex flex-col items-center gap-2 p-8 text-center" data-testid="exit-empty">
          <UserMinus className="h-8 w-8 text-muted-foreground" />
          <p className="text-sm font-medium">Belum ada kasus exit clearance.</p>
          <p className="text-[13px] text-muted-foreground">
            Buat kasus untuk karyawan yang akan berhenti agar checklist serah terima tercatat.
          </p>
          {can("exit_clearance", "create") && (
            <Button className="mt-1" onClick={openDialog}>
              <Plus className="mr-1.5 h-4 w-4" />Buat Kasus
            </Button>
          )}
        </Card>
      ) : (
        <Card className="border-border bg-card" data-testid="exit-table-card">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>No. Kasus</TableHead>
                  <TableHead>Karyawan</TableHead>
                  <TableHead>Project</TableHead>
                  <TableHead>Tipe</TableHead>
                  <TableHead>Kerja Terakhir</TableHead>
                  <TableHead>Checklist</TableHead>
                  <TableHead>Aset</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Aksi</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((row) => {
                  const st = STATES[row.case_state] || { label: row.case_state_label, variant: "outline" };
                  const progress = row.progress || { done: 0, total: 0 };
                  return (
                    <TableRow key={row.id} data-testid={`exit-row-${row.id}`}>
                      <TableCell className="font-medium">
                        <Link className="text-primary hover:underline" to={`/employees/exit-clearance/${row.id}`}>
                          {row.case_number}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <p className="font-medium">{row.employee_name}</p>
                        <p className="text-[11px] text-muted-foreground">{row.employee_number || "-"}</p>
                      </TableCell>
                      <TableCell>{row.project_name || "-"}</TableCell>
                      <TableCell>{row.exit_type_label || "-"}</TableCell>
                      <TableCell>{formatDate(row.last_working_date)}</TableCell>
                      <TableCell>
                        <Badge variant={progress.total && progress.done === progress.total ? "success" : "outline"}>
                          {progress.done}/{progress.total}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {row.outstanding_assets > 0 ? (
                          <Badge variant="warning">{row.outstanding_assets} aktif</Badge>
                        ) : (
                          <span className="text-[12px] text-muted-foreground">Tidak ada</span>
                        )}
                      </TableCell>
                      <TableCell><Badge variant={st.variant}>{st.label}</Badge></TableCell>
                      <TableCell className="text-right">
                        <Button asChild size="sm" variant="outline">
                          <Link to={`/employees/exit-clearance/${row.id}`}>Buka</Link>
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </Card>
      )}

      <Dialog open={open} onOpenChange={(value) => !saving && setOpen(value)}>
        <DialogContent className="bg-card sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Buat kasus exit clearance</DialogTitle>
            <DialogDescription>
              Checklist serah terima lintas bagian dibuat otomatis setelah kasus disimpan.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label htmlFor="exit-employee" className="text-[13px]">Karyawan</Label>
              <select id="exit-employee" className={`${selectClass} mt-1`} value={form.employee_id}
                onChange={(e) => setForm((f) => ({ ...f, employee_id: e.target.value }))}
                data-testid="exit-employee">
                <option value="">{candLoading ? "Memuat…" : "Pilih karyawan aktif"}</option>
                {candidates.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.full_name} · {c.employee_number || "-"}{c.project_name ? ` · ${c.project_name}` : ""}
                  </option>
                ))}
              </select>
              {selectedEmployee?.join_date && (
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Bergabung {formatDate(selectedEmployee.join_date)}
                </p>
              )}
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <Label htmlFor="exit-type" className="text-[13px]">Tipe keluar</Label>
                <select id="exit-type" className={`${selectClass} mt-1`} value={form.exit_type}
                  onChange={(e) => setForm((f) => ({ ...f, exit_type: e.target.value }))} data-testid="exit-type">
                  {EXIT_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              </div>
              <div>
                <Label htmlFor="exit-last-day" className="text-[13px]">Tanggal kerja terakhir</Label>
                <Input id="exit-last-day" type="date" className="mt-1" value={form.last_working_date}
                  onChange={(e) => setForm((f) => ({ ...f, last_working_date: e.target.value }))}
                  data-testid="exit-last-day" />
              </div>
            </div>
            <div>
              <Label htmlFor="exit-reason" className="text-[13px]">Alasan keluar</Label>
              <Input id="exit-reason" className="mt-1" maxLength={255} value={form.reason}
                placeholder="Mis. mengundurkan diri untuk alasan keluarga"
                onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))} data-testid="exit-reason" />
            </div>
            <div>
              <Label htmlFor="exit-notes" className="text-[13px]">Catatan (opsional)</Label>
              <Textarea id="exit-notes" className="mt-1" rows={3} value={form.notes}
                onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} data-testid="exit-notes" />
            </div>
            <p className="flex items-start gap-1.5 text-[11px] text-muted-foreground">
              <ClipboardList className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              Pastikan tanggal kerja terakhir sesuai dokumen pengunduran diri. Persetujuan final baru dapat
              dilakukan pada/setelah tanggal tersebut.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={saving}>Batal</Button>
            <Button onClick={submit} disabled={saving} data-testid="exit-create-submit">
              {saving ? "Menyimpan…" : "Buat Kasus"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageBody>
  );
};

export default EmployeeExitClearancePage;
