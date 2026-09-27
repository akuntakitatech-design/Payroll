import React, { useRef, useState } from "react";
import { FileUp, Loader2, Trash2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const LEVEL_CLS = {
  REQUIRED: "border-amber-300 bg-amber-50 text-amber-800",
  RECOMMENDED: "border-sky-300 bg-sky-50 text-sky-800",
  OPTIONAL: "border-border bg-muted text-muted-foreground",
};

/** Enhancement 01G Form Builder - custom field input (cf_*). Values go to draft `custom`, never to master data. */
export const CustomFieldInput = ({ field, value, onChange, error, disabled, files = [], onUpload, onRemove }) => {
  const id = `pef-${field.key}`;
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);
  const common = { id, disabled, "aria-invalid": !!error, "aria-describedby": `${id}-hint`, "data-testid": `public-custom-${field.key}` };
  const cls = `h-12 text-base ${error ? "border-destructive" : ""}`;
  const opts = field.options || [];
  let control;
  if (field.type === "textarea") {
    control = <Textarea rows={3} className="min-h-[96px] text-base" value={value || ""} maxLength={field.validation?.max_length || 2000} placeholder={field.placeholder || undefined} onChange={(e) => onChange(field.key, e.target.value)} {...common} />;
  } else if (field.type === "dropdown") {
    control = (
      <Select value={opts.some((o) => o.value === value) ? value : undefined} onValueChange={(v) => onChange(field.key, v)} disabled={disabled}>
        <SelectTrigger className={cls} {...common}><SelectValue placeholder={field.placeholder || "Pilih"} /></SelectTrigger>
        <SelectContent>{opts.map((o) => <SelectItem key={o.value} value={o.value} className="py-3 text-base">{o.label}</SelectItem>)}</SelectContent>
      </Select>
    );
  } else if (field.type === "radio") {
    control = (
      <RadioGroup value={value || ""} onValueChange={(v) => onChange(field.key, v)} disabled={disabled} className="grid gap-2" {...common}>
        {opts.map((o) => (
          <label key={o.value} className="flex min-h-12 cursor-pointer items-center gap-3 rounded-lg border p-3">
            <RadioGroupItem value={o.value} id={`${id}-${o.value}`} data-testid={`public-custom-${field.key}-${o.value}`} /><span className="text-sm">{o.label}</span>
          </label>
        ))}
      </RadioGroup>
    );
  } else if (field.type === "checkbox") {
    const cur = Array.isArray(value) ? value : [];
    control = opts.length ? (
      <div className="grid gap-2" data-testid={`public-custom-${field.key}`}>
        {opts.map((o) => (
          <label key={o.value} className="flex min-h-12 cursor-pointer items-center gap-3 rounded-lg border p-3">
            <Checkbox checked={cur.includes(o.value)} disabled={disabled} data-testid={`public-custom-${field.key}-${o.value}`}
              onCheckedChange={(c) => onChange(field.key, c ? [...cur, o.value] : cur.filter((x) => x !== o.value))} />
            <span className="text-sm">{o.label}</span>
          </label>
        ))}
      </div>
    ) : (
      <label className="flex min-h-12 items-center gap-3 rounded-lg border p-3"><Checkbox checked={value === true} disabled={disabled} onCheckedChange={(c) => onChange(field.key, !!c)} {...common} /><span className="text-sm">Ya</span></label>
    );
  } else if (field.type === "file") {
    const mine = files.filter((f) => f.field_key === field.key);
    const accept = (field.validation?.allowed_ext || ["pdf", "jpg", "jpeg", "png", "webp"]).map((e) => `.${e}`).join(",");
    control = (
      <div className="space-y-2" data-testid={`public-custom-${field.key}`}>
        {mine.map((f) => (
          <div key={f.id} className="flex items-center justify-between gap-2 rounded-lg border bg-muted/40 p-3 text-sm" data-testid={`public-custom-file-${field.key}`}>
            <span className="min-w-0 truncate">{f.file_name}</span>
            <Button type="button" variant="ghost" size="sm" className="h-10" disabled={disabled} onClick={() => onRemove(f.id)} aria-label={`Hapus ${f.file_name}`}><Trash2 className="h-4 w-4" /></Button>
          </div>
        ))}
        <input ref={fileRef} type="file" accept={accept} className="hidden" data-testid={`public-custom-fileinput-${field.key}`}
          onChange={async (e) => { const fl = e.target.files?.[0]; e.target.value = ""; if (!fl) return; setBusy(true); try { await onUpload(field.key, fl); } catch { /* toast di induk */ } finally { setBusy(false); } }} />
        <Button type="button" variant="outline" className="h-12 w-full" disabled={disabled || busy} onClick={() => fileRef.current?.click()} data-testid={`public-custom-upload-${field.key}`}>
          {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileUp className="mr-2 h-4 w-4" />}Unggah berkas
        </Button>
        <p className="text-xs text-muted-foreground">Format: {accept.replaceAll(".", "").replaceAll(",", ", ")} · maks {field.validation?.max_mb || 10} MB. Berkas belum menjadi dokumen resmi sebelum diverifikasi HR.</p>
      </div>
    );
  } else {
    control = <Input className={cls} value={value ?? ""} autoComplete="off" placeholder={field.placeholder || undefined}
      type={field.type === "date" ? "date" : "text"} inputMode={field.type === "number" ? "decimal" : undefined}
      maxLength={field.type === "text" ? field.validation?.max_length || 255 : undefined}
      onChange={(e) => onChange(field.key, e.target.value)} {...common} />;
  }
  return (
    <div className="space-y-1.5" data-testid={`public-fieldwrap-${field.key}`}>
      <div className="flex flex-wrap items-center gap-2">
        <Label htmlFor={id} className="text-sm font-medium">{field.label}</Label>
        {field.level && field.level !== "OPTIONAL" && <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${LEVEL_CLS[field.level]}`} data-testid={`public-custom-level-${field.key}`}>{field.level === "REQUIRED" ? "Wajib" : "Anjuran"}</span>}
      </div>
      {control}
      <div id={`${id}-hint`} className="space-y-0.5">
        {field.help_text && <p className="text-xs text-muted-foreground">{field.help_text}</p>}
        {error && <p className="text-sm font-medium text-destructive" role="alert" data-testid={`public-custom-error-${field.key}`}>{error}</p>}
      </div>
    </div>
  );
};

export const customFilled = (field, value, files) => {
  if (field.type === "file") return files.some((f) => f.field_key === field.key);
  if (Array.isArray(value)) return value.length > 0;
  return value !== undefined && value !== null && value !== "" && value !== false;
};
