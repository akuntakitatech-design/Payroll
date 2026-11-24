import React from "react";
import { Inbox } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** Kondisi kosong: jelaskan langkah berikutnya, tanpa ilustrasi berlebihan. */
const EmptyState = ({
  icon: Icon = Inbox,
  title = "Belum ada data.",
  description = "Tambahkan data pertama agar bisa dipakai di modul lain.",
  actionLabel,
  onAction,
  testId = "table-empty-state",
  className,
}) => (
  <div
    data-testid={testId}
    className={cn(
      "flex flex-col items-start gap-2 rounded-xl border border-dashed border-border-strong bg-[linear-gradient(180deg,#FFFFFF_0%,hsl(var(--surface-2))_100%)] px-5 py-8 shadow-[var(--shadow-xs)] sm:px-6",
      className
    )}
  >
    <div className="flex items-center gap-2.5">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-primary-border bg-primary-soft text-primary shadow-[var(--shadow-xs)]">
        <Icon className="h-4 w-4" strokeWidth={1.9} />
      </span>
      <p className="text-sm font-bold text-ink-1">{title}</p>
    </div>
    <p className="max-w-xl text-[13px] text-muted-foreground">{description}</p>
    {actionLabel && onAction && (
      <Button size="sm" onClick={onAction} className="mt-1" data-testid="table-empty-state-cta">
        {actionLabel}
      </Button>
    )}
  </div>
);

export default EmptyState;
