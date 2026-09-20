import React from "react";
import { Link } from "react-router-dom";
import { Building2, MapPin, RefreshCw, Users, FileText, Boxes, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import HeaderIllustration from "./HeaderIllustration";

/**
 * Header dashboard: sapaan, identitas perusahaan, statistik inline sebagai
 * chip, tombol aksi, dan ilustrasi SVG kecil di kanan.
 *
 * Gradient halus hanya dipakai di sini (jauh di bawah 20% viewport) agar
 * memberi kesan premium tanpa mengganggu area baca.
 */
const StatChip = ({ icon: Icon, label, value }) => (
  <span
    className="inline-flex items-center gap-2 rounded-full border border-white/70 bg-white/80 px-3 py-1.5 text-[12px] backdrop-blur-sm"
    data-testid="dashboard-header-inline-stat"
  >
    <Icon className="h-3.5 w-3.5 shrink-0 text-primary" strokeWidth={2} />
    <span className="font-semibold text-ink-1" data-numeric="true">
      {value}
    </span>
    <span className="text-ink-3">{label}</span>
  </span>
);

const DashboardHeader = ({ greeting, firstName, company, counts, periodLabel, onRefresh, refreshing, canCreateEmployee }) => (
  <section
    className="dashboard-hero surface-noise relative overflow-hidden rounded-panel border border-primary-border/60 shadow-card"
    data-testid="dashboard-header"
  >
    <div className="relative z-10 flex flex-col gap-6 p-6 lg:flex-row lg:items-center lg:justify-between lg:gap-8">
      <div className="min-w-0 flex-1">
        <p className="text-[12px] font-semibold uppercase tracking-[0.1em] text-primary-strong/80">
          {periodLabel}
        </p>

        <h1 className="mt-2 text-[24px] font-semibold leading-[1.2] tracking-[-0.02em] text-ink-1 sm:text-[26px]">
          {greeting}, {firstName}
        </h1>

        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-ink-2">
          <span className="inline-flex items-center gap-1.5 font-medium">
            <Building2 className="h-3.5 w-3.5 text-primary" strokeWidth={2} />
            {company?.name || "Belum ada perusahaan aktif"}
          </span>
          {company?.city && (
            <>
              <span className="h-1 w-1 rounded-full bg-ink-3/40" aria-hidden="true" />
              <span className="inline-flex items-center gap-1.5">
                <MapPin className="h-3.5 w-3.5 text-ink-3" strokeWidth={2} />
                {company.city}
              </span>
            </>
          )}
          {company?.code && (
            <>
              <span className="h-1 w-1 rounded-full bg-ink-3/40" aria-hidden="true" />
              <span className="rounded-md border border-primary-border/70 bg-white/70 px-1.5 py-0.5 text-[11.5px] font-semibold text-primary-strong">
                {company.code}
              </span>
            </>
          )}
        </div>

        {counts && (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <StatChip icon={Users} value={counts.users} label="pengguna" />
            <StatChip icon={FileText} value={counts.documents} label="dokumen" />
            <StatChip icon={Boxes} value={`${counts.active_modules}/${counts.available_modules}`} label="modul aktif" />
          </div>
        )}

        <div className="mt-5 flex flex-wrap items-center gap-2">
          {canCreateEmployee && (
            <Button asChild size="sm" className="h-9 rounded-lg shadow-xs">
              <Link to="/employees" data-testid="dashboard-header-primary-action">
                <Plus className="mr-1.5 h-4 w-4" strokeWidth={2.25} />
                Kelola Karyawan
              </Link>
            </Button>
          )}
          <Button
            asChild
            variant="outline"
            size="sm"
            className="h-9 rounded-lg border-white/80 bg-white/80 hover:bg-white"
          >
            <Link to="/documents" data-testid="dashboard-header-secondary-action">
              Arsip Dokumen
            </Link>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onRefresh}
            disabled={refreshing}
            className="h-9 rounded-lg text-ink-2 hover:bg-white/70"
            data-testid="dashboard-refresh"
          >
            <RefreshCw className={`mr-1.5 h-4 w-4 ${refreshing ? "animate-spin" : ""}`} strokeWidth={2} />
            Muat ulang
          </Button>
        </div>
      </div>

      <div className="hidden shrink-0 lg:block" aria-hidden="true">
        <HeaderIllustration className="h-[152px] w-[228px]" />
      </div>
    </div>
  </section>
);

export default DashboardHeader;
