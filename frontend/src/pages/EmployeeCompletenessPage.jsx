import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  CheckCircle2, ClipboardCheck, Clock3, Gauge, Loader2, Plus, RefreshCw, Settings2, ShieldCheck, Trash2, Undo2, UserRound, Users,
} from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import DataTable, { FilterBar, FilterSelect, Pagination, TableCard } from "@/components/common/DataTable";
import DetailDrawer from "@/components/common/DetailDrawer";
import {
  CompletenessBreakdown, CompletenessStatusBadge, LEVEL_META, LevelBadge, PendingBadge, formatEvaluated,
} from "@/components/employees/CompletenessCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const SCOPE_SOURCES = {
  branch: "/master/branches/options", position: "/master/positions/options", project: "/master/projects/options",
  work_location: "/master/work-locations/options", department: "/master/departments/options", division: "/master/divisions/options",
  job_grade: "/master/job-grades/options", employment_status: "/master/employment-statuses/options",
  employee_status: "/employee-statuses",
};
const CATEGORY_OPTIONS = [["ACTIVE", "Aktif"], ["STANDBY", "Standby"], ["INACTIVE", "Tidak aktif"]];
const SCORE_RANGES = [
  { value: "0-49", label: "0 – 49%", min: 0, max: 49.9 },
  { value: "50-79", label: "50 – 79%", min: 50, max: 79.9 },
  { value: "80-99", label: "80 – 99%", min: 80, max: 99.9 },
  { value: "100", label: "100%", min: 100, max: 100 },
];
const EMPTY_FILTERS = { project_id: "", department_id: "", division_id: "", employee_status_id: "", completeness_status: "",
  score: "", missing: "", pending: "" };

/* ------------------------------------------------------------------ status evaluasi (dipakai Ringkasan & Master) */
function PendingBanner({ summary, canConfigure, onReevaluate, busy }) {
  if (!summary || (!summary.refresh_running && !summary.pending)) return null;
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-info-border bg-info-soft p-3 sm:flex-row sm:items-center sm:justify-between"
      data-testid="completeness-pending-banner" role="status">
      <div className="flex items-start gap-2 text-sm">
        {summary.refresh_running ? <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-info" /> : <Clock3 className="mt-0.5 h-4 w-4 shrink-0 text-info" />}
        <span>
          {summary.refresh_running
            ? "Hasil kelengkapan sedang dievaluasi ulang di latar belakang. Halaman ini akan diperbarui otomatis."
            : <><b data-numeric="true" data-testid="completeness-pending-count">{summary.pending}</b> hasil karyawan menunggu evaluasi ulang karena aturan atau master data berubah.</>}
        </span>
      </div>
      {!summary.refresh_running && canConfigure && (
        <Button size="sm" variant="outline" className="bg-card" onClick={onReevaluate} disabled={busy} data-testid="completeness-pending-reevaluate">
          <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", busy && "animate-spin")} />Evaluasi Ulang Sekarang
        </Button>
      )}
    </div>
  );
}

const Kpi = ({ icon: Icon, label, value, meta, tone = "primary", testId }) => (
  <Card className="shadow-card" data-testid={testId}>
    <CardContent className="p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[13px] font-medium text-muted-foreground">{label}</p>
        <span className={cn("flex h-9 w-9 items-center justify-center rounded-lg border", {
          primary: "border-primary-border bg-primary-soft text-primary", success: "border-success-border bg-success-soft text-success",
          warning: "border-warning-border bg-warning-soft text-warning", info: "border-info-border bg-info-soft text-info",
        }[tone])}><Icon className="h-4 w-4" /></span>
      </div>
      <p className="mt-3 text-[28px] font-semibold leading-[1.1] tracking-[-0.02em]" data-numeric="true" data-testid={`${testId}-value`}>{value}</p>
      {meta && <p className="mt-1 text-meta">{meta}</p>}
    </CardContent>
  </Card>
);

/* ------------------------------------------------------------------ drawer detail kekurangan */
function DetailPanel({ row, onClose, onChanged }) {
  const navigate = useNavigate();
  const { can } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    setError(null);
    try { setData((await api.get(`/employees/${row.employee_id}/completeness`)).data); } catch (e) { setError(errorMessage(e)); }
  }, [row.employee_id]);
  useEffect(() => { setData(null); load(); }, [load]);
  const reevaluate = async () => {
    setBusy(true);
    try {
      const { data: res } = await api.post(`/employees/${row.employee_id}/completeness/reevaluate`);
      toast.success(res.message); await load(); onChanged();
    } catch (e) { toast.error(errorMessage(e)); } finally { setBusy(false); }
  };
  const openTab = (tab) => navigate(`/employees/${row.employee_id}?tab=${tab}`);
  const missingReq = (data?.items || []).filter((i) => i.level === "REQUIRED" && !["COMPLETE", "NOT_APPLICABLE", "OFF"].includes(i.status)).length;
  return (
    <DetailDrawer open onOpenChange={(o) => !o && onClose()} testId="completeness-detail-drawer" className="sm:max-w-lg"
      title={row.full_name} description={`${row.employee_number || "-"} · ${row.project || "Tanpa proyek"}`}
      footer={<>
        <Button variant="outline" size="sm" onClick={() => navigate(`/employees/${row.employee_id}`)} data-testid="completeness-detail-open-profile">
          <UserRound className="mr-1.5 h-4 w-4" />Buka Profil</Button>
        {can("employee", "edit") && (
          <Button size="sm" onClick={reevaluate} disabled={busy || !data} data-testid="completeness-detail-reevaluate">
            <RefreshCw className={cn("mr-1.5 h-4 w-4", busy && "animate-spin")} />{busy ? "Mengevaluasi…" : "Evaluasi Ulang"}</Button>
        )}
      </>}>
      {error ? (
        <div className="space-y-2 text-sm" data-testid="completeness-detail-error"><p className="text-danger">{error}</p>
          <Button size="sm" variant="outline" onClick={load} data-testid="completeness-detail-retry">Coba lagi</Button></div>
      ) : !data ? (
        <div className="space-y-3" data-testid="completeness-detail-loading"><Skeleton className="h-8 w-24" /><Skeleton className="h-2 w-full" /><Skeleton className="h-40 w-full" /></div>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <CompletenessStatusBadge status={data.completeness_status} testId="completeness-detail-status" />
            {data.is_stale && <PendingBadge testId="completeness-detail-pending" />}
          </div>
          {data.completeness_status !== "EXCLUDED" && (
            <div className="space-y-1.5">
              <div className="flex items-baseline justify-between">
                <span className="text-meta">{data.required_fulfilled} dari {data.required_total} data wajib terpenuhi · {missingReq} kurang</span>
                <span className="text-xl font-semibold" data-numeric="true" data-testid="completeness-detail-score">{data.score_pct}%</span>
              </div>
              <Progress value={Number(data.score_pct) || 0} className="h-2" aria-label="Persentase kelengkapan" />
            </div>
          )}
          <div className="flex flex-wrap gap-3 text-meta">
            <span className="flex items-center gap-1.5"><LevelBadge level="REQUIRED" />dihitung dalam skor</span>
            <span className="flex items-center gap-1.5"><LevelBadge level="RECOMMENDED" />tidak memengaruhi skor</span>
          </div>
          {data.completeness_status === "EXCLUDED"
            ? <p className="text-sm text-muted-foreground">Karyawan nonaktif tidak dihitung dalam kelengkapan data.</p>
            : <CompletenessBreakdown data={data} mode="all" onOpenTab={openTab} testId="completeness-detail-breakdown" />}
          <p className="text-meta" data-testid="completeness-detail-evaluated">Evaluasi terakhir: {formatEvaluated(data.evaluated_at)}</p>
        </div>
      )}
    </DetailDrawer>
  );
}

/* ------------------------------------------------------------------ tab Ringkasan / Monitoring */
function SummaryTab({ summary, summaryError, reloadSummary, catalog, canConfigure, onReevaluate, busy, refreshToken }) {
  const [lookups, setLookups] = useState(null);
  const [statuses, setStatuses] = useState([]);
  const [list, setList] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(20);
  const [detail, setDetail] = useState(null);

  useEffect(() => { const t = setTimeout(() => setDebounced(search.trim()), 350); return () => clearTimeout(t); }, [search]);
  useEffect(() => {
    api.get("/employees/catalog").then(({ data }) => setLookups(data)).catch(() => setLookups({}));
    api.get("/employee-statuses", { params: { active: "true" } }).then(({ data }) => setStatuses(data.items || [])).catch(() => setStatuses([]));
  }, []);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const params = { page, limit };
      if (debounced) params.q = debounced;
      ["project_id", "department_id", "division_id", "employee_status_id", "completeness_status", "missing"].forEach((k) => {
        if (filters[k]) params[k] = filters[k];
      });
      const range = SCORE_RANGES.find((r) => r.value === filters.score);
      if (range) { params.score_min = range.min; params.score_max = range.max; }
      if (filters.pending === "yes") params.pending = true;
      setList((await api.get("/completeness/employees", { params })).data);
    } catch (e) { setError(errorMessage(e)); } finally { setLoading(false); }
  }, [page, limit, debounced, filters]);
  useEffect(() => { load(); }, [load, refreshToken]);

  const setF = (k, v) => { setFilters((p) => ({ ...p, [k]: v })); setPage(1); };
  const opts = (key) => (lookups?.[key] || []).map((o) => ({ value: o.id, label: o.name }));
  const reqOptions = useMemo(() => (catalog?.requirements || []).filter((r) => r.level === "REQUIRED")
    .map((r) => ({ value: r.code, label: r.label })), [catalog]);
  const activeCount = Object.values(filters).filter(Boolean).length + (debounced ? 1 : 0);
  const totalPages = Math.max(1, Math.ceil((list?.total || 0) / limit));

  const columns = [
    { key: "full_name", header: "Karyawan", className: "min-w-[11rem]", render: (r) => (
      <div className="min-w-0"><div className="font-medium" data-testid={`completeness-row-name-${r.employee_id}`}>{r.full_name}</div>
        <div className="font-mono text-[12px] text-muted-foreground">{r.employee_number || "-"}</div></div>) },
    { key: "project", header: "Proyek", render: (r) => r.project || <span className="text-muted-foreground">-</span> },
    { key: "department", header: "Departemen", hideOnMobile: true, render: (r) => r.department || <span className="text-muted-foreground">-</span> },
    { key: "division", header: "Divisi", hideOnMobile: true, render: (r) => r.division || <span className="text-muted-foreground">-</span> },
    { key: "employee_status", header: "Status Karyawan", render: (r) => r.employee_status || <span className="text-muted-foreground">-</span> },
    { key: "score_pct", header: "Kelengkapan", className: "min-w-[9rem]", render: (r) => (r.score_pct === null
      ? <span className="text-muted-foreground">-</span>
      : <div className="flex items-center gap-2"><Progress value={Number(r.score_pct)} className="h-2 w-20" aria-label="Kelengkapan" />
        <span className="text-[13px] font-medium" data-numeric="true" data-testid={`completeness-row-score-${r.employee_id}`}>{r.score_pct}%</span></div>) },
    { key: "completeness_status", header: "Status", render: (r) => (
      <div className="flex flex-wrap gap-1"><CompletenessStatusBadge status={r.completeness_status} testId={`completeness-row-status-${r.employee_id}`} />
        {r.pending && <PendingBadge testId={`completeness-row-pending-${r.employee_id}`} />}</div>) },
    { key: "missing_count", header: "Data kurang", align: "right", render: (r) => (
      <span data-numeric="true" className={cn("font-medium", r.missing_count ? "text-foreground" : "text-muted-foreground")}
        data-testid={`completeness-row-missing-${r.employee_id}`}>{r.missing_count}</span>) },
    { key: "evaluated_at", header: "Evaluasi terakhir", hideOnMobile: true, render: (r) => <span className="whitespace-nowrap text-meta">{formatEvaluated(r.evaluated_at)}</span> },
  ];

  return (
    <div className="space-y-4">
      {summaryError ? (
        <Card data-testid="completeness-summary-error"><CardContent className="flex flex-wrap items-center justify-between gap-3 p-4 text-sm">
          <span className="text-danger">Ringkasan belum dapat dimuat. {summaryError}</span>
          <Button variant="outline" size="sm" onClick={reloadSummary} data-testid="completeness-summary-retry">Coba lagi</Button></CardContent></Card>
      ) : !summary ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5" data-testid="completeness-summary-loading">
          {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-[112px] w-full" />)}</div>
      ) : (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5" data-testid="completeness-summary">
          <Kpi icon={Users} label="Total Karyawan" value={summary.total} testId="summary-total"
            meta={summary.counts?.EXCLUDED ? `${summary.counts.EXCLUDED} nonaktif tidak dihitung` : "Karyawan yang dievaluasi"} />
          <Kpi icon={CheckCircle2} tone="success" label="Lengkap" value={summary.counts?.LENGKAP ?? 0} testId="summary-count-LENGKAP" />
          <Kpi icon={ClipboardCheck} tone="warning" label="Belum Lengkap" value={summary.counts?.BELUM_LENGKAP ?? 0} testId="summary-count-BELUM_LENGKAP" />
          <Kpi icon={Clock3} tone="info" label="Menunggu Evaluasi" value={summary.pending ?? 0} testId="summary-pending"
            meta={summary.refresh_running ? "Sedang dievaluasi…" : summary.not_evaluated ? `${summary.not_evaluated} belum pernah dievaluasi` : null} />
          <Kpi icon={Gauge} label="Rata-rata Kelengkapan" value={summary.average_score === null ? "-" : `${summary.average_score}%`} testId="summary-average"
            meta="Dari karyawan yang dihitung" />
        </div>
      )}
      <PendingBanner summary={summary} canConfigure={canConfigure} onReevaluate={onReevaluate} busy={busy} />
      {summary?.top_missing?.length > 0 && (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-section-title">Data wajib yang paling sering kurang</CardTitle></CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {summary.top_missing.slice(0, 10).map((m) => (
              <Button key={m.code} size="sm" variant={filters.missing === m.code ? "default" : "outline"} data-testid={`top-missing-${m.code}`}
                onClick={() => setF("missing", filters.missing === m.code ? "" : m.code)}>
                {m.label}<Badge variant="secondary" className="ml-2" data-numeric="true">{m.count}</Badge>
              </Button>
            ))}
          </CardContent>
        </Card>
      )}
      <FilterBar search={search} onSearchChange={(v) => { setSearch(v); setPage(1); }} searchPlaceholder="Cari nama atau nomor karyawan"
        showReset={activeCount > 0} activeFilterCount={activeCount} onReset={() => { setFilters(EMPTY_FILTERS); setSearch(""); setPage(1); }}>
        <FilterSelect label="Proyek" value={filters.project_id} onChange={(v) => setF("project_id", v)} options={opts("projects")} allLabel="Semua proyek" testId="filter-project" />
        <FilterSelect label="Departemen" value={filters.department_id} onChange={(v) => setF("department_id", v)} options={opts("departments")} allLabel="Semua departemen" testId="filter-department" />
        <FilterSelect label="Divisi" value={filters.division_id} onChange={(v) => setF("division_id", v)} options={opts("divisions")} allLabel="Semua divisi" testId="filter-division" />
        <FilterSelect label="Status Karyawan" value={filters.employee_status_id} onChange={(v) => setF("employee_status_id", v)}
          options={statuses.map((s) => ({ value: s.id, label: s.name }))} allLabel="Semua status" testId="filter-employee-status" />
        <FilterSelect label="Kelengkapan" value={filters.completeness_status} onChange={(v) => setF("completeness_status", v)}
          options={[{ value: "LENGKAP", label: "Lengkap" }, { value: "BELUM_LENGKAP", label: "Belum lengkap" }, { value: "EXCLUDED", label: "Tidak dihitung (nonaktif)" }]}
          allLabel="Semua" testId="filter-completeness-status" />
        <FilterSelect label="Rentang kelengkapan" value={filters.score} onChange={(v) => setF("score", v)}
          options={SCORE_RANGES.map((r) => ({ value: r.value, label: r.label }))} allLabel="Semua rentang" testId="filter-score-range" />
        <FilterSelect label="Data yang kurang" value={filters.missing} onChange={(v) => setF("missing", v)} options={reqOptions}
          allLabel="Semua data" testId="filter-missing" />
        <FilterSelect label="Menunggu evaluasi" value={filters.pending} onChange={(v) => setF("pending", v)}
          options={[{ value: "yes", label: "Hanya yang menunggu" }]} allLabel="Semua" testId="filter-pending" />
      </FilterBar>
      <TableCard>
        {error ? (
          <div className="flex flex-wrap items-center justify-between gap-3 p-4 text-sm" data-testid="completeness-list-error">
            <span className="text-danger">Daftar belum dapat dimuat. {error}</span>
            <Button size="sm" variant="outline" onClick={load} data-testid="completeness-list-retry">Coba lagi</Button>
          </div>
        ) : (
          <>
            <DataTable columns={columns} rows={list?.items || []} loading={loading && !list} rowKey={(r) => r.employee_id}
              testId="completeness-table" onRowClick={(r) => setDetail(r)}
              emptyProps={{ icon: ClipboardCheck, title: "Tidak ada karyawan untuk filter ini.", description: "Ubah atau reset filter untuk melihat karyawan lain.",
                testId: "completeness-list-empty" }} />
            {list && list.total > 0 && (
              <Pagination page={page} totalPages={totalPages} total={list.total} limit={limit} onPageChange={setPage}
                onLimitChange={(n) => { setLimit(n); setPage(1); }} />
            )}
          </>
        )}
      </TableCard>
      {detail && <DetailPanel row={detail} onClose={() => setDetail(null)} onChanged={() => { load(); reloadSummary(); }} />}
    </div>
  );
}

/* ------------------------------------------------------------------ Master Kelengkapan */
const ScopeChips = ({ req, meta }) => {
  const inc = (req.scopes || []).filter((s) => s.mode === "INCLUDE");
  const exc = (req.scopes || []).filter((s) => s.mode === "EXCLUDE");
  const chip = (s) => <Badge key={s.id} variant="outline" className="mr-1 mt-1 font-normal">{meta.scope_types[s.scope_type]}: {s.scope_label}</Badge>;
  return (
    <div className="space-y-1 text-[12px]" data-testid={`req-scope-summary-${req.code}`}>
      {inc.length ? <div><span className="font-medium">Berlaku untuk:</span> {inc.map(chip)}</div>
        : <div className="text-muted-foreground">{req.applicability === "scoped_only" ? "Belum berlaku untuk siapa pun (atur cakupan)" : req.applicability_label}</div>}
      {exc.length > 0 && <div><span className="font-medium">Dikecualikan untuk:</span> {exc.map(chip)}</div>}
    </div>
  );
};

function ScopeDialog({ req, meta, onClose, onChanged, canConfigure }) {
  const [mode, setMode] = useState("INCLUDE");
  const [type, setType] = useState("project");
  const [options, setOptions] = useState([]);
  const [loadingOpts, setLoadingOpts] = useState(false);
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const scopeTypes = Object.entries(meta.scope_types || {}).filter(([k]) => k !== "company");
  useEffect(() => {
    setValue("");
    if (type === "business_status_category") { setOptions(CATEGORY_OPTIONS); return; }
    if (!SCOPE_SOURCES[type]) { setOptions([]); return; }
    setLoadingOpts(true);
    api.get(SCOPE_SOURCES[type], type === "employee_status" ? { params: { active: "true" } } : undefined)
      .then(({ data }) => setOptions((data.items || data || []).map((o) => [o.id, `${o.code ? `${o.code} – ` : ""}${o.name}`])))
      .catch(() => setOptions([])).finally(() => setLoadingOpts(false));
  }, [type]);
  const add = async () => {
    setSaving(true);
    try {
      await api.post("/completeness/scopes", { requirement_code: req.code, scope_type: type, scope_id: value, mode });
      toast.success("Cakupan disimpan. Hasil karyawan dievaluasi ulang di latar belakang."); setValue(""); onChanged();
    } catch (e) { toast.error(errorMessage(e)); } finally { setSaving(false); }
  };
  const remove = async (id) => {
    try { await api.delete(`/completeness/scopes/${id}`); toast.success("Cakupan dihapus. Hasil karyawan dievaluasi ulang di latar belakang."); onChanged(); }
    catch (e) { toast.error(errorMessage(e)); }
  };
  const section = (m, title, hint) => {
    const rows = (req.scopes || []).filter((s) => s.mode === m);
    return (
      <div className="space-y-2" data-testid={`scope-section-${m}`}>
        <div><p className="text-sm font-semibold">{title}</p><p className="text-meta">{hint}</p></div>
        {rows.length === 0 ? <p className="rounded-md border border-dashed border-border px-3 py-2 text-[13px] text-muted-foreground">Belum ada.</p> : (
          <ul className="space-y-1.5">{rows.map((s) => (
            <li key={s.id} className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-1.5 text-[13px]" data-testid={`scope-item-${s.id}`}>
              <span><span className="text-muted-foreground">{meta.scope_types[s.scope_type]}:</span> <b className="font-medium">{s.scope_label}</b></span>
              {canConfigure && <Button size="icon" variant="ghost" className="h-8 w-8" aria-label="Hapus cakupan" onClick={() => remove(s.id)} data-testid={`scope-delete-${s.id}`}>
                <Trash2 className="h-4 w-4" /></Button>}
            </li>))}</ul>
        )}
      </div>
    );
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl" data-testid="scope-dialog">
        <DialogHeader>
          <DialogTitle>Cakupan: {req.label}</DialogTitle>
          <DialogDescription>
            {req.applicability === "scoped_only"
              ? "Sertifikasi ini hanya dihitung untuk karyawan yang masuk daftar \"Berlaku untuk\". Tanpa daftar itu, sertifikasi tidak dihitung untuk siapa pun."
              : `Bawaan: ${req.applicability_label}. "Berlaku untuk" mempersempit ke kelompok tertentu; "Dikecualikan untuk" membebaskan kelompok tertentu.`}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {section("INCLUDE", "Berlaku untuk", "Hanya karyawan dalam kelompok ini yang wajib/dianjurkan melengkapi.")}
          {section("EXCLUDE", "Dikecualikan untuk", "Karyawan dalam kelompok ini tidak perlu melengkapi.")}
          {canConfigure && (
            <div className="space-y-2 rounded-lg border border-border bg-muted/40 p-3" data-testid="scope-form">
              <p className="text-sm font-semibold">Tambah cakupan</p>
              <div className="grid gap-2 sm:grid-cols-3">
                <Select value={mode} onValueChange={setMode}>
                  <SelectTrigger className="h-9 bg-card" data-testid="scope-mode" aria-label="Jenis cakupan"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="INCLUDE">Berlaku untuk</SelectItem><SelectItem value="EXCLUDE">Dikecualikan untuk</SelectItem></SelectContent>
                </Select>
                <Select value={type} onValueChange={setType}>
                  <SelectTrigger className="h-9 bg-card" data-testid="scope-type" aria-label="Berdasarkan"><SelectValue /></SelectTrigger>
                  <SelectContent>{scopeTypes.map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
                </Select>
                <Select value={value} onValueChange={setValue} disabled={loadingOpts}>
                  <SelectTrigger className="h-9 bg-card" data-testid="scope-value" aria-label="Pilih nilai">
                    <SelectValue placeholder={loadingOpts ? "Memuat…" : options.length ? "Pilih" : "Tidak ada data"} /></SelectTrigger>
                  <SelectContent>{options.map(([id, l]) => <SelectItem key={id} value={id}>{l}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} data-testid="scope-close">Tutup</Button>
          {canConfigure && <Button onClick={add} disabled={saving || !value} data-testid="scope-add">
            <Plus className="mr-1.5 h-4 w-4" />Simpan cakupan</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function MasterTab({ catalog, catalogError, reloadCatalog, canConfigure, summary, onReevaluate, busy, onRuleChanged }) {
  const [scopeCode, setScopeCode] = useState(null);
  const [savingCode, setSavingCode] = useState(null);
  const grouped = useMemo(() => (catalog ? catalog.categories.map((c) => ({ ...c, items: catalog.requirements.filter((r) => r.category === c.key) })) : []), [catalog]);
  const changed = async () => { await reloadCatalog(); onRuleChanged(); };
  const setLevel = async (code, level) => {
    setSavingCode(code);
    try { await api.put(`/completeness/rules/${encodeURIComponent(code)}`, { level }); toast.success("Level disimpan. Hasil karyawan dievaluasi ulang di latar belakang."); await changed(); }
    catch (e) { toast.error(errorMessage(e)); } finally { setSavingCode(null); }
  };
  const reset = async (code) => {
    setSavingCode(code);
    try { await api.delete(`/completeness/rules/${encodeURIComponent(code)}`); toast.success("Level dikembalikan ke bawaan."); await changed(); }
    catch (e) { toast.error(errorMessage(e)); } finally { setSavingCode(null); }
  };
  if (catalogError) return <Card data-testid="completeness-master-error"><CardContent className="flex flex-wrap items-center justify-between gap-3 p-4 text-sm">
    <span className="text-danger">Master kelengkapan belum dapat dimuat. {catalogError}</span>
    <Button variant="outline" size="sm" onClick={reloadCatalog} data-testid="completeness-master-retry">Coba lagi</Button></CardContent></Card>;
  if (!catalog) return <div className="space-y-3" data-testid="completeness-master-loading"><Skeleton className="h-24 w-full" /><Skeleton className="h-64 w-full" /></div>;
  const scopeReq = scopeCode && catalog.requirements.find((r) => r.code === scopeCode);
  return (
    <div className="space-y-4" data-testid="completeness-master">
      <PendingBanner summary={summary} canConfigure={canConfigure} onReevaluate={onReevaluate} busy={busy} />
      <div className="flex items-start gap-2 rounded-lg border border-border bg-card p-3 text-[13px] text-muted-foreground" data-testid="completeness-master-legend">
        {canConfigure ? <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" /> : <Settings2 className="mt-0.5 h-4 w-4 shrink-0" />}
        <span>
          {canConfigure ? "Atur level dan cakupan per perusahaan. " : <b className="text-foreground" data-testid="completeness-master-readonly">Mode baca saja. </b>}
          <b className="text-foreground">Wajib</b> dihitung dalam skor, <b className="text-foreground">Anjuran</b> hanya ditampilkan sebagai saran, <b className="text-foreground">Nonaktif</b> tidak diperiksa.
          Kode sistem requirement tidak dapat diubah.
        </span>
      </div>
      {grouped.map((g) => (
        <Card key={g.key} data-testid={`req-group-${g.key}`}>
          <CardHeader className="pb-2"><CardTitle className="text-section-title">{g.label}</CardTitle></CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <Table className="min-w-[760px]">
                <TableHeader><TableRow><TableHead>Requirement</TableHead><TableHead>Cakupan</TableHead>
                  <TableHead className="w-44">Level</TableHead><TableHead className="w-44 text-right">Aksi</TableHead></TableRow></TableHeader>
                <TableBody>
                  {g.items.length === 0 ? <TableRow><TableCell colSpan={4} className="text-sm text-muted-foreground">Belum ada requirement (tambahkan master terkait).</TableCell></TableRow>
                    : g.items.map((r) => (
                      <TableRow key={r.code} data-testid={`req-row-${r.code}`}>
                        <TableCell className="align-top"><div className="font-medium">{r.label}</div>
                          <div className="text-[12px] text-muted-foreground" title="Kode sistem (tidak dapat diubah)">
                            <span className="font-mono">{r.code}</span>{r.sensitive ? " · data sensitif" : ""}</div></TableCell>
                        <TableCell className="align-top"><ScopeChips req={r} meta={catalog} /></TableCell>
                        <TableCell className="align-top">
                          {canConfigure ? (
                            <Select value={r.level} onValueChange={(v) => setLevel(r.code, v)} disabled={savingCode === r.code}>
                              <SelectTrigger className="h-9" data-testid={`req-level-${r.code}`} aria-label={`Level ${r.label}`}><SelectValue /></SelectTrigger>
                              <SelectContent>{Object.entries(LEVEL_META).map(([k, m]) => <SelectItem key={k} value={k}>{m.label}</SelectItem>)}</SelectContent>
                            </Select>
                          ) : <LevelBadge level={r.level} testId={`req-level-badge-${r.code}`} />}
                          {r.is_overridden && <div className="mt-1 text-[12px] text-muted-foreground">Diubah · bawaan: {LEVEL_META[r.default_level]?.label}</div>}
                        </TableCell>
                        <TableCell className="align-top text-right">
                          <div className="flex justify-end gap-1">
                            <Button size="sm" variant="ghost" onClick={() => setScopeCode(r.code)} data-testid={`req-scope-${r.code}`}>
                              <Settings2 className="mr-1 h-4 w-4" />{canConfigure ? "Atur cakupan" : "Lihat cakupan"}</Button>
                            {canConfigure && r.is_overridden && <Button size="icon" variant="ghost" aria-label="Kembalikan level bawaan" onClick={() => reset(r.code)}
                              disabled={savingCode === r.code} data-testid={`req-reset-${r.code}`}><Undo2 className="h-4 w-4" /></Button>}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      ))}
      {scopeReq && <ScopeDialog req={scopeReq} meta={catalog} canConfigure={canConfigure} onClose={() => setScopeCode(null)} onChanged={changed} />}
    </div>
  );
}

/* ------------------------------------------------------------------ halaman */
export default function EmployeeCompletenessPage() {
  const { can } = useAuth();
  const canConfigure = can("employee_completeness", "configure");
  const [tab, setTab] = useState("summary");
  const [summary, setSummary] = useState(null);
  const [summaryError, setSummaryError] = useState(null);
  const [catalog, setCatalog] = useState(null);
  const [catalogError, setCatalogError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const watchUntil = useRef(0);
  const wasRunning = useRef(false);

  const reloadSummary = useCallback(async () => {
    try { setSummary((await api.get("/completeness/summary")).data); setSummaryError(null); }
    catch (e) { setSummaryError(errorMessage(e)); }
  }, []);
  const reloadCatalog = useCallback(async () => {
    try { setCatalog((await api.get("/completeness/catalog")).data); setCatalogError(null); }
    catch (e) { setCatalogError(errorMessage(e)); }
  }, []);
  useEffect(() => { reloadSummary(); reloadCatalog(); }, [reloadSummary, reloadCatalog]);

  // Polling ringan HANYA saat evaluasi latar belakang berjalan / baru saja ada perubahan aturan.
  useEffect(() => {
    if (!summary) return undefined;
    if (wasRunning.current && !summary.refresh_running) setRefreshToken((k) => k + 1); // selesai -> segarkan daftar
    wasRunning.current = !!summary.refresh_running;
    const watching = summary.refresh_running || (summary.pending > 0 && Date.now() < watchUntil.current);
    if (!watching) return undefined;
    const t = setTimeout(reloadSummary, 3000);
    return () => clearTimeout(t);
  }, [summary, reloadSummary]);

  const onRuleChanged = () => { watchUntil.current = Date.now() + 60000; reloadSummary(); };
  const reevaluate = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/completeness/reevaluate", {});
      toast.success(data.message); await reloadSummary(); setRefreshToken((k) => k + 1);
    } catch (e) { toast.error(errorMessage(e)); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title="Kelengkapan Data Karyawan" subtitle="Pantau data wajib yang belum lengkap dan atur Master Kelengkapan per perusahaan."
        actions={canConfigure && <Button variant="outline" onClick={reevaluate} disabled={busy || summary?.refresh_running} data-testid="completeness-reevaluate">
          <RefreshCw className={cn("mr-1.5 h-4 w-4", (busy || summary?.refresh_running) && "animate-spin")} />{busy ? "Mengevaluasi…" : "Evaluasi Ulang Semua"}</Button>} />
      <PageBody>
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList data-testid="completeness-tabs">
            <TabsTrigger value="summary" data-testid="tab-completeness-summary"><ClipboardCheck className="mr-1.5 h-4 w-4" />Monitoring</TabsTrigger>
            <TabsTrigger value="master" data-testid="tab-completeness-master"><Settings2 className="mr-1.5 h-4 w-4" />Master Kelengkapan</TabsTrigger>
          </TabsList>
          <TabsContent value="summary" className="mt-4">
            <SummaryTab summary={summary} summaryError={summaryError} reloadSummary={reloadSummary} catalog={catalog} canConfigure={canConfigure}
              onReevaluate={reevaluate} busy={busy} refreshToken={refreshToken} />
          </TabsContent>
          <TabsContent value="master" className="mt-4">
            <MasterTab catalog={catalog} catalogError={catalogError} reloadCatalog={reloadCatalog} canConfigure={canConfigure} summary={summary}
              onReevaluate={reevaluate} busy={busy} onRuleChanged={onRuleChanged} />
          </TabsContent>
        </Tabs>
      </PageBody>
    </>
  );
}
