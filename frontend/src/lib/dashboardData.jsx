import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/**
 * Satu sumber data untuk ringkasan dashboard.
 *
 * Dipakai bersama oleh halaman Dashboard dan lonceng notifikasi di topbar,
 * sehingga `/dashboard/summary` hanya dipanggil SEKALI per konteks perusahaan
 * (bukan dua kali). Endpoint ini murni baca, jadi aman pada mode hanya-baca.
 */
const DashboardDataContext = createContext(null);

export const DashboardDataProvider = ({ children }) => {
  const { company } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.get("/dashboard/summary");
      setData(res.data);
    } catch (err) {
      setError(errorMessage(err, "Ringkasan belum dapat ditampilkan. Coba muat ulang halaman."));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!company?.id) {
      setLoading(false);
      return;
    }
    load();
  }, [load, company?.id]);

  const value = useMemo(
    () => ({ data, loading, error, reload: load, attention: data?.attention || [] }),
    [data, loading, error, load]
  );

  return <DashboardDataContext.Provider value={value}>{children}</DashboardDataContext.Provider>;
};

export const useDashboardData = () => {
  const ctx = useContext(DashboardDataContext);
  if (!ctx) {
    return { data: null, loading: false, error: "", reload: () => {}, attention: [] };
  }
  return ctx;
};
