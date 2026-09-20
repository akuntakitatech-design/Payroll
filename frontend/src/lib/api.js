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

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    const url = error?.config?.url || "";
    if (status === 401 && !url.includes("/auth/login")) {
      if (onUnauthorized) onUnauthorized();
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
  return fallback;
};
