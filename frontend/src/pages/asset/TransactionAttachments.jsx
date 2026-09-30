import React, { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Download, Eye, FileText, Loader2, Paperclip, Plus, RefreshCw, Trash2 } from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { DOC_TYPES, downloadDocument, viewDocument } from "@/pages/asset/AssetDocumentsPanel";

/* Phase 2A CP4 (revisi UX) - Lampiran Dokumen langsung dari FORM transaksi.
   File tidak diunggah ke object storage sebelum transaksi memiliki ID. Ditahan di state ("Menunggu disimpan"),
   lalu diunggah ke mekanisme asset_documents CP4 yang sama setelah transaksi tersimpan (draft/publish).
   SIGNED_BAST TIDAK tersedia di sini (hanya setelah Published, melalui panel Dokumen). Backend tetap menegakkan
   seluruh aturan (permission, scope 01I, limit, format, ukuran). */

const EXT = ["pdf", "jpg", "jpeg", "png"];
const MAX_MB = 10;
const MAX_PER_SOURCE = 10;
// Hanya jenis non-BAST yang boleh dipilih sebelum/di luar konteks BAST resmi.
const PENDING_DOC_TYPES = DOC_TYPES.filter(([k]) => k !== "SIGNED_BAST");

const fmtSize = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round((n || 0) / 1024))} KB`);

const STATUS_META = {
  PENDING: { label: "Menunggu disimpan", cls: "border-border bg-muted text-muted-foreground", Icon: FileText },
  UPLOADING: { label: "Mengunggah…", cls: "border-info-border bg-info-soft text-info", Icon: Loader2, spin: true },
  DONE: { label: "Terunggah", cls: "border-success-border bg-success-soft text-success", Icon: CheckCircle2 },
  ERROR: { label: "Gagal", cls: "border-danger-border bg-danger-soft text-danger", Icon: AlertCircle },
};

const StatusBadge = ({ status, testId }) => {
  const m = STATUS_META[status] || STATUS_META.PENDING;
  const Icon = m.Icon;
  return (
    <Badge variant="outline" className={cn("whitespace-nowrap gap-1", m.cls)} data-testid={testId}>
      <Icon className={cn("h-3 w-3", m.spin && "animate-spin")} aria-hidden />
      {m.label}
    </Badge>
  );
};

let _seq = 0;
const nextKey = () => `att-${Date.now()}-${_seq++}`;

/**
 * Section "Lampiran Dokumen" untuk form transaksi (Penyerahan / Pengembalian / Opening Existing).
 * Ref API:
 *   - hasPending(): boolean  -> ada lampiran yang belum terunggah
 *   - flushPending(sourceId, docState): Promise<{uploaded, failed}> -> unggah semua lampiran menunggu ke transaksi
 */
const TransactionAttachments = forwardRef(function TransactionAttachments(
  { sourceType, sourceId = null, docState = null, disabled = false, testId = "txn-attachments" },
  ref
) {
  const { can } = useAuth();
  const canCreate = can("asset_document", "create");
  const canView = can("asset_document", "view");
  const [pending, setPending] = useState([]);
  const [existing, setExisting] = useState([]); // dokumen aktif yang sudah terunggah (mode edit draft)
  const pendingRef = useRef(pending);
  const storedSource = useRef(sourceId);
  pendingRef.current = pending;

  const loadExisting = useCallback(async () => {
    if (!sourceId || !canView) { setExisting([]); return; }
    try {
      const res = await api.get("/asset-documents", { params: { source_type: sourceType, source_id: sourceId } });
      setExisting((res.data?.items || []).filter((d) => d.doc_status === "ACTIVE"));
    } catch {
      setExisting([]);
    }
  }, [sourceType, sourceId, canView]);

  useEffect(() => { storedSource.current = sourceId; loadExisting(); }, [sourceId, loadExisting]);

  const activeTotal = existing.length + pending.filter((p) => p.status !== "ERROR").length;
  const limitReached = activeTotal >= MAX_PER_SOURCE;

  const addRow = () => {
    if (limitReached) return;
    setPending((list) => [...list, { key: nextKey(), type: "", file: null, fileName: "", size: 0, notes: "", status: "PENDING", error: "" }]);
  };
  const patchRow = (key, patch) => setPending((list) => list.map((p) => (p.key === key ? { ...p, ...patch } : p)));
  const removeRow = (key) => setPending((list) => list.filter((p) => p.key !== key));

  const pickFile = (key, f) => {
    if (!f) return patchRow(key, { file: null, fileName: "", size: 0, error: "" });
    const ext = (f.name.split(".").pop() || "").toLowerCase();
    if (!EXT.includes(ext)) return patchRow(key, { file: null, fileName: "", size: 0, error: "Format tidak didukung. Gunakan PDF, JPG, JPEG, atau PNG." });
    if (f.size > MAX_MB * 1048576) return patchRow(key, { file: null, fileName: "", size: 0, error: "Ukuran file melebihi batas 10 MB." });
    patchRow(key, { file: f, fileName: f.name, size: f.size, error: "", status: "PENDING" });
  };

  const uploadOne = useCallback(async (item, sid) => {
    const fd = new FormData();
    fd.append("source_type", sourceType);
    fd.append("source_id", sid);
    fd.append("document_type", item.type);
    if (item.notes) fd.append("notes", item.notes);
    fd.append("file", item.file);
    await api.post("/asset-documents", fd);
  }, [sourceType]);

  const flushPending = useCallback(async (sid, _docState) => {
    storedSource.current = sid;
    let uploaded = 0, failed = 0;
    const items = pendingRef.current.filter((p) => p.status !== "DONE" && p.type && p.file);
    for (const item of items) {
      patchRow(item.key, { status: "UPLOADING", error: "" });
      try {
        await uploadOne(item, sid);
        patchRow(item.key, { status: "DONE", error: "" });
        uploaded += 1;
      } catch (e) {
        patchRow(item.key, { status: "ERROR", error: errorMessage(e, "Lampiran gagal diunggah.") });
        failed += 1;
      }
    }
    await loadExisting();
    return { uploaded, failed };
  }, [uploadOne, loadExisting]);

  const retryOne = async (key) => {
    const item = pendingRef.current.find((p) => p.key === key);
    if (!item || !storedSource.current || !item.type || !item.file) return;
    patchRow(key, { status: "UPLOADING", error: "" });
    try {
      await uploadOne(item, storedSource.current);
      patchRow(key, { status: "DONE", error: "" });
      await loadExisting();
    } catch (e) {
      patchRow(key, { status: "ERROR", error: errorMessage(e, "Lampiran gagal diunggah.") });
    }
  };

  useImperativeHandle(ref, () => ({
    hasPending: () => pendingRef.current.some((p) => p.status !== "DONE" && p.type && p.file),
    flushPending,
  }), [flushPending]);

  if (!canCreate) return null;

  return (
    <section className="space-y-3 rounded-xl border border-border bg-surface-1/40 p-4" data-testid={testId} aria-labelledby={`${testId}-title`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 id={`${testId}-title`} className="flex items-center gap-2 text-sm font-semibold text-ink-1">
            <Paperclip className="h-4 w-4 text-primary" />Lampiran Dokumen
          </h3>
          <p className="text-[12px] text-muted-foreground">
            Tambahkan foto kondisi, berita acara, atau dokumen pendukung. PDF/JPG/JPEG/PNG · maks. 10 MB/file · maks. 10 dokumen/transaksi.
            BAST Ditandatangani tersedia setelah transaksi dipublish.
          </p>
        </div>
        <Button type="button" size="sm" variant="outline" onClick={addRow} disabled={disabled || limitReached}
          title={limitReached ? "Batas 10 dokumen tercapai" : undefined} data-testid={`${testId}-add`}>
          <Plus className="mr-1.5 h-4 w-4" />Tambah Lampiran
        </Button>
      </div>

      {existing.length > 0 && (
        <ul className="space-y-2" data-testid={`${testId}-existing`}>
          {existing.map((d) => (
            <li key={d.id} className="flex flex-col gap-2 rounded-lg border border-border bg-card p-2.5 sm:flex-row sm:items-center" data-testid={`${testId}-existing-${d.id}`}>
              <FileText className="hidden h-4 w-4 shrink-0 text-muted-foreground sm:block" aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-medium">{d.file_name}</p>
                <p className="text-[12px] text-muted-foreground">{d.document_type_label} · {fmtSize(d.file_size)}</p>
              </div>
              <StatusBadge status="DONE" testId={`${testId}-existing-status-${d.id}`} />
              <div className="flex gap-1.5">
                <Button type="button" size="sm" variant="outline" onClick={() => viewDocument(d)} data-testid={`${testId}-existing-view-${d.id}`}><Eye className="mr-1 h-3.5 w-3.5" />Lihat</Button>
                <Button type="button" size="sm" variant="outline" onClick={() => downloadDocument(d)} data-testid={`${testId}-existing-download-${d.id}`}><Download className="mr-1 h-3.5 w-3.5" />Unduh</Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {pending.length === 0 && existing.length === 0 && (
        <p className="rounded-lg border border-dashed border-border p-4 text-center text-[13px] text-muted-foreground" data-testid={`${testId}-empty`}>
          Belum ada lampiran. Klik "Tambah Lampiran" untuk menyertakan dokumen bersama transaksi ini.
        </p>
      )}

      {pending.length > 0 && (
        <ul className="space-y-2" data-testid={`${testId}-pending`}>
          {pending.map((p) => (
            <li key={p.key} className="space-y-2 rounded-lg border border-border bg-card p-3" data-testid={`${testId}-row-${p.key}`}>
              <div className="grid gap-2 sm:grid-cols-[minmax(0,220px)_1fr_auto] sm:items-end">
                <div className="space-y-1">
                  <Label className="text-[12px]">Jenis Dokumen</Label>
                  <Select value={p.type} onValueChange={(val) => patchRow(p.key, { type: val })} disabled={p.status === "UPLOADING" || p.status === "DONE"}>
                    <SelectTrigger className="h-9" data-testid={`${testId}-type-${p.key}`}><SelectValue placeholder="Pilih jenis" /></SelectTrigger>
                    <SelectContent>
                      {PENDING_DOC_TYPES.map(([k, l]) => <SelectItem key={k} value={k} data-testid={`${testId}-type-option-${k}`}>{l}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label className="text-[12px]">Pilih File</Label>
                  <Input type="file" className="h-9" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                    disabled={p.status === "UPLOADING" || p.status === "DONE"}
                    onChange={(e) => pickFile(p.key, e.target.files?.[0])} data-testid={`${testId}-file-${p.key}`} />
                </div>
                <div className="flex items-center gap-1.5">
                  <StatusBadge status={p.status} testId={`${testId}-status-${p.key}`} />
                  {p.status === "ERROR" && (
                    <Button type="button" size="sm" variant="outline" onClick={() => retryOne(p.key)} data-testid={`${testId}-retry-${p.key}`}>
                      <RefreshCw className="mr-1 h-3.5 w-3.5" />Coba Lagi
                    </Button>
                  )}
                  {p.status !== "DONE" && p.status !== "UPLOADING" && (
                    <Button type="button" size="sm" variant="ghost" className="text-danger" onClick={() => removeRow(p.key)}
                      aria-label="Hapus lampiran" data-testid={`${testId}-remove-${p.key}`}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              </div>
              {p.fileName && (
                <p className="text-[12px] text-muted-foreground" data-testid={`${testId}-fileinfo-${p.key}`}>
                  {p.fileName}{p.size ? ` · ${fmtSize(p.size)}` : ""}
                </p>
              )}
              <Textarea rows={1} placeholder="Keterangan (opsional)" value={p.notes}
                disabled={p.status === "UPLOADING" || p.status === "DONE"}
                onChange={(e) => patchRow(p.key, { notes: e.target.value })} data-testid={`${testId}-notes-${p.key}`} />
              {p.error && <p className="text-[12px] text-danger" role="alert" data-testid={`${testId}-error-${p.key}`}>{p.error}</p>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
});

export default TransactionAttachments;
