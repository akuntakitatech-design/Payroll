import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  CalendarClock,
  History,
  Plus,
  RefreshCw,
  ShieldAlert,
  UserX,
  UsersRound,
} from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { brandTitle, useBranding } from "@/lib/branding";
import { useAuth } from "@/lib/auth";
import { formatDate, formatDateTime } from "@/lib/format";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import StatusBadge from "@/components/common/StatusBadge";
import EmptyState from "@/components/common/EmptyState";
import { SubscriptionBadge, subscriptionHint } from "@/components/common/SubscriptionBadge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

const ACTION_LABELS = {
  create: "Membuat",
  update: "Memperbarui",
  update_subscription: "Mengubah masa layanan",
  activate: "Mengaktifkan",
  deactivate: "Menonaktifkan",
  assign_tenant_admin: "Menunjuk Tenant Admin",
  revoke_tenant_admin: "Mencabut Tenant Admin",
  assign_role: "Menambah user",
  upload: "Mengunggah",
  replace: "Mengganti",
  delete: "Menghapus",
};

const Kpi = ({ label, value, hint, tone = "default", testId, icon: Icon }) => (
  <Card className="border-border bg-card p-4 shadow-xs" data-testid={testId}>
    <div className="flex items-start justify-between gap-2">
      <p className="text-[13px] font-medium text-muted-foreground">{label}</p>
      {Icon && (
        <span
          className={
            tone === "danger"
              ? "text-danger"
              : tone === "warning"
                ? "text-warning"
                : "text-primary"
          }
        >
          <Icon className="h-4 w-4" />
        </span>
      )}
    </div>
    <p className="mt-2 text-[28px] font-semibold leading-none tracking-[-0.02em] tabular-nums" data-numeric="true" data-testid={`${testId}-value`}>
      {value}
    </p>
    {hint && <p className="mt-1.5 text-xs text-muted-foreground">{hint}</p>}
  </Card>
);

const TenantRow = ({ t, onOpen, testPrefix }) => (
  <button
    type="button"
    onClick={() => onOpen(t)}
    className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors duration-150 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    data-testid={`${testPrefix}-${t.code}`}
  >
    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border bg-secondary text-[10px] font-bold text-secondary-foreground">
      {(t.code || "").slice(0, 4)}
    </span>
    <span className="min-w-0 flex-1">
      <span className="block truncate text-sm font-medium text-ink-1">{t.name}</span>
      <span className="block truncate text-xs text-muted-foreground">{subscriptionHint(t.subscription)}</span>
    </span>
    <span className="flex shrink-0 flex-col items-end gap-1">
      <SubscriptionBadge subscription={t.subscription} testId={`${testPrefix}-badge-${t.code}`} />
      {t.status !== "active" && <StatusBadge status="inactive" label="Nonaktif" />}
    </span>
  </button>
);

const PlatformDashboardPage = () => {
  const { branding } = useBranding();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    document.title = brandTitle(branding, "Platform Dashboard");
  }, [branding]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.get("/platform/dashboard");
      setData(res.data);
    } catch (err) {
      setError(errorMessage(err, "Ringkasan platform belum dapat dimuat."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openTenant = (t) => navigate(`/platform/tenants/${t.id}`);
  const tot = data?.totals || {};

  return (
    <>
      <PageHeader
        title="Platform Dashboard"
        subtitle={`Ringkasan seluruh tenant ${branding.app_name} — status operasional, masa layanan, dan aktivitas terbaru.`}
        actions={
          <>
            <Button variant="outline" onClick={load} disabled={loading} data-testid="platform-dashboard-refresh">
              <RefreshCw className={`mr-1.5 h-4 w-4 ${loading ? "animate-spin" : ""}`} /> Muat ulang
            </Button>
            <Button asChild data-testid="platform-dashboard-add-tenant">
              <Link to="/platform/tenants?new=1">
                <Plus className="mr-1.5 h-4 w-4" /> Tambah Tenant
              </Link>
            </Button>
          </>
        }
      />
      <PageBody>
        <p className="text-[18px] font-semibold tracking-[-0.01em] text-ink-1" data-testid="platform-dashboard-greeting">
          Halo, {user?.full_name?.split(" ")[0] || "Admin"}. Berikut kondisi tenant hari ini.
        </p>

        {error && (
          <Card className="flex flex-wrap items-center justify-between gap-3 border-danger-border bg-danger-soft p-4" data-testid="platform-dashboard-error">
            <span className="flex items-center gap-2 text-sm text-destructive">
              <AlertTriangle className="h-4 w-4" /> {error}
            </span>
            <Button size="sm" variant="outline" onClick={load}>Coba lagi</Button>
          </Card>
        )}

        {loading && !data ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-[104px] rounded-xl" />
            ))}
          </div>
        ) : (
          data && (
            <>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" data-testid="platform-kpis">
                <Kpi label="Total tenant" value={tot.tenants} icon={Building2} testId="kpi-total-tenants"
                  hint={`${tot.operational_active} aktif · ${tot.operational_inactive} nonaktif`} />
                <Kpi label="Masa layanan aktif" value={tot.subscription_active} icon={CalendarClock} testId="kpi-subscription-active"
                  hint={`${tot.subscription_unlimited} tenant legacy (belum diatur)`} />
                <Kpi label="Masa tenggang" value={tot.subscription_grace} icon={AlertTriangle} tone="warning" testId="kpi-subscription-grace"
                  hint="Tetap beroperasi dengan peringatan" />
                <Kpi label="Layanan berakhir" value={tot.subscription_expired} icon={ShieldAlert} tone="danger" testId="kpi-subscription-expired"
                  hint="User tenant diblokir" />
                <Kpi label="Operasional nonaktif" value={tot.operational_inactive} icon={UserX} tone={tot.operational_inactive ? "danger" : "default"} testId="kpi-inactive"
                  hint="Dinonaktifkan Platform Admin" />
                <Kpi label="User tenant" value={tot.tenant_users} icon={UsersRound} testId="kpi-tenant-users" hint="Akun aktif di seluruh tenant" />
                <Kpi label="Karyawan" value={tot.employees} icon={UsersRound} testId="kpi-employees" hint="Total karyawan seluruh tenant" />
                <Kpi label="Tenant tanpa admin" value={tot.tenants_without_admin} icon={ShieldAlert} tone={tot.tenants_without_admin ? "warning" : "default"} testId="kpi-no-admin"
                  hint="Perlu ditunjuk Tenant Admin" />
              </div>

              <div className="grid gap-4 xl:grid-cols-12">
                <Card className="border-border bg-card p-4 xl:col-span-5" data-testid="platform-attention-card">
                  <div className="mb-2 flex items-center justify-between">
                    <h2 className="text-section-title">Perlu ditindaklanjuti</h2>
                    <span className="text-xs text-muted-foreground">Tenggang, berakhir, atau nonaktif</span>
                  </div>
                  {data.needs_attention.length ? (
                    <div className="space-y-0.5">
                      {data.needs_attention.map((t) => <TenantRow key={t.id} t={t} onOpen={openTenant} testPrefix="attention" />)}
                    </div>
                  ) : (
                    <EmptyState icon={ShieldAlert} title="Semua tenant dalam kondisi baik." description="Tidak ada tenant yang berada di masa tenggang, berakhir, atau nonaktif." />
                  )}
                  <div className="mt-4 border-t border-border pt-3">
                    <div className="mb-2 flex items-center justify-between">
                      <h3 className="text-sm font-semibold">Berakhir dalam 30 hari</h3>
                      <span className="text-xs text-muted-foreground">Pengingat H-30 / H-14 / H-7 / H-1</span>
                    </div>
                    {data.expiring_soon.length ? (
                      data.expiring_soon.map((t) => <TenantRow key={t.id} t={t} onOpen={openTenant} testPrefix="expiring" />)
                    ) : (
                      <p className="text-[13px] text-muted-foreground" data-testid="expiring-empty">Tidak ada masa layanan yang berakhir dalam 30 hari.</p>
                    )}
                  </div>
                </Card>

                <Card className="border-border bg-card p-4 xl:col-span-4" data-testid="platform-activity-card">
                  <div className="mb-2 flex items-center justify-between">
                    <h2 className="text-section-title">Aktivitas platform terbaru</h2>
                    <History className="h-4 w-4 text-muted-foreground" />
                  </div>
                  {data.recent_activities.length ? (
                    <ol className="space-y-3">
                      {data.recent_activities.map((a) => (
                        <li key={a.id} className="border-l-2 border-primary-border pl-3" data-testid="platform-activity-item">
                          <p className="text-[13px] text-ink-1">
                            <span className="font-semibold">{a.user_name || "Sistem"}</span>{" "}
                            {(ACTION_LABELS[a.action] || a.action).toLowerCase()}{" "}
                            {a.resource === "platform_branding" ? (a.record_label || "branding platform") : `tenant ${a.tenant_name || a.record_label || ""}`}
                          </p>
                          <p className="text-xs text-muted-foreground">{formatDateTime(a.created_at)}{a.notes ? ` · ${a.notes}` : ""}</p>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <EmptyState icon={History} title="Belum ada aktivitas." description="Aktivitas pengelolaan tenant dan branding akan tampil di sini." />
                  )}
                </Card>

                <Card className="border-border bg-card p-4 xl:col-span-3" data-testid="platform-recent-tenants-card">
                  <div className="mb-2 flex items-center justify-between">
                    <h2 className="text-section-title">Tenant terbaru</h2>
                    <Link to="/platform/tenants" className="flex items-center gap-1 text-xs font-medium text-primary hover:underline" data-testid="platform-view-all-tenants">
                      Semua <ArrowRight className="h-3 w-3" />
                    </Link>
                  </div>
                  <div className="space-y-0.5">
                    {data.recent_tenants.map((t) => (
                      <button
                        key={t.id}
                        type="button"
                        onClick={() => openTenant(t)}
                        className="flex w-full items-center justify-between gap-2 rounded-lg px-2 py-2 text-left transition-colors duration-150 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        data-testid={`recent-tenant-${t.code}`}
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-medium">{t.name}</span>
                          <span className="block text-xs text-muted-foreground">{t.code} · {t.created_at ? formatDate(t.created_at) : "-"}</span>
                        </span>
                        <ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      </button>
                    ))}
                  </div>
                </Card>
              </div>
            </>
          )
        )}
      </PageBody>
    </>
  );
};

export default PlatformDashboardPage;
