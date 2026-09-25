import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  AlertTriangle, ArrowLeft, CheckCircle2, Download, Eye, FileSpreadsheet, History, Loader2, RefreshCw, Search, Upload, XCircle,
} from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { downloadFile } from "@/lib/download";
import { useAuth } from "@/lib/auth";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";

const LONG = { timeout: 900000 };
const CLASS_META = {
  NEW: { label: "BARU", cls: "border-emerald-200 bg-emerald-50 text-emerald-800" },
  UPDATE: { label: "UPDATE", cls: "border-sky-200 bg-sky-50 text-sky-800" },
  UNCHANGED: { label: "TIDAK BERUBAH", cls: "border-slate-200 bg-slate-50 text-slate-700" },
  CONFLICT: { label: "KONFLIK", cls: "border-amber-300 bg-amber-50 text-amber-900" },
  ERROR: { label: "ERROR", cls: "border-rose-200 bg-rose-50 text-rose-800" },
};
const COMMIT_META = {
  PENDING: { label: "Menunggu commit", cls: "border-slate-200 bg-white text-slate-700" },
  COMMITTED: { label: "Tersimpan", cls: "border-emerald-200 bg-emerald-50 text-emerald-800" },
  FAILED: { label: "Gagal", cls: "border-rose-200 bg-rose-50 text-rose-800" },
  SKIPPED: { label: "Dilewati", cls: "border-slate-200 bg-slate-50 text-slate-600" },
};
const BATCH_META = {
  ANALYZED: { label: "Sudah dianalisis — belum disimpan", cls: "border-sky-200 bg-sky-50 text-sky-800" },
  COMMITTING: { label: "Sedang disimpan", cls: "border-amber-200 bg-amber-50 text-amber-900" },
  COMMITTED: { label: "Tersimpan semua", cls: "border-emerald-200 bg-emerald-50 text-emerald-800" },
  PARTIAL: { label: "Tersimpan sebagian", cls: "border-amber-300 bg-amber-50 text-amber-900" },
  FAILED: { label: "Gagal disimpan", cls: "border-rose-200 bg-rose-50 text-rose-800" },
  CANCELLED: { label: "Dibatalkan", cls: "border-slate-200 bg-slate-50 text-slate-600" },
};
const COUNTS = [
  ["NEW", "count_new"], ["UPDATE", "count_update"], ["UNCHANGED", "count_unchanged"],
  ["CONFLICT", "count_conflict"], ["ERROR", "count_error"],
];
const errMsg = (e) => {
  const d = e?.response?.data?.detail;
  if (d && typeof d === "object" && !Array.isArray(d) && d.message) return d.message;
  return errorMessage(e);
};
const fmt = (v) => (v ? new Date(v.endsWith?.("Z") || v.includes?.("+") ? v : `${v}Z`).toLocaleString("id-ID") : "-");

const Pill = ({ meta, testid }) => (
  <Badge variant="outline" className={`whitespace-nowrap ${meta?.cls || ""}`} data-testid={testid}>{meta?.label || "-"}</Badge>
);

const STEPS = ["Unduh template", "Unggah file", "Analisis & validasi", "Periksa preview", "Commit"];
const Stepper = ({ current }) => (
  <ol className="flex flex-wrap gap-2" data-testid="migration-stepper">
    {STEPS.map((s, i) => (
      <li key={s} className={`flex items-center gap-2 rounded-full border px-3 py-1 text-xs ${
        i < current ? "border-emerald-200 bg-emerald-50 text-emerald-800" : i === current
          ? "border-primary bg-primary text-primary-foreground" : "border-border text-muted-foreground"}`}>
        {i < current ? <CheckCircle2 className="h-3.5 w-3.5" /> : <span className="font-semibold">{i + 1}</span>}{s}
      </li>
    ))}
  </ol>
);

const Issues = ({ items, tone }) => (items?.length ? (
  <ul className={`space-y-0.5 text-xs ${tone}`}>
    {items.slice(0, 4).map((e, i) => (
      <li key={i}>{e.sheet ? <span className="font-medium">{e.sheet}{e.row ? ` baris ${e.row}` : ""}: </span> : null}{e.message}</li>
    ))}
    {items.length > 4 && <li className="text-muted-foreground">+{items.length - 4} lainnya (lihat file hasil validasi)</li>}
  </ul>
) : null);

function BatchDetail({ batchId, file, onChanged, onStatus, readOnly = false }) {
  const [batch, setBatch] = useState(null);
  const [rows, setRows] = useState({ items: [], total: 0 });
  const [filter, setFilter] = useState("ALL");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [confirm, setConfirm] = useState(false);
  const [ackDup, setAckDup] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [commitFile, setCommitFile] = useState(file || null);
  const [dupFromServer, setDupFromServer] = useState(false);
  const fileRef = useRef(null);
  const limit = 25;

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const params = { page, limit };
      if (filter !== "ALL") params.row_class = filter;
      if (q.trim()) params.q = q.trim();
      const [b, r] = await Promise.all([
        api.get(`/employee-import/batches/${batchId}`),
        api.get(`/employee-import/batches/${batchId}/rows`, { params }),
      ]);
      setBatch(b.data.batch); setRows(r.data); onStatus?.(b.data.batch.batch_status);
    } catch (e) { setError(errMsg(e)); } finally { setLoading(false); }
  }, [batchId, filter, q, page]);
  useEffect(() => { load(); }, [load]);

  const doCommit = async () => {
    setCommitting(true);
    try {
      const fd = new FormData();
      fd.append("file", commitFile);
      fd.append("confirm_duplicate", ackDup ? "true" : "false");
      const { data } = await api.post(`/employee-import/batches/${batchId}/commit`, fd, LONG);
      toast.success(data.summary);
      setConfirm(false); setFilter("ALL"); setPage(1);
      await load(); onChanged?.();
    } catch (e) {
      if (e?.response?.status === 409 && e?.response?.data?.detail?.duplicate_of_batch_id) { setDupFromServer(true); setAckDup(false); }
      toast.error(errMsg(e));
    } finally { setCommitting(false); }
  };

  if (loading && !batch) return <Skeleton className="h-64 w-full" data-testid="batch-detail-loading" />;
  if (error && !batch) return (
    <Card data-testid="batch-detail-error"><CardContent className="flex items-center justify-between gap-3 p-6 text-sm">
      <span className="text-rose-700">{error}</span><Button variant="outline" onClick={load} data-testid="batch-detail-retry">Coba lagi</Button></CardContent></Card>
  );
  const isDup = (w) => w.includes("pernah di-commit");
  const dupWarning = (batch.warnings || []).find(isDup) || (dupFromServer
    ? "File yang sama persis sudah pernah di-commit pada batch lain. Commit ulang memerlukan konfirmasi eksplisit." : null);
  const otherWarnings = (batch.warnings || []).filter((w) => !isDup(w));
  const canCommit = !readOnly && batch.batch_status === "ANALYZED" && (batch.count_new + batch.count_update) > 0;
  const pages = Math.max(1, Math.ceil((rows.total || 0) / limit));

  return (
    <div className="space-y-4" data-testid="batch-detail">
      <Card>
        <CardHeader className="gap-2">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <CardTitle className="truncate text-base" data-testid="batch-number">{batch.batch_number}</CardTitle>
              <CardDescription className="break-all">{batch.file_name} · diunggah {fmt(batch.analyzed_at)} oleh {batch.uploaded_by_name || "-"}</CardDescription>
            </div>
            <Pill meta={BATCH_META[batch.batch_status]} testid="batch-status-badge" />
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            <button type="button" onClick={() => { setFilter("ALL"); setPage(1); }} data-testid="count-ALL"
              className={`rounded-lg border p-3 text-left transition-colors ${filter === "ALL" ? "ring-2 ring-primary" : "hover:bg-secondary"}`}>
              <div className="text-xs text-muted-foreground">Total karyawan</div>
              <div className="text-xl font-semibold">{batch.total_employees}</div>
            </button>
            {COUNTS.map(([k, f]) => (
              <button type="button" key={k} onClick={() => { setFilter(k); setPage(1); }} data-testid={`count-${k}`}
                className={`rounded-lg border p-3 text-left transition-colors ${CLASS_META[k].cls} ${filter === k ? "ring-2 ring-primary" : "hover:opacity-80"}`}>
                <div className="text-xs">{CLASS_META[k].label}</div>
                <div className="text-xl font-semibold">{batch[f]}</div>
              </button>
            ))}
          </div>
          {["COMMITTED", "PARTIAL", "FAILED"].includes(batch.batch_status) && (
            <div className="rounded-lg border bg-secondary/40 p-3 text-sm" data-testid="commit-result">
              Hasil commit {fmt(batch.committed_at)}: <b>{batch.committed_count}</b> tersimpan, <b>{batch.failed_count}</b> gagal,{" "}
              <b>{batch.skipped_count}</b> dilewati (tidak berubah / konflik / error).
            </div>
          )}
          {readOnly && (
            <div className="flex items-center gap-2 rounded-lg border bg-secondary/40 p-3 text-sm text-muted-foreground" data-testid="batch-readonly-note">
              <Eye className="h-4 w-4 shrink-0" />Mode baca saja: detail batch dari riwayat tidak dapat di-commit atau diubah.
              {batch.batch_status === "ANALYZED" && " Untuk menyimpan data, unggah ulang file pada tab Impor & Migrasi."}
            </div>
          )}
          {dupWarning && (
            <div className="flex gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900" role="alert" data-testid="duplicate-hash-warning">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <div><p className="font-medium">File ini sudah pernah di-commit sebelumnya.</p><p>{dupWarning}</p></div>
            </div>
          )}
          {otherWarnings.map((w) => (
            <div key={w} className="flex gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900" data-testid="batch-warning">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{w}
            </div>
          ))}
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" data-testid="download-validation-result"
              onClick={() => downloadFile(`/employee-import/batches/${batchId}/validation-result`, "Hasil-Validasi.xlsx")
                .catch((e) => toast.error(errMsg(e)))}>
              <Download className="mr-1.5 h-4 w-4" /> Unduh hasil validasi
            </Button>
            {canCommit && (
              <Button onClick={() => { setAckDup(false); setConfirm(true); }} data-testid="open-commit-dialog">
                <CheckCircle2 className="mr-1.5 h-4 w-4" /> Commit {batch.count_new + batch.count_update} karyawan
              </Button>
            )}
            {!readOnly && batch.batch_status === "ANALYZED" && (
              <Button variant="ghost" data-testid="cancel-batch" onClick={async () => {
                try { await api.post(`/employee-import/batches/${batchId}/cancel`); toast.success("Batch dibatalkan."); load(); onChanged?.(); }
                catch (e) { toast.error(errMsg(e)); }
              }}>Batalkan batch</Button>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="text-base">Preview per karyawan</CardTitle>
          <div className="relative w-full sm:w-72">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input className="pl-8" placeholder="Cari nomor / nama" value={q} data-testid="preview-search"
              onChange={(e) => { setQ(e.target.value); setPage(1); }} />
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table className="min-w-[860px]">
              <TableHeader><TableRow>
                <TableHead>Nomor</TableHead><TableHead>Nama</TableHead><TableHead>Klasifikasi</TableHead>
                <TableHead className="w-[34%]">Perubahan</TableHead><TableHead className="w-[26%]">Konflik / Error / Warning</TableHead>
                <TableHead>Status commit</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {loading ? Array.from({ length: 4 }).map((_, i) => (
                  <TableRow key={i}><TableCell colSpan={6}><Skeleton className="h-6 w-full" /></TableCell></TableRow>
                )) : rows.items.length === 0 ? (
                  <TableRow><TableCell colSpan={6} className="py-10 text-center text-sm text-muted-foreground" data-testid="preview-empty">
                    Tidak ada baris untuk filter ini.</TableCell></TableRow>
                ) : rows.items.map((r) => (
                  <TableRow key={r.id} data-testid={`preview-row-${r.seq}`} className="align-top">
                    <TableCell className="whitespace-nowrap font-mono text-xs">{r.employee_number}</TableCell>
                    <TableCell className="min-w-[140px]">{r.full_name || "-"}</TableCell>
                    <TableCell><Pill meta={CLASS_META[r.row_class]} testid={`row-class-${r.seq}`} /></TableCell>
                    <TableCell>
                      {r.changes?.length ? (
                        <ul className="space-y-0.5 text-xs">
                          {r.changes.slice(0, 6).map((c, i) => (
                            <li key={i}><span className="font-medium">{c.label}:</span>{" "}
                              {c.old !== null && c.old !== undefined && <span className="text-muted-foreground line-through">{String(c.old)}</span>}
                              {c.old !== null && c.old !== undefined && " → "}<span>{String(c.new ?? "-")}</span></li>
                          ))}
                          {r.changes.length > 6 && <li className="text-muted-foreground">+{r.changes.length - 6} perubahan lain</li>}
                        </ul>
                      ) : <span className="text-xs text-muted-foreground">—</span>}
                    </TableCell>
                    <TableCell className="space-y-1">
                      <Issues items={r.errors} tone="text-rose-700" />
                      <Issues items={r.warnings} tone="text-amber-800" />
                      {r.commit_error && <p className="text-xs text-rose-700">Commit: {r.commit_error}</p>}
                      {!r.errors?.length && !r.warnings?.length && !r.commit_error && <span className="text-xs text-muted-foreground">—</span>}
                    </TableCell>
                    <TableCell><Pill meta={COMMIT_META[r.commit_status]} testid={`row-commit-${r.seq}`} /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="flex items-center justify-between gap-2 border-t p-3 text-sm">
            <span className="text-muted-foreground" data-testid="preview-total">{rows.total} baris · halaman {page}/{pages}</span>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)} data-testid="preview-prev">Sebelumnya</Button>
              <Button size="sm" variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)} data-testid="preview-next">Berikutnya</Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <AlertDialog open={confirm} onOpenChange={(o) => !committing && setConfirm(o)}>
        <AlertDialogContent className="max-h-[90vh] overflow-y-auto" data-testid="commit-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Simpan hasil impor ke data karyawan?</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2 text-sm">
                <p><b>{batch.count_new}</b> karyawan baru dan <b>{batch.count_update}</b> karyawan diperbarui akan disimpan.
                  {" "}{batch.count_conflict + batch.count_error + batch.count_unchanged} baris lain (konflik / error / tidak berubah) dilewati.</p>
                <p>Setiap karyawan disimpan terpisah: bila satu gagal, hanya karyawan itu yang dibatalkan. Sel kosong tidak menghapus data lama.</p>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          {(batch.count_conflict + batch.count_error) > 0 && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900" data-testid="commit-dialog-skip-warning">
              {batch.count_conflict} konflik dan {batch.count_error} error TIDAK akan disimpan. Unduh hasil validasi untuk memperbaikinya.
            </div>
          )}
          <div className="space-y-2 rounded-lg border p-3 text-sm">
            <p>File asli tidak disimpan sistem. Pilih kembali <b>file yang sama</b> untuk konfirmasi.</p>
            <input ref={fileRef} type="file" accept=".xlsx,.xlsm" className="hidden" data-testid="commit-file-input"
              onChange={(e) => setCommitFile(e.target.files?.[0] || null)} />
            <Button type="button" size="sm" variant="outline" onClick={() => fileRef.current?.click()} data-testid="commit-choose-file">
              <FileSpreadsheet className="mr-1.5 h-4 w-4" /> {commitFile ? commitFile.name : "Pilih file"}
            </Button>
          </div>
          {dupWarning && (
            <label className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900" data-testid="commit-dup-ack">
              <Checkbox checked={ackDup} onCheckedChange={(v) => setAckDup(Boolean(v))} className="mt-0.5" />
              File ini pernah di-commit sebelumnya. Saya memahami dan tetap ingin memproses ulang.
            </label>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={committing} data-testid="commit-cancel">Batal</AlertDialogCancel>
            <AlertDialogAction disabled={committing || !commitFile || (dupWarning && !ackDup)} data-testid="commit-confirm"
              onClick={(e) => { e.preventDefault(); doCommit(); }}>
              {committing ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}Ya, commit sekarang
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function HistoryTab({ onOpen, refreshKey }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(1);
  const load = useCallback(async () => {
    setError(null);
    try { setData((await api.get("/employee-import/batches", { params: { page, limit: 15 } })).data); }
    catch (e) { setError(errMsg(e)); }
  }, [page]);
  useEffect(() => { load(); }, [load, refreshKey]);
  if (error) return <Card data-testid="history-error"><CardContent className="flex justify-between gap-3 p-6 text-sm">
    <span className="text-rose-700">{error}</span><Button variant="outline" onClick={load} data-testid="history-retry">Coba lagi</Button></CardContent></Card>;
  if (!data) return <Skeleton className="h-48 w-full" data-testid="history-loading" />;
  const pages = Math.max(1, Math.ceil(data.total / 15));
  return (
    <Card data-testid="history-table">
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <Table className="min-w-[980px]">
            <TableHeader><TableRow>
              <TableHead>File</TableHead><TableHead>Diunggah</TableHead><TableHead>Status</TableHead><TableHead className="text-right">Total</TableHead>
              {COUNTS.map(([k]) => <TableHead key={k} className="text-right">{CLASS_META[k].label}</TableHead>)}
              <TableHead>Commit</TableHead><TableHead />
            </TableRow></TableHeader>
            <TableBody>
              {data.items.length === 0 ? (
                <TableRow><TableCell colSpan={11} className="py-10 text-center text-sm text-muted-foreground" data-testid="history-empty">
                  Belum ada riwayat impor.</TableCell></TableRow>
              ) : data.items.map((b) => (
                <TableRow key={b.id} data-testid={`history-row-${b.id}`}>
                  <TableCell className="max-w-[220px]"><div className="truncate font-medium">{b.file_name}</div>
                    <div className="font-mono text-xs text-muted-foreground">{b.batch_number}</div></TableCell>
                  <TableCell className="whitespace-nowrap text-xs">{fmt(b.analyzed_at)}<div className="text-muted-foreground">{b.uploaded_by_name || "-"}</div></TableCell>
                  <TableCell><Pill meta={BATCH_META[b.batch_status]} testid={`history-status-${b.id}`} />
                    {b.duplicate_of_batch_id && <div className="mt-1 text-xs text-rose-700">File duplikat</div>}</TableCell>
                  <TableCell className="text-right">{b.total_employees}</TableCell>
                  {COUNTS.map(([k, f]) => <TableCell key={k} className="text-right">{b[f]}</TableCell>)}
                  <TableCell className="whitespace-nowrap text-xs">{b.committed_at ? <>{fmt(b.committed_at)}<div className="text-muted-foreground">
                    {b.committed_count} ok · {b.failed_count} gagal</div></> : "-"}</TableCell>
                  <TableCell><Button size="sm" variant="outline" onClick={() => onOpen(b.id)} data-testid={`history-open-${b.id}`}>
                    <Eye className="mr-1 h-4 w-4" />Detail</Button></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        <div className="flex items-center justify-between border-t p-3 text-sm">
          <span className="text-muted-foreground" data-testid="history-total">{data.total} batch</span>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)} data-testid="history-prev">Sebelumnya</Button>
            <Button size="sm" variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)} data-testid="history-next">Berikutnya</Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function EmployeeMigrationPage() {
  const navigate = useNavigate();
  const { can } = useAuth();
  const [tab, setTab] = useState("import");
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [batchId, setBatchId] = useState(null);
  const [historyBatch, setHistoryBatch] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [downloaded, setDownloaded] = useState(false);
  const [batchStatus, setBatchStatus] = useState(null);
  const inputRef = useRef(null);

  if (!can("employee", "import")) {
    return <PageBody><Card data-testid="migration-forbidden"><CardContent className="p-6 text-sm">
      Anda tidak memiliki hak akses <b>Impor Massal Data Karyawan</b>. Hubungi Tenant Admin / HR Admin.</CardContent></Card></PageBody>;
  }

  const analyze = async () => {
    if (!file) return;
    setUploading(true); setUploadError(null);
    try {
      const fd = new FormData(); fd.append("file", file);
      const { data } = await api.post("/employee-import/batches", fd, LONG);
      setBatchStatus(null); setBatchId(data.batch.id); setRefreshKey((k) => k + 1);
      if (data.duplicate_committed_batch) toast.warning("File ini pernah di-commit sebelumnya. Periksa peringatan sebelum commit.");
      else toast.success("Analisis selesai. Periksa preview sebelum commit.");
    } catch (e) {
      const d = e?.response?.data?.detail;
      setUploadError(d?.header_errors ? [d.message, ...d.header_errors] : [errMsg(e)]);
    } finally { setUploading(false); }
  };
  const done = ["COMMITTED", "PARTIAL", "FAILED"].includes(batchStatus);
  const step = done ? 5 : batchId ? 3 : file ? 2 : downloaded ? 1 : 0;

  return (
    <>
      <PageHeader title="Impor & Migrasi Data Karyawan" subtitle="Migrasi data karyawan dari Excel 6 sheet: analisis dulu, periksa, lalu commit."
        actions={<div className="flex flex-wrap items-center gap-2">
          {can("employee", "create") && (
            <Button variant="ghost" onClick={() => navigate("/employees/import")} data-testid="migration-legacy-import">
              Impor sederhana (format lama)</Button>
          )}
          <Button variant="outline" onClick={() => navigate("/employees")} data-testid="migration-back">
            <ArrowLeft className="mr-1.5 h-4 w-4" /> Data Karyawan</Button>
        </div>} />
      <PageBody>
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList data-testid="migration-tabs">
            <TabsTrigger value="import" data-testid="tab-import"><Upload className="mr-1.5 h-4 w-4" />Impor & Migrasi</TabsTrigger>
            <TabsTrigger value="history" data-testid="tab-history"><History className="mr-1.5 h-4 w-4" />Riwayat Impor</TabsTrigger>
          </TabsList>
          <TabsContent value="import" className="mt-4 space-y-4">
            <Stepper current={step} />
            <Card>
              <CardHeader>
                <CardTitle className="text-base">1–3. Template, unggah, analisis</CardTitle>
                <CardDescription>Sheet: PETUNJUK, DATA_KARYAWAN, KEPEGAWAIAN, BANK_BPJS, KELUARGA, MASTER_REFERENCE. Nomor Karyawan menjadi kunci lintas sheet.
                  Analisis belum mengubah data karyawan.</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
                <Button variant="outline" data-testid="download-template" onClick={() =>
                  downloadFile("/employee-import/template", "Template-Migrasi-Karyawan-01E.xlsx").then(() => setDownloaded(true))
                    .catch((e) => toast.error(errMsg(e)))}>
                  <Download className="mr-1.5 h-4 w-4" /> Unduh template
                </Button>
                <input ref={inputRef} type="file" accept=".xlsx,.xlsm" className="hidden" data-testid="upload-file-input"
                  onChange={(e) => { setFile(e.target.files?.[0] || null); setBatchId(null); setBatchStatus(null); setUploadError(null); e.target.value = ""; }} />
                <Button variant="outline" onClick={() => inputRef.current?.click()} data-testid="choose-file" className="max-w-full">
                  <FileSpreadsheet className="mr-1.5 h-4 w-4 shrink-0" /><span className="truncate">{file ? file.name : "Pilih file Excel"}</span>
                </Button>
                <Button disabled={!file || uploading} onClick={analyze} data-testid="analyze-button">
                  {uploading ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-1.5 h-4 w-4" />}
                  {uploading ? "Menganalisis…" : "Analisis & validasi"}
                </Button>
              </CardContent>
              {uploadError && (
                <CardContent className="pt-0">
                  <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800" data-testid="upload-error">
                    <div className="flex items-center gap-2 font-medium"><XCircle className="h-4 w-4" />{uploadError[0]}</div>
                    {uploadError.length > 1 && <ul className="ml-6 mt-1 list-disc">{uploadError.slice(1).map((m) => <li key={m}>{m}</li>)}</ul>}
                  </div>
                </CardContent>
              )}
            </Card>
            {batchId ? <BatchDetail key={batchId} batchId={batchId} file={file} onStatus={setBatchStatus} onChanged={() => setRefreshKey((k) => k + 1)} /> : (
              <Card data-testid="import-empty"><CardContent className="p-6 text-sm text-muted-foreground">
                Belum ada file yang dianalisis. Unduh template, isi data, lalu unggah untuk melihat preview.</CardContent></Card>
            )}
          </TabsContent>
          <TabsContent value="history" className="mt-4 space-y-4">
            {historyBatch ? (
              <>
                <Button variant="ghost" onClick={() => setHistoryBatch(null)} data-testid="history-back"><ArrowLeft className="mr-1.5 h-4 w-4" />Kembali ke riwayat</Button>
                <BatchDetail key={historyBatch} batchId={historyBatch} readOnly />
              </>
            ) : <HistoryTab onOpen={setHistoryBatch} refreshKey={refreshKey} />}
          </TabsContent>
        </Tabs>
      </PageBody>
    </>
  );
}
