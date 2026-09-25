import React, { useEffect, useRef, useState } from "react";
import { ImageUp, Loader2, RotateCcw, Save, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { assetUrl, brandTitle, PlatformLogo, useBranding } from "@/lib/branding";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";

export const IMAGE_ACCEPT = ".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp";
const ALLOWED_EXT = ["png", "jpg", "jpeg", "webp"];

/** Validasi di frontend (backend tetap memvalidasi ulang). Return pesan error atau null. */
export const validateImageFile = (file, maxMb = 10) => {
  if (!file) return "Pilih berkas terlebih dahulu.";
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  if (!ALLOWED_EXT.includes(ext)) return "Format tidak didukung. Gunakan PNG, JPG, JPEG, atau WEBP.";
  if (file.size > maxMb * 1024 * 1024) return `Ukuran berkas melebihi batas ${maxMb} MB.`;
  return null;
};

const TEXT_FIELDS = [
  { name: "app_name", label: "Nama aplikasi", required: true, max: 60 },
  { name: "subtitle", label: "Subtitle", max: 80, hint: "Tampil di samping logo, mis. HRIS & Payroll." },
  { name: "tagline", label: "Tagline", max: 200, hint: "Tampil di bagian bawah panel hero login." },
  { name: "login_headline", label: "Headline halaman login", max: 160 },
  { name: "login_supporting_text", label: "Teks pendukung halaman login", max: 500, textarea: true },
  { name: "support_contact", label: "Kontak bantuan", max: 160, hint: "Opsional. Ditampilkan pada dialog Lupa Password." },
];

const AssetCard = ({ asset, title, description, branding, onChanged, testId }) => {
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const url = branding[`${asset}_url`];

  const upload = async (file) => {
    setError("");
    const msg = validateImageFile(file, branding.max_logo_mb || 10);
    if (msg) {
      setError(msg);
      return;
    }
    const form = new FormData();
    form.append("file", file);
    setBusy(true);
    try {
      const { data } = await api.post(`/platform/branding/${asset}`, form);
      toast.success(`${title} berhasil disimpan.`);
      onChanged(data);
    } catch (err) {
      setError(errorMessage(err, `${title} tidak dapat diunggah.`));
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      const { data } = await api.delete(`/platform/branding/${asset}`);
      toast.success(`${title} dihapus. Tampilan kembali ke default.`);
      onChanged(data);
    } catch (err) {
      toast.error(errorMessage(err, `${title} tidak dapat dihapus.`));
    } finally {
      setBusy(false);
      setConfirmOpen(false);
    }
  };

  return (
    <Card className="border-border bg-card p-4" data-testid={testId}>
      <h2 className="text-section-title">{title}</h2>
      <p className="mt-0.5 text-[13px] text-muted-foreground">{description}</p>
      <div className="mt-4 flex h-28 items-center justify-center rounded-lg border border-dashed border-border bg-secondary/60 p-3" data-testid={`${testId}-preview`}>
        {url ? (
          <img src={assetUrl(url)} alt={title} className="max-h-full max-w-full object-contain" data-testid={`${testId}-image`} />
        ) : asset === "logo" ? (
          <div className="flex flex-col items-center gap-2">
            <PlatformLogo testId={`${testId}-default`} />
            <span className="text-[11px] text-muted-foreground">Logo teks default (belum ada logo custom)</span>
          </div>
        ) : (
          <span className="text-xs text-muted-foreground" data-testid={`${testId}-empty`}>Memakai favicon bawaan</span>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={IMAGE_ACCEPT}
        className="hidden"
        onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
        data-testid={`${testId}-input`}
      />
      {error && <p className="mt-2 text-xs text-destructive" role="alert" data-testid={`${testId}-error`}>{error}</p>}
      <p className="mt-2 text-xs text-muted-foreground">PNG, JPG, JPEG, atau WEBP · maksimal {branding.max_logo_mb || 10} MB.</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button onClick={() => inputRef.current?.click()} disabled={busy} data-testid={`${testId}-upload`}>
          {busy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <ImageUp className="mr-1.5 h-4 w-4" />}
          {url ? "Ganti" : "Unggah"}
        </Button>
        {url && (
          <Button variant="outline" className="text-destructive hover:text-destructive" onClick={() => setConfirmOpen(true)} disabled={busy} data-testid={`${testId}-delete`}>
            <Trash2 className="mr-1.5 h-4 w-4" /> Hapus
          </Button>
        )}
      </div>
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={`Hapus ${title.toLowerCase()}?`}
        description="Tampilan akan kembali ke default KelolaKita. Logo tenant tidak terpengaruh."
        confirmLabel="Hapus"
        destructive
        loading={busy}
        onConfirm={remove}
      />
    </Card>
  );
};

const PlatformBrandingPage = () => {
  const { branding, setBranding, refresh } = useBranding();
  const [form, setForm] = useState(null);
  const [defaults, setDefaults] = useState({});
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    document.title = brandTitle(branding, "Branding Platform");
  }, [branding]);

  const load = async () => {
    setLoadError("");
    try {
      const { data } = await api.get("/platform/branding");
      setDefaults(data.defaults || {});
      setForm(Object.fromEntries(TEXT_FIELDS.map((f) => [f.name, data[f.name] || ""])));
      setBranding((b) => ({ ...b, ...data }));
    } catch (err) {
      setLoadError(errorMessage(err, "Pengaturan branding tidak dapat dimuat."));
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const save = async () => {
    const e = {};
    if (String(form.app_name || "").trim().length < 2) e.app_name = "Nama aplikasi minimal 2 karakter.";
    if (Object.keys(e).length) return setErrors(e);
    setSaving(true);
    try {
      const payload = Object.fromEntries(TEXT_FIELDS.map((f) => [f.name, String(form[f.name] || "").trim() || null]));
      const { data } = await api.put("/platform/branding", payload);
      setBranding((b) => ({ ...b, ...data }));
      toast.success("Branding platform disimpan. Halaman login memakai konfigurasi baru.");
    } catch (err) {
      setErrors({ __form__: errorMessage(err, "Branding tidak dapat disimpan.") });
    } finally {
      setSaving(false);
    }
  };

  const onAssetChanged = (data) => {
    setBranding((b) => ({ ...b, ...data }));
    refresh();
  };

  return (
    <>
      <PageHeader
        title="Branding Platform"
        subtitle="Identitas produk yang tampil di halaman login dan Konsol Platform. Terpisah dari logo masing-masing tenant."
        actions={
          <Button onClick={save} disabled={!form || saving} data-testid="branding-save">
            {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Save className="mr-1.5 h-4 w-4" />} Simpan branding
          </Button>
        }
      />
      <PageBody>
        {loadError && (
          <Card className="flex items-center justify-between gap-3 border-danger-border bg-danger-soft p-4 text-sm text-destructive" data-testid="branding-load-error">
            {loadError}
            <Button size="sm" variant="outline" onClick={load}>Coba lagi</Button>
          </Card>
        )}
        <div className="grid gap-4 xl:grid-cols-3">
          <Card className="border-border bg-card p-4 xl:col-span-2" data-testid="branding-text-card">
            <h2 className="text-section-title">Teks & identitas</h2>
            <p className="mt-0.5 text-[13px] text-muted-foreground">Kosongkan kolom untuk kembali ke nilai default.</p>
            {!form ? (
              <Skeleton className="mt-4 h-72 w-full" />
            ) : (
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                {TEXT_FIELDS.map((f) => (
                  <div key={f.name} className={f.textarea ? "space-y-1.5 sm:col-span-2" : "space-y-1.5"}>
                    <Label htmlFor={`br-${f.name}`} className="text-[13px]">
                      {f.label} {f.required && <span className="text-destructive">*</span>}
                    </Label>
                    {f.textarea ? (
                      <Textarea id={`br-${f.name}`} rows={3} maxLength={f.max} value={form[f.name]} placeholder={defaults[f.name] || ""}
                        onChange={(e) => { setForm((p) => ({ ...p, [f.name]: e.target.value })); setErrors({}); }} data-testid={`branding-${f.name}-input`} />
                    ) : (
                      <Input id={`br-${f.name}`} maxLength={f.max} value={form[f.name]} placeholder={defaults[f.name] || ""}
                        onChange={(e) => { setForm((p) => ({ ...p, [f.name]: e.target.value })); setErrors({}); }} data-testid={`branding-${f.name}-input`} />
                    )}
                    {errors[f.name] ? (
                      <p className="text-xs text-destructive" data-testid={`branding-${f.name}-error`}>{errors[f.name]}</p>
                    ) : (
                      f.hint && <p className="text-xs text-muted-foreground">{f.hint}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
            {errors.__form__ && (
              <p className="mt-3 rounded-lg border border-danger-border bg-danger-soft px-3 py-2 text-sm text-destructive" data-testid="branding-form-error">{errors.__form__}</p>
            )}
            {form && (
              <Button variant="ghost" size="sm" className="mt-3" onClick={() => setForm(Object.fromEntries(TEXT_FIELDS.map((f) => [f.name, ""])))} data-testid="branding-reset-defaults">
                <RotateCcw className="mr-1.5 h-4 w-4" /> Kosongkan semua (pakai default)
              </Button>
            )}
          </Card>

          <div className="space-y-4">
            <AssetCard asset="logo" title="Logo platform" description="Tampil di halaman login dan sidebar Konsol Platform." branding={branding} onChanged={onAssetChanged} testId="branding-logo" />
            <AssetCard asset="favicon" title="Favicon" description="Ikon kecil pada tab browser." branding={branding} onChanged={onAssetChanged} testId="branding-favicon" />
          </div>
        </div>

        <Card className="overflow-hidden border-border bg-card" data-testid="branding-preview">
          <div className="border-b border-border px-4 py-3">
            <h2 className="text-section-title">Pratinjau panel login</h2>
          </div>
          <div className="login-accent p-6 text-white">
            <PlatformLogo inverse testId="branding-preview-logo" />
            <p className="mt-5 max-w-xl text-xl font-semibold leading-snug">{form?.login_headline || defaults.login_headline}</p>
            <p className="mt-2 max-w-xl text-sm text-white/80">{form?.login_supporting_text || defaults.login_supporting_text}</p>
            <p className="mt-4 text-xs text-white/60">{form?.tagline || defaults.tagline}</p>
          </div>
        </Card>
      </PageBody>
    </>
  );
};

export default PlatformBrandingPage;
