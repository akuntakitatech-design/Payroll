"""Enhancement 01G - Form Pembaruan Data (backoffice): active form, monitoring, Form Builder settings.

View (employee:view)           : GET /employees/update-form/overview, /monitoring
Configure (employee_form:configure): GET /config, /preview; POST/PUT sections; PUT /layout; POST/PUT fields; scopes
Core fields: only visible / label / help text / order / section. Core levels are READ from 01F (never written here).
Custom fields `cf_*`: never hard-deleted (only inactive). This router never writes 01F rules/snapshots or master employee data.
"""
import re
from typing import Any, Dict, List, Literal, Optional

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from ..core import completeness as engine
from ..core import form_builder as FB
from ..core import public_form as P
from ..core.audit import log_action
from ..core.db import NO_ID, audit_fields, get_engine, new_id, now
from ..core import data_scope as dscope  # Upgrade 01I
from ..core.deps import AuthContext, require_permission
from .completeness import SCOPE_COLLECTIONS

router = APIRouter(prefix="/employees/update-form", tags=["employee-form-builder"])
_view = require_permission("employee", "view")
_conf = dscope.full_scope_dependency(require_permission("employee_form", "configure"))  # 01I: konfigurasi tenant-wide -> 403 restricted
MODULE, RESOURCE = "employee_core", "employee_form"
_ID_RE = re.compile(r"^[A-Za-z0-9\-]{1,64}$")


def _bad(msg: str, code: int = status.HTTP_422_UNPROCESSABLE_ENTITY) -> HTTPException:
    return HTTPException(code, msg)


# =================================================================== view: form aktif + monitoring
@router.get("/overview")
async def overview(ctx: AuthContext = Depends(_view)):
    cfg = await FB.load_config(ctx.company_id)
    code = (ctx.company or {}).get("code")
    fields = [f for f in cfg["fields"] if f["active"]]
    return {"company": {"name": (ctx.company or {}).get("name"), "code": code},
            "public_path": f"/public/{code}/update-data" if code else None,
            "form": {"version": cfg["version"], "sections_active": sum(1 for s in cfg["sections"] if s["active"]),
                     "fields_visible": sum(1 for f in fields if f["visible"]),
                     "custom_active": sum(1 for f in fields if f["source"] == "CUSTOM")},
            "can_configure": "employee_form:configure" in ctx.permissions or "*:*" in ctx.permissions}


_MON_SQL = """
SELECT COUNT(*) AS active_employees,
       COALESCE(SUM(s.employee_id IS NULL), 0) AS not_started,
       COALESCE(SUM(s.has_draft), 0) AS draft,
       COALESCE(SUM(s.has_submitted), 0) AS submitted,
       COALESCE(SUM(s.has_pending), 0) AS pending_hr,
       COALESCE(SUM(s.has_revision), 0) AS revision_requested,
       COALESCE(SUM(s.has_approved), 0) AS approved,
       COALESCE(SUM(s.has_rejected), 0) AS rejected
FROM employees e
{assign_join}
LEFT JOIN (
    SELECT employee_id, MAX(status = :draft) AS has_draft, MAX(submitted_at IS NOT NULL) AS has_submitted,
           MAX(status = :pending) AS has_pending, MAX(status = :revision) AS has_revision,
           MAX(status = :approved) AS has_approved, MAX(status = :rejected) AS has_rejected
    FROM employee_update_submissions WHERE company_id = :cid GROUP BY employee_id
) s ON s.employee_id = e.id
WHERE e.company_id = :cid AND e.status = 'active' {where}
"""
_ASSIGN_JOIN = """LEFT JOIN (
    SELECT employee_id, MAX(project_id) AS project_id FROM employee_assignments
    WHERE company_id = :cid AND assignment_status = 'ACTIVE' GROUP BY employee_id
) a ON a.employee_id = e.id"""


async def monitoring_summary(cid: str, project_id: Optional[str] = None, department_id: Optional[str] = None,
                             employee_status_id: Optional[str] = None, scope_project_ids=None) -> Dict[str, int]:
    """DB-side aggregate (1 query, tenant-scoped, no N+1). Semantics identical to the 01G state:
    not_started = active employee without any submission row; draft = has a DRAFT; submitted = ever submitted
    (submitted_at set); pending_hr = has a PENDING_HR_VERIFICATION submission. Project = active assignment, else employee.project_id."""
    where, params = [], {"cid": cid, "draft": P.DRAFT, "pending": P.PENDING, "revision": P.REVISION,
                         "approved": P.APPROVED, "rejected": P.REJECTED}
    if project_id:
        where.append("AND COALESCE(a.project_id, e.project_id) = :project_id")
        params["project_id"] = project_id
    if department_id:
        where.append("AND e.department_id = :department_id")
        params["department_id"] = department_id
    if employee_status_id:
        where.append("AND e.current_employee_status_id = :status_id")
        params["status_id"] = employee_status_id
    # Upgrade 01I: scope_project_ids None = ALL_TENANT; set (bisa kosong) = hanya karyawan dengan assignment
    # ACTIVE pada project tsb (sumber otoritatif 01D), di SQL. Kosong -> 0 (fail-closed).
    if scope_project_ids is not None:
        if scope_project_ids:
            where.append("AND e.id IN (SELECT sa1.employee_id FROM employee_assignments sa1 WHERE sa1.company_id = :cid"
                         " AND sa1.assignment_status = 'ACTIVE' AND sa1.project_id IN :scope_pids)")
            params["scope_pids"] = sorted(scope_project_ids)
        else:
            where.append("AND 1 = 0")
    q = _MON_SQL.format(assign_join=_ASSIGN_JOIN if project_id else "", where=" ".join(where))
    stmt = sa.text(q)
    if "scope_pids" in params:
        stmt = stmt.bindparams(sa.bindparam("scope_pids", expanding=True))
    async with get_engine().connect() as conn:
        row = (await conn.execute(stmt, params)).mappings().one()
    return {k: int(row[k] or 0) for k in ("active_employees", "not_started", "draft", "submitted", "pending_hr",
                                          "revision_requested", "approved", "rejected")}  # 01H: status keputusan HR


@router.get("/monitoring")
async def monitoring(project_id: Optional[str] = Query(None, max_length=64), department_id: Optional[str] = Query(None, max_length=64),
                     employee_status_id: Optional[str] = Query(None, max_length=64), ctx: AuthContext = Depends(_view)):
    cid, tdb = ctx.company_id, ctx.tdb
    allowed = await dscope.allowed_project_ids(ctx)  # Upgrade 01I
    summary = await monitoring_summary(cid, project_id, department_id, employee_status_id, scope_project_ids=allowed)
    opts = {}
    for key, coll in (("projects", "projects"), ("departments", "departments"), ("employee_statuses", "employee_business_statuses")):
        rows = await tdb[coll].find({"company_id": cid, "status": {"$nin": ["deleted", "inactive"]}}, {"id": 1, "name": 1, "code": 1}).to_list(1000)
        if coll == "projects" and allowed is not None:
            rows = [r for r in rows if r["id"] in allowed]
        opts[key] = sorted([{"id": r["id"], "label": r.get("name") or r.get("code") or r["id"]} for r in rows], key=lambda x: x["label"])
    return {"summary": summary, "filters": opts,
            "note": "Draft & kiriman belum mengubah data master sampai disetujui di menu Verifikasi Pembaruan Data (01H)."}


# =================================================================== configure
async def _scope_options(ctx: AuthContext) -> Dict[str, List[Dict[str, str]]]:
    out = {}
    for stype, coll in SCOPE_COLLECTIONS.items():
        rows = await ctx.tdb[coll].find({"company_id": ctx.company_id, "status": {"$ne": "deleted"}}, {"id": 1, "name": 1, "code": 1}).to_list(1000)
        out[stype] = sorted([{"id": r["id"], "label": f"{r.get('code') or ''} {r.get('name') or ''}".strip() or r["id"]} for r in rows],
                            key=lambda x: x["label"])
    return out


@router.get("/config")
async def get_config(ctx: AuthContext = Depends(_conf)):
    cfg = await FB.load_config(ctx.company_id)
    levels = FB.levels_from_rules(await engine.load_rules(ctx.company_id))
    for f in cfg["fields"]:
        if f["source"] == "CORE":
            lv = levels.get(f["key"], "NOT_APPLICABLE")
            f["level"], f["level_label"] = lv, FB.LEVEL_LABELS.get(lv, "Tidak Dinilai")
            # hidden but REQUIRED by 01F rules -> still shown on the public form (01F REQUIRED > hidden)
            f["forced_when_hidden"] = (not f["visible"]) and lv == "REQUIRED"
        else:
            f["level"], f["level_label"] = f["form_level"], FB.LEVEL_LABELS[f["form_level"]]
        f["scopes"] = [{"id": s["id"], "scope_type": s["scope_type"], "scope_id": s.get("scope_id"), "scope_label": s.get("scope_label"),
                        "mode": s["mode"]} for s in cfg["scopes"].get(f["key"], [])]
    return {"sections": cfg["sections"], "fields": cfg["fields"], "version": cfg["version"],
            "custom_types": list(FB.CUSTOM_TYPES), "custom_levels": list(FB.CUSTOM_LEVELS), "scope_types": FB.SCOPE_TYPES,
            "scope_options": await _scope_options(ctx),
            "notes": {"core_level": "Level field inti mengikuti Master Kelengkapan Data (01F) dan tidak diubah di sini.",
                      "forced": "Field inti yang Wajib (01F) untuk seorang karyawan tetap tampil walaupun disembunyikan."}}


async def _upsert(ctx: AuthContext, coll: str, key_col: str, key: str, patch: Dict[str, Any], create: Dict[str, Any]) -> Dict[str, Any]:
    t = ctx.tdb[coll]
    row = await t.find_one({"company_id": ctx.company_id, key_col: key}, NO_ID)
    if row:
        await t.update_one({"id": row["id"]}, {"$set": {**patch, "updated_at": now(), "updated_by": ctx.user_id}})
        return {**row, **patch}
    doc = {"id": new_id(), "company_id": ctx.company_id, "status": "active", key_col: key, **create, **patch,
           **audit_fields(ctx.user_id, creating=True)}
    await t.insert_one(dict(doc))
    return doc


class SectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: Optional[str] = Field(None, min_length=2, max_length=80)
    description: Optional[str] = Field(None, max_length=300)
    active: Optional[bool] = None


@router.post("/sections", status_code=201)
async def create_section(body: SectionIn, ctx: AuthContext = Depends(_conf)):
    if not body.label:
        raise _bad("Nama section wajib diisi.")
    cfg = await FB.load_config(ctx.company_id)
    existing = {s["key"] for s in cfg["sections"]}
    if len(existing) >= 30:
        raise _bad("Maksimal 30 section.")
    base = "cs_" + (FB.slug(body.label) or "section")[:36]
    key, n = base, 2
    while key in existing or len(key) < 5:
        key, n = f"{base[:38]}_{n}", n + 1
    if not FB.SECTION_KEY_RE.match(key):
        raise _bad("Nama section tidak valid.")
    await _upsert(ctx, "employee_form_sections", "section_key", key,
                  {"label": body.label.strip(), "description": body.description, "status": "active" if body.active is not False else "inactive"},
                  {"is_system": False, "sort_order": max([s["sort_order"] for s in cfg["sections"]] or [0]) + 10})
    await log_action(ctx, "employee_form.section_created", RESOURCE, key, body.label, None, {"label": body.label}, module=MODULE)
    return {"key": key, "message": "Section ditambahkan."}


@router.put("/sections/{key}")
async def update_section(key: str, body: SectionIn, ctx: AuthContext = Depends(_conf)):
    cfg = await FB.load_config(ctx.company_id)
    sec = next((s for s in cfg["sections"] if s["key"] == key), None)
    if not sec:
        raise _bad("Section tidak ditemukan.", 404)
    patch: Dict[str, Any] = {}
    if body.label is not None:
        patch["label"] = body.label.strip()
    if body.description is not None:
        patch["description"] = body.description.strip() or None
    if body.active is not None:
        patch["status"] = "active" if body.active else "inactive"
    if not patch:
        raise _bad("Tidak ada perubahan.")
    await _upsert(ctx, "employee_form_sections", "section_key", key, patch,
                  {"is_system": sec["is_system"], "sort_order": sec["sort_order"]})
    await log_action(ctx, "employee_form.section_updated", RESOURCE, key, sec["label"],
                     {"label": sec["label"], "active": sec["active"]}, patch, module=MODULE)
    return {"message": "Section diperbarui."}


class LayoutSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(..., max_length=64)
    fields: List[str] = Field(default_factory=list, max_length=200)


class LayoutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sections: List[LayoutSection] = Field(..., max_length=40)


@router.put("/layout")
async def save_layout(body: LayoutIn, ctx: AuthContext = Depends(_conf)):
    """Reorder sections + reorder/move fields (drag & drop). Sections/fields not mentioned keep their position."""
    cfg = await FB.load_config(ctx.company_id)
    secs = {s["key"]: s for s in cfg["sections"]}
    fields = {f["key"]: f for f in cfg["fields"]}
    seen = set()
    for ls in body.sections:
        if ls.key not in secs:
            raise _bad(f"Section tidak dikenal: {ls.key}")
        if ls.fields and secs[ls.key]["kind"] != "fields":
            raise _bad(f"Section {secs[ls.key]['label']} tidak dapat berisi field.")
        for k in ls.fields:
            if k not in fields or k in seen:
                raise _bad(f"Field tidak dikenal atau ganda: {k}")
            seen.add(k)
    for i, ls in enumerate(body.sections):
        s = secs[ls.key]
        if s["sort_order"] != i * 10:
            await _upsert(ctx, "employee_form_sections", "section_key", ls.key, {"sort_order": i * 10},
                          {"is_system": s["is_system"], "label": s["label"]})
        for j, k in enumerate(ls.fields):
            f = fields[k]
            if f["section"] != ls.key or f["sort_order"] != j * 10:
                await _upsert(ctx, "employee_form_fields", "field_key", k, {"section_key": ls.key, "sort_order": j * 10},
                              {"source": f["source"], "visible": f["visible"]})
    await log_action(ctx, "employee_form.layout_saved", RESOURCE, None, None, None,
                     {"sections": [ls.key for ls in body.sections], "fields_moved": len(seen)}, module=MODULE)
    return {"message": "Urutan form disimpan.", "version": (await FB.load_config(ctx.company_id))["version"]}


class OptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: Optional[str] = Field(None, max_length=64)
    label: str = Field(..., min_length=1, max_length=120)
    active: bool = True


class FieldIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: Optional[str] = Field(None, max_length=64)
    label: Optional[str] = Field(None, min_length=2, max_length=120)
    label_override: Optional[str] = Field(None, max_length=120)
    help_text: Optional[str] = Field(None, max_length=300)
    placeholder: Optional[str] = Field(None, max_length=120)
    visible: Optional[bool] = None
    active: Optional[bool] = None
    section_key: Optional[str] = Field(None, max_length=64)
    type: Optional[Literal["text", "number", "date", "dropdown", "radio", "checkbox", "textarea", "file"]] = None
    form_level: Optional[Literal["REQUIRED", "RECOMMENDED", "OPTIONAL"]] = None
    options: Optional[List[OptionIn]] = Field(None, max_length=FB.MAX_OPTIONS)
    validation: Optional[Dict[str, Any]] = None


_CORE_ALLOWED = {"label_override", "help_text", "placeholder", "visible", "section_key"}
_NOT_NULLABLE = {"label", "visible", "active", "section_key", "type", "form_level", "options", "validation"}


def _clean_options(opts: List[OptionIn], old: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out, seen = [], set()
    for o in opts:
        val = (o.value or FB.slug(o.label) or "opsi").strip()[:64]
        if not re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", val):
            raise _bad(f"Nilai opsi tidak valid: {o.label}")
        if val in seen:
            raise _bad(f"Opsi ganda: {o.label}")
        seen.add(val)
        out.append({"value": val, "label": o.label.strip(), "active": o.active})
    for o in old:  # an option that already existed is never deleted -> kept as inactive
        if o.get("value") not in seen:
            out.append({**o, "active": False})
    return out


def _clean_validation(t: str, v: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    v = v or {}
    out: Dict[str, Any] = {}
    try:
        if t in ("text", "textarea") and v.get("max_length") not in (None, ""):
            out["max_length"] = max(1, min(int(v["max_length"]), FB.TEXT_MAX if t == "text" else FB.TEXTAREA_MAX))
        if t == "number":
            for k in ("min", "max"):
                if v.get(k) not in (None, ""):
                    out[k] = float(v[k])
            if "min" in out and "max" in out and out["min"] > out["max"]:
                raise _bad("Nilai minimum lebih besar dari maksimum.")
        if t == "file":
            ext = [e for e in (v.get("allowed_ext") or sorted(P.PUBLIC_EXTENSIONS)) if e in P.PUBLIC_EXTENSIONS]
            out["allowed_ext"] = sorted(set(ext)) or sorted(P.PUBLIC_EXTENSIONS)
            out["max_mb"] = min(float(v.get("max_mb") or P.PUBLIC_MAX_MB), P.PUBLIC_MAX_MB)
    except (TypeError, ValueError):
        raise _bad("Aturan validasi tidak valid.") from None
    return out


async def _field_has_data(ctx: AuthContext, key: str) -> bool:
    if not FB.FIELD_KEY_RE.match(key):
        return False
    if await ctx.tdb.employee_custom_field_values.count_documents({"company_id": ctx.company_id, "field_key": key}):
        return True
    if await ctx.tdb.employee_submission_files.count_documents({"company_id": ctx.company_id, "field_key": key}):
        return True
    async with get_engine().connect() as conn:
        n = (await conn.execute(sa.text(
            f"SELECT COUNT(*) FROM employee_update_submissions WHERE company_id = :c AND JSON_EXISTS(proposed, '$.custom.{key}')"),
            {"c": ctx.company_id})).scalar()
    return bool(n)


def _guard_names(key: Optional[str], label: Optional[str]) -> None:
    """Backend-authoritative: a custom field may not use reserved / HR-only / system names (key or label)."""
    if key is not None:
        why = FB.protected_name(key[3:]) if key.startswith("cf_") else "harus diawali cf_"
        if why or key in FB.reserved_keys():
            raise _bad(f"Key '{key}' tidak diizinkan: {why or 'key sistem'}. Status, penempatan, jabatan, grade, payroll, "
                       "kontrak, role/permission, dan field sistem hanya dikelola HR.")
    if label is not None:
        why = FB.protected_name(label) or ("sama dengan label field inti" if FB.slug(label) in FB.core_labels() else None)
        if why:
            raise _bad(f"Label '{label.strip()}' tidak diizinkan: {why}. Gunakan field inti yang sudah ada atau nama lain.")


@router.post("/fields", status_code=201)
async def create_field(body: FieldIn, ctx: AuthContext = Depends(_conf)):
    cfg = await FB.load_config(ctx.company_id)
    if not body.label or not body.type:
        raise _bad("Label dan tipe field wajib diisi.")
    if sum(1 for f in cfg["fields"] if f["source"] == "CUSTOM") >= FB.MAX_CUSTOM_FIELDS:
        raise _bad(f"Maksimal {FB.MAX_CUSTOM_FIELDS} custom field.")
    key = (body.key or ("cf_" + (FB.slug(body.label) or "field"))).strip().lower()[:44]
    if not FB.FIELD_KEY_RE.match(key):
        raise _bad("Key harus diawali 'cf_' dan hanya huruf kecil, angka, atau garis bawah (3-40 karakter setelah cf_).")
    if any(f["key"] == key for f in cfg["fields"]):
        raise _bad("Key sudah dipakai.", status.HTTP_409_CONFLICT)
    _guard_names(key, body.label)
    sections = {s["key"]: s for s in cfg["sections"]}
    section = body.section_key or "personal"
    if section not in sections or sections[section]["kind"] != "fields":
        raise _bad("Section tidak valid untuk field.")
    options = _clean_options(body.options or [], []) if body.type in FB.OPTION_TYPES else []
    if body.type in ("dropdown", "radio") and not [o for o in options if o["active"]]:
        raise _bad("Tipe pilihan memerlukan minimal satu opsi.")
    order = max([f["sort_order"] for f in cfg["fields"] if f["section"] == section] or [0]) + 10
    doc = await _upsert(ctx, "employee_form_fields", "field_key", key, {
        "source": "CUSTOM", "section_key": section, "sort_order": order, "visible": body.visible is not False,
        "label_override": body.label.strip(), "help_text": body.help_text, "placeholder": body.placeholder,
        "field_type": body.type, "options": options, "validation": _clean_validation(body.type, body.validation),
        "form_level": body.form_level or "OPTIONAL", "data_version": 1, "status": "active"}, {})
    await log_action(ctx, "employee_form.field_created", RESOURCE, doc["id"], key, None,
                     {"type": body.type, "section": section, "form_level": body.form_level or "OPTIONAL"}, module=MODULE)
    return {"key": key, "message": "Custom field ditambahkan."}


@router.put("/fields/{key}")
async def update_field(key: str, body: FieldIn, ctx: AuthContext = Depends(_conf)):
    cfg = await FB.load_config(ctx.company_id)
    f = next((x for x in cfg["fields"] if x["key"] == key), None)
    if not f:
        raise _bad("Field tidak ditemukan.", 404)
    sent = body.model_dump(exclude_unset=True)
    if body.key is not None and body.key != key:
        raise _bad("Key field tidak dapat diubah.")
    sent.pop("key", None)
    nulls = sorted(k for k in _NOT_NULLABLE if k in sent and sent[k] is None)
    if nulls:  # code review 01G-FB: explicit null must not be stored (would silently fall back to defaults)
        raise _bad("Nilai tidak boleh kosong: " + ", ".join(nulls) + ".")
    if body.section_key is not None:
        sec = next((s for s in cfg["sections"] if s["key"] == body.section_key), None)
        if not sec or sec["kind"] != "fields":
            raise _bad("Section tidak valid untuk field.")
    patch: Dict[str, Any] = {}
    if f["source"] == "CORE":
        extra = set(sent) - _CORE_ALLOWED
        if extra:
            raise _bad("Field inti hanya dapat diatur tampil/sembunyi, label, teks bantuan, dan section. "
                       "Level Wajib/Anjuran diatur di Master Kelengkapan Data.")
        for k in ("help_text", "placeholder", "visible", "section_key"):
            if k in sent:
                patch[k] = sent[k]
        if "label_override" in sent:
            patch["label_override"] = (sent["label_override"] or "").strip() or None
    else:
        has_data = await _field_has_data(ctx, key)
        if body.type and body.type != f["type"]:
            if has_data and not (f["type"] == "text" and body.type == "textarea"):
                raise _bad("Tipe field tidak dapat diubah karena sudah memiliki data.", status.HTTP_409_CONFLICT)
            patch["field_type"] = body.type
        t = patch.get("field_type") or f["type"]
        if body.label is not None:
            if body.label.strip() != f["label"]:
                _guard_names(None, body.label)
            patch["label_override"] = body.label.strip()
        for k in ("help_text", "placeholder", "visible", "section_key", "form_level"):
            if k in sent:
                patch[k] = sent[k]
        if body.active is not None:
            patch["status"] = "active" if body.active else "inactive"
        if body.options is not None:
            patch["options"] = _clean_options(body.options, f["options"]) if t in FB.OPTION_TYPES else []
            if t in ("dropdown", "radio") and not [o for o in patch["options"] if o["active"]]:
                raise _bad("Tipe pilihan memerlukan minimal satu opsi aktif.")
        if body.validation is not None or "field_type" in patch:
            patch["validation"] = _clean_validation(t, body.validation if body.validation is not None else f["validation"])
        patch["data_version"] = int(f.get("data_version") or 0) + 1
    if not patch:
        raise _bad("Tidak ada perubahan.")
    await _upsert(ctx, "employee_form_fields", "field_key", key, patch,
                  {"source": f["source"], "section_key": f["section"], "sort_order": f["sort_order"], "visible": f["visible"]})
    before = {k: f.get({"label_override": "label", "field_type": "type", "section_key": "section", "status": "active"}.get(k, k)) for k in patch}
    await log_action(ctx, "employee_form.field_updated", RESOURCE, None, key, before, patch, module=MODULE)
    return {"message": "Field diperbarui."}


class ScopeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope_type: str = Field(..., max_length=32)
    scope_id: Optional[str] = Field(None, max_length=64)
    mode: Literal["INCLUDE", "EXCLUDE"] = "INCLUDE"


@router.post("/fields/{key}/scopes", status_code=201)
async def add_scope(key: str, body: ScopeIn, ctx: AuthContext = Depends(_conf)):
    cfg = await FB.load_config(ctx.company_id)
    f = next((x for x in cfg["fields"] if x["key"] == key), None)
    if not f:
        raise _bad("Field tidak ditemukan.", 404)
    stype = body.scope_type.strip().lower()
    if stype not in FB.SCOPE_TYPES or stype == "business_status_category":
        raise _bad("Jenis scope tidak dikenal.")
    scope_id, label = None, FB.SCOPE_TYPES["company"]
    if stype != "company":
        if not body.scope_id or not _ID_RE.match(body.scope_id):
            raise _bad("Pilih data scope yang valid.")
        ref = await ctx.tdb[SCOPE_COLLECTIONS[stype]].find_one(
            {"company_id": ctx.company_id, "id": body.scope_id, "status": {"$ne": "deleted"}}, NO_ID)
        if not ref:  # tenant isolation: referensi harus milik tenant aktif
            raise _bad("Data scope tidak ditemukan pada perusahaan aktif.")
        scope_id, label = body.scope_id, f"{FB.SCOPE_TYPES[stype]}: {ref.get('code') or ''} {ref.get('name') or ''}".strip()
    if len(cfg["scopes"].get(key, [])) >= 50:
        raise _bad("Maksimal 50 scope per field.")
    if any(s["scope_type"] == stype and (s.get("scope_id") or None) == scope_id and s["mode"] == body.mode for s in cfg["scopes"].get(key, [])):
        raise _bad("Scope yang sama sudah ada.", status.HTTP_409_CONFLICT)
    doc = {"id": new_id(), "company_id": ctx.company_id, "status": "active", "field_key": key, "scope_type": stype,
           "scope_id": scope_id, "scope_label": label, "mode": body.mode, **audit_fields(ctx.user_id, creating=True)}
    await ctx.tdb.employee_form_field_scopes.insert_one(dict(doc))
    await log_action(ctx, "employee_form.scope_added", RESOURCE, doc["id"], key, None,
                     {"scope_type": stype, "scope_id": scope_id, "mode": body.mode}, module=MODULE)
    return {"id": doc["id"], "message": "Scope ditambahkan."}


@router.delete("/fields/{key}/scopes/{scope_id}")
async def remove_scope(key: str, scope_id: str, ctx: AuthContext = Depends(_conf)):
    row = await ctx.tdb.employee_form_field_scopes.find_one(
        {"company_id": ctx.company_id, "id": scope_id, "field_key": key, "status": {"$ne": "deleted"}}, NO_ID)
    if not row:
        raise _bad("Scope tidak ditemukan.", 404)
    await ctx.tdb.employee_form_field_scopes.update_one({"id": row["id"]}, {"$set": {
        "status": "deleted", "updated_at": now(), "updated_by": ctx.user_id}})
    await log_action(ctx, "employee_form.scope_removed", RESOURCE, row["id"], key,
                     {"scope_type": row["scope_type"], "scope_id": row.get("scope_id"), "mode": row["mode"]}, None, module=MODULE)
    return {"message": "Scope dihapus."}


@router.get("/preview")
async def preview(employee_id: Optional[str] = Query(None, max_length=64), ctx: AuthContext = Depends(_conf)):
    """Read-only preview. With employee_id: layout as that employee would see it (01F snapshot is only READ)."""
    cfg = await FB.load_config(ctx.company_id)
    if not employee_id:
        levels, forced, forced_sec = FB.levels_without_snapshot(await engine.load_rules(ctx.company_id))
        layout = FB.resolve_layout(cfg, levels, forced, forced_sec)
        return {"mode": "GENERIC", "employee": None, "layout": layout,
                "note": "Pratinjau umum (read-only): field ber-scope ditampilkan semua; field inti Wajib (01F) tetap tampil walau disembunyikan. Tidak membuat draft/kiriman."}
    emp = await ctx.tdb.employees.find_one({"company_id": ctx.company_id, "id": employee_id}, NO_ID)
    if not emp:
        raise _bad("Karyawan tidak ditemukan.", 404)
    snap = await ctx.tdb.employee_completeness.find_one({"company_id": ctx.company_id, "employee_id": employee_id}, NO_ID) or {}
    items = snap.get("items")
    items = FB._j(items) or []
    if items:
        levels, forced, forced_sec = FB.levels_from_snapshot(items)
    else:
        levels, forced, forced_sec = FB.levels_without_snapshot(await engine.load_rules(ctx.company_id))
    layout = FB.resolve_layout(cfg, levels, forced, forced_sec, emp, await FB.scope_context(ctx.company_id, emp))
    return {"mode": "EMPLOYEE", "employee": {"id": emp["id"], "employee_number": emp.get("employee_number"),
                                             "full_name": emp.get("full_name")}, "layout": layout}
