import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  CalendarClock,
  ClipboardCheck,
  FileSignature,
  Handshake,
  Hourglass,
  Plus,
  RefreshCw,
  ShieldCheck,
  UserCheck,
  UserPlus,
  UserX,
  Users,
} from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate, formatDateTime } from "@/lib/format";
import { HISTORY_ACTION_LABELS, RECRUITMENT_ROUTES } from "@/lib/recruitment";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import EmptyState from "@/components/common/EmptyState";
import StageBadge from "@/components/recruitment/StageBadge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

const TONES = {
  default: "border-primary-border bg-primary-soft text-primary",
  success: "border-success-border bg-success-soft text-success",
  warning: "border-warning-border bg-warning-soft text-warning",
  critical: "border-danger-border bg-danger-soft text-danger",
};

const StatTile = ({ label, value, hint, icon: Icon, tone = "default", testId, to }) => {
  const inner = (
    <div className="rounded-lg border border-border bg-card px-4 py-3 transition-colors hover:border-primary/40" data-testid={testId}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-[12px] text-muted-foreground">{label}</p>
        {Icon && (
          <span className={`flex h-7 w-7 items-center justify-center rounded-md border ${TONES[tone]}`}>
            <Icon className="h-3.5 w-3.5" strokeWidth={1.75} />
          </span>
        )}
      </div>
      <p className="mt-1 text-2xl font-semibold leading-tight text-foreground" data-numeric="true">
        {value}
      </p>
      {hint && <p className="mt-0.5 text-[12px] text-muted-foreground">{hint}</p>}
    </div>
  );
  return to ? (
    <Link to={to} className="block rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
      {inner}
    </Link>
  ) : (
    inner
  );
};

const Panel = ({ title, description, action, children, testId }) => (
  <section className="overflow-hidden rounded-lg border border-border bg-card" data-testid={testId}>
    <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
      <div>
        <h2 className="text-section-title">{title}</h2>
        {description && <p className="text-[12px] text-muted-foreground">{description}</p>}
      </div>
      {action}
    </div>
    {children}
  </section>
);

const RecruitmentDashboardPage = () => {
  const { can, company } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.get("/recruitment/summary");
      setData(res.data);
    } catch (err) {
      const msg = errorMessage(err, "Ringkasan rekrutmen tidak dapat dimuat.");
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    document.title = "Rekrutmen · HRIS Suite";
  }, [load, company?.id]);

  const candidatesUrl = (stage) => `${RECRUITMENT_ROUTES.candidates}${stage ? `?stage_status=${stage}` : ""}`;

  return (
    <>
      <PageHeader
        title="Rekrutmen"
        subtitle="Kandidat masuk, screening, interview, approval, dan offering untuk perusahaan aktif."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={load} disabled={loading} data-testid="recruitment-refresh">
              <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} /> Muat ulang
            </Button>
            <Button variant="outline" onClick={() => navigate(RECRUITMENT_ROUTES.candidates)} data-testid="recruitment-open-candidates">
              <Users className="mr-2 h-4 w-4" /> Daftar Kandidat
            </Button>
            {can("recruitment", "create") && (
              <Button onClick={() => navigate(`${RECRUITMENT_ROUTES.candidates}?new=1`)} data-testid="recruitment-add-candidate">
                <Plus className="mr-2 h-4 w-4" /> Tambah Kandidat
              </Button>
            )}
          </div>
        }
      />
      <PageBody>
        {loading && !data ? (
          <div className="space-y-4" data-testid="recruitment-dashboard-loading">
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-24 w-full" />
              ))}
            </div>
            <Skeleton className="h-64 w-full" />
          </div>
        ) : error && !data ? (
          <div className="rounded-lg border border-border bg-card" data-testid="recruitment-dashboard-error">
            <EmptyState
              icon={Activity}
              title="Ringkasan tidak dapat dimuat."
              description={error}
              actionLabel="Coba lagi"
              onAction={load}
            />
          </div>
        ) : (
          <div className="space-y-4" data-testid="recruitment-dashboard">
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatTile
                label="Kandidat Aktif"
                value={data.active}
                hint={`${data.total} kandidat tercatat`}
                icon={Users}
                testId="stat-active"
                to={candidatesUrl("")}
              />
              <StatTile
                label="Screening"
                value={data.screening}
                hint={`${data.draft} draft menunggu dimulai`}
                icon={ClipboardCheck}
                tone="warning"
                testId="stat-screening"
                to={candidatesUrl("screening")}
              />
              <StatTile
                label="Lolos Screening"
                value={data.screening_passed}
                hint="Siap dijadwalkan interview"
                icon={UserCheck}
                tone="success"
                testId="stat-passed"
                to={candidatesUrl("screening_passed")}
              />
              <StatTile
                label="Tidak Lolos"
                value={data.screening_failed}
                hint="Dihentikan pada screening"
                icon={UserX}
                tone="critical"
                testId="stat-failed"
                to={candidatesUrl("screening_failed")}
              />
            </div>

            <div className="grid grid-cols-2 gap-3 lg:grid-cols-5" data-testid="stat-pipeline">
              <StatTile
                label="Interview Dijadwalkan"
                value={data.interview_scheduled ?? 0}
                hint={`${data.interview_done ?? 0} interview selesai`}
                icon={CalendarClock}
                testId="stat-interview"
                to={candidatesUrl("interview_scheduled")}
              />
              <StatTile
                label="Menunggu Approval"
                value={data.awaiting_approval ?? 0}
                hint={`${data.rejected ?? 0} ditolak approval`}
                icon={Hourglass}
                tone="warning"
                testId="stat-awaiting-approval"
                to={candidatesUrl("awaiting_approval")}
              />
              <StatTile
                label="Approved"
                value={data.approved ?? 0}
                hint="Siap dibuatkan offering"
                icon={ShieldCheck}
                tone="success"
                testId="stat-approved"
                to={candidatesUrl("approved")}
              />
              <StatTile
                label="Offering Aktif"
                value={data.offering_active ?? 0}
                hint={`${data.offering_declined ?? 0} offering ditolak`}
                icon={FileSignature}
                testId="stat-offering"
                to={candidatesUrl("offering")}
              />
              <StatTile
                label="Offering Diterima"
                value={data.offering_accepted ?? 0}
                hint="Siap onboarding (Tahap C)"
                icon={Handshake}
                tone="success"
                testId="stat-offering-accepted"
                to={candidatesUrl("offering_accepted")}
              />
            </div>

            <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
              <div className="xl:col-span-3">
                <Panel
                  title="Kandidat Terbaru"
                  description="Enam kandidat yang paling baru ditambahkan."
                  testId="recent-candidates-panel"
                  action={
                    <Button variant="ghost" size="sm" onClick={() => navigate(RECRUITMENT_ROUTES.candidates)} data-testid="recent-candidates-all">
                      Semua <ArrowRight className="ml-1 h-3.5 w-3.5" />
                    </Button>
                  }
                >
                  {data.recent_candidates.length === 0 ? (
                    <EmptyState
                      icon={UserPlus}
                      title="Belum ada kandidat."
                      description="Tambahkan kandidat pertama dari input HR. Portal pelamar publik menyusul pada fase berikutnya."
                      actionLabel={can("recruitment", "create") ? "Tambah Kandidat" : undefined}
                      onAction={() => navigate(`${RECRUITMENT_ROUTES.candidates}?new=1`)}
                    />
                  ) : (
                    <ul className="divide-y divide-border" data-testid="recent-candidates-list">
                      {data.recent_candidates.map((c) => (
                        <li key={c.id}>
                          <Link
                            to={RECRUITMENT_ROUTES.candidate(c.id)}
                            className="flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-muted/60 focus-visible:outline-none focus-visible:bg-muted/60"
                            data-testid={`recent-candidate-${c.id}`}
                          >
                            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                              <UserPlus className="h-4 w-4" />
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-[13px] font-medium">{c.full_name}</span>
                              <span className="block truncate text-[12px] text-muted-foreground">
                                {c.candidate_number}
                                {c.position_name || c.applied_position_title
                                  ? ` · ${c.position_name || c.applied_position_title}`
                                  : ""}
                                {c.applied_at ? ` · ${formatDate(c.applied_at)}` : ""}
                              </span>
                            </span>
                            <StageBadge stage={c.stage_status} label={c.stage_label} tone={c.stage_tone} />
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </Panel>
              </div>

              <div className="xl:col-span-2">
                <Panel title="Aktivitas Terbaru" description="Perubahan status dan hasil screening." testId="recent-activity-panel">
                  {data.recent_activity.length === 0 ? (
                    <EmptyState
                      icon={Activity}
                      title="Belum ada aktivitas."
                      description="Aktivitas muncul saat kandidat dibuat, screening dimulai, atau hasil screening diisi."
                    />
                  ) : (
                    <ul className="divide-y divide-border" data-testid="recent-activity-list">
                      {data.recent_activity.map((a) => (
                        <li key={a.id} className="px-4 py-2.5">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <p className="truncate text-[13px] font-medium">
                                {a.candidate_name || "Kandidat"}{" "}
                                <span className="font-normal text-muted-foreground">· {HISTORY_ACTION_LABELS[a.action] || a.action}</span>
                              </p>
                              <p className="text-[12px] text-muted-foreground">
                                {a.from_label ? `${a.from_label} → ` : ""}
                                {a.to_label || "-"}
                                {a.changed_by_name ? ` · ${a.changed_by_name}` : ""}
                              </p>
                            </div>
                            <span className="shrink-0 text-[11px] text-muted-foreground">{formatDateTime(a.changed_at)}</span>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </Panel>
              </div>
            </div>
          </div>
        )}
      </PageBody>
    </>
  );
};

export default RecruitmentDashboardPage;
