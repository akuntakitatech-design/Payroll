import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, Loader2, LogOut, Send } from "lucide-react";
import { toast } from "sonner";
import { Toaster } from "@/components/ui/sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { publicFormApi, sessionStore, enforcePublicAnalyticsOff } from "@/lib/publicFormApi";
import { CompletenessCard, FieldInput, PublicShell, REQ_FIELDS, SaveStatus, SECTION_TITLES, StatusScreen, StepProgress, STEPS, stepOf } from "@/components/public-form/PublicFormParts";
import { FamilySection } from "@/components/public-form/FamilySection";
import { DocumentsSection } from "@/components/public-form/DocumentsSection";
import { ReviewSection } from "@/components/public-form/ReviewSection";

const MSG_EXPIRED = "Sesi Anda telah berakhir. Silakan verifikasi kembali untuk melanjutkan.";
const MSG_FALLBACK = "Data Anda belum dapat diverifikasi melalui form ini. Silakan hubungi HR/Admin Site.";
const MSG_RATE = "Terlalu banyak percobaan verifikasi. Demi keamanan, silakan coba lagi beberapa saat lagi.";
const digits = (v) => String(v || "").replace(/\D/g, "");
const mask = (v) => (v.length <= 4 ? "*".repeat(v.length) : "*".repeat(v.length - 4) + v.slice(-4));
const fmtDate = (iso) => { try { return new Date(iso).toLocaleString("id-ID", { dateStyle: "long", timeStyle: "short" }); } catch { return iso; } };

export default function PublicEmployeeFormPage() {
  const { companyCode } = useParams();
  const scope = String(companyCode || "").trim().toUpperCase();
  const [phase, setPhase] = useState("loading");
  const [company, setCompany] = useState(null);
  const [notice, setNotice] = useState(null);
  const [sess, setSess] = useState(null);
  const [form, setForm] = useState(null);
  const [values, setValues] = useState({});
  const [sens, setSens] = useState({});
  const [draftMasked, setDraftMasked] = useState({});
  const [ops, setOps] = useState([]);
  const [noNpwp, setNoNpwp] = useState(false);
  const [files, setFiles] = useState([]);
  const [version, setVersion] = useState(null);
  const [step, setStep] = useState(0);
  const [errors, setErrors] = useState({});
  const [saveState, setSaveState] = useState(null);
  const [savedAt, setSavedAt] = useState(null);
  const [busy, setBusy] = useState(false);
  const [agree, setAgree] = useState(false);
  const dirty = useRef(false);
  const saving = useRef(null);
  const topRef = useRef(null);

  const expire = useCallback(() => { sessionStore.clear(scope); setSess(null); setPhase("expired"); }, [scope]);

  const hydrate = useCallback((f) => {
    const d = f.draft?.proposed || {};
    const v = {}, dm = {};
    f.fields.forEach((fd) => {
      const dv = d.fields?.[fd.key];
      if (fd.sensitive) { if (dv && typeof dv === "object" && dv.masked) dm[fd.key] = dv.masked; }
      else v[fd.key] = dv !== undefined && dv !== null ? String(dv) : fd.value !== null && fd.value !== undefined ? String(fd.value) : "";
    });
    setForm(f); setValues(v); setSens({}); setDraftMasked(dm); setOps(d.family || []); setNoNpwp(!!d.no_npwp);
    setFiles(f.draft?.files || []); setVersion(f.draft?.version ?? null); setErrors({}); dirty.current = false;
    setSaveState(f.draft ? "saved" : null); setSavedAt(f.draft?.draft_saved_at ? fmtDate(f.draft.draft_saved_at) : null);
  }, []);

  const loadForm = useCallback(async (token, next = "welcome") => {
    try {
      const f = await publicFormApi.form(token);
      hydrate(f);
      setPhase(f.mode === "READ_ONLY" ? "pending" : next);
    } catch (e) {
      if (e.status === 401) expire(); else setNotice(e.detail);
    }
  }, [hydrate, expire]);

  // ------------------------------------------------------------------ init portal / undangan
  // ------------------------------------------------------------------ init portal (analytics dicek dulu)
  useEffect(() => {
    if (enforcePublicAnalyticsOff()) return;
    document.title = "Pembaruan Data Karyawan";
    (async () => {
      try {
        const p = await publicFormApi.portal(scope);
        setCompany(p.company);
        const saved = sessionStore.get(scope);
        if (saved) { setSess(saved); await loadForm(saved, "welcome"); } else setPhase("verify");
      } catch (e) {
        setPhase(e.status === 429 ? "verify" : "invalid");
        setNotice(e.status === 429 ? MSG_RATE : e.detail);
      }
    })();
  }, [scope, loadForm]);

  // ------------------------------------------------------------------ payload & simpan draft
  const fieldsBy = useMemo(() => Object.fromEntries((form?.fields || []).map((f) => [f.key, f])), [form]);
  const buildPayload = useCallback(() => {
    const out = {};
    (form?.fields || []).forEach((fd) => {
      if (fd.sensitive) {
        const nv = (sens[fd.key] || "").trim();
        if (nv) out[fd.key] = nv; else if (draftMasked[fd.key]) out[fd.key] = draftMasked[fd.key];
      } else {
        const nv = (values[fd.key] || "").trim();
        if (nv && nv !== String(fd.value ?? "")) out[fd.key] = nv;
      }
    });
    return { version, fields: out, family: ops, no_npwp: noNpwp };
  }, [form, sens, draftMasked, values, ops, noNpwp, version]);

  const focusError = useCallback((errs) => {
    const first = Object.keys(errs)[0];
    if (!first) return;
    const sec = first.startsWith("family") ? "family" : stepOf(fieldsBy[first]?.section);
    const idx = STEPS.findIndex((s) => s.key === sec);
    if (idx >= 0) setStep(idx);
    setTimeout(() => document.getElementById(`pef-${first}`)?.focus(), 150);
  }, [fieldsBy]);

  const save = useCallback(async ({ silent = false } = {}) => {
    if (!sess) return false;
    if (saving.current) await saving.current.catch(() => {});
    const payload = buildPayload();
    if (payload.version === null && !Object.keys(payload.fields).length && !payload.family.length && !payload.no_npwp) { dirty.current = false; return true; }
    setSaveState("saving");
    const run = publicFormApi.saveDraft(sess, payload);
    saving.current = run;
    try {
      const r = await run;
      setVersion(r.version); setSaveState("saved"); setSavedAt(new Date().toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" }));
      dirty.current = false; setErrors({});
      // nilai sensitif baru tidak ditahan di browser: diganti bentuk masking (server memulihkan nilai asli saat simpan berikutnya)
      const moved = {};
      Object.entries(sens).forEach(([k, v]) => { if ((v || "").trim()) moved[k] = mask(digits(v)); });
      if (Object.keys(moved).length) { setDraftMasked((d) => ({ ...d, ...moved })); setSens({}); }
      if (ops.some((o) => o.data?.nik && !String(o.data.nik).includes("*"))) setOps((cur) => cur.map((o) => (o.data?.nik && !String(o.data.nik).includes("*") ? { ...o, data: { ...o.data, nik: mask(digits(o.data.nik)) } } : o)));
      return true;
    } catch (e) {
      setSaveState("error");
      if (e.status === 401) { expire(); return false; }
      if (e.status === 409) { setNotice(e.detail); if (!silent) toast.warning(e.detail); return false; }
      if (e.status === 422) {
        const errs = { ...e.errors };
        e.rejected.forEach((k) => { errs[k] = "Field ini tidak dapat diubah melalui formulir."; });
        setErrors(errs);
        if (!silent) { toast.error(e.detail); focusError(errs); }
        return false;
      }
      if (!silent) toast.error(e.detail);
      return false;
    } finally {
      saving.current = null;
    }
  }, [sess, buildPayload, sens, ops, expire, focusError]);

  // autosave hemat: 3 detik setelah perubahan terakhir, hanya bila ada perubahan
  useEffect(() => {
    if (phase !== "form" || !dirty.current) return undefined;
    setSaveState("dirty");
    const t = setTimeout(() => { if (dirty.current) save({ silent: true }); }, 3000);
    return () => clearTimeout(t);
  }, [values, sens, ops, noNpwp, phase, save]);

  const change = (k, v) => { dirty.current = true; if (fieldsBy[k]?.sensitive) setSens((s) => ({ ...s, [k]: v })); else setValues((s) => ({ ...s, [k]: v })); setErrors((e) => ({ ...e, [k]: undefined })); };
  const changeOps = (next) => { dirty.current = true; setOps(next); };

  const refreshDraftMeta = async () => {
    const f = await publicFormApi.form(sess);
    setFiles(f.draft?.files || []); setVersion(f.draft?.version ?? null);
  };
  const upload = async (code, file, replaceIds = []) => {
    try {
      if (dirty.current) await save({ silent: true });
      await publicFormApi.upload(sess, file, code);
      // "Ganti": berkas pending lama untuk jenis yang sama dihapus SETELAH berkas baru berhasil diunggah
      for (const id of replaceIds) { await publicFormApi.removeFile(sess, id).catch(() => {}); }
      await refreshDraftMeta();
      toast.success(replaceIds.length ? "Berkas diganti di draft." : "Berkas terunggah ke draft.");
    } catch (e) { if (e.status === 401) expire(); throw e; }
  };
  const removeFile = async (id) => {
    try { await publicFormApi.removeFile(sess, id); await refreshDraftMeta(); } catch (e) { if (e.status === 401) expire(); else toast.error(e.detail); }
  };

  // ------------------------------------------------------------------ kelengkapan (master 01F) vs isian draft
  const analysis = useMemo(() => {
    const payload = buildPayload();
    const provided = (k) => !!payload.fields[k];
    const addressed = (it) => {
      if (it.code.startsWith("DOC.")) return files.some((f) => `DOC.${String(f.document_type_code).toUpperCase()}` === it.code);
      if (it.code === "PERSONAL.PHOTO") return files.some((f) => f.document_type_code === "PHOTO");
      if (it.code === "FAMILY.SPOUSE") return ops.some((o) => o.op !== "remove" && ["SUAMI", "ISTRI"].includes(o.data?.relationship));
      if (it.code === "TAX.NPWP" && noNpwp) return true;
      if (it.code === "PERSONAL.EMERGENCY_CONTACT" && ops.some((o) => o.op !== "remove" && o.data?.is_emergency_contact && o.data?.phone)) return true;
      const fs = REQ_FIELDS[it.code];
      if (!fs) return false;
      return fs.every((k) => provided(k) || (it.status === "MISSING" && fieldsBy[k]?.has_value));
    };
    const state = {}, badge = {}, docNeed = {};
    STEPS.forEach((s) => { state[s.key] = { ok: true, required: [], recommended: [], changes: 0 }; });
    (form?.completeness?.missing || []).forEach((it) => {
      if (addressed(it)) return;
      const st = state[stepOf(it.section)];
      if (!st) return;
      if (it.level === "REQUIRED") { st.ok = false; st.required.push(it.label); } else st.recommended.push(it.label);
      (REQ_FIELDS[it.code] || []).forEach((k) => { badge[k] = it.level; });
      docNeed[it.code] = it.level;
    });
    Object.keys(payload.fields).forEach((k) => { const s = stepOf(fieldsBy[k]?.section); if (state[s]) state[s].changes += 1; });
    state.family.changes = ops.length; state.documents.changes = files.length;
    if (noNpwp) state.bank_tax.changes += 1;
    const firstGap = STEPS.findIndex((s) => state[s.key] && !state[s.key].ok);
    const total = Object.keys(payload.fields).length + ops.length + files.length + (noNpwp ? 1 : 0);
    return { state, badge, docNeed, firstGap, total };
  }, [buildPayload, files, ops, noNpwp, form, fieldsBy]);

  // ------------------------------------------------------------------ navigasi & kirim
  const goStep = (i) => { setStep(i); setTimeout(() => window.scrollTo({ top: 0, behavior: "auto" }), 0); };
  const next = async () => { setBusy(true); const ok = dirty.current ? await save() : true; setBusy(false); if (ok) goStep(Math.min(step + 1, STEPS.length - 1)); };
  const back = () => { if (dirty.current) save({ silent: true }); goStep(Math.max(step - 1, 0)); };

  const submit = async () => {
    if (busy) return;
    if (analysis.firstGap >= 0) { toast.warning("Masih ada data wajib yang belum dilengkapi."); goStep(analysis.firstGap); return; }
    setBusy(true);
    try {
      if (dirty.current || version === null) { const ok = await save(); if (!ok) return; }
      const cur = await publicFormApi.form(sess);
      await publicFormApi.submit(sess, cur.draft?.version);
      setForm((f) => ({ ...f, submitted_at: new Date().toISOString() }));
      setPhase("submitted");
      publicFormApi.logout(sess).catch(() => {});
      sessionStore.clear(scope); setSess(null);
    } catch (e) {
      if (e.status === 401) expire();
      else if (e.status === 422 && Object.keys(e.errors).length) { setErrors(e.errors); focusError(e.errors); toast.error(e.detail); }
      else toast.error(e.detail);
    } finally { setBusy(false); }
  };

  const logout = async () => { if (sess) { if (dirty.current) await save({ silent: true }); publicFormApi.logout(sess).catch(() => {}); } sessionStore.clear(scope); setSess(null); setPhase("verify"); };

  // ------------------------------------------------------------------ render
  const logoSrc = company?.has_logo ? publicFormApi.logoUrl(scope) : null;
  return (
    <PublicShell company={company} logoSrc={logoSrc}>
      <Toaster position="top-center" visibleToasts={3} closeButton />
      <div ref={topRef} className="scroll-mt-20" />
      {phase === "loading" && <div className="space-y-4" data-testid="public-loading"><Skeleton className="h-8 w-2/3" /><Skeleton className="h-40 w-full" /><Skeleton className="h-12 w-full" /></div>}
      {phase === "invalid" && <StatusScreen icon="warn" title="Halaman tidak tersedia" testid="public-invalid">{notice}</StatusScreen>}
      {phase === "verify" && <VerifyStep scope={scope} initialNotice={notice}
        onVerified={async (token) => { sessionStore.set(scope, token); setSess(token); setNotice(null); await loadForm(token, "welcome"); }} />}
      {phase === "expired" && (
        <StatusScreen icon="wait" title="Sesi berakhir" testid="public-expired"
          action={<Button className="h-12 w-full text-base sm:w-auto" onClick={() => { setNotice(null); setPhase("verify"); }} data-testid="public-reverify-button">Verifikasi Ulang</Button>}>
          <p>{MSG_EXPIRED}</p><p className="text-sm">Draft yang sudah tersimpan tetap aman dan akan terbuka kembali setelah verifikasi.</p>
        </StatusScreen>
      )}
      {phase === "welcome" && form && (
        <div className="space-y-5" data-testid="public-welcome">
          <section className="rounded-2xl border bg-background p-5 sm:p-7">
            <h1 className="text-2xl font-semibold leading-snug sm:text-3xl" data-testid="public-welcome-title">Halo, {values.full_name || "Karyawan"}</h1>
            <p className="mt-2 text-base text-muted-foreground">Silakan periksa dan lengkapi data Anda. Data yang Anda kirim akan diverifikasi terlebih dahulu oleh HR.</p>
            <dl className="mt-5 grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl bg-muted/50 p-3"><dt className="text-xs text-muted-foreground">Nama</dt><dd className="font-medium break-words" data-testid="public-welcome-name">{values.full_name || "-"}</dd></div>
              <div className="rounded-xl bg-muted/50 p-3"><dt className="text-xs text-muted-foreground">Nomor Karyawan</dt><dd className="font-medium" data-testid="public-welcome-number">{form.view_only?.employee_number || "-"}</dd></div>
              {form.view_only?.work_location && <div className="rounded-xl bg-muted/50 p-3"><dt className="text-xs text-muted-foreground">Lokasi kerja / site</dt><dd className="font-medium" data-testid="public-welcome-site">{form.view_only.work_location}</dd></div>}
              {form.view_only?.position && <div className="rounded-xl bg-muted/50 p-3"><dt className="text-xs text-muted-foreground">Jabatan</dt><dd className="font-medium">{form.view_only.position}</dd></div>}
            </dl>
            {form.draft && <p className="mt-4 rounded-xl border border-primary/30 bg-[hsl(var(--accent-mint,168_55%_92%))] p-3 text-sm" data-testid="public-welcome-draft">Anda memiliki draft yang tersimpan{savedAt ? ` (${savedAt})` : ""}. Isian Anda akan dilanjutkan.</p>}
          </section>
          <CompletenessCard completeness={form.completeness} />
          <div className="flex flex-col gap-3 sm:flex-row">
            <Button className="h-12 flex-1 text-base" onClick={() => { setPhase("form"); goStep(0); }} data-testid="public-start-button">{form.draft ? "Lanjutkan Mengisi" : "Mulai Periksa Data"}<ArrowRight className="ml-2 h-5 w-5" /></Button>
            <Button variant="outline" className="h-12 text-base" onClick={logout} data-testid="public-logout-button"><LogOut className="mr-2 h-4 w-4" />Keluar</Button>
          </div>
        </div>
      )}
      {phase === "form" && form && (
        <div className="space-y-5" data-testid="public-form">
          <div className="flex items-center justify-between gap-2"><SaveStatus state={saveState} at={savedAt} /><Button variant="ghost" size="sm" className="h-10" onClick={logout} data-testid="public-form-logout"><LogOut className="mr-1 h-4 w-4" />Keluar</Button></div>
          <StepProgress index={step} total={STEPS.length} label={STEPS[step].label} />
          {notice && <Alert data-testid="public-form-notice"><AlertDescription className="flex flex-wrap items-center gap-2">{notice}<Button size="sm" variant="outline" onClick={() => { setNotice(null); loadForm(sess, "form"); }} data-testid="public-reload-button">Muat ulang</Button></AlertDescription></Alert>}
          {(STEPS[step].sections || []).map((secKey) => (
            <section key={secKey} className="space-y-5 rounded-2xl border bg-background p-4 sm:p-6" data-testid={`public-section-${secKey}`}>
              {STEPS[step].sections.length > 1 && <h3 className="text-base font-semibold" data-testid={`public-section-title-${secKey}`}>{SECTION_TITLES[secKey] || secKey}</h3>}
              {form.fields.filter((f) => f.section === secKey).map((f) => (
                <FieldInput key={f.key} field={f} value={f.sensitive ? sens[f.key] : values[f.key]} onChange={change} error={errors[f.key]}
                  badge={analysis.badge[f.key]} draftMasked={f.sensitive ? draftMasked[f.key] : null} options={f.options ? form.options[f.options] : null} disabled={busy} />
              ))}
              {secKey === "bank_tax" && (
                <label className="flex min-h-12 items-center gap-3 rounded-lg border p-3"><Checkbox checked={noNpwp} onCheckedChange={(v) => { dirty.current = true; setNoNpwp(!!v); }} data-testid="public-no-npwp" /><span className="text-sm">Saya tidak memiliki NPWP</span></label>
              )}
            </section>
          ))}
          {STEPS[step].key === "family" && <FamilySection family={form.family} ops={ops} setOps={changeOps} options={form.options} disabled={busy} errors={errors} />}
          {STEPS[step].key === "documents" && <DocumentsSection documents={form.documents} files={files} onUpload={upload} onRemove={removeFile} disabled={busy} missingCodes={analysis.docNeed} />}
          {STEPS[step].key === "review" && (<>
            <CompletenessCard completeness={form.completeness} compact />
            <ReviewSection sectionState={analysis.state} changedCount={analysis.total} onGo={goStep} agree={agree} setAgree={setAgree} disabled={busy} />
            {analysis.firstGap >= 0 && <Alert className="border-amber-300 bg-amber-50" data-testid="public-review-blocked"><AlertDescription className="text-amber-900">Masih ada data <b>wajib</b> yang belum dilengkapi. <button type="button" className="font-semibold underline" onClick={() => goStep(analysis.firstGap)} data-testid="public-review-goto-gap">Lengkapi sekarang</button></AlertDescription></Alert>}
          </>)}
          <div className="sticky bottom-0 z-10 -mx-4 border-t bg-background/95 px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 backdrop-blur">
            <div className="flex gap-2">
              {step > 0 && <Button variant="outline" className="h-12 px-4" onClick={back} disabled={busy} aria-label="Kembali" data-testid="public-back-button"><ArrowLeft className="h-5 w-5" /><span className="ml-1 hidden sm:inline">Kembali</span></Button>}
              {STEPS[step].key !== "review" ? (
                <Button className="h-12 flex-1 text-base" onClick={next} disabled={busy} data-testid="public-next-button">{busy ? <Loader2 className="mr-2 h-5 w-5 animate-spin" /> : null}Simpan &amp; Lanjutkan</Button>
              ) : (
                <Button className="h-12 flex-1 text-base" onClick={submit} disabled={busy || !agree || analysis.firstGap >= 0 || analysis.total === 0} data-testid="public-submit-button">{busy ? <Loader2 className="mr-2 h-5 w-5 animate-spin" /> : <Send className="mr-2 h-5 w-5" />}Kirim Data ke HR</Button>
              )}
            </div>
            {STEPS[step].key === "review" && analysis.total === 0 && <p className="mt-2 text-xs text-muted-foreground" data-testid="public-submit-empty">Belum ada perubahan data atau dokumen yang diajukan.</p>}
          </div>
        </div>
      )}
      {phase === "submitted" && (
        <StatusScreen icon="ok" title="Data berhasil dikirim" testid="public-submitted">
          <p>Data Anda telah dikirim dan sedang menunggu verifikasi HR.</p><p className="text-sm">Anda dapat menutup halaman ini. HR akan menindaklanjuti data Anda.</p>
        </StatusScreen>
      )}
      {phase === "pending" && (
        <StatusScreen icon="wait" title="Menunggu verifikasi HR" testid="public-pending"
          action={<Button variant="outline" className="h-12 w-full text-base sm:w-auto" onClick={logout} data-testid="public-pending-logout"><LogOut className="mr-2 h-4 w-4" />Keluar</Button>}>
          <p data-testid="public-pending-text">Data Anda sudah dikirim{form?.draft?.submitted_at ? ` pada ${fmtDate(form.draft.submitted_at)}` : ""}. Saat ini sedang menunggu verifikasi HR.</p>
          <p className="text-sm">Data yang sudah dikirim tidak dapat diubah dari halaman ini. Hubungi HR bila ada koreksi.</p>
        </StatusScreen>
      )}
    </PublicShell>
  );
}

const VerifyStep = ({ scope, initialNotice, onVerified }) => {
  const [v, setV] = useState({ employee_number: "", nik: "", birth_date: "" });
  const [err, setErr] = useState({});
  const [msg, setMsg] = useState(initialNotice || null);
  const [fails, setFails] = useState(0);
  const [busy, setBusy] = useState(false);
  const set = (k, val) => { setV((s) => ({ ...s, [k]: val })); setErr((e) => ({ ...e, [k]: undefined })); };
  const submit = async (e) => {
    e.preventDefault();
    if (busy) return;
    const x = {};
    if (!v.employee_number.trim()) x.employee_number = "Isi Nomor Karyawan.";
    if (!/^\d{16}$/.test(digits(v.nik))) x.nik = "NIK KTP terdiri dari 16 digit angka.";
    if (!v.birth_date) x.birth_date = "Pilih tanggal lahir.";
    setErr(x);
    if (Object.keys(x).length) { document.getElementById(`pv-${Object.keys(x)[0]}`)?.focus(); return; }
    setBusy(true); setMsg(null);
    const payload = { employee_number: v.employee_number.trim(), nik: digits(v.nik), birth_date: v.birth_date };
    try {
      const r = await publicFormApi.verifyPortal(scope, payload);
      setV({ employee_number: "", nik: "", birth_date: "" });
      await onVerified(r.session_token);
    } catch (ex) {
      setMsg(ex.status === 429 ? MSG_RATE : ex.detail);
      if (ex.status === 400 || ex.status === 429) setFails((n) => n + 1);
    } finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} noValidate className="space-y-5" data-testid="public-verify-form">
      <div>
        <h1 className="text-2xl font-semibold leading-snug sm:text-3xl" data-testid="public-verify-title">Pembaruan Data Karyawan</h1>
        <p className="mt-2 text-base text-muted-foreground">Silakan verifikasi data Anda sebelum melanjutkan pembaruan data karyawan.</p>
      </div>
      <section className="space-y-4 rounded-2xl border bg-background p-4 sm:p-6">
        {[["employee_number", "Nomor Karyawan", "text", "Contoh: EMP-0001"], ["nik", "NIK KTP", "nik", "16 digit angka"], ["birth_date", "Tanggal Lahir", "date", ""]].map(([k, l, t, ph]) => (
          <div key={k} className="space-y-1.5">
            <Label htmlFor={`pv-${k}`} className="text-sm font-medium">{l}</Label>
            <Input id={`pv-${k}`} value={v[k]} onChange={(e) => set(k, e.target.value)} placeholder={ph || undefined} disabled={busy}
              type={t === "date" ? "date" : "text"} inputMode={t === "nik" ? "numeric" : undefined} maxLength={t === "nik" ? 20 : 64}
              autoComplete="off" autoCapitalize={k === "employee_number" ? "characters" : "off"} spellCheck={false}
              className={`h-12 text-base ${err[k] ? "border-destructive" : ""}`} aria-invalid={!!err[k]} data-testid={`public-verify-${k}`} />
            {err[k] && <p className="text-sm font-medium text-destructive" role="alert" data-testid={`public-verify-error-${k}`}>{err[k]}</p>}
          </div>
        ))}
        {msg && (
          <Alert className="border-amber-300 bg-amber-50" data-testid="public-verify-message">
            <AlertDescription className="space-y-1 text-amber-900"><p>{msg}</p>{fails >= 2 && <div className="border-t border-amber-200 pt-2 text-sm" data-testid="public-verify-fallback"><p className="font-medium">Sudah yakin data yang dimasukkan benar?</p><p>{MSG_FALLBACK}</p></div>}</AlertDescription>
          </Alert>
        )}
        <Button type="submit" className="h-12 w-full text-base" disabled={busy} data-testid="public-verify-submit">
          {busy ? <Loader2 className="mr-2 h-5 w-5 animate-spin" /> : null}Verifikasi Data Saya
        </Button>
      </section>
      <p className="text-xs leading-relaxed text-muted-foreground">Halaman ini khusus pembaruan data karyawan dan tidak memerlukan akun HRIS. Data Anda dikirim ke HR untuk diverifikasi terlebih dahulu.</p>
    </form>
  );
};
