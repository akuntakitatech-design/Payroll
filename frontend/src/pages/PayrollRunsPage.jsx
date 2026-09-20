import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { AlertTriangle, Calculator, Loader2, Plus, RefreshCw, Wallet } from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatCurrency, formatDate } from "@/lib/format";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import EmptyState from "@/components/common/EmptyState";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
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

export const RUN_STATUS_TONE = {
  draft: "bg-slate-100 text-slate-700 border-slate-200",
  pending_approval: "bg-amber-100 text-amber-800 border-amber-200",
  approved: "bg-emerald-100 text-emerald-800 border-emerald-200",
  rejected: "bg-red-100 text-red-800 border-red-200",
  paid: "bg-sky-100 text-sky-800 border-sky-200",
};

export const RunStatusBadge = ({ status, label, testId }) => (
  <Badge
    variant="outline"
    className={RUN_STATUS_TONE[status] || RUN_STATUS_TONE.draft}
    data-testid={testId}
  >
    {label || status || "-"}
  </Badge>
);

const StatTile = ({ label, value, hint }) => (
  <Card className="bg-card">
    <CardContent className="p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums text-foreground">{value}</p>
      {hint ? <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p> : null}
    </CardContent>
  </Card>
);

const PayrollRunsPage = () => {
  const navigate = useNavigate();
  const { can } = useAuth();
  const [loading, setLoading] = useState(true);
  const [runs, setRuns] = useState([]);
  const [summary, setSummary] = useState(null);
  const [catalog, setCatalog] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const now = useMemo(() => new Date(), []);
  const [form, setForm] = useState({
    year: String(now.getFullYear()),
    month: String(now.getMonth() + 1),
    payment_date: "",
    notes: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [runsRes, sumRes, catRes] = await Promise.all([
        api.get("/payroll/runs"),
        api.get("/payroll/summary"),
        api.get("/payroll/catalog"),
      ]);
      setRuns(runsRes.data?.items || []);
      setSummary(sumRes.data || null);
      setCatalog(catRes.data || null);
    } catch (error) {
      toast.error(errorMessage(error, "Gagal memuat data payroll."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const months = catalog?.months || [];
  const years = useMemo(() => {
    const y = now.getFullYear();
    return [y + 1, y, y - 1, y - 2];
  }, [now]);

  const submit = async () => {
    setSaving(true);
    try {
      const { data } = await api.post("/payroll/runs", {
        year: Number(form.year),
        month: Number(form.month),
        payment_date: form.payment_date || null,
        notes: form.notes || null,
      });
      toast.success(
        `Payroll ${data.period_label} dibuat dengan ${data.employee_count} slip gaji.`
      );
      setDialogOpen(false);
      navigate(`/payroll/runs/${data.id}`);
    } catch (error) {
      toast.error(errorMessage(error, "Gagal membuat payroll."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Payroll Bulanan"
        subtitle="Hitung gaji, BPJS dan PPh 21 per periode, lalu ajukan untuk persetujuan."
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={load} data-testid="payroll-refresh">
              <RefreshCw className="mr-1.5 h-4 w-4" /> Muat ulang
            </Button>
            {can("payroll", "create") ? (
              <Button onClick={() => setDialogOpen(true)} data-testid="payroll-run-create">
                <Plus className="mr-1.5 h-4 w-4" /> Jalankan Payroll
              </Button>
            ) : null}
          </div>
        }
      />

      <PageBody>
        {summary?.employees_without_salary > 0 ? (
          <Card className="border-amber-200 bg-amber-50">
            <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
              <div className="flex items-start gap-2.5">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
                <div>
                  <p className="text-sm font-medium text-amber-900">
                    {summary.employees_without_salary} karyawan belum punya struktur gaji
                  </p>
                  <p className="text-xs text-amber-800">
                    Karyawan tanpa gaji pokok otomatis dilewati saat payroll dihitung.
                  </p>
                </div>
              </div>
              <Button
                variant="outline"
                className="border-amber-300 bg-white"
                onClick={() => navigate("/payroll/salaries")}
                data-testid="payroll-goto-salaries"
              >
                Lengkapi Struktur Gaji
              </Button>
            </CardContent>
          </Card>
        ) : null}

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StatTile
            label="Periode terakhir"
            value={summary?.latest_run?.period_label || "-"}
            hint={summary?.latest_run?.status_label || "Belum ada payroll"}
          />
          <StatTile
            label="Menunggu persetujuan"
            value={summary?.pending_approval_count ?? 0}
            hint="Periode yang perlu ditindak"
          />
          <StatTile
            label="Karyawan aktif"
            value={summary?.active_employees ?? 0}
            hint={`${summary?.employees_with_salary ?? 0} sudah punya struktur gaji`}
          />
          <StatTile
            label="Gaji bersih periode terakhir"
            value={formatCurrency(summary?.latest_run?.totals?.net_pay)}
            hint={`${summary?.latest_run?.employee_count ?? 0} slip gaji`}
          />
        </div>

        <Card>
          <CardContent className="p-0">
            {loading ? (
              <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> Memuat periode payroll…
              </div>
            ) : runs.length === 0 ? (
              <EmptyState
                icon={Wallet}
                title="Belum ada periode payroll"
                description="Mulai dengan menjalankan payroll untuk bulan berjalan. Sistem akan menghitung BPJS dan PPh 21 secara otomatis."
                actionLabel={can("payroll", "create") ? "Jalankan Payroll" : undefined}
                onAction={can("payroll", "create") ? () => setDialogOpen(true) : undefined}
                testId="payroll-runs-empty"
              />
            ) : (
              <Table data-testid="payroll-runs-table">
                <TableHeader>
                  <TableRow>
                    <TableHead>Periode</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Karyawan</TableHead>
                    <TableHead className="text-right">Bruto</TableHead>
                    <TableHead className="text-right">PPh 21</TableHead>
                    <TableHead className="text-right">Gaji Bersih</TableHead>
                    <TableHead>Tanggal Bayar</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {runs.map((run) => (
                    <TableRow
                      key={run.id}
                      className="cursor-pointer"
                      onClick={() => navigate(`/payroll/runs/${run.id}`)}
                      data-testid={`payroll-run-row-${run.id}`}
                    >
                      <TableCell className="font-medium">{run.period_label}</TableCell>
                      <TableCell>
                        <RunStatusBadge
                          status={run.run_status}
                          label={run.status_label}
                          testId={`payroll-run-status-${run.id}`}
                        />
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {run.employee_count ?? 0}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatCurrency(run.totals?.gross)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatCurrency(run.totals?.pph21)}
                      </TableCell>
                      <TableCell className="text-right font-medium tabular-nums">
                        {formatCurrency(run.totals?.net_pay)}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {run.payment_date ? formatDate(run.payment_date) : "-"}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button variant="ghost" size="sm">
                          Buka
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </PageBody>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="bg-card sm:max-w-md" data-testid="payroll-run-dialog">
          <DialogHeader>
            <DialogTitle>Jalankan Payroll</DialogTitle>
            <DialogDescription>
              Sistem menghitung gaji seluruh karyawan aktif yang sudah memiliki struktur gaji.
              Bulan Desember otomatis memakai rekonsiliasi tahunan Pasal 17.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Bulan</Label>
                <Select
                  value={form.month}
                  onValueChange={(v) => setForm((f) => ({ ...f, month: v }))}
                >
                  <SelectTrigger data-testid="payroll-run-month">
                    <SelectValue placeholder="Pilih bulan" />
                  </SelectTrigger>
                  <SelectContent>
                    {months.map((m) => (
                      <SelectItem key={m.value} value={String(m.value)}>
                        {m.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Tahun</Label>
                <Select
                  value={form.year}
                  onValueChange={(v) => setForm((f) => ({ ...f, year: v }))}
                >
                  <SelectTrigger data-testid="payroll-run-year">
                    <SelectValue placeholder="Pilih tahun" />
                  </SelectTrigger>
                  <SelectContent>
                    {years.map((y) => (
                      <SelectItem key={y} value={String(y)}>
                        {y}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label>Rencana tanggal pembayaran</Label>
              <Input
                type="date"
                value={form.payment_date}
                onChange={(e) => setForm((f) => ({ ...f, payment_date: e.target.value }))}
                data-testid="payroll-run-payment-date"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Catatan (opsional)</Label>
              <Textarea
                rows={2}
                value={form.notes}
                onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                placeholder="Misal: termasuk tunjangan proyek Balikpapan"
                data-testid="payroll-run-notes"
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)} disabled={saving}>
              Batal
            </Button>
            <Button onClick={submit} disabled={saving} data-testid="payroll-run-submit">
              {saving ? (
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
              ) : (
                <Calculator className="mr-1.5 h-4 w-4" />
              )}
              Hitung Payroll
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default PayrollRunsPage;
