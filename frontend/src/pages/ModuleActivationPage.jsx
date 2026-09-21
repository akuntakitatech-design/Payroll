import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Loader2, Lock, ShieldCheck, ArrowUpRight, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useSystemMode } from "@/lib/useSystemMode";
import { formatDateTime } from "@/lib/format";
import { MODULE_INFO, NAV_GROUPS } from "@/lib/nav";
import { MODULE_FOUNDATIONS, moduleReadiness, moduleAuditGroup } from "@/lib/moduleFoundation";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import { Card } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import ConfirmDialog from "@/components/common/ConfirmDialog";

const ModuleActivationPage = () => {
  const { can, refreshSession, company } = useAuth();
  const mode = useSystemMode();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const request = useRef(0);
  const canConfigure = can("module", "config");

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
    document.title = "Aktivasi Modul · HRIS Suite";
    return () => { request.current += 1; };
  }, [load, company?.id]);

  const applyToggle = async (mod, nextActive) => {
    if (mode.read_only || mod.key === "accounting" || !canConfigure) return;
    setPending(mod.key);
    try {
      const res = await api.put("/modules/toggle", { module_key: mod.key, is_active: nextActive });
      toast.success(res.data.message, {
        description: nextActive
          ? MODULE_FOUNDATIONS[mod.key] ? "Akses fondasi aktif. Fitur operasional belum dibangun." : "Menu modul kini muncul di navigasi perusahaan."
          : "Akses modul dinonaktifkan. Data yang sudah ada tidak dihapus.",
      });
      await load();
      await refreshSession();
    } catch (err) {
      toast.error(errorMessage(err, "Status modul tidak dapat diubah."));
    } finally {
      setPending(null);
      setConfirm(null);
      setConfirmLoading(false);
    }
  };

  const activeCount = items.filter((m) => m.is_active).length;

  return <>
    <PageHeader title="Aktivasi Modul" subtitle="Atur akses modul per perusahaan. Akses aktif tidak berarti seluruh fitur operasional sudah tersedia." actions={<span className="text-[13px] text-muted-foreground tabular-nums" data-testid="module-active-count">{loading ? "Memuat status…" : `${activeCount} dari ${items.length} akses modul aktif`}</span>} />
    <PageBody>
      <div className="rounded-lg border border-border bg-secondary px-4 py-3 text-[12px] leading-relaxed text-secondary-foreground" data-testid="module-audit-legend">
        <p className="font-semibold">Hasil audit & kesiapan modul</p>
        <p className="mt-1">A · Modul aktif &nbsp; / &nbsp; B · Belum lengkap &nbsp; / &nbsp; C · Belum aktif</p>
        <p className="mt-1 text-muted-foreground">D · Proses yang belum tersedia dicantumkan pada struktur masing-masing modul. Modul existing dipertahankan; Akuntansi ditunda.</p>
      </div>
      {mode.read_only && <div className="rounded-lg border border-warning-border bg-warning-soft px-4 py-3 text-[13px] text-warning" data-testid="module-readonly-notice">Mode hanya-baca: perubahan aktivasi modul dinonaktifkan.</div>}
      {!canConfigure && <p className="text-[13px] text-muted-foreground" data-testid="module-view-only-notice">Anda hanya dapat melihat status modul. Perubahan dilakukan oleh pengguna yang memiliki hak konfigurasi modul.</p>}
      {loading ? <div className="grid gap-3 md:grid-cols-2" data-testid="modules-loading">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-32 w-full" />)}</div>
        : error ? <Card className="space-y-3 p-4" role="alert" data-testid="modules-error"><p className="text-sm">{error}</p><Button variant="outline" onClick={load} data-testid="modules-retry"><RefreshCw className="mr-2 h-4 w-4" />Coba lagi</Button></Card>
        : !items.length ? <Card className="p-5" data-testid="modules-empty"><p className="text-sm">Katalog modul belum tersedia. Hubungi administrator untuk memeriksa konfigurasi lingkungan.</p></Card>
        : <div className="grid gap-3 md:grid-cols-2">{items.map((mod) => {
          const info = MODULE_INFO[mod.key];
          const Icon = info?.icon || ShieldCheck;
          const readiness = moduleReadiness(mod);
          const nav = NAV_GROUPS.flatMap((group) => group.items).find((item) => item.module === mod.key && !item.hidden);
          const canOpen = mod.is_active && nav && (!nav.resource || can(nav.resource, nav.action || "view")) && mod.key !== "accounting";
          const reason = mod.key === "accounting" ? "Akuntansi ditunda sesuai lingkup pengembangan." : mode.read_only ? "Dinonaktifkan pada mode hanya-baca." : !canConfigure ? "Anda tidak memiliki hak konfigurasi modul." : !mod.can_toggle ? "Modul dasar selalu aktif." : "";
          return <Card key={mod.key} className="border-border bg-card p-4 transition-colors hover:border-primary/30" data-testid={`module-card-${mod.key}`}>
            <div className="flex items-start justify-between gap-3">
              <div className="flex min-w-0 items-start gap-3"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-secondary text-secondary-foreground"><Icon className="h-4 w-4" /></span>
                <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><p className="text-sm font-semibold">{mod.name}</p>{mod.is_core && <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground"><Lock className="h-3 w-3" />Modul dasar</span>}</div>
                  <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">{mod.key === "attendance" ? "Struktur kehadiran, GPS, jadwal kerja, dan koreksi HR." : mod.description}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5"><Badge variant="outline" className="text-[10px] font-normal" data-testid={`module-audit-badge-${mod.key}`}>{moduleAuditGroup(mod)}</Badge><span className="text-[11px] font-medium text-primary" data-testid={`module-readiness-${mod.key}`}>{readiness.label}</span></div>
                  <p className="mt-1 text-[11px] text-muted-foreground">{readiness.description}</p>
                  {mod.is_active && mod.activated_at && <p className="mt-1 text-[10px] text-muted-foreground">Akses aktif sejak {formatDateTime(mod.activated_at)}</p>}
                </div>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1.5"><span title={reason || `Atur akses ${mod.name}`} data-testid={`module-toggle-disabled-reason-${mod.key}`}>
                {pending === mod.key ? <span className="flex h-6 w-10 items-center justify-center"><Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /></span> : <Switch checked={mod.is_active} disabled={!!reason || !!pending} onCheckedChange={(v) => v ? applyToggle(mod, true) : setConfirm({ mod })} aria-label={`Aktifkan modul ${mod.name}`} data-testid={`module-toggle-${mod.key}`} />}
              </span><span className="text-[10px] text-muted-foreground">{mod.is_active ? "Akses aktif" : "Nonaktif"}</span></div>
            </div>
            {canOpen && <div className="mt-3 flex justify-end border-t border-border pt-2"><Link to={nav.to} className="inline-flex items-center gap-1.5 rounded text-[12px] font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" data-testid={`module-open-${mod.key}`}>{MODULE_FOUNDATIONS[mod.key] ? "Lihat struktur modul" : "Buka modul existing"}<ArrowUpRight className="h-3.5 w-3.5" /></Link></div>}
          </Card>;
        })}</div>}
    </PageBody>
    <ConfirmDialog open={!!confirm} onOpenChange={(v) => !v && setConfirm(null)} title={`Nonaktifkan modul ${confirm?.mod?.name}?`} description="Menu dan akses modul akan dinonaktifkan untuk perusahaan ini. Data yang sudah ada tidak dihapus dan dapat diakses kembali setelah modul diaktifkan." confirmLabel="Ya, nonaktifkan" loading={confirmLoading} onConfirm={() => { setConfirmLoading(true); applyToggle(confirm.mod, false); }} />
  </>;
};

export default ModuleActivationPage;
