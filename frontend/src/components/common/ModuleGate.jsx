import React, { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { Lock, Layers } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { MODULE_INFO, NAV_GROUPS, matchNavModule } from "@/lib/nav";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const NAV_LABELS = NAV_GROUPS.flatMap((group) => group.items).reduce((acc, item) => {
  if (item.module && !acc[item.module]) acc[item.module] = item.label;
  return acc;
}, {});

/**
 * Guard route berbasis aktivasi modul.
 *
 * Menu hanya menyembunyikan tautan; komponen ini memastikan URL langsung
 * (bookmark, tautan dari dokumen, riwayat browser) juga tidak menampilkan
 * halaman modul yang belum aktif. Backend tetap penentu akhir lewat 403.
 *
 * `accounting` dikecualikan karena halaman placeholder-nya sudah menampilkan
 * status "ditunda" yang lebih informatif.
 */
const ModuleGate = ({ children }) => {
  const location = useLocation();
  const { hasModule, can, company } = useAuth();
  const moduleKey = matchNavModule(location.pathname);
  const blocked = moduleKey && moduleKey !== "accounting" && !hasModule(moduleKey);

  useEffect(() => {
    if (blocked) {
      document.title = `${MODULE_INFO[moduleKey]?.name || NAV_LABELS[moduleKey] || "Modul"} · HRIS Suite`;
    }
  }, [blocked, moduleKey]);

  if (!blocked) return children;

  const name = MODULE_INFO[moduleKey]?.name || NAV_LABELS[moduleKey] || "Modul";
  const Icon = MODULE_INFO[moduleKey]?.icon || Layers;

  return (
    <>
      <PageHeader title={name} subtitle="Modul ini belum aktif untuk perusahaan Anda." />
      <PageBody>
        <Card className="max-w-2xl p-5" data-testid="module-gate-inactive">
          <div className="flex items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-locked-border bg-locked-soft text-locked">
              <Lock className="h-5 w-5" strokeWidth={1.75} />
            </span>
            <div className="min-w-0">
              <h2 className="text-section-title">Akses modul belum diaktifkan</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Modul <strong>{name}</strong> belum diaktifkan untuk{" "}
                {company?.name ? <strong>{company.name}</strong> : "perusahaan ini"}, atau modul
                prasyaratnya belum aktif. Seluruh menu dan fitur turunannya ikut ditutup.
              </p>
              <p className="mt-2 text-[12.5px] leading-relaxed text-muted-foreground">
                Data yang sudah ada tidak dihapus. Saat modul diaktifkan kembali, seluruh data lama
                tampil lagi seperti semula. Aktivasi dilakukan Platform Admin melalui Konsol Platform.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                {can("module", "view") && (
                  <Button asChild variant="outline" data-testid="module-gate-open-activation">
                    <Link to="/setup/modules">
                      <Icon className="mr-1.5 h-4 w-4" />Lihat modul perusahaan
                    </Link>
                  </Button>
                )}
                <Button asChild variant="ghost" data-testid="module-gate-back-dashboard">
                  <Link to="/">Kembali ke ringkasan</Link>
                </Button>
              </div>
            </div>
          </div>
        </Card>
      </PageBody>
    </>
  );
};

export default ModuleGate;
