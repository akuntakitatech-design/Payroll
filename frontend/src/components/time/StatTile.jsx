import React from "react";
import { cn } from "@/lib/utils";

const TONES = {
  primary: "border-primary-border bg-primary-soft text-primary",
  success: "border-success-border bg-success-soft text-success",
  warning: "border-warning-border bg-warning-soft text-warning",
  danger: "border-danger-border bg-danger-soft text-danger",
  info: "border-info-border bg-info-soft text-info",
  neutral: "border-border bg-muted text-muted-foreground",
};

/** Kartu angka ringkas untuk dashboard Time Management. */
export const StatTile = ({ label, value, hint, icon: Icon, tone = "neutral", onClick, testId }) => {
  const Comp = onClick ? "button" : "div";
  return (
    <Comp
      type={onClick ? "button" : undefined}
      onClick={onClick}
      data-testid={testId}
      className={cn(
        "flex w-full items-start gap-3 rounded-lg border border-border bg-card p-3 text-left",
        onClick &&
          "transition-transform duration-200 hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 active:translate-y-0"
      )}
    >
      {Icon && (
        <span className={cn("rounded-md border p-1.5", TONES[tone] || TONES.neutral)}>
          <Icon className="h-4 w-4" strokeWidth={1.75} />
        </span>
      )}
      <span className="min-w-0 flex-1">
        <span className="block text-[12px] text-muted-foreground">{label}</span>
        <span className="block text-xl font-semibold text-foreground" data-numeric="true">
          {value ?? "-"}
        </span>
        {hint && <span className="mt-0.5 block text-[12px] text-muted-foreground">{hint}</span>}
      </span>
    </Comp>
  );
};

export default StatTile;
