import React, { useEffect, useState } from "react";
import { Building2 } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Logo TENANT (perusahaan) - terpisah dari logo platform.
 * Gambar diambil lewat endpoint ber-autentikasi (token Bearer), sehingga
 * tidak ada URL publik yang bisa dipakai tenant lain:
 *   - source="current"  -> GET /companies/current/logo  (tenant aktif milik user)
 *   - source="platform" -> GET /platform/tenants/{id}/logo (khusus Platform Admin)
 * Bila belum ada logo -> placeholder default perusahaan.
 */
export const TenantLogo = ({ source = "current", tenantId, version, hasLogo, name, size = "md", className, testId = "tenant-logo" }) => {
  const [src, setSrc] = useState(null);
  const box = size === "lg" ? "h-14 w-14" : size === "sm" ? "h-8 w-8" : "h-10 w-10";

  useEffect(() => {
    let revoked = false;
    let objectUrl = null;
    setSrc(null);
    if (!hasLogo) return undefined;
    const url = source === "platform" ? `/platform/tenants/${tenantId}/logo` : "/companies/current/logo";
    api
      .get(url, { responseType: "blob", params: { v: version || undefined } })
      .then(({ data }) => {
        if (revoked) return;
        objectUrl = URL.createObjectURL(data);
        setSrc(objectUrl);
      })
      .catch(() => setSrc(null));
    return () => {
      revoked = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [source, tenantId, version, hasLogo]);

  return (
    <span
      className={cn(
        "flex shrink-0 items-center justify-center overflow-hidden rounded-lg border border-border bg-card",
        box,
        className
      )}
      data-testid={testId}
      data-has-logo={src ? "true" : "false"}
    >
      {src ? (
        <img src={src} alt={`Logo ${name || "perusahaan"}`} className="h-full w-full object-contain p-0.5" data-testid={`${testId}-image`} />
      ) : (
        <span className="flex h-full w-full items-center justify-center bg-secondary text-muted-foreground" data-testid={`${testId}-placeholder`}>
          <Building2 className={size === "lg" ? "h-6 w-6" : "h-4 w-4"} strokeWidth={1.75} />
        </span>
      )}
    </span>
  );
};

/** Ambil versi logo dari logo_url ("/api/companies/current/logo?v=xxxx"). */
export const logoVersion = (company) => {
  const url = company?.logo_url || "";
  const i = url.indexOf("v=");
  return i >= 0 ? url.slice(i + 2) : null;
};

export default TenantLogo;
