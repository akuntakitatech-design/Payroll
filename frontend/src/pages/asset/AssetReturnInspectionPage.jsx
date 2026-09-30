import React, { useCallback, useEffect, useRef, useState } from "react";
import { ClipboardCheck, Eye, Pencil, RefreshCw, Send, Undo2, XCircle } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate, formatDateTime } from "@/lib/format";
import { PageBody, SectionHeader } from "@/components/common/PageHeader";
import { AssetDocumentsPanel } from "@/pages/asset/AssetDocumentsPanel";
import TransactionAttachments from "@/pages/asset/TransactionAttachments";
import DataTable, { FilterBar, FilterSelect, Pagination, RowActions, TableCard } from "@/components/common/DataTable";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import EmptyState from "@/components/common/EmptyState";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  BastPdfActions, DetailButton, EmployeeSearchField, INSPECTION_RESULTS, InfoGrid, ItemField, STATE_META, SnapshotView, StateBadge,
  bastIssuedMessage, employeeLabel, todayIso,
} from "@/pages/asset/assetLifecycleShared";

// Phase 2A CP2 - Pengembalian (DRAFT -> PUBLISHED, parsial; BAST Pengembalian terbit saat publish) dan
// Pemeriksaan GA (PENDING_INSPECTION -> READY / MAINTENANCE / DAMAGED / LOST; LOST hanya bila dipilih eksplisit).
// CP2.1: pemilik izin `asset_return:publish` dapat "Simpan & Publish" (atomik di backend); karyawan dicari server-side.
const OPTS_PARAMS = { params: { include_employees: false } };

const usePaged = (path, params) => {
  const [state, setState] = useState({ rows: [], total: 0, loading: true, error: "" });
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(20);
  const key = JSON.stringify(params);
  const load = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: "" }));
    try {
      const { data } = await api.get(path, { params: { page, limit, ...JSON.parse(key) } });
      setState({ rows: data.items, total: data.total, loading: false, error: "" });
    } catch (e) {
      setState({ rows: [], total: 0, loading: false, error: errorMessage(e, "Data gagal dimuat.") });
    }
  }, [path, page, limit, key]);
  useEffect(() => {
    const t = setTimeout(load, 200);
    return () => clearTimeout(t);
  }, [load]);
  return { ...state, page, setPage, limit, setLimit, load };
};

const Paged = ({ data, columns, testId, emptyProps, onRowClick }) => (
  <TableCard>
    {data.error && !data.loading ? (
      <EmptyState testId={`${testId}-error`} icon={RefreshCw} title="Data gagal dimuat" description={data.error} actionLabel="Coba lagi" onAction={data.load} />
    ) : (
      <>
        <DataTable testId={testId} columns={columns} rows={data.rows} loading={data.loading} onRowClick={onRowClick} emptyProps={emptyProps} />
        <Pagination page={data.page} totalPages={Math.max(1, Math.ceil(data.total / data.limit))} total={data.total} limit={data.limit}
          onPageChange={data.setPage} onLimitChange={(v) => { data.setLimit(v); data.setPage(1); }} />
      </>
    )}
  </TableCard>
);

// ------------------------------------------------------------------ Tab Pengembalian
const ReturnsTab = ({ perms, onPublished }) => {
  const [search, setSearch] = useState("");
  const [docState, setDocState] = useState("");
  const data = usePaged("/asset-returns", { q: search || undefined, doc_state: docState || undefined });
  const [opts, setOpts] = useState(null);
  const [form, setForm] = useState(null);
  const [holdings, setHoldings] = useState([]);
  const [saving, setSaving] = useState(false);
  const [detail, setDetail] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [acting, setActing] = useState(false);
  const attachRef = useRef(null);

  const loadHoldings = async (employeeId) => {
    setHoldings([]);
    if (!employeeId) return;
    try {
      const { data: d } = await api.get("/asset-holdings", { params: { employee_id: employeeId } });
      setHoldings(d.items);
    } catch (e) {
      toast.error(errorMessage(e, "Aset yang dipegang karyawan gagal dimuat."));
    }
  };

  const openCreate = async () => {
    try {
      const { data: o } = await api.get("/asset-returns/options", OPTS_PARAMS);
      setOpts(o);
      setHoldings([]);
      setForm({ mode: "create", values: { employee_id: "", employee: null, return_date: todayIso(), ga_pic_name: o.ga_pic_name || "", manual_number: "", notes: "", items: {} } });
    } catch (e) {
      toast.error(errorMessage(e, "Pilihan pengembalian gagal dimuat."));
    }
  };

  const openEdit = async (doc) => {
    try {
      const [{ data: o }, { data: full }] = await Promise.all([api.get("/asset-returns/options", OPTS_PARAMS), api.get(`/asset-returns/${doc.id}`)]);
      setOpts(o);
      await loadHoldings(full.employee_id);
      const items = {};
      (full.items || []).forEach((i) => { items[i.holding_id] = { condition_id: i.condition_id || "", accessories: i.accessories || "", item_notes: i.item_notes || "" }; });
      setDetail(null);
      setForm({ mode: "edit", id: full.id, values: { employee_id: full.employee_id,
        employee: { id: full.employee_id, full_name: full.employee_name, employee_number: full.employee_number }, return_date: full.return_date, ga_pic_name: full.ga_pic_name || "",
        manual_number: full.manual_number || "", notes: full.notes || "", items } });
    } catch (e) {
      toast.error(errorMessage(e, "Draft pengembalian gagal dimuat."));
    }
  };

  const setVal = (k, v) => setForm((f) => ({ ...f, values: { ...f.values, [k]: v } }));
  const toggleHolding = (h, checked) => setForm((f) => {
    const items = { ...f.values.items };
    if (checked) items[h.id] = { condition_id: h.condition_id || "", accessories: h.accessories_out || "", item_notes: "" };
    else delete items[h.id];
    return { ...f, values: { ...f.values, items } };
  });
  const setItem = (hid, k, v) => setForm((f) => ({ ...f, values: { ...f.values, items: { ...f.values.items, [hid]: { ...f.values.items[hid], [k]: v } } } }));

  const validateForm = (v) => {
    const ids = Object.keys(v.items);
    if (!v.employee_id) { toast.error("Karyawan wajib dipilih."); return false; }
    if (!ids.length) { toast.error("Pilih minimal satu aset yang dikembalikan."); return false; }
    if (ids.some((id) => !v.items[id].condition_id)) { toast.error("Kondisi saat dikembalikan wajib diisi untuk setiap aset."); return false; }
    return true;
  };
  const buildBody = (v) => ({ employee_id: v.employee_id, return_date: v.return_date, ga_pic_name: v.ga_pic_name || null, manual_number: v.manual_number || null,
    notes: v.notes || null, items: Object.keys(v.items).map((id) => ({ holding_id: id, ...v.items[id] })) });

  // Simpan & Publish: satu operasi atomik di backend. Gagal -> tidak ada perubahan tersimpan; input form dipertahankan.
  const saveAndPublish = async () => {
    setSaving(true);
    try {
      const body = buildBody(form.values);
      const { data: d } = form.mode === "create"
        ? await api.post("/asset-returns/save-and-publish", body)
        : await api.post(`/asset-returns/${form.id}/save-and-publish`, body);
      toast.success(`${bastIssuedMessage(d.bast_number)}. Aset menunggu pemeriksaan.`);
      const res = attachRef.current ? await attachRef.current.flushPending(d.id, d.doc_state) : { uploaded: 0, failed: 0 };
      if (res.failed > 0) {
        toast.warning(`Transaksi berhasil disimpan. ${res.failed} lampiran gagal diunggah. Silakan coba unggah kembali dari panel Dokumen.`, { duration: 9000 });
      }
      setConfirm(null);
      setForm(null);
      setDetail(d);
      onPublished?.();
      data.load();
    } catch (e) {
      setConfirm(null);
      toast.error(errorMessage(e, "Simpan & Publish gagal. Tidak ada perubahan yang disimpan; periksa isian lalu coba lagi."), { duration: 9000 });
    } finally {
      setSaving(false);
    }
  };

  const save = async () => {
    const v = form.values;
    if (!validateForm(v)) return;
    setSaving(true);
    const body = buildBody(v);
    try {
      const { data: d } = form.mode === "create" ? await api.post("/asset-returns", body) : await api.put(`/asset-returns/${form.id}`, body);
      toast.success(form.mode === "create" ? "Draft pengembalian disimpan." : "Draft pengembalian diperbarui.");
      if (d.manual_number_warning) toast.warning(d.manual_number_warning, { duration: 9000 });
      const res = attachRef.current ? await attachRef.current.flushPending(d.id, d.doc_state) : { uploaded: 0, failed: 0 };
      if (res.failed > 0) {
        toast.warning(`Transaksi berhasil disimpan. ${res.failed} lampiran gagal diunggah. Silakan coba unggah kembali.`, { duration: 9000 });
        setForm((f) => (f ? { ...f, mode: "edit", id: d.id } : f));
      } else {
        setForm(null);
        setDetail(d);
      }
      data.load();
    } catch (e) {
      toast.error(errorMessage(e, "Draft pengembalian gagal disimpan."), { duration: 9000 });
    } finally {
      setSaving(false);
    }
  };

  const openDetail = async (row) => {
    try {
      setDetail((await api.get(`/asset-returns/${row.id}`)).data);
    } catch (e) {
      toast.error(errorMessage(e, "Detail pengembalian gagal dimuat."));
    }
  };

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

  const runConfirm = async () => {
    const { type, doc } = confirm;
    if (type === "save_publish") return saveAndPublish();
    setActing(true);
    try {
      if (type === "publish") {
        const { data: d } = await api.post(`/asset-returns/${doc.id}/publish`);
        toast.success(`${bastIssuedMessage(d.bast_number)}. Aset menunggu pemeriksaan.`);
        setDetail(d);
        onPublished?.();
      } else {
        await api.post(`/asset-returns/${doc.id}/cancel`);
        toast.success("Draft pengembalian dibatalkan.");
        setDetail(null);
      }
      setConfirm(null);
      data.load();
    } catch (e) {
      toast.error(errorMessage(e, type === "publish" ? "Publish pengembalian gagal." : "Pembatalan gagal."), { duration: 9000 });
      setConfirm(null);
    } finally {
      setActing(false);
    }
  };

  const columns = [
    { key: "bast_number", header: "Nomor BAST", render: (r) => <span className="font-medium tabular-nums">{r.bast_number || "—"}</span> },
    { key: "return_date", header: "Tanggal", render: (r) => formatDate(r.return_date) },
    { key: "employee_name", header: "Karyawan", render: (r) => employeeLabel({ full_name: r.employee_name, employee_number: r.employee_number }) },
    { key: "project_name", header: "Project", hideOnMobile: true, render: (r) => r.project_name || "-" },
    { key: "doc_state", header: "Status", render: (r) => <StateBadge state={r.doc_state} testId={`return-state-${r.id}`} /> },
    { key: "actions", header: "", align: "right", render: (r) => (
      <div className="flex items-center justify-end gap-1">
        <DetailButton onClick={() => openDetail(r)} testId={`return-detail-button-${r.id}`} />
        <RowActions testId={`return-row-actions-${r.id}`} actions={[
          { key: "view", label: "Lihat detail", icon: Eye, onSelect: () => openDetail(r), testId: `return-view-${r.id}` },
          r.doc_state === "DRAFT" && perms.returnEdit && { key: "edit", label: "Ubah draft", icon: Pencil, onSelect: () => openEdit(r), testId: `return-edit-${r.id}` },
        ]} />
      </div>
    ) },
  ];
  const v = form?.values;
  // Simpan & Publish = izin simpan (create untuk form baru / edit untuk draft) + izin publish (permission efektif).
  const canSavePublish = !!form && perms.returnPublish && (form.mode === "create" ? perms.returnCreate : perms.returnEdit);
  const selectedCount = v ? Object.keys(v.items).length : 0;

  return (
    <div className="space-y-4" data-testid="asset-return-tab">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">Pengembalian boleh sebagian. Aset yang tidak dikembalikan tetap Dipakai.</p>
        {perms.returnCreate && (
          <Button onClick={openCreate} data-testid="return-add-button"><Undo2 className="mr-2 h-4 w-4" /> Buat Pengembalian</Button>
        )}
      </div>
      <FilterBar search={search} onSearchChange={(x) => { setSearch(x); data.setPage(1); }} searchPlaceholder="Cari nomor BAST, referensi, atau karyawan…"
        showReset={!!(search || docState)} onReset={() => { setSearch(""); setDocState(""); data.setPage(1); }}>
        <FilterSelect label="Status" value={docState} onChange={(x) => { setDocState(x); data.setPage(1); }} allLabel="Semua status" testId="return-filter-state"
          options={[{ value: "DRAFT", label: "Draft" }, { value: "PUBLISHED", label: "Terbit" }, { value: "CANCELLED", label: "Dibatalkan" }]} />
      </FilterBar>
      <Paged data={data} columns={columns} testId="return-table" onRowClick={openDetail}
        emptyProps={{ icon: Undo2, testId: "return-list-empty", title: "Belum ada pengembalian", description: "Buat pengembalian saat karyawan menyerahkan kembali aset ke GA." }} />

      <Dialog open={!!form} onOpenChange={(o) => !o && !saving && !confirm && setForm(null)}>
        <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-3xl" data-testid="return-form-dialog">
          <DialogHeader>
            <DialogTitle>{form?.mode === "edit" ? "Ubah Draft Pengembalian" : "Buat Pengembalian"}</DialogTitle>
            <DialogDescription>
              Pilih karyawan, lalu centang aset yang benar-benar dikembalikan. Satu pengembalian untuk aset dari project yang sama.
              {canSavePublish ? " Simpan & Publish langsung menerbitkan BAST Pengembalian." : ""}
            </DialogDescription>
          </DialogHeader>
          {v && (
            <div className="space-y-5">
              <div className="grid gap-4 sm:grid-cols-2">
                <EmployeeSearchField label="Karyawan pemegang aset" required endpoint="/asset-returns/employee-search" value={v.employee_id}
                  selected={v.employee} disabled={form.mode === "edit"} testId="return-employee-select"
                  hint="Hanya karyawan yang sedang memegang aset aktif."
                  onSelect={(e) => { setForm((f) => ({ ...f, values: { ...f.values, employee_id: e.id, employee: e, items: {} } })); loadHoldings(e.id); }} />
                <div className="space-y-1.5">
                  <Label htmlFor="rt-date">Tanggal pengembalian <span className="text-danger">*</span></Label>
                  <Input id="rt-date" type="date" value={v.return_date} onChange={(e) => setVal("return_date", e.target.value)} data-testid="return-date-input" />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="rt-pic">PIC GA penerima</Label>
                  <Input id="rt-pic" value={v.ga_pic_name} onChange={(e) => setVal("ga_pic_name", e.target.value)} data-testid="return-pic-input" />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="rt-ref">Nomor referensi (opsional)</Label>
                  <Input id="rt-ref" value={v.manual_number} onChange={(e) => setVal("manual_number", e.target.value)} data-testid="return-manual-number-input" />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="rt-notes">Catatan</Label>
                <Textarea id="rt-notes" rows={2} value={v.notes} onChange={(e) => setVal("notes", e.target.value)} data-testid="return-notes-input" />
              </div>
              <div className="space-y-2" data-testid="return-holding-picker">
                <p className="text-sm font-semibold">Aset yang sedang dipegang {selectedCount ? `(${selectedCount} dipilih)` : ""}</p>
                {!v.employee_id ? (
                  <p className="text-sm text-muted-foreground">Pilih karyawan terlebih dahulu.</p>
                ) : holdings.length === 0 ? (
                  <p className="text-sm text-muted-foreground" data-testid="return-holding-empty">Karyawan ini tidak memegang aset aktif.</p>
                ) : (
                  holdings.map((h) => {
                    const it = v.items[h.id];
                    return (
                      <div key={h.id} className={cn("rounded-md border border-border p-3", it && "border-primary/40 bg-primary-soft/30")}>
                        <label className="flex cursor-pointer items-start gap-3">
                          <Checkbox checked={!!it} onCheckedChange={(c) => toggleHolding(h, !!c)} data-testid={`return-holding-option-${h.id}`} />
                          <span className="min-w-0 flex-1 text-sm">
                            <span className="font-medium">{h.asset_code}</span> · {h.asset_name}
                            <span className="block text-[12px] text-muted-foreground">
                              SN: {h.serial_number || "-"} · Project: {h.project_name || "-"} · Diserahkan {formatDate(h.start_date)} ({h.bast_number || "-"})
                            </span>
                          </span>
                          <StateBadge state="IN_USE" />
                        </label>
                        {it && (
                          <div className="mt-3 grid gap-3 border-t border-border pt-3 sm:grid-cols-3" data-testid={`return-item-fields-${h.id}`}>
                            <p className="text-[12px] font-medium text-muted-foreground sm:col-span-3">Detail pengembalian {h.asset_code}</p>
                            <ItemField label="Kondisi saat kembali" required>
                              <Select value={it.condition_id} onValueChange={(x) => setItem(h.id, "condition_id", x)}>
                                <SelectTrigger className="h-9" aria-label={`Kondisi ${h.asset_code}`} data-testid={`return-item-condition-${h.id}`}><SelectValue placeholder="Pilih kondisi" /></SelectTrigger>
                                <SelectContent>{(opts?.conditions || []).map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
                              </Select>
                            </ItemField>
                            <ItemField label="Kelengkapan" htmlFor={`rt-acc-${h.id}`}>
                              <Input id={`rt-acc-${h.id}`} className="h-9" placeholder="Mis. charger, tas" value={it.accessories} onChange={(e) => setItem(h.id, "accessories", e.target.value)}
                                data-testid={`return-item-accessories-${h.id}`} />
                            </ItemField>
                            <ItemField label="Catatan" htmlFor={`rt-note-${h.id}`}>
                              <Input id={`rt-note-${h.id}`} className="h-9" placeholder="Opsional" value={it.item_notes} onChange={(e) => setItem(h.id, "item_notes", e.target.value)}
                                data-testid={`return-item-notes-${h.id}`} />
                            </ItemField>
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>

              <TransactionAttachments ref={attachRef} sourceType="RETURN"
                sourceId={form.mode === "edit" ? form.id : null} docState="DRAFT"
                disabled={saving} testId="return-attachments" />
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setForm(null)} disabled={saving} data-testid="return-form-cancel-button">Batal</Button>
            <Button variant={canSavePublish ? "outline" : "default"} onClick={save} disabled={saving} data-testid="return-form-save-button">
              {saving && !confirm ? "Menyimpan…" : "Simpan Draft"}
            </Button>
            {canSavePublish && (
              <Button onClick={() => validateForm(v) && setConfirm({ type: "save_publish", doc: { items: Object.keys(v.items) } })} disabled={saving}
                data-testid="return-form-save-publish-button">
                <Send className="mr-2 h-4 w-4" /> Simpan &amp; Publish
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Sheet open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-2xl" data-testid="return-detail-sheet">
          {detail && (
            <div className="space-y-5">
              <SheetHeader>
                <SheetTitle className="flex flex-wrap items-center gap-2">{detail.bast_number || "Draft Pengembalian"} <StateBadge state={detail.doc_state} testId="return-detail-state" /></SheetTitle>
                <SheetDescription>{detail.doc_state === "DRAFT" ? "Tinjau draft sebelum dipublish." : "Dokumen terbit bersifat final (read-only). Hasil pemeriksaan tidak mengubah BAST ini."}</SheetDescription>
              </SheetHeader>
              <AssetDocumentsPanel sourceType="RETURN" sourceId={detail.id} docState={detail.doc_state}
                assets={(detail.items || []).map((i) => ({ asset_id: i.asset_id, asset_code: i.asset_code, asset_name: i.asset_name }))}
                testId="return-doc-panel" />
              {detail.doc_state === "PUBLISHED" && detail.bast_snapshot ? (
                <>
                  <BastPdfActions bastId={detail.bast_id} systemNumber={detail.bast_number} testIdPrefix="return-bast" />
                  <SnapshotView snapshot={detail.bast_snapshot} testId="return-snapshot" />
                </>
              ) : (
                <>
                  <InfoGrid rows={[["Karyawan", employeeLabel({ full_name: detail.employee_name, employee_number: detail.employee_number })],
                    ["Tanggal", formatDate(detail.return_date)], ["Project", detail.project_name], ["PIC GA", detail.ga_pic_name],
                    ["No. Referensi", detail.manual_number], ["Catatan", detail.notes]]} />
                  <div className="space-y-2" data-testid="return-detail-items">
                    {(detail.items || []).map((i) => (
                      <div key={i.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border px-3 py-2 text-sm">
                        <span><span className="font-medium">{i.asset_code}</span> · {i.asset_name}
                          <span className="block text-[12px] text-muted-foreground">Kondisi kembali: {i.condition_name || "-"} · Kelengkapan: {i.accessories || "-"}</span></span>
                        <StateBadge state={i.lifecycle_state} />
                      </div>
                    ))}
                  </div>
                </>
              )}
              {detail.doc_state === "DRAFT" && (
                <div className="flex flex-wrap gap-2 border-t border-border pt-4">
                  {perms.returnEdit && <Button variant="outline" onClick={() => openEdit(detail)} data-testid="return-edit-button"><Pencil className="mr-2 h-4 w-4" /> Ubah Draft</Button>}
                  {perms.returnEdit && <Button variant="outline" onClick={() => setConfirm({ type: "cancel", doc: detail })} data-testid="return-cancel-button"><XCircle className="mr-2 h-4 w-4" /> Batalkan Draft</Button>}
                  {perms.returnPublish ? (
                    <Button onClick={() => setConfirm({ type: "publish", doc: detail })} data-testid="return-publish-button"><Send className="mr-2 h-4 w-4" /> Publish &amp; Terbitkan BAST</Button>
                  ) : (
                    <p className="flex items-center gap-2 text-[12px] text-muted-foreground" data-testid="return-publish-hint"><ClipboardCheck className="h-4 w-4" /> Publish dilakukan oleh pengguna dengan izin terbit pengembalian.</p>
                  )}
                </div>
              )}
            </div>
          )}
        </SheetContent>
      </Sheet>
      <ConfirmDialog open={!!confirm} onOpenChange={(o) => !o && !acting && !saving && setConfirm(null)} loading={acting || saving} destructive={confirm?.type === "cancel"}
        title={confirm?.type === "cancel" ? "Batalkan draft pengembalian?" : confirm?.type === "save_publish" ? "Simpan & publish pengembalian aset?" : "Publish pengembalian aset?"}
        description={confirm && confirm.type !== "cancel"
          ? `${confirm.doc.items?.length || 0} aset akan ditutup holding-nya, berstatus Menunggu Pemeriksaan, dan BAST Pengembalian terbit sekarang. Aset lain milik karyawan tetap Dipakai. Tindakan ini tidak dapat dibatalkan.`
          : "Draft akan ditandai dibatalkan."}
        confirmLabel={confirm?.type === "cancel" ? "Batalkan Draft" : confirm?.type === "save_publish" ? "Simpan & Publish" : "Publish"} onConfirm={runConfirm} />
    </div>
  );
};

// ------------------------------------------------------------------ Tab Pemeriksaan
const InspectionTab = ({ state, perms, refreshKey }) => {
  const [search, setSearch] = useState("");
  const data = usePaged("/asset-inspections", { inspection_state: state, q: search || undefined, _r: refreshKey });
  const [conditions, setConditions] = useState([]);
  const [current, setCurrent] = useState(null);
  const [values, setValues] = useState({});
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const pending = state === "PENDING";

  const open = async (row) => {
    try {
      if (!conditions.length) {
        const { data: o } = await api.get("/asset-returns/options", OPTS_PARAMS);
        setConditions(o.conditions || []);
      }
    } catch { /* pilihan kondisi opsional untuk tampilan */ }
    setCurrent(row);
    setValues({ final_condition_id: row.final_condition_id || "", completeness: row.completeness || "", notes: row.notes || "", result_state: row.result_state || "" });
  };

  const saveInput = async () => {
    setBusy(true);
    try {
      const { data: d } = await api.put(`/asset-inspections/${current.id}`, {
        final_condition_id: values.final_condition_id || null, completeness: values.completeness || null, notes: values.notes || null,
        result_state: values.result_state || null });
      toast.success("Input pemeriksaan disimpan.");
      setCurrent(d);
      data.load();
    } catch (e) {
      toast.error(errorMessage(e, "Input pemeriksaan gagal disimpan."), { duration: 9000 });
    } finally {
      setBusy(false);
    }
  };

  const complete = async () => {
    setBusy(true);
    try {
      const { data: d } = await api.post(`/asset-inspections/${current.id}/complete`, {
        result_state: values.result_state, final_condition_id: values.final_condition_id || null,
        completeness: values.completeness || null, notes: values.notes || null });
      toast.success(`Pemeriksaan selesai. Aset ${d.asset_code} kini ${STATE_META[d.result_state]?.label || d.result_state}.`);
      setConfirm(false);
      setCurrent(null);
      data.load();
    } catch (e) {
      toast.error(errorMessage(e, "Pemeriksaan gagal diselesaikan."), { duration: 9000 });
      setConfirm(false);
    } finally {
      setBusy(false);
    }
  };

  const columns = [
    { key: "asset_code", header: "Aset", render: (r) => <span><span className="font-medium">{r.asset_code}</span><span className="block text-[12px] text-muted-foreground">{r.asset_name}</span></span> },
    { key: "employee_name", header: "Karyawan sebelumnya", render: (r) => employeeLabel({ full_name: r.employee_name, employee_number: r.employee_number }) },
    { key: "return_date", header: "Tgl kembali", render: (r) => formatDate(r.return_date) },
    { key: "bast_number", header: "BAST Pengembalian", hideOnMobile: true, render: (r) => r.bast_number || "-" },
    pending
      ? { key: "returned_condition_name", header: "Kondisi kembali", hideOnMobile: true, render: (r) => r.returned_condition_name || "-" }
      : { key: "completed_at", header: "Selesai", hideOnMobile: true, render: (r) => formatDateTime(r.completed_at) },
    { key: "state", header: pending ? "Status aset" : "Hasil akhir", render: (r) => <StateBadge state={pending ? r.lifecycle_state : r.result_state} testId={`inspection-state-${r.id}`} /> },
    { key: "actions", header: "", align: "right", render: (r) => (
      <DetailButton onClick={() => open(r)} label={pending ? "Periksa" : "Detail"} testId={`inspection-detail-button-${r.id}`} />
    ) },
  ];
  const canSave = pending && (current?.inspected_by ? perms.inspEdit : perms.inspCreate);

  return (
    <div className="space-y-4" data-testid={pending ? "inspection-pending-tab" : "inspection-completed-tab"}>
      <FilterBar search={search} onSearchChange={(x) => { setSearch(x); data.setPage(1); }} searchPlaceholder="Cari kode/nama/serial aset atau karyawan…"
        showReset={!!search} onReset={() => setSearch("")} />
      <Paged data={data} columns={columns} testId={pending ? "inspection-pending-table" : "inspection-completed-table"} onRowClick={open}
        emptyProps={{ icon: ClipboardCheck, testId: pending ? "inspection-pending-empty" : "inspection-completed-empty",
          title: pending ? "Tidak ada aset yang menunggu pemeriksaan" : "Belum ada pemeriksaan selesai",
          description: pending ? "Aset masuk ke antrean ini setelah pengembalian dipublish." : "Riwayat hasil pemeriksaan akan tampil di sini." }} />

      <Dialog open={!!current} onOpenChange={(o) => !o && !busy && setCurrent(null)}>
        <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-xl" data-testid="inspection-dialog">
          {current && (
            <>
              <DialogHeader>
                <DialogTitle>Pemeriksaan {current.asset_code}</DialogTitle>
                <DialogDescription>{current.asset_name} · dikembalikan {formatDate(current.return_date)} oleh {current.employee_name || "-"} ({current.bast_number || "-"})</DialogDescription>
              </DialogHeader>
              {!pending ? (
                <InfoGrid testId="inspection-completed-detail" rows={[["Hasil akhir", <StateBadge key="r" state={current.result_state} />],
                  ["Kondisi akhir", current.final_condition_name], ["Kelengkapan", current.completeness], ["Catatan", current.notes],
                  ["Diselesaikan", formatDateTime(current.completed_at)]]} />
              ) : (
                <div className="space-y-4">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-1.5">
                      <Label>Kondisi akhir</Label>
                      <Select value={values.final_condition_id} onValueChange={(x) => setValues((s) => ({ ...s, final_condition_id: x }))} disabled={!canSave && !perms.inspComplete}>
                        <SelectTrigger data-testid="inspection-condition-select"><SelectValue placeholder="Pilih kondisi" /></SelectTrigger>
                        <SelectContent>{conditions.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="insp-comp">Kelengkapan</Label>
                      <Input id="insp-comp" value={values.completeness} onChange={(e) => setValues((s) => ({ ...s, completeness: e.target.value }))}
                        disabled={!canSave && !perms.inspComplete} data-testid="inspection-completeness-input" />
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="insp-notes">Catatan pemeriksaan</Label>
                    <Textarea id="insp-notes" rows={2} value={values.notes} onChange={(e) => setValues((s) => ({ ...s, notes: e.target.value }))}
                      disabled={!canSave && !perms.inspComplete} data-testid="inspection-notes-input" />
                  </div>
                  <div className="space-y-2">
                    <Label>Hasil akhir (wajib dipilih eksplisit)</Label>
                    <RadioGroup value={values.result_state} onValueChange={(x) => setValues((s) => ({ ...s, result_state: x }))} className="grid gap-2 sm:grid-cols-2"
                      data-testid="inspection-result-group">
                      {INSPECTION_RESULTS.map((r) => (
                        <label key={r.value} htmlFor={`res-${r.value}`} className={cn("flex cursor-pointer items-start gap-2 rounded-md border border-border p-2.5",
                          values.result_state === r.value && "border-primary bg-primary-soft/40")}>
                          <RadioGroupItem id={`res-${r.value}`} value={r.value} data-testid={`inspection-result-${r.value}`} />
                          <span className="text-sm"><span className="font-medium">{r.label}</span><span className="block text-[12px] text-muted-foreground">{r.help}</span></span>
                        </label>
                      ))}
                    </RadioGroup>
                    {values.result_state === "LOST" && (
                      <Alert data-testid="inspection-lost-warning"><AlertDescription>Hasil Hilang dipilih secara eksplisit. Pastikan aset memang tidak kembali; kondisi buruk atau kelengkapan kurang bukan alasan status Hilang.</AlertDescription></Alert>
                    )}
                  </div>
                </div>
              )}
              <DialogFooter className="gap-2">
                <Button variant="outline" onClick={() => setCurrent(null)} disabled={busy} data-testid="inspection-close-button">Tutup</Button>
                {pending && canSave && <Button variant="outline" onClick={saveInput} disabled={busy} data-testid="inspection-save-button">Simpan Input</Button>}
                {pending && perms.inspComplete && (
                  <Button onClick={() => {
                    if (!values.result_state) return toast.error("Pilih hasil akhir pemeriksaan secara eksplisit.");
                    if (!values.final_condition_id) return toast.error("Kondisi akhir wajib dipilih.");
                    return setConfirm(true);
                  }} disabled={busy} data-testid="inspection-complete-button">Selesaikan Pemeriksaan</Button>
                )}
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
      <ConfirmDialog open={confirm} onOpenChange={(o) => !o && !busy && setConfirm(false)} loading={busy} destructive={values.result_state === "LOST"}
        title="Selesaikan pemeriksaan?"
        description={`Status aset ${current?.asset_code || ""} akan menjadi ${STATE_META[values.result_state]?.label || "-"}. Hasil pemeriksaan final dan tidak dapat diubah. BAST Pengembalian tidak berubah.`}
        confirmLabel="Selesaikan" onConfirm={complete} />
    </div>
  );
};

const AssetReturnInspectionPage = () => {
  const { can } = useAuth();
  const perms = {
    returnView: can("asset_return", "view"), returnCreate: can("asset_return", "create"), returnEdit: can("asset_return", "edit"),
    returnPublish: can("asset_return", "publish"), inspView: can("asset_inspection", "view"), inspCreate: can("asset_inspection", "create"),
    inspEdit: can("asset_inspection", "edit"), inspComplete: can("asset_inspection", "complete"),
  };
  const [tab, setTab] = useState(perms.returnView ? "returns" : "pending");
  const [refreshKey, setRefreshKey] = useState(0);
  return (
    <PageBody className="space-y-4">
      <div className="space-y-4" data-testid="asset-return-inspection-page">
        <SectionHeader title="Pengembalian & Pemeriksaan"
          description="Karyawan mengembalikan aset ke GA (BAST Pengembalian terbit saat publish), lalu GA memeriksa dan menentukan status akhir aset." />
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList data-testid="return-inspection-tabs">
            {perms.returnView && <TabsTrigger value="returns" data-testid="tab-returns">Pengembalian</TabsTrigger>}
            {perms.inspView && <TabsTrigger value="pending" data-testid="tab-pending-inspection">Menunggu Pemeriksaan</TabsTrigger>}
            {perms.inspView && <TabsTrigger value="completed" data-testid="tab-completed-inspection">Selesai</TabsTrigger>}
          </TabsList>
          {perms.returnView && <TabsContent value="returns" className="mt-4"><ReturnsTab perms={perms} onPublished={() => setRefreshKey((k) => k + 1)} /></TabsContent>}
          {perms.inspView && <TabsContent value="pending" className="mt-4"><InspectionTab state="PENDING" perms={perms} refreshKey={refreshKey} /></TabsContent>}
          {perms.inspView && <TabsContent value="completed" className="mt-4"><InspectionTab state="COMPLETED" perms={perms} refreshKey={refreshKey} /></TabsContent>}
        </Tabs>
      </div>
    </PageBody>
  );
};

export default AssetReturnInspectionPage;
