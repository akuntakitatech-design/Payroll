import React from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, Bell, FileWarning, Info, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDashboardData } from "@/lib/dashboardData";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

/**
 * Lonceng notifikasi.
 *
 * Isinya BUKAN data hias: diambil dari daftar "Perlu Ditindaklanjuti" yang
 * dihitung backend dari kontrak, sertifikasi, dokumen, dan kelengkapan setup
 * yang sebenarnya. Sumber datanya sama dengan halaman Dashboard sehingga
 * `/dashboard/summary` tetap dipanggil sekali saja.
 */
const ICONS = {
  critical: { icon: AlertTriangle, cls: "text-danger" },
  warning: { icon: FileWarning, cls: "text-warning" },
  info: { icon: Info, cls: "text-info" },
};

const NotificationBell = () => {
  const navigate = useNavigate();
  const { attention, loading } = useDashboardData();
  const count = attention.length;
  const hasCritical = attention.some((a) => a.severity === "critical");

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={count > 0 ? `Notifikasi: ${count} hal perlu ditindaklanjuti` : "Notifikasi"}
          data-testid="topbar-notification-button"
          className="relative flex h-9 w-9 items-center justify-center rounded-lg text-ink-2 transition-colors duration-150 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Bell className="h-[18px] w-[18px]" strokeWidth={1.9} />
          {!loading && count > 0 && (
            <span
              className={cn(
                "absolute right-1.5 top-1.5 flex h-[15px] min-w-[15px] items-center justify-center rounded-full px-[3px] text-[9.5px] font-bold leading-none text-white ring-2 ring-card",
                hasCritical ? "bg-danger" : "bg-warning"
              )}
              data-numeric="true"
              data-testid="topbar-notification-badge"
            >
              {count > 9 ? "9+" : count}
            </span>
          )}
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-[22rem] p-0" data-testid="topbar-notification-menu">
        <DropdownMenuLabel className="flex items-center justify-between gap-2 px-3 py-2.5">
          <span className="text-[13px] font-semibold text-ink-1">Perlu ditindaklanjuti</span>
          <span className="text-[11.5px] font-normal text-ink-3" data-numeric="true">
            {count} item
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator className="my-0" />

        {count === 0 ? (
          <div className="flex flex-col items-center gap-2 px-4 py-7 text-center">
            <span className="flex h-10 w-10 items-center justify-center rounded-full border border-success-border bg-success-soft text-success">
              <ShieldCheck className="h-5 w-5" strokeWidth={1.75} />
            </span>
            <p className="text-[12.5px] font-medium text-ink-1">Tidak ada notifikasi</p>
            <p className="max-w-[26ch] text-[11.5px] leading-[1.5] text-ink-3">
              Sistem akan memberi tahu bila ada kontrak, sertifikasi, atau dokumen yang perlu diperiksa.
            </p>
          </div>
        ) : (
          <div className="max-h-[22rem] overflow-y-auto scrollbar-thin py-1">
            {attention.map((item) => {
              const conf = ICONS[item.severity] || ICONS.info;
              const Icon = conf.icon;
              return (
                <DropdownMenuItem
                  key={item.key}
                  onClick={() => navigate(item.action_link)}
                  data-testid={`notification-item-${item.key}`}
                  className="flex cursor-pointer items-start gap-2.5 px-3 py-2.5"
                >
                  <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", conf.cls)} strokeWidth={1.9} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[12.5px] font-medium leading-snug text-ink-1">
                      {item.title}
                    </span>
                    <span className="mt-0.5 block text-[11.5px] leading-[1.45] text-ink-3">
                      {item.action_label}
                    </span>
                  </span>
                </DropdownMenuItem>
              );
            })}
          </div>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export default NotificationBell;
