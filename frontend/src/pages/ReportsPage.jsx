import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  BarChart3, Download, Package, Plane, RefreshCw, Search, ShieldCheck, UserMinus, Users,
} from "lucide-react";
import { toast } from "sonner";

import { api, errorMessage } from "@/lib/api";
import { formatCurrency, formatDate, formatDateTime } from "@/lib/format";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

const selectClass =
  "h-9 w-full rounded-lg border border-input bg-card px-3 text-sm text-ink-1 shadow-[var(--shadow-input)] transition-[border-color,box-shadow] duration-150 hover:border-border-strong focus-visible:outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/25";

const REPORT_ICONS = {
  karyawan: Users,
  kepatuhan: ShieldCheck,
  roster: Plane,
  aset: Package,
  exit: UserMinus,
};

// Filter yang relevan per laporan (mencegah form penuh pilihan yang tidak berpengaruh).
const FILTERS_BY_REPORT = {
  karyawan: ["project", "q", "status"],
  kepatuhan: ["project", "q", "horizon", "verification"],
  roster: ["project", "q", "dates", "plan_status", "approval"],
  aset: ["project", "q", "category", "lifecycle"],
  exit: ["project", "q", "dates", "case_state"],
};

const SUMMARY_LABELS = {
  total: "Total Baris",
  active: "Karyawan Aktif",
  inactive: "Karyawan Tidak Aktif",
  expired: "Kedaluwarsa",
  due_soon: "Akan Berakhir",
  confirmed: "Rencana Terkonfirmasi",
  pending_approval: "Menunggu Persetujuan HR",
  unassigned: "Belum Ada Pemegang",
  open: "Kasus Berjalan",
  completed: "Kasus Selesai",
  outstanding_assets: "Aset Belum Kembali",
};

const DATE_KEYS = new Set(["join_date", "expiry_date", "off_start", "off_end", "depart_date",
  "return_date", "acquisition_date", "request_date", "last_working_date"]);
const CURRENCY_KEYS = new Set(["acquisition_value"]);

const emptyFilters = {
  project_id: "", q: "", status: "", horizon_days: "90", verification_state: "",
  date_from: "", date_to: "", plan_status: "", approval_state: "",
  category_id: "", lifecycle_state: "", case_state: "",
};

const applyHorizon = (kind) => kind === "kepatuhan";

const buildParams = (kind, filters) => {
  const shown = FILTERS_BY_REPORT[kind] || [];
  const params = {};
  const allow = (key) => shown.includes(key);
  if (allow("project") && filters.project_id) params.project_id = filters.project_id;
  if (allow("q") && filters.q.trim()) params.q = filters.q.trim();
  if (allow("status") && filters.status) params.status = filters.status;
  if (applyHorizon(kind) && filters.horizon_days) params.horizon_days = filters.horizon_days;
  if (allow("verification") && filters.verification_state) params.verification_state = filters.verification_state;
  if (allow("dates")) {
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;
  }
  if (allow("plan_status") && filters.plan_status) params.plan_status = filters.plan_status;
  if (allow("approval") && filters.approval_state) params.approval_state = filters.approval_state;
  if (allow("category") && filters.category_id) params.category_id = filters.category_id;
  if (allow("lifecycle") && filters.lifecycle_state) params.lifecycle_state = filters.lifecycle_state;
  if (allow("case_state") && filters.case_state) params.case_state = filters.case_state;
  return params;
};

const cellValue = (column, row) => {
  const value = row[column.key];
  if (value === null || value === undefined || value === "") return "-";
  if (CURRENCY_KEYS.has(column.key)) return formatCurrency(value);
  if (DATE_KEYS.has(column.key)) return formatDate(value);
  return String(value);
};

const ReportsPage = () => {
  const [catalog, setCatalog] = useState({ items: [], options: {}, can_export: false });
  const [kind, setKind] = useState("karyawan");
  const [filters, setFilters] = useState(emptyFilters);
  const [debounced, setDebounced] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(filters.q), 350);
    return () => clearTimeout(t);
  }, [filters.q]);

  useEffect(() => {
    api.get("/reports")
      .then(({ data: payload }) => {
        setCatalog(payload);
        if (payload.items?.length && !payload.items.some((i) => i.key === kind)) {
          setKind(payload.items[0].key);
        }
      })
      .catch((err) => setError(errorMessage(err, "Katalog laporan tidak dapat dimuat.")));
    document.title = "Pusat Laporan · HRIS Suite";
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const active = useMemo(
    () => catalog.items.find((i) => i.key === kind) || null,
    [catalog.items, kind]
  );

  const params = useMemo(
    () => buildParams(kind, { ...filters, q: debounced }),
    [kind, filters, debounced]
  );

  const load = useCallback(async () => {
    if (!kind) return;
    setLoading(true);
    setError("");
    try {
      const { data: payload } = await api.get(`/reports/${kind}`, { params });
      setData(payload);
    } catch (err) {
      setError(errorMessage(err, "Laporan tidak dapat dimuat."));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [kind, params]);

  useEffect(() => { load(); }, [load]);

  const exportReport = async () => {
    if (!catalog.can_export) return;
    setExporting(true);
    try {
      const res = await api.get(`/reports/${kind}/export`, { params, responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${(active?.title || "Laporan").replace(/\s+/g, "-")}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      toast.success("Laporan diunduh dalam format Excel.");
    } catch (err) {
      toast.error(errorMessage(err, "Laporan gagal diekspor."));
    } finally {
      setExporting(false);
    }
  };

  const shown = FILTERS_BY_REPORT[kind] || [];
  const show = (key) => shown.includes(key);
  const options = catalog.options || {};
  const summary = data?.summary || {};
  const summaryEntries = Object.entries(summary).filter(
    ([key, value]) => value !== null && value !== undefined && typeof value !== "boolean" && key !== "value_visible"
  );

  return (
    <>
      <PageHeader
        title="Pusat Laporan"
        subtitle="Lima laporan lintas modul dengan filter organisasi dan ekspor Excel. Cakupan data mengikuti peran Anda."
        icon={BarChart3}
        actions={
          catalog.can_export && (
            <Button onClick={exportReport} disabled={exporting || loading || !data} data-testid="reports-export">
              <Download className="mr-2 h-4 w-4" />
              {exporting ? "Menyiapkan…" : "Ekspor Excel"}
            </Button>
          )
        }
      />
      <PageBody>
        <div
          className="flex max-w-full snap-x gap-1.5 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
          data-testid="reports-tabs"
          role="tablist"
          aria-label="Jenis laporan"
        >
          {catalog.items.map((item) => {
            const Icon = REPORT_ICONS[item.key] || BarChart3;
            const isActive = item.key === kind;
            return (
              <button
                key={item.key}
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => { setKind(item.key); setFilters(emptyFilters); setDebounced(""); }}
                data-testid={`reports-tab-${item.key}`}
                className={cn(
                  "inline-flex shrink-0 snap-start items-center gap-1.5 whitespace-nowrap rounded-lg border px-3 py-1.5 text-[13px] font-semibold",
                  "transition-[background-color,color,box-shadow,border-color] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
                  isActive
                    ? "border-[hsl(var(--primary-active))] bg-[image:var(--gradient-primary)] text-white shadow-[var(--shadow-button-primary)]"
                    : "border-border bg-card text-ink-2 hover:bg-[hsl(var(--surface-2))] hover:text-ink-1"
                )}
              >
                <Icon className="h-4 w-4 shrink-0" strokeWidth={1.75} />
                {item.title.replace("Laporan ", "")}
              </button>
            );
          })}
        </div>

        {active?.description && (
          <p className="text-[12.5px] text-muted-foreground" data-testid="reports-description">
            {active.description}
          </p>
        )}

        <Card className="border-border bg-card p-4" data-testid="reports-filters">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {show("project") && (
              <div>
                <Label htmlFor="rep-project" className="text-[13px]">Project</Label>
                <select id="rep-project" className={`${selectClass} mt-1`} value={filters.project_id}
                  onChange={(e) => setFilters((f) => ({ ...f, project_id: e.target.value }))}
                  data-testid="reports-project">
                  <option value="">Semua project</option>
                  {(options.projects || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
            )}
            {show("status") && (
              <div>
                <Label htmlFor="rep-status" className="text-[13px]">Status Data</Label>
                <select id="rep-status" className={`${selectClass} mt-1`} value={filters.status}
                  onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
                  data-testid="reports-status">
                  <option value="">Semua status</option>
                  <option value="active">Aktif</option>
                  <option value="inactive">Tidak Aktif</option>
                </select>
              </div>
            )}
            {show("horizon") && (
              <div>
                <Label htmlFor="rep-horizon" className="text-[13px]">Horizon (hari)</Label>
                <Input id="rep-horizon" type="number" min={1} max={730} className="mt-1"
                  value={filters.horizon_days}
                  onChange={(e) => setFilters((f) => ({ ...f, horizon_days: e.target.value }))}
                  data-testid="reports-horizon" />
              </div>
            )}
            {show("verification") && (
              <div>
                <Label htmlFor="rep-verification" className="text-[13px]">Status Verifikasi</Label>
                <select id="rep-verification" className={`${selectClass} mt-1`} value={filters.verification_state}
                  onChange={(e) => setFilters((f) => ({ ...f, verification_state: e.target.value }))}
                  data-testid="reports-verification">
                  <option value="">Semua status</option>
                  {(options.verification_states || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
            )}
            {show("plan_status") && (
              <div>
                <Label htmlFor="rep-plan" className="text-[13px]">Status Rencana</Label>
                <select id="rep-plan" className={`${selectClass} mt-1`} value={filters.plan_status}
                  onChange={(e) => setFilters((f) => ({ ...f, plan_status: e.target.value }))}
                  data-testid="reports-plan-status">
                  <option value="">Semua status</option>
                  {(options.plan_statuses || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
            )}
            {show("approval") && (
              <div>
                <Label htmlFor="rep-approval" className="text-[13px]">Persetujuan HR</Label>
                <select id="rep-approval" className={`${selectClass} mt-1`} value={filters.approval_state}
                  onChange={(e) => setFilters((f) => ({ ...f, approval_state: e.target.value }))}
                  data-testid="reports-approval">
                  <option value="">Semua status</option>
                  {(options.approval_states || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
            )}
            {show("category") && (
              <div>
                <Label htmlFor="rep-category" className="text-[13px]">Kategori Aset</Label>
                <select id="rep-category" className={`${selectClass} mt-1`} value={filters.category_id}
                  onChange={(e) => setFilters((f) => ({ ...f, category_id: e.target.value }))}
                  data-testid="reports-category">
                  <option value="">Semua kategori</option>
                  {(options.asset_categories || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
            )}
            {show("lifecycle") && (
              <div>
                <Label htmlFor="rep-lifecycle" className="text-[13px]">Status Aset</Label>
                <select id="rep-lifecycle" className={`${selectClass} mt-1`} value={filters.lifecycle_state}
                  onChange={(e) => setFilters((f) => ({ ...f, lifecycle_state: e.target.value }))}
                  data-testid="reports-lifecycle">
                  <option value="">Semua status</option>
                  {(options.lifecycle_states || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
            )}
            {show("case_state") && (
              <div>
                <Label htmlFor="rep-case" className="text-[13px]">Status Kasus</Label>
                <select id="rep-case" className={`${selectClass} mt-1`} value={filters.case_state}
                  onChange={(e) => setFilters((f) => ({ ...f, case_state: e.target.value }))}
                  data-testid="reports-case-state">
                  <option value="">Semua status</option>
                  {(options.case_states || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
            )}
            {show("dates") && (
              <>
                <div>
                  <Label htmlFor="rep-from" className="text-[13px]">Dari Tanggal</Label>
                  <Input id="rep-from" type="date" className="mt-1" value={filters.date_from}
                    onChange={(e) => setFilters((f) => ({ ...f, date_from: e.target.value }))}
                    data-testid="reports-date-from" />
                </div>
                <div>
                  <Label htmlFor="rep-to" className="text-[13px]">Sampai Tanggal</Label>
                  <Input id="rep-to" type="date" className="mt-1" value={filters.date_to}
                    onChange={(e) => setFilters((f) => ({ ...f, date_to: e.target.value }))}
                    data-testid="reports-date-to" />
                </div>
              </>
            )}
            <div className={cn(shown.includes("q") ? "" : "hidden")}>
              <Label htmlFor="rep-search" className="text-[13px]">Cari</Label>
              <div className="relative mt-1">
                <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input id="rep-search" className="pl-8" placeholder="Nama / nomor karyawan"
                  value={filters.q}
                  onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))}
                  data-testid="reports-search" />
              </div>
            </div>
            <div className="flex items-end gap-2">
              <Button variant="outline" onClick={load} disabled={loading} data-testid="reports-refresh">
                <RefreshCw className="mr-1.5 h-4 w-4" />Muat ulang
              </Button>
              <Button variant="ghost" onClick={() => { setFilters(emptyFilters); setDebounced(""); }}
                data-testid="reports-reset">
                Reset
              </Button>
            </div>
          </div>
          {data?.scope_label && (
            <p className="mt-2 text-[11px] text-muted-foreground" data-testid="reports-scope">
              Cakupan data: {data.scope_label}
              {data.generated_at ? ` · dibuat ${formatDateTime(data.generated_at)}` : ""}
            </p>
          )}
        </Card>

        {summaryEntries.length > 0 && (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4" data-testid="reports-summary">
            {summaryEntries.map(([key, value]) => (
              <Card key={key} className="border-border bg-card p-3">
                <p className="text-[12px] text-muted-foreground">{SUMMARY_LABELS[key] || key}</p>
                <p className="mt-1 text-2xl font-semibold tabular-nums">{value ?? 0}</p>
              </Card>
            ))}
          </div>
        )}

        {data?.note && (
          <div className="rounded-lg border border-warning-border bg-warning-soft px-3 py-2 text-sm text-warning"
            data-testid="reports-note">
            {data.note}
          </div>
        )}

        {loading ? (
          <Skeleton className="h-64 w-full rounded-xl" />
        ) : error ? (
          <Card className="space-y-3 p-4" role="alert" data-testid="reports-error">
            <p className="text-sm">{error}</p>
            <Button variant="outline" onClick={load}>Coba lagi</Button>
          </Card>
        ) : !data || data.items.length === 0 ? (
          <Card className="flex flex-col items-center gap-2 p-8 text-center" data-testid="reports-empty">
            <BarChart3 className="h-8 w-8 text-muted-foreground" />
            <p className="text-sm font-medium">Tidak ada data untuk filter ini.</p>
            <p className="text-[13px] text-muted-foreground">
              Ubah filter atau reset untuk melihat seluruh data dalam cakupan Anda.
            </p>
          </Card>
        ) : (
          <Card className="border-border bg-card" data-testid="reports-table-card">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5">
              <p className="text-[13px] font-semibold text-ink-1">{data.title}</p>
              <Badge variant="outline" data-testid="reports-total">{data.total} baris</Badge>
            </div>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    {data.columns.map((col) => (
                      <TableHead key={col.key} className="whitespace-nowrap">{col.label}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((row, index) => (
                    <TableRow key={row.case_number || row.asset_code || `${row.employee_number || "row"}-${index}`}
                      data-testid={`reports-row-${index}`}>
                      {data.columns.map((col) => (
                        <TableCell key={col.key} className="whitespace-nowrap text-[12.5px]">
                          {cellValue(col, row)}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </Card>
        )}
      </PageBody>
    </>
  );
};

export default ReportsPage;
