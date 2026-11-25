import React, { useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle, ArrowDownRight, ArrowUpRight, CalendarClock, CheckCircle2, ChevronRight,
  CircleAlert, Gauge, Info, LogIn, LogOut, TrendingUp, UserMinus, UserRound, Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ChartCard, DonutChart, BarList, TrendChart, PeriodBars } from "./charts";
import { formatMoney, formatMinutes, formatNumber, formatPct } from "@/lib/dashboardAnalytics";

const KPI_ICONS = {
  total_employees: Users,
  active_employees: UserRound,
  inactive_employees: UserMinus,
  joined: LogIn,
  exited: LogOut,
  turnover: TrendingUp,
  retention: CheckCircle2,
  avg_age: UserRound,
  avg_tenure: CalendarClock,
};

const TONES = {
  success: "border-success-border bg-success-soft text-success",
  info: "border-primary-border bg-primary-soft text-primary",
  warning: "border-warning-border bg-warning-soft text-warning",
  critical: "border-danger-border bg-danger-soft text-danger",
  overdue: "border-danger-border bg-danger-soft text-danger",
  neutral: "border-border bg-secondary text-ink-2",
};

const formatKpiValue = (kpi) => {
  if (!kpi.available || kpi.value === null || kpi.value === undefined) return "—";
  if (kpi.unit === "percent") return formatPct(kpi.value, 2);
  if (kpi.unit === "year") return `${Number(kpi.value).toLocaleString("id-ID")} th`;
  return formatNumber(kpi.value);
};

const KpiTile = ({ kpi }) => {
  const Icon = KPI_ICONS[kpi.key] || Gauge;
  const delta = kpi.delta_pct;
  const neutral = delta === null || delta === undefined || delta === 0;
  const good = neutral ? null : kpi.good_when === "down" ? delta < 0 : delta > 0;
  const DeltaIcon = neutral || delta === 0 ? Info : delta > 0 ? ArrowUpRight : ArrowDownRight;
  const body = (
    <>
      <div className="flex items-start justify-between gap-3">
        <p className="text-[12.5px] font-semibold uppercase tracking-[0.04em] text-ink-3">{kpi.label}</p>
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-primary-border bg-[linear-gradient(180deg,hsl(var(--primary-soft))_0%,#FFFFFF_100%)] text-primary shadow-[var(--shadow-raised)]">
          <Icon className="h-4 w-4" strokeWidth={1.9} />
        </span>
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="text-[26px] font-bold leading-[1.1] tracking-[-0.02em] text-ink-1 tabular-nums">
          {formatKpiValue(kpi)}
        </span>
        {!neutral && (
          <span className={cn("inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[11px] font-semibold",
            good ? "bg-success-soft text-success" : "bg-danger-soft text-danger")}>
            <DeltaIcon className="h-3 w-3" />
            {Math.abs(delta)}%
          </span>
        )}
      </div>
      <p className="mt-1 line-clamp-2 text-[11.5px] leading-relaxed text-ink-3">
        {kpi.note || (kpi.prev !== null && kpi.prev !== undefined
          ? `Sebelumnya ${formatKpiValue({ ...kpi, value: kpi.prev })}`
          : kpi.tooltip || "")}
      </p>
    </>
  );

  const className = "flex flex-col rounded-card border border-border bg-card p-4 shadow-card transition-[box-shadow,border-color] duration-150";
  if (!kpi.link) {
    return <div className={className} title={kpi.tooltip} data-testid={`kpi-${kpi.key}-card`}>{body}</div>;
  }
  return (
    <Link
      to={kpi.link}
      title={kpi.tooltip}
      className={cn(className, "group hover:border-primary-border hover:shadow-float focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring")}
      data-testid={`kpi-${kpi.key}-card`}
    >
      {body}
    </Link>
  );
};

export const KpiGrid = ({ kpis = [], testId = "dashboard-kpi-grid" }) => (
  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6" data-testid={testId}>
    {kpis.map((kpi) => <KpiTile key={kpi.key} kpi={kpi} />)}
  </div>
);

const Metric = ({ label, value, hint, tone }) => (
  <div className="rounded-lg border border-border bg-secondary/60 px-3 py-2.5">
    <p className="text-[11px] font-medium uppercase tracking-[0.03em] text-ink-3">{label}</p>
    <p className={cn("mt-0.5 text-[18px] font-bold tabular-nums", tone === "warning" ? "text-warning" : tone === "critical" ? "text-danger" : "text-ink-1")}>
      {value}
    </p>
    {hint && <p className="mt-0.5 text-[11px] text-ink-3">{hint}</p>}
  </div>
);

export const InsightList = ({ items = [] }) => (
  <ChartCard
    title="Executive Insight"
    subtitle="Ringkasan otomatis berbasis aturan dari data aktual pada filter aktif."
    testId="dashboard-insights"
  >
    {items.length ? (
      <ul className="space-y-2">
        {items.map((item) => {
          const Icon = item.severity === "warning" ? AlertTriangle : item.severity === "success" ? CheckCircle2 : Info;
          return (
            <li key={item.key} className="flex items-start gap-2.5 rounded-lg border border-border bg-card px-3 py-2.5">
              <span className={cn("mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md border", TONES[item.severity] || TONES.info)}>
                <Icon className="h-3.5 w-3.5" />
              </span>
              <div className="min-w-0">
                <p className="text-[12.5px] leading-relaxed text-ink-1">{item.text}</p>
                <p className="mt-1 text-[11px] text-ink-3">Sumber: {item.source}</p>
              </div>
              {item.link && (
                <Link to={item.link} className="ml-auto shrink-0 text-primary hover:underline" aria-label="Buka detail">
                  <ChevronRight className="h-4 w-4" />
                </Link>
              )}
            </li>
          );
        })}
      </ul>
    ) : (
      <p className="py-6 text-center text-[12.5px] text-ink-3">Belum ada insight pada periode ini.</p>
    )}
  </ChartCard>
);

export const ActionCenter = ({ items = [] }) => (
  <ChartCard
    title="Action Center"
    subtitle="Pekerjaan yang perlu ditindaklanjuti, diurutkan berdasarkan tingkat kepentingan."
    testId="dashboard-action-center"
  >
    {items.length ? (
      <ul className="divide-y divide-border">
        {items.map((item) => (
          <li key={item.key}>
            <Link
              to={item.link}
              className="flex items-start gap-2.5 py-2.5 transition-colors hover:bg-secondary/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              data-testid={`action-${item.key}`}
            >
              <span className={cn("mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md border text-[11px] font-bold", TONES[item.severity] || TONES.neutral)}>
                {item.count > 99 ? "99+" : item.count}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[12.5px] font-semibold text-ink-1">{item.title}</p>
                <p className="text-[11.5px] leading-relaxed text-ink-3">{item.description}</p>
              </div>
              <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-ink-3" />
            </Link>
          </li>
        ))}
      </ul>
    ) : (
      <div className="flex items-center gap-2 py-6 text-[12.5px] text-ink-3">
        <CheckCircle2 className="h-4 w-4 text-success" /> Tidak ada pekerjaan mendesak pada filter ini.
      </div>
    )}
  </ChartCard>
);

const DEMO_TABS = [
  { key: "gender", label: "Jenis Kelamin", chart: "donut", filterKey: "gender" },
  { key: "age_bands", label: "Kelompok Usia", chart: "bars", filterKey: "age_band" },
  { key: "generation", label: "Generasi", chart: "donut", filterKey: null },
  { key: "marital_status", label: "Pernikahan", chart: "bars", filterKey: "marital_status" },
  { key: "religion", label: "Agama", chart: "bars", filterKey: "religion" },
  { key: "education", label: "Pendidikan", chart: "bars", filterKey: "education" },
  { key: "tenure_bands", label: "Masa Kerja", chart: "bars", filterKey: null },
  { key: "province", label: "Domisili", chart: "bars", filterKey: null },
  { key: "dependents", label: "Tanggungan", chart: "donut", filterKey: null },
];

export const DemographyWidget = ({ demography, filters = {}, onCrossFilter, chartOverride }) => {
  const [tab, setTab] = useState("gender");
  const active = DEMO_TABS.find((t) => t.key === tab) || DEMO_TABS[0];
  const items = demography?.[active.key] || [];
  const activeKey = active.filterKey ? filters[active.filterKey] : null;
  const missing = demography?.missing || {};
  const mode = chartOverride || active.chart;

  return (
    <ChartCard
      title="Profil Demografi Karyawan"
      subtitle={`Basis ${formatNumber(demography?.basis || 0)} karyawan. Klik kategori untuk memfilter dashboard.`}
      testId="dashboard-demography"
      footer={
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          <span>Rata-rata usia: <strong className="text-ink-1">{demography?.avg_age ?? "—"}</strong></span>
          <span>Rata-rata masa kerja: <strong className="text-ink-1">{demography?.avg_tenure ?? "—"}</strong></span>
          <span>Tanpa tanggal lahir: <strong className="text-ink-1">{formatNumber(missing.birth_date || 0)}</strong></span>
          <span>Tanpa pendidikan: <strong className="text-ink-1">{formatNumber(missing.education || 0)}</strong></span>
        </div>
      }
      actions={
        <Select value={tab} onValueChange={setTab}>
          <SelectTrigger className="h-8 w-[190px] text-[12px]" data-testid="demography-selector">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {DEMO_TABS.map((t) => <SelectItem key={t.key} value={t.key}>{t.label}</SelectItem>)}
          </SelectContent>
        </Select>
      }
    >
      {mode === "donut" ? (
        <DonutChart
          items={items}
          onSelect={active.filterKey && onCrossFilter ? (item) => onCrossFilter(active.filterKey, item.key) : undefined}
          activeKey={activeKey}
          testId="demography-chart"
        />
      ) : (
        <BarList
          items={items}
          onSelect={active.filterKey && onCrossFilter ? (item) => onCrossFilter(active.filterKey, item.key) : undefined}
          activeKey={activeKey}
          testId="demography-chart"
          emptyLabel="Belum ada data untuk kategori ini."
        />
      )}
    </ChartCard>
  );
};

const ORG_DIMENSIONS = [
  ["branch_id", "Unit Operasional", "branch_id"],
  ["project_id", "Proyek", "project_id"],
  ["work_location_id", "Lokasi Kerja", "work_location_id"],
  ["department_id", "Departemen", "department_id"],
  ["division_id", "Divisi", "division_id"],
  ["position_id", "Jabatan", "position_id"],
  ["job_grade_id", "Grade / Level", "job_grade_id"],
  ["cost_center_id", "Cost Center", "cost_center_id"],
  ["employment_status_id", "Status Kepegawaian", "employment_status_id"],
  ["business_status", "Status Karyawan", null],
  ["contract_type", "Tipe Kontrak", "contract_type_id"],
  ["roster_pattern", "Pola Roster", "roster_pattern_id"],
];

export const OrganizationWidget = ({ organization, filters = {}, onFilter }) => {
  const [dim, setDim] = useState("branch_id");
  const meta = ORG_DIMENSIONS.find(([key]) => key === dim) || ORG_DIMENSIONS[0];
  const block = organization?.dimensions?.[dim] || { items: [] };
  const coverage = organization?.coverage || {};
  const filterKey = meta[2];
  const activeKey = filterKey === "branch_id" ? filters.branch_id
    : filterKey === "project_id" ? filters.project_id
      : filterKey === "contract_type_id" ? filters.contract_type_id
        : filterKey === "roster_pattern_id" ? filters.roster_pattern_id
          : filterKey ? filters[filterKey] : null;

  return (
    <ChartCard
      title="Organisasi & Distribusi Tenaga Kerja"
      subtitle="Klik batang untuk memfilter seluruh dashboard pada dimensi tersebut."
      testId="dashboard-organization"
      footer={
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          <span>Sudah ditempatkan: <strong className="text-ink-1">{formatNumber(coverage.assigned || 0)}</strong> ({coverage.assigned_pct || 0}%)</span>
          <span>Belum ditempatkan: <strong className="text-ink-1">{formatNumber(coverage.unassigned || 0)}</strong></span>
        </div>
      }
      actions={
        <Select value={dim} onValueChange={setDim}>
          <SelectTrigger className="h-8 w-[190px] text-[12px]" data-testid="organization-dimension">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ORG_DIMENSIONS.map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}
          </SelectContent>
        </Select>
      }
    >
      {block.state === "not_supported" ? (
        <p className="py-6 text-[12.5px] leading-relaxed text-ink-3">{block.note}</p>
      ) : (
        <BarList
          items={block.items || []}
          onSelect={filterKey && onFilter ? (item) => onFilter(filterKey, item.key) : undefined}
          activeKey={activeKey}
          testId="organization-chart"
        />
      )}
    </ChartCard>
  );
};

export const MovementWidget = ({ movement }) => (
  <ChartCard
    title="Pergerakan Karyawan"
    subtitle="Masuk, keluar, dan pertumbuhan bersih per bulan pada periode terpilih."
    testId="dashboard-movement"
    footer={
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        <span>Masuk: <strong className="text-ink-1">{formatNumber(movement?.joined || 0)}</strong></span>
        <span>Keluar: <strong className="text-ink-1">{formatNumber(movement?.exited || 0)}</strong></span>
        <span>Net: <strong className="text-ink-1">{formatNumber(movement?.net_growth || 0)}</strong></span>
        <span>Mutasi penempatan: <strong className="text-ink-1">{formatNumber(movement?.mutations || 0)}</strong></span>
        <span>Turnover: <strong className="text-ink-1">{formatPct(movement?.turnover_pct, 2)}</strong></span>
      </div>
    }
  >
    <TrendChart
      data={(movement?.trend || []).map((row) => ({ ...row, month: row.month }))}
      series={[
        { key: "joined", label: "Masuk", color: "#087E70" },
        { key: "exited", label: "Keluar", color: "#B45309" },
      ]}
      testId="movement-trend"
    />
    {movement?.exits_by_type?.length ? (
      <div className="mt-3 border-t border-border pt-2.5">
        <p className="mb-1.5 text-[11.5px] font-semibold text-ink-2">Alasan keluar terbanyak</p>
        <BarList items={movement.exits_by_type} testId="movement-exit-types" />
      </div>
    ) : null}
  </ChartCard>
);

export const RecruitmentWidget = ({ recruitment }) => {
  if (!recruitment || recruitment.state === "inactive") {
    return <UnavailableWidget title="Rekrutmen" note="Modul Rekrutmen belum aktif atau Anda tidak memiliki akses." />;
  }
  return (
    <ChartCard
      title="Rekrutmen"
      subtitle="Pipeline kandidat dan konversi menjadi karyawan."
      testId="dashboard-recruitment"
      footer={<span>Waktu rekrut hingga diterima: <strong className="text-ink-1">{recruitment.time_to_hire_days ?? "—"} hari</strong></span>}
    >
      <div className="mb-3 grid gap-2 sm:grid-cols-3">
        <Metric label="Kandidat periode" value={formatNumber(recruitment.total_candidates || 0)} />
        <Metric label="Dalam proses" value={formatNumber(recruitment.pipeline || 0)} />
        <Metric label="Diterima" value={formatNumber(recruitment.hired || 0)} />
      </div>
      <BarList items={recruitment.funnel || []} testId="recruitment-funnel" />
    </ChartCard>
  );
};

export const RosterWidget = ({ roster }) => {
  if (!roster || roster.state === "inactive") {
    return <UnavailableWidget title="Roster & Cuti" note="Modul Roster & Mobilisasi belum aktif atau Anda tidak memiliki akses." />;
  }
  return (
    <ChartCard
      title="Agenda Roster, Cuti & Mobilisasi"
      subtitle="30 hari ke depan. Konfirmasi mengikuti kebijakan H-10 perusahaan."
      testId="dashboard-roster"
    >
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Sedang cuti" value={formatNumber(roster.on_leave || 0)} />
        <Metric label="Cuti ≤ 7 hari" value={formatNumber(roster.upcoming_7 || 0)} />
        <Metric label="Perlu konfirmasi" value={formatNumber(roster.need_confirmation || 0)} tone={roster.need_confirmation ? "warning" : undefined} />
        <Metric label="Mobilisasi pending" value={formatNumber(roster.mobilization_pending || 0)} tone={roster.mobilization_pending ? "warning" : undefined} />
      </div>
      <ul className="mt-3 divide-y divide-border">
        {(roster.agenda || []).slice(0, 8).map((item, index) => (
          <li key={`${item.kind}-${item.date}-${index}`} className="flex items-center gap-2 py-2">
            <span className="w-20 shrink-0 text-[11.5px] font-semibold tabular-nums text-ink-2">{item.date.slice(5)}</span>
            <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink-1">{item.label}</span>
            <Badge variant="outline" className="shrink-0 text-[10px]">{item.kind.replace("_", " ")}</Badge>
          </li>
        ))}
        {!(roster.agenda || []).length && (
          <li className="py-4 text-center text-[12.5px] text-ink-3">Tidak ada agenda pada 30 hari ke depan.</li>
        )}
      </ul>
      <div className="mt-2 flex justify-end">
        <Button asChild variant="outline" size="sm">
          <Link to="/modules/mobilization/rencana">Buka Roster <ChevronRight className="ml-1 h-3.5 w-3.5" /></Link>
        </Button>
      </div>
    </ChartCard>
  );
};

const ATT_LABELS = {
  present: "Hadir", late: "Terlambat", early_leave: "Pulang cepat",
  late_and_early_leave: "Terlambat & pulang cepat", no_check_out: "Belum absen pulang",
  awaiting_location_approval: "Menunggu approval lokasi", location_rejected: "Lokasi ditolak",
  day_off: "OFF", holiday: "Libur", leave: "Cuti", permission: "Izin", sick: "Sakit",
  unpaid_leave: "Cuti tidak dibayar", absent: "Alfa", no_schedule: "Tanpa jadwal",
};

export const AttendanceWidget = ({ attendance }) => {
  if (!attendance || attendance.state === "inactive") {
    return <UnavailableWidget title="Absensi" note="Modul Absensi belum aktif atau Anda tidak memiliki akses." />;
  }
  if (attendance.state === "no_data") {
    return <UnavailableWidget title="Absensi" note={attendance.note} />;
  }
  return (
    <ChartCard
      title="Absensi"
      subtitle="Rekap kehadiran pada periode filter."
      testId="dashboard-attendance"
      footer={
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          <span>Jam kerja aktual: <strong className="text-ink-1">{formatMinutes(attendance.work_minutes)}</strong></span>
          <span>Lembur disetujui: <strong className="text-ink-1">{formatMinutes(attendance.overtime_minutes)}</strong></span>
          <span>Catatan tidak valid: <strong className="text-ink-1">{formatNumber(attendance.invalid || 0)}</strong></span>
        </div>
      }
    >
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Tingkat kehadiran" value={attendance.attendance_rate_pct === null ? "—" : formatPct(attendance.attendance_rate_pct)} />
        <Metric label="Hadir" value={formatNumber(attendance.present || 0)} />
        <Metric label="Terlambat" value={formatNumber(attendance.late || 0)} tone={attendance.late ? "warning" : undefined} />
        <Metric label="Alfa" value={formatNumber(attendance.absent || 0)} tone={attendance.absent ? "critical" : undefined} />
      </div>
      <div className="mt-3">
        <BarList
          items={(attendance.by_status || []).map((row) => ({ ...row, label: ATT_LABELS[row.key] || row.label }))}
          testId="attendance-status-chart"
        />
      </div>
    </ChartCard>
  );
};

export const PayrollWidget = ({ payroll }) => {
  if (!payroll || payroll.state === "inactive" || payroll.state === "restricted") {
    return <UnavailableWidget title="Payroll & Biaya Tenaga Kerja" note="Memerlukan modul Payroll aktif dan izin payroll:view." />;
  }
  if (payroll.state === "no_data") {
    return <UnavailableWidget title="Payroll & Biaya Tenaga Kerja" note={payroll.note} />;
  }
  return (
    <ChartCard
      title="Payroll & Biaya Tenaga Kerja"
      subtitle={`Periode ${payroll.period} · status ${payroll.run_status}`}
      testId="dashboard-payroll"
      footer={
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          <span>BPJS karyawan: <strong className="text-ink-1">{formatMoney(payroll.bpjs_employee)}</strong></span>
          <span>BPJS perusahaan: <strong className="text-ink-1">{formatMoney(payroll.bpjs_employer)}</strong></span>
          <span>PPh 21: <strong className="text-ink-1">{formatMoney(payroll.pph21)}</strong></span>
          <span>Run belum dibayar: <strong className="text-ink-1">{formatNumber(payroll.outstanding_runs || 0)}</strong></span>
        </div>
      }
    >
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Total bruto" value={formatMoney(payroll.gross)} />
        <Metric label="Take home pay" value={formatMoney(payroll.net_pay)} />
        <Metric label="Potongan" value={formatMoney(payroll.total_deductions)} />
        <Metric label="Biaya perusahaan" value={formatMoney(payroll.employer_cost)} />
      </div>
      {(payroll.by_unit || []).length > 0 && (
        <div className="mt-3">
          <p className="mb-1.5 text-[11.5px] font-semibold text-ink-2">Biaya tenaga kerja per unit operasional</p>
          <BarList
            items={payroll.by_unit.map((row) => ({ key: row.label, label: row.label, count: row.value, pct: 0 }))}
            valueFormatter={formatMoney}
            hidePct
            testId="payroll-unit-chart"
          />
          <p className="mt-1 text-[11px] text-ink-3">Nilai dalam rupiah (biaya perusahaan per unit).</p>
        </div>
      )}
      {(payroll.trend || []).length > 0 && (
        <div className="mt-3">
          <p className="mb-1.5 text-[11.5px] font-semibold text-ink-2">Tren biaya perusahaan</p>
          <PeriodBars
            data={(payroll.trend || []).map((row) => ({ label: row.period, value: row.employer_cost }))}
            testId="payroll-trend"
          />
        </div>
      )}
    </ChartCard>
  );
};

export const CompetencyWidget = ({ competency }) => {
  const buckets = competency?.buckets || {};
  return (
    <ChartCard
      title="Kompetensi & Sertifikasi"
      subtitle={`${formatNumber(competency?.total || 0)} sertifikasi tercatat untuk karyawan pada filter aktif.`}
      testId="dashboard-competency"
      footer={<span>Riwayat pelatihan belum tersedia pada sistem.</span>}
    >
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Aktif" value={formatNumber(buckets.active || 0)} />
        <Metric label="Berakhir ≤ 90 hari" value={formatNumber(buckets.expiring_90 || 0)} tone={buckets.expiring_90 ? "warning" : undefined} />
        <Metric label="Kedaluwarsa" value={formatNumber(buckets.expired || 0)} tone={buckets.expired ? "critical" : undefined} />
        <Metric label="Tanpa masa berlaku" value={formatNumber(buckets.no_expiry || 0)} />
      </div>
      <div className="mt-3">
        <BarList items={competency?.by_type || []} testId="competency-type-chart" />
      </div>
    </ChartCard>
  );
};

export const AdministrationWidget = ({ administration }) => {
  const comp = administration?.completeness || {};
  const doc = administration?.document_expiry || {};
  const contract = administration?.contract_expiry || {};
  const profile = administration?.profile || {};
  const expiryItems = [
    { key: "7", label: "Berakhir ≤ 7 hari", count: doc["7"] || 0 },
    { key: "30", label: "8–30 hari", count: doc["30"] || 0 },
    { key: "60", label: "31–60 hari", count: doc["60"] || 0 },
    { key: "90", label: "61–90 hari", count: doc["90"] || 0 },
    { key: "expired", label: "Sudah kedaluwarsa", count: doc.expired || 0 },
  ];
  const totalDoc = expiryItems.reduce((sum, item) => sum + item.count, 0);
  return (
    <ChartCard
      title="Administrasi & Kepatuhan"
      subtitle="Kelengkapan data karyawan dan masa berlaku dokumen/kontrak."
      testId="dashboard-administration"
      footer={
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          <span>Kontrak ≤ 30 hari: <strong className="text-ink-1">{formatNumber((contract["7"] || 0) + (contract["30"] || 0))}</strong></span>
          <span>Kontrak kedaluwarsa: <strong className="text-ink-1">{formatNumber(contract.expired || 0)}</strong></span>
        </div>
      }
    >
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Rata-rata kelengkapan" value={comp.avg_pct === null || comp.avg_pct === undefined ? "—" : formatPct(comp.avg_pct)} />
        <Metric label="Sudah dievaluasi" value={formatNumber(comp.evaluated || 0)} />
        <Metric label="Belum dievaluasi" value={formatNumber(comp.not_evaluated || 0)} tone={comp.not_evaluated ? "warning" : undefined} />
        <Metric label="Tanpa foto profil" value={formatNumber(profile.without_photo || 0)} />
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <div>
          <p className="mb-1.5 text-[11.5px] font-semibold text-ink-2">Masa berlaku dokumen</p>
          <BarList
            items={expiryItems.map((item) => ({ ...item, pct: totalDoc ? Math.round((item.count / totalDoc) * 1000) / 10 : 0 }))}
            testId="document-expiry-chart"
          />
        </div>
        <div>
          <p className="mb-1.5 text-[11.5px] font-semibold text-ink-2">Kekurangan data administratif</p>
          <BarList
            items={[
              { key: "bank", label: "Tanpa rekening bank", count: profile.without_bank || 0, pct: 0 },
              { key: "npwp", label: "Tanpa NPWP", count: profile.without_npwp || 0, pct: 0 },
              { key: "bpjs", label: "Tanpa BPJS Kesehatan", count: profile.without_bpjs || 0, pct: 0 },
              { key: "emergency", label: "Tanpa kontak darurat", count: profile.without_emergency_contact || 0, pct: 0 },
            ]}
            hidePct
            testId="profile-gaps-chart"
          />
        </div>
      </div>
    </ChartCard>
  );
};

export const SelfWidget = ({ self }) => (
  <ChartCard title="Ringkasan Saya" subtitle="Data pribadi Anda pada periode berjalan." testId="dashboard-self">
    {self?.state !== "ready" ? (
      <p className="py-4 text-[12.5px] text-ink-3">{self?.note || "Data pribadi tidak tersedia."}</p>
    ) : (
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Hadir bulan ini" value={formatNumber(self.attendance_month?.present || 0)} hint={`${self.attendance_month?.late || 0} terlambat`} />
        <Metric label="Pengajuan cuti pending" value={formatNumber(self.pending_leave || 0)} />
        <Metric label="Dokumen berakhir ≤ 90 hari" value={formatNumber(self.documents_expiring_90 || 0)} tone={self.documents_expiring_90 ? "warning" : undefined} />
        <Metric label="Kelengkapan data" value={self.completeness_pct === null || self.completeness_pct === undefined ? "—" : formatPct(self.completeness_pct)} />
      </div>
    )}
  </ChartCard>
);

export const UnavailableWidget = ({ title, note }) => (
  <ChartCard title={title} testId={`dashboard-unavailable-${String(title).toLowerCase().replace(/\s+/g, "-")}`}>
    <div className="flex items-start gap-2 rounded-lg border border-border bg-secondary/60 px-3 py-3">
      <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-ink-3" />
      <p className="text-[12.5px] leading-relaxed text-ink-3">{note}</p>
    </div>
  </ChartCard>
);
