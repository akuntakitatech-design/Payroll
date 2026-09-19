import React, { useCallback, useEffect, useRef, useState } from "react";
import { Download, Eye, FileText, Loader2, MoreHorizontal, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate, formatFileSize, daysUntil } from "@/lib/format";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import DataTable, { FilterBar, FilterSelect, Pagination, TableCard } from "@/components/common/DataTable";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import StatusBadge from "@/components/common/StatusBadge";
import DocumentPreviewDialog from "@/components/common/DocumentPreview";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const DocumentsPage = () => {
  const { can, company } = useAuth();
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState({ total: 0, page: 1, limit: 20, total_pages: 1 });
  const [loading, setLoading] = useState(true);
  const [catalog, setCatalog] = useState({ owner_types: [], document_types: [], max_size_mb: 15 });
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [ownerFilter, setOwnerFilter] = useState("");
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(20);

  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ document_type_id: "", name: "", owner_type: "company" });
  const [file, setFile] = useState(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [downloading, setDownloading] = useState(null);
  const [previewId, setPreviewId] = useState(null);
  const fileInput = useRef(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 350);
    return () => clearTimeout(t);
  }, [search]);

  const loadCatalog = useCallback(async () => {
    try {
      const res = await api.get("/documents/catalog");
      setCatalog(res.data);
    } catch {
      /* ignore */
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, limit };
      if (debounced) params.q = debounced;
      if (typeFilter) params.document_type_id = typeFilter;
      if (ownerFilter) params.owner_type = ownerFilter;
      const res = await api.get("/documents", { params });
      setRows(res.data.items || []);
      setMeta({
        total: res.data.total,
        page: res.data.page,
        limit: res.data.limit,
        total_pages: res.data.total_pages,
      });
    } catch (err) {
      toast.error(errorMessage(err, "Gagal memuat arsip dokumen."));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [page, limit, debounced, typeFilter, ownerFilter]);

  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    loadCatalog();
    document.title = "Arsip Dokumen · HRIS Suite";
  }, [loadCatalog, company?.id]);

  const openUpload = () => {
    setForm({ document_type_id: catalog.document_types[0]?.id || "", name: "", owner_type: "company" });
    setFile(null);
    setError("");
    setOpen(true);
  };

  const submit = async () => {
    setError("");
    if (!file) {
      setError("Pilih berkas yang ingin diunggah terlebih dahulu.");
      return;
    }
    if (!form.document_type_id) {
      setError("Tipe dokumen wajib dipilih agar aturan format dan masa berlaku bisa diterapkan.");
      return;
    }
    if (!form.name?.trim()) {
      setError("Nama dokumen wajib diisi agar mudah dicari kembali.");
      return;
    }
    setSubmitting(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      Object.entries(form).forEach(([k, v]) => {
        if (v !== "" && v !== null && v !== undefined) fd.append(k, v);
      });
      await api.post("/documents", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(`Dokumen "${form.name}" berhasil diunggah.`);
      setOpen(false);
      load();
    } catch (err) {
      setError(errorMessage(err, "Dokumen tidak dapat diunggah."));
    } finally {
      setSubmitting(false);
    }
  };

  const download = async (row) => {
    setDownloading(row.id);
    try {
      const res = await api.get(`/documents/${row.id}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = row.file_name || row.name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (err) {
      toast.error(errorMessage(err, "Berkas tidak dapat diunduh."));
    } finally {
      setDownloading(null);
    }
  };

  const runConfirm = async () => {
    setConfirmLoading(true);
    try {
      const res = await api.delete(`/documents/${confirm.id}`);
      toast.success(res.data.message);
      setConfirm(null);
      load();
    } catch (err) {
      toast.error(errorMessage(err, "Dokumen tidak dapat dihapus."));
      setConfirm(null);
    } finally {
      setConfirmLoading(false);
    }
  };

  const columns = [
    {
      key: "name",
      header: "Dokumen",
      render: (row) => (
        <div className="flex min-w-0 items-start gap-2">
          <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          <div className="min-w-0">
            <p className="truncate font-medium">{row.name}</p>
            <p className="truncate text-xs text-muted-foreground">
              {row.file_name} · {formatFileSize(row.file_size)}
            </p>
          </div>
        </div>
      ),
    },
    {
      key: "document_type_name",
      header: "Tipe",
      hideOnMobile: true,
      render: (row) => row.document_type_name || "-",
    },
    {
      key: "owner_label",
      header: "Pemilik",
      hideOnMobile: true,
      render: (row) => (
        <div>
          <p className="text-sm">{row.owner_label || "-"}</p>
          <p className="text-xs text-muted-foreground">
            {catalog.owner_types.find((o) => o.key === row.owner_type)?.label || row.owner_type}
          </p>
        </div>
      ),
    },
    {
      key: "expiry_date",
      header: "Masa Berlaku",
      hideOnMobile: true,
      render: (row) => {
        if (!row.expiry_date) return <span className="text-muted-foreground">Tidak ada</span>;
        const d = daysUntil(row.expiry_date);
        return (
          <div className="flex items-center gap-2">
            <span>{formatDate(row.expiry_date)}</span>
            {d !== null && d < 30 && (
              <Badge variant={d < 0 ? "destructive" : "secondary"} className="text-[11px]">
                {d < 0 ? "Kedaluwarsa" : `${d} hari`}
              </Badge>
            )}
          </div>
        );
      },
    },
    { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
    {
      key: "actions",
      header: "",
      className: "w-12 text-right",
      render: (row) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={(e) => e.stopPropagation()} data-testid={`doc-actions-${row.id}`}>
              {downloading === row.id ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <MoreHorizontal className="h-4 w-4" />
              )}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuItem onClick={() => setPreviewId(row.id)} data-testid={`doc-preview-${row.id}`}>
              <Eye className="mr-2 h-4 w-4" /> Lihat pratinjau
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => download(row)} data-testid={`doc-download-${row.id}`}>
              <Download className="mr-2 h-4 w-4" /> Unduh berkas
            </DropdownMenuItem>
            {can("document", "delete") && (
              <DropdownMenuItem
                className="text-destructive focus:text-destructive"
                onClick={() => setConfirm(row)}
                data-testid={`doc-delete-${row.id}`}
              >
                <Trash2 className="mr-2 h-4 w-4" /> Hapus dokumen
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ];

  const hasFilters = !!debounced || !!typeFilter || !!ownerFilter;
  const noTypes = catalog.document_types.length === 0;

  return (
    <>
      <PageHeader
        title="Arsip Dokumen"
        subtitle="Berkas karyawan dan perusahaan tersimpan di satu tempat."
        actions={
          can("document", "create") && (
            <Button onClick={openUpload} disabled={noTypes} data-testid="page-header-primary-action">
              <Upload className="mr-2 h-4 w-4" /> Unggah Dokumen
            </Button>
          )
        }
      />
      <PageBody>
        {noTypes && (
          <div className="rounded-lg border border-border bg-secondary px-4 py-3 text-sm text-secondary-foreground">
            Belum ada Tipe Dokumen. Buat tipe dokumen terlebih dahulu di menu{" "}
            <span className="font-medium">Setup → Tipe Dokumen</span> agar aturan format berkas dan
            masa berlaku bisa diterapkan otomatis.
          </div>
        )}

        <FilterBar
          search={search}
          onSearchChange={(v) => {
            setSearch(v);
            setPage(1);
          }}
          searchPlaceholder="Cari nama dokumen, nomor, atau pemilik…"
          showReset={hasFilters}
          onReset={() => {
            setSearch("");
            setTypeFilter("");
            setOwnerFilter("");
            setPage(1);
          }}
        >
          <FilterSelect
            label="Tipe Dokumen"
            value={typeFilter}
            onChange={(v) => {
              setTypeFilter(v);
              setPage(1);
            }}
            options={catalog.document_types.map((t) => ({ value: t.id, label: t.name }))}
            allLabel="Semua tipe"
            testId="filter-document-type"
          />
          <FilterSelect
            label="Pemilik"
            value={ownerFilter}
            onChange={(v) => {
              setOwnerFilter(v);
              setPage(1);
            }}
            options={catalog.owner_types.map((o) => ({ value: o.key, label: o.label }))}
            allLabel="Semua pemilik"
            testId="filter-owner-type"
          />
        </FilterBar>

        <TableCard>
          <DataTable
            columns={columns}
            rows={rows}
            loading={loading}
            testId="documents-table"
            onRowClick={(row) => setPreviewId(row.id)}
            emptyProps={{
              icon: FileText,
              title: hasFilters ? "Tidak ada dokumen yang cocok." : "Belum ada dokumen.",
              description: hasFilters
                ? "Coba ubah kata kunci atau hapus filter yang aktif."
                : "Unggah dokumen pertama agar arsip perusahaan tersimpan rapi dan mudah dicari.",
              actionLabel: !hasFilters && can("document", "create") && !noTypes ? "Unggah Dokumen" : undefined,
              onAction: openUpload,
            }}
          />
          {rows.length > 0 && (
            <Pagination
              page={meta.page}
              totalPages={meta.total_pages}
              total={meta.total}
              limit={meta.limit}
              onPageChange={setPage}
              onLimitChange={(v) => {
                setLimit(v);
                setPage(1);
              }}
            />
          )}
        </TableCard>
      </PageBody>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto bg-card sm:max-w-2xl" data-testid="upload-dialog">
          <DialogHeader>
            <DialogTitle className="font-semibold">Unggah Dokumen</DialogTitle>
            <DialogDescription>
              Pilih berkas, tentukan tipe dan pemiliknya. Maksimal {catalog.max_size_mb} MB atau sesuai
              batas pada tipe dokumen.
            </DialogDescription>
          </DialogHeader>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="doc-file">
                Berkas <span className="text-destructive">*</span>
              </Label>
              <Input
                id="doc-file"
                ref={fileInput}
                type="file"
                onChange={(e) => {
                  const f = e.target.files?.[0] || null;
                  setFile(f);
                  if (f && !form.name) setForm((p) => ({ ...p, name: f.name.replace(/\.[^.]+$/, "") }));
                  setError("");
                }}
                data-testid="upload-file-input"
              />
              {file && (
                <p className="text-xs text-muted-foreground">
                  {file.name} · {formatFileSize(file.size)}
                </p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label>
                Tipe Dokumen <span className="text-destructive">*</span>
              </Label>
              <Select
                value={form.document_type_id}
                onValueChange={(v) => setForm((p) => ({ ...p, document_type_id: v }))}
              >
                <SelectTrigger data-testid="upload-type-select">
                  <SelectValue placeholder="Pilih tipe dokumen" />
                </SelectTrigger>
                <SelectContent>
                  {catalog.document_types.map((t) => (
                    <SelectItem key={t.id} value={t.id}>
                      {t.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label>Pemilik Dokumen</Label>
              <Select
                value={form.owner_type}
                onValueChange={(v) => setForm((p) => ({ ...p, owner_type: v }))}
              >
                <SelectTrigger data-testid="upload-owner-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {catalog.owner_types.map((o) => (
                    <SelectItem key={o.key} value={o.key}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="doc-name">
                Nama Dokumen <span className="text-destructive">*</span>
              </Label>
              <Input
                id="doc-name"
                value={form.name}
                onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                placeholder="KTP Rina Kusuma"
                data-testid="upload-name-input"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="doc-owner-label">Nama Pemilik / Referensi</Label>
              <Input
                id="doc-owner-label"
                value={form.owner_label || ""}
                onChange={(e) => setForm((p) => ({ ...p, owner_label: e.target.value }))}
                placeholder="Rina Kusuma"
                data-testid="upload-owner-label-input"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="doc-number">Nomor Dokumen</Label>
              <Input
                id="doc-number"
                value={form.document_number || ""}
                onChange={(e) => setForm((p) => ({ ...p, document_number: e.target.value }))}
                data-testid="upload-number-input"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="doc-issued">Tanggal Terbit</Label>
              <Input
                id="doc-issued"
                type="date"
                value={form.issued_date || ""}
                onChange={(e) => setForm((p) => ({ ...p, issued_date: e.target.value }))}
                data-testid="upload-issued-input"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="doc-expiry">Berlaku Sampai</Label>
              <Input
                id="doc-expiry"
                type="date"
                value={form.expiry_date || ""}
                onChange={(e) => setForm((p) => ({ ...p, expiry_date: e.target.value }))}
                data-testid="upload-expiry-input"
              />
            </div>
          </div>

          {error && (
            <div
              className="rounded-lg border border-danger-border bg-danger-soft px-3 py-2 text-sm text-destructive"
              data-testid="upload-error"
            >
              {error}
            </div>
          )}

          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setOpen(false)} disabled={submitting}>
              Batal
            </Button>
            <Button onClick={submit} disabled={submitting} data-testid="upload-submit">
              {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Unggah
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <DocumentPreviewDialog
        documentId={previewId}
        open={!!previewId}
        onOpenChange={(v) => !v && setPreviewId(null)}
      />

      <ConfirmDialog
        open={!!confirm}        onOpenChange={(v) => !v && setConfirm(null)}
        title="Hapus dokumen dari daftar aktif?"
        description={`Dokumen "${confirm?.name}" akan diarsipkan dan tidak lagi muncul di daftar aktif. Jejak unggahan tetap tersimpan di audit log untuk keperluan kepatuhan.`}
        destructive
        confirmLabel="Hapus dokumen"
        loading={confirmLoading}
        onConfirm={runConfirm}
      />
    </>
  );
};

export default DocumentsPage;
