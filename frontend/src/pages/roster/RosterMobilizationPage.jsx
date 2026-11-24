import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CheckCircle2, History, Plane, RefreshCw, Search, XCircle } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate, formatDateTime } from "@/lib/format";
import { PageBody } from "@/components/common/PageHeader";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const selectClass = "h-9 w-full rounded-lg border border-input bg-card px-3 text-sm text-ink-1 shadow-[var(--shadow-input)] transition-[border-color,box-shadow] duration-150 hover:border-border-strong focus-visible:outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/25";

const STATES = {
  NOT_SET: { label: "Belum diatur", variant: "warning" },
  PLANNED: { label: "Direncanakan", variant: "info" },
  DEPARTED: { label: "Berangkat / cuti", variant: "default" },
  RETURNED: { label: "Sudah kembali", variant: "success" },
  CANCELLED: { label: "Dibatalkan", variant: "destructive" },
};

const APPROVALS = {
  PENDING_APPROVAL: { label: "Menunggu Persetujuan HR", variant: "warning" },
  APPROVED: { label: "Disetujui HR", variant: "success" },
  REJECTED: { label: "Ditolak HR", variant: "destructive" },
};

const Stat = ({ label, value, tone = "default", testId }) => (
  <Card className="border-border bg-card p-3" data-testid={testId}>
    <p className="text-[12px] text-muted-foreground">{label}</p>
    <p className={`mt-1 text-2xl font-semibold tabular-nums ${tone === "warning" ? "text-warning" : ""}`}>{value ?? 0}</p>
  </Card>
);

const emptyForm = {
  depart_date: "", depart_time: "", depart_mode: "PESAWAT",
  depart_carrier: "", depart_ticket: "", depart_from: "", depart_to: "",
  return_date: "", return_time: "", return_mode: "PESAWAT",
  return_carrier: "", return_ticket: "", return_from: "", return_to: "",
  accommodation: "", notes: "", reason: "",
};

const APPROVAL_HISTORY = {
  PENDING_APPROVAL: "Menunggu Persetujuan HR",
  APPROVED: "Disetujui HR",
  REJECTED: "Ditolak HR",
};

const approvalSnapshotText = (data) => {
  if (!data || !data.approval_state) return "-";
  const label = APPROVAL_HISTORY[data.approval_state] || data.approval_state;
  return data.approved_by_name ? `${label} · ${data.approved_by_name}` : label;
};

const snapshotText = (data) => {
  if (!data) return "-";
  const depart = [formatDate(data.depart_date), data.depart_time].filter(Boolean).join(" ");
  const ret = [formatDate(data.return_date), data.return_time].filter(Boolean).join(" ");
  const departMeta = [data.depart_mode_label, data.depart_carrier].filter(Boolean).join(" · ");
  const returnMeta = [data.return_mode_label, data.return_carrier].filter(Boolean).join(" · ");
  return `Berangkat ${depart || "-"}${departMeta ? ` (${departMeta})` : ""}`
    + ` · Kembali ${ret || "-"}${returnMeta ? ` (${returnMeta})` : ""}`;
};

const RosterMobilizationPage = () => {
  const { can } = useAuth();
  const [searchParams] = useSearchParams();
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState(() => searchParams.get("project") || "");
  const [stateFilter, setStateFilter] = useState("");
  const [approvalFilter, setApprovalFilter] = useState("");
  const [q, setQ] = useState("");
  const [includePast, setIncludePast] = useState(false);
  const [rows, setRows] = useState([]);
  const [counts, setCounts] = useState({});
  const [approvalCounts, setApprovalCounts] = useState({});
  const [modes, setModes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [target, setTarget] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [cancelTarget, setCancelTarget] = useState(null);
  const [cancelReason, setCancelReason] = useState("");
  const [cancelling, setCancelling] = useState(false);
  const [approveTarget, setApproveTarget] = useState(null);
  const [approveNote, setApproveNote] = useState("");
  const [rejectTarget, setRejectTarget] = useState(null);
  const [rejectReason, setRejectReason] = useState("");
  const [deciding, setDeciding] = useState(false);
  const [historyTarget, setHistoryTarget] = useState(null);
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  useEffect(() => {
    api.get("/roster/projects")
      .then(({ data }) => setProjects(data.items || []))
      .catch(() => setProjects([]));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = {};
      if (projectId) params.project_id = projectId;
      if (stateFilter) params.state = stateFilter;
      if (approvalFilter) params.approval_state = approvalFilter;
      if (q.trim()) params.q = q.trim();
      if (includePast) params.include_past = true;
      const { data } = await api.get("/roster/mobilizations", { params });
      setRows(data.items || []);
      setCounts(data.counts || {});
      setApprovalCounts(data.approval_counts || {});
      setModes(data.modes || []);
    } catch (err) {
      setError(errorMessage(err, "Data mobilisasi tidak dapat dimuat."));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [projectId, stateFilter, approvalFilter, q, includePast]);

  useEffect(() => { load(); }, [load]);

  const openForm = (row) => {
    const mob = row.mobilization || {};
    setTarget(row);
    setForm({
      ...emptyForm,
      depart_date: mob.depart_date || row.off_start || "",
      depart_time: mob.depart_time || "",
      depart_mode: mob.depart_mode || "PESAWAT",
      depart_carrier: mob.depart_carrier || "",
      depart_ticket: mob.depart_ticket || "",
      depart_from: mob.depart_from || "",
      depart_to: mob.depart_to || "",
      return_date: mob.return_date || row.off_end || "",
      return_time: mob.return_time || "",
      return_mode: mob.return_mode || "PESAWAT",
      return_carrier: mob.return_carrier || "",
      return_ticket: mob.return_ticket || "",
      return_from: mob.return_from || "",
      return_to: mob.return_to || "",
      accommodation: mob.accommodation || "",
      notes: mob.notes || "",
      reason: "",
    });
  };

  const scheduleChanged = useMemo(() => {
    const mob = target?.mobilization;
    if (!mob) return false;
    return ["depart_date", "depart_time", "depart_mode", "return_date", "return_time", "return_mode"]
      .some((key) => (mob[key] || "") !== (form[key] || ""));
  }, [target, form]);

  const save = async () => {
    if (!target) return;
    if (!form.depart_date || !form.return_date) {
      toast.error("Tanggal berangkat dan kembali wajib diisi.");
      return;
    }
    if (scheduleChanged && form.reason.trim().length < 3) {
      toast.error("Alasan perubahan jadwal wajib diisi (minimal 3 karakter).");
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.put(`/roster/mobilizations/${target.plan_id}`, {
        ...form,
        depart_carrier: form.depart_carrier || null,
        depart_ticket: form.depart_ticket || null,
        depart_from: form.depart_from || null,
        depart_to: form.depart_to || null,
        return_carrier: form.return_carrier || null,
        return_ticket: form.return_ticket || null,
        return_from: form.return_from || null,
        return_to: form.return_to || null,
        depart_time: form.depart_time || null,
        return_time: form.return_time || null,
        accommodation: form.accommodation || null,
        notes: form.notes || null,
        reason: form.reason || null,
      });
      toast.success(data.message || "Mobilisasi disimpan.");
      setTarget(null);
      await load();
    } catch (err) {
      toast.error(errorMessage(err, "Mobilisasi gagal disimpan."));
    } finally {
      setSaving(false);
    }
  };

  const cancel = async () => {
    if (!cancelTarget) return;
    setCancelling(true);
    try {
      const { data } = await api.post(`/roster/mobilizations/${cancelTarget.plan_id}/cancel`,
        { reason: cancelReason.trim() });
      toast.success(data.message || "Mobilisasi dibatalkan.");
      setCancelTarget(null);
      setCancelReason("");
      await load();
    } catch (err) {
      toast.error(errorMessage(err, "Mobilisasi gagal dibatalkan."));
    } finally {
      setCancelling(false);
    }
  };

  const approve = async () => {
    if (!approveTarget) return;
    setDeciding(true);
    try {
      const { data } = await api.post(`/roster/mobilizations/${approveTarget.plan_id}/approve`,
        { note: approveNote.trim() || null });
      toast.success(data.message || "Mobilisasi disetujui.");
      setApproveTarget(null);
      setApproveNote("");
      await load();
    } catch (err) {
      toast.error(errorMessage(err, "Mobilisasi gagal disetujui."));
    } finally {
      setDeciding(false);
    }
  };

  const reject = async () => {
    if (!rejectTarget) return;
    if (rejectReason.trim().length < 3) {
      toast.error("Alasan penolakan wajib diisi (minimal 3 karakter).");
      return;
    }
    setDeciding(true);
    try {
      const { data } = await api.post(`/roster/mobilizations/${rejectTarget.plan_id}/reject`,
        { reason: rejectReason.trim() });
      toast.success(data.message || "Mobilisasi ditolak.");
      setRejectTarget(null);
      setRejectReason("");
      await load();
    } catch (err) {
      toast.error(errorMessage(err, "Mobilisasi gagal ditolak."));
    } finally {
      setDeciding(false);
    }
  };

  const openHistory = async (row) => {
    setHistoryTarget(row);
    setHistory([]);
    setHistoryLoading(true);
    try {
      const { data } = await api.get("/roster/schedule-changes", { params: { plan_id: row.plan_id } });
      setHistory(data.items || []);
    } catch (err) {
      toast.error(errorMessage(err, "Histori jadwal tidak dapat dimuat."));
    } finally {
      setHistoryLoading(false);
    }
  };

  const canEdit = can("roster", "edit");
  const canApprove = can("roster", "approve");

  return (
    <PageBody>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Belum diatur" value={counts.NOT_SET} tone="warning" testId="mob-stat-not-set" />
        <Stat label="Menunggu Persetujuan HR" value={approvalCounts.PENDING_APPROVAL} tone="warning"
          testId="mob-stat-pending" />
        <Stat label="Direncanakan" value={counts.PLANNED} testId="mob-stat-planned" />
        <Stat label="Berangkat / cuti" value={counts.DEPARTED} testId="mob-stat-departed" />
        <Stat label="Sudah kembali" value={counts.RETURNED} testId="mob-stat-returned" />
        <Stat label="Dibatalkan" value={counts.CANCELLED} testId="mob-stat-cancelled" />
      </div>

      <Card className="border-border bg-card p-4" data-testid="mob-controls">
        <div className="grid gap-3 lg:grid-cols-[1fr_170px_190px_1fr_auto] lg:items-end">
          <div>
            <Label htmlFor="mob-project" className="text-[13px]">Project</Label>
            <select id="mob-project" className={`${selectClass} mt-1`} value={projectId}
              onChange={(e) => setProjectId(e.target.value)} data-testid="mob-project">
              <option value="">Semua project</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.code}</option>)}
            </select>
          </div>
          <div>
            <Label htmlFor="mob-state" className="text-[13px]">Status</Label>
            <select id="mob-state" className={`${selectClass} mt-1`} value={stateFilter}
              onChange={(e) => setStateFilter(e.target.value)} data-testid="mob-state">
              <option value="">Semua status</option>
              {Object.entries(STATES).map(([value, st]) => (
                <option key={value} value={value}>{st.label}</option>
              ))}
            </select>
          </div>
          <div>
            <Label htmlFor="mob-approval" className="text-[13px]">Persetujuan</Label>
            <select id="mob-approval" className={`${selectClass} mt-1`} value={approvalFilter}
              onChange={(e) => setApprovalFilter(e.target.value)} data-testid="mob-approval">
              <option value="">Semua persetujuan</option>
              {Object.entries(APPROVALS).map(([value, ap]) => (
                <option key={value} value={value}>{ap.label}</option>
              ))}
            </select>
          </div>
          <div>
            <Label htmlFor="mob-search" className="text-[13px]">Cari karyawan</Label>
            <div className="relative mt-1">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input id="mob-search" className="pl-8" placeholder="Nama atau NIK"
                value={q} onChange={(e) => setQ(e.target.value)} data-testid="mob-search" />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Label htmlFor="mob-past" className="flex items-center gap-2 text-[12px] text-muted-foreground">
              <Switch id="mob-past" checked={includePast} onCheckedChange={setIncludePast} data-testid="mob-past" />
              Tampilkan yang lewat
            </Label>
            <Button variant="outline" onClick={load} disabled={loading} data-testid="mob-refresh">
              <RefreshCw className="mr-1.5 h-4 w-4" />Muat ulang
            </Button>
          </div>
        </div>
        <p className="mt-2 text-[11px] text-muted-foreground">
          Hanya rencana cuti yang sudah dikonfirmasi (H-10) yang dapat dimobilisasi. Tanggal berangkat dan kembali
          harus di dalam periode off agar karyawan kembali sebelum hari kerja. Mobilisasi yang diatur GA berstatus
          Menunggu Persetujuan HR sampai disetujui HR Manager.
        </p>
      </Card>

      {loading ? (
        <Skeleton className="h-64 w-full rounded-xl" />
      ) : error ? (
        <Card className="space-y-3 p-4" role="alert" data-testid="mob-error">
          <p className="text-sm">{error}</p>
          <Button variant="outline" onClick={load}>Coba lagi</Button>
        </Card>
      ) : rows.length === 0 ? (
        <Card className="flex flex-col items-center gap-2 p-8 text-center" data-testid="mob-empty">
          <Plane className="h-8 w-8 text-muted-foreground" />
          <p className="text-sm font-medium">Belum ada rencana cuti terkonfirmasi.</p>
          <p className="text-[13px] text-muted-foreground">
            Konfirmasi rencana cuti di tab Rencana Cuti (H-10) agar mobilisasi dapat diatur.
          </p>
        </Card>
      ) : (
        <Card className="border-border bg-card" data-testid="mob-table-card">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Karyawan</TableHead>
                  <TableHead>Project</TableHead>
                  <TableHead>Periode Off</TableHead>
                  <TableHead>Berangkat</TableHead>
                  <TableHead>Kembali</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Persetujuan</TableHead>
                  <TableHead className="text-right">Aksi</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => {
                  const st = STATES[row.travel_state] || { label: row.travel_state_label, variant: "outline" };
                  const mob = row.mobilization;
                  return (
                    <TableRow key={row.plan_id} data-testid={`mob-row-${row.plan_id}`}>
                      <TableCell>
                        <p className="font-medium">{row.employee_name}</p>
                        <p className="text-[11px] text-muted-foreground">{row.employee_number || "-"}</p>
                      </TableCell>
                      <TableCell>{row.project_name || "-"}</TableCell>
                      <TableCell className="text-[12px]">
                        {formatDate(row.off_start)} – {formatDate(row.off_end)}
                      </TableCell>
                      <TableCell className="text-[12px]">
                        {mob ? (
                          <>
                            <p className="font-medium">{formatDate(mob.depart_date)} {mob.depart_time || ""}</p>
                            <p className="text-muted-foreground">
                              {mob.depart_mode_label}{mob.depart_carrier ? ` · ${mob.depart_carrier}` : ""}
                              {mob.depart_ticket ? ` · ${mob.depart_ticket}` : ""}
                            </p>
                          </>
                        ) : "-"}
                      </TableCell>
                      <TableCell className="text-[12px]">
                        {mob ? (
                          <>
                            <p className="font-medium">{formatDate(mob.return_date)} {mob.return_time || ""}</p>
                            <p className="text-muted-foreground">
                              {mob.return_mode_label}{mob.return_carrier ? ` · ${mob.return_carrier}` : ""}
                            </p>
                          </>
                        ) : "-"}
                      </TableCell>
                      <TableCell><Badge variant={st.variant}>{st.label}</Badge></TableCell>
                      <TableCell>
                        {mob ? (
                          <div className="space-y-1">
                            <Badge variant={(APPROVALS[mob.approval_state] || {}).variant || "outline"}>
                              {(APPROVALS[mob.approval_state] || {}).label || mob.approval_state_label}
                            </Badge>
                            {mob.approval_state === "REJECTED" && mob.approval_note && (
                              <p className="max-w-[200px] truncate text-[11px] text-muted-foreground"
                                title={mob.approval_note}>
                                {mob.approval_note}
                              </p>
                            )}
                            {mob.approval_state === "APPROVED" && mob.approved_by_name && (
                              <p className="text-[11px] text-muted-foreground">oleh {mob.approved_by_name}</p>
                            )}
                          </div>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex flex-wrap justify-end gap-1">
                          {canEdit && (
                            <Button size="sm" variant="outline" onClick={() => openForm(row)}
                              data-testid={`mob-edit-${row.plan_id}`}>
                              {mob ? "Ubah" : "Atur"}
                            </Button>
                          )}
                          {canApprove && mob && !["RETURNED", "CANCELLED"].includes(row.travel_state)
                            && mob.approval_state !== "APPROVED" && (
                            <Button size="sm" variant="outline" onClick={() => { setApproveNote(""); setApproveTarget(row); }}
                              data-testid={`mob-approve-${row.plan_id}`}>
                              <CheckCircle2 className="mr-1 h-3.5 w-3.5" />Setujui
                            </Button>
                          )}
                          {canApprove && mob && !["RETURNED", "CANCELLED"].includes(row.travel_state)
                            && mob.approval_state !== "REJECTED" && (
                            <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive"
                              onClick={() => { setRejectReason(""); setRejectTarget(row); }}
                              data-testid={`mob-reject-${row.plan_id}`}>
                              <XCircle className="mr-1 h-3.5 w-3.5" />Tolak
                            </Button>
                          )}
                          {canEdit && mob && !["RETURNED", "CANCELLED"].includes(row.travel_state) && (
                            <Button size="sm" variant="ghost"
                              onClick={() => { setCancelReason(""); setCancelTarget(row); }}
                              data-testid={`mob-cancel-${row.plan_id}`}>
                              <XCircle className="mr-1 h-3.5 w-3.5" />Batal
                            </Button>
                          )}
                          <Button size="sm" variant="ghost" onClick={() => openHistory(row)}
                            data-testid={`mob-history-${row.plan_id}`}>
                            <History className="mr-1 h-3.5 w-3.5" />Histori
                          </Button>
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

      <Dialog open={!!target} onOpenChange={(open) => { if (!open && !saving) setTarget(null); }}>
        <DialogContent className="bg-card sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{target?.mobilization ? "Ubah mobilisasi" : "Atur mobilisasi"}</DialogTitle>
            <DialogDescription>
              {target?.employee_name} · {formatDate(target?.off_start)} – {formatDate(target?.off_end)}
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-[65vh] space-y-4 overflow-y-auto pr-1">
            <div>
              <h3 className="text-section-title">Keberangkatan</h3>
              <div className="mt-2 grid gap-3 sm:grid-cols-2">
                <div>
                  <Label htmlFor="mob-depart-date" className="text-[13px]">Tanggal berangkat</Label>
                  <Input id="mob-depart-date" type="date" className="mt-1" value={form.depart_date}
                    onChange={(e) => setForm((f) => ({ ...f, depart_date: e.target.value }))}
                    data-testid="mob-depart-date" />
                </div>
                <div>
                  <Label htmlFor="mob-depart-time" className="text-[13px]">Jam (opsional)</Label>
                  <Input id="mob-depart-time" type="time" className="mt-1" value={form.depart_time}
                    onChange={(e) => setForm((f) => ({ ...f, depart_time: e.target.value }))}
                    data-testid="mob-depart-time" />
                </div>
                <div>
                  <Label htmlFor="mob-depart-mode" className="text-[13px]">Moda</Label>
                  <select id="mob-depart-mode" className={`${selectClass} mt-1`} value={form.depart_mode}
                    onChange={(e) => setForm((f) => ({ ...f, depart_mode: e.target.value }))}
                    data-testid="mob-depart-mode">
                    {(modes.length ? modes : [{ value: "PESAWAT", label: "Pesawat" }]).map((m) => (
                      <option key={m.value} value={m.value}>{m.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <Label htmlFor="mob-depart-carrier" className="text-[13px]">Maskapai / armada</Label>
                  <Input id="mob-depart-carrier" className="mt-1" value={form.depart_carrier}
                    onChange={(e) => setForm((f) => ({ ...f, depart_carrier: e.target.value }))}
                    data-testid="mob-depart-carrier" />
                </div>
                <div>
                  <Label htmlFor="mob-depart-ticket" className="text-[13px]">No. tiket</Label>
                  <Input id="mob-depart-ticket" className="mt-1" value={form.depart_ticket}
                    onChange={(e) => setForm((f) => ({ ...f, depart_ticket: e.target.value }))}
                    data-testid="mob-depart-ticket" />
                </div>
                <div>
                  <Label htmlFor="mob-depart-from" className="text-[13px]">Dari</Label>
                  <Input id="mob-depart-from" className="mt-1" value={form.depart_from}
                    onChange={(e) => setForm((f) => ({ ...f, depart_from: e.target.value }))}
                    data-testid="mob-depart-from" />
                </div>
                <div>
                  <Label htmlFor="mob-depart-to" className="text-[13px]">Ke</Label>
                  <Input id="mob-depart-to" className="mt-1" value={form.depart_to}
                    onChange={(e) => setForm((f) => ({ ...f, depart_to: e.target.value }))}
                    data-testid="mob-depart-to" />
                </div>
              </div>
            </div>
            <div>
              <h3 className="text-section-title">Kepulangan</h3>
              <div className="mt-2 grid gap-3 sm:grid-cols-2">
                <div>
                  <Label htmlFor="mob-return-date" className="text-[13px]">Tanggal kembali</Label>
                  <Input id="mob-return-date" type="date" className="mt-1" value={form.return_date}
                    onChange={(e) => setForm((f) => ({ ...f, return_date: e.target.value }))}
                    data-testid="mob-return-date" />
                </div>
                <div>
                  <Label htmlFor="mob-return-time" className="text-[13px]">Jam (opsional)</Label>
                  <Input id="mob-return-time" type="time" className="mt-1" value={form.return_time}
                    onChange={(e) => setForm((f) => ({ ...f, return_time: e.target.value }))}
                    data-testid="mob-return-time" />
                </div>
                <div>
                  <Label htmlFor="mob-return-mode" className="text-[13px]">Moda</Label>
                  <select id="mob-return-mode" className={`${selectClass} mt-1`} value={form.return_mode}
                    onChange={(e) => setForm((f) => ({ ...f, return_mode: e.target.value }))}
                    data-testid="mob-return-mode">
                    {(modes.length ? modes : [{ value: "PESAWAT", label: "Pesawat" }]).map((m) => (
                      <option key={m.value} value={m.value}>{m.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <Label htmlFor="mob-return-carrier" className="text-[13px]">Maskapai / armada</Label>
                  <Input id="mob-return-carrier" className="mt-1" value={form.return_carrier}
                    onChange={(e) => setForm((f) => ({ ...f, return_carrier: e.target.value }))}
                    data-testid="mob-return-carrier" />
                </div>
                <div>
                  <Label htmlFor="mob-return-ticket" className="text-[13px]">No. tiket</Label>
                  <Input id="mob-return-ticket" className="mt-1" value={form.return_ticket}
                    onChange={(e) => setForm((f) => ({ ...f, return_ticket: e.target.value }))}
                    data-testid="mob-return-ticket" />
                </div>
                <div>
                  <Label htmlFor="mob-return-from" className="text-[13px]">Dari</Label>
                  <Input id="mob-return-from" className="mt-1" value={form.return_from}
                    onChange={(e) => setForm((f) => ({ ...f, return_from: e.target.value }))}
                    data-testid="mob-return-from" />
                </div>
                <div>
                  <Label htmlFor="mob-return-to" className="text-[13px]">Ke</Label>
                  <Input id="mob-return-to" className="mt-1" value={form.return_to}
                    onChange={(e) => setForm((f) => ({ ...f, return_to: e.target.value }))}
                    data-testid="mob-return-to" />
                </div>
              </div>
            </div>
            <div>
              <Label htmlFor="mob-accommodation" className="text-[13px]">Akomodasi (opsional)</Label>
              <Textarea id="mob-accommodation" className="mt-1" rows={2} value={form.accommodation}
                onChange={(e) => setForm((f) => ({ ...f, accommodation: e.target.value }))}
                data-testid="mob-accommodation" />
            </div>
            <div>
              <Label htmlFor="mob-notes" className="text-[13px]">Catatan (opsional)</Label>
              <Textarea id="mob-notes" className="mt-1" rows={2} value={form.notes}
                onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                data-testid="mob-notes" />
            </div>
            {scheduleChanged && (
              <div>
                <Label htmlFor="mob-reason" className="text-[13px]">Alasan perubahan jadwal</Label>
                <Textarea id="mob-reason" className="mt-1" rows={2} value={form.reason}
                  placeholder="Wajib diisi karena tanggal/jam/moda berubah"
                  onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))}
                  data-testid="mob-reason" />
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Perubahan jadwal tercatat permanen pada histori beserta alasan dan pelakunya.
                </p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTarget(null)} disabled={saving}>Batal</Button>
            <Button onClick={save} disabled={saving} data-testid="mob-save">
              {saving ? "Menyimpan…" : "Simpan"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!cancelTarget} onOpenChange={(open) => { if (!open && !cancelling) setCancelTarget(null); }}>
        <DialogContent className="bg-card sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Batalkan mobilisasi</DialogTitle>
            <DialogDescription>
              {cancelTarget?.employee_name} · {formatDate(cancelTarget?.mobilization?.depart_date)}. Rencana cuti tetap
              berlaku; perjalanan ditandai dibatalkan.
            </DialogDescription>
          </DialogHeader>
          <Textarea rows={3} value={cancelReason} placeholder="Alasan pembatalan (wajib)"
            onChange={(e) => setCancelReason(e.target.value)} data-testid="mob-cancel-reason" />
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelTarget(null)} disabled={cancelling}>Kembali</Button>
            <Button variant="destructive" onClick={cancel} disabled={cancelling || cancelReason.trim().length < 3}
              data-testid="mob-cancel-submit">
              {cancelling ? "Membatalkan…" : "Batalkan Perjalanan"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!approveTarget} onOpenChange={(open) => { if (!open && !deciding) setApproveTarget(null); }}>
        <DialogContent className="bg-card sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Setujui mobilisasi</DialogTitle>
            <DialogDescription>
              {approveTarget?.employee_name} · berangkat {formatDate(approveTarget?.mobilization?.depart_date)}, kembali{" "}
              {formatDate(approveTarget?.mobilization?.return_date)}.
            </DialogDescription>
          </DialogHeader>
          <Textarea rows={2} value={approveNote} placeholder="Catatan persetujuan (opsional)"
            onChange={(e) => setApproveNote(e.target.value)} data-testid="mob-approve-note" />
          <DialogFooter>
            <Button variant="outline" onClick={() => setApproveTarget(null)} disabled={deciding}>Batal</Button>
            <Button onClick={approve} disabled={deciding} data-testid="mob-approve-submit">
              {deciding ? "Menyetujui…" : "Setujui Mobilisasi"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!rejectTarget} onOpenChange={(open) => { if (!open && !deciding) setRejectTarget(null); }}>
        <DialogContent className="bg-card sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Tolak mobilisasi</DialogTitle>
            <DialogDescription>
              {rejectTarget?.employee_name}. Alasan wajib diisi agar GA dapat memperbaiki jadwal lalu mengajukan ulang.
            </DialogDescription>
          </DialogHeader>
          <Textarea rows={3} value={rejectReason} placeholder="Alasan penolakan (wajib, minimal 3 karakter)"
            onChange={(e) => setRejectReason(e.target.value)} data-testid="mob-reject-reason" />
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectTarget(null)} disabled={deciding}>Batal</Button>
            <Button variant="destructive" onClick={reject}
              disabled={deciding || rejectReason.trim().length < 3} data-testid="mob-reject-submit">
              {deciding ? "Menolak…" : "Tolak Mobilisasi"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!historyTarget} onOpenChange={(open) => !open && setHistoryTarget(null)}>
        <DialogContent className="bg-card sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Histori perubahan jadwal</DialogTitle>
            <DialogDescription>
              {historyTarget?.employee_name} · {historyTarget?.project_name}
            </DialogDescription>
          </DialogHeader>
          {historyLoading ? (
            <Skeleton className="h-32 w-full rounded-xl" />
          ) : history.length === 0 ? (
            <p className="text-[13px] text-muted-foreground">Belum ada perubahan tercatat.</p>
          ) : (
            <div className="max-h-[55vh] space-y-3 overflow-y-auto">
              {history.map((h) => (
                <div key={h.id} className="rounded-lg border border-border p-3" data-testid={`mob-history-item-${h.id}`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <Badge variant="outline">{h.change_type_label}</Badge>
                    <span className="text-[11px] text-muted-foreground">
                      {formatDateTime(h.changed_at)} · {h.changed_by_name || "-"}
                    </span>
                  </div>
                  <p className="mt-2 text-[12px]">
                    {["APPROVED", "REJECTED"].includes(h.change_type) ? (
                      <>
                        <span className="text-muted-foreground">Status:</span>{" "}
                        {approvalSnapshotText(h.before_data)} → {approvalSnapshotText(h.after_data)}
                      </>
                    ) : (
                      <>
                        <span className="text-muted-foreground">Sebelum:</span> {snapshotText(h.before_data)}
                      </>
                    )}
                  </p>
                  {!["APPROVED", "REJECTED"].includes(h.change_type) && (
                    <p className="text-[12px]">
                      <span className="text-muted-foreground">Sesudah:</span> {snapshotText(h.after_data)}
                    </p>
                  )}
                  {h.reason && (
                    <p className="mt-1 text-[12px]"><span className="text-muted-foreground">Alasan:</span> {h.reason}</p>
                  )}
                </div>
              ))}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setHistoryTarget(null)}>Tutup</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageBody>
  );
};

export default RosterMobilizationPage;
