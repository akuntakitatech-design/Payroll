import React, { useState } from "react";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

/**
 * Dialog hasil screening HR. Keputusan akhir (lolos / tidak lolos) dikirim ke
 * POST /recruitment/candidates/{id}/screening; state machine di backend yang
 * memutuskan sah/tidaknya perubahan status.
 */
export const ScreeningDialog = ({ open, onOpenChange, candidate, catalog, onSaved }) => {
  const [result, setResult] = useState("");
  const [score, setScore] = useState("");
  const [recommendation, setRecommendation] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const reset = () => {
    setResult("");
    setScore("");
    setRecommendation("");
    setNotes("");
    setError("");
  };

  const handleOpenChange = (v) => {
    if (!v) reset();
    onOpenChange(v);
  };

  const submit = async () => {
    setError("");
    if (!result) {
      setError("Pilih hasil screening: Lolos atau Tidak Lolos.");
      return;
    }
    if (score !== "" && (Number(score) < 0 || Number(score) > 100)) {
      setError("Skor harus di antara 0 sampai 100.");
      return;
    }
    setSubmitting(true);
    try {
      const payload = { screening_result: result };
      if (score !== "") payload.screening_score = Number(score);
      if (recommendation) payload.screening_recommendation = recommendation;
      if (notes.trim()) payload.screening_notes = notes.trim();
      const res = await api.post(`/recruitment/candidates/${candidate.id}/screening`, payload);
      toast.success(
        result === "passed"
          ? `${candidate.full_name} dinyatakan lolos screening.`
          : `${candidate.full_name} dinyatakan tidak lolos screening.`
      );
      reset();
      onOpenChange(false);
      onSaved?.(res.data);
    } catch (err) {
      setError(errorMessage(err, "Hasil screening tidak dapat disimpan."));
    } finally {
      setSubmitting(false);
    }
  };

  const choices = [
    { key: "passed", label: "Lolos", icon: CheckCircle2, active: "border-success-border bg-success-soft text-success" },
    { key: "failed", label: "Tidak Lolos", icon: XCircle, active: "border-danger-border bg-danger-soft text-danger" },
  ];

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="bg-card sm:max-w-lg" data-testid="screening-dialog">
        <DialogHeader>
          <DialogTitle className="text-base font-semibold">Hasil Screening HR</DialogTitle>
          <DialogDescription className="leading-relaxed">
            {candidate?.full_name} · {candidate?.candidate_number}. Keputusan ini mengubah status kandidat dan
            tercatat di riwayat serta Audit Log.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>
              Keputusan <span className="text-destructive">*</span>
            </Label>
            <div className="grid grid-cols-2 gap-2">
              {choices.map(({ key, label, icon: Icon, active }) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setResult(key)}
                  aria-pressed={result === key}
                  data-testid={`screening-result-${key}`}
                  className={cn(
                    "flex items-center justify-center gap-2 rounded-lg border px-3 py-2.5 text-sm font-medium transition-colors",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    result === key ? active : "border-border bg-background text-foreground hover:bg-muted/60"
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="screening-score">Skor (0–100)</Label>
              <Input
                id="screening-score"
                type="number"
                min={0}
                max={100}
                value={score}
                onChange={(e) => setScore(e.target.value)}
                placeholder="Opsional"
                data-testid="screening-score"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Rekomendasi</Label>
              <Select value={recommendation || "__empty__"} onValueChange={(v) => setRecommendation(v === "__empty__" ? "" : v)}>
                <SelectTrigger data-testid="screening-recommendation">
                  <SelectValue placeholder="Pilih…" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__empty__">— Tidak diisi —</SelectItem>
                  {(catalog?.screening_recommendations || []).map((r) => (
                    <SelectItem key={r.key} value={r.key}>
                      {r.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="screening-notes">Catatan Screening</Label>
            <Textarea
              id="screening-notes"
              rows={4}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Kesesuaian kualifikasi, kelengkapan dokumen, catatan wawancara awal…"
              data-testid="screening-notes"
            />
          </div>

          {error && (
            <div
              className="rounded-lg border border-danger-border bg-danger-soft px-3 py-2 text-sm text-destructive"
              data-testid="screening-error"
            >
              {error}
            </div>
          )}
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => handleOpenChange(false)} disabled={submitting} data-testid="screening-cancel">
            Batal
          </Button>
          <Button onClick={submit} disabled={submitting} data-testid="screening-submit">
            {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Simpan Hasil Screening
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ScreeningDialog;
