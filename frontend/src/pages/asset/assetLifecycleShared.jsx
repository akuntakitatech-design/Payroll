import React, { useEffect, useRef, useState } from "react";
import { ChevronsUpDown, Download, Eye, FileText, Loader2, Search, UserRound, X } from "lucide-react";
import { toast } from "sonner";

import { api, errorMessage } from "@/lib/api";
import { downloadFile } from "@/lib/download";
import { formatDate } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

// Phase 2A CP2 - komponen bersama siklus Penyerahan / Pengembalian / Pemeriksaan + Dokumen BAST.

export const BADGE_TONE = {
  success: "border-success-border bg-success-soft text-success",
  warning: "border-warning-border bg-warning-soft text-warning",
  danger: "border-danger-border bg-danger-soft text-danger",
  info: "border-info-border bg-info-soft text-info",
  teal: "border-[hsl(var(--teal-border))] bg-[hsl(var(--teal-soft))] text-[hsl(var(--teal))]",
  purple: "border-[hsl(var(--maintenance-border))] bg-[hsl(var(--maintenance-soft))] text-[hsl(var(--maintenance))]",
  muted: "border-border bg-muted text-muted-foreground",
};

export const STATE_META = {
  DRAFT: { label: "Draft", tone: "muted" },
  PUBLISHED: { label: "Terbit", tone: "success" },
  CANCELLED: { label: "Dibatalkan", tone: "muted" },
  ISSUED: { label: "Terbit", tone: "success" },
  PENDING: { label: "Menunggu Pemeriksaan", tone: "warning" },
  COMPLETED: { label: "Selesai", tone: "success" },
  ACTIVE: { label: "Aktif", tone: "info" },
  CLOSED: { label: "Ditutup", tone: "muted" },
  IN_USE: { label: "Dipakai", tone: "teal" },
  PENDING_INSPECTION: { label: "Menunggu Pemeriksaan", tone: "warning" },
  READY: { label: "Siap Pakai", tone: "success" },
  MAINTENANCE: { label: "Perbaikan", tone: "purple" },
  DAMAGED: { label: "Rusak", tone: "danger" },
  LOST: { label: "Hilang", tone: "danger" },
  DISPOSED: { label: "Dihapuskan", tone: "muted" },
};

export const INSPECTION_RESULTS = [
  { value: "READY", label: "Siap Pakai", help: "Aset layak dan dapat diserahkan kembali." },
  { value: "MAINTENANCE", label: "Perbaikan", help: "Aset perlu diperbaiki sebelum dipakai lagi." },
  { value: "DAMAGED", label: "Rusak", help: "Aset rusak dan tidak dapat dipakai." },
  { value: "LOST", label: "Hilang", help: "Hanya bila aset benar-benar tidak kembali / hilang." },
];

export const BAST_TYPE_LABEL = { HANDOVER: "Penyerahan", RETURN: "Pengembalian", EXISTING: "Existing / Saldo Awal" };

export const StateBadge = ({ state, testId, className }) => {
  const meta = STATE_META[state] || { label: state || "-", tone: "muted" };
  return (
    <Badge variant="outline" className={cn("whitespace-nowrap font-medium", BADGE_TONE[meta.tone], className)} data-testid={testId}>
      {meta.label}
    </Badge>
  );
};

export const todayIso = () => {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};

export const toOptions = (rows, labelKey = "name") => (rows || []).map((r) => ({ value: r.id, label: r[labelKey] || "-" }));

/** Pesan standar saat BAST terbit (CP2.1). */
export const bastIssuedMessage = (number) => `BAST berhasil diterbitkan: ${number || "-"}`;

const BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"];

/** Snapshot `issued_at` ("YYYY-MM-DD HH:MM UTC" / ISO) -> "28 September 2026, 15:34 WIB" (Asia/Jakarta, UTC+7). */
export const formatIssuedWib = (value) => {
  if (!value) return "-";
  const m = String(value).match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
  const d = m ? new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5])) : new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  const w = new Date(d.getTime() + 7 * 3600 * 1000);
  const pad = (n) => String(n).padStart(2, "0");
  return `${w.getUTCDate()} ${BULAN[w.getUTCMonth()]} ${w.getUTCFullYear()}, ${pad(w.getUTCHours())}:${pad(w.getUTCMinutes())} WIB`;
};

/** Aksi utama baris daftar: tombol "Detail" yang terlihat (bukan hanya menu ⋯). */
export const DetailButton = ({ onClick, testId, label = "Detail" }) => (
  <Button variant="outline" size="sm" className="h-8" onClick={(e) => { e.stopPropagation(); onClick(); }} data-testid={testId}>
    <Eye className="h-4 w-4 sm:mr-1.5" /><span className="hidden sm:inline">{label}</span>
  </Button>
);

/** Kartu detail per aset di form: judul "Aset n dari N" + kode/nama, isian berlabel jelas. */
export const AssetItemCard = ({ index, total, code, name, onRemove, children, testId }) => (
  <div className="rounded-md border border-border bg-card" data-testid={testId}>
    <div className="flex items-start justify-between gap-2 border-b border-border bg-muted/40 px-3 py-2">
      <div className="min-w-0 text-sm">
        <span className="text-[12px] font-medium text-muted-foreground">Aset {index} dari {total}</span>
        <span className="block truncate font-semibold">{code} <span className="font-normal text-muted-foreground">— {name}</span></span>
      </div>
      {onRemove && (
        <Button variant="ghost" size="sm" className="h-8 px-2" onClick={onRemove} aria-label={`Hapus ${code} dari daftar`} data-testid={testId && `${testId}-remove`}>
          <X className="h-4 w-4" />
        </Button>
      )}
    </div>
    <div className="grid gap-3 p-3 sm:grid-cols-3">{children}</div>
  </div>
);

export const ItemField = ({ label, htmlFor, required, children }) => (
  <div className="min-w-0 space-y-1">
    <Label htmlFor={htmlFor} className="text-[12px]">{label}{required && <span className="text-danger"> *</span>}</Label>
    {children}
  </div>
);

/**
 * Pencarian karyawan server-side (CP2.1): debounce, limit + "muat lebih banyak", loading/empty state, hapus pilihan.
 * Cakupan Data 01I ditegakkan backend di SQL - hasil hanya karyawan dalam scope user.
 */
export const EmployeeSearchField = ({ label = "Karyawan", required, endpoint, value, selected, onSelect, testId, disabled, hint }) => {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [items, setItems] = useState([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const reqId = useRef(0);
  const LIMIT = 20;

  useEffect(() => {
    if (!open) return undefined;
    const t = setTimeout(async () => {
      const id = ++reqId.current;
      setLoading(true);
      setError("");
      try {
        const { data } = await api.get(endpoint, { params: { q: q.trim() || undefined, page, limit: LIMIT } });
        if (id !== reqId.current) return;
        setItems((prev) => (page === 1 ? data.items : [...prev, ...data.items]));
        setTotal(data.total);
      } catch (e) {
        if (id === reqId.current) setError(errorMessage(e, "Pencarian karyawan gagal."));
      } finally {
        if (id === reqId.current) setLoading(false);
      }
    }, page === 1 ? 300 : 0);
    return () => clearTimeout(t);
  }, [open, q, page, endpoint]);

  const pick = (e) => {
    onSelect(e);
    setOpen(false);
  };
  const shown = selected && value ? `${selected.employee_number ? `${selected.employee_number} — ` : ""}${selected.full_name || "-"}` : "";

  return (
    <div className="space-y-1.5">
      <Label>{label}{required && <span className="text-danger"> *</span>}</Label>
      <Popover open={open} onOpenChange={(o) => { setOpen(o); if (o) { setQ(""); setPage(1); } }}>
        <PopoverTrigger asChild>
          <Button type="button" variant="outline" role="combobox" aria-expanded={open} disabled={disabled}
            className={cn("h-9 w-full justify-between px-3 font-normal", !shown && "text-muted-foreground")} data-testid={testId}>
            <span className="flex min-w-0 items-center gap-2"><UserRound className="h-4 w-4 shrink-0 opacity-60" /><span className="truncate">{shown || "Cari nama atau nomor karyawan…"}</span></span>
            <ChevronsUpDown className="h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-[var(--radix-popover-trigger-width)] min-w-[18rem] p-0" data-testid={testId && `${testId}-popover`}>
          <div className="relative border-b border-border p-2">
            <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input autoFocus value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder="Ketik nama atau nomor karyawan…"
              className="h-9 pl-8 pr-8" data-testid={testId && `${testId}-input`} />
            {q && (
              <button type="button" onClick={() => { setQ(""); setPage(1); }} aria-label="Hapus pencarian"
                className="absolute right-4 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                data-testid={testId && `${testId}-clear`}>
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
          <div className="max-h-64 overflow-y-auto py-1" role="listbox" data-testid={testId && `${testId}-results`}>
            {error ? (
              <p className="px-3 py-4 text-sm text-danger" data-testid={testId && `${testId}-error`}>{error}</p>
            ) : loading && page === 1 ? (
              <div className="flex items-center gap-2 px-3 py-4 text-sm text-muted-foreground" data-testid={testId && `${testId}-loading`}>
                <Loader2 className="h-4 w-4 animate-spin" /> Mencari karyawan…
              </div>
            ) : items.length === 0 ? (
              <p className="px-3 py-4 text-sm text-muted-foreground" data-testid={testId && `${testId}-empty`}>
                {q.trim() ? `Tidak ada karyawan yang cocok dengan "${q.trim()}".` : "Tidak ada karyawan yang tersedia."}
              </p>
            ) : (
              items.map((e) => (
                <button type="button" key={e.id} role="option" aria-selected={e.id === value} onClick={() => pick(e)}
                  className={cn("flex w-full flex-col items-start px-3 py-2 text-left hover:bg-muted focus-visible:bg-muted focus-visible:outline-none",
                    e.id === value && "bg-muted")}
                  data-testid={testId && `${testId}-option-${e.id}`}>
                  <span className="text-sm font-medium">{e.employee_number ? `${e.employee_number} — ` : ""}{e.full_name}</span>
                  <span className="text-[12px] text-muted-foreground">
                    {[e.project_name ? `Proyek: ${e.project_name}` : "Tanpa proyek aktif", e.active_holdings != null ? `${e.active_holdings} aset dipegang` : null].filter(Boolean).join(" · ")}
                  </span>
                </button>
              ))
            )}
            {!error && items.length > 0 && items.length < total && (
              <div className="border-t border-border p-1">
                <Button type="button" variant="ghost" size="sm" className="w-full" disabled={loading} onClick={() => setPage((p) => p + 1)}
                  data-testid={testId && `${testId}-more`}>
                  {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null} Muat lebih banyak ({items.length} dari {total})
                </Button>
              </div>
            )}
          </div>
        </PopoverContent>
      </Popover>
      {hint && <p className="text-[12px] text-muted-foreground">{hint}</p>}
    </div>
  );
};

export const employeeLabel = (e) => (e ? `${e.full_name || "-"}${e.employee_number ? ` · ${e.employee_number}` : ""}` : "-");

/** Tombol Lihat PDF (tab baru) + Unduh PDF. PDF selalu dibuat on-the-fly oleh backend dari snapshot BAST. */
export const BastPdfActions = ({ bastId, systemNumber, size = "sm", testIdPrefix = "bast" }) => {
  const [busy, setBusy] = useState("");
  if (!bastId) return null;
  const fallback = `${(systemNumber || "BAST").replace(/\//g, "-")}.pdf`;
  const view = async () => {
    setBusy("view");
    const win = window.open("", "_blank");
    try {
      const res = await api.get(`/asset-basts/${bastId}/pdf`, { params: { inline: true }, responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      if (win) win.location.href = url;
      else window.location.assign(url);
      window.setTimeout(() => window.URL.revokeObjectURL(url), 60000);
    } catch (e) {
      if (win) win.close();
      toast.error(errorMessage(e, "PDF BAST gagal dibuka."));
    } finally {
      setBusy("");
    }
  };
  const download = async () => {
    setBusy("download");
    try {
      await downloadFile(`/asset-basts/${bastId}/pdf`, fallback);
    } catch (e) {
      toast.error(errorMessage(e, "PDF BAST gagal diunduh."));
    } finally {
      setBusy("");
    }
  };
  return (
    <div className="flex flex-wrap gap-2">
      <Button variant="outline" size={size} onClick={view} disabled={!!busy} data-testid={`${testIdPrefix}-pdf-view-button`}>
        {busy === "view" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileText className="mr-2 h-4 w-4" />} Lihat PDF
      </Button>
      <Button variant="outline" size={size} onClick={download} disabled={!!busy} data-testid={`${testIdPrefix}-pdf-download-button`}>
        {busy === "download" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />} Unduh PDF
      </Button>
    </div>
  );
};

export const InfoGrid = ({ rows, testId }) => (
  <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2" data-testid={testId}>
    {rows.filter(Boolean).map(([label, value, id]) => (
      <div key={label} className="min-w-0">
        <dt className="text-[12px] font-medium text-muted-foreground">{label}</dt>
        <dd className="break-words text-sm text-foreground" data-testid={id}>{value || value === 0 ? value : "-"}</dd>
      </div>
    ))}
  </dl>
);

/** Tampilan resmi dokumen terbit: dibaca dari snapshot BAST (immutable), bukan master live. */
export const SnapshotView = ({ snapshot, testId = "bast-snapshot" }) => {
  if (!snapshot) return null;
  const emp = snapshot.employee || {};
  const condLabel = { HANDOVER: "Kondisi diserahkan", EXISTING: "Kondisi saat saldo awal" }[snapshot.bast_type] || "Kondisi diterima GA";
  return (
    <div className="space-y-4" data-testid={testId}>
      <InfoGrid
        rows={[
          ["Nomor BAST", snapshot.system_number, `${testId}-number`],
          ["Tanggal", formatDate(snapshot.bast_date)],
          ["No. Referensi (saat terbit)", snapshot.manual_number],
          ["Perusahaan", snapshot.company?.legal_name || snapshot.company?.name],
          ["Karyawan", `${emp.full_name || "-"}${emp.employee_number ? ` (${emp.employee_number})` : ""}`, `${testId}-employee`],
          ["Jabatan", emp.position || emp.job_title],
          ["Project", snapshot.project?.name],
          ["Lokasi Kerja", snapshot.work_location?.name],
          ["PIC GA", snapshot.ga_pic_name],
          ["Diterbitkan", `${formatIssuedWib(snapshot.issued_at)} · ${snapshot.issued_by_name || "-"}`],
          snapshot.notes ? ["Catatan", snapshot.notes] : null,
        ]}
      />
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full min-w-[34rem] text-sm" data-testid={`${testId}-items`}>
          <thead className="bg-muted/60 text-left text-[12px] text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">No</th>
              <th className="px-3 py-2 font-medium">Aset</th>
              <th className="px-3 py-2 font-medium">Serial</th>
              <th className="px-3 py-2 font-medium">{condLabel}</th>
              <th className="px-3 py-2 font-medium">Kelengkapan</th>
            </tr>
          </thead>
          <tbody>
            {(snapshot.items || []).map((it) => (
              <tr key={`${it.line_no}-${it.asset_id}`} className="border-t border-border align-top">
                <td className="px-3 py-2 tabular-nums">{it.line_no}</td>
                <td className="px-3 py-2">
                  <div className="font-medium">{it.asset_code}</div>
                  <div className="text-[12px] text-muted-foreground">{[it.name, it.brand, it.model, it.legacy_code && `Kode lama ${it.legacy_code}`].filter(Boolean).join(" · ")}</div>
                </td>
                <td className="px-3 py-2">{it.serial_number || "-"}</td>
                <td className="px-3 py-2">{it.condition || "-"}</td>
                <td className="px-3 py-2">{it.accessories || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[12px] text-muted-foreground">
        Isi dokumen dikunci saat terbit. Perubahan data karyawan/aset/project setelahnya tidak mengubah BAST ini.
      </p>
    </div>
  );
};
