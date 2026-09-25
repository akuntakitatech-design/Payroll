// Upgrade 01B - Status Karyawan (status bisnis). 3 kategori sistem TERKUNCI.
// Kode internal: ACTIVE | STANDBY | INACTIVE -> label UI: AKTIF | STANDBY | TIDAK AKTIF.
export const STATUS_CATEGORIES = [
  { value: "ACTIVE", label: "AKTIF" },
  { value: "STANDBY", label: "STANDBY" },
  { value: "INACTIVE", label: "TIDAK AKTIF" },
];

export const CATEGORY_LABELS = Object.fromEntries(STATUS_CATEGORIES.map((c) => [c.value, c.label]));

// Memakai token warna semantik existing (success / warning / muted).
export const CATEGORY_STYLES = {
  ACTIVE: "border-success-border bg-success-soft text-success",
  STANDBY: "border-warning-border bg-warning-soft text-warning",
  INACTIVE: "border-border bg-muted text-muted-foreground",
};

export const CATEGORY_DOT = {
  ACTIVE: "bg-success",
  STANDBY: "bg-warning",
  INACTIVE: "bg-muted-foreground",
};

export const SOURCE_LABELS = {
  MANUAL: "Manual",
  LEGACY_BASELINE: "Baseline migrasi",
  IMPORT: "Impor Excel",
  SYSTEM: "Sistem",
};

// Tanggal hari ini (zona waktu lokal browser) format YYYY-MM-DD untuk batas tanggal efektif.
export const todayISO = () => {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};
