import React from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Lock } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

/**
 * Kartu KPI dengan empat varian visual.
 *
 * Varian `locked` dipakai ketika datanya BELUM ADA di sistem (mis. modul
 * Absensi yang belum memiliki tabel kehadiran). Kartu tetap tampil sejajar
 * dan setinggi kartu lain, tetapi TIDAK menampilkan angka karangan -
 * hanya keterangan jujur beserta tautan tindak lanjut.
 */
const TONES = {
  normal: {
    iconWrap: "border-primary-border bg-primary-soft text-primary",
    value: "text-ink-1",
  },
  success: {
    iconWrap: "border-success-border bg-success-soft text-success",
    value: "text-ink-1",
  },
  warning: {
    iconWrap: "border-warning-border bg-warning-soft text-warning",
    value: "text-ink-1",
  },
  critical: {
    iconWrap: "border-danger-border bg-danger-soft text-danger",
    value: "text-ink-1",
  },
};

const KpiCard = ({
  label,
  value,
  suffix,
  meta,
  icon: Icon,
  tone = "normal",
  badge,
  link,
  locked = false,
  lockedReason,
  lockedActionLabel = "Lihat Aktivasi Modul",
  testId,
  actionTestId,
}) => {
  const conf = TONES[tone] || TONES.normal;

  if (locked) {
    return (
      <div
        data-testid={testId}
        className="flex flex-col rounded-card border border-locked-border bg-card p-4 shadow-card"
      >
        <div className="flex items-start justify-between gap-3">
          <p className="text-[13px] font-medium text-ink-3">{label}</p>
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-locked-border bg-locked-soft text-locked">
            <Lock className="h-4 w-4" strokeWidth={1.75} />
          </span>
        </div>

        <div className="mt-3 rounded-lg border border-locked-border bg-locked-soft px-3 py-2.5">
          <p className="text-[12.5px] font-medium leading-[1.5] text-ink-2">Data belum tersedia</p>
          {lockedReason && (
            <p className="mt-0.5 text-[11.5px] leading-[1.5] text-ink-3">{lockedReason}</p>
          )}
        </div>

        {link && (
          <Button
            asChild
            variant="outline"
            size="sm"
            className="mt-auto h-8 w-full justify-center pt-0 text-[12.5px]"
          >
            <Link to={link} data-testid={actionTestId} className="mt-3">
              {lockedActionLabel}
            </Link>
          </Button>
        )}
      </div>
    );
  }

  const body = (
    <>
      <div className="flex items-start justify-between gap-3">
        <p className="text-[13px] font-medium text-ink-3">{label}</p>
        {Icon && (
          <span
            className={cn(
              "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border",
              conf.iconWrap
            )}
          >
            <Icon className="h-4 w-4" strokeWidth={1.75} />
          </span>
        )}
      </div>

      <div className="mt-3 flex items-baseline gap-1.5">
        <span
          className={cn("text-[28px] font-semibold leading-[1.1] tracking-[-0.02em]", conf.value)}
          data-numeric="true"
        >
          {value}
        </span>
        {suffix && <span className="text-[14px] font-medium text-ink-3">{suffix}</span>}
      </div>

      <div className="mt-2 flex items-center justify-between gap-2">
        {meta && <p className="text-[12px] leading-[1.5] text-ink-3">{meta}</p>}
        {badge}
      </div>

      {link && (
        <span className="mt-auto inline-flex items-center gap-1 pt-3 text-[12.5px] font-medium text-primary">
          Lihat detail
          <ArrowUpRight className="h-3.5 w-3.5 transition-transform duration-150 group-hover:translate-x-0.5 group-hover:-translate-y-0.5" strokeWidth={2} />
        </span>
      )}
    </>
  );

  if (!link) {
    return (
      <div
        data-testid={testId}
        className="flex flex-col rounded-card border border-border bg-card p-4 shadow-card"
      >
        {body}
      </div>
    );
  }

  return (
    <Link
      to={link}
      data-testid={testId}
      className="group flex flex-col rounded-card border border-border bg-card p-4 shadow-card transition-[box-shadow,border-color] duration-150 hover:border-primary-border hover:shadow-float focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
    >
      {body}
    </Link>
  );
};

export default KpiCard;
