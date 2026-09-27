"""Upgrade 01F - Service evaluasi Kelengkapan Data (SATU service).

- `load_rules`   : katalog efektif tenant (default katalog + override level + scope) + rules_hash.
- `load_context` : bulk loader (1 query per tabel per chunk; tanpa N+1) untuk sekumpulan karyawan.
- `evaluate`     : fungsi murni (tanpa I/O) -> item per requirement + skor.
- `refresh`      : evaluasi + UPSERT snapshot `employee_completeness` (hanya kode/status/skor), per chunk 500.
- `safe_refresh` : dipanggil dari trigger bisnis SETELAH transaksi selesai. Tidak pernah melempar error;
                   bila gagal -> snapshot ditandai `is_stale` + log tipe error saja (tanpa nilai data).
- `schedule_tenant_refresh` : evaluasi ulang seluruh tenant di latar belakang, digabung (coalesced) per tenant
                   sehingga banyak perubahan rule beruntun tidak memicu banyak evaluasi penuh paralel.
Formula (keputusan user): skor = WAJIB terpenuhi / WAJIB applicable x 100. ANJURAN tidak menurunkan skor,
NONAKTIF / tidak berlaku tidak masuk penyebut. 100% = LENGKAP, selain itu BELUM_LENGKAP.

Konkurensi: snapshot ditulis dengan INSERT ... ON DUPLICATE KEY UPDATE pada unique index existing
`ux_employee_completeness_emp (company_id, employee_id)` (dibuat m0007; tidak butuh schema baru). Update hanya
diterapkan bila hasil baru dibaca dari data yang sama/lebih baru (`evaluated_at` >= snapshot tersimpan).
Deadlock/lock-wait (MariaDB 1213/1205) antara UPDATE stale se-tenant dan upsert per chunk: kedua sisi mengunci baris
berurutan `employee_id` (urutan kunci sama) + retry terbatas dengan backoff kecil (operasi idempotent).
Perubahan konfigurasi (rule/scope): mutasi utama + audit dalam SATU transaksi (retry aman karena di-rollback penuh);
side-effect (stale + evaluasi ulang tenant) dijalankan SETELAH commit dan tidak pernah menggagalkan respons.
"""
import asyncio
import hashlib
import json
import logging
import random
from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Set

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import insert as mysql_insert

from . import completeness_mapping as M
from .db import NO_ID, _doc_to_row, _guard_write, get_db, get_engine, get_table, new_id, now, transaction
from .expiry import days_left
from .field_validators import blank, check as validate
from .tenancy import get_tenant_db

logger = logging.getLogger(__name__)

SNAP = "employee_completeness"
EXCLUDED_EMP_STATUS = {"deleted", "archived"}
INACTIVE_DOC_STATUS = {"deleted", "archived", "inactive"}
CHUNK = 500
# kolom yang di-update saat snapshot sudah ada (evaluated_at WAJIB terakhir: MariaDB mengevaluasi SET berurutan)
_UPSERT_COLS = ["status", "score_pct", "completeness_status", "required_total", "required_fulfilled",
                "recommended_total", "recommended_fulfilled", "missing_codes", "recommended_missing_codes", "items",
                "catalog_version", "rules_hash", "evaluated_trigger", "is_stale", "stale_reason", "updated_at",
                "updated_by", "extra", "evaluated_at"]


# ------------------------------------------------------------------ konflik kunci DB (deadlock / lock wait)
LOCK_CONFLICT_CODES = {1213, 1205}  # ER_LOCK_DEADLOCK, ER_LOCK_WAIT_TIMEOUT -> transaksi/statement di-rollback server
LOCK_RETRY_ATTEMPTS = 5
LOCK_RETRY_BASE_DELAY = 0.05  # detik; backoff eksponensial + jitter: ~0.05-0.1, 0.1-0.2, 0.2-0.4, 0.4-0.8 (maks ~1.5 dtk)


class ConfigBusyError(Exception):
    """Mutasi konfigurasi utama gagal karena konflik kunci DB setelah retry (TIDAK tersimpan)."""


def is_lock_conflict(exc: BaseException) -> bool:
    seen: Set[int] = set()
    e: Optional[BaseException] = exc
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        for cand in (e, getattr(e, "orig", None)):
            args = getattr(cand, "args", None) or ()
            if args and isinstance(args[0], int) and args[0] in LOCK_CONFLICT_CODES:
                return True
        e = e.__cause__ or e.__context__
    return False


async def with_lock_retry(fn: Callable[[], Awaitable[Any]], what: str, attempts: int = LOCK_RETRY_ATTEMPTS,
                          base_delay: float = LOCK_RETRY_BASE_DELAY) -> Any:
    """Jalankan `fn` (HARUS idempotent / satu transaksi utuh); ulangi hanya bila konflik kunci DB."""
    for i in range(attempts):
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001
            if i == attempts - 1 or not is_lock_conflict(exc):
                raise
            logger.info("Konflik kunci DB pada %s (percobaan %s/%s) - dicoba ulang", what, i + 1, attempts)
            await asyncio.sleep(base_delay * (2 ** i) * (1 + random.random()))


def _chunks(items: List[Any], size: int = CHUNK) -> Iterable[List[Any]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _today() -> str:
    return date.today().isoformat()


def _in_effect(row: Dict[str, Any], today: str) -> bool:
    ef, et = (row.get("effective_from") or "")[:10], (row.get("effective_to") or "")[:10]
    return (not ef or ef <= today) and (not et or et >= today)


# ------------------------------------------------------------------ loader
async def load_rules(company_id: str) -> Dict[str, Any]:
    db = get_tenant_db(company_id)
    q = {"company_id": company_id, "status": {"$ne": "deleted"}}
    doc_types = await db.document_types.find(q, NO_ID).to_list(1000)
    cert_types = await db.certification_types.find(q, NO_ID).to_list(1000)
    rules = await db.completeness_rules.find(q, NO_ID).to_list(2000)
    scopes = await db.completeness_rule_scopes.find(q, NO_ID).to_list(5000)
    reqs = M.STATIC_REQUIREMENTS + M.dynamic_requirements(doc_types, cert_types)
    levels = {r["requirement_code"]: r.get("level") for r in rules if r.get("level") in M.LEVELS}
    by_code: Dict[str, List[Dict[str, Any]]] = {}
    for s in scopes:
        by_code.setdefault(s.get("requirement_code"), []).append(s)
    # master yang memengaruhi applicability ikut ke hash -> perubahan master terdeteksi sebagai "menunggu evaluasi"
    lk = await _load_lookups(company_id)
    sig = json.dumps({"v": M.CATALOG_VERSION, "req": sorted((r.code, r.default_level, r.applicability, r.ref_id or "",
                                     json.dumps(r.extra, sort_keys=True)) for r in reqs),
                      "lk": [sorted((k, v or "") for k, v in lk["business_category"].items()),
                             sorted(lk["requires_contract"].items())],
                      "lv": sorted(levels.items()),
                      "sc": sorted((s.get("requirement_code"), s.get("scope_type"), s.get("scope_id") or "", s.get("mode"),
                                    s.get("effective_from") or "", s.get("effective_to") or "") for s in scopes)}, default=str)
    return {"requirements": reqs, "levels": levels, "scopes": by_code,
            "rules_hash": hashlib.sha256(sig.encode()).hexdigest()[:32]}


async def load_context(company_id: str, employee_ids: List[str], rules: Optional[Dict[str, Any]] = None,
                       lookups: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Muat data sumber untuk <= CHUNK karyawan (dipanggil per chunk oleh `refresh`)."""
    db = get_tenant_db(company_id)
    rules = rules or await load_rules(company_id)
    lookups = lookups or await _load_lookups(company_id)
    ctx: Dict[str, Any] = {"employees": [], **rules, **lookups, "today": _today()}
    idx: Dict[str, Dict[str, Any]] = {k: {} for k in ("assign", "family", "docs", "contracts", "certs", "salary")}
    ctx.update(idx)
    if not employee_ids:
        return ctx
    ctx["employees"] = await db.employees.find({"company_id": company_id, "id": {"$in": list(employee_ids)},
                                                "status": {"$nin": list(EXCLUDED_EMP_STATUS)}}, NO_ID).to_list(len(employee_ids))
    ids = [e["id"] for e in ctx["employees"]]
    if not ids:
        return ctx
    base = {"company_id": company_id, "employee_id": {"$in": ids}}
    for a in await db.employee_assignments.find({**base, "assignment_status": "ACTIVE"}, NO_ID).to_list(100000):
        idx["assign"][a["employee_id"]] = a
    for f in await db.employee_family_members.find({**base, "status": {"$ne": "deleted"}}, NO_ID).to_list(100000):
        idx["family"].setdefault(f["employee_id"], []).append(f)
    for c in await db.employee_contracts.find({**base, "status": {"$ne": "deleted"}}, NO_ID).to_list(100000):
        idx["contracts"].setdefault(c["employee_id"], []).append(c)
    for c in await db.employee_certifications.find({**base, "status": {"$ne": "deleted"}}, NO_ID).to_list(100000):
        idx["certs"].setdefault(c["employee_id"], []).append(c)
    for s in await db.employee_salaries.find(base, NO_ID).to_list(100000):
        idx["salary"][s["employee_id"]] = s
    for d in await db.documents.find({"company_id": company_id, "owner_type": "employee", "owner_id": {"$in": ids},
                                      "is_deleted": {"$ne": True}}, NO_ID).to_list(100000):
        idx["docs"].setdefault(d["owner_id"], []).append(d)
    return ctx


async def _load_lookups(company_id: str) -> Dict[str, Any]:
    db = get_tenant_db(company_id)
    return {
        "business_category": {s["id"]: s.get("system_category") for s in
                              await db.employee_business_statuses.find({"company_id": company_id}, NO_ID).to_list(500)},
        "requires_contract": {s["id"]: bool(s.get("requires_contract")) for s in
                              await db.employment_statuses.find({"company_id": company_id}, NO_ID).to_list(500)},
    }


# ------------------------------------------------------------------ evaluate (murni)
def _scope_value(emp: Dict[str, Any], ctx: Dict[str, Any], scope_type: str) -> Optional[str]:
    if scope_type == "business_status_category":
        return ctx["business_category"].get(emp.get("current_employee_status_id"))
    if scope_type == "employee_status":  # status karyawan 01B spesifik (mis. "Project Selesai - Standby")
        return emp.get("current_employee_status_id")
    if scope_type == "project":
        a = ctx["assign"].get(emp["id"])
        return (a or {}).get("project_id") or emp.get("project_id")
    return emp.get(f"{scope_type}_id")


def _default_applicable(req: M.Requirement, emp: Dict[str, Any], ctx: Dict[str, Any], category: Optional[str]) -> bool:
    sal = ctx["salary"].get(emp["id"])
    app = req.applicability
    if app == "all":
        return True
    if app == "active_category":
        return category == "ACTIVE"
    if app == "has_salary":
        return sal is not None
    if app == "has_npwp":
        return bool(sal and sal.get("has_npwp"))
    if app == "bpjs_kes":
        return bool(sal and sal.get("bpjs_kesehatan_enrolled"))
    if app == "bpjs_tk":
        return bool(sal and (sal.get("bpjs_jht_enrolled") or sal.get("bpjs_jp_enrolled")))
    if app == "married":
        return (emp.get("marital_status") or "").lower() == "married"
    if app == "requires_contract":
        return ctx["requires_contract"].get(emp.get("employment_status_id"), False)
    if app == "scoped_only":
        return False  # hanya berlaku lewat scope INCLUDE yang cocok
    return True


def _applicable(req: M.Requirement, emp: Dict[str, Any], ctx: Dict[str, Any], category: Optional[str]) -> bool:
    scopes = [s for s in ctx["scopes"].get(req.code, []) if _in_effect(s, ctx["today"])]

    def match(s):
        return s.get("scope_type") == "company" or (_scope_value(emp, ctx, s.get("scope_type")) or "") == (s.get("scope_id") or "-")
    if any(s.get("mode") == "EXCLUDE" and match(s) for s in scopes):
        return False
    includes = [s for s in scopes if s.get("mode") == "INCLUDE"]
    if includes:
        if not any(match(s) for s in includes):
            return False
        return True if req.applicability == "scoped_only" else _default_applicable(req, emp, ctx, category)
    return _default_applicable(req, emp, ctx, category)


def _expiry_status(rows: List[Dict[str, Any]], date_key: str) -> Dict[str, Any]:
    valid, expired = [], []
    for r in rows:
        left = days_left(r.get(date_key))
        (expired if left is not None and left < 0 else valid).append(r)
    if valid:
        dates = sorted(str(r.get(date_key)) for r in valid if r.get(date_key))
        return {"status": M.COMPLETE, "expires_on": dates[-1][:10] if dates else None}
    return {"status": M.EXPIRED if expired else M.MISSING}


def _check(req: M.Requirement, emp: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    eid = emp["id"]
    kind = req.check
    if kind in ("field", "all_fields"):
        vals = [emp.get(f) for f in req.fields]
        if any(blank(v) for v in vals):
            return {"status": M.MISSING}
        if not all(validate(vk, v) for vk, v in zip(req.validators or (None,) * len(vals), vals)):
            return {"status": M.INVALID}
        return {"status": M.COMPLETE}
    if kind == "emergency":
        if not blank(emp.get("emergency_contact_name")) and not blank(emp.get("emergency_contact_phone")):
            return {"status": M.COMPLETE}
        fam = any(f.get("is_emergency_contact") and not blank(f.get("phone")) for f in ctx["family"].get(eid, []))
        return {"status": M.COMPLETE if fam else M.MISSING}
    if kind == "assignment":
        return {"status": M.COMPLETE if ctx["assign"].get(eid) else M.MISSING}
    if kind == "spouse":
        ok = any((f.get("relationship") or "").upper() in ("SUAMI", "ISTRI") for f in ctx["family"].get(eid, []))
        return {"status": M.COMPLETE if ok else M.MISSING}
    if kind == "ptkp":
        sal = ctx["salary"].get(eid) or {}
        extra = sal.get("extra") if isinstance(sal.get("extra"), dict) else {}
        ptkp = (sal.get("ptkp_status") or "").strip().upper()
        if not ptkp:
            return {"status": M.MISSING}
        if ptkp == "TK/0" and not (extra.get("ptkp_confirmed_at") or sal.get("ptkp_confirmed_at")):
            return {"status": M.UNVERIFIED}  # default bawaan payroll != bukti konfirmasi
        return {"status": M.COMPLETE}
    if kind == "contract":
        today = ctx["today"]
        rows = [c for c in ctx["contracts"].get(eid, []) if c.get("status") == "active"
                and (not c.get("start_date") or str(c["start_date"])[:10] <= today)]
        return _expiry_status(rows, "end_date")
    if kind == "document":
        rows = [d for d in ctx["docs"].get(eid, []) if d.get("document_type_id") == req.ref_id
                and d.get("status") not in INACTIVE_DOC_STATUS]
        if not req.extra.get("has_expiry"):
            return {"status": M.COMPLETE if rows else M.MISSING}
        return _expiry_status(rows, "expiry_date")
    if kind == "certification":
        rows = [c for c in ctx["certs"].get(eid, []) if c.get("certification_type_id") == req.ref_id
                and c.get("status") not in INACTIVE_DOC_STATUS]
        return _expiry_status(rows, "expiry_date")
    return {"status": M.NA}


def evaluate(emp: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    category = ctx["business_category"].get(emp.get("current_employee_status_id"))
    base = {"employee_id": emp["id"], "catalog_version": M.CATALOG_VERSION, "rules_hash": ctx["rules_hash"]}
    if category == "INACTIVE" or emp.get("status") == "inactive":
        return {**base, "completeness_status": M.EXCLUDED, "score_pct": None, "required_total": 0, "required_fulfilled": 0,
                "recommended_total": 0, "recommended_fulfilled": 0, "missing_codes": [], "recommended_missing_codes": [],
                "items": []}
    items, req_t, req_f, rec_t, rec_f, missing, rec_missing = [], 0, 0, 0, 0, [], []
    for req in ctx["requirements"]:
        level = ctx["levels"].get(req.code, req.default_level)
        item = {"code": req.code, "category": req.category, "level": level}
        if level == M.OFF:
            item["status"] = M.OFF
        elif not _applicable(req, emp, ctx, category):
            item["status"] = M.NA
        else:
            item.update(_check(req, emp, ctx))
            done = item["status"] == M.COMPLETE
            if level == M.REQUIRED:
                req_t += 1
                req_f += done
                if not done:
                    missing.append(req.code)
            else:
                rec_t += 1
                rec_f += done
                if not done:
                    rec_missing.append(req.code)
        items.append(item)
    score = round(req_f * 100.0 / req_t, 1) if req_t else 100.0
    return {**base, "completeness_status": M.LENGKAP if req_f == req_t else M.BELUM_LENGKAP, "score_pct": score,
            "required_total": req_t, "required_fulfilled": req_f, "recommended_total": rec_t, "recommended_fulfilled": rec_f,
            "missing_codes": missing, "recommended_missing_codes": rec_missing, "items": items}


# ------------------------------------------------------------------ persist
async def _exec(stmt) -> None:
    """Satu statement tulis snapshot dalam transaksi sendiri (titik tunggal untuk retry & uji injeksi kegagalan)."""
    async with get_engine().begin() as conn:
        await conn.execute(stmt)


async def _upsert_snapshots(docs: List[Dict[str, Any]]) -> None:
    if not docs or _guard_write(SNAP, "upsert"):
        return
    table = get_table(SNAP)
    # urutan employee_id = urutan kunci yang sama dengan UPDATE stale (mencegah siklus deadlock)
    rows = [_doc_to_row(table, d, full=True) for d in sorted(docs, key=lambda d: d.get("employee_id") or "")]
    stmt = mysql_insert(table).values(rows)
    ins = stmt.inserted
    newer = sa.or_(table.c.evaluated_at.is_(None), ins.evaluated_at >= table.c.evaluated_at)
    stmt = stmt.on_duplicate_key_update([(c, sa.case((newer, ins[c]), else_=table.c[c])) for c in _UPSERT_COLS])

    await with_lock_retry(lambda: _exec(stmt), "upsert snapshot kelengkapan")  # idempotent (guard evaluated_at)


async def _delete_snapshots(company_id: str, employee_ids: List[str]) -> None:
    if employee_ids:
        await with_lock_retry(lambda: get_tenant_db(company_id)[SNAP].delete_many(
            {"company_id": company_id, "employee_id": {"$in": employee_ids}}), "hapus snapshot karyawan nonaktif")


async def _refresh_chunk(company_id: str, part: List[str], trigger: str, user_id: Optional[str],
                         rules: Dict[str, Any], lookups: Dict[str, Any]) -> int:
    ts = now()  # diambil SEBELUM data sumber dibaca -> penentu "hasil terbaru" saat upsert bersamaan
    ctx = await load_context(company_id, part, rules, lookups)
    docs = []
    for emp in ctx["employees"]:
        res = evaluate(emp, ctx)
        docs.append({"id": new_id(), "company_id": company_id, "status": "active", **res, "evaluated_at": ts,
                     "evaluated_trigger": trigger[:64], "is_stale": False, "stale_reason": None,
                     "created_at": ts, "updated_at": ts, "created_by": user_id, "updated_by": user_id})
    for sub in _chunks(docs, 250):
        await _upsert_snapshots(sub)
    found = {d["employee_id"] for d in docs}
    await _delete_snapshots(company_id, [e for e in part if e not in found])  # karyawan terhapus/diarsipkan
    return len(docs)


async def active_employee_ids(company_id: str) -> List[str]:
    return sorted(await get_tenant_db(company_id).employees.distinct(
        "id", {"company_id": company_id, "status": {"$nin": list(EXCLUDED_EMP_STATUS)}}))


async def purge_orphans(company_id: str) -> None:
    """Hapus snapshot milik karyawan yang sudah tidak ada/terhapus (satu statement SQL, tenant-scoped)."""
    await get_db().execute(
        "DELETE ec FROM employee_completeness ec LEFT JOIN employees e ON e.id = ec.employee_id AND e.company_id = ec.company_id "
        "AND e.status NOT IN ('deleted','archived') WHERE ec.company_id = :cid AND e.id IS NULL", {"cid": company_id})


_full_locks: Dict[Any, asyncio.Lock] = {}


def _full_refresh_lock(company_id: str) -> asyncio.Lock:
    """Satu evaluasi PENUH per tenant pada satu waktu (per event loop/proses): manual, latar belakang, dan harian
    diserialkan sehingga tidak saling mengunci baris snapshot yang sama. Evaluasi parsial (trigger bisnis) tidak ikut."""
    key = (id(asyncio.get_running_loop()), company_id)
    lock = _full_locks.get(key)
    if lock is None:
        lock = _full_locks[key] = asyncio.Lock()
    return lock


async def _refresh_ids(company_id: str, ids: List[str], trigger: str, user_id: Optional[str], full: bool) -> Dict[str, Any]:
    rules = await load_rules(company_id)
    lookups = await _load_lookups(company_id)
    started = now()
    total = 0
    for part in _chunks(ids):
        total += await _refresh_chunk(company_id, part, trigger, user_id, rules, lookups)
    if full:
        await with_lock_retry(lambda: purge_orphans(company_id), "hapus snapshot yatim")
    return {"evaluated": total, "rules_hash": rules["rules_hash"], "evaluated_at": started}


async def refresh(company_id: str, employee_ids: Optional[List[str]] = None, trigger: str = "manual",
                  user_id: Optional[str] = None) -> Dict[str, Any]:
    """employee_ids=None -> seluruh karyawan tenant (diproses per chunk 500)."""
    if employee_ids is not None:
        return await _refresh_ids(company_id, sorted({e for e in employee_ids if e}), trigger, user_id, False)
    async with _full_refresh_lock(company_id):
        # daftar karyawan + rules dibaca SETELAH lock didapat -> selalu memakai konfigurasi terbaru
        return await _refresh_ids(company_id, await active_employee_ids(company_id), trigger, user_id, True)


async def mark_stale(company_id: str, employee_ids: Optional[List[str]], reason: str) -> None:
    """Idempotent. Konflik kunci DB -> retry terbatas; error lain / retry habis dilempar ke pemanggil."""
    if _guard_write(SNAP, "update_many"):
        return
    # seluruh tenant: UPDATE per chunk (500) berurutan employee_id lewat unique index -> kunci singkat & urutan kunci
    # sama dengan upsert snapshot (bukan satu UPDATE besar yang mengunci ribuan baris dalam urutan scan acak)
    ids = await _snapshot_ids(company_id) if employee_ids is None else sorted(set(employee_ids))
    for part in _chunks(ids):
        await _mark_stale_chunk(company_id, part, reason)


async def _snapshot_ids(company_id: str) -> List[str]:
    async with get_engine().connect() as conn:
        res = await conn.execute(sa.text("SELECT employee_id FROM employee_completeness WHERE company_id = :cid AND is_stale = 0 "
                                         "ORDER BY employee_id"), {"cid": company_id})
        return [r[0] for r in res.fetchall()]


async def _mark_stale_chunk(company_id: str, part: List[str], reason: str) -> None:
    table = get_table(SNAP)
    stmt = (sa.update(table).where(table.c.company_id == company_id, table.c.employee_id.in_(part))
            .values(is_stale=True, stale_reason=reason[:200], updated_at=now()))

    await with_lock_retry(lambda: _exec(stmt), "penandaan stale kelengkapan")  # idempotent


async def run_config_mutation(fn: Callable[[Any], Awaitable[Any]], what: str) -> Any:
    """Mutasi konfigurasi utama (rule/scope + audit) dalam SATU transaksi. Konflik kunci -> seluruh transaksi di-rollback
    server lalu diulang (aman, tanpa duplikat). Bila tetap gagal -> ConfigBusyError (perubahan TIDAK tersimpan)."""
    async def _once():
        async with transaction() as tx:
            return await fn(tx)
    try:
        return await with_lock_retry(_once, what)
    except Exception as exc:  # noqa: BLE001
        if is_lock_conflict(exc):
            logger.warning("Mutasi konfigurasi kelengkapan gagal setelah retry (%s): %s", what, type(exc).__name__)
            raise ConfigBusyError(what) from exc
        raise


async def after_config_change(company_id: str, reason: str) -> bool:
    """Side-effect SETELAH mutasi konfigurasi committed: tandai snapshot tenant stale. TIDAK PERNAH melempar error.
    Walau gagal, evaluasi ulang tenant tetap dijadwalkan pemanggil (schedule_tenant_refresh) dan rules_hash snapshot
    yang berbeda tetap terbaca sebagai 'menunggu evaluasi' (eventual consistency)."""
    try:
        await mark_stale(company_id, None, reason)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Penandaan stale setelah perubahan konfigurasi kelengkapan gagal (non-blocking): %s", type(exc).__name__)
        return False


async def safe_refresh(company_id: Optional[str], employee_ids: Optional[Iterable[Optional[str]]], trigger: str,
                       user_id: Optional[str] = None) -> None:
    """Trigger dari alur bisnis. TIDAK PERNAH melempar error ke pemanggil."""
    if not company_id:
        return
    ids = None if employee_ids is None else sorted({e for e in employee_ids if e})
    if ids is not None and not ids:
        return
    try:
        await refresh(company_id, ids, trigger, user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Evaluasi kelengkapan gagal (trigger=%s, jumlah=%s): %s", trigger, len(ids or []), type(exc).__name__)
        try:
            await mark_stale(company_id, ids, f"evaluasi gagal ({trigger})")
        except Exception as exc2:  # noqa: BLE001
            logger.warning("Penandaan stale kelengkapan gagal: %s", type(exc2).__name__)


SALARY_SOURCE_FIELDS = ("ptkp_status", "has_npwp", "bpjs_kesehatan_enrolled", "bpjs_jht_enrolled", "bpjs_jp_enrolled",
                        "ptkp_confirmed_at")


def salary_source_changed(before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]]) -> bool:
    """True bila perubahan data gaji menyentuh sumber kelengkapan (TAX.PTKP, applicability NPWP/BPJS/has_salary)."""
    if not before or not after:
        return True
    return any(before.get(f) != after.get(f) for f in SALARY_SOURCE_FIELDS)


# ------------------------------------------------------------------ evaluasi ulang tenant (latar belakang, coalesced)
_running: Set[str] = set()
_pending: Set[str] = set()


def tenant_refresh_running(company_id: str) -> bool:
    return company_id in _running


async def schedule_tenant_refresh(company_id: str, trigger: str, user_id: Optional[str] = None) -> None:
    """Dipanggil via BackgroundTasks setelah rule/scope berubah. Bila evaluasi tenant sedang berjalan, permintaan
    digabung: satu putaran tambahan dijalankan setelah putaran berjalan selesai (bukan N evaluasi paralel)."""
    if company_id in _running:
        _pending.add(company_id)
        return
    _running.add(company_id)
    try:
        while True:
            _pending.discard(company_id)
            await safe_refresh(company_id, None, trigger, user_id)
            if company_id not in _pending:
                break
            await asyncio.sleep(0)
    finally:
        _running.discard(company_id)


async def daily_reevaluation() -> Dict[str, Any]:
    """Job harian (scheduler existing): masa berlaku dokumen/kontrak/sertifikasi & scope bertanggal berubah seiring
    waktu. Tenant-aware, per chunk 500, idempotent (upsert satu snapshot per karyawan)."""
    db = get_db()
    out = {}
    for company in await db.companies.find({"status": {"$nin": ["archived", "deleted"]}}, NO_ID).to_list(1000):
        cid = company["id"]
        if cid in _running:
            out[company.get("code")] = "skipped_running"
            continue
        _running.add(cid)
        try:
            out[company.get("code")] = (await refresh(cid, None, "daily"))["evaluated"]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Evaluasi harian kelengkapan gagal untuk %s: %s", company.get("code"), type(exc).__name__)
            out[company.get("code")] = "failed"
        finally:
            _running.discard(cid)
    logger.info("Evaluasi harian kelengkapan: %s", out)
    return out


def utc_iso(v: Any) -> Any:
    return v.replace(tzinfo=timezone.utc).isoformat() if isinstance(v, datetime) and v.tzinfo is None else v
