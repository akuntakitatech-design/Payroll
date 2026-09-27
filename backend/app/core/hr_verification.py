"""Upgrade 01H - HR Verification: review "Data Saat Ini vs Data Usulan", deteksi konflik, dan apply transaksional.

Keputusan terkunci (UPGRADE_01H_HR_VERIFICATION_AUDIT.md §4/§13, rekomendasi Q1-Q8):
- Keputusan per PENGAJUAN: Setujui (semua diterapkan) / Tolak / Minta Perbaikan. HR tidak mengedit nilai usulan.
- Item CONFLICT (data resmi berubah setelah submit) wajib diputuskan eksplisit: use_proposed | keep_current.
- Apply all-or-nothing dalam SATU transaksi DB; objek storage disalin SEBELUM transaksi (kompensasi bila gagal),
  objek foto lama dihapus SETELAH commit.
- DOCUMENT -> baris baru `documents` (dokumen lama tipe sama TIDAK dihapus); PHOTO -> prefix foto karyawan;
  CUSTOM_FIELD (file) -> referensi di `employee_custom_field_values` (bukan dokumen resmi).
- `no_npwp` TIDAK diterapkan otomatis (menyentuh payroll) -> info saja. `notes` karyawan -> tampil saja.
- Revisi memakai baris submission yang SAMA (REVISION_REQUESTED tetap terbuka).
- review_history / apply_result hanya menyimpan NAMA field/status, bukan nilai data.
"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from pydantic import ValidationError

from . import completeness as engine
from . import form_builder as FB
from . import public_form as P
from . import storage as S
from .audit import build_audit_entry
from .db import NO_ID, new_id, now, transaction
from .sensitive import can_view_sensitive, mask_value

logger = logging.getLogger("hris.hr_verification")

MODULE = "employee_core"
RESOURCE = "employee_public_form"

OK, ALREADY_APPLIED, CONFLICT, SKIPPED, INFO = "OK", "ALREADY_APPLIED", "CONFLICT", "SKIPPED", "INFO"
USE_PROPOSED, KEEP_CURRENT = "use_proposed", "keep_current"
BOTH = [USE_PROPOSED, KEEP_CURRENT]
APPLIED, KEPT, NOT_APPLIED = "APPLIED", "KEPT", "NOT_APPLIED"  # status tampilan untuk pengajuan yang sudah diputuskan
STATE_LABELS = {OK: "Akan diterapkan", ALREADY_APPLIED: "Sudah sama dengan data resmi", CONFLICT: "Konflik",
                SKIPPED: "Tidak akan diterapkan", INFO: "Informasi",
                APPLIED: "Diterapkan", KEPT: "Data saat ini dipertahankan", NOT_APPLIED: "Tidak diterapkan"}
STATUS_LABELS = {P.DRAFT: "Draft", P.PENDING: "Menunggu Verifikasi", P.REVISION: "Perlu Perbaikan",
                 P.APPROVED: "Disetujui", P.REJECTED: "Ditolak"}
REVIEW_STATUSES = (P.PENDING, P.REVISION, P.APPROVED, P.REJECTED)
FILE_PROMOTED, FILE_REJECTED = "PROMOTED", "REJECTED"
SECTION_ORDER = [("personal", "Data Pribadi"), ("contact", "Kontak & Alamat"), ("bank_tax", "Bank & Pajak"),
                 ("bpjs", "BPJS"), ("family", "Keluarga"), ("custom", "Pertanyaan Tambahan"),
                 ("documents", "Dokumen & Foto")]
SECTION_LABELS = dict(SECTION_ORDER)
MSG_NOT_FOUND = "Pengajuan tidak ditemukan pada perusahaan aktif Anda."
MSG_PROCESSED = "Pengajuan ini sudah diproses atau tidak sedang menunggu verifikasi. Muat ulang halaman."
MSG_CHANGED = "Data resmi karyawan berubah saat pengajuan diproses. Muat ulang halaman lalu periksa kembali."


class UnresolvedConflicts(Exception):
    """Approve ditolak (HTTP 409) karena masih ada item CONFLICT tanpa resolusi."""
    message = "Masih ada item konflik yang belum diputuskan. Pilih 'Pakai usulan' atau 'Pertahankan data saat ini'."

    def __init__(self, conflicts: List[str]):
        super().__init__(self.message)
        self.conflicts = conflicts


# ------------------------------------------------------------------ util
def jl(v: Any) -> Any:
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return None
    return v


def tx_json(v: Any) -> Any:
    """Kolom JSON dari `_TxWriter.select_one_for_update` masih berupa string mentah (asyncmy) -> dekode."""
    if isinstance(v, (str, bytes)):
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


def iso(v: Any) -> Any:
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, datetime):
        return P.utc(v).isoformat()
    return v


def _enums_and_labels():
    from ..routers.employee_profile import RELATIONSHIPS  # lazy: hindari import siklik core<->routers
    from ..routers.employees import EDUCATIONS, GENDERS, MARITAL_STATUSES, RELIGIONS
    enums = {"gender": [g["key"] for g in GENDERS], "marital": [m["key"] for m in MARITAL_STATUSES],
             "religion": [r["key"] for r in RELIGIONS], "education": [e["key"] for e in EDUCATIONS]}
    labels = {"gender": {g["key"]: g["label"] for g in GENDERS},
              "marital_status": {m["key"]: m["label"] for m in MARITAL_STATUSES},
              "religion": {r["key"]: r["label"] for r in RELIGIONS},
              "education": {e["key"]: e["label"] for e in EDUCATIONS},
              "relationship": dict(RELATIONSHIPS)}
    return enums, labels


def _norm(key: str, v: Any) -> Any:
    return P.normalize_value(key, v)


def _fam_norm(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    out = {}
    for k in P.FAMILY_EDITABLE:
        v = row.get(k)
        if k == "is_emergency_contact":
            out[k] = bool(v)
            continue
        s = str(v).strip() if v not in (None, "") else ""
        if k == "relationship":
            s = s.upper()
        elif k == "nik":
            s = P.norm_digits(s)
        out[k] = s or None
    return out


def _classify(base: Any, cur: Any, prop: Any) -> str:
    if cur == prop:
        return ALREADY_APPLIED
    if cur == base:
        return OK
    return CONFLICT


# ------------------------------------------------------------------ konteks data
async def get_submission(tdb, cid: str, sid: str) -> Dict[str, Any]:
    sub = await tdb.employee_update_submissions.find_one({"company_id": cid, "id": sid}, NO_ID) if sid else None
    if not sub or sub.get("status") not in REVIEW_STATUSES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, MSG_NOT_FOUND)
    return sub


async def load_context(tdb, cid: str, sub: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    eid = sub["employee_id"]
    emp = await tdb.employees.find_one({"company_id": cid, "id": eid}, NO_ID) or {}
    family = {r["id"]: r for r in await tdb.employee_family_members.find(
        {"company_id": cid, "employee_id": eid, "status": {"$ne": "deleted"}}, NO_ID).to_list(200)}
    official_rows = await tdb.employee_custom_field_values.find(
        {"company_id": cid, "employee_id": eid, "status": {"$ne": "deleted"}}, NO_ID).to_list(500)
    official = {r["field_key"]: r.get("value") for r in official_rows}  # Collection sudah mendekode kolom JSON
    cfg = cfg or await FB.load_config(cid)
    defs = {f["key"]: f for f in cfg["fields"] if f["source"] == "CUSTOM"}
    files = await tdb.employee_submission_files.find(
        {"company_id": cid, "submission_id": sub["id"], "status": {"$ne": "removed"}}, NO_ID).sort("uploaded_at", 1).to_list(100)
    doc_types = {d["id"]: d for d in await tdb.document_types.find(
        {"company_id": cid, "owner_scope": "employee"}, NO_ID).to_list(300)}
    docs = await tdb.documents.find({"company_id": cid, "owner_type": "employee", "owner_id": eid,
                                     "is_deleted": {"$ne": True}, "status": {"$ne": "deleted"}},
                                    {"_id": 0, "id": 1, "document_type_id": 1, "created_at": 1}).to_list(1000)
    existing_docs: Dict[str, int] = {}
    for d in docs:
        existing_docs[d.get("document_type_id")] = existing_docs.get(d.get("document_type_id"), 0) + 1
    return {"emp": emp, "family": family, "official": official, "defs": defs, "files": files,
            "doc_types": doc_types, "existing_docs": existing_docs}


# ------------------------------------------------------------------ evaluasi (murni, tanpa I/O)
def evaluate(sub: Dict[str, Any], data: Dict[str, Any], enums: Optional[Dict[str, List[str]]] = None) -> Dict[str, Any]:
    """-> {"items": [...], "conflicts": [item_key], ...}. Nilai mentah (belum dimasking)."""
    proposed = jl(sub.get("proposed")) or {}
    baseline = jl(sub.get("baseline")) or {}
    emp, family, official, defs = data["emp"], data["family"], data["official"], data["defs"]
    items: List[Dict[str, Any]] = []
    base_fields = baseline.get("fields") or {}
    for k, v in (proposed.get("fields") or {}).items():
        spec = P.EDITABLE_FIELDS.get(k)
        if not spec:
            items.append({"key": f"field:{k}", "kind": "field", "field": k, "section": "personal", "label": k,
                          "current": None, "proposed": None, "state": SKIPPED, "note": "Field tidak diizinkan."})
            continue
        prop = _norm(k, v)
        cur = _norm(k, emp.get(k))
        base = _norm(k, base_fields.get(k)) if k in base_fields else cur
        st = _classify(base, cur, prop)
        note = None
        if enums is not None and prop is not None and P.validate_field(k, prop, enums):
            st, note = SKIPPED, "Nilai usulan tidak valid lagi terhadap aturan saat ini."
        items.append({"key": f"field:{k}", "kind": "field", "field": k, "section": spec[0], "label": spec[1],
                      "sensitive": spec[3], "identity": spec[4], "current": emp.get(k), "proposed": prop,
                      "baseline": base_fields.get(k), "state": st, "options": BOTH if st == CONFLICT else [],
                      "note": note or ("Data resmi diubah pihak lain setelah karyawan mengirim pengajuan." if st == CONFLICT else None)})
    base_custom = baseline.get("custom") or {}
    for k, v in (proposed.get("custom") or {}).items():
        d = defs.get(k)
        label = (d or {}).get("label") or k
        if not d or not d.get("active") or d.get("type") == "file":
            items.append({"key": f"custom:{k}", "kind": "custom", "field": k, "section": "custom", "label": label,
                          "current": official.get(k), "proposed": v, "state": SKIPPED,
                          "note": "Pertanyaan sudah dinonaktifkan/dihapus - tidak akan diterapkan."})
            continue
        val, msg = FB.validate_custom(d, v)
        if msg or val is None:
            items.append({"key": f"custom:{k}", "kind": "custom", "field": k, "section": "custom", "label": label,
                          "field_type": d.get("type"), "current": official.get(k), "proposed": v, "state": SKIPPED,
                          "note": "Jawaban tidak sesuai lagi dengan definisi pertanyaan saat ini - tidak akan diterapkan."})
            continue
        cur = official.get(k)
        base = base_custom.get(k) if k in base_custom else cur
        st = _classify(base, cur, val)
        items.append({"key": f"custom:{k}", "kind": "custom", "field": k, "section": "custom", "label": label,
                      "field_type": d.get("type"), "options_def": d.get("options") or [], "current": cur, "proposed": val,
                      "state": st, "options": BOTH if st == CONFLICT else [],
                      "note": "Nilai resmi berubah setelah karyawan mengirim pengajuan." if st == CONFLICT else None})
    base_family = baseline.get("family") or {}
    for i, op in enumerate(proposed.get("family") or []):
        kind, ref = op.get("op"), op.get("ref")
        row = family.get(ref) if ref else None
        item = {"key": f"family:{i}", "kind": "family", "op": kind, "ref": ref, "section": "family",
                "reason": op.get("reason"), "current": None, "proposed": op.get("data"), "state": OK, "options": [], "note": None}
        if kind == "add":
            data_n = _fam_norm(op.get("data") or {})
            warn = []
            for r in family.values():
                rn = _fam_norm(r)
                if data_n.get("nik") and rn.get("nik") == data_n["nik"]:
                    warn.append("Sudah ada anggota keluarga dengan NIK yang sama.")
                elif (rn.get("full_name") or "").casefold() == (data_n.get("full_name") or "").casefold() \
                        and rn.get("relationship") == data_n.get("relationship"):
                    warn.append("Sudah ada anggota keluarga dengan nama & hubungan yang sama.")
            item["note"] = " ".join(sorted(set(warn))) or None
            item["warning"] = bool(warn)
        elif kind == "update":
            if not row:
                item.update(state=CONFLICT, options=[KEEP_CURRENT],
                            note="Anggota keluarga ini sudah dihapus dari data resmi - perubahan tidak dapat diterapkan.")
            else:
                cur_n, prop_n = _fam_norm(row), _fam_norm(op.get("data") or {})
                base_n = _fam_norm(base_family.get(ref)) if ref in base_family else cur_n
                st = _classify(base_n, cur_n, prop_n)
                item.update(current=row, state=st, options=BOTH if st == CONFLICT else [],
                            note="Data anggota keluarga diubah pihak lain setelah pengajuan dikirim." if st == CONFLICT else None)
        elif kind == "remove":
            if not row:
                item.update(state=ALREADY_APPLIED, current=base_family.get(ref),
                            note="Anggota keluarga ini sudah tidak ada di data resmi.")
            else:
                cur_n = _fam_norm(row)
                base_n = _fam_norm(base_family.get(ref)) if ref in base_family else cur_n
                st = OK if cur_n == base_n else CONFLICT
                item.update(current=row, state=st, options=BOTH if st == CONFLICT else [],
                            note="Data anggota keluarga diubah pihak lain setelah pengajuan dikirim." if st == CONFLICT else None)
        else:
            item.update(state=SKIPPED, note="Operasi keluarga tidak dikenal.")
        items.append(item)
    # ---- lampiran
    active_files = [f for f in data["files"] if f.get("status") in ("active", FILE_PROMOTED, FILE_REJECTED)]
    photos = [f for f in active_files if f.get("purpose") == "PHOTO"]
    if photos:
        chosen = photos[-1]  # unggahan foto terakhir = foto yang diusulkan
        base_ver = baseline.get("photo_version", "__none__")
        cur_ver = emp.get("photo_version")
        if base_ver != "__none__" and (base_ver or None) != (cur_ver or None):
            st, note = CONFLICT, "Foto profil resmi berubah setelah pengajuan dikirim."
        else:
            st, note = OK, ("Foto profil lama akan diganti." if emp.get("photo_path") else None)
        items.append({"key": "photo", "kind": "photo", "section": "documents", "label": "Foto profil", "file_id": chosen["id"],
                      "current": bool(emp.get("photo_path")), "proposed": chosen.get("file_name"), "state": st,
                      "options": BOTH if st == CONFLICT else [], "note": note,
                      "superseded_file_ids": [f["id"] for f in photos[:-1]]})
    for f in active_files:
        if f.get("purpose") != "DOCUMENT":
            continue
        dt = data["doc_types"].get(f.get("document_type_id"))
        usable = dt and (dt.get("status") or "active") not in ("deleted", "inactive", "archived")
        existing = data["existing_docs"].get(f.get("document_type_id"), 0)
        items.append({"key": f"file:{f['id']}", "kind": "document", "section": "documents", "file_id": f["id"],
                      "label": (dt or {}).get("name") or f.get("document_type_code"), "document_type_id": f.get("document_type_id"),
                      "current": existing, "proposed": f.get("file_name"), "state": OK if usable else SKIPPED, "options": [],
                      "note": (("Sudah ada %d dokumen tipe ini - dokumen baru ditambahkan, dokumen lama tidak dihapus." % existing)
                               if existing and usable else None) if usable else "Tipe dokumen sudah tidak aktif - tidak akan diterapkan."})
    by_key: Dict[str, List[Dict[str, Any]]] = {}
    for f in active_files:
        if f.get("purpose") == "CUSTOM_FIELD" and f.get("field_key"):
            by_key.setdefault(f["field_key"], []).append(f)
    for fk, fl in by_key.items():
        d = defs.get(fk)
        usable = d and d.get("active") and d.get("type") == "file"
        items.append({"key": f"custom:{fk}", "kind": "custom_file", "field": fk, "section": "custom",
                      "label": (d or {}).get("label") or fk, "file_ids": [f["id"] for f in fl],
                      "current": official.get(fk), "proposed": [f.get("file_name") for f in fl],
                      "state": OK if usable else SKIPPED, "options": [],
                      "note": None if usable else "Pertanyaan sudah dinonaktifkan/dihapus - berkas tidak akan diterapkan."})
    if proposed.get("no_npwp"):
        items.append({"key": "info:no_npwp", "kind": "info", "section": "bank_tax", "label": "Menyatakan tidak memiliki NPWP",
                      "current": None, "proposed": True, "state": INFO, "options": [],
                      "note": "Tidak diterapkan otomatis - sesuaikan status NPWP di Struktur Gaji bila perlu."})
    conflicts = [i["key"] for i in items if i["state"] == CONFLICT]
    return {"items": items, "conflicts": conflicts, "notes": proposed.get("notes"), "no_npwp": bool(proposed.get("no_npwp"))}


def decided_view(ev: Dict[str, Any], sub: Dict[str, Any], files: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Tampilan pengajuan yang sudah DISETUJUI/DITOLAK: status item diambil dari hasil keputusan (apply_result &
    status lampiran), BUKAN dari diff terhadap data resmi terkini (yang sudah berubah karena keputusan itu sendiri)."""
    status = sub.get("status")
    if status not in (P.APPROVED, P.REJECTED):
        return ev
    res = jl(sub.get("apply_result")) or {}
    applied = res.get("applied") or {}
    skipped = {s.get("key"): s for s in (res.get("skipped") or []) if isinstance(s, dict)}
    fstatus = {f["id"]: f.get("status") for f in files}
    out = []
    for it in ev["items"]:
        it = dict(it, options=[])
        if it["state"] == INFO:
            out.append(it)
            continue
        if status == P.REJECTED:
            st = NOT_APPLIED
        elif it["key"] in skipped:
            st = KEPT if skipped[it["key"]].get("resolution") == KEEP_CURRENT else NOT_APPLIED
        elif it["kind"] == "field":
            st = APPLIED if it["field"] in (applied.get("fields") or []) else NOT_APPLIED
        elif it["kind"] in ("custom", "custom_file"):
            st = APPLIED if it["field"] in (applied.get("custom") or []) else NOT_APPLIED
        elif it["kind"] == "photo":
            st = APPLIED if applied.get("photo") else NOT_APPLIED
        elif it["kind"] == "document":
            st = APPLIED if fstatus.get(it.get("file_id")) == FILE_PROMOTED else NOT_APPLIED
        else:  # keluarga: diterapkan kecuali tercatat dilewati
            st = NOT_APPLIED if it["state"] == SKIPPED else APPLIED
        it["state"] = st
        it["note"] = ("Dokumen baru ditambahkan sebagai dokumen resmi; dokumen lama tidak dihapus."
                      if st == APPLIED and it["kind"] == "document" else None)
        out.append(it)
    return dict(ev, items=out, conflicts=[])


def change_summary(sub: Dict[str, Any], files: Optional[List[Dict[str, Any]]] = None) -> Dict[str, int]:
    proposed = jl(sub.get("proposed")) or {}
    out: Dict[str, int] = {}
    for k in (proposed.get("fields") or {}):
        sec = (P.EDITABLE_FIELDS.get(k) or ("personal",))[0]
        out[sec] = out.get(sec, 0) + 1
    if proposed.get("family"):
        out["family"] = len(proposed["family"])
    custom = len(proposed.get("custom") or {})
    if custom:
        out["custom"] = custom
    if files:
        out["documents"] = len(files)
    return out


# ------------------------------------------------------------------ presentasi (masking)
def _display(field: Optional[str], v: Any, labels: Dict[str, Dict[str, str]]) -> Any:
    if v is None or v == "":
        return None
    if field in labels and isinstance(v, str):
        return labels[field].get(v, v)
    return v


def _mask_family(d: Optional[Dict[str, Any]], full: bool, labels) -> Optional[Dict[str, Any]]:
    if not d:
        return None
    out = {k: d.get(k) for k in P.FAMILY_EDITABLE}
    out["is_emergency_contact"] = bool(out.get("is_emergency_contact"))
    out["relationship_label"] = labels["relationship"].get((out.get("relationship") or "").upper(), out.get("relationship"))
    if out.get("nik") and not full:
        out["nik"] = mask_value(out["nik"])
    return out


def present_items(items: List[Dict[str, Any]], full: bool, labels) -> List[Dict[str, Any]]:
    out = []
    for it in items:
        o = {k: v for k, v in it.items() if k not in ("baseline",)}
        o["state_label"] = STATE_LABELS.get(it["state"])
        if it["kind"] == "field":
            for side in ("current", "proposed"):
                v = it.get(side)
                if it.get("sensitive") and v and not full:
                    o[side] = mask_value(v)
                else:
                    o[side] = _display(it.get("field"), v, labels)
        elif it["kind"] == "family":
            o["current"] = _mask_family(it.get("current"), full, labels)
            o["proposed"] = _mask_family(it.get("proposed"), full, labels)
            o["label"] = {"add": "Tambah anggota keluarga", "update": "Ubah anggota keluarga",
                          "remove": "Hapus anggota keluarga"}.get(it.get("op"), "Keluarga")
        elif it["kind"] == "custom_file":
            cur = it.get("current")
            o["current"] = [x.get("file_name") for x in (cur or {}).get("files", [])] if isinstance(cur, dict) else cur
        out.append(o)
    return out


# ------------------------------------------------------------------ keputusan
def _history_entry(sub: Dict[str, Any], decision: str, ctx, note: Optional[str], items: Optional[List[str]] = None) -> Dict[str, Any]:
    return {"round": int(sub.get("revision_count") or 0) + 1, "submitted_at": iso(sub.get("submitted_at")),
            "decision": decision, "decided_at": now().isoformat(), "reviewer_id": ctx.user_id,
            "reviewer": (ctx.user or {}).get("full_name"), "note": note, "items": items or [],
            "changed_fields": jl(sub.get("changed_fields")) or []}


async def _lock_pending(tx, cid: str, sub: Dict[str, Any], version: int) -> Dict[str, Any]:
    cur = await tx.select_one_for_update("employee_update_submissions", {"id": sub["id"], "company_id": cid})
    if not cur or cur.get("status") != P.PENDING or int(cur.get("version") or 0) != int(version):
        raise HTTPException(status.HTTP_409_CONFLICT, MSG_PROCESSED)
    return cur


def _check_pending(sub: Dict[str, Any], version: int) -> None:
    if sub.get("status") != P.PENDING or int(sub.get("version") or 0) != int(version):
        raise HTTPException(status.HTTP_409_CONFLICT, MSG_PROCESSED)


async def reject(ctx, sub: Dict[str, Any], version: int, reason: str) -> None:
    _check_pending(sub, version)
    cid, ts = ctx.company_id, now()
    history = (jl(sub.get("review_history")) or []) + [_history_entry(sub, P.REJECTED, ctx, reason)]
    emp = await ctx.tdb.employees.find_one({"company_id": cid, "id": sub["employee_id"]}, {"employee_number": 1}) or {}
    audit = build_audit_entry(ctx, "employee_update.rejected", RESOURCE, sub["id"], emp.get("employee_number"), None,
                              {"status": P.REJECTED, "changed_fields": jl(sub.get("changed_fields")) or [],
                               "employee_id": sub["employee_id"]}, module=MODULE, notes=reason)
    async with transaction() as tx:
        await _lock_pending(tx, cid, sub, version)
        await tx.update("employee_update_submissions", {"id": sub["id"], "company_id": cid}, {
            "status": P.REJECTED, "open_slot": None, "reviewed_by": ctx.user_id,
            "reviewed_by_name": (ctx.user or {}).get("full_name"), "reviewed_at": ts, "review_note": reason,
            "review_history": history, "apply_result": {"decision": P.REJECTED, "applied": {}, "skipped": []},
            "version": int(version) + 1, "updated_at": ts, "updated_by": ctx.user_id})
        await tx.update("employee_submission_files", {"company_id": cid, "submission_id": sub["id"], "status": "active"},
                        {"status": FILE_REJECTED, "review_status_at": ts, "updated_at": ts})
        await tx.insert("audit_logs", audit)


async def request_revision(ctx, sub: Dict[str, Any], version: int, note: str, items: List[str]) -> None:
    _check_pending(sub, version)
    cid, ts = ctx.company_id, now()
    history = (jl(sub.get("review_history")) or []) + [_history_entry(sub, P.REVISION, ctx, note, items)]
    emp = await ctx.tdb.employees.find_one({"company_id": cid, "id": sub["employee_id"]}, {"employee_number": 1}) or {}
    audit = build_audit_entry(ctx, "employee_update.revision_requested", RESOURCE, sub["id"], emp.get("employee_number"), None,
                              {"status": P.REVISION, "items": items, "revision_count": int(sub.get("revision_count") or 0) + 1,
                               "employee_id": sub["employee_id"]}, module=MODULE, notes=note)
    async with transaction() as tx:
        await _lock_pending(tx, cid, sub, version)
        await tx.update("employee_update_submissions", {"id": sub["id"], "company_id": cid}, {
            "status": P.REVISION, "reviewed_by": ctx.user_id, "reviewed_by_name": (ctx.user or {}).get("full_name"),
            "reviewed_at": ts, "review_note": note, "revision_count": int(sub.get("revision_count") or 0) + 1,
            "review_history": history, "version": int(version) + 1, "updated_at": ts, "updated_by": ctx.user_id})
        await tx.insert("audit_logs", audit)


def _photo_prefix(cid: str, eid: str) -> str:
    return f"{S.APP_NAME}/companies/{cid}/employees/{eid}/photo/"


async def approve(ctx, sub: Dict[str, Any], version: int, resolutions: Dict[str, str], confirm_identity: bool,
                  note: Optional[str]) -> Dict[str, Any]:
    _check_pending(sub, version)
    cid, tdb, eid = ctx.company_id, ctx.tdb, sub["employee_id"]
    data = await load_context(tdb, cid, sub)
    emp = data["emp"]
    if not emp or emp.get("status") != "active":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Karyawan tidak lagi aktif. Pengajuan ini tidak dapat diterapkan - silakan Tolak dengan alasan.")
    enums, _labels = _enums_and_labels()
    ev = evaluate(sub, data, enums)
    by_key = {i["key"]: i for i in ev["items"]}
    unknown = sorted(k for k in resolutions if k not in by_key or by_key[k]["state"] != CONFLICT)
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Resolusi hanya berlaku untuk item yang konflik: " + ", ".join(unknown) + ".")
    missing = [k for k in ev["conflicts"] if k not in resolutions]
    if missing:
        raise UnresolvedConflicts(missing)
    for k, r in resolutions.items():
        if r not in by_key[k]["options"]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Pilihan resolusi tidak valid untuk {k}.")

    def applies(it: Dict[str, Any]) -> bool:
        return it["state"] == OK or (it["state"] == CONFLICT and resolutions.get(it["key"]) == USE_PROPOSED)

    core_patch: Dict[str, Any] = {}
    for it in ev["items"]:
        if it["kind"] == "field" and applies(it):
            k, v = it["field"], it["proposed"]
            if k not in P.EDITABLE_FIELDS:  # whitelist ulang (defense in depth)
                continue
            if v is not None and P.validate_field(k, v, enums):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Nilai usulan untuk '{it['label']}' tidak valid.")
            core_patch[k] = v
    identity_applied = any(k in P.IDENTITY_FIELDS for k in core_patch)
    if identity_applied and not confirm_identity:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Pengajuan mengubah data identitas (nama/NIK/tanggal lahir). Centang konfirmasi identitas untuk melanjutkan.")
    if core_patch.get("nik"):
        dup = await tdb.employees.find_one({"company_id": cid, "nik": core_patch["nik"], "id": {"$ne": eid},
                                            "status": {"$ne": "deleted"}}, {"id": 1})
        if dup:
            raise HTTPException(status.HTTP_409_CONFLICT, "NIK KTP usulan sudah dipakai karyawan lain. Pengajuan tidak dapat diterapkan.")
    from ..routers.employee_profile import FamilyInput  # lazy import
    family_plan: List[Tuple[str, Optional[str], Dict[str, Any]]] = []
    for it in ev["items"]:
        if it["kind"] != "family" or not applies(it):
            continue
        if it["op"] in ("add", "update"):
            try:
                fam = FamilyInput(**{k: (it["proposed"] or {}).get(k) for k in P.FAMILY_EDITABLE
                                     if (it["proposed"] or {}).get(k) is not None})
            except ValidationError:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Data keluarga usulan tidak valid lagi.") from None
            clean = {k: v for k, v in fam.model_dump().items() if k in P.FAMILY_EDITABLE}
            family_plan.append((it["op"], it.get("ref"), clean))
        elif it["op"] == "remove":
            family_plan.append(("remove", it.get("ref"), {}))
    custom_plan = {it["field"]: it["proposed"] for it in ev["items"] if it["kind"] == "custom" and applies(it)}
    files_by_id = {f["id"]: f for f in data["files"]}
    custom_file_plan = {it["field"]: [files_by_id[i] for i in it["file_ids"]] for it in ev["items"]
                        if it["kind"] == "custom_file" and applies(it)}
    photo_item = by_key.get("photo")
    photo_file = files_by_id.get(photo_item["file_id"]) if photo_item and applies(photo_item) else None
    doc_items = [it for it in ev["items"] if it["kind"] == "document" and applies(it)]

    # ---- salin objek storage SEBELUM transaksi (kompensasi bila transaksi gagal)
    copied: List[str] = []
    doc_rows: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    photo_path = None
    try:
        for it in doc_items:
            f = files_by_id[it["file_id"]]
            doc_id = new_id()
            dst = S.object_path(cid, doc_id, f.get("file_extension"))
            S.copy_object(f["storage_path"], dst, f.get("mime_type"))
            copied.append(dst)
            dt = data["doc_types"].get(f.get("document_type_id")) or {}
            doc_rows.append((f, {"id": doc_id, "company_id": cid, "status": "active", "document_type_id": f.get("document_type_id"),
                                 "name": dt.get("name") or f.get("document_type_code"), "owner_type": "employee", "owner_id": eid,
                                 "owner_label": emp.get("full_name"), "file_name": f.get("file_name"), "storage_path": dst,
                                 "file_size": f.get("file_size"), "file_extension": f.get("file_extension"),
                                 "mime_type": f.get("mime_type"), "is_deleted": False, "version": 1,
                                 "notes": "Dari Formulir Pembaruan Data karyawan (diverifikasi HR)",
                                 "created_at": now(), "updated_at": now(), "created_by": ctx.user_id, "updated_by": ctx.user_id}))
        if photo_file:
            photo_path = f"{_photo_prefix(cid, eid)}{new_id()}.{photo_file.get('file_extension')}"
            S.copy_object(photo_file["storage_path"], photo_path, photo_file.get("mime_type"))
            copied.append(photo_path)
    except S.StorageError:
        _cleanup(copied)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Penyimpanan berkas sedang tidak tersedia. Pengajuan BELUM diterapkan - silakan coba lagi.") from None

    ts = now()
    uid, uname = ctx.user_id, (ctx.user or {}).get("full_name")
    applied = {"fields": sorted(core_patch), "family": [f"{op}" for op, _r, _d in family_plan],
               "custom": sorted(custom_plan) + sorted(custom_file_plan), "documents": [d["id"] for _f, d in doc_rows],
               "photo": bool(photo_file)}
    skipped = [{"key": it["key"], "state": it["state"], "resolution": resolutions.get(it["key"])}
               for it in ev["items"] if not applies(it) and it["state"] != INFO]
    apply_result = {"decision": P.APPROVED, "applied": applied, "skipped": skipped, "resolutions": resolutions,
                    "info": ["no_npwp_not_applied"] if ev["no_npwp"] else []}
    history = (jl(sub.get("review_history")) or []) + [_history_entry(sub, P.APPROVED, ctx, note)]
    old_photo = emp.get("photo_path") if photo_file else None
    audits = [build_audit_entry(ctx, "employee_update.approved", RESOURCE, sub["id"], emp.get("employee_number"), None,
                                {"status": P.APPROVED, "applied": applied, "skipped": [s["key"] for s in skipped],
                                 "resolutions": resolutions, "employee_id": eid}, module=MODULE, notes=note)]
    src_note = "Pembaruan data karyawan disetujui HR (Verifikasi Pembaruan Data)"
    emp_patch = dict(core_patch)
    if photo_file:
        emp_patch.update({"photo_path": photo_path, "photo_version": new_id()[:8]})
    if core_patch:
        audits.append(build_audit_entry(ctx, "update", "employee", eid, core_patch.get("full_name") or emp.get("full_name"),
                                        before={k: emp.get(k) for k in core_patch}, after=dict(core_patch), notes=src_note))
    if photo_file:
        audits.append(build_audit_entry(ctx, "photo_replace" if old_photo else "photo_upload", "employee", eid, emp.get("full_name"),
                                        before={"photo": bool(old_photo)}, after={"photo": True, "size": photo_file.get("file_size"),
                                                                                   "content_type": photo_file.get("mime_type")}, notes=src_note))
    try:
        async with transaction() as tx:
            await _lock_pending(tx, cid, sub, version)
            locked = await tx.select_one_for_update("employees", {"id": eid, "company_id": cid})
            if not locked or locked.get("status") != "active":
                raise HTTPException(status.HTTP_409_CONFLICT, MSG_CHANGED)
            for it in ev["items"]:  # deteksi konflik diulang di dalam transaksi
                if it["kind"] == "field" and _norm(it["field"], locked.get(it["field"])) != _norm(it["field"], emp.get(it["field"])):
                    raise HTTPException(status.HTTP_409_CONFLICT, MSG_CHANGED)
            if photo_item and (locked.get("photo_version") or None) != (emp.get("photo_version") or None):
                raise HTTPException(status.HTTP_409_CONFLICT, MSG_CHANGED)
            for op, ref, _d in family_plan:
                if op in ("update", "remove"):
                    row = await tx.select_one_for_update("employee_family_members", {"id": ref, "company_id": cid})
                    if _fam_norm(row) != _fam_norm(data["family"].get(ref)):
                        raise HTTPException(status.HTTP_409_CONFLICT, MSG_CHANGED)
            for k in list(custom_plan) + list(custom_file_plan):
                row = await tx.select_one_for_update("employee_custom_field_values",
                                                     {"company_id": cid, "employee_id": eid, "field_key": k})
                if (tx_json(row.get("value")) if row else None) != data["official"].get(k):
                    raise HTTPException(status.HTTP_409_CONFLICT, MSG_CHANGED)
            # ---- apply
            if emp_patch:
                await tx.update("employees", {"id": eid, "company_id": cid}, {**emp_patch, "updated_at": ts, "updated_by": uid})
            for op, ref, fdata in family_plan:
                if op == "add":
                    row = {"id": new_id(), "company_id": cid, "status": "active", "employee_id": eid, **fdata,
                           "created_at": ts, "updated_at": ts, "created_by": uid, "updated_by": uid}
                    await tx.insert("employee_family_members", row)
                    audits.append(build_audit_entry(ctx, "family_create", "employee", eid, emp.get("full_name"),
                                                    after=fdata, notes=src_note))
                elif op == "update":
                    full = {k: fdata.get(k) for k in P.FAMILY_EDITABLE}
                    full["is_emergency_contact"] = bool(full.get("is_emergency_contact"))
                    await tx.update("employee_family_members", {"id": ref, "company_id": cid},
                                    {**full, "updated_at": ts, "updated_by": uid})
                    before = {k: data["family"][ref].get(k) for k in P.FAMILY_EDITABLE}
                    audits.append(build_audit_entry(ctx, "family_update", "employee", eid, emp.get("full_name"),
                                                    before=before, after=full, notes=src_note))
                else:
                    before = {k: data["family"][ref].get(k) for k in P.FAMILY_EDITABLE}
                    await tx.delete("employee_family_members", {"id": ref, "company_id": cid})
                    audits.append(build_audit_entry(ctx, "family_delete", "employee", eid, emp.get("full_name"),
                                                    before=before, notes=src_note))
            official_values = dict(custom_plan)
            for fk, fl in custom_file_plan.items():
                official_values[fk] = {"files": [{"submission_file_id": f["id"], "file_name": f.get("file_name"),
                                                  "mime_type": f.get("mime_type"), "file_size": f.get("file_size")} for f in fl]}
            for fk, val in official_values.items():
                text = ", ".join(val) if isinstance(val, list) else (
                    ", ".join(x["file_name"] or "" for x in val["files"]) if isinstance(val, dict) else str(val))
                vals = {"value": val, "value_text": text[:512], "source_submission_id": sub["id"], "updated_at": ts, "updated_by": uid}
                n = await tx.update("employee_custom_field_values", {"company_id": cid, "employee_id": eid, "field_key": fk}, vals)
                if not n:
                    await tx.insert("employee_custom_field_values", {"id": new_id(), "company_id": cid, "status": "active",
                                                                     "employee_id": eid, "field_key": fk, **vals,
                                                                     "created_at": ts, "created_by": uid})
            if official_values:
                audits.append(build_audit_entry(ctx, "custom_fields_update", "employee", eid, emp.get("full_name"),
                                                after={"fields": sorted(official_values)}, notes=src_note))
            for f, doc in doc_rows:
                await tx.insert("documents", doc)
                await tx.update("employee_submission_files", {"id": f["id"], "company_id": cid},
                                {"status": FILE_PROMOTED, "document_id": doc["id"], "review_status_at": ts, "updated_at": ts})
                audits.append(build_audit_entry(ctx, "upload", "document", doc["id"], doc["name"],
                                                after={k: v for k, v in doc.items() if k != "storage_path"}, notes=src_note))
            promoted = {f["id"] for f, _d in doc_rows} | ({photo_file["id"]} if photo_file else set()) | \
                       {f["id"] for fl in custom_file_plan.values() for f in fl}
            for fid in promoted - {f["id"] for f, _d in doc_rows}:
                await tx.update("employee_submission_files", {"id": fid, "company_id": cid},
                                {"status": FILE_PROMOTED, "review_status_at": ts, "updated_at": ts})
            for f in data["files"]:  # lampiran yang tidak dipromosikan (dilewati / foto lama yang tergantikan)
                if f.get("status") == "active" and f["id"] not in promoted:
                    await tx.update("employee_submission_files", {"id": f["id"], "company_id": cid},
                                    {"status": FILE_REJECTED, "review_status_at": ts, "updated_at": ts})
            await tx.update("employee_update_submissions", {"id": sub["id"], "company_id": cid}, {
                "status": P.APPROVED, "open_slot": None, "reviewed_by": uid, "reviewed_by_name": uname, "reviewed_at": ts,
                "review_note": note, "review_history": history, "apply_result": apply_result,
                "version": int(version) + 1, "updated_at": ts, "updated_by": uid})
            for a in audits:
                await tx.insert("audit_logs", a)
    except BaseException:
        _cleanup(copied)
        raise
    # ---- setelah commit
    if old_photo and old_photo != photo_path and old_photo.startswith(_photo_prefix(cid, eid)):
        try:
            S.delete_object(old_photo)
        except Exception:  # noqa: BLE001 - objek lama yatim tidak boleh menggagalkan keputusan yang sudah commit
            logger.warning("Gagal menghapus foto lama karyawan %s setelah approval 01H.", eid)
    await engine.safe_refresh(cid, [eid], "hr_verification", uid)
    snap = await tdb.employee_completeness.find_one({"company_id": cid, "employee_id": eid}, NO_ID) or {}
    after = {"score_pct": snap.get("score_pct"), "status": snap.get("completeness_status"),
             "missing_codes": jl(snap.get("missing_codes")) or []}
    await tdb.employee_update_submissions.update_one({"id": sub["id"]}, {"$set": {"completeness_after": after}})
    return {"applied": applied, "skipped": skipped, "completeness_after": after}


def _cleanup(paths: List[str]) -> None:
    for p in paths:
        try:
            S.delete_object(p)
        except Exception:  # noqa: BLE001
            logger.warning("Kompensasi: gagal menghapus salinan objek %s", p)
