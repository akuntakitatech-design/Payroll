import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors } from "@dnd-kit/core";
import { SortableContext, arrayMove, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Eye, EyeOff, Filter, GripVertical, Lock, Pencil, Plus, Save, Trash2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { FORCED_LABEL, FormPreview, LEVEL_BADGE as LEVEL_CLS, TYPE_LABELS } from "@/components/employee-form/FormPreview";

const BASE = "/employees/update-form";
const LEVEL_LABELS = { REQUIRED: "Wajib", RECOMMENDED: "Anjuran", OPTIONAL: "Opsional" };

/** Confirmation before deactivating / hiding (reversible, but affects what employees see). */
const ConfirmDialog = ({ confirm, onClose }) => (
  <AlertDialog open={!!confirm} onOpenChange={(o) => !o && onClose()}>
    <AlertDialogContent data-testid="fb-confirm-dialog">
      <AlertDialogHeader><AlertDialogTitle>{confirm?.title}</AlertDialogTitle><AlertDialogDescription>{confirm?.description}</AlertDialogDescription></AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel data-testid="fb-confirm-cancel">Batal</AlertDialogCancel>
        <AlertDialogAction onClick={async () => { const run = confirm?.action; onClose(); if (run) await run(); }} data-testid="fb-confirm-ok">{confirm?.confirmLabel || "Ya, lanjutkan"}</AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
);

const Sortable = ({ id, children, testid }) => {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });
  const style = { transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.6 : 1 };
  return (
    <div ref={setNodeRef} style={style} data-testid={testid}>
      {children(
        <button type="button" className="flex h-10 w-8 shrink-0 cursor-grab items-center justify-center rounded-md text-muted-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:cursor-grabbing"
          aria-label="Seret untuk mengubah urutan (Spasi lalu panah atas/bawah)" data-testid={`${testid}-handle`} {...attributes} {...listeners}><GripVertical className="h-4 w-4" /></button>
      )}
    </div>
  );
};

export const FormBuilderSettings = ({ onChanged }) => {
  const [cfg, setCfg] = useState(null);
  const [order, setOrder] = useState(null); // {sections: [key], fields: {sectionKey: [fieldKey]}}
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [fieldDlg, setFieldDlg] = useState(null);
  const [sectionDlg, setSectionDlg] = useState(null);
  const [scopeDlg, setScopeDlg] = useState(null);
  const [preview, setPreview] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));

  const load = useCallback(async () => {
    try {
      const { data } = await api.get(`${BASE}/config`);
      setCfg(data);
      const fields = {};
      data.sections.forEach((s) => { fields[s.key] = data.fields.filter((f) => f.section === s.key).map((f) => f.key); });
      setOrder({ sections: data.sections.map((s) => s.key), fields });
      setDirty(false);
      if (onChanged) onChanged();
    } catch (e) { toast.error(errorMessage(e)); }
  }, [onChanged]);
  useEffect(() => { load(); }, [load]);

  const secBy = useMemo(() => Object.fromEntries((cfg?.sections || []).map((s) => [s.key, s])), [cfg]);
  const fieldBy = useMemo(() => Object.fromEntries((cfg?.fields || []).map((f) => [f.key, f])), [cfg]);

  const onSectionDrag = ({ active, over }) => {
    if (!over || active.id === over.id) return;
    setOrder((o) => ({ ...o, sections: arrayMove(o.sections, o.sections.indexOf(active.id), o.sections.indexOf(over.id)) }));
    setDirty(true);
  };
  const onFieldDrag = (sec) => ({ active, over }) => {
    if (!over || active.id === over.id) return;
    setOrder((o) => { const l = o.fields[sec]; return { ...o, fields: { ...o.fields, [sec]: arrayMove(l, l.indexOf(active.id), l.indexOf(over.id)) } }; });
    setDirty(true);
  };
  const saveLayout = async () => {
    setSaving(true);
    try {
      await api.put(`${BASE}/layout`, { sections: order.sections.map((k) => ({ key: k, fields: secBy[k]?.kind === "fields" ? order.fields[k] || [] : [] })) });
      toast.success("Urutan form disimpan."); await load();
    } catch (e) { toast.error(errorMessage(e)); } finally { setSaving(false); }
  };
  const patchField = async (key, body, msg = "Field diperbarui.") => {
    try { await api.put(`${BASE}/fields/${key}`, body); toast.success(msg); await load(); } catch (e) { toast.error(errorMessage(e)); }
  };
  const patchSection = async (key, body) => {
    try { await api.put(`${BASE}/sections/${key}`, body); toast.success("Section diperbarui."); await load(); } catch (e) { toast.error(errorMessage(e)); }
  };
  const openPreview = async () => {
    try { const { data } = await api.get(`${BASE}/preview`); setPreview(data); } catch (e) { toast.error(errorMessage(e)); }
  };

  if (!cfg || !order) return <div className="space-y-3" data-testid="form-builder-loading"><Skeleton className="h-10 w-1/2" /><Skeleton className="h-48 w-full" /></div>;
  return (
    <div className="space-y-4" data-testid="form-builder">
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => setSectionDlg({})} variant="outline" data-testid="fb-add-section"><Plus className="mr-1.5 h-4 w-4" />Tambah Section</Button>
        <Button onClick={() => setFieldDlg({ create: true })} data-testid="fb-add-field"><Plus className="mr-1.5 h-4 w-4" />Tambah Custom Field</Button>
        <Button onClick={openPreview} variant="outline" data-testid="fb-preview"><Eye className="mr-1.5 h-4 w-4" />Preview Form</Button>
        {dirty && <Button onClick={saveLayout} disabled={saving} className="ml-auto" data-testid="fb-save-layout"><Save className="mr-1.5 h-4 w-4" />Simpan Urutan</Button>}
      </div>
      <p className="text-sm text-muted-foreground" data-testid="fb-core-note">{cfg.notes.core_level} {cfg.notes.forced}</p>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onSectionDrag}>
        <SortableContext items={order.sections} strategy={verticalListSortingStrategy}>
          <div className="space-y-3">
            {order.sections.map((sk) => {
              const s = secBy[sk];
              if (!s) return null;
              return (
                <Sortable key={sk} id={sk} testid={`fb-section-${sk}`}>{(handle) => (
                  <Card className={s.active ? "" : "opacity-70"}>
                    <CardHeader className="flex flex-row flex-wrap items-center gap-2 space-y-0 p-3 sm:p-4">
                      {handle}
                      <CardTitle className="text-base" data-testid={`fb-section-title-${sk}`}>{s.label}</CardTitle>
                      <Badge variant="outline">{s.is_system ? "Sistem" : "Custom"}</Badge>
                      {s.kind !== "fields" && <Badge variant="secondary">{s.kind === "family" ? "Daftar keluarga" : "Unggah dokumen"}</Badge>}
                      {!s.active && <Badge variant="secondary" data-testid={`fb-section-inactive-${sk}`}>Nonaktif</Badge>}
                      {s.kind === "fields" && <Badge variant="outline" className="text-[11px]" data-testid={`fb-section-count-${sk}`}>{(order.fields[sk] || []).length} field</Badge>}
                      <div className="ml-auto flex items-center gap-2">
                        <Button size="sm" variant="ghost" onClick={() => setSectionDlg(s)} aria-label={`Ubah nama section ${s.label}`} data-testid={`fb-section-edit-${sk}`}><Pencil className="h-4 w-4" /></Button>
                        <Switch checked={s.active} onCheckedChange={(v) => (v ? patchSection(sk, { active: true }) : setConfirm({
                          title: `Nonaktifkan section "${s.label}"?`, confirmLabel: "Nonaktifkan",
                          description: "Section dan field di dalamnya tidak ditampilkan di form karyawan. Field inti yang Wajib menurut aturan kelengkapan tetap ditampilkan. Data lama tidak dihapus dan section dapat diaktifkan kembali.",
                          action: () => patchSection(sk, { active: false }) }))} aria-label={`Aktifkan section ${s.label}`} data-testid={`fb-section-active-${sk}`} />
                      </div>
                    </CardHeader>
                    {s.kind === "fields" && (
                      <CardContent className="p-3 pt-0 sm:p-4 sm:pt-0">
                        {(order.fields[sk] || []).length === 0 && <p className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground">Belum ada field. Pindahkan field ke section ini melalui tombol Edit pada field.</p>}
                        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onFieldDrag(sk)}>
                          <SortableContext items={order.fields[sk] || []} strategy={verticalListSortingStrategy}>
                            <ul className="divide-y rounded-lg border">
                              {(order.fields[sk] || []).map((fk) => {
                                const f = fieldBy[fk];
                                if (!f) return null;
                                return (
                                  <Sortable key={fk} id={fk} testid={`fb-field-${fk}`}>{(h) => (
                                    <li className={`flex flex-wrap items-center gap-2 px-2 py-2 ${!f.active || !f.visible ? "bg-muted/40" : ""}`}>
                                      {h}
                                      <div className="min-w-0 flex-1">
                                        <p className="truncate text-sm font-medium" data-testid={`fb-field-label-${fk}`}>{f.label}</p>
                                        <div className="mt-0.5 flex flex-wrap gap-1">
                                          <Badge variant="outline" className="text-[11px]">{f.source === "CORE" ? <><Lock className="mr-1 h-3 w-3" />Inti</> : `Custom · ${TYPE_LABELS[f.type]}`}</Badge>
                                          <Badge variant="outline" className={`text-[11px] ${LEVEL_CLS[f.level_label] || ""}`} data-testid={`fb-field-level-${fk}`}>{f.level_label}</Badge>
                                          {!f.visible && <Badge variant="secondary" className="text-[11px]">Disembunyikan</Badge>}
                                          {f.forced_when_hidden && <Badge variant="outline" className="border-warning-border bg-warning-soft text-[11px] text-warning" data-testid={`fb-field-forced-${fk}`}>{FORCED_LABEL}</Badge>}
                                          {!f.active && <Badge variant="secondary" className="text-[11px]" data-testid={`fb-field-inactive-${fk}`}>Nonaktif</Badge>}
                                          {f.scopes.length > 0 && <Badge variant="secondary" className="text-[11px]">Scope: {f.scopes.length}</Badge>}
                                        </div>
                                      </div>
                                      <Button size="sm" variant="ghost" onClick={() => (f.visible ? setConfirm({
                                        title: `Sembunyikan "${f.label}"?`, confirmLabel: "Sembunyikan",
                                        description: f.source === "CORE" && f.level === "REQUIRED"
                                          ? "Field ini Wajib menurut aturan kelengkapan (01F), sehingga tetap ditampilkan kepada karyawan yang diwajibkan walaupun disembunyikan."
                                          : "Field tidak ditampilkan dan tidak dapat diubah dari form karyawan. Data yang sudah ada tidak dihapus.",
                                        action: () => patchField(fk, { visible: false }, "Field disembunyikan.") }) : patchField(fk, { visible: true }, "Field ditampilkan."))} aria-label={f.visible ? `Sembunyikan ${f.label}` : `Tampilkan ${f.label}`} data-testid={`fb-field-visible-${fk}`}>{f.visible ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}</Button>
                                      <Button size="sm" variant="ghost" onClick={() => setScopeDlg(f)} aria-label={`Atur scope ${f.label}`} data-testid={`fb-field-scope-${fk}`}><Filter className="h-4 w-4" /></Button>
                                      <Button size="sm" variant="ghost" onClick={() => setFieldDlg(f)} aria-label={`Edit ${f.label}`} data-testid={`fb-field-edit-${fk}`}><Pencil className="h-4 w-4" /></Button>
                                    </li>
                                  )}</Sortable>
                                );
                              })}
                            </ul>
                          </SortableContext>
                        </DndContext>
                      </CardContent>
                    )}
                  </Card>
                )}</Sortable>
              );
            })}
          </div>
        </SortableContext>
      </DndContext>
      {sectionDlg && <SectionDialog section={sectionDlg} onClose={() => setSectionDlg(null)} onSaved={load} />}
      {fieldDlg && <FieldDialog field={fieldDlg} cfg={cfg} onClose={() => setFieldDlg(null)} onSaved={load} askConfirm={setConfirm} />}
      {scopeDlg && <ScopeDialog field={fieldBy[scopeDlg.key] || scopeDlg} cfg={cfg} onClose={() => setScopeDlg(null)} onSaved={load} />}
      {preview && <PreviewDialog data={preview} onClose={() => setPreview(null)} />}
      <ConfirmDialog confirm={confirm} onClose={() => setConfirm(null)} />
    </div>
  );
};

const SectionDialog = ({ section, onClose, onSaved }) => {
  const [label, setLabel] = useState(section.label || "");
  const [desc, setDesc] = useState(section.description || "");
  const save = async () => {
    try {
      if (section.key) await api.put(`${BASE}/sections/${section.key}`, { label, description: desc });
      else await api.post(`${BASE}/sections`, { label, description: desc || null });
      toast.success(section.key ? "Section diperbarui." : "Section ditambahkan."); onClose(); onSaved();
    } catch (e) { toast.error(errorMessage(e)); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="fb-section-dialog">
        <DialogHeader><DialogTitle>{section.key ? "Ubah Section" : "Tambah Section"}</DialogTitle><DialogDescription>Section tampil sebagai satu langkah di form publik.</DialogDescription></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5"><Label htmlFor="fb-sec-label">Nama section</Label><Input id="fb-sec-label" value={label} maxLength={80} onChange={(e) => setLabel(e.target.value)} data-testid="fb-section-label-input" /></div>
          <div className="space-y-1.5"><Label htmlFor="fb-sec-desc">Keterangan (opsional)</Label><Textarea id="fb-sec-desc" value={desc} maxLength={300} onChange={(e) => setDesc(e.target.value)} data-testid="fb-section-desc-input" /></div>
        </div>
        <DialogFooter><Button variant="outline" onClick={onClose}>Batal</Button><Button onClick={save} disabled={label.trim().length < 2} data-testid="fb-section-save">Simpan</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const FieldDialog = ({ field, cfg, onClose, onSaved, askConfirm }) => {
  const create = !!field.create, core = field.source === "CORE";
  const [f, setF] = useState(() => ({
    label: create ? "" : core ? field.label_override || "" : field.label, help_text: field.help_text || "", placeholder: field.placeholder || "",
    section_key: field.section || "personal", type: field.type || "text", form_level: field.form_level || "OPTIONAL",
    active: field.active !== false, options: (field.options || []).filter((o) => o.active !== false).map((o) => ({ value: o.value, label: o.label })),
    validation: field.validation || {},
  }));
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const fieldSections = cfg.sections.filter((s) => s.kind === "fields");
  const hasOptions = ["dropdown", "radio", "checkbox"].includes(f.type);
  const save = async () => {
    if (!core && !create && field.active !== false && f.active === false && askConfirm) {
      askConfirm({ title: `Nonaktifkan custom field "${field.label}"?`, confirmLabel: "Nonaktifkan",
        description: "Field tidak lagi ditampilkan di form karyawan. Jawaban yang sudah ada tetap tersimpan (tidak dihapus) dan field dapat diaktifkan kembali.",
        action: doSave });
      return;
    }
    await doSave();
  };
  const doSave = async () => {
    try {
      if (core) await api.put(`${BASE}/fields/${field.key}`, { label_override: f.label.trim() || null, help_text: f.help_text || null, section_key: f.section_key });
      else {
        const body = { label: f.label.trim(), help_text: f.help_text || null, placeholder: f.placeholder || null, section_key: f.section_key, type: f.type,
          form_level: f.form_level, validation: f.validation, options: hasOptions ? f.options.filter((o) => o.label.trim()) : [] };
        if (create) await api.post(`${BASE}/fields`, body); else await api.put(`${BASE}/fields/${field.key}`, { ...body, active: f.active });
      }
      toast.success(create ? "Custom field ditambahkan." : "Field diperbarui."); onClose(); onSaved();
    } catch (e) { toast.error(errorMessage(e)); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg" data-testid="fb-field-dialog">
        <DialogHeader>
          <DialogTitle>{create ? "Tambah Custom Field" : core ? `Field Inti: ${field.default_label}` : `Edit ${field.label}`}</DialogTitle>
          <DialogDescription>{core ? `Level "${field.level_label}" mengikuti Master Kelengkapan Data (01F)${field.grouped_with?.length ? ` dan diatur bersama: ${field.requirement_label}` : ""}. Field inti tidak dapat dihapus.` : "Jawaban custom field menjadi data resmi setelah diverifikasi HR. Custom field tidak ikut skor kelengkapan."}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5"><Label htmlFor="fb-f-label">{core ? "Label tampilan (kosongkan = label bawaan)" : "Label / pertanyaan"}</Label><Input id="fb-f-label" value={f.label} maxLength={120} placeholder={core ? field.default_label : ""} onChange={(e) => set("label", e.target.value)} data-testid="fb-field-label-input" /></div>
          {!core && (
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5"><Label>Tipe</Label>
                <Select value={f.type} onValueChange={(v) => set("type", v)}><SelectTrigger data-testid="fb-field-type"><SelectValue /></SelectTrigger>
                  <SelectContent>{cfg.custom_types.map((t) => <SelectItem key={t} value={t}>{TYPE_LABELS[t]}</SelectItem>)}</SelectContent></Select></div>
              <div className="space-y-1.5"><Label>Kebutuhan</Label>
                <Select value={f.form_level} onValueChange={(v) => set("form_level", v)}><SelectTrigger data-testid="fb-field-level"><SelectValue /></SelectTrigger>
                  <SelectContent>{cfg.custom_levels.map((l) => <SelectItem key={l} value={l}>{LEVEL_LABELS[l]}</SelectItem>)}</SelectContent></Select></div>
            </div>
          )}
          <div className="space-y-1.5"><Label>Section</Label>
            <Select value={f.section_key} onValueChange={(v) => set("section_key", v)}><SelectTrigger data-testid="fb-field-section"><SelectValue /></SelectTrigger>
              <SelectContent>{fieldSections.map((s) => <SelectItem key={s.key} value={s.key}>{s.label}</SelectItem>)}</SelectContent></Select></div>
          <div className="space-y-1.5"><Label htmlFor="fb-f-help">Teks bantuan</Label><Input id="fb-f-help" value={f.help_text} maxLength={300} onChange={(e) => set("help_text", e.target.value)} data-testid="fb-field-help-input" /></div>
          {!core && hasOptions && (
            <div className="space-y-2" data-testid="fb-field-options">
              <Label>Opsi</Label>
              {f.options.map((o, i) => (
                <div key={i} className="flex gap-2">
                  <Input value={o.label} maxLength={120} onChange={(e) => set("options", f.options.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} aria-label={`Opsi ${i + 1}`} data-testid={`fb-option-${i}`} />
                  <Button variant="ghost" size="icon" onClick={() => set("options", f.options.filter((_, j) => j !== i))} aria-label={`Nonaktifkan opsi ${i + 1}`}><Trash2 className="h-4 w-4" /></Button>
                </div>
              ))}
              <Button variant="outline" size="sm" onClick={() => set("options", [...f.options, { label: "" }])} data-testid="fb-option-add"><Plus className="mr-1 h-4 w-4" />Tambah opsi</Button>
              {!create && <p className="text-xs text-muted-foreground">Opsi yang dihapus disimpan sebagai nonaktif (data lama tetap aman).</p>}
            </div>
          )}
          {!core && f.type === "number" && (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label htmlFor="fb-min">Minimum</Label><Input id="fb-min" inputMode="decimal" value={f.validation.min ?? ""} onChange={(e) => set("validation", { ...f.validation, min: e.target.value })} /></div>
              <div className="space-y-1.5"><Label htmlFor="fb-max">Maksimum</Label><Input id="fb-max" inputMode="decimal" value={f.validation.max ?? ""} onChange={(e) => set("validation", { ...f.validation, max: e.target.value })} /></div>
            </div>
          )}
          {!core && f.type === "file" && <p className="rounded-lg border bg-muted/40 p-3 text-xs text-muted-foreground">Berkas diunggah sebagai lampiran pending (PDF/JPG/PNG/WEBP, maks 10 MB) dan baru menjadi dokumen resmi setelah verifikasi HR.</p>}
          {!core && !create && (
            <label className="flex items-center justify-between gap-3 rounded-lg border p-3"><span className="text-sm">Aktif (nonaktifkan bila tidak dipakai lagi; data lama tetap tersimpan)</span>
              <Switch checked={f.active} onCheckedChange={(v) => set("active", v)} data-testid="fb-field-active" /></label>
          )}
        </div>
        <DialogFooter><Button variant="outline" onClick={onClose}>Batal</Button><Button onClick={save} disabled={!core && f.label.trim().length < 2} data-testid="fb-field-save">Simpan</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const ScopeDialog = ({ field, cfg, onClose, onSaved }) => {
  const [type, setType] = useState("department");
  const [sid, setSid] = useState("");
  const [mode, setMode] = useState("INCLUDE");
  const types = Object.entries(cfg.scope_types).filter(([k]) => k !== "business_status_category" && k !== "company");
  const add = async () => {
    try { await api.post(`${BASE}/fields/${field.key}/scopes`, { scope_type: type, scope_id: sid, mode }); toast.success("Scope ditambahkan."); onSaved(); onClose(); } catch (e) { toast.error(errorMessage(e)); }
  };
  const remove = async (id) => {
    try { await api.delete(`${BASE}/fields/${field.key}/scopes/${id}`); toast.success("Scope dihapus."); onSaved(); onClose(); } catch (e) { toast.error(errorMessage(e)); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="fb-scope-dialog">
        <DialogHeader><DialogTitle>Scope: {field.label}</DialogTitle><DialogDescription>Tanpa scope = tampil untuk semua karyawan. Scope hanya menentukan siapa yang melihat field; tidak mengubah aturan kelengkapan 01F.</DialogDescription></DialogHeader>
        <ul className="space-y-2" data-testid="fb-scope-list">
          {field.scopes.length === 0 && <li className="text-sm text-muted-foreground">Semua karyawan</li>}
          {field.scopes.map((s) => (
            <li key={s.id} className="flex items-center justify-between gap-2 rounded-lg border p-2 text-sm">
              <span><Badge variant="outline" className="mr-2">{s.mode === "INCLUDE" ? "Hanya" : "Kecuali"}</Badge>{s.scope_label}</span>
              <Button size="sm" variant="ghost" onClick={() => remove(s.id)} aria-label="Hapus scope" data-testid={`fb-scope-remove-${s.id}`}><Trash2 className="h-4 w-4" /></Button>
            </li>
          ))}
        </ul>
        <div className="grid gap-2 sm:grid-cols-3">
          <Select value={mode} onValueChange={setMode}><SelectTrigger data-testid="fb-scope-mode"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="INCLUDE">Hanya untuk</SelectItem><SelectItem value="EXCLUDE">Kecuali</SelectItem></SelectContent></Select>
          <Select value={type} onValueChange={(v) => { setType(v); setSid(""); }}><SelectTrigger data-testid="fb-scope-type"><SelectValue /></SelectTrigger><SelectContent>{types.map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent></Select>
          <Select value={sid} onValueChange={setSid}><SelectTrigger data-testid="fb-scope-value"><SelectValue placeholder="Pilih" /></SelectTrigger><SelectContent>{(cfg.scope_options[type] || []).map((o) => <SelectItem key={o.id} value={o.id}>{o.label}</SelectItem>)}</SelectContent></Select>
        </div>
        <DialogFooter><Button variant="outline" onClick={onClose}>Tutup</Button><Button onClick={add} disabled={!sid} data-testid="fb-scope-add">Tambah Scope</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const PreviewDialog = ({ data, onClose }) => (
  <Dialog open onOpenChange={(o) => !o && onClose()}>
    <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-4xl" data-testid="fb-preview-dialog">
      <DialogHeader><DialogTitle>Preview Form Publik</DialogTitle><DialogDescription>Konfigurasi terkini, read-only (tidak membuat draft/kiriman).</DialogDescription></DialogHeader>
      <FormPreview data={data} />
      <DialogFooter><Button onClick={onClose} data-testid="fb-preview-close">Tutup</Button></DialogFooter>
    </DialogContent>
  </Dialog>
);
