import React from "react";
import { AlertTriangle, CalendarClock, ShieldAlert } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Informasi masa layanan tenant aktif (dihitung backend, lihat active_company.subscription).
 * - GRACE           : peringatan masa tenggang (tenant tetap beroperasi).
 * - ACTIVE H-30..H-1: pengingat menjelang berakhir.
 * - EXPIRED         : hanya terlihat oleh Platform Admin (user tenant sudah diblokir backend).
 * Tidak ada notification engine - hanya banner di aplikasi.
 */
const TONES = {
  warning: "border-warning-border bg-warning-soft text-warning",
  info: "border-info-border bg-info-soft text-info",
  danger: "border-danger-border bg-danger-soft text-danger",
};

export const TenantSubscriptionBanner = () => {
  const { company, isSuperAdmin } = useAuth();
  const sub = company?.subscription;
  if (!sub || sub.unlimited) return null;

  let tone = null;
  let Icon = CalendarClock;
  let title = "";
  let body = "";
  if (sub.status === "grace") {
    tone = "warning";
    Icon = AlertTriangle;
    title = "Masa layanan tenant telah berakhir dan sedang berada dalam masa tenggang.";
    body = `Silakan hubungi administrator platform untuk perpanjangan. Masa tenggang sampai ${formatDate(
      sub.grace_end_date
    )} (${sub.grace_days_remaining} hari lagi).`;
  } else if (sub.status === "expired" && isSuperAdmin) {
    tone = "danger";
    Icon = ShieldAlert;
    title = `Mode Platform Admin: masa layanan ${company?.name || "tenant"} telah berakhir.`;
    body = "User tenant tidak dapat masuk ke modul operasional. Data tetap utuh; perpanjang lewat Platform > Tenant Management.";
  } else if (sub.status === "active" && sub.reminder_stage) {
    tone = "info";
    title = `Masa layanan tenant berakhir ${sub.days_remaining === 0 ? "hari ini" : `dalam ${sub.days_remaining} hari`} (${formatDate(
      sub.end_date
    )}).`;
    body = "Silakan hubungi administrator platform untuk perpanjangan agar operasional tidak terhenti.";
  }
  if (!tone) return null;

  return (
    <div
      role="status"
      data-testid={`tenant-subscription-banner-${sub.status}`}
      data-reminder-stage={sub.reminder_stage || undefined}
      className={cn("flex items-start gap-3 border-b px-4 py-2.5 text-[13px] sm:px-6", TONES[tone])}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <div className="min-w-0">
        <p className="font-medium" data-testid="tenant-subscription-banner-title">{title}</p>
        <p className="opacity-90">{body}</p>
      </div>
    </div>
  );
};

export default TenantSubscriptionBanner;
