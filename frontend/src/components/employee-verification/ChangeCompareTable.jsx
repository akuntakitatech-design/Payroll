import React from "react";
import { AlertTriangle, CheckCircle2, Eye, FileText, Info, MinusCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { cn } from "@/lib/utils";

/* Upgrade 01H - tabel perbandingan "Data Saat Ini | Data Usulan | Keterangan" per section. */

export const STATE_STYLE = {
  OK: { cls: "border-emerald-200 bg-emerald-50 text-emerald-800", icon: CheckCircle2 },
  CONFLICT: { cls: "border-amber-300 bg-amber-50 text-amber-900", icon: AlertTriangle },
  ALREADY_APPLIED: { cls: "border-slate-200 bg-slate-50 text-slate-700", icon: CheckCircle2 },
  SKIPPED: { cls: "border-slate-200 bg-slate-100 text-slate-600", icon: MinusCircle },
  INFO: { cls: "border-sky-200 bg-sky-50 text-sky-800", icon: Info },
  // pengajuan yang sudah diputuskan
  APPLIED: { cls: "border-emerald-200 bg-emerald-50 text-emerald-800", icon: CheckCircle2 },
  KEPT: { cls: "border-slate-200 bg-slate-50 text-slate-700", icon: MinusCircle },
  NOT_APPLIED: { cls: "border-slate-200 bg-slate-100 text-slate-600", icon: MinusCircle },
};

export const StateBadge = ({ state, label, testid }) => {
  const s = STATE_STYLE[state] || STATE_STYLE.INFO;
  const Icon = s.icon;
  return (
    <Badge variant="outline" className={cn("whitespace-nowrap font-medium", s.cls)} data-testid={testid}>
      <Icon className="mr-1 h-3.5 w-3.5" />{label}
    </Badge>
  );
};

const Empty = () => <span className="text-muted-foreground">—</span>;

const fmtVal = (v) => {
  if (v === null || v === undefined || v === "") return <Empty />;
  if (v === true) return "Ya";
  if (v === false) return "Tidak";
  if (Array.isArray(v)) return v.length ? v.join(", ") : <Empty />;
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
};

const FamilyCard = ({ d }) => {
  if (!d) return <Empty />;
  return (
    <div className="space-y-0.5 text-sm">
      <p className="font-medium">{d.full_name || "-"} <span className="font-normal text-muted-foreground">· {d.relationship_label || d.relationship}</span></p>
      <p className="text-xs text-muted-foreground">
        {[d.nik && `NIK ${d.nik}`, d.birth_place, d.birth_date, d.gender === "male" ? "Laki-laki" : d.gender === "female" ? "Perempuan" : null,
          d.occupation, d.phone, d.is_emergency_contact ? "Kontak darurat" : null].filter(Boolean).join(" · ") || "—"}
      </p>
    </div>
  );
};

function CurrentCell({ it }) {
  if (it.kind === "family") return <FamilyCard d={it.current} />;
  if (it.kind === "photo") return it.current ? "Sudah ada foto profil" : <Empty />;
  if (it.kind === "document") return it.current ? `${it.current} dokumen tipe ini` : <Empty />;
  if (it.kind === "info") return <Empty />;
  return <span className="break-words">{fmtVal(it.current)}</span>;
}

function ProposedCell({ it, onPreview }) {
  if (it.kind === "family") {
    if (it.op === "remove") return <span className="font-medium text-rose-700">Dihapus{it.reason ? ` — alasan: ${it.reason}` : ""}</span>;
    return <FamilyCard d={it.proposed} />;
  }
  if (it.kind === "photo" || it.kind === "document") {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <FileText className="h-4 w-4 shrink-0 text-muted-foreground" /><span className="break-all">{it.proposed}</span>
        {onPreview && it.file_id && <Button type="button" size="sm" variant="outline" className="h-7 px-2" onClick={() => onPreview(it.file_id)} data-testid={`uv-preview-${it.file_id}`}><Eye className="mr-1 h-3.5 w-3.5" />Lihat</Button>}
      </div>
    );
  }
  if (it.kind === "custom_file") {
    return (
      <div className="flex flex-wrap items-center gap-2">
        {(it.file_ids || []).map((fid, i) => (
          <Button key={fid} type="button" size="sm" variant="outline" className="h-7 px-2" onClick={() => onPreview?.(fid)} data-testid={`uv-preview-${fid}`}>
            <FileText className="mr-1 h-3.5 w-3.5" />{(it.proposed || [])[i] || "Berkas"}
          </Button>
        ))}
      </div>
    );
  }
  return <span className="break-words font-medium">{fmtVal(it.proposed)}</span>;
}

export function ChangeCompareTable({ items, resolutions, onResolve, flagged, onFlag, canDecide, onPreview }) {
  return (
    <div className="overflow-hidden rounded-lg border" data-testid="uv-compare-table">
      <div className="hidden grid-cols-[minmax(150px,1.1fr)_1.4fr_1.4fr_minmax(170px,1fr)] gap-3 border-b bg-muted/50 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground md:grid">
        <span>Data</span><span>Data Saat Ini</span><span>Data Usulan</span><span>Keterangan</span>
      </div>
      {items.map((it) => {
        const conflict = it.state === "CONFLICT";
        const changed = it.state === "OK" || conflict;
        return (
          <div key={it.key} className={cn("border-b px-4 py-3 last:border-b-0", conflict ? "bg-amber-50/70" : changed ? "bg-emerald-50/40" : "bg-card")} data-testid={`uv-item-${it.key}`}>
            <div className="grid gap-2 md:grid-cols-[minmax(150px,1.1fr)_1.4fr_1.4fr_minmax(170px,1fr)] md:gap-3">
              <div className="text-sm font-semibold text-foreground">
                {it.label}
                {it.identity && <Badge variant="outline" className="ml-2 border-violet-200 bg-violet-50 text-[10px] text-violet-800">Identitas</Badge>}
              </div>
              <div className="text-sm text-muted-foreground"><span className="mr-1 text-xs font-medium md:hidden">Saat ini: </span><span data-testid={`uv-current-${it.key}`}><CurrentCell it={it} /></span></div>
              <div className="text-sm"><span className="mr-1 text-xs font-medium text-muted-foreground md:hidden">Usulan: </span><span data-testid={`uv-proposed-${it.key}`}><ProposedCell it={it} onPreview={onPreview} /></span></div>
              <div className="space-y-1">
                <StateBadge state={it.state} label={it.state_label} testid={`uv-state-${it.key}`} />
                {it.note && <p className={cn("text-xs", conflict || it.warning ? "text-amber-800" : "text-muted-foreground")}>{it.note}</p>}
              </div>
            </div>
            {conflict && canDecide && (
              <RadioGroup value={resolutions[it.key] || ""} onValueChange={(v) => onResolve(it.key, v)} className="mt-3 flex flex-col gap-2 rounded-md border border-amber-300 bg-white p-3 sm:flex-row sm:gap-6" data-testid={`uv-resolve-${it.key}`}>
                <p className="text-xs font-semibold text-amber-900 sm:self-center">Putuskan konflik:</p>
                {(it.options || []).includes("use_proposed") && (
                  <div className="flex items-center gap-2"><RadioGroupItem value="use_proposed" id={`${it.key}-p`} data-testid={`uv-resolve-${it.key}-use_proposed`} /><Label htmlFor={`${it.key}-p`} className="text-sm">Pakai usulan karyawan</Label></div>
                )}
                <div className="flex items-center gap-2"><RadioGroupItem value="keep_current" id={`${it.key}-k`} data-testid={`uv-resolve-${it.key}-keep_current`} /><Label htmlFor={`${it.key}-k`} className="text-sm">Pertahankan data saat ini</Label></div>
              </RadioGroup>
            )}
            {onFlag && canDecide && it.state !== "INFO" && (
              <label className="mt-2 flex w-fit cursor-pointer items-center gap-2 text-xs text-muted-foreground">
                <input type="checkbox" className="h-3.5 w-3.5 accent-amber-600" checked={flagged.includes(it.key)} onChange={() => onFlag(it.key)} data-testid={`uv-flag-${it.key}`} />
                Tandai perlu diperbaiki
              </label>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default ChangeCompareTable;
