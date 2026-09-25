import React, { useCallback, useEffect, useRef, useState } from "react";
import { ImageUp, Loader2, Save, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import { Field } from "@/components/common/FormDialog";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import StatusBadge from "@/components/common/StatusBadge";
import { SubscriptionBadge, subscriptionHint } from "@/components/common/SubscriptionBadge";
import { formatDate } from "@/lib/format";
import { logoVersion, TenantLogo } from "@/components/common/TenantLogo";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import { IMAGE_ACCEPT, validateImageFile } from "@/pages/platform/PlatformBrandingPage";

const MAX_LOGO_MB = 10;

const FIELDS = [
  { name: "name", label: "Nama Perusahaan", required: true },
  { name: "legal_name", label: "Nama Badan Hukum" },
  { name: "npwp", label: "NPWP" },
  { name: "industry", label: "Bidang Usaha" },
  { name: "phone", label: "Telepon" },
  { name: "email", label: "Email" },
  { name: "website", label: "Website" },
  { name: "city", label: "Kota" },
  { name: "province", label: "Provinsi" },
  { name: "postal_code", label: "Kode Pos" },
  {
    name: "timezone",
    label: "Zona Waktu",
    type: "select",
    required: true,
    options: [
      { value: "Asia/Jakarta", label: "WIB — Asia/Jakarta" },
      { value: "Asia/Makassar", label: "WITA — Asia/Makassar" },
      { value: "Asia/Jayapura", label: "WIT — Asia/Jayapura" },
    ],
  },
  {
    name: "currency",
    label: "Mata Uang",
    type: "select",
    required: true,
    options: [
      { value: "IDR", label: "IDR — Rupiah" },
      { value: "USD", label: "USD — Dolar AS" },
      { value: "SGD", label: "SGD — Dolar Singapura" },
    ],
  },
  {
    name: "fiscal_year_start_month",
    label: "Awal Tahun Buku",
    type: "select",
    required: true,
    options: [
      "Januari", "Februari", "Maret", "April", "Mei", "Juni",
      "Juli", "Agustus", "September", "Oktober", "November", "Desember",
    ].map((m, i) => ({ value: String(i + 1), label: m })),
  },
  { name: "address", label: "Alamat Lengkap", type: "textarea", colSpan: 2 },
];

const COUNT_LABELS = {
  branches: "Cabang",
  work_locations: "Lokasi Kerja",
  departments: "Departemen",
  divisions: "Divisi",
  positions: "Jabatan",
  job_grades: "Grade",
  cost_centers: "Cost Center",
  projects: "Proyek",
};

const CompanyProfilePage = () => {
  const { can, refreshSession, company, isSuperAdmin } = useAuth();
  const [data, setData] = useState(null);
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const editable = can("company", "edit");
  const logoInput = useRef(null);
  const [logoBusy, setLogoBusy] = useState(false);
  const [logoError, setLogoError] = useState("");
  const [logoConfirm, setLogoConfirm] = useState(false);

  const uploadLogo = async (file) => {
    setLogoError("");
    const msg = validateImageFile(file, MAX_LOGO_MB);
    if (msg) {
      setLogoError(msg);
      if (logoInput.current) logoInput.current.value = "";
      return;
    }
    const form = new FormData();
    form.append("file", file);
    setLogoBusy(true);
    try {
      const { data: res } = await api.post("/companies/current/logo", form);
      toast.success(res.message);
      setData((d) => (d ? { ...d, company: { ...d.company, ...res.company } } : d));
      await refreshSession();
    } catch (err) {
      setLogoError(errorMessage(err, "Logo tidak dapat diunggah."));
    } finally {
      setLogoBusy(false);
      if (logoInput.current) logoInput.current.value = "";
    }
  };

  const deleteLogo = async () => {
    setLogoBusy(true);
    try {
      const { data: res } = await api.delete("/companies/current/logo");
      toast.success(res.message);
      setData((d) => (d ? { ...d, company: { ...d.company, ...res.company } } : d));
      await refreshSession();
    } catch (err) {
      toast.error(errorMessage(err, "Logo tidak dapat dihapus."));
    } finally {
      setLogoBusy(false);
      setLogoConfirm(false);
    }
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/companies/current");
      setData(res.data);
      const c = res.data.company;
      const next = {};
      FIELDS.forEach((f) => {
        next[f.name] = c[f.name] ?? "";
      });
      next.fiscal_year_start_month = String(c.fiscal_year_start_month || 1);
      setValues(next);
    } catch (err) {
      toast.error(errorMessage(err, "Gagal memuat profil perusahaan."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    document.title = "Profil Perusahaan · HRIS Suite";
  }, [load, company?.id]);

  const handleChange = (name, value) => {
    setValues((p) => ({ ...p, [name]: value }));
    setErrors((p) => ({ ...p, [name]: undefined, __form__: undefined }));
  };

  const handleSave = async () => {
    const nextErrors = {};
    FIELDS.filter((f) => f.required).forEach((f) => {
      if (!String(values[f.name] ?? "").trim()) nextErrors[f.name] = `${f.label} wajib diisi.`;
    });
    if (Object.keys(nextErrors).length) {
      setErrors(nextErrors);
      toast.error("Beberapa kolom wajib masih kosong. Periksa kembali form di bawah.");
      return;
    }
    setSaving(true);
    try {
      const payload = {};
      FIELDS.forEach((f) => {
        const v = values[f.name];
        payload[f.name] = v === "" ? null : v;
      });
      payload.fiscal_year_start_month = Number(values.fiscal_year_start_month || 1);
      await api.put("/companies/current", payload);
      toast.success("Profil perusahaan berhasil disimpan.");
      await refreshSession();
      load();
    } catch (err) {
      setErrors({ __form__: errorMessage(err, "Profil perusahaan tidak dapat disimpan.") });
      toast.error(errorMessage(err, "Profil perusahaan tidak dapat disimpan."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Profil Perusahaan"
        subtitle="Identitas perusahaan yang dipakai pada dokumen, kontrak, dan laporan."
        actions={
          editable && (
            <Button onClick={handleSave} disabled={saving || loading} data-testid="company-save-button">
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
              Simpan perubahan
            </Button>
          )
        }
      />
      <PageBody>
        {loading ? (
          <Skeleton className="h-96 w-full" />
        ) : (
          data && (
            <div className="grid gap-4 lg:grid-cols-3">
              <Card className="border-border bg-card p-4 lg:col-span-1" data-testid="company-summary-card">
                <div className="flex items-start gap-3">
                  <TenantLogo
                    size="lg"
                    hasLogo={!!data.company.logo_path}
                    version={logoVersion(data.company)}
                    name={data.company.name}
                    testId="company-logo"
                  />
                  <div className="min-w-0">
                    <p className="text-section-title">{data.company.name}</p>
                    <p className="text-sm text-muted-foreground">Kode: {data.company.code}</p>
                    <StatusBadge status={data.company.status} className="mt-1.5" />
                  </div>
                </div>
                {editable && (
                  <div className="mt-3 space-y-1.5" data-testid="company-logo-controls">
                    <input
                      ref={logoInput}
                      type="file"
                      accept={IMAGE_ACCEPT}
                      className="hidden"
                      onChange={(e) => e.target.files?.[0] && uploadLogo(e.target.files[0])}
                      data-testid="company-logo-input"
                    />
                    <div className="flex flex-wrap gap-2">
                      <Button size="sm" variant="outline" onClick={() => logoInput.current?.click()} disabled={logoBusy} data-testid="company-logo-upload">
                        {logoBusy ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <ImageUp className="mr-1.5 h-3.5 w-3.5" />}
                        {data.company.logo_path ? "Ganti logo" : "Unggah logo"}
                      </Button>
                      {data.company.logo_path && (
                        <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={() => setLogoConfirm(true)} disabled={logoBusy} data-testid="company-logo-delete">
                          <Trash2 className="mr-1.5 h-3.5 w-3.5" /> Hapus
                        </Button>
                      )}
                    </div>
                    <p className="text-[11px] text-muted-foreground">PNG, JPG, JPEG, atau WEBP · maksimal {MAX_LOGO_MB} MB.</p>
                    {logoError && <p className="text-xs text-destructive" role="alert" data-testid="company-logo-error">{logoError}</p>}
                  </div>
                )}
                <div className="mt-4 space-y-2 border-t border-border pt-4">
                  <p className="text-[12px] text-muted-foreground">
                    Kelengkapan master data
                  </p>
                  <ul className="space-y-1.5">
                    {Object.entries(data.counts).map(([key, value]) => (
                      <li key={key} className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">{COUNT_LABELS[key] || key}</span>
                        <span className="font-medium" data-numeric="true" data-testid={`company-count-${key}`}>
                          {value}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
                {/* Masa layanan: hanya ditampilkan; perubahan khusus Platform Admin (Platform > Tenant Management). */}
                <div className="mt-4 space-y-2 border-t border-border pt-4" data-testid="company-subscription-card">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[12px] text-muted-foreground">Masa layanan</p>
                    <SubscriptionBadge subscription={data.company.subscription} testId="company-subscription-badge" />
                  </div>
                  <ul className="space-y-1.5 text-sm">
                    <li className="flex items-center justify-between">
                      <span className="text-muted-foreground">Mulai</span>
                      <span className="font-medium" data-testid="company-subscription-start">
                        {data.company.subscription?.start_date ? formatDate(data.company.subscription.start_date) : "-"}
                      </span>
                    </li>
                    <li className="flex items-center justify-between">
                      <span className="text-muted-foreground">Berakhir</span>
                      <span className="font-medium" data-testid="company-subscription-end">
                        {data.company.subscription?.end_date ? formatDate(data.company.subscription.end_date) : "-"}
                      </span>
                    </li>
                  </ul>
                  <p className="text-xs text-muted-foreground" data-testid="company-subscription-hint">
                    {subscriptionHint(data.company.subscription)} · diatur oleh Platform Admin.
                  </p>
                </div>
                {!editable && (
                  <p className="mt-4 rounded-lg border border-border bg-secondary px-3 py-2 text-xs text-secondary-foreground">
                    Anda hanya dapat melihat data ini. Hubungi HR Manager atau Pemilik Perusahaan untuk mengubahnya.
                  </p>
                )}
              </Card>

              <Card className="border-border bg-card p-4 lg:col-span-2">
                <h2 className="text-section-title">Data Perusahaan</h2>
                <p className="mt-0.5 text-sm text-muted-foreground">
                  Kolom bertanda * wajib diisi. Setiap perubahan tercatat di audit log.
                </p>
                <fieldset
                  disabled={!editable}
                  className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 disabled:opacity-90"
                >
                  {FIELDS.map((f) => {
                    // Identitas tenant hanya dapat diubah Platform Admin (Platform -> Tenant Management).
                    const tenantLocked = !isSuperAdmin && ["name", "legal_name"].includes(f.name);
                    const field = tenantLocked
                      ? { ...f, disabled: true, hint: "Hanya dapat diubah oleh Platform Admin." }
                      : f;
                    return (
                      <Field
                        key={f.name}
                        field={field}
                        value={values[f.name]}
                        error={errors[f.name]}
                        onChange={handleChange}
                      />
                    );
                  })}
                </fieldset>
                {errors.__form__ && (
                  <div className="mt-4 rounded-lg border border-danger-border bg-danger-soft px-3 py-2 text-sm text-destructive">
                    {errors.__form__}
                  </div>
                )}
              </Card>
            </div>
          )
        )}
      </PageBody>
      <ConfirmDialog
        open={logoConfirm}
        onOpenChange={setLogoConfirm}
        title="Hapus logo perusahaan?"
        description="Placeholder default akan ditampilkan. Logo platform tidak terpengaruh."
        confirmLabel="Hapus"
        destructive
        loading={logoBusy}
        onConfirm={deleteLogo}
      />
    </>
  );
};

export default CompanyProfilePage;
