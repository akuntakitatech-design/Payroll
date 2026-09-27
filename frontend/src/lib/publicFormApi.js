/**
 * 01G-B - Klien API Formulir Publik Karyawan.
 * - TIDAK memakai instance `api` HRIS (tidak ada token HRIS / interceptor login).
 * - Token sesi publik hanya di sessionStorage (per tab, hilang saat tab ditutup) - tidak di URL / localStorage.
 * - Tidak ada console.log nilai form/token. Error dinormalisasi ke { status, detail, errors, rejected }.
 */
const BASE = `${process.env.REACT_APP_BACKEND_URL}/api/public/employee-form`;
const KEY = (scope) => `kk_pef_session:${scope}`;

export const sessionStore = {
  get: (scope) => {
    try {
      return window.sessionStorage.getItem(KEY(scope));
    } catch {
      return null;
    }
  },
  set: (scope, token) => {
    try {
      window.sessionStorage.setItem(KEY(scope), token);
    } catch {
      /* storage tidak tersedia: sesi hanya di memori */
    }
  },
  clear: (scope) => {
    try {
      window.sessionStorage.removeItem(KEY(scope));
    } catch {
      /* abaikan */
    }
  },
};

export class PublicFormError extends Error {
  constructor(status, body) {
    const detail = typeof body?.detail === "string" ? body.detail : "Terjadi kendala. Silakan coba lagi.";
    super(detail);
    this.status = status;
    this.detail = detail;
    this.errors = body?.errors && !Array.isArray(body.errors) ? body.errors : {};
    this.rejected = body?.rejected_fields || [];
  }
}

async function request(method, path, { token, json, form } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  let body;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (form) {
    body = form;
  }
  let res;
  try {
    res = await fetch(`${BASE}${path}`, { method, headers, body, credentials: "omit", cache: "no-store", referrerPolicy: "no-referrer" });
  } catch {
    throw new PublicFormError(0, { detail: "Koneksi internet bermasalah. Periksa jaringan Anda lalu coba lagi." });
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) throw new PublicFormError(res.status, data);
  return data;
}

export const publicFormApi = {
  portal: (code) => request("GET", `/portal/${encodeURIComponent(code)}`),
  logoUrl: (code) => `${BASE}/portal/${encodeURIComponent(code)}/logo`,
  verifyPortal: (code, payload) => request("POST", `/portal/${encodeURIComponent(code)}/verify`, { json: payload }),
  form: (s) => request("GET", "/form", { token: s }),
  saveDraft: (s, payload) => request("PUT", "/draft", { token: s, json: payload }),
  submit: (s, version) => request("POST", "/submit", { token: s, json: { version } }),
  upload: (s, file, code) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("document_type_code", code);
    return request("POST", "/attachments", { token: s, form: fd });
  },
  removeFile: (s, id) => request("DELETE", `/attachments/${encodeURIComponent(id)}`, { token: s }),
  logout: (s) => request("POST", "/logout", { token: s }),
};

/**
 * Analytics lapisan KEDUA. Lapisan utama: index.html tidak pernah memuat/meng-init PostHog pada /public/*.
 * Bila dokumen ini awalnya dimuat dari route internal (navigasi SPA ke /public/*), PostHog mungkin sudah aktif:
 * hentikan capture/recording lalu muat ulang dokumen penuh agar index.html memutuskan ulang (tanpa PostHog)
 * SEBELUM pengguna mengetik apa pun. Mengembalikan true bila halaman sedang dimuat ulang.
 */
export function enforcePublicAnalyticsOff() {
  try {
    const ph = window.posthog;
    if (ph && typeof ph.opt_out_capturing === "function") ph.opt_out_capturing();
    if (ph && typeof ph.stopSessionRecording === "function") ph.stopSessionRecording();
  } catch {
    /* abaikan */
  }
  if (window.__KK_PUBLIC_FORM__ !== true) {
    window.location.replace(window.location.pathname);
    return true;
  }
  return false;
}
