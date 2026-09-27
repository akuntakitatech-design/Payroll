import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import {
  AlertTriangle, ArrowLeft, CheckCircle2, Clock, FileText, Fingerprint, Loader2, MessageSquareWarning, RefreshCw, StickyNote, XCircle,
} from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { formatDateTime, formatFileSize } from "@/lib/format";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import { ChangeCompareTable } from "@/components/employee-verification/ChangeCompareTable";
import { StatusPill, UV_BASE } from "@/pages/EmployeeUpdateVerificationPage";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";

const DECISION_LABEL = { APPROVED: "Disetujui", REJECTED: "Ditolak", REVISION_REQUESTED: "Diminta perbaikan" };
const DECISION_ICON = { APPROVED: CheckCircle2, REJECTED: XCircle, REVISION_REQUESTED: MessageSquareWarning };
const PURPOSE_LABEL = { DOCUMENT: "Dokumen", PHOTO: "Foto profil", CUSTOM_FIELD: "Pertanyaan tambahan" };
const FILE_STATUS = { active: "Menunggu", PROMOTED: "Diterapkan", REJECTED: "Tidak diterapkan" };

const Score = ({ label, snap, testid }) => (
  <div className="rounded-lg border bg-card p-3" data-testid={testid}>
    <p className="text-xs text-muted-foreground">{label}</p>
    <p className="text-xl font-bold tabular-nums">{snap?.score_pct != null ? `${Math.round(snap.score_pct)}%` : "—"}</p>
  </div>
);

function History({ d }) {
  const events = [];
  (d.history || []).forEach((h) => {
    if (h.submitted_at) events.push({ at: h.submitted_at, title: h.round > 1 ? `Dikirim ulang (putaran ${h.round})` : "Dikirim karyawan", icon: Clock });
    events.push({ at: h.decided_at, title: `${DECISION_LABEL[h.decision] || h.decision} oleh ${h.reviewer || "HR"}`, note: h.note, icon: DECISION_ICON[h.decision] || Clock, decision: h.decision });
  });
  if (d.status === "PENDING_HR_VERIFICATION" && d.submitted_at) events.push({ at: d.submitted_at, title: d.revision_count ? `Dikirim ulang (putaran ${d.revision_count + 1})` : "Dikirim karyawan", icon: Clock, current: true });
  if (!events.length) return <p className="text-sm text-muted-foreground">Belum ada riwayat keputusan.</p>;
  return (
    <ol className="space-y-3" data-testid="uv-history">
      {events.map((e, i) => {
        const Icon = e.icon;
        return (
          <li key={i} className="flex gap-3">
            <span className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border ${e.decision === "APPROVED" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : e.decision === "REJECTED" ? "border-rose-200 bg-rose-50 text-rose-700" : e.decision ? "border-amber-300 bg-amber-50 text-amber-800" : "bg-muted text-muted-foreground"}`}><Icon className="h-3.5 w-3.5" /></span>
            <div className="min-w-0">
              <p className="text-sm font-medium">{e.title}</p>
              <p className="text-xs text-muted-foreground">{e.at ? formatDateTime(e.at) : ""}</p>
              {e.note && <p className="mt-1 whitespace-pre-line break-words rounded-md bg-muted/60 p-2 text-sm">{e.note}</p>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export default function EmployeeUpdateVerificationDetailPage() {
  const { id } = useParams();
  const [d, setD] = useState(null);
  const [error, setError] = useState(null);
  const [resolutions, setResolutions] = useState({});
  const [flagged, setFlagged] = useState([]);
  const [dialog, setDialog] = useState(null); // approve | reject | revision
  const [text, setText] = useState("");
  const [confirmId, setConfirmId] = useState(false);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try { const { data } = await api.get(`${UV_BASE}/${id}`); setD(data); setResolutions({}); setFlagged([]); }
    catch (e) { setError(errorMessage(e)); }
  }, [id]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => () => { if (preview?.url) URL.revokeObjectURL(preview.url); }, [preview]);

  const unresolved = useMemo(() => (d?.conflicts || []).filter((k) => !resolutions[k]), [d, resolutions]);
  const openPreview = async (fileId) => {
    const f = d.files.find((x) => x.id === fileId);
    try {
      const res = await api.get(`${UV_BASE}/${id}/files/${fileId}`, { responseType: "blob" });
      setPreview({ url: URL.createObjectURL(res.data), mime: f?.mime_type || res.data.type, name: f?.file_name || "Berkas" });
    } catch (e) { toast.error("Berkas tidak dapat dibuka. Penyimpanan berkas mungkin sedang tidak tersedia."); }
  };
  const openDialog = (kind) => { setText(""); setConfirmId(false); setDialog(kind); };
  const decide = async () => {
    setBusy(true);
    try {
      let res;
      if (dialog === "approve") res = await api.post(`${UV_BASE}/${id}/approve`, { version: d.version, resolutions, confirm_identity: confirmId, note: text.trim() || null });
      if (dialog === "reject") res = await api.post(`${UV_BASE}/${id}/reject`, { version: d.version, reason: text.trim() });
      if (dialog === "revision") res = await api.post(`${UV_BASE}/${id}/request-revision`, { version: d.version, note: text.trim(), items: flagged });
      toast.success(res.data.message);
      setD(res.data.submission); setResolutions({}); setFlagged([]); setDialog(null);
    } catch (e) {
      const st = e?.response?.status;
      toast.error(errorMessage(e));
      if (st === 409) { setDialog(null); load(); }
    } finally { setBusy(false); }
  };

  if (error) return (<><PageHeader title="Verifikasi Pembaruan Data" /><PageBody><Alert data-testid="uv-detail-error"><AlertDescription className="flex flex-wrap items-center gap-2">{error}<Button size="sm" variant="outline" onClick={load} data-testid="uv-detail-retry"><RefreshCw className="mr-1.5 h-3.5 w-3.5" />Coba lagi</Button><Button size="sm" variant="ghost" asChild><Link to={UV_BASE}>Kembali ke daftar</Link></Button></AlertDescription></Alert></PageBody></>);
  if (!d) return (<><PageHeader title="Verifikasi Pembaruan Data" /><PageBody><div className="space-y-3" data-testid="uv-detail-loading"><Skeleton className="h-24 w-full" /><Skeleton className="h-64 w-full" /></div></PageBody></>);

  const identityPending = (d.identity_fields || []).length > 0;
  const needText = dialog === "reject" || dialog === "revision";
  const textOk = !needText || text.trim().length >= 5;
  const canApprove = d.can_decide && unresolved.length === 0;
  return (
    <>
      <PageHeader
        title={<span className="flex flex-wrap items-center gap-2">{d.employee.full_name}<StatusPill status={d.status} label={d.status_label} testid="uv-detail-status" /></span>}
        subtitle={`${d.employee.employee_number || ""}${d.employee.position ? ` · ${d.employee.position}` : ""}${d.employee.project ? ` · ${d.employee.project}` : ""}${d.submitted_at ? ` · dikirim ${formatDateTime(d.submitted_at)}` : ""}`}
        actions={<Button variant="outline" asChild data-testid="uv-back"><Link to={UV_BASE}><ArrowLeft className="mr-1.5 h-4 w-4" />Kembali</Link></Button>} />
      <PageBody>
        {d.employee_inactive && <Alert className="border-rose-300 bg-rose-50" data-testid="uv-inactive-alert"><AlertDescription className="text-rose-900">Karyawan tidak lagi aktif. Pengajuan ini tidak dapat diterapkan — hanya dapat ditolak.</AlertDescription></Alert>}
        {d.has_conflict && d.can_decide && (
          <Alert className="border-amber-300 bg-amber-50" data-testid="uv-conflict-alert">
            <AlertDescription className="flex items-start gap-2 text-amber-900"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>Ada <b>{d.conflicts.length}</b> data yang diubah pihak lain setelah karyawan mengirim pengajuan. Putuskan setiap konflik (Pakai usulan / Pertahankan data saat ini) sebelum menyetujui.</span></AlertDescription>
          </Alert>
        )}
        {identityPending && d.can_decide && <Alert className="border-violet-200 bg-violet-50" data-testid="uv-identity-alert"><AlertDescription className="flex items-start gap-2 text-violet-900"><Fingerprint className="mt-0.5 h-4 w-4 shrink-0" /><span>Pengajuan mengubah <b>data identitas</b>. Data ini juga dipakai untuk verifikasi portal karyawan — pastikan sesuai dokumen resmi (KTP).</span></AlertDescription></Alert>}
        {d.status !== "PENDING_HR_VERIFICATION" && d.review_note && (
          <Alert data-testid="uv-review-note"><AlertDescription><p className="text-sm font-semibold">Catatan HR ({d.reviewed_by_name || "HR"}, {d.reviewed_at ? formatDateTime(d.reviewed_at) : ""})</p><p className="whitespace-pre-line break-words text-sm">{d.review_note}</p></AlertDescription></Alert>
        )}

        <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
          <div className="space-y-4">
            {d.sections.map((s) => (
              <Card key={s.key} data-testid={`uv-section-${s.key}`}>
                <CardHeader className="pb-3"><CardTitle className="flex items-center gap-2 text-base">{s.label}<Badge variant="secondary" className="font-medium">{s.items.length} item</Badge></CardTitle></CardHeader>
                <CardContent className="pt-0">
                  <ChangeCompareTable items={s.items} resolutions={resolutions} onResolve={(k, v) => setResolutions((r) => ({ ...r, [k]: v }))}
                    flagged={flagged} onFlag={(k) => setFlagged((f) => (f.includes(k) ? f.filter((x) => x !== k) : [...f, k]))}
                    canDecide={d.can_decide} onPreview={openPreview} />
                </CardContent>
              </Card>
            ))}
            {!d.sections.length && <Card><CardContent className="p-6 text-sm text-muted-foreground" data-testid="uv-no-changes">Tidak ada perubahan data pada pengajuan ini.</CardContent></Card>}
          </div>
          <div className="space-y-4">
            <Card data-testid="uv-completeness">
              <CardHeader className="pb-2"><CardTitle className="text-base">Kelengkapan Data (01F)</CardTitle><CardDescription>Skor resmi dihitung dari data master.</CardDescription></CardHeader>
              <CardContent className="grid grid-cols-2 gap-2">
                <Score label="Saat dikirim" snap={d.completeness.before} testid="uv-score-before" />
                <Score label={d.completeness.after ? "Setelah diterapkan" : "Saat ini"} snap={d.completeness.after || d.completeness.current} testid="uv-score-after" />
              </CardContent>
            </Card>
            {(d.notes || d.no_npwp) && (
              <Card data-testid="uv-notes">
                <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2 text-base"><StickyNote className="h-4 w-4" />Catatan karyawan</CardTitle></CardHeader>
                <CardContent className="space-y-2 text-sm">
                  {d.notes && <p className="whitespace-pre-line break-words">{d.notes}</p>}
                  {d.no_npwp && <p className="rounded-md bg-sky-50 p-2 text-sky-900" data-testid="uv-no-npwp">Karyawan menyatakan tidak memiliki NPWP — <b>tidak diterapkan otomatis</b>. Sesuaikan di Struktur Gaji bila perlu.</p>}
                </CardContent>
              </Card>
            )}
            {d.files.length > 0 && (
              <Card data-testid="uv-files">
                <CardHeader className="pb-2"><CardTitle className="text-base">Lampiran ({d.files.length})</CardTitle></CardHeader>
                <CardContent className="space-y-2">
                  {d.files.map((f) => (
                    <button type="button" key={f.id} onClick={() => openPreview(f.id)} className="flex w-full items-start gap-2 rounded-md border p-2 text-left transition-colors hover:bg-muted/50" data-testid={`uv-file-${f.id}`}>
                      <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                      <span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{f.document_type_name || PURPOSE_LABEL[f.purpose]}</span><span className="block truncate text-xs text-muted-foreground">{f.file_name} · {formatFileSize(f.file_size)}</span></span>
                      <Badge variant="outline" className="shrink-0 text-[10px]">{FILE_STATUS[f.status] || f.status}</Badge>
                    </button>
                  ))}
                </CardContent>
              </Card>
            )}
            <Card><CardHeader className="pb-2"><CardTitle className="text-base">Riwayat keputusan</CardTitle></CardHeader><CardContent><History d={d} /></CardContent></Card>
          </div>
        </div>
      </PageBody>

      {d.can_decide && (
        <div className="sticky bottom-0 z-20 border-t bg-card px-4 py-3 shadow-[0_-4px_12px_rgba(0,0,0,0.04)] sm:px-6" data-testid="uv-action-bar">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-muted-foreground" data-testid="uv-action-hint">{unresolved.length ? `${unresolved.length} konflik belum diputuskan.` : "Setujui = semua perubahan diterapkan ke data resmi dalam satu langkah."}{flagged.length ? ` · ${flagged.length} item ditandai perlu perbaikan.` : ""}</p>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" className="border-rose-200 text-rose-700 hover:bg-rose-50" onClick={() => openDialog("reject")} data-testid="uv-reject-button"><XCircle className="mr-1.5 h-4 w-4" />Tolak</Button>
              <Button variant="outline" className="border-amber-300 text-amber-800 hover:bg-amber-50" onClick={() => openDialog("revision")} data-testid="uv-revision-button"><MessageSquareWarning className="mr-1.5 h-4 w-4" />Minta Perbaikan</Button>
              <Button onClick={() => openDialog("approve")} disabled={!canApprove} data-testid="uv-approve-button"><CheckCircle2 className="mr-1.5 h-4 w-4" />Setujui &amp; Terapkan</Button>
            </div>
          </div>
        </div>
      )}

      <Dialog open={!!dialog} onOpenChange={(o) => !o && !busy && setDialog(null)}>
        <DialogContent className="sm:max-w-lg" data-testid={`uv-dialog-${dialog}`}>
          <DialogHeader>
            <DialogTitle>{dialog === "approve" ? "Setujui & terapkan pengajuan?" : dialog === "reject" ? "Tolak pengajuan?" : "Minta perbaikan ke karyawan?"}</DialogTitle>
            <DialogDescription>
              {dialog === "approve" && "Semua perubahan yang ditandai “Akan diterapkan” dan konflik yang Anda pilih “Pakai usulan” akan disimpan ke data resmi karyawan, dokumen dan foto dipromosikan, lalu kelengkapan data dihitung ulang."}
              {dialog === "reject" && "Tidak ada data resmi yang diubah. Lampiran tidak akan menjadi dokumen resmi. Karyawan dapat melihat alasan penolakan dan mengajukan pembaruan baru."}
              {dialog === "revision" && "Pengajuan dikembalikan ke karyawan (pengajuan yang sama) agar dapat diperbaiki dan dikirim ulang. Tidak ada data resmi yang diubah."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            {dialog === "revision" && flagged.length > 0 && <p className="text-sm text-muted-foreground" data-testid="uv-flag-count">{flagged.length} item ditandai perlu diperbaiki.</p>}
            {dialog === "approve" && identityPending && (
              <label className="flex items-start gap-2 rounded-md border border-violet-200 bg-violet-50 p-3 text-sm text-violet-900">
                <Checkbox checked={confirmId} onCheckedChange={(v) => setConfirmId(!!v)} data-testid="uv-confirm-identity" />
                <span>Saya sudah memeriksa perubahan data identitas ({d.identity_fields.join(", ")}) terhadap dokumen resmi.</span>
              </label>
            )}
            <div className="space-y-1.5">
              <Label htmlFor="uv-text">{dialog === "approve" ? "Catatan (opsional)" : dialog === "reject" ? "Alasan penolakan (wajib)" : "Catatan perbaikan untuk karyawan (wajib)"}</Label>
              <Textarea id="uv-text" rows={4} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)}
                placeholder={dialog === "reject" ? "Contoh: Foto KTP tidak terbaca." : dialog === "revision" ? "Contoh: Mohon lengkapi RT/RW pada alamat KTP." : ""} data-testid="uv-dialog-text" />
              {needText && !textOk && <p className="text-xs text-muted-foreground">Minimal 5 karakter.</p>}
            </div>
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setDialog(null)} disabled={busy} data-testid="uv-dialog-cancel">Batal</Button>
            <Button onClick={decide} disabled={busy || !textOk || (dialog === "approve" && identityPending && !confirmId)}
              className={dialog === "reject" ? "bg-rose-600 hover:bg-rose-700" : dialog === "revision" ? "bg-amber-600 hover:bg-amber-700" : ""} data-testid="uv-dialog-confirm">
              {busy && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
              {dialog === "approve" ? "Setujui & Terapkan" : dialog === "reject" ? "Tolak Pengajuan" : "Kirim Permintaan Perbaikan"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!preview} onOpenChange={(o) => !o && setPreview(null)}>
        <DialogContent className="max-h-[92dvh] sm:max-w-3xl" data-testid="uv-preview-dialog">
          <DialogHeader><DialogTitle className="truncate pr-6">{preview?.name}</DialogTitle><DialogDescription>Lampiran pengajuan (privat).</DialogDescription></DialogHeader>
          {preview && (preview.mime?.startsWith("image/")
            ? <img src={preview.url} alt={preview.name} className="max-h-[70dvh] w-full rounded-md object-contain" />
            : <iframe title={preview.name} src={preview.url} className="h-[70dvh] w-full rounded-md border" />)}
        </DialogContent>
      </Dialog>
    </>
  );
}
