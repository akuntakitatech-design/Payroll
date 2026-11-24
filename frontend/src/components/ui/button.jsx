import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva } from "class-variance-authority";

import { cn } from "@/lib/utils"

/**
 * Sistem tombol premium "soft 3D":
 * - Primary   : emerald gradient + raised shadow (aksi utama)
 * - Secondary : silver/white gradient + teks navy
 * - Outline   : putih dengan border slate + raised shadow
 * - Navy      : ekspor / unduh (identitas korporat)
 * - Warning   : amber untuk aksi yang perlu perhatian
 * - Cancel    : netral untuk membatalkan
 * Semua state (hover naik, pressed masuk, focus ring) seragam.
 */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg border text-sm font-semibold transition-[transform,box-shadow,background-color,border-color,color,opacity] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-60 disabled:shadow-none [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "border-[hsl(var(--primary-active))] bg-[image:var(--gradient-primary)] text-white shadow-[var(--shadow-button-primary)] hover:-translate-y-px hover:bg-[image:var(--gradient-primary-hover)] hover:shadow-[var(--shadow-button-primary-hover)] active:translate-y-0 active:shadow-[var(--shadow-button-pressed)]",
        secondary:
          "border-border-strong bg-[image:var(--gradient-secondary)] text-ink-1 shadow-[var(--shadow-button-secondary)] hover:-translate-y-px hover:border-primary-border hover:text-primary active:translate-y-0 active:shadow-[var(--shadow-button-pressed)]",
        outline:
          "border-input bg-card text-ink-1 shadow-[var(--shadow-raised)] hover:-translate-y-px hover:border-primary-border hover:bg-primary-soft/60 hover:text-primary active:translate-y-0 active:shadow-[var(--shadow-button-pressed)]",
        navy:
          "border-[hsl(var(--navy-deep))] bg-[image:var(--gradient-navy)] text-white shadow-[var(--shadow-button-navy)] hover:-translate-y-px hover:brightness-110 active:translate-y-0 active:shadow-[var(--shadow-button-pressed)]",
        destructive:
          "border-[hsl(0_72%_30%)] bg-[image:var(--gradient-danger)] text-white shadow-[var(--shadow-button-danger)] hover:-translate-y-px hover:brightness-110 active:translate-y-0 active:shadow-[var(--shadow-button-pressed)]",
        warning:
          "border-[hsl(28_88%_26%)] bg-[image:var(--gradient-warning)] text-white shadow-[var(--shadow-button-warning)] hover:-translate-y-px hover:brightness-105 active:translate-y-0 active:shadow-[var(--shadow-button-pressed)]",
        cancel:
          "border-border-strong bg-muted text-ink-2 shadow-[var(--shadow-xs)] hover:-translate-y-px hover:bg-border hover:text-ink-1 active:translate-y-0 active:shadow-none",
        ghost:
          "border-transparent bg-transparent text-ink-2 shadow-none hover:bg-accent hover:text-ink-1 active:bg-primary-soft",
        link:
          "border-transparent bg-transparent text-primary shadow-none underline-offset-4 hover:underline"
      },
      size: {
        default: "h-9 px-3.5",
        sm: "h-8 px-3 text-[13px]",
        lg: "h-10 px-5",
        icon: "h-9 w-9",
        "icon-sm": "h-8 w-8",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

const Button = React.forwardRef(({ className, variant, size, asChild = false, ...props }, ref) => {
  const Comp = asChild ? Slot : "button"
  return (
    <Comp
      className={cn(buttonVariants({ variant, size, className }))}
      ref={ref}
      {...props} />
  );
})
Button.displayName = "Button"

export { Button, buttonVariants }
