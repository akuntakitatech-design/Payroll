import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, CalendarDays, CalendarRange, CheckCircle2, ClipboardList, Plane, Save, Users } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { PageBody } from "@/components/common/PageHeader";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

const selectClass = "h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

const Stat = ({ label, value, icon: Icon, tone = "default" }) => (
  <Card className="border-border bg-card p-3" data-testid={`roster-stat-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}>
    <div className="flex items-center justify-between gap-2">
      <p className="text-[12px] text-muted-foreground">{label}</p>
      <Icon className={`h-4 w-4 ${tone === "warning" ? "text-warning" : "text-muted-foreground"}`} />
    </div>
    <p className="mt-1 text-2xl font-semibold tabular-nums">{value ?? 0}</p>
  </Card>
);

const RosterOverviewPage = () => {
  const { can } = useAuth();
  const [data, setData] = useState(null);
  const [summary, setSummary] = useState(null);
  const [projectId, setProjectId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    roster_enabled: false, pattern_id: "", start_date: "", mobilization_enabled: false, notes: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data: res } = await api.get("/roster/projects");
      setData(res);
      setProjectId((prev) => prev || res.items?.[0]?.id || "");
    } catch (err) {
      setError(errorMessage(err, "Data roster belum dapat dimuat."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const selected = useMemo(
    () => (data?.items || []).find((p) => p.id === projectId) || null,
    [data, projectId],
  );

  useEffect(() => {
    if (!selected) return;
    const roster = selected.roster || {};
    setForm({
      roster_enabled: !!roster.enabled,
      pattern_id: roster.pattern_id || "",
      start_date: roster.start_date || "",
      mobilization_enabled: !!roster.mobilization_enabled,
      notes: roster.notes || "",
    });
  }, [selected]);

  const loadSummary = useCallback(async () => {
    if (!projectId) return;
    try {
      const { data: res } = await api.get("/roster/summary", { params: { project_id: projectId } });
      setSummary(res.items?.[0] || null);
    } catch {
      setSummary(null);
    }
  }, [projectId]);

  useEffect(() => { loadSummary(); }, [loadSummary]);

  const save = async () => {
    if (!selected) return;
    if (form.roster_enabled && (!form.pattern_id || !form.start_date)) {
      toast.error("Pola roster dan tanggal awal/POH wajib diisi saat roster diaktifkan.");
      return;
    }
    setSaving(true);
    try {
      const { data: res } = await api.put(`/roster/projects/${selected.id}`, {
        roster_enabled: form.roster_enabled,
        pattern_id: form.pattern_id || null,
        start_date: form.start_date || null,
        mobilization_enabled: form.mobilization_enabled,
        notes: form.notes || null,
      });
      toast.success(res.message);
      await load();
      await loadSummary();
    } catch (err) {
      toast.error(errorMessage(err, "Konfigurasi roster tidak dapat disimpan."));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <PageBody><Skeleton className="h-40 w-full rounded-xl" /><Skeleton className="h-64 w-full rounded-xl" /></PageBody>;
  }

  if (error) {
    return (
      <PageBody>
        <Card className="space-y-3 p-4" role="alert" data-testid="roster-overview-error">
          <p className="text-sm">{error}</p>
          <Button variant="outline" onClick={load}>Coba lagi</Button>
        </Card>
      </PageBody>
    );
  }

  const projects = data?.items || [];
  const patterns = data?.patterns || [];
  const roster = selected?.roster;

  return (
    <PageBody>
      {!projects.length ? (
        <Card className="p-5" data-testid="roster-empty">
          <p className="text-sm">Belum ada project aktif. Buat project terlebih dahulu di Setup → Proyek.</p>
        </Card>
      ) : (
        <>
          <Card className="border-border bg-card p-4" data-testid="roster-project-card">
            <div className="grid gap-3 lg:grid-cols-[1fr_auto] lg:items-end">
              <div>
                <Label htmlFor="roster-project" className="text-[13px]">Project</Label>
                <select id="roster-project" className={`${selectClass} mt-1`} value={projectId}
                  onChange={(e) => setProjectId(e.target.value)} data-testid="roster-project-select">
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>{p.name} · {p.code}</option>
                  ))}
                </select>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-[12px] text-muted-foreground">
                  <Badge variant="outline">{selected?.active_employees ?? 0} karyawan aktif</Badge>
                  {roster?.enabled ? (
                    <Badge variant="default">Roster aktif</Badge>
                  ) : (
                    <Badge variant="secondary">Roster belum diatur</Badge>
                  )}
                  {roster?.enabled && (
                    <span>
                      {roster.pattern_name} · {roster.work_days} hari kerja / {roster.off_days} hari off
                      {roster.start_date ? ` · POH ${formatDate(roster.start_date)}` : ""}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" asChild data-testid="roster-open-calendar">
                  <Link to="/modules/mobilization/kalender"><CalendarRange className="mr-1.5 h-4 w-4" />Kalender</Link>
                </Button>
                <Button variant="outline" asChild data-testid="roster-open-plans">
                  <Link to="/modules/mobilization/rencana"><ClipboardList className="mr-1.5 h-4 w-4" />Rencana Cuti</Link>
                </Button>
              </div>
            </div>
          </Card>

          {summary && (
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6" data-testid="roster-summary">
              <Stat label="Karyawan Aktif" value={summary.active_employees} icon={Users} />
              <Stat label="Rencana Cuti" value={summary.planned} icon={CalendarRange} />
              <Stat label="Terkonfirmasi" value={summary.confirmed} icon={CheckCircle2} />
              <Stat label="Sedang Cuti" value={summary.on_leave} icon={CalendarDays} />
              <Stat label="Akan Kembali" value={summary.returning} icon={Plane} />
              <Stat label="Replacement" value={summary.replacement_needed} icon={AlertTriangle} tone="warning" />
            </div>
          )}

          <Card className="border-border bg-card p-4" data-testid="roster-config-card">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-section-title">Konfigurasi Roster Project</h2>
                <p className="text-xs text-muted-foreground">
                  Pola roster dan tanggal awal/POH menghasilkan kalender kerja/off. Flag mobilisasi dipakai pada tahap GA.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Label htmlFor="roster-enabled" className="text-[13px]">Roster aktif</Label>
                <Switch id="roster-enabled" checked={form.roster_enabled} disabled={!can("roster", "edit")}
                  onCheckedChange={(v) => setForm((p) => ({ ...p, roster_enabled: v }))} data-testid="roster-enabled" />
              </div>
            </div>

            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <div>
                <Label htmlFor="roster-pattern" className="text-[13px]">Pola Roster</Label>
                <select id="roster-pattern" className={`${selectClass} mt-1`} value={form.pattern_id}
                  disabled={!can("roster", "edit")}
                  onChange={(e) => setForm((p) => ({ ...p, pattern_id: e.target.value }))} data-testid="roster-pattern">
                  <option value="">Pilih pola…</option>
                  {patterns.map((p) => (
                    <option key={p.id} value={p.id}>{p.name} · {p.work_days}/{p.off_days}</option>
                  ))}
                </select>
                {!patterns.length && (
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    Belum ada pola. Tambahkan di Setup → Pola Roster.
                  </p>
                )}
              </div>
              <div>
                <Label htmlFor="roster-start" className="text-[13px]">Tanggal awal roster / POH</Label>
                <Input id="roster-start" type="date" className="mt-1" value={form.start_date}
                  disabled={!can("roster", "edit")}
                  onChange={(e) => setForm((p) => ({ ...p, start_date: e.target.value }))} data-testid="roster-start-date" />
              </div>
              <div className="flex items-center gap-2 md:col-span-2">
                <Switch id="roster-mobilization" checked={form.mobilization_enabled} disabled={!can("roster", "edit")}
                  onCheckedChange={(v) => setForm((p) => ({ ...p, mobilization_enabled: v }))} data-testid="roster-mobilization" />
                <Label htmlFor="roster-mobilization" className="text-[13px]">Project menggunakan mobilisasi</Label>
              </div>
              <div className="md:col-span-2">
                <Label htmlFor="roster-notes" className="text-[13px]">Catatan</Label>
                <Textarea id="roster-notes" rows={2} className="mt-1" value={form.notes}
                  disabled={!can("roster", "edit")}
                  onChange={(e) => setForm((p) => ({ ...p, notes: e.target.value }))} data-testid="roster-notes" />
              </div>
            </div>

            {can("roster", "edit") && (
              <div className="mt-3 flex justify-end">
                <Button onClick={save} disabled={saving} data-testid="roster-save">
                  <Save className="mr-1.5 h-4 w-4" />{saving ? "Menyimpan…" : "Simpan konfigurasi"}
                </Button>
              </div>
            )}
          </Card>
        </>
      )}
    </PageBody>
  );
};

export default RosterOverviewPage;
