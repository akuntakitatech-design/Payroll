import React, { useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, Boxes, CalendarClock, Clock, RefreshCw, Users } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useDashboardData } from "@/lib/dashboardData";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import DashboardHeader from "@/components/dashboard/DashboardHeader";
import KpiCard from "@/components/dashboard/KpiCard";
import PriorityCard from "@/components/dashboard/PriorityCard";
import HrTodayCard from "@/components/dashboard/HrTodayCard";
import DepartmentChart from "@/components/dashboard/DepartmentChart";
import ApprovalCard from "@/components/dashboard/ApprovalCard";
import ExpiringDocsCard from "@/components/dashboard/ExpiringDocsCard";
import SetupChecklistCard from "@/components/dashboard/SetupChecklistCard";

const MONTHS = [
  "Januari", "Februari", "Maret", "April", "Mei", "Juni",
  "Juli", "Agustus", "September", "Oktober", "November", "Desember",
];
const DAYS = ["Minggu", "Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"];

const greetingFor = (hour) => {
  if (hour < 11) return "Selamat pagi";
  if (hour < 15) return "Selamat siang";
  if (hour < 18) return "Selamat sore";
  return "Selamat malam";
};

/** Kerangka pemuatan yang meniru bentuk akhir, supaya tidak terasa melompat. */
const DashboardSkeleton = () => (
  <div className="space-y-5">
    <Skeleton className="h-[188px] w-full rounded-panel" />
    <div className="grid gap-5 xl:grid-cols-12">
      <div className="xl:col-span-5">
        <Skeleton className="h-[320px] w-full rounded-card" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:col-span-7">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-[150px] w-full rounded-card" />
        ))}
      </div>
    </div>
    <div className="grid gap-5 xl:grid-cols-12">
      <Skeleton className="h-[300px] w-full rounded-card xl:col-span-5" />
      <Skeleton className="h-[300px] w-full rounded-card xl:col-span-7" />
    </div>
  </div>
);

const DashboardPage = () => {
  const { user, company, can } = useAuth();
  const { data, loading, error, reload } = useDashboardData();

  useEffect(() => {
    document.title = "Dashboard · HRIS & Payroll Dashboard";
  }, []);

  const now = new Date();
  const periodLabel = useMemo(
    () => `${DAYS[now.getDay()]}, ${now.getDate()} ${MONTHS[now.getMonth()]} ${now.getFullYear()}`,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const greeting = greetingFor(now.getHours());
  const firstName = user?.full_name?.split(" ")[0] || "Pengguna";

  const kpi = data?.kpi;

  return (
    <div className="px-4 py-5 sm:px-6 sm:py-6">
      {/* ---------- Header dashboard ---------- */}
      <DashboardHeader
        greeting={greeting}
        firstName={firstName}
        company={company || data?.company}
        counts={data?.counts}
        periodLabel={periodLabel}
        onRefresh={reload}
        refreshing={loading}
        canCreateEmployee={can("employee", "view")}
      />

      {error && (
        <div
          className="mt-5 flex flex-wrap items-center gap-3 rounded-card border border-danger-border bg-danger-soft px-4 py-3"
          data-testid="dashboard-error"
        >
          <AlertCircle className="h-4 w-4 shrink-0 text-danger" strokeWidth={2} />
          <p className="min-w-0 flex-1 text-[13px] text-danger">{error}</p>
          <Button variant="outline" size="sm" onClick={reload} className="h-8" data-testid="dashboard-error-retry">
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Coba lagi
          </Button>
        </div>
      )}

      {loading && !data ? (
        <div className="mt-5">
          <DashboardSkeleton />
        </div>
      ) : (
        data && (
          <>
            {/* ---------- Prioritas + KPI ----------
                Kartu prioritas diletakkan sejajar KPI supaya pertanyaan
                "apa yang harus saya kerjakan hari ini?" terjawab lebih dulu. */}
            <div className="mt-5 grid gap-5 xl:grid-cols-12">
              <div className="xl:col-span-5">
                <PriorityCard items={data.attention} />
              </div>

              <div className="grid auto-rows-min content-start gap-4 sm:grid-cols-2 xl:col-span-7">
                <KpiCard
                  label="Karyawan Aktif"
                  value={kpi?.employees_active?.value ?? data.counts.employees}
                  meta={kpi?.employees_active?.meta}
                  icon={Users}
                  tone="normal"
                  link="/employees"
                  testId="kpi-karyawan-aktif-card"
                />

                {/* Kejujuran data: modul Absensi belum punya data kehadiran,
                    jadi kartu ini tampil terkunci tanpa angka karangan. */}
                <KpiCard
                  label="Hadir Hari Ini"
                  icon={Clock}
                  locked
                  lockedReason={kpi?.attendance_today?.meta}
                  lockedActionLabel={kpi?.attendance_today?.action_label || "Lihat Aktivasi Modul"}
                  link={kpi?.attendance_today?.link || "/setup/modules"}
                  testId="kpi-hadir-hari-ini-locked-card"
                  actionTestId="kpi-hadir-hari-ini-activate-button"
                />

                <KpiCard
                  label="Kontrak Akan Berakhir"
                  value={kpi?.contracts_ending?.value ?? 0}
                  meta={kpi?.contracts_ending?.meta}
                  icon={CalendarClock}
                  tone={
                    kpi?.contracts_ending?.severity === "critical"
                      ? "critical"
                      : kpi?.contracts_ending?.value > 0
                        ? "warning"
                        : "success"
                  }
                  link="/reminders?kind=contract"
                  testId="kpi-kontrak-akan-berakhir-card"
                  badge={
                    kpi?.contracts_ending?.expired > 0 ? (
                      <span className="shrink-0 rounded-full border border-danger-border bg-danger-soft px-2 py-0.5 text-[10.5px] font-semibold text-danger">
                        Perlu perhatian
                      </span>
                    ) : null
                  }
                />

                <KpiCard
                  label="Modul Aktif"
                  value={kpi?.modules_active?.value ?? data.counts.active_modules}
                  suffix={`/ ${kpi?.modules_active?.total ?? data.counts.available_modules}`}
                  meta={kpi?.modules_active?.meta}
                  icon={Boxes}
                  tone="normal"
                  link="/setup/modules"
                  testId="kpi-modul-aktif-card"
                />
              </div>
            </div>

            {/* ---------- Ringkasan SDM + Chart departemen ---------- */}
            <div className="mt-5 grid gap-5 xl:grid-cols-12">
              <div className="xl:col-span-5">
                <HrTodayCard rows={data.hr_today?.rows || []} asOfLabel={periodLabel} />
              </div>
              <div className="xl:col-span-7">
                <DepartmentChart
                  data={data.department_distribution || []}
                  totalEmployees={data.counts.employees}
                />
              </div>
            </div>

            {/* ---------- Persetujuan + Dokumen + Setup ---------- */}
            <div className="mt-5 grid items-start gap-5 lg:grid-cols-2 xl:grid-cols-12">
              <div className="xl:col-span-4">
                <ApprovalCard
                  pending={data.pending_approvals}
                  workflowCount={data.counts.approval_workflows}
                />
              </div>
              <div className="xl:col-span-4">
                <ExpiringDocsCard
                  documents={data.expiring_documents}
                  horizonDays={data.horizon_days}
                  totalDocuments={data.counts.documents}
                />
              </div>
              <div className="lg:col-span-2 xl:col-span-4">
                <SetupChecklistCard progress={data.setup_progress} />
              </div>
            </div>

            {/* ---------- Catatan penutup ---------- */}
            <p className="mt-5 text-[11.5px] leading-[1.5] text-ink-3">
              Angka pada halaman ini dihitung langsung dari basis data perusahaan aktif
              {company?.name ? ` (${company.name})` : ""}. Kartu yang menampilkan keterangan
              &ldquo;data belum tersedia&rdquo; berarti modulnya memang belum memiliki data
              &mdash; bukan kegagalan sistem.{" "}
              <Link
                to="/setup/modules"
                className="font-medium text-primary underline-offset-2 hover:underline"
                data-testid="dashboard-modules-footnote-link"
              >
                Lihat aktivasi modul
              </Link>
            </p>
          </>
        )
      )}
    </div>
  );
};

export default DashboardPage;
