import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRightLeft, Eye, PackagePlus, PackageSearch, Pencil, RefreshCw, Repeat2, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate, formatDateTime } from "@/lib/format";
import { PageBody, SectionHeader } from "@/components/common/PageHeader";
import DataTable, { FilterBar, FilterSelect, Pagination, RowActions, TableCard } from "@/components/common/DataTable";
import FormDialog from "@/components/common/FormDialog";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import EmptyState from "@/components/common/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";

// Phase 2A CP1 - Daftar Aset (master aset). Tanpa pemegang/penyerahan/BAST (CP berikutnya).
// Hak akses: can(resource, action) dari RBAC; nilai perolehan hanya tampil bila API mengirimkannya (asset_value:view).

const BADGE_TONE = {
  success: "border-success-border bg-success-soft text-success",
  warning: "border-warning-border bg-warning-soft text-warning",
  danger: "border-danger-border bg-danger-soft text-danger",
  info: "border-border bg-secondary text-secondary-foreground",
  muted: "border-border bg-muted text-muted-foreground",
};

const EVENT_LABELS = {
  CREATED: "Aset dibuat",
  UPDATED: "Data aset diubah",
  STATUS_CHANGE: "Status diubah",
  RELOCATION: "Relokasi",
};

const FIELD_LABELS = {
  asset_code: "Kode", name: "Nama", category_id: "Kategori", unit_id: "Satuan", brand: "Merk", model: "Tipe/Model",
  serial_number: "Serial Number", acquisition_date: "Tanggal Perolehan", acquisition_year: "Tahun Perolehan",
  acquisition_value: "Nilai Perolehan", project_id: "Project", work_location_id: "Lokasi", condition_id: "Kondisi",
  status_id: "Status", notes: "Keterangan", asset_code_mode: "Mode Kode",
};

const FILTER_KEYS = ["category_id", "unit_id", "status_id", "condition_id", "project_id", "work_location_id"];

const formatRupiah = (value) => {
  if (value === null || value === undefined || value === "") return "-";
  const [intPart, dec = "00"] = String(value).split(".");
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `Rp ${grouped},${dec.padEnd(2, "0").slice(0, 2)}`;
};

export const AssetStatusBadge = ({ label, tone, testId }) => (
  <Badge variant="outline" className={`whitespace-nowrap font-medium ${BADGE_TONE[tone] || BADGE_TONE.muted}`} data-testid={testId}>
    {label || "-"}
  </Badge>
);

const InfoItem = ({ label, value, testId }) => (
  <div className="min-w-0 space-y-0.5">
    <p className="text-[12px] text-muted-foreground">{label}</p>
    <p className="break-words text-[13px] font-medium text-foreground" data-testid={testId}>{value || "-"}</p>
  </div>
);

export default function AssetListPage() {
  const { can } = useAuth();
  const [opts, setOpts] = useState(null);
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [filters, setFilters] = useState({});
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(20);

  const [form, setForm] = useState(null); // {mode: create|edit, asset?}
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 350);
    return () => clearTimeout(t);
  }, [search]);

  const loadOptions = useCallback(async () => {
    try {
      const res = await api.get("/assets/form-options");
      setOpts(res.data);
    } catch (e) {
      setLoadError(errorMessage(e, "Gagal memuat pilihan master aset."));
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const params = { page, limit, q: debounced || undefined };
      FILTER_KEYS.forEach((k) => {
        if (filters[k]) params[k] = filters[k];
      });
      const res = await api.get("/assets", { params });
      setRows(res.data.items || []);
      setTotal(res.data.total || 0);
    } catch (e) {
      setLoadError(errorMessage(e, "Gagal memuat daftar aset."));
    } finally {
      setLoading(false);
    }
  }, [page, limit, debounced, filters]);

  useEffect(() => {
    loadOptions();
  }, [loadOptions]);
  useEffect(() => {
    load();
  }, [load]);

  const perms = opts?.permissions || {};
  const restricted = opts && !opts.scope?.all_tenant;
  const toOptions = (list = []) => list.map((o) => ({ value: o.id, label: o.code ? `${o.name} (${o.code})` : o.name }));
  const categoryById = useMemo(() => Object.fromEntries((opts?.categories || []).map((c) => [c.id, c])), [opts]);

  // ------------------------------------------------------------------ detail
  const openDetail = async (row) => {
    setDetail({ ...row, events: null });
    setDetailLoading(true);
    try {
      const res = await api.get(`/assets/${row.id}`);
      setDetail(res.data);
    } catch (e) {
      toast.error(errorMessage(e, "Gagal memuat detail aset."));
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const refreshAfter = async (saved) => {
    await load();
    if (detail && saved && detail.id === saved.id) openDetail(saved);
  };

  // ------------------------------------------------------------------ forms
  const openCreate = () => {
    const readyDefault = (opts?.statuses || []).find((s) => s.system_state === "READY" && s.is_default);
    const baik = (opts?.conditions || []).find((c) => c.code === "BAIK");
    setValues({ status_id: readyDefault?.id || "", condition_id: baik?.id || "" });
    setErrors({});
    setForm({ mode: "create" });
  };

  const openEdit = async (row) => {
    let asset = row;
    if (asset.code_editable === undefined || (perms.value_view && asset.acquisition_value === undefined)) {
      try {
        asset = (await api.get(`/assets/${row.id}`)).data;
      } catch (e) {
        toast.error(errorMessage(e, "Gagal memuat data aset."));
        return;
      }
    }
    const v = {};
    ["asset_code", "name", "category_id", "unit_id", "brand", "model", "serial_number", "acquisition_date",
      "acquisition_year", "condition_id", "notes"].forEach((k) => {
      v[k] = asset[k] ?? "";
    });
    if (perms.value_edit && asset.acquisition_value !== undefined) v.acquisition_value = asset.acquisition_value ?? "";
    setValues(v);
    setErrors({});
    setForm({ mode: "edit", asset });
  };

  const openStatus = (row) => {
    setValues({ status_id: "", reason: "" });
    setErrors({});
    setForm({ mode: "status", asset: row });
  };

  const openRelocate = (row) => {
    setValues({ project_id: row.project_id || "", work_location_id: row.work_location_id || "", notes: "" });
    setErrors({});
    setForm({ mode: "relocate", asset: row });
  };

  const handleChange = (name, value) => {
    setValues((prev) => {
      const next = { ...prev, [name]: value };
      if (name === "category_id" && form?.mode === "create" && categoryById[value]?.default_unit_id) {
        next.unit_id = categoryById[value].default_unit_id;
      }
      return next;
    });
    setErrors((prev) => ({ ...prev, [name]: undefined }));
  };

  const assetFields = () => {
    const isCreate = form?.mode === "create";
    const cat = categoryById[values.category_id];
    const f = [
      {
        name: "asset_code",
        label: "Kode Aset",
        placeholder: isCreate ? "Kosongkan untuk kode otomatis (AST-000001)" : "",
        hint: isCreate ? "Diisi manual atau otomatis; unik per perusahaan." : form?.asset?.code_editable === false ? "Kode terkunci karena aset sudah memiliki histori." : "",
        disabled: !isCreate && form?.asset?.code_editable === false,
      },
      { name: "name", label: "Nama Aset", required: true },
      { name: "category_id", label: "Kategori", type: "select", required: true, options: toOptions(opts?.categories) },
      { name: "unit_id", label: "Satuan", type: "select", required: true, options: toOptions(opts?.units), hint: "Hanya label; satu kode aset = satu unit fisik." },
      { name: "brand", label: "Merk" },
      { name: "model", label: "Tipe / Model" },
      { name: "serial_number", label: "Serial Number", required: !!cat?.serial_number_required, hint: cat?.serial_number_required ? "Wajib untuk kategori ini; unik per perusahaan." : "Opsional; unik per perusahaan bila diisi." },
      { name: "condition_id", label: "Kondisi", type: "select", required: true, options: toOptions(opts?.conditions) },
      { name: "acquisition_date", label: "Tanggal Perolehan", type: "date" },
      { name: "acquisition_year", label: "Tahun Perolehan", type: "number", placeholder: "2024", hint: "Boleh diisi tanpa tanggal; mengikuti tanggal bila tanggal diisi." },
    ];
    if (perms.value_edit) f.push({ name: "acquisition_value", label: "Nilai Perolehan (Rp)", placeholder: "15000000.00", hint: "Opsional. Maksimal 2 angka desimal." });
    if (isCreate) {
      f.push(
        { name: "project_id", label: "Project", type: "select", required: !!restricted, options: toOptions(opts?.projects), emptyLabel: "— Tanpa project —", hint: restricted ? "Wajib project dalam cakupan data Anda." : "" },
        { name: "work_location_id", label: "Lokasi Kerja", type: "select", options: toOptions(opts?.work_locations), emptyLabel: "— Tanpa lokasi —" },
        { name: "status_id", label: "Status", type: "select", required: true, options: toOptions((opts?.statuses || []).filter((s) => s.manual_selectable)) },
      );
    }
    f.push({ name: "notes", label: "Keterangan", type: "textarea", colSpan: 2 });
    return f;
  };

  const statusFields = () => [
    {
      name: "status_id",
      label: "Status Tujuan",
      type: "select",
      required: true,
      options: toOptions((opts?.statuses || []).filter((s) => s.manual_selectable && s.id !== form?.asset?.status_id)),
      hint: "Perubahan mengikuti aturan lifecycle; transisi yang tidak diizinkan akan ditolak.",
    },
    { name: "reason", label: "Alasan", type: "textarea", required: true, colSpan: 2 },
  ];

  const relocateFields = () => [
    { name: "project_id", label: "Project Tujuan", type: "select", required: !!restricted, options: toOptions(opts?.projects), emptyLabel: "— Tanpa project —" },
    { name: "work_location_id", label: "Lokasi Kerja Tujuan", type: "select", options: toOptions(opts?.work_locations), emptyLabel: "— Tanpa lokasi —" },
    { name: "notes", label: "Catatan", type: "textarea", colSpan: 2 },
  ];

  const validate = (fields) => {
    const errs = {};
    fields.forEach((f) => {
      if (f.required && !f.disabled && (values[f.name] === undefined || values[f.name] === null || String(values[f.name]).trim() === "")) {
        errs[f.name] = `${f.label} wajib diisi.`;
      }
    });
    setErrors(errs);
    return !Object.keys(errs).length;
  };

  const handleSubmit = async () => {
    const mode = form?.mode;
    const fields = mode === "status" ? statusFields() : mode === "relocate" ? relocateFields() : assetFields();
    if (!validate(fields)) return;
    setSubmitting(true);
    try {
      let res;
      if (mode === "create") {
        const payload = {};
        fields.forEach((f) => {
          const v = values[f.name];
          if (v !== "" && v !== undefined && v !== null) payload[f.name] = v;
        });
        res = await api.post("/assets", payload);
        toast.success(`Aset ${res.data.asset_code} berhasil ditambahkan.`);
      } else if (mode === "edit") {
        const a = form.asset;
        const payload = {};
        fields.forEach((f) => {
          if (f.disabled) return;
          const nv = values[f.name] === "" ? null : values[f.name];
          const ov = a[f.name] === "" || a[f.name] === undefined ? null : a[f.name];
          if (String(nv ?? "") !== String(ov ?? "")) payload[f.name] = nv;
        });
        if (!Object.keys(payload).length) {
          toast.info("Tidak ada perubahan.");
          setForm(null);
          return;
        }
        res = await api.put(`/assets/${a.id}`, payload);
        toast.success(`Aset ${res.data.asset_code} berhasil diperbarui.`);
      } else if (mode === "status") {
        res = await api.post(`/assets/${form.asset.id}/status`, { status_id: values.status_id, reason: values.reason });
        toast.success(`Status aset ${res.data.asset_code} diubah menjadi ${res.data.status_name}.`);
      } else if (mode === "relocate") {
        res = await api.post(`/assets/${form.asset.id}/relocate`, {
          project_id: values.project_id || null,
          work_location_id: values.work_location_id || null,
          notes: values.notes || null,
        });
        toast.success(`Aset ${res.data.asset_code} berhasil direlokasi.`);
      }
      setForm(null);
      await refreshAfter(res?.data);
    } catch (e) {
      toast.error(errorMessage(e, "Gagal menyimpan data aset."), { duration: 9000 });
    } finally {
      setSubmitting(false);
    }
  };

  const runDelete = async () => {
    setDeleting(true);
    try {
      await api.delete(`/assets/${confirmDelete.id}`);
      toast.success(`Aset ${confirmDelete.asset_code} berhasil dihapus.`);
      setConfirmDelete(null);
      if (detail?.id === confirmDelete.id) setDetail(null);
      await load();
    } catch (e) {
      toast.error(errorMessage(e, "Gagal menghapus aset."), { duration: 9000 });
    } finally {
      setDeleting(false);
    }
  };

  const rowActions = (row) => [
    { label: "Lihat detail", icon: Eye, onSelect: () => openDetail(row), testId: `asset-row-detail-${row.id}` },
    can("asset", "edit") && { label: "Ubah data", icon: Pencil, onSelect: () => openEdit(row), testId: `asset-row-edit-${row.id}` },
    can("asset", "edit") && { label: "Ubah status", icon: Repeat2, onSelect: () => openStatus(row), testId: `asset-row-status-${row.id}` },
    can("asset", "edit") && row.lifecycle_state === "READY" && { label: "Relokasi", icon: ArrowRightLeft, onSelect: () => openRelocate(row), testId: `asset-row-relocate-${row.id}` },
    can("asset", "delete") && { label: "Hapus", icon: Trash2, destructive: true, onSelect: () => setConfirmDelete(row), testId: `asset-row-delete-${row.id}` },
  ];

  const columns = [
    { key: "asset_code", header: "Kode", render: (r) => <span className="font-mono text-[12px] font-semibold" data-testid={`asset-code-${r.id}`}>{r.asset_code}</span> },
    { key: "name", header: "Nama", render: (r) => <span className="font-medium">{r.name}</span> },
    { key: "category", header: "Kategori", hideOnMobile: true, render: (r) => r.category_name || "-" },
    { key: "unit", header: "Satuan", hideOnMobile: true, render: (r) => r.unit_name || "-" },
    { key: "brand", header: "Merk / Tipe", hideOnMobile: true, render: (r) => [r.brand, r.model].filter(Boolean).join(" · ") || "-" },
    { key: "serial", header: "Serial Number", hideOnMobile: true, render: (r) => <span className="font-mono text-[12px]">{r.serial_number || "-"}</span> },
    { key: "project", header: "Project", hideOnMobile: true, render: (r) => r.project_name || <span className="text-muted-foreground">Tanpa project</span> },
    { key: "location", header: "Lokasi", hideOnMobile: true, render: (r) => r.work_location_name || "-" },
    { key: "condition", header: "Kondisi", hideOnMobile: true, render: (r) => r.condition_name || "-" },
    { key: "status", header: "Status", render: (r) => <AssetStatusBadge label={r.status_name} tone={r.status_color} testId={`asset-status-${r.id}`} /> },
    { key: "actions", header: "", className: "w-12 text-right", render: (r) => <RowActions actions={rowActions(r)} testId={`asset-row-actions-${r.id}`} /> },
  ];

  const hasFilters = !!debounced || FILTER_KEYS.some((k) => filters[k]);
  const setFilter = (k) => (v) => {
    setFilters((prev) => ({ ...prev, [k]: v }));
    setPage(1);
  };
  const projectFilterOptions = [...(opts?.scope?.all_tenant ? [{ value: "none", label: "Tanpa project" }] : []), ...toOptions(opts?.projects)];
  const formTitle = { create: "Tambah Aset", edit: `Ubah Aset ${form?.asset?.asset_code || ""}`, status: `Ubah Status ${form?.asset?.asset_code || ""}`, relocate: `Relokasi ${form?.asset?.asset_code || ""}` }[form?.mode];
  const formFields = form?.mode === "status" ? statusFields() : form?.mode === "relocate" ? relocateFields() : form ? assetFields() : [];

  return (
    <PageBody className="space-y-4">
      <div className="space-y-4" data-testid="asset-list-page">
      <SectionHeader
        title="Daftar Aset"
        description="Satu kode aset mewakili satu unit fisik. Data mengikuti cakupan project Anda."
        actions={
          can("asset", "create") && (
            <Button onClick={openCreate} disabled={!opts} data-testid="asset-add-button">
              <PackagePlus className="mr-2 h-4 w-4" /> Tambah Aset
            </Button>
          )
        }
      />
      <FilterBar
        search={search}
        onSearchChange={(v) => {
          setSearch(v);
          setPage(1);
        }}
        searchPlaceholder="Cari kode, nama, serial number, merk, atau tipe…"
        showReset={hasFilters}
        onReset={() => {
          setSearch("");
          setFilters({});
          setPage(1);
        }}
      >
        <FilterSelect label="Kategori" value={filters.category_id} onChange={setFilter("category_id")} options={toOptions(opts?.categories)} allLabel="Semua kategori" testId="asset-filter-category" />
        <FilterSelect label="Satuan" value={filters.unit_id} onChange={setFilter("unit_id")} options={toOptions(opts?.units)} allLabel="Semua satuan" testId="asset-filter-unit" />
        <FilterSelect label="Status" value={filters.status_id} onChange={setFilter("status_id")} options={toOptions(opts?.statuses)} allLabel="Semua status" testId="asset-filter-status" />
        <FilterSelect label="Kondisi" value={filters.condition_id} onChange={setFilter("condition_id")} options={toOptions(opts?.conditions)} allLabel="Semua kondisi" testId="asset-filter-condition" />
        <FilterSelect label="Project" value={filters.project_id} onChange={setFilter("project_id")} options={projectFilterOptions} allLabel="Semua project" testId="asset-filter-project" />
        <FilterSelect label="Lokasi" value={filters.work_location_id} onChange={setFilter("work_location_id")} options={toOptions(opts?.work_locations)} allLabel="Semua lokasi" testId="asset-filter-location" />
      </FilterBar>

      <TableCard>
        {loadError && !loading ? (
          <EmptyState
            testId="asset-list-error"
            icon={RefreshCw}
            title="Daftar aset gagal dimuat"
            description={loadError}
            actionLabel="Coba lagi"
            onAction={() => {
              loadOptions();
              load();
            }}
          />
        ) : (
          <>
            <DataTable
              testId="asset-table"
              columns={columns}
              rows={rows}
              loading={loading}
              onRowClick={openDetail}
              emptyProps={{
                icon: PackageSearch,
                testId: "asset-list-empty",
                title: hasFilters ? "Tidak ada aset yang cocok" : "Belum ada aset",
                description: hasFilters
                  ? "Ubah kata kunci atau filter pencarian."
                  : restricted
                    ? "Belum ada aset pada project dalam cakupan data Anda."
                    : "Tambahkan aset pertama untuk mulai mencatat inventaris per unit fisik.",
                actionLabel: !hasFilters && can("asset", "create") ? "Tambah Aset" : undefined,
                onAction: !hasFilters && can("asset", "create") ? openCreate : undefined,
              }}
            />
            <Pagination
              page={page}
              totalPages={Math.max(1, Math.ceil(total / limit))}
              total={total}
              limit={limit}
              onPageChange={setPage}
              onLimitChange={(v) => {
                setLimit(v);
                setPage(1);
              }}
            />
          </>
        )}
      </TableCard>

      <Sheet open={!!detail} onOpenChange={(v) => !v && setDetail(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-xl" data-testid="asset-detail-sheet">
          <SheetHeader>
            <SheetTitle className="flex flex-wrap items-center gap-2">
              <span className="font-mono" data-testid="asset-detail-code">{detail?.asset_code}</span>
              {detail && <AssetStatusBadge label={detail.status_name} tone={detail.status_color} testId="asset-detail-status" />}
            </SheetTitle>
            <SheetDescription data-testid="asset-detail-name">{detail?.name}</SheetDescription>
          </SheetHeader>
          {detail && (
            <div className="mt-4 space-y-5">
              <div className="flex flex-wrap gap-2">
                {can("asset", "edit") && (
                  <Button size="sm" variant="outline" onClick={() => openEdit(detail)} data-testid="asset-detail-edit">
                    <Pencil className="mr-1.5 h-3.5 w-3.5" /> Ubah
                  </Button>
                )}
                {can("asset", "edit") && (
                  <Button size="sm" variant="outline" onClick={() => openStatus(detail)} data-testid="asset-detail-change-status">
                    <Repeat2 className="mr-1.5 h-3.5 w-3.5" /> Ubah Status
                  </Button>
                )}
                {can("asset", "edit") && detail.lifecycle_state === "READY" && (
                  <Button size="sm" variant="outline" onClick={() => openRelocate(detail)} data-testid="asset-detail-relocate">
                    <ArrowRightLeft className="mr-1.5 h-3.5 w-3.5" /> Relokasi
                  </Button>
                )}
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-3 rounded-lg border border-border p-3">
                <InfoItem label="Kategori" value={detail.category_name} testId="asset-detail-category" />
                <InfoItem label="Satuan" value={detail.unit_name} />
                <InfoItem label="Merk" value={detail.brand} />
                <InfoItem label="Tipe / Model" value={detail.model} />
                <InfoItem label="Serial Number" value={detail.serial_number} testId="asset-detail-serial" />
                <InfoItem label="Kondisi" value={detail.condition_name} />
                <InfoItem label="Project" value={detail.project_name || "Tanpa project"} testId="asset-detail-project" />
                <InfoItem label="Lokasi Kerja" value={detail.work_location_name} />
                <InfoItem label="Kategori Sistem" value={detail.lifecycle_label} />
                <InfoItem label="Tanggal Perolehan" value={detail.acquisition_date ? formatDate(detail.acquisition_date) : null} />
                <InfoItem label="Tahun Perolehan" value={detail.acquisition_year} />
                {"acquisition_value" in detail && (
                  <InfoItem label="Nilai Perolehan" value={formatRupiah(detail.acquisition_value)} testId="asset-detail-value" />
                )}
                <div className="col-span-2">
                  <InfoItem label="Keterangan" value={detail.notes} />
                </div>
              </div>
              <div className="space-y-2">
                <p className="text-sm font-semibold">Histori</p>
                {detailLoading || !detail.events ? (
                  <div className="space-y-2">
                    <Skeleton className="h-10 w-full" />
                    <Skeleton className="h-10 w-full" />
                  </div>
                ) : detail.events.length === 0 ? (
                  <p className="text-[13px] text-muted-foreground">Belum ada histori.</p>
                ) : (
                  <ol className="space-y-2" data-testid="asset-detail-events">
                    {detail.events.map((e) => (
                      <li key={e.id} className="rounded-lg border border-border p-2.5 text-[13px]" data-testid={`asset-event-${e.event_type}`}>
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-medium">{EVENT_LABELS[e.event_type] || e.event_type}</span>
                          <span className="text-[12px] text-muted-foreground">{formatDateTime(e.event_at)}</span>
                        </div>
                        <p className="mt-0.5 text-[12px] text-muted-foreground">
                          {e.actor_name || "Sistem"}
                          {e.from_state && e.to_state && e.from_state !== e.to_state ? ` · ${e.from_state} → ${e.to_state}` : ""}
                          {Object.keys(e.changes || {}).filter((k) => k !== "asset_code_mode").length
                            ? ` · ${Object.keys(e.changes).filter((k) => k !== "asset_code_mode").map((k) => FIELD_LABELS[k] || k).join(", ")}`
                            : ""}
                        </p>
                        {e.notes && <p className="mt-1 text-[12px]">{e.notes}</p>}
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>

      <FormDialog
        open={!!form}
        onOpenChange={(v) => !v && setForm(null)}
        title={formTitle}
        description={
          form?.mode === "status"
            ? "Status berkategori Dipakai / Menunggu Pemeriksaan hanya terjadi lewat transaksi."
            : form?.mode === "relocate"
              ? "Relokasi hanya untuk aset Siap Pakai. Perubahan dicatat di histori aset."
              : "Kolom bertanda * wajib diisi. Perubahan tercatat di histori dan audit log."
        }
        fields={formFields}
        values={values}
        errors={errors}
        onChange={handleChange}
        onSubmit={handleSubmit}
        submitting={submitting}
        submitLabel={form?.mode === "create" ? "Simpan Aset" : "Simpan"}
        wide={form?.mode === "create" || form?.mode === "edit"}
      />

      <ConfirmDialog
        open={!!confirmDelete}
        onOpenChange={(v) => !v && setConfirmDelete(null)}
        title={`Hapus aset ${confirmDelete?.asset_code || ""}?`}
        description="Aset dihapus dari daftar. Untuk aset yang sudah tidak dipakai, sebaiknya ubah status ke kategori Dihapuskan agar riwayat tetap utuh."
        destructive
        confirmLabel="Hapus aset"
        loading={deleting}
        onConfirm={runDelete}
      />
      </div>
    </PageBody>
  );
}
