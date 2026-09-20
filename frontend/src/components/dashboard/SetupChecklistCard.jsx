import React from "react";
import { Link } from "react-router-dom";
import { Check, ChevronRight, ListChecks } from "lucide-react";
import { cn } from "@/lib/utils";
import SectionCard, { SectionHeader } from "./SectionCard";

/**
 * "Kelengkapan Setup" - progress cincin tipis + checklist langkah.
 * Langkah yang belum selesai ditegaskan; yang sudah selesai dibuat tenang.
 */
const SetupChecklistCard = ({ progress }) => {
  const percent = progress?.percent ?? 0;
  const steps = progress?.steps || [];

  return (
    <SectionCard className="flex h-full flex-col" data-testid="card-kelengkapan-setup">
      <SectionHeader
        icon={ListChecks}
        title="Kelengkapan Setup"
        description={`${progress?.done ?? 0} dari ${progress?.total ?? 0} langkah selesai`}
        aside={
          <span
            className="inline-flex items-center rounded-full border border-primary-border bg-primary-soft px-2.5 py-1 text-[12.5px] font-semibold text-primary"
            data-numeric="true"
            data-testid="setup-progress-percent"
          >
            {percent}%
          </span>
        }
      />

      <div className="px-5">
        <div
          className="h-2 w-full overflow-hidden rounded-full bg-surface-2"
          role="progressbar"
          aria-valuenow={percent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Kelengkapan setup"
          data-testid="setup-progress"
        >
          <div
            className="h-full rounded-full bg-primary transition-[width] duration-500"
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>

      <ul className="mt-3 flex-1 space-y-0.5 px-3 pb-4">
        {steps.map((step) => (
          <li key={step.key}>
            <Link
              to={step.link}
              data-testid={`setup-checklist-item-${step.key}`}
              className="group flex items-center gap-2.5 rounded-lg px-2.5 py-2 transition-colors duration-150 hover:bg-surface-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
            >
              <span
                className={cn(
                  "flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded-[5px] border",
                  step.done
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border-strong bg-card"
                )}
                style={{ height: "18px", width: "18px" }}
                aria-hidden="true"
              >
                {step.done && <Check className="h-3 w-3" strokeWidth={3} />}
              </span>
              <span
                className={cn(
                  "min-w-0 flex-1 truncate text-[12.5px]",
                  step.done ? "text-ink-3" : "font-medium text-ink-1"
                )}
              >
                {step.label}
              </span>
              <ChevronRight className="h-3.5 w-3.5 shrink-0 text-ink-3 opacity-0 transition-opacity duration-150 group-hover:opacity-100" />
            </Link>
          </li>
        ))}
      </ul>
    </SectionCard>
  );
};

export default SetupChecklistCard;
