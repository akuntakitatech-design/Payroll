"""Upgrade 01F - API Kelengkapan Data.

Melihat kelengkapan  : `employee:view` (tenant-scoped; company_id dari token).
Mengelola Master     : `employee_completeness:configure` (level per requirement + scope applicability).
Respons hanya berisi kode/status/skor - tidak ada nilai field / nilai sensitif.
"""
import re
from datetime import date
from typing import Any, Dict, List, Optional

import json

import sqlalchemy as sa
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, text

from ..core import completeness as engine
from ..core import completeness_mapping as M
from ..core.audit import build_audit_entry, log_action
from ..core.db import NO_ID, audit_fields, get_engine, get_table, new_id, now, serialize, serialize_list
from ..core.deps import AuthContext, require_permission

router = APIRouter(tags=["completeness"])
_view = require_permission("employee", "view")
_conf = require_permission("employee_completeness", "configure")
_edit = require_permission("employee", "edit")

SCOPE_COLLECTIONS = {"branch": "branches", "position": "positions", "project": "projects", "work_location": "work_locations",
                     "department": "departments", "division": "divisions", "job_grade": "job_grades",
                     "employment_status": "employment_statuses", "employee_status": "employee_business_statuses"}
BUSINESS_CATEGORIES = ("ACTIVE", "STANDBY", "INACTIVE")


class RuleUpdate(BaseModel):
    level: str
    notes: Optional[str] = Field(None, max_length=1000)

    @field_validator("level")
    @classmethod
    def _lv(cls, v: str) -> str:
        v = (v or "").strip().upper()
        if v not in M.LEVELS:
            raise ValueError("Level harus REQUIRED, RECOMMENDED, atau OFF.")
        return v


class ScopeCreate(BaseModel):
    requirement_code: str = Field(..., max_length=64)
    scope_type: str
    scope_id: Optional[str] = Field(None, max_length=64)
    mode: str = "INCLUDE"
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=1000)

    @field_validator("effective_from", "effective_to")
    @classmethod
    def _dt(cls, v: Optional[str]) -> Optional[str]:
        if v in (None, ""):
            return None
        try:
            return date.fromisoformat(v[:10]).isoformat()
        except ValueError as exc:
            raise ValueError("Format tanggal harus YYYY-MM-DD.") from exc


class ReevaluateIn(BaseModel):
    employee_ids: Optional[List[str]] = Field(None, max_length=10000)


async def _requirements(company_id: str) -> Dict[str, Any]:
    rules = await engine.load_rules(company_id)
    return {"rules": rules, "by_code": {r.code: r for r in rules["requirements"]}}


def _label_items(items: List[Dict[str, Any]], by_code: Dict[str, M.Requirement]) -> List[Dict[str, Any]]:
    out = []
    for it in items or []:
        req = by_code.get(it.get("code"))
        out.append({**it, "label": req.label if req else it.get("code"), "status_label": M.STATUS_LABELS.get(it.get("status"))})
    return out


def _public_snapshot(snap: Dict[str, Any], by_code: Dict[str, M.Requirement]) -> Dict[str, Any]:
    s = serialize(snap)
    s["items"] = _label_items(s.get("items"), by_code)
    s["missing"] = [{"code": c, "label": by_code[c].label if c in by_code else c} for c in s.get("missing_codes") or []]
    return s


# ------------------------------------------------------------------ view
@router.get("/completeness/catalog")
async def catalog(ctx: AuthContext = Depends(_view)):
    data = await _requirements(ctx.company_id)
    rules = data["rules"]
    reqs = []
    for r in rules["requirements"]:
        p = r.public()
        p["level"] = rules["levels"].get(r.code, r.default_level)
        p["is_overridden"] = r.code in rules["levels"]
        p["scopes"] = serialize_list(rules["scopes"].get(r.code, []))
        p["applicability_label"] = M.APPLICABILITY.get(r.applicability)
        reqs.append(p)
    return {**M.catalog_metadata(), "rules_hash": rules["rules_hash"], "requirements": reqs,
            "refresh_running": engine.tenant_refresh_running(ctx.company_id)}


@router.get("/employees/{employee_id}/completeness")
async def employee_completeness(employee_id: str, ctx: AuthContext = Depends(_view)):
    emp = await ctx.tdb.employees.find_one({"company_id": ctx.company_id, "id": employee_id, "status": {"$ne": "deleted"}},
                                           {"id": 1})
    if not emp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Karyawan tidak ditemukan.")
    data = await _requirements(ctx.company_id)
    snap = await ctx.tdb.employee_completeness.find_one({"company_id": ctx.company_id, "employee_id": employee_id}, NO_ID)
    evaluated = snap.get("evaluated_at") if snap else None
    ev_day = evaluated.date().isoformat() if hasattr(evaluated, "date") else str(evaluated or "")[:10]
    if (not snap or snap.get("is_stale") or snap.get("rules_hash") != data["rules"]["rules_hash"]
            or ev_day != date.today().isoformat()):
        await engine.refresh(ctx.company_id, [employee_id], "on_read", ctx.user_id)
        snap = await ctx.tdb.employee_completeness.find_one({"company_id": ctx.company_id, "employee_id": employee_id}, NO_ID)
    if not snap:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kelengkapan belum tersedia untuk karyawan ini.")
    out = _public_snapshot(snap, data["by_code"])
    out["categories"] = [{"key": k, "label": l, "tab": t} for k, l, t in M.CATEGORIES]
    return out


def _pending_expr(ec, rules_hash: str):
    return sa.or_(ec.c.is_stale.is_(True), ec.c.rules_hash.is_(None), ec.c.rules_hash != rules_hash)


def _base_join():
    ec, e = get_table(engine.SNAP), get_table("employees")
    j = ec.join(e, sa.and_(e.c.id == ec.c.employee_id, e.c.company_id == ec.c.company_id))
    return ec, e, j


@router.get("/completeness/summary")
async def summary(ctx: AuthContext = Depends(_view)):
    """Agregat di database (tanpa memuat seluruh snapshot ke memori aplikasi)."""
    data = await _requirements(ctx.company_id)
    h = data["rules"]["rules_hash"]
    ec, e, j = _base_join()
    alive = sa.and_(ec.c.company_id == ctx.company_id, e.c.status.notin_(list(engine.EXCLUDED_EMP_STATUS)))
    counts = {M.LENGKAP: 0, M.BELUM_LENGKAP: 0, M.EXCLUDED: 0}
    score_sum = score_n = pending = total = 0
    last = None
    stmt = (sa.select(ec.c.completeness_status, func.count(), func.sum(ec.c.score_pct), func.count(ec.c.score_pct),
                      func.sum(sa.case((_pending_expr(ec, h), 1), else_=0)), func.max(ec.c.evaluated_at))
            .select_from(j).where(alive).group_by(ec.c.completeness_status))
    async with get_engine().connect() as conn:
        for st, n, ssum, sn, pend, mx in (await conn.execute(stmt)).fetchall():
            counts[st] = counts.get(st, 0) + int(n)
            total += int(n)
            score_sum += float(ssum or 0)
            score_n += int(sn or 0)
            pending += int(pend or 0)
            last = mx if mx and (last is None or mx > last) else last
        miss_rows = (await conn.execute(text(
            "SELECT jt.code, COUNT(*) FROM employee_completeness ec "
            "JOIN employees e ON e.id = ec.employee_id AND e.company_id = ec.company_id AND e.status NOT IN ('deleted','archived') "
            "CROSS JOIN JSON_TABLE(ec.missing_codes, '$[*]' COLUMNS (code VARCHAR(64) PATH '$')) jt "
            "WHERE ec.company_id = :cid GROUP BY jt.code ORDER BY COUNT(*) DESC"), {"cid": ctx.company_id})).fetchall()
        active_emp = (await conn.execute(sa.select(func.count()).select_from(e).where(
            sa.and_(e.c.company_id == ctx.company_id, e.c.status.notin_(list(engine.EXCLUDED_EMP_STATUS)))))).scalar() or 0
    by_code = data["by_code"]
    per_cat: Dict[str, int] = {}
    for code, n in miss_rows:
        cat = by_code[code].category if code in by_code else "OTHER"
        per_cat[cat] = per_cat.get(cat, 0) + int(n)
    return {"total": total, "counts": counts, "average_score": round(score_sum / score_n, 1) if score_n else None,
            "stale": pending, "pending": pending, "not_evaluated": max(0, int(active_emp) - total),
            "refresh_running": engine.tenant_refresh_running(ctx.company_id), "last_evaluated_at": last,
            "top_missing": [{"code": c, "label": by_code[c].label if c in by_code else c, "count": int(n)} for c, n in miss_rows[:15]],
            "missing_by_category": [{"key": k, "label": l, "count": per_cat.get(k, 0)} for k, l, _t in M.CATEGORIES]}


def _like(term: str) -> str:
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


@router.get("/completeness/employees")
async def list_employees(completeness_status: Optional[str] = Query(None, max_length=32),
                         missing: Optional[str] = Query(None, max_length=64), q: Optional[str] = Query(None, max_length=64),
                         project_id: Optional[str] = Query(None, max_length=64), department_id: Optional[str] = Query(None, max_length=64),
                         division_id: Optional[str] = Query(None, max_length=64),
                         employee_status_id: Optional[str] = Query(None, max_length=64),
                         score_min: Optional[float] = Query(None, ge=0, le=100), score_max: Optional[float] = Query(None, ge=0, le=100),
                         pending: Optional[bool] = Query(None), page: int = Query(1, ge=1),
                         limit: int = Query(25, ge=1, le=200), ctx: AuthContext = Depends(_view)):
    """Filter + pagination di database. Kolom sensitif karyawan tidak pernah dipilih."""
    h = (await engine.load_rules(ctx.company_id))["rules_hash"]
    ec, e, j = _base_join()
    conds = [ec.c.company_id == ctx.company_id, e.c.status.notin_(list(engine.EXCLUDED_EMP_STATUS))]
    if completeness_status:
        conds.append(ec.c.completeness_status == completeness_status.strip().upper())
    if missing:
        conds.append(func.json_contains(ec.c.missing_codes, json.dumps(missing.strip().upper())) == 1)
    for col, val in (("project_id", project_id), ("department_id", department_id), ("division_id", division_id),
                     ("current_employee_status_id", employee_status_id)):
        if val:
            conds.append(e.c[col] == val)
    if score_min is not None:
        conds.append(ec.c.score_pct >= score_min)
    if score_max is not None:
        conds.append(ec.c.score_pct <= score_max)
    if pending is True:
        conds.append(_pending_expr(ec, h))
    term = (q or "").strip()
    if term:
        like = _like(term)
        conds.append(sa.or_(e.c.full_name.ilike(like, escape="\\"), e.c.employee_number.ilike(like, escape="\\")))
    where = sa.and_(*conds)
    cols = [ec.c.employee_id, e.c.full_name, e.c.employee_number, e.c.project_id, e.c.department_id, e.c.division_id,
            e.c.current_employee_status_id, ec.c.score_pct, ec.c.completeness_status, ec.c.required_total,
            ec.c.required_fulfilled, ec.c.missing_codes, ec.c.evaluated_at,
            sa.case((_pending_expr(ec, h), 1), else_=0).label("pending")]
    stmt = (sa.select(*cols).select_from(j).where(where)
            .order_by(ec.c.score_pct.is_(None), ec.c.score_pct.asc(), e.c.full_name.asc())
            .offset((page - 1) * limit).limit(limit))
    async with get_engine().connect() as conn:
        total = (await conn.execute(sa.select(func.count()).select_from(j).where(where))).scalar() or 0
        rows = (await conn.execute(stmt)).mappings().fetchall()
    names = await _names(ctx, rows)
    items = []
    for r in rows:
        mc = r["missing_codes"]
        mc = json.loads(mc) if isinstance(mc, str) else (mc or [])
        items.append({"employee_id": r["employee_id"], "full_name": r["full_name"], "employee_number": r["employee_number"],
                      "project": names["projects"].get(r["project_id"]), "department": names["departments"].get(r["department_id"]),
                      "division": names["divisions"].get(r["division_id"]),
                      "employee_status": names["employee_business_statuses"].get(r["current_employee_status_id"]),
                      "score_pct": r["score_pct"], "completeness_status": r["completeness_status"],
                      "required_total": r["required_total"], "required_fulfilled": r["required_fulfilled"],
                      "missing_count": len(mc), "is_stale": bool(r["pending"]), "pending": bool(r["pending"]),
                      "evaluated_at": r["evaluated_at"]})
    return {"items": serialize_list(items), "total": int(total), "page": page, "limit": limit}


async def _names(ctx: AuthContext, rows) -> Dict[str, Dict[str, str]]:
    want = {"projects": "project_id", "departments": "department_id", "divisions": "division_id",
            "employee_business_statuses": "current_employee_status_id"}
    out: Dict[str, Dict[str, str]] = {}
    for coll, key in want.items():
        ids = sorted({r[key] for r in rows if r[key]})
        out[coll] = {}
        if ids:
            for m in await ctx.tdb[coll].find({"company_id": ctx.company_id, "id": {"$in": ids}}, NO_ID).to_list(len(ids)):
                out[coll][m["id"]] = m.get("name") or m.get("code")
    return out


@router.post("/employees/{employee_id}/completeness/reevaluate")
async def reevaluate_employee(employee_id: str, ctx: AuthContext = Depends(_edit)):
    emp = await ctx.tdb.employees.find_one({"company_id": ctx.company_id, "id": employee_id, "status": {"$ne": "deleted"}},
                                           {"id": 1})
    if not emp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Karyawan tidak ditemukan.")
    res = await engine.refresh(ctx.company_id, [employee_id], "manual_employee", ctx.user_id)
    return {"evaluated": res["evaluated"], "message": "Kelengkapan data dievaluasi ulang."}


# ------------------------------------------------------------------ configure
async def _assert_code(company_id: str, code: str) -> M.Requirement:
    data = await _requirements(company_id)
    req = data["by_code"].get(code)
    if not req:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kode requirement tidak dikenal pada perusahaan aktif.")
    return req


_BUSY_MSG = "Perubahan belum tersimpan karena server sedang memproses data kelengkapan. Silakan coba lagi."


async def _config_tx(fn, what: str):
    """Mutasi utama + audit dalam satu transaksi (retry konflik kunci). Gagal setelah retry -> 503, TIDAK dianggap sukses."""
    try:
        return await engine.run_config_mutation(fn, what)
    except engine.ConfigBusyError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _BUSY_MSG)


async def _after_change(ctx: AuthContext, bg: BackgroundTasks, reason: str, trigger: str) -> None:
    """Side-effect SETELAH commit: stale (non-blocking, retry di engine) + evaluasi ulang tenant SELALU dijadwalkan."""
    await engine.after_config_change(ctx.company_id, reason)
    bg.add_task(engine.schedule_tenant_refresh, ctx.company_id, trigger, ctx.user_id)


@router.put("/completeness/rules/{code}")
async def set_rule(code: str, payload: RuleUpdate, bg: BackgroundTasks, ctx: AuthContext = Depends(_conf)):
    code = code.upper()
    req = await _assert_code(ctx.company_id, code)

    async def _mutate(tx):
        before = await tx.select_one_for_update("completeness_rules", {"company_id": ctx.company_id, "requirement_code": code})
        if before:
            await tx.update("completeness_rules", {"company_id": ctx.company_id, "id": before["id"]}, {
                "level": payload.level, "notes": payload.notes, "status": "active", "updated_at": now(), "updated_by": ctx.user_id})
        else:
            await tx.insert("completeness_rules", {"id": new_id(), "company_id": ctx.company_id, "status": "active",
                                                   "requirement_code": code, "level": payload.level, "notes": payload.notes,
                                                   **audit_fields(ctx.user_id, creating=True)})
        await tx.insert("audit_logs", build_audit_entry(
            ctx, "completeness_rule_update", "employee_completeness", code, req.label,
            before={"level": (before or {}).get("level") or req.default_level}, after={"level": payload.level},
            notes=f"Level kelengkapan {code} -> {payload.level}"))

    await _config_tx(_mutate, "ubah rule kelengkapan")
    await _after_change(ctx, bg, "rule berubah", "rule_change")
    return {"message": f"Level '{req.label}' disimpan: {M.LEVEL_LABELS[payload.level]}. Evaluasi ulang berjalan di latar belakang."}


@router.delete("/completeness/rules/{code}")
async def reset_rule(code: str, bg: BackgroundTasks, ctx: AuthContext = Depends(_conf)):
    code = code.upper()
    req = await _assert_code(ctx.company_id, code)

    async def _mutate(tx):
        n = await tx.delete("completeness_rules", {"company_id": ctx.company_id, "requirement_code": code})
        if n:
            await tx.insert("audit_logs", build_audit_entry(
                ctx, "completeness_rule_reset", "employee_completeness", code, req.label,
                after={"level": req.default_level}, notes=f"Level kelengkapan {code} kembali ke default"))
        return n

    if await _config_tx(_mutate, "reset rule kelengkapan"):
        await _after_change(ctx, bg, "rule berubah", "rule_change")
    return {"message": f"Level '{req.label}' kembali ke default ({M.LEVEL_LABELS[req.default_level]})."}


@router.post("/completeness/scopes", status_code=status.HTTP_201_CREATED)
async def add_scope(payload: ScopeCreate, bg: BackgroundTasks, ctx: AuthContext = Depends(_conf)):
    code = payload.requirement_code.strip().upper()
    req = await _assert_code(ctx.company_id, code)
    stype, mode = payload.scope_type.strip().lower(), payload.mode.strip().upper()
    if stype not in M.SCOPE_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Jenis scope tidak dikenal.")
    if mode not in M.SCOPE_MODES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Mode scope harus INCLUDE atau EXCLUDE.")
    if payload.effective_from and payload.effective_to and payload.effective_from > payload.effective_to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tanggal mulai harus sebelum tanggal akhir.")
    scope_id, label = None, M.SCOPE_TYPES["company"]
    if stype == "business_status_category":
        scope_id = (payload.scope_id or "").strip().upper()
        if scope_id not in BUSINESS_CATEGORIES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Kategori status harus ACTIVE, STANDBY, atau INACTIVE.")
        label = scope_id
    elif stype != "company":
        if not payload.scope_id or not re.fullmatch(r"[A-Za-z0-9\-]{1,64}", payload.scope_id):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pilih data scope yang valid.")
        ref = await ctx.tdb[SCOPE_COLLECTIONS[stype]].find_one(
            {"company_id": ctx.company_id, "id": payload.scope_id, "status": {"$ne": "deleted"}}, NO_ID)
        if not ref:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Data scope tidak ditemukan pada perusahaan aktif.")
        scope_id, label = payload.scope_id, f"{ref.get('code') or ''} {ref.get('name') or ''}".strip()
    dup_flt = {"company_id": ctx.company_id, "requirement_code": code, "scope_type": stype, "scope_id": scope_id, "mode": mode,
               "status": {"$ne": "deleted"}}
    doc = {"id": new_id(), "company_id": ctx.company_id, "status": "active", "requirement_code": code, "scope_type": stype,
           "scope_id": scope_id, "scope_label": label[:255], "mode": mode, "effective_from": payload.effective_from,
           "effective_to": payload.effective_to, "notes": payload.notes, **audit_fields(ctx.user_id, creating=True)}

    async def _mutate(tx):
        if await tx.select_one_for_update("completeness_rule_scopes", dup_flt):
            return False
        await tx.insert("completeness_rule_scopes", dict(doc))
        await tx.insert("audit_logs", build_audit_entry(
            ctx, "completeness_scope_create", "employee_completeness", doc["id"], req.label,
            after={"code": code, "scope_type": stype, "scope": label, "mode": mode},
            notes=f"Scope {mode} {M.SCOPE_TYPES[stype]} untuk {code}"))
        return True

    if not await _config_tx(_mutate, "tambah scope kelengkapan"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Scope yang sama sudah ada untuk requirement ini.")
    await _after_change(ctx, bg, "scope berubah", "scope_change")
    return {"scope": serialize(doc), "message": "Scope ditambahkan. Evaluasi ulang berjalan di latar belakang."}


@router.delete("/completeness/scopes/{scope_id}")
async def delete_scope(scope_id: str, bg: BackgroundTasks, ctx: AuthContext = Depends(_conf)):
    flt = {"company_id": ctx.company_id, "id": scope_id}

    async def _mutate(tx):
        row = await tx.select_one_for_update("completeness_rule_scopes", flt)
        if not row:
            return False
        await tx.delete("completeness_rule_scopes", flt)
        await tx.insert("audit_logs", build_audit_entry(
            ctx, "completeness_scope_delete", "employee_completeness", scope_id, row.get("requirement_code"),
            before={"code": row.get("requirement_code"), "scope_type": row.get("scope_type"),
                    "scope": row.get("scope_label"), "mode": row.get("mode")}, notes="Scope kelengkapan dihapus"))
        return True

    if not await _config_tx(_mutate, "hapus scope kelengkapan"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scope tidak ditemukan.")
    await _after_change(ctx, bg, "scope berubah", "scope_change")
    return {"message": "Scope dihapus. Evaluasi ulang berjalan di latar belakang."}


@router.post("/completeness/reevaluate")
async def reevaluate(payload: ReevaluateIn, ctx: AuthContext = Depends(_conf)):
    res = await engine.refresh(ctx.company_id, payload.employee_ids, "manual", ctx.user_id)
    await log_action(ctx, "completeness_reevaluate", "employee_completeness", None, None,
                     after={"evaluated": res["evaluated"]}, notes=f"Evaluasi ulang kelengkapan: {res['evaluated']} karyawan")
    return {"evaluated": res["evaluated"], "evaluated_at": res["evaluated_at"],
            "message": f"{res['evaluated']} karyawan dievaluasi ulang."}
