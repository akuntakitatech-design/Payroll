import React from "react";
import { cn } from "@/lib/utils";
import { STATUS_LABELS } from "@/lib/format";

// Badge dipakai hanya untuk status kerja, bukan metadata biasa.
const STYLES = {
  active: "border-success-border bg-success-soft text-success",
  inactive: "border-border bg-muted text-muted-foreground",
  draft: "border-border bg-muted text-muted-foreground",
  pending: "border-warning-border bg-warning-soft text-warning",
  approved: "border-success-border bg-success-soft text-success",
  rejected: "border-danger-border bg-danger-soft text-danger",
  archived: "border-warning-border bg-warning-soft text-warning",
  deleted: "border-danger-border bg-danger-soft text-danger",
};

export const StatusBadge = ({ status = "active", className, label }) => (
  <span
    data-testid="status-badge"
    className={cn(
      "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium leading-5",
      STYLES[status] || STYLES.inactive,
      className
    )}
  >
    {label || STATUS_LABELS[status] || status}
  </span>
);

const EXPIRY_STYLES = {
  expired: "border-danger-border bg-danger-soft text-danger",
  due_soon: "border-warning-border bg-warning-soft text-warning",
  ok: "border-border bg-muted text-muted-foreground",
  none: "border-border bg-muted text-muted-foreground",
};

/**
 * Badge masa berlaku dipakai konsisten di kontrak, sertifikasi dan dokumen.
 * state: expired | due_soon | ok | none
 */
export const ExpiryBadge = ({ state = "none", daysLeft, className, testId }) => {
  let text;
  if (state === "none") text = "Tanpa masa berlaku";
  else if (state === "expired") text = `Kedaluwarsa ${Math.abs(daysLeft ?? 0)} hari`;
  else text = `${daysLeft} hari lagi`;

  return (
    <span
      data-testid={testId || "expiry-badge"}
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium leading-5",
        EXPIRY_STYLES[state] || EXPIRY_STYLES.none,
        className
      )}
    >
      {text}
    </span>
  );
};

/**
 * Metadata ditampilkan sebagai teks dipisah titik tengah — bukan tumpukan badge.
 * <MetaLine items={["WF-KONTRAK", "Kontrak Kerja", "Default"]} />
 */
export const MetaLine = ({ items = [], className, testId }) => {
  const clean = items.filter(Boolean);
  if (!clean.length) return null;
  return (
    <p className={cn("text-[12px] text-muted-foreground", className)} data-testid={testId}>
      {clean.join(" · ")}
    </p>
  );
};

export default StatusBadge;
