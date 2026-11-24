import React, { useCallback, useEffect, useMemo, useState } from "react";
import { CalendarRange, RefreshCw } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { PageBody } from "@/components/common/PageHeader";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const selectClass = "h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

const addDays = (iso, days) => {
  if (!iso) return null;
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
};

const RosterCalendarPage = () => {
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("");
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/roster/projects")
      .then(({ data: res }) => {
        setProjects(res.items || []);
        setProjectId((prev) => prev || res.items?.[0]?.id || "");
      })
      .catch((err) => setError(errorMessage(err, "Daftar project tidak dapat dimuat.")));
  }, []);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError("");
    try {
      const { data: res } = await api.get("/roster/calendar", { params: { project_id: projectId, month } });
      setData(res);
    } catch (err) {
      setData(null);
      setError(errorMessage(err, "Kalender roster tidak dapat dimuat."));
    } finally {
      setLoading(false);
    }
  }, [projectId, month]);

  useEffect(() => { load(); }, [load]);

  const summary = useMemo(() => {
    if (!data) return null;
    return `${data.active_employees} karyawan aktif · ${data.cycles.length} siklus off pada bulan ini`;
  }, [data]);

  return (
    <PageBody>
      <Card className="border-border bg-card p-4" data-testid="roster-calendar-controls">
        <div className="grid gap-3 md:grid-cols-[1fr_200px_auto] md:items-end">
          <div>
            <Label htmlFor="calendar-project" className="text-[13px]">Project</Label>
            <select id="calendar-project" className={`${selectClass} mt-1`} value={projectId}
              onChange={(e) => setProjectId(e.target.value)} data-testid="roster-calendar-project">
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.code}</option>)}
            </select>
          </div>
          <div>
            <Label htmlFor="calendar-month" className="text-[13px]">Bulan</Label>
            <Input id="calendar-month" type="month" className="mt-1" value={month}
              onChange={(e) => setMonth(e.target.value)} data-testid="roster-calendar-month" />
          </div>
          <Button variant="outline" onClick={load} disabled={loading || !projectId} data-testid="roster-calendar-refresh">
            <RefreshCw className="mr-1.5 h-4 w-4" />Muat ulang
          </Button>
        </div>
        {data && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-[12px] text-muted-foreground">
            <Badge variant="outline"><CalendarRange className="mr-1 h-3 w-3" />{data.pattern.name}</Badge>
            <span>{data.pattern.work_days} hari kerja / {data.pattern.off_days} hari off</span>
            <span>· POH {formatDate(data.start_date)}</span>
            <span>· {summary}</span>
          </div>
        )}
      </Card>

      {loading ? (
        <Skeleton className="h-64 w-full rounded-xl" />
      ) : error ? (
        <Card className="space-y-3 p-4" role="alert" data-testid="roster-calendar-error">
          <p className="text-sm">{error}</p>
          <Button variant="outline" onClick={load}>Coba lagi</Button>
        </Card>
      ) : !data ? null : !data.cycles.length ? (
        <Card className="p-5" data-testid="roster-calendar-empty">
          <p className="text-sm">Tidak ada siklus off pada bulan ini.</p>
        </Card>
      ) : (
        <Card className="border-border bg-card" data-testid="roster-calendar-table">
          <div className="table-scroll">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Siklus</TableHead>
                  <TableHead>Mulai Cuti</TableHead>
                  <TableHead>Selesai</TableHead>
                  <TableHead>Kembali Kerja</TableHead>
                  <TableHead className="text-right">Karyawan</TableHead>
                  <TableHead>Nama (sebagian)</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.cycles.map((cycle) => (
                  <TableRow key={cycle.cycle_no} data-testid={`roster-cycle-${cycle.cycle_no}`}>
                    <TableCell className="font-medium">#{cycle.cycle_no + 1}</TableCell>
                    <TableCell>{formatDate(cycle.off_start)}</TableCell>
                    <TableCell>{formatDate(cycle.off_end)}</TableCell>
                    <TableCell>{formatDate(addDays(cycle.off_end, 1))}</TableCell>
                    <TableCell className="text-right tabular-nums">{cycle.employee_count}</TableCell>
                    <TableCell className="text-[12px] text-muted-foreground">
                      {(cycle.employees || []).slice(0, 3).join(", ")}
                      {cycle.employees?.length > 3 ? ` +${cycle.employees.length - 3}` : ""}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </Card>
      )}
    </PageBody>
  );
};

export default RosterCalendarPage;
