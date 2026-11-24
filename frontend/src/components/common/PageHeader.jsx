import React from "react";
import { cn } from "@/lib/utils";

/**
 * Header halaman standar: judul 24px/700 deep navy, deskripsi singkat, aksi utama di kanan.
 * `icon` opsional: container emerald soft-3D untuk identitas visual halaman.
 */
export const PageHeader = ({ title, subtitle, actions, icon: Icon, className, children }) => (
  <div
    data-testid="page-header"
    className={cn(
      "border-b border-border bg-card px-4 py-4 shadow-[0_1px_0_rgba(15,23,42,0.04)] sm:px-6",
      className
    )}
  >
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-center gap-3">
        {Icon && (
          <span
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-primary-border bg-[linear-gradient(180deg,hsl(var(--primary-soft))_0%,#FFFFFF_100%)] text-primary shadow-[var(--shadow-raised)]"
            aria-hidden="true"
          >
            <Icon className="h-5 w-5" strokeWidth={1.9} />
          </span>
        )}
        <div className="min-w-0 space-y-0.5">
          <h1 className="text-page-title">{title}</h1>
          {subtitle && (
            <p className="max-w-2xl text-[13.5px] leading-relaxed text-muted-foreground">{subtitle}</p>
          )}
        </div>
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
      "flex flex-col gap-2 border-b border-border pb-2.5 sm:flex-row sm:items-center sm:justify-between",
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
