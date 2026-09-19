import React, { useCallback, useEffect, useState } from "react";
import { Loader2, Lock, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { MODULE_INFO } from "@/lib/nav";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import { Card } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import ConfirmDialog from "@/components/common/ConfirmDialog";

const ModuleActivationPage = () => {
  const { can, refreshSession, company } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  const canConfigure = can("module", "config");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/modules");
      setItems(res.data.items || []);
    } catch (err) {
      toast.error(errorMessage(err, "Gagal memuat daftar modul."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    document.title = "Aktivasi Modul · HRIS Suite";
  }, [load, company?.id]);

  const applyToggle = async (mod, nextActive) => {
    setPending(mod.key);
    try {
      const res = await api.put("/modules/toggle", { module_key: mod.key, is_active: nextActive });
      toast.success(res.data.message, {
        description: nextActive
          ? "Menu modul ini kini muncul di navigasi perusahaan."
          : "Menu modul ini disembunyikan dan API-nya ditolak untuk perusahaan ini.",
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

  const handleToggle = (mod, nextActive) => {
    if (!nextActive) {
      setConfirm({ mod });
      return;
    }
    applyToggle(mod, true);
  };

  const activeCount = items.filter((m) => m.is_active).length;

  return (
    <>
      <PageHeader
        title="Aktivasi Modul"
        subtitle="Aktifkan modul yang dipakai perusahaan ini. Modul nonaktif tidak muncul di menu."
        actions={
          <span className="text-[13px] text-muted-foreground" data-numeric="true" data-testid="module-active-count">
            {activeCount} dari {items.length} modul aktif
          </span>
        }
      />
      <PageBody>
        {!canConfigure && (
          <div className="rounded-lg border border-border bg-secondary px-4 py-3 text-sm text-secondary-foreground">
            Anda hanya dapat melihat status modul. Perubahan langganan modul dilakukan oleh Pemilik
            Perusahaan atau Super Admin.
          </div>
        )}
        {loading ? (
          <div className="grid gap-3 md:grid-cols-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-28 w-full" />
            ))}
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {items.map((mod) => {
              const info = MODULE_INFO[mod.key];
              const Icon = info?.icon || ShieldCheck;
              return (
                <Card
                  key={mod.key}
                  className="border-border bg-card p-4"
                  data-testid={`module-card-${mod.key}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex min-w-0 items-start gap-3">
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-secondary text-secondary-foreground">
                        <Icon className="h-4 w-4" />
                      </span>
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-semibold">{mod.name}</p>
                          {!mod.can_toggle && (
                            <span className="inline-flex items-center gap-1 text-[12px] text-muted-foreground">
                              <Lock className="h-3 w-3" /> Modul dasar
                            </span>
                          )}
                          {mod.status === "planned" && (
                            <span className="text-[12px] text-muted-foreground">Fase berikutnya</span>
                          )}
                        </div>
                        <p className="mt-0.5 text-[13px] text-muted-foreground">{mod.description}</p>
                        {mod.is_active && mod.activated_at && (
                          <p className="mt-1 text-[11px] text-muted-foreground">
                            Aktif sejak {formatDateTime(mod.activated_at)}
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1.5">
                      {pending === mod.key ? (
                        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                      ) : (
                        <Switch
                          checked={mod.is_active}
                          disabled={!canConfigure || !mod.can_toggle}
                          onCheckedChange={(v) => handleToggle(mod, v)}
                          aria-label={`Aktifkan modul ${mod.name}`}
                          data-testid={`module-toggle-${mod.key}`}
                        />
                      )}
                      <span className="text-[11px] font-medium text-muted-foreground">
                        {mod.is_active ? "Aktif" : "Nonaktif"}
                      </span>
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </PageBody>

      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(v) => !v && setConfirm(null)}
        title={`Nonaktifkan modul ${confirm?.mod?.name}?`}
        description={`Menu ${confirm?.mod?.name} akan hilang dari navigasi semua pengguna perusahaan ini, dan permintaan API terkait akan ditolak. Data yang sudah ada tidak dihapus dan akan kembali muncul bila modul diaktifkan lagi.`}
        confirmLabel="Ya, nonaktifkan"
        loading={confirmLoading}
        onConfirm={() => {
          setConfirmLoading(true);
          applyToggle(confirm.mod, false);
        }}
      />
    </>
  );
};

export default ModuleActivationPage;
