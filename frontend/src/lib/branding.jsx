import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, BACKEND_URL } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Branding PLATFORM (KelolaKita). Selalu dibaca dari backend (/api/public/branding) -
 * nilai di bawah hanya cadangan saat server belum merespons, bukan sumber utama.
 * Branding platform TERPISAH dari logo tenant (lihat components/common/TenantLogo.jsx).
 */
const FALLBACK = {
  app_name: "KelolaKita",
  subtitle: "HRIS & Payroll",
  tagline: "",
  login_headline: "",
  login_supporting_text: "",
  has_logo: false,
  logo_url: null,
  has_favicon: false,
  favicon_url: null,
  max_logo_mb: 10,
};

const BrandingContext = createContext({ branding: FALLBACK, loaded: false, refresh: () => {} });

export const assetUrl = (path) => (path ? `${BACKEND_URL}${path}` : null);

const applyFavicon = (branding) => {
  const href = branding.favicon_url ? assetUrl(branding.favicon_url) : `${process.env.PUBLIC_URL || ""}/favicon.svg`;
  let link = document.querySelector("link[rel='icon']");
  if (!link) {
    link = document.createElement("link");
    link.rel = "icon";
    document.head.appendChild(link);
  }
  if (branding.favicon_url) link.removeAttribute("type");
  else link.type = "image/svg+xml";
  link.href = href;
};

export const BrandingProvider = ({ children }) => {
  const [branding, setBranding] = useState(FALLBACK);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get("/public/branding");
      setBranding({ ...FALLBACK, ...data });
      applyFavicon(data);
    } catch {
      /* tetap pakai cadangan */
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Halaman lama menulis judul tab "... · HRIS Suite". Ganti otomatis dengan nama produk
  // dari konfigurasi branding agar judul tidak hardcoded di setiap halaman.
  useEffect(() => {
    const product = [branding.app_name, branding.subtitle].filter(Boolean).join(" — ");
    const fix = () => {
      const t = document.title || "";
      if (/HRIS( & Payroll)? Suite/.test(t)) document.title = t.replace(/HRIS( & Payroll)? Suite/g, product);
    };
    fix();
    const el = document.querySelector("title");
    if (!el || typeof MutationObserver === "undefined") return undefined;
    const obs = new MutationObserver(fix);
    obs.observe(el, { childList: true, characterData: true, subtree: true });
    return () => obs.disconnect();
  }, [branding.app_name, branding.subtitle]);

  const value = useMemo(() => ({ branding, loaded, refresh, setBranding }), [branding, loaded, refresh]);
  return <BrandingContext.Provider value={value}>{children}</BrandingContext.Provider>;
};

export const useBranding = () => useContext(BrandingContext);

/** Judul tab browser: "<halaman> · KelolaKita — HRIS & Payroll". */
export const brandTitle = (branding, page) => {
  const product = [branding.app_name, branding.subtitle].filter(Boolean).join(" — ");
  return page ? `${page} · ${product}` : product;
};

/**
 * Logo teks default KelolaKita (sementara, sampai Platform Admin mengunggah logo final).
 * Tampil bila belum ada logo custom.
 */
export const DefaultPlatformMark = ({ size = "md", className }) => {
  const box = size === "lg" ? "h-11 w-11 text-lg" : size === "sm" ? "h-7 w-7 text-[13px]" : "h-9 w-9 text-[15px]";
  return (
    <span
      aria-hidden="true"
      className={cn(
        "relative flex shrink-0 items-center justify-center rounded-xl bg-primary font-bold tracking-tight text-primary-foreground shadow-xs",
        box,
        className
      )}
    >
      K
      <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full border-2 border-card bg-destructive" />
    </span>
  );
};

/**
 * Logo PLATFORM: gambar hasil upload Platform Admin, atau logo teks default.
 * variant="full" menampilkan nama aplikasi + subtitle di samping tanda.
 */
export const PlatformLogo = ({ variant = "full", size = "md", inverse = false, className, testId = "platform-logo" }) => {
  const { branding } = useBranding();
  const [broken, setBroken] = useState(false);
  const src = !broken && branding.logo_url ? assetUrl(branding.logo_url) : null;
  const imgH = size === "lg" ? "h-12" : size === "sm" ? "h-7" : "h-9";

  useEffect(() => setBroken(false), [branding.logo_url]);

  if (src) {
    return (
      <span className={cn("flex min-w-0 items-center gap-2.5", className)} data-testid={testId}>
        {/* Di latar gelap (hero login), logo custom ditaruh di atas "chip" putih agar warna logo apa pun tetap terbaca. */}
        <span className={cn("flex shrink-0 items-center", inverse && "rounded-xl bg-white px-3 py-2 shadow-sm")}>
          <img
            src={src}
            alt={`Logo ${branding.app_name}`}
            className={cn(imgH, "w-auto max-w-[11rem] shrink-0 object-contain")}
            onError={() => setBroken(true)}
            data-testid={`${testId}-image`}
          />
        </span>
        {variant === "full" && branding.subtitle && (
          <span className={cn("truncate text-[11px] font-medium", inverse ? "text-white/75" : "text-ink-3")}>
            {branding.subtitle}
          </span>
        )}
      </span>
    );
  }
  return (
    <span className={cn("flex min-w-0 items-center gap-2.5", className)} data-testid={testId}>
      <DefaultPlatformMark size={size} className={inverse ? "bg-white text-primary" : undefined} />
      {variant !== "mark" && (
        <span className="min-w-0 leading-tight" data-testid={`${testId}-text`}>
          <span
            className={cn(
              "block truncate font-bold tracking-[-0.01em]",
              size === "lg" ? "text-xl" : "text-[14px]",
              inverse ? "text-white" : "text-ink-1"
            )}
          >
            {branding.app_name}
          </span>
          {branding.subtitle && (
            <span className={cn("block truncate text-[11px] font-medium", inverse ? "text-white/75" : "text-ink-3")}>
              {branding.subtitle}
            </span>
          )}
        </span>
      )}
    </span>
  );
};
