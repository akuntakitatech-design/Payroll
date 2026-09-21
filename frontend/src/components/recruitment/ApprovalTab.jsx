import React, { useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle2, Circle, CircleDot, Loader2, Send, Settings2, XCircle } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import EmptyState from "@/components/common/EmptyState";
import StageBadge from "@/components/recruitment/StageBadge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const StepIcon = ({ step }) => {
  if (step.decision === "approved") return <CheckCircle2 className="h-5 w-5 text-success" />;
  if (step.decision === "rejected") return <XCircle className="h-5 w-5 text-danger" />;
  if (step.is_current) return <CircleDot className="h-5 w-5 text-warning" />;
  return <Circle className="h-5 w-5 text-muted-foreground/60" />;
};

/**
 * Tab Approval: visual langkah approval (snapshot dari konfigurasi Alur
 * Persetujuan existing). Tombol Setujui/Tolak hanya untuk approver tahap aktif.
 */
export const ApprovalTab = ({ candidate, approval, onChanged }) => {
  const { can } = useAuth();
  const [submitOpen, setSubmitOpen] = useState(false);
  const [submitNotes, setSubmitNotes] = useState("");
  const [decide, setDecide] = useState(null); // {step, decision}
  const [decideNotes, setDecideNotes] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const stage = candidate.stage_status;
  const rounds = approval?.rounds || [];
  const currentRound = rounds.length ? rounds[rounds.length - 1] : null;

  const runSubmit = async () => {
    setBusy(true);
    setError("");
    try {
      await api.post(`/recruitment/candidates/${candidate.id}/submit-approval`, { notes: submitNotes || undefined });
      toast.success("Kandidat diajukan untuk approval.");
      setSubmitOpen(false);
      setSubmitNotes("");
      onChanged?.();
    } catch (err) {
      setError(errorMessage(err, "Pengajuan approval gagal."));
    } finally {
      setBusy(false);
    }
  };

  const runDecide = async () => {
    setBusy(true);
    setError("");
    try {
      await api.post(`/recruitment/candidates/${candidate.id}/approvals/${decide.step.id}/decide`, {
        decision: decide.decision,
        notes: decideNotes || undefined,
      });
      toast.success(decide.decision === "approved" ? "Tahap approval disetujui." : "Kandidat ditolak pada tahap ini.");
      setDecide(null);
      setDecideNotes("");
      onChanged?.();
    } catch (err) {
      setError(errorMessage(err, "Keputusan tidak dapat disimpan."));
    } finally {
      setBusy(false);
    }
  };

  const workflowMissing = approval && !approval.workflow_available;

  return (
    <div className="space-y-3" data-testid="approval-tab">
      {/* Konfigurasi workflow */}
      {workflowMissing ? (
        <div
          className="flex flex-col gap-3 rounded-lg border border-warning-border bg-warning-soft px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
          data-testid="approval-workflow-missing"
        >
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-warning" />
            <div>
              <p className="text-sm font-semibold text-foreground">Workflow approval Recruitment belum dikonfigurasi.</p>
              <p className="text-[12px] text-muted-foreground">
                Pengajuan approval tidak dapat diteruskan sampai perusahaan memiliki Alur Persetujuan dengan jenis dokumen Rekrutmen. Tidak ada penyetuju default otomatis.
              </p>
            </div>
          </div>
          {can("approval_workflow", "create") && (
            <Button asChild variant="outline" size="sm" data-testid="approval-config-link">
              <Link to={approval.config_route || "/setup/approval-workflows"}>
                <Settings2 className="mr-2 h-4 w-4" /> Atur Alur Persetujuan
              </Link>
            </Button>
          )}
        </div>
      ) : approval?.workflow ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-card px-4 py-3" data-testid="approval-workflow-info">
          <div>
            <p className="text-[12px] text-muted-foreground">Workflow yang dipakai</p>
            <p className="text-sm font-semibold">
              {approval.workflow.name} <span className="font-normal text-muted-foreground">· {approval.workflow.code} · {approval.workflow.steps.length} tahap</span>
            </p>
          </div>
          {approval.can_submit && (
            <Button onClick={() => setSubmitOpen(true)} data-testid="approval-submit-button">
              <Send className="mr-2 h-4 w-4" /> Ajukan Approval
            </Button>
          )}
        </div>
      ) : null}

      {/* Langkah */}
      {!currentRound ? (
        <div className="rounded-lg border border-border bg-card" data-testid="approval-empty">
          <EmptyState
            icon={CircleDot}
            title="Belum ada pengajuan approval."
            description={
              approval?.submit_blockers?.length
                ? approval.submit_blockers.join(" ")
                : "Ajukan kandidat setelah seluruh interview selesai."
            }
            actionLabel={approval?.can_submit ? "Ajukan Approval" : undefined}
            onAction={() => setSubmitOpen(true)}
          />
        </div>
      ) : (
        rounds
          .slice()
          .reverse()
          .map((round) => (
            <div key={round.round} className="overflow-hidden rounded-lg border border-border bg-card" data-testid={`approval-round-${round.round}`}>
              <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
                <h3 className="text-section-title">
                  Ronde {round.round}
                  {round.round !== approval.current_round && <span className="ml-2 text-[12px] font-normal text-muted-foreground">(tidak aktif)</span>}
                </h3>
                {round.round === approval.current_round && (
                  <StageBadge stage={stage} label={candidate.stage_label} tone={candidate.stage_tone} />
                )}
              </div>
              <ol className="divide-y divide-border">
                {round.steps.map((step) => (
                  <li key={step.id} className={cn("flex items-start gap-3 px-4 py-3", step.is_current && "bg-warning-soft/40")} data-testid={`approval-step-${step.id}`}>
                    <StepIcon step={step} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-[13px] font-semibold">
                          {step.step_order}. {step.step_name}
                        </p>
                        <StageBadge stage={step.decision} label={step.decision_label} tone={step.decision_tone} testId={`approval-decision-${step.id}`} />
                        {step.i_am_approver && step.decision === "pending" && (
                          <span className="text-[11px] text-muted-foreground">Anda adalah penyetuju tahap ini</span>
                        )}
                      </div>
                      <p className="text-[12px] text-muted-foreground">
                        Penyetuju: {step.approver_label || step.approver_type}
                        {step.decided_by_name ? ` · Diputuskan oleh ${step.decided_by_name} · ${formatDateTime(step.decided_at)}` : ""}
                      </p>
                      {step.notes && <p className="mt-1 text-[12px]">{step.notes}</p>}
                    </div>
                    {step.can_decide && (
                      <div className="flex shrink-0 gap-1.5">
                        <Button size="sm" onClick={() => { setDecideNotes(""); setError(""); setDecide({ step, decision: "approved" }); }} data-testid={`approval-approve-${step.id}`}>
                          <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" /> Setujui
                        </Button>
                        <Button size="sm" variant="outline" className="text-destructive hover:text-destructive" onClick={() => { setDecideNotes(""); setError(""); setDecide({ step, decision: "rejected" }); }} data-testid={`approval-reject-${step.id}`}>
                          <XCircle className="mr-1.5 h-3.5 w-3.5" /> Tolak
                        </Button>
                      </div>
                    )}
                  </li>
                ))}
              </ol>
            </div>
          ))
      )}

      {stage === "rejected" && (
        <p className="text-[12px] text-muted-foreground" data-testid="approval-rejected-note">
          Kandidat ditolak pada approval. Pengajuan ulang (ronde baru) belum tersedia pada tahap ini.
        </p>
      )}

      {/* Dialog submit */}
      <Dialog open={submitOpen} onOpenChange={setSubmitOpen}>
        <DialogContent className="bg-card sm:max-w-md" data-testid="approval-submit-dialog">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">Ajukan Approval</DialogTitle>
            <DialogDescription className="leading-relaxed">
              Tahap penyetuju disalin (snapshot) dari workflow {approval?.workflow?.name}. Perubahan konfigurasi setelah ini tidak memengaruhi pengajuan yang berjalan.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <ol className="space-y-1 text-[13px]">
              {(approval?.workflow?.steps || []).map((s) => (
                <li key={s.id} className="flex items-center gap-2">
                  <Circle className="h-3.5 w-3.5 text-muted-foreground" /> {s.step_order}. {s.name} <span className="text-muted-foreground">· {s.approver_label}</span>
                </li>
              ))}
            </ol>
            <div className="space-y-1.5">
              <Label htmlFor="approval-notes">Catatan pengajuan</Label>
              <Textarea id="approval-notes" rows={3} value={submitNotes} onChange={(e) => setSubmitNotes(e.target.value)} data-testid="approval-submit-notes" />
            </div>
            {error && <div className="rounded-lg border border-danger-border bg-danger-soft px-3 py-2 text-sm text-destructive" data-testid="approval-error">{error}</div>}
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setSubmitOpen(false)} disabled={busy} data-testid="approval-submit-cancel">Batal</Button>
            <Button onClick={runSubmit} disabled={busy} data-testid="approval-submit-confirm">
              {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Ajukan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog decide */}
      <Dialog open={!!decide} onOpenChange={(v) => !v && setDecide(null)}>
        <DialogContent className="bg-card sm:max-w-md" data-testid="approval-decide-dialog">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">
              {decide?.decision === "approved" ? "Setujui tahap ini?" : "Tolak kandidat pada tahap ini?"}
            </DialogTitle>
            <DialogDescription className="leading-relaxed">
              {decide?.step?.step_order}. {decide?.step?.step_name} · {candidate.full_name}.{" "}
              {decide?.decision === "rejected"
                ? "Penolakan menghentikan ronde approval dan kandidat berstatus Ditolak."
                : "Tahap berikutnya akan menunggu penyetujunya."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="decide-notes">Catatan {decide?.decision === "rejected" ? "/ alasan penolakan" : ""}</Label>
              <Textarea id="decide-notes" rows={3} value={decideNotes} onChange={(e) => setDecideNotes(e.target.value)} data-testid="approval-decide-notes" />
            </div>
            {error && <div className="rounded-lg border border-danger-border bg-danger-soft px-3 py-2 text-sm text-destructive" data-testid="approval-error">{error}</div>}
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setDecide(null)} disabled={busy} data-testid="approval-decide-cancel">Batal</Button>
            <Button
              onClick={runDecide}
              disabled={busy}
              variant={decide?.decision === "rejected" ? "destructive" : "default"}
              data-testid="approval-decide-confirm"
            >
              {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {decide?.decision === "approved" ? "Setujui" : "Tolak"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ApprovalTab;
