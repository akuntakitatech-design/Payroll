import React from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, ChevronRight, FileWarning, Info, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import SectionCard, { SectionHeader } from "./SectionCard";

/**
 * Kartu prioritas "Perlu Ditindaklanjuti".
 *
 * Hanya berisi hal yang benar-benar butuh keputusan manusia. Tingkat urgensi
 * dibatasi tiga (critical / warning / info) agar tidak berubah menjadi
 * pelangi badge yang melelahkan mata.
 */
const SEVERITY = {
  critical: {
    icon: AlertTriangle,
    label: "Segera",
    strip: "bg-danger",
    chip: "border-danger-border bg-danger-soft text-danger",
    iconColor: "text-danger",
  },
  warning: {
    icon: FileWarning,
    label: "Perlu dicek",
    strip: "bg-warning",
    chip: "border-warning-border bg-warning-soft text-warning",
    iconColor: "text-warning",
  },
  info: {
    icon: Info,
    label: "Informasi",
    strip: "bg-info",
    chip: "border-info-border bg-info-soft text-info",
    iconColor: "text-info",
  },
};

const PriorityCard = ({ items = [] }) => {
  const navigate = useNavigate();
  const criticalCount = items.filter((i) => i.severity === "critical").length;

  return (
    <SectionCard className="flex h-full flex-col" data-testid="card-perlu-ditindaklanjuti">
      <SectionHeader
        icon={ShieldCheck}
        title="Perlu Ditindaklanjuti"
        description="Kondisi normal ditangani sistem. Di sini hanya hal yang butuh keputusan Anda."
        aside={
          <span
            className={cn(
              "inline-flex items-center rounded-full border px-2.5 py-1 text-[11.5px] font-semibold",
              criticalCount > 0
                ? "border-danger-border bg-danger-soft text-danger"
                : items.length > 0
                  ? "border-warning-border bg-warning-soft text-warning"
                  : "border-success-border bg-success-soft text-success"
            )}
            data-numeric="true"
            data-testid="dashboard-attention-count"
          >
            {items.length} item
          </span>
        }
      />

      <div className="flex-1 space-y-2 px-5 pb-5" data-testid="dashboard-needs-attention-list">
        {items.length === 0 ? (
          <div className="flex items-start gap-3 rounded-lg border border-success-border bg-success-soft px-4 py-4">
            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-success" strokeWidth={1.75} />
            <div>
              <p className="text-[13.5px] font-semibold text-ink-1">Tidak ada yang perlu ditindaklanjuti.</p>
              <p className="mt-0.5 text-[12.5px] leading-[1.5] text-ink-2">
                Konfigurasi dasar sudah lengkap. Sistem akan memberi tahu begitu ada kontrak,
                sertifikasi, atau dokumen yang mendekati masa berakhir.
              </p>
            </div>
          </div>
        ) : (
          items.map((item, idx) => {
            const conf = SEVERITY[item.severity] || SEVERITY.info;
            const Icon = conf.icon;
            return (
              <button
                type="button"
                key={item.key}
                data-testid={`priority-item-${item.key}`}
                onClick={() => navigate(item.action_link)}
                style={{ animationDelay: `${idx * 45}ms` }}
                className="group relative flex w-full animate-rise items-start gap-3 overflow-hidden rounded-lg border border-border bg-card py-3 pl-4 pr-3 text-left transition-[background-color,border-color,box-shadow] duration-150 hover:border-border-strong hover:bg-surface-1 hover:shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
              >
                <span
                  className={cn(
                    "absolute left-0 top-2.5 bottom-2.5 w-[3px] rounded-full",
                    conf.strip
                  )}
                  aria-hidden="true"
                />
                <Icon
                  className={cn("mt-0.5 h-4 w-4 shrink-0", conf.iconColor)}
                  strokeWidth={1.75}
                />
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="text-[13.5px] font-semibold text-ink-1">{item.title}</span>
                    <span
                      className={cn(
                        "rounded-full border px-2 py-0.5 text-[11px] font-medium leading-4",
                        conf.chip
                      )}
                    >
                      {conf.label}
                    </span>
                  </span>
                  <span className="mt-1 block text-[12.5px] leading-[1.5] text-ink-3">
                    {item.description}
                  </span>
                  <span className="mt-1.5 inline-flex items-center gap-1 text-[12.5px] font-medium text-primary">
                    {item.action_label}
                    <ChevronRight className="h-3.5 w-3.5 transition-transform duration-150 group-hover:translate-x-0.5" />
                  </span>
                </span>
              </button>
            );
          })
        )}
      </div>
    </SectionCard>
  );
};

export default PriorityCard;
