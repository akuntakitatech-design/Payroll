import React from "react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

/**
 * Panel detail samping: dipakai untuk melihat isi satu record
 * tanpa kehilangan konteks daftar.
 */
export const DetailDrawer = ({
  open,
  onOpenChange,
  title,
  description,
  footer,
  children,
  testId = "detail-drawer",
  className,
}) => (
  <Sheet open={open} onOpenChange={onOpenChange}>
    <SheetContent
      side="right"
      className={cn("flex w-full flex-col gap-0 p-0 sm:max-w-md", className)}
      data-testid={testId}
    >
      <SheetHeader className="space-y-1 border-b border-border px-5 py-4 text-left">
        <SheetTitle className="pr-8 text-base font-semibold">{title}</SheetTitle>
        {description && (
          <SheetDescription className="text-[13px]">{description}</SheetDescription>
        )}
      </SheetHeader>
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
      {footer && (
        <div className="flex flex-wrap items-center gap-2 border-t border-border px-5 py-3">
          {footer}
        </div>
      )}
    </SheetContent>
  </Sheet>
);

export default DetailDrawer;
