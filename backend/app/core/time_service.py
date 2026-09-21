"""Layanan domain bersama Time Management (di atas ``timekeeping``).

Dipakai lintas router: resolusi karyawan dari pengguna login, resolusi jadwal,
perhitungan ulang satu baris absensi, buku besar saldo cuti, perhitungan hari
kerja untuk cuti, dan perhitungan lembur aktual.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException, status

from .db import NO_ID, audit_fields, get_db, new_id, now
from . import timekeeping as tk


# --------------------------------------------------------------------------
# Karyawan <-> Pengguna (REUSE mapping existing employees.user_id)
# --------------------------------------------------------------------------
async def my_employee(ctx, required: bool = True) -> Optional[Dict[str, Any]]:
    db = get_db()
    emp = await db.employees.find_one(
        {"company_id": ctx.company_id, "user_id": ctx.user_id, "status": {"$ne": "deleted"}}, NO_ID
    )
    if not emp and required:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Akun Anda belum terhubung ke data karyawan pada perusahaan aktif. "
            "Hubungi HR untuk menghubungkan akun pengguna dengan Data Karyawan.",
        )
    if emp and emp.get("status") != "active" and required:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Data karyawan Anda tidak berstatus aktif, sehingga absensi mandiri tidak dapat dilakukan.",
        )
    return emp


# --------------------------------------------------------------------------
# Ruang lingkup data Absensi (REUSE matrix RBAC existing, tanpa permission baru)
# --------------------------------------------------------------------------
ATTENDANCE_ADMIN_ACTIONS = ("edit", "delete", "export", "approve")


def self_service_only(ctx) -> bool:
    """True bila pengguna hanya memegang hak self-service Absensi (view + create).

    Karyawan biasa memegang ``attendance:view`` dan ``attendance:create`` untuk
    absen mandiri; tanpa salah satu hak lanjutan (edit/delete/export/approve)
    ruang lingkup datanya dibatasi ke karyawan dirinya sendiri.
    """
    if getattr(ctx, "is_super_admin", False):
        return False
    return not any(ctx.has_permission("attendance", a) for a in ATTENDANCE_ADMIN_ACTIONS)


async def scope_employee_id(ctx) -> Optional[str]:
    """Kembalikan employee_id yang WAJIB dipakai sebagai filter untuk pengguna
    self-service; ``None`` bila pengguna berhak melihat data seluruh perusahaan.
    Pengguna self-service yang belum tertaut ke Data Karyawan mendapat filter
    kosong ("-") agar tidak ada baris yang bocor."""
    if not self_service_only(ctx):
        return None
    emp = await my_employee(ctx, required=False)
    return emp["id"] if emp else "-"


def require_hr_scope(ctx) -> None:
    """Tolak tindakan administratif Absensi (jadwal massal, input manual, impor,
    master shift) untuk pengguna yang hanya memegang hak self-service."""
    if self_service_only(ctx):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Tindakan ini hanya untuk HR/atasan dengan hak kelola Absensi. "
            "Akun Anda hanya dapat melakukan absensi mandiri.",
        )


async def get_employee(company_id: str, employee_id: str) -> Dict[str, Any]:
    db = get_db()
    emp = await db.employees.find_one(
        {"company_id": company_id, "id": employee_id, "status": {"$ne": "deleted"}}, NO_ID
    )
    if not emp:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Karyawan tidak ditemukan pada perusahaan aktif Anda.")
    return emp


async def employee_index(company_id: str) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """(indeks berdasarkan id, indeks berdasarkan nomor karyawan/NIK huruf besar)."""
    db = get_db()
    rows = await db.employees.find(
        {"company_id": company_id, "status": {"$ne": "deleted"}}, NO_ID
    ).to_list(5000)
    by_id = {r["id"]: r for r in rows}
    by_number: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        for key in (r.get("employee_number"), r.get("nik")):
            if key:
                by_number.setdefault(str(key).strip().upper(), r)
    return by_id, by_number


async def label_map(company_id: str, collection: str, ids: Iterable[str]) -> Dict[str, str]:
    ids = sorted({i for i in ids if i})
    if not ids:
        return {}
    db = get_db()
    rows = await db[collection].find({"company_id": company_id, "id": {"$in": ids}}, NO_ID).to_list(2000)
    return {r["id"]: (r.get("name") or r.get("code") or "-") for r in rows}


# --------------------------------------------------------------------------
# Jadwal, shift, lokasi kerja
# --------------------------------------------------------------------------
async def schedule_for(company_id: str, employee_id: str, work_date: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    return await db.work_schedules.find_one(
        {"company_id": company_id, "employee_id": employee_id, "work_date": work_date,
         "status": {"$ne": "deleted"}}, NO_ID
    )


async def shift_index(company_id: str) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    db = get_db()
    rows = await db.work_shifts.find(
        {"company_id": company_id, "status": {"$ne": "deleted"}}, NO_ID
    ).to_list(200)
    return {r["id"]: r for r in rows}, {str(r.get("code") or "").upper(): r for r in rows}


async def location_index(company_id: str) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    db = get_db()
    rows = await db.work_locations.find(
        {"company_id": company_id, "status": {"$ne": "deleted"}}, NO_ID
    ).to_list(500)
    return {r["id"]: r for r in rows}, {str(r.get("code") or "").upper(): r for r in rows}


async def resolve_context(company: Dict[str, Any], employee: Dict[str, Any], work_date: str) -> Dict[str, Any]:
    """Konteks bersama satu hari kerja: jadwal + shift + lokasi kerja + jenis hari."""
    company_id = company["id"]
    db = get_db()
    schedule = await schedule_for(company_id, employee["id"], work_date)
    shift = None
    if schedule and schedule.get("shift_id"):
        shift = await db.work_shifts.find_one({"company_id": company_id, "id": schedule["shift_id"]}, NO_ID)
    location_id = (schedule or {}).get("work_location_id") or employee.get("work_location_id")
    location = None
    if location_id:
        location = await db.work_locations.find_one({"company_id": company_id, "id": location_id}, NO_ID)
    cal = await tk.calendar_map(company_id, [work_date])
    day_type = tk.resolve_day_type(work_date, schedule, cal.get(work_date))
    return {
        "schedule": schedule, "shift": shift, "work_location": location,
        "calendar_day": cal.get(work_date), "day_type": day_type,
        "tz": tk.tz_for(company, location),
    }


# --------------------------------------------------------------------------
# Perhitungan ulang satu baris absensi (satu-satunya tempat)
# --------------------------------------------------------------------------
async def approved_leave_on(company_id: str, employee_id: str, work_date: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    return await db.leave_requests.find_one({
        "company_id": company_id, "employee_id": employee_id, "request_status": "approved",
        "start_date": {"$lte": work_date}, "end_date": {"$gte": work_date},
    }, NO_ID)


async def approved_overtime_minutes(company_id: str, employee_id: str, work_date: str) -> int:
    db = get_db()
    rows = await db.overtime_requests.find({
        "company_id": company_id, "employee_id": employee_id,
        "work_date": work_date, "request_status": "approved",
    }, NO_ID).to_list(50)
    return sum(int(r.get("approved_minutes") or 0) for r in rows)


async def recompute_attendance(company: Dict[str, Any], attendance: Dict[str, Any],
                               persist: bool = True) -> Dict[str, Any]:
    company_id = company["id"]
    db = get_db()
    shift = None
    if attendance.get("shift_id"):
        shift = await db.work_shifts.find_one({"company_id": company_id, "id": attendance["shift_id"]}, NO_ID)
    location = None
    if attendance.get("work_location_id"):
        location = await db.work_locations.find_one(
            {"company_id": company_id, "id": attendance["work_location_id"]}, NO_ID)
    tz = tk.tz_for(company, location)

    metrics = tk.compute_attendance_metrics(
        shift, attendance["work_date"], tz,
        attendance.get("check_in_at"), attendance.get("check_out_at"))

    leave = await approved_leave_on(company_id, attendance["employee_id"], attendance["work_date"])
    leave_status = tk.LEAVE_CATEGORY_TO_STATUS.get(leave.get("leave_category") or "", "leave") if leave else None

    candidate = {**attendance, **metrics,
                 "leave_type_code": leave.get("leave_type_code") if leave else None,
                 "leave_status": leave_status}
    status_key, is_valid = tk.resolve_attendance_status(candidate)

    patch: Dict[str, Any] = {
        **metrics,
        "attendance_status": status_key, "is_valid": is_valid,
        "period_key": tk.period_key_of(attendance["work_date"]),
        "leave_request_id": leave.get("id") if leave else None,
        "leave_type_code": leave.get("leave_type_code") if leave else None,
        "approved_overtime_minutes": await approved_overtime_minutes(
            company_id, attendance["employee_id"], attendance["work_date"]),
    }
    if persist:
        await db.attendances.update_one(
            {"company_id": company_id, "id": attendance["id"]},
            {"$set": {**patch, "updated_at": now()}})
    return {**attendance, **patch}


async def recompute_range(company: Dict[str, Any], employee_id: str, dates: Iterable[str]) -> int:
    db = get_db()
    dates = sorted({d for d in dates if d})
    if not dates:
        return 0
    rows = await db.attendances.find({
        "company_id": company["id"], "employee_id": employee_id,
        "work_date": {"$in": list(dates)}, "status": {"$ne": "deleted"},
    }, NO_ID).to_list(500)
    for row in rows:
        await recompute_attendance(company, row)
    return len(rows)


# --------------------------------------------------------------------------
# Buku besar saldo cuti
# --------------------------------------------------------------------------
MOVEMENTS = {
    "entitlement": "Hak Cuti",
    "adjustment": "Penyesuaian",
    "usage": "Terpakai",
    "reversal": "Pengembalian",
    "carry_forward": "Saldo Dibawa",
}


async def add_ledger(ctx, employee: Dict[str, Any], leave_type: Dict[str, Any], year: int,
                     movement_type: str, days: float, reference_type: str,
                     reference_id: Optional[str], notes: Optional[str] = None,
                     effective_date: Optional[str] = None) -> Dict[str, Any]:
    if movement_type not in MOVEMENTS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Jenis pergerakan saldo tidak dikenal.")
    db = get_db()
    entry = {
        "id": new_id(), "company_id": ctx.company_id, "status": "active",
        "employee_id": employee["id"], "employee_name": employee.get("full_name"),
        "leave_type_id": leave_type["id"], "leave_type_code": leave_type.get("code"),
        "year": int(year), "movement_type": movement_type, "days": float(days),
        "reference_type": reference_type, "reference_id": reference_id, "notes": notes,
        "effective_date": effective_date, "created_by_name": ctx.user.get("full_name"),
        **audit_fields(ctx.user_id),
    }
    await db.leave_ledger.insert_one(dict(entry))
    await recalc_balance(ctx.company_id, employee, leave_type, int(year))
    return entry


async def recalc_balance(company_id: str, employee: Dict[str, Any],
                         leave_type: Dict[str, Any], year: int) -> Dict[str, Any]:
    db = get_db()
    rows = await db.leave_ledger.find({
        "company_id": company_id, "employee_id": employee["id"],
        "leave_type_id": leave_type["id"], "year": int(year), "status": "active",
    }, NO_ID).to_list(2000)
    totals = {key: 0.0 for key in MOVEMENTS}
    for r in rows:
        totals[r["movement_type"]] = totals.get(r["movement_type"], 0.0) + float(r.get("days") or 0)

    pending_rows = await db.leave_requests.find({
        "company_id": company_id, "employee_id": employee["id"],
        "leave_type_id": leave_type["id"], "request_status": "pending",
        "start_date": {"$gte": f"{year}-01-01", "$lte": f"{year}-12-31"},
    }, NO_ID).to_list(500)
    pending_days = sum(float(r.get("working_days") or 0) for r in pending_rows if r.get("deduct_balance"))

    entitlement = totals["entitlement"] + totals["carry_forward"]
    used = totals["usage"] - totals["reversal"]
    available = entitlement + totals["adjustment"] - used - pending_days

    doc = {
        "company_id": company_id, "status": "active",
        "employee_id": employee["id"], "employee_name": employee.get("full_name"),
        "leave_type_id": leave_type["id"], "leave_type_code": leave_type.get("code"),
        "year": int(year),
        "entitlement_days": round(totals["entitlement"], 2),
        "carry_forward_days": round(totals["carry_forward"], 2),
        "adjustment_days": round(totals["adjustment"], 2),
        "used_days": round(used, 2), "pending_days": round(pending_days, 2),
        "available_days": round(available, 2),
        "recalculated_at": now(), "updated_at": now(),
    }
    await db.leave_balances.update_one(
        {"company_id": company_id, "employee_id": employee["id"],
         "leave_type_id": leave_type["id"], "year": int(year)},
        {"$set": doc}, upsert=True)
    return doc


async def ensure_entitlement(ctx, employee: Dict[str, Any], leave_type: Dict[str, Any],
                             year: int) -> Dict[str, Any]:
    """Buat hak cuti awal dari kuota default bila belum ada (idempoten)."""
    db = get_db()
    existing = await db.leave_ledger.count_documents({
        "company_id": ctx.company_id, "employee_id": employee["id"],
        "leave_type_id": leave_type["id"], "year": int(year), "movement_type": "entitlement",
    })
    quota = float(leave_type.get("default_quota_days") or 0)
    if not existing and quota > 0:
        await add_ledger(ctx, employee, leave_type, year, "entitlement", quota,
                         "leave_type_quota", leave_type["id"],
                         notes=f"Hak cuti otomatis dari kuota default {leave_type.get('name')} tahun {year}.",
                         effective_date=f"{year}-01-01")
    return await recalc_balance(ctx.company_id, employee, leave_type, int(year))


# --------------------------------------------------------------------------
# Hari kerja untuk pengajuan cuti (tanpa hardcode Sabtu/Minggu)
# --------------------------------------------------------------------------
async def leave_day_breakdown(company: Dict[str, Any], employee: Dict[str, Any],
                              start_date: str, end_date: str, day_part: str,
                              leave_policy: Dict[str, Any]) -> Dict[str, Any]:
    company_id = company["id"]
    db = get_db()
    dates = tk.date_range(start_date, end_date)
    schedules = await db.work_schedules.find({
        "company_id": company_id, "employee_id": employee["id"],
        "work_date": {"$in": dates}, "status": {"$ne": "deleted"},
    }, NO_ID).to_list(500)
    sched_map = {s["work_date"]: s for s in schedules}
    cal = await tk.calendar_map(company_id, dates)

    breakdown: List[Dict[str, Any]] = []
    working = 0.0
    for d in dates:
        day_type = tk.resolve_day_type(d, sched_map.get(d), cal.get(d))
        counts = tk.is_working_day_type(day_type)
        if not counts:
            if day_type == "weekly_off" and leave_policy.get("count_day_off_as_leave"):
                counts = True
            elif day_type in tk.HOLIDAY_DAY_TYPES and leave_policy.get("count_holiday_as_leave"):
                counts = True
        value = 0.0
        if counts:
            value = 0.5 if (day_part != "full_day" and len(dates) == 1) else 1.0
            working += value
        breakdown.append({
            "work_date": d, "day_type": day_type,
            "day_type_label": tk.DAY_TYPES.get(day_type, "-"),
            "counted_days": value, "has_schedule": d in sched_map,
        })
    return {
        "dates": dates, "calendar_days": len(dates), "working_days": round(working, 2),
        "breakdown": breakdown, "period_keys": sorted({tk.period_key_of(d) for d in dates}),
    }


# --------------------------------------------------------------------------
# Lembur aktual dari absensi
# --------------------------------------------------------------------------
def round_minutes(minutes: int, interval: int) -> int:
    interval = max(1, int(interval or 1))
    return int(minutes // interval) * interval


async def compute_actual_overtime(company: Dict[str, Any], request: Dict[str, Any],
                                  overtime_policy: Dict[str, Any]) -> Dict[str, Any]:
    """Potensi lembur aktual. Kehadiran aktual BUKAN otomatis payable."""
    db = get_db()
    att = await db.attendances.find_one({
        "company_id": company["id"], "employee_id": request["employee_id"],
        "work_date": request["work_date"], "status": {"$ne": "deleted"},
    }, NO_ID)
    if not att or not att.get("check_out_at"):
        return {
            "attendance_id": att["id"] if att else None,
            "actual_minutes": 0, "rounded_minutes": 0,
            "note": "Belum ada Absen Pulang pada tanggal tersebut, sehingga lembur aktual belum dapat dihitung.",
        }

    check_out = tk.as_aware(att.get("check_out_at"))
    check_in = tk.as_aware(att.get("check_in_at"))
    scheduled_end = tk.as_aware(att.get("scheduled_end_at"))
    scheduled_start = tk.as_aware(att.get("scheduled_start_at"))

    minutes = 0
    if scheduled_end:
        minutes = max(0, int((check_out - scheduled_end).total_seconds() // 60))
    elif check_in:
        minutes = max(0, int((check_out - check_in).total_seconds() // 60))

    if overtime_policy.get("allow_pre_shift_overtime") and scheduled_start and check_in:
        minutes += max(0, int((scheduled_start - check_in).total_seconds() // 60))

    max_per_day = int(overtime_policy.get("max_minutes_per_day") or 0)
    if max_per_day:
        minutes = min(minutes, max_per_day)
    rounded = round_minutes(minutes, overtime_policy.get("rounding_interval_minutes") or 1)
    minimum = int(overtime_policy.get("minimum_minutes") or 0)
    if rounded < minimum:
        rounded = 0
    return {
        "attendance_id": att["id"], "actual_minutes": minutes, "rounded_minutes": rounded,
        "note": (f"Lembur aktual {tk.minutes_to_hhmm(minutes)}; setelah pembulatan "
                 f"{tk.minutes_to_hhmm(rounded)} (minimal {minimum} menit)."),
    }
