import React from "react";
import { Link } from "react-router-dom";
import { CalendarCheck2, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import SectionCard, { SectionHeader } from "./SectionCard";

/**
 * "Ringkasan SDM Hari Ini" - enam metrik nyata dari database, disusun dua
 * kolom agar mudah dipindai. Warna hanya dipakai untuk menandai urgensi.
 */
const TONE_DOT = {
  normal: "bg-primary",
  success: "bg-success",
  warning: "bg-warning",
  critical: "bg-danger",
};

const TONE_VALUE = {
  normal: "text-ink-1",
  success: "text-ink-1",
  warning: "text-warning",
  critical: "text-danger",
};

const HrTodayCard = ({ rows = [], asOfLabel }) => (
  <SectionCard className="flex h-full flex-col" data-testid="card-ringkasan-sdm">
    <SectionHeader
      icon={CalendarCheck2}
      title="Ringkasan SDM Hari Ini"
      description={asOfLabel ? `Data per ${asOfLabel}` : "Kondisi kepegawaian terkini"}
    />

    <div className="grid flex-1 grid-cols-1 gap-2 px-5 pb-5 sm:grid-cols-2">
      {rows.map((row, idx) => (
        <Link
          key={row.key}
          to={row.link}
          data-testid={`hr-today-row-${row.key}`}
          style={{ animationDelay: `${idx * 40}ms` }}
          className="group flex animate-rise items-start gap-3 rounded-lg border border-border bg-card px-3.5 py-3 transition-[background-color,border-color] duration-150 hover:border-border-strong hover:bg-surface-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
        >
          <span
            className={cn("mt-[7px] h-2 w-2 shrink-0 rounded-full", TONE_DOT[row.tone] || TONE_DOT.normal)}
            aria-hidden="true"
          />
          <span className="min-w-0 flex-1">
            <span className="flex items-baseline justify-between gap-2">
              <span className="truncate text-[12.5px] font-medium text-ink-2">{row.label}</span>
              <span
                className={cn(
                  "shrink-0 text-[18px] font-semibold leading-none tracking-[-0.01em]",
                  TONE_VALUE[row.tone] || TONE_VALUE.normal
                )}
                data-numeric="true"
              >
                {row.value}
              </span>
            </span>
            <span className="mt-1 flex items-center gap-1 text-[11.5px] leading-[1.45] text-ink-3">
              <span className="min-w-0 truncate">{row.meta}</span>
              <ChevronRight className="h-3 w-3 shrink-0 opacity-0 transition-opacity duration-150 group-hover:opacity-70" />
            </span>
          </span>
        </Link>
      ))}
    </div>
  </SectionCard>
);

export default HrTodayCard;
