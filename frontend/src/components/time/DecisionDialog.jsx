import React, { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";

/**
 * Dialog keputusan persetujuan (setujui / tolak) dengan catatan wajib saat menolak.
 * mode: "approve" | "reject"
 */
export const DecisionDialog = ({
  open,
  onOpenChange,
  mode = "approve",
  title,
  description,
  submitting,
  onSubmit,
  showApprovedMinutes = false,
  defaultApprovedMinutes,
}) => {
  const [notes, setNotes] = useState("");
  const [minutes, setMinutes] = useState("");
  const [error, setError] = useState("");
  const rejecting = mode === "reject";

  useEffect(() => {
    if (open) {
      setNotes("");
      setError("");
      setMinutes(
        defaultApprovedMinutes === null || defaultApprovedMinutes === undefined
          ? ""
          : String(defaultApprovedMinutes)
      );
    }
  }, [open, defaultApprovedMinutes]);

  const submit = () => {
    if (rejecting && notes.trim().length < 3) {
      setError("Alasan penolakan wajib diisi minimal 3 karakter.");
      return;
    }
    onSubmit?.({
      notes: notes.trim() || null,
      approved_minutes:
        showApprovedMinutes && !rejecting && minutes !== "" ? Number(minutes) : undefined,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="decision-dialog" className="bg-card sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-base font-semibold">
            {title || (rejecting ? "Tolak Pengajuan" : "Setujui Pengajuan")}
          </DialogTitle>
          {description && <DialogDescription className="leading-relaxed">{description}</DialogDescription>}
        </DialogHeader>
        <div className="space-y-3">
          {showApprovedMinutes && !rejecting && (
            <div className="space-y-1.5">
              <Label htmlFor="decision-minutes" className="text-[13px] font-medium">
                Menit Lembur Disetujui
              </Label>
              <Input
                id="decision-minutes"
                type="number"
                min={0}
                value={minutes}
                onChange={(e) => setMinutes(e.target.value)}
                data-testid="decision-approved-minutes"
              />
              <p className="text-[12px] text-muted-foreground">
                Kosongkan untuk memakai perhitungan sistem (aktual vs rencana).
              </p>
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="decision-notes" className="text-[13px] font-medium">
              Catatan {rejecting && <span className="text-destructive">*</span>}
            </Label>
            <Textarea
              id="decision-notes"
              rows={3}
              value={notes}
              onChange={(e) => {
                setNotes(e.target.value);
                setError("");
              }}
              placeholder={rejecting ? "Jelaskan alasan penolakan…" : "Catatan tambahan (opsional)"}
              aria-invalid={!!error}
              data-testid="decision-notes"
            />
            {error && <p className="text-xs font-medium text-destructive">{error}</p>}
          </div>
        </div>
        <DialogFooter className="gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={submitting}
            data-testid="decision-cancel"
          >
            Batal
          </Button>
          <Button
            type="button"
            onClick={submit}
            disabled={submitting}
            variant={rejecting ? "destructive" : "default"}
            data-testid="decision-submit"
          >
            {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {rejecting ? "Tolak" : "Setujui"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default DecisionDialog;
