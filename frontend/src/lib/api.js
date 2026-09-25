import axios from "axios";

// Kosong => panggil /api relatif (produksi: Nginx mem-proxy ke backend).
// Terisi => panggil backend langsung (preview Emergent / backend berdomain sendiri).
export const BACKEND_URL = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");
export const API = `${BACKEND_URL}/api`;

export const TOKEN_KEY = "hris_access_token";
export const REFRESH_KEY = "hris_refresh_token";

export const api = axios.create({ baseURL: API, timeout: 60000 });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

let onUnauthorized = null;
export const setUnauthorizedHandler = (fn) => {
  onUnauthorized = fn;
};

// Tenant dinonaktifkan Platform Admin / masa layanan berakhir -> sesi diakhiri dengan pesan yang jelas.
export const FLASH_KEY = "hris_login_flash";
let onTenantInactive = null;
export const setTenantInactiveHandler = (fn) => {
  onTenantInactive = fn;
};

// Akun masih memakai password sementara -> arahkan ke halaman wajib ganti password.
let onPasswordChangeRequired = null;
export const setPasswordChangeRequiredHandler = (fn) => {
  onPasswordChangeRequired = fn;
};

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    const url = error?.config?.url || "";
    if (status === 401 && !url.includes("/auth/login")) {
      if (onUnauthorized) onUnauthorized();
    }
    if (status === 403 && error?.response?.headers?.["x-password-change-required"] === "true") {
      if (onPasswordChangeRequired) onPasswordChangeRequired();
    }
    const tenantStatus = error?.response?.headers?.["x-tenant-status"];
    if (status === 403 && (tenantStatus === "inactive" || tenantStatus === "expired") && !url.includes("/auth/login")) {
      const detail = error?.response?.data?.detail;
      try {
        sessionStorage.setItem(
          FLASH_KEY,
          typeof detail === "string"
            ? detail
            : tenantStatus === "expired"
              ? "Masa layanan tenant telah berakhir. Silakan hubungi administrator platform."
              : "Tenant Anda sedang dinonaktifkan."
        );
      } catch {
        /* ignore */
      }
      if (onTenantInactive) onTenantInactive();
    }
    return Promise.reject(error);
  }
);

export const errorMessage = (error, fallback = "Terjadi kesalahan. Silakan coba lagi.") => {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d) => d.msg || String(d)).join("; ");
  }
  if (error?.message === "Network Error") {
    return "Tidak dapat menghubungi server. Periksa koneksi internet Anda.";
  }
  if (error?.code === "ECONNABORTED") {
    return "Server terlalu lama merespons. Coba lagi beberapa saat.";
  }
  const status = error?.response?.status;
  if (status === 502 || status === 503 || status === 504) {
    return `Server aplikasi belum siap atau sedang dimulai ulang (HTTP ${status}). Coba lagi dalam beberapa saat.`;
  }
  if (status >= 500) {
    return `Terjadi gangguan pada server (HTTP ${status}). Silakan coba lagi.`;
  }
  return fallback;
};
