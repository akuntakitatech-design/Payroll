import React, { useCallback, useEffect, useRef, useState } from "react";
import { Download, Eye, FileText, History, Paperclip, RefreshCw, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";

import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { downloadFile } from "@/lib/download";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

/* Phase 2A CP4 - Dokumen Transaksi Aset. File fisik tersimpan sekali di object storage; panel transaksi & Profil
   Karyawan membaca metadata yang sama. Backend tetap menegakkan permission & scope - UI hanya kenyamanan. */

export const DOC_TYPES = [
  ["SIGNED_BAST", "BAST Ditandatangani"],
  ["CONDITION_PHOTO", "Foto Kondisi"],
  ["HANDOVER_REPORT", "Berita Acara / Surat Serah Terima"],
  ["DAMAGE_OR_LOSS_EVIDENCE", "Bukti Kerusakan / Kehilangan"],
  ["SUPPORTING_DOCUMENT", "Dokumen Pendukung"],
  ["OTHER", "Lainnya"],
];
const EXT = ["pdf", "jpg", "jpeg", "png"];
const MAX_MB = 10;
const STATUS_TONE = { ACTIVE: "border-success/40 text-success", SUPERSEDED: "border-warning/40 text-warning", DELETED: "text-muted-foreground" };

const fmtSize = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round((n || 0) / 1024))} KB`);
const fmtTime = (v) => (v ? new Date(String(v).endsWith("Z") || String(v).includes("+") ? v : `${v}Z`).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" }) : "-");

export const viewDocument = async (doc) => {
  const win = window.open("", "_blank");
  try {
    const res = await api.get(`/asset-documents/${doc.id}/file`, { responseType: "blob" });
    const url = window.URL.createObjectURL(new Blob([res.data], { type: doc.mime_type }));
    if (win) win.location.href = url;
    else window.location.assign(url);
    window.setTimeout(() => window.URL.revokeObjectURL(url), 60000);
  } catch (e) {
    if (win) win.close();
    toast.error(errorMessage(e, "Dokumen gagal dibuka."));
  }
};

export const downloadDocument = async (doc) => {
  try {
    await downloadFile(`/asset-documents/${doc.id}/file`, doc.file_name, { params: { download: true } });
  } catch (e) {
    toast.error(errorMessage(e, "Dokumen gagal diunduh."));
  }
};

export const DocStatusBadge = ({ doc, testId }) => (
  <Badge variant="outline" className={cn("whitespace-nowrap", STATUS_TONE[doc.doc_status])} data-testid={testId}>
    {doc.status_label}{doc.document_type === "SIGNED_BAST" ? ` · v${doc.version_no}` : ""}
  </Badge>
);

export const DocumentRow = ({ doc, actions, meta, testId }) => (
  <li className="flex flex-col gap-2 rounded-lg border border-border bg-card p-3 sm:flex-row sm:items-center" data-testid={testId}>
    <FileText className="hidden h-5 w-5 shrink-0 text-muted-foreground sm:block" aria-hidden />
    <div className="min-w-0 flex-1 space-y-0.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{doc.document_type_label}</span>
        <DocStatusBadge doc={doc} testId={`${testId}-status`} />
      </div>
      <p className="truncate text-[13px]" title={doc.file_name}>{doc.file_name} <span className="text-muted-foreground">· {fmtSize(doc.file_size)}</span></p>
      <p className="text-[12px] text-muted-foreground">
        Diunggah {fmtTime(doc.uploaded_at)} oleh {doc.uploaded_by_name || "-"}
        {doc.asset_code ? ` · Aset ${doc.asset_code}` : ""}{doc.document_date ? ` · Tgl dokumen ${formatDate(doc.document_date)}` : ""}
        {doc.doc_status === "DELETED" ? ` · Dihapus ${fmtTime(doc.deleted_at)} oleh ${doc.deleted_by_name || "-"}${doc.delete_reason ? ` (${doc.delete_reason})` : ""}` : ""}
      </p>
      {meta}
    </div>
    <div className="flex flex-wrap gap-1.5">{actions}</div>
  </li>
);

const UploadDialog = ({ open, onOpenChange, sourceType, sourceId, assets, replace, canSigned, onDone }) => {
  const [type, setType] = useState("");
  const [assetId, setAssetId] = useState("none");
  const [docDate, setDocDate] = useState("");
  const [notes, setNotes] = useState("");
  const [file, setFile] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef(null);
  useEffect(() => {
    if (open) {
      setType(replace ? "SIGNED_BAST" : "");
      setAssetId("none");
      setDocDate("");
      setNotes("");
      setFile(null);
      setErr("");
    }
  }, [open, replace]);
  const pick = (f) => {
    setErr("");
    if (!f) return setFile(null);
    const ext = (f.name.split(".").pop() || "").toLowerCase();
    if (!EXT.includes(ext)) return setErr("Format file tidak didukung. Gunakan PDF, JPG, JPEG, atau PNG.");
    if (f.size > MAX_MB * 1048576) return setErr("Ukuran file melebihi batas 10 MB.");
    setFile(f);
  };
  const submit = async () => {
    if (!type) return setErr("Pilih jenis dokumen.");
    if (!file) return setErr("Pilih file terlebih dahulu.");
    setBusy(true);
    const fd = new FormData();
    fd.append("file", file);
    if (docDate) fd.append("document_date", docDate);
    if (notes) fd.append("notes", notes);
    try {
      if (replace) {
        await api.post(`/asset-documents/${replace.id}/replace`, fd);
        toast.success("Versi baru BAST ditandatangani tersimpan. Versi lama ditandai digantikan.");
      } else {
        fd.append("source_type", sourceType);
        fd.append("source_id", sourceId);
        fd.append("document_type", type);
        if (assetId !== "none") fd.append("asset_id", assetId);
        await api.post("/asset-documents", fd);
        toast.success("Dokumen berhasil diunggah.");
      }
      onOpenChange(false);
      onDone();
    } catch (e) {
      setErr(errorMessage(e, "Dokumen gagal diunggah."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" data-testid="doc-upload-dialog">
        <DialogHeader>
          <DialogTitle>{replace ? "Ganti Versi BAST Ditandatangani" : "Unggah Dokumen"}</DialogTitle>
          <DialogDescription>
            {replace ? `Versi ${replace.version_no} akan ditandai "Digantikan" (tidak dihapus).` : "PDF, JPG, JPEG, atau PNG · maks. 10 MB per file · maks. 10 dokumen aktif per transaksi."}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {!replace && (
            <div className="space-y-1.5">
              <Label>Jenis Dokumen *</Label>
              <Select value={type} onValueChange={setType}>
                <SelectTrigger data-testid="doc-upload-type"><SelectValue placeholder="Pilih jenis dokumen" /></SelectTrigger>
                <SelectContent>
                  {DOC_TYPES.filter(([k]) => k !== "SIGNED_BAST" || canSigned).map(([k, l]) => (
                    <SelectItem key={k} value={k} data-testid={`doc-type-option-${k}`}>{l}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {!canSigned && <p className="text-[12px] text-muted-foreground">BAST Ditandatangani tersedia setelah transaksi dipublish.</p>}
            </div>
          )}
          {!replace && assets?.length > 0 && (
            <div className="space-y-1.5">
              <Label>Aset terkait (opsional)</Label>
              <Select value={assetId} onValueChange={setAssetId}>
                <SelectTrigger data-testid="doc-upload-asset"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Semua aset pada transaksi</SelectItem>
                  {assets.map((a) => <SelectItem key={a.asset_id} value={a.asset_id}>{a.asset_code} — {a.asset_name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="doc-upload-date">Tanggal Dokumen (opsional)</Label>
            <Input id="doc-upload-date" type="date" value={docDate} onChange={(e) => setDocDate(e.target.value)} data-testid="doc-upload-date" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="doc-upload-file">File *</Label>
            <Input id="doc-upload-file" ref={inputRef} type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
              onChange={(e) => pick(e.target.files?.[0])} data-testid="doc-upload-file" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="doc-upload-notes">Catatan (opsional)</Label>
            <Textarea id="doc-upload-notes" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} data-testid="doc-upload-notes" />
          </div>
          {err && <p className="text-sm text-danger" role="alert" data-testid="doc-upload-error">{err}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="doc-upload-cancel">Batal</Button>
          <Button onClick={submit} disabled={busy} data-testid="doc-upload-submit">
            <Upload className="mr-1.5 h-4 w-4" />{busy ? "Mengunggah..." : replace ? "Simpan Versi Baru" : "Unggah"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export const AssetDocumentsPanel = ({ sourceType, sourceId, docState, assets, testId = "doc-panel" }) => {
  const { can } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [history, setHistory] = useState(false);
  const [upload, setUpload] = useState(false);
  const [replace, setReplace] = useState(null);
  const [del, setDel] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    setError("");
    try {
      const res = await api.get("/asset-documents", { params: { source_type: sourceType, source_id: sourceId, include_history: history } });
      setData(res.data);
    } catch (e) {
      setError(errorMessage(e, "Dokumen gagal dimuat."));
    }
  }, [sourceType, sourceId, history]);
  useEffect(() => { if (sourceId) load(); }, [load, sourceId]);
  if (!can("asset_document", "view") || !sourceId || docState === "CANCELLED") return null;
  const perm = data?.can || {};
  const full = (data?.active_count || 0) >= (data?.max_per_source || 10);
  const remove = async () => {
    setBusy(true);
    try {
      await api.delete(`/asset-documents/${del.id}`, { params: { reason: del.reason || undefined } });
      toast.success("Dokumen dihapus (soft delete, tercatat di audit trail).");
      setDel(null);
      load();
    } catch (e) {
      toast.error(errorMessage(e, "Dokumen gagal dihapus."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="space-y-3 rounded-xl border border-border p-4" data-testid={testId} aria-labelledby={`${testId}-title`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 id={`${testId}-title`} className="flex items-center gap-2 text-sm font-semibold"><Paperclip className="h-4 w-4" />Dokumen Transaksi</h3>
          <p className="text-[12px] text-muted-foreground" data-testid={`${testId}-count`}>
            {data ? `${data.active_count} dari ${data.max_per_source} dokumen aktif` : "Memuat..."} · otomatis tampil di Profil Karyawan
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-[12px] text-muted-foreground">
            <Switch checked={history} onCheckedChange={setHistory} data-testid={`${testId}-history-toggle`} aria-label="Tampilkan versi lama & dokumen dihapus" />
            <History className="h-3.5 w-3.5" />Riwayat
          </label>
          {perm.create && (
            <Button size="sm" onClick={() => setUpload(true)} disabled={full} title={full ? "Batas 10 dokumen aktif tercapai" : undefined} data-testid={`${testId}-upload-button`}>
              <Upload className="mr-1.5 h-4 w-4" />Unggah Dokumen
            </Button>
          )}
        </div>
      </div>
      {error && (
        <div className="flex items-center gap-2 text-sm text-danger" role="alert" data-testid={`${testId}-error`}>
          {error}<Button size="sm" variant="outline" onClick={load}><RefreshCw className="mr-1 h-3.5 w-3.5" />Coba lagi</Button>
        </div>
      )}
      {!data && !error && <Skeleton className="h-16 w-full" />}
      {data && data.items.length === 0 && (
        <p className="rounded-lg border border-dashed border-border p-4 text-center text-[13px] text-muted-foreground" data-testid={`${testId}-empty`}>
          Belum ada dokumen. {perm.create ? "Unggah BAST bertanda tangan, foto kondisi, atau dokumen pendukung." : ""}
        </p>
      )}
      {data && data.items.length > 0 && (
        <ul className="space-y-2" data-testid={`${testId}-list`}>
          {data.items.map((d) => (
            <DocumentRow key={d.id} doc={d} testId={`${testId}-row-${d.id}`} actions={(
              <>
                {d.doc_status !== "DELETED" && (
                  <>
                    <Button size="sm" variant="outline" onClick={() => viewDocument(d)} data-testid={`${testId}-view-${d.id}`}><Eye className="mr-1 h-3.5 w-3.5" />Lihat</Button>
                    <Button size="sm" variant="outline" onClick={() => downloadDocument(d)} data-testid={`${testId}-download-${d.id}`}><Download className="mr-1 h-3.5 w-3.5" />Unduh</Button>
                  </>
                )}
                {d.doc_status === "ACTIVE" && d.document_type === "SIGNED_BAST" && perm.create && (
                  <Button size="sm" variant="outline" onClick={() => setReplace(d)} data-testid={`${testId}-replace-${d.id}`}><RefreshCw className="mr-1 h-3.5 w-3.5" />Ganti Versi</Button>
                )}
                {d.doc_status === "ACTIVE" && d.document_type !== "SIGNED_BAST" && perm.delete && (
                  <Button size="sm" variant="outline" className="text-danger" onClick={() => setDel({ ...d, reason: "" })} data-testid={`${testId}-delete-${d.id}`}><Trash2 className="mr-1 h-3.5 w-3.5" />Hapus</Button>
                )}
              </>
            )} />
          ))}
        </ul>
      )}
      <UploadDialog open={upload || !!replace} onOpenChange={(v) => { if (!v) { setUpload(false); setReplace(null); } }} sourceType={sourceType}
        sourceId={sourceId} assets={assets} replace={replace} canSigned={docState === "PUBLISHED"} onDone={load} />
      <ConfirmDialog open={!!del} onOpenChange={(v) => !v && setDel(null)} title="Hapus dokumen?" destructive loading={busy}
        description={del ? `"${del.file_name}" akan dinonaktifkan (soft delete). File tetap tersimpan untuk audit dan tidak lagi tampil sebagai dokumen aktif.` : ""}
        confirmLabel="Hapus Dokumen" onConfirm={remove} />
    </section>
  );
};

export default AssetDocumentsPanel;
