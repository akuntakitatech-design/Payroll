"""Phase 2A CP1 - Manajemen Aset: aturan lifecycle, normalisasi identitas, validasi, seed master default,
validator master Status Aset, dan serialisasi aman (redaksi nilai perolehan).

Prinsip (ASSET_BAST_FINAL_BLUEPRINT.md):
- 1 baris aset = 1 unit fisik (tanpa kuantitas). Satuan hanya informasi.
- `lifecycle_state` = kategori sistem otoritatif; status tenant (`asset_statuses`) hanya label berkategori.
  Business logic TIDAK bergantung pada label/nama/kode status tenant.
- IN_USE dan PENDING_INSPECTION hanya lewat transaksi (CP berikutnya), tidak bisa dipilih manual.
- Tidak ada pengecekan nama role; semua otorisasi lewat permission.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict, Iterable, Optional

from fastapi import HTTPException

from . import doc_sequence
from .db import NO_ID, audit_fields, get_db, new_id

READY, IN_USE, PENDING_INSPECTION = "READY", "IN_USE", "PENDING_INSPECTION"
MAINTENANCE, DAMAGED, LOST, DISPOSED = "MAINTENANCE", "DAMAGED", "LOST", "DISPOSED"
LIFECYCLE_STATES = {
    READY: "Siap Pakai", IN_USE: "Dipakai", PENDING_INSPECTION: "Menunggu Pemeriksaan",
    MAINTENANCE: "Perbaikan", DAMAGED: "Rusak", LOST: "Hilang", DISPOSED: "Dihapuskan",
}
# State yang boleh dipilih saat membuat aset / diubah manual (bukan lewat transaksi) - blueprint §3.
MANUAL_STATES = (READY, MAINTENANCE, DAMAGED, LOST, DISPOSED)
# Transisi manual - blueprint §7 (kolom "Keluar ke" yang lewat "ubah status").
MANUAL_TRANSITIONS = {
    READY: {MAINTENANCE, DAMAGED, LOST, DISPOSED},
    MAINTENANCE: {READY, DAMAGED, DISPOSED},
    DAMAGED: {MAINTENANCE, DISPOSED},
    LOST: {READY, DISPOSED},
    DISPOSED: set(),            # terminal; pembatalan hanya oleh izin asset:delete (lihat check_transition)
    IN_USE: set(),              # hanya lewat Pengembalian (CP berikutnya)
    PENDING_INSPECTION: set(),  # hanya lewat Pemeriksaan (CP berikutnya)
}
TRANSACTION_LOCKED = (IN_USE, PENDING_INSPECTION)
ASSET_CODE_SEQ = "ASSET_CODE"
MAX_VALUE = Decimal("9999999999999999.99")  # DECIMAL(18,2)
CENT = Decimal("0.01")

DEFAULT_UNITS = [("UNIT", "Unit"), ("PCS", "Pcs"), ("SET", "Set"), ("PSG", "Pasang"), ("BUAH", "Buah"), ("PKT", "Paket")]
DEFAULT_CATEGORIES = [  # code, name, prefix, SN wajib, unit default
    ("LAPTOP", "Laptop", "LPT", True, "UNIT"), ("HP", "Handphone", "HP", True, "UNIT"),
    ("KENDARAAN", "Kendaraan", "KDR", True, "UNIT"), ("KAMERA", "Kamera", "KMR", True, "UNIT"),
    ("ALAT", "Alat Kerja", "ALT", False, "UNIT"), ("FURNITUR", "Furnitur", "FRN", False, "UNIT"),
    ("LAINNYA", "Lainnya", "LN", False, "UNIT"),
]
DEFAULT_CONDITIONS = [("BAIK", "Baik", True, 0), ("LECET", "Baik - Lecet Ringan", True, 1),
                      ("RUSAK_RINGAN", "Rusak Ringan", False, 5), ("RUSAK_BERAT", "Rusak Berat", False, 8),
                      ("HILANG", "Hilang", False, 9)]
DEFAULT_CONDITION_CODE = "BAIK"
STATE_COLORS = {READY: "success", IN_USE: "info", PENDING_INSPECTION: "warning", MAINTENANCE: "warning",
                DAMAGED: "danger", LOST: "danger", DISPOSED: "muted"}


def _err(code: int, msg: str) -> HTTPException:
    return HTTPException(code, msg)


# ------------------------------------------------------------------ normalisasi
def norm_code(value: Optional[str]) -> Optional[str]:
    v = re.sub(r"\s+", " ", (value or "").strip()).upper()
    return v or None


def norm_serial(value: Optional[str]) -> Optional[str]:
    v = re.sub(r"\s+", "", (value or "")).upper()
    return v or None


def clean_text(value: Any, max_len: int = 255) -> Optional[str]:
    if value is None:
        return None
    v = str(value).strip()
    if len(v) > max_len:
        raise _err(422, f"Teks melebihi {max_len} karakter.")
    return v or None


def parse_value(raw: Any) -> Optional[Decimal]:
    """Nilai perolehan: desimal >= 0, maksimal 2 angka di belakang koma, <= DECIMAL(18,2). Tidak lewat float."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    if isinstance(raw, bool):
        raise _err(422, "Nilai perolehan tidak valid.")
    try:
        d = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        raise _err(422, "Nilai perolehan harus berupa angka.")
    if not d.is_finite() or d < 0:
        raise _err(422, "Nilai perolehan harus angka >= 0.")
    if d != d.quantize(CENT):
        raise _err(422, "Nilai perolehan maksimal 2 angka di belakang koma.")
    if d > MAX_VALUE:
        raise _err(422, "Nilai perolehan melebihi batas maksimum.")
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def format_value(v: Any) -> Optional[str]:
    if v is None:
        return None
    return str(Decimal(str(v)).quantize(CENT))


def parse_acquisition(date_raw: Any, year_raw: Any, *, current: Optional[Dict[str, Any]] = None,
                      date_given: bool = True, year_given: bool = True) -> Dict[str, Any]:
    """Tanggal + tahun perolehan. Tahun boleh tanpa tanggal; jika tanggal ada, tahun mengikuti tanggal;
    keduanya diisi tapi tidak konsisten -> 422. Tahun TIDAK dihapus hanya karena tanggal dikosongkan."""
    out: Dict[str, Any] = {}
    today = date.today()
    d_val: Optional[str] = (current or {}).get("acquisition_date")
    y_val: Optional[int] = (current or {}).get("acquisition_year")
    if date_given:
        s = (str(date_raw).strip() if date_raw is not None else "")
        if s:
            try:
                dd = date.fromisoformat(s[:10])
            except ValueError:
                raise _err(422, "Tanggal perolehan tidak valid (format YYYY-MM-DD).")
            if dd > today:
                raise _err(422, "Tanggal perolehan tidak boleh di masa depan.")
            d_val = dd.isoformat()
        else:
            d_val = None
        out["acquisition_date"] = d_val
    if year_given:
        if year_raw is None or (isinstance(year_raw, str) and not year_raw.strip()):
            y_val = None
        else:
            try:
                y = int(str(year_raw).strip())
            except ValueError:
                raise _err(422, "Tahun perolehan harus 4 digit angka.")
            if not (1900 <= y <= today.year):
                raise _err(422, f"Tahun perolehan harus antara 1900 dan {today.year}.")
            y_val = y
    if d_val:
        dy = int(d_val[:4])
        if year_given and y_val is not None and y_val != dy:
            raise _err(422, "Tahun perolehan tidak sesuai dengan tanggal perolehan.")
        y_val = dy
    if year_given or date_given:
        out["acquisition_year"] = y_val
    return out


# ------------------------------------------------------------------ seed master default (idempoten)
async def seed_defaults(company_id: str, actor_id: Optional[str]) -> Dict[str, int]:
    """Hanya menambah master default yang kodenya belum ada. Tidak menimpa/menghidupkan ulang perubahan tenant."""
    db = get_db()
    added = {"units": 0, "categories": 0, "conditions": 0, "statuses": 0}

    async def _ins(coll: str, key: str, doc: Dict[str, Any]) -> None:
        if await db[coll].count_documents({"company_id": company_id, "code": doc["code"]}):
            return
        try:
            await db[coll].insert_one({"id": new_id(), "company_id": company_id, "status": "active", **doc,
                                       **audit_fields(actor_id, creating=True)})
            added[key] += 1
        except HTTPException as exc:
            if exc.status_code != 409:
                raise

    for i, (code, name) in enumerate(DEFAULT_UNITS):
        await _ins("asset_units", "units", {"code": code, "name": name, "sort_order": i + 1})
    units = {u["code"]: u["id"] for u in await db.asset_units.find({"company_id": company_id}, NO_ID).to_list(500)}
    for i, (code, name, prefix, sn, unit) in enumerate(DEFAULT_CATEGORIES):
        await _ins("asset_categories", "categories", {"code": code, "name": name, "code_prefix": prefix,
                                                      "serial_number_required": sn, "default_unit_id": units.get(unit),
                                                      "sort_order": i + 1})
    for i, (code, name, usable, sev) in enumerate(DEFAULT_CONDITIONS):
        await _ins("asset_conditions", "conditions", {"code": code, "name": name, "is_usable": usable, "severity": sev,
                                                      "sort_order": i + 1})
    for i, (state, label) in enumerate(LIFECYCLE_STATES.items()):
        # Default hanya bila kategori sistem ini belum punya status default aktif (tidak mengganggu konfigurasi tenant).
        has_default = await db.asset_statuses.count_documents(
            {"company_id": company_id, "system_state": state, "is_default": True, "status": "active"})
        await _ins("asset_statuses", "statuses", {"code": state, "name": label, "system_state": state,
                                                  "is_default": not has_default, "color": STATE_COLORS[state],
                                                  "sort_order": i + 1})
    await doc_sequence.get_config(company_id, ASSET_CODE_SEQ, actor_id)
    return added


# ------------------------------------------------------------------ validator master Status Aset
async def _status_row(company_id: str, record_id: str) -> Optional[Dict[str, Any]]:
    return await get_db().asset_statuses.find_one({"company_id": company_id, "id": record_id}, NO_ID)


async def _other_active(company_id: str, state: str, exclude_id: str) -> int:
    return await get_db().asset_statuses.count_documents(
        {"company_id": company_id, "system_state": state, "status": "active", "id": {"$ne": exclude_id}})


async def validate_status_master(company_id: str, op: str, data: Dict[str, Any], record_id: Optional[str]) -> None:
    """Menjaga pemetaan kategori sistem tetap valid:
    - setiap kategori sistem harus selalu punya >= 1 status aktif dan tepat 1 default aktif;
    - kategori sistem tidak dapat diubah bila status sudah dipakai aset;
    - status default tidak dapat dinonaktifkan/dihapus/dilepas default-nya (tetapkan status lain sebagai default)."""
    db = get_db()
    cur = await _status_row(company_id, record_id) if record_id else None
    if op == "create":
        if data.get("is_default") and (data.get("status") or "active") != "active":
            raise _err(422, "Status default harus berstatus aktif.")
        return
    if not cur:
        return  # engine akan mengembalikan 404
    state = cur.get("system_state")
    is_default = bool(cur.get("is_default"))
    if op == "update":
        if "system_state" in data and data["system_state"] != state:
            if await db.assets.count_documents({"company_id": company_id, "status_id": record_id}):
                raise _err(409, "Kategori sistem tidak dapat diubah karena status ini sudah dipakai aset.")
            if is_default or not await _other_active(company_id, state, record_id):
                raise _err(422, f"Status ini adalah status default/terakhir untuk kategori sistem {state}. "
                                "Tetapkan status lain sebagai default terlebih dahulu.")
        if "is_default" in data and not data["is_default"] and is_default:
            raise _err(422, "Setiap kategori sistem wajib punya satu status default. "
                            "Tetapkan status lain sebagai default; status ini akan dilepas otomatis.")
        if data.get("is_default") and (data.get("status") or cur.get("status")) != "active":
            raise _err(422, "Status default harus berstatus aktif. Aktifkan status ini terlebih dahulu.")
        if data.get("status") not in ("inactive", "archived"):
            return
    if op in ("status", "delete", "update"):
        deactivating = op == "delete" or data.get("status") in ("inactive", "archived")
        if not deactivating:
            return
        if is_default:
            raise _err(422, "Status default tidak dapat dinonaktifkan/dihapus. "
                            "Tetapkan status lain sebagai default terlebih dahulu.")
        if cur.get("status") == "active" and not await _other_active(company_id, state, record_id):
            raise _err(422, f"Kategori sistem {state} wajib punya minimal satu status aktif.")


async def after_status_master_saved(company_id: str, record: Dict[str, Any]) -> None:
    """Setelah simpan: bila record menjadi default, default lain pada kategori sistem yang sama dilepas."""
    if record and record.get("is_default"):
        await get_db().asset_statuses.update_many(
            {"company_id": company_id, "system_state": record.get("system_state"), "is_default": True,
             "id": {"$ne": record["id"]}},
            {"$set": {"is_default": False}})


MASTER_VALIDATORS = {"asset_status": validate_status_master}
MASTER_POST_HOOKS = {"asset_status": after_status_master_saved}


async def default_status_for(company_id: str, state: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    q = {"company_id": company_id, "system_state": state, "status": "active"}
    return (await db.asset_statuses.find_one({**q, "is_default": True}, NO_ID)
            or await db.asset_statuses.find_one(q, NO_ID))


def check_transition(from_state: str, to_state: str, *, can_revert_disposal: bool, revert_target: Optional[str]) -> None:
    if from_state == to_state:
        return  # ganti label dalam kategori sistem yang sama
    if to_state not in MANUAL_STATES:
        raise _err(409, f"Status berkategori {to_state} hanya dapat terjadi lewat transaksi, bukan diubah manual.")
    if from_state in TRANSACTION_LOCKED:
        raise _err(409, f"Aset berstatus {LIFECYCLE_STATES[from_state]} hanya dapat berubah lewat transaksi.")
    if from_state == DISPOSED:
        if not can_revert_disposal:
            raise _err(409, "Aset yang sudah Dihapuskan bersifat final. Pembatalan hanya oleh pengguna berizin hapus aset.")
        if revert_target and to_state != revert_target:
            raise _err(409, f"Pembatalan penghapusan hanya dapat mengembalikan aset ke status sebelumnya ({revert_target}).")
        return
    if to_state not in MANUAL_TRANSITIONS.get(from_state, set()):
        raise _err(409, f"Perubahan status dari {from_state} ke {to_state} tidak diizinkan.")


# ------------------------------------------------------------------ serialisasi aman
SAFE_AUDIT_EXCLUDE = {"acquisition_value", "asset_code_norm", "serial_number_norm", "extra", "_id"}


def audit_view(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Representasi untuk audit log: TANPA nilai perolehan mentah (hanya penanda ada/tidak)."""
    if doc is None:
        return None
    out = {k: v for k, v in doc.items() if k not in SAFE_AUDIT_EXCLUDE}
    out["acquisition_value_set"] = doc.get("acquisition_value") is not None
    return out


async def label_maps(company_id: str, docs: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    docs = list(docs)
    db = get_db()
    spec = {"category_id": "asset_categories", "unit_id": "asset_units", "condition_id": "asset_conditions",
            "status_id": "asset_statuses", "project_id": "projects", "work_location_id": "work_locations"}
    maps: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for field, coll in spec.items():
        ids = sorted({d.get(field) for d in docs if d.get(field)})
        rows = await db[coll].find({"company_id": company_id, "id": {"$in": ids}}, NO_ID).to_list(len(ids) + 1) if ids else []
        maps[field] = {r["id"]: r for r in rows}
    return maps


def present(doc: Dict[str, Any], maps: Dict[str, Dict[str, Dict[str, Any]]], *, can_view_value: bool,
            include_value: bool = True) -> Dict[str, Any]:
    """Output API aset. `acquisition_value` HANYA disertakan bila pemanggil punya izin asset_value:view
    (redaksi di backend: key dihapus, bukan dikosongkan di frontend)."""
    out = {k: v for k, v in doc.items() if k not in ("acquisition_value", "extra", "_id")}
    for field in ("category_id", "unit_id", "condition_id", "status_id", "project_id", "work_location_id"):
        ref = maps.get(field, {}).get(doc.get(field) or "")
        base = field[:-3]
        out[f"{base}_name"] = ref.get("name") if ref else None
        if field in ("project_id", "work_location_id", "category_id"):
            out[f"{base}_code"] = ref.get("code") if ref else None
    st = maps.get("status_id", {}).get(doc.get("status_id") or "")
    out["status_color"] = (st or {}).get("color") or STATE_COLORS.get(doc.get("lifecycle_state"))
    out["lifecycle_label"] = LIFECYCLE_STATES.get(doc.get("lifecycle_state"))
    if can_view_value and include_value:
        out["acquisition_value"] = format_value(doc.get("acquisition_value"))
    return out
