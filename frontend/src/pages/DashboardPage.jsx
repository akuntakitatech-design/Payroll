import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Circle,
  FileWarning,
  History,
  Info,
  Inbox,
  Lock,
  RefreshCw,
} from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate, formatDateTime, daysUntil } from "@/lib/format";
import { MODULE_INFO } from "@/lib/nav";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import { MetaLine } from "@/components/common/StatusBadge";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";

// Warna status terkendali: hanya untuk menandai tingkat urgensi, bukan dekorasi.
const SEVERITY = {
  critical: { icon: AlertTriangle, label: "Segera", cls: "border-danger-border bg-danger-soft text-danger" },
  warning: { icon: FileWarning, label: "Perlu dicek", cls: "border-warning-border bg-warning-soft text-warning" },
  info: { icon: Info, label: "Informasi", cls: "border-info-border bg-info-soft text-info" },
};

const StatTile = ({ label, value, hint }) => (
  <div className="rounded-lg border border-border bg-card px-4 py-3">
    <p className="text-[12px] text-muted-foreground">{label}</p>
    <p className="mt-0.5 text-xl font-semibold leading-tight" data-numeric="true">
      {value}
    </p>
    {hint && <p className="mt-0.5 text-[12px] text-muted-foreground">{hint}</p>}
  </div>
);

const PanelHeader = ({ title, description, aside }) => (
  <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
    <div className="min-w-0">
      <h2 className="text-section-title">{title}</h2>
      {description && <p className="mt-0.5 text-[13px] text-muted-foreground">{description}</p>}
    </div>
    {aside}
  </div>
);

const DashboardPage = () => {
  const { user, company, can } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.get("/dashboard/summary");
      setData(res.data);
    } catch (err) {
      setError(errorMessage(err, "Ringkasan belum dapat ditampilkan. Coba muat ulang halaman."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    document.title = "Dashboard · HRIS & Payroll Suite";
  }, [load, company?.id]);

  const hour = new Date().getHours();
  const greeting = hour < 11 ? "Selamat pagi" : hour < 15 ? "Selamat siang" : hour < 18 ? "Selamat sore" : "Selamat malam";

  return (
    <>
      <PageHeader
        title={`${greeting}, ${user?.full_name?.split(" ")[0] || "Pengguna"}`}
        subtitle={
          company
            ? `${company.name} · ${company.city || "-"}`
            : "Pilih perusahaan untuk mulai bekerja."
        }
        actions={
          <Button variant="outline" onClick={load} disabled={loading} data-testid="dashboard-refresh">
            <RefreshCw className={`mr-1.5 h-4 w-4 ${loading ? "animate-spin" : ""}`} /> Muat ulang
          </Button>
        }
      />

      <PageBody>
        {error && (
          <div className="rounded-md border border-danger-border bg-danger-soft px-4 py-3 text-[13px] text-danger">
            {error}
          </div>
        )}

        {loading ? (
          <div className="grid gap-4 lg:grid-cols-12">
            <div className="space-y-4 lg:col-span-8">
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-56 w-full" />
            </div>
            <div className="space-y-4 lg:col-span-4">
              <Skeleton className="h-64 w-full" />
            </div>
          </div>
        ) : (
          data && (
            <>
              {/* Fokus utama: hal yang perlu ditindaklanjuti hari ini */}
              <Card className="overflow-hidden">
                <PanelHeader
                  title="Perlu Ditindaklanjuti"
                  description="Kondisi normal ditangani sistem. Di sini hanya hal yang butuh keputusan Anda."
                  aside={
                    <span
                      className="shrink-0 text-[13px] text-muted-foreground"
                      data-numeric="true"
                      data-testid="dashboard-attention-count"
                    >
                      {data.attention.length} item
                    </span>
                  }
                />
                <div className="divide-y divide-border" data-testid="dashboard-needs-attention-list">
                  {data.attention.length === 0 ? (
                    <div className="flex items-start gap-3 px-4 py-6">
                      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                      <div>
                        <p className="text-sm font-medium">Tidak ada yang perlu ditindaklanjuti.</p>
                        <p className="text-[13px] text-muted-foreground">
                          Konfigurasi dasar sudah lengkap. Sistem akan memberi tahu bila ada pengecualian.
                        </p>
                      </div>
                    </div>
                  ) : (
                    data.attention.map((item) => {
                      const conf = SEVERITY[item.severity] || SEVERITY.info;
                      const Icon = conf.icon;
                      return (
                        <button
                          type="button"
                          key={item.key}
                          data-testid={`dashboard-needs-attention-item-${item.key}`}
                          onClick={() => navigate(item.action_link.split("?")[0])}
                          className="flex w-full flex-col items-start gap-2 px-4 py-3 text-left transition-colors duration-150 hover:bg-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring sm:flex-row sm:items-start sm:gap-3"
                        >
                          <Icon className="mt-0.5 hidden h-4 w-4 shrink-0 text-muted-foreground sm:block" strokeWidth={1.75} />
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <Icon className="h-4 w-4 shrink-0 text-muted-foreground sm:hidden" strokeWidth={1.75} />
                              <p className="text-sm font-medium">{item.title}</p>
                              <span
                                className={`rounded-full border px-2 py-0.5 text-[11px] font-medium leading-5 ${conf.cls}`}
                              >
                                {conf.label}
                              </span>
                            </div>
                            <p className="mt-0.5 text-[13px] text-muted-foreground">{item.description}</p>
                          </div>
                          <span
                            className="flex shrink-0 items-center gap-1 text-[13px] font-medium text-primary sm:mt-0.5"
                            data-testid={`dashboard-needs-attention-item-action-${item.key}`}
                          >
                            {item.action_label} <ArrowRight className="h-3.5 w-3.5" />
                          </span>
                        </button>
                      );
                    })
                  )}
                </div>
              </Card>

              {/* Angka pendukung \u2014 netral, tidak dominan */}
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <StatTile label="Pengguna aktif" value={data.counts.users} hint="Pada perusahaan ini" />
                <StatTile
                  label="Unit organisasi"
                  value={data.counts.departments + data.counts.divisions}
                  hint={`${data.counts.departments} departemen · ${data.counts.divisions} divisi`}
                />
                <StatTile label="Proyek aktif" value={data.counts.projects} hint="Siap dipakai penempatan" />
                <StatTile
                  label="Modul aktif"
                  value={`${data.counts.active_modules}/${data.counts.available_modules}`}
                  hint="Langganan modul perusahaan"
                />
              </div>

              <div className="grid gap-4 lg:grid-cols-12">
                <div className="space-y-4 lg:col-span-8">
                  <div className="grid gap-4 md:grid-cols-2">
                    <Card className="overflow-hidden" data-testid="dashboard-pending-approvals">
                      <PanelHeader title="Menunggu Persetujuan Anda" />
                      <div className="px-4 py-3">
                        <p className="text-xl font-semibold leading-tight" data-numeric="true">
                          {data.pending_approvals.count}
                        </p>
                        <p className="mt-1 text-[13px] text-muted-foreground">{data.pending_approvals.note}</p>
                        <Button asChild variant="outline" size="sm" className="mt-3">
                          <Link to="/setup/approval-workflows">Atur alur persetujuan</Link>
                        </Button>
                      </div>
                    </Card>

                    <Card className="overflow-hidden" data-testid="dashboard-expiring-documents">
                      <PanelHeader title="Dokumen Menjelang Berakhir" />
                      <div className="px-4 py-3">
                        {data.expiring_documents.length === 0 ? (
                          <p className="text-[13px] text-muted-foreground">
                            Tidak ada dokumen yang mendekati masa berakhir dalam {data.horizon_days} hari.
                          </p>
                        ) : (
                          <ul className="divide-y divide-border">
                            {data.expiring_documents.map((doc) => {
                              const d = daysUntil(doc.expiry_date);
                              return (
                                <li key={doc.id} className="flex items-center justify-between gap-3 py-2 first:pt-0">
                                  <span className="min-w-0">
                                    <span className="block truncate text-[13px] font-medium">{doc.name}</span>
                                    <MetaLine items={[doc.owner_label || "Perusahaan", formatDate(doc.expiry_date)]} />
                                  </span>
                                  <span
                                    className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium leading-5 ${
                                      d < 0
                                        ? "border-danger-border bg-danger-soft text-danger"
                                        : "border-warning-border bg-warning-soft text-warning"
                                    }`}
                                    data-numeric="true"
                                  >
                                    {d < 0 ? `Lewat ${Math.abs(d)} hari` : `${d} hari`}
                                  </span>
                                </li>
                              );
                            })}
                          </ul>
                        )}
                        <Button asChild variant="outline" size="sm" className="mt-3">
                          <Link to="/documents">Buka arsip dokumen</Link>
                        </Button>
                      </div>
                    </Card>
                  </div>

                  <Card className="overflow-hidden" data-testid="dashboard-module-tiles">
                    <PanelHeader
                      title="Modul HR"
                      description="Modul yang belum aktif dapat diaktifkan pada halaman Aktivasi Modul."
                    />
                    <div className="divide-y divide-border">
                      {data.module_cards.map((mod) => {
                        const info = MODULE_INFO[mod.key];
                        const Icon = info?.icon || Lock;
                        return (
                          <div
                            key={mod.key}
                            data-testid={`dashboard-module-tile-${mod.key}`}
                            className="flex items-start gap-3 px-4 py-3"
                          >
                            <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} />
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <p className="text-[13px] font-medium">{mod.name}</p>
                                <span className="text-[12px] text-muted-foreground">
                                  {mod.state === "available" ? "Siap dipakai" : mod.is_active ? "Aktif" : "Belum aktif"}
                                </span>
                              </div>
                              <p className="mt-0.5 text-[13px] text-muted-foreground">{mod.description}</p>
                            </div>
                            {mod.is_active ? (
                              <Button asChild variant="ghost" size="sm" className="shrink-0 text-primary">
                                <Link to={mod.link || `/modules/${mod.key}`}>
                                  {mod.action_label || "Lihat rencana modul"}
                                </Link>
                              </Button>
                            ) : (
                              <span className="shrink-0 text-[12px] text-muted-foreground">Nonaktif</span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </Card>
                </div>

                <div className="space-y-4 lg:col-span-4">
                  <Card className="overflow-hidden" data-testid="dashboard-setup-progress-card">
                    <PanelHeader
                      title="Kelengkapan Setup"
                      aside={
                        <span className="shrink-0 text-[13px] font-semibold text-primary" data-numeric="true">
                          {data.setup_progress.percent}%
                        </span>
                      }
                    />
                    <div className="px-4 py-3">
                      <Progress
                        value={data.setup_progress.percent}
                        className="h-1.5"
                        data-testid="dashboard-setup-progress-bar"
                      />
                      <p className="mt-2 text-[12px] text-muted-foreground" data-numeric="true">
                        {data.setup_progress.done} dari {data.setup_progress.total} langkah selesai
                      </p>
                      <ul className="mt-2 space-y-0.5">
                        {data.setup_progress.steps.map((step) => (
                          <li key={step.key}>
                            <Link
                              to={step.link}
                              data-testid={`setup-step-${step.key}`}
                              className="flex items-center gap-2 rounded-md px-2 py-1.5 text-[13px] transition-colors duration-150 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            >
                              {step.done ? (
                                <CheckCircle2 className="h-4 w-4 shrink-0 text-success" />
                              ) : (
                                <Circle className="h-4 w-4 shrink-0 text-muted-foreground" />
                              )}
                              <span className={step.done ? "text-muted-foreground" : "font-medium"}>
                                {step.label}
                              </span>
                            </Link>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </Card>

                  {data.ending_projects.length > 0 && (
                    <Card className="overflow-hidden" data-testid="dashboard-ending-projects">
                      <PanelHeader title="Proyek Berakhir Segera" />
                      <ul className="divide-y divide-border px-4">
                        {data.ending_projects.map((p) => (
                          <li key={p.id} className="flex items-center justify-between gap-3 py-2">
                            <span className="min-w-0">
                              <span className="block truncate text-[13px] font-medium">{p.name}</span>
                              <MetaLine items={[p.code]} />
                            </span>
                            <span className="shrink-0 text-[12px] text-muted-foreground" data-numeric="true">
                              {formatDate(p.end_date)}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </Card>
                  )}

                  {can("audit_log", "view") && (
                    <Card className="overflow-hidden" data-testid="dashboard-audit-feed-card">
                      <PanelHeader
                        title="Aktivitas Terbaru"
                        aside={
                          <Button asChild variant="ghost" size="sm" className="h-7 shrink-0 px-2 text-[12px]">
                            <Link to="/audit-logs">
                              <History className="mr-1 h-3.5 w-3.5" /> Semua
                            </Link>
                          </Button>
                        }
                      />
                      <div className="px-4 py-3">
                        {data.recent_activity.length === 0 ? (
                          <p className="text-[13px] text-muted-foreground">Belum ada aktivitas tercatat.</p>
                        ) : (
                          <ul className="space-y-2.5">
                            {data.recent_activity.map((log) => (
                              <li key={log.id} className="border-l-2 border-border pl-3">
                                <p className="text-[13px]">
                                  <span className="font-medium">{log.user_name || log.user_email}</span>{" "}
                                  <span className="text-muted-foreground">{log.action}</span>{" "}
                                  <span className="font-medium">{log.record_label || log.resource}</span>
                                </p>
                                <p className="text-[12px] text-muted-foreground" data-numeric="true">
                                  {formatDateTime(log.created_at)}
                                </p>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    </Card>
                  )}

                  {data.attention.length === 0 && (
                    <div
                      className="flex items-start gap-3 rounded-lg border border-dashed border-border bg-muted/40 px-4 py-3"
                      data-testid="dashboard-inbox-hint"
                    >
                      <Inbox className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} />
                      <p className="text-[13px] text-muted-foreground">
                        Tidak ada pengecualian yang tertunda. Sistem akan menampilkan daftar tindakan begitu ada
                        kontrak, sertifikasi, atau pengajuan yang perlu diperiksa.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </>
          )
        )}
      </PageBody>
    </>
  );
};

export default DashboardPage;
