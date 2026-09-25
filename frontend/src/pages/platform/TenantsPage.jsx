import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  Building2,
  CalendarPlus,
  Copy,
  Eye,
  KeyRound,
  MoreHorizontal,
  Pencil,
  Plus,
  Power,
  RotateCcw,
  ShieldAlert,
  UserMinus,
  UserPlus,
} from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { brandTitle, useBranding } from "@/lib/branding";
import { TenantLogo } from "@/components/common/TenantLogo";
import TenantCreateWizard from "./TenantCreateWizard";
import { formatDate, formatDateTime } from "@/lib/format";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import DataTable, { FilterBar, FilterSelect, TableCard } from "@/components/common/DataTable";
import FormDialog from "@/components/common/FormDialog";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import StatusBadge from "@/components/common/StatusBadge";
import { SubscriptionBadge, subscriptionHint } from "@/components/common/SubscriptionBadge";
import EmptyState from "@/components/common/EmptyState";
import { Button } from "@/components/ui/button";
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
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const STATUS_OPTIONS = [
  { value: "active", label: "Aktif" },
  { value: "inactive", label: "Nonaktif" },
];

const SUBSCRIPTION_OPTIONS = [
  { value: "active", label: "Aktif" },
  { value: "grace", label: "Masa Tenggang" },
  { value: "expired", label: "Berakhir" },
];

// Masa layanan: tanggal boleh kosong = tenant legacy / tanpa batas (tidak diblokir).
const SUBSCRIPTION_FORM_FIELDS = [
  { name: "subscription_start_date", label: "Tanggal Mulai Layanan", type: "date" },
  {
    name: "subscription_end_date",
    label: "Tanggal Berakhir Layanan",
    type: "date",
    hint: "Kosongkan untuk tenant legacy / tanpa batas.",
  },
  {
    name: "grace_period_days",
    label: "Grace Period (hari)",
    type: "number",
    hint: "Masa tenggang setelah tanggal berakhir; tenant tetap beroperasi dengan peringatan. Kosong = default konfigurasi.",
  },
  { name: "subscription_notes", label: "Catatan Masa Layanan", type: "textarea", rows: 2, hint: "Opsional." },
];

export const EDIT_FIELDS = [
  { name: "name", label: "Nama Tenant", required: true },
  { name: "legal_name", label: "Nama Badan Hukum", hint: "Opsional." },
  { name: "pic_name", label: "Nama PIC", required: true },
  { name: "pic_phone", label: "No. HP PIC", required: true },
  { name: "email", label: "Email Utama Tenant", required: true, type: "email" },
  { name: "status", label: "Status Operasional", type: "select", required: true, options: STATUS_OPTIONS },
  ...SUBSCRIPTION_FORM_FIELDS,
];

export const subscriptionValues = (row) => ({
  subscription_start_date: row?.subscription?.start_date || "",
  subscription_end_date: row?.subscription?.end_date || "",
  grace_period_days: row?.subscription?.grace_period_days ?? "",
  subscription_notes: row?.subscription?.notes || "",
});

export const subscriptionPayload = (values) => ({
  subscription_start_date: values.subscription_start_date || null,
  subscription_end_date: values.subscription_end_date || null,
  grace_period_days:
    values.grace_period_days === "" || values.grace_period_days === null || values.grace_period_days === undefined
      ? null
      : Number(values.grace_period_days),
  subscription_notes: values.subscription_notes?.trim() || null,
});

export const ADMIN_FIELDS = [
  { name: "email", label: "Email Tenant Admin", required: true, placeholder: "admin@perusahaan.co.id" },
  {
    name: "full_name",
    label: "Nama Lengkap",
    hint: "Wajib bila email belum terdaftar - akun baru dibuat dengan kata sandi sementara acak.",
  },
];

const TenantsPage = () => {
  const { isSuperAdmin } = useAuth();
  const { branding } = useBranding();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [wizardOpen, setWizardOpen] = useState(searchParams.get("new") === "1");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [subscriptionFilter, setSubscriptionFilter] = useState("");
  const [search, setSearch] = useState("");
  const [forbidden, setForbidden] = useState(false);

  const [formMode, setFormMode] = useState(null); // "create" | "edit"
  const [editing, setEditing] = useState(null);
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);

  const [adminTenant, setAdminTenant] = useState(null);
  const [adminValues, setAdminValues] = useState({ email: "", full_name: "" });
  const [adminErrors, setAdminErrors] = useState({});
  const [credential, setCredential] = useState(null);

  const [confirm, setConfirm] = useState(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  useEffect(() => {
    document.title = brandTitle(branding, "Tenant Registry");
  }, [branding]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (statusFilter) params.status = statusFilter;
      if (subscriptionFilter) params.subscription = subscriptionFilter;
      if (search.trim()) params.q = search.trim();
      const { data } = await api.get("/platform/tenants", { params });
      setRows(data.items || []);
      setForbidden(false);
    } catch (err) {
      if (err?.response?.status === 403) setForbidden(true);
      else toast.error(errorMessage(err, "Daftar tenant tidak dapat dimuat."));
    } finally {
      setLoading(false);
    }
  }, [statusFilter, subscriptionFilter, search]);

  useEffect(() => {
    if (isSuperAdmin) load();
    else setLoading(false);
  }, [isSuperAdmin, load]);

  const summary = useMemo(
    () => ({
      total: rows.length,
      active: rows.filter((r) => r.status === "active").length,
      inactive: rows.filter((r) => r.status !== "active").length,
      grace: rows.filter((r) => r.subscription?.status === "grace").length,
      expired: rows.filter((r) => r.subscription?.status === "expired").length,
    }),
    [rows]
  );

  const openCreate = () => setWizardOpen(true);

  const openEdit = (row) => {
    setFormMode("edit");
    setEditing(row);
    setValues({
      name: row.name || "",
      legal_name: row.legal_name || "",
      pic_name: row.pic_name || "",
      pic_phone: row.pic_phone || "",
      email: row.email || "",
      status: row.status === "active" ? "active" : "inactive",
      ...subscriptionValues(row),
    });
    setErrors({});
  };

  const handleChange = (name, value) => {
    setValues((p) => ({ ...p, [name]: value }));
    setErrors((p) => ({ ...p, [name]: undefined, __form__: undefined }));
  };

  const submitTenant = async () => {
    const next = {};
    if (String(values.name || "").trim().length < 2) next.name = "Nama tenant minimal 2 karakter.";
    if (String(values.pic_name || "").trim().length < 2) next.pic_name = "Nama PIC wajib diisi.";
    if (!/^[0-9+()\-\s]{6,20}$/.test(String(values.pic_phone || "").trim())) next.pic_phone = "Nomor HP 6-20 digit.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(values.email || "").trim())) next.email = "Email utama tidak valid.";
    const { subscription_start_date: sd, subscription_end_date: ed, grace_period_days: gp } = values;
    if (sd && ed && ed < sd) next.subscription_end_date = "Tanggal berakhir tidak boleh lebih awal dari tanggal mulai.";
    if (gp !== "" && gp !== null && gp !== undefined && (!Number.isInteger(Number(gp)) || Number(gp) < 0)) {
      next.grace_period_days = "Grace period harus bilangan bulat, tidak boleh negatif.";
    }
    if (Object.keys(next).length) {
      setErrors(next);
      return;
    }
    setSubmitting(true);
    try {
      await api.put(`/platform/tenants/${editing.id}`, {
        name: values.name.trim(),
        legal_name: values.legal_name?.trim() || null,
        pic_name: values.pic_name.trim(),
        pic_phone: values.pic_phone.trim(),
        email: values.email.trim().toLowerCase(),
        status: values.status,
        ...subscriptionPayload(values),
      });
      toast.success("Informasi tenant diperbarui.");
      setFormMode(null);
      load();
    } catch (err) {
      setErrors({ __form__: errorMessage(err, "Tenant tidak dapat disimpan.") });
    } finally {
      setSubmitting(false);
    }
  };

  const submitAdmin = async () => {
    const email = String(adminValues.email || "").trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setAdminErrors({ email: "Masukkan email yang valid." });
      return;
    }
    setSubmitting(true);
    try {
      const { data } = await api.post(`/platform/tenants/${adminTenant.id}/admins`, {
        email,
        full_name: adminValues.full_name?.trim() || null,
      });
      toast.success(data.message);
      if (data.temporary_password) {
        setCredential({ email: data.user.email, password: data.temporary_password, tenant: adminTenant.name });
      }
      setAdminTenant(null);
      load();
    } catch (err) {
      setAdminErrors({ __form__: errorMessage(err, "Tenant Admin tidak dapat ditunjuk.") });
    } finally {
      setSubmitting(false);
    }
  };

  const runConfirm = async () => {
    if (!confirm) return;
    setConfirmLoading(true);
    try {
      let data;
      if (confirm.type === "revoke") {
        ({ data } = await api.delete(`/platform/tenants/${confirm.row.id}/admins/${confirm.admin.id}`));
      } else {
        ({ data } = await api.post(`/platform/tenants/${confirm.row.id}/${confirm.type}`));
      }
      toast.success(data.message);
      setConfirm(null);
      load();
    } catch (err) {
      toast.error(errorMessage(err, "Tindakan tidak dapat dilakukan."));
      setConfirm(null);
    } finally {
      setConfirmLoading(false);
    }
  };

  const copyCredential = async () => {
    try {
      await navigator.clipboard.writeText(`Email: ${credential.email}\nKata sandi sementara: ${credential.password}`);
      toast.success("Kredensial disalin.");
    } catch {
      toast.error("Tidak dapat menyalin otomatis. Salin secara manual.");
    }
  };

  const columns = [
    {
      key: "name",
      header: "Tenant",
      render: (row) => (
        <div className="flex min-w-0 items-center gap-3">
          <TenantLogo source="platform" tenantId={row.id} hasLogo={row.has_logo} version={row.logo_version} name={row.name} size="sm" testId={`tenant-logo-${row.code}`} />
          <div className="min-w-0">
            <Link to={`/platform/tenants/${row.id}`} className="block truncate font-medium text-ink-1 hover:text-primary hover:underline" data-testid={`tenant-name-${row.code}`}>{row.name}</Link>
            <p className="truncate text-xs text-muted-foreground">
              {row.code} · {row.employee_count} karyawan · dibuat {row.created_at ? formatDateTime(row.created_at) : "-"}
            </p>
          </div>
        </div>
      ),
    },
    {
      key: "status",
      header: "Operasional",
      render: (row) => (
        <span data-testid={`tenant-status-${row.code}`}>
          <StatusBadge status={row.status} label={row.status === "active" ? "Aktif" : "Nonaktif"} />
        </span>
      ),
    },
    {
      key: "subscription",
      header: "Masa Layanan",
      render: (row) => (
        <div className="min-w-0" data-testid={`tenant-subscription-${row.code}`}>
          <SubscriptionBadge subscription={row.subscription} testId={`tenant-subscription-badge-${row.code}`} />
          <p className="mt-0.5 text-xs text-muted-foreground" data-testid={`tenant-subscription-hint-${row.code}`}>
            {subscriptionHint(row.subscription)}
          </p>
        </div>
      ),
    },
    {
      key: "end_date",
      header: "Berakhir",
      render: (row) => (
        <span className="whitespace-nowrap text-[13px] tabular-nums" data-testid={`tenant-end-date-${row.code}`}>
          {row.subscription?.end_date ? formatDate(row.subscription.end_date) : "-"}
        </span>
      ),
    },
    {
      key: "pic",
      header: "PIC & Email Utama",
      render: (row) => (
        <div className="min-w-0 text-[13px]" data-testid={`tenant-pic-${row.code}`}>
          <p className="truncate font-medium">{row.pic_name || "-"}</p>
          <p className="truncate text-xs text-muted-foreground">{row.email || "-"}{row.pic_phone ? ` · ${row.pic_phone}` : ""}</p>
        </div>
      ),
    },
    {
      key: "tenant_admins",
      header: "Tenant Admin",
      render: (row) =>
        row.tenant_admins?.length ? (
          <div className="min-w-0 space-y-0.5" data-testid={`tenant-admins-${row.code}`}>
            {row.tenant_admins.map((a) => (
              <p key={a.id} className="truncate text-[13px]">
                <span className="font-medium">{a.full_name}</span>
                <span className="text-muted-foreground"> · {a.email}</span>
              </p>
            ))}
          </div>
        ) : (
          <span className="text-[13px] text-muted-foreground" data-testid={`tenant-admins-${row.code}`}>
            Belum ditunjuk
          </span>
        ),
    },
    {
      key: "user_count",
      header: "Jumlah User",
      className: "text-right",
      render: (row) => (
        <span className="tabular-nums" data-testid={`tenant-users-${row.code}`}>{row.user_count}</span>
      ),
    },
    {
      key: "actions",
      header: "Aksi",
      className: "w-16 text-right",
      render: (row) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-8 w-8" data-testid={`tenant-actions-${row.code}`}>
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-60">
            <DropdownMenuItem onClick={() => navigate(`/platform/tenants/${row.id}`)} data-testid={`tenant-detail-${row.code}`}>
              <Eye className="mr-2 h-4 w-4" /> Lihat detail tenant
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => openEdit(row)} data-testid={`tenant-edit-${row.code}`}>
              <Pencil className="mr-2 h-4 w-4" /> Ubah informasi tenant
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => openEdit(row)} data-testid={`tenant-renew-${row.code}`}>
              <CalendarPlus className="mr-2 h-4 w-4" /> Atur / perpanjang masa layanan
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => {
                setAdminTenant(row);
                setAdminValues({ email: "", full_name: "" });
                setAdminErrors({});
              }}
              data-testid={`tenant-assign-admin-${row.code}`}
            >
              <UserPlus className="mr-2 h-4 w-4" /> Tunjuk Tenant Admin
            </DropdownMenuItem>
            {(row.tenant_admins || []).map((a) => (
              <DropdownMenuItem
                key={a.id}
                onClick={() => setConfirm({ type: "revoke", row, admin: a })}
                data-testid={`tenant-revoke-admin-${row.code}-${a.id}`}
              >
                <UserMinus className="mr-2 h-4 w-4" /> Cabut admin: {a.full_name}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            {row.status === "active" ? (
              <DropdownMenuItem
                className="text-destructive focus:text-destructive"
                onClick={() => setConfirm({ type: "deactivate", row })}
                data-testid={`tenant-deactivate-${row.code}`}
              >
                <Power className="mr-2 h-4 w-4" /> Nonaktifkan tenant
              </DropdownMenuItem>
            ) : (
              <DropdownMenuItem
                onClick={() => setConfirm({ type: "activate", row })}
                data-testid={`tenant-activate-${row.code}`}
              >
                <RotateCcw className="mr-2 h-4 w-4" /> Aktifkan kembali
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ];

  if (!isSuperAdmin || forbidden) {
    return (
      <>
        <PageHeader title="Tenant Registry" subtitle={`Konsol Platform ${branding.app_name}`} />
        <PageBody>
          <TableCard>
            <div data-testid="tenant-forbidden">
              <EmptyState
                icon={ShieldAlert}
                title="Khusus Platform Admin"
                description={`Pengelolaan tenant hanya dapat dilakukan oleh Platform Admin ${branding.app_name}.`}
              />
            </div>
          </TableCard>
        </PageBody>
      </>
    );
  }

  const confirmCopy = {
    deactivate: {
      title: `Nonaktifkan ${confirm?.row?.name}?`,
      description:
        "User tenant tidak akan dapat login atau menjalankan operasional. Data karyawan, payroll, dan histori TIDAK dihapus dan tersedia kembali saat tenant diaktifkan.",
      confirmLabel: "Nonaktifkan",
      destructive: true,
    },
    activate: {
      title: `Aktifkan kembali ${confirm?.row?.name}?`,
      description: "User tenant dapat login dan beroperasi kembali. Seluruh data tetap seperti sebelum dinonaktifkan.",
      confirmLabel: "Aktifkan",
    },
    revoke: {
      title: `Cabut Tenant Admin ${confirm?.admin?.full_name}?`,
      description: "Hanya peran Tenant Admin di tenant ini yang dicabut. Akun dan peran lain tidak diubah.",
      confirmLabel: "Cabut",
      destructive: true,
    },
  }[confirm?.type] || {};

  return (
    <>
      <PageHeader
        title="Tenant Registry"
        subtitle="Daftar seluruh tenant: status operasional, masa layanan, PIC, dan Tenant Admin."
        actions={
          <Button onClick={openCreate} data-testid="tenant-add-button">
            <Plus className="mr-1.5 h-4 w-4" /> Tambah Tenant
          </Button>
        }
      />
      <PageBody>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5" data-testid="tenant-summary">
          {[
            ["Total tenant", summary.total],
            ["Operasional aktif", summary.active],
            ["Nonaktif", summary.inactive],
            ["Masa tenggang", summary.grace],
            ["Layanan berakhir", summary.expired],
          ].map(([label, value]) => (
            <div key={label} className="rounded-xl border border-border bg-card px-4 py-3 shadow-xs">
              <p className="text-xs text-muted-foreground">{label}</p>
              <p className="mt-0.5 text-xl font-semibold tabular-nums">{value}</p>
            </div>
          ))}
        </div>

        <TableCard>
          <FilterBar search={search} onSearchChange={setSearch} searchPlaceholder="Cari nama atau kode tenant…">
            <FilterSelect
              label="Operasional"
              value={statusFilter}
              onChange={setStatusFilter}
              options={STATUS_OPTIONS}
              testId="tenant-status-filter"
            />
            <FilterSelect
              label="Masa Layanan"
              value={subscriptionFilter}
              onChange={setSubscriptionFilter}
              options={SUBSCRIPTION_OPTIONS}
              testId="tenant-subscription-filter"
            />
          </FilterBar>
          <DataTable
            columns={columns}
            rows={rows}
            loading={loading}
            testId="tenant-table"
            emptyProps={{
              icon: Building2,
              title: "Belum ada tenant.",
              description: "Tambahkan tenant pertama beserta Tenant Admin-nya.",
            }}
          />
        </TableCard>
      </PageBody>

      <FormDialog
        open={!!formMode}
        onOpenChange={(open) => !open && setFormMode(null)}
        title={`Ubah Tenant ${editing?.code || ""}`}
        description="Kode tenant bersifat permanen. Status operasional dan masa layanan adalah dua hal terpisah: tenant diblokir bila nonaktif ATAU masa layanan (termasuk tenggang) telah habis."
        fields={EDIT_FIELDS}
        values={values}
        errors={errors}
        onChange={handleChange}
        onSubmit={submitTenant}
        submitting={submitting}
        submitLabel="Simpan"
      />

      <TenantCreateWizard
        open={wizardOpen}
        onOpenChange={(o) => {
          setWizardOpen(o);
          if (!o && searchParams.get("new")) setSearchParams({}, { replace: true });
        }}
        onCreated={(data, opts) => {
          if (opts?.open) navigate(`/platform/tenants/${data.id}`);
          else load();
        }}
      />

      <FormDialog
        open={!!adminTenant}
        onOpenChange={(open) => !open && setAdminTenant(null)}
        title={`Tunjuk Tenant Admin · ${adminTenant?.name || ""}`}
        description="Tenant Admin mengelola user, peran tenant, master, karyawan, proyek, dan modul di tenant ini. Tenant Admin tidak dapat membuat atau mengubah tenant."
        fields={ADMIN_FIELDS}
        values={adminValues}
        errors={adminErrors}
        onChange={(name, value) => {
          setAdminValues((p) => ({ ...p, [name]: value }));
          setAdminErrors((p) => ({ ...p, [name]: undefined, __form__: undefined }));
        }}
        onSubmit={submitAdmin}
        submitting={submitting}
        submitLabel="Tunjuk Admin"
      />

      <Dialog open={!!credential} onOpenChange={(open) => !open && setCredential(null)}>
        <DialogContent className="bg-card sm:max-w-md" data-testid="tenant-credential-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <KeyRound className="h-4 w-4" /> Kredensial Tenant Admin
            </DialogTitle>
            <DialogDescription>
              Akun baru untuk {credential?.tenant}. Kata sandi sementara ini hanya ditampilkan sekali - serahkan secara
              aman dan minta pengguna menggantinya setelah login.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 rounded-lg border border-border bg-secondary px-4 py-3 font-mono text-[13px]">
            <p data-testid="tenant-credential-email">{credential?.email}</p>
            <p data-testid="tenant-credential-password">{credential?.password}</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={copyCredential} data-testid="tenant-credential-copy">
              <Copy className="mr-1.5 h-4 w-4" /> Salin
            </Button>
            <Button onClick={() => setCredential(null)} data-testid="tenant-credential-close">
              Sudah disimpan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(open) => !open && setConfirm(null)}
        title={confirmCopy.title}
        description={confirmCopy.description}
        confirmLabel={confirmCopy.confirmLabel}
        destructive={confirmCopy.destructive}
        loading={confirmLoading}
        onConfirm={runConfirm}
      />
    </>
  );
};

export default TenantsPage;
