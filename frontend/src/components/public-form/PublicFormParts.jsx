import React, { useState } from "react";
import { AlertTriangle, CheckCircle2, Clock3, Loader2, ShieldCheck } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

/** 6 langkah (spesifikasi 01G-B). Section backend "contact" ditampilkan di langkah Data Pribadi. */
export const STEPS = [
  { key: "personal", label: "Data Pribadi", sections: ["personal", "contact"] },
  { key: "family", label: "Keluarga" },
  { key: "bank_tax", label: "Bank & Pajak", sections: ["bank_tax"] },
  { key: "bpjs", label: "BPJS", sections: ["bpjs"] },
  { key: "documents", label: "Dokumen" },
  { key: "review", label: "Review" },
];
export const SECTION_TITLES = { personal: "Identitas", contact: "Kontak & Alamat" };
/** Section backend -> key langkah. */
export const stepOf = (section) => (section === "contact" ? "personal" : section);

/** Kode kelengkapan 01F -> field formulir (hanya untuk menandai isian; skor TIDAK dihitung ulang di frontend). */
export const REQ_FIELDS = {
  "PERSONAL.FULL_NAME": ["full_name"], "PERSONAL.NIK": ["nik"], "PERSONAL.GENDER": ["gender"],
  "PERSONAL.BIRTH": ["birth_place", "birth_date"], "PERSONAL.MARITAL": ["marital_status"],
  "PERSONAL.RELIGION": ["religion"], "PERSONAL.EDUCATION": ["education"], "PERSONAL.PHONE": ["phone"],
  "PERSONAL.EMAIL": ["email"], "PERSONAL.ADDRESS_KTP": ["address"], "PERSONAL.DOMICILE": ["domicile_address"],
  "PERSONAL.EMERGENCY_CONTACT": ["emergency_contact_name", "emergency_contact_phone"],
  "BANK.ACCOUNT": ["bank_name", "bank_account_number", "bank_account_name"], "TAX.NPWP": ["npwp"],
  "BPJS.KESEHATAN": ["bpjs_kesehatan_number"], "BPJS.TK": ["bpjs_tk_number"],
};

export const PublicShell = ({ company, logoSrc, children }) => {
  const [broken, setBroken] = useState(false);
  const initial = (company?.name || "?").replace(/^PT\.?\s+/i, "").charAt(0).toUpperCase();
  return (
    <div className="min-h-[100dvh] bg-[hsl(var(--surface-1,210_20%_98%))] text-foreground" data-testid="public-form-shell">
      <header className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80 sticky top-0 z-20">
        <div className="mx-auto flex max-w-3xl items-center gap-3 px-4 py-3">
          {logoSrc && !broken ? (
            <img src={logoSrc} alt={`Logo ${company?.name || "perusahaan"}`} onError={() => setBroken(true)}
              className="h-10 w-10 shrink-0 rounded-lg border bg-white object-contain p-0.5" data-testid="public-company-logo" />
          ) : (
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary text-base font-semibold text-primary-foreground" aria-hidden>
              {initial}
            </div>
          )}
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold leading-tight" data-testid="public-company-name">{company?.name || "Memuat…"}</p>
            <p className="text-xs text-muted-foreground">Pembaruan Data Karyawan</p>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-3xl px-4 pb-10 pt-5 sm:pt-8">{children}</main>
    </div>
  );
};

export const StepProgress = ({ index, total, label }) => (
  <div className="space-y-2" data-testid="public-step-progress">
    <p className="text-xs font-medium uppercase tracking-wide text-primary" data-testid="public-step-counter">Langkah {index + 1} dari {total}</p>
    <h2 className="text-xl font-semibold leading-snug sm:text-2xl" data-testid="public-step-title">{label}</h2>
    <Progress value={((index + 1) / total) * 100} className="h-2" aria-label={`Langkah ${index + 1} dari ${total}`} />
  </div>
);

export const CompletenessCard = ({ completeness, compact = false }) => {
  if (!completeness?.available) return null;
  const req = completeness.missing.filter((m) => m.level === "REQUIRED");
  const rec = completeness.missing.filter((m) => m.level !== "REQUIRED");
  const pct = Math.round(Number(completeness.score_pct || 0));
  return (
    <section className="rounded-xl border bg-background p-4 sm:p-5" data-testid="public-completeness-card">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm text-muted-foreground">Kelengkapan Data Anda</p>
          <p className="text-2xl font-semibold text-primary" data-testid="public-completeness-score">{pct}%</p>
        </div>
        <ShieldCheck className="h-8 w-8 text-primary/70" aria-hidden />
      </div>
      <Progress value={pct} className="mt-3 h-2" aria-label={`Kelengkapan ${pct}%`} />
      {!compact && (req.length > 0 || rec.length > 0) && (
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          {req.length > 0 && (
            <div data-testid="public-completeness-required">
              <p className="mb-1.5 text-sm font-semibold text-amber-800">Wajib dilengkapi</p>
              <ul className="space-y-1 text-sm">{req.map((m) => <li key={m.code} className="flex gap-2"><span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />{m.label}</li>)}</ul>
            </div>
          )}
          {rec.length > 0 && (
            <div data-testid="public-completeness-recommended">
              <p className="mb-1.5 text-sm font-semibold text-sky-800">Disarankan</p>
              <ul className="space-y-1 text-sm">{rec.map((m) => <li key={m.code} className="flex gap-2"><span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-sky-500" />{m.label}</li>)}</ul>
            </div>
          )}
        </div>
      )}
      <p className="mt-3 text-xs text-muted-foreground">Persentase dari data yang sudah tercatat di HR. Perubahan Anda dihitung setelah diverifikasi HR.</p>
    </section>
  );
};

const LEVEL_BADGE = {
  REQUIRED: "border-amber-300 bg-amber-50 text-amber-800",
  RECOMMENDED: "border-sky-300 bg-sky-50 text-sky-800",
};

export const FieldInput = ({ field, value, onChange, error, badge, draftMasked, options, disabled, inputRef }) => {
  const id = `pef-${field.key}`;
  const common = { id, disabled, "aria-invalid": !!error, "aria-describedby": `${id}-hint`, "data-testid": `public-field-${field.key}` };
  const cls = `h-12 text-base ${error ? "border-destructive focus-visible:ring-destructive" : ""}`;
  let control;
  if (field.type === "select") {
    control = (
      <Select value={(options || []).some((o) => o.key === value) ? value : undefined} onValueChange={(v) => onChange(field.key, v)} disabled={disabled}>
        <SelectTrigger ref={inputRef} className={cls} {...common}><SelectValue placeholder="Pilih" /></SelectTrigger>
        <SelectContent>{(options || []).map((o) => <SelectItem key={o.key} value={o.key} className="py-3 text-base">{o.label}</SelectItem>)}</SelectContent>
      </Select>
    );
  } else if (field.type === "textarea") {
    control = <Textarea ref={inputRef} rows={3} className={`min-h-[96px] text-base ${error ? "border-destructive" : ""}`} value={value || ""} maxLength={1000}
      onChange={(e) => onChange(field.key, e.target.value)} {...common} />;
  } else {
    const t = field.type;
    control = <Input ref={inputRef} className={cls} value={value || ""} autoComplete="off" spellCheck={false}
      type={t === "date" ? "date" : t === "email" ? "email" : t === "tel" ? "tel" : "text"}
      inputMode={t === "digits" ? "numeric" : t === "tel" ? "tel" : t === "email" ? "email" : undefined}
      placeholder={field.sensitive && field.masked ? "Kosongkan bila tidak berubah" : undefined}
      onChange={(e) => onChange(field.key, e.target.value)} {...common} />;
  }
  return (
    <div className="space-y-1.5" data-testid={`public-fieldwrap-${field.key}`}>
      <div className="flex flex-wrap items-center gap-2">
        <Label htmlFor={id} className="text-sm font-medium">{field.label}</Label>
        {badge && <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${LEVEL_BADGE[badge]}`} data-testid={`public-field-badge-${field.key}`}>{badge === "REQUIRED" ? "Wajib dilengkapi" : "Disarankan"}</span>}
      </div>
      {control}
      <div id={`${id}-hint`} className="space-y-0.5">
        {field.sensitive && field.masked && <p className="text-xs text-muted-foreground" data-testid={`public-field-existing-${field.key}`}>Tersimpan di HR: <span className="font-mono">{field.masked}</span></p>}
        {!field.sensitive && field.has_value && <p className="text-xs text-muted-foreground">Data dari HR — ubah bila tidak sesuai.</p>}
        {draftMasked && <p className="text-xs text-primary" data-testid={`public-field-draft-${field.key}`}>Perubahan tersimpan di draft: <span className="font-mono">{draftMasked}</span></p>}
        {error && <p className="text-sm font-medium text-destructive" role="alert" data-testid={`public-field-error-${field.key}`}>{error}</p>}
      </div>
    </div>
  );
};

export const SaveStatus = ({ state, at }) => {
  if (state === "saving") return <span className="inline-flex items-center gap-1 text-xs text-muted-foreground" data-testid="public-save-status"><Loader2 className="h-3.5 w-3.5 animate-spin" />Menyimpan…</span>;
  if (state === "saved") return <span className="inline-flex items-center gap-1 text-xs text-primary" data-testid="public-save-status"><CheckCircle2 className="h-3.5 w-3.5" />Tersimpan{at ? ` ${at}` : ""}</span>;
  if (state === "dirty") return <span className="text-xs text-muted-foreground" data-testid="public-save-status">Belum disimpan</span>;
  if (state === "error") return <span className="inline-flex items-center gap-1 text-xs text-destructive" data-testid="public-save-status"><AlertTriangle className="h-3.5 w-3.5" />Gagal menyimpan</span>;
  return null;
};

/** Route /public/* yang tidak dikenal: pesan generik, tanpa memanggil API apa pun. */
export const PublicUnavailable = () => {
  React.useEffect(() => { document.title = "Pembaruan Data Karyawan"; }, []);
  return (
    <PublicShell company={{ name: "Pembaruan Data Karyawan" }}>
      <StatusScreen icon="warn" title="Halaman tidak tersedia" testid="public-unavailable">
        <p>Portal pembaruan data tidak tersedia. Silakan hubungi HR perusahaan Anda.</p>
      </StatusScreen>
    </PublicShell>
  );
};

export const StatusScreen = ({ icon = "ok", title, children, action, testid }) => {
  const Icon = icon === "ok" ? CheckCircle2 : icon === "wait" ? Clock3 : AlertTriangle;
  const tone = icon === "ok" ? "bg-[hsl(var(--accent-mint,168_55%_92%))] text-primary" : icon === "wait" ? "bg-sky-50 text-sky-700" : "bg-amber-50 text-amber-700";
  return (
    <section className="rounded-2xl border bg-background p-6 sm:p-8" data-testid={testid}>
      <div className={`mb-4 flex h-14 w-14 items-center justify-center rounded-full ${tone}`}><Icon className="h-7 w-7" aria-hidden /></div>
      <h1 className="text-2xl font-semibold leading-snug" data-testid={`${testid}-title`}>{title}</h1>
      <div className="mt-2 space-y-2 text-base text-muted-foreground">{children}</div>
      {action && <div className="mt-6">{action}</div>}
    </section>
  );
};
