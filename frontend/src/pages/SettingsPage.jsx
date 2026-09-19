import React, { useCallback, useEffect, useState } from "react";
import { Loader2, Save } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import { Field } from "@/components/common/FormDialog";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

const GROUPS = [
  {
    key: "identity",
    title: "Penomoran & Format",
    description: "Menentukan bagaimana sistem membuat nomor induk karyawan dan menampilkan angka/tanggal.",
    fields: [
      { name: "employee_id_prefix", label: "Awalan NIK Karyawan", hint: "Contoh: NEP menghasilkan NEP-0001." },
      { name: "employee_id_next_number", label: "Nomor Berikutnya", type: "number" },
      {
        name: "date_format",
        label: "Format Tanggal",
        type: "select",
        options: [
          { value: "DD/MM/YYYY", label: "DD/MM/YYYY (31/12/2026)" },
          { value: "DD-MM-YYYY", label: "DD-MM-YYYY (31-12-2026)" },
          { value: "YYYY-MM-DD", label: "YYYY-MM-DD (2026-12-31)" },
        ],
      },
      {
        name: "number_format",
        label: "Format Angka",
        type: "select",
        options: [
          { value: "1.000,00", label: "1.000,00 (Indonesia)" },
          { value: "1,000.00", label: "1,000.00 (Internasional)" },
        ],
      },
      {
        name: "week_start",
        label: "Awal Minggu",
        type: "select",
        options: [
          { value: "monday", label: "Senin" },
          { value: "sunday", label: "Minggu" },
        ],
      },
      {
        name: "default_language",
        label: "Bahasa Antarmuka",
        type: "select",
        options: [{ value: "id", label: "Bahasa Indonesia" }],
      },
    ],
  },
  {
    key: "notification",
    title: "Notifikasi",
    description: "Alamat email yang menerima ringkasan dan pengingat sistem.",
    fields: [
      { name: "notification_email", label: "Email Notifikasi" },
      { name: "enable_email_notification", label: "Aktifkan Notifikasi Email", type: "boolean" },
    ],
  },
  {
    key: "security",
    title: "Keamanan & Audit",
    description: "Kebijakan keamanan akun dan lama penyimpanan jejak audit.",
    fields: [
      { name: "password_min_length", label: "Panjang Minimal Kata Sandi", type: "number" },
      { name: "session_timeout_minutes", label: "Batas Sesi (menit)", type: "number" },
      { name: "enable_audit_retention_days", label: "Simpan Audit Log (hari)", type: "number" },
      {
        name: "require_two_factor",
        label: "Wajib Verifikasi Dua Langkah",
        type: "boolean",
        hint: "Disiapkan untuk fase berikutnya.",
      },
    ],
  },
];

const ALL_FIELDS = GROUPS.flatMap((g) => g.fields);

const SettingsPage = () => {
  const { can, company } = useAuth();
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const editable = can("settings", "config");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/companies/current");
      const s = res.data.settings || {};
      const next = {};
      ALL_FIELDS.forEach((f) => {
        next[f.name] = s[f.name] ?? (f.type === "boolean" ? false : "");
      });
      setValues(next);
    } catch (err) {
      toast.error(errorMessage(err, "Gagal memuat pengaturan sistem."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    document.title = "Pengaturan Sistem · HRIS Suite";
  }, [load, company?.id]);

  const handleChange = (name, value) => {
    setValues((p) => ({ ...p, [name]: value }));
    setErrors((p) => ({ ...p, [name]: undefined }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = {};
      ALL_FIELDS.forEach((f) => {
        const v = values[f.name];
        if (f.type === "boolean") payload[f.name] = !!v;
        else if (f.type === "number") payload[f.name] = v === "" ? null : Number(v);
        else payload[f.name] = v === "" ? null : v;
      });
      Object.keys(payload).forEach((k) => payload[k] === null && delete payload[k]);
      await api.put("/companies/current/settings", payload);
      toast.success("Pengaturan sistem berhasil disimpan.");
      load();
    } catch (err) {
      const msg = errorMessage(err, "Pengaturan tidak dapat disimpan.");
      setErrors({ __form__: msg });
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Pengaturan Sistem"
        subtitle="Format nomor, tanggal, dan aturan keamanan untuk perusahaan aktif."
        actions={
          editable && (
            <Button onClick={handleSave} disabled={saving || loading} data-testid="settings-save-button">
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
              Simpan pengaturan
            </Button>
          )
        }
      />
      <PageBody>
        {!editable && (
          <div className="rounded-lg border border-border bg-secondary px-4 py-3 text-sm text-secondary-foreground">
            Anda hanya memiliki akses lihat untuk pengaturan sistem. Perubahan hanya dapat dilakukan oleh
            HR Manager atau Pemilik Perusahaan.
          </div>
        )}
        {loading ? (
          <Skeleton className="h-96 w-full" />
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {GROUPS.map((group) => (
              <Card
                key={group.key}
                className="border-border bg-card p-4"
                data-testid={`settings-group-${group.key}`}
              >
                <h2 className="text-section-title">{group.title}</h2>
                <p className="mt-0.5 text-sm text-muted-foreground">{group.description}</p>
                <fieldset disabled={!editable} className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
                  {group.fields.map((f) => (
                    <Field
                      key={f.name}
                      field={f}
                      value={values[f.name]}
                      error={errors[f.name]}
                      onChange={handleChange}
                    />
                  ))}
                </fieldset>
              </Card>
            ))}
          </div>
        )}
        {errors.__form__ && (
          <div className="rounded-lg border border-danger-border bg-danger-soft px-3 py-2 text-sm text-destructive">
            {errors.__form__}
          </div>
        )}
      </PageBody>
    </>
  );
};

export default SettingsPage;
