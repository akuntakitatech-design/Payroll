import React from "react";
import { AlertTriangle, CheckCircle2, ChevronRight } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { STEPS } from "@/components/public-form/PublicFormParts";

/** Ringkasan per bagian. REQUIRED yang belum dilengkapi memblokir kirim; RECOMMENDED tidak. */
export const ReviewSection = ({ sectionState, changedCount, onGo, agree, setAgree, disabled }) => (
  <div className="space-y-4" data-testid="public-review-section">
    <ul className="divide-y rounded-xl border bg-background">
      {STEPS.filter((s) => s.key !== "review").map((s, i) => {
        const st = sectionState[s.key] || { ok: true, required: [], recommended: [], changes: 0 };
        return (
          <li key={s.key}>
            <button type="button" onClick={() => onGo(i)} className="flex min-h-[64px] w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" data-testid={`public-review-row-${s.key}`}>
              {st.ok ? <CheckCircle2 className="h-6 w-6 shrink-0 text-primary" aria-label="Lengkap" /> : <AlertTriangle className="h-6 w-6 shrink-0 text-amber-600" aria-label="Perlu dilengkapi" />}
              <div className="min-w-0 flex-1">
                <p className="font-medium">{s.label}</p>
                <p className="text-sm text-muted-foreground" data-testid={`public-review-status-${s.key}`}>
                  {!st.ok ? `Wajib dilengkapi: ${st.required.join(", ")}` : st.changes ? `${st.changes} perubahan diajukan` : "Tidak ada perubahan"}
                  {st.ok && st.recommended.length > 0 ? ` · Disarankan: ${st.recommended.join(", ")}` : ""}
                </p>
              </div>
              <ChevronRight className="h-5 w-5 shrink-0 text-muted-foreground" />
            </button>
          </li>
        );
      })}
    </ul>
    <p className="text-sm text-muted-foreground" data-testid="public-review-changes">Total perubahan yang akan dikirim: <span className="font-semibold text-foreground">{changedCount}</span></p>
    <label className="flex min-h-12 cursor-pointer items-start gap-3 rounded-xl border bg-background p-4">
      <Checkbox className="mt-0.5 h-5 w-5" checked={agree} disabled={disabled} onCheckedChange={(v) => setAgree(!!v)} data-testid="public-review-agree" />
      <span className="text-sm leading-relaxed">Saya menyatakan data yang saya isi benar dan dapat dipertanggungjawabkan.</span>
    </label>
  </div>
);
