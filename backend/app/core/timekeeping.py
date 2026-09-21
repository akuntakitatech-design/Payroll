"""Layanan bersama Time Management (Absensi + Cuti/Izin/Sakit + Lembur).

SATU sumber perhitungan waktu untuk ketiga area, sesuai arsitektur bersama:

    Karyawan -> Kalender Kerja -> Jadwal/Shift -> Lokasi Kerja -> Absensi
             -> Cuti/Izin/Sakit -> Lembur -> Approval -> Rekap -> Tutup Periode

Modul ini TIDAK menyentuh Payroll/BPJS/PPh21. Ia hanya menyediakan:
  * resolusi timezone (canonical backend, bukan timezone browser)
  * resolusi work_date & shift (termasuk shift lintas tengah malam)
  * perhitungan menit terjadwal / aktual / terlambat / pulang cepat
  * deteksi hari OFF & hari libur dari kalender kerja
  * perhitungan jarak geofence (Haversine) di BACKEND
  * resolusi status kehadiran (label Bahasa Indonesia)
  * pemeriksaan Tutup Periode (period lock)

Catatan bahasa: key internal tetap bahasa Inggris (enum/field/API), label
yang dilihat pengguna selalu Bahasa Indonesia.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status

from .db import NO_ID, get_db

DEFAULT_TZ = "Asia/Jakarta"

# --------------------------------------------------------------------------
# Katalog (label Bahasa Indonesia untuk UI)
# --------------------------------------------------------------------------
ATTENDANCE_STATUSES: Dict[str, Dict[str, str]] = {
    "present": {"label": "Hadir", "tone": "success"},
    "late": {"label": "Terlambat", "tone": "warning"},
    "early_leave": {"label": "Pulang Cepat", "tone": "warning"},
    "late_and_early_leave": {"label": "Terlambat & Pulang Cepat", "tone": "warning"},
    "no_check_out": {"label": "Belum Absen Pulang", "tone": "warning"},
    "awaiting_location_approval": {"label": "Menunggu Persetujuan Lokasi", "tone": "warning"},
    "location_rejected": {"label": "Lokasi Ditolak", "tone": "danger"},
    "day_off": {"label": "OFF", "tone": "neutral"},
    "holiday": {"label": "Libur", "tone": "neutral"},
    "leave": {"label": "Cuti", "tone": "info"},
    "permission": {"label": "Izin", "tone": "info"},
    "sick": {"label": "Sakit", "tone": "info"},
    "unpaid_leave": {"label": "Cuti Tidak Dibayar", "tone": "neutral"},
    "absent": {"label": "Alfa", "tone": "danger"},
    "no_schedule": {"label": "Tidak Ada Jadwal", "tone": "neutral"},
}

ATTENDANCE_SOURCES: Dict[str, str] = {
    "web": "Web",
    "mobile": "Ponsel",
    "excel_import": "Import Excel",
    "manual": "Manual HR",
    "device_api": "Perangkat Absensi",
}

GEOFENCE_POLICIES: Dict[str, str] = {
    "inside_required": "Dalam Radius Wajib",
    "outside_requires_approval": "Di Luar Radius Perlu Persetujuan",
    "gps_only": "GPS Saja (Karyawan Lapangan)",
    "disabled": "Tanpa Geofence",
}

GEOFENCE_RESULTS: Dict[str, str] = {
    "inside": "Di Dalam Radius",
    "outside": "Di Luar Radius",
    "gps_unavailable": "GPS Tidak Tersedia",
    "accuracy_warning": "Akurasi GPS Rendah",
    "not_applicable": "Tidak Berlaku",
}

LOCATION_APPROVAL_STATUSES: Dict[str, str] = {
    "not_required": "Tidak Perlu Persetujuan",
    "pending": "Menunggu Persetujuan",
    "approved": "Disetujui",
    "rejected": "Ditolak",
}

LOCATION_APPROVAL_FOR: Dict[str, str] = {
    "check_in": "Absen Masuk",
    "check_out": "Absen Pulang",
    "both": "Absen Masuk & Pulang",
}

LOCATION_REASON_CODES: Dict[str, str] = {
    "client_visit": "Kunjungan Klien",
    "business_trip": "Dinas Luar",
    "project_work": "Proyek",
    "field_duty": "Tugas Lapangan",
    "location_change": "Perubahan Lokasi",
    "other": "Lainnya",
}

DAY_TYPES: Dict[str, str] = {
    "workday": "Hari Kerja",
    "weekly_off": "OFF Mingguan",
    "national_holiday": "Libur Nasional",
    "company_holiday": "Libur Perusahaan",
    "joint_leave": "Cuti Bersama",
    "workday_override": "Hari Kerja Pengganti",
}
CALENDAR_DAY_TYPES = ["national_holiday", "company_holiday", "joint_leave", "workday_override"]
HOLIDAY_DAY_TYPES = {"national_holiday", "company_holiday", "joint_leave"}

LEAVE_CATEGORIES: Dict[str, str] = {
    "annual": "Cuti Tahunan",
    "sick": "Sakit",
    "permission": "Izin",
    "maternity": "Cuti Melahirkan",
    "special": "Cuti Khusus",
    "unpaid": "Cuti Tidak Dibayar",
}
# Kategori cuti -> status yang muncul pada Rekap Kehadiran.
LEAVE_CATEGORY_TO_STATUS: Dict[str, str] = {
    "annual": "leave",
    "special": "leave",
    "maternity": "leave",
    "sick": "sick",
    "permission": "permission",
    "unpaid": "unpaid_leave",
}

REQUEST_STATUSES: Dict[str, Dict[str, str]] = {
    "pending": {"label": "Menunggu Persetujuan", "tone": "warning"},
    "approved": {"label": "Disetujui", "tone": "success"},
    "rejected": {"label": "Ditolak", "tone": "danger"},
    "cancelled": {"label": "Dibatalkan", "tone": "neutral"},
}

CORRECTION_TYPES: Dict[str, str] = {
    "missing_check_in": "Lupa Absen Masuk",
    "missing_check_out": "Lupa Absen Pulang",
    "wrong_time": "Waktu Salah",
}

DAY_PARTS: Dict[str, str] = {
    "full_day": "Sehari Penuh",
    "half_day_morning": "Setengah Hari (Pagi)",
    "half_day_afternoon": "Setengah Hari (Sore)",
}

OVERTIME_DAY_CATEGORIES: Dict[str, str] = {
    "workday": "Hari Kerja",
    "day_off": "Hari OFF / Istirahat",
    "holiday": "Hari Libur",
}

OVERTIME_CATEGORIES: Dict[str, str] = {
    "operational": "Operasional",
    "project": "Proyek",
    "maintenance": "Pemeliharaan",
    "urgent": "Mendesak",
    "other": "Lainnya",
}

PERIOD_STATUSES: Dict[str, Dict[str, str]] = {
    "open": {"label": "Terbuka", "tone": "success"},
    "closed": {"label": "Ditutup", "tone": "danger"},
}

EXCEPTION_KINDS: Dict[str, str] = {
    "no_check_out": "Belum Absen Pulang",
    "no_schedule": "Tidak Ada Jadwal",
    "awaiting_location_approval": "Menunggu Persetujuan Lokasi",
    "gps_problem": "GPS Bermasalah",
    "duplicate": "Data Duplikat",
    "import_employee_not_found": "Employee Import Tidak Ditemukan",
    "leave_conflict": "Konflik Cuti",
    "overtime_conflict": "Konflik Lembur",
}

DEFAULT_ATTENDANCE_POLICY: Dict[str, Any] = {
    "default_geofence_policy": "outside_requires_approval",
    "default_radius_meter": 150,
    "gps_accuracy_max_meter": 150,
    "allow_check_in_without_schedule": False,
    "auto_absent_after_period_close": True,
}

DEFAULT_OVERTIME_POLICY: Dict[str, Any] = {
    "minimum_minutes": 30,
    "rounding_interval_minutes": 15,
    "max_minutes_per_day": 240,
    "pre_approval_required": True,
    "retroactive_allowed": True,
    "allow_pre_shift_overtime": False,
}

DEFAULT_LEAVE_POLICY: Dict[str, Any] = {
    "count_day_off_as_leave": False,
    "count_holiday_as_leave": False,
    "allow_cancel_after_approved": True,
    "cancel_requires_approval": False,
}


def status_label(key: Optional[str]) -> str:
    return ATTENDANCE_STATUSES.get(key or "", {}).get("label", key or "-")


def catalog_list(mapping: Dict[str, Any]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for key, value in mapping.items():
        if isinstance(value, dict):
            out.append({"key": key, "label": value.get("label", key), "tone": value.get("tone", "neutral")})
        else:
            out.append({"key": key, "label": value})
    return out


# --------------------------------------------------------------------------
# Timezone & tanggal
# --------------------------------------------------------------------------
def tz_for(company: Optional[Dict[str, Any]], work_location: Optional[Dict[str, Any]] = None) -> ZoneInfo:
    """Timezone kanonik: lokasi kerja (bila diisi) -> perusahaan -> Asia/Jakarta."""
    name = None
    if work_location:
        name = (work_location.get("timezone") or "").strip() or None
    if not name and company:
        name = (company.get("timezone") or "").strip() or None
    try:
        return ZoneInfo(name or DEFAULT_TZ)
    except Exception:  # noqa: BLE001 - timezone tidak dikenal -> default aman
        return ZoneInfo(DEFAULT_TZ)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def as_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def to_local(dt: Optional[datetime], tz: ZoneInfo) -> Optional[datetime]:
    dt = as_aware(dt)
    return dt.astimezone(tz) if dt else None


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)(:[0-5]\d)?$")


def parse_date_str(value: Any, label: str = "Tanggal", required: bool = True) -> Optional[str]:
    if value in (None, ""):
        if required:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{label} wajib diisi.")
        return None
    text = str(value).strip()[:10]
    if not DATE_RE.match(text):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{label} harus berformat YYYY-MM-DD.")
    try:
        date.fromisoformat(text)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{label} bukan tanggal yang valid.")
    return text


def parse_time_str(value: Any, label: str = "Jam", required: bool = True) -> Optional[str]:
    if value in (None, ""):
        if required:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{label} wajib diisi.")
        return None
    text = str(value).strip()
    m = TIME_RE.match(text)
    if not m:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{label} harus berformat HH:MM (24 jam).")
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def time_to_minutes(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    m = TIME_RE.match(str(value).strip())
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def period_key_of(work_date: str) -> str:
    return str(work_date)[:7]


def period_label_of(period_key: str) -> str:
    months = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
              "Agustus", "September", "Oktober", "November", "Desember"]
    try:
        year, month = period_key.split("-")
        return f"{months[int(month) - 1]} {year}"
    except Exception:  # noqa: BLE001
        return period_key


def date_range(start: str, end: str) -> List[str]:
    d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    if d1 < d0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Tanggal selesai tidak boleh lebih awal dari tanggal mulai.")
    if (d1 - d0).days > 400:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Rentang tanggal maksimal 400 hari.")
    return [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def month_bounds(period_key: str) -> Tuple[str, str]:
    year, month = int(period_key[:4]), int(period_key[5:7])
    first = date(year, month, 1)
    last = date(year + (month == 12), (month % 12) + 1, 1) - timedelta(days=1)
    return first.isoformat(), last.isoformat()


# --------------------------------------------------------------------------
# Shift (termasuk lintas tengah malam)
# --------------------------------------------------------------------------
def shift_is_overnight(shift: Dict[str, Any]) -> bool:
    if shift.get("is_overnight"):
        return True
    start, end = time_to_minutes(shift.get("start_time")), time_to_minutes(shift.get("end_time"))
    return bool(start is not None and end is not None and end <= start)


def shift_bounds(work_date: str, shift: Dict[str, Any], tz: ZoneInfo) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Batas jadwal (UTC) untuk satu work_date. Shift malam berakhir hari berikutnya."""
    start_m, end_m = time_to_minutes(shift.get("start_time")), time_to_minutes(shift.get("end_time"))
    if start_m is None or end_m is None:
        return None, None
    d = date.fromisoformat(work_date)
    start_local = datetime.combine(d, time(start_m // 60, start_m % 60), tzinfo=tz)
    end_day = d + timedelta(days=1) if end_m <= start_m else d
    end_local = datetime.combine(end_day, time(end_m // 60, end_m % 60), tzinfo=tz)
    return to_utc(start_local), to_utc(end_local)


def shift_break_minutes(shift: Dict[str, Any]) -> int:
    bs, be = time_to_minutes(shift.get("break_start")), time_to_minutes(shift.get("break_end"))
    if bs is None or be is None:
        return 0
    span = be - bs
    if span < 0:
        span += 24 * 60
    return max(0, span)


def shift_scheduled_minutes(shift: Dict[str, Any]) -> int:
    start_m, end_m = time_to_minutes(shift.get("start_time")), time_to_minutes(shift.get("end_time"))
    if start_m is None or end_m is None:
        return 0
    span = end_m - start_m
    if span <= 0:
        span += 24 * 60
    return max(0, span - shift_break_minutes(shift))


def compute_attendance_metrics(
    shift: Optional[Dict[str, Any]],
    work_date: str,
    tz: ZoneInfo,
    check_in_at: Optional[datetime],
    check_out_at: Optional[datetime],
) -> Dict[str, Any]:
    """Menit terjadwal / aktual / terlambat / pulang cepat. Semua di backend."""
    out: Dict[str, Any] = {
        "scheduled_start_at": None, "scheduled_end_at": None, "scheduled_minutes": 0,
        "actual_work_minutes": 0, "late_minutes": 0, "early_leave_minutes": 0,
    }
    check_in_at, check_out_at = as_aware(check_in_at), as_aware(check_out_at)

    if shift and not shift.get("is_day_off"):
        s, e = shift_bounds(work_date, shift, tz)
        out["scheduled_start_at"], out["scheduled_end_at"] = s, e
        out["scheduled_minutes"] = shift_scheduled_minutes(shift)
        if check_in_at and s:
            tol = int(shift.get("late_tolerance_minutes") or 0)
            diff = int((check_in_at - s).total_seconds() // 60)
            out["late_minutes"] = max(0, diff - tol)
        if check_out_at and e:
            tol = int(shift.get("early_leave_tolerance_minutes") or 0)
            diff = int((e - check_out_at).total_seconds() // 60)
            out["early_leave_minutes"] = max(0, diff - tol)

    if check_in_at and check_out_at:
        gross = int((check_out_at - check_in_at).total_seconds() // 60)
        if gross < 0:
            gross = 0
        brk = shift_break_minutes(shift) if shift else 0
        # Istirahat hanya dipotong bila durasi kerja memang melewati istirahat.
        out["actual_work_minutes"] = max(0, gross - brk) if gross > brk else gross
    return out


# --------------------------------------------------------------------------
# Geofence (Haversine) — keputusan ADA DI BACKEND
# --------------------------------------------------------------------------
EARTH_RADIUS_M = 6371008.8


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def effective_location_policy(
    work_location: Optional[Dict[str, Any]], attendance_policy: Dict[str, Any]
) -> str:
    if not work_location:
        return attendance_policy.get("default_geofence_policy") or "disabled"
    if work_location.get("geofence_enabled") is False:
        return "disabled"
    policy = (work_location.get("attendance_location_policy") or "").strip()
    if policy in GEOFENCE_POLICIES:
        return policy
    return attendance_policy.get("default_geofence_policy") or "outside_requires_approval"


def evaluate_geofence(
    work_location: Optional[Dict[str, Any]],
    attendance_policy: Dict[str, Any],
    latitude: Optional[float],
    longitude: Optional[float],
    accuracy: Optional[float],
) -> Dict[str, Any]:
    """Hasil evaluasi geofence. Frontend TIDAK menentukan valid/tidak valid."""
    policy = effective_location_policy(work_location, attendance_policy)
    radius = None
    if work_location and work_location.get("radius_meter") not in (None, ""):
        radius = float(work_location.get("radius_meter"))
    if radius is None:
        radius = float(attendance_policy.get("default_radius_meter") or 150)
    max_acc = work_location.get("gps_accuracy_max_meter") if work_location else None
    if max_acc in (None, ""):
        max_acc = attendance_policy.get("gps_accuracy_max_meter") or 150
    max_acc = float(max_acc)

    result: Dict[str, Any] = {
        "policy": policy,
        "policy_label": GEOFENCE_POLICIES.get(policy, policy),
        "configured_radius_meter": radius,
        "distance_meter": None,
        "geofence_result": "not_applicable",
        "requires_approval": False,
        "blocked": False,
        "message": "",
    }

    if policy == "disabled":
        result["geofence_result"] = "not_applicable"
        result["message"] = "Lokasi kerja ini tidak menggunakan aturan geofence."
        return result

    has_gps = latitude is not None and longitude is not None
    if not has_gps:
        result["geofence_result"] = "gps_unavailable"
        result["blocked"] = True
        result["message"] = (
            "Titik GPS wajib dikirim untuk lokasi kerja ini. Aktifkan izin lokasi pada perangkat Anda."
        )
        return result

    if accuracy is not None and float(accuracy) > max_acc:
        result["geofence_result"] = "accuracy_warning"
        result["requires_approval"] = policy != "gps_only"
        result["message"] = (
            f"Akurasi GPS {float(accuracy):.0f} meter melebihi batas {max_acc:.0f} meter."
        )

    if policy == "gps_only":
        if result["geofence_result"] == "not_applicable":
            result["geofence_result"] = "inside"
        result["requires_approval"] = False
        result.setdefault("message", "")
        if not result["message"]:
            result["message"] = "Kebijakan GPS Saja: titik lokasi dicatat tanpa batas radius kantor."
        if work_location and work_location.get("latitude") not in (None, "") and work_location.get("longitude") not in (None, ""):
            result["distance_meter"] = round(
                haversine_meters(float(latitude), float(longitude),
                                 float(work_location["latitude"]), float(work_location["longitude"])), 2
            )
        return result

    if not work_location or work_location.get("latitude") in (None, "") or work_location.get("longitude") in (None, ""):
        result["geofence_result"] = "not_applicable"
        result["message"] = (
            "Koordinat lokasi kerja belum diatur, sehingga jarak tidak dapat dihitung. "
            "Lengkapi latitude/longitude pada Master Lokasi Kerja."
        )
        return result

    distance = haversine_meters(
        float(latitude), float(longitude),
        float(work_location["latitude"]), float(work_location["longitude"]),
    )
    result["distance_meter"] = round(distance, 2)
    if distance <= radius:
        if result["geofence_result"] in ("not_applicable",):
            result["geofence_result"] = "inside"
            result["message"] = f"Berada di dalam radius ({distance:.0f} m / {radius:.0f} m)."
        result["requires_approval"] = result["geofence_result"] == "accuracy_warning"
        return result

    result["geofence_result"] = "outside"
    result["message"] = f"Di luar radius: jarak {distance:.0f} m, radius diizinkan {radius:.0f} m."
    if policy == "inside_required":
        result["blocked"] = True
    else:  # outside_requires_approval
        result["requires_approval"] = True
    return result


# --------------------------------------------------------------------------
# Kalender kerja & jadwal
# --------------------------------------------------------------------------
async def calendar_map(company_id: str, dates: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    dates = sorted(set(d for d in dates if d))
    if not dates:
        return {}
    db = get_db()
    rows = await db.work_calendar_days.find(
        {"company_id": company_id, "calendar_date": {"$in": list(dates)}, "status": {"$ne": "deleted"}}, NO_ID
    ).to_list(1000)
    return {r["calendar_date"]: r for r in rows}


def resolve_day_type(
    work_date: str, schedule: Optional[Dict[str, Any]], calendar_day: Optional[Dict[str, Any]]
) -> str:
    """Hari OFF/libur TIDAK boleh otomatis menjadi Alfa.

    Prioritas: hari kerja pengganti > libur (kalender) > OFF (jadwal) > hari kerja.
    Tidak ada hardcode Sabtu/Minggu — OFF berasal dari jadwal atau kalender.
    """
    cal_type = (calendar_day or {}).get("day_type")
    if cal_type == "workday_override":
        return "workday_override"
    if cal_type in HOLIDAY_DAY_TYPES:
        return cal_type
    if schedule and schedule.get("is_day_off"):
        return "weekly_off"
    if not schedule:
        return "workday"
    return "workday"


def is_working_day_type(day_type: str) -> bool:
    return day_type in ("workday", "workday_override")


# --------------------------------------------------------------------------
# Kebijakan Time Management per perusahaan
# --------------------------------------------------------------------------
async def get_time_policies(company_id: str) -> Dict[str, Any]:
    db = get_db()
    row = await db.time_policies.find_one({"company_id": company_id}, NO_ID) or {}
    return {
        "attendance": {**DEFAULT_ATTENDANCE_POLICY, **(row.get("attendance") or {})},
        "overtime": {**DEFAULT_OVERTIME_POLICY, **(row.get("overtime") or {})},
        "leave": {**DEFAULT_LEAVE_POLICY, **(row.get("leave") or {})},
    }


# --------------------------------------------------------------------------
# Tutup Periode (period lock)
# --------------------------------------------------------------------------
class PeriodLocked(HTTPException):
    def __init__(self, period_key: str):
        super().__init__(
            status.HTTP_409_CONFLICT,
            f"Periode {period_label_of(period_key)} sudah DITUTUP. "
            "Gunakan menu Tutup Periode lalu 'Buka Kembali Periode' dengan alasan "
            "bila data periode ini benar-benar harus diperbaiki.",
        )


async def closed_period_keys(company_id: str, keys: Iterable[str]) -> List[str]:
    keys = sorted({k for k in keys if k})
    if not keys:
        return []
    db = get_db()
    rows = await db.time_periods.find(
        {"company_id": company_id, "period_key": {"$in": list(keys)}, "period_status": "closed"}, NO_ID
    ).to_list(100)
    return [r["period_key"] for r in rows]


async def assert_period_open(company_id: str, *dates_or_keys: str) -> None:
    """Tolak perubahan pada periode yang sudah ditutup (HTTP 409, bukan 500)."""
    keys = {period_key_of(v) if len(str(v)) > 7 else str(v) for v in dates_or_keys if v}
    closed = await closed_period_keys(company_id, keys)
    if closed:
        raise PeriodLocked(sorted(closed)[0])


# --------------------------------------------------------------------------
# Resolusi status kehadiran
# --------------------------------------------------------------------------
def resolve_attendance_status(att: Dict[str, Any]) -> Tuple[str, bool]:
    """Kembalikan (status, is_valid). Status Cuti/Izin/Sakit berasal dari
    pengajuan yang DISETUJUI — bukan dari label Excel."""
    if att.get("leave_type_code") and att.get("leave_status"):
        return att["leave_status"], True

    day_type = att.get("day_type") or "workday"
    if att.get("location_approval_status") == "rejected":
        return "location_rejected", False
    if att.get("location_approval_status") == "pending":
        return "awaiting_location_approval", False

    has_in, has_out = bool(att.get("check_in_at")), bool(att.get("check_out_at"))
    if not has_in:
        if day_type in HOLIDAY_DAY_TYPES:
            return "holiday", True
        if day_type == "weekly_off":
            return "day_off", True
        if not att.get("shift_id") and not att.get("schedule_id"):
            return "no_schedule", True
        return "absent", True

    if not has_out:
        return "no_check_out", True

    late = int(att.get("late_minutes") or 0) > 0
    early = int(att.get("early_leave_minutes") or 0) > 0
    if late and early:
        return "late_and_early_leave", True
    if late:
        return "late", True
    if early:
        return "early_leave", True
    return "present", True


def decorate_attendance(att: Dict[str, Any]) -> Dict[str, Any]:
    """Tambahkan label Bahasa Indonesia untuk UI."""
    out = dict(att)
    out["attendance_status_label"] = status_label(att.get("attendance_status"))
    out["attendance_status_tone"] = ATTENDANCE_STATUSES.get(att.get("attendance_status") or "", {}).get("tone", "neutral")
    out["source_label"] = ATTENDANCE_SOURCES.get(att.get("source") or "", att.get("source") or "-")
    out["check_in_source_label"] = ATTENDANCE_SOURCES.get(att.get("check_in_source") or "", "-")
    out["check_out_source_label"] = ATTENDANCE_SOURCES.get(att.get("check_out_source") or "", "-")
    out["day_type_label"] = DAY_TYPES.get(att.get("day_type") or "", "-")
    out["geofence_policy_label"] = GEOFENCE_POLICIES.get(att.get("geofence_policy") or "", "-")
    out["check_in_geofence_label"] = GEOFENCE_RESULTS.get(att.get("check_in_geofence_result") or "", "-")
    out["check_out_geofence_label"] = GEOFENCE_RESULTS.get(att.get("check_out_geofence_result") or "", "-")
    out["location_approval_label"] = LOCATION_APPROVAL_STATUSES.get(att.get("location_approval_status") or "", "-")
    out["location_reason_label"] = LOCATION_REASON_CODES.get(att.get("location_reason_code") or "", None)
    out["check_out_location_reason_label"] = LOCATION_REASON_CODES.get(
        att.get("check_out_location_reason_code") or "", None)
    out["location_approval_for_label"] = LOCATION_APPROVAL_FOR.get(att.get("location_approval_for") or "", None)
    return out


def minutes_to_hhmm(total: Optional[int]) -> str:
    total = int(total or 0)
    return f"{total // 60}j {total % 60}m"


# --------------------------------------------------------------------------
# Privasi GPS — koordinat hanya untuk role yang berhak
# --------------------------------------------------------------------------
GPS_FIELDS = (
    "check_in_latitude", "check_in_longitude", "check_out_latitude", "check_out_longitude",
)


def redact_gps(att: Dict[str, Any], allowed: bool) -> Dict[str, Any]:
    """Sembunyikan koordinat presisi bila pengguna tidak punya izin.

    Jarak & hasil geofence tetap ditampilkan agar status kehadiran tetap
    dapat dipahami tanpa membuka lokasi persis karyawan.
    """
    if allowed:
        return att
    out = dict(att)
    for field in GPS_FIELDS:
        if out.get(field) is not None:
            out[field] = None
    out["gps_redacted"] = True
    return out
