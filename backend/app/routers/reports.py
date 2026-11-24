"""Modul 7 Blueprint HRGA - Pusat Laporan & Export.

Satu tempat untuk lima laporan lintas modul: Karyawan, Kepatuhan Dokumen, Roster & Mobilisasi,
Aset, dan Exit Clearance. Semua laporan:
- tunduk pada Cakupan Data 01I (ALL_TENANT vs SELECTED_PROJECTS) di SQL, bukan difilter di UI;
- memakai filter organisasi (project/site/departemen/divisi/jabatan) sesuai konteks laporan;
- dapat diekspor ke Excel dengan kolom yang sama seperti yang tampil di layar;
- dicatat di audit log saat diekspor.

Endpoint:
    GET /api/reports                 -> katalog laporan + opsi filter
    GET /api/reports/{kind}          -> data laporan (JSON)
    GET /api/reports/{kind}/export   -> unduhan Excel
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..core import data_scope as dscope
from ..core.asset_service import LIFECYCLE_STATES
from ..core.audit import log_action
from ..core.db import NO_ID, get_db, serialize_list
from ..core.deps import AuthContext, require_permission
from ..core.employee_status import today_local
from ..core.time_excel import export_sheet
from .exit_clearance import CASE_LABELS, EXIT_TYPES
from .roster_mobilization import (APPROVAL_LABELS, APPROVAL_STATES, STATE_LABELS, _approval_state,
                                 _travel_state)
from .roster import PLAN_STATUSES

router = APIRouter(prefix="/reports", tags=["Laporan"])

_view = require_permission("report", "view")
_export = require_permission("report", "export")

VERIFICATION_LABELS = {"PENDING": "Menunggu Verifikasi", "VERIFIED": "Terverifikasi", "REJECTED": "Ditolak"}
VERIFICATION_STATES = ("PENDING", "VERIFIED", "REJECTED")
PLAN_LABELS = {"PLANNED": "Direncanakan", "CONFIRMED": "Terkonfirmasi", "POSTPONED": "Ditunda"}
EMPLOYEE_STATUS_LABELS = {"active": "Aktif", "inactive": "Tidak Aktif"}

MAX_ROWS = 20000


def _err(code: int, msg: str) -> HTTPException:
    return HTTPException(code, msg)


def _today() -> date:
    return date.fromisoformat(today_local())


def _parse_date(value: Optional[str], label: str) -> Optional[date]:
    text = str(value or "").strip()[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{label} harus berformat YYYY-MM-DD.") from exc


def _text(value: Any) -> str:
    return str(value or "").strip()


async def _name_map(ctx: AuthContext, collection: str, ids: List[Optional[str]]) -> Dict[str, str]:
    clean = [i for i in dict.fromkeys(ids) if i]
    if not clean:
        return {}
    rows = serialize_list(await get_db()[collection].find(
        {"company_id": ctx.company_id, "id": {"$in": clean}}, {"id": 1, "name": 1, "code": 1}).to_list(len(clean) + 1))
    out = {}
    for row in rows:
        label = row.get("name") or row.get("code") or row["id"]
        out[row["id"]] = label
    return out


async def _scoped_employees(ctx: AuthContext, project_id: Optional[str], q: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """Karyawan dalam cakupan data (id, nomor, nama, project) untuk join laporan."""
    scope = await dscope.get_scope(ctx)
    flt: Dict[str, Any] = {"company_id": ctx.company_id, "status": {"$ne": "deleted"}}
    if project_id:
        flt["project_id"] = project_id
    needle = _text(q)
    if needle:
        flt["$or"] = [{"full_name": {"$regex": needle, "$options": "i"}},
                      {"employee_number": {"$regex": needle, "$options": "i"}},
                      {"nik": {"$regex": needle, "$options": "i"}}]
    rows = serialize_list(await get_db().employees.find(dscope.with_scope(flt, scope), NO_ID).to_list(MAX_ROWS))
    return {r["id"]: r for r in rows}


def _project_scope(flt: Dict[str, Any], scope: dscope.DataScope) -> Dict[str, Any]:
    return dscope.with_project_scope(flt, scope)


def _scope_label(scope: dscope.DataScope) -> str:
    return "Seluruh project" if scope.is_all else f"{len(scope.project_ids)} project sesuai cakupan data"


# --------------------------------------------------------------------------- 1. Karyawan
EMPLOYEE_COLUMNS = [
    {"key": "employee_number", "label": "NIK / No. Karyawan"},
    {"key": "full_name", "label": "Nama Karyawan"},
    {"key": "project_name", "label": "Project"},
    {"key": "work_location_name", "label": "Site / Lokasi Kerja"},
    {"key": "department_name", "label": "Departemen"},
    {"key": "division_name", "label": "Divisi"},
    {"key": "position_name", "label": "Jabatan"},
    {"key": "employment_status_name", "label": "Status Kepegawaian"},
    {"key": "join_date", "label": "Tanggal Masuk"},
    {"key": "status_label", "label": "Status Data"},
    {"key": "email", "label": "Email"},
    {"key": "phone", "label": "Telepon"},
]


async def _report_employees(ctx: AuthContext, f: Dict[str, Any]) -> Dict[str, Any]:
    db = get_db()
    scope = await dscope.get_scope(ctx)
    flt: Dict[str, Any] = {"company_id": ctx.company_id, "status": {"$ne": "deleted"}}
    for key in ("project_id", "work_location_id", "department_id", "division_id", "position_id"):
        if f.get(key):
            flt[key] = f[key]
    if f.get("status"):
        flt["status"] = f["status"]
    needle = _text(f.get("q"))
    if needle:
        flt["$or"] = [{"full_name": {"$regex": needle, "$options": "i"}},
                      {"employee_number": {"$regex": needle, "$options": "i"}},
                      {"nik": {"$regex": needle, "$options": "i"}}]
    flt = dscope.with_scope(flt, scope)
    rows = serialize_list(await db.employees.find(flt, NO_ID).sort("full_name", 1).to_list(MAX_ROWS))
    maps = {
        "project": await _name_map(ctx, "projects", [r.get("project_id") for r in rows]),
        "location": await _name_map(ctx, "work_locations", [r.get("work_location_id") for r in rows]),
        "department": await _name_map(ctx, "departments", [r.get("department_id") for r in rows]),
        "division": await _name_map(ctx, "divisions", [r.get("division_id") for r in rows]),
        "position": await _name_map(ctx, "positions", [r.get("position_id") for r in rows]),
        "employment": await _name_map(ctx, "employment_statuses", [r.get("employment_status_id") for r in rows]),
    }
    items = [{
        "employee_number": r.get("employee_number"),
        "full_name": r.get("full_name"),
        "project_name": maps["project"].get(r.get("project_id")),
        "work_location_name": maps["location"].get(r.get("work_location_id")),
        "department_name": maps["department"].get(r.get("department_id")),
        "division_name": maps["division"].get(r.get("division_id")),
        "position_name": maps["position"].get(r.get("position_id")),
        "employment_status_name": maps["employment"].get(r.get("employment_status_id")),
        "join_date": r.get("join_date"),
        "status_label": EMPLOYEE_STATUS_LABELS.get(r.get("status"), r.get("status")),
        "email": r.get("email"),
        "phone": r.get("phone"),
    } for r in rows]
    active = sum(1 for r in rows if r.get("status") == "active")
    return {"items": items, "total": len(items),
            "summary": {"total": len(items), "active": active, "inactive": len(items) - active}}


# --------------------------------------------------------------------------- 2. Kepatuhan dokumen
COMPLIANCE_COLUMNS = [
    {"key": "employee_number", "label": "NIK / No. Karyawan"},
    {"key": "employee_name", "label": "Nama Karyawan"},
    {"key": "project_name", "label": "Project"},
    {"key": "document_type_name", "label": "Tipe Dokumen"},
    {"key": "document_name", "label": "Nama Dokumen"},
    {"key": "document_number", "label": "Nomor Dokumen"},
    {"key": "expiry_date", "label": "Berlaku Sampai"},
    {"key": "days_left", "label": "Sisa Hari"},
    {"key": "expiry_label", "label": "Status Masa Berlaku"},
    {"key": "verification_label", "label": "Status Verifikasi"},
    {"key": "verified_by_name", "label": "Diverifikasi Oleh"},
]


async def _report_compliance(ctx: AuthContext, f: Dict[str, Any]) -> Dict[str, Any]:
    db = get_db()
    today = _today()
    raw_horizon = f.get("horizon_days")
    try:
        horizon = 90 if raw_horizon in (None, "") else int(raw_horizon)
    except (TypeError, ValueError) as exc:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Horizon hari harus berupa angka.") from exc
    if horizon < 1 or horizon > 730:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Horizon hari harus antara 1 dan 730.")
    limit = (today + timedelta(days=horizon)).isoformat()
    employees = await _scoped_employees(ctx, f.get("project_id"), f.get("q"))
    if not employees:
        return {"items": [], "total": 0, "summary": {"total": 0, "expired": 0, "due_soon": 0}}
    docs = serialize_list(await db.documents.find({
        "company_id": ctx.company_id, "owner_type": "employee", "is_deleted": False,
        "owner_id": {"$in": list(employees)}, "expiry_date": {"$ne": None, "$lte": limit},
    }, NO_ID).sort("expiry_date", 1).to_list(MAX_ROWS))
    wanted_verification = _text(f.get("verification_state")).upper()
    if wanted_verification:
        if wanted_verification not in VERIFICATION_STATES:
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                       "Status verifikasi tidak dikenal. Pilihan: Menunggu Verifikasi, Terverifikasi, Ditolak.")
        docs = [d for d in docs
                if str(d.get("verification_state") or "VERIFIED") == wanted_verification]
    type_names = await _name_map(ctx, "document_types", [d.get("document_type_id") for d in docs])
    project_names = await _name_map(ctx, "projects", [e.get("project_id") for e in employees.values()])
    items = []
    for doc in docs:
        expiry = _parse_date(doc.get("expiry_date"), "Masa berlaku")
        if not expiry:
            continue
        days_left = (expiry - today).days
        emp = employees.get(doc.get("owner_id")) or {}
        state = "expired" if days_left < 0 else "due_soon"
        items.append({
            "employee_number": emp.get("employee_number"),
            "employee_name": emp.get("full_name"),
            "project_name": project_names.get(emp.get("project_id")),
            "document_type_name": type_names.get(doc.get("document_type_id")),
            "document_name": doc.get("name"),
            "document_number": doc.get("document_number"),
            "expiry_date": expiry.isoformat(),
            "days_left": days_left,
            "expiry_label": "Kedaluwarsa" if state == "expired" else "Akan berakhir",
            "verification_label": VERIFICATION_LABELS.get(
                str(doc.get("verification_state") or "VERIFIED"), doc.get("verification_state")),
            "verified_by_name": doc.get("verified_by_name"),
            "_state": state,
        })
    summary = {
        "total": len(items),
        "expired": sum(1 for i in items if i["_state"] == "expired"),
        "due_soon": sum(1 for i in items if i["_state"] == "due_soon"),
        "horizon_days": horizon,
    }
    for item in items:
        item.pop("_state", None)
    return {"items": items, "total": len(items), "summary": summary}


# --------------------------------------------------------------------------- 3. Roster & mobilisasi
ROSTER_COLUMNS = [
    {"key": "employee_number", "label": "NIK / No. Karyawan"},
    {"key": "employee_name", "label": "Nama Karyawan"},
    {"key": "project_name", "label": "Project"},
    {"key": "off_start", "label": "Mulai Cuti Project"},
    {"key": "off_end", "label": "Selesai Cuti Project"},
    {"key": "plan_status_label", "label": "Status Rencana"},
    {"key": "depart_date", "label": "Tanggal Berangkat"},
    {"key": "return_date", "label": "Tanggal Kembali"},
    {"key": "travel_label", "label": "Status Perjalanan"},
    {"key": "approval_label", "label": "Persetujuan HR"},
    {"key": "approved_by_name", "label": "Disetujui Oleh"},
]


async def _report_roster(ctx: AuthContext, f: Dict[str, Any]) -> Dict[str, Any]:
    db = get_db()
    scope = await dscope.get_scope(ctx)
    flt: Dict[str, Any] = {"company_id": ctx.company_id, "status": {"$ne": "deleted"}}
    if f.get("project_id"):
        flt["project_id"] = f["project_id"]
    else:
        flt = _project_scope(flt, scope)
    if f.get("plan_status"):
        state = _text(f["plan_status"]).upper()
        if state not in PLAN_STATUSES:
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Status rencana cuti tidak dikenal.")
        flt["plan_status"] = state
    date_from = _parse_date(f.get("date_from"), "Tanggal mulai")
    date_to = _parse_date(f.get("date_to"), "Tanggal selesai")
    if date_from:
        flt["off_end"] = {"$gte": date_from.isoformat()}
    if date_to:
        flt["off_start"] = {"$lte": date_to.isoformat()}
    plans = serialize_list(await db.roster_leave_plans.find(flt, NO_ID).to_list(MAX_ROWS))
    if not plans:
        return {"items": [], "total": 0, "summary": {"total": 0, "confirmed": 0, "pending_approval": 0}}

    plan_ids = [p["id"] for p in plans]
    mobs = {m["plan_id"]: m for m in serialize_list(await db.roster_mobilizations.find(
        {"company_id": ctx.company_id, "plan_id": {"$in": plan_ids}}, NO_ID).to_list(MAX_ROWS))}
    wanted_approval = _text(f.get("approval_state")).upper()
    if wanted_approval:
        if wanted_approval not in APPROVAL_STATES:
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                       "Status persetujuan tidak dikenal. Pilihan: Menunggu Persetujuan HR, Disetujui HR, Ditolak HR.")
        plans = [p for p in plans if mobs.get(p["id"]) and _approval_state(mobs[p["id"]]) == wanted_approval]

    employees = await _scoped_employees(ctx, None, f.get("q"))
    project_names = await _name_map(ctx, "projects", [p.get("project_id") for p in plans])
    today = _today()
    items = []
    for plan in plans:
        emp = employees.get(plan.get("employee_id"))
        if emp is None:
            continue
        mob = mobs.get(plan["id"])
        travel = _travel_state(mob, today)
        items.append({
            "employee_number": emp.get("employee_number"),
            "employee_name": emp.get("full_name"),
            "project_name": project_names.get(plan.get("project_id")),
            "off_start": plan.get("off_start"),
            "off_end": plan.get("off_end"),
            "plan_status_label": PLAN_LABELS.get(plan.get("plan_status"), plan.get("plan_status")),
            "depart_date": (mob or {}).get("depart_date"),
            "return_date": (mob or {}).get("return_date"),
            "travel_label": STATE_LABELS.get(travel, travel),
            "approval_label": APPROVAL_LABELS.get(_approval_state(mob), "-") if mob else "-",
            "approved_by_name": (mob or {}).get("approved_by_name"),
            "_approval": _approval_state(mob) if mob else "",
        })
    summary = {
        "total": len(items),
        "confirmed": sum(1 for i in items if i["plan_status_label"] == PLAN_LABELS["CONFIRMED"]),
        "pending_approval": sum(1 for i in items if i["_approval"] == "PENDING_APPROVAL"),
    }
    for item in items:
        item.pop("_approval", None)
    return {"items": items, "total": len(items), "summary": summary}


# --------------------------------------------------------------------------- 4. Aset
ASSET_COLUMNS = [
    {"key": "asset_code", "label": "Kode Aset"},
    {"key": "name", "label": "Nama Aset"},
    {"key": "category_name", "label": "Kategori"},
    {"key": "project_name", "label": "Project"},
    {"key": "work_location_name", "label": "Lokasi Kerja"},
    {"key": "condition_name", "label": "Kondisi"},
    {"key": "lifecycle_label", "label": "Status Aset"},
    {"key": "holder_name", "label": "Pemegang Saat Ini"},
    {"key": "acquisition_date", "label": "Tanggal Perolehan"},
    {"key": "acquisition_value", "label": "Nilai Perolehan"},
]


async def _report_assets(ctx: AuthContext, f: Dict[str, Any]) -> Dict[str, Any]:
    if not ctx.has_module("asset"):
        return {"items": [], "total": 0, "summary": {"total": 0, "unassigned": 0},
                "note": "Modul Manajemen Aset belum diaktifkan untuk perusahaan ini."}
    db = get_db()
    scope = await dscope.get_scope(ctx)
    flt: Dict[str, Any] = {"company_id": ctx.company_id, "status": {"$ne": "deleted"}}
    if f.get("project_id"):
        flt["project_id"] = f["project_id"]
    else:
        flt = _project_scope(flt, scope)
    if f.get("category_id"):
        flt["category_id"] = f["category_id"]
    if f.get("lifecycle_state"):
        state = _text(f["lifecycle_state"]).upper()
        if state not in LIFECYCLE_STATES:
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Status aset tidak dikenal.")
        flt["lifecycle_state"] = state
    needle = _text(f.get("q"))
    if needle:
        flt["$or"] = [{"name": {"$regex": needle, "$options": "i"}},
                      {"asset_code": {"$regex": needle, "$options": "i"}},
                      {"serial_number": {"$regex": needle, "$options": "i"}}]
    rows = serialize_list(await db.assets.find(flt, NO_ID).sort("asset_code", 1).to_list(MAX_ROWS))
    if not rows:
        return {"items": [], "total": 0, "summary": {"total": 0, "unassigned": 0}}

    asset_ids = [r["id"] for r in rows]
    holdings = serialize_list(await db.asset_holdings.find(
        {"company_id": ctx.company_id, "holding_status": "ACTIVE", "asset_id": {"$in": asset_ids}},
        NO_ID).to_list(MAX_ROWS))
    holder_by_asset = {h["asset_id"]: h.get("employee_id") for h in holdings}
    maps = {
        "category": await _name_map(ctx, "asset_categories", [r.get("category_id") for r in rows]),
        "project": await _name_map(ctx, "projects", [r.get("project_id") for r in rows]),
        "location": await _name_map(ctx, "work_locations", [r.get("work_location_id") for r in rows]),
        "condition": await _name_map(ctx, "asset_conditions", [r.get("condition_id") for r in rows]),
        "employee": await _name_map(ctx, "employees", list(holder_by_asset.values())),
    }
    can_view_value = ctx.has_permission("asset_value", "view")
    items = []
    for r in rows:
        item = {
            "asset_code": r.get("asset_code"),
            "name": r.get("name"),
            "category_name": maps["category"].get(r.get("category_id")),
            "project_name": maps["project"].get(r.get("project_id")),
            "work_location_name": maps["location"].get(r.get("work_location_id")),
            "condition_name": maps["condition"].get(r.get("condition_id")),
            "lifecycle_label": LIFECYCLE_STATES.get(r.get("lifecycle_state"), r.get("lifecycle_state")),
            "holder_name": maps["employee"].get(holder_by_asset.get(r.get("id"))),
            "acquisition_date": r.get("acquisition_date"),
            "acquisition_value": r.get("acquisition_value") if can_view_value else None,
        }
        items.append(item)
    return {"items": items, "total": len(items),
            "summary": {"total": len(items), "unassigned": sum(1 for i in items if not i["holder_name"]),
                        "value_visible": can_view_value}}


# --------------------------------------------------------------------------- 5. Exit clearance
EXIT_COLUMNS = [
    {"key": "case_number", "label": "No. Kasus"},
    {"key": "employee_number", "label": "NIK / No. Karyawan"},
    {"key": "employee_name", "label": "Nama Karyawan"},
    {"key": "project_name", "label": "Project"},
    {"key": "exit_type_label", "label": "Tipe Keluar"},
    {"key": "request_date", "label": "Tanggal Pengajuan"},
    {"key": "last_working_date", "label": "Tanggal Kerja Terakhir"},
    {"key": "case_state_label", "label": "Status Kasus"},
    {"key": "checklist_progress", "label": "Checklist Selesai"},
    {"key": "outstanding_assets", "label": "Aset Belum Kembali"},
]


async def _report_exit(ctx: AuthContext, f: Dict[str, Any]) -> Dict[str, Any]:
    db = get_db()
    scope = await dscope.get_scope(ctx)
    flt: Dict[str, Any] = {"company_id": ctx.company_id, "status": {"$ne": "deleted"}}
    if f.get("project_id"):
        flt["project_id"] = f["project_id"]
    if f.get("case_state"):
        state = _text(f["case_state"]).upper()
        if state not in CASE_LABELS:
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Status kasus exit tidak dikenal.")
        flt["case_state"] = state
    date_from = _parse_date(f.get("date_from"), "Tanggal mulai")
    date_to = _parse_date(f.get("date_to"), "Tanggal selesai")
    if date_from:
        flt["last_working_date"] = {"$gte": date_from.isoformat()}
    if date_to:
        flt["last_working_date"] = {**(flt.get("last_working_date") or {}), "$lte": date_to.isoformat()}
    flt = dscope.with_scope(flt, scope, "employee_id")
    cases = serialize_list(await db.exit_clearances.find(flt, NO_ID)
                           .sort([("last_working_date", -1)]).to_list(MAX_ROWS))
    if not cases:
        return {"items": [], "total": 0, "summary": {"total": 0, "open": 0, "completed": 0}}

    case_ids = [c["id"] for c in cases]
    items_rows = serialize_list(await db.exit_clearance_items.find(
        {"company_id": ctx.company_id, "clearance_id": {"$in": case_ids}},
        {"clearance_id": 1, "item_state": 1}).to_list(MAX_ROWS))
    progress: Dict[str, Dict[str, int]] = {cid: {"done": 0, "total": 0} for cid in case_ids}
    for item in items_rows:
        bucket = progress.get(item.get("clearance_id"))
        if not bucket:
            continue
        bucket["total"] += 1
        if item.get("item_state") in ("DONE", "NA"):
            bucket["done"] += 1

    employee_ids = [c.get("employee_id") for c in cases]
    holdings = serialize_list(await db.asset_holdings.find(
        {"company_id": ctx.company_id, "employee_id": {"$in": employee_ids}, "holding_status": "ACTIVE"},
        {"employee_id": 1}).to_list(MAX_ROWS))
    outstanding: Dict[str, int] = {}
    for h in holdings:
        outstanding[h["employee_id"]] = outstanding.get(h["employee_id"], 0) + 1

    project_names = await _name_map(ctx, "projects", [c.get("project_id") for c in cases])
    items = []
    for c in cases:
        item = progress.get(c["id"]) or {"done": 0, "total": 0}
        items.append({
            "case_number": c.get("case_number"),
            "employee_number": c.get("employee_number"),
            "employee_name": c.get("employee_name"),
            "project_name": project_names.get(c.get("project_id")),
            "exit_type_label": EXIT_TYPES.get(c.get("exit_type"), c.get("exit_type")),
            "request_date": c.get("request_date"),
            "last_working_date": c.get("last_working_date"),
            "case_state_label": CASE_LABELS.get(c.get("case_state"), c.get("case_state")),
            "checklist_progress": f"{item['done']}/{item['total']}",
            "outstanding_assets": outstanding.get(c.get("employee_id"), 0),
            "_state": c.get("case_state"),
        })
    summary = {
        "total": len(items),
        "open": sum(1 for i in items if i["_state"] in ("DRAFT", "PENDING_APPROVAL")),
        "completed": sum(1 for i in items if i["_state"] == "COMPLETED"),
        "outstanding_assets": sum(int(i["outstanding_assets"]) for i in items),
    }
    for item in items:
        item.pop("_state", None)
    return {"items": items, "total": len(items), "summary": summary}


# --------------------------------------------------------------------------- registry
REPORTS: Dict[str, Dict[str, Any]] = {
    "karyawan": {
        "title": "Laporan Karyawan",
        "description": "Data induk karyawan dengan penempatan, site, dan status kepegawaian.",
        "builder": _report_employees,
        "columns": EMPLOYEE_COLUMNS,
    },
    "kepatuhan": {
        "title": "Laporan Kepatuhan Dokumen",
        "description": "Dokumen karyawan yang kedaluwarsa atau akan berakhir beserta status verifikasi.",
        "builder": _report_compliance,
        "columns": COMPLIANCE_COLUMNS,
    },
    "roster": {
        "title": "Laporan Roster & Mobilisasi",
        "description": "Rencana cuti project, jadwal perjalanan, dan status persetujuan HR.",
        "builder": _report_roster,
        "columns": ROSTER_COLUMNS,
    },
    "aset": {
        "title": "Laporan Aset",
        "description": "Register aset per project beserta kondisi, status, dan pemegang saat ini.",
        "builder": _report_assets,
        "columns": ASSET_COLUMNS,
    },
    "exit": {
        "title": "Laporan Exit Clearance",
        "description": "Kasus keluar karyawan, progres checklist, dan aset yang belum kembali.",
        "builder": _report_exit,
        "columns": EXIT_COLUMNS,
    },
}


def _report_or_404(kind: str) -> Dict[str, Any]:
    entry = REPORTS.get((kind or "").strip().lower())
    if not entry:
        raise _err(status.HTTP_404_NOT_FOUND,
                   "Jenis laporan tidak ditemukan. Pilihan: Karyawan, Kepatuhan Dokumen, Roster, Aset, Exit Clearance.")
    return entry


async def _filters(
    project_id: Optional[str] = None,
    work_location_id: Optional[str] = None,
    department_id: Optional[str] = None,
    division_id: Optional[str] = None,
    position_id: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
    horizon_days: Optional[int] = None,
    verification_state: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    plan_status: Optional[str] = None,
    approval_state: Optional[str] = None,
    category_id: Optional[str] = None,
    lifecycle_state: Optional[str] = None,
    case_state: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "project_id": project_id, "work_location_id": work_location_id, "department_id": department_id,
        "division_id": division_id, "position_id": position_id, "status": status, "q": q,
        "horizon_days": horizon_days, "verification_state": verification_state,
        "date_from": date_from, "date_to": date_to, "plan_status": plan_status,
        "approval_state": approval_state, "category_id": category_id,
        "lifecycle_state": lifecycle_state, "case_state": case_state,
    }


async def _filter_options(ctx: AuthContext) -> Dict[str, Any]:
    db = get_db()
    scope = await dscope.get_scope(ctx)
    allowed = None if scope.is_all else list(scope.project_ids)

    async def _options(collection: str, extra: Optional[Dict[str, Any]] = None,
                       scoped_projects: bool = False) -> List[Dict[str, str]]:
        flt: Dict[str, Any] = {"company_id": ctx.company_id, "status": {"$ne": "deleted"}}
        if extra:
            flt.update(extra)
        if scoped_projects and allowed is not None:
            flt["id"] = {"$in": allowed}
        rows = serialize_list(await db[collection].find(
            flt, {"id": 1, "name": 1, "code": 1}).sort("name", 1).to_list(500))
        return [{"value": r["id"], "label": (f"{r.get('code')} · {r.get('name')}"
                                             if r.get("code") else (r.get("name") or r["id"]))} for r in rows]

    return {
        "projects": await _options("projects", {"status": "active"}, scoped_projects=True),
        "work_locations": await _options("work_locations", {"status": "active"}),
        "departments": await _options("departments", {"status": "active"}),
        "divisions": await _options("divisions", {"status": "active"}),
        "positions": await _options("positions", {"status": "active"}),
        "asset_categories": await _options("asset_categories") if ctx.has_module("asset") else [],
        "lifecycle_states": [{"value": k, "label": v} for k, v in LIFECYCLE_STATES.items()],
        "plan_statuses": [{"value": k, "label": v} for k, v in PLAN_LABELS.items()],
        "approval_states": [{"value": k, "label": v} for k, v in APPROVAL_LABELS.items()],
        "verification_states": [{"value": k, "label": v} for k, v in VERIFICATION_LABELS.items()],
        "travel_states": [{"value": k, "label": v} for k, v in STATE_LABELS.items()],
        "exit_types": [{"value": k, "label": v} for k, v in EXIT_TYPES.items()],
        "case_states": [{"value": k, "label": v} for k, v in CASE_LABELS.items()],
    }


@router.get("")
async def report_catalog(ctx: AuthContext = Depends(_view)):
    """Katalog laporan yang tersedia + opsi filter (project mengikuti cakupan data)."""
    return {
        "items": [{"key": key, "title": entry["title"], "description": entry["description"],
                   "columns": entry["columns"]} for key, entry in REPORTS.items()],
        "options": await _filter_options(ctx),
        "can_export": ctx.has_permission("report", "export"),
    }


@router.get("/{kind}")
async def run_report(kind: str, filters: Dict[str, Any] = Depends(_filters),
                     ctx: AuthContext = Depends(_view)):
    entry = _report_or_404(kind)
    data = await entry["builder"](ctx, filters)
    scope = await dscope.get_scope(ctx)
    data.update({
        "report": kind,
        "title": entry["title"],
        "description": entry["description"],
        "columns": entry["columns"],
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "scope_label": _scope_label(scope),
    })
    return data


@router.get("/{kind}/export")
async def export_report(kind: str, filters: Dict[str, Any] = Depends(_filters),
                        ctx: AuthContext = Depends(_export)):
    entry = _report_or_404(kind)
    data = await entry["builder"](ctx, filters)
    scope = await dscope.get_scope(ctx)
    scope_label = _scope_label(scope)
    generated = datetime.now().astimezone()
    meta = [
        ("Perusahaan", ctx.company.get("name") or "-"),
        ("Laporan", entry["title"]),
        ("Cakupan Data", scope_label),
        ("Dibuat", generated.strftime("%d-%m-%Y %H:%M")),
        ("Dibuat Oleh", (ctx.user or {}).get("full_name") or "-"),
        ("Jumlah Baris", str(data["total"])),
    ]
    for key, value in (data.get("summary") or {}).items():
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            meta.append((key.replace("_", " ").title(), str(value)))
    blob = export_sheet(entry["title"], entry["columns"], data["items"], meta=meta)
    await log_action(ctx, "export", "report", None, entry["title"], module="hr_core",
                     notes=f"Ekspor {entry['title']} ({data['total']} baris), cakupan: {scope_label}")
    filename = f"{entry['title'].replace(' ', '-')}-{generated.strftime('%Y%m%d')}.xlsx"
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
