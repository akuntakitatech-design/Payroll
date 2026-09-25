"""Upgrade 01B - Status Karyawan (status bisnis) + riwayat.

Konsep:
- 3 kategori sistem TERKUNCI (tidak bisa ditambah/dihapus/diganti nama tenant):
  ACTIVE (UI: AKTIF) | STANDBY (UI: STANDBY) | INACTIVE (UI: TIDAK AKTIF).
- Master status bisnis per tenant (`employee_business_statuses`) dipetakan ke salah
  satu kategori. Default per tenant: AKTIF / STANDBY / TIDAK_AKTIF.
- `employees.current_employee_status_id` = status bisnis saat ini.
- `employees.status` (legacy active/inactive/archived/deleted) TETAP dipakai modul
  lain; disinkronkan lewat compatibility bridge: ACTIVE/STANDBY -> active,
  INACTIVE -> inactive. `archived`/`deleted` tidak pernah diubah oleh status bisnis.
- `employment_status_id` (PKWT/PKWTT) adalah konsep berbeda dan tidak disentuh.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from .db import NO_ID, audit_fields, get_db, new_id, now

CATEGORIES: Dict[str, str] = {"ACTIVE": "AKTIF", "STANDBY": "STANDBY", "INACTIVE": "TIDAK AKTIF"}
CATEGORY_ORDER = ["ACTIVE", "STANDBY", "INACTIVE"]
LEGACY_BY_CATEGORY: Dict[str, str] = {"ACTIVE": "active", "STANDBY": "active", "INACTIVE": "inactive"}
# Status legacy yang TIDAK boleh diubah oleh status bisnis (lifecycle teknis).
TECHNICAL_LEGACY = {"archived", "deleted"}

DEFAULT_STATUSES: List[Dict[str, Any]] = [
    {"code": "AKTIF", "name": "Aktif", "system_category": "ACTIVE", "sort_order": 1,
     "description": "Status default: karyawan aktif bekerja."},
    {"code": "STANDBY", "name": "Standby", "system_category": "STANDBY", "sort_order": 2,
     "description": "Status default: karyawan dalam pool perusahaan, menunggu penempatan."},
    {"code": "TIDAK_AKTIF", "name": "Tidak Aktif", "system_category": "INACTIVE", "sort_order": 3,
     "description": "Status default: karyawan tidak lagi aktif (resign, PHK, pensiun, dll.)."},
]
DEFAULT_CODE_BY_CATEGORY = {d["system_category"]: d["code"] for d in DEFAULT_STATUSES}

SOURCES = ("MANUAL", "LEGACY_BASELINE", "IMPORT", "SYSTEM")
TABLE = "employee_business_statuses"
HISTORY = "employee_status_history"
TZ = ZoneInfo("Asia/Jakarta")


def today_local() -> str:
    """Tanggal hari ini (WIB) format YYYY-MM-DD - batas atas tanggal efektif."""
    return datetime.now(TZ).date().isoformat()


def category_label(category: Optional[str]) -> Optional[str]:
    return CATEGORIES.get(category or "")


def legacy_for(category: str) -> str:
    return LEGACY_BY_CATEGORY[category]


def default_category_for_legacy(legacy: Optional[str]) -> Optional[str]:
    """Pemetaan legacy -> kategori default. active -> ACTIVE; inactive/archived/deleted ->
    INACTIVE. Nilai lain -> None (dilaporkan, tidak dipaksakan)."""
    if legacy == "active":
        return "ACTIVE"
    if legacy in ("inactive", "archived", "deleted"):
        return "INACTIVE"
    return None


async def ensure_default_statuses(company_id: str, user_id: Optional[str] = None,
                                  apply: bool = True) -> List[str]:
    """Pastikan 3 status default tenant ada (idempotent). Kembalikan kode yang dibuat."""
    db = get_db()
    created: List[str] = []
    for d in DEFAULT_STATUSES:
        exists = await db[TABLE].count_documents({"company_id": company_id, "code": d["code"]})
        if exists:
            continue
        created.append(d["code"])
        if apply:
            await db[TABLE].insert_one({
                "id": new_id(), "company_id": company_id, "status": "active",
                "is_active": True, "is_default": True, **d, **audit_fields(user_id, creating=True),
            })
    return created


async def default_status(company_id: str, category: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    row = await db[TABLE].find_one(
        {"company_id": company_id, "code": DEFAULT_CODE_BY_CATEGORY[category], "is_default": True}, NO_ID
    )
    if not row:
        row = await db[TABLE].find_one(
            {"company_id": company_id, "system_category": category, "is_active": True}, NO_ID
        )
    return row


def history_doc(company_id: str, employee_id: str, new_status: Dict[str, Any],
                previous: Optional[Dict[str, Any]], *, effective_date: Optional[str], reason: str,
                notes: Optional[str], source: str, actor_id: Optional[str], actor_name: Optional[str],
                legacy_before: Optional[str], legacy_after: Optional[str]) -> Dict[str, Any]:
    ts = now()
    return {
        "id": new_id(), "company_id": company_id, "status": "active", "employee_id": employee_id,
        "previous_status_id": previous.get("id") if previous else None,
        "new_status_id": new_status["id"],
        "previous_category": previous.get("system_category") if previous else None,
        "new_category": new_status.get("system_category"),
        "effective_date": effective_date, "reason": reason, "notes": notes, "source": source,
        "changed_by": actor_id, "changed_by_name": actor_name,
        "legacy_status_before": legacy_before, "legacy_status_after": legacy_after,
        "created_at": ts, "updated_at": ts, "created_by": actor_id, "updated_by": actor_id,
    }


async def prepare_new_employee(company_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Dipanggil SEBELUM insert karyawan baru (create/import/konversi kandidat):
    buang field status bisnis dari payload, pasang status default sesuai legacy status."""
    data.pop("current_employee_status_id", None)
    legacy = data.get("status") or "active"
    category = default_category_for_legacy(legacy) or "ACTIVE"
    status_row = await default_status(company_id, category)
    if status_row:
        data["current_employee_status_id"] = status_row["id"]
    return status_row


async def record_initial_history(company_id: str, employee: Dict[str, Any],
                                 status_row: Optional[Dict[str, Any]], source: str,
                                 actor_id: Optional[str], actor_name: Optional[str],
                                 reason: str) -> None:
    """Riwayat awal karyawan baru. Tanggal efektif = tanggal pencatatan (fakta),
    bukan tanggal karangan."""
    if not status_row:
        return
    await get_db()[HISTORY].insert_one(history_doc(
        company_id, employee["id"], status_row, None, effective_date=today_local(), reason=reason,
        notes=None, source=source, actor_id=actor_id, actor_name=actor_name,
        legacy_before=None, legacy_after=employee.get("status") or "active",
    ))


async def backfill_company(company_id: str, apply: bool = True) -> Dict[str, Any]:
    """Backfill karyawan tenant yang belum punya status bisnis (idempotent).

    active -> Aktif; inactive/archived/deleted -> Tidak Aktif. Legacy `status` TIDAK
    diubah (archived tetap archived, deleted tetap deleted). Riwayat awal ditandai
    source=LEGACY_BASELINE tanpa tanggal efektif (tidak mengarang tanggal historis).
    """
    db = get_db()
    rows = await db.employees.find(
        {"company_id": company_id, "$or": [{"current_employee_status_id": None},
                                           {"current_employee_status_id": {"$exists": False}}]},
        {"_id": 0, "id": 1, "status": 1, "full_name": 1},
    ).to_list(100000)
    defaults = {c: await default_status(company_id, c) for c in CATEGORY_ORDER}
    counts: Dict[str, int] = {}
    unmapped: List[Dict[str, Any]] = []
    for e in rows:
        legacy = e.get("status")
        category = default_category_for_legacy(legacy)
        target = defaults.get(category) if category else None
        if not target:
            unmapped.append({"employee_id": e["id"], "legacy_status": legacy})
            continue
        counts[legacy] = counts.get(legacy, 0) + 1
        if apply:
            # Hanya isi kolom status bisnis; kolom legacy & updated_* tidak disentuh.
            await db.employees.update_one(
                {"company_id": company_id, "id": e["id"], "current_employee_status_id": None},
                {"$set": {"current_employee_status_id": target["id"]}},
            )
            await db[HISTORY].insert_one(history_doc(
                company_id, e["id"], target, None, effective_date=None,
                reason=f"Baseline migrasi dari status legacy '{legacy}'", notes=None,
                source="LEGACY_BASELINE", actor_id=None, actor_name=None,
                legacy_before=legacy, legacy_after=legacy,
            ))
    return {"company_id": company_id, "backfilled_by_legacy": counts, "unmapped": unmapped}


async def usage_counts(company_id: str, status_ids: List[str]) -> Dict[str, Dict[str, int]]:
    """Jumlah penggunaan per status: karyawan saat ini + referensi riwayat."""
    db = get_db()
    out = {sid: {"current": 0, "history": 0} for sid in status_ids}
    if not status_ids:
        return out
    emps = await db.employees.find(
        {"company_id": company_id, "current_employee_status_id": {"$in": status_ids},
         "status": {"$ne": "deleted"}},
        {"_id": 0, "current_employee_status_id": 1},
    ).to_list(100000)
    for e in emps:
        out[e["current_employee_status_id"]]["current"] += 1
    hist = await db[HISTORY].find(
        {"company_id": company_id, "$or": [{"new_status_id": {"$in": status_ids}},
                                           {"previous_status_id": {"$in": status_ids}}]},
        {"_id": 0, "new_status_id": 1, "previous_status_id": 1},
    ).to_list(200000)
    for h in hist:
        for key in ("new_status_id", "previous_status_id"):
            if h.get(key) in out:
                out[h[key]]["history"] += 1
    return out


async def is_status_used(company_id: str, status_id: str) -> bool:
    """Pernah dipakai = masih jadi status karyawan (termasuk terhapus/arsip) atau ada di riwayat."""
    db = get_db()
    if await db.employees.count_documents({"company_id": company_id,
                                           "current_employee_status_id": status_id}):
        return True
    return bool(await db[HISTORY].count_documents(
        {"company_id": company_id, "$or": [{"new_status_id": status_id}, {"previous_status_id": status_id}]}
    ))
