import React, { useCallback, useEffect, useState } from "react";
import { ClipboardList, RefreshCw, Sparkles, UserPlus } from "lucide-react";
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

const STATUS = {
  PLANNED: { label: "Direncanakan", variant: "outline" },
  CONFIRMED: { label: "Terkonfirmasi", variant: "default" },
  POSTPONED: { label: "Ditunda", variant: "secondary" },
};

const RosterPlansPage = () => {
  const { can } = useAuth();
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [generating, setGenerating] = useState(false);
  const [deciding, setDeciding] = useState(null);
  const [postpone, setPostpone] = useState(null);
  const [postponing, setPostponing] = useState(false);
  const [replacement, setReplacement] = useState(null);
  const [replacementOptions, setReplacementOptions] = useState([]);
  const [replacementLoading, setReplacementLoading] = useState(false);
  const [replacementSaving, setReplacementSaving] = useState(false);

  useEffect(() => {
    api.get("/roster/projects")
      .then(({ data }) => setProjects(data.items || []))
      .catch((err) => setError(errorMessage(err, "Daftar project tidak dapat dimuat.")));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = {};
      if (projectId) params.project_id = projectId;
      if (statusFilter) params.status = statusFilter;
      const { data } = await api.get("/roster/plans", { params });
      setPlans(data.items || []);
    } catch (err) {
      setError(errorMessage(err, "Rencana cuti tidak dapat dimuat."));
      setPlans([]);
    } finally {
      setLoading(false);
    }
  }, [projectId, statusFilter]);

  useEffect(() => { load(); }, [load]);

  const generate = async () => {
    if (!projectId) {
      toast.error("Pilih project terlebih dahulu.");
      return;
    }
    setGenerating(true);
    try {
      const { data } = await api.post("/roster/plans/generate", { project_id: projectId, horizon_days: 30 });
      toast.success(data.message || "Rencana cuti dibuat.");
      await load();
    } catch (err) {
      toast.error(errorMessage(err, "Rencana cuti tidak dapat dibuat."));
    } finally {
      setGenerating(false);
    }
  };

  const decide = async (plan, action, note = "") => {
    setDeciding(plan.id);
    try {
      const { data } = await api.patch(`/roster/plans/${plan.id}`, { action, note });
      toast.success(data.message);
      setPostpone(null);
      await load();
    } catch (err) {
      toast.error(errorMessage(err, "Keputusan rencana cuti gagal disimpan."));
    } finally {
      setDeciding(null);
    }
  };

  const openReplacement = async (plan) => {
    setReplacement({ plan, employeeId: plan.replacement_employee_id || "" });
    setReplacementOptions([]);
    setReplacementLoading(true);
    try {
      const { data } = await api.get("/roster/employees", {
        params: { project_id: plan.project_id },
      });
      setReplacementOptions((data.items || []).filter((e) => e.id !== plan.employee_id));
    } catch (err) {
      toast.error(errorMessage(err, "Daftar karyawan project tidak dapat dimuat."));
    } finally {
      setReplacementLoading(false);
    }
  };

  const saveReplacement = async () => {
    if (!replacement) return;
    setReplacementSaving(true);
    try {
      const { data } = await api.patch(`/roster/plans/${replacement.plan.id}/replacement`, {
        employee_id: replacement.employeeId || null,
      });
      toast.success(data.message);
      setReplacement(null);
      await load();
    } catch (err) {
      toast.error(errorMessage(err, "Penugasan pengganti gagal disimpan."));
    } finally {
      setReplacementSaving(false);
    }
  };

  return (
    <PageBody>
      <Card className="border-border bg-card p-4" data-testid="roster-plans-controls">
        <div className="grid gap-3 lg:grid-cols-[1fr_200px_auto] lg:items-end">
          <div>
            <Label htmlFor="plans-project" className="text-[13px]">Project</Label>
            <select id="plans-project" className={`${selectClass} mt-1`} value={projectId}
              onChange={(e) => setProjectId(e.target.value)} data-testid="roster-plans-project">
              <option value="">Semua project</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.code}</option>)}
            </select>
          </div>
          <div>
            <Label htmlFor="plans-status" className="text-[13px]">Status</Label>
            <select id="plans-status" className={`${selectClass} mt-1`} value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)} data-testid="roster-plans-status">
              <option value="">Semua status</option>
              <option value="PLANNED">Direncanakan</option>
              <option value="CONFIRMED">Terkonfirmasi</option>
              <option value="POSTPONED">Ditunda</option>
            </select>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={load} disabled={loading} data-testid="roster-plans-refresh">
              <RefreshCw className="mr-1.5 h-4 w-4" />Muat ulang
            </Button>
            {can("roster", "create") && (
              <Button onClick={generate} disabled={generating || !projectId} data-testid="roster-generate">
                <Sparkles className="mr-1.5 h-4 w-4" />{generating ? "Membuat…" : "Buat rencana H-30"}
              </Button>
            )}
          </div>
        </div>
        <p className="mt-2 text-[11px] text-muted-foreground">
          Generate membuat rencana cuti untuk siklus off terdekat (maksimal 30 hari ke depan). Konfirmasi H-10 dapat
          dilakukan maksimal 10 hari sebelum tanggal cuti.
        </p>
      </Card>

      {loading ? (
        <Skeleton className="h-64 w-full rounded-xl" />
      ) : error ? (
        <Card className="space-y-3 p-4" role="alert" data-testid="roster-plans-error">
          <p className="text-sm">{error}</p>
          <Button variant="outline" onClick={load}>Coba lagi</Button>
        </Card>
      ) : !plans.length ? (
        <Card className="p-5" data-testid="roster-plans-empty">
          <div className="flex items-center gap-2 text-sm font-medium"><ClipboardList className="h-4 w-4" />Belum ada rencana cuti.</div>
          <p className="mt-1 text-sm text-muted-foreground">
            Pilih project lalu klik “Buat rencana H-30” untuk membuat rencana dari pola roster.
          </p>
        </Card>
      ) : (
        <Card className="border-border bg-card" data-testid="roster-plans-table">
          <div className="table-scroll">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Karyawan</TableHead>
                  <TableHead>Project</TableHead>
                  <TableHead>Mulai Cuti</TableHead>
                  <TableHead>Selesai</TableHead>
                  <TableHead className="text-right">H-</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Replacement</TableHead>
                  <TableHead className="text-right">Aksi</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {plans.map((plan) => {
                  const st = STATUS[plan.plan_status] || { label: plan.plan_status, variant: "outline" };
                  const canDecide = plan.plan_status === "PLANNED" && plan.days_until >= 0 && plan.days_until <= 10;
                  return (
                    <TableRow key={plan.id} data-testid={`roster-plan-${plan.id}`}>
                      <TableCell>
                        <p className="font-medium">{plan.employee_name}</p>
                        <p className="text-[11px] text-muted-foreground">{plan.employee_number}</p>
                      </TableCell>
                      <TableCell>{plan.project_name}</TableCell>
                      <TableCell>{formatDate(plan.off_start)}</TableCell>
                      <TableCell>{formatDate(plan.off_end)}</TableCell>
                      <TableCell className="text-right tabular-nums">{plan.days_until ?? "-"}</TableCell>
                      <TableCell><Badge variant={st.variant}>{st.label}</Badge></TableCell>
                      <TableCell>
                        {plan.replacement_employee_name ? (
                          <span className="text-[12px] font-medium">{plan.replacement_employee_name}</span>
                        ) : plan.replacement_needed ? (
                          <Badge variant="outline">Perlu</Badge>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex flex-wrap justify-end gap-1">
                          {plan.plan_status === "PLANNED" && (
                            canDecide && can("roster", "edit") ? (
                              <>
                                <Button size="sm" variant="outline" disabled={deciding === plan.id}
                                  onClick={() => decide(plan, "CONFIRM")} data-testid={`plan-confirm-${plan.id}`}>
                                  Konfirmasi
                                </Button>
                                <Button size="sm" variant="ghost" disabled={deciding === plan.id}
                                  onClick={() => setPostpone({ plan, note: "" })} data-testid={`plan-postpone-${plan.id}`}>
                                  Tunda
                                </Button>
                              </>
                            ) : (
                              <span className="text-[11px] text-muted-foreground">
                                {plan.days_until < 0 ? "Jadwal lewat" : "H-10 belum tiba"}
                              </span>
                            )
                          )}
                          {can("roster", "edit") && plan.plan_status !== "POSTPONED" && (
                            <Button size="sm" variant="ghost" onClick={() => openReplacement(plan)}
                              data-testid={`plan-replacement-${plan.id}`}>
                              <UserPlus className="mr-1 h-3.5 w-3.5" />Pengganti
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </Card>
      )}

      <Dialog open={!!postpone} onOpenChange={(open) => !open && !postponing && setPostpone(null)}>
        <DialogContent className="bg-card sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Tunda rencana cuti</DialogTitle>
            <DialogDescription>
              {postpone?.plan?.employee_name} · {formatDate(postpone?.plan?.off_start)} s.d. {formatDate(postpone?.plan?.off_end)}.
              Catatan penundaan wajib diisi.
            </DialogDescription>
          </DialogHeader>
          <Textarea rows={3} value={postpone?.note || ""} placeholder="Alasan penundaan (mis. operasional project)"
            onChange={(e) => setPostpone((p) => ({ ...p, note: e.target.value }))} data-testid="roster-postpone-note" />
          <DialogFooter>
            <Button variant="outline" onClick={() => setPostpone(null)} disabled={postponing}>Batal</Button>
            <Button disabled={postponing || (postpone?.note || "").trim().length < 3}
              onClick={() => decide(postpone.plan, "POSTPONE", postpone.note.trim())} data-testid="roster-postpone-submit">
              {postponing ? "Menyimpan…" : "Tunda"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={!!replacement} onOpenChange={(open) => { if (!open && !replacementSaving) setReplacement(null); }}>
        <DialogContent className="bg-card sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Karyawan pengganti</DialogTitle>
            <DialogDescription>
              {replacement?.plan?.employee_name} · cuti {formatDate(replacement?.plan?.off_start)} s.d.{" "}
              {formatDate(replacement?.plan?.off_end)}. Pilih karyawan yang menggantikan selama periode tersebut.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="plan-replacement-select">Karyawan Pengganti</Label>
            <select id="plan-replacement-select" className={`${selectClass} mt-1`}
              value={replacement?.employeeId || ""}
              onChange={(e) => setReplacement((r) => ({ ...r, employeeId: e.target.value }))}
              disabled={replacementLoading} data-testid="plan-replacement-select">
              <option value="">— Tanpa pengganti —</option>
              {replacementOptions.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.full_name}{e.employee_number ? ` · ${e.employee_number}` : ""}
                </option>
              ))}
            </select>
            <p className="text-[11px] text-muted-foreground">
              Hanya karyawan aktif pada project yang sama dan tidak memiliki cuti project yang bertabrakan.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReplacement(null)} disabled={replacementSaving}>Batal</Button>
            <Button onClick={saveReplacement} disabled={replacementSaving || replacementLoading}
              data-testid="plan-replacement-submit">
              {replacementSaving ? "Menyimpan…" : "Simpan"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageBody>
  );
};

export default RosterPlansPage;
