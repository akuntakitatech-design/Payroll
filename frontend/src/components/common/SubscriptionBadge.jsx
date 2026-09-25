import React from "react";
import { cn } from "@/lib/utils";
import { formatDate } from "@/lib/format";

// Status masa layanan tenant (dihitung backend: active | grace | expired; end_date kosong = legacy/tanpa batas).
const STYLES = {
  active: "border-success-border bg-success-soft text-success",
  grace: "border-warning-border bg-warning-soft text-warning",
  expired: "border-danger-border bg-danger-soft text-danger",
  unlimited: "border-info-border bg-info-soft text-info",
};

export const subscriptionKey = (sub) => (!sub ? "unlimited" : sub.unlimited ? "unlimited" : sub.status);

export const subscriptionLabel = (sub) =>
  ({ active: "Aktif", grace: "Masa Tenggang", expired: "Berakhir", unlimited: "Tanpa batas" })[subscriptionKey(sub)];

/** Keterangan singkat: "342 hari tersisa", "Tenggang 5 hari lagi", "Berakhir sejak 01 Jan 2026". */
export const subscriptionHint = (sub) => {
  if (!sub || sub.unlimited) return "Legacy - belum diatur";
  if (sub.status === "active") return sub.days_remaining === 0 ? "Berakhir hari ini" : `${sub.days_remaining} hari tersisa`;
  if (sub.status === "grace") return `Tenggang s.d. ${formatDate(sub.grace_end_date)} (${sub.grace_days_remaining} hari)`;
  return `Diblokir sejak ${formatDate(sub.grace_end_date)}`;
};

export const SubscriptionBadge = ({ subscription, className, testId }) => (
  <span
    data-testid={testId || "subscription-badge"}
    className={cn(
      "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium leading-5",
      STYLES[subscriptionKey(subscription)],
      className
    )}
  >
    {subscriptionLabel(subscription)}
  </span>
);

export default SubscriptionBadge;
