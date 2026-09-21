import React, { useCallback, useEffect, useMemo, useState } from "react";
import { MoreHorizontal, Plus, Pencil, Power, Trash2, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { MASTER_CONFIG, COLUMN_LABELS, LOCATION_TYPE_LABELS } from "@/lib/masterConfig";
import { formatCurrency, formatDate, boolLabel } from "@/lib/format";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import DataTable, { FilterBar, FilterSelect, Pagination, TableCard } from "@/components/common/DataTable";
import FormDialog from "@/components/common/FormDialog";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import StatusBadge from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const STATUS_OPTIONS = [
  { value: "active", label: "Aktif" },
  { value: "inactive", label: "Nonaktif" },
  { value: "archived", label: "Diarsipkan" },
];

const MasterDataPage = ({ resourcePath }) => {
  const config = MASTER_CONFIG[resourcePath];
  const { can } = useAuth();

  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState({ total: 0, page: 1, limit: 20, total_pages: 1 });
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [statusFilter, setStatusFilter] = useState("active");
  const [relationFilter, setRelationFilter] = useState({});
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(20);

  const [options, setOptions] = useState({});
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);

  const [confirm, setConfirm] = useState(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  const relationFields = useMemo(
    () => (config?.fields || []).filter((f) => f.relation),
    [config]
  );

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 350);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    setSearch("");
    setDebounced("");
    setStatusFilter("active");
    setRelationFilter({});
    setPage(1);
    document.title = `${config?.label || "Master Data"} · HRIS Suite`;
  }, [resourcePath, config?.label]);

  const loadOptions = useCallback(async () => {
    const uniquePaths = [...new Set(relationFields.map((f) => f.relation))];
    const result = {};
    await Promise.all(
      uniquePaths.map(async (path) => {
        try {
          const res = await api.get(`/master/${path}/options`);
          result[path] = res.data.items || [];
        } catch {
          result[path] = [];
        }
      })
    );
    setOptions(result);
  }, [relationFields]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, limit };
      if (debounced) params.q = debounced;
      if (statusFilter) params.status = statusFilter;
      Object.entries(relationFilter).forEach(([k, v]) => {
        if (v) params[k] = v;
      });
      const res = await api.get(`/master/${resourcePath}`, { params });
      setRows(res.data.items || []);
      setMeta({
        total: res.data.total,
        page: res.data.page,
        limit: res.data.limit,
        total_pages: res.data.total_pages,
      });
    } catch (err) {
      toast.error(errorMessage(err, `Gagal memuat data ${config?.label}.`));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [resourcePath, page, limit, debounced, statusFilter, relationFilter, config?.label]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    loadOptions();
  }, [loadOptions]);

  if (!config) return null;

  const fieldsWithOptions = config.fields.map((f) =>
    f.relation
      ? {
          ...f,
          options: (options[f.relation] || []).map((o) => ({
            value: o.id,
            label: o.code ? `${o.code} — ${o.name}` : o.name,
          })),
        }
      : f
  );

  const openCreate = () => {
    setEditing(null);
    const initial = {};
    config.fields.forEach((f) => {
      if (f.defaultValue !== undefined) initial[f.name] = f.defaultValue;
    });
    setValues(initial);
    setErrors({});
    setDialogOpen(true);
  };

  const openEdit = (row) => {
    setEditing(row);
    const next = {};
    config.fields.forEach((f) => {
      next[f.name] = row[f.name] ?? f.defaultValue ?? (f.type === "boolean" ? false : "");
    });
    setValues(next);
    setErrors({});
    setDialogOpen(true);
  };

  const handleChange = (name, value) => {
    setValues((prev) => ({ ...prev, [name]: value }));
    setErrors((prev) => ({ ...prev, [name]: undefined, __form__: undefined }));
  };

  const handleSubmit = async () => {
    const nextErrors = {};
    config.fields.forEach((f) => {
      if (f.required && !String(values[f.name] ?? "").trim()) {
        nextErrors[f.name] = `${f.label} wajib diisi.`;
      }
    });
    if (Object.keys(nextErrors).length) {
      setErrors(nextErrors);
      return;
    }
    setSubmitting(true);
    try {
      const payload = {};
      config.fields.forEach((f) => {
        const v = values[f.name];
        if (f.type === "boolean") payload[f.name] = !!v;
        else if (v === "" || v === undefined || v === null) payload[f.name] = null;
        else payload[f.name] = v;
      });
      if (editing) {
        await api.put(`/master/${resourcePath}/${editing.id}`, payload);
        toast.success(`${config.singular} "${payload.name}" berhasil diperbarui.`);
      } else {
        await api.post(`/master/${resourcePath}`, payload);
        toast.success(`${config.singular} "${payload.name}" berhasil ditambahkan.`);
      }
      setDialogOpen(false);
      load();
      loadOptions();
    } catch (err) {
      setErrors({ __form__: errorMessage(err, "Data tidak dapat disimpan.") });
    } finally {
      setSubmitting(false);
    }
  };

  const runConfirm = async () => {
    if (!confirm) return;
    setConfirmLoading(true);
    try {
      if (confirm.type === "delete") {
        await api.delete(`/master/${resourcePath}/${confirm.row.id}`);
        toast.success(`${config.singular} "${confirm.row.name}" berhasil dihapus.`);
      } else {
        const res = await api.patch(`/master/${resourcePath}/${confirm.row.id}/status`, {
          status: confirm.status,
        });
        toast.success(res.data.message);
      }
      setConfirm(null);
      load();
      loadOptions();
    } catch (err) {
      toast.error(errorMessage(err, "Tindakan tidak dapat dilakukan."), { duration: 9000 });
      setConfirm(null);
    } finally {
      setConfirmLoading(false);
    }
  };

  const renderCell = (row, key) => {
    const value = row[key];
    if (key.endsWith("_id")) return row[`${key}_name`] || "-";
    if (config.currencyFields?.includes(key)) return formatCurrency(value);
    if (config.dateFields?.includes(key)) return formatDate(value);
    if (key === "location_type") return LOCATION_TYPE_LABELS[value] || value || "-";
    if (typeof value === "boolean") return boolLabel(value);
    if (key === "code") return <span className="font-medium">{value}</span>;
    if (key === "name") return <span className="font-medium">{value}</span>;
    return value ?? "-";
  };

  const columns = [
    ...config.columns.map((key) => ({
      key,
      header: COLUMN_LABELS[key] || key,
      hideOnMobile: !(["code", "name"].includes(key)),
      cellClassName: config.currencyFields?.includes(key) ? "whitespace-nowrap" : "",
      render: (row) => renderCell(row, key),
    })),
    {
      key: "status",
      header: "Status",
      render: (row) => <StatusBadge status={row.status} />,
    },
    {
      key: "actions",
      header: "",
      className: "w-12 text-right",
      render: (row) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              aria-label="Aksi baris"
              data-testid={`row-actions-${row.id}`}
            >
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            {can(config.resource, "edit") && (
              <DropdownMenuItem onClick={() => openEdit(row)} data-testid={`row-edit-${row.id}`}>
                <Pencil className="mr-2 h-4 w-4" /> Ubah data
              </DropdownMenuItem>
            )}
            {can(config.resource, "edit") && row.status === "active" && (
              <DropdownMenuItem
                onClick={() =>
                  setConfirm({
                    type: "status",
                    status: "inactive",
                    row,
                    title: `Nonaktifkan ${config.singular}?`,
                    description: `"${row.name}" tidak akan muncul lagi sebagai pilihan baru, tetapi seluruh riwayat data yang sudah memakainya tetap aman.`,
                  })
                }
                data-testid={`row-deactivate-${row.id}`}
              >
                <Power className="mr-2 h-4 w-4" /> Nonaktifkan
              </DropdownMenuItem>
            )}
            {can(config.resource, "edit") && row.status !== "active" && (
              <DropdownMenuItem
                onClick={() =>
                  setConfirm({
                    type: "status",
                    status: "active",
                    row,
                    title: `Aktifkan kembali ${config.singular}?`,
                    description: `"${row.name}" akan kembali muncul sebagai pilihan di seluruh modul.`,
                  })
                }
                data-testid={`row-activate-${row.id}`}
              >
                <RotateCcw className="mr-2 h-4 w-4" /> Aktifkan kembali
              </DropdownMenuItem>
            )}
            {can(config.resource, "delete") && (
              <DropdownMenuItem
                className="text-destructive focus:text-destructive"
                onClick={() =>
                  setConfirm({
                    type: "delete",
                    row,
                    destructive: true,
                    title: `Hapus ${config.singular} secara permanen?`,
                    description: `"${row.name}" akan dihapus dan tidak dapat dikembalikan. Jika data ini sudah dipakai transaksi lain, sistem akan menolak dan menyarankan Anda menonaktifkannya saja.`,
                  })
                }
                data-testid={`row-delete-${row.id}`}
              >
                <Trash2 className="mr-2 h-4 w-4" /> Hapus
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ];

  const hasFilters = !!debounced || statusFilter !== "active" || Object.values(relationFilter).some(Boolean);

  return (
    <>
      <PageHeader
        title={config.label}
        subtitle={config.subtitle}
        actions={
          can(config.resource, "create") && (
            <Button onClick={openCreate} data-testid="page-header-primary-action">
              <Plus className="mr-2 h-4 w-4" /> Tambah {config.singular}
            </Button>
          )
        }
      />
      <PageBody>
        <FilterBar
          search={search}
          onSearchChange={(v) => {
            setSearch(v);
            setPage(1);
          }}
          searchPlaceholder={`Cari kode atau nama ${config.label.toLowerCase()}…`}
          showReset={hasFilters}
          onReset={() => {
            setSearch("");
            setStatusFilter("active");
            setRelationFilter({});
            setPage(1);
          }}
        >
          <FilterSelect
            label="Status"
            value={statusFilter}
            onChange={(v) => {
              setStatusFilter(v);
              setPage(1);
            }}
            options={STATUS_OPTIONS}
            allLabel="Semua status"
            testId="filter-status"
          />
          {relationFields.map((f) => (
            <FilterSelect
              key={f.name}
              label={f.label}
              value={relationFilter[f.name] || ""}
              onChange={(v) => {
                setRelationFilter((prev) => ({ ...prev, [f.name]: v }));
                setPage(1);
              }}
              options={(options[f.relation] || []).map((o) => ({ value: o.id, label: o.name }))}
              allLabel={`Semua ${f.label.toLowerCase()}`}
              testId={`filter-${f.name}`}
            />
          ))}
        </FilterBar>

        <TableCard>
          <DataTable
            columns={columns}
            rows={rows}
            loading={loading}
            testId={`master-table-${resourcePath}`}
            emptyProps={{
              title: hasFilters ? "Tidak ada data yang cocok." : "Belum ada data.",
              description: hasFilters
                ? "Coba ubah kata kunci atau hapus filter yang aktif."
                : `Tambahkan ${config.singular.toLowerCase()} pertama agar bisa dipakai di modul lain.`,
              actionLabel: !hasFilters && can(config.resource, "create") ? `Tambah ${config.singular}` : undefined,
              onAction: openCreate,
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

      <FormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        title={editing ? `Ubah ${config.singular}` : `Tambah ${config.singular}`}
        description={
          editing
            ? "Perubahan akan tercatat di audit log beserta nilai sebelum dan sesudahnya."
            : `Isi data ${config.singular.toLowerCase()} berikut. Kolom bertanda * wajib diisi.`
        }
        fields={fieldsWithOptions}
        values={values}
        errors={errors}
        onChange={handleChange}
        onSubmit={handleSubmit}
        submitting={submitting}
        submitLabel={editing ? "Simpan perubahan" : `Simpan ${config.singular}`}
      />

      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(v) => !v && setConfirm(null)}
        title={confirm?.title}
        description={confirm?.description}
        destructive={confirm?.destructive}
        confirmLabel={confirm?.type === "delete" ? "Hapus permanen" : "Ya, lanjutkan"}
        loading={confirmLoading}
        onConfirm={runConfirm}
      />
    </>
  );
};

export default MasterDataPage;
