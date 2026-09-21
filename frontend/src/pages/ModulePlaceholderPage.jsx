import React, { useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { ArrowRight, Layers, Lock, AlertCircle, RefreshCw } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { api, errorMessage } from "@/lib/api";
import { MODULE_INFO, NAV_GROUPS } from "@/lib/nav";
import { MODULE_FOUNDATIONS } from "@/lib/moduleFoundation";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

const navItems = NAV_GROUPS.flatMap((group) => group.items);

const ModulePlaceholderPage = () => {
  const { moduleKey } = useParams();
  const { can, hasModule, company } = useAuth();
  const info = MODULE_INFO[moduleKey];
  const foundation = MODULE_FOUNDATIONS[moduleKey];
  const nav = navItems.find((item) => item.module === moduleKey && !item.hidden);
  const resource = nav?.resource || (moduleKey === "employee_core" ? "employee" : moduleKey);
  const permitted = can(resource, "view");
  const [state, setState] = useState({ loading: true, active: false, error: "" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    document.title = `${info?.name || "Modul"} · HRIS Suite`;
    let current = true;
    setState({ loading: true, active: false, error: "" });
    if (!info || !permitted || moduleKey === "accounting") {
      setState({ loading: false, active: false, error: "" });
      return () => { current = false; };
    }
    api.get("/modules").then(({ data }) => {
      const mod = data.items.find((item) => item.key === moduleKey);
      if (current) setState({ loading: false, active: !!mod?.is_active, error: "" });
    }).catch((error) => {
      if (current) setState({ loading: false, active: false, error: errorMessage(error, "Status akses modul belum dapat dimuat.") });
    });
    return () => { current = false; };
  }, [moduleKey, company?.id, permitted, info, attempt]);

  const back = <Button asChild variant="outline" data-testid="module-back-dashboard"><Link to="/">Kembali ke ringkasan</Link></Button>;
  if (!info) return <PageBody><Card className="p-5 space-y-3" data-testid="module-not-found"><h1 className="text-section-title">Modul tidak dikenal</h1><p className="text-sm text-muted-foreground">Alamat modul ini tidak terdaftar.</p>{back}</Card></PageBody>;
  if (!permitted) return <PageBody><Card className="p-5 space-y-3" data-testid="module-access-denied"><Lock className="h-5 w-5 text-muted-foreground" /><h1 className="text-section-title">Akses tidak diizinkan</h1><p className="text-sm text-muted-foreground">Anda tidak memiliki hak akses untuk modul ini. Hubungi administrator perusahaan.</p>{back}</Card></PageBody>;
  if (moduleKey === "accounting") return <PageBody><Card className="p-5 space-y-3" data-testid="accounting-deferred"><Badge variant="outline">Ditunda</Badge><h1 className="text-section-title">Akuntansi belum dikerjakan</h1><p className="text-sm text-muted-foreground">Akuntansi tetap modul opsional terpisah. Payroll dan Permintaan Keuangan tidak bergantung pada aktivasi Akuntansi.</p>{back}</Card></PageBody>;
  if (state.loading) return <PageBody><Skeleton className="h-48 w-full" data-testid="module-loading" /></PageBody>;
  if (state.error) return <PageBody><Card className="p-5 space-y-3" role="alert" data-testid="module-error"><AlertCircle className="h-5 w-5 text-destructive" /><p className="text-sm">{state.error}</p><Button variant="outline" onClick={() => setAttempt((n) => n + 1)} data-testid="module-retry"><RefreshCw className="mr-2 h-4 w-4" />Coba lagi</Button></Card></PageBody>;
  if (!state.active) return <><PageHeader title={info.name} subtitle="Akses modul belum diaktifkan untuk perusahaan ini." /><PageBody><Card className="p-5 space-y-3" data-testid="module-inactive"><Lock className="h-5 w-5 text-muted-foreground" /><p className="text-sm">Data tidak dihapus ketika akses modul dinonaktifkan. Administrator dapat mengaturnya melalui Aktivasi Modul.</p>{can("module", "view") ? <Button asChild variant="outline" data-testid="placeholder-module-activation-cta"><Link to="/setup/modules">Lihat aktivasi modul</Link></Button> : back}</Card></PageBody></>;
  if (moduleKey === "employee_core") return <Navigate to="/employees" replace />;
  if (moduleKey === "payroll") return <Navigate to="/payroll/runs" replace />;
  const Icon = info.icon || Layers;
  const dependencies = (foundation?.dependencies || []).map((path) => navItems.find((item) => item.to === path && !item.hidden)).filter((item) => item && (!item.resource || can(item.resource, item.action || "view")) && hasModule(item.module));

  return <>
    <PageHeader title={info.name} subtitle={info.summary} actions={<Badge variant="secondary" className="h-7 px-2.5" data-testid="placeholder-module-status-badge">Akses aktif · Fondasi tersedia</Badge>} />
    <PageBody>
      <div className="rounded-lg border border-warning-border bg-warning-soft px-4 py-3 text-[13px] text-warning" data-testid="module-foundation-notice"><strong>Fitur operasional belum dibangun.</strong> Tahap ini menyiapkan struktur dan penggunaan kembali modul existing. Tidak ada data simulasi atau transaksi baru.</div>
      <div className="grid gap-4 lg:grid-cols-3" data-testid="placeholder-module-page">
        <Card className="border-border bg-card p-5 lg:col-span-2">
          <div className="flex items-center gap-2"><Icon className="h-4 w-4 text-primary" /><h2 className="text-section-title">Struktur proses</h2><Badge variant="outline" className="ml-auto text-[11px]">Tahap berikutnya</Badge></div>
          <p className="mt-3 rounded-md border border-border bg-secondary px-3 py-2 text-[12px] leading-relaxed" data-testid="module-process-flow">{foundation?.flow}</p>
          <div className="mt-3 divide-y divide-border" data-testid="module-workstreams">
            {(foundation?.sections || []).map(([title, description], index) => <div key={title} className="flex gap-3 py-3"><span className="pt-0.5 text-[11px] tabular-nums text-muted-foreground">{String(index + 1).padStart(2, "0")}</span><div className="min-w-0 flex-1"><h3 className="text-[13px] font-semibold">{title}</h3><p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">{description}</p></div><span className="shrink-0 pt-0.5 text-[10px] text-muted-foreground">Belum dibangun</span></div>)}
          </div>
          <Button disabled variant="outline" className="mt-3" data-testid="placeholder-module-primary-cta"><Lock className="mr-2 h-3.5 w-3.5" />Transaksi belum tersedia</Button>
        </Card>
        <div className="space-y-4">
          <Card className="border-border bg-card p-5"><h2 className="text-section-title">Gunakan yang sudah ada</h2><p className="mt-1 text-[12px] text-muted-foreground">Data terpusat, tanpa mengisi ulang atau membuat master pengganti.</p><div className="mt-3 space-y-2">{dependencies.length ? dependencies.map((item) => <Link key={item.to} to={item.to} data-testid={`placeholder-module-dependency-link-${item.key}`} className="flex items-center justify-between gap-2 rounded-md border border-border bg-background px-3 py-2.5 text-[12px] transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><span>{item.label}</span><ArrowRight className="h-3.5 w-3.5 text-muted-foreground" /></Link>) : <p className="text-[12px] text-muted-foreground" data-testid="module-dependencies-empty">Belum ada konfigurasi terkait yang dapat Anda akses.</p>}</div></Card>
          <div className="border-l-2 border-primary pl-4"><h3 className="text-[13px] font-semibold">Fokus pada yang perlu ditindaklanjuti</h3><p className="mt-2 text-[12px] leading-relaxed text-muted-foreground">{foundation?.focus}</p></div>
        </div>
      </div>
    </PageBody>
  </>;
};

export default ModulePlaceholderPage;
