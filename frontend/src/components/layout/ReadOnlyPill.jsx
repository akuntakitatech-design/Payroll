import React from "react";
import { Lock } from "lucide-react";
import { useSystemMode } from "@/lib/useSystemMode";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

/**
 * Pil penanda mode hanya-baca.
 *
 * Ditampilkan hanya bila backend melaporkan `read_only: true`, yaitu saat
 * aplikasi terhubung ke database & object storage PRODUKSI tetapi seluruh
 * operasi tulis sengaja dinonaktifkan. Dibuat ringkas agar informatif tanpa
 * memakan ruang topbar.
 */
const ReadOnlyPill = () => {
  const mode = useSystemMode();
  if (!mode?.read_only) return null;

  return (
    <TooltipProvider>
      <Tooltip delayDuration={150}>
        <TooltipTrigger asChild>
          <span
            data-testid="read-only-mode-pill"
            className="hidden shrink-0 items-center gap-1.5 rounded-full border border-warning-border bg-warning-soft px-2.5 py-1 text-[11.5px] font-medium text-warning lg:inline-flex"
          >
            <Lock className="h-3.5 w-3.5" strokeWidth={2.1} />
            Mode hanya-baca
          </span>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-[20rem]">
          <p className="text-[12px] leading-[1.5]">
            Terhubung ke database &amp; penyimpanan <strong>produksi</strong>. Data yang tampil adalah
            data asli, dan semua perubahan dinonaktifkan untuk melindunginya.
          </p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};

export default ReadOnlyPill;
