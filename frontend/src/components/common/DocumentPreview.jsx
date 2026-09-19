import React, { useCallback, useEffect, useState } from "react";
import { Download, ExternalLink, FileWarning, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { formatDate, formatFileSize } from "@/lib/format";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ExpiryBadge } from "./StatusBadge";

/**
 * Pratinjau dokumen langsung di layar (gambar, PDF, teks) tanpa perlu mengunduh.
 * Berkas diambil lewat API ber-otentikasi lalu dirender dari blob URL,
 * sehingga kontrol akses per perusahaan tetap berlaku.
 */
const DocumentPreviewDialog = ({ documentId, open, onOpenChange }) => {
  const [info, setInfo] = useState(null);
  const [blobUrl, setBlobUrl] = useState(null);
  const [textContent, setTextContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const cleanup = useCallback(() => {
    setBlobUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    setTextContent("");
  }, []);

  useEffect(() => {
    if (!open || !documentId) return undefined;
    let cancelled = false;
    let createdUrl = null;

    const run = async () => {
      setLoading(true);
      setError("");
      try {
        const metaRes = await api.get(`/documents/${documentId}/preview-info`);
        if (cancelled) return;
        setInfo(metaRes.data);
        if (metaRes.data.has_file === false) {
          setError(
            metaRes.data.unavailable_reason ||
              "Berkas dokumen ini tidak tersedia di penyimpanan, sehingga tidak dapat dipratinjau."
          );
          setLoading(false);
          return;
        }
        if (metaRes.data.preview_kind === "unsupported") {
          setLoading(false);
          return;
        }
        const fileRes = await api.get(`/documents/${documentId}/preview`, { responseType: "blob" });
        if (cancelled) return;
        if (metaRes.data.preview_kind === "text") {
          const text = await fileRes.data.text();
          setTextContent(text.slice(0, 20000));
        } else {
          createdUrl = URL.createObjectURL(fileRes.data);
          setBlobUrl(createdUrl);
        }
      } catch (err) {
        if (!cancelled) setError(errorMessage(err, "Pratinjau dokumen tidak dapat dimuat."));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    run();

    return () => {
      cancelled = true;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [open, documentId]);

  useEffect(() => {
    if (!open) {
      cleanup();
      setInfo(null);
      setError("");
    }
  }, [open, cleanup]);

  const download = async () => {
    try {
      const res = await api.get(`/documents/${documentId}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = info?.file_name || info?.name || "dokumen";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (err) {
      toast.error(errorMessage(err, "Berkas tidak dapat diunduh."));
    }
  };

  const renderBody = () => {
    if (loading) {
      return (
        <div className="space-y-3" data-testid="document-preview-loading">
          <Skeleton className="h-8 w-2/3" />
          <Skeleton className="h-[26rem] w-full" />
        </div>
      );
    }
    if (error) {
      return (
        <div
          className="flex flex-col items-center gap-2 rounded-lg border border-danger-border bg-danger-soft px-6 py-12 text-center"
          data-testid="document-preview-error"
        >
          <FileWarning className="h-6 w-6 text-destructive" />
          <p className="text-sm font-medium text-destructive">{error}</p>
          <Button variant="outline" size="sm" onClick={download} data-testid="document-preview-fallback-download">
            <Download className="mr-2 h-4 w-4" /> Coba unduh berkas
          </Button>
        </div>
      );
    }
    if (!info) return null;
    if (info.preview_kind === "image" && blobUrl) {
      return (
        <div className="flex max-h-[32rem] items-center justify-center overflow-auto rounded-lg border border-border bg-secondary/40 p-3">
          <img
            src={blobUrl}
            alt={info.name || "Pratinjau dokumen"}
            className="max-h-[30rem] w-auto rounded-lg object-contain"
            data-testid="document-preview-image"
          />
        </div>
      );
    }
    if (info.preview_kind === "pdf" && blobUrl) {
      return (
        <object
          data={blobUrl}
          type="application/pdf"
          className="h-[32rem] w-full rounded-lg border border-border bg-card"
          aria-label={info.name || "Pratinjau dokumen PDF"}
          data-testid="document-preview-pdf"
        >
          <div className="flex h-full flex-col items-center justify-center gap-2 px-6 py-12 text-center">
            <FileWarning className="h-6 w-6 text-muted-foreground" />
            <p className="text-sm font-medium">Peramban ini tidak dapat menampilkan PDF di dalam halaman.</p>
            <p className="max-w-sm text-sm text-muted-foreground">
              Buka berkas di tab baru untuk melihatnya, atau unduh salinannya.
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => window.open(blobUrl, "_blank", "noopener")}
              data-testid="document-preview-pdf-newtab"
            >
              <ExternalLink className="mr-2 h-4 w-4" /> Buka di tab baru
            </Button>
          </div>
        </object>
      );
    }
    if (info.preview_kind === "text") {
      return (
        <pre
          className="max-h-[32rem] overflow-auto rounded-lg border border-border bg-secondary/40 p-4 font-mono text-xs leading-relaxed"
          data-testid="document-preview-text"
        >
          {textContent || "(Berkas kosong)"}
        </pre>
      );
    }
    return (
      <div
        className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border bg-card px-6 py-12 text-center"
        data-testid="document-preview-unsupported"
      >
        <FileWarning className="h-6 w-6 text-muted-foreground" />
        <p className="text-sm font-medium">Format ini belum bisa dipratinjau di layar.</p>
        <p className="max-w-sm text-sm text-muted-foreground">
          Berkas {info.file_extension ? `.${info.file_extension}` : ""} perlu dibuka dengan aplikasi
          pendukung. Anda tetap dapat mengunduhnya.
        </p>
        <Button variant="outline" size="sm" onClick={download} data-testid="document-preview-download-unsupported">
          <Download className="mr-2 h-4 w-4" /> Unduh berkas
        </Button>
      </div>
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[92vh] overflow-y-auto bg-card sm:max-w-4xl"
        data-testid="document-preview-dialog"
      >
        <DialogHeader>
          <DialogTitle className="font-semibold" data-testid="document-preview-title">
            {info?.name || "Pratinjau Dokumen"}
          </DialogTitle>
          <DialogDescription className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span>{info?.file_name || "Memuat berkas…"}</span>
            {info?.file_size ? <span>· {formatFileSize(info.file_size)}</span> : null}
            {info?.document_number ? <span>· No. {info.document_number}</span> : null}
            {info?.expiry_date ? (
              <span className="flex items-center gap-2">
                · Berlaku sampai {formatDate(info.expiry_date)}
              </span>
            ) : null}
          </DialogDescription>
        </DialogHeader>

        {renderBody()}

        <DialogFooter className="gap-2 sm:justify-between">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            {info?.owner_label ? <span>Pemilik: {info.owner_label}</span> : null}
          </div>
          <div className="flex flex-wrap gap-2">
            {blobUrl && (
              <Button
                variant="outline"
                onClick={() => window.open(blobUrl, "_blank", "noopener")}
                data-testid="document-preview-newtab"
              >
                <ExternalLink className="mr-2 h-4 w-4" /> Buka di tab baru
              </Button>
            )}
            <Button variant="outline" onClick={download} data-testid="document-preview-download">
              <Download className="mr-2 h-4 w-4" /> Unduh
            </Button>
            <Button onClick={() => onOpenChange(false)} data-testid="document-preview-close">
              Tutup
            </Button>
          </div>
        </DialogFooter>
        {loading && (
          <span className="sr-only">
            <Loader2 className="animate-spin" /> Memuat
          </span>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default DocumentPreviewDialog;
