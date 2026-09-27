import React, { useState } from "react";
import { Pencil, Plus, Trash2, Undo2, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const EMPTY = { relationship: "", full_name: "", nik: "", birth_place: "", birth_date: "", gender: "", occupation: "", phone: "", is_emergency_contact: false };

/** Gabungan anggota keluarga HR + operasi draft (add/update/remove). Tidak ada tabel desktop di HP. */
export const FamilySection = ({ family, ops, setOps, options, disabled, errors }) => {
  const [edit, setEdit] = useState(null); // {mode:'add'|'update'|'draft', ref, index, data}
  const [formErr, setFormErr] = useState({});
  const rel = (k) => (options.relationship || []).find((o) => o.key === k)?.label || k || "-";
  const opFor = (ref) => ops.find((o) => o.ref === ref && o.op !== "add");

  const openAdd = () => { setFormErr({}); setEdit({ mode: "add", data: { ...EMPTY } }); };
  const openUpdate = (m) => {
    const op = opFor(m.ref);
    const base = { ...EMPTY, ...Object.fromEntries(Object.entries(m).filter(([k]) => k in EMPTY && k !== "nik")), ...(op?.op === "update" ? op.data : {}) };
    setFormErr({});
    setEdit({ mode: "update", ref: m.ref, nikMasked: m.nik_masked, data: { ...base, nik: op?.data?.nik || "" } });
  };
  const openDraft = (i) => { setFormErr({}); setEdit({ mode: "draft", index: i, data: { ...EMPTY, ...ops[i].data } }); };
  const set = (k, v) => setEdit((e) => ({ ...e, data: { ...e.data, [k]: v } }));

  const save = () => {
    const d = edit.data;
    const err = {};
    if (!d.relationship) err.relationship = "Pilih hubungan keluarga.";
    if (!d.full_name || d.full_name.trim().length < 2) err.full_name = "Isi nama lengkap (minimal 2 huruf).";
    if (d.nik && !d.nik.includes("*") && !/^\d{16}$/.test(d.nik.replace(/\s/g, ""))) err.nik = "NIK harus 16 digit angka.";
    if (Object.keys(err).length) { setFormErr(err); return; }
    const data = Object.fromEntries(Object.entries(d).filter(([, v]) => v !== "" && v !== null && v !== undefined).map(([k, v]) => [k, typeof v === "string" ? v.trim() : v]));
    if (data.nik && !data.nik.includes("*")) data.nik = data.nik.replace(/\s/g, "");
    if (edit.mode === "add") setOps([...ops, { op: "add", ref: null, data }]);
    else if (edit.mode === "draft") setOps(ops.map((o, i) => (i === edit.index ? { ...o, data } : o)));
    else setOps([...ops.filter((o) => !(o.ref === edit.ref && o.op !== "add")), { op: "update", ref: edit.ref, data }]);
    setEdit(null);
  };
  const remove = (ref) => setOps([...ops.filter((o) => !(o.ref === ref && o.op !== "add")), { op: "remove", ref, reason: "Diajukan karyawan" }]);
  const undo = (ref) => setOps(ops.filter((o) => !(o.ref === ref && o.op !== "add")));

  const Card = ({ title, sub, badge, tone, actions, testid }) => (
    <div className={`flex items-start gap-3 rounded-xl border bg-background p-4 ${tone || ""}`} data-testid={testid}>
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[hsl(var(--accent-mint,168_55%_92%))] text-primary"><UserRound className="h-5 w-5" /></div>
      <div className="min-w-0 flex-1">
        <p className="break-words font-medium">{title}</p>
        {sub && <p className="text-sm text-muted-foreground">{sub}</p>}
        {badge && <span className="mt-1 inline-block rounded-full border px-2 py-0.5 text-[11px] font-medium">{badge}</span>}
        <div className="mt-3 flex flex-wrap gap-2">{actions}</div>
      </div>
    </div>
  );

  return (
    <div className="space-y-3" data-testid="public-family-section">
      {family.length === 0 && ops.filter((o) => o.op === "add").length === 0 && (
        <p className="rounded-xl border border-dashed p-4 text-sm text-muted-foreground" data-testid="public-family-empty">Belum ada data keluarga. Tambahkan pasangan, anak, atau keluarga lain bila ada.</p>
      )}
      {family.map((m) => {
        const op = opFor(m.ref);
        const shown = op?.op === "update" ? { ...m, ...op.data } : m;
        return (
          <Card key={m.ref} testid={`public-family-card-${m.ref}`} title={`${rel(shown.relationship)} — ${shown.full_name || "-"}`}
            sub={[shown.birth_date, shown.is_emergency_contact ? "Kontak darurat" : null].filter(Boolean).join(" · ")}
            badge={op?.op === "update" ? "Perubahan diajukan" : op?.op === "remove" ? "Akan dihapus (menunggu HR)" : null}
            tone={op?.op === "remove" ? "opacity-70" : ""}
            actions={op?.op === "remove" ? (
              <Button type="button" variant="outline" size="sm" className="h-10" disabled={disabled} onClick={() => undo(m.ref)} data-testid={`public-family-undo-${m.ref}`}><Undo2 className="mr-1 h-4 w-4" />Batalkan</Button>
            ) : (<>
              <Button type="button" variant="outline" size="sm" className="h-10" disabled={disabled} onClick={() => openUpdate(m)} data-testid={`public-family-edit-${m.ref}`}><Pencil className="mr-1 h-4 w-4" />Edit</Button>
              <Button type="button" variant="ghost" size="sm" className="h-10 text-destructive" disabled={disabled} onClick={() => remove(m.ref)} data-testid={`public-family-remove-${m.ref}`}><Trash2 className="mr-1 h-4 w-4" />Hapus</Button>
            </>)} />
        );
      })}
      {ops.map((o, i) => o.op === "add" && (
        <Card key={`add-${i}`} testid={`public-family-new-${i}`} title={`${rel(o.data?.relationship)} — ${o.data?.full_name || "-"}`} sub={o.data?.birth_date} badge="Baru (menunggu HR)"
          actions={<>
            <Button type="button" variant="outline" size="sm" className="h-10" disabled={disabled} onClick={() => openDraft(i)} data-testid={`public-family-new-edit-${i}`}><Pencil className="mr-1 h-4 w-4" />Edit</Button>
            <Button type="button" variant="ghost" size="sm" className="h-10 text-destructive" disabled={disabled} onClick={() => setOps(ops.filter((_, j) => j !== i))} data-testid={`public-family-new-remove-${i}`}><Trash2 className="mr-1 h-4 w-4" />Hapus</Button>
          </>} />
      ))}
      {errors && Object.keys(errors).some((k) => k.startsWith("family")) && (
        <p className="text-sm font-medium text-destructive" role="alert" data-testid="public-family-error">{Object.entries(errors).filter(([k]) => k.startsWith("family")).map(([, v]) => v).join(" ")}</p>
      )}
      <Button type="button" variant="outline" className="h-12 w-full border-dashed text-base" disabled={disabled} onClick={openAdd} data-testid="public-family-add-button"><Plus className="mr-2 h-5 w-5" />Tambah Anggota Keluarga</Button>

      <Dialog open={!!edit} onOpenChange={(o) => !o && setEdit(null)}>
        <DialogContent className="flex h-[100dvh] max-h-[100dvh] w-screen max-w-none flex-col gap-0 overflow-hidden rounded-none p-0 sm:h-auto sm:max-h-[90dvh] sm:max-w-lg sm:rounded-2xl" data-testid="public-family-dialog">
          <DialogHeader className="border-b px-5 py-4 text-left">
            <DialogTitle>{edit?.mode === "update" ? "Ubah Anggota Keluarga" : "Tambah Anggota Keluarga"}</DialogTitle>
            <DialogDescription>Perubahan akan diverifikasi HR terlebih dahulu.</DialogDescription>
          </DialogHeader>
          {edit && (
            <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
              <div className="space-y-1.5"><Label htmlFor="fam-rel">Hubungan</Label>
                <Select value={edit.data.relationship || undefined} onValueChange={(v) => set("relationship", v)}>
                  <SelectTrigger id="fam-rel" className="h-12 text-base" data-testid="public-family-field-relationship"><SelectValue placeholder="Pilih hubungan" /></SelectTrigger>
                  <SelectContent>{(options.relationship || []).map((o) => <SelectItem key={o.key} value={o.key} className="py-3 text-base">{o.label}</SelectItem>)}</SelectContent>
                </Select>{formErr.relationship && <p className="text-sm text-destructive" role="alert">{formErr.relationship}</p>}</div>
              {[["full_name", "Nama lengkap", "text"], ["nik", "NIK (opsional)", "digits"], ["birth_place", "Tempat lahir", "text"], ["birth_date", "Tanggal lahir", "date"], ["occupation", "Pekerjaan", "text"], ["phone", "No. HP", "tel"]].map(([k, l, t]) => (
                <div key={k} className="space-y-1.5"><Label htmlFor={`fam-${k}`}>{l}</Label>
                  <Input id={`fam-${k}`} className="h-12 text-base" type={t === "date" ? "date" : t === "tel" ? "tel" : "text"} inputMode={t === "digits" ? "numeric" : t === "tel" ? "tel" : undefined}
                    autoComplete="off" value={edit.data[k] || ""} onChange={(e) => set(k, e.target.value)} placeholder={k === "nik" && edit.nikMasked ? `Tersimpan: ${edit.nikMasked}` : undefined} data-testid={`public-family-field-${k}`} />
                  {formErr[k] && <p className="text-sm text-destructive" role="alert">{formErr[k]}</p>}</div>
              ))}
              <div className="space-y-1.5"><Label htmlFor="fam-gender">Jenis kelamin</Label>
                <Select value={edit.data.gender || undefined} onValueChange={(v) => set("gender", v)}>
                  <SelectTrigger id="fam-gender" className="h-12 text-base" data-testid="public-family-field-gender"><SelectValue placeholder="Pilih" /></SelectTrigger>
                  <SelectContent>{(options.gender || []).map((o) => <SelectItem key={o.key} value={o.key} className="py-3 text-base">{o.label}</SelectItem>)}</SelectContent>
                </Select></div>
              <label className="flex min-h-12 items-center gap-3 rounded-lg border p-3"><Checkbox checked={!!edit.data.is_emergency_contact} onCheckedChange={(v) => set("is_emergency_contact", !!v)} data-testid="public-family-field-emergency" /><span className="text-sm">Jadikan kontak darurat</span></label>
            </div>
          )}
          <DialogFooter className="flex-row gap-2 border-t px-5 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
            <Button type="button" variant="outline" className="h-12 flex-1" onClick={() => setEdit(null)} data-testid="public-family-cancel">Batal</Button>
            <Button type="button" className="h-12 flex-1" onClick={save} data-testid="public-family-save">Simpan</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
