import * as React from "react"
import { cva } from "class-variance-authority";

import { cn } from "@/lib/utils"

// Badge status: pil ringkas, kontras cukup, warna mengikuti makna status.
const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold leading-5 tracking-[0.01em] transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1",
  {
    variants: {
      variant: {
        default: "border-primary-border bg-primary-soft text-primary-strong",
        secondary: "border-border bg-muted text-ink-2",
        destructive: "border-danger-border bg-danger-soft text-danger",
        success: "border-success-border bg-success-soft text-success",
        warning: "border-warning-border bg-warning-soft text-warning",
        info: "border-info-border bg-info-soft text-info",
        maintenance: "border-[hsl(var(--maintenance-border))] bg-[hsl(var(--maintenance-soft))] text-[hsl(var(--maintenance))]",
        teal: "border-[hsl(var(--teal-border))] bg-[hsl(var(--teal-soft))] text-[hsl(var(--teal))]",
        navy: "border-[hsl(var(--navy-border))] bg-[hsl(var(--navy-soft))] text-[hsl(var(--navy))]",
        outline: "border-border-strong bg-card text-ink-3",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({
  className,
  variant,
  ...props
}) {
  return (<div className={cn(badgeVariants({ variant }), className)} {...props} />);
}

export { Badge, badgeVariants }
