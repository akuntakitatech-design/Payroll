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

import io
import re
import zipfile
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from openpyxl import Workbook

from ..core import data_scope as dscope
from ..core.asset_service import LIFECYCLE_STATES
from ..core.audit import log_action
from ..core.db import NO_ID, get_db, serialize_list
from ..core.deps import AuthContext, require_permission
from ..core.employee_status import today_local
from ..core.storage import get_object
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

# Batas bundel ZIP per karyawan (Modul 7). Dibuat konservatif agar satu permintaan
# tidak menghabiskan memori server ketika filter terlalu luas.
MAX_BUNDLE_EMPLOYEES = 200
MAX_BUNDLE_BYTES = 150 * 1024 * 1024

_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


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


def _safe_name(text: Any, fallback: str = "berkas") -> str:
    out = _UNSAFE_NAME.sub("-", str(text or "")).strip("-.")
    return out[:60] or fallback


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
    if not ctx.has_module("employee_core"):
        return {"items": [], "total": 0, "summary": {"total": 0, "active": 0, "inactive": 0},
                "note": "Modul Data Karyawan belum diaktifkan untuk perusahaan ini."}
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
    if not ctx.has_module("employee_core"):
        return {"items": [], "total": 0, "summary": {"total": 0, "expired": 0, "due_soon": 0},
                "note": "Modul Data Karyawan belum diaktifkan untuk perusahaan ini."}
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
    {"key": "replacement_name", "label": "Karyawan Pengganti"},
]


async def _report_roster(ctx: AuthContext, f: Dict[str, Any]) -> Dict[str, Any]:
    if not ctx.has_module("mobilization"):
        return {"items": [], "total": 0, "summary": {"total": 0, "confirmed": 0, "pending_approval": 0},
                "note": "Modul Roster & Mobilisasi belum diaktifkan untuk perusahaan ini."}
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
    replacement_names = await _name_map(
        ctx, "employees", [p.get("replacement_employee_id") for p in plans])
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
            "replacement_name": replacement_names.get(plan.get("replacement_employee_id")),
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
    if not ctx.has_module("employee_core"):
        return {"items": [], "total": 0,
                "summary": {"total": 0, "open": 0, "completed": 0, "outstanding_assets": 0},
                "note": "Modul Data Karyawan belum diaktifkan untuk perusahaan ini."}
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


# --------------------------------------------------------------------------- bundle ZIP
GENDER_LABELS = {"male": "Laki-laki", "female": "Perempuan"}
MARITAL_LABELS = {"single": "Belum Menikah", "married": "Menikah", "divorced": "Cerai",
                  "widowed": "Janda/Duda"}


def _biodata_xlsx(employee: Dict[str, Any], names: Dict[str, str], docs: List[Dict[str, Any]]) -> bytes:
    """Berkas biodata per karyawan: sheet Biodata (key/value) + sheet Dokumen."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Biodata"
    ws.append(["Field", "Nilai"])
    rows = [
        ("NIK / No. Karyawan", employee.get("employee_number")),
        ("Nama Lengkap", employee.get("full_name")),
        ("NIK KTP", employee.get("nik")),
        ("NPWP", employee.get("npwp")),
        ("Jenis Kelamin", GENDER_LABELS.get(employee.get("gender"), employee.get("gender"))),
        ("Tempat Lahir", employee.get("birth_place")),
        ("Tanggal Lahir", employee.get("birth_date")),
        ("Agama", employee.get("religion")),
        ("Status Perkawinan", MARITAL_LABELS.get(employee.get("marital_status"), employee.get("marital_status"))),
        ("Pendidikan", employee.get("education")),
        ("Email", employee.get("email")),
        ("Telepon", employee.get("phone")),
        ("Alamat", employee.get("address")),
        ("Kota", employee.get("city")),
        ("Tanggal Masuk", employee.get("join_date")),
        ("Project", names.get("project")),
        ("Site / Lokasi Kerja", names.get("location")),
        ("Departemen", names.get("department")),
        ("Divisi", names.get("division")),
        ("Jabatan", names.get("position")),
        ("Status Kepegawaian", names.get("employment")),
        ("Status Data", EMPLOYEE_STATUS_LABELS.get(employee.get("status"), employee.get("status"))),
    ]
    for label, value in rows:
        ws.append([label, value if value is not None else ""])
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 46

    sheet = wb.create_sheet("Dokumen")
    sheet.append(["Tipe Dokumen", "Nama Dokumen", "Nomor", "Tanggal Terbit", "Berlaku Sampai",
                  "Status Verifikasi", "Nama Berkas"])
    for doc in docs:
        sheet.append([
            doc.get("document_type_name") or "", doc.get("name") or "", doc.get("document_number") or "",
            doc.get("issued_date") or "", doc.get("expiry_date") or "",
            VERIFICATION_LABELS.get(str(doc.get("verification_state") or "VERIFIED"), ""),
            doc.get("file_name") or "",
        ])
    for letter, width in zip("ABCDEFG", (22, 32, 20, 16, 16, 22, 34)):
        sheet.column_dimensions[letter].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@router.get("/karyawan/bundle")
async def export_employee_bundle(
    project_id: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    q: Optional[str] = None,
    employee_id: Optional[str] = None,
    ctx: AuthContext = Depends(_export),
):
    """ZIP per karyawan: biodata (Excel) + seluruh dokumen versi terkini.

    Filter sama dengan Laporan Karyawan. Dibatasi agar satu permintaan tidak menghabiskan memori
    server: maksimum 200 karyawan dan 150 MB berkas.
    """
    db = get_db()
    scope = await dscope.get_scope(ctx)
    if employee_id:
        rows = [await dscope.get_scoped_employee(ctx, employee_id)]
    else:
        flt: Dict[str, Any] = {"company_id": ctx.company_id, "status": {"$ne": "deleted"}}
        if project_id:
            flt["project_id"] = project_id
        if status_filter:
            if status_filter not in ("active", "inactive"):
                raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                           "Status karyawan tidak dikenal. Pilihan: Aktif atau Tidak Aktif.")
            flt["status"] = status_filter
        needle = _text(q)
        if needle:
            flt["$or"] = [{"full_name": {"$regex": needle, "$options": "i"}},
                          {"employee_number": {"$regex": needle, "$options": "i"}},
                          {"nik": {"$regex": needle, "$options": "i"}}]
        rows = serialize_list(await db.employees.find(dscope.with_scope(flt, scope), NO_ID)
                              .sort("full_name", 1).to_list(MAX_BUNDLE_EMPLOYEES + 1))
    if not rows:
        raise _err(status.HTTP_404_NOT_FOUND, "Tidak ada karyawan yang cocok dengan filter ini.")
    if len(rows) > MAX_BUNDLE_EMPLOYEES:
        raise _err(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                   f"Bundel dibatasi {MAX_BUNDLE_EMPLOYEES} karyawan per unduhan. "
                   "Persempit filter project atau gunakan pencarian.")

    employee_ids = [r["id"] for r in rows]
    doc_flt: Dict[str, Any] = {
        "company_id": ctx.company_id, "owner_type": "employee", "owner_id": {"$in": employee_ids},
        "is_deleted": False,
        "$sql": (lambda t: t.c.superseded_by_document_id.is_(None)),
    }
    docs = serialize_list(await db.documents.find(doc_flt, NO_ID).sort("name", 1).to_list(MAX_ROWS))
    type_names = await _name_map(ctx, "document_types", [d.get("document_type_id") for d in docs])
    for doc in docs:
        doc["document_type_name"] = type_names.get(doc.get("document_type_id"))
    docs_by_employee: Dict[str, List[Dict[str, Any]]] = {}
    for doc in docs:
        docs_by_employee.setdefault(doc.get("owner_id"), []).append(doc)

    names_map = {
        "project": await _name_map(ctx, "projects", [r.get("project_id") for r in rows]),
        "location": await _name_map(ctx, "work_locations", [r.get("work_location_id") for r in rows]),
        "department": await _name_map(ctx, "departments", [r.get("department_id") for r in rows]),
        "division": await _name_map(ctx, "divisions", [r.get("division_id") for r in rows]),
        "position": await _name_map(ctx, "positions", [r.get("position_id") for r in rows]),
        "employment": await _name_map(ctx, "employment_statuses", [r.get("employment_status_id") for r in rows]),
    }

    buffer = io.BytesIO()
    failed: List[str] = []
    total_bytes = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for emp in rows:
            folder = (f"{_safe_name(emp.get('employee_number'), 'karyawan')}_"
                      f"{_safe_name(emp.get('full_name'), emp['id'][:8])}")
            emp_docs = docs_by_employee.get(emp["id"], [])
            per_names = {key: mp.get(emp.get(f"{key}_id")) for key, mp in
                         (("project", names_map["project"]), ("location", names_map["location"]),
                          ("department", names_map["department"]), ("division", names_map["division"]),
                          ("position", names_map["position"]), ("employment", names_map["employment"]))}
            archive.writestr(f"{folder}/biodata.xlsx", _biodata_xlsx(emp, per_names, emp_docs))
            for doc in emp_docs:
                if not doc.get("storage_path"):
                    continue
                file_label = (f"{_safe_name(doc.get('document_type_name'), 'dokumen')}-"
                              f"{_safe_name(doc.get('file_name'), 'berkas')}")
                try:
                    data, _content_type = get_object(doc["storage_path"])
                except Exception:  # noqa: BLE001 - satu berkas gagal tidak boleh menggagalkan bundel
                    failed.append(f"{folder}/dokumen/{file_label}")
                    continue
                total_bytes += len(data)
                if total_bytes > MAX_BUNDLE_BYTES:
                    raise _err(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                               "Ukuran bundel melebihi 150 MB. Persempit filter (project atau pencarian) "
                               "lalu unduh bertahap.")
                archive.writestr(f"{folder}/dokumen/{file_label}", data)
        if failed:
            archive.writestr("BERKAS-GAGAL-DIAMBIL.txt",
                             "Berkas berikut tidak dapat diambil dari object storage:\n" + "\n".join(failed))

    generated = datetime.now().astimezone()
    await log_action(ctx, "export", "report", None, "Bundel karyawan (ZIP)", module="hr_core",
                     notes=f"Bundel ZIP {len(rows)} karyawan, {total_bytes} byte berkas, cakupan: "
                           f"{_scope_label(scope)}")
    filename = f"Biodata-Karyawan-{generated.strftime('%Y%m%d')}.zip"
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
