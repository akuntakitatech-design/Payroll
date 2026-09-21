"""Fondasi Time Management: Master Shift, Kalender Kerja, Jenis Cuti,
Kebijakan Waktu, dan Tutup / Buka Kembali Periode.

Semua tabel tenant-scoped. RBAC memakai resource existing:
  * ``attendance`` (modul attendance) untuk shift, kalender, periode
  * ``leave`` (modul leave_overtime) untuk jenis cuti
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..core.audit import log_action
from ..core.db import ASCENDING, NO_ID, get_db, now, serialize_list
from ..core.deps import AuthContext, get_auth, require_permission
from ..core.repo import TenantRepository
from ..core import time_approval as ta
from ..core import time_service as svc
from ..core import timekeeping as tk

router = APIRouter(prefix="/time", tags=["Time Management - Fondasi"])


def _att(action: str):
    return require_permission("attendance", action, "attendance")


def _leave(action: str):
    return require_permission("leave", action, "leave_overtime")


# ==========================================================================
# KATALOG (label Bahasa Indonesia untuk seluruh UI Time Management)
# ==========================================================================
@router.get("/catalog")
async def catalog(ctx: AuthContext = Depends(get_auth)):
    db = get_db()
    shifts = await db.work_shifts.find(
        {"company_id": ctx.company_id, "status": "active"}, NO_ID
    ).sort("sort_order", ASCENDING).to_list(200)
    locations = await db.work_locations.find(
        {"company_id": ctx.company_id, "status": {"$ne": "deleted"}}, NO_ID
    ).sort("name", ASCENDING).to_list(300)
    leave_types = await db.leave_types.find(
        {"company_id": ctx.company_id, "status": "active"}, NO_ID
    ).sort("sort_order", ASCENDING).to_list(100)
    policies = await tk.get_time_policies(ctx.company_id)

    return {
        "attendance_statuses": tk.catalog_list(tk.ATTENDANCE_STATUSES),
        "attendance_sources": tk.catalog_list(tk.ATTENDANCE_SOURCES),
        "geofence_policies": tk.catalog_list(tk.GEOFENCE_POLICIES),
        "geofence_results": tk.catalog_list(tk.GEOFENCE_RESULTS),
        "location_approval_statuses": tk.catalog_list(tk.LOCATION_APPROVAL_STATUSES),
        "location_reason_codes": tk.catalog_list(tk.LOCATION_REASON_CODES),
        "day_types": tk.catalog_list(tk.DAY_TYPES),
        "calendar_day_types": [
            {"key": k, "label": tk.DAY_TYPES[k]} for k in tk.CALENDAR_DAY_TYPES
        ],
        "leave_categories": tk.catalog_list(tk.LEAVE_CATEGORIES),
        "request_statuses": tk.catalog_list(tk.REQUEST_STATUSES),
        "correction_types": tk.catalog_list(tk.CORRECTION_TYPES),
        "day_parts": tk.catalog_list(tk.DAY_PARTS),
        "overtime_day_categories": tk.catalog_list(tk.OVERTIME_DAY_CATEGORIES),
        "overtime_categories": tk.catalog_list(tk.OVERTIME_CATEGORIES),
        "exception_kinds": tk.catalog_list(tk.EXCEPTION_KINDS),
        "period_statuses": tk.catalog_list(tk.PERIOD_STATUSES),
        "shifts": [
            {"id": s["id"], "code": s.get("code"), "name": s.get("name"),
             "start_time": s.get("start_time"), "end_time": s.get("end_time"),
             "is_overnight": bool(s.get("is_overnight")), "is_day_off": bool(s.get("is_day_off"))}
            for s in shifts
        ],
        "work_locations": [
            {"id": l["id"], "code": l.get("code"), "name": l.get("name"),
             "latitude": l.get("latitude"), "longitude": l.get("longitude"),
             "radius_meter": l.get("radius_meter"),
             "geofence_enabled": l.get("geofence_enabled"),
             "attendance_location_policy": l.get("attendance_location_policy"),
             "policy_label": tk.GEOFENCE_POLICIES.get(l.get("attendance_location_policy") or "", "-")}
            for l in locations
        ],
        "leave_types": [
            {"id": t["id"], "code": t.get("code"), "name": t.get("name"),
             "category": t.get("category"),
             "category_label": tk.LEAVE_CATEGORIES.get(t.get("category") or "", "-"),
             "deduct_balance": bool(t.get("deduct_balance")),
             "is_paid": bool(t.get("is_paid")),
             "attachment_required": bool(t.get("attachment_required")),
             "allow_half_day": bool(t.get("allow_half_day")),
             "minimum_notice_days": t.get("minimum_notice_days"),
             "maximum_consecutive_days": t.get("maximum_consecutive_days"),
             "default_quota_days": t.get("default_quota_days")}
            for t in leave_types
        ],
        "policies": policies,
        "approval_readiness": {
            kind: await ta.workflow_state(ctx.company_id, kind) for kind in ta.DOCUMENT_KINDS
        },
        "can": {
            "attendance_view": ctx.has_permission("attendance", "view"),
            "attendance_create": ctx.has_permission("attendance", "create"),
            "attendance_edit": ctx.has_permission("attendance", "edit"),
            "attendance_approve": ctx.has_permission("attendance", "approve"),
            "attendance_export": ctx.has_permission("attendance", "export"),
            "leave_view": ctx.has_permission("leave", "view"),
            "leave_create": ctx.has_permission("leave", "create"),
            "leave_edit": ctx.has_permission("leave", "edit"),
            "leave_approve": ctx.has_permission("leave", "approve"),
            "leave_export": ctx.has_permission("leave", "export"),
        },
    }


# ==========================================================================
# MASTER SHIFT
# ==========================================================================
class ShiftInput(BaseModel):
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=120)
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    break_start: Optional[str] = None
    break_end: Optional[str] = None
    late_tolerance_minutes: int = 0
    early_leave_tolerance_minutes: int = 0
    is_day_off: bool = False
    sort_order: int = 0
    description: Optional[str] = None


def _shift_payload(payload: ShiftInput) -> Dict[str, Any]:
    data = payload.model_dump()
    data["code"] = data["code"].strip().upper()
    if data.get("is_day_off"):
        data["start_time"] = None
        data["end_time"] = None
        data["break_start"] = None
        data["break_end"] = None
        data["is_overnight"] = False
        return data
    data["start_time"] = tk.parse_time_str(data.get("start_time"), "Jam Masuk", required=True)
    data["end_time"] = tk.parse_time_str(data.get("end_time"), "Jam Pulang", required=True)
    data["break_start"] = tk.parse_time_str(data.get("break_start"), "Istirahat Mulai", required=False)
    data["break_end"] = tk.parse_time_str(data.get("break_end"), "Istirahat Selesai", required=False)
    if bool(data["break_start"]) != bool(data["break_end"]):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Istirahat Mulai dan Istirahat Selesai harus diisi bersamaan.")
    for field, label in (("late_tolerance_minutes", "Toleransi Terlambat"),
                         ("early_leave_tolerance_minutes", "Toleransi Pulang Cepat")):
        value = int(data.get(field) or 0)
        if value < 0 or value > 480:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"{label} harus antara 0 dan 480 menit.")
        data[field] = value
    data["is_overnight"] = tk.shift_is_overnight(data)
    return data


def _decorate_shift(shift: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(shift)
    out["scheduled_minutes"] = tk.shift_scheduled_minutes(shift)
    out["scheduled_hours_label"] = tk.minutes_to_hhmm(out["scheduled_minutes"])
    out["break_minutes"] = tk.shift_break_minutes(shift)
    out["is_overnight"] = bool(shift.get("is_overnight"))
    out["window_label"] = (
        "OFF" if shift.get("is_day_off")
        else f"{shift.get('start_time') or '-'} - {shift.get('end_time') or '-'}"
        + (" (lintas hari)" if shift.get("is_overnight") else "")
    )
    return out


@router.get("/shifts")
async def list_shifts(
    q: Optional[str] = None,
    include_inactive: bool = True,
    ctx: AuthContext = Depends(_att("view")),
):
    repo = TenantRepository("work_shifts", ctx.company_id)
    filters: Dict[str, Any] = {}
    if not include_inactive:
        filters["status"] = "active"
    result = await repo.list(q=q, search_fields=["code", "name"], filters=filters,
                             page=1, limit=200, sort_by="sort_order", sort_dir="asc")
    result["items"] = [_decorate_shift(s) for s in serialize_list(result["items"])]
    return result


@router.post("/shifts", status_code=status.HTTP_201_CREATED)
async def create_shift(payload: ShiftInput, ctx: AuthContext = Depends(_att("create"))):
    svc.require_hr_scope(ctx)
    repo = TenantRepository("work_shifts", ctx.company_id)
    data = _shift_payload(payload)
    await repo.ensure_unique("code", data["code"], label="Kode Shift")
    created = await repo.create(data, ctx.user_id)
    await log_action(ctx, "create", "attendance", created["id"], f"Shift {created['code']}",
                     after=created, module="attendance", notes="Shift dibuat")
    return _decorate_shift(created)


@router.put("/shifts/{shift_id}")
async def update_shift(shift_id: str, payload: ShiftInput, ctx: AuthContext = Depends(_att("edit"))):
    repo = TenantRepository("work_shifts", ctx.company_id)
    data = _shift_payload(payload)
    await repo.ensure_unique("code", data["code"], exclude_id=shift_id, label="Kode Shift")
    before, after = await repo.update(shift_id, data, ctx.user_id)
    await log_action(ctx, "update", "attendance", shift_id, f"Shift {after['code']}",
                     before=before, after=after, module="attendance", notes="Shift diubah")
    return _decorate_shift(after)


@router.patch("/shifts/{shift_id}/status")
async def set_shift_status(
    shift_id: str,
    new_status: str = Body(..., embed=True, alias="status"),
    ctx: AuthContext = Depends(_att("edit")),
):
    if new_status not in ("active", "inactive"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Status hanya boleh Aktif atau Nonaktif.")
    repo = TenantRepository("work_shifts", ctx.company_id)
    before, after = await repo.set_status(shift_id, new_status, ctx.user_id)
    await log_action(ctx, "status", "attendance", shift_id, f"Shift {after['code']}",
                     before=before, after=after, module="attendance")
    return _decorate_shift(after)


@router.delete("/shifts/{shift_id}")
async def delete_shift(shift_id: str, ctx: AuthContext = Depends(_att("delete"))):
    db = get_db()
    repo = TenantRepository("work_shifts", ctx.company_id)
    shift = await repo.get(shift_id)
    used = await db.work_schedules.count_documents(
        {"company_id": ctx.company_id, "shift_id": shift_id, "status": {"$ne": "deleted"}}
    )
    if used:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Shift ini sudah dipakai pada {used} jadwal kerja. Nonaktifkan shift, jangan dihapus, "
            "agar riwayat jadwal tetap utuh.",
        )
    before, after = await repo.update(shift_id, {"status": "deleted"}, ctx.user_id)
    await log_action(ctx, "delete", "attendance", shift_id, f"Shift {shift.get('code')}",
                     before=before, after=after, module="attendance")
    return {"message": f"Shift {shift.get('code')} berhasil dihapus."}


# ==========================================================================
# KALENDER KERJA (libur nasional / perusahaan / cuti bersama)
# ==========================================================================
class CalendarDayInput(BaseModel):
    calendar_date: str
    day_type: str
    name: str = Field(..., min_length=1, max_length=160)
    notes: Optional[str] = None


@router.get("/calendar-days")
async def list_calendar_days(
    year: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    ctx: AuthContext = Depends(_att("view")),
):
    db = get_db()
    query: Dict[str, Any] = {"company_id": ctx.company_id, "status": {"$ne": "deleted"}}
    if year:
        query["calendar_date"] = {"$gte": f"{year}-01-01", "$lte": f"{year}-12-31"}
    elif date_from and date_to:
        query["calendar_date"] = {
            "$gte": tk.parse_date_str(date_from, "Tanggal Mulai"),
            "$lte": tk.parse_date_str(date_to, "Tanggal Selesai"),
        }
    rows = await db.work_calendar_days.find(query, NO_ID).sort("calendar_date", ASCENDING).to_list(1000)
    return {
        "items": [
            {**r, "day_type_label": tk.DAY_TYPES.get(r.get("day_type") or "", "-")}
            for r in serialize_list(rows)
        ],
        "total": len(rows),
    }


@router.post("/calendar-days", status_code=status.HTTP_201_CREATED)
async def create_calendar_day(payload: CalendarDayInput, ctx: AuthContext = Depends(_att("create"))):
    svc.require_hr_scope(ctx)
    if payload.day_type not in tk.CALENDAR_DAY_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Jenis hari kalender tidak dikenal.")
    data = payload.model_dump()
    data["calendar_date"] = tk.parse_date_str(data["calendar_date"], "Tanggal")
    repo = TenantRepository("work_calendar_days", ctx.company_id)
    await repo.ensure_unique("calendar_date", data["calendar_date"], label="Tanggal kalender")
    created = await repo.create(data, ctx.user_id)
    await log_action(ctx, "create", "attendance", created["id"],
                     f"Kalender {created['calendar_date']}", after=created, module="attendance")
    return {**created, "day_type_label": tk.DAY_TYPES.get(created["day_type"], "-")}


@router.put("/calendar-days/{day_id}")
async def update_calendar_day(day_id: str, payload: CalendarDayInput, ctx: AuthContext = Depends(_att("edit"))):
    if payload.day_type not in tk.CALENDAR_DAY_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Jenis hari kalender tidak dikenal.")
    data = payload.model_dump()
    data["calendar_date"] = tk.parse_date_str(data["calendar_date"], "Tanggal")
    repo = TenantRepository("work_calendar_days", ctx.company_id)
    await repo.ensure_unique("calendar_date", data["calendar_date"], exclude_id=day_id, label="Tanggal kalender")
    before, after = await repo.update(day_id, data, ctx.user_id)
    await log_action(ctx, "update", "attendance", day_id, f"Kalender {after['calendar_date']}",
                     before=before, after=after, module="attendance")
    return {**after, "day_type_label": tk.DAY_TYPES.get(after["day_type"], "-")}


@router.delete("/calendar-days/{day_id}")
async def delete_calendar_day(day_id: str, ctx: AuthContext = Depends(_att("delete"))):
    repo = TenantRepository("work_calendar_days", ctx.company_id)
    row = await repo.get(day_id)
    before, after = await repo.update(day_id, {"status": "deleted"}, ctx.user_id)
    await log_action(ctx, "delete", "attendance", day_id, f"Kalender {row.get('calendar_date')}",
                     before=before, after=after, module="attendance")
    return {"message": "Tanggal kalender berhasil dihapus."}


# ==========================================================================
# JENIS CUTI / IZIN / SAKIT
# ==========================================================================
class LeaveTypeInput(BaseModel):
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=120)
    category: str = "annual"
    deduct_balance: bool = True
    is_paid: bool = True
    attachment_required: bool = False
    approval_required: bool = True
    allow_half_day: bool = True
    minimum_notice_days: int = 0
    maximum_consecutive_days: Optional[int] = None
    default_quota_days: float = 0
    sort_order: int = 0
    description: Optional[str] = None


def _decorate_leave_type(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **row,
        "category_label": tk.LEAVE_CATEGORIES.get(row.get("category") or "", "-"),
        "recap_status": tk.LEAVE_CATEGORY_TO_STATUS.get(row.get("category") or "", "leave"),
        "recap_status_label": tk.status_label(
            tk.LEAVE_CATEGORY_TO_STATUS.get(row.get("category") or "", "leave")
        ),
    }


@router.get("/leave-types")
async def list_leave_types(
    q: Optional[str] = None,
    include_inactive: bool = True,
    ctx: AuthContext = Depends(_leave("view")),
):
    repo = TenantRepository("leave_types", ctx.company_id)
    filters: Dict[str, Any] = {} if include_inactive else {"status": "active"}
    result = await repo.list(q=q, search_fields=["code", "name"], filters=filters,
                             page=1, limit=200, sort_by="sort_order", sort_dir="asc")
    result["items"] = [_decorate_leave_type(r) for r in serialize_list(result["items"])]
    return result


def _leave_type_payload(payload: LeaveTypeInput) -> Dict[str, Any]:
    data = payload.model_dump()
    if data["category"] not in tk.LEAVE_CATEGORIES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Kategori cuti tidak dikenal.")
    data["code"] = data["code"].strip().upper()
    if int(data.get("minimum_notice_days") or 0) < 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Minimal pemberitahuan tidak boleh negatif.")
    if data.get("maximum_consecutive_days") is not None and int(data["maximum_consecutive_days"]) <= 0:
        data["maximum_consecutive_days"] = None
    if float(data.get("default_quota_days") or 0) < 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Kuota default tidak boleh negatif.")
    return data


@router.post("/leave-types", status_code=status.HTTP_201_CREATED)
async def create_leave_type(payload: LeaveTypeInput, ctx: AuthContext = Depends(_leave("create"))):
    repo = TenantRepository("leave_types", ctx.company_id)
    data = _leave_type_payload(payload)
    await repo.ensure_unique("code", data["code"], label="Kode Jenis Cuti")
    created = await repo.create(data, ctx.user_id)
    await log_action(ctx, "create", "leave", created["id"], f"Jenis Cuti {created['name']}",
                     after=created, module="leave_overtime")
    return _decorate_leave_type(created)


@router.put("/leave-types/{type_id}")
async def update_leave_type(type_id: str, payload: LeaveTypeInput, ctx: AuthContext = Depends(_leave("edit"))):
    repo = TenantRepository("leave_types", ctx.company_id)
    data = _leave_type_payload(payload)
    await repo.ensure_unique("code", data["code"], exclude_id=type_id, label="Kode Jenis Cuti")
    before, after = await repo.update(type_id, data, ctx.user_id)
    await log_action(ctx, "update", "leave", type_id, f"Jenis Cuti {after['name']}",
                     before=before, after=after, module="leave_overtime")
    return _decorate_leave_type(after)


@router.patch("/leave-types/{type_id}/status")
async def set_leave_type_status(
    type_id: str,
    new_status: str = Body(..., embed=True, alias="status"),
    ctx: AuthContext = Depends(_leave("edit")),
):
    if new_status not in ("active", "inactive"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Status hanya boleh Aktif atau Nonaktif.")
    repo = TenantRepository("leave_types", ctx.company_id)
    before, after = await repo.set_status(type_id, new_status, ctx.user_id)
    await log_action(ctx, "status", "leave", type_id, f"Jenis Cuti {after['name']}",
                     before=before, after=after, module="leave_overtime")
    return _decorate_leave_type(after)


@router.delete("/leave-types/{type_id}")
async def delete_leave_type(type_id: str, ctx: AuthContext = Depends(_leave("delete"))):
    db = get_db()
    repo = TenantRepository("leave_types", ctx.company_id)
    row = await repo.get(type_id)
    used = await db.leave_requests.count_documents(
        {"company_id": ctx.company_id, "leave_type_id": type_id, "status": {"$ne": "deleted"}}
    )
    if used:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Jenis cuti ini sudah dipakai pada {used} pengajuan. Nonaktifkan saja agar riwayat tetap utuh.",
        )
    before, after = await repo.update(type_id, {"status": "deleted"}, ctx.user_id)
    await log_action(ctx, "delete", "leave", type_id, f"Jenis Cuti {row.get('name')}",
                     before=before, after=after, module="leave_overtime")
    return {"message": f"Jenis cuti {row.get('name')} berhasil dihapus."}


# ==========================================================================
# KEBIJAKAN WAKTU
# ==========================================================================
@router.get("/policies")
async def get_policies(ctx: AuthContext = Depends(_att("view"))):
    return await tk.get_time_policies(ctx.company_id)


@router.put("/policies")
async def update_policies(
    payload: Dict[str, Any] = Body(...),
    ctx: AuthContext = Depends(_att("edit")),
):
    before = await tk.get_time_policies(ctx.company_id)
    merged = {
        "attendance": {**before["attendance"], **(payload.get("attendance") or {})},
        "overtime": {**before["overtime"], **(payload.get("overtime") or {})},
        "leave": {**before["leave"], **(payload.get("leave") or {})},
    }
    policy = merged["attendance"].get("default_geofence_policy")
    if policy not in tk.GEOFENCE_POLICIES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Kebijakan lokasi absensi default tidak dikenal.")
    for field, label, lo, hi in (
        ("minimum_minutes", "Lembur minimal", 0, 480),
        ("rounding_interval_minutes", "Pembulatan lembur", 1, 120),
        ("max_minutes_per_day", "Maksimal lembur per hari", 0, 960),
    ):
        value = int(merged["overtime"].get(field) or 0)
        if value < lo or value > hi:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"{label} harus antara {lo} dan {hi} menit.")
        merged["overtime"][field] = value

    db = get_db()
    await db.time_policies.update_one(
        {"company_id": ctx.company_id},
        {"$set": {
            "company_id": ctx.company_id, "status": "active",
            "attendance": merged["attendance"], "overtime": merged["overtime"], "leave": merged["leave"],
            "updated_at": now(), "updated_by": ctx.user_id,
        }},
        upsert=True,
    )
    await log_action(ctx, "config", "attendance", None, "Kebijakan Time Management",
                     before=before, after=merged, module="attendance")
    return merged


# ==========================================================================
# TUTUP / BUKA KEMBALI PERIODE
# ==========================================================================
class PeriodActionInput(BaseModel):
    period_key: str
    reason: Optional[str] = None


def _decorate_period(row: Dict[str, Any]) -> Dict[str, Any]:
    state = row.get("period_status") or "open"
    return {
        **row,
        "period_label": row.get("period_label") or tk.period_label_of(row.get("period_key") or ""),
        "period_status": state,
        "period_status_label": tk.PERIOD_STATUSES.get(state, {}).get("label", "-"),
        "period_status_tone": tk.PERIOD_STATUSES.get(state, {}).get("tone", "neutral"),
    }


def _valid_period_key(value: str) -> str:
    text = str(value or "").strip()
    if len(text) != 7 or text[4] != "-" or not text[:4].isdigit() or not text[5:].isdigit():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Periode harus berformat YYYY-MM.")
    if not 1 <= int(text[5:]) <= 12:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Bulan periode tidak valid.")
    return text


@router.get("/periods")
async def list_periods(
    year: Optional[int] = None,
    ctx: AuthContext = Depends(_att("view")),
):
    db = get_db()
    query: Dict[str, Any] = {"company_id": ctx.company_id, "status": {"$ne": "deleted"}}
    if year:
        query["period_key"] = {"$gte": f"{year}-01", "$lte": f"{year}-12"}
    rows = await db.time_periods.find(query, NO_ID).sort("period_key", -1).to_list(240)
    return {"items": [_decorate_period(r) for r in serialize_list(rows)], "total": len(rows)}


@router.get("/periods/{period_key}")
async def get_period(period_key: str, ctx: AuthContext = Depends(_att("view"))):
    key = _valid_period_key(period_key)
    db = get_db()
    row = await db.time_periods.find_one({"company_id": ctx.company_id, "period_key": key}, NO_ID)
    if not row:
        return _decorate_period({"period_key": key, "period_status": "open", "history": []})
    return _decorate_period(row)


@router.post("/periods/close")
async def close_period(payload: PeriodActionInput, ctx: AuthContext = Depends(_att("approve"))):
    key = _valid_period_key(payload.period_key)
    db = get_db()
    before = await db.time_periods.find_one({"company_id": ctx.company_id, "period_key": key}, NO_ID)
    if before and before.get("period_status") == "closed":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Periode {tk.period_label_of(key)} sudah dalam keadaan ditutup.")
    pending_leave = await db.leave_requests.count_documents({
        "company_id": ctx.company_id, "request_status": "pending",
        "period_keys": {"$regex": key},
    })
    history = list((before or {}).get("history") or [])
    history.append({
        "action": "close", "at": tk.now_utc().isoformat(), "by": ctx.user_id,
        "by_name": ctx.user.get("full_name"), "reason": payload.reason,
    })
    patch = {
        "company_id": ctx.company_id, "period_key": key, "status": "active",
        "period_label": tk.period_label_of(key), "period_status": "closed",
        "closed_by": ctx.user_id, "closed_by_name": ctx.user.get("full_name"),
        "closed_at": now(), "close_notes": payload.reason, "history": history,
        "updated_at": now(), "updated_by": ctx.user_id,
    }
    await db.time_periods.update_one(
        {"company_id": ctx.company_id, "period_key": key}, {"$set": patch}, upsert=True
    )
    after = await db.time_periods.find_one({"company_id": ctx.company_id, "period_key": key}, NO_ID)
    await log_action(ctx, "period_close", "attendance", after["id"], f"Tutup Periode {tk.period_label_of(key)}",
                     before=before, after=after, module="attendance", notes=payload.reason)
    result = _decorate_period(after)
    result["warning"] = (
        f"Masih ada {pending_leave} pengajuan cuti berstatus Menunggu Persetujuan pada periode ini."
        if pending_leave else None
    )
    return result


@router.post("/periods/reopen")
async def reopen_period(payload: PeriodActionInput, ctx: AuthContext = Depends(_att("approve"))):
    key = _valid_period_key(payload.period_key)
    if not (payload.reason or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Alasan wajib diisi saat membuka kembali periode.")
    db = get_db()
    before = await db.time_periods.find_one({"company_id": ctx.company_id, "period_key": key}, NO_ID)
    if not before or before.get("period_status") != "closed":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Periode {tk.period_label_of(key)} tidak sedang ditutup.")
    history = list(before.get("history") or [])
    history.append({
        "action": "reopen", "at": tk.now_utc().isoformat(), "by": ctx.user_id,
        "by_name": ctx.user.get("full_name"), "reason": payload.reason,
    })
    await db.time_periods.update_one(
        {"company_id": ctx.company_id, "period_key": key},
        {"$set": {
            "period_status": "open", "reopened_by": ctx.user_id,
            "reopened_by_name": ctx.user.get("full_name"), "reopened_at": now(),
            "reopen_reason": payload.reason, "history": history,
            "updated_at": now(), "updated_by": ctx.user_id,
        }},
    )
    after = await db.time_periods.find_one({"company_id": ctx.company_id, "period_key": key}, NO_ID)
    await log_action(ctx, "period_reopen", "attendance", after["id"],
                     f"Buka Kembali Periode {tk.period_label_of(key)}",
                     before=before, after=after, module="attendance", notes=payload.reason)
    return _decorate_period(after)
