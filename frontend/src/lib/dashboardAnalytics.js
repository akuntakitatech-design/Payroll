import { api } from "@/lib/api";

/** Preset periode dashboard. Nilai tanggal dihitung di klien agar konsisten dengan zona waktu pengguna. */
export const PERIOD_PRESETS = [
  { key: "this_month", label: "Bulan ini" },
  { key: "last_month", label: "Bulan lalu" },
  { key: "last_3m", label: "3 bulan terakhir" },
  { key: "last_6m", label: "6 bulan terakhir" },
  { key: "ytd", label: "Tahun berjalan" },
  { key: "custom", label: "Rentang khusus" },
];

const iso = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/** Rentang [from, to] untuk sebuah preset. `custom` memakai nilai pengguna apa adanya. */
export const periodRange = (preset, custom = {}) => {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth(), 1);
  if (preset === "custom") {
    return { from: custom.from || iso(first), to: custom.to || iso(now) };
  }
  if (preset === "last_month") {
    const start = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const end = new Date(now.getFullYear(), now.getMonth(), 0);
    return { from: iso(start), to: iso(end) };
  }
  if (preset === "last_3m") {
    const start = new Date(now.getFullYear(), now.getMonth() - 2, 1);
    return { from: iso(start), to: iso(now) };
  }
  if (preset === "last_6m") {
    const start = new Date(now.getFullYear(), now.getMonth() - 5, 1);
    return { from: iso(start), to: iso(now) };
  }
  if (preset === "ytd") {
    return { from: `${now.getFullYear()}-01-01`, to: iso(now) };
  }
  return { from: iso(first), to: iso(now) };
};

/** Filter yang dikirim ke API. Nilai kosong tidak ikut dikirim. */
export const FILTER_FIELDS = [
  { key: "branch_id", label: "Unit Operasional", optionKey: "branches" },
  { key: "work_location_id", label: "Lokasi Kerja", optionKey: "work_locations" },
  { key: "project_id", label: "Proyek", optionKey: "projects" },
  { key: "department_id", label: "Departemen", optionKey: "departments" },
  { key: "division_id", label: "Divisi", optionKey: "divisions" },
  { key: "position_id", label: "Jabatan", optionKey: "positions" },
  { key: "job_grade_id", label: "Grade / Level", optionKey: "job_grades" },
  { key: "cost_center_id", label: "Cost Center", optionKey: "cost_centers" },
  { key: "employment_status_id", label: "Status Kepegawaian", optionKey: "employment_statuses" },
  { key: "contract_type_id", label: "Tipe Kontrak", optionKey: "contract_types" },
  { key: "roster_pattern_id", label: "Pola Roster", optionKey: "roster_patterns" },
];

export const PRIMARY_FILTERS = ["branch_id", "project_id", "department_id"];
export const ADVANCED_FILTERS = FILTER_FIELDS.filter((f) => !PRIMARY_FILTERS.includes(f.key));

/** Filter cross-filter dari klik grafik (atribut personal). */
export const CROSS_FILTERS = [
  { key: "gender", label: "Jenis Kelamin" },
  { key: "age_band", label: "Kelompok Usia" },
  { key: "education", label: "Pendidikan" },
  { key: "marital_status", label: "Status Pernikahan" },
  { key: "religion", label: "Agama" },
];

export const buildParams = ({ preset, custom, filters, category }) => {
  const range = periodRange(preset, custom);
  const params = { category, date_from: range.from, date_to: range.to };
  [...FILTER_FIELDS, ...CROSS_FILTERS].forEach(({ key }) => {
    const value = filters[key];
    if (value) params[key] = value;
  });
  return params;
};

/** Permintaan analitik; pemanggil mengatur AbortController untuk dedupe. */
export const fetchAnalytics = (params, signal) =>
  api.get("/dashboard/analytics", { params, signal });

const PREFS_PREFIX = "hr-command-center";

const prefsKey = (session) => {
  const userId = session?.user?.id || "anon";
  const companyId = session?.active_company?.id || "none";
  return `${PREFS_PREFIX}:${userId}:${companyId}`;
};

export const DEFAULT_WIDGETS = [
  "kpi",
  "action_center",
  "demography",
  "organization",
  "movement",
  "insights",
];

export const loadPrefs = (session) => {
  try {
    const raw = window.localStorage.getItem(prefsKey(session));
    if (!raw) return { widgets: {}, order: [...DEFAULT_WIDGETS], savedFilters: [] };
    const parsed = JSON.parse(raw);
    return {
      widgets: parsed.widgets || {},
      order: Array.isArray(parsed.order) && parsed.order.length ? parsed.order : [...DEFAULT_WIDGETS],
      savedFilters: Array.isArray(parsed.savedFilters) ? parsed.savedFilters : [],
    };
  } catch {
    return { widgets: {}, order: [...DEFAULT_WIDGETS], savedFilters: [] };
  }
};

export const savePrefs = (session, prefs) => {
  try {
    window.localStorage.setItem(prefsKey(session), JSON.stringify(prefs));
  } catch {
    /* localStorage penuh / diblokir: preferensi diabaikan, dashboard tetap berjalan */
  }
};

export const formatNumber = (value) => {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("id-ID").format(value);
};

export const formatPct = (value, digits = 1) => {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${Number(value).toLocaleString("id-ID", { minimumFractionDigits: 0, maximumFractionDigits: digits })}%`;
};

export const formatMoney = (value) => {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `Rp ${new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 }).format(value)}`;
};

export const formatMinutes = (value) => {
  if (value === null || value === undefined) return "—";
  const hours = Math.floor(value / 60);
  const minutes = Math.round(value % 60);
  return `${formatNumber(hours)}j ${minutes}m`;
};
