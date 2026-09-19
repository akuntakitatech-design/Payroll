import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  BadgeCheck,
  CalendarClock,
  CalendarDays,
  ChevronRight,
  FileSignature,
  FileText,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import { FilterSelect } from "@/components/common/DataTable";
import EmptyState from "@/components/common/EmptyState";
import { ExpiryBadge } from "@/components/common/StatusBadge";
import ContractRenewDialog from "@/components/payroll/ContractRenewDialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

const KIND_ICONS = {
  contract: FileSignature,
  certification: BadgeCheck,
  document: FileText,
};

const SummaryTile = ({ label, value, hint, icon: Icon, tone = "default", active, onClick, testId }) => {
  const tones = {
    default: "text-foreground",
    warning: "text-[hsl(38,80%,28%)]",
    critical: "text-destructive",
  };
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testId}
      className={`rounded-lg border bg-card p-4 text-left transition-transform duration-150 hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
        active ? "border-primary ring-1 ring-primary/30" : "border-border"
      }`}
    >
      <div className="flex items-center justify-between">
        <p className="text-[12px] text-muted-foreground">{label}</p>
        {Icon && <Icon className="h-4 w-4 text-muted-foreground" />}
      </div>
      <p className={`mt-2 text-xl font-semibold ${tones[tone]}`} data-numeric="true">
        {value}
      </p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </button>
  );
};

const ExpiryCalendarPage = () => {
  const navigate = useNavigate();
  const { company, can } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [renewContractId, setRenewContractId] = useState(null);

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(Number(searchParams.get("days")) || 90);
  const [kind, setKind] = useState(searchParams.get("kind") || "");
  const [state, setState] = useState(searchParams.get("state") || "");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { days };
      if (kind) params.kind = kind;
      if (state) params.state = state;
      const res = await api.get("/reminders/expiry", { params });
      setData(res.data);
    } catch (err) {
      toast.error(errorMessage(err, "Kalender masa berlaku tidak dapat dimuat."));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [days, kind, state]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    document.title = "Kalender Masa Berlaku · HRIS Suite";
  }, [company?.id]);

  useEffect(() => {
    const next = {};
    if (days !== 90) next.days = String(days);
    if (kind) next.kind = kind;
    if (state) next.state = state;
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days, kind, state]);

  const summary = data?.summary;
  const months = useMemo(() => data?.months || [], [data]);
  const hasFilters = !!kind || !!state || days !== 90;

  return (
    <>
      <PageHeader
        title="Kalender Masa Berlaku"
        subtitle="Pantau kontrak, sertifikasi, dan dokumen yang akan berakhir."
        actions={
          <Button variant="outline" onClick={load} data-testid="reminders-refresh">
            <RefreshCw className="mr-2 h-4 w-4" /> Muat ulang
          </Button>
        }
      />
      <PageBody>
        {loading && !data ? (
          <>
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-64 w-full" />
          </>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <SummaryTile
                label="Sudah Kedaluwarsa"
                value={summary?.expired ?? 0}
                hint="Perlu tindakan segera"
                icon={AlertTriangle}
                tone={summary?.expired ? "critical" : "default"}
                active={state === "expired"}
                onClick={() => setState(state === "expired" ? "" : "expired")}
                testId="summary-expired"
              />
              <SummaryTile
                label="Segera Berakhir"
                value={summary?.due_soon ?? 0}
                hint={`Dalam ${data?.policy_reminder_days ?? 30} hari (kebijakan perusahaan)`}
                icon={CalendarClock}
                tone={summary?.due_soon ? "warning" : "default"}
                active={state === "due_soon"}
                onClick={() => setState(state === "due_soon" ? "" : "due_soon")}
                testId="summary-due-soon"
              />
              <SummaryTile
                label="Masih Aman"
                value={summary?.ok ?? 0}
                hint="Belum perlu tindakan"
                icon={ShieldCheck}
                testId="summary-ok"
              />
              <SummaryTile
                label="Total Dipantau"
                value={summary?.total ?? 0}
                hint="Kontrak + sertifikasi + dokumen"
                icon={CalendarDays}
                testId="summary-total"
              />
            </div>

            <div className="flex flex-col gap-3 rounded-lg border border-border bg-card p-3 sm:flex-row sm:flex-wrap sm:items-end">
              <FilterSelect
                label="Rentang waktu"
                value={String(days)}
                onChange={(v) => setDays(Number(v) || 90)}
                options={[
                  { value: "30", label: "30 hari ke depan" },
                  { value: "60", label: "60 hari ke depan" },
                  { value: "90", label: "90 hari ke depan" },
                  { value: "180", label: "6 bulan ke depan" },
                  { value: "365", label: "1 tahun ke depan" },
                ]}
                allLabel="90 hari ke depan"
                testId="filter-window"
              />
              <FilterSelect
                label="Jenis data"
                value={kind}
                onChange={setKind}
                options={(data?.available_kinds || []).map((k) => ({ value: k.key, label: k.label }))}
                allLabel="Semua jenis"
                testId="filter-kind"
              />
              <FilterSelect
                label="Kondisi"
                value={state}
                onChange={setState}
                options={[
                  { value: "expired", label: "Sudah kedaluwarsa" },
                  { value: "due_soon", label: "Segera berakhir" },
                ]}
                allLabel="Semua kondisi"
                testId="filter-state"
              />
              {hasFilters && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-9 self-end text-muted-foreground"
                  onClick={() => {
                    setKind("");
                    setState("");
                    setDays(90);
                  }}
                  data-testid="reminders-reset"
                >
                  Hapus filter
                </Button>
              )}
            </div>

            {months.length === 0 ? (
              <EmptyState
                icon={CalendarDays}
                title="Tidak ada masa berlaku yang perlu ditindak."
                description={`Tidak ada kontrak, sertifikasi, atau dokumen yang berakhir dalam ${days} hari ke depan pada filter ini.`}
                testId="reminders-empty"
              />
            ) : (
              <div className="space-y-4" data-testid="reminders-calendar">
                {months.map((month) => (
                  <div
                    key={month.key}
                    className="overflow-hidden rounded-lg border border-border bg-card"
                    data-testid={`reminder-month-${month.key}`}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3">
                      <h2 className="text-section-title">{month.label}</h2>
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        {month.expired > 0 && (
                          <span className="rounded-full border border-[hsl(0,50%,85%)] bg-[hsl(0,72%,95%)] px-2 py-0.5 font-medium text-[hsl(0,72%,35%)]">
                            {month.expired} kedaluwarsa
                          </span>
                        )}
                        {month.due_soon > 0 && (
                          <span className="rounded-full border border-[hsl(43,40%,80%)] bg-[hsl(43,74%,92%)] px-2 py-0.5 font-medium text-[hsl(38,80%,28%)]">
                            {month.due_soon} segera berakhir
                          </span>
                        )}
                        <span>{month.items.length} item</span>
                      </div>
                    </div>
                    <ul className="divide-y divide-border">
                      {month.items.map((item) => {
                        const Icon = KIND_ICONS[item.kind] || FileText;
                        const canRenew = item.kind === "contract" && can("contract", "create");
                        return (
                          <li key={`${item.kind}-${item.id}`} className="flex items-stretch">
                            <button
                              type="button"
                              onClick={() => navigate(item.link)}
                              className="flex min-w-0 flex-1 items-center gap-3 px-4 py-3 text-left transition-colors duration-150 hover:bg-secondary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                              data-testid={`reminder-item-${item.kind}-${item.id}`}
                            >
                              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-secondary text-secondary-foreground">
                                <Icon className="h-4 w-4" />
                              </span>
                              <span className="min-w-0 flex-1">
                                <span className="flex flex-wrap items-center gap-2">
                                  <span className="truncate font-medium">{item.title}</span>
                                  <ExpiryBadge state={item.state} daysLeft={item.days_left} />
                                </span>
                                <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                                  {item.kind_label} · {item.subtitle}
                                  {item.person_name ? ` · ${item.person_name}` : ""} · berakhir{" "}
                                  {formatDate(item.expiry_date)}
                                </span>
                              </span>
                              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                            </button>
                            {canRenew && (
                              <div className="flex items-center pr-3">
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => setRenewContractId(item.id)}
                                  data-testid={`reminder-renew-${item.id}`}
                                >
                                  <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Perpanjang
                                </Button>
                              </div>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </PageBody>

      <ContractRenewDialog
        contractId={renewContractId}
        open={!!renewContractId}
        onClose={() => setRenewContractId(null)}
        onRenewed={() => load()}
      />
    </>
  );
};

export default ExpiryCalendarPage;
