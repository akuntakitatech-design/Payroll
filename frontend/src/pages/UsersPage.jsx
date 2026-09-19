import React, { useCallback, useEffect, useMemo, useState } from "react";
import { MoreHorizontal, Plus, Pencil, Power, RotateCcw, UserMinus, Building2 } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import DataTable, { FilterBar, FilterSelect, Pagination, TableCard } from "@/components/common/DataTable";
import FormDialog from "@/components/common/FormDialog";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import StatusBadge from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const ROLE_LABELS = {
  super_admin: "Super Admin",
  company_owner: "Pemilik Perusahaan",
  hr_admin: "HR Admin",
  hr_manager: "HR Manager",
  finance: "Finance",
  manager: "Manager",
  supervisor: "Supervisor",
  employee: "Karyawan",
};

const UsersPage = () => {
  const { can, isSuperAdmin, user: me, company, companies } = useAuth();
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState({ total: 0, page: 1, limit: 20, total_pages: 1 });
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(20);
  const [roles, setRoles] = useState([]);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [values, setValues] = useState({});
  const [selectedRoles, setSelectedRoles] = useState([]);
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);

  const [grantUser, setGrantUser] = useState(null);
  const [grantCompany, setGrantCompany] = useState("");
  const [grantRoles, setGrantRoles] = useState([]);
  const [confirm, setConfirm] = useState(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 350);
    return () => clearTimeout(t);
  }, [search]);

  const loadRoles = useCallback(async () => {
    try {
      const res = await api.get("/auth/catalog");
      // roles list comes from /roles when permitted; fall back to static labels
      setRoles(
        Object.keys(ROLE_LABELS)
          .filter((k) => isSuperAdmin || k !== "super_admin")
          .map((k) => ({ key: k, name: ROLE_LABELS[k] }))
      );
      void res;
    } catch {
      setRoles(Object.keys(ROLE_LABELS).map((k) => ({ key: k, name: ROLE_LABELS[k] })));
    }
  }, [isSuperAdmin]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, limit };
      if (debounced) params.q = debounced;
      if (roleFilter) params.role_key = roleFilter;
      if (statusFilter) params.status = statusFilter;
      const res = await api.get("/users", { params });
      setRows(res.data.items || []);
      setMeta({
        total: res.data.total,
        page: res.data.page,
        limit: res.data.limit,
        total_pages: res.data.total_pages,
      });
    } catch (err) {
      toast.error(errorMessage(err, "Gagal memuat daftar pengguna."));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [page, limit, debounced, roleFilter, statusFilter]);

  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    loadRoles();
    document.title = "Pengguna · HRIS Suite";
  }, [loadRoles]);

  const baseFields = useMemo(
    () => [
      { name: "full_name", label: "Nama Lengkap", required: true },
      { name: "email", label: "Email", required: !editing, hint: editing ? "Email tidak dapat diubah." : "Dipakai untuk login." },
      { name: "job_title", label: "Jabatan / Posisi" },
      { name: "employee_number", label: "Nomor Induk Karyawan" },
      { name: "phone", label: "Telepon" },
      {
        name: "password",
        label: editing ? "Kata Sandi Baru" : "Kata Sandi",
        required: !editing,
        hint: editing ? "Kosongkan bila tidak ingin mengganti kata sandi." : "Minimal 8 karakter.",
      },
      ...(editing
        ? [
            {
              name: "status",
              label: "Status Akun",
              type: "select",
              required: true,
              options: [
                { value: "active", label: "Aktif" },
                { value: "inactive", label: "Nonaktif" },
              ],
            },
          ]
        : []),
    ],
    [editing]
  );

  const openCreate = () => {
    setEditing(null);
    setValues({});
    setSelectedRoles(["employee"]);
    setErrors({});
    setDialogOpen(true);
  };

  const openEdit = (row) => {
    setEditing(row);
    setValues({
      full_name: row.full_name || "",
      email: row.email || "",
      job_title: row.job_title || "",
      employee_number: row.employee_number || "",
      phone: row.phone || "",
      password: "",
      status: row.status || "active",
    });
    setSelectedRoles(row.role_keys || []);
    setErrors({});
    setDialogOpen(true);
  };

  const toggleRole = (key) =>
    setSelectedRoles((prev) => (prev.includes(key) ? prev.filter((r) => r !== key) : [...prev, key]));

  const handleSubmit = async () => {
    const nextErrors = {};
    if (!String(values.full_name || "").trim()) nextErrors.full_name = "Nama lengkap wajib diisi.";
    if (!editing && !String(values.email || "").trim()) nextErrors.email = "Email wajib diisi.";
    if (!editing && String(values.password || "").length < 8)
      nextErrors.password = "Kata sandi minimal 8 karakter.";
    if (editing && values.password && String(values.password).length < 8)
      nextErrors.password = "Kata sandi baru minimal 8 karakter.";
    if (!selectedRoles.length)
      nextErrors.__form__ = "Pilih minimal satu peran agar pengguna tahu apa yang boleh dikerjakan.";
    if (Object.keys(nextErrors).length) {
      setErrors(nextErrors);
      return;
    }
    setSubmitting(true);
    try {
      if (editing) {
        const payload = {
          full_name: values.full_name,
          job_title: values.job_title || null,
          employee_number: values.employee_number || null,
          phone: values.phone || null,
          status: values.status,
          role_keys: selectedRoles,
        };
        if (values.password) payload.password = values.password;
        Object.keys(payload).forEach((k) => payload[k] === null && delete payload[k]);
        await api.put(`/users/${editing.id}`, payload);
        toast.success(`Data pengguna ${values.full_name} berhasil diperbarui.`);
      } else {
        await api.post("/users", {
          email: values.email,
          full_name: values.full_name,
          password: values.password,
          job_title: values.job_title || null,
          employee_number: values.employee_number || null,
          phone: values.phone || null,
          role_keys: selectedRoles,
        });
        toast.success(`Pengguna ${values.full_name} berhasil ditambahkan.`);
      }
      setDialogOpen(false);
      load();
    } catch (err) {
      setErrors({ __form__: errorMessage(err, "Data pengguna tidak dapat disimpan.") });
    } finally {
      setSubmitting(false);
    }
  };

  const runConfirm = async () => {
    if (!confirm) return;
    setConfirmLoading(true);
    try {
      if (confirm.type === "revoke") {
        await api.delete(`/users/${confirm.row.id}`);
        toast.success(`Akses ${confirm.row.full_name} pada perusahaan ini dicabut.`);
      } else {
        await api.put(`/users/${confirm.row.id}`, { status: confirm.status });
        toast.success(
          confirm.status === "active"
            ? `Akun ${confirm.row.full_name} diaktifkan kembali.`
            : `Akun ${confirm.row.full_name} dinonaktifkan.`
        );
      }
      setConfirm(null);
      load();
    } catch (err) {
      toast.error(errorMessage(err, "Tindakan tidak dapat dilakukan."));
      setConfirm(null);
    } finally {
      setConfirmLoading(false);
    }
  };

  const submitGrant = async () => {
    if (!grantCompany || !grantRoles.length) {
      toast.error("Pilih perusahaan tujuan dan minimal satu peran.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await api.post(`/users/${grantUser.id}/grant-company-access`, {
        company_id: grantCompany,
        role_keys: grantRoles,
      });
      toast.success(res.data.message);
      setGrantUser(null);
      setGrantCompany("");
      setGrantRoles([]);
    } catch (err) {
      toast.error(errorMessage(err, "Akses perusahaan tidak dapat diberikan."));
    } finally {
      setSubmitting(false);
    }
  };

  const columns = [
    {
      key: "full_name",
      header: "Nama",
      render: (row) => (
        <div className="min-w-0">
          <p className="truncate font-medium">{row.full_name}</p>
          <p className="truncate text-xs text-muted-foreground">{row.email}</p>
        </div>
      ),
    },
    { key: "job_title", header: "Jabatan", hideOnMobile: true, render: (row) => row.job_title || "-" },
    {
      key: "role_keys",
      header: "Peran",
      hideOnMobile: true,
      render: (row) => (
        <span className="text-[13px] text-foreground">
          {(row.role_keys || []).map((r) => ROLE_LABELS[r] || r).join(" · ") || "-"}
        </span>
      ),
    },
    {
      key: "last_login_at",
      header: "Login Terakhir",
      hideOnMobile: true,
      render: (row) => (row.last_login_at ? formatDateTime(row.last_login_at) : "Belum pernah"),
    },
    { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
    {
      key: "actions",
      header: "",
      className: "w-12 text-right",
      render: (row) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-8 w-8" data-testid={`user-actions-${row.id}`}>
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-60">
            {can("user", "edit") && (
              <DropdownMenuItem onClick={() => openEdit(row)} data-testid={`user-edit-${row.id}`}>
                <Pencil className="mr-2 h-4 w-4" /> Ubah data &amp; peran
              </DropdownMenuItem>
            )}
            {can("user", "edit") && companies.length > 1 && (
              <DropdownMenuItem
                onClick={() => {
                  setGrantUser(row);
                  setGrantCompany("");
                  setGrantRoles([]);
                }}
                data-testid={`user-grant-${row.id}`}
              >
                <Building2 className="mr-2 h-4 w-4" /> Beri akses perusahaan lain
              </DropdownMenuItem>
            )}
            {can("user", "edit") && row.status === "active" && row.id !== me?.id && (
              <DropdownMenuItem
                onClick={() =>
                  setConfirm({
                    type: "status",
                    status: "inactive",
                    row,
                    title: "Nonaktifkan akun pengguna?",
                    description: `${row.full_name} tidak akan bisa login lagi. Seluruh riwayat aktivitasnya tetap tersimpan di audit log.`,
                  })
                }
                data-testid={`user-deactivate-${row.id}`}
              >
                <Power className="mr-2 h-4 w-4" /> Nonaktifkan akun
              </DropdownMenuItem>
            )}
            {can("user", "edit") && row.status !== "active" && (
              <DropdownMenuItem
                onClick={() =>
                  setConfirm({
                    type: "status",
                    status: "active",
                    row,
                    title: "Aktifkan kembali akun ini?",
                    description: `${row.full_name} akan dapat login kembali dengan peran yang sudah diberikan.`,
                  })
                }
                data-testid={`user-activate-${row.id}`}
              >
                <RotateCcw className="mr-2 h-4 w-4" /> Aktifkan akun
              </DropdownMenuItem>
            )}
            {can("user", "delete") && row.id !== me?.id && (
              <DropdownMenuItem
                className="text-destructive focus:text-destructive"
                onClick={() =>
                  setConfirm({
                    type: "revoke",
                    row,
                    destructive: true,
                    title: "Cabut akses dari perusahaan ini?",
                    description: `${row.full_name} tidak lagi menjadi anggota ${company?.name}. Akunnya tidak dihapus dan akses ke perusahaan lain tetap berjalan.`,
                  })
                }
                data-testid={`user-revoke-${row.id}`}
              >
                <UserMinus className="mr-2 h-4 w-4" /> Cabut akses perusahaan
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ];

  const rolePicker = (selected, onToggle, testPrefix) => (
    <div className="space-y-2 sm:col-span-2">
      <Label className="text-sm font-medium">
        Peran di {company?.name} <span className="text-destructive">*</span>
      </Label>
      <div className="grid grid-cols-1 gap-1.5 rounded-lg border border-border bg-background p-3 sm:grid-cols-2">
        {roles.map((role) => (
          <label
            key={role.key}
            className="flex cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent"
          >
            <Checkbox
              checked={selected.includes(role.key)}
              onCheckedChange={() => onToggle(role.key)}
              data-testid={`${testPrefix}-${role.key}`}
              className="mt-0.5"
            />
            <span>{role.name}</span>
          </label>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        Hak akses detail setiap peran dapat diatur di menu Peran &amp; Hak Akses.
      </p>
    </div>
  );

  const hasFilters = !!debounced || !!roleFilter || !!statusFilter;

  return (
    <>
      <PageHeader
        title="Pengguna"
        subtitle={`Akun yang memiliki akses ke ${company?.name || "perusahaan aktif"}.`}
        actions={
          can("user", "create") && (
            <Button onClick={openCreate} data-testid="page-header-primary-action">
              <Plus className="mr-2 h-4 w-4" /> Tambah Pengguna
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
          searchPlaceholder="Cari nama, email, atau NIK…"
          showReset={hasFilters}
          onReset={() => {
            setSearch("");
            setRoleFilter("");
            setStatusFilter("");
            setPage(1);
          }}
        >
          <FilterSelect
            label="Peran"
            value={roleFilter}
            onChange={(v) => {
              setRoleFilter(v);
              setPage(1);
            }}
            options={roles.map((r) => ({ value: r.key, label: r.name }))}
            allLabel="Semua peran"
            testId="filter-role"
          />
          <FilterSelect
            label="Status"
            value={statusFilter}
            onChange={(v) => {
              setStatusFilter(v);
              setPage(1);
            }}
            options={[
              { value: "active", label: "Aktif" },
              { value: "inactive", label: "Nonaktif" },
            ]}
            allLabel="Semua status"
            testId="filter-status"
          />
        </FilterBar>

        <TableCard>
          <DataTable
            columns={columns}
            rows={rows}
            loading={loading}
            testId="users-table"
            emptyProps={{
              title: hasFilters ? "Tidak ada pengguna yang cocok." : "Belum ada pengguna lain.",
              description: hasFilters
                ? "Coba ubah kata kunci atau hapus filter yang aktif."
                : "Tambahkan akun untuk tim HR, Finance, manager, dan karyawan.",
              actionLabel: !hasFilters && can("user", "create") ? "Tambah Pengguna" : undefined,
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
        title={editing ? `Ubah Pengguna — ${editing.full_name}` : "Tambah Pengguna"}
        description={
          editing
            ? "Perubahan data dan peran akan tercatat di audit log."
            : "Akun baru langsung mendapat akses ke perusahaan aktif sesuai peran yang dipilih."
        }
        fields={baseFields.map((f) => (f.name === "email" && editing ? { ...f, disabled: true } : f))}
        values={values}
        errors={errors}
        onChange={(name, value) => {
          setValues((p) => ({ ...p, [name]: value }));
          setErrors((p) => ({ ...p, [name]: undefined, __form__: undefined }));
        }}
        onSubmit={handleSubmit}
        submitting={submitting}
        submitLabel={editing ? "Simpan perubahan" : "Simpan Pengguna"}
        extra={rolePicker(selectedRoles, toggleRole, "user-role-checkbox")}
      />

      <FormDialog
        open={!!grantUser}
        onOpenChange={(v) => !v && setGrantUser(null)}
        title={`Beri akses perusahaan — ${grantUser?.full_name || ""}`}
        description="Satu akun dapat bekerja di beberapa perusahaan dengan peran berbeda. Data tiap perusahaan tetap terpisah."
        fields={[
          {
            name: "company_id",
            label: "Perusahaan Tujuan",
            type: "select",
            required: true,
            options: companies.filter((c) => c.id !== company?.id).map((c) => ({ value: c.id, label: c.name })),
          },
        ]}
        values={{ company_id: grantCompany }}
        onChange={(_, value) => setGrantCompany(value)}
        onSubmit={submitGrant}
        submitting={submitting}
        submitLabel="Berikan akses"
        extra={
          <div className="space-y-2">
            <Label className="text-sm font-medium">
              Peran di perusahaan tujuan <span className="text-destructive">*</span>
            </Label>
            <div className="grid grid-cols-1 gap-1.5 rounded-lg border border-border bg-background p-3 sm:grid-cols-2">
              {roles.map((role) => (
                <label
                  key={role.key}
                  className="flex cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent"
                >
                  <Checkbox
                    checked={grantRoles.includes(role.key)}
                    onCheckedChange={() =>
                      setGrantRoles((prev) =>
                        prev.includes(role.key) ? prev.filter((r) => r !== role.key) : [...prev, role.key]
                      )
                    }
                    data-testid={`grant-role-checkbox-${role.key}`}
                    className="mt-0.5"
                  />
                  <span>{role.name}</span>
                </label>
              ))}
            </div>
          </div>
        }
      />

      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(v) => !v && setConfirm(null)}
        title={confirm?.title}
        description={confirm?.description}
        destructive={confirm?.destructive}
        confirmLabel={confirm?.type === "revoke" ? "Cabut akses" : "Ya, lanjutkan"}
        loading={confirmLoading}
        onConfirm={runConfirm}
      />
    </>
  );
};

export default UsersPage;
