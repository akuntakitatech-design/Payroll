import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ClipboardCheck, Eye, HandCoins, Pencil, RefreshCw, Send, XCircle } from "lucide-react";
import { toast } from "sonner";

import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { PageBody, SectionHeader } from "@/components/common/PageHeader";
import DataTable, { FilterBar, FilterSelect, Pagination, RowActions, TableCard } from "@/components/common/DataTable";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import EmptyState from "@/components/common/EmptyState";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  AssetItemCard, BastPdfActions, DetailButton, EmployeeSearchField, InfoGrid, ItemField, SnapshotView, StateBadge,
  bastIssuedMessage, employeeLabel, toOptions, todayIso,
} from "@/pages/asset/assetLifecycleShared";

// Phase 2A CP2 - Penyerahan Aset: DRAFT -> PUBLISHED (atomik di backend). Hanya aset READY yang dapat dipilih.
// Tidak ada transfer langsung antar karyawan: aset dipakai wajib dikembalikan + diperiksa dulu.
// CP2.1: pemilik izin `asset_handover:publish` dapat "Simpan & Publish" langsung dari form (satu transaksi atomik di
// backend); tanpa izin publish hanya "Simpan Draft". Otorisasi murni permission efektif, bukan nama role.

const NONE = "__none__";
const DOC_STATES = [
  { value: "DRAFT", label: "Draft" },
  { value: "PUBLISHED", label: "Terbit" },
  { value: "CANCELLED", label: "Dibatalkan" },
];

const SelectField = ({ label, value, onChange, options, placeholder, testId, allowNone, required }) => (
  <div className="space-y-1.5">
    <Label>
      {label}
      {required && <span className="text-danger"> *</span>}
    </Label>
    <Select value={value || (allowNone ? NONE : "")} onValueChange={(v) => onChange(v === NONE ? "" : v)}>
      <SelectTrigger data-testid={testId}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {allowNone && <SelectItem value={NONE}>Tanpa {label.toLowerCase()}</SelectItem>}
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  </div>
);

const emptyForm = (opts) => ({
  employee_id: "", employee: null, handover_date: todayIso(), project_id: "", work_location_id: "", manual_number: "", notes: "",
  ga_pic_name: opts?.ga_pic_name || "", items: [],
});

const AssetHandoverPage = () => {
  const { can } = useAuth();
  const perms = {
    create: can("asset_handover", "create"),
    edit: can("asset_handover", "edit"),
    publish: can("asset_handover", "publish"),
  };
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(20);
  const [search, setSearch] = useState("");
  const [docState, setDocState] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [opts, setOpts] = useState(null);
  const [form, setForm] = useState(null); // {mode, id, values}
  const [saving, setSaving] = useState(false);
  const [assetQuery, setAssetQuery] = useState("");
  const [detail, setDetail] = useState(null);
  const [confirm, setConfirm] = useState(null); // {type, doc}
  const [acting, setActing] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const { data } = await api.get("/asset-handovers", { params: { page, limit, q: search || undefined, doc_state: docState || undefined } });
      setRows(data.items);
      setTotal(data.total);
    } catch (e) {
      setLoadError(errorMessage(e, "Daftar penyerahan gagal dimuat."));
    } finally {
      setLoading(false);
    }
  }, [page, limit, search, docState]);

  const loadOptions = useCallback(async () => {
    try {
      const { data } = await api.get("/asset-handovers/options", { params: { include_employees: false } });
      setOpts(data);
      return data;
    } catch (e) {
      toast.error(errorMessage(e, "Pilihan karyawan/aset gagal dimuat."));
      return null;
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(load, search ? 300 : 0);
    return () => clearTimeout(t);
  }, [load, search]);

  const openDetail = async (row) => {
    try {
      const { data } = await api.get(`/asset-handovers/${row.id}`);
      setDetail(data);
    } catch (e) {
      toast.error(errorMessage(e, "Detail penyerahan gagal dimuat."));
    }
  };

  const openCreate = async () => {
    const o = (await loadOptions()) || opts;
    setAssetQuery("");
    setForm({ mode: "create", values: emptyForm(o) });
  };

  const openEdit = async (doc) => {
    await loadOptions();
    const full = doc.items ? doc : (await api.get(`/asset-handovers/${doc.id}`)).data;
    setAssetQuery("");
    setDetail(null);
    setForm({
      mode: "edit", id: full.id,
      values: {
        employee_id: full.employee_id || "",
        employee: full.employee_id ? { id: full.employee_id, full_name: full.employee_name, employee_number: full.employee_number } : null,
        handover_date: full.handover_date || todayIso(), project_id: full.project_id || "",
        work_location_id: full.work_location_id || "", manual_number: full.manual_number || "", notes: full.notes || "",
        ga_pic_name: full.ga_pic_name || "",
        items: (full.items || []).map((i) => ({ asset_id: i.asset_id, asset_code: i.asset_code, name: i.asset_name,
          condition_id: i.condition_id || "", accessories: i.accessories || "", item_notes: i.item_notes || "" })),
      },
    });
  };

  const setVal = (k) => (v) => setForm((f) => ({ ...f, values: { ...f.values, [k]: v } }));
  const selectedIds = useMemo(() => new Set((form?.values.items || []).map((i) => i.asset_id)), [form]);
  const toggleAsset = (a, checked) =>
    setForm((f) => {
      const items = checked
        ? [...f.values.items, { asset_id: a.id, asset_code: a.asset_code, name: a.name, condition_id: a.condition_id || "", accessories: "", item_notes: "" }]
        : f.values.items.filter((i) => i.asset_id !== a.id);
      return { ...f, values: { ...f.values, items } };
    });
  const setItem = (assetId, key, value) =>
    setForm((f) => ({ ...f, values: { ...f.values, items: f.values.items.map((i) => (i.asset_id === assetId ? { ...i, [key]: value } : i)) } }));

  const availableAssets = useMemo(() => {
    const q = assetQuery.trim().toLowerCase();
    const list = opts?.assets || [];
    return q ? list.filter((a) => [a.asset_code, a.name, a.serial_number].some((x) => (x || "").toLowerCase().includes(q))) : list;
  }, [opts, assetQuery]);

  const buildBody = (v) => ({
      employee_id: v.employee_id, handover_date: v.handover_date, project_id: v.project_id || null,
      work_location_id: v.work_location_id || null, manual_number: v.manual_number || null, notes: v.notes || null,
      ga_pic_name: v.ga_pic_name || null,
      items: v.items.map((i) => ({ asset_id: i.asset_id, condition_id: i.condition_id || null, accessories: i.accessories || null,
        item_notes: i.item_notes || null })),
  });

  const validateForm = (v) => {
    if (!v.employee_id) { toast.error("Karyawan penerima wajib dipilih."); return false; }
    if (!v.items.length) { toast.error("Pilih minimal satu aset Siap Pakai."); return false; }
    return true;
  };

  // Simpan & Publish: satu operasi atomik di backend. Gagal -> tidak ada perubahan tersimpan; input form dipertahankan.
  const saveAndPublish = async () => {
    const v = form.values;
    setSaving(true);
    try {
      const body = buildBody(v);
      const { data } = form.mode === "create"
        ? await api.post("/asset-handovers/save-and-publish", body)
        : await api.post(`/asset-handovers/${form.id}/save-and-publish`, body);
      toast.success(bastIssuedMessage(data.bast_number));
      setConfirm(null);
      setForm(null);
      setDetail(data);
      load();
    } catch (e) {
      setConfirm(null);
      toast.error(errorMessage(e, "Simpan & Publish gagal. Tidak ada perubahan yang disimpan; periksa isian lalu coba lagi."), { duration: 9000 });
    } finally {
      setSaving(false);
    }
  };

  const saveDraft = async () => {
    const v = form.values;
    if (!validateForm(v)) return;
    setSaving(true);
    const body = buildBody(v);
    try {
      const { data } = form.mode === "create" ? await api.post("/asset-handovers", body) : await api.put(`/asset-handovers/${form.id}`, body);
      toast.success(form.mode === "create" ? "Draft penyerahan disimpan." : "Draft penyerahan diperbarui.");
      if (data.manual_number_warning) toast.warning(data.manual_number_warning, { duration: 9000 });
      setForm(null);
      setDetail(data);
      load();
    } catch (e) {
      toast.error(errorMessage(e, "Draft penyerahan gagal disimpan."), { duration: 9000 });
    } finally {
      setSaving(false);
    }
  };

  const runConfirm = async () => {
    const { type, doc } = confirm;
    if (type === "save_publish") return saveAndPublish();
    setActing(true);
    try {
      if (type === "publish") {
        const { data } = await api.post(`/asset-handovers/${doc.id}/publish`);
        toast.success(bastIssuedMessage(data.bast_number));
        setDetail(data);
      } else {
        await api.post(`/asset-handovers/${doc.id}/cancel`);
        toast.success("Draft penyerahan dibatalkan.");
        setDetail(null);
      }
      setConfirm(null);
      load();
    } catch (e) {
      toast.error(errorMessage(e, type === "publish" ? "Publish penyerahan gagal." : "Pembatalan gagal."), { duration: 9000 });
      setConfirm(null);
      if (detail) openDetail(detail);
    } finally {
      setActing(false);
    }
  };

  const columns = [
    { key: "bast_number", header: "Nomor BAST", render: (r) => <span className="font-medium tabular-nums">{r.bast_number || "—"}</span> },
    { key: "handover_date", header: "Tanggal", render: (r) => formatDate(r.handover_date) },
    { key: "employee_name", header: "Karyawan", render: (r) => employeeLabel({ full_name: r.employee_name, employee_number: r.employee_number }) },
    { key: "project_name", header: "Project", hideOnMobile: true, render: (r) => r.project_name || "-" },
    { key: "manual_number", header: "No. Referensi", hideOnMobile: true, render: (r) => r.manual_number || "-" },
    { key: "doc_state", header: "Status", render: (r) => <StateBadge state={r.doc_state} testId={`handover-state-${r.id}`} /> },
    {
      key: "actions", header: "", align: "right",
      render: (r) => (
        <div className="flex items-center justify-end gap-1">
          <DetailButton onClick={() => openDetail(r)} testId={`handover-detail-button-${r.id}`} />
          <RowActions
            testId={`handover-row-actions-${r.id}`}
            actions={[
              { key: "view", label: "Lihat detail", icon: Eye, onSelect: () => openDetail(r), testId: `handover-view-${r.id}` },
              r.doc_state === "DRAFT" && perms.edit && { key: "edit", label: "Ubah draft", icon: Pencil, onSelect: () => openEdit(r), testId: `handover-edit-${r.id}` },
            ]}
          />
        </div>
      ),
    },
  ];

  const v = form?.values;
  // Simpan & Publish = izin simpan (create untuk form baru / edit untuk draft) + izin publish.
  const canSavePublish = !!form && perms.publish && (form.mode === "create" ? perms.create : perms.edit);
  const hasFilters = !!(search || docState);

  return (
    <PageBody className="space-y-4">
      <div className="space-y-4" data-testid="asset-handover-page">
        <SectionHeader
          title="Penyerahan Aset"
          description="Serahkan satu atau beberapa aset Siap Pakai kepada satu karyawan. BAST Penyerahan terbit saat draft dipublish."
          actions={
            perms.create && (
              <Button onClick={openCreate} data-testid="handover-add-button">
                <HandCoins className="mr-2 h-4 w-4" /> Buat Penyerahan
              </Button>
            )
          }
        />
        <FilterBar
          search={search}
          onSearchChange={(val) => {
            setSearch(val);
            setPage(1);
          }}
          searchPlaceholder="Cari nomor BAST, nomor referensi, atau nama/NIK karyawan…"
          showReset={hasFilters}
          onReset={() => {
            setSearch("");
            setDocState("");
            setPage(1);
          }}
        >
          <FilterSelect label="Status" value={docState} onChange={(val) => { setDocState(val); setPage(1); }} options={DOC_STATES}
            allLabel="Semua status" testId="handover-filter-state" />
        </FilterBar>
        <TableCard>
          {loadError && !loading ? (
            <EmptyState testId="handover-list-error" icon={RefreshCw} title="Daftar penyerahan gagal dimuat" description={loadError}
              actionLabel="Coba lagi" onAction={load} />
          ) : (
            <>
              <DataTable testId="handover-table" columns={columns} rows={rows} loading={loading} onRowClick={openDetail}
                emptyProps={{
                  icon: HandCoins, testId: "handover-list-empty",
                  title: hasFilters ? "Tidak ada penyerahan yang cocok" : "Belum ada penyerahan aset",
                  description: hasFilters ? "Ubah kata kunci atau filter." : "Buat penyerahan untuk menyerahkan aset Siap Pakai kepada karyawan.",
                  actionLabel: !hasFilters && perms.create ? "Buat Penyerahan" : undefined,
                  onAction: !hasFilters && perms.create ? openCreate : undefined,
                }} />
              <Pagination page={page} totalPages={Math.max(1, Math.ceil(total / limit))} total={total} limit={limit} onPageChange={setPage}
                onLimitChange={(val) => { setLimit(val); setPage(1); }} />
            </>
          )}
        </TableCard>
      </div>

      {/* Form draft penyerahan */}
      <Dialog open={!!form} onOpenChange={(o) => !o && !saving && !confirm && setForm(null)}>
        <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-3xl" data-testid="handover-form-dialog">
          <DialogHeader>
            <DialogTitle>{form?.mode === "edit" ? "Ubah Draft Penyerahan" : "Buat Penyerahan"}</DialogTitle>
            <DialogDescription>
              {canSavePublish
                ? "Simpan Draft untuk dilanjutkan nanti, atau Simpan & Publish untuk langsung menerbitkan BAST. Status aset berubah menjadi Dipakai saat dipublish."
                : "Draft belum mengubah status aset. Status aset berubah menjadi Dipakai saat draft dipublish oleh pengguna berizin."}
            </DialogDescription>
          </DialogHeader>
          {!opts || !v ? (
            <div className="space-y-2"><Skeleton className="h-9 w-full" /><Skeleton className="h-9 w-full" /><Skeleton className="h-40 w-full" /></div>
          ) : (
            <div className="space-y-5">
              {opts.restricted && (
                <Alert data-testid="handover-scope-note"><AlertDescription>Karyawan, aset, dan project dibatasi sesuai cakupan data Anda.</AlertDescription></Alert>
              )}
              <div className="grid gap-4 sm:grid-cols-2">
                <EmployeeSearchField label="Karyawan penerima" required endpoint="/asset-handovers/employee-search" value={v.employee_id}
                  selected={v.employee} testId="handover-employee-select"
                  onSelect={(e) => setForm((f) => ({ ...f, values: { ...f.values, employee_id: e.id, employee: e } }))} />
                <div className="space-y-1.5">
                  <Label htmlFor="ho-date">Tanggal penyerahan <span className="text-danger">*</span></Label>
                  <Input id="ho-date" type="date" value={v.handover_date} onChange={(e) => setVal("handover_date")(e.target.value)} data-testid="handover-date-input" />
                </div>
                <SelectField label="Project" value={v.project_id} onChange={setVal("project_id")} placeholder="Pilih project" allowNone={!opts.restricted}
                  required={opts.restricted} options={toOptions(opts.projects)} testId="handover-project-select" />
                <SelectField label="Lokasi kerja" value={v.work_location_id} onChange={setVal("work_location_id")} placeholder="Pilih lokasi" allowNone
                  options={toOptions(opts.work_locations)} testId="handover-location-select" />
                <div className="space-y-1.5">
                  <Label htmlFor="ho-pic">PIC GA</Label>
                  <Input id="ho-pic" value={v.ga_pic_name} onChange={(e) => setVal("ga_pic_name")(e.target.value)} data-testid="handover-pic-input" />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="ho-ref">Nomor referensi (opsional)</Label>
                  <Input id="ho-ref" value={v.manual_number} onChange={(e) => setVal("manual_number")(e.target.value)} placeholder="Mis. nomor BAST kertas"
                    data-testid="handover-manual-number-input" />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ho-notes">Catatan</Label>
                <Textarea id="ho-notes" rows={2} value={v.notes} onChange={(e) => setVal("notes")(e.target.value)} data-testid="handover-notes-input" />
              </div>

              <div className="space-y-2">
                <div className="flex flex-wrap items-end justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold">Aset Siap Pakai</p>
                    <p className="text-[12px] text-muted-foreground">Aset yang sedang dipakai tidak muncul di sini; kembalikan dan periksa terlebih dahulu.</p>
                  </div>
                  <Input className="h-9 w-full sm:w-64" placeholder="Cari kode, nama, serial…" value={assetQuery} onChange={(e) => setAssetQuery(e.target.value)}
                    data-testid="handover-asset-search-input" />
                </div>
                <div className="max-h-56 overflow-y-auto rounded-md border border-border" data-testid="handover-asset-picker">
                  {availableAssets.length === 0 ? (
                    <p className="px-3 py-6 text-sm text-muted-foreground" data-testid="handover-asset-picker-empty">Tidak ada aset Siap Pakai yang tersedia.</p>
                  ) : (
                    availableAssets.map((a) => (
                      <label key={a.id} className="flex cursor-pointer items-center gap-3 border-b border-border px-3 py-2 last:border-b-0 hover:bg-muted/50">
                        <Checkbox checked={selectedIds.has(a.id)} onCheckedChange={(c) => toggleAsset(a, !!c)} data-testid={`handover-asset-option-${a.id}`} />
                        <span className="min-w-0 flex-1">
                          <span className="block text-sm font-medium">{a.asset_code} · {a.name}</span>
                          <span className="block text-[12px] text-muted-foreground">SN: {a.serial_number || "-"}</span>
                        </span>
                      </label>
                    ))
                  )}
                </div>
              </div>

              {v.items.length > 0 && (
                <div className="space-y-2" data-testid="handover-selected-items">
                  <p className="text-sm font-semibold">Detail per aset ({v.items.length})</p>
                  {v.items.map((i, idx) => (
                    <AssetItemCard key={i.asset_id} index={idx + 1} total={v.items.length} code={i.asset_code} name={i.name}
                      testId={`handover-item-card-${i.asset_id}`} onRemove={() => toggleAsset({ id: i.asset_id }, false)}>
                      <ItemField label="Kondisi">
                        <Select value={i.condition_id || ""} onValueChange={(val) => setItem(i.asset_id, "condition_id", val)}>
                          <SelectTrigger className="h-9" aria-label={`Kondisi ${i.asset_code}`} data-testid={`handover-item-condition-${i.asset_id}`}><SelectValue placeholder="Pilih kondisi" /></SelectTrigger>
                          <SelectContent>{(opts.conditions || []).map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
                        </Select>
                      </ItemField>
                      <ItemField label="Kelengkapan" htmlFor={`ho-acc-${i.asset_id}`}>
                        <Input id={`ho-acc-${i.asset_id}`} className="h-9" placeholder="Mis. charger, tas" value={i.accessories}
                          onChange={(e) => setItem(i.asset_id, "accessories", e.target.value)} data-testid={`handover-item-accessories-${i.asset_id}`} />
                      </ItemField>
                      <ItemField label="Catatan" htmlFor={`ho-note-${i.asset_id}`}>
                        <Input id={`ho-note-${i.asset_id}`} className="h-9" placeholder="Opsional" value={i.item_notes}
                          onChange={(e) => setItem(i.asset_id, "item_notes", e.target.value)} data-testid={`handover-item-notes-${i.asset_id}`} />
                      </ItemField>
                    </AssetItemCard>
                  ))}
                </div>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setForm(null)} disabled={saving} data-testid="handover-form-cancel-button">Batal</Button>
            <Button variant={canSavePublish ? "outline" : "default"} onClick={saveDraft} disabled={saving || !opts} data-testid="handover-form-save-button">
              {saving && !confirm ? "Menyimpan…" : "Simpan Draft"}
            </Button>
            {canSavePublish && (
              <Button onClick={() => validateForm(v) && setConfirm({ type: "save_publish", doc: { items: v.items, employee_name: v.employee?.full_name } })}
                disabled={saving || !opts} data-testid="handover-form-save-publish-button">
                <Send className="mr-2 h-4 w-4" /> Simpan &amp; Publish
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail / review */}
      <Sheet open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-2xl" data-testid="handover-detail-sheet">
          {detail && (
            <div className="space-y-5">
              <SheetHeader>
                <SheetTitle className="flex flex-wrap items-center gap-2">
                  {detail.bast_number || "Draft Penyerahan"} <StateBadge state={detail.doc_state} testId="handover-detail-state" />
                </SheetTitle>
                <SheetDescription>
                  {detail.doc_state === "DRAFT" ? "Tinjau draft sebelum dipublish. Draft dapat diubah atau dibatalkan." : "Dokumen terbit bersifat final (read-only)."}
                </SheetDescription>
              </SheetHeader>
              {detail.manual_number_warning && (
                <Alert data-testid="handover-manual-warning"><AlertDescription>{detail.manual_number_warning}</AlertDescription></Alert>
              )}
              {detail.doc_state === "PUBLISHED" && detail.bast_snapshot ? (
                <>
                  <BastPdfActions bastId={detail.bast_id} systemNumber={detail.bast_number} testIdPrefix="handover-bast" />
                  <SnapshotView snapshot={detail.bast_snapshot} testId="handover-snapshot" />
                </>
              ) : (
                <>
                  <InfoGrid rows={[
                    ["Karyawan", employeeLabel({ full_name: detail.employee_name, employee_number: detail.employee_number }), "handover-detail-employee"],
                    ["Tanggal", formatDate(detail.handover_date)],
                    ["Project", detail.project_name], ["Lokasi kerja", detail.work_location_name],
                    ["PIC GA", detail.ga_pic_name], ["No. Referensi", detail.manual_number], ["Catatan", detail.notes],
                  ]} />
                  <div className="space-y-2" data-testid="handover-detail-items">
                    <p className="text-sm font-semibold">Aset ({detail.items?.length || 0})</p>
                    {(detail.items || []).map((i) => (
                      <div key={i.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border px-3 py-2">
                        <div className="text-sm"><span className="font-medium">{i.asset_code}</span> · {i.asset_name}
                          <span className="block text-[12px] text-muted-foreground">Kondisi: {i.condition_name || "-"} · Kelengkapan: {i.accessories || "-"}</span>
                        </div>
                        <StateBadge state={i.lifecycle_state} />
                      </div>
                    ))}
                  </div>
                </>
              )}
              {detail.doc_state === "DRAFT" && (
                <div className="flex flex-wrap gap-2 border-t border-border pt-4">
                  {perms.edit && (
                    <Button variant="outline" onClick={() => openEdit(detail)} data-testid="handover-edit-button"><Pencil className="mr-2 h-4 w-4" /> Ubah Draft</Button>
                  )}
                  {perms.edit && (
                    <Button variant="outline" onClick={() => setConfirm({ type: "cancel", doc: detail })} data-testid="handover-cancel-button">
                      <XCircle className="mr-2 h-4 w-4" /> Batalkan Draft
                    </Button>
                  )}
                  {perms.publish && (
                    <Button onClick={() => setConfirm({ type: "publish", doc: detail })} data-testid="handover-publish-button">
                      <Send className="mr-2 h-4 w-4" /> Publish &amp; Terbitkan BAST
                    </Button>
                  )}
                  {!perms.publish && (
                    <p className="flex items-center gap-2 text-[12px] text-muted-foreground" data-testid="handover-publish-hint">
                      <ClipboardCheck className="h-4 w-4" /> Publish dilakukan oleh pengguna dengan izin terbit penyerahan.
                    </p>
                  )}
                </div>
              )}
            </div>
          )}
        </SheetContent>
      </Sheet>

      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(o) => !o && !acting && !saving && setConfirm(null)}
        loading={acting || saving}
        destructive={confirm?.type === "cancel"}
        title={confirm?.type === "cancel" ? "Batalkan draft penyerahan?" : confirm?.type === "save_publish" ? "Simpan & publish penyerahan aset?" : "Publish penyerahan aset?"}
        description={
          confirm && confirm.type !== "cancel"
            ? `${confirm.doc.items?.length || 0} aset akan berstatus Dipakai oleh ${confirm.doc.employee_name || "karyawan"}, holding aktif dibuat, dan BAST Penyerahan terbit dengan nomor sistem. Tindakan ini tidak dapat dibatalkan; bila satu aset tidak lagi Siap Pakai, seluruh publish dibatalkan.`
            : "Draft akan ditandai dibatalkan dan tidak dapat dipublish."
        }
        confirmLabel={confirm?.type === "cancel" ? "Batalkan Draft" : confirm?.type === "save_publish" ? "Simpan & Publish" : "Publish"}
        onConfirm={runConfirm}
      />
    </PageBody>
  );
};

export default AssetHandoverPage;
