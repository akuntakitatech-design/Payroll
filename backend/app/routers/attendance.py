"""ABSENSI: Absen Masuk/Pulang ber-GPS, koreksi, import Excel, persetujuan
lokasi, masalah kehadiran, dashboard, dan Rekap Kehadiran.

Keputusan geofence, status kehadiran, dan perhitungan menit SELALU di backend.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..core.audit import log_action
from ..core.db import ASCENDING, NO_ID, audit_fields, get_db, new_id, now, serialize_list
from ..core.deps import AuthContext, get_auth, require_permission
from ..core.repo import TenantRepository
from ..core import time_approval as ta
from ..core import time_excel as tx
from ..core import time_service as svc
from ..core import timekeeping as tk

router = APIRouter(prefix="/attendance", tags=["Time Management - Absensi"])


def _perm(action: str):
    return require_permission("attendance", action, "attendance")


def _can_see_gps(ctx: AuthContext) -> bool:
    return ctx.has_permission("attendance", "approve") or ctx.has_permission("attendance", "edit")


# ==========================================================================
# ABSEN MASUK / ABSEN PULANG (self service)
# ==========================================================================
class CheckInput(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy: Optional[float] = None
    location_captured_at: Optional[str] = None
    reason_code: Optional[str] = None
    reason: Optional[str] = None
    note: Optional[str] = None
    source: str = "web"
    # Kunci idempotensi dari klien (satu nilai per niat absen). Retry/double-click
    # dengan kunci yang sama mengembalikan transaksi yang sama, bukan transaksi baru.
    client_request_id: Optional[str] = Field(default=None, max_length=64)


def _validate_source(source: str) -> str:
    if source not in tk.ATTENDANCE_SOURCES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Sumber absensi tidak dikenal.")
    return source


def _client_time(value: Optional[str]):
    """Waktu capture GPS dari perangkat: hanya informasi pendukung, BUKAN sumber waktu absensi."""
    if not value:
        return None
    try:
        from datetime import datetime as _dt
        parsed = _dt.fromisoformat(str(value).replace("Z", "+00:00"))
        return tk.to_utc(parsed) if parsed.tzinfo else None
    except ValueError:
        return None


async def _today_context(ctx: AuthContext, employee: Dict[str, Any]) -> Dict[str, Any]:
    """Tentukan work_date kanonik untuk absensi mandiri (server-side)."""
    company = ctx.company
    tz = tk.tz_for(company)
    local_now = tk.now_utc().astimezone(tz)
    today = local_now.date().isoformat()
    yesterday = (local_now.date().fromordinal(local_now.date().toordinal() - 1)).isoformat()

    context = await svc.resolve_context(company, employee, today)
    # Shift malam kemarin yang belum selesai tetap menjadi milik work_date kemarin.
    prev = await svc.resolve_context(company, employee, yesterday)
    if prev.get("shift") and tk.shift_is_overnight(prev["shift"]):
        _, prev_end = tk.shift_bounds(yesterday, prev["shift"], prev["tz"])
        if prev_end and tk.now_utc() <= prev_end:
            db = get_db()
            open_row = await db.attendances.find_one({
                "company_id": ctx.company_id, "employee_id": employee["id"],
                "work_date": yesterday, "status": {"$ne": "deleted"}}, NO_ID)
            if open_row and open_row.get("check_in_at") and not open_row.get("check_out_at"):
                return {"work_date": yesterday, **prev}
            if not context.get("shift"):
                return {"work_date": yesterday, **prev}
    return {"work_date": today, **context}


async def _geofence_for(ctx: AuthContext, context: Dict[str, Any], payload: CheckInput) -> Dict[str, Any]:
    policies = await tk.get_time_policies(ctx.company_id)
    result = tk.evaluate_geofence(
        context.get("work_location"), policies["attendance"],
        payload.latitude, payload.longitude, payload.accuracy)
    if result["blocked"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, result["message"])
    if result["requires_approval"]:
        if not payload.reason_code or payload.reason_code not in tk.LOCATION_REASON_CODES:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"{result['message']} Pilih alasan absensi di luar radius terlebih dahulu.")
        # Keterangan bebas wajib hanya untuk alasan "Lainnya"; alasan lain cukup dipilih.
        if payload.reason_code == "other" and len((payload.reason or "").strip()) < 3:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Keterangan wajib diisi bila memilih alasan Lainnya.")
    return result


def _today_status(context: Dict[str, Any], row: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Status harian user-facing (dihitung backend) untuk kartu Absensi Saya."""
    if row:
        decorated = tk.decorate_attendance(row)
        return {"key": row.get("attendance_status") or "present",
                "label": decorated["attendance_status_label"],
                "tone": decorated["attendance_status_tone"]}
    schedule = context.get("schedule")
    day_type = context.get("day_type")
    if schedule and schedule.get("is_day_off"):
        return {"key": "day_off", "label": tk.status_label("day_off"), "tone": "neutral"}
    if day_type in tk.HOLIDAY_DAY_TYPES:
        return {"key": "holiday", "label": tk.status_label("holiday"), "tone": "neutral"}
    if not schedule:
        if day_type == "weekly_off":
            return {"key": "day_off", "label": tk.status_label("day_off"), "tone": "neutral"}
        return {"key": "no_schedule", "label": "Jadwal kerja belum tersedia", "tone": "neutral"}
    return {"key": "not_checked_in", "label": "Belum Absen", "tone": "neutral"}


@router.get("/me/today")
async def my_today(ctx: AuthContext = Depends(_perm("view"))):
    employee = await svc.my_employee(ctx, required=False)
    if not employee:
        return {"linked": False,
                "message": "Akun Anda belum terhubung ke Data Karyawan pada perusahaan aktif."}
    context = await _today_context(ctx, employee)
    db = get_db()
    row = await db.attendances.find_one({
        "company_id": ctx.company_id, "employee_id": employee["id"],
        "work_date": context["work_date"], "status": {"$ne": "deleted"}}, NO_ID)
    policies = await tk.get_time_policies(ctx.company_id)
    loc = context.get("work_location")
    policy = tk.effective_location_policy(loc, policies["attendance"])
    schedule = context.get("schedule")
    shift = context.get("shift")
    is_day_off = bool(schedule and schedule.get("is_day_off"))
    has_shift = bool(shift and not is_day_off)
    can_check_in = bool(row is None or not row.get("check_in_at")) and not is_day_off and (
        bool(schedule) or bool(policies["attendance"].get("allow_check_in_without_schedule")))
    return {
        "linked": True,
        "employee": {"id": employee["id"], "full_name": employee.get("full_name"),
                     "employee_number": employee.get("employee_number")},
        "server_time": tk.now_utc(),
        "timezone": str(context["tz"]),
        "work_date": context["work_date"],
        "day_type": context["day_type"],
        "day_type_label": tk.DAY_TYPES.get(context["day_type"], "-"),
        "shift": ({"id": shift["id"], "code": shift.get("code"),
                   "name": shift.get("name"),
                   "start_time": shift.get("start_time"),
                   "end_time": shift.get("end_time"),
                   "break_start": shift.get("break_start"),
                   "break_end": shift.get("break_end"),
                   "late_tolerance_minutes": shift.get("late_tolerance_minutes"),
                   "is_overnight": tk.shift_is_overnight(shift)}
                  if has_shift else None),
        "is_day_off": is_day_off,
        "work_location": ({"id": loc["id"], "name": loc.get("name"), "code": loc.get("code"),
                           "address": loc.get("address"),
                           "latitude": loc.get("latitude"), "longitude": loc.get("longitude"),
                           "radius_meter": loc.get("radius_meter")} if loc else None),
        "location_policy": policy,
        "location_policy_label": tk.GEOFENCE_POLICIES.get(policy, "-"),
        "gps_required": policy != "disabled",
        "has_schedule": bool(schedule),
        "today_status": _today_status(context, row),
        "attendance": tk.decorate_attendance(row) if row else None,  # data milik sendiri
        "can_check_in": can_check_in,
        "can_check_out": bool(row and row.get("check_in_at") and not row.get("check_out_at")),
        "reason_codes": tk.catalog_list(tk.LOCATION_REASON_CODES),
    }


def _clock_response(saved: Dict[str, Any], geo: Optional[Dict[str, Any]], message: str,
                    idempotent: bool = False) -> Dict[str, Any]:
    return {"attendance": tk.decorate_attendance(saved), "geofence": geo,
            "message": message, "idempotent": idempotent}


@router.post("/check-in")
async def check_in(payload: CheckInput, ctx: AuthContext = Depends(_perm("create"))):
    _validate_source(payload.source)
    employee = await svc.my_employee(ctx)
    db = get_db()

    # Idempotensi: retry dengan kunci yang sama -> transaksi yang sama (bukan duplikat/409).
    if payload.client_request_id:
        dup = await db.attendances.find_one({
            "company_id": ctx.company_id, "employee_id": employee["id"],
            "check_in_request_id": payload.client_request_id, "status": {"$ne": "deleted"}}, NO_ID)
        if dup:
            return _clock_response(dup, None, "Absen Masuk sudah tercatat sebelumnya.", idempotent=True)

    context = await _today_context(ctx, employee)
    work_date = context["work_date"]
    await tk.assert_period_open(ctx.company_id, work_date)

    policies = await tk.get_time_policies(ctx.company_id)
    if not context.get("schedule") and not policies["attendance"].get("allow_check_in_without_schedule"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Jadwal kerja belum tersedia untuk tanggal {work_date}. Hubungi HR untuk menetapkan jadwal, "
            "atau aktifkan kebijakan absen tanpa jadwal.")
    if context.get("schedule") and context["schedule"].get("is_day_off"):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Tanggal {work_date} adalah hari OFF Anda. Ajukan Lembur bila memang bekerja.")

    # Cegah double Absen Masuk lebih awal (unique index tetap menjadi pengaman akhir).
    existing = await db.attendances.find_one({
        "company_id": ctx.company_id, "employee_id": employee["id"],
        "work_date": work_date, "status": {"$ne": "deleted"}}, NO_ID)
    if existing and existing.get("check_in_at"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Anda sudah melakukan Absen Masuk untuk hari ini.")

    geo = await _geofence_for(ctx, context, payload)
    requires_approval = bool(geo["requires_approval"])
    if requires_approval:
        # Pastikan alur persetujuan siap SEBELUM menyimpan agar tidak ada absensi menggantung.
        await ta.ensure_ready(ctx, "attendance_location", employee["id"])

    shift = context.get("shift") or {}
    loc = context.get("work_location") or {}
    server_now = tk.now_utc()
    metrics = tk.compute_attendance_metrics(shift or None, work_date, context["tz"], server_now, None)

    doc = {
        "id": new_id(), "company_id": ctx.company_id, "status": "active",
        "employee_id": employee["id"], "employee_number": employee.get("employee_number"),
        "employee_name": employee.get("full_name"),
        "work_date": work_date, "period_key": tk.period_key_of(work_date),
        "schedule_id": (context.get("schedule") or {}).get("id"),
        "shift_id": shift.get("id"), "shift_code": shift.get("code"), "shift_name": shift.get("name"),
        "work_location_id": loc.get("id"), "is_day_off": False, "day_type": context["day_type"],
        "scheduled_start_at": metrics["scheduled_start_at"], "scheduled_end_at": metrics["scheduled_end_at"],
        "scheduled_minutes": metrics["scheduled_minutes"],
        "check_in_at": server_now, "check_in_source": payload.source,
        "check_in_latitude": payload.latitude, "check_in_longitude": payload.longitude,
        "check_in_accuracy": payload.accuracy,
        "check_in_location_captured_at": server_now,
        "check_in_client_captured_at": _client_time(payload.location_captured_at),
        "check_in_request_id": payload.client_request_id,
        "check_in_distance_meter": geo["distance_meter"],
        "configured_radius_meter": geo["configured_radius_meter"],
        "geofence_policy": geo["policy"], "check_in_geofence_result": geo["geofence_result"],
        "location_approval_status": "pending" if requires_approval else "not_required",
        "location_approval_for": "check_in" if requires_approval else None,
        "location_approval_round": 1 if requires_approval else None,
        "location_reason_code": payload.reason_code if requires_approval else None,
        "location_reason": payload.reason if requires_approval else None,
        "late_minutes": metrics["late_minutes"], "early_leave_minutes": 0, "actual_work_minutes": 0,
        "note": payload.note, "source": payload.source,
        **audit_fields(ctx.user_id),
    }
    try:
        await db.attendances.insert_one(dict(doc))
    except Exception as exc:  # noqa: BLE001 - unique index (company, employee, work_date)
        existing = await db.attendances.find_one({
            "company_id": ctx.company_id, "employee_id": employee["id"], "work_date": work_date}, NO_ID)
        if existing and payload.client_request_id and existing.get("check_in_request_id") == payload.client_request_id:
            return _clock_response(existing, None, "Absen Masuk sudah tercatat sebelumnya.", idempotent=True)
        if existing and existing.get("check_in_at"):
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "Anda sudah melakukan Absen Masuk untuk hari ini.")
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Absensi untuk tanggal ini sudah ada. Muat ulang halaman.") from exc

    saved = await svc.recompute_attendance(ctx.company, doc)
    if requires_approval:
        await ta.submit(ctx, "attendance_location", saved["id"],
                        f"Absen Masuk {employee.get('full_name')} {work_date}", employee["id"])
    await log_action(ctx, "check_in_outside_radius" if requires_approval else "check_in",
                     "attendance", saved["id"],
                     f"Absen Masuk {employee.get('full_name')} {work_date}",
                     after={k: v for k, v in saved.items() if k not in ("extra",)},
                     module="attendance", notes=geo["message"])
    return _clock_response(
        saved, geo,
        "Absen Masuk tercatat dan MENUNGGU PERSETUJUAN LOKASI karena berada di luar radius."
        if requires_approval else "Absen Masuk berhasil dicatat.")


@router.post("/check-out")
async def check_out(payload: CheckInput, ctx: AuthContext = Depends(_perm("create"))):
    _validate_source(payload.source)
    employee = await svc.my_employee(ctx)
    db = get_db()

    if payload.client_request_id:
        dup = await db.attendances.find_one({
            "company_id": ctx.company_id, "employee_id": employee["id"],
            "check_out_request_id": payload.client_request_id, "status": {"$ne": "deleted"}}, NO_ID)
        if dup:
            return _clock_response(dup, None, "Absen Pulang sudah tercatat sebelumnya.", idempotent=True)

    row = await db.attendances.find_one({
        "company_id": ctx.company_id, "employee_id": employee["id"],
        "check_in_at": {"$ne": None}, "check_out_at": None, "status": {"$ne": "deleted"},
    }, NO_ID)
    if not row:
        context_now = await _today_context(ctx, employee)
        already = await db.attendances.find_one({
            "company_id": ctx.company_id, "employee_id": employee["id"],
            "work_date": context_now["work_date"],
            "check_out_at": {"$ne": None}, "status": {"$ne": "deleted"}}, NO_ID)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Anda sudah melakukan Absen Pulang untuk hari ini." if already
            else "Belum ada Absen Masuk yang terbuka. Lakukan Absen Masuk terlebih dahulu.")
    await tk.assert_period_open(ctx.company_id, row["work_date"])

    context = await svc.resolve_context(ctx.company, employee, row["work_date"])
    geo = await _geofence_for(ctx, context, payload)
    prev_status = row.get("location_approval_status") or "not_required"
    outside = bool(geo["requires_approval"])
    # Putaran persetujuan baru hanya bila Absen Pulang di luar radius dan belum ada
    # persetujuan yang masih menunggu. Lokasi yang sudah DITOLAK tetap ditolak (histori dijaga).
    new_round: Optional[int] = None
    if outside and prev_status in ("not_required", "approved"):
        await ta.ensure_ready(ctx, "attendance_location", employee["id"])
        new_round = await ta.next_round(ctx.company_id, "attendance_location", row["id"])

    server_now = tk.now_utc()
    patch: Dict[str, Any] = {
        "check_out_at": server_now, "check_out_source": payload.source,
        "check_out_latitude": payload.latitude, "check_out_longitude": payload.longitude,
        "check_out_accuracy": payload.accuracy, "check_out_location_captured_at": server_now,
        "check_out_client_captured_at": _client_time(payload.location_captured_at),
        "check_out_request_id": payload.client_request_id,
        "check_out_distance_meter": geo["distance_meter"],
        "check_out_geofence_result": geo["geofence_result"],
        "check_out_location_reason_code": payload.reason_code if outside else None,
        "check_out_location_reason": payload.reason if outside else None,
        "updated_at": now(), "updated_by": ctx.user_id,
    }
    if payload.note:
        patch["note"] = payload.note
    if outside:
        if prev_status == "pending":
            patch["location_approval_for"] = "both" if row.get("location_approval_for") == "check_in" else (
                row.get("location_approval_for") or "check_out")
        elif new_round is not None:
            patch["location_approval_status"] = "pending"
            patch["location_approval_for"] = "check_out"
            patch["location_approval_round"] = new_round
            patch["location_decided_by"] = None
            patch["location_decided_at"] = None
            patch["location_decision_notes"] = None

    updated = await db.attendances.find_one_and_update(
        {"company_id": ctx.company_id, "id": row["id"], "check_out_at": None},
        {"$set": patch}, return_document=True)
    if not updated:
        fresh = await db.attendances.find_one({"company_id": ctx.company_id, "id": row["id"]}, NO_ID)
        if fresh and payload.client_request_id and fresh.get("check_out_request_id") == payload.client_request_id:
            return _clock_response(fresh, None, "Absen Pulang sudah tercatat sebelumnya.", idempotent=True)
        raise HTTPException(status.HTTP_409_CONFLICT, "Absen Pulang sudah dicatat oleh proses lain.")

    if new_round is not None:
        await ta.submit(ctx, "attendance_location", row["id"],
                        f"Absen Pulang {employee.get('full_name')} {row['work_date']}", employee["id"],
                        approval_round=new_round)

    saved = await svc.recompute_attendance(ctx.company, updated)
    await log_action(ctx, "check_out_outside_radius" if outside else "check_out",
                     "attendance", saved["id"],
                     f"Absen Pulang {employee.get('full_name')} {row['work_date']}",
                     before=row, after=saved, module="attendance", notes=geo["message"])
    return _clock_response(
        saved, geo,
        "Absen Pulang tercatat dan MENUNGGU PERSETUJUAN LOKASI karena berada di luar radius."
        if outside and saved.get("location_approval_status") == "pending" else "Absen Pulang berhasil dicatat.")


@router.get("/me")
async def my_attendance(
    period: Optional[str] = None,
    ctx: AuthContext = Depends(_perm("view")),
):
    employee = await svc.my_employee(ctx, required=False)
    if not employee:
        return {"items": [], "total": 0, "linked": False}
    period = period or tk.period_key_of(tk.now_utc().astimezone(tk.tz_for(ctx.company)).date().isoformat())
    date_from, date_to = tk.month_bounds(period)
    db = get_db()
    rows = await db.attendances.find({
        "company_id": ctx.company_id, "employee_id": employee["id"],
        "work_date": {"$gte": date_from, "$lte": date_to}, "status": {"$ne": "deleted"},
    }, NO_ID).sort("work_date", -1).to_list(400)
    rows = serialize_list(rows)
    locations_by_id, _ = await svc.location_index(ctx.company_id)
    items = []
    for r in rows:  # data milik sendiri: koordinat tidak perlu disamarkan
        loc = locations_by_id.get(r.get("work_location_id") or "")
        item = tk.decorate_attendance(r)
        item["work_location_name"] = (loc or {}).get("name")
        item["timezone"] = str(tk.tz_for(ctx.company, loc))
        items.append(item)
    return {"linked": True, "period": period, "items": items, "total": len(items)}


# ==========================================================================
# DAFTAR & DETAIL (HR)
# ==========================================================================
async def _decorate_rows(ctx: AuthContext, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    locations_by_id, _ = await svc.location_index(ctx.company_id)
    employees_by_id, _ = await svc.employee_index(ctx.company_id)
    allowed = _can_see_gps(ctx)
    out = []
    for r in rows:
        emp = employees_by_id.get(r.get("employee_id") or "") or {}
        loc = locations_by_id.get(r.get("work_location_id") or "")
        item = tk.decorate_attendance(r)
        item["work_location_name"] = (loc or {}).get("name")
        item["timezone"] = str(tk.tz_for(ctx.company, loc))  # jam ditampilkan pada zona lokasi kerja
        item["department_id"] = emp.get("department_id")
        item["position_id"] = emp.get("position_id")
        item["project_id"] = emp.get("project_id")
        item["late_label"] = tk.minutes_to_hhmm(r.get("late_minutes"))
        item["work_minutes_label"] = tk.minutes_to_hhmm(r.get("actual_work_minutes"))
        out.append(tk.redact_gps(item, allowed))
    return out


@router.get("")
async def list_attendance(
    work_date: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    period: Optional[str] = None,
    employee_id: Optional[str] = None,
    department_id: Optional[str] = None,
    position_id: Optional[str] = None,
    project_id: Optional[str] = None,
    work_location_id: Optional[str] = None,
    attendance_status: Optional[str] = None,
    source: Optional[str] = None,
    location_approval_status: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    ctx: AuthContext = Depends(_perm("view")),
):
    db = get_db()
    query: Dict[str, Any] = {"company_id": ctx.company_id, "status": {"$ne": "deleted"}}
    scoped_employee = await svc.scope_employee_id(ctx)
    if scoped_employee:
        employee_id = scoped_employee  # karyawan self-service: hanya data dirinya sendiri
        department_id = position_id = project_id = None
    if work_date:
        query["work_date"] = tk.parse_date_str(work_date, "Tanggal")
    elif period:
        f, t = tk.month_bounds(period)
        query["work_date"] = {"$gte": f, "$lte": t}
    elif date_from and date_to:
        query["work_date"] = {"$gte": tk.parse_date_str(date_from, "Tanggal Mulai"),
                              "$lte": tk.parse_date_str(date_to, "Tanggal Selesai")}
    if employee_id:
        query["employee_id"] = employee_id
    if work_location_id:
        query["work_location_id"] = work_location_id
    if attendance_status:
        query["attendance_status"] = attendance_status
    if source:
        query["source"] = source
    if location_approval_status:
        query["location_approval_status"] = location_approval_status
    if department_id or position_id or project_id:
        emp_q: Dict[str, Any] = {"company_id": ctx.company_id}
        if department_id:
            emp_q["department_id"] = department_id
        if position_id:
            emp_q["position_id"] = position_id
        if project_id:
            emp_q["project_id"] = project_id
        emps = await db.employees.find(emp_q, NO_ID).to_list(3000)
        query["employee_id"] = {"$in": [e["id"] for e in emps] or ["-"]}

    page, limit = max(1, int(page)), min(200, max(1, int(limit)))
    total = await db.attendances.count_documents(query)
    rows = await db.attendances.find(query, NO_ID).sort(
        [("work_date", -1), ("employee_name", ASCENDING)]
    ).skip((page - 1) * limit).limit(limit).to_list(limit)
    return {"items": await _decorate_rows(ctx, serialize_list(rows)), "total": total,
            "page": page, "limit": limit, "total_pages": max(1, (total + limit - 1) // limit)}


@router.get("/dashboard")
async def dashboard(work_date: Optional[str] = None, ctx: AuthContext = Depends(_perm("view"))):
    db = get_db()
    tz = tk.tz_for(ctx.company)
    today = work_date or tk.now_utc().astimezone(tz).date().isoformat()
    today = tk.parse_date_str(today, "Tanggal")
    scope: Dict[str, Any] = {}
    scoped_employee = await svc.scope_employee_id(ctx)
    if scoped_employee:
        scope = {"employee_id": scoped_employee}

    rows = await db.attendances.find(
        {"company_id": ctx.company_id, "work_date": today, "status": {"$ne": "deleted"}, **scope}, NO_ID
    ).to_list(3000)
    schedules = await db.work_schedules.find(
        {"company_id": ctx.company_id, "work_date": today, "status": {"$ne": "deleted"}, **scope}, NO_ID
    ).to_list(3000)
    leaves = await db.leave_requests.find({
        "company_id": ctx.company_id, "request_status": "approved",
        "start_date": {"$lte": today}, "end_date": {"$gte": today}, **scope}, NO_ID).to_list(1000)

    scheduled_working = [s for s in schedules if not s.get("is_day_off")]
    with_attendance = {r["employee_id"] for r in rows if r.get("check_in_at")}
    on_leave_ids = {l["employee_id"] for l in leaves}

    counters = {
        "present_today": sum(1 for r in rows if r.get("check_in_at")),
        "late_today": sum(1 for r in rows if int(r.get("late_minutes") or 0) > 0),
        "working_now": sum(1 for r in rows if r.get("check_in_at") and not r.get("check_out_at")),
        "no_check_out": sum(1 for r in rows if r.get("attendance_status") == "no_check_out"),
        "awaiting_location_approval": sum(1 for r in rows if r.get("location_approval_status") == "pending"),
        "absent_today": max(0, len([s for s in scheduled_working
                                    if s["employee_id"] not in with_attendance
                                    and s["employee_id"] not in on_leave_ids])),
        "on_leave_today": len(on_leave_ids),
        "scheduled_today": len(scheduled_working),
    }
    leave_breakdown: Dict[str, int] = {}
    for l in leaves:
        key = tk.LEAVE_CATEGORY_TO_STATUS.get(l.get("leave_category") or "", "leave")
        leave_breakdown[key] = leave_breakdown.get(key, 0) + 1

    return {
        "work_date": today,
        "counters": counters,
        "leave_breakdown": [{"status": k, "label": tk.status_label(k), "count": v}
                            for k, v in leave_breakdown.items()],
        "today_rows": await _decorate_rows(ctx, serialize_list(rows)),
        "on_leave_rows": [
            {"employee_id": l["employee_id"], "employee_name": l.get("employee_name"),
             "leave_type_name": l.get("leave_type_name"),
             "status": tk.LEAVE_CATEGORY_TO_STATUS.get(l.get("leave_category") or "", "leave"),
             "status_label": tk.status_label(tk.LEAVE_CATEGORY_TO_STATUS.get(l.get("leave_category") or "", "leave")),
             "start_date": l.get("start_date"), "end_date": l.get("end_date")}
            for l in leaves],
    }


@router.get("/exceptions")
async def exceptions(
    period: Optional[str] = None,
    ctx: AuthContext = Depends(_perm("view")),
):
    db = get_db()
    tz = tk.tz_for(ctx.company)
    period = period or tk.period_key_of(tk.now_utc().astimezone(tz).date().isoformat())
    date_from, date_to = tk.month_bounds(period)
    span = {"$gte": date_from, "$lte": date_to}
    scope: Dict[str, Any] = {}
    scoped_employee = await svc.scope_employee_id(ctx)
    if scoped_employee:
        scope = {"employee_id": scoped_employee}

    rows = await db.attendances.find(
        {"company_id": ctx.company_id, "work_date": span, "status": {"$ne": "deleted"}, **scope}, NO_ID
    ).to_list(5000)
    schedules = await db.work_schedules.find(
        {"company_id": ctx.company_id, "work_date": span, "status": {"$ne": "deleted"}, **scope}, NO_ID
    ).to_list(9000)
    sched_keys = {(s["employee_id"], s["work_date"]) for s in schedules}
    imports = await db.time_imports.find(
        {"company_id": ctx.company_id, "import_kind": "attendance"}, NO_ID
    ).sort("imported_at", -1).to_list(50)
    leaves = await db.leave_requests.find(
        {"company_id": ctx.company_id, "request_status": "approved",
         "start_date": {"$lte": date_to}, "end_date": {"$gte": date_from}, **scope}, NO_ID).to_list(2000)
    overtimes = await db.overtime_requests.find(
        {"company_id": ctx.company_id, "work_date": span,
         "request_status": {"$in": ["pending", "approved"]}, **scope}, NO_ID).to_list(2000)

    def brief(r: Dict[str, Any], note: str) -> Dict[str, Any]:
        return {"employee_id": r.get("employee_id"), "employee_name": r.get("employee_name"),
                "work_date": r.get("work_date"), "attendance_id": r.get("id"), "note": note}

    leave_conflict = []
    for l in leaves:
        for r in rows:
            if r["employee_id"] == l["employee_id"] and l["start_date"] <= r["work_date"] <= l["end_date"] \
                    and r.get("check_in_at"):
                leave_conflict.append(brief(
                    r, f"Ada absensi nyata padahal {l.get('leave_type_name')} sudah disetujui."))

    overtime_conflict = []
    for o in overtimes:
        conflict_leave = next(
            (l for l in leaves if l["employee_id"] == o["employee_id"]
             and l["start_date"] <= o["work_date"] <= l["end_date"]
             and (l.get("day_part") or "full_day") == "full_day"), None)
        if conflict_leave:
            overtime_conflict.append({
                "employee_id": o["employee_id"], "employee_name": o.get("employee_name"),
                "work_date": o["work_date"], "overtime_id": o["id"],
                "note": f"Lembur bertabrakan dengan {conflict_leave.get('leave_type_name')} sehari penuh."})

    groups = {
        "no_check_out": [brief(r, "Absen Masuk ada, Absen Pulang belum dicatat.")
                         for r in rows if r.get("attendance_status") == "no_check_out"],
        "no_schedule": [brief(r, "Absensi tercatat tanpa jadwal kerja.")
                        for r in rows if (r["employee_id"], r["work_date"]) not in sched_keys],
        "awaiting_location_approval": [brief(r, f"Jarak {r.get('check_in_distance_meter') or 0:.0f} m dari lokasi kerja.")
                                       for r in rows if r.get("location_approval_status") == "pending"],
        "gps_problem": [brief(r, "GPS tidak tersedia atau akurasi rendah.")
                        for r in rows if r.get("check_in_geofence_result") in ("gps_unavailable", "accuracy_warning")
                        or r.get("check_out_geofence_result") in ("gps_unavailable", "accuracy_warning")],
        "duplicate": [],
        "import_employee_not_found": [
            {"batch_id": b["id"], "filename": b.get("filename"), "work_date": None,
             "note": f"{len(b.get('errors') or [])} baris gagal dikenali pada import {b.get('filename')}."}
            for b in imports if b.get("error_rows")],
        "leave_conflict": leave_conflict,
        "overtime_conflict": overtime_conflict,
    }
    return {
        "period": period,
        "groups": [{"kind": k, "label": tk.EXCEPTION_KINDS[k], "count": len(v), "items": v[:100]}
                   for k, v in groups.items()],
        "total": sum(len(v) for v in groups.values()),
    }


# ==========================================================================
# REKAP KEHADIRAN
# ==========================================================================
RECAP_COLUMNS = [
    {"key": "employee_number", "label": "Nomor Karyawan"},
    {"key": "employee_name", "label": "Nama Karyawan"},
    {"key": "department_name", "label": "Departemen"},
    {"key": "position_name", "label": "Jabatan"},
    {"key": "scheduled_days", "label": "Hari Kerja Terjadwal"},
    {"key": "present_days", "label": "Hadir"},
    {"key": "late_days", "label": "Terlambat"},
    {"key": "late_minutes", "label": "Menit Terlambat"},
    {"key": "early_leave_days", "label": "Pulang Cepat"},
    {"key": "early_leave_minutes", "label": "Menit Pulang Cepat"},
    {"key": "absent_days", "label": "Alfa"},
    {"key": "leave_days", "label": "Cuti"},
    {"key": "sick_days", "label": "Sakit"},
    {"key": "permission_days", "label": "Izin"},
    {"key": "unpaid_leave_days", "label": "Cuti Tidak Dibayar"},
    {"key": "day_off_days", "label": "OFF"},
    {"key": "holiday_days", "label": "Libur"},
    {"key": "actual_work_minutes", "label": "Jam Kerja Aktual (menit)"},
    {"key": "approved_overtime_minutes", "label": "Lembur Disetujui (menit)"},
]


async def _build_recap(ctx: AuthContext, period: str, filters: Dict[str, Optional[str]]) -> Dict[str, Any]:
    db = get_db()
    date_from, date_to = tk.month_bounds(period)
    span = {"$gte": date_from, "$lte": date_to}

    emp_q: Dict[str, Any] = {"company_id": ctx.company_id, "status": "active"}
    for field in ("department_id", "position_id", "project_id", "work_location_id"):
        if filters.get(field):
            emp_q[field] = filters[field]
    if filters.get("employee_id"):
        emp_q["id"] = filters["employee_id"]
    employees = await db.employees.find(emp_q, NO_ID).sort("full_name", ASCENDING).to_list(3000)
    emp_ids = [e["id"] for e in employees]
    if not emp_ids:
        return {"period": period, "period_label": tk.period_label_of(period),
                "columns": RECAP_COLUMNS, "items": [], "total": 0}

    attendances = await db.attendances.find(
        {"company_id": ctx.company_id, "employee_id": {"$in": emp_ids},
         "work_date": span, "status": {"$ne": "deleted"}}, NO_ID).to_list(20000)
    schedules = await db.work_schedules.find(
        {"company_id": ctx.company_id, "employee_id": {"$in": emp_ids},
         "work_date": span, "status": {"$ne": "deleted"}}, NO_ID).to_list(40000)
    leaves = await db.leave_requests.find(
        {"company_id": ctx.company_id, "employee_id": {"$in": emp_ids}, "request_status": "approved",
         "start_date": {"$lte": date_to}, "end_date": {"$gte": date_from}}, NO_ID).to_list(4000)
    overtimes = await db.overtime_requests.find(
        {"company_id": ctx.company_id, "employee_id": {"$in": emp_ids},
         "work_date": span, "request_status": "approved"}, NO_ID).to_list(4000)
    calendar = await tk.calendar_map(ctx.company_id, tk.date_range(date_from, date_to))

    dept_labels = await svc.label_map(ctx.company_id, "departments", [e.get("department_id") for e in employees])
    pos_labels = await svc.label_map(ctx.company_id, "positions", [e.get("position_id") for e in employees])

    all_dates = tk.date_range(date_from, date_to)
    items: List[Dict[str, Any]] = []
    for emp in employees:
        sched = {s["work_date"]: s for s in schedules if s["employee_id"] == emp["id"]}
        atts = {a["work_date"]: a for a in attendances if a["employee_id"] == emp["id"]}
        emp_leaves = [l for l in leaves if l["employee_id"] == emp["id"]]
        row = {
            "employee_id": emp["id"], "employee_number": emp.get("employee_number"),
            "employee_name": emp.get("full_name"),
            "department_name": dept_labels.get(emp.get("department_id") or "", "-"),
            "position_name": pos_labels.get(emp.get("position_id") or "", "-"),
            "scheduled_days": 0, "present_days": 0, "late_days": 0, "late_minutes": 0,
            "early_leave_days": 0, "early_leave_minutes": 0, "absent_days": 0,
            "leave_days": 0, "sick_days": 0, "permission_days": 0, "unpaid_leave_days": 0,
            "day_off_days": 0, "holiday_days": 0,
            "actual_work_minutes": 0, "approved_overtime_minutes": 0,
        }
        if filters.get("source"):
            atts = {d: a for d, a in atts.items() if a.get("source") == filters["source"]}
        if filters.get("attendance_status"):
            atts = {d: a for d, a in atts.items() if a.get("attendance_status") == filters["attendance_status"]}

        for d in all_dates:
            schedule = sched.get(d)
            day_type = tk.resolve_day_type(d, schedule, calendar.get(d))
            att = atts.get(d)
            leave = next((l for l in emp_leaves if l["start_date"] <= d <= l["end_date"]), None)
            if tk.is_working_day_type(day_type) and schedule and not schedule.get("is_day_off"):
                row["scheduled_days"] += 1

            if leave:
                cat = tk.LEAVE_CATEGORY_TO_STATUS.get(leave.get("leave_category") or "", "leave")
                key = {"leave": "leave_days", "sick": "sick_days", "permission": "permission_days",
                       "unpaid_leave": "unpaid_leave_days"}.get(cat, "leave_days")
                row[key] += 1
                if att:
                    row["actual_work_minutes"] += int(att.get("actual_work_minutes") or 0)
                continue
            if day_type in tk.HOLIDAY_DAY_TYPES:
                row["holiday_days"] += 1
                if att:
                    row["actual_work_minutes"] += int(att.get("actual_work_minutes") or 0)
                continue
            if day_type == "weekly_off":
                row["day_off_days"] += 1
                if att:
                    row["actual_work_minutes"] += int(att.get("actual_work_minutes") or 0)
                continue
            if not att or not att.get("check_in_at"):
                if schedule and not schedule.get("is_day_off"):
                    row["absent_days"] += 1
                continue
            if att.get("location_approval_status") == "rejected":
                row["absent_days"] += 1
                continue
            row["present_days"] += 1
            row["actual_work_minutes"] += int(att.get("actual_work_minutes") or 0)
            if int(att.get("late_minutes") or 0) > 0:
                row["late_days"] += 1
                row["late_minutes"] += int(att.get("late_minutes") or 0)
            if int(att.get("early_leave_minutes") or 0) > 0:
                row["early_leave_days"] += 1
                row["early_leave_minutes"] += int(att.get("early_leave_minutes") or 0)

        row["approved_overtime_minutes"] = sum(
            int(o.get("approved_minutes") or 0) for o in overtimes if o["employee_id"] == emp["id"])
        row["actual_work_label"] = tk.minutes_to_hhmm(row["actual_work_minutes"])
        row["approved_overtime_label"] = tk.minutes_to_hhmm(row["approved_overtime_minutes"])
        # Kesiapan Payroll (BACA SAJA - tidak mengubah Payroll/BPJS/PPh21).
        row["payroll_readiness"] = {
            "present_days": row["present_days"],
            "absent_days": row["absent_days"],
            "unpaid_leave_days": row["unpaid_leave_days"],
            "late_minutes": row["late_minutes"],
            "early_leave_minutes": row["early_leave_minutes"],
            "approved_overtime_minutes": row["approved_overtime_minutes"],
        }
        items.append(row)

    return {"period": period, "period_label": tk.period_label_of(period),
            "date_from": date_from, "date_to": date_to,
            "columns": RECAP_COLUMNS, "items": items, "total": len(items)}


@router.get("/recap")
async def recap(
    period: Optional[str] = None,
    employee_id: Optional[str] = None,
    department_id: Optional[str] = None,
    position_id: Optional[str] = None,
    project_id: Optional[str] = None,
    work_location_id: Optional[str] = None,
    attendance_status: Optional[str] = None,
    source: Optional[str] = None,
    ctx: AuthContext = Depends(_perm("view")),
):
    tz = tk.tz_for(ctx.company)
    period = period or tk.period_key_of(tk.now_utc().astimezone(tz).date().isoformat())
    scoped_employee = await svc.scope_employee_id(ctx)
    if scoped_employee:
        employee_id, department_id, position_id, project_id = scoped_employee, None, None, None
    return await _build_recap(ctx, period, {
        "employee_id": employee_id, "department_id": department_id, "position_id": position_id,
        "project_id": project_id, "work_location_id": work_location_id,
        "attendance_status": attendance_status, "source": source})


@router.get("/recap/export")
async def export_recap(
    period: Optional[str] = None,
    employee_id: Optional[str] = None,
    department_id: Optional[str] = None,
    position_id: Optional[str] = None,
    project_id: Optional[str] = None,
    work_location_id: Optional[str] = None,
    attendance_status: Optional[str] = None,
    source: Optional[str] = None,
    ctx: AuthContext = Depends(_perm("export")),
):
    tz = tk.tz_for(ctx.company)
    period = period or tk.period_key_of(tk.now_utc().astimezone(tz).date().isoformat())
    data = await _build_recap(ctx, period, {
        "employee_id": employee_id, "department_id": department_id, "position_id": position_id,
        "project_id": project_id, "work_location_id": work_location_id,
        "attendance_status": attendance_status, "source": source})
    blob = tx.export_sheet(
        "Rekap Kehadiran", RECAP_COLUMNS, data["items"],
        meta=[("Perusahaan", ctx.company.get("name")), ("Periode", data["period_label"]),
              ("Jumlah Karyawan", str(data["total"]))])
    await log_action(ctx, "export", "attendance", None, f"Ekspor Rekap Kehadiran {data['period_label']}",
                     module="attendance")
    return Response(content=blob,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition":
                             f'attachment; filename="Rekap-Kehadiran-{period}.xlsx"'})


# ==========================================================================
# ABSENSI MANUAL & KOREKSI HR
# ==========================================================================
class ManualAttendanceInput(BaseModel):
    employee_id: str
    work_date: str
    check_in_at: Optional[str] = None
    check_out_at: Optional[str] = None
    reason: str = Field(..., min_length=3)
    note: Optional[str] = None


def _parse_dt_local(value: Optional[str], tz, label: str):
    if not value:
        return None
    from datetime import datetime as _dt
    text = str(value).strip().replace("T", " ")[:16]
    try:
        naive = _dt.strptime(text, "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"{label} harus berformat YYYY-MM-DD HH:MM.")
    return tk.to_utc(naive.replace(tzinfo=tz))


@router.post("/manual", status_code=status.HTTP_201_CREATED)
async def manual_attendance(payload: ManualAttendanceInput, ctx: AuthContext = Depends(_perm("create"))):
    svc.require_hr_scope(ctx)
    work_date = tk.parse_date_str(payload.work_date, "Tanggal")
    await tk.assert_period_open(ctx.company_id, work_date)
    employee = await svc.get_employee(ctx.company_id, payload.employee_id)
    context = await svc.resolve_context(ctx.company, employee, work_date)
    tz = context["tz"]
    check_in = _parse_dt_local(payload.check_in_at, tz, "Jam Masuk")
    check_out = _parse_dt_local(payload.check_out_at, tz, "Jam Pulang")
    if check_out and not check_in:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Jam Pulang tidak boleh diisi tanpa Jam Masuk.")
    if check_in and check_out and check_out <= check_in:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Jam Pulang harus lebih akhir dari Jam Masuk.")

    db = get_db()
    shift = context.get("shift") or {}
    loc = context.get("work_location") or {}
    existing = await db.attendances.find_one(
        {"company_id": ctx.company_id, "employee_id": employee["id"], "work_date": work_date}, NO_ID)
    base = {
        "schedule_id": (context.get("schedule") or {}).get("id"),
        "shift_id": shift.get("id"), "shift_code": shift.get("code"), "shift_name": shift.get("name"),
        "work_location_id": loc.get("id"), "day_type": context["day_type"],
        "is_day_off": bool((context.get("schedule") or {}).get("is_day_off")),
        "check_in_at": check_in, "check_out_at": check_out,
        "check_in_source": "manual" if check_in else None,
        "check_out_source": "manual" if check_out else None,
        "source": "manual", "note": payload.note,
        "manual_reason": payload.reason, "correction_reason": payload.reason,
        "corrected_by": ctx.user_id, "corrected_at": now(),
        "location_approval_status": "not_required",
        "period_key": tk.period_key_of(work_date),
    }
    if existing:
        await db.attendances.update_one(
            {"company_id": ctx.company_id, "id": existing["id"]},
            {"$set": {**base, "updated_at": now(), "updated_by": ctx.user_id}})
        row = await db.attendances.find_one({"company_id": ctx.company_id, "id": existing["id"]}, NO_ID)
        action = "attendance_manual_update"
    else:
        row = {
            "id": new_id(), "company_id": ctx.company_id, "status": "active",
            "employee_id": employee["id"], "employee_number": employee.get("employee_number"),
            "employee_name": employee.get("full_name"), "work_date": work_date,
            **base, **audit_fields(ctx.user_id)}
        await db.attendances.insert_one(dict(row))
        action = "attendance_manual_create"

    saved = await svc.recompute_attendance(ctx.company, row)
    await log_action(ctx, action, "attendance", saved["id"],
                     f"Absensi manual {employee.get('full_name')} {work_date}",
                     before=existing, after=saved, module="attendance", notes=payload.reason)
    return {"attendance": tk.decorate_attendance(saved),
            "message": "Absensi manual berhasil disimpan beserta alasan dan jejak audit."}


# ==========================================================================
# KOREKSI ABSENSI (pengajuan karyawan)
# ==========================================================================
class CorrectionInput(BaseModel):
    work_date: str
    correction_type: str
    proposed_check_in_at: Optional[str] = None
    proposed_check_out_at: Optional[str] = None
    reason: str = Field(..., min_length=3)
    document_id: Optional[str] = None


@router.post("/corrections", status_code=status.HTTP_201_CREATED)
async def create_correction(payload: CorrectionInput, ctx: AuthContext = Depends(_perm("create"))):
    if payload.correction_type not in tk.CORRECTION_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Jenis koreksi tidak dikenal.")
    work_date = tk.parse_date_str(payload.work_date, "Tanggal")
    await tk.assert_period_open(ctx.company_id, work_date)
    employee = await svc.my_employee(ctx)
    context = await svc.resolve_context(ctx.company, employee, work_date)
    tz = context["tz"]
    proposed_in = _parse_dt_local(payload.proposed_check_in_at, tz, "Usulan Jam Masuk")
    proposed_out = _parse_dt_local(payload.proposed_check_out_at, tz, "Usulan Jam Pulang")
    if not proposed_in and not proposed_out:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Isi minimal salah satu usulan jam (masuk atau pulang).")
    if proposed_in and proposed_out and proposed_out <= proposed_in:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Usulan Jam Pulang harus lebih akhir dari Usulan Jam Masuk.")

    db = get_db()
    overlap = await db.attendance_corrections.count_documents({
        "company_id": ctx.company_id, "employee_id": employee["id"],
        "work_date": work_date, "request_status": "pending"})
    if overlap:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Masih ada pengajuan koreksi yang menunggu persetujuan untuk tanggal ini.")

    att = await db.attendances.find_one({
        "company_id": ctx.company_id, "employee_id": employee["id"],
        "work_date": work_date, "status": {"$ne": "deleted"}}, NO_ID)

    repo = TenantRepository("attendance_corrections", ctx.company_id)
    created = await repo.create({
        "employee_id": employee["id"], "employee_name": employee.get("full_name"),
        "attendance_id": (att or {}).get("id"), "work_date": work_date,
        "period_key": tk.period_key_of(work_date), "correction_type": payload.correction_type,
        "current_check_in_at": (att or {}).get("check_in_at"),
        "current_check_out_at": (att or {}).get("check_out_at"),
        "proposed_check_in_at": proposed_in, "proposed_check_out_at": proposed_out,
        "reason": payload.reason, "document_id": payload.document_id,
        "request_status": "pending", "submitted_by": ctx.user_id, "submitted_at": now(),
        "before_value": {"check_in_at": str((att or {}).get("check_in_at") or ""),
                         "check_out_at": str((att or {}).get("check_out_at") or "")},
    }, ctx.user_id)

    await ta.submit(ctx, "attendance_correction", created["id"],
                    f"Koreksi Absensi {employee.get('full_name')} {work_date}", employee["id"])
    await log_action(ctx, "correction_submit", "attendance", created["id"],
                     f"Pengajuan Koreksi Absensi {work_date}", after=created,
                     module="attendance", notes=payload.reason)
    return {"correction": created, "message": "Pengajuan koreksi terkirim dan menunggu persetujuan."}


@router.get("/corrections")
async def list_corrections(
    request_status: Optional[str] = None,
    mine: bool = False,
    ctx: AuthContext = Depends(_perm("view")),
):
    db = get_db()
    query: Dict[str, Any] = {"company_id": ctx.company_id, "status": {"$ne": "deleted"}}
    if request_status:
        query["request_status"] = request_status
    scoped_employee = await svc.scope_employee_id(ctx)
    if mine or scoped_employee:
        employee = await svc.my_employee(ctx, required=False)
        query["employee_id"] = employee["id"] if employee else "-"
    rows = await db.attendance_corrections.find(query, NO_ID).sort("submitted_at", -1).to_list(500)
    out = []
    for r in serialize_list(rows):
        state = await ta.state_for(ctx, "attendance_correction", r["id"])
        out.append({
            **r,
            "correction_type_label": tk.CORRECTION_TYPES.get(r.get("correction_type") or "", "-"),
            "request_status_label": tk.REQUEST_STATUSES.get(r.get("request_status") or "", {}).get("label", "-"),
            "request_status_tone": tk.REQUEST_STATUSES.get(r.get("request_status") or "", {}).get("tone", "neutral"),
            "approval": state,
        })
    return {"items": out, "total": len(out)}


# ==========================================================================
# PERSETUJUAN (lokasi & koreksi) - memakai lapisan approval bersama
# ==========================================================================
@router.get("/approvals")
async def list_approvals(
    document_kind: Optional[str] = None,
    ctx: AuthContext = Depends(_perm("view")),
):
    kinds = [document_kind] if document_kind else ["attendance_location", "attendance_correction"]
    rows = await ta.pending_for_me(ctx, kinds)
    db = get_db()
    items = []
    allowed = _can_see_gps(ctx)
    for row in rows:
        detail: Dict[str, Any] = {}
        if row["document_kind"] == "attendance_location":
            att = await db.attendances.find_one(
                {"company_id": ctx.company_id, "id": row["record_id"]}, NO_ID)
            if att:
                loc = await db.work_locations.find_one(
                    {"company_id": ctx.company_id, "id": att.get("work_location_id")}, NO_ID) or {}
                approval_for = att.get("location_approval_for") or "check_in"
                # Peristiwa yang sedang dimintakan persetujuan pada putaran ini.
                if int(row.get("approval_round") or 1) > 1 and approval_for == "both":
                    approval_for = "check_out"

                def _map(lat, lng):
                    return (f"https://www.google.com/maps?q={lat},{lng}"
                            if allowed and lat is not None and lng is not None else None)

                detail = tk.redact_gps({
                    **tk.decorate_attendance(att),
                    "work_location_name": loc.get("name"),
                    "work_location_address": loc.get("address"),
                    "timezone": str(tk.tz_for(ctx.company, loc or None)),
                    "work_location_latitude": loc.get("latitude") if allowed else None,
                    "work_location_longitude": loc.get("longitude") if allowed else None,
                    "approval_for": approval_for,
                    "approval_for_label": tk.LOCATION_APPROVAL_FOR.get(approval_for, "Absen Masuk"),
                    "check_in_map_url": _map(att.get("check_in_latitude"), att.get("check_in_longitude")),
                    "check_out_map_url": _map(att.get("check_out_latitude"), att.get("check_out_longitude")),
                    # kompatibilitas: map_url = titik peristiwa yang dimintakan persetujuan
                    "map_url": (_map(att.get("check_out_latitude"), att.get("check_out_longitude"))
                                if approval_for == "check_out"
                                else _map(att.get("check_in_latitude"), att.get("check_in_longitude"))),
                }, allowed)
        else:
            corr = await db.attendance_corrections.find_one(
                {"company_id": ctx.company_id, "id": row["record_id"]}, NO_ID)
            if corr:
                detail = {**corr,
                          "correction_type_label": tk.CORRECTION_TYPES.get(corr.get("correction_type") or "", "-")}
        items.append({
            "approval": {**row,
                         "document_label": ta.DOCUMENT_KINDS[row["document_kind"]]["label"]},
            "detail": detail,
        })
    return {"items": items, "total": len(items)}


class DecisionInput(BaseModel):
    decision: str
    notes: Optional[str] = None


async def _apply_correction(ctx: AuthContext, correction: Dict[str, Any]) -> Dict[str, Any]:
    db = get_db()
    employee = await svc.get_employee(ctx.company_id, correction["employee_id"])
    work_date = correction["work_date"]
    context = await svc.resolve_context(ctx.company, employee, work_date)
    shift = context.get("shift") or {}
    loc = context.get("work_location") or {}
    att = await db.attendances.find_one(
        {"company_id": ctx.company_id, "employee_id": employee["id"], "work_date": work_date}, NO_ID)
    patch = {
        "check_in_at": correction.get("proposed_check_in_at") or (att or {}).get("check_in_at"),
        "check_out_at": correction.get("proposed_check_out_at") or (att or {}).get("check_out_at"),
        "correction_reason": correction.get("reason"),
        "corrected_by": ctx.user_id, "corrected_at": now(),
    }
    if att:
        await db.attendances.update_one(
            {"company_id": ctx.company_id, "id": att["id"]},
            {"$set": {**patch, "updated_at": now(), "updated_by": ctx.user_id}})
        row = await db.attendances.find_one({"company_id": ctx.company_id, "id": att["id"]}, NO_ID)
    else:
        row = {
            "id": new_id(), "company_id": ctx.company_id, "status": "active",
            "employee_id": employee["id"], "employee_number": employee.get("employee_number"),
            "employee_name": employee.get("full_name"), "work_date": work_date,
            "period_key": tk.period_key_of(work_date),
            "schedule_id": (context.get("schedule") or {}).get("id"),
            "shift_id": shift.get("id"), "shift_code": shift.get("code"), "shift_name": shift.get("name"),
            "work_location_id": loc.get("id"), "day_type": context["day_type"],
            "source": "manual", "check_in_source": "manual", "check_out_source": "manual",
            "location_approval_status": "not_required", **patch, **audit_fields(ctx.user_id)}
        await db.attendances.insert_one(dict(row))
    saved = await svc.recompute_attendance(ctx.company, row)
    await db.attendance_corrections.update_one(
        {"company_id": ctx.company_id, "id": correction["id"]},
        {"$set": {"applied_at": now(), "attendance_id": saved["id"],
                  "after_value": {"check_in_at": str(saved.get("check_in_at") or ""),
                                  "check_out_at": str(saved.get("check_out_at") or "")},
                  "updated_at": now(), "updated_by": ctx.user_id}})
    return saved


@router.post("/approvals/{approval_id}/decide")
async def decide_approval(approval_id: str, payload: DecisionInput,
                          ctx: AuthContext = Depends(_perm("view"))):
    """Keputusan persetujuan Absensi.

    Otorisasi: pengguna harus penyetuju tahap aktif sesuai Konfigurasi Alur
    Persetujuan (``ta.decide`` -> ``is_step_approver``), ATAU memegang
    ``attendance:approve``. Tanpa ini, tahap yang penyetujunya role HR Admin
    (tanpa ``attendance:approve``) tidak akan pernah bisa diputuskan.
    """
    db = get_db()
    row = await TenantRepository("time_approvals", ctx.company_id).get(approval_id)
    if not ctx.has_permission("attendance", "approve") and not await ta.is_step_approver(ctx, row):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Anda bukan penyetuju tahap ini dan tidak memiliki hak persetujuan Absensi.")
    if row["document_kind"] not in ("attendance_location", "attendance_correction"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Gunakan menu persetujuan yang sesuai untuk jenis dokumen ini.")
    result = await ta.decide(ctx, approval_id, payload.decision, payload.notes)
    overall = result["state"]["overall"]

    if row["document_kind"] == "attendance_location" and overall in ("approved", "rejected"):
        att = await db.attendances.find_one({"company_id": ctx.company_id, "id": row["record_id"]}, NO_ID)
        if att:
            await tk.assert_period_open(ctx.company_id, att["work_date"])
            await db.attendances.update_one(
                {"company_id": ctx.company_id, "id": att["id"]},
                {"$set": {"location_approval_status": overall,
                          "location_decided_by": ctx.user_id, "location_decided_at": now(),
                          "location_decision_notes": payload.notes,
                          "updated_at": now(), "updated_by": ctx.user_id}})
            fresh = await db.attendances.find_one({"company_id": ctx.company_id, "id": att["id"]}, NO_ID)
            await svc.recompute_attendance(ctx.company, fresh)
            await log_action(ctx, f"geofence_{overall}", "attendance", att["id"],
                             f"Persetujuan Lokasi {att.get('employee_name')} {att.get('work_date')}",
                             before=att, after=fresh, module="attendance", notes=payload.notes)

    if row["document_kind"] == "attendance_correction" and overall in ("approved", "rejected"):
        corr = await db.attendance_corrections.find_one(
            {"company_id": ctx.company_id, "id": row["record_id"]}, NO_ID)
        if corr:
            await tk.assert_period_open(ctx.company_id, corr["work_date"])
            await db.attendance_corrections.update_one(
                {"company_id": ctx.company_id, "id": corr["id"]},
                {"$set": {"request_status": overall, "decided_by": ctx.user_id,
                          "decided_at": now(), "decision_notes": payload.notes,
                          "updated_at": now(), "updated_by": ctx.user_id}})
            if overall == "approved":
                await _apply_correction(ctx, corr)
            after = await db.attendance_corrections.find_one(
                {"company_id": ctx.company_id, "id": corr["id"]}, NO_ID)
            await log_action(ctx, f"correction_{overall}", "attendance", corr["id"],
                             f"Koreksi Absensi {corr.get('employee_name')} {corr.get('work_date')}",
                             before=corr, after=after, module="attendance", notes=payload.notes)

    return {"state": result["state"],
            "message": ("Disetujui." if payload.decision == "approved" else "Ditolak.")}


# ==========================================================================
# IMPORT ABSENSI EXCEL
# ==========================================================================
@router.get("/imports/template")
async def attendance_template(ctx: AuthContext = Depends(_perm("create"))):
    svc.require_hr_scope(ctx)
    _, shifts_by_code = await svc.shift_index(ctx.company_id)
    data = tx.build_attendance_template(sorted(shifts_by_code.keys()))
    return Response(content=data,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="Template-Import-Absensi.xlsx"'})


@router.post("/imports/analyze")
async def analyze_attendance_file(file: UploadFile = File(...), ctx: AuthContext = Depends(_perm("create"))):
    svc.require_hr_scope(ctx)
    headers, rows = tx.read_rows(await file.read())
    return {
        "filename": file.filename, "headers": headers, "total_rows": len(rows),
        "sample_rows": rows[:10],
        "suggested_mapping": tx.guess_mapping(headers, tx.ATTENDANCE_FIELD_ALIASES),
        "fields": [{"key": k, "label": v, "required": k in tx.ATTENDANCE_REQUIRED_FIELDS}
                   for k, v in tx.ATTENDANCE_FIELD_LABELS.items()],
    }


async def _validate_attendance_rows(ctx: AuthContext, rows: List[Dict[str, Any]],
                                    mapping: Dict[str, str], overwrite: bool) -> Dict[str, Any]:
    db = get_db()
    _, employees_by_number = await svc.employee_index(ctx.company_id)
    _, shifts_by_code = await svc.shift_index(ctx.company_id)
    tz = tk.tz_for(ctx.company)

    seen = set()
    prepared: List[Dict[str, Any]] = []
    for row in rows:
        errors: List[str] = []

        def get(field: str):
            column = mapping.get(field)
            return row.get(column) if column else None

        number = str(get("employee_number") or "").strip().upper()
        emp = employees_by_number.get(number)
        if not number:
            errors.append("Nomor Karyawan / NIK kosong.")
        elif not emp:
            errors.append(f"Karyawan dengan nomor '{number}' tidak ditemukan pada perusahaan aktif.")
        elif emp.get("status") != "active":
            errors.append(f"Karyawan '{emp.get('full_name')}' tidak berstatus aktif.")

        work_date = None
        raw_date = str(get("work_date") or "").strip()[:10]
        if not raw_date:
            errors.append("Tanggal kosong.")
        else:
            try:
                work_date = tk.parse_date_str(raw_date, "Tanggal")
            except HTTPException as exc:
                errors.append(str(exc.detail))

        time_in = time_out = None
        for field, label, target in (("check_in", "Jam Masuk", "in"), ("check_out", "Jam Pulang", "out")):
            raw = str(get(field) or "").strip()
            if not raw:
                continue
            raw = raw[-8:] if len(raw) > 8 and ":" in raw else raw
            if " " in raw:
                raw = raw.split(" ")[-1]
            try:
                parsed = tk.parse_time_str(raw[:5], label)
            except HTTPException as exc:
                errors.append(str(exc.detail))
                continue
            if target == "in":
                time_in = parsed
            else:
                time_out = parsed
        if not time_in and not time_out:
            errors.append("Jam Masuk dan Jam Pulang kosong; minimal salah satu wajib diisi.")

        shift_code = str(get("shift_code") or "").strip().upper()
        shift = shifts_by_code.get(shift_code) if shift_code else None
        if shift_code and not shift:
            errors.append(f"Kode Shift '{shift_code}' tidak ditemukan.")

        duplicate_in_file = False
        if emp and work_date:
            key = (emp["id"], work_date)
            if key in seen:
                duplicate_in_file = True
                errors.append("Baris duplikat di dalam berkas (karyawan & tanggal sama).")
            seen.add(key)

        existing = None
        schedule = None
        if emp and work_date and not errors:
            existing = await db.attendances.find_one(
                {"company_id": ctx.company_id, "employee_id": emp["id"], "work_date": work_date}, NO_ID)
            schedule = await svc.schedule_for(ctx.company_id, emp["id"], work_date)
            if not shift and schedule and schedule.get("shift_id"):
                shift = await db.work_shifts.find_one(
                    {"company_id": ctx.company_id, "id": schedule["shift_id"]}, NO_ID)
            closed = await tk.closed_period_keys(ctx.company_id, [tk.period_key_of(work_date)])
            if closed:
                errors.append(f"Periode {tk.period_label_of(closed[0])} sudah ditutup.")

        overnight = bool(shift and tk.shift_is_overnight(shift))
        if time_in and time_out and not overnight:
            if tk.time_to_minutes(time_out) <= tk.time_to_minutes(time_in):
                errors.append("Jam Pulang lebih awal dari Jam Masuk padahal shift bukan lintas hari.")

        action = "error" if errors else (("update" if overwrite else "skip") if existing else "create")
        prepared.append({
            "row": row.get("__row__"), "employee_number": number,
            "employee_name": (emp or {}).get("full_name") or str(get("employee_name") or ""),
            "employee_id": (emp or {}).get("id"), "work_date": work_date,
            "check_in": time_in, "check_out": time_out,
            "shift_code": (shift or {}).get("code"), "shift_id": (shift or {}).get("id"),
            "is_overnight": overnight, "schedule_id": (schedule or {}).get("id"),
            "work_location_id": (schedule or {}).get("work_location_id") or (emp or {}).get("work_location_id"),
            "note": get("note"), "duplicate_in_file": duplicate_in_file,
            "existing": bool(existing), "action": action, "errors": errors,
        })

    summary = {
        "total_rows": len(prepared),
        "create_rows": sum(1 for r in prepared if r["action"] == "create"),
        "update_rows": sum(1 for r in prepared if r["action"] == "update"),
        "skipped_rows": sum(1 for r in prepared if r["action"] == "skip"),
        "error_rows": sum(1 for r in prepared if r["action"] == "error"),
    }
    return {"rows": prepared, "summary": summary}


def _mapping_from_form(raw: str) -> Dict[str, str]:
    try:
        mapping = json.loads(raw)
    except Exception:  # noqa: BLE001
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pemetaan kolom tidak valid.")
    for field in tx.ATTENDANCE_REQUIRED_FIELDS:
        if not mapping.get(field):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"Kolom '{tx.ATTENDANCE_FIELD_LABELS[field]}' wajib dipetakan.")
    return mapping


@router.post("/imports/preview")
async def preview_attendance_import(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    overwrite_existing: bool = Form(False),
    ctx: AuthContext = Depends(_perm("create")),
):
    svc.require_hr_scope(ctx)
    if overwrite_existing and not ctx.has_permission("attendance", "edit"):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Anda tidak memiliki hak untuk memperbarui absensi yang sudah ada.")
    mapping_dict = _mapping_from_form(mapping)
    _, rows = tx.read_rows(await file.read())
    result = await _validate_attendance_rows(ctx, rows, mapping_dict, overwrite_existing)
    return {"filename": file.filename, **result}


@router.post("/imports/commit")
async def commit_attendance_import(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    overwrite_existing: bool = Form(False),
    ctx: AuthContext = Depends(_perm("create")),
):
    svc.require_hr_scope(ctx)
    if overwrite_existing and not ctx.has_permission("attendance", "edit"):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Anda tidak memiliki hak untuk memperbarui absensi yang sudah ada.")
    mapping_dict = _mapping_from_form(mapping)
    _, rows = tx.read_rows(await file.read())
    result = await _validate_attendance_rows(ctx, rows, mapping_dict, overwrite_existing)

    db = get_db()
    tz = tk.tz_for(ctx.company)
    batch_id = new_id()
    created = updated = 0
    for r in result["rows"]:
        if r["action"] not in ("create", "update"):
            continue
        check_in = _parse_dt_local(f"{r['work_date']} {r['check_in']}", tz, "Jam Masuk") if r["check_in"] else None
        check_out = None
        if r["check_out"]:
            out_date = r["work_date"]
            if r["is_overnight"] or (r["check_in"] and tk.time_to_minutes(r["check_out"]) <= tk.time_to_minutes(r["check_in"])):
                from datetime import date as _d, timedelta as _td
                out_date = (_d.fromisoformat(r["work_date"]) + _td(days=1)).isoformat()
            check_out = _parse_dt_local(f"{out_date} {r['check_out']}", tz, "Jam Pulang")

        payload = {
            "schedule_id": r["schedule_id"], "shift_id": r["shift_id"], "shift_code": r["shift_code"],
            "work_location_id": r["work_location_id"], "check_in_at": check_in, "check_out_at": check_out,
            "check_in_source": "excel_import" if check_in else None,
            "check_out_source": "excel_import" if check_out else None,
            "source": "excel_import", "import_batch_id": batch_id, "note": r["note"],
            "location_approval_status": "not_required",
            "period_key": tk.period_key_of(r["work_date"]),
        }
        if r["action"] == "create":
            doc = {"id": new_id(), "company_id": ctx.company_id, "status": "active",
                   "employee_id": r["employee_id"], "employee_number": r["employee_number"],
                   "employee_name": r["employee_name"], "work_date": r["work_date"],
                   **payload, **audit_fields(ctx.user_id)}
            await db.attendances.insert_one(dict(doc))
            await svc.recompute_attendance(ctx.company, doc)
            created += 1
        else:
            before = await db.attendances.find_one(
                {"company_id": ctx.company_id, "employee_id": r["employee_id"],
                 "work_date": r["work_date"]}, NO_ID)
            await db.attendances.update_one(
                {"company_id": ctx.company_id, "id": before["id"]},
                {"$set": {**payload, "correction_reason": "Diperbarui melalui Import Absensi",
                          "corrected_by": ctx.user_id, "corrected_at": now(),
                          "updated_at": now(), "updated_by": ctx.user_id}})
            fresh = await db.attendances.find_one({"company_id": ctx.company_id, "id": before["id"]}, NO_ID)
            await svc.recompute_attendance(ctx.company, fresh)
            await log_action(ctx, "attendance_import_update", "attendance", before["id"],
                             f"Perbarui absensi {r['employee_name']} {r['work_date']}",
                             before=before, after=fresh, module="attendance",
                             notes="Diperbarui melalui Import Absensi")
            updated += 1

    batch = {
        "id": batch_id, "company_id": ctx.company_id, "status": "active",
        "import_kind": "attendance", "filename": file.filename, "mapping": mapping_dict,
        "options": {"overwrite_existing": bool(overwrite_existing)},
        "total_rows": result["summary"]["total_rows"], "success_rows": created,
        "updated_rows": updated, "error_rows": result["summary"]["error_rows"],
        "skipped_rows": result["summary"]["skipped_rows"],
        "errors": [{"row": r["row"], "employee_number": r["employee_number"], "errors": r["errors"]}
                   for r in result["rows"] if r["action"] == "error"][:500],
        "imported_by": ctx.user_id, "imported_by_name": ctx.user.get("full_name"),
        "imported_at": now(),
        "period_keys": sorted({tk.period_key_of(r["work_date"]) for r in result["rows"] if r.get("work_date")}),
        **audit_fields(ctx.user_id),
    }
    await db.time_imports.insert_one(dict(batch))
    await log_action(ctx, "import", "attendance", batch_id,
                     f"Import Absensi: {file.filename}", after=batch, module="attendance")
    return {"batch_id": batch_id,
            "summary": {**result["summary"], "created_rows": created, "updated_rows": updated},
            "errors": batch["errors"],
            "message": (f"Import absensi selesai: {created} dibuat, {updated} diperbarui, "
                        f"{result['summary']['skipped_rows']} dilewati, "
                        f"{result['summary']['error_rows']} gagal.")}


@router.get("/imports")
async def list_attendance_imports(ctx: AuthContext = Depends(_perm("view"))):
    svc.require_hr_scope(ctx)
    db = get_db()
    rows = await db.time_imports.find(
        {"company_id": ctx.company_id, "import_kind": "attendance"}, NO_ID
    ).sort("imported_at", -1).to_list(100)
    return {"items": serialize_list(rows), "total": len(rows)}


@router.get("/{attendance_id}")
async def get_attendance(attendance_id: str, ctx: AuthContext = Depends(_perm("view"))):
    row = await TenantRepository("attendances", ctx.company_id).get(attendance_id)
    scoped_employee = await svc.scope_employee_id(ctx)
    if scoped_employee and row.get("employee_id") != scoped_employee:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Data absensi tidak ditemukan.")
    decorated = (await _decorate_rows(ctx, [row]))[0]
    return {"attendance": decorated,
            "approval": await ta.state_for(ctx, "attendance_location", attendance_id)}
