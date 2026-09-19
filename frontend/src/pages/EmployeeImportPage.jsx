import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  Loader2,
  RotateCcw,
  Upload,
  Users,
} from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { downloadFile } from "@/lib/download";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const STEPS = [
  { key: 1, label: "Unduh template" },
  { key: 2, label: "Unggah & validasi" },
  { key: 3, label: "Periksa hasil" },
  { key: 4, label: "Simpan data" },
];

const Stepper = ({ current }) => (
  <ol className="flex flex-wrap items-center gap-2" data-testid="import-stepper">
    {STEPS.map((step, index) => {
      const state = current > step.key ? "done" : current === step.key ? "active" : "todo";
      return (
        <li key={step.key} className="flex items-center gap-2">
          <span
            className={`flex h-7 w-7 items-center justify-center rounded-full border text-xs font-semibold ${
              state === "done"
                ? "border-emerald-200 bg-emerald-100 text-emerald-800"
                : state === "active"
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border bg-secondary text-muted-foreground"
            }`}
          >
            {state === "done" ? <CheckCircle2 className="h-4 w-4" /> : step.key}
          </span>
          <span
            className={`text-sm ${
              state === "todo" ? "text-muted-foreground" : "font-medium text-foreground"
            }`}
          >
            {step.label}
          </span>
          {index < STEPS.length - 1 ? (
            <Separator className="hidden w-8 sm:block" orientation="horizontal" />
          ) : null}
        </li>
      );
    })}
  </ol>
);

const EmployeeImportPage = () => {
  const navigate = useNavigate();
  const fileRef = useRef(null);
  const [meta, setMeta] = useState(null);
  const [file, setFile] = useState(null);
  const [validating, setValidating] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [report, setReport] = useState(null);
  const [result, setResult] = useState(null);

  const loadMeta = useCallback(async () => {
    try {
      const { data } = await api.get("/employees/import/columns");
      setMeta(data);
    } catch (error) {
      toast.error(errorMessage(error, "Informasi template tidak dapat dimuat."));
    }
  }, []);

  useEffect(() => {
    loadMeta();
    document.title = "Impor Karyawan · HRIS Suite";
  }, [loadMeta]);

  const step = result ? 4 : report ? 3 : file ? 2 : 1;

  const validRows = useMemo(
    () => (report?.rows || []).filter((row) => row.is_valid),
    [report]
  );
  const invalidRows = useMemo(
    () => (report?.rows || []).filter((row) => !row.is_valid),
    [report]
  );

  const downloadTemplate = async () => {
    setDownloading(true);
    try {
      await downloadFile("/employees/import/template", "Template-Impor-Karyawan.xlsx");
      toast.success("Template Excel diunduh.");
    } catch (error) {
      toast.error(errorMessage(error, "Template tidak dapat diunduh."));
    } finally {
      setDownloading(false);
    }
  };

  const pickFile = (selected) => {
    setReport(null);
    setResult(null);
    setFile(selected || null);
  };

  const validate = async () => {
    if (!file) return;
    setValidating(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/employees/import/validate", fd);
      setReport(data);
      setResult(null);
      if (data?.invalid_count) {
        toast.warning(data.summary || "Sebagian baris perlu diperbaiki.");
      } else {
        toast.success(data?.summary || "Semua baris valid.");
      }
    } catch (error) {
      toast.error(errorMessage(error, "Berkas gagal divalidasi."));
    } finally {
      setValidating(false);
    }
  };

  const commit = async () => {
    setCommitting(true);
    try {
      const { data } = await api.post("/employees/import/commit", {
        rows: validRows.map((row) => ({ excel_row: row.excel_row, payload: row.payload })),
      });
      setResult(data);
      toast.success(data?.summary || `${data?.created_count || 0} karyawan berhasil diimpor.`);
    } catch (error) {
      toast.error(errorMessage(error, "Data gagal disimpan."));
    } finally {
      setCommitting(false);
    }
  };

  const reset = () => {
    setFile(null);
    setReport(null);
    setResult(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  return (
    <>
      <PageHeader
        title="Impor Karyawan dari Excel"
        subtitle="Unggah satu berkas untuk membuat banyak karyawan sekaligus, termasuk gaji pokok."
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={() => navigate("/employees")} data-testid="import-back">
              <ArrowLeft className="mr-2 h-4 w-4" /> Data karyawan
            </Button>
            <Button
              variant="outline"
              onClick={downloadTemplate}
              disabled={downloading}
              data-testid="import-download-template"
            >
              {downloading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Download className="mr-2 h-4 w-4" />
              )}
              Unduh template
            </Button>
          </div>
        }
      />
      <PageBody>
        <Stepper current={step} />

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Unggah berkas</CardTitle>
            <CardDescription>
              Format .xlsx atau .xlsm, maksimal {meta?.max_rows || 500} baris dan{" "}
              {meta?.max_size_mb || 5} MB. Kolom wajib ditandai bintang pada template.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <Input
                ref={fileRef}
                type="file"
                accept=".xlsx,.xlsm"
                onChange={(e) => pickFile(e.target.files?.[0])}
                className="sm:max-w-md"
                data-testid="import-file-input"
              />
              <Button onClick={validate} disabled={!file || validating} data-testid="import-validate">
                {validating ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Upload className="mr-2 h-4 w-4" />
                )}
                Validasi berkas
              </Button>
              {(file || report) && (
                <Button variant="ghost" onClick={reset} data-testid="import-reset">
                  <RotateCcw className="mr-2 h-4 w-4" /> Mulai ulang
                </Button>
              )}
            </div>
            {meta?.columns ? (
              <details className="rounded-lg border border-border bg-secondary/30 p-3 text-sm">
                <summary className="cursor-pointer font-medium">
                  Lihat {meta.columns.length} kolom template
                </summary>
                <ul className="mt-2 grid grid-cols-1 gap-1 text-xs text-muted-foreground sm:grid-cols-2">
                  {meta.columns.map((col) => (
                    <li key={col.field}>
                      <span className="font-medium text-foreground">{col.label}</span>
                      {col.required ? " (wajib)" : ""}
                      {col.hint ? ` — ${col.hint}` : ""}
                      {col.master ? ` · harus ada di master ${col.master}` : ""}
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
          </CardContent>
        </Card>

        {report && !result ? (
          <Card data-testid="import-report">
            <CardHeader>
              <CardTitle className="text-base">Hasil validasi</CardTitle>
              <CardDescription>{report.summary}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline" data-testid="import-total">
                  {report.total_rows} baris terbaca
                </Badge>
                <Badge
                  variant="outline"
                  className="border-emerald-200 bg-emerald-100 text-emerald-800"
                  data-testid="import-valid-count"
                >
                  {report.valid_count} siap diimpor
                </Badge>
                {report.invalid_count > 0 && (
                  <Badge
                    variant="outline"
                    className="border-red-200 bg-red-100 text-red-800"
                    data-testid="import-invalid-count"
                  >
                    {report.invalid_count} perlu diperbaiki
                  </Badge>
                )}
              </div>

              {invalidRows.length > 0 && (
                <div className="overflow-hidden rounded-lg border border-border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-20">Baris</TableHead>
                        <TableHead>Nama</TableHead>
                        <TableHead>Masalah</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {invalidRows.map((row) => (
                        <TableRow key={row.excel_row} data-testid={`import-invalid-${row.excel_row}`}>
                          <TableCell className="tabular-nums">{row.excel_row}</TableCell>
                          <TableCell>{row.full_name || "-"}</TableCell>
                          <TableCell className="text-sm text-destructive">
                            {row.errors.join("; ")}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}

              {validRows.length > 0 && (
                <div className="overflow-hidden rounded-lg border border-border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-20">Baris</TableHead>
                        <TableHead>Nama</TableHead>
                        <TableHead>NIK karyawan</TableHead>
                        <TableHead>Catatan</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {validRows.slice(0, 50).map((row) => (
                        <TableRow key={row.excel_row} data-testid={`import-valid-${row.excel_row}`}>
                          <TableCell className="tabular-nums">{row.excel_row}</TableCell>
                          <TableCell className="font-medium">{row.full_name}</TableCell>
                          <TableCell>{row.employee_number || "otomatis"}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {row.warnings?.length ? row.warnings.join("; ") : "-"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}

              <div className="flex flex-wrap items-center justify-end gap-2">
                {report.invalid_count > 0 && (
                  <p className="mr-auto flex items-center gap-2 text-xs text-muted-foreground">
                    <AlertTriangle className="h-3.5 w-3.5" /> Baris bermasalah akan dilewati.
                  </p>
                )}
                <Button
                  onClick={commit}
                  disabled={!report.can_commit || committing}
                  data-testid="import-commit"
                >
                  {committing ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <FileSpreadsheet className="mr-2 h-4 w-4" />
                  )}
                  Impor {validRows.length} karyawan
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : null}

        {result ? (
          <Card data-testid="import-result">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" /> Impor selesai
              </CardTitle>
              <CardDescription>{result.summary}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap gap-2">
                <Badge
                  variant="outline"
                  className="border-emerald-200 bg-emerald-100 text-emerald-800"
                  data-testid="import-created-count"
                >
                  {result.created_count} karyawan dibuat
                </Badge>
                {result.failed_count > 0 && (
                  <Badge variant="outline" className="border-red-200 bg-red-100 text-red-800">
                    {result.failed_count} gagal
                  </Badge>
                )}
              </div>
              {result.failed?.length > 0 && (
                <ul className="space-y-1 text-xs text-destructive">
                  {result.failed.map((row) => (
                    <li key={row.excel_row}>
                      Baris {row.excel_row} ({row.full_name || "-"}): {row.error}
                    </li>
                  ))}
                </ul>
              )}
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => navigate("/employees")} data-testid="import-goto-employees">
                  <Users className="mr-2 h-4 w-4" /> Lihat data karyawan
                </Button>
                <Button variant="outline" onClick={reset} data-testid="import-again">
                  <RotateCcw className="mr-2 h-4 w-4" /> Impor berkas lain
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : null}
      </PageBody>
    </>
  );
};

export default EmployeeImportPage;
