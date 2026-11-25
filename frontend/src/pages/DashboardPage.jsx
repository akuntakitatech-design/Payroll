import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown, ArrowUp, Download, LayoutDashboard, Maximize2, Minimize2, RefreshCw, Settings2,
  ShieldAlert,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import { downloadFile } from "@/lib/download";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger,
} from "@/components/ui/sheet";
import DashboardFilters from "@/components/dashboard/DashboardFilters";
import { ChoicePills } from "@/components/dashboard/charts";
import {
  ActionCenter, AdministrationWidget, AttendanceWidget, CompetencyWidget, DemographyWidget,
  InsightList, KpiGrid, MovementWidget, OrganizationWidget, PayrollWidget, RecruitmentWidget,
  RosterWidget, SelfWidget,
} from "@/components/dashboard/AnalyticsSections";
import {
  buildParams, fetchAnalytics, loadPrefs, savePrefs, DEFAULT_WIDGETS, periodRange,
} from "@/lib/dashboardAnalytics";
import { cn } from "@/lib/utils";

const TABS = [
  { key: "summary", label: "Ringkasan", tab: "ringkasan" },
  { key: "demography", label: "Demografi", tab: "demografi" },
  { key: "organization", label: "Organisasi & Manpower", tab: "organisasi" },
  { key: "movement", label: "Pergerakan Karyawan", tab: "pergerakan" },
  { key: "recruitment", label: "Rekrutmen", tab: "rekrutmen", module: "recruitment", resource: "recruitment" },
  { key: "roster", label: "Roster & Cuti", tab: "roster", module: "mobilization", resource: "roster" },
  { key: "attendance", label: "Absensi", tab: "absensi", module: "attendance" },
  { key: "payroll", label: "Payroll & Biaya", tab: "payroll", module: "payroll", resource: "payroll" },
  { key: "competency", label: "Kompetensi", tab: "kompetensi", module: "employee_core", resource: "certification" },
  { key: "administration", label: "Administrasi & Kepatuhan", tab: "administrasi", module: "employee_core" },
];

const WIDGET_META = {
  kpi: { label: "Executive KPI", mandatory: true },
  action_center: { label: "Action Center" },
  demography: { label: "Profil Demografi" },
  organization: { label: "Organisasi & Penempatan" },
  movement: { label: "Pergerakan Karyawan" },
  insights: { label: "Executive Insight" },
};

const CHART_TYPE_OPTIONS = [
  { key: "donut", label: "Donut" },
  { key: "bars", label: "Batang" },
];

const DashboardPage = () => {
  const { session, can, hasModule } = useAuth();
  const [tab, setTab] = useState("summary");
  const [preset, setPreset] = useState("this_month");
  const [custom, setCustom] = useState(() => periodRange("this_month"));
  const [filters, setFilters] = useState({});
  const [state, setState] = useState({ loading: true, error: "", data: null });
  const [reloadKey, setReloadKey] = useState(0);
  const [fullscreen, setFullscreen] = useState(false);
  const [prefs, setPrefs] = useState(() => loadPrefs(session));
  const abortRef = useRef(null);
  const rootRef = useRef(null);

  const canPeople = can("report", "view");
  const options = state.data?.filter_options || {};

  useEffect(() => { setPrefs(loadPrefs(session)); }, [session]);

  const visibleTabs = useMemo(
    () => TABS.filter((t) => {
      if (t.key === "summary") return true;
      if (t.resource && !can(t.resource, "view")) return false;
      if (t.module && !hasModule(t.module)) return false;
      if (t.key !== "payroll" && !canPeople) return false;
      return true;
    }),
    [can, hasModule, canPeople]
  );

  useEffect(() => {
    if (!visibleTabs.some((t) => t.key === tab)) setTab("summary");
  }, [visibleTabs, tab]);

  // Debounce filter/periode + batalkan permintaan sebelumnya (dedupe).
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const params = buildParams({ preset, custom, filters, category: tab });
      if (abortRef.current) abortRef.current.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setState((prev) => ({ ...prev, loading: true, error: "" }));
      fetchAnalytics(params, controller.signal)
        .then(({ data }) => setState({ loading: false, error: "", data }))
        .catch((error) => {
          if (error.name === "CanceledError" || error.code === "ERR_CANCELED") return;
          setState({ loading: false, error: error?.response?.data?.detail || "Gagal memuat analitik dashboard.", data: null });
        });
    }, 320);
    return () => window.clearTimeout(timer);
  }, [preset, custom, filters, tab, reloadKey]);

  useEffect(() => {
    document.title = "HR Command Center · HRIS Suite";
  }, []);

  useEffect(() => {
    const onFsChange = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onFsChange);
    return () => document.removeEventListener("fullscreenchange", onFsChange);
  }, []);

  const updatePrefs = useCallback((next) => {
    setPrefs(next);
    savePrefs(session, next);
  }, [session]);

  const setFilter = useCallback((key, value) => {
    setFilters((prev) => {
      const next = { ...prev };
      if (value) next[key] = value; else delete next[key];
      return next;
    });
  }, []);

  const resetFilters = useCallback(() => {
    setFilters({});
    setPreset("this_month");
    setCustom(periodRange("this_month"));
  }, []);

  const activeCount = Object.keys(filters).length;

  const saveFilterSet = useCallback((name) => {
    const saved = (prefs.savedFilters || []).filter((f) => f.name !== name);
    updatePrefs({ ...prefs, savedFilters: [...saved, { name, filters, preset, custom }] });
  }, [prefs, filters, preset, custom, updatePrefs]);

  const loadFilterSet = useCallback((name) => {
    const found = (prefs.savedFilters || []).find((f) => f.name === name);
    if (!found) return;
    setFilters(found.filters || {});
    setPreset(found.preset || "this_month");
    setCustom(found.custom || periodRange(found.preset || "this_month"));
  }, [prefs.savedFilters]);

  const deleteFilterSet = useCallback((name) => {
    updatePrefs({ ...prefs, savedFilters: (prefs.savedFilters || []).filter((f) => f.name !== name) });
  }, [prefs, updatePrefs]);

  const toggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) {
      document.exitFullscreen?.();
    } else {
      rootRef.current?.requestFullscreen?.();
    }
  }, []);

  const exportExcel = useCallback(() => {
    const params = buildParams({ preset, custom, filters, category: tab });
    downloadFile("/dashboard/analytics/export", `dashboard-${tab}.xlsx`, { params });
  }, [preset, custom, filters, tab]);

  const widgetOrder = prefs.order?.length ? prefs.order.filter((k) => WIDGET_META[k]) : [...DEFAULT_WIDGETS];
  const widgetVisible = (key) => WIDGET_META[key]?.mandatory || prefs.widgets?.[key] !== false;
  const moveWidget = (key, direction) => {
    const index = widgetOrder.indexOf(key);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= widgetOrder.length) return;
    const next = [...widgetOrder];
    [next[index], next[target]] = [next[target], next[index]];
    updatePrefs({ ...prefs, order: next });
  };
  const toggleWidget = (key, value) => {
    if (WIDGET_META[key]?.mandatory) return;
    updatePrefs({ ...prefs, widgets: { ...(prefs.widgets || {}), [key]: value } });
  };

  const data = state.data;
  const kpis = data?.kpis || [];
  const chartType = prefs.chartTypes?.demography || "donut";
  // Deret 6 bulan dari backend dipakai untuk sparkline di kartu KPI.
  const series = useMemo(() => {
    const trailing = data?.movement?.trailing || [];
    return {
      headcount: trailing.map((p) => p.headcount),
      joined: trailing.map((p) => p.joined),
      exited: trailing.map((p) => p.exited),
    };
  }, [data]);

  const renderSummary = () => {
    const blocks = {
      kpi: <KpiGrid kpis={kpis} series={series} />,
      action_center: <ActionCenter items={data?.action_center || []} />,
      demography: (
        <DemographyWidget
          demography={data?.demography}
          filters={filters}
          onCrossFilter={setFilter}
          chartOverride={chartType}
        />
      ),
      organization: <OrganizationWidget organization={data?.organization} filters={filters} onFilter={setFilter} />,
      movement: <MovementWidget movement={data?.movement} />,
      insights: <InsightList items={data?.insights || []} />,
    };
    const order = widgetOrder.filter(widgetVisible);
    const wide = new Set(["kpi"]);
    return (
      <div className="grid gap-4 xl:grid-cols-2">
        {order.map((key) => (
          <div key={key} className={cn("min-w-0", (wide.has(key) || key === "kpi") && "xl:col-span-2")}>
            {blocks[key]}
          </div>
        ))}
      </div>
    );
  };

  const renderTab = () => {
    if (tab === "summary") return renderSummary();
    return (
      <div className="grid gap-4">
        {canPeople && <KpiGrid kpis={kpis} series={series} testId="dashboard-kpi-grid-secondary" />}
        {tab === "demography" && (
          <div className="flex flex-wrap items-center justify-end gap-2" data-testid="dashboard-chart-type">
            <span className="text-[11.5px] font-medium text-ink-3">Tipe grafik</span>
            <ChoicePills
              options={CHART_TYPE_OPTIONS}
              value={chartType}
              onChange={(value) => updatePrefs({ ...prefs, chartTypes: { ...(prefs.chartTypes || {}), demography: value } })}
              ariaLabel="Tipe grafik demografi"
            />
          </div>
        )}
        <div className="grid gap-4 xl:grid-cols-2">
          {tab === "demography" && (
            <DemographyWidget demography={data?.demography} filters={filters} onCrossFilter={setFilter} chartOverride={chartType} />
          )}
          {tab === "organization" && (
            <OrganizationWidget organization={data?.organization} filters={filters} onFilter={setFilter} />
          )}
          {tab === "movement" && <MovementWidget movement={data?.movement} />}
          {tab === "recruitment" && <RecruitmentWidget recruitment={data?.recruitment} />}
          {tab === "roster" && <RosterWidget roster={data?.roster} />}
          {tab === "attendance" && <AttendanceWidget attendance={data?.attendance} />}
          {tab === "payroll" && <PayrollWidget payroll={data?.payroll} />}
          {tab === "competency" && <CompetencyWidget competency={data?.competency} />}
          {tab === "administration" && <AdministrationWidget administration={data?.administration} />}
          {(tab === "organization" || tab === "movement" || tab === "administration") && (
            <InsightList items={data?.insights || []} />
          )}
          {(tab === "demography" || tab === "recruitment" || tab === "roster" || tab === "attendance" || tab === "payroll" || tab === "competency") && (
            <ActionCenter items={data?.action_center || []} />
          )}
        </div>
      </div>
    );
  };

  return (
    <div ref={rootRef} className="min-h-full bg-background" data-testid="dashboard-root">
      <PageHeader
        title="HR Command Center"
        subtitle="Monitoring, analitik, dan tindakan operasional SDM dalam satu tempat."
        icon={LayoutDashboard}
        actions={
          <div className="flex flex-wrap items-center gap-1.5">
            <Button variant="outline" size="sm" onClick={() => setReloadKey((n) => n + 1)} data-testid="dashboard-refresh">
              <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", state.loading && "animate-spin")} />Refresh
            </Button>
            <Button variant="outline" size="sm" onClick={exportExcel} data-testid="dashboard-export">
              <Download className="mr-1.5 h-3.5 w-3.5" />Export
            </Button>
            <Button variant="outline" size="sm" onClick={toggleFullscreen} data-testid="dashboard-fullscreen">
              {fullscreen ? <Minimize2 className="mr-1.5 h-3.5 w-3.5" /> : <Maximize2 className="mr-1.5 h-3.5 w-3.5" />}
              {fullscreen ? "Keluar" : "Fullscreen"}
            </Button>
            <Sheet>
              <SheetTrigger asChild>
                <Button variant="outline" size="sm" data-testid="dashboard-settings">
                  <Settings2 className="mr-1.5 h-3.5 w-3.5" />Atur Dashboard
                </Button>
              </SheetTrigger>
              <SheetContent className="w-full sm:max-w-md">
                <SheetHeader>
                  <SheetTitle>Atur Dashboard</SheetTitle>
                  <SheetDescription>
                    Pilih widget yang tampil pada tab Ringkasan dan atur urutannya. Preferensi
                    disimpan per pengguna dan perusahaan. Widget wajib tidak dapat disembunyikan.
                  </SheetDescription>
                </SheetHeader>
                <div className="mt-4 space-y-2">
                  {widgetOrder.map((key, index) => {
                    const meta = WIDGET_META[key];
                    if (!meta) return null;
                    return (
                      <div key={key} className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2">
                        <div className="min-w-0 flex-1">
                          <Label className="text-[12.5px] font-semibold">{meta.label}</Label>
                          {meta.mandatory && <p className="text-[11px] text-ink-3">Widget wajib</p>}
                        </div>
                        <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => moveWidget(key, -1)}
                                disabled={index === 0} aria-label={`Naikkan ${meta.label}`}>
                          <ArrowUp className="h-3.5 w-3.5" />
                        </Button>
                        <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => moveWidget(key, 1)}
                                disabled={index === widgetOrder.length - 1} aria-label={`Turunkan ${meta.label}`}>
                          <ArrowDown className="h-3.5 w-3.5" />
                        </Button>
                        <Switch
                          checked={widgetVisible(key)}
                          disabled={meta.mandatory}
                          onCheckedChange={(v) => toggleWidget(key, v)}
                          aria-label={`Tampilkan ${meta.label}`}
                        />
                      </div>
                    );
                  })}
                </div>
                <div className="mt-4 border-t border-border pt-3">
                  <Button variant="outline" size="sm"
                          onClick={() => updatePrefs({ widgets: {}, order: [...DEFAULT_WIDGETS], savedFilters: prefs.savedFilters || [] })}
                          data-testid="dashboard-settings-reset">
                    Kembalikan ke default
                  </Button>
                  <p className="mt-2 text-[11px] leading-relaxed text-ink-3">
                    Urutan diatur dengan tombol naik/turun (drag-and-drop belum tersedia).
                  </p>
                </div>
              </SheetContent>
            </Sheet>
          </div>
        }
      />

      <DashboardFilters
        options={options}
        filters={filters}
        setFilter={setFilter}
        onReset={resetFilters}
        preset={preset}
        setPreset={setPreset}
        custom={custom}
        setCustom={setCustom}
        saved={prefs.savedFilters || []}
        onSave={saveFilterSet}
        onLoad={loadFilterSet}
        onDelete={deleteFilterSet}
        activeCount={activeCount}
        disabled={!canPeople}
      />

      {canPeople && (
        <div className="border-b border-border bg-card px-4 sm:px-6" data-testid="dashboard-tabs">
          <div className="flex gap-1 overflow-x-auto py-2">
            {visibleTabs.map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => setTab(item.key)}
                className={cn(
                  "shrink-0 rounded-lg border px-3 py-1.5 text-[12.5px] font-semibold transition-[box-shadow,transform,border-color] duration-150",
                  tab === item.key
                    ? "border-[#065F50] bg-[linear-gradient(180deg,#087E70_0%,#065F50_100%)] text-white shadow-[0_2px_0_#043F36,inset_0_1px_0_rgba(255,255,255,0.18)]"
                    : "border-border bg-[linear-gradient(180deg,#FFFFFF_0%,#F1F5F9_100%)] text-ink-2 shadow-[0_1px_0_#CBD5E1] hover:border-primary-border hover:text-ink-1",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                )}
                data-testid={`dashboard-tab-${item.key}`}
                aria-current={tab === item.key ? "page" : undefined}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      )}

      <PageBody>
        {state.loading && !data && (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" data-testid="dashboard-loading">
            {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-28 w-full" />)}
            <Skeleton className="h-64 w-full xl:col-span-3" />
          </div>
        )}

        {state.error && (
          <Card className="p-5" data-testid="dashboard-error">
            <div className="flex items-start gap-3">
              <ShieldAlert className="mt-0.5 h-5 w-5 text-danger" />
              <div>
                <p className="text-sm font-semibold text-ink-1">Analitik belum dapat dimuat</p>
                <p className="mt-1 text-[12.5px] text-ink-3">{state.error}</p>
                <Button variant="outline" size="sm" className="mt-3" onClick={() => setReloadKey((n) => n + 1)}>
                  <RefreshCw className="mr-1.5 h-3.5 w-3.5" />Coba lagi
                </Button>
              </div>
            </div>
          </Card>
        )}

        {data && (
          <>
            {!canPeople && (
              <div className="mb-3 rounded-lg border border-border bg-card px-3 py-2.5 text-[12.5px] text-ink-3" data-testid="dashboard-restricted-note">
                Akun Anda tidak memiliki izin analitik lintas karyawan. Yang ditampilkan hanya ringkasan pribadi.
              </div>
            )}
            {!canPeople && <SelfWidget self={data.self} />}
            {canPeople && renderTab()}
            {state.loading && (
              <div className="pointer-events-none fixed inset-x-0 top-0 z-40 h-0.5 bg-primary/20" data-testid="dashboard-loading-bar">
                <div className="h-full w-1/3 animate-pulse bg-primary" />
              </div>
            )}
          </>
        )}
      </PageBody>
    </div>
  );
};

export default DashboardPage;
