import React, { useState } from "react";
import { Download, FileText, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { api, errorMessage } from "@/lib/api";
import { downloadFile } from "@/lib/download";
import { formatDate } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// Phase 2A CP2 - komponen bersama siklus Penyerahan / Pengembalian / Pemeriksaan + Dokumen BAST.

export const BADGE_TONE = {
  success: "border-success-border bg-success-soft text-success",
  warning: "border-warning-border bg-warning-soft text-warning",
  danger: "border-danger-border bg-danger-soft text-danger",
  info: "border-border bg-secondary text-secondary-foreground",
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
  IN_USE: { label: "Dipakai", tone: "info" },
  PENDING_INSPECTION: { label: "Menunggu Pemeriksaan", tone: "warning" },
  READY: { label: "Siap Pakai", tone: "success" },
  MAINTENANCE: { label: "Perbaikan", tone: "warning" },
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

export const BAST_TYPE_LABEL = { HANDOVER: "Penyerahan", RETURN: "Pengembalian" };

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
  const handover = snapshot.bast_type === "HANDOVER";
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
          ["Diterbitkan", `${snapshot.issued_at || "-"} · ${snapshot.issued_by_name || "-"}`],
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
              <th className="px-3 py-2 font-medium">{handover ? "Kondisi diserahkan" : "Kondisi diterima GA"}</th>
              <th className="px-3 py-2 font-medium">Kelengkapan</th>
            </tr>
          </thead>
          <tbody>
            {(snapshot.items || []).map((it) => (
              <tr key={`${it.line_no}-${it.asset_id}`} className="border-t border-border align-top">
                <td className="px-3 py-2 tabular-nums">{it.line_no}</td>
                <td className="px-3 py-2">
                  <div className="font-medium">{it.asset_code}</div>
                  <div className="text-[12px] text-muted-foreground">{[it.name, it.brand, it.model].filter(Boolean).join(" · ")}</div>
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
