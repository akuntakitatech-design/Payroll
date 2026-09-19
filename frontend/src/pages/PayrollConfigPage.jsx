import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Info, Loader2, RotateCcw, Save } from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const PERCENT_FIELDS = [
  "bpjs_kes_employee_rate",
  "bpjs_kes_employer_rate",
  "jht_employee_rate",
  "jht_employer_rate",
  "jp_employee_rate",
  "jp_employer_rate",
  "jkm_employer_rate",
];

const toForm = (statutory) => {
  const form = {};
  PERCENT_FIELDS.forEach((key) => {
    form[key] = String(Number(((statutory?.[key] ?? 0) * 100).toFixed(4)));
  });
  form.bpjs_kes_cap = String(statutory?.bpjs_kes_cap ?? 0);
  form.jp_cap = String(statutory?.jp_cap ?? 0);
  form.default_working_days = String(statutory?.default_working_days ?? 22);
  form.jkk_risk_class = statutory?.jkk_risk_class || "sedang";
  form.employer_bpjs_is_taxable = !!statutory?.employer_bpjs_is_taxable;
  form.non_npwp_surcharge = !!statutory?.non_npwp_surcharge;
  return form;
};

const NumberField = ({ id, label, hint, suffix, value, onChange, step = "0.01", testId }) => (
  <div className="space-y-1.5">
    <Label htmlFor={id}>{label}</Label>
    <div className="flex items-center gap-2">
      <Input
        id={id}
        type="number"
        step={step}
        min="0"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        data-testid={testId}
      />
      {suffix ? <span className="text-sm text-muted-foreground">{suffix}</span> : null}
    </div>
    {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
  </div>
);

const PayrollConfigPage = () => {
  const { can } = useAuth();
  const editable = can("payroll", "config");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [statutory, setStatutory] = useState(null);
  const [riskClasses, setRiskClasses] = useState([]);
  const [form, setForm] = useState(null);

  const load = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    try {
      const { data } = await api.get("/payroll/config");
      setStatutory(data?.statutory || null);
      const raw = data?.jkk_risk_classes || [];
      const list = Array.isArray(raw)
        ? raw
        : Object.entries(raw).map(([value, info]) => ({
            value,
            label: info?.label || value,
            rate: info?.rate || 0,
          }));
      setRiskClasses(list);
      setForm(toForm(data?.statutory));
    } catch (error) {
      toast.error(errorMessage(error, "Konfigurasi payroll tidak dapat dimuat."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    document.title = "Konfigurasi Payroll · HRIS Suite";
  }, []);

  const set = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  const save = async () => {
    setSaving(true);
    try {
      const payload = {
        bpjs_kes_cap: Number(form.bpjs_kes_cap),
        jp_cap: Number(form.jp_cap),
        default_working_days: Number(form.default_working_days),
        jkk_risk_class: form.jkk_risk_class,
        employer_bpjs_is_taxable: form.employer_bpjs_is_taxable,
        non_npwp_surcharge: form.non_npwp_surcharge,
      };
      PERCENT_FIELDS.forEach((key) => {
        payload[key] = Number(form[key]) / 100;
      });
      const { data } = await api.put("/payroll/config", payload);
      setStatutory(data?.statutory || null);
      setForm(toForm(data?.statutory));
      toast.success("Konfigurasi payroll disimpan. Hitung ulang payroll draf agar memakai angka baru.");
    } catch (error) {
      toast.error(errorMessage(error, "Konfigurasi gagal disimpan."));
    } finally {
      setSaving(false);
    }
  };

  if (loading || !form) {
    return (
      <>
        <PageHeader title="Konfigurasi Payroll" subtitle="Memuat parameter BPJS dan pajak…" />
        <PageBody>
          <Skeleton className="h-56 w-full" />
          <Skeleton className="h-56 w-full" />
        </PageBody>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Konfigurasi Payroll"
        subtitle="Parameter BPJS, PPh 21, dan hari kerja yang dipakai seluruh perhitungan."
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => load({ silent: true })} data-testid="payroll-config-reset">
              <RotateCcw className="mr-2 h-4 w-4" /> Muat ulang
            </Button>
            {editable && (
              <Button onClick={save} disabled={saving} data-testid="payroll-config-save">
                {saving ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Save className="mr-2 h-4 w-4" />
                )}
                Simpan
              </Button>
            )}
          </div>
        }
      />
      <PageBody>
        <div className="flex items-start gap-2 rounded-lg border border-border bg-secondary/40 p-3 text-xs text-muted-foreground">
          <Info className="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            PPh 21 dihitung dengan metode TER bulanan (PMK 168/2023) dan direkonsiliasi memakai
            tarif Pasal 17 pada masa pajak Desember. Nilai default mengikuti ketentuan yang berlaku;
            ubah hanya bila perusahaan memiliki kebijakan atau kelas risiko berbeda.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">BPJS Kesehatan</CardTitle>
              <CardDescription>Batas upah dan iuran pekerja/pemberi kerja.</CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <NumberField
                id="bpjs-kes-cap"
                label="Batas upah (Rp)"
                step="100000"
                value={form.bpjs_kes_cap}
                onChange={(v) => set("bpjs_kes_cap", v)}
                testId="config-bpjs-kes-cap"
              />
              <NumberField
                id="bpjs-kes-emp"
                label="Iuran pekerja"
                suffix="%"
                value={form.bpjs_kes_employee_rate}
                onChange={(v) => set("bpjs_kes_employee_rate", v)}
                testId="config-bpjs-kes-employee"
              />
              <NumberField
                id="bpjs-kes-er"
                label="Iuran perusahaan"
                suffix="%"
                value={form.bpjs_kes_employer_rate}
                onChange={(v) => set("bpjs_kes_employer_rate", v)}
                testId="config-bpjs-kes-employer"
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">BPJS Ketenagakerjaan</CardTitle>
              <CardDescription>JHT, Jaminan Pensiun, JKK, dan JKM.</CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <NumberField
                id="jht-emp"
                label="JHT pekerja"
                suffix="%"
                value={form.jht_employee_rate}
                onChange={(v) => set("jht_employee_rate", v)}
                testId="config-jht-employee"
              />
              <NumberField
                id="jht-er"
                label="JHT perusahaan"
                suffix="%"
                value={form.jht_employer_rate}
                onChange={(v) => set("jht_employer_rate", v)}
                testId="config-jht-employer"
              />
              <NumberField
                id="jp-emp"
                label="JP pekerja"
                suffix="%"
                value={form.jp_employee_rate}
                onChange={(v) => set("jp_employee_rate", v)}
                testId="config-jp-employee"
              />
              <NumberField
                id="jp-er"
                label="JP perusahaan"
                suffix="%"
                value={form.jp_employer_rate}
                onChange={(v) => set("jp_employer_rate", v)}
                testId="config-jp-employer"
              />
              <NumberField
                id="jp-cap"
                label="Batas upah JP (Rp)"
                step="100000"
                value={form.jp_cap}
                onChange={(v) => set("jp_cap", v)}
                testId="config-jp-cap"
              />
              <NumberField
                id="jkm"
                label="JKM perusahaan"
                suffix="%"
                value={form.jkm_employer_rate}
                onChange={(v) => set("jkm_employer_rate", v)}
                testId="config-jkm"
              />
              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="jkk-class">Kelas risiko JKK</Label>
                <Select
                  value={form.jkk_risk_class}
                  onValueChange={(v) => set("jkk_risk_class", v)}
                >
                  <SelectTrigger id="jkk-class" data-testid="config-jkk-class">
                    <SelectValue placeholder="Pilih kelas risiko" />
                  </SelectTrigger>
                  <SelectContent>
                    {riskClasses.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Tarif JKK aktif saat ini: {((statutory?.jkk_employer_rate || 0) * 100).toFixed(2)}%
                </p>
              </div>
            </CardContent>
          </Card>

          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle className="text-base">Pajak & Kehadiran</CardTitle>
              <CardDescription>
                Dasar perhitungan PPh 21 dan asumsi hari kerja per bulan.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <NumberField
                id="working-days"
                label="Hari kerja default per bulan"
                step="1"
                value={form.default_working_days}
                onChange={(v) => set("default_working_days", v)}
                testId="config-working-days"
              />
              <div className="space-y-3">
                <div className="flex items-start justify-between gap-4 rounded-lg border border-border p-3">
                  <div>
                    <p className="text-sm font-medium">BPJS perusahaan menambah bruto pajak</p>
                    <p className="text-xs text-muted-foreground">
                      Iuran kesehatan, JKK, dan JKM yang dibayar perusahaan diperlakukan sebagai
                      natura.
                    </p>
                  </div>
                  <Switch
                    checked={form.employer_bpjs_is_taxable}
                    onCheckedChange={(v) => set("employer_bpjs_is_taxable", v)}
                    data-testid="config-employer-bpjs-taxable"
                  />
                </div>
                <div className="flex items-start justify-between gap-4 rounded-lg border border-border p-3">
                  <div>
                    <p className="text-sm font-medium">Tambahan 20% tanpa NPWP</p>
                    <p className="text-xs text-muted-foreground">
                      Aktifkan bila perusahaan menerapkan surcharge bagi pekerja tanpa NPWP.
                    </p>
                  </div>
                  <Switch
                    checked={form.non_npwp_surcharge}
                    onCheckedChange={(v) => set("non_npwp_surcharge", v)}
                    data-testid="config-non-npwp-surcharge"
                  />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </PageBody>
    </>
  );
};

export default PayrollConfigPage;
