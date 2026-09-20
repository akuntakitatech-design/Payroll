import { useEffect, useState } from "react";
import { api } from "@/lib/api";

/**
 * Membaca mode operasi backend dari GET /api/system/mode.
 *
 * Dipakai untuk menampilkan pil "Mode hanya-baca" di topbar ketika aplikasi
 * terhubung ke database & storage produksi tetapi seluruh operasi tulis
 * sengaja dinonaktifkan.
 */
let cached = null;

export const useSystemMode = () => {
  const [mode, setMode] = useState(cached);

  useEffect(() => {
    if (cached) return;
    let alive = true;
    api
      .get("/system/mode")
      .then((res) => {
        cached = res.data;
        if (alive) setMode(res.data);
      })
      .catch(() => {
        // Backend versi lama belum punya endpoint ini - cukup abaikan.
        cached = { read_only: false };
        if (alive) setMode(cached);
      });
    return () => {
      alive = false;
    };
  }, []);

  return mode || { read_only: false };
};
