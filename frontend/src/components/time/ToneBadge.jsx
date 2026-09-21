import React from "react";
import { cn } from "@/lib/utils";

const TONES = {
  success: "border-success-border bg-success-soft text-success",
  warning: "border-warning-border bg-warning-soft text-warning",
  danger: "border-danger-border bg-danger-soft text-danger",
  info: "border-info-border bg-info-soft text-info",
  neutral: "border-border bg-muted text-muted-foreground",
};

/** Badge status Time Management — warna mengikuti token tema aplikasi. */
export const ToneBadge = ({ tone = "neutral", label, className, testId }) => (
  <span
    data-testid={testId}
    className={cn(
      "inline-flex items-center whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium leading-5",
      TONES[tone] || TONES.neutral,
      className
    )}
  >
    {label || "-"}
  </span>
);

export default ToneBadge;
