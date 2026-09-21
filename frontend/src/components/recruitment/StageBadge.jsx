import React from "react";
import { cn } from "@/lib/utils";
import { STAGE_LABELS, STAGE_TONES, STAGE_TONE_CLASS } from "@/lib/recruitment";

/** Badge tahapan kandidat. Mengutamakan label/tone dari backend bila tersedia. */
export const StageBadge = ({ stage, label, tone, className, testId }) => {
  const resolvedTone = tone || STAGE_TONES[stage] || "neutral";
  const resolvedLabel = label || STAGE_LABELS[stage] || stage || "-";
  return (
    <span
      data-testid={testId || "stage-badge"}
      data-stage={stage}
      className={cn(
        "inline-flex items-center whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium leading-5",
        STAGE_TONE_CLASS[resolvedTone] || STAGE_TONE_CLASS.neutral,
        className
      )}
    >
      {resolvedLabel}
    </span>
  );
};

export default StageBadge;
