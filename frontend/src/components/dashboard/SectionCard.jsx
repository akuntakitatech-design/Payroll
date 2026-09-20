import React from "react";
import { cn } from "@/lib/utils";

/**
 * Kerangka kartu dashboard: border halus, sudut lembut, shadow tipis.
 * Hover hanya menaikkan shadow & menguatkan border - tanpa transform,
 * dan transisi dibatasi pada properti tertentu (bukan `all`).
 */
export const SectionCard = ({ className, children, interactive = false, ...rest }) => (
  <section
    className={cn(
      "rounded-card border border-border bg-card shadow-card",
      interactive &&
        "transition-[box-shadow,border-color] duration-150 hover:border-border-strong hover:shadow-float",
      className
    )}
    {...rest}
  >
    {children}
  </section>
);

export const SectionHeader = ({ title, description, icon: Icon, aside, className }) => (
  <div className={cn("flex items-start justify-between gap-3 px-5 pb-3 pt-4", className)}>
    <div className="flex min-w-0 items-start gap-3">
      {Icon && (
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-primary-border bg-primary-soft text-primary">
          <Icon className="h-4 w-4" strokeWidth={1.75} />
        </span>
      )}
      <div className="min-w-0">
        <h2 className="text-[15px] font-semibold leading-tight tracking-[-0.005em] text-ink-1">{title}</h2>
        {description && <p className="mt-1 text-[12.5px] leading-[1.5] text-ink-3">{description}</p>}
      </div>
    </div>
    {aside && <div className="shrink-0">{aside}</div>}
  </div>
);

export const SectionDivider = () => <div className="h-px bg-border" />;

/** Baris footer kartu untuk tautan lanjutan. */
export const SectionFooter = ({ children, className }) => (
  <div className={cn("border-t border-border px-5 py-3", className)}>{children}</div>
);

export default SectionCard;
