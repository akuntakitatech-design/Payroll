import React, { useState } from "react";
import { Monitor, Smartphone, ChevronLeft, ChevronRight, Users, FileUp, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

export const TYPE_LABELS = { text: "Teks singkat", number: "Angka", date: "Tanggal", dropdown: "Dropdown", radio: "Pilihan tunggal (radio)", checkbox: "Kotak centang", textarea: "Teks panjang", file: "Berkas / dokumen" };
export const LEVEL_BADGE = {
  Wajib: "border-warning-border bg-warning-soft text-warning",
  Anjuran: "border-info-border bg-info-soft text-info",
};
export const FORCED_LABEL = "Tetap ditampilkan karena diwajibkan aturan kelengkapan";

/** Read-only field mock (preview only: no draft/submission is ever created). */
const PreviewField = ({ f }) => {
  const id = `pv-${f.key}`;
  let control;
  if (f.source === "CUSTOM" && ["dropdown", "radio", "checkbox"].includes(f.type)) {
    control = (
      <div className="grid gap-1.5">
        {(f.options || []).map((o) => (
          <div key={o.value} className="flex min-h-10 items-center gap-2 rounded-md border px-3 text-sm text-muted-foreground">
            <span className={cn("h-4 w-4 shrink-0 border", f.type === "checkbox" ? "rounded-sm" : "rounded-full")} aria-hidden />{o.label}
          </div>
        ))}
        {!(f.options || []).length && <p className="text-xs text-muted-foreground">Belum ada opsi.</p>}
      </div>
    );
  } else if (f.source === "CUSTOM" && f.type === "textarea") {
    control = <Textarea id={id} disabled rows={2} placeholder={f.placeholder || ""} />;
  } else if (f.source === "CUSTOM" && f.type === "file") {
    control = <div className="flex h-11 items-center justify-center gap-2 rounded-md border border-dashed text-sm text-muted-foreground"><FileUp className="h-4 w-4" />Unggah berkas (lampiran pending)</div>;
  } else {
    control = <Input id={id} disabled placeholder={f.placeholder || ""} type={f.type === "date" ? "date" : "text"} className="h-11" />;
  }
  return (
    <div className="space-y-1.5" data-testid={`preview-field-${f.key}`}>
      <div className="flex flex-wrap items-center gap-1.5">
        <Label htmlFor={id} className="text-sm font-medium">{f.label}</Label>
        {f.level_label && f.level_label !== "Opsional" && f.level_label !== "Tidak Dinilai" && (
          <Badge variant="outline" className={cn("text-[11px]", LEVEL_BADGE[f.level_label])}>{f.level_label}</Badge>
        )}
        {f.forced && <Badge variant="outline" className="border-warning-border bg-warning-soft text-[11px] text-warning" data-testid={`preview-forced-${f.key}`}>{FORCED_LABEL}</Badge>}
        {f.scoped && <Badge variant="secondary" className="text-[11px]">Ber-scope</Badge>}
      </div>
      {control}
      {f.help_text && <p className="text-xs text-muted-foreground">{f.help_text}</p>}
    </div>
  );
};

/** Preview of the public form (desktop / mobile). Built from the server layout = same source of truth as the public form. */
export const FormPreview = ({ data }) => {
  const [device, setDevice] = useState("desktop");
  const [idx, setIdx] = useState(0);
  const steps = [...(data?.layout?.steps || []), { key: "review", label: "Review & Kirim", kind: "review", fields: [] }];
  const cur = steps[Math.min(idx, steps.length - 1)];
  return (
    <div className="space-y-3" data-testid="form-preview">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground" data-testid="form-preview-note"><Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />{data?.note || "Pratinjau read-only. Tidak membuat draft atau kiriman karyawan."}</p>
        <ToggleGroup type="single" value={device} onValueChange={(v) => v && setDevice(v)} variant="outline" size="sm" data-testid="form-preview-device">
          <ToggleGroupItem value="desktop" aria-label="Pratinjau desktop" data-testid="form-preview-desktop"><Monitor className="mr-1.5 h-4 w-4" />Desktop</ToggleGroupItem>
          <ToggleGroupItem value="mobile" aria-label="Pratinjau mobile" data-testid="form-preview-mobile"><Smartphone className="mr-1.5 h-4 w-4" />Mobile</ToggleGroupItem>
        </ToggleGroup>
      </div>
      <div className="flex justify-center rounded-xl border bg-muted/40 p-3 sm:p-5">
        <div className={cn("w-full overflow-hidden bg-background shadow-sm", device === "mobile" ? "max-w-[390px] rounded-[28px] border-4 border-ink-1/80" : "max-w-3xl rounded-xl border")}
          data-testid={`form-preview-frame-${device}`}>
          <div className="border-b px-4 py-3">
            <p className="text-xs text-muted-foreground">Pembaruan Data Karyawan</p>
            <p className="text-sm font-semibold">Langkah {Math.min(idx, steps.length - 1) + 1} dari {steps.length}: {cur.label}</p>
            <div className="mt-2 flex gap-1" aria-hidden>{steps.map((s, i) => <span key={s.key} className={cn("h-1.5 flex-1 rounded-full", i <= idx ? "bg-primary" : "bg-muted")} />)}</div>
          </div>
          <div className={cn("space-y-4 p-4", device === "mobile" ? "min-h-[420px]" : "min-h-[320px] sm:p-6")} data-testid={`form-preview-step-${cur.key}`}>
            {cur.forced && <Badge variant="outline" className="border-warning-border bg-warning-soft text-warning">Section nonaktif, tetap tampil karena ada data wajib</Badge>}
            {cur.description && <p className="text-sm text-muted-foreground">{cur.description}</p>}
            {cur.kind === "fields" && cur.fields.map((f) => <PreviewField key={f.key} f={f} />)}
            {cur.kind === "family" && <div className="flex items-center gap-2 rounded-lg border p-4 text-sm text-muted-foreground"><Users className="h-4 w-4" />Daftar anggota keluarga: tambah / ubah (diajukan ke HR)</div>}
            {cur.kind === "documents" && <div className="flex items-center gap-2 rounded-lg border p-4 text-sm text-muted-foreground"><FileUp className="h-4 w-4" />Unggah dokumen (lampiran pending sampai diverifikasi HR)</div>}
            {cur.kind === "review" && <div className="rounded-lg border p-4 text-sm text-muted-foreground">Ringkasan per langkah, persetujuan, lalu tombol <b>Kirim Data ke HR</b>.</div>}
          </div>
          <div className="flex gap-2 border-t p-3">
            <Button variant="outline" size="sm" className="h-10" disabled={idx === 0} onClick={() => setIdx((i) => Math.max(0, i - 1))} data-testid="form-preview-prev"><ChevronLeft className="h-4 w-4" />Kembali</Button>
            <Button size="sm" className="h-10 flex-1" disabled={idx >= steps.length - 1} onClick={() => setIdx((i) => Math.min(steps.length - 1, i + 1))} data-testid="form-preview-next">Lanjut<ChevronRight className="ml-1 h-4 w-4" /></Button>
          </div>
        </div>
      </div>
      <ol className="flex flex-wrap gap-1.5" data-testid="form-preview-steps">
        {steps.map((s, i) => (
          <li key={s.key}><Button variant={i === idx ? "default" : "outline"} size="sm" className="h-8" onClick={() => setIdx(i)} data-testid={`form-preview-goto-${s.key}`}>{i + 1}. {s.label}</Button></li>
        ))}
      </ol>
    </div>
  );
};
