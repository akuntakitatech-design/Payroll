import React, { useRef, useState } from "react";
import { Camera, CheckCircle2, FileText, FolderOpen, Loader2, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";

const fmtSize = (b) => (b >= 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);

/** Upload dari HP (kamera / galeri-file). Berkas = lampiran pending (bukan dokumen resmi sampai diverifikasi HR). */
export const DocumentsSection = ({ documents, files, onUpload, onRemove, disabled, missingCodes }) => {
  const [busy, setBusy] = useState(null);
  const [errs, setErrs] = useState({});
  const refs = useRef({});

  const pick = async (doc, file, replaceIds = []) => {
    if (!file) return;
    const ext = (file.name.split(".").pop() || "").toLowerCase();
    const allowed = doc.allowed_extensions || [];
    let err = null;
    if (!allowed.includes(ext)) err = `Jenis berkas tidak didukung. Gunakan: ${allowed.join(", ").toUpperCase()}.`;
    else if (file.size > doc.max_size_mb * 1048576) err = `Ukuran berkas terlalu besar. Maksimal ${doc.max_size_mb} MB.`;
    else if (file.size === 0) err = "Berkas kosong. Pilih berkas lain.";
    if (err) { setErrs((e) => ({ ...e, [doc.code]: err })); return; }
    setErrs((e) => ({ ...e, [doc.code]: null }));
    setBusy(doc.code);
    try {
      await onUpload(doc.code, file, replaceIds);
    } catch (e) {
      setErrs((x) => ({ ...x, [doc.code]: e.detail || "Upload gagal. Coba lagi." }));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-3" data-testid="public-documents-section">
      {documents.map((doc) => {
        const mine = files.filter((f) => f.document_type_code === doc.code);
        const isImageOnly = (doc.allowed_extensions || []).every((x) => ["jpg", "jpeg", "png", "webp"].includes(x));
        const accept = (doc.allowed_extensions || []).map((x) => `.${x}`).join(",");
        const status = mine.length ? "Berkas baru diunggah — menunggu verifikasi HR" : doc.has_existing ? "Sudah ada di HR (unggah bila ingin memperbarui)" : "Belum diunggah";
        const need = missingCodes[`DOC.${String(doc.code).toUpperCase()}`] || (doc.code === "PHOTO" && missingCodes["PERSONAL.PHOTO"]);
        return (
          <div key={doc.code} className="rounded-xl border bg-background p-4" data-testid={`public-doc-card-${doc.code}`}>
            <div className="flex items-start gap-3">
              <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${mine.length ? "bg-[hsl(var(--accent-mint,168_55%_92%))] text-primary" : "bg-muted text-muted-foreground"}`}>
                {mine.length ? <CheckCircle2 className="h-5 w-5" /> : <FileText className="h-5 w-5" />}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium">{doc.name}</p>
                  {need && !mine.length && <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${need === "REQUIRED" ? "border-amber-300 bg-amber-50 text-amber-800" : "border-sky-300 bg-sky-50 text-sky-800"}`}>{need === "REQUIRED" ? "Wajib dilengkapi" : "Disarankan"}</span>}
                </div>
                <p className="text-sm text-muted-foreground" data-testid={`public-doc-status-${doc.code}`}>{status}</p>
                <p className="text-xs text-muted-foreground">{(doc.allowed_extensions || []).join(", ").toUpperCase()} · maks {doc.max_size_mb} MB</p>
              </div>
            </div>
            {mine.map((f) => (
              <div key={f.id} className="mt-3 flex items-center gap-2 rounded-lg bg-muted/50 px-3 py-2" data-testid={`public-doc-file-${f.id}`}>
                <p className="min-w-0 flex-1 truncate text-sm">{f.file_name} <span className="text-muted-foreground">({fmtSize(f.file_size)})</span></p>
                <Button type="button" size="sm" variant="ghost" className="h-10 text-destructive" disabled={disabled || busy} onClick={() => onRemove(f.id)} aria-label={`Hapus ${f.file_name}`} data-testid={`public-doc-remove-${f.id}`}><Trash2 className="h-4 w-4" /></Button>
              </div>
            ))}
            {errs[doc.code] && <p className="mt-2 text-sm font-medium text-destructive" role="alert" data-testid={`public-doc-error-${doc.code}`}>{errs[doc.code]}</p>}
            <div className="mt-3 grid grid-cols-2 gap-2">
              <input type="file" accept="image/*" capture="environment" className="hidden" ref={(el) => { refs.current[`cam-${doc.code}`] = el; }}
                onChange={(e) => { pick(doc, e.target.files?.[0], mine.map((f) => f.id)); e.target.value = ""; }} data-testid={`public-doc-camera-input-${doc.code}`} />
              <input type="file" accept={accept} className="hidden" ref={(el) => { refs.current[`file-${doc.code}`] = el; }}
                onChange={(e) => { pick(doc, e.target.files?.[0], mine.map((f) => f.id)); e.target.value = ""; }} data-testid={`public-doc-file-input-${doc.code}`} />
              <Button type="button" variant="outline" className="h-12" disabled={disabled || !!busy} onClick={() => refs.current[`cam-${doc.code}`]?.click()} data-testid={`public-doc-camera-${doc.code}`}>
                {busy === doc.code ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Camera className="mr-2 h-4 w-4" />}Kamera
              </Button>
              <Button type="button" variant="outline" className="h-12" disabled={disabled || !!busy} onClick={() => refs.current[`file-${doc.code}`]?.click()} data-testid={`public-doc-upload-${doc.code}`}>
                <FolderOpen className="mr-2 h-4 w-4" />{mine.length ? "Ganti" : isImageOnly ? "Galeri" : "Pilih File"}
              </Button>
            </div>
          </div>
        );
      })}
      <p className="text-xs text-muted-foreground">Dokumen resmi yang sudah ada di HR tidak langsung diganti. Berkas baru diverifikasi HR terlebih dahulu.</p>
    </div>
  );
};
