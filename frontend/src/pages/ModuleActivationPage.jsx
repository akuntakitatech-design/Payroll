import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Lock, RefreshCw, ShieldCheck } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useSystemMode } from "@/lib/useSystemMode";
import { formatDateTime } from "@/lib/format";
import { MODULE_INFO, NAV_GROUPS } from "@/lib/nav";
import { MODULE_FOUNDATIONS, moduleReadiness, moduleAuditGroup } from "@/lib/moduleFoundation";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

/**
 * Tampilan modul untuk tenant: HANYA-BACA.
 * Aktivasi modul dikelola Platform Admin lewat Konsol Platform (Tenant -> Modul & Fitur),
 * sehingga menu yang tampil di tenant selalu mengikuti modul yang diambil tenant.
 */
const ModuleActivationPage = () => {
  const { can, company } = useAuth();
  const mode = useSystemMode();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const request = useRef(0);

  const load = useCallback(async () => {
    const id = ++request.current;
    setLoading(true);
    setError("");
    try {
      const res = await api.get("/modules");
      if (id === request.current) setItems(res.data.items || []);
    } catch (err) {
      if (id === request.current) setError(errorMessage(err, "Gagal memuat daftar modul."));
    } finally {
      if (id === request.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    document.title = "Modul Perusahaan · HRIS Suite";
    return () => { request.current += 1; };
  }, [load, company?.id]);

  const activeItems = items.filter((m) => m.is_active);

  return <>
    <PageHeader
      title="Modul Perusahaan"
      subtitle="Daftar modul yang aktif untuk perusahaan Anda. Menu dan fitur di tenant hanya menampilkan modul yang aktif."
      actions={<span className="text-[13px] text-muted-foreground tabular-nums" data-testid="module-active-count">{loading ? "Memuat status…" : `${activeItems.length} modul aktif`}</span>}
    />
    <PageBody>
      <div className="rounded-lg border border-border bg-secondary px-4 py-3 text-[12px] leading-relaxed text-secondary-foreground" data-testid="module-platform-notice">
        <p className="font-semibold">Aktivasi modul dikelola Platform Admin</p>
        <p className="mt-1">
          Menambah atau menonaktifkan modul dilakukan melalui <strong>Konsol Platform → pilih tenant → tab Modul &amp; Fitur</strong>.
          Halaman ini hanya menampilkan modul yang tersedia untuk perusahaan Anda. Data lama tidak dihapus saat modul dinonaktifkan.
        </p>
      </div>
      {mode.read_only && <div className="rounded-lg border border-warning-border bg-warning-soft px-4 py-3 text-[13px] text-warning" data-testid="module-readonly-notice">Mode hanya-baca: data modul tidak dapat diubah dari lingkungan ini.</div>}
      {loading ? <div className="grid gap-3 md:grid-cols-2" data-testid="modules-loading">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-32 w-full" />)}</div>
        : error ? <Card className="space-y-3 p-4" role="alert" data-testid="modules-error"><p className="text-sm">{error}</p><Button variant="outline" onClick={load} data-testid="modules-retry"><RefreshCw className="mr-2 h-4 w-4" />Coba lagi</Button></Card>
        : !activeItems.length ? <Card className="p-5" data-testid="modules-empty"><p className="text-sm">Belum ada modul aktif untuk perusahaan ini. Hubungi Platform Admin untuk mengaktifkan modul yang dibutuhkan.</p></Card>
        : <div className="grid gap-3 md:grid-cols-2">{activeItems.map((mod) => {
          const info = MODULE_INFO[mod.key];
          const Icon = info?.icon || ShieldCheck;
          const readiness = moduleReadiness(mod);
          const nav = NAV_GROUPS.flatMap((group) => group.items).find((item) => item.module === mod.key && !item.hidden);
          const canOpen = mod.is_active && nav && (!nav.resource || can(nav.resource, nav.action || "view"));
          return <Card key={mod.key} className="border-border bg-card p-4 transition-colors hover:border-primary/30" data-testid={`module-card-${mod.key}`}>
            <div className="flex items-start justify-between gap-3">
              <div className="flex min-w-0 items-start gap-3"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-secondary text-secondary-foreground"><Icon className="h-4 w-4" /></span>
                <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><p className="text-sm font-semibold">{mod.name}</p>{mod.is_core && <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground"><Lock className="h-3 w-3" />Modul dasar</span>}</div>
                  <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">{mod.key === "attendance" ? "Struktur kehadiran, GPS, jadwal kerja, dan koreksi HR." : mod.description}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5"><Badge variant="outline" className="text-[10px] font-normal" data-testid={`module-audit-badge-${mod.key}`}>{moduleAuditGroup(mod)}</Badge><span className="text-[11px] font-medium text-primary" data-testid={`module-readiness-${mod.key}`}>{readiness.label}</span></div>
                  <p className="mt-1 text-[11px] text-muted-foreground">{readiness.description}</p>
                  {mod.is_active && mod.activated_at && <p className="mt-1 text-[10px] text-muted-foreground">Aktif sejak {formatDateTime(mod.activated_at)}</p>}
                </div>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1.5">
                <Badge variant={mod.is_active ? "default" : "secondary"} data-testid={`module-status-${mod.key}`}>{mod.is_active ? "Aktif" : "Nonaktif"}</Badge>
                <span className="text-[10px] text-muted-foreground">{mod.is_active ? "Menu tampil" : "Menu disembunyikan"}</span>
              </div>
            </div>
            {canOpen && <div className="mt-3 flex justify-end border-t border-border pt-2"><Link to={nav.to} className="inline-flex items-center gap-1.5 rounded text-[12px] font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" data-testid={`module-open-${mod.key}`}>{MODULE_FOUNDATIONS[mod.key] ? "Lihat struktur modul" : "Buka modul existing"}<ArrowUpRight className="h-3.5 w-3.5" /></Link></div>}
          </Card>;
        })}</div>}
    </PageBody>
  </>;
};

export default ModuleActivationPage;
