import React from "react";
import { cn } from "@/lib/utils";
import { CATEGORY_DOT, CATEGORY_LABELS, CATEGORY_STYLES } from "@/lib/employeeStatus";

// Kategori sistem (AKTIF / STANDBY / TIDAK AKTIF) sebagai chip kecil.
export const CategoryBadge = ({ category, className, testId }) => {
  if (!category) return null;
  return (
    <span
      data-testid={testId || "employee-status-category-badge"}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase leading-4 tracking-wide",
        CATEGORY_STYLES[category] || CATEGORY_STYLES.INACTIVE,
        className
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", CATEGORY_DOT[category] || CATEGORY_DOT.INACTIVE)} aria-hidden="true" />
      {CATEGORY_LABELS[category] || category}
    </span>
  );
};

// Nama status bisnis + chip kategori. Contoh: "Aktif Project  [AKTIF]".
export const EmployeeStatusBadge = ({ name, category, archived = false, className, testId }) => {
  if (!name && !category) {
    return (
      <span className="text-sm text-muted-foreground" data-testid={testId || "employee-status-empty"}>
        Belum diatur
      </span>
    );
  }
  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)} data-testid={testId || "employee-status-badge"}>
      <span className="text-sm font-medium text-foreground">{name}</span>
      <CategoryBadge category={category} />
      {archived && (
        <span className="inline-flex items-center rounded-full border border-warning-border bg-warning-soft px-2 py-0.5 text-[11px] font-medium text-warning">
          Diarsipkan
        </span>
      )}
    </div>
  );
};

export default EmployeeStatusBadge;
