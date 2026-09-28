import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  CheckCircle2, ClipboardCheck, Download, FileSpreadsheet, History, Loader2, Plus, RefreshCw, Search, Send, Upload, XCircle,
} from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { PageBody, SectionHeader } from "@/components/common/PageHeader";
import { AssetDocumentsPanel } from "@/pages/asset/AssetDocumentsPanel";
import DataTable, { Pagination, TableCard } from "@/components/common/DataTable";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import EmptyState from "@/components/common/EmptyState";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  AssetItemCard, BADGE_TONE, BastPdfActions, DetailButton, EmployeeSearchField, InfoGrid, ItemField, SnapshotView, StateBadge,
  employeeLabel, todayIso,
} from "@/pages/asset/assetLifecycleShared";

// Phase 2A CP3 - Impor Master Aset + Saldo Awal (Opening Existing Holding).
// Alur impor: Upload -> Preview & Validasi (backend, batch) -> Konfirmasi -> Selesai. Commit hanya bila 0 ERROR.
// Saldo awal: DRAFT -> PUBLISHED (BAST-EXS), bukan penyerahan baru. Otorisasi murni permission efektif (tanpa nama role).

const NONE = "__none__";
const CLASS_META = { VALID: { label: "Valid", tone: "success" }, WARNING: { label: "Warning", tone: "warning" }, ERROR: { label: "Error", tone: "danger" } };
const STEPS = ["Upload", "Preview & Validasi", "Konfirmasi", "Selesai"];
const TYPE_LABEL = { MASTER: "Master Aset", OPENING: "Saldo Awal" };
const BATCH_STATE = { PREVIEWED: { label: "Preview", tone: "warning" }, COMMITTED: { label: "Selesai", tone: "success" }, CANCELLED: { label: "Dibatalkan", tone: "muted" } };

const ToneBadge = ({ meta, testId }) => (
  <Badge variant="outline" className={cn("whitespace-nowrap font-medium", BADGE_TONE[meta?.tone || "muted"])} data-testid={testId}>
    {meta?.label || "-"}
  </Badge>
);

const downloadBlob = async (url, params, fallbackName) => {
  const res = await api.get(url, { params, responseType: "blob" });
  const disp = res.headers?.["content-disposition"] || "";
  const name = (disp.match(/filename="([^"]+)"/) || [])[1] || fallbackName;
  const href = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = href;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
};

const Stepper = ({ step, testId }) => (
  <ol className="flex flex-wrap items-center gap-2" data-testid={testId} aria-label="Langkah impor">
    {STEPS.map((label, i) => {
      const n = i + 1;
      const state = n < step ? "done" : n === step ? "current" : "todo";
      return (
        <li key={label} className="flex items-center gap-2" aria-current={state === "current" ? "step" : undefined} data-testid={`${testId}-step-${n}`}>
          <span className={cn("flex h-7 w-7 items-center justify-center rounded-full border text-[12px] font-semibold",
            state === "done" && "border-success-border bg-success-soft text-success",
            state === "current" && "border-primary bg-primary text-primary-foreground",
            state === "todo" && "border-border bg-muted text-muted-foreground")}>
            {state === "done" ? <CheckCircle2 className="h-4 w-4" /> : n}
          </span>
          <span className={cn("text-[13px]", state === "current" ? "font-semibold text-foreground" : "text-muted-foreground")}>{label}</span>
          {n < STEPS.length && <span className="mx-1 hidden h-px w-6 bg-border sm:block" aria-hidden />}
        </li>
      );
    })}
  </ol>
);

const Stat = ({ label, value, tone, testId }) => (
  <div className={cn("rounded-lg border px-3 py-2", tone ? BADGE_TONE[tone] : "border-border bg-card")} data-testid={testId}>
    <p className="text-[12px] opacity-80">{label}</p>
    <p className="text-lg font-semibold tabular-nums">{value ?? 0}</p>
  </div>
);

const rowSummary = (type, d) => (type === "MASTER"
  ? [d.name || d.raw?.name, d.raw?.category, d.raw?.status, d.legacy_code && `Kode lama ${d.legacy_code}`, d.serial_number && `SN ${d.serial_number}`]
  : [d.employee_number && `${d.employee_number}${d.employee_name ? ` · ${d.employee_name}` : ""}`, d.asset_code || d.raw?.asset_code || d.raw?.legacy_code || d.raw?.serial_number, d.opening_date])
  .filter(Boolean).join(" · ");

const BatchRows = ({ batch, testId }) => {
  const [filter, setFilter] = useState("");
  const [rows, setRows] = useState([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const limit = 50;
  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.get(`/asset-imports/${batch.id}/rows`, { params: { page, limit, ...(filter ? { row_class: filter } : {}) } })
      .then((r) => { if (alive) { setRows(r.data.items); setTotal(r.data.total); } })
      .catch((e) => toast.error(errorMessage(e)))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [batch.id, filter, page]);
  const columns = [
    { key: "row_no", header: "Baris", render: (r) => <span className="tabular-nums">{r.row_no}</span> },
    { key: "row_class", header: "Hasil", render: (r) => <ToneBadge meta={CLASS_META[r.row_class]} testId={`${testId}-class-${r.row_no}`} /> },
    { key: "data", header: "Data", render: (r) => <span className="text-[13px]">{rowSummary(batch.import_type, r.data) || "-"}</span> },
    { key: "messages", header: "Keterangan", render: (r) => (r.messages?.length ? (
      <ul className="space-y-0.5 text-[12.5px]" data-testid={`${testId}-msg-${r.row_no}`}>
        {r.messages.map((m, i) => <li key={i} className={m.level === "ERROR" ? "text-danger" : "text-warning"}>{m.message}</li>)}
      </ul>) : <span className="text-[12.5px] text-muted-foreground">OK</span>) },
  ];
  return (
    <div className="space-y-2" data-testid={testId}>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter hasil validasi">
        {[["", "Semua", batch.total_rows], ["VALID", "Valid", batch.valid_rows], ["WARNING", "Warning", batch.warning_rows], ["ERROR", "Error", batch.error_rows]].map(([v, l, n]) => (
          <Button key={l} size="sm" variant={filter === v ? "default" : "outline"} onClick={() => { setFilter(v); setPage(1); }}
            aria-pressed={filter === v} data-testid={`${testId}-filter-${l.toLowerCase()}`}>{l} ({n ?? 0})</Button>
        ))}
      </div>
      <TableCard>
        <DataTable testId={`${testId}-table`} columns={columns} rows={rows.map((r) => ({ ...r, id: r.id }))} loading={loading}
          emptyProps={{ icon: FileSpreadsheet, title: "Tidak ada baris", description: "Tidak ada baris untuk filter ini." }} />
        <Pagination page={page} totalPages={Math.max(1, Math.ceil(total / limit))} total={total} limit={limit} onPageChange={setPage} onLimitChange={() => {}} />
      </TableCard>
    </div>
  );
};

const GroupSummary = ({ summary, testId }) => {
  const groups = summary?.groups || [];
  if (!summary?.employee_groups) return null;
  return (
    <div className="space-y-2 rounded-lg border border-border bg-card p-3" data-testid={testId}>
      <p className="text-sm font-medium" data-testid={`${testId}-count`}>
        Pengelompokan per karyawan: {summary.employee_groups} karyawan → {summary.employee_groups} dokumen BAST-EXS
      </p>
      <div className="max-h-48 overflow-auto">
        <table className="w-full min-w-[28rem] text-[13px]">
          <thead className="text-left text-[12px] text-muted-foreground">
            <tr><th className="py-1 pr-2 font-medium">Karyawan</th><th className="py-1 pr-2 font-medium">Tanggal Saldo Awal</th>
              <th className="py-1 pr-2 font-medium">Jumlah Aset</th><th className="py-1 font-medium">Baris Error</th></tr>
          </thead>
          <tbody>
            {groups.map((g) => (
              <tr key={g.employee_number} className="border-t border-border" data-testid={`${testId}-row-${g.employee_number}`}>
                <td className="py-1 pr-2">{g.employee_number}{g.employee_name ? ` · ${g.employee_name}` : ""}</td>
                <td className="py-1 pr-2">{g.opening_date ? formatDate(g.opening_date) : "-"}</td>
                <td className="py-1 pr-2 tabular-nums">{g.assets}</td>
                <td className={cn("py-1 tabular-nums", g.error_rows ? "text-danger" : "text-muted-foreground")}>{g.error_rows}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const ImportWizard = ({ type, can, onDone }) => {
  const [step, setStep] = useState(1);
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [batch, setBatch] = useState(null);
  const [result, setResult] = useState(null);
  const [mode, setMode] = useState("draft");
  const inputRef = useRef(null);
  const tid = type === "MASTER" ? "import-master" : "import-opening";
  const canCommit = can("asset_import", "commit") && (type === "MASTER" || can("asset_opening", "create"));
  const canPublish = can("asset_opening", "publish");
  const reset = () => { setStep(1); setFile(null); setBatch(null); setResult(null); setMode("draft"); if (inputRef.current) inputRef.current.value = ""; };

  const upload = async () => {
    if (!file) return toast.error("Pilih file .xlsx terlebih dahulu.");
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/asset-imports/preview", fd, { params: { import_type: type }, headers: { "Content-Type": "multipart/form-data" } });
      setBatch(data);
      setStep(2);
      toast.success(`Validasi selesai: ${data.total_rows} baris diperiksa.`);
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  const commit = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/asset-imports/${batch.id}/commit`, type === "OPENING" ? { mode } : {});
      setResult(data);
      setStep(4);
      toast.success(type === "MASTER" ? `${data.created_count} aset berhasil diimpor (${data.batch_number}).`
        : `${data.opening_count} saldo awal dibuat (${data.batch_number}).`);
      onDone?.();
    } catch (e) {
      toast.error(errorMessage(e));
      try { setBatch((await api.get(`/asset-imports/${batch.id}`)).data); } catch { /* biarkan */ }
      setStep(2);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4" data-testid={`${tid}-wizard`}>
      <Stepper step={step} testId={`${tid}-stepper`} />
      {step === 1 && (
        <div className="grid gap-4 rounded-lg border border-border bg-card p-4 md:grid-cols-[1fr_auto]">
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              {type === "MASTER"
                ? "Unduh template, isi data aset (Asset Code sistem dibuat otomatis), lalu upload. Aset yang sedang dipegang karyawan diimpor sebagai Siap Pakai, kemudian dicatat lewat Saldo Awal."
                : "Unduh template, isi Nomor Karyawan + identitas aset (Asset Code sistem, Kode Aset Lama, atau Serial Number). Baris karyawan yang sama menjadi satu dokumen BAST-EXS."}
            </p>
            <div className="space-y-1.5">
              <Label htmlFor={`${tid}-file`}>File Excel (.xlsx)</Label>
              <Input id={`${tid}-file`} ref={inputRef} type="file" accept=".xlsx" onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid={`${tid}-file-input`} />
            </div>
          </div>
          <div className="flex flex-col gap-2 md:w-56">
            <Button variant="outline" onClick={() => downloadBlob("/asset-imports/template", { import_type: type }, `template-${type === "OPENING" ? "saldo-awal" : "master"}-aset.xlsx`).catch((e) => toast.error(errorMessage(e)))}
              data-testid={`${tid}-template-button`}><Download className="mr-1.5 h-4 w-4" />Download Template</Button>
            <Button onClick={upload} disabled={busy || !file || !can("asset_import", "create")} data-testid={`${tid}-upload-button`}>
              {busy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Upload className="mr-1.5 h-4 w-4" />}Upload & Validasi
            </Button>
          </div>
        </div>
      )}
      {step >= 2 && step <= 3 && batch && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" data-testid={`${tid}-summary`}>
            <Stat label="Total baris" value={batch.total_rows} testId={`${tid}-stat-total`} />
            <Stat label="Valid" value={batch.valid_rows} tone="success" testId={`${tid}-stat-valid`} />
            <Stat label="Warning" value={batch.warning_rows} tone="warning" testId={`${tid}-stat-warning`} />
            <Stat label="Error" value={batch.error_rows} tone={batch.error_rows ? "danger" : undefined} testId={`${tid}-stat-error`} />
          </div>
          {batch.error_rows > 0 && (
            <Alert className="border-danger-border bg-danger-soft" data-testid={`${tid}-error-alert`}>
              <AlertDescription className="text-danger">
                Ada {batch.error_rows} baris ERROR. Perbaiki file lalu upload ulang - impor tidak dapat diproses sebagian.
              </AlertDescription>
            </Alert>
          )}
          {type === "OPENING" && <GroupSummary summary={batch.summary} testId={`${tid}-groups`} />}
          {step === 2 && <BatchRows batch={batch} testId={`${tid}-rows`} />}
          {step === 3 && (
            <div className="space-y-3 rounded-lg border border-border bg-card p-4" data-testid={`${tid}-confirm`}>
              <p className="text-sm">Batch <span className="font-semibold">{batch.batch_number}</span> · {batch.file_name} · {batch.total_rows} baris siap diproses.</p>
              {type === "OPENING" && (
                <RadioGroup value={mode} onValueChange={setMode} className="space-y-2" data-testid={`${tid}-mode`}>
                  <label className="flex items-start gap-2 text-sm"><RadioGroupItem value="draft" data-testid={`${tid}-mode-draft`} />
                    <span><span className="font-medium">Simpan sebagai Draft</span> - saldo awal dibuat DRAFT, aset belum berubah.</span></label>
                  {canPublish && (
                    <label className="flex items-start gap-2 text-sm"><RadioGroupItem value="publish" data-testid={`${tid}-mode-publish`} />
                      <span><span className="font-medium">Simpan & Publish</span> - aset menjadi Dipakai dan BAST-EXS terbit (satu transaksi).</span></label>
                  )}
                </RadioGroup>
              )}
              {!canCommit && <p className="text-[13px] text-muted-foreground" data-testid={`${tid}-commit-hint`}>Proses impor dilakukan oleh pengguna dengan izin proses impor.</p>}
            </div>
          )}
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="outline" onClick={reset} disabled={busy} data-testid={`${tid}-reupload-button`}><RefreshCw className="mr-1.5 h-4 w-4" />Upload Ulang</Button>
            {step === 2 && (
              <Button onClick={() => setStep(3)} disabled={!batch.can_commit} data-testid={`${tid}-next-button`}>Lanjut ke Konfirmasi</Button>
            )}
            {step === 3 && (
              <>
                <Button variant="outline" onClick={() => setStep(2)} disabled={busy} data-testid={`${tid}-back-button`}>Kembali</Button>
                <Button onClick={commit} disabled={busy || !canCommit} data-testid={`${tid}-commit-button`}>
                  {busy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <ClipboardCheck className="mr-1.5 h-4 w-4" />}
                  {type === "OPENING" && mode === "publish" ? "Proses & Publish" : "Proses Impor"}
                </Button>
              </>
            )}
          </div>
        </div>
      )}
      {step === 4 && result && (
        <div className="space-y-3 rounded-lg border border-success-border bg-success-soft p-4" data-testid={`${tid}-done`}>
          <p className="flex items-center gap-2 font-semibold text-success"><CheckCircle2 className="h-5 w-5" />Impor selesai · {result.batch_number}</p>
          <p className="text-sm" data-testid={`${tid}-done-count`}>
            {type === "MASTER" ? `${result.created_count} aset berhasil dibuat.` : `${result.opening_count} saldo awal dibuat${result.commit_mode === "PUBLISH" ? " dan diterbitkan" : " sebagai draft"}.`}
          </p>
          {(type === "MASTER" ? result.new_asset_codes : result.bast_numbers)?.length > 0 && (
            <div className="max-h-32 overflow-auto rounded border border-border bg-card p-2 text-[12.5px] tabular-nums" data-testid={`${tid}-done-codes`}>
              {(type === "MASTER" ? result.new_asset_codes : result.bast_numbers).join(", ")}
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => downloadBlob(`/asset-imports/${result.id}/result`, {}, `hasil-impor-${String(result.batch_number || "").replaceAll("/", "-")}.xlsx`).catch((e) => toast.error(errorMessage(e)))} data-testid={`${tid}-result-button`}>
              <Download className="mr-1.5 h-4 w-4" />Download Hasil Import
            </Button>
            <Button variant="outline" onClick={reset} data-testid={`${tid}-new-button`}>Impor File Lain</Button>
          </div>
        </div>
      )}
    </div>
  );
};

const emptyForm = (pic = "") => ({ employee_id: "", employee: null, opening_date: todayIso(), project_id: "", work_location_id: "", ga_pic_name: pic, manual_number: "", notes: "", items: [] });

const OpeningForm = ({ open, onOpenChange, options, editing, onSaved, can }) => {
  const [form, setForm] = useState(emptyForm());
  const [q, setQ] = useState("");
  const [found, setFound] = useState([]);
  const [searching, setSearching] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  useEffect(() => {
    if (!open) return;
    setQ("");
    setForm(editing ? { ...emptyForm(), ...editing, employee: { id: editing.employee_id, full_name: editing.employee_name, employee_number: editing.employee_number },
      items: (editing.items || []).map((i) => ({ asset_id: i.asset_id, asset_code: i.asset_code, asset_name: i.asset_name, condition_id: i.condition_id || "", accessories: i.accessories || "", item_notes: i.item_notes || "" })) } : emptyForm(options.ga_pic_name || ""));
  }, [open, editing, options.ga_pic_name]);
  useEffect(() => {
    if (!open) return undefined;
    const t = setTimeout(() => {
      setSearching(true);
      api.get("/asset-openings/asset-search", { params: { q, limit: 10 } }).then((r) => setFound(r.data.items)).catch(() => setFound([])).finally(() => setSearching(false));
    }, 300);
    return () => clearTimeout(t);
  }, [q, open]);
  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));
  const pickEmployee = async (e) => {
    setForm((f) => ({ ...f, employee_id: e?.id || "", employee: e }));
    if (!e) return;
    try {
      const { data } = await api.get("/asset-openings/employee-context", { params: { employee_id: e.id } });
      if (data.project_id) setForm((f) => ({ ...f, project_id: f.project_id || data.project_id }));
    } catch { /* default project opsional */ }
  };
  const addAsset = (a) => setForm((f) => (f.items.some((i) => i.asset_id === a.id) ? f
    : { ...f, items: [...f.items, { asset_id: a.id, asset_code: a.asset_code, asset_name: a.name, condition_id: a.condition_id || "", accessories: "", item_notes: "" }] }));
  const setItem = (idx, k, v) => setForm((f) => ({ ...f, items: f.items.map((it, i) => (i === idx ? { ...it, [k]: v } : it)) }));
  const payload = () => ({ employee_id: form.employee_id, opening_date: form.opening_date, project_id: form.project_id || null,
    work_location_id: form.work_location_id || null, ga_pic_name: form.ga_pic_name || null, manual_number: form.manual_number || null, notes: form.notes || null,
    items: form.items.map(({ asset_id, condition_id, accessories, item_notes }) => ({ asset_id, condition_id, accessories, item_notes })) });
  const valid = form.employee_id && form.items.length > 0 && form.items.every((i) => i.condition_id);
  const save = async (publish) => {
    setBusy(true);
    try {
      let res;
      if (publish) res = await api.post(editing ? `/asset-openings/${editing.id}/save-and-publish` : "/asset-openings/save-and-publish", payload());
      else res = editing ? await api.put(`/asset-openings/${editing.id}`, payload()) : await api.post("/asset-openings", payload());
      toast.success(publish ? `Saldo awal diterbitkan: ${res.data.bast_number}` : "Draft saldo awal tersimpan.");
      onSaved(res.data);
    } catch (e) {
      toast.error(errorMessage(e));   // input tetap di form agar dapat diperbaiki
    } finally {
      setBusy(false);
      setConfirm(false);
    }
  };
  const canSave = editing ? can("asset_opening", "edit") : can("asset_opening", "create");
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-2xl" data-testid="opening-form">
        <SheetHeader>
          <SheetTitle>{editing ? "Ubah Draft Saldo Awal" : "Saldo Awal Baru"}</SheetTitle>
          <SheetDescription>Untuk aset yang sudah dipegang karyawan saat sistem mulai dipakai - bukan penyerahan baru.</SheetDescription>
        </SheetHeader>
        <div className="mt-4 space-y-4">
          <EmployeeSearchField required endpoint="/asset-openings/employee-search" value={form.employee_id} selected={form.employee}
            onSelect={pickEmployee} testId="opening-employee-select" />
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5"><Label htmlFor="opening-date">Tanggal Saldo Awal / Mulai Holding <span className="text-danger">*</span></Label>
              <Input id="opening-date" type="date" max={todayIso()} value={form.opening_date} onChange={(e) => set("opening_date")(e.target.value)} data-testid="opening-date-input" /></div>
            <div className="space-y-1.5"><Label>Proyek</Label>
              <Select value={form.project_id || NONE} onValueChange={(v) => set("project_id")(v === NONE ? "" : v)}>
                <SelectTrigger data-testid="opening-project-select"><SelectValue placeholder="Pilih proyek" /></SelectTrigger>
                <SelectContent>{!options.restricted && <SelectItem value={NONE}>Tanpa proyek</SelectItem>}
                  {(options.projects || []).map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent>
              </Select></div>
            <div className="space-y-1.5"><Label>Lokasi</Label>
              <Select value={form.work_location_id || NONE} onValueChange={(v) => set("work_location_id")(v === NONE ? "" : v)}>
                <SelectTrigger data-testid="opening-location-select"><SelectValue placeholder="Pilih lokasi" /></SelectTrigger>
                <SelectContent><SelectItem value={NONE}>Tanpa lokasi</SelectItem>
                  {(options.work_locations || []).map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent>
              </Select></div>
            <div className="space-y-1.5"><Label htmlFor="opening-manual">Nomor Referensi Manual</Label>
              <Input id="opening-manual" value={form.manual_number || ""} onChange={(e) => set("manual_number")(e.target.value)} data-testid="opening-manual-input" /></div>
            <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="opening-pic">PIC GA (pencatat)</Label>
              <Input id="opening-pic" value={form.ga_pic_name || ""} onChange={(e) => set("ga_pic_name")(e.target.value)} data-testid="opening-pic-input" /></div>
          </div>
          <div className="space-y-1.5"><Label htmlFor="opening-notes">Catatan</Label>
            <Textarea id="opening-notes" rows={2} value={form.notes || ""} onChange={(e) => set("notes")(e.target.value)} data-testid="opening-notes-input" /></div>
          <div className="space-y-2 rounded-lg border border-border p-3">
            <Label htmlFor="opening-asset-search">Cari aset Siap Pakai (Asset Code, Kode Lama, Serial, Nama)</Label>
            <div className="relative"><Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input id="opening-asset-search" className="pl-8" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ketik minimal sebagian kode…" data-testid="opening-asset-search-input" /></div>
            <div className="max-h-44 space-y-1 overflow-auto" data-testid="opening-asset-results">
              {searching && <p className="text-[12.5px] text-muted-foreground">Mencari…</p>}
              {!searching && found.length === 0 && <p className="text-[12.5px] text-muted-foreground" data-testid="opening-asset-empty">Tidak ada aset Siap Pakai yang cocok.</p>}
              {found.map((a) => (
                <div key={a.id} className="flex items-center justify-between gap-2 rounded border border-border px-2 py-1.5 text-[13px]">
                  <span><span className="font-medium">{a.asset_code}</span> · {a.name}{a.legacy_code ? ` · Kode lama ${a.legacy_code}` : ""}{a.serial_number ? ` · SN ${a.serial_number}` : ""}</span>
                  <Button size="sm" variant="outline" onClick={() => addAsset(a)} disabled={form.items.some((i) => i.asset_id === a.id)} data-testid={`opening-asset-add-${a.id}`}>
                    <Plus className="mr-1 h-3.5 w-3.5" />Tambah</Button>
                </div>
              ))}
            </div>
          </div>
          <div className="space-y-2" data-testid="opening-selected-items">
            {form.items.map((it, idx) => (
              <AssetItemCard key={it.asset_id} index={idx + 1} total={form.items.length} code={it.asset_code} name={it.asset_name}
                onRemove={() => setForm((f) => ({ ...f, items: f.items.filter((_, i) => i !== idx) }))} testId={`opening-item-${it.asset_id}`}>
                <ItemField label="Kondisi saat saldo awal" required>
                  <Select value={it.condition_id || ""} onValueChange={(v) => setItem(idx, "condition_id", v)}>
                    <SelectTrigger data-testid={`opening-item-condition-${it.asset_id}`}><SelectValue placeholder="Pilih kondisi" /></SelectTrigger>
                    <SelectContent>{(options.conditions || []).map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
                  </Select>
                </ItemField>
                <ItemField label="Kelengkapan"><Input value={it.accessories} onChange={(e) => setItem(idx, "accessories", e.target.value)} data-testid={`opening-item-accessories-${it.asset_id}`} /></ItemField>
                <ItemField label="Catatan"><Input value={it.item_notes} onChange={(e) => setItem(idx, "item_notes", e.target.value)} data-testid={`opening-item-notes-${it.asset_id}`} /></ItemField>
              </AssetItemCard>
            ))}
          </div>
          <div className="flex flex-wrap justify-end gap-2 border-t border-border pt-3">
            {canSave && <Button variant="outline" onClick={() => save(false)} disabled={busy || !valid} data-testid="opening-form-save-button">Simpan Draft</Button>}
            {can("asset_opening", "publish") && canSave && (
              <Button onClick={() => setConfirm(true)} disabled={busy || !valid} data-testid="opening-form-save-publish-button"><Send className="mr-1.5 h-4 w-4" />Simpan & Publish</Button>
            )}
          </div>
          {!can("asset_opening", "publish") && <p className="text-right text-[12.5px] text-muted-foreground" data-testid="opening-publish-hint">Publish dilakukan oleh pengguna dengan izin terbit saldo awal.</p>}
        </div>
        <ConfirmDialog open={confirm} onOpenChange={setConfirm} title="Simpan & Publish saldo awal?"
          description={`${form.items.length} aset akan tercatat dipegang ${employeeLabel(form.employee)} dan dokumen BAST-EXS terbit. Tindakan ini tidak dapat dibatalkan.`}
          confirmLabel="Simpan & Publish" onConfirm={() => save(true)} loading={busy} />
      </SheetContent>
    </Sheet>
  );
};

const OpeningSection = ({ can, reloadKey }) => {
  const [options, setOptions] = useState({});
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [detail, setDetail] = useState(null);
  const [confirm, setConfirm] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [busy, setBusy] = useState(false);
  const [stateFilter, setStateFilter] = useState("");
  const limit = 20;
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await api.get("/asset-openings", { params: { page, limit, ...(stateFilter ? { doc_state: stateFilter } : {}) } });
      setRows(data.items);
      setTotal(data.total);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, [page, stateFilter]);
  useEffect(() => { load(); }, [load, reloadKey]);   // reloadKey: impor saldo awal massal selesai -> daftar dimuat ulang
  useEffect(() => { api.get("/asset-openings/options").then((r) => setOptions(r.data)).catch(() => {}); }, []);
  const openDetail = async (r) => { try { setDetail((await api.get(`/asset-openings/${r.id}`)).data); } catch (e) { toast.error(errorMessage(e)); } };

  // CP4: deep-link ?open=<id> (dari Profil Karyawan / Asset 360)
  const [searchParams, setSearchParams] = useSearchParams();
  useEffect(() => {
    const id = searchParams.get("open");
    if (!id) return;
    openDetail({ id });
    const p = new URLSearchParams(searchParams);
    p.delete("open");
    setSearchParams(p, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);
  const publish = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/asset-openings/${detail.id}/publish`);
      toast.success(`Saldo awal diterbitkan: ${data.bast_number}`);
      setDetail(data);
      load();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
      setConfirm(false);
    }
  };
  const cancelDraft = async () => {
    setBusy(true);
    try {
      await api.post(`/asset-openings/${detail.id}/cancel`);
      toast.success("Draft saldo awal dibatalkan.");
      setDetail(null);
      load();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
      setConfirmCancel(false);
    }
  };
  const columns = [
    { key: "bast_number", header: "Nomor BAST-EXS", render: (r) => <span className="font-medium tabular-nums">{r.bast_number || "—"}</span> },
    { key: "employee_name", header: "Karyawan", render: (r) => employeeLabel({ full_name: r.employee_name, employee_number: r.employee_number }) },
    { key: "opening_date", header: "Tanggal Saldo Awal", hideOnMobile: true, render: (r) => formatDate(r.opening_date) },
    { key: "project_name", header: "Proyek", hideOnMobile: true, render: (r) => r.project_name || "-" },
    { key: "item_count", header: "Aset", render: (r) => <span className="tabular-nums">{r.item_count}</span> },
    { key: "doc_state", header: "Status", render: (r) => <StateBadge state={r.doc_state} testId={`opening-state-${r.id}`} /> },
    { key: "actions", header: "", render: (r) => <DetailButton onClick={() => openDetail(r)} testId={`opening-detail-button-${r.id}`} label="Lihat Detail" /> },
  ];
  return (
    <div className="space-y-3" data-testid="opening-section">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">Catat aset yang sudah dipegang karyawan. Aset menjadi Dipakai setelah dipublish (BAST-EXS).</p>
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter status saldo awal">
            {[["", "Semua"], ["DRAFT", "Draft"], ["PUBLISHED", "Terbit"], ["CANCELLED", "Dibatalkan"]].map(([v, l]) => (
              <Button key={l} size="sm" variant={stateFilter === v ? "default" : "outline"} aria-pressed={stateFilter === v}
                onClick={() => { setStateFilter(v); setPage(1); }} data-testid={`opening-filter-${(v || "all").toLowerCase()}`}>{l}</Button>
            ))}
          </div>
        </div>
        {can("asset_opening", "create") && (
          <Button onClick={() => { setEditing(null); setFormOpen(true); }} data-testid="opening-add-button"><Plus className="mr-1.5 h-4 w-4" />Saldo Awal Manual</Button>
        )}
      </div>
      <TableCard>
        {error && !loading ? (
          <EmptyState testId="opening-list-error" icon={RefreshCw} title="Daftar saldo awal gagal dimuat" description={error} actionLabel="Coba lagi" onAction={load} />
        ) : (
          <>
            <DataTable testId="opening-table" columns={columns} rows={rows} loading={loading}
              emptyProps={{ icon: ClipboardCheck, testId: "opening-list-empty", title: "Belum ada saldo awal", description: "Buat saldo awal manual atau gunakan impor massal." }} />
            <Pagination page={page} totalPages={Math.max(1, Math.ceil(total / limit))} total={total} limit={limit} onPageChange={setPage} onLimitChange={() => {}} />
          </>
        )}
      </TableCard>
      <OpeningForm open={formOpen} onOpenChange={setFormOpen} options={options} editing={editing} can={can}
        onSaved={(d) => { setFormOpen(false); setDetail(d); load(); }} />
      <Sheet open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-2xl" data-testid="opening-detail">
          {detail && (
            <>
              <SheetHeader>
                <SheetTitle className="flex flex-wrap items-center gap-2">{detail.bast_number || "Draft Saldo Awal"} <StateBadge state={detail.doc_state} testId="opening-detail-state" /></SheetTitle>
                <SheetDescription>Saldo awal / existing holding - bukan penyerahan baru.</SheetDescription>
              </SheetHeader>
              <div className="mt-4 space-y-4">
                {!detail.bast_snapshot && <InfoGrid testId="opening-detail-info" rows={[["Karyawan", employeeLabel({ full_name: detail.employee_name, employee_number: detail.employee_number })],
                  ["Tanggal Saldo Awal", formatDate(detail.opening_date)], ["Proyek", detail.project_name || "-"], ["Lokasi", detail.work_location_name || "-"],
                  ["PIC GA", detail.ga_pic_name || "-"], ["No. Referensi", detail.manual_number || "-"], ["Catatan", detail.notes || "-"]]} />}
                <AssetDocumentsPanel sourceType="OPENING_EXISTING" sourceId={detail.id} docState={detail.doc_state}
                  assets={(detail.items || []).map((i) => ({ asset_id: i.asset_id, asset_code: i.asset_code, asset_name: i.asset_name }))}
                  testId="opening-doc-panel" />
                {detail.bast_snapshot ? <SnapshotView snapshot={detail.bast_snapshot} testId="opening-snapshot" /> : (
                  <ul className="space-y-1 text-sm" data-testid="opening-detail-items">
                    {detail.items.map((i) => <li key={i.asset_id}>{i.asset_code} · {i.asset_name} · {i.condition_name || "-"}</li>)}
                  </ul>
                )}
                <div className="flex flex-wrap gap-2">
                  {detail.bast_id && <BastPdfActions bastId={detail.bast_id} systemNumber={detail.bast_number} testIdPrefix="opening-bast" />}
                  {detail.doc_state === "DRAFT" && can("asset_opening", "edit") && (
                    <Button variant="outline" onClick={() => { setEditing(detail); setDetail(null); setFormOpen(true); }} data-testid="opening-edit-button">Ubah Draft</Button>
                  )}
                  {detail.doc_state === "DRAFT" && can("asset_opening", "edit") && (
                    <Button variant="outline" onClick={() => setConfirmCancel(true)} data-testid="opening-cancel-button">Batalkan Draft</Button>
                  )}
                  {detail.doc_state === "DRAFT" && can("asset_opening", "publish") && (
                    <Button onClick={() => setConfirm(true)} data-testid="opening-publish-button"><Send className="mr-1.5 h-4 w-4" />Publish</Button>
                  )}
                </div>
              </div>
              <ConfirmDialog open={confirm} onOpenChange={setConfirm} title="Publish saldo awal?"
                description="Aset akan tercatat dipegang karyawan (Dipakai) dan BAST-EXS terbit. Tindakan ini tidak dapat dibatalkan."
                confirmLabel="Publish" onConfirm={publish} loading={busy} />
              <ConfirmDialog open={confirmCancel} onOpenChange={setConfirmCancel} title="Batalkan draft saldo awal?" destructive
                description="Draft akan dibatalkan. Aset tidak berubah dan tidak ada BAST yang terbit." confirmLabel="Batalkan Draft" onConfirm={cancelDraft} loading={busy} />
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
};

const HistorySection = () => {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [view, setView] = useState(null);
  const limit = 20;
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await api.get("/asset-imports", { params: { page, limit } });
      setRows(data.items);
      setTotal(data.total);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, [page]);
  useEffect(() => { load(); }, [load]);
  const columns = [
    { key: "batch_number", header: "Nomor Batch", render: (r) => <span className="font-medium tabular-nums">{r.batch_number}</span> },
    { key: "import_type", header: "Jenis", render: (r) => TYPE_LABEL[r.import_type] || r.import_type },
    { key: "file_name", header: "File", hideOnMobile: true, render: (r) => <span className="text-[13px]">{r.file_name}</span> },
    { key: "total_rows", header: "Baris", render: (r) => <span className="tabular-nums">{r.total_rows}</span> },
    { key: "counts", header: "Valid / Warning / Error", hideOnMobile: true, render: (r) => (
      <span className="tabular-nums text-[13px]" data-testid={`history-counts-${r.id}`}>
        <span className="text-success">{r.valid_rows}</span> / <span className="text-warning">{r.warning_rows}</span> / <span className={r.error_rows ? "text-danger" : ""}>{r.error_rows}</span>
      </span>) },
    { key: "done", header: "Berhasil", render: (r) => <span className="tabular-nums" data-testid={`history-done-${r.id}`}>{r.batch_state === "COMMITTED" ? (r.import_type === "MASTER" ? `${r.created_count} aset` : `${r.opening_count} dokumen`) : "-"}</span> },
    { key: "batch_state", header: "Status", render: (r) => <ToneBadge meta={BATCH_STATE[r.batch_state]} testId={`history-state-${r.id}`} /> },
    { key: "uploaded_by_name", header: "Diunggah", hideOnMobile: true, render: (r) => `${r.uploaded_by_name || "-"} · ${formatDate(r.uploaded_at)}` },
    { key: "actions", header: "", render: (r) => (
      <div className="flex gap-1">
        <DetailButton onClick={() => setView(r)} testId={`history-detail-button-${r.id}`} label="Lihat Detail" />
        {r.batch_state === "COMMITTED" && (
          <Button size="sm" variant="ghost" onClick={() => downloadBlob(`/asset-imports/${r.id}/result`, {}, `hasil-impor-${String(r.batch_number || "").replaceAll("/", "-")}.xlsx`).catch((e) => toast.error(errorMessage(e)))}
            data-testid={`history-result-button-${r.id}`} aria-label="Download hasil impor"><Download className="h-4 w-4" /></Button>
        )}
      </div>) },
  ];
  return (
    <div className="space-y-3" data-testid="history-section">
      <TableCard>
        {error && !loading ? (
          <EmptyState testId="history-error" icon={RefreshCw} title="Riwayat impor gagal dimuat" description={error} actionLabel="Coba lagi" onAction={load} />
        ) : (
          <>
            <DataTable testId="history-table" columns={columns} rows={rows} loading={loading}
              emptyProps={{ icon: History, testId: "history-empty", title: "Belum ada riwayat impor", description: "Batch impor master dan saldo awal akan tampil di sini." }} />
            <Pagination page={page} totalPages={Math.max(1, Math.ceil(total / limit))} total={total} limit={limit} onPageChange={setPage} onLimitChange={() => {}} />
          </>
        )}
      </TableCard>
      <Dialog open={!!view} onOpenChange={(o) => !o && setView(null)}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-4xl" data-testid="history-detail">
          {view && (
            <>
              <DialogHeader>
                <DialogTitle>{view.batch_number} · {TYPE_LABEL[view.import_type]}</DialogTitle>
                <DialogDescription>{view.file_name} · diunggah {view.uploaded_by_name || "-"}{view.committed_by_name ? ` · diproses ${view.committed_by_name}` : ""}</DialogDescription>
              </DialogHeader>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-5" data-testid="history-detail-stats">
                <Stat label="Total baris" value={view.total_rows} />
                <Stat label="Valid" value={view.valid_rows} tone="success" />
                <Stat label="Warning" value={view.warning_rows} tone="warning" />
                <Stat label="Error" value={view.error_rows} tone={view.error_rows ? "danger" : undefined} />
                <Stat label={view.import_type === "MASTER" ? "Aset dibuat" : "Dokumen dibuat"} value={view.import_type === "MASTER" ? view.created_count : view.opening_count} />
              </div>
              {view.import_type === "OPENING" && <GroupSummary summary={view.summary} testId="history-groups" />}
              <BatchRows batch={view} testId="history-rows" />
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default function AssetImportOpeningPage() {
  const { can } = useAuth();
  const canImport = can("asset_import", "view");
  const canOpening = can("asset_opening", "view");
  const [tab, setTab] = useState(() => (new URLSearchParams(window.location.search).get("tab") === "opening" || !canImport ? "opening" : "master"));
  const [historyKey, setHistoryKey] = useState(0);
  if (!canImport && !canOpening) {
    return <PageBody><EmptyState icon={XCircle} title="Tidak ada akses" description="Anda tidak memiliki izin Impor Aset maupun Saldo Awal." testId="imports-no-access" /></PageBody>;
  }
  return (
    <PageBody>
      <SectionHeader title="Impor & Saldo Awal" description="Bawa aset existing ke sistem: impor master aset, lalu catat aset yang sudah dipegang karyawan tanpa penyerahan palsu." />
      <Tabs value={tab} onValueChange={setTab} data-testid="imports-tabs">
        <div className="max-w-full overflow-x-auto">
          <TabsList>
            {canImport && <TabsTrigger value="master" data-testid="imports-tab-master"><FileSpreadsheet className="mr-1.5 h-4 w-4" />Import Master Aset</TabsTrigger>}
            {canOpening && <TabsTrigger value="opening" data-testid="imports-tab-opening"><ClipboardCheck className="mr-1.5 h-4 w-4" />Opening Existing Holding</TabsTrigger>}
            {canImport && <TabsTrigger value="history" data-testid="imports-tab-history"><History className="mr-1.5 h-4 w-4" />Riwayat Import</TabsTrigger>}
          </TabsList>
        </div>
        {canImport && <TabsContent value="master" className="mt-4"><ImportWizard type="MASTER" can={can} onDone={() => setHistoryKey((k) => k + 1)} /></TabsContent>}
        {canOpening && (
          <TabsContent value="opening" className="mt-4 space-y-6">
            <OpeningSection can={can} reloadKey={historyKey} />
            {canImport && (
              <div className="space-y-3">
                <h3 className="text-base font-semibold">Impor Saldo Awal Massal (Excel)</h3>
                <ImportWizard type="OPENING" can={can} onDone={() => setHistoryKey((k) => k + 1)} />
              </div>
            )}
          </TabsContent>
        )}
        {canImport && <TabsContent value="history" className="mt-4"><HistorySection key={historyKey} /></TabsContent>}
      </Tabs>
    </PageBody>
  );
}
