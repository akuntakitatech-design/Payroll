import React, { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft, CheckCircle2, ClipboardList, Package, Send, ShieldCheck, XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate, formatDateTime } from "@/lib/format";
import { PageBody } from "@/components/common/PageHeader";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const STATES = {
  DRAFT: { label: "Draft", variant: "secondary" },
  PENDING_APPROVAL: { label: "Menunggu Persetujuan", variant: "info" },
  COMPLETED: { label: "Selesai", variant: "success" },
  CANCELLED: { label: "Dibatalkan", variant: "destructive" },
};

const ITEM_STATES = {
  PENDING: { label: "Belum", variant: "outline" },
  DONE: { label: "Selesai", variant: "success" },
  NA: { label: "Tidak Berlaku", variant: "secondary" },
};

const todayISO = () => {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
};

const EmployeeExitClearanceDetailPage = () => {
  const { clearanceId } = useParams();
  const { can } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [naTarget, setNaTarget] = useState(null);
  const [approveOpen, setApproveOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [note, setNote] = useState("");
  const [cancelReason, setCancelReason] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data: res } = await api.get(`/exit-clearance/${clearanceId}`);
      setData(res);
    } catch (err) {
      setError(errorMessage(err, "Detail exit clearance tidak dapat dimuat."));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [clearanceId]);

  useEffect(() => { load(); }, [load]);

  const itemState = async (item, state, itemNote = "") => {
    setBusy(item.id);
    try {
      await api.patch(`/exit-clearance/${clearanceId}/items/${item.id}`,
        { item_state: state, note: itemNote || null });
      toast.success("Item checklist diperbarui.");
      setNaTarget(null);
      await load();
    } catch (err) {
      toast.error(errorMessage(err, "Item checklist gagal diperbarui."));
    } finally {
      setBusy("");
    }
  };

  const submit = async () => {
    setBusy("submit");
    try {
      const { data: res } = await api.post(`/exit-clearance/${clearanceId}/submit`);
      toast.success(res.message);
      await load();
    } catch (err) {
      toast.error(errorMessage(err, "Kasus gagal diajukan."));
    } finally {
      setBusy("");
    }
  };

  const approve = async () => {
    setBusy("approve");
    try {
      const { data: res } = await api.post(`/exit-clearance/${clearanceId}/approve`,
        { note: note.trim() || null });
      toast.success(res.message);
      setApproveOpen(false);
      setNote("");
      await load();
    } catch (err) {
      toast.error(errorMessage(err, "Persetujuan final gagal."));
    } finally {
      setBusy("");
    }
  };

  const cancel = async () => {
    setBusy("cancel");
    try {
      const { data: res } = await api.post(`/exit-clearance/${clearanceId}/cancel`,
        { reason: cancelReason.trim() });
      toast.success(res.message);
      setCancelOpen(false);
      setCancelReason("");
      await load();
    } catch (err) {
      toast.error(errorMessage(err, "Kasus gagal dibatalkan."));
    } finally {
      setBusy("");
    }
  };

  if (loading) {
    return <PageBody><Skeleton className="h-72 w-full rounded-xl" /></PageBody>;
  }
  if (error || !data) {
    return (
      <PageBody>
        <Card className="space-y-3 p-4" role="alert" data-testid="exit-detail-error">
          <p className="text-sm">{error || "Kasus tidak ditemukan."}</p>
          <div className="flex gap-2">
            <Button variant="outline" onClick={load}>Coba lagi</Button>
            <Button asChild variant="ghost">
              <Link to="/employees/exit-clearance">Kembali</Link>
            </Button>
          </div>
        </Card>
      </PageBody>
    );
  }

  const item = data.item;
  const employee = data.employee || {};
  const items = data.items || [];
  const outstanding = data.outstanding_assets || [];
  const progress = item.progress || { done: 0, total: 0 };
  const st = STATES[item.case_state] || { label: item.case_state_label, variant: "outline" };
  const editable = can("exit_clearance", "edit") && ["DRAFT", "PENDING_APPROVAL"].includes(item.case_state);
  const pendingItems = items.filter((i) => i.item_state === "PENDING").length;
  const today = todayISO();
  const canApproveNow = item.case_state === "PENDING_APPROVAL" && item.last_working_date <= today;

  return (
    <PageBody>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <Button asChild variant="ghost" size="sm" className="-ml-2">
            <Link to="/employees/exit-clearance">
              <ArrowLeft className="mr-1.5 h-4 w-4" />Exit Clearance
            </Link>
          </Button>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-page-title">{item.case_number}</h1>
            <Badge variant={st.variant}>{st.label}</Badge>
          </div>
          <p className="text-[13px] text-muted-foreground">
            {item.employee_name} · {item.employee_number || "-"} · {item.exit_type_label}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {editable && item.case_state === "DRAFT" && (
            <Button onClick={submit} disabled={busy === "submit" || pendingItems > 0}
              data-testid="exit-submit">
              <Send className="mr-1.5 h-4 w-4" />
              {pendingItems > 0 ? `${pendingItems} item belum diputuskan` : "Ajukan untuk Persetujuan"}
            </Button>
          )}
          {item.case_state === "PENDING_APPROVAL" && can("exit_clearance", "approve") && (
            <Button variant="default" onClick={() => { setNote(""); setApproveOpen(true); }}
              disabled={!canApproveNow} data-testid="exit-approve-open">
              <ShieldCheck className="mr-1.5 h-4 w-4" />Setujui Final
            </Button>
          )}
          {["DRAFT", "PENDING_APPROVAL"].includes(item.case_state) && can("exit_clearance", "delete") && (
            <Button variant="outline" onClick={() => { setCancelReason(""); setCancelOpen(true); }}
              data-testid="exit-cancel-open">
              <XCircle className="mr-1.5 h-4 w-4" />Batalkan Kasus
            </Button>
          )}
        </div>
      </div>

      {item.case_state === "PENDING_APPROVAL" && !canApproveNow && (
        <Card className="border-warning-border bg-warning-soft p-3 text-[13px] text-warning" role="status"
          data-testid="exit-approve-hint">
          Persetujuan final baru dapat dilakukan pada/setelah tanggal kerja terakhir
          ({formatDate(item.last_working_date)}).
        </Card>
      )}

      <div className="grid gap-3 lg:grid-cols-3">
        <Card className="border-border bg-card p-4 lg:col-span-2" data-testid="exit-case-info">
          <h2 className="text-section-title">Informasi Kasus</h2>
          <dl className="mt-3 grid gap-3 text-[13px] sm:grid-cols-2">
            <div>
              <dt className="text-muted-foreground">Karyawan</dt>
              <dd className="font-medium">{employee.full_name} · {employee.employee_number || "-"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Project saat ini</dt>
              <dd className="font-medium">{employee.project_name || item.project_name || "-"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Jabatan</dt>
              <dd className="font-medium">{employee.job_title || "-"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Status karyawan</dt>
              <dd className="font-medium">
                {employee.status_name || employee.status || "-"}
                {employee.status_category ? ` · ${employee.status_category}` : ""}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Tipe keluar</dt>
              <dd className="font-medium">{item.exit_type_label}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Tanggal kerja terakhir</dt>
              <dd className="font-medium">{formatDate(item.last_working_date)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Tanggal pengajuan</dt>
              <dd className="font-medium">{formatDate(item.request_date)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Terakhir diperbarui</dt>
              <dd className="font-medium">{formatDateTime(item.updated_at)}</dd>
            </div>
            {item.reason && (
              <div className="sm:col-span-2">
                <dt className="text-muted-foreground">Alasan keluar</dt>
                <dd className="font-medium">{item.reason}</dd>
              </div>
            )}
            {item.notes && (
              <div className="sm:col-span-2">
                <dt className="text-muted-foreground">Catatan</dt>
                <dd className="whitespace-pre-line">{item.notes}</dd>
              </div>
            )}
            {item.decision_note && (
              <div className="sm:col-span-2">
                <dt className="text-muted-foreground">Catatan keputusan</dt>
                <dd className="whitespace-pre-line">{item.decision_note}</dd>
              </div>
            )}
            {item.cancel_reason && (
              <div className="sm:col-span-2">
                <dt className="text-muted-foreground">Alasan pembatalan</dt>
                <dd>{item.cancel_reason}</dd>
              </div>
            )}
          </dl>
        </Card>

        <div className="space-y-3">
          <Card className="border-border bg-card p-4" data-testid="exit-progress">
            <div className="flex items-center justify-between">
              <h2 className="text-section-title">Progres Serah Terima</h2>
              <Badge variant={progress.total && progress.done === progress.total ? "success" : "outline"}>
                {progress.done}/{progress.total}
              </Badge>
            </div>
            <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-muted">
              <div className="h-full bg-primary transition-all"
                style={{ width: `${progress.total ? Math.round((progress.done / progress.total) * 100) : 0}%` }} />
            </div>
            <p className="mt-2 flex items-start gap-1.5 text-[11px] text-muted-foreground">
              <ClipboardList className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              Semua item harus Selesai atau Tidak Berlaku sebelum persetujuan final.
            </p>
          </Card>

          <Card className={`border-border p-4 ${outstanding.length ? "bg-warning-soft" : "bg-card"}`}
            data-testid="exit-outstanding">
            <div className="flex items-center justify-between">
              <h2 className="text-section-title">Aset Outstanding</h2>
              <Badge variant={outstanding.length ? "warning" : "success"}>{outstanding.length}</Badge>
            </div>
            {outstanding.length === 0 ? (
              <p className="mt-2 text-[13px] text-muted-foreground">
                Tidak ada aset aktif yang masih dipegang karyawan.
              </p>
            ) : (
              <>
                <p className="mt-2 flex items-start gap-1.5 text-[12px] text-warning">
                  <Package className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  Aset berikut harus dikembalikan sebelum item GA ditutup dan persetujuan final.
                </p>
                <ul className="mt-2 space-y-1 text-[12px]">
                  {outstanding.map((a) => (
                    <li key={a.holding_id || a.asset_id} className="flex justify-between gap-2">
                      <span className="font-medium">{a.asset_code || "-"}</span>
                      <span className="truncate text-muted-foreground">{a.asset_name || "-"}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </Card>
        </div>
      </div>

      <Card className="border-border bg-card" data-testid="exit-checklist">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-section-title">Checklist Serah Terima</h2>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            Tandai Selesai bila sudah diserahkan; Tidak Berlaku wajib disertai catatan alasan.
          </p>
        </div>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">#</TableHead>
                <TableHead>Bagian</TableHead>
                <TableHead>Item</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Catatan</TableHead>
                <TableHead className="text-right">Aksi</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((row) => {
                const ist = ITEM_STATES[row.item_state] || { label: row.item_state_label, variant: "outline" };
                const locked = !editable || busy === row.id;
                return (
                  <TableRow key={row.id} data-testid={`exit-item-${row.id}`}>
                    <TableCell className="text-muted-foreground">{row.line_no}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{row.category_label}</Badge>
                    </TableCell>
                    <TableCell className="font-medium">{row.name}</TableCell>
                    <TableCell><Badge variant={ist.variant}>{ist.label}</Badge></TableCell>
                    <TableCell className="max-w-[260px] text-[12px] text-muted-foreground">
                      <span className="line-clamp-2">{row.note || "-"}</span>
                    </TableCell>
                    <TableCell className="text-right">
                      {editable ? (
                        <div className="flex justify-end gap-1">
                          {row.item_state !== "DONE" && (
                            <Button size="sm" variant="outline" disabled={locked}
                              onClick={() => itemState(row, "DONE")}
                              data-testid={`exit-item-done-${row.id}`}>
                              <CheckCircle2 className="mr-1 h-3.5 w-3.5" />Selesai
                            </Button>
                          )}
                          {row.item_state !== "NA" && (
                            <Button size="sm" variant="ghost" disabled={locked}
                              onClick={() => setNaTarget({ item: row, note: row.note || "" })}
                              data-testid={`exit-item-na-${row.id}`}>
                              N/A
                            </Button>
                          )}
                          {row.item_state !== "PENDING" && (
                            <Button size="sm" variant="ghost" disabled={locked}
                              onClick={() => itemState(row, "PENDING")}
                              data-testid={`exit-item-reset-${row.id}`}>
                              Reset
                            </Button>
                          )}
                        </div>
                      ) : (
                        <span className="text-[11px] text-muted-foreground">-</span>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </Card>

      <Dialog open={!!naTarget} onOpenChange={(open) => !open && setNaTarget(null)}>
        <DialogContent className="bg-card sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Tandai Tidak Berlaku</DialogTitle>
            <DialogDescription>
              {naTarget?.item?.name}. Jelaskan alasan item ini tidak berlaku untuk karyawan tersebut.
            </DialogDescription>
          </DialogHeader>
          <Textarea rows={3} value={naTarget?.note || ""} placeholder="Alasan tidak berlaku (wajib)"
            onChange={(e) => setNaTarget((t) => ({ ...t, note: e.target.value }))}
            data-testid="exit-na-note" />
          <DialogFooter>
            <Button variant="outline" onClick={() => setNaTarget(null)}>Batal</Button>
            <Button disabled={(naTarget?.note || "").trim().length < 3}
              onClick={() => itemState(naTarget.item, "NA", naTarget.note.trim())}
              data-testid="exit-na-submit">
              Simpan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={approveOpen} onOpenChange={(open) => !busy && setApproveOpen(open)}>
        <DialogContent className="bg-card sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Setujui exit clearance</DialogTitle>
            <DialogDescription>
              Status karyawan akan diubah menjadi Tidak Aktif efektif {formatDate(item.last_working_date)}.
              Pastikan seluruh serah terima benar-benar selesai.
            </DialogDescription>
          </DialogHeader>
          <Textarea rows={3} value={note} placeholder="Catatan persetujuan (opsional)"
            onChange={(e) => setNote(e.target.value)} data-testid="exit-approve-note" />
          <DialogFooter>
            <Button variant="outline" onClick={() => setApproveOpen(false)} disabled={busy === "approve"}>
              Batal
            </Button>
            <Button onClick={approve} disabled={busy === "approve"} data-testid="exit-approve-submit">
              {busy === "approve" ? "Memproses…" : "Setujui & Nonaktifkan"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={cancelOpen} onOpenChange={(open) => !busy && setCancelOpen(open)}>
        <DialogContent className="bg-card sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Batalkan kasus</DialogTitle>
            <DialogDescription>
              Kasus akan ditandai Dibatalkan. Status karyawan tidak berubah.
            </DialogDescription>
          </DialogHeader>
          <Textarea rows={3} value={cancelReason} placeholder="Alasan pembatalan (wajib)"
            onChange={(e) => setCancelReason(e.target.value)} data-testid="exit-cancel-reason" />
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelOpen(false)} disabled={busy === "cancel"}>
              Kembali
            </Button>
            <Button variant="destructive" onClick={cancel} disabled={busy === "cancel"}
              data-testid="exit-cancel-submit">
              {busy === "cancel" ? "Membatalkan…" : "Batalkan Kasus"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageBody>
  );
};

export default EmployeeExitClearanceDetailPage;
