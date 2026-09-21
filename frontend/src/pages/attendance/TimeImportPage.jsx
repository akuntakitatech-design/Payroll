import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  Loader2,
  RotateCcw,
  Upload,
} from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { downloadFile } from "@/lib/download";
import { PageBody, SectionHeader } from "@/components/common/PageHeader";
import { DataTable, TableCard } from "@/components/common/DataTable";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { formatDateTime } from "@/lib/format";

const KINDS = {
  attendance: {
    label: "Absensi",
    base: "/attendance/imports",
    templateName: "Template-Import-Absensi.xlsx",
    description:
      "Impor jam masuk & pulang dari mesin absensi atau rekap manual. Nomor karyawan harus sesuai Data Karyawan.",
  },
  schedule: {
    label: "Jadwal Kerja",
    base: "/schedules/imports",
    templateName: "Template-Import-Jadwal.xlsx",
    description: "Impor jadwal shift per karyawan per tanggal, termasuk hari OFF dan lokasi kerja.",
  },
};

const STEPS = [
  { key: 1, label: "Unduh template" },
  { key: 2, label: "Unggah & petakan kolom" },
  { key: 3, label: "Pratinjau validasi" },
  { key: 4, label: "Simpan data" },
];

const Stepper = ({ current, testId }) => (
  <ol className="flex flex-wrap items-center gap-3" data-testid={testId}>
    {STEPS.map((step) => {
      const state = current > step.key ? "done" : current === step.key ? "active" : "todo";
      return (
        <li key={step.key} className="flex items-center gap-2">
          <span
            className={`flex h-7 w-7 items-center justify-center rounded-full border text-xs font-semibold ${
              state === "done"
                ? "border-success-border bg-success-soft text-success"
                : state === "active"
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border bg-secondary text-muted-foreground"
            }`}
          >
            {state === "done" ? <CheckCircle2 className="h-4 w-4" /> : step.key}
          </span>
          <span className={`text-[13px] ${state === "todo" ? "text-muted-foreground" : "font-medium text-foreground"}`}>
            {step.label}
          </span>
        </li>
      );
    })}
  </ol>
);

const ImportWizard = ({ kind }) => {
  const meta = KINDS[kind];
  const fileRef = useRef(null);
  const [file, setFile] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [mapping, setMapping] = useState({});
  const [overwrite, setOverwrite] = useState(false);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState("");
  const [batches, setBatches] = useState([]);

  const loadBatches = useCallback(async () => {
    try {
      const { data } = await api.get(meta.base);
      setBatches(data?.items || []);
    } catch (error) {
      setBatches([]);
    }
  }, [meta.base]);

  useEffect(() => {
    loadBatches();
  }, [loadBatches]);

  const reset = () => {
    setFile(null);
    setAnalysis(null);
    setMapping({});
    setPreview(null);
    setResult(null);
    setOverwrite(false);
    if (fileRef.current) fileRef.current.value = "";
  };

  const step = result ? 4 : preview ? 3 : analysis ? 2 : 1;

  const downloadTemplate = async () => {
    setBusy("template");
    try {
      await downloadFile(`${meta.base}/template`, meta.templateName);
      toast.success("Template Excel berhasil diunduh.");
    } catch (error) {
      toast.error(errorMessage(error, "Template tidak dapat diunduh."));
    } finally {
      setBusy("");
    }
  };

  const analyze = async (selected) => {
    setFile(selected || null);
    setPreview(null);
    setResult(null);
    if (!selected) {
      setAnalysis(null);
      return;
    }
    setBusy("analyze");
    try {
      const fd = new FormData();
      fd.append("file", selected);
      const { data } = await api.post(`${meta.base}/analyze`, fd);
      setAnalysis(data);
      setMapping(data?.suggested_mapping || {});
      toast.success(`${data?.total_rows || 0} baris terbaca. Periksa pemetaan kolom.`);
    } catch (error) {
      setAnalysis(null);
      toast.error(errorMessage(error, "Berkas tidak dapat dibaca."));
    } finally {
      setBusy("");
    }
  };

  const runPreview = async () => {
    const missing = (analysis?.fields || [])
      .filter((f) => f.required && !mapping[f.key])
      .map((f) => f.label);
    if (missing.length) {
      toast.error(`Kolom wajib belum dipetakan: ${missing.join(", ")}.`);
      return;
    }
    setBusy("preview");
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("mapping", JSON.stringify(mapping));
      fd.append("overwrite_existing", overwrite ? "true" : "false");
      const { data } = await api.post(`${meta.base}/preview`, fd);
      setPreview(data);
      setResult(null);
      const s = data?.summary || {};
      if (s.error_rows) toast.warning(`${s.error_rows} baris bermasalah dan akan dilewati.`);
      else toast.success("Semua baris valid dan siap disimpan.");
    } catch (error) {
      toast.error(errorMessage(error, "Pratinjau gagal dibuat."), { duration: 9000 });
    } finally {
      setBusy("");
    }
  };

  const commit = async () => {
    setBusy("commit");
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("mapping", JSON.stringify(mapping));
      fd.append("overwrite_existing", overwrite ? "true" : "false");
      const { data } = await api.post(`${meta.base}/commit`, fd);
      setResult(data);
      toast.success(data?.message || "Impor selesai.");
      loadBatches();
    } catch (error) {
      toast.error(errorMessage(error, "Data gagal disimpan."), { duration: 9000 });
    } finally {
      setBusy("");
    }
  };

  const summary = preview?.summary || {};
  const errorRows = (preview?.rows || []).filter((r) => r.action === "error");
  const okRows = (preview?.rows || []).filter((r) => r.action === "create" || r.action === "update");
  const skippedRows = (preview?.rows || []).filter((r) => r.action === "skip");

  return (
    <div className="space-y-4">
      <Stepper current={step} testId={`import-stepper-${kind}`} />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Unggah Berkas Excel</CardTitle>
          <CardDescription>{meta.description}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <Button
              variant="outline"
              onClick={downloadTemplate}
              disabled={busy === "template"}
              data-testid={`import-template-${kind}`}
            >
              {busy === "template" ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Download className="mr-2 h-4 w-4" />
              )}
              Unduh Template
            </Button>
            <Input
              ref={fileRef}
              type="file"
              accept=".xlsx,.xlsm"
              onChange={(e) => analyze(e.target.files?.[0])}
              className="sm:max-w-md"
              data-testid={`import-file-${kind}`}
            />
            {(file || analysis) && (
              <Button variant="ghost" onClick={reset} data-testid={`import-reset-${kind}`}>
                <RotateCcw className="mr-2 h-4 w-4" /> Mulai Ulang
              </Button>
            )}
          </div>

          {analysis && (
            <>
              <Separator />
              <div className="space-y-3">
                <p className="text-[13px] font-medium text-foreground">
                  Pemetaan Kolom ({analysis.total_rows} baris terbaca)
                </p>
                <div className="grid gap-3 sm:grid-cols-2">
                  {(analysis.fields || []).map((field) => (
                    <div key={field.key} className="space-y-1.5">
                      <Label className="text-[13px] font-medium">
                        {field.label}
                        {field.required && <span className="ml-0.5 text-destructive">*</span>}
                      </Label>
                      <Select
                        value={mapping[field.key] || "__empty__"}
                        onValueChange={(v) =>
                          setMapping((s) => {
                            const next = { ...s };
                            if (v === "__empty__") delete next[field.key];
                            else next[field.key] = v;
                            return next;
                          })
                        }
                      >
                        <SelectTrigger data-testid={`import-map-${kind}-${field.key}`}>
                          <SelectValue placeholder="Pilih kolom Excel…" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__empty__">— Tidak dipetakan —</SelectItem>
                          {(analysis.headers || []).map((h) => (
                            <SelectItem key={h} value={h}>
                              {h}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  ))}
                </div>

                <div className="flex items-center gap-2 rounded-md border border-border bg-muted/40 px-3 py-2">
                  <Switch
                    id={`overwrite-${kind}`}
                    checked={overwrite}
                    onCheckedChange={setOverwrite}
                    data-testid={`import-overwrite-${kind}`}
                  />
                  <Label htmlFor={`overwrite-${kind}`} className="text-[13px]">
                    Perbarui data yang sudah ada (tanpa ini, baris duplikat akan dilewati)
                  </Label>
                </div>

                <Button onClick={runPreview} disabled={busy === "preview"} data-testid={`import-preview-${kind}`}>
                  {busy === "preview" ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Upload className="mr-2 h-4 w-4" />
                  )}
                  Pratinjau Validasi
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {preview && !result && (
        <Card data-testid={`import-preview-result-${kind}`}>
          <CardHeader>
            <CardTitle className="text-base">Hasil Pratinjau</CardTitle>
            <CardDescription>Tidak ada data yang disimpan pada tahap ini.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline">{summary.total_rows || 0} baris terbaca</Badge>
              <Badge variant="outline" className="border-success-border bg-success-soft text-success">
                {okRows.length} siap disimpan
              </Badge>
              {skippedRows.length > 0 && (
                <Badge variant="outline" className="border-warning-border bg-warning-soft text-warning">
                  {skippedRows.length} dilewati
                </Badge>
              )}
              {errorRows.length > 0 && (
                <Badge variant="outline" className="border-danger-border bg-danger-soft text-danger">
                  {errorRows.length} bermasalah
                </Badge>
              )}
            </div>

            {errorRows.length > 0 && (
              <TableCard>
                <DataTable
                  columns={[
                    { key: "row", header: "Baris", align: "right" },
                    { key: "employee_number", header: "Nomor Karyawan" },
                    { key: "work_date", header: "Tanggal" },
                    {
                      key: "errors",
                      header: "Masalah",
                      render: (r) => <span className="text-destructive">{(r.errors || []).join("; ")}</span>,
                    },
                  ]}
                  rows={errorRows}
                  rowKey={(r) => `err-${r.row}`}
                  testId={`import-errors-${kind}`}
                  emptyProps={{ title: "Tidak ada baris bermasalah." }}
                />
              </TableCard>
            )}

            {okRows.length > 0 && (
              <TableCard>
                <DataTable
                  columns={[
                    { key: "row", header: "Baris", align: "right" },
                    { key: "employee_number", header: "Nomor Karyawan" },
                    { key: "employee_name", header: "Nama" },
                    { key: "work_date", header: "Tanggal" },
                    {
                      key: "action",
                      header: "Tindakan",
                      render: (r) => (r.action === "update" ? "Perbarui" : "Buat baru"),
                    },
                  ]}
                  rows={okRows.slice(0, 100)}
                  rowKey={(r) => `ok-${r.row}`}
                  testId={`import-ok-${kind}`}
                  emptyProps={{ title: "Tidak ada baris siap simpan." }}
                />
              </TableCard>
            )}

            <div className="flex flex-wrap items-center justify-end gap-2">
              {errorRows.length > 0 && (
                <p className="mr-auto flex items-center gap-2 text-[12px] text-muted-foreground">
                  <AlertTriangle className="h-3.5 w-3.5" /> Baris bermasalah tidak akan disimpan.
                </p>
              )}
              <Button onClick={commit} disabled={!okRows.length || busy === "commit"} data-testid={`import-commit-${kind}`}>
                {busy === "commit" ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <FileSpreadsheet className="mr-2 h-4 w-4" />
                )}
                Simpan {okRows.length} baris
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {result && (
        <Card data-testid={`import-result-${kind}`}>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <CheckCircle2 className="h-4 w-4 text-success" /> Impor Selesai
            </CardTitle>
            <CardDescription>{result.message}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline" className="border-success-border bg-success-soft text-success">
                {result.summary?.created_rows || 0} dibuat
              </Badge>
              <Badge variant="outline">{result.summary?.updated_rows || 0} diperbarui</Badge>
              <Badge variant="outline">{result.summary?.skipped_rows || 0} dilewati</Badge>
              {(result.summary?.error_rows || 0) > 0 && (
                <Badge variant="outline" className="border-danger-border bg-danger-soft text-danger">
                  {result.summary.error_rows} gagal
                </Badge>
              )}
            </div>
            <Button variant="outline" onClick={reset} data-testid={`import-again-${kind}`}>
              <RotateCcw className="mr-2 h-4 w-4" /> Impor Berkas Lain
            </Button>
          </CardContent>
        </Card>
      )}

      <SectionHeader title="Riwayat Impor" description="Setiap batch impor tercatat agar dapat ditelusuri." />
      <TableCard>
        <DataTable
          columns={[
            { key: "filename", header: "Berkas" },
            { key: "imported_by_name", header: "Oleh", hideOnMobile: true },
            { key: "imported_at", header: "Waktu", render: (r) => formatDateTime(r.imported_at) },
            { key: "total_rows", header: "Baris", align: "right" },
            { key: "success_rows", header: "Dibuat", align: "right" },
            { key: "updated_rows", header: "Diperbarui", align: "right" },
            { key: "error_rows", header: "Gagal", align: "right" },
          ]}
          rows={batches}
          testId={`import-history-${kind}`}
          emptyProps={{ title: "Belum ada riwayat impor.", description: "Riwayat akan muncul setelah impor pertama." }}
        />
      </TableCard>
    </div>
  );
};

const TimeImportPage = () => (
  <PageBody>
    <Tabs defaultValue="attendance">
      <TabsList data-testid="import-kind-tabs">
        <TabsTrigger value="attendance" data-testid="import-tab-attendance">
          Impor Absensi
        </TabsTrigger>
        <TabsTrigger value="schedule" data-testid="import-tab-schedule">
          Impor Jadwal
        </TabsTrigger>
      </TabsList>
      <TabsContent value="attendance" className="mt-4">
        <ImportWizard kind="attendance" />
      </TabsContent>
      <TabsContent value="schedule" className="mt-4">
        <ImportWizard kind="schedule" />
      </TabsContent>
    </Tabs>
  </PageBody>
);

export default TimeImportPage;
