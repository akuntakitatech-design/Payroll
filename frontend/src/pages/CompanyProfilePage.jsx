import React, { useCallback, useEffect, useState } from "react";
import { Loader2, Save, Building2 } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import { Field } from "@/components/common/FormDialog";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import StatusBadge from "@/components/common/StatusBadge";

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
  { name: "logo_url", label: "URL Logo", hint: "Tautan gambar logo perusahaan (opsional)." },
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
  const { can, refreshSession, company } = useAuth();
  const [data, setData] = useState(null);
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const editable = can("company", "edit");

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
                  <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                    <Building2 className="h-6 w-6" />
                  </span>
                  <div className="min-w-0">
                    <p className="text-section-title">{data.company.name}</p>
                    <p className="text-sm text-muted-foreground">Kode: {data.company.code}</p>
                    <StatusBadge status={data.company.status} className="mt-1.5" />
                  </div>
                </div>
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
                  {FIELDS.map((f) => (
                    <Field
                      key={f.name}
                      field={f}
                      value={values[f.name]}
                      error={errors[f.name]}
                      onChange={handleChange}
                    />
                  ))}
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
    </>
  );
};

export default CompanyProfilePage;
