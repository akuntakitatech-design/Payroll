import { useEffect, useState } from "react";
import { api } from "@/lib/api";

let cached = null;
let pending = null;

// Status gagal dimuat tidak boleh dianggap otomatis mengizinkan operasi tulis.
export const useSystemMode = () => {
  const [mode, setMode] = useState(cached);
  useEffect(() => {
    let alive = true;
    if (cached) { setMode(cached); return; }
    if (!pending) {
      pending = api.get("/system/mode").then(({ data }) => {
        cached = data;
        return data;
      }).finally(() => { pending = null; });
    }
    pending.then((data) => { if (alive) setMode(data); }).catch(() => {
      if (alive) setMode({ read_only: true, unavailable: true });
    });
    return () => { alive = false; };
  }, []);
  return mode || { read_only: true, loading: true };
};
