import React from "react";
import { Lock, FlaskConical } from "lucide-react";
import { useSystemMode } from "@/lib/useSystemMode";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

const ReadOnlyPill = () => {
  const mode = useSystemMode();
  if (mode.loading) return <span className="text-[11px] text-muted-foreground" data-testid="environment-loading">Memeriksa lingkungan…</span>;
  const development = mode.environment === "development";
  if (!mode.read_only && !development) return null;
  const Icon = development ? FlaskConical : Lock;
  return <TooltipProvider><Tooltip delayDuration={150}><TooltipTrigger asChild>
    <span tabIndex={0} data-testid={development ? "environment-indicator" : "read-only-mode-pill"} className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-warning-border bg-warning-soft px-2.5 py-1 text-[11px] font-medium text-warning"><Icon className="h-3.5 w-3.5" />{development ? "DEVELOPMENT" : mode.unavailable ? "Mode belum terverifikasi" : "Mode hanya-baca"}</span>
  </TooltipTrigger><TooltipContent side="bottom" className="max-w-xs"><p className="text-[12px] leading-relaxed">{development ? "Lingkungan pengembangan dengan database terpisah. Bukan data produksi. R2 development belum dikonfigurasi." : mode.unavailable ? "Status lingkungan belum dapat dimuat. Perubahan aktivasi modul dinonaktifkan sementara." : "Terhubung ke produksi dalam mode hanya-baca. Perubahan dinonaktifkan untuk melindungi data asli."}</p></TooltipContent></Tooltip></TooltipProvider>;
};
export default ReadOnlyPill;
