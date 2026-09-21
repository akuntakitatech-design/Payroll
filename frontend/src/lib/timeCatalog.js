import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

/**
 * Katalog Time Management (status, shift, lokasi kerja, jenis cuti, kebijakan).
 * Di-cache per sesi perusahaan aktif agar halaman terasa ringan.
 */
let cache = null;
let inflight = null;

export const invalidateTimeCatalog = () => {
  cache = null;
  inflight = null;
};

export const fetchTimeCatalog = async (force = false) => {
  if (cache && !force) return cache;
  if (inflight && !force) return inflight;
  inflight = api.get("/time/catalog").then(({ data }) => {
    cache = data;
    inflight = null;
    return data;
  });
  return inflight;
};

export const useTimeCatalog = () => {
  const [catalog, setCatalog] = useState(cache);
  const [loading, setLoading] = useState(!cache);
  const [error, setError] = useState(null);

  const reload = useCallback(async (force = true) => {
    setLoading(true);
    try {
      const data = await fetchTimeCatalog(force);
      setCatalog(data);
      setError(null);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!cache) reload(false);
    else setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { catalog, loading, error, reload };
};

/** Cari label dari daftar katalog [{key,label}]. */
export const labelOf = (list, key, fallback = "-") =>
  (list || []).find((item) => item.key === key)?.label || fallback;

export const toneOf = (list, key, fallback = "neutral") =>
  (list || []).find((item) => item.key === key)?.tone || fallback;

/** Opsi untuk komponen Select dari katalog. */
export const asOptions = (list, { valueKey = "key", labelKey = "label" } = {}) =>
  (list || []).map((item) => ({ value: String(item[valueKey]), label: item[labelKey] }));

/** 495 -> "8j 15m" */
export const minutesToLabel = (total) => {
  if (total === null || total === undefined || total === "") return "-";
  const value = Number(total);
  if (Number.isNaN(value)) return "-";
  if (value === 0) return "0m";
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  const hours = Math.floor(abs / 60);
  const mins = abs % 60;
  if (!hours) return `${sign}${mins}m`;
  if (!mins) return `${sign}${hours}j`;
  return `${sign}${hours}j ${mins}m`;
};

/** "2026-09-21T01:00:00Z" -> "08:00" pada zona waktu perangkat. */
export const timeOf = (value) => {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
};

export const dayLabel = (isoDate) => {
  if (!isoDate) return "-";
  const d = new Date(`${String(isoDate).slice(0, 10)}T00:00:00`);
  if (Number.isNaN(d.getTime())) return String(isoDate);
  return d.toLocaleDateString("id-ID", { weekday: "short", day: "2-digit", month: "short", year: "numeric" });
};

export const shortDay = (isoDate) => {
  if (!isoDate) return "-";
  const d = new Date(`${String(isoDate).slice(0, 10)}T00:00:00`);
  if (Number.isNaN(d.getTime())) return String(isoDate);
  return d.toLocaleDateString("id-ID", { day: "2-digit", month: "short" });
};

export const todayIso = () => {
  const d = new Date();
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 10);
};

export const currentPeriodKey = () => todayIso().slice(0, 7);

/** Daftar periode (YYYY-MM) untuk filter: 12 bulan ke belakang, 2 bulan ke depan. */
export const periodOptions = () => {
  const now = new Date();
  const out = [];
  for (let i = 2; i >= -12; i -= 1) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    out.push({
      value: key,
      label: d.toLocaleDateString("id-ID", { month: "long", year: "numeric" }),
    });
  }
  return out;
};

export const monthBounds = (periodKey) => {
  const [y, m] = String(periodKey || currentPeriodKey()).split("-").map(Number);
  const start = new Date(y, m - 1, 1);
  const end = new Date(y, m, 0);
  const fmt = (d) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  return { dateFrom: fmt(start), dateTo: fmt(end) };
};

/** Jam pada zona waktu perusahaan (mis. "Asia/Jakarta"); fallback zona perangkat. */
export const timeInZone = (value, timeZone) => {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "-";
  try {
    return d.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", timeZone: timeZone || undefined });
  } catch (e) {
    return d.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
  }
};

/** Jam:menit:detik pada zona waktu perusahaan untuk jam berjalan. */
export const clockInZone = (value, timeZone) => {
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return "--:--:--";
  try {
    return d.toLocaleTimeString("id-ID", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      timeZone: timeZone || undefined,
    });
  } catch (e) {
    return d.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }
};
