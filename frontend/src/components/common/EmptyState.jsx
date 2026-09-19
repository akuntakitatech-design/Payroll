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
      "flex flex-col items-start gap-2 rounded-md border border-dashed border-border bg-muted/40 px-4 py-8 sm:px-6",
      className
    )}
  >
    <div className="flex items-center gap-2 text-muted-foreground">
      <Icon className="h-4 w-4" strokeWidth={1.75} />
      <p className="text-sm font-semibold text-foreground">{title}</p>
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
