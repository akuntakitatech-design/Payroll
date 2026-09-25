import React, { useEffect, useState } from "react";
import { Check, CheckCircle2, ChevronLeft, ChevronRight, Copy, KeyRound, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const STEPS = ["Data Tenant", "Tenant Admin Pertama", "Review & Buat"];
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PHONE_RE = /^[0-9+()\-\s]{6,20}$/;

const EMPTY = {
  name: "",
  code: "",
  legal_name: "",
  pic_name: "",
  email: "",
  pic_phone: "",
  subscription_start_date: "",
  subscription_end_date: "",
  grace_period_days: "7",
  subscription_notes: "",
  admin_use_primary_email: true,
  admin_full_name: "",
  admin_email: "",
};

const suggestCode = (name) =>
  (name || "")
    .toUpperCase()
    .replace(/\b(PT|CV|TBK|PERSERO)\b\.?/g, "")
    .replace(/[^A-Z0-9]+/g, "")
    .slice(0, 10);

const FieldRow = ({ id, label, required, error, hint, children }) => (
  <div className="space-y-1.5">
    <Label htmlFor={id} className="text-[13px]">
      {label} {required && <span className="text-destructive">*</span>}
    </Label>
    {children}
    {error ? (
      <p className="text-xs text-destructive" data-testid={`${id}-error`}>{error}</p>
    ) : (
      hint && <p className="text-xs text-muted-foreground">{hint}</p>
    )}
  </div>
);

const ReviewItem = ({ label, value, testId }) => (
  <div className="flex items-start justify-between gap-3 py-1.5 text-sm">
    <span className="text-muted-foreground">{label}</span>
    <span className="max-w-[60%] text-right font-medium text-ink-1" data-testid={testId}>{value || "-"}</span>
  </div>
);

export const TenantCreateWizard = ({ open, onOpenChange, onCreated }) => {
  const [step, setStep] = useState(0);
  const [v, setV] = useState(EMPTY);
  const [codeTouched, setCodeTouched] = useState(false);
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (open) {
      setStep(0);
      setV(EMPTY);
      setCodeTouched(false);
      setErrors({});
      setResult(null);
    }
  }, [open]);

  const set = (name, value) => {
    setV((p) => {
      const next = { ...p, [name]: value };
      if (name === "name" && !codeTouched) next.code = suggestCode(value);
      return next;
    });
    setErrors((p) => ({ ...p, [name]: undefined, __form__: undefined }));
  };

  const validateStep = (s) => {
    const e = {};
    if (s === 0) {
      if (v.name.trim().length < 2) e.name = "Nama tenant minimal 2 karakter.";
      if (!/^[A-Za-z0-9_-]{2,20}$/.test(v.code.trim())) e.code = "Kode 2-20 karakter: huruf, angka, - atau _.";
      if (v.pic_name.trim().length < 2) e.pic_name = "Nama PIC wajib diisi.";
      if (!EMAIL_RE.test(v.email.trim())) e.email = "Masukkan email utama tenant yang valid.";
      if (!PHONE_RE.test(v.pic_phone.trim())) e.pic_phone = "Nomor HP 6-20 digit (boleh +, spasi, -).";
      if (!v.subscription_start_date) e.subscription_start_date = "Tanggal mulai layanan wajib diisi.";
      if (!v.subscription_end_date) e.subscription_end_date = "Tanggal berakhir layanan wajib diisi.";
      if (v.subscription_start_date && v.subscription_end_date && v.subscription_end_date < v.subscription_start_date)
        e.subscription_end_date = "Tanggal berakhir tidak boleh lebih awal dari tanggal mulai.";
      const g = v.grace_period_days;
      if (g === "" || !Number.isInteger(Number(g)) || Number(g) < 0) e.grace_period_days = "Grace period bilangan bulat ≥ 0.";
    }
    if (s === 1 && !v.admin_use_primary_email) {
      if (v.admin_full_name.trim().length < 2) e.admin_full_name = "Nama Tenant Admin wajib diisi.";
      if (!EMAIL_RE.test(v.admin_email.trim())) e.admin_email = "Masukkan email Tenant Admin yang valid.";
    }
    setErrors(e);
    return !Object.keys(e).length;
  };

  const next = () => validateStep(step) && setStep((s) => Math.min(2, s + 1));
  const back = () => setStep((s) => Math.max(0, s - 1));

  const adminEmail = v.admin_use_primary_email ? v.email.trim().toLowerCase() : v.admin_email.trim().toLowerCase();
  const adminName = v.admin_use_primary_email ? v.pic_name.trim() : v.admin_full_name.trim();

  const submit = async () => {
    if (!validateStep(0)) return setStep(0);
    if (!validateStep(1)) return setStep(1);
    setSubmitting(true);
    try {
      const { data } = await api.post("/platform/tenants", {
        name: v.name.trim(),
        code: v.code.trim().toUpperCase(),
        legal_name: v.legal_name.trim() || null,
        status: "active",
        email: v.email.trim().toLowerCase(),
        pic_name: v.pic_name.trim(),
        pic_phone: v.pic_phone.trim(),
        subscription_start_date: v.subscription_start_date,
        subscription_end_date: v.subscription_end_date,
        grace_period_days: Number(v.grace_period_days),
        subscription_notes: v.subscription_notes.trim() || null,
        admin_use_primary_email: v.admin_use_primary_email,
        admin_full_name: v.admin_use_primary_email ? null : v.admin_full_name.trim(),
        admin_email: v.admin_use_primary_email ? null : v.admin_email.trim().toLowerCase(),
      });
      setResult(data);
      toast.success(`Tenant ${data.name} dan Tenant Admin pertama berhasil dibuat.`);
      onCreated?.(data, { silent: true });
    } catch (err) {
      setErrors({ __form__: errorMessage(err, "Tenant tidak dapat dibuat.") });
    } finally {
      setSubmitting(false);
    }
  };

  const copyCredential = async () => {
    const fa = result?.first_admin;
    try {
      await navigator.clipboard.writeText(`Email: ${fa.user.email}\nPassword sementara: ${fa.temporary_password}`);
      toast.success("Kredensial disalin.");
    } catch {
      toast.error("Tidak dapat menyalin otomatis. Salin secara manual.");
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !submitting && onOpenChange(o)}>
      <DialogContent className="max-h-[92vh] overflow-y-auto bg-card sm:max-w-2xl" data-testid="tenant-wizard">
        {result ? (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2 text-base">
                <CheckCircle2 className="h-5 w-5 text-success" /> Tenant {result.name} siap digunakan
              </DialogTitle>
              <DialogDescription>
                Tenant, data PIC, email utama, dan Tenant Admin pertama sudah terbentuk. Password sementara di bawah hanya
                ditampilkan <strong>sekali</strong> — serahkan secara aman; pengguna wajib menggantinya setelah login.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-2 rounded-lg border border-border bg-secondary px-4 py-3 text-[13px]" data-testid="tenant-wizard-credential">
              <p className="flex items-center gap-2 font-semibold"><KeyRound className="h-4 w-4" /> Kredensial Tenant Admin pertama</p>
              <p className="font-mono" data-testid="tenant-wizard-credential-email">{result.first_admin?.user?.email}</p>
              <p className="font-mono" data-testid="tenant-wizard-credential-password">{result.first_admin?.temporary_password}</p>
              <p className="text-xs text-muted-foreground">
                Kode tenant: <span className="font-semibold">{result.code}</span> (permanen)
              </p>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={copyCredential} data-testid="tenant-wizard-copy">
                <Copy className="mr-1.5 h-4 w-4" /> Salin
              </Button>
              <Button onClick={() => { onOpenChange(false); onCreated?.(result, { open: true }); }} data-testid="tenant-wizard-done">
                Sudah disimpan, buka detail tenant
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle className="text-base">Tambah Tenant</DialogTitle>
              <DialogDescription>
                Tenant dan Tenant Admin pertama dibuat sekaligus dalam satu proses.
              </DialogDescription>
            </DialogHeader>

            <ol className="grid grid-cols-3 gap-2" data-testid="tenant-wizard-steps">
              {STEPS.map((label, i) => (
                <li
                  key={label}
                  className={cn(
                    "flex items-center gap-2 rounded-lg border px-2.5 py-2 text-[12px] font-medium",
                    i === step ? "border-primary bg-primary-soft text-primary" : i < step ? "border-primary-border text-ink-2" : "border-border text-ink-3"
                  )}
                  data-testid={`tenant-wizard-step-${i + 1}`}
                  aria-current={i === step ? "step" : undefined}
                >
                  <span className={cn("flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px]", i <= step ? "bg-primary text-primary-foreground" : "bg-muted text-ink-3")}>
                    {i < step ? <Check className="h-3 w-3" /> : i + 1}
                  </span>
                  <span className="truncate">{label}</span>
                </li>
              ))}
            </ol>

            {step === 0 && (
              <div className="grid gap-4 sm:grid-cols-2" data-testid="tenant-wizard-step-data">
                <FieldRow id="wz-name" label="Nama Tenant" required error={errors.name}>
                  <Input id="wz-name" value={v.name} onChange={(e) => set("name", e.target.value)} placeholder="PT Contoh Sejahtera" data-testid="wizard-name-input" />
                </FieldRow>
                <FieldRow id="wz-code" label="Kode Tenant" required error={errors.code} hint="Unik dan permanen — tidak berubah walau nama perusahaan diganti.">
                  <Input id="wz-code" value={v.code} onChange={(e) => { setCodeTouched(true); set("code", e.target.value.toUpperCase()); }} placeholder="CONTOH" data-testid="wizard-code-input" />
                </FieldRow>
                <FieldRow id="wz-pic" label="Nama PIC" required error={errors.pic_name}>
                  <Input id="wz-pic" value={v.pic_name} onChange={(e) => set("pic_name", e.target.value)} placeholder="Nama penanggung jawab" data-testid="wizard-pic-name-input" />
                </FieldRow>
                <FieldRow id="wz-phone" label="No. HP PIC" required error={errors.pic_phone}>
                  <Input id="wz-phone" value={v.pic_phone} onChange={(e) => set("pic_phone", e.target.value)} placeholder="0812xxxxxxx" data-testid="wizard-pic-phone-input" />
                </FieldRow>
                <FieldRow id="wz-email" label="Email Utama Tenant" required error={errors.email} hint="Email kontak perusahaan.">
                  <Input id="wz-email" type="email" value={v.email} onChange={(e) => set("email", e.target.value)} placeholder="admin@perusahaan.co.id" data-testid="wizard-email-input" />
                </FieldRow>
                <FieldRow id="wz-legal" label="Nama Badan Hukum" hint="Opsional.">
                  <Input id="wz-legal" value={v.legal_name} onChange={(e) => set("legal_name", e.target.value)} data-testid="wizard-legal-name-input" />
                </FieldRow>
                <FieldRow id="wz-start" label="Tanggal mulai layanan" required error={errors.subscription_start_date}>
                  <Input id="wz-start" type="date" value={v.subscription_start_date} onChange={(e) => set("subscription_start_date", e.target.value)} data-testid="wizard-start-input" />
                </FieldRow>
                <FieldRow id="wz-end" label="Tanggal berakhir layanan" required error={errors.subscription_end_date}>
                  <Input id="wz-end" type="date" value={v.subscription_end_date} onChange={(e) => set("subscription_end_date", e.target.value)} data-testid="wizard-end-input" />
                </FieldRow>
                <FieldRow id="wz-grace" label="Grace period (hari)" required error={errors.grace_period_days} hint="Tenant tetap beroperasi dengan peringatan selama masa tenggang.">
                  <Input id="wz-grace" type="number" min={0} value={v.grace_period_days} onChange={(e) => set("grace_period_days", e.target.value)} data-testid="wizard-grace-input" />
                </FieldRow>
                <FieldRow id="wz-notes" label="Catatan masa layanan" hint="Opsional.">
                  <Textarea id="wz-notes" rows={2} value={v.subscription_notes} onChange={(e) => set("subscription_notes", e.target.value)} data-testid="wizard-notes-input" />
                </FieldRow>
              </div>
            )}

            {step === 1 && (
              <div className="space-y-4" data-testid="tenant-wizard-step-admin">
                <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-border p-3 transition-colors duration-150 hover:bg-accent" htmlFor="wz-use-primary">
                  <Checkbox
                    id="wz-use-primary"
                    checked={v.admin_use_primary_email}
                    onCheckedChange={(c) => set("admin_use_primary_email", c === true)}
                    className="mt-0.5"
                    data-testid="wizard-use-primary-email-checkbox"
                  />
                  <span>
                    <span className="block text-sm font-medium">Gunakan Email Utama Tenant sebagai Tenant Admin pertama</span>
                    <span className="block text-xs text-muted-foreground">
                      {v.admin_use_primary_email
                        ? `Akun Tenant Admin dibuat dengan email ${v.email || "utama tenant"} dan hanya terikat ke tenant baru ini.`
                        : "Isi nama dan email login Tenant Admin terpisah. Email Utama Tenant tetap menjadi email kontak perusahaan."}
                    </span>
                  </span>
                </label>
                {v.admin_use_primary_email ? (
                  <div className="rounded-lg border border-border bg-secondary px-4 py-3 text-sm" data-testid="wizard-admin-preview">
                    <ReviewItem label="Nama admin" value={adminName} testId="wizard-admin-preview-name" />
                    <ReviewItem label="Email login" value={adminEmail} testId="wizard-admin-preview-email" />
                    <ReviewItem label="Role" value="Tenant Admin (otomatis)" />
                    <ReviewItem label="Password sementara" value="Dibuat otomatis oleh sistem (ditampilkan sekali)" testId="wizard-admin-preview-password" />
                  </div>
                ) : (
                  <div className="grid gap-4 sm:grid-cols-2">
                    <FieldRow id="wz-admin-name" label="Nama Tenant Admin" required error={errors.admin_full_name}>
                      <Input id="wz-admin-name" value={v.admin_full_name} onChange={(e) => set("admin_full_name", e.target.value)} data-testid="wizard-admin-name-input" />
                    </FieldRow>
                    <FieldRow id="wz-admin-email" label="Email Login Tenant Admin" required error={errors.admin_email} hint="Email Utama Tenant tetap menjadi email kontak perusahaan.">
                      <Input id="wz-admin-email" type="email" value={v.admin_email} onChange={(e) => set("admin_email", e.target.value)} data-testid="wizard-admin-email-input" />
                    </FieldRow>
                    <FieldRow id="wz-admin-password" label="Password sementara" hint="Dibuat acak oleh sistem saat tenant disimpan dan ditampilkan satu kali.">
                      <Input id="wz-admin-password" value="Dibuat otomatis oleh sistem" readOnly disabled data-testid="wizard-admin-password-auto" />
                    </FieldRow>
                  </div>
                )}
                <p className="text-xs text-muted-foreground">
                  Tanpa aktivasi email: Tenant Admin dapat langsung login memakai email login + password sementara, lalu
                  wajib mengganti password pada login pertama. Password hanya disimpan sebagai hash. Email yang sudah
                  terdaftar tidak dapat dipakai.
                </p>
              </div>
            )}

            {step === 2 && (
              <div className="grid gap-4 sm:grid-cols-2" data-testid="tenant-wizard-step-review">
                <div className="rounded-lg border border-border p-3">
                  <p className="mb-1 text-[12px] font-semibold uppercase tracking-wide text-ink-3">Tenant</p>
                  <ReviewItem label="Nama" value={v.name} testId="review-name" />
                  <ReviewItem label="Kode (permanen)" value={v.code.toUpperCase()} testId="review-code" />
                  <ReviewItem label="PIC" value={v.pic_name} testId="review-pic" />
                  <ReviewItem label="No. HP PIC" value={v.pic_phone} />
                  <ReviewItem label="Email utama" value={v.email} testId="review-email" />
                </div>
                <div className="rounded-lg border border-border p-3">
                  <p className="mb-1 text-[12px] font-semibold uppercase tracking-wide text-ink-3">Masa layanan & admin</p>
                  <ReviewItem label="Mulai" value={v.subscription_start_date ? formatDate(v.subscription_start_date) : "-"} />
                  <ReviewItem label="Berakhir" value={v.subscription_end_date ? formatDate(v.subscription_end_date) : "-"} />
                  <ReviewItem label="Grace period" value={`${v.grace_period_days} hari`} />
                  <ReviewItem label="Tenant Admin" value={adminName} testId="review-admin-name" />
                  <ReviewItem label="Email login admin" value={adminEmail} testId="review-admin-email" />
                </div>
              </div>
            )}

            {errors.__form__ && (
              <div className="rounded-lg border border-danger-border bg-danger-soft px-3 py-2 text-sm text-destructive" role="alert" data-testid="tenant-wizard-error">
                {errors.__form__}
              </div>
            )}

            <DialogFooter className="gap-2 sm:justify-between">
              <Button variant="outline" onClick={step === 0 ? () => onOpenChange(false) : back} disabled={submitting} data-testid="tenant-wizard-back">
                {step === 0 ? "Batal" : (<><ChevronLeft className="mr-1 h-4 w-4" /> Kembali</>)}
              </Button>
              {step < 2 ? (
                <Button onClick={next} data-testid="tenant-wizard-next">
                  Lanjut <ChevronRight className="ml-1 h-4 w-4" />
                </Button>
              ) : (
                <Button onClick={submit} disabled={submitting} data-testid="tenant-wizard-submit">
                  {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Buat Tenant
                </Button>
              )}
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default TenantCreateWizard;
