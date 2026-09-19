import React from "react";
import { cn } from "@/lib/utils";

/**
 * Header halaman standar: judul 24px/600, deskripsi singkat, aksi utama di kanan.
 */
export const PageHeader = ({ title, subtitle, actions, className, children }) => (
  <div
    data-testid="page-header"
    className={cn("border-b border-border bg-card px-4 py-4 sm:px-6", className)}
  >
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0 space-y-0.5">
        <h1 className="text-page-title">{title}</h1>
        {subtitle && <p className="max-w-2xl text-sm text-muted-foreground">{subtitle}</p>}
      </div>
      {actions && (
        <div
          className="flex shrink-0 flex-col gap-2 sm:flex-row sm:items-center"
          data-testid="page-header-actions"
        >
          {actions}
        </div>
      )}
    </div>
    {children}
  </div>
);

export const PageBody = ({ children, className }) => (
  <div className={cn("space-y-4 px-4 py-4 sm:px-6 sm:py-5", className)}>{children}</div>
);

/** Judul seksi di dalam halaman (16px/600) dengan garis pemisah halus. */
export const SectionHeader = ({ title, description, actions, className }) => (
  <div
    className={cn(
      "flex flex-col gap-2 border-b border-border pb-2 sm:flex-row sm:items-center sm:justify-between",
      className
    )}
  >
    <div className="min-w-0">
      <h2 className="text-section-title">{title}</h2>
      {description && <p className="mt-0.5 text-[13px] text-muted-foreground">{description}</p>}
    </div>
    {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
  </div>
);

export default PageHeader;
