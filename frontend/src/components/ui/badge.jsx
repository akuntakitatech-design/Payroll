import * as React from "react"
import { cva } from "class-variance-authority";

import { cn } from "@/lib/utils"

// Badge hanya untuk status/label singkat. Metadata biasa cukup teks biasa.
const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium leading-5 transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1",
  {
    variants: {
      variant: {
        default: "border-primary-border bg-primary-soft text-primary",
        secondary: "border-border bg-muted text-muted-foreground",
        destructive: "border-danger-border bg-danger-soft text-danger",
        success: "border-success-border bg-success-soft text-success",
        warning: "border-warning-border bg-warning-soft text-warning",
        info: "border-info-border bg-info-soft text-info",
        outline: "border-border bg-card text-muted-foreground",
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
