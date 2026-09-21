"""
Seed DEVELOPMENT untuk Time Management V1.

Bersifat idempoten (aman dijalankan berulang) dan hanya mengisi master/konfigurasi
yang dibutuhkan agar modul Absensi, Cuti/Izin/Sakit, dan Lembur dapat dipakai:

- Master shift kerja (pagi / siang / malam-overnight / OFF)
- Kalender kerja (libur nasional & cuti bersama contoh)
- Konfigurasi geofence pada master lokasi kerja EXISTING (tidak membuat lokasi baru)
- Master jenis cuti / izin / sakit
- Alur persetujuan (absensi luar radius, koreksi absensi, lembur) bila belum ada
- Hak cuti awal (ledger + saldo) untuk karyawan aktif

Tidak menyalin data apa pun dari environment produksi.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .core.db import NO_ID, audit_fields, get_db, new_id

CURRENT_YEAR = datetime.now(timezone.utc).year

SHIFTS: List[Dict[str, Any]] = [
    {
        "code": "SHIFT-P", "name": "Shift Pagi", "description": "08:00 - 17:00, istirahat 12:00 - 13:00",
        "start_time": "08:00", "end_time": "17:00", "break_start": "12:00", "break_end": "13:00",
        "late_tolerance_minutes": 15, "early_leave_tolerance_minutes": 0,
        "is_overnight": False, "is_day_off": False, "sort_order": 1,
    },
    {
        "code": "SHIFT-S", "name": "Shift Siang", "description": "13:00 - 22:00, istirahat 18:00 - 19:00",
        "start_time": "13:00", "end_time": "22:00", "break_start": "18:00", "break_end": "19:00",
        "late_tolerance_minutes": 10, "early_leave_tolerance_minutes": 0,
        "is_overnight": False, "is_day_off": False, "sort_order": 2,
    },
    {
        "code": "SHIFT-M", "name": "Shift Malam", "description": "23:00 - 07:00 (lintas hari), istirahat 03:00 - 04:00",
        "start_time": "23:00", "end_time": "07:00", "break_start": "03:00", "break_end": "04:00",
        "late_tolerance_minutes": 10, "early_leave_tolerance_minutes": 0,
        "is_overnight": True, "is_day_off": False, "sort_order": 3,
    },
    {
        "code": "SHIFT-OFF", "name": "Hari OFF", "description": "Hari tidak masuk kerja terjadwal",
        "start_time": None, "end_time": None, "break_start": None, "break_end": None,
        "late_tolerance_minutes": 0, "early_leave_tolerance_minutes": 0,
        "is_overnight": False, "is_day_off": True, "sort_order": 9,
    },
]

CALENDAR_DAYS: List[Dict[str, Any]] = [
    {"calendar_date": f"{CURRENT_YEAR}-01-01", "day_type": "national_holiday", "name": "Tahun Baru"},
    {"calendar_date": f"{CURRENT_YEAR}-05-01", "day_type": "national_holiday", "name": "Hari Buruh Internasional"},
    {"calendar_date": f"{CURRENT_YEAR}-08-17", "day_type": "national_holiday", "name": "Hari Kemerdekaan RI"},
    {"calendar_date": f"{CURRENT_YEAR}-12-25", "day_type": "national_holiday", "name": "Hari Raya Natal"},
    {"calendar_date": f"{CURRENT_YEAR}-12-26", "day_type": "collective_leave", "name": "Cuti Bersama Natal"},
]

LEAVE_TYPES: List[Dict[str, Any]] = [
    {
        "code": "CT-TAHUNAN", "name": "Cuti Tahunan", "description": "Hak cuti tahunan karyawan",
        "category": "leave", "deduct_balance": True, "is_paid": True,
        "attachment_required": False, "approval_required": True, "allow_half_day": True,
        "minimum_notice_days": 3, "maximum_consecutive_days": 12,
        "default_quota_days": 12, "sort_order": 1, "color": "emerald",
    },
    {
        "code": "CT-SAKIT", "name": "Sakit", "description": "Sakit dengan surat keterangan dokter",
        "category": "sick", "deduct_balance": False, "is_paid": True,
        "attachment_required": True, "approval_required": True, "allow_half_day": False,
        "minimum_notice_days": 0, "maximum_consecutive_days": 14,
        "default_quota_days": 0, "sort_order": 2, "color": "amber",
    },
    {
        "code": "CT-IZIN", "name": "Izin", "description": "Izin keperluan pribadi (tidak mengurangi saldo cuti)",
        "category": "permission", "deduct_balance": False, "is_paid": False,
        "attachment_required": False, "approval_required": True, "allow_half_day": True,
        "minimum_notice_days": 1, "maximum_consecutive_days": 3,
        "default_quota_days": 0, "sort_order": 3, "color": "sky",
    },
    {
        "code": "CT-PENTING", "name": "Cuti Alasan Penting", "description": "Pernikahan, kelahiran, atau duka keluarga",
        "category": "leave", "deduct_balance": False, "is_paid": True,
        "attachment_required": False, "approval_required": True, "allow_half_day": False,
        "minimum_notice_days": 0, "maximum_consecutive_days": 3,
        "default_quota_days": 0, "sort_order": 4, "color": "violet",
    },
    {
        "code": "CT-MELAHIRKAN", "name": "Cuti Melahirkan", "description": "Cuti melahirkan sesuai ketentuan",
        "category": "leave", "deduct_balance": False, "is_paid": True,
        "attachment_required": True, "approval_required": True, "allow_half_day": False,
        "minimum_notice_days": 14, "maximum_consecutive_days": 90,
        "default_quota_days": 0, "sort_order": 5, "color": "rose",
    },
]

TIME_WORKFLOWS: List[Dict[str, Any]] = [
    {
        "code": "WF-ABSEN-LOKASI", "name": "Persetujuan Absensi Di Luar Radius",
        "document_kind": "attendance",
        "description": "Absensi di luar radius lokasi kerja wajib disetujui atasan lalu HR.",
        "steps": [
            {"step_order": 1, "name": "Atasan Langsung", "approver_type": "supervisor"},
            {"step_order": 2, "name": "HR Administrator", "approver_type": "role", "approver_role_key": "hr_admin"},
        ],
    },
    {
        "code": "WF-KOREKSI-ABSEN", "name": "Persetujuan Koreksi Absensi",
        "document_kind": "attendance_correction",
        "description": "Koreksi jam absensi wajib disetujui atasan lalu HR.",
        "steps": [
            {"step_order": 1, "name": "Atasan Langsung", "approver_type": "supervisor"},
            {"step_order": 2, "name": "HR Administrator", "approver_type": "role", "approver_role_key": "hr_admin"},
        ],
    },
    {
        "code": "WF-LEMBUR", "name": "Persetujuan Lembur",
        "document_kind": "overtime",
        "description": "Lembur wajib disetujui atasan lalu HR Manager.",
        "steps": [
            {"step_order": 1, "name": "Atasan Langsung", "approver_type": "supervisor"},
            {"step_order": 2, "name": "HR Manager", "approver_type": "role", "approver_role_key": "hr_manager"},
        ],
    },
]

# Koordinat contoh (Indonesia) untuk lokasi kerja development.
LOCATION_GEO: Dict[str, Dict[str, Any]] = {
    "LOC-HO": {"latitude": -6.226500, "longitude": 106.809700, "radius_meter": 150, "timezone": "Asia/Jakarta"},
    "LOC-SITE1": {"latitude": 0.520000, "longitude": 117.540000, "radius_meter": 500, "timezone": "Asia/Makassar"},
    "LOC-WH": {"latitude": -7.239000, "longitude": 112.680000, "radius_meter": 200, "timezone": "Asia/Jakarta"},
    "LOC-KBS-HO": {"latitude": -6.175400, "longitude": 106.827200, "radius_meter": 150, "timezone": "Asia/Jakarta"},
    "LOC-KBS-PRJ": {"latitude": -6.900000, "longitude": 107.618600, "radius_meter": 400, "timezone": "Asia/Jakarta"},
}

DEFAULT_TIME_POLICIES: Dict[str, Any] = {
    "attendance": {
        "default_geofence_policy": "outside_requires_approval",
        "default_radius_meter": 150,
        "gps_accuracy_max_meter": 150,
        "allow_check_in_without_schedule": False,
        "auto_absent_after_period_close": True,
    },
    "overtime": {
        "minimum_minutes": 30,
        "rounding_interval_minutes": 15,
        "max_minutes_per_day": 240,
        "pre_approval_required": True,
        "retroactive_allowed": True,
        "allow_pre_shift_overtime": False,
    },
    "leave": {
        "count_holiday_as_leave": False,
        "count_day_off_as_leave": False,
        "half_day_value": 0.5,
        "max_backdate_days": 7,
        "attachment_max_mb": 5,
    },
}


async def _ensure(collection: str, filter_q: Dict[str, Any], doc: Dict[str, Any]) -> Dict[str, Any]:
    db = get_db()
    existing = await db[collection].find_one(filter_q, NO_ID)
    if existing:
        return existing
    payload = {"id": new_id(), "status": "active", **doc}
    payload.update(audit_fields(None, creating=True))
    await db[collection].insert_one(dict(payload))
    return {k: v for k, v in payload.items() if k != "_id"}


async def seed_shifts(company_id: str) -> None:
    for shift in SHIFTS:
        await _ensure("work_shifts", {"company_id": company_id, "code": shift["code"]},
                      {"company_id": company_id, **shift})


async def seed_calendar(company_id: str) -> None:
    for day in CALENDAR_DAYS:
        await _ensure("work_calendar_days",
                      {"company_id": company_id, "calendar_date": day["calendar_date"]},
                      {"company_id": company_id, "notes": None, **day})


async def seed_leave_types(company_id: str) -> None:
    for lt in LEAVE_TYPES:
        await _ensure("leave_types", {"company_id": company_id, "code": lt["code"]},
                      {"company_id": company_id, **lt})


async def seed_policies(company_id: str) -> None:
    await _ensure("time_policies", {"company_id": company_id},
                  {"company_id": company_id, **DEFAULT_TIME_POLICIES})


async def seed_location_geofence(company_id: str) -> None:
    """Melengkapi koordinat & geofence pada lokasi kerja existing (tanpa membuat master baru)."""
    db = get_db()
    locations = await db.work_locations.find({"company_id": company_id, "status": "active"}, NO_ID).to_list(100)
    for loc in locations:
        geo = LOCATION_GEO.get(loc.get("code"))
        updates: Dict[str, Any] = {}
        if loc.get("latitude") in (None, 0) and geo:
            updates["latitude"] = geo["latitude"]
            updates["longitude"] = geo["longitude"]
        if not loc.get("radius_meter"):
            updates["radius_meter"] = (geo or {}).get("radius_meter", 150)
        if not loc.get("timezone"):
            updates["timezone"] = (geo or {}).get("timezone", "Asia/Jakarta")
        if loc.get("geofence_enabled") is None:
            updates["geofence_enabled"] = True
        if not loc.get("attendance_location_policy"):
            updates["attendance_location_policy"] = "outside_requires_approval"
        if not loc.get("gps_accuracy_max_meter"):
            updates["gps_accuracy_max_meter"] = 150
        if updates:
            await db.work_locations.update_one({"company_id": company_id, "id": loc["id"]}, {"$set": updates})


async def seed_time_workflows(company_id: str) -> None:
    db = get_db()
    for wf in TIME_WORKFLOWS:
        existing = await db.approval_workflows.find_one(
            {"company_id": company_id, "document_kind": wf["document_kind"], "status": "active"}, NO_ID
        )
        if existing:
            workflow = existing
        else:
            workflow = await _ensure(
                "approval_workflows", {"company_id": company_id, "code": wf["code"]},
                {
                    "company_id": company_id, "code": wf["code"], "name": wf["name"],
                    "document_kind": wf["document_kind"], "scope_type": "company", "scope_id": None,
                    "description": wf["description"], "is_default": True,
                    "step_count": len(wf["steps"]), "is_demo_data": True,
                },
            )
        for step in wf["steps"]:
            await _ensure(
                "approval_steps",
                {"company_id": company_id, "workflow_id": workflow["id"], "step_order": step["step_order"]},
                {
                    "company_id": company_id, "workflow_id": workflow["id"],
                    "step_order": step["step_order"], "name": step["name"],
                    "approver_type": step["approver_type"],
                    "approver_role_key": step.get("approver_role_key"),
                    "approver_user_id": None, "approver_position_id": None,
                    "is_mandatory": True, "allow_delegation": True, "sla_days": 2,
                    "condition_note": None, "is_demo_data": True,
                },
            )


async def seed_leave_entitlements(company_id: str) -> None:
    """Hak cuti awal + saldo untuk karyawan aktif (idempoten)."""
    db = get_db()
    employees = await db.employees.find(
        {"company_id": company_id, "status": "active"}, NO_ID
    ).to_list(1000)
    leave_types = await db.leave_types.find(
        {"company_id": company_id, "status": "active"}, NO_ID
    ).to_list(50)
    quota_types = [lt for lt in leave_types if float(lt.get("default_quota_days") or 0) > 0]
    if not (employees and quota_types):
        return

    from .core.time_service import recalc_balance

    for emp in employees:
        for lt in quota_types:
            exists = await db.leave_ledger.count_documents({
                "company_id": company_id, "employee_id": emp["id"],
                "leave_type_id": lt["id"], "year": CURRENT_YEAR, "movement_type": "entitlement",
            })
            if not exists:
                entry = {
                    "id": new_id(), "company_id": company_id, "status": "active",
                    "employee_id": emp["id"], "employee_name": emp.get("full_name"),
                    "leave_type_id": lt["id"], "leave_type_code": lt.get("code"),
                    "year": CURRENT_YEAR, "movement_type": "entitlement",
                    "days": float(lt.get("default_quota_days") or 0),
                    "reference_type": "leave_type_quota", "reference_id": lt["id"],
                    "notes": f"Hak cuti awal {lt.get('name')} tahun {CURRENT_YEAR}.",
                    "effective_date": f"{CURRENT_YEAR}-01-01", "created_by_name": "Sistem",
                    **audit_fields(None, creating=True),
                }
                await db.leave_ledger.insert_one(dict(entry))
            await recalc_balance(company_id, emp, lt, CURRENT_YEAR)


async def seed_time_permissions() -> None:
    """Top-up hak akses Time Management per-kunci (idempoten, tidak menimpa perubahan manual)."""
    from .core.rbac import default_role_permissions

    db = get_db()
    matrix = default_role_permissions()
    for role_key, keys in matrix.items():
        wanted = [k for k in keys if k.split(":")[0] in ("attendance", "leave")]
        for key in wanted:
            exists = await db.role_permissions.count_documents(
                {"role_key": role_key, "permission_key": key}
            )
            if exists:
                continue
            await db.role_permissions.insert_one({
                "id": new_id(), "company_id": None, "role_key": role_key,
                "permission_key": key, "status": "active",
                **audit_fields(None, creating=True),
            })


async def seed_supervisor_links(company_id: str) -> None:
    """Pastikan atasan langsung dapat ditentukan (kepala departemen/divisi)."""
    db = get_db()
    employees = await db.employees.find({"company_id": company_id, "status": "active"}, NO_ID).to_list(1000)
    if not employees:
        return
    # Cari karyawan yang tertaut ke pengguna berperan supervisor/manager.
    candidates: List[Dict[str, Any]] = []
    for emp in employees:
        if not emp.get("user_id"):
            continue
        roles = await db.user_company_roles.find(
            {"company_id": company_id, "user_id": emp["user_id"], "status": "active"}, NO_ID
        ).to_list(20)
        keys = {r.get("role_key") for r in roles}
        if keys & {"supervisor", "manager", "hr_manager"}:
            candidates.append(emp)
    if not candidates:
        return
    head = candidates[0]
    for coll, key in (("departments", "department_id"), ("divisions", "division_id")):
        rows = await db[coll].find({"company_id": company_id, "status": "active"}, NO_ID).to_list(100)
        for row in rows:
            if not row.get("head_user_id"):
                await db[coll].update_one(
                    {"company_id": company_id, "id": row["id"]},
                    {"$set": {"head_user_id": head["user_id"]}},
                )


async def seed_time_management(company_ids: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    db = get_db()
    await seed_time_permissions()
    if company_ids:
        ids = list(company_ids.values())
    else:
        rows = await db.companies.find({"status": "active"}, NO_ID).to_list(100)
        ids = [r["id"] for r in rows]
    for company_id in ids:
        await seed_shifts(company_id)
        await seed_calendar(company_id)
        await seed_leave_types(company_id)
        await seed_policies(company_id)
        await seed_location_geofence(company_id)
        await seed_time_workflows(company_id)
        await seed_supervisor_links(company_id)
        await seed_leave_entitlements(company_id)
    return {"companies_seeded": len(ids)}
