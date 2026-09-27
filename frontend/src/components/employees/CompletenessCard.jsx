import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, ChevronRight, CircleDashed, ClipboardCheck, Clock3, Info, RefreshCw } from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";

/* ------------------------------------------------------------------ shared (dipakai kartu, drawer, master) */
export const COMPLETENESS_META = {
  LENGKAP: { label: "Lengkap", cls: "border-success-border bg-success-soft text-foreground" },
  BELUM_LENGKAP: { label: "Belum lengkap", cls: "border-warning-border bg-warning-soft text-foreground" },
  EXCLUDED: { label: "Tidak dihitung (nonaktif)", cls: "border-border bg-muted text-muted-foreground" },
};
export const LEVEL_META = {
  REQUIRED: { label: "Wajib", cls: "border-primary-border bg-primary-soft text-foreground" },
  RECOMMENDED: { label: "Anjuran", cls: "border-info-border bg-info-soft text-foreground" },
  OFF: { label: "Nonaktif", cls: "border-border bg-muted text-muted-foreground" },
};
const ITEM_TONE = {
  COMPLETE: "border-success-border bg-success-soft",
  MISSING: "border-warning-border bg-warning-soft",
  INVALID: "border-danger-border bg-danger-soft",
  EXPIRED: "border-danger-border bg-danger-soft",
  UNVERIFIED: "border-info-border bg-info-soft",
};

/** evaluated_at dari API = UTC tanpa zona -> tampilkan waktu lokal. */
export const formatEvaluated = (v) => (v ? formatDateTime(`${String(v).replace(/Z|\+00:00$/, "")}Z`) : "-");

export const CompletenessStatusBadge = ({ status, testId }) => {
  const meta = COMPLETENESS_META[status] || COMPLETENESS_META.BELUM_LENGKAP;
  return <Badge variant="outline" className={cn("whitespace-nowrap font-medium", meta.cls)} data-testid={testId}>{meta.label}</Badge>;
};

export const LevelBadge = ({ level, testId }) => (
  <Badge variant="outline" className={cn("whitespace-nowrap text-[11px] font-medium", LEVEL_META[level]?.cls)} data-testid={testId}>
    {LEVEL_META[level]?.label || level}
  </Badge>
);

export const PendingBadge = ({ testId = "completeness-pending-badge" }) => (
  <Badge variant="outline" className="gap-1 whitespace-nowrap border-info-border bg-info-soft text-foreground" data-testid={testId}>
    <Clock3 className="h-3 w-3" />Menunggu evaluasi
  </Badge>
);

const ItemStatus = ({ item }) => (
  <span className={cn("inline-flex items-center gap-1 whitespace-nowrap rounded-md border px-1.5 py-0.5 text-[11px] font-medium text-foreground",
    ITEM_TONE[item.status] || "border-border bg-muted")} data-testid={`completeness-item-status-${item.code}`}>
    {item.status === "COMPLETE" ? <CheckCircle2 className="h-3 w-3 text-success" /> : <CircleDashed className="h-3 w-3" />}
    {item.status === "COMPLETE" ? "Terpenuhi" : item.status_label}
  </span>
);

/**
 * Rincian per kategori. mode="missing": hanya data yang belum terpenuhi (kartu profil).
 * mode="all": semua requirement yang berlaku, terpenuhi maupun belum (drawer monitoring).
 * Hanya kode/label/status dari API - TIDAK ada nilai field karyawan.
 */
export const CompletenessBreakdown = ({ data, mode = "missing", onOpenTab, testId = "completeness-breakdown" }) => {
  const applicable = (data.items || []).filter((i) => !["NOT_APPLICABLE", "OFF"].includes(i.status));
  const shown = mode === "all" ? applicable : applicable.filter((i) => i.status !== "COMPLETE");
  const groups = (data.categories || []).map((c) => ({ ...c, items: shown.filter((i) => i.category === c.key) }))
    .filter((g) => g.items.length);
  if (!groups.length) return null;
  return (
    <ul className="divide-y divide-border rounded-lg border border-border" data-testid={testId}>
      {groups.map((g) => (
        <li key={g.key} className="space-y-2 p-3" data-testid={`${testId}-group-${g.key}`}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-semibold">{g.label}</p>
            {onOpenTab && (
              <Button size="sm" variant="ghost" className="h-8 text-primary" onClick={() => onOpenTab(g.tab)}
                data-testid={`${testId}-open-${g.key}`}>
                Buka tab {g.label}<ChevronRight className="ml-1 h-4 w-4" />
              </Button>
            )}
          </div>
          <ul className="space-y-1.5">
            {g.items.map((i) => (
              <li key={i.code} className="flex flex-wrap items-center justify-between gap-2 text-[13px]" data-testid={`completeness-item-${i.code}`}>
                <span className="flex min-w-0 items-center gap-2">
                  <LevelBadge level={i.level} />
                  <span className="truncate">{i.label}</span>
                </span>
                <ItemStatus item={i} />
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ul>
  );
};

/* ------------------------------------------------------------------ kartu Profile 360 */
export const CompletenessCard = ({ employeeId, refreshKey, onOpenTab }) => {
  const { can } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const canReevaluate = can("employee", "edit");

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setData((await api.get(`/employees/${employeeId}/completeness`)).data); }
    catch (e) { setError(errorMessage(e)); } finally { setLoading(false); }
  }, [employeeId]);
  useEffect(() => { load(); }, [load, refreshKey]);

  const reevaluate = async () => {
    setBusy(true);
    try {
      const { data: res } = await api.post(`/employees/${employeeId}/completeness/reevaluate`);
      toast.success(res.message || "Kelengkapan data dievaluasi ulang.");
      await load();
    } catch (e) { toast.error(errorMessage(e)); } finally { setBusy(false); }
  };

  if (loading && !data) return (
    <Card data-testid="completeness-loading"><CardContent className="space-y-3 p-5">
      <Skeleton className="h-4 w-40" /><Skeleton className="h-8 w-24" /><Skeleton className="h-2 w-full" /><Skeleton className="h-16 w-full" />
    </CardContent></Card>
  );
  if (error && !data) return (
    <Card data-testid="completeness-error"><CardContent className="flex flex-wrap items-center justify-between gap-3 p-4 text-sm">
      <span className="text-danger">Kelengkapan data belum dapat dimuat. {error}</span>
      <Button size="sm" variant="outline" onClick={load} data-testid="completeness-retry">Coba lagi</Button>
    </CardContent></Card>
  );

  const items = data.items || [];
  const missingRequired = items.filter((i) => i.level === "REQUIRED" && !["COMPLETE", "NOT_APPLICABLE", "OFF"].includes(i.status));
  const recommended = items.filter((i) => i.level === "RECOMMENDED" && !["COMPLETE", "NOT_APPLICABLE", "OFF"].includes(i.status));
  const requiredOnly = { ...data, items: missingRequired };
  const recommendedOnly = { ...data, items: recommended };
  const excluded = data.completeness_status === "EXCLUDED";

  return (
    <Card data-testid="completeness-card">
      <CardHeader className="gap-2 pb-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2 text-section-title"><ClipboardCheck className="h-4 w-4 text-primary" />Kelengkapan Data</CardTitle>
            <CardDescription>Skor dihitung dari data <b>wajib</b> yang berlaku untuk karyawan ini. Data <b>anjuran</b> tidak menurunkan skor.</CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {data.is_stale && <PendingBadge />}
            <CompletenessStatusBadge status={data.completeness_status} testId="completeness-status" />
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {excluded ? (
          <p className="text-sm text-muted-foreground" data-testid="completeness-excluded">Karyawan berstatus nonaktif tidak dihitung dalam kelengkapan data.</p>
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-[auto,1fr] sm:items-center">
              <p className="text-[28px] font-semibold leading-none tracking-tight" data-numeric="true" data-testid="completeness-score">{data.score_pct}%</p>
              <div className="space-y-1.5">
                <Progress value={Number(data.score_pct) || 0} className="h-2" aria-label="Persentase kelengkapan" />
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-meta">
                  <span data-testid="completeness-required-count"><b className="text-foreground" data-numeric="true">{data.required_fulfilled}</b> dari <b className="text-foreground" data-numeric="true">{data.required_total}</b> data wajib terpenuhi</span>
                  <span data-testid="completeness-missing-count"><b className="text-foreground" data-numeric="true">{missingRequired.length}</b> data wajib kurang</span>
                </div>
              </div>
            </div>
            {missingRequired.length === 0 ? (
              <div className="flex items-center gap-2 rounded-lg border border-success-border bg-success-soft p-3 text-sm" data-testid="completeness-all-done">
                <CheckCircle2 className="h-4 w-4 text-success" />Semua data wajib sudah lengkap.
              </div>
            ) : (
              <div className="space-y-2">
                <p className="text-[13px] font-semibold">Data wajib yang perlu dilengkapi</p>
                <CompletenessBreakdown data={requiredOnly} onOpenTab={onOpenTab} testId="completeness-missing-list" />
              </div>
            )}
            {recommended.length > 0 && (
              <div className="space-y-2" data-testid="completeness-recommended">
                <p className="flex items-center gap-1.5 text-[13px] font-semibold"><Info className="h-3.5 w-3.5 text-info" />Anjuran — tidak memengaruhi skor</p>
                <CompletenessBreakdown data={recommendedOnly} onOpenTab={onOpenTab} testId="completeness-recommended-list" />
              </div>
            )}
          </>
        )}
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3 text-meta">
          <span data-testid="completeness-evaluated-at">Evaluasi terakhir: {formatEvaluated(data.evaluated_at)}</span>
          {canReevaluate ? (
            <Button size="sm" variant="outline" onClick={reevaluate} disabled={busy || loading} data-testid="completeness-reevaluate-employee">
              <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", (busy || loading) && "animate-spin")} />{busy ? "Mengevaluasi…" : "Evaluasi Ulang"}
            </Button>
          ) : (
            <Button size="sm" variant="ghost" onClick={load} disabled={loading} data-testid="completeness-refresh">
              <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", loading && "animate-spin")} />Muat ulang
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default CompletenessCard;
