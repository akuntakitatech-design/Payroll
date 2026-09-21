import React from "react";
import { Check, Clock, X, MinusCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatDateTime } from "@/lib/format";

const ICONS = {
  approved: Check,
  rejected: X,
  pending: Clock,
  skipped: MinusCircle,
};

const STYLES = {
  approved: "border-success-border bg-success-soft text-success",
  rejected: "border-danger-border bg-danger-soft text-danger",
  pending: "border-warning-border bg-warning-soft text-warning",
  skipped: "border-border bg-muted text-muted-foreground",
};

/**
 * Riwayat persetujuan berjenjang (snapshot alur saat pengajuan dibuat).
 * rows: [{ id, step_order, step_name, approver_label, decision, decision_label,
 *          decided_by_name, decided_at, notes }]
 */
export const ApprovalTimeline = ({ rows = [], emptyLabel = "Belum ada tahap persetujuan.", testId = "approval-timeline" }) => {
  if (!rows.length) {
    return (
      <p className="text-[13px] text-muted-foreground" data-testid={`${testId}-empty`}>
        {emptyLabel}
      </p>
    );
  }
  return (
    <ol className="space-y-2" data-testid={testId}>
      {rows.map((row) => {
        const decision = row.decision || "pending";
        const Icon = ICONS[decision] || Clock;
        return (
          <li
            key={row.id || `${row.step_order}-${row.step_name}`}
            className="flex items-start gap-3 rounded-md border border-border bg-card p-2.5"
            data-testid={`${testId}-step-${row.step_order}`}
          >
            <span className={cn("mt-0.5 rounded-full border p-1", STYLES[decision] || STYLES.pending)}>
              <Icon className="h-3.5 w-3.5" strokeWidth={2} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[13px] font-medium text-foreground">
                Tahap {row.step_order}: {row.step_name || "Persetujuan"}
              </p>
              <p className="text-[12px] text-muted-foreground">
                {row.approver_label || "Penyetuju"} ·{" "}
                {row.decision_label || (decision === "pending" ? "Menunggu Persetujuan" : decision)}
              </p>
              {row.decided_at && (
                <p className="text-[12px] text-muted-foreground">
                  {row.decided_by_name || "-"} · {formatDateTime(row.decided_at)}
                </p>
              )}
              {row.notes && <p className="mt-1 text-[12px] text-foreground">Catatan: {row.notes}</p>}
            </div>
          </li>
        );
      })}
    </ol>
  );
};

export default ApprovalTimeline;
