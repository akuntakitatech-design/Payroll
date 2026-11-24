import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CalendarClock, Plane, RefreshCw, Undo2, Users } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { PageBody } from "@/components/common/PageHeader";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const selectClass = "h-9 w-full rounded-lg border border-input bg-card px-3 text-sm text-ink-1 shadow-[var(--shadow-input)] transition-[border-color,box-shadow] duration-150 hover:border-border-strong focus-visible:outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/25";

const Stat = ({ label, value, icon: Icon, tone = "default", testId }) => (
  <Card className="border-border bg-card p-3" data-testid={testId}>
    <div className="flex items-center justify-between gap-2">
      <p className="text-[12px] text-muted-foreground">{label}</p>
      <Icon className={`h-4 w-4 ${tone === "warning" ? "text-warning" : "text-muted-foreground"}`} />
    </div>
    <p className={`mt-1 text-2xl font-semibold tabular-nums ${tone === "warning" ? "text-warning" : ""}`}>{value ?? 0}</p>
  </Card>
);

const RosterReturningPage = () => {
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("");
  const [days, setDays] = useState("14");
  const [rows, setRows] = useState([]);
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/roster/projects")
      .then(({ data }) => setProjects(data.items || []))
      .catch(() => setProjects([]));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = { days: Number(days) || 14 };
      if (projectId) params.project_id = projectId;
      const { data } = await api.get("/roster/returning", { params });
      setRows(data.items || []);
      setCounts(data.counts || {});
    } catch (err) {
      setError(errorMessage(err, "Data karyawan yang akan kembali tidak dapat dimuat."));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [projectId, days]);

  useEffect(() => { load(); }, [load]);

  const dayLabel = (row) => {
    if (row.days_until_return === 0) return "Hari ini";
    if (row.days_until_return === 1) return "Besok";
    return `${row.days_until_return} hari lagi`;
  };

  return (
    <PageBody>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Sedang Cuti" value={counts.on_leave} icon={Users} testId="returning-stat-on-leave" />
        <Stat label="Kembali Hari Ini" value={counts.due_today} icon={CalendarClock} testId="returning-stat-today" />
        <Stat label="Kembali ≤ 7 Hari" value={counts.due_7d} icon={Undo2} testId="returning-stat-week" />
        <Stat label="Transport Belum Siap" value={counts.transport_missing} icon={Plane} tone="warning"
          testId="returning-stat-transport" />
      </div>

      <Card className="border-border bg-card p-4" data-testid="returning-controls">
        <div className="grid gap-3 lg:grid-cols-[1fr_200px_auto] lg:items-end">
          <div>
            <Label htmlFor="returning-project" className="text-[13px]">Project</Label>
            <select id="returning-project" className={`${selectClass} mt-1`} value={projectId}
              onChange={(e) => setProjectId(e.target.value)} data-testid="returning-project">
              <option value="">Semua project</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.code}</option>)}
            </select>
          </div>
          <div>
            <Label htmlFor="returning-days" className="text-[13px]">Rentang kembali</Label>
            <select id="returning-days" className={`${selectClass} mt-1`} value={days}
              onChange={(e) => setDays(e.target.value)} data-testid="returning-days">
              <option value="7">7 hari ke depan</option>
              <option value="14">14 hari ke depan</option>
              <option value="30">30 hari ke depan</option>
            </select>
          </div>
          <Button variant="outline" onClick={load} disabled={loading} data-testid="returning-refresh">
            <RefreshCw className="mr-1.5 h-4 w-4" />Muat ulang
          </Button>
        </div>
        <p className="mt-2 text-[11px] text-muted-foreground">
          Tanggal kembali mengikuti mobilisasi GA bila sudah diatur; jika belum, dipakai akhir periode off roster.
        </p>
      </Card>

      {loading ? (
        <Skeleton className="h-64 w-full rounded-xl" />
      ) : error ? (
        <Card className="space-y-3 p-4" role="alert" data-testid="returning-error">
          <p className="text-sm">{error}</p>
          <Button variant="outline" onClick={load}>Coba lagi</Button>
        </Card>
      ) : rows.length === 0 ? (
        <Card className="flex flex-col items-center gap-2 p-8 text-center" data-testid="returning-empty">
          <Undo2 className="h-8 w-8 text-muted-foreground" />
          <p className="text-sm font-medium">Tidak ada karyawan yang kembali dalam rentang ini.</p>
          <p className="text-[13px] text-muted-foreground">
            Ubah rentang atau pastikan rencana cuti project sudah dikonfirmasi (H-10).
          </p>
        </Card>
      ) : (
        <Card className="border-border bg-card" data-testid="returning-table-card">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Karyawan</TableHead>
                  <TableHead>Project</TableHead>
                  <TableHead>Periode Off</TableHead>
                  <TableHead>Kembali Pada</TableHead>
                  <TableHead>Sisa Hari</TableHead>
                  <TableHead>Transport</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => {
                  const mob = row.mobilization;
                  return (
                    <TableRow key={row.plan_id} data-testid={`returning-row-${row.plan_id}`}>
                      <TableCell>
                        <p className="font-medium">{row.employee_name}</p>
                        <p className="text-[11px] text-muted-foreground">{row.employee_number || "-"}</p>
                      </TableCell>
                      <TableCell>{row.project_name || "-"}</TableCell>
                      <TableCell className="text-[12px]">
                        {formatDate(row.off_start)} – {formatDate(row.off_end)}
                      </TableCell>
                      <TableCell className="text-[12px]">
                        <p className="font-medium">{formatDate(row.return_date)}</p>
                        {mob?.return_time && <p className="text-muted-foreground">{mob.return_time}</p>}
                      </TableCell>
                      <TableCell>
                        <Badge variant={row.days_until_return === 0 ? "warning" : "outline"}>
                          {dayLabel(row)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-[12px]">
                        {row.transport_ready ? (
                          <>
                            <p className="font-medium">{mob.return_mode_label}</p>
                            <p className="text-muted-foreground">
                              {mob.return_carrier || "-"}{mob.return_ticket ? ` · ${mob.return_ticket}` : ""}
                            </p>
                          </>
                        ) : (
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge variant="warning">Belum diatur</Badge>
                            <Button asChild size="sm" variant="ghost">
                              <Link to={`/modules/mobilization/mobilisasi${row.project_id ? `?project=${row.project_id}` : ""}`}>
                                Atur
                              </Link>
                            </Button>
                          </div>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant={row.on_leave ? "default" : "secondary"}>
                          {row.on_leave ? "Sedang cuti" : "Akan cuti"}
                        </Badge>
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
  );
};

export default RosterReturningPage;
