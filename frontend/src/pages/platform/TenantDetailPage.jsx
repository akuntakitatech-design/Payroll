import React, { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  CalendarPlus,
  Copy,
  History,
  KeyRound,
  Lock,
  Pencil,
  Power,
  RotateCcw,
  UserMinus,
  UserPlus,
  UsersRound,
} from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { brandTitle, useBranding } from "@/lib/branding";
import { formatDate, formatDateTime } from "@/lib/format";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import FormDialog from "@/components/common/FormDialog";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import StatusBadge from "@/components/common/StatusBadge";
import EmptyState from "@/components/common/EmptyState";
import { SubscriptionBadge, subscriptionHint } from "@/components/common/SubscriptionBadge";
import { TenantLogo } from "@/components/common/TenantLogo";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EDIT_FIELDS, subscriptionPayload, subscriptionValues } from "./TenantsPage";

const ACTION_LABELS = {
  create: "Membuat",
  update: "Memperbarui",
  update_subscription: "Mengubah masa layanan",
  activate: "Mengaktifkan tenant",
  deactivate: "Menonaktifkan tenant",
  assign_tenant_admin: "Menunjuk Tenant Admin",
  revoke_tenant_admin: "Mencabut Tenant Admin",
  assign_role: "Menambah user ke tenant",
  upload_logo: "Mengunggah logo",
  replace_logo: "Mengganti logo",
  delete_logo: "Menghapus logo",
  login: "Login",
  login_failed: "Login gagal",
  login_blocked: "Login diblokir",
  logout: "Logout",
};

const RENEW_FIELDS = [
  { name: "subscription_start_date", label: "Tanggal Mulai Layanan", type: "date" },
  { name: "subscription_end_date", label: "Tanggal Berakhir Layanan (baru)", type: "date", required: true },
  { name: "grace_period_days", label: "Grace Period (hari)", type: "number", required: true },
  { name: "subscription_notes", label: "Catatan Perpanjangan", type: "textarea", rows: 2, hint: "Opsional, mis. nomor kontrak." },
];

const addMonths = (iso, months) => {
  const base = iso ? new Date(`${iso}T00:00:00`) : new Date();
  const d = new Date(base);
  d.setMonth(d.getMonth() + months);
  return d.toISOString().slice(0, 10);
};

const InfoRow = ({ label, value, testId }) => (
  <div className="flex items-start justify-between gap-3 py-2 text-sm">
    <span className="text-muted-foreground">{label}</span>
    <span className="max-w-[62%] break-words text-right font-medium text-ink-1" data-testid={testId}>{value ?? "-"}</span>
  </div>
);

const TenantDetailPage = () => {
  const { tenantId } = useParams();
  const { branding } = useBranding();
  const [tenant, setTenant] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [users, setUsers] = useState(null);
  const [activities, setActivities] = useState(null);
  const [roles, setRoles] = useState([]);
  const [tab, setTab] = useState("summary");

  const [editOpen, setEditOpen] = useState(false);
  const [renewOpen, setRenewOpen] = useState(false);
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [userOpen, setUserOpen] = useState(false);
  const [userValues, setUserValues] = useState({ email: "", full_name: "", role_key: "tenant_admin" });
  const [userErrors, setUserErrors] = useState({});
  const [credential, setCredential] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const { data } = await api.get(`/platform/tenants/${tenantId}`);
      setTenant(data);
    } catch (err) {
      setLoadError(errorMessage(err, "Tenant tidak dapat dimuat."));
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  const loadUsers = useCallback(async () => {
    try {
      const { data } = await api.get(`/platform/tenants/${tenantId}/users`);
      setUsers(data.items || []);
    } catch (err) {
      toast.error(errorMessage(err, "Daftar user tidak dapat dimuat."));
      setUsers([]);
    }
  }, [tenantId]);

  const loadActivities = useCallback(async () => {
    try {
      const { data } = await api.get(`/platform/tenants/${tenantId}/activities`, { params: { limit: 100 } });
      setActivities(data.items || []);
    } catch (err) {
      toast.error(errorMessage(err, "Aktivitas tidak dapat dimuat."));
      setActivities([]);
    }
  }, [tenantId]);

  useEffect(() => {
    load();
    loadUsers();
    loadActivities();
    api.get("/platform/tenant-roles").then(({ data }) => setRoles(data.items || [])).catch(() => setRoles([]));
  }, [load, loadUsers, loadActivities]);

  useEffect(() => {
    document.title = brandTitle(branding, tenant ? `Tenant ${tenant.code}` : "Detail Tenant");
  }, [branding, tenant]);

  const refreshAll = () => {
    load();
    loadUsers();
    loadActivities();
  };

  const openEdit = () => {
    setValues({
      name: tenant.name || "",
      legal_name: tenant.legal_name || "",
      pic_name: tenant.pic_name || "",
      pic_phone: tenant.pic_phone || "",
      email: tenant.email || "",
      status: tenant.status === "active" ? "active" : "inactive",
      ...subscriptionValues(tenant),
    });
    setErrors({});
    setEditOpen(true);
  };

  const openRenew = () => {
    const sub = tenant.subscription || {};
    setValues({
      ...subscriptionValues(tenant),
      subscription_end_date: addMonths(sub.end_date && sub.status !== "expired" ? sub.end_date : null, 12),
      grace_period_days: sub.grace_period_days ?? 7,
    });
    setErrors({});
    setRenewOpen(true);
  };

  const onChange = (name, value) => {
    setValues((p) => ({ ...p, [name]: value }));
    setErrors((p) => ({ ...p, [name]: undefined, __form__: undefined }));
  };

  const saveEdit = async () => {
    const e = {};
    if (String(values.name || "").trim().length < 2) e.name = "Nama tenant minimal 2 karakter.";
    if (String(values.pic_name || "").trim().length < 2) e.pic_name = "Nama PIC wajib diisi.";
    if (!/^[0-9+()\-\s]{6,20}$/.test(String(values.pic_phone || "").trim())) e.pic_phone = "Nomor HP 6-20 digit.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(values.email || "").trim())) e.email = "Email utama tidak valid.";
    if (values.subscription_start_date && values.subscription_end_date && values.subscription_end_date < values.subscription_start_date)
      e.subscription_end_date = "Tanggal berakhir tidak boleh lebih awal dari tanggal mulai.";
    if (Object.keys(e).length) return setErrors(e);
    setSubmitting(true);
    try {
      await api.put(`/platform/tenants/${tenantId}`, {
        name: values.name.trim(),
        legal_name: values.legal_name?.trim() || null,
        pic_name: values.pic_name.trim(),
        pic_phone: values.pic_phone.trim(),
        email: values.email.trim().toLowerCase(),
        status: values.status,
        ...subscriptionPayload(values),
      });
      toast.success("Informasi tenant diperbarui. Kode tenant tetap tidak berubah.");
      setEditOpen(false);
      refreshAll();
    } catch (err) {
      setErrors({ __form__: errorMessage(err, "Tenant tidak dapat disimpan.") });
    } finally {
      setSubmitting(false);
    }
  };

  const saveRenew = async () => {
    const e = {};
    if (!values.subscription_end_date) e.subscription_end_date = "Tanggal berakhir wajib diisi.";
    if (values.subscription_start_date && values.subscription_end_date && values.subscription_end_date < values.subscription_start_date)
      e.subscription_end_date = "Tanggal berakhir tidak boleh lebih awal dari tanggal mulai.";
    const g = values.grace_period_days;
    if (g === "" || g === null || !Number.isInteger(Number(g)) || Number(g) < 0) e.grace_period_days = "Grace period bilangan bulat ≥ 0.";
    if (Object.keys(e).length) return setErrors(e);
    setSubmitting(true);
    try {
      const { data } = await api.put(`/platform/tenants/${tenantId}`, subscriptionPayload(values));
      toast.success(`Masa layanan diperbarui: ${data.subscription?.status_label || "Aktif"} hingga ${formatDate(data.subscription?.end_date)}.`);
      setRenewOpen(false);
      refreshAll();
    } catch (err) {
      setErrors({ __form__: errorMessage(err, "Masa layanan tidak dapat diperbarui.") });
    } finally {
      setSubmitting(false);
    }
  };

  const saveUser = async () => {
    const email = String(userValues.email || "").trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return setUserErrors({ email: "Masukkan email yang valid." });
    if (!userValues.role_key) return setUserErrors({ role_key: "Pilih peran." });
    setSubmitting(true);
    try {
      const { data } = await api.post(`/platform/tenants/${tenantId}/users`, {
        email,
        full_name: userValues.full_name?.trim() || null,
        role_key: userValues.role_key,
      });
      toast.success(data.message);
      if (data.temporary_password) setCredential({ email: data.user.email, password: data.temporary_password });
      setUserOpen(false);
      refreshAll();
    } catch (err) {
      setUserErrors({ __form__: errorMessage(err, "User tidak dapat ditambahkan.") });
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
        ({ data } = await api.delete(`/platform/tenants/${tenantId}/admins/${confirm.user.id}`));
      } else if (confirm.type === "reset") {
        ({ data } = await api.post(`/platform/tenants/${tenantId}/users/${confirm.user.id}/reset-password`));
        // Password sementara hanya ada di state dialog; tidak disimpan di mana pun.
        setCredential({ email: data.user.email, password: data.temporary_password, reset: true });
      } else {
        ({ data } = await api.post(`/platform/tenants/${tenantId}/${confirm.type}`));
      }
      toast.success(data.message);
      refreshAll();
    } catch (err) {
      toast.error(errorMessage(err, "Tindakan tidak dapat dilakukan."));
    } finally {
      setConfirm(null);
      setConfirmLoading(false);
    }
  };

  const copyCredential = async () => {
    try {
      await navigator.clipboard.writeText(`Email: ${credential.email}\nPassword sementara: ${credential.password}`);
      toast.success("Kredensial disalin.");
    } catch {
      toast.error("Tidak dapat menyalin otomatis. Salin secara manual.");
    }
  };

  if (loading && !tenant) {
    return (
      <PageBody>
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-72 w-full rounded-xl" />
      </PageBody>
    );
  }
  if (loadError && !tenant) {
    return (
      <PageBody>
        <Card className="p-6" data-testid="tenant-detail-error">
          <EmptyState icon={Lock} title="Tenant tidak dapat dimuat" description={loadError} />
          <div className="mt-3 flex justify-center gap-2">
            <Button variant="outline" asChild><Link to="/platform/tenants">Kembali ke registry</Link></Button>
            <Button onClick={load}>Coba lagi</Button>
          </div>
        </Card>
      </PageBody>
    );
  }

  const sub = tenant.subscription || {};
  const blocked = tenant.status !== "active" || sub.status === "expired";
  const roleOptions = roles.map((r) => ({ value: r.key, label: r.name }));

  return (
    <>
      <PageHeader
        title={tenant.name}
        subtitle={`Detail tenant · kode ${tenant.code}`}
        actions={
          <>
            <Button variant="outline" asChild data-testid="tenant-detail-back">
              <Link to="/platform/tenants"><ArrowLeft className="mr-1.5 h-4 w-4" /> Registry</Link>
            </Button>
            <Button variant="outline" onClick={openEdit} data-testid="tenant-detail-edit">
              <Pencil className="mr-1.5 h-4 w-4" /> Ubah
            </Button>
            <Button onClick={openRenew} data-testid="tenant-detail-renew">
              <CalendarPlus className="mr-1.5 h-4 w-4" /> Perpanjang layanan
            </Button>
          </>
        }
      />
      <PageBody>
        <Card className="flex flex-col gap-4 border-border bg-card p-4 sm:flex-row sm:items-center" data-testid="tenant-detail-header">
          <TenantLogo source="platform" tenantId={tenant.id} hasLogo={tenant.has_logo} version={tenant.logo_version} name={tenant.name} size="lg" testId="tenant-detail-logo" />
          <div className="min-w-0 flex-1 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-section-title" data-testid="tenant-detail-name">{tenant.name}</p>
              <Badge variant="outline" className="font-mono" data-testid="tenant-detail-code">{tenant.code}</Badge>
              <span className="text-[11px] text-muted-foreground">kode permanen</span>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span data-testid="tenant-detail-status">
                <StatusBadge status={tenant.status} label={tenant.status === "active" ? "Operasional aktif" : "Operasional nonaktif"} />
              </span>
              <SubscriptionBadge subscription={sub} testId="tenant-detail-subscription-badge" />
              <span data-testid="tenant-detail-subscription-hint">{subscriptionHint(sub)}</span>
            </div>
            {blocked && (
              <p className="text-xs text-danger" data-testid="tenant-detail-blocked-note">
                User tenant saat ini tidak dapat login ({tenant.status !== "active" ? "tenant dinonaktifkan" : "masa layanan berakhir"}). Data tetap tersimpan.
              </p>
            )}
          </div>
          <div className="flex shrink-0 gap-2">
            {tenant.status === "active" ? (
              <Button variant="outline" className="text-destructive hover:text-destructive" onClick={() => setConfirm({ type: "deactivate" })} data-testid="tenant-detail-deactivate">
                <Power className="mr-1.5 h-4 w-4" /> Nonaktifkan
              </Button>
            ) : (
              <Button variant="outline" onClick={() => setConfirm({ type: "activate" })} data-testid="tenant-detail-activate">
                <RotateCcw className="mr-1.5 h-4 w-4" /> Aktifkan kembali
              </Button>
            )}
          </div>
        </Card>

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList data-testid="tenant-detail-tabs">
            <TabsTrigger value="summary" data-testid="tenant-tab-summary">Ringkasan</TabsTrigger>
            <TabsTrigger value="users" data-testid="tenant-tab-users">Users ({users?.length ?? tenant.user_count})</TabsTrigger>
            <TabsTrigger value="activity" data-testid="tenant-tab-activity">Aktivitas</TabsTrigger>
          </TabsList>

          <TabsContent value="summary" className="mt-4">
            <div className="grid gap-4 lg:grid-cols-3">
              <Card className="border-border bg-card p-4" data-testid="tenant-profile-card">
                <h2 className="text-section-title">Profil & PIC</h2>
                <div className="mt-2 divide-y divide-border">
                  <InfoRow label="Nama badan hukum" value={tenant.legal_name || "-"} />
                  <InfoRow label="Email utama" value={tenant.email || "-"} testId="tenant-detail-email" />
                  <InfoRow label="Nama PIC" value={tenant.pic_name || "-"} testId="tenant-detail-pic-name" />
                  <InfoRow label="No. HP PIC" value={tenant.pic_phone || "-"} testId="tenant-detail-pic-phone" />
                  <InfoRow label="Zona waktu" value={tenant.timezone || "-"} />
                  <InfoRow label="Dibuat" value={tenant.created_at ? formatDateTime(tenant.created_at) : "-"} />
                </div>
              </Card>
              <Card className="border-border bg-card p-4" data-testid="tenant-subscription-card">
                <div className="flex items-center justify-between">
                  <h2 className="text-section-title">Masa layanan</h2>
                  <SubscriptionBadge subscription={sub} testId="tenant-subscription-card-badge" />
                </div>
                <div className="mt-2 divide-y divide-border">
                  <InfoRow label="Mulai" value={sub.start_date ? formatDate(sub.start_date) : "-"} testId="tenant-detail-sub-start" />
                  <InfoRow label="Berakhir" value={sub.end_date ? formatDate(sub.end_date) : "Tanpa batas (legacy)"} testId="tenant-detail-sub-end" />
                  <InfoRow label="Grace period" value={sub.grace_period_days != null ? `${sub.grace_period_days} hari` : "-"} />
                  <InfoRow label="Akhir masa tenggang" value={sub.grace_end_date ? formatDate(sub.grace_end_date) : "-"} />
                  <InfoRow label="Sisa hari" value={sub.days_remaining != null ? (sub.days_remaining >= 0 ? `${sub.days_remaining} hari` : "Lewat") : "-"} testId="tenant-detail-sub-days" />
                  <InfoRow label="Pengingat" value={sub.reminder_stage || "-"} />
                  <InfoRow label="Catatan" value={sub.notes || "-"} />
                </div>
                <Button variant="outline" className="mt-3 w-full" onClick={openRenew} data-testid="tenant-subscription-renew">
                  <CalendarPlus className="mr-1.5 h-4 w-4" /> Atur / perpanjang masa layanan
                </Button>
              </Card>
              <Card className="border-border bg-card p-4" data-testid="tenant-stats-card">
                <h2 className="text-section-title">Statistik</h2>
                <div className="mt-2 divide-y divide-border">
                  <InfoRow label="User aktif" value={tenant.user_count} testId="tenant-detail-user-count" />
                  <InfoRow label="Karyawan" value={tenant.employee_count} testId="tenant-detail-employee-count" />
                  <InfoRow label="Tenant Admin" value={(tenant.tenant_admins || []).map((a) => a.full_name).join(", ") || "Belum ada"} testId="tenant-detail-admins" />
                </div>
                <p className="mt-3 rounded-lg border border-border bg-secondary px-3 py-2 text-xs text-secondary-foreground">
                  Status operasional dan masa layanan dikelola terpisah. Tenant tidak pernah dihapus permanen; menonaktifkan tenant tidak menghapus data.
                </p>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="users" className="mt-4">
            <Card className="border-border bg-card" data-testid="tenant-users-card">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3">
                <div>
                  <h2 className="text-section-title">User tenant</h2>
                  <p className="text-xs text-muted-foreground">User hanya terikat ke tenant ini; Tenant Admin tidak memiliki akses platform.</p>
                </div>
                <Button onClick={() => { setUserValues({ email: "", full_name: "", role_key: "tenant_admin" }); setUserErrors({}); setUserOpen(true); }} data-testid="tenant-users-add">
                  <UserPlus className="mr-1.5 h-4 w-4" /> Tambah user
                </Button>
              </div>
              {users === null ? (
                <div className="p-4"><Skeleton className="h-24 w-full" /></div>
              ) : users.length ? (
                <div className="table-scroll">
                  <Table data-testid="tenant-users-table">
                    <TableHeader>
                      <TableRow>
                        <TableHead>Nama</TableHead>
                        <TableHead>Peran</TableHead>
                        <TableHead>Login terakhir</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead className="w-24 text-right">Aksi</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {users.map((u) => (
                        <TableRow key={u.id} data-testid={`tenant-user-row-${u.email}`}>
                          <TableCell>
                            <p className="font-medium">{u.full_name}</p>
                            <p className="text-xs text-muted-foreground">{u.email}</p>
                          </TableCell>
                          <TableCell>
                            <div className="flex flex-wrap gap-1">
                              {u.role_names.map((r, i) => (
                                <Badge key={r} variant={u.role_keys[i] === "tenant_admin" ? "default" : "secondary"} className="font-medium">{r}</Badge>
                              ))}
                            </div>
                          </TableCell>
                          <TableCell className="whitespace-nowrap text-[13px]">
                            {u.last_login_at ? formatDateTime(u.last_login_at) : "Belum pernah"}
                            {u.must_change_password && <p className="text-xs text-warning">Password sementara</p>}
                          </TableCell>
                          <TableCell><StatusBadge status={u.status} /></TableCell>
                          <TableCell className="text-right">
                            <div className="flex items-center justify-end gap-1">
                            <Button variant="ghost" size="icon" className="h-8 w-8" title="Reset Password" aria-label={`Reset password ${u.full_name}`}
                              disabled={u.status !== "active"}
                              onClick={() => setConfirm({ type: "reset", user: u })} data-testid={`tenant-user-reset-password-${u.email}`}>
                              <KeyRound className="h-4 w-4" />
                            </Button>
                            {u.is_tenant_admin && (
                              <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" title="Cabut Tenant Admin"
                                onClick={() => setConfirm({ type: "revoke", user: u })} data-testid={`tenant-user-revoke-${u.email}`}>
                                <UserMinus className="h-4 w-4" />
                              </Button>
                            )}
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              ) : (
                <EmptyState icon={UsersRound} title="Belum ada user." description="Tambahkan Tenant Admin agar tenant dapat dikelola." />
              )}
            </Card>
          </TabsContent>

          <TabsContent value="activity" className="mt-4">
            <Card className="border-border bg-card p-4" data-testid="tenant-activity-card">
              <h2 className="text-section-title">Aktivitas & audit tenant</h2>
              <p className="text-xs text-muted-foreground">Diambil dari audit log tenant (100 aktivitas terbaru).</p>
              {activities === null ? (
                <Skeleton className="mt-3 h-40 w-full" />
              ) : activities.length ? (
                <ol className="mt-3 space-y-3">
                  {activities.map((a) => (
                    <li key={a.id} className="border-l-2 border-primary-border pl-3" data-testid="tenant-activity-item">
                      <p className="text-[13px] text-ink-1">
                        <span className="font-semibold">{a.user_name || a.user_email || "Sistem"}</span> — {ACTION_LABELS[a.action] || a.action}
                        {a.record_label ? ` · ${a.record_label}` : ""} <span className="text-muted-foreground">({a.resource})</span>
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {formatDateTime(a.created_at)}
                        {a.notes ? ` · ${a.notes}` : ""}
                        {a.changed_fields?.length ? ` · ${a.changed_fields.slice(0, 5).join(", ")}` : ""}
                      </p>
                    </li>
                  ))}
                </ol>
              ) : (
                <EmptyState icon={History} title="Belum ada aktivitas." description="Aktivitas penting tenant akan tercatat di sini." />
              )}
            </Card>
          </TabsContent>
        </Tabs>
      </PageBody>

      <FormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        title={`Ubah Tenant ${tenant.code}`}
        description="Kode tenant bersifat permanen dan tidak ikut berubah walau nama perusahaan diganti."
        fields={EDIT_FIELDS}
        values={values}
        errors={errors}
        onChange={onChange}
        onSubmit={saveEdit}
        submitting={submitting}
        submitLabel="Simpan"
      />
      <FormDialog
        open={renewOpen}
        onOpenChange={setRenewOpen}
        title={`Perpanjang masa layanan · ${tenant.name}`}
        description="Perpanjangan langsung memulihkan akses tenant yang berada di masa tenggang atau sudah berakhir. Status operasional tidak berubah."
        fields={RENEW_FIELDS}
        values={values}
        errors={errors}
        onChange={onChange}
        onSubmit={saveRenew}
        submitting={submitting}
        submitLabel="Simpan perpanjangan"
        extra={
          <div className="flex flex-wrap gap-2" data-testid="renew-quick-options">
            {[1, 3, 6, 12].map((m) => (
              <Button key={m} type="button" size="sm" variant="outline" data-testid={`renew-plus-${m}`}
                onClick={() => onChange("subscription_end_date", addMonths(sub.end_date && sub.status !== "expired" ? sub.end_date : null, m))}>
                +{m} bulan
              </Button>
            ))}
          </div>
        }
      />
      <FormDialog
        open={userOpen}
        onOpenChange={setUserOpen}
        title={`Tambah user · ${tenant.name}`}
        description="Email yang belum terdaftar akan dibuatkan akun dengan password sementara acak (ditampilkan sekali)."
        fields={[
          { name: "email", label: "Email", required: true, type: "email" },
          { name: "full_name", label: "Nama Lengkap", hint: "Wajib bila email belum terdaftar." },
          { name: "role_key", label: "Peran", type: "select", required: true, options: roleOptions },
        ]}
        values={userValues}
        errors={userErrors}
        onChange={(n, val) => { setUserValues((p) => ({ ...p, [n]: val })); setUserErrors((p) => ({ ...p, [n]: undefined, __form__: undefined })); }}
        onSubmit={saveUser}
        submitting={submitting}
        submitLabel="Tambahkan"
      />
      <Dialog open={!!credential} onOpenChange={(o) => !o && setCredential(null)}>
        <DialogContent className="bg-card sm:max-w-md" data-testid="tenant-credential-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base"><KeyRound className="h-4 w-4" /> {credential?.reset ? "Password berhasil direset" : "Kredensial akun baru"}</DialogTitle>
            <DialogDescription>
              Password sementara hanya ditampilkan sekali dan tidak dapat dilihat ulang setelah dialog ditutup. Serahkan secara aman; pengguna wajib menggantinya saat login berikutnya.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 rounded-lg border border-border bg-secondary px-4 py-3 font-mono text-[13px]">
            <p data-testid="tenant-credential-email">{credential?.email}</p>
            <p data-testid="tenant-credential-password">{credential?.password}</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={copyCredential} data-testid="tenant-credential-copy"><Copy className="mr-1.5 h-4 w-4" /> Salin</Button>
            <Button onClick={() => setCredential(null)} data-testid="tenant-credential-close">Sudah disimpan</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={
          confirm?.type === "deactivate"
            ? `Nonaktifkan ${tenant.name}?`
            : confirm?.type === "activate"
              ? `Aktifkan kembali ${tenant.name}?`
              : confirm?.type === "reset"
                ? `Reset password ${confirm?.user?.full_name}?`
                : `Cabut Tenant Admin ${confirm?.user?.full_name}?`
        }
        description={
          confirm?.type === "reset"
            ? "Password saat ini langsung tidak berlaku. Sistem membuat password sementara baru (ditampilkan sekali) dan pengguna wajib menggantinya saat login berikutnya."
            : confirm?.type === "deactivate"
            ? "User tenant tidak dapat login atau beroperasi. Data karyawan, payroll, dan histori TIDAK dihapus."
            : confirm?.type === "activate"
              ? "User tenant dapat login kembali (selama masa layanan belum berakhir). Seluruh data tetap utuh."
              : "Hanya peran Tenant Admin di tenant ini yang dicabut. Tenant wajib memiliki minimal satu Tenant Admin."
        }
        confirmLabel={
          confirm?.type === "activate" ? "Aktifkan" : confirm?.type === "deactivate" ? "Nonaktifkan" : confirm?.type === "reset" ? "Reset Password" : "Cabut"
        }
        destructive={confirm?.type !== "activate" && confirm?.type !== "reset"}
        loading={confirmLoading}
        onConfirm={runConfirm}
      />
    </>
  );
};

export default TenantDetailPage;
