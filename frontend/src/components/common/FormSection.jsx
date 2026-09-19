import React from "react";
import { cn } from "@/lib/utils";

/**
 * Seksi form terstruktur: judul + garis pemisah + grid 2 kolom di desktop,
 * 1 kolom di mobile. Menghindari pola "kartu di dalam kartu".
 */
export const FormSection = ({ title, description, children, columns = 2, className, testId }) => (
  <section className={cn("space-y-3", className)} data-testid={testId}>
    {(title || description) && (
      <div className="border-b border-border pb-1.5">
        {title && (
          <h3 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
            {title}
          </h3>
        )}
        {description && <p className="mt-1 text-[13px] text-muted-foreground">{description}</p>}
      </div>
    )}
    <div
      className={cn(
        "grid grid-cols-1 gap-x-4 gap-y-3",
        columns === 2 && "sm:grid-cols-2",
        columns === 3 && "sm:grid-cols-2 lg:grid-cols-3"
      )}
    >
      {children}
    </div>
  </section>
);

/** Baris label + nilai untuk panel detail (read-only). */
export const DetailRow = ({ label, children, className }) => (
  <div className={cn("flex flex-col gap-0.5 py-1.5", className)}>
    <span className="text-[12px] text-muted-foreground">{label}</span>
    <span className="text-sm text-foreground">{children ?? "-"}</span>
  </div>
);

export default FormSection;
