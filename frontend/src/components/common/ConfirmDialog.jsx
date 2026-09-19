import React from "react";
import { Loader2 } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { cn } from "@/lib/utils";

const ConfirmDialog = ({
  open,
  onOpenChange,
  title = "Konfirmasi tindakan",
  description,
  confirmLabel = "Lanjutkan",
  cancelLabel = "Batal",
  destructive = false,
  loading = false,
  onConfirm,
}) => (
  <AlertDialog open={open} onOpenChange={onOpenChange}>
    <AlertDialogContent data-testid="confirm-dialog">
      <AlertDialogHeader>
        <AlertDialogTitle>{title}</AlertDialogTitle>
        {description && (
          <AlertDialogDescription className="leading-relaxed">{description}</AlertDialogDescription>
        )}
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel disabled={loading} data-testid="confirm-dialog-cancel">
          {cancelLabel}
        </AlertDialogCancel>
        <AlertDialogAction
          onClick={(e) => {
            e.preventDefault();
            onConfirm?.();
          }}
          disabled={loading}
          data-testid="confirm-dialog-confirm"
          className={cn(
            destructive && "bg-destructive text-destructive-foreground hover:bg-destructive/90"
          )}
        >
          {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {confirmLabel}
        </AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
);

export default ConfirmDialog;
