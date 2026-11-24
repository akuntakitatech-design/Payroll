import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { History, RefreshCw, Search, UserMinus } from "lucide-react";
import { toast } from "sonner";

import { api, errorMessage } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { useAuth } from "@/lib/auth";
import { PageBody, PageHeader } from "@/components/common/PageHeader";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const selectClass =
  "h-9 w-full rounded-lg border border-input bg-card px-3 text-sm text-ink-1 shadow-[var(--shadow-input)] transition-[border-color,box-shadow] duration-150 hover:border-border-strong focus-visible:outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/25";

const STATES = {
  COMPLETED: { label: "Selesai", tone: "text-success" },
  CANCELLED: { label: "Dibatalkan", tone: "text-muted-foreground" },
};

const Stat = ({ label, value, tone = "default", testId }) => (
  <Card className="border-border bg-card p-3" data-testid={testId}>
    <p className="text-[12px] text-muted-foreground">{label}</p>
    <p className={`mt-1 text-2xl font-semibold tabular-nums ${tone === "success" ? "text-success" : ""}`}>
      {value ?? 0}
    </p>
  </Card>
);

const EmployeeExitHistoryPage = () => {
  const { can } = useAuth();
  const [items, setItems] = useState([]);
  const [counts, setCounts] = useState({ COMPLETED: 0, CANCELLED: 0 });
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [stateFilter, setStateFilter] = useState("");
  const [projectId, setProjectId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q), 350);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    document.title = "Histori Exit Clearance · HRIS Suite";
    api.get("/roster/projects")
      .then(({ data }) => setProjects(data.items || []))
      .catch(() => setProjects([]));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = {};
      if (stateFilter) params.state = stateFilter;
      if (projectId) params.project_id = projectId;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      if (debounced.trim()) params.q = debounced.trim();
      const { data } = await api.get("/exit-clearance/history", { params });
      setItems(data.items || []);
      setCounts(data.counts || { COMPLETED: 0, CANCELLED: 0 });
    } catch (err) {
      setError(errorMessage(err, "Histori exit clearance tidak dapat dimuat."));
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [stateFilter, projectId, dateFrom, dateTo, debounced]);

  useEffect(() => { load(); }, [load]);

  const total = items.length;
  const hasFilters = !!stateFilter || !!projectId || !!dateFrom || !!dateTo || !!debounced;
  const resetFilters = () => {
    setStateFilter("");
    setProjectId("");
    setDateFrom("");
    setDateTo("");
    setQ("");
  };

  const summary = useMemo(() => ([
    { key: "total", label: "Total Histori", value: total },
    { key: "completed", label: "Selesai", value: counts.COMPLETED, tone: "success" },
    { key: "cancelled", label: "Dibatalkan", value: counts.CANCELLED },
  ]), [total, counts]);

  return (
    <>
      <PageHeader
        title="Histori Exit Clearance"
        subtitle="Kasus yang sudah selesai atau dibatalkan, lengkap dengan progres checklist dan keputusannya."
        icon={History}
        actions={
          <Button asChild variant="outline">
            <Link to="/employees/exit-clearance">
              <UserMinus className="mr-1.5 h-4 w-4" />Exit Clearance
            </Link>
          </Button>
        }
      />
      <PageBody>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3" data-testid="exit-history-summary">
        {summary.map((s) => (
          <Stat key={s.key} label={s.label} value={s.value} tone={s.tone} testId={`exit-history-stat-${s.key}`} />
        ))}
      </div>

      <Card className="border-border bg-card p-4" data-testid="exit-history-controls">
        <div className="grid gap-3 lg:grid-cols-[1fr_170px_1fr_150px_150px_auto] lg:items-end">
          <div>
            <Label htmlFor="hx-search" className="text-[13px]">Cari</Label>
            <div className="relative mt-1">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input id="hx-search" className="pl-8" placeholder="No. kasus, nama, atau NIK"
                value={q} onChange={(e) => setQ(e.target.value)} data-testid="exit-history-search" />
            </div>
          </div>
          <div>
            <Label htmlFor="hx-project" className="text-[13px]">Project</Label>
            <select id="hx-project" className={`${selectClass} mt-1`} value={projectId}
              onChange={(e) => setProjectId(e.target.value)} data-testid="exit-history-project">
              <option value="">Semua project</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.code}</option>)}
            </select>
          </div>
          <div>
            <Label htmlFor="hx-state" className="text-[13px]">Status</Label>
            <select id="hx-state" className={`${selectClass} mt-1`} value={stateFilter}
              onChange={(e) => setStateFilter(e.target.value)} data-testid="exit-history-state">
              <option value="">Semua status</option>
              <option value="COMPLETED">Selesai</option>
              <option value="CANCELLED">Dibatalkan</option>
            </select>
          </div>
          <div>
            <Label htmlFor="hx-from" className="text-[13px]">Dari Tanggal</Label>
            <Input id="hx-from" type="date" className="mt-1" value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)} data-testid="exit-history-from" />
          </div>
          <div>
            <Label htmlFor="hx-to" className="text-[13px]">Sampai Tanggal</Label>
            <Input id="hx-to" type="date" className="mt-1" value={dateTo}
              onChange={(e) => setDateTo(e.target.value)} data-testid="exit-history-to" />
          </div>
          <div className="flex items-end gap-2">
            <Button variant="outline" onClick={load} disabled={loading} data-testid="exit-history-refresh">
              <RefreshCw className="mr-1.5 h-4 w-4" />Muat ulang
            </Button>
            {hasFilters && (
              <Button variant="ghost" onClick={resetFilters} data-testid="exit-history-reset">Reset</Button>
            )}
          </div>
        </div>
        <p className="mt-2 text-[11px] text-muted-foreground">
          Histori memuat kasus yang sudah <span className="font-medium">Selesai</span> atau{" "}
          <span className="font-medium">Dibatalkan</span>. Kasus berjalan tetap ada di halaman Exit Clearance.
        </p>
      </Card>

      {loading ? (
        <Skeleton className="h-64 w-full rounded-xl" />
      ) : error ? (
        <Card className="space-y-3 p-4" role="alert" data-testid="exit-history-error">
          <p className="text-sm">{error}</p>
          <Button variant="outline" onClick={load}>Coba lagi</Button>
        </Card>
      ) : items.length === 0 ? (
        <Card className="flex flex-col items-center gap-2 p-8 text-center" data-testid="exit-history-empty">
          <History className="h-8 w-8 text-muted-foreground" />
          <p className="text-sm font-medium">
            {hasFilters ? "Tidak ada histori yang cocok." : "Belum ada histori exit clearance."}
          </p>
          <p className="text-[13px] text-muted-foreground">
            {hasFilters
              ? "Ubah filter atau reset untuk melihat seluruh histori."
              : "Kasus yang sudah diselesaikan atau dibatalkan akan muncul di sini."}
          </p>
          {can("exit_clearance", "view") && (
            <Button asChild variant="outline" className="mt-1">
              <Link to="/employees/exit-clearance">
                <UserMinus className="mr-1.5 h-4 w-4" />Buka Exit Clearance
              </Link>
            </Button>
          )}
        </Card>
      ) : (
        <Card className="border-border bg-card" data-testid="exit-history-table-card">
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
                  <TableHead>Status</TableHead>
                  <TableHead>Diputuskan</TableHead>
                  <TableHead className="text-right">Aksi</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((row) => {
                  const st = STATES[row.case_state] || { label: row.case_state_label, tone: "" };
                  return (
                    <TableRow key={row.id} data-testid={`exit-history-row-${row.id}`}>
                      <TableCell className="font-medium">{row.case_number}</TableCell>
                      <TableCell>
                        <p className="font-medium">{row.employee_name}</p>
                        <p className="text-[11px] text-muted-foreground">{row.employee_number || "-"}</p>
                      </TableCell>
                      <TableCell>{row.project_name || "-"}</TableCell>
                      <TableCell className="text-[12px]">{row.exit_type_label}</TableCell>
                      <TableCell className="text-[12px]">{formatDate(row.last_working_date)}</TableCell>
                      <TableCell className="text-[12px] tabular-nums">
                        {row.progress?.done ?? 0}/{row.progress?.total ?? 0}
                      </TableCell>
                      <TableCell>
                        <span className={`text-[12px] font-medium ${st.tone}`}>{st.label}</span>
                      </TableCell>
                      <TableCell className="text-[12px]">
                        {row.decided_at || row.cancelled_at
                          ? formatDateTime(row.decided_at || row.cancelled_at)
                          : "-"}
                      </TableCell>
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
      </PageBody>
    </>
  );
};

export default EmployeeExitHistoryPage;
