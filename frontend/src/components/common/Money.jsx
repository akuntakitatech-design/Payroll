import React from "react";
import { formatCurrency, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Nilai uang: format Indonesia (Rp 12.500.000), rata kanan, tabular-nums.
 * Dipakai di payroll, keuangan, dan akuntansi agar angka mudah discan.
 */
export const Money = ({ value, className, emphasis = false, testId }) => (
  <span
    data-numeric="true"
    data-testid={testId}
    className={cn(
      "block text-right",
      emphasis ? "text-[15px] font-semibold text-foreground" : "text-sm text-foreground",
      className
    )}
  >
    {formatCurrency(value)}
  </span>
);

/** Angka biasa (kuantitas, jumlah tahap, hari) \u2014 rata kanan & tabular. */
export const Num = ({ value, suffix, className, testId }) => (
  <span data-numeric="true" data-testid={testId} className={cn("block text-right", className)}>
    {formatNumber(value)}
    {suffix ? ` ${suffix}` : ""}
  </span>
);

export default Money;
