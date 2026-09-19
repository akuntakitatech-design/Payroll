import dayjs from "dayjs";
import "dayjs/locale/id";
import relativeTime from "dayjs/plugin/relativeTime";

dayjs.extend(relativeTime);
dayjs.locale("id");

export const formatDate = (value, pattern = "DD MMM YYYY") => {
  if (!value) return "-";
  const d = dayjs(value);
  return d.isValid() ? d.format(pattern) : String(value);
};

export const formatDateTime = (value) => formatDate(value, "DD MMM YYYY, HH:mm");

export const fromNow = (value) => {
  if (!value) return "-";
  const d = dayjs(value);
  return d.isValid() ? d.fromNow() : "-";
};

export const formatNumber = (value) => {
  if (value === null || value === undefined || value === "") return "-";
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  return new Intl.NumberFormat("id-ID").format(n);
};

export const formatCurrency = (value, currency = "IDR") => {
  if (value === null || value === undefined || value === "") return "-";
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  return new Intl.NumberFormat("id-ID", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(n);
};

export const formatFileSize = (bytes) => {
  if (!bytes) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let size = Number(bytes);
  let i = 0;
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024;
    i += 1;
  }
  return `${size.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
};

export const initials = (name) => {
  if (!name) return "?";
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0])
    .join("")
    .toUpperCase();
};

export const boolLabel = (value) => (value ? "Ya" : "Tidak");

export const STATUS_LABELS = {
  active: "Aktif",
  inactive: "Nonaktif",
  archived: "Diarsipkan",
  deleted: "Dihapus",
};

export const daysUntil = (value) => {
  if (!value) return null;
  const d = dayjs(value);
  if (!d.isValid()) return null;
  return d.startOf("day").diff(dayjs().startOf("day"), "day");
};
