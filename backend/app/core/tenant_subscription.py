"""Masa berlaku layanan tenant (subscription) - Tenant Foundation.

Dua konsep TERPISAH (tidak digabung dalam satu field):

A. Status Operasional  -> kolom existing `companies.status` (active / inactive),
   diatur manual oleh Platform Admin (Aktifkan / Nonaktifkan).
B. Status Masa Layanan -> TIDAK disimpan; selalu DIHITUNG dari tanggal:
     subscription_start_date, subscription_end_date, grace_period_days
   di tabel existing `companies` (kolom additive, nullable).

Aturan status masa layanan (tanggal = "hari ini" menurut zona waktu tenant):
  ACTIVE  : today <= end_date
  GRACE   : end_date < today <= end_date + grace_period_days
  EXPIRED : today >  end_date + grace_period_days

Kompatibilitas legacy (keputusan final):
  - end_date KOSONG  -> status ACTIVE dengan `unlimited = True` ("Tanpa batas / legacy").
    Tenant lama/demo TIDAK diblokir sampai Platform Admin mengatur periodenya.
  - grace_period_days KOSONG saat dihitung -> 0 hari. Saat Platform Admin menyimpan
    periode tanpa mengisi grace, nilai default diambil dari konfigurasi
    TENANT_DEFAULT_GRACE_PERIOD_DAYS lalu DISIMPAN per tenant.
  - start_date bersifat informasi periode; akses hanya ditentukan end_date + grace.

Aturan akses final (user tenant; Platform Admin selalu bypass):
  BLOCKED jika status operasional != active  ATAU  status masa layanan == EXPIRED.
  GRACE tetap boleh beroperasi (dengan peringatan).

Tahap pengingat (H-30 / H-14 / H-7 / H-1) dihitung di sini agar reminder
email/WA dapat ditambahkan nanti tanpa mengubah model data.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

SUB_ACTIVE = "active"
SUB_GRACE = "grace"
SUB_EXPIRED = "expired"

SUBSCRIPTION_FIELDS = ("subscription_start_date", "subscription_end_date", "grace_period_days", "subscription_notes")

# Ambang pengingat menjelang berakhir (hari sebelum end_date), dari terjauh ke terdekat.
REMINDER_THRESHOLDS = (30, 14, 7, 1)

STATUS_LABELS = {SUB_ACTIVE: "Aktif", SUB_GRACE: "Masa Tenggang", SUB_EXPIRED: "Berakhir"}


def parse_date(value: Any) -> Optional[date]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def tenant_today(company: Optional[Dict[str, Any]] = None) -> date:
    tz_name = (company or {}).get("timezone") or "Asia/Jakarta"
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo(tz_name)).date()
        except Exception:
            pass
    return (datetime.now(timezone.utc) + timedelta(hours=7)).date()


def reminder_stage(days_remaining: Optional[int]) -> Optional[str]:
    """'H-30' / 'H-14' / 'H-7' / 'H-1' untuk tenant ACTIVE yang mendekati end_date."""
    if days_remaining is None or days_remaining < 0:
        return None
    stage = None
    for t in REMINDER_THRESHOLDS:
        if days_remaining <= t:
            stage = f"H-{t}"
    return stage


def subscription_info(company: Optional[Dict[str, Any]], today: Optional[date] = None) -> Dict[str, Any]:
    c = company or {}
    today = today or tenant_today(c)
    start = parse_date(c.get("subscription_start_date"))
    end = parse_date(c.get("subscription_end_date"))
    raw_grace = c.get("grace_period_days")
    grace = max(0, int(raw_grace)) if raw_grace not in (None, "") else 0
    info: Dict[str, Any] = {
        "start_date": start.isoformat() if start else None,
        "end_date": end.isoformat() if end else None,
        "grace_period_days": raw_grace if raw_grace not in (None, "") else None,
        "grace_end_date": None,
        "notes": c.get("subscription_notes"),
        "unlimited": end is None,
        "status": SUB_ACTIVE,
        "days_remaining": None,
        "grace_days_remaining": None,
        "reminder_stage": None,
        "today": today.isoformat(),
    }
    if end is None:
        info["status_label"] = "Tanpa batas (legacy)"
        return info
    grace_end = end + timedelta(days=grace)
    info["grace_end_date"] = grace_end.isoformat()
    info["days_remaining"] = (end - today).days
    if today <= end:
        info["status"] = SUB_ACTIVE
        info["reminder_stage"] = reminder_stage(info["days_remaining"])
    elif today <= grace_end:
        info["status"] = SUB_GRACE
        info["grace_days_remaining"] = (grace_end - today).days
    else:
        info["status"] = SUB_EXPIRED
    info["status_label"] = STATUS_LABELS[info["status"]]
    return info


def is_subscription_expired(company: Optional[Dict[str, Any]]) -> bool:
    return subscription_info(company)["status"] == SUB_EXPIRED


def tenant_block_reason(company: Optional[Dict[str, Any]]) -> Optional[str]:
    """None = boleh beroperasi; 'inactive' / 'expired' = diblokir (untuk user tenant)."""
    if not company:
        return None
    if company.get("status") != "active":
        return "inactive"
    if is_subscription_expired(company):
        return "expired"
    return None
