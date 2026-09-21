import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, ClipboardCheck, RefreshCw, XCircle } from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { PageBody, SectionHeader } from "@/components/common/PageHeader";
import EmptyState from "@/components/common/EmptyState";
import ToneBadge from "@/components/time/ToneBadge";
import DecisionDialog from "@/components/time/DecisionDialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";
import { dayLabel, minutesToLabel } from "@/lib/timeCatalog";
import { formatDateTime } from "@/lib/format";

const LeaveOvertimeApprovalsPage = () => {
  const { can } = useAuth();
  const [leaveItems, setLeaveItems] = useState([]);
  const [overtimeItems, setOvertimeItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialog, setDialog] = useState(null); // { kind, item, mode }
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [l, o] = await Promise.all([api.get("/leave/approvals"), api.get("/overtime/approvals")]);
      setLeaveItems(l.data?.items || []);
      setOvertimeItems(o.data?.items || []);
    } catch (error) {
      toast.error(errorMessage(error, "Daftar persetujuan tidak dapat dimuat."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const decide = async ({ notes, approved_minutes }) => {
    if (!dialog) return;
    const { kind, item, mode } = dialog;
    const requestId = item.approval.record_id;
    const approvalId = item.approval.id;
    const url =
      kind === "leave"
        ? `/leave/requests/${requestId}/approvals/${approvalId}/decide`
        : `/overtime/requests/${requestId}/approvals/${approvalId}/decide`;
    setSubmitting(true);
    try {
      const payload = { decision: mode === "approve" ? "approved" : "rejected", notes };
      if (kind === "overtime" && approved_minutes !== undefined && approved_minutes !== null) {
        payload.approved_minutes = approved_minutes;
      }
      const { data } = await api.post(url, payload);
      toast.success(data?.message || "Keputusan tersimpan.");
      setDialog(null);
      load();
    } catch (error) {
      toast.error(errorMessage(error, "Keputusan tidak dapat disimpan."), { duration: 9000 });
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <PageBody>
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </PageBody>
    );
  }

  const empty = leaveItems.length === 0 && overtimeItems.length === 0;

  return (
    <PageBody>
      <SectionHeader
        title="Persetujuan Cuti & Lembur"
        description="Pengajuan yang menunggu keputusan Anda pada tahap yang aktif."
        actions={
          <Button variant="ghost" onClick={load} data-testid="lo-approvals-refresh">
            <RefreshCw className="mr-2 h-4 w-4" /> Muat Ulang
          </Button>
        }
      />

      {empty ? (
        <EmptyState
          icon={ClipboardCheck}
          title="Tidak ada pengajuan yang menunggu keputusan Anda."
          description="Pengajuan cuti dan lembur akan muncul di sini bila Anda menjadi penyetuju pada tahap aktif."
          testId="lo-approvals-empty"
        />
      ) : (
        <div className="grid gap-3 lg:grid-cols-2" data-testid="lo-approvals-list">
          {leaveItems.map((item) => {
            const a = item.approval;
            const d = item.detail || {};
            return (
              <Card key={a.id} data-testid={`leave-approval-card-${a.id}`}>
                <CardHeader className="pb-2">
                  <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
                    {d.employee_name || "-"}
                    <ToneBadge tone="warning" label={d.leave_type_name || a.document_label} />
                  </CardTitle>
                  <CardDescription>
                    {dayLabel(d.start_date)} s/d {dayLabel(d.end_date)} · {d.working_days} hari kerja · Tahap{" "}
                    {a.step_order}: {a.step_name}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <dl className="grid grid-cols-2 gap-2 text-[13px]">
                    <div>
                      <dt className="text-[12px] text-muted-foreground">Bagian Hari</dt>
                      <dd className="font-medium">{d.day_part_label || "-"}</dd>
                    </div>
                    <div>
                      <dt className="text-[12px] text-muted-foreground">Kurangi Saldo</dt>
                      <dd className="font-medium">{d.deduct_balance ? "Ya" : "Tidak"}</dd>
                    </div>
                    <div className="col-span-2">
                      <dt className="text-[12px] text-muted-foreground">Alasan</dt>
                      <dd className="font-medium">{d.reason || "-"}</dd>
                    </div>
                    <div className="col-span-2">
                      <dt className="text-[12px] text-muted-foreground">Diajukan</dt>
                      <dd className="font-medium">{formatDateTime(a.submitted_at)}</dd>
                    </div>
                  </dl>
                  {can("leave", "approve") && (
                    <div className="flex flex-wrap gap-2">
                      <Button size="sm" onClick={() => setDialog({ kind: "leave", item, mode: "approve" })} data-testid={`leave-approve-${a.id}`}>
                        <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" /> Setujui
                      </Button>
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => setDialog({ kind: "leave", item, mode: "reject" })}
                        data-testid={`leave-reject-${a.id}`}
                      >
                        <XCircle className="mr-1.5 h-3.5 w-3.5" /> Tolak
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}

          {overtimeItems.map((item) => {
            const a = item.approval;
            const d = item.detail || {};
            return (
              <Card key={a.id} data-testid={`overtime-approval-card-${a.id}`}>
                <CardHeader className="pb-2">
                  <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
                    {d.employee_name || "-"}
                    <ToneBadge tone="warning" label="Lembur" />
                  </CardTitle>
                  <CardDescription>
                    {dayLabel(d.work_date)} · {d.planned_start_time} - {d.planned_end_time} · Tahap {a.step_order}:{" "}
                    {a.step_name}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <dl className="grid grid-cols-2 gap-2 text-[13px]">
                    <div>
                      <dt className="text-[12px] text-muted-foreground">Menit Diajukan</dt>
                      <dd className="font-medium">{minutesToLabel(d.requested_minutes)}</dd>
                    </div>
                    <div>
                      <dt className="text-[12px] text-muted-foreground">Menit Aktual (perkiraan)</dt>
                      <dd className="font-medium">{minutesToLabel(d.actual_preview?.actual_minutes)}</dd>
                    </div>
                    <div className="col-span-2">
                      <dt className="text-[12px] text-muted-foreground">Alasan</dt>
                      <dd className="font-medium">{d.reason || "-"}</dd>
                    </div>
                    {d.actual_preview?.note && (
                      <div className="col-span-2">
                        <dt className="text-[12px] text-muted-foreground">Catatan Sistem</dt>
                        <dd className="font-medium">{d.actual_preview.note}</dd>
                      </div>
                    )}
                  </dl>
                  {can("leave", "approve") && (
                    <div className="flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        onClick={() => setDialog({ kind: "overtime", item, mode: "approve" })}
                        data-testid={`overtime-approve-${a.id}`}
                      >
                        <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" /> Setujui
                      </Button>
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => setDialog({ kind: "overtime", item, mode: "reject" })}
                        data-testid={`overtime-reject-${a.id}`}
                      >
                        <XCircle className="mr-1.5 h-3.5 w-3.5" /> Tolak
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <DecisionDialog
        open={!!dialog}
        onOpenChange={(o) => !o && setDialog(null)}
        mode={dialog?.mode}
        title={
          dialog?.mode === "reject"
            ? dialog?.kind === "leave"
              ? "Tolak Pengajuan Cuti"
              : "Tolak Pengajuan Lembur"
            : dialog?.kind === "leave"
            ? "Setujui Pengajuan Cuti"
            : "Setujui Pengajuan Lembur"
        }
        description={dialog?.item?.detail?.employee_name}
        submitting={submitting}
        onSubmit={decide}
        showApprovedMinutes={dialog?.kind === "overtime"}
        defaultApprovedMinutes={
          dialog?.kind === "overtime"
            ? dialog?.item?.detail?.actual_preview?.rounded_minutes ?? dialog?.item?.detail?.requested_minutes
            : undefined
        }
      />
    </PageBody>
  );
};

export default LeaveOvertimeApprovalsPage;
