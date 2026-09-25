import React, { useCallback, useEffect, useState } from "react";
import { Lock, MoreHorizontal, Pencil, Plus, Power, RotateCcw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { STATUS_CATEGORIES } from "@/lib/employeeStatus";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import DataTable, { FilterBar, FilterSelect, TableCard } from "@/components/common/DataTable";
import FormDialog from "@/components/common/FormDialog";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import StatusBadge from "@/components/common/StatusBadge";
import { CategoryBadge } from "@/components/employees/EmployeeStatusBadge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const ACTIVE_OPTIONS = [
  { value: "true", label: "Aktif" },
  { value: "false", label: "Nonaktif" },
];
const EMPTY = { code: "", name: "", system_category: "", description: "", sort_order: "", is_active: true };

export default function EmployeeStatusMasterPage() {
  const { can } = useAuth();
  const canManage = can("employee_status", "manage");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [category, setCategory] = useState("");
  const [active, setActive] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [values, setValues] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  useEffect(() => {
    document.title = "Status Karyawan · KelolaKita";
  }, []);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const params = {};
      if (debounced) params.q = debounced;
      if (category) params.category = category;
      if (active) params.active = active;
      const res = await api.get("/employee-statuses", { params });
      setRows(res.data.items || []);
    } catch (err) {
      setLoadError(errorMessage(err, "Daftar status gagal dimuat."));
    } finally {
      setLoading(false);
    }
  }, [debounced, category, active]);

  useEffect(() => {
    load();
  }, [load]);

  const openCreate = () => {
    setEditing(null);
    setValues(EMPTY);
    setErrors({});
    setDialogOpen(true);
  };
  const openEdit = (row) => {
    setEditing(row);
    setValues({
      code: row.code || "",
      name: row.name || "",
      system_category: row.system_category || "",
      description: row.description || "",
      sort_order: row.sort_order ?? "",
      is_active: !!row.is_active,
    });
    setErrors({});
    setDialogOpen(true);
  };

  const lockedCategory = !!editing && (editing.is_default || editing.is_used);
  const lockedCode = !!editing && (editing.is_default || editing.is_used);
  const fields = [
    {
      name: "code", label: "Kode Status", required: true, placeholder: "Mis. AKTIF_PROJECT", disabled: lockedCode,
      hint: lockedCode ? "Terkunci: status default / sudah pernah digunakan." : "Huruf besar, angka, garis bawah.",
    },
    { name: "name", label: "Nama Status", required: true, placeholder: "Mis. Aktif Project" },
    {
      name: "system_category", label: "Kategori Sistem", type: "select", required: true, disabled: lockedCategory,
      options: STATUS_CATEGORIES, placeholder: "Pilih kategori",
      hint: lockedCategory
        ? "Terkunci agar makna riwayat lama tidak berubah."
        : "Hanya AKTIF, STANDBY, atau TIDAK AKTIF.",
    },
    { name: "sort_order", label: "Urutan", type: "number", placeholder: "Otomatis bila kosong" },
    { name: "description", label: "Deskripsi", type: "textarea", colSpan: 2 },
    ...(editing ? [] : [{ name: "is_active", label: "Aktif", type: "boolean" }]),
  ];

  const handleChange = (name, value) => {
    setValues((p) => ({ ...p, [name]: value }));
    setErrors((p) => ({ ...p, [name]: undefined }));
  };

  const handleSubmit = async () => {
    const e = {};
    if (!values.code.trim()) e.code = "Kode status wajib diisi.";
    if (values.name.trim().length < 2) e.name = "Nama status wajib diisi.";
    if (!values.system_category) e.system_category = "Pilih kategori sistem.";
    if (Object.keys(e).length) return setErrors(e);
    setSubmitting(true);
    const body = {
      code: values.code.trim().toUpperCase(),
      name: values.name.trim(),
      system_category: values.system_category,
      description: values.description || null,
      sort_order: values.sort_order === "" ? null : Number(values.sort_order),
    };
    try {
      if (editing) {
        await api.put(`/employee-statuses/${editing.id}`, body);
        toast.success("Status karyawan diperbarui.");
      } else {
        await api.post("/employee-statuses", { ...body, is_active: !!values.is_active });
        toast.success("Status karyawan ditambahkan.");
      }
      setDialogOpen(false);
      load();
    } catch (err) {
      toast.error(errorMessage(err, "Status karyawan gagal disimpan."), { duration: 9000 });
    } finally {
      setSubmitting(false);
    }
  };

  const runConfirm = async () => {
    setConfirmLoading(true);
    try {
      const { type, row } = confirm;
      if (type === "delete") await api.delete(`/employee-statuses/${row.id}`);
      else await api.patch(`/employee-statuses/${row.id}/${type}`);
      toast.success(
        type === "delete" ? "Status dihapus." : type === "activate" ? "Status diaktifkan." : "Status dinonaktifkan."
      );
      setConfirm(null);
      load();
    } catch (err) {
      toast.error(errorMessage(err, "Tindakan tidak dapat dilakukan."), { duration: 9000 });
      setConfirm(null);
    } finally {
      setConfirmLoading(false);
    }
  };

  const columns = [
    {
      key: "code",
      header: "Kode",
      render: (r) => (
        <span className="inline-flex items-center gap-1.5 font-medium" data-testid={`status-code-${r.code}`}>
          {r.code}
          {r.is_default && <Lock className="h-3 w-3 text-muted-foreground" aria-label="Status default" />}
        </span>
      ),
    },
    {
      key: "name",
      header: "Nama Status",
      render: (r) => (
        <div>
          <p className="font-medium">{r.name}</p>
          {r.description && <p className="line-clamp-1 text-[12px] text-muted-foreground">{r.description}</p>}
        </div>
      ),
    },
    { key: "system_category", header: "Kategori Sistem", render: (r) => <CategoryBadge category={r.system_category} testId={`status-category-${r.code}`} /> },
    {
      key: "is_active",
      header: "Status Aktif",
      render: (r) => <StatusBadge status={r.is_active ? "active" : "inactive"} label={r.is_active ? "Aktif" : "Nonaktif"} />,
    },
    {
      key: "usage",
      header: "Jumlah Penggunaan",
      hideOnMobile: true,
      render: (r) => (
        <div className="text-sm" data-testid={`status-usage-${r.code}`}>
          <span className="font-medium">{r.usage_current ?? 0}</span>
          <span className="text-muted-foreground"> karyawan</span>
          <span className="block text-[11px] text-muted-foreground">{r.usage_history ?? 0} catatan riwayat</span>
        </div>
      ),
    },
    {
      key: "actions",
      header: "Aksi",
      className: "w-16 text-right",
      render: (r) =>
        canManage ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-8 w-8" aria-label="Aksi baris" data-testid={`status-row-actions-${r.code}`}>
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52">
              <DropdownMenuItem onClick={() => openEdit(r)} data-testid={`status-row-edit-${r.code}`}>
                <Pencil className="mr-2 h-4 w-4" /> Edit
              </DropdownMenuItem>
              {r.is_active && !r.is_default && (
                <DropdownMenuItem
                  onClick={() => setConfirm({ type: "deactivate", row: r })}
                  data-testid={`status-row-deactivate-${r.code}`}
                >
                  <Power className="mr-2 h-4 w-4" /> Nonaktifkan
                </DropdownMenuItem>
              )}
              {!r.is_active && (
                <DropdownMenuItem onClick={() => setConfirm({ type: "activate", row: r })} data-testid={`status-row-activate-${r.code}`}>
                  <RotateCcw className="mr-2 h-4 w-4" /> Aktifkan
                </DropdownMenuItem>
              )}
              {!r.is_used && !r.is_default && (
                <DropdownMenuItem
                  className="text-destructive focus:text-destructive"
                  onClick={() => setConfirm({ type: "delete", row: r })}
                  data-testid={`status-row-delete-${r.code}`}
                >
                  <Trash2 className="mr-2 h-4 w-4" /> Hapus
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null,
    },
  ];

  const hasFilters = !!debounced || !!category || !!active;
  const confirmText = {
    deactivate: {
      title: "Nonaktifkan status?",
      description: (r) =>
        `"${r.name}" tidak dapat dipilih untuk perubahan status baru. Karyawan yang sedang memakai status ini dan riwayat lama tetap aman.`,
      label: "Ya, nonaktifkan",
    },
    activate: { title: "Aktifkan status?", description: (r) => `"${r.name}" dapat dipilih kembali saat Ubah Status.`, label: "Ya, aktifkan" },
    delete: {
      title: "Hapus status permanen?",
      description: (r) => `"${r.name}" belum pernah digunakan dan akan dihapus permanen.`,
      label: "Hapus permanen",
    },
  }[confirm?.type || "activate"];

  return (
    <>
      <PageHeader
        title="Status Karyawan"
        subtitle="Status bisnis karyawan per perusahaan, dipetakan ke 3 kategori sistem: AKTIF, STANDBY, TIDAK AKTIF."
        actions={
          canManage && (
            <Button onClick={openCreate} data-testid="employee-status-add-button">
              <Plus className="mr-2 h-4 w-4" /> Tambah Status
            </Button>
          )
        }
      />
      <PageBody>
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-muted/30 px-4 py-3 text-[13px] text-muted-foreground" data-testid="employee-status-category-info">
          <Lock className="h-3.5 w-3.5" aria-hidden="true" />
          Kategori sistem terkunci:
          {STATUS_CATEGORIES.map((c) => (
            <CategoryBadge key={c.value} category={c.value} testId={`locked-category-${c.value}`} />
          ))}
        </div>
        <FilterBar
          search={search}
          onSearchChange={setSearch}
          searchPlaceholder="Cari kode atau nama status…"
          showReset={hasFilters}
          onReset={() => {
            setSearch("");
            setCategory("");
            setActive("");
          }}
        >
          <FilterSelect label="Kategori" value={category} onChange={setCategory} options={STATUS_CATEGORIES} allLabel="Semua kategori" testId="filter-status-category" />
          <FilterSelect label="Aktif / Nonaktif" value={active} onChange={setActive} options={ACTIVE_OPTIONS} allLabel="Semua" testId="filter-status-active" />
        </FilterBar>
        <TableCard>
          {loadError ? (
            <div className="flex flex-wrap items-center justify-between gap-3 p-5 text-sm text-danger" data-testid="employee-status-load-error">
              {loadError}
              <Button size="sm" variant="outline" onClick={load}>Coba lagi</Button>
            </div>
          ) : (
            <DataTable
              columns={columns}
              rows={rows}
              loading={loading}
              testId="employee-status-table"
              emptyProps={{
                title: hasFilters ? "Tidak ada status yang cocok." : "Belum ada status karyawan.",
                description: hasFilters ? "Ubah kata kunci atau hapus filter." : "Tambahkan status bisnis pertama.",
                actionLabel: !hasFilters && canManage ? "Tambah Status" : undefined,
                onAction: openCreate,
              }}
            />
          )}
        </TableCard>
      </PageBody>

      <FormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        title={editing ? "Edit Status Karyawan" : "Tambah Status Karyawan"}
        description={
          editing
            ? "Perubahan tercatat di audit log. Kategori dan kode terkunci bila status sudah pernah digunakan."
            : "Status bisnis baru harus dipetakan ke salah satu kategori sistem."
        }
        fields={fields}
        values={values}
        errors={errors}
        onChange={handleChange}
        onSubmit={handleSubmit}
        submitting={submitting}
        submitLabel={editing ? "Simpan perubahan" : "Simpan status"}
      />
      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(v) => !v && setConfirm(null)}
        title={confirmText.title}
        description={confirm ? confirmText.description(confirm.row) : ""}
        destructive={confirm?.type === "delete"}
        confirmLabel={confirmText.label}
        loading={confirmLoading}
        onConfirm={runConfirm}
      />
    </>
  );
}
