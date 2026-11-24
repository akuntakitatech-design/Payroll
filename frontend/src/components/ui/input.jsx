import * as React from "react"

import { cn } from "@/lib/utils"

const Input = React.forwardRef(({ className, type, ...props }, ref) => {
  return (
    <input
      type={type}
      className={cn(
        "flex h-9 w-full rounded-lg border border-input bg-card px-3 py-1.5 text-sm text-ink-1 shadow-[var(--shadow-input)] transition-[border-color,box-shadow,background-color] duration-150 file:border-0 file:bg-transparent file:text-sm file:font-semibold file:text-ink-1 placeholder:text-muted-foreground/85 hover:border-border-strong focus-visible:outline-none focus-visible:border-[hsl(var(--ring))] focus-visible:ring-2 focus-visible:ring-ring/25 disabled:cursor-not-allowed disabled:bg-muted disabled:opacity-70 aria-[invalid=true]:border-destructive aria-[invalid=true]:focus-visible:ring-destructive/20",
        className
      )}
      ref={ref}
      {...props} />
  );
})
Input.displayName = "Input"

export { Input }
