"""Phase 2A CP2 - Siklus Penyerahan, Pengembalian & Pemeriksaan Aset + Dokumen BAST.

Alur terkunci: READY -> Penyerahan (DRAFT -> PUBLISHED) -> IN_USE -> Pengembalian (DRAFT -> PUBLISHED) ->
PENDING_INSPECTION -> Pemeriksaan GA -> READY / MAINTENANCE / DAMAGED / LOST.
- Tidak ada transfer langsung karyawan A -> B: penyerahan hanya menerima aset READY, dan aset hanya kembali READY
  melalui pengembalian + pemeriksaan.
- Publish atomik (satu transaksi DB): kunci baris aset/holding (SELECT ... FOR UPDATE), validasi ulang seluruh item,
  alokasi nomor BAST (doc_sequence, per company + tipe + tahun), snapshot immutable, holding, status aset, event.
  Satu item gagal -> seluruh publish di-rollback. Unique `asset_holdings(company_id, active_lock)` = jaring pengaman
  maks. 1 holding ACTIVE per aset.
- BAST Pengembalian terbit saat return dipublish; hasil pemeriksaan TIDAK mengubah snapshot/PDF BAST.
- PDF dibuat on-the-fly dari snapshot (tanpa object storage).
- 01I: semua list/detail difilter di SQL (`project_id` dokumen), karyawan wajib dalam scope, UUID di luar scope -> 404
  generik; scope dicek ulang saat publish/complete. Otorisasi murni permission (tanpa nama role).
"""
from __future__ import annotations

import re
from contextlib import asynccontextmanager
from datetime import date
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError, OperationalError

from ..core import asset_service as svc
from ..core import data_scope as dscope
from ..core import doc_sequence
from ..core.asset_bast_pdf import build_bast_pdf
from ..core.audit import log_action
from ..core.db import NO_ID, get_db, get_table, new_id, now, transaction
from ..core.deps import AuthContext, require_permission
from .assets import _event, _master

router = APIRouter(tags=["Manajemen Aset - Siklus"])

DRAFT, PUBLISHED, CANCELLED = "DRAFT", "PUBLISHED", "CANCELLED"
ACTIVE, CLOSED = "ACTIVE", "CLOSED"
INSPECTION_RESULTS = ("READY", "MAINTENANCE", "DAMAGED", "LOST")
SEQ = {"HANDOVER": "BAST_HANDOVER", "RETURN": "BAST_RETURN"}
TXT = {"accessories", "item_notes", "notes", "completeness"}


# ------------------------------------------------------------------ helpers
def _norm_manual(v: Optional[str]) -> Optional[str]:
    v = re.sub(r"\s+", " ", (v or "").strip()).upper()
    return v or None


def _text(v: Any, limit: int = 2000) -> Optional[str]:
    v = (str(v).strip() if v is not None else "")
    return v[:limit] or None


def _date(v: Optional[str], label: str) -> str:
    if not v:
        return date.today().isoformat()
    try:
        return date.fromisoformat(str(v)[:10]).isoformat()
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{label} tidak valid (format YYYY-MM-DD).") from None


def _unprocessable(msg: str):
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, msg)


def _conflict(msg: str):
    return HTTPException(status.HTTP_409_CONFLICT, msg)


def _not_found():
    return HTTPException(status.HTTP_404_NOT_FOUND, dscope.NOT_FOUND_MSG)


LOCK_CONFLICT_CODES = {1205, 1213}   # lock wait timeout / deadlock (MariaDB/MySQL)


@asynccontextmanager
async def _atomic(conflict_msg: str):
    """Satu transaksi DB untuk publish/complete. Pelanggaran unique (mis. `ux_asset_holding_active`,
    `ux_asset_bast_number`) atau deadlock/lock-timeout akibat aksi bersamaan -> 409 dengan pesan spesifik;
    seluruh perubahan di-rollback (tidak ada publish parsial)."""
    try:
        async with transaction() as tx:
            try:
                yield tx
            except IntegrityError:
                raise _conflict(conflict_msg) from None
    except OperationalError as exc:
        code = getattr(getattr(exc, "orig", None), "args", [None])[0]
        if code in LOCK_CONFLICT_CODES:
            raise _conflict(conflict_msg + " Silakan muat ulang lalu coba lagi.") from None
        raise


def _stamp(actor: Optional[str], creating: bool = True) -> Dict[str, Any]:
    ts = now()
    out = {"updated_at": ts, "updated_by": actor}
    if creating:
        out.update({"id": new_id(), "status": "active", "created_at": ts, "created_by": actor})
    return out


def _page(total: int, page: int, limit: int, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"items": items, "total": total, "page": page, "limit": limit,
            "pages": (total + limit - 1) // limit if total else 0}


def _like(term: str) -> str:
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _employee_match(cid: str, term: str):
    e = get_table("employees")
    like = _like(term.strip())
    return sa.select(e.c.id).where(e.c.company_id == cid, sa.or_(e.c.full_name.like(like), e.c.employee_number.like(like)))


def _doc_search(cid: str, q: Optional[str]):
    """Pencarian dokumen siklus: nomor referensi/manual, nomor BAST sistem, nama/NIK karyawan (semua di SQL;
    tetap di-AND dengan filter scope baris dokumen)."""
    if not q or not q.strip():
        return None
    b = get_table("asset_basts")
    manual, up = _like(_norm_manual(q) or ""), _like(q.strip().upper())
    bast_ids = sa.select(b.c.id).where(b.c.company_id == cid, sa.func.upper(b.c.system_number).like(up))
    emp_ids = _employee_match(cid, q)
    return lambda t: sa.or_(t.c.manual_number_norm.like(manual), t.c.bast_id.in_(bast_ids), t.c.employee_id.in_(emp_ids))


async def _names(cid: str, coll: str, ids, field: str = "name") -> Dict[str, Any]:
    ids = sorted({i for i in ids if i})
    if not ids:
        return {}
    rows = await get_db()[coll].find({"company_id": cid, "id": {"$in": ids}}, NO_ID).to_list(len(ids))
    return {r["id"]: r for r in rows} if field is None else {r["id"]: r.get(field) for r in rows}


async def _user_names(ids) -> Dict[str, Any]:
    ids = sorted({i for i in ids if i})
    if not ids:
        return {}
    rows = await get_db().users.find({"id": {"$in": ids}}, NO_ID).to_list(len(ids))
    return {r["id"]: r.get("full_name") or r.get("email") for r in rows}


async def _visible(ctx: AuthContext, coll: str, record_id: str) -> Dict[str, Any]:
    """Dokumen siklus ber-project: filter scope di SQL, 404 generik bila di luar scope/tenant."""
    scope = await dscope.get_scope(ctx)
    doc = await get_db()[coll].find_one(dscope.with_project_scope({"company_id": ctx.company_id, "id": record_id}, scope), NO_ID)
    if not doc or doc.get("status") == "deleted":
        raise _not_found()
    return dscope.assert_project_record_visible(scope, doc)


async def _employee(ctx: AuthContext, scope, employee_id: Optional[str]) -> Dict[str, Any]:
    if not employee_id:
        raise _unprocessable("Karyawan wajib dipilih.")
    emp = await get_db().employees.find_one(dscope.with_scope({"company_id": ctx.company_id, "id": employee_id}, scope), NO_ID)
    if not emp or emp.get("status") != "active":
        raise _not_found()
    return emp


async def _manual_warning(cid: str, norm: Optional[str], exclude_ids: List[str]) -> Optional[str]:
    """Nomor manual/referensi: duplikat hanya PERINGATAN (tidak memblokir)."""
    if not norm:
        return None
    db = get_db()
    n = 0
    for coll in ("asset_handovers", "asset_returns"):
        n += await db[coll].count_documents({"company_id": cid, "manual_number_norm": norm, "doc_state": {"$ne": CANCELLED},
                                             "id": {"$nin": exclude_ids or ["-"]}})
    return f"Nomor referensi '{norm}' juga dipakai pada {n} dokumen lain." if n else None


async def _list(ctx, coll: str, flt: Dict[str, Any], page: int, limit: int, sort_col: str = "created_at"):
    scope = await dscope.get_scope(ctx)
    flt = dscope.with_project_scope(flt, scope)
    db = get_db()
    total = await db[coll].count_documents(flt)
    rows = await db[coll].find(flt, NO_ID).sort([(sort_col, -1), ("id", 1)]).skip((page - 1) * limit).limit(limit).to_list(limit)
    return total, rows


async def _decorate(cid: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    emps = await _names(cid, "employees", [r.get("employee_id") for r in rows], None)
    projects = await _names(cid, "projects", [r.get("project_id") for r in rows])
    locs = await _names(cid, "work_locations", [r.get("work_location_id") for r in rows])
    basts = await _names(cid, "asset_basts", [r.get("bast_id") for r in rows], "system_number")
    out = []
    for r in rows:
        e = emps.get(r.get("employee_id")) or {}
        out.append({**r, "employee_name": e.get("full_name"), "employee_number": e.get("employee_number"),
                    "project_name": projects.get(r.get("project_id")), "work_location_name": locs.get(r.get("work_location_id")),
                    "bast_number": basts.get(r.get("bast_id"))})
    return out


async def _tx_get(tx, coll: str, cid: Optional[str], record_id: Optional[str]) -> Dict[str, Any]:
    """Baca master lewat koneksi transaksi yang sama (tanpa koneksi pool kedua saat baris sedang dikunci)."""
    if not record_id:
        return {}
    flt = {"id": record_id} if cid is None else {"company_id": cid, "id": record_id}
    return await tx.select_one(coll, flt) or {}


async def _snapshot_items(tx, cid: str, assets: Dict[str, Dict[str, Any]], items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for it in items:
        a = assets[it["asset_id"]]
        out.append({"line_no": it["line_no"], "asset_id": a["id"], "asset_code": a.get("asset_code"), "name": a.get("name"),
                    "category": (await _tx_get(tx, "asset_categories", cid, a.get("category_id"))).get("name"),
                    "brand": a.get("brand"), "model": a.get("model"), "serial_number": a.get("serial_number"),
                    "unit": (await _tx_get(tx, "asset_units", cid, a.get("unit_id"))).get("name"),
                    "condition": (await _tx_get(tx, "asset_conditions", cid, it.get("condition_id"))).get("name"),
                    "accessories": it.get("accessories"), "item_notes": it.get("item_notes")})
    return out


async def _snapshot_header(tx, ctx, btype: str, doc: Dict[str, Any], emp: Dict[str, Any], number: str, bast_date: str,
                           project_id: Optional[str], work_location_id: Optional[str]) -> Dict[str, Any]:
    cid = ctx.company_id
    company = await _tx_get(tx, "companies", None, cid)
    project = await _tx_get(tx, "projects", cid, project_id)
    loc = await _tx_get(tx, "work_locations", cid, work_location_id)
    issuer = await _tx_get(tx, "users", None, ctx.user_id)
    position = await _tx_get(tx, "positions", cid, emp.get("position_id"))
    return {"bast_type": btype, "system_number": number, "manual_number": doc.get("manual_number"), "bast_date": bast_date,
            "company": {k: company.get(k) for k in ("code", "name", "legal_name", "address", "city")},
            "employee": {**{k: emp.get(k) for k in ("id", "full_name", "employee_number", "job_title")},
                         "position": position.get("name")},
            "project": {"id": project_id, "name": project.get("name"), "code": project.get("code")},
            "work_location": {"id": work_location_id, "name": loc.get("name")},
            "ga_pic_name": doc.get("ga_pic_name"), "notes": doc.get("notes"),
            "issued_at": now().strftime("%Y-%m-%d %H:%M UTC"),
            "issued_by_name": issuer.get("full_name") or issuer.get("email")}


def _clean_items(raw: Any, key: str) -> List[Dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise _unprocessable("Minimal satu aset wajib dipilih.")
    seen, out = set(), []
    for i, it in enumerate(raw, 1):
        if not isinstance(it, dict) or not it.get(key):
            raise _unprocessable(f"Item #{i} tidak valid.")
        if it[key] in seen:
            raise _unprocessable("Aset yang sama tidak boleh dipilih dua kali dalam satu transaksi.")
        seen.add(it[key])
        out.append({key: it[key], "condition_id": it.get("condition_id"), "accessories": _text(it.get("accessories")),
                    "item_notes": _text(it.get("item_notes")), "line_no": i})
    return out


# ------------------------------------------------------------------ Penyerahan (handover)
HO_FIELDS = {"employee_id", "handover_date", "project_id", "work_location_id", "ga_pic_name", "manual_number", "notes", "items"}


async def _validate_handover(ctx: AuthContext, payload: Dict[str, Any]) -> Dict[str, Any]:
    unknown = sorted(k for k in payload if k not in HO_FIELDS)
    if unknown:
        raise _unprocessable(f"Kolom tidak dikenal: {', '.join(unknown)}.")
    scope = await dscope.get_scope(ctx)
    emp = await _employee(ctx, scope, payload.get("employee_id"))
    project_id = payload.get("project_id") or None
    await dscope.ensure_target_project_allowed(ctx, project_id)
    await _master(ctx.company_id, "projects", project_id, "Project")
    await _master(ctx.company_id, "work_locations", payload.get("work_location_id") or None, "Lokasi kerja")
    items = _clean_items(payload.get("items"), "asset_id")
    db = get_db()
    for it in items:
        a = await db.assets.find_one(dscope.with_project_scope({"company_id": ctx.company_id, "id": it["asset_id"]}, scope), NO_ID)
        if not a or a.get("status") == "deleted":
            raise _not_found()
        if a.get("lifecycle_state") != "READY":
            raise _conflict(f"Aset {a.get('asset_code')} tidak berstatus Siap Pakai (READY). Aset yang sedang dipakai "
                            "wajib dikembalikan ke GA dan diperiksa terlebih dahulu.")
        it["condition_id"] = it.get("condition_id") or a.get("condition_id")
        await _master(ctx.company_id, "asset_conditions", it["condition_id"], "Kondisi")
    manual = _text(payload.get("manual_number"), 128)
    return {"employee_id": emp["id"], "handover_date": _date(payload.get("handover_date"), "Tanggal penyerahan"),
            "project_id": project_id, "work_location_id": payload.get("work_location_id") or None,
            "ga_pic_name": _text(payload.get("ga_pic_name"), 255), "manual_number": manual,
            "manual_number_norm": _norm_manual(manual), "notes": _text(payload.get("notes")), "items": items}


async def _handover_detail(ctx, doc: Dict[str, Any]) -> Dict[str, Any]:
    db = get_db()
    items = await db.asset_handover_items.find({"company_id": ctx.company_id, "handover_id": doc["id"]}, NO_ID).sort([("line_no", 1)]).to_list(500)
    assets = await _names(ctx.company_id, "assets", [i["asset_id"] for i in items], None)
    conds = await _names(ctx.company_id, "asset_conditions", [i.get("condition_id") for i in items])
    for i in items:
        a = assets.get(i["asset_id"]) or {}
        i.update({"asset_code": a.get("asset_code"), "asset_name": a.get("name"), "serial_number": a.get("serial_number"),
                  "lifecycle_state": a.get("lifecycle_state"), "condition_name": conds.get(i.get("condition_id"))})
    return await _finish_detail(ctx, doc, items)


async def _finish_detail(ctx, doc: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, Any]:
    out = (await _decorate(ctx.company_id, [doc]))[0]
    out["items"] = items
    out["manual_number_warning"] = await _manual_warning(ctx.company_id, doc.get("manual_number_norm"), [doc["id"]])
    out["bast_snapshot"] = None
    if doc.get("bast_id"):   # dokumen terbit: tampilan resmi = snapshot BAST (bukan master live)
        b = await get_db().asset_basts.find_one({"company_id": ctx.company_id, "id": doc["bast_id"]}, NO_ID)
        out["bast_snapshot"] = (b or {}).get("snapshot")
    return out


async def _write_items(tx, coll: str, parent_key: str, parent_id: str, cid: str, items, actor) -> List[Dict[str, Any]]:
    await tx.delete(coll, {"company_id": cid, parent_key: parent_id})
    rows = []
    for it in items:
        row = {**_stamp(actor), "company_id": cid, parent_key: parent_id, **it}
        await tx.insert(coll, dict(row))
        rows.append(row)
    return rows


def _require_also(ctx: AuthContext, resource: str, action: str) -> None:
    """Simpan & Publish = izin simpan (create/edit) DAN izin publish. Murni permission efektif, tanpa nama role."""
    if not ctx.has_permission(resource, action):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Anda tidak memiliki hak akses untuk tindakan ini.")


@router.get("/asset-handovers/options")
async def handover_options(include_employees: bool = True,
                           ctx: AuthContext = Depends(require_permission("asset_handover", "view"))):
    """`include_employees=false` (dipakai UI CP2.1): karyawan dicari lewat /asset-handovers/employee-search."""
    scope = await dscope.get_scope(ctx)
    db, cid = get_db(), ctx.company_id
    emps = (await db.employees.find(dscope.with_scope({"company_id": cid, "status": "active"}, scope), NO_ID)
            .sort([("full_name", 1)]).to_list(2000)) if include_employees else []
    assets = await db.assets.find(dscope.with_project_scope({"company_id": cid, "lifecycle_state": "READY", "status": "active"}, scope),
                                  NO_ID).sort([("asset_code_norm", 1)]).to_list(2000)
    pflt = {"company_id": cid, "status": "active"}
    if not scope.is_all:
        pflt["id"] = {"$in": sorted(scope.project_ids) or ["-"]}
    projects = await db.projects.find(pflt, NO_ID).sort([("name", 1)]).to_list(1000)
    locs = await db.work_locations.find({"company_id": cid, "status": "active"}, NO_ID).sort([("name", 1)]).to_list(1000)
    conds = await db.asset_conditions.find({"company_id": cid, "status": "active"}, NO_ID).sort([("sort_order", 1)]).to_list(200)
    return {"employees": [{"id": e["id"], "full_name": e.get("full_name"), "employee_number": e.get("employee_number")} for e in emps],
            "assets": [{"id": a["id"], "asset_code": a.get("asset_code"), "name": a.get("name"), "serial_number": a.get("serial_number"),
                        "condition_id": a.get("condition_id"), "project_id": a.get("project_id")} for a in assets],
            "projects": [{"id": p["id"], "name": p.get("name")} for p in projects],
            "work_locations": [{"id": w["id"], "name": w.get("name")} for w in locs],
            "conditions": [{"id": c["id"], "name": c.get("name")} for c in conds],
            "restricted": not scope.is_all,
            "ga_pic_name": (await _user_names([ctx.user_id])).get(ctx.user_id)}


# ------------------------------------------------------------------ Pencarian karyawan (server-side, CP2.1)
EMP_SEARCH_MAX = 50


async def _employee_search(ctx: AuthContext, q: Optional[str], page: int, limit: int, holders_only: bool) -> Dict[str, Any]:
    """Cari karyawan aktif by nama / nomor karyawan di SQL, berhalaman (tanpa memuat seluruh karyawan ke browser).
    Cakupan Data 01I diterapkan di SQL: user restricted hanya menemukan karyawan dalam project scope-nya.
    `holders_only` = hanya karyawan yang memegang aset aktif (holding project juga dalam scope) untuk Pengembalian."""
    cid = ctx.company_id
    scope = await dscope.get_scope(ctx)
    flt = dscope.with_scope({"company_id": cid, "status": "active"}, scope)
    extra = []
    term = (q or "").strip()
    if term:
        like = _like(term)
        extra.append(lambda t, like=like: sa.or_(t.c.full_name.like(like), t.c.employee_number.like(like)))
    if holders_only:
        h = get_table("asset_holdings")
        hsel = sa.select(h.c.employee_id).where(h.c.company_id == cid, h.c.holding_status == ACTIVE)
        pclause = dscope.project_scope_clause(scope, h.c.project_id)
        if pclause is not None:
            hsel = hsel.where(pclause)
        extra.append(lambda t, hsel=hsel: t.c.id.in_(hsel))
    if extra:
        prev = flt.get("$sql")
        flt["$sql"] = ([*prev] if isinstance(prev, (list, tuple)) else ([prev] if prev else [])) + extra
    db = get_db()
    total = await db.employees.count_documents(flt)
    rows = await db.employees.find(flt, NO_ID).sort([("full_name", 1), ("id", 1)]).skip((page - 1) * limit).limit(limit).to_list(limit)
    ids = [r["id"] for r in rows]
    proj_of: Dict[str, Optional[str]] = {}
    if ids:
        asg = await db.employee_assignments.find({"company_id": cid, "employee_id": {"$in": ids}, "assignment_status": "ACTIVE"},
                                                 NO_ID).to_list(len(ids) * 3)
        pnames = await _names(cid, "projects", [x.get("project_id") for x in asg])
        for x in asg:
            proj_of.setdefault(x["employee_id"], pnames.get(x.get("project_id")))
    holding_counts: Dict[str, int] = {}
    if holders_only and ids:
        hs = await db.asset_holdings.find(dscope.with_project_scope({"company_id": cid, "holding_status": ACTIVE,
                                                                     "employee_id": {"$in": ids}}, scope), NO_ID).to_list(5000)
        for x in hs:
            holding_counts[x["employee_id"]] = holding_counts.get(x["employee_id"], 0) + 1
    items = [{"id": r["id"], "full_name": r.get("full_name"), "employee_number": r.get("employee_number"),
              "project_name": proj_of.get(r["id"]), **({"active_holdings": holding_counts.get(r["id"], 0)} if holders_only else {})}
             for r in rows]
    return _page(total, page, limit, items)


@router.get("/asset-handovers/employee-search")
async def handover_employee_search(q: Optional[str] = None, page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=EMP_SEARCH_MAX),
                                   ctx: AuthContext = Depends(require_permission("asset_handover", "view"))):
    return await _employee_search(ctx, q, page, limit, holders_only=False)


@router.get("/asset-handovers")
async def list_handovers(doc_state: Optional[str] = None, employee_id: Optional[str] = None, q: Optional[str] = None,
                         project_id: Optional[str] = None, page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100),
                         ctx: AuthContext = Depends(require_permission("asset_handover", "view"))):
    flt: Dict[str, Any] = {"company_id": ctx.company_id, "status": "active"}
    if doc_state:
        flt["doc_state"] = doc_state
    if employee_id:
        flt["employee_id"] = employee_id
    if project_id:
        flt["project_id"] = project_id
    search = _doc_search(ctx.company_id, q)
    if search is not None:
        flt["$sql"] = [search]
    total, rows = await _list(ctx, "asset_handovers", flt, page, limit)
    return _page(total, page, limit, await _decorate(ctx.company_id, rows))


@router.post("/asset-handovers", status_code=201)
async def create_handover(payload: Dict[str, Any] = Body(...), ctx: AuthContext = Depends(require_permission("asset_handover", "create"))):
    data = await _validate_handover(ctx, payload)
    items = data.pop("items")
    doc = {**_stamp(ctx.user_id), "company_id": ctx.company_id, "doc_state": DRAFT, "ga_pic_user_id": ctx.user_id,
           "row_version": 1, **data}
    async with transaction() as tx:
        await tx.insert("asset_handovers", dict(doc))
        await _write_items(tx, "asset_handover_items", "handover_id", doc["id"], ctx.company_id, items, ctx.user_id)
    await log_action(ctx, "create", "asset_handover", doc["id"], "Draft penyerahan", after={"items": len(items)}, module="asset")
    return await _handover_detail(ctx, doc)


@router.get("/asset-handovers/{handover_id}")
async def get_handover(handover_id: str, ctx: AuthContext = Depends(require_permission("asset_handover", "view"))):
    return await _handover_detail(ctx, await _visible(ctx, "asset_handovers", handover_id))


@router.put("/asset-handovers/{handover_id}")
async def update_handover(handover_id: str, payload: Dict[str, Any] = Body(...),
                          ctx: AuthContext = Depends(require_permission("asset_handover", "edit"))):
    cur = await _visible(ctx, "asset_handovers", handover_id)
    if cur.get("doc_state") != DRAFT:
        raise _conflict("Hanya draft penyerahan yang dapat diubah. Nomor referensi dokumen terbit diubah lewat aksi khusus.")
    data = await _validate_handover(ctx, payload)
    items = data.pop("items")
    async with transaction() as tx:
        locked = await tx.select_one_for_update("asset_handovers", {"company_id": ctx.company_id, "id": handover_id})
        if not locked or locked.get("doc_state") != DRAFT:
            raise _conflict("Draft penyerahan sudah tidak dapat diubah.")
        await tx.update("asset_handovers", {"company_id": ctx.company_id, "id": handover_id},
                        {**data, **_stamp(ctx.user_id, False), "row_version": int(locked.get("row_version") or 1) + 1})
        await _write_items(tx, "asset_handover_items", "handover_id", handover_id, ctx.company_id, items, ctx.user_id)
    await log_action(ctx, "update", "asset_handover", handover_id, "Draft penyerahan", after={"items": len(items)}, module="asset")
    return await _handover_detail(ctx, await _visible(ctx, "asset_handovers", handover_id))


@router.post("/asset-handovers/{handover_id}/cancel")
async def cancel_handover(handover_id: str, ctx: AuthContext = Depends(require_permission("asset_handover", "edit"))):
    return await _cancel(ctx, "asset_handovers", "asset_handover", handover_id)


async def _cancel(ctx, coll: str, resource: str, record_id: str):
    await _visible(ctx, coll, record_id)
    async with transaction() as tx:
        cur = await tx.select_one_for_update(coll, {"company_id": ctx.company_id, "id": record_id})
        if not cur or cur.get("doc_state") != DRAFT:
            raise _conflict("Hanya draft yang dapat dibatalkan; dokumen terbit tidak dapat dibatalkan/dihapus.")
        await tx.update(coll, {"company_id": ctx.company_id, "id": record_id},
                        {"doc_state": CANCELLED, "cancelled_at": now(), "cancelled_by": ctx.user_id, **_stamp(ctx.user_id, False)})
    await log_action(ctx, "cancel", resource, record_id, "Draft dibatalkan", module="asset")
    return {"id": record_id, "doc_state": CANCELLED}


HO_CONFLICT = "Konflik penyerahan bersamaan: aset sudah memiliki pemegang aktif atau sedang diproses. Publish dibatalkan seluruhnya."


async def _handover_prepare(ctx: AuthContext, handover_date: str):
    """Persiapan publish di luar transaksi: status IN_USE + baris counter BAST (tidak mengonsumsi nomor)."""
    in_use = await svc.default_status_for(ctx.company_id, "IN_USE")
    if not in_use:
        raise _unprocessable("Status aset untuk kategori sistem IN_USE belum dikonfigurasi.")
    prepared = await doc_sequence.prepare(ctx.company_id, SEQ["HANDOVER"], when=date.fromisoformat(handover_date), actor_id=ctx.user_id)
    return in_use, prepared


async def _handover_finalize(tx, ctx: AuthContext, scope, handover_id: str, emp: Dict[str, Any], items: List[Dict[str, Any]],
                             in_use: Dict[str, Any], prepared: Dict[str, Any]) -> str:
    """Satu-satunya logika publish penyerahan (dipakai Publish draft & Simpan & Publish), di DALAM transaksi pemanggil:
    kunci + validasi ulang, nomor BAST, snapshot, holding, status aset, event. Gagal -> seluruh transaksi rollback."""
    cid, actor = ctx.company_id, ctx.user_id
    if not items:
        raise _unprocessable("Draft penyerahan tidak memiliki item aset.")
    cur = await tx.select_one_for_update("asset_handovers", {"company_id": cid, "id": handover_id})
    if not cur or cur.get("doc_state") != DRAFT:
        raise _conflict("Penyerahan ini sudah diterbitkan atau dibatalkan.")
    e2 = await tx.select_one("employees", {"company_id": cid, "id": emp["id"]})
    if not e2 or e2.get("status") != "active":
        raise _unprocessable("Karyawan tidak lagi aktif.")
    emp = e2   # snapshot memakai data karyawan terbaru saat terbit
    assets: Dict[str, Dict[str, Any]] = {}
    for it in sorted(items, key=lambda x: x["asset_id"]):   # urutan kunci stabil -> hindari deadlock
        a = await tx.select_one_for_update("assets", {"company_id": cid, "id": it["asset_id"]})
        if not a or a.get("status") == "deleted" or not scope.allows_project(a.get("project_id")):
            raise _conflict("Salah satu aset tidak lagi tersedia dalam cakupan Anda. Publish dibatalkan seluruhnya.")
        if a.get("lifecycle_state") != "READY":
            raise _conflict(f"Aset {a.get('asset_code')} tidak lagi Siap Pakai (READY). Publish dibatalkan seluruhnya.")
        if await tx.select_one("asset_holdings", {"company_id": cid, "active_lock": a["id"]}):
            raise _conflict(f"Aset {a.get('asset_code')} masih memiliki pemegang aktif. Publish dibatalkan seluruhnya.")
        assets[a["id"]] = a

    async def _taken(candidate):
        return bool(await tx.select_one("asset_basts", {"company_id": cid, "system_number": candidate}))
    number = await doc_sequence.allocate_in_tx(tx, prepared, exists=_taken)
    snap = await _snapshot_header(tx, ctx, "HANDOVER", cur, emp, number, cur["handover_date"], cur.get("project_id"),
                                  cur.get("work_location_id"))
    snap["items"] = await _snapshot_items(tx, cid, assets, items)
    bast = {**_stamp(actor), "company_id": cid, "bast_type": "HANDOVER", "system_number": number,
            "sequence_key": SEQ["HANDOVER"], "sequence_period": cur["handover_date"][:4], "source_type": "HANDOVER",
            "source_id": handover_id, "employee_id": emp["id"], "project_id": cur.get("project_id"),
            "bast_date": cur["handover_date"], "manual_number": cur.get("manual_number"),
            "manual_number_norm": cur.get("manual_number_norm"), "doc_state": "ISSUED", "snapshot": snap,
            "issued_at": now(), "issued_by": actor}
    await tx.insert("asset_basts", dict(bast))
    for it in items:
        a = assets[it["asset_id"]]
        holding = {**_stamp(actor), "company_id": cid, "asset_id": a["id"], "employee_id": emp["id"],
                   "handover_id": handover_id, "handover_bast_id": bast["id"], "start_date": cur["handover_date"],
                   "project_id": cur.get("project_id"), "work_location_id": cur.get("work_location_id"),
                   "initial_condition_id": it.get("condition_id"), "accessories_out": it.get("accessories"),
                   "holding_status": ACTIVE, "active_lock": a["id"]}
        await tx.insert("asset_holdings", dict(holding))
        await tx.update("assets", {"company_id": cid, "id": a["id"]},
                        {"lifecycle_state": "IN_USE", "status_id": in_use["id"], "project_id": cur.get("project_id"),
                         "work_location_id": cur.get("work_location_id"), "condition_id": it.get("condition_id"),
                         "row_version": int(a.get("row_version") or 1) + 1, **_stamp(actor, False)})
        await tx.insert("asset_events", _event(cid, a["id"], "HANDOVER", actor, from_state="READY", to_state="IN_USE",
                                               project_id=cur.get("project_id"), work_location_id=cur.get("work_location_id"),
                                               condition_id=it.get("condition_id"), status_id=in_use["id"],
                                               employee_id=emp["id"], holding_id=holding["id"], bast_id=bast["id"],
                                               changes={"bast_number": number}))
    await tx.update("asset_handovers", {"company_id": cid, "id": handover_id},
                    {"doc_state": PUBLISHED, "bast_id": bast["id"], "published_at": now(), "published_by": actor,
                     **_stamp(actor, False)})
    return number


@router.post("/asset-handovers/{handover_id}/publish")
async def publish_handover(handover_id: str, ctx: AuthContext = Depends(require_permission("asset_handover", "publish"))):
    cid = ctx.company_id
    ho = await _visible(ctx, "asset_handovers", handover_id)
    if ho.get("doc_state") != DRAFT:
        raise _conflict("Penyerahan ini sudah diterbitkan atau dibatalkan.")
    scope = await dscope.get_scope(ctx)                         # scope dicek ulang saat publish
    emp = await _employee(ctx, scope, ho.get("employee_id"))
    await dscope.ensure_target_project_allowed(ctx, ho.get("project_id"))
    items = await get_db().asset_handover_items.find({"company_id": cid, "handover_id": handover_id}, NO_ID).sort([("line_no", 1)]).to_list(500)
    if not items:
        raise _unprocessable("Draft penyerahan tidak memiliki item aset.")
    in_use, prepared = await _handover_prepare(ctx, ho["handover_date"])
    async with _atomic(HO_CONFLICT) as tx:
        number = await _handover_finalize(tx, ctx, scope, handover_id, emp, items, in_use, prepared)
    await log_action(ctx, "publish", "asset_handover", handover_id, number, after={"items": len(items), "bast": number}, module="asset")
    return await _handover_detail(ctx, await _visible(ctx, "asset_handovers", handover_id))


@router.post("/asset-handovers/save-and-publish", status_code=201)
async def save_and_publish_new_handover(payload: Dict[str, Any] = Body(...),
                                        ctx: AuthContext = Depends(require_permission("asset_handover", "publish"))):
    """Simpan & Publish dari form baru: buat draft + publish dalam SATU transaksi. Gagal -> tidak ada draft,
    holding, perubahan status, maupun nomor BAST yang tersisa."""
    _require_also(ctx, "asset_handover", "create")
    data = await _validate_handover(ctx, payload)
    items = data.pop("items")
    scope = await dscope.get_scope(ctx)
    emp = await _employee(ctx, scope, data["employee_id"])
    in_use, prepared = await _handover_prepare(ctx, data["handover_date"])
    doc = {**_stamp(ctx.user_id), "company_id": ctx.company_id, "doc_state": DRAFT, "ga_pic_user_id": ctx.user_id,
           "row_version": 1, **data}
    async with _atomic(HO_CONFLICT) as tx:
        await tx.insert("asset_handovers", dict(doc))
        rows = await _write_items(tx, "asset_handover_items", "handover_id", doc["id"], ctx.company_id, items, ctx.user_id)
        number = await _handover_finalize(tx, ctx, scope, doc["id"], emp, rows, in_use, prepared)
    await log_action(ctx, "create", "asset_handover", doc["id"], "Penyerahan (Simpan & Publish)", after={"items": len(rows)}, module="asset")
    await log_action(ctx, "publish", "asset_handover", doc["id"], number, after={"items": len(rows), "bast": number}, module="asset")
    return await _handover_detail(ctx, await _visible(ctx, "asset_handovers", doc["id"]))


@router.post("/asset-handovers/{handover_id}/save-and-publish")
async def save_and_publish_handover(handover_id: str, payload: Dict[str, Any] = Body(...),
                                    ctx: AuthContext = Depends(require_permission("asset_handover", "publish"))):
    """Simpan & Publish draft existing: update draft + publish dalam SATU transaksi. Gagal -> draft kembali ke versi
    tersimpan sebelumnya (rollback)."""
    _require_also(ctx, "asset_handover", "edit")
    cur = await _visible(ctx, "asset_handovers", handover_id)
    if cur.get("doc_state") != DRAFT:
        raise _conflict("Penyerahan ini sudah diterbitkan atau dibatalkan.")
    data = await _validate_handover(ctx, payload)
    items = data.pop("items")
    scope = await dscope.get_scope(ctx)
    emp = await _employee(ctx, scope, data["employee_id"])
    in_use, prepared = await _handover_prepare(ctx, data["handover_date"])
    async with _atomic(HO_CONFLICT) as tx:
        locked = await tx.select_one_for_update("asset_handovers", {"company_id": ctx.company_id, "id": handover_id})
        if not locked or locked.get("doc_state") != DRAFT:
            raise _conflict("Penyerahan ini sudah diterbitkan atau dibatalkan.")
        await tx.update("asset_handovers", {"company_id": ctx.company_id, "id": handover_id},
                        {**data, **_stamp(ctx.user_id, False), "row_version": int(locked.get("row_version") or 1) + 1})
        rows = await _write_items(tx, "asset_handover_items", "handover_id", handover_id, ctx.company_id, items, ctx.user_id)
        number = await _handover_finalize(tx, ctx, scope, handover_id, emp, rows, in_use, prepared)
    await log_action(ctx, "update", "asset_handover", handover_id, "Draft penyerahan (Simpan & Publish)", after={"items": len(rows)}, module="asset")
    await log_action(ctx, "publish", "asset_handover", handover_id, number, after={"items": len(rows), "bast": number}, module="asset")
    return await _handover_detail(ctx, await _visible(ctx, "asset_handovers", handover_id))


async def _edit_manual(ctx, coll: str, resource: str, record_id: str, payload: Dict[str, Any]):
    cur = await _visible(ctx, coll, record_id)
    if cur.get("doc_state") != PUBLISHED:
        raise _conflict("Nomor referensi draft diubah melalui form draft.")
    manual = _text(payload.get("manual_number"), 128)
    vals = {"manual_number": manual, "manual_number_norm": _norm_manual(manual), **_stamp(ctx.user_id, False)}
    async with transaction() as tx:
        await tx.update(coll, {"company_id": ctx.company_id, "id": record_id}, vals)
        if cur.get("bast_id"):   # kolom pencarian saja; snapshot/PDF tetap immutable
            await tx.update("asset_basts", {"company_id": ctx.company_id, "id": cur["bast_id"]},
                            {"manual_number": manual, "manual_number_norm": vals["manual_number_norm"]})
    await log_action(ctx, "update_manual_number", resource, record_id, manual or "-",
                     before={"manual_number": cur.get("manual_number")}, after={"manual_number": manual}, module="asset")
    return {"id": record_id, "manual_number": manual,
            "manual_number_warning": await _manual_warning(ctx.company_id, vals["manual_number_norm"], [record_id])}


@router.put("/asset-handovers/{handover_id}/manual-number")
async def handover_manual_number(handover_id: str, payload: Dict[str, Any] = Body(...),
                                 ctx: AuthContext = Depends(require_permission("asset_handover", "edit"))):
    return await _edit_manual(ctx, "asset_handovers", "asset_handover", handover_id, payload)


# ------------------------------------------------------------------ Holding & Pengembalian (return)
RT_FIELDS = {"employee_id", "return_date", "ga_pic_name", "manual_number", "notes", "items"}


@router.get("/asset-holdings")
async def list_holdings(employee_id: Optional[str] = None, holding_status: str = ACTIVE, asset_id: Optional[str] = None,
                        ctx: AuthContext = Depends(require_permission("asset_return", "view"))):
    scope = await dscope.get_scope(ctx)
    flt: Dict[str, Any] = {"company_id": ctx.company_id, "holding_status": holding_status}
    if employee_id:
        flt["employee_id"] = employee_id
    if asset_id:
        flt["asset_id"] = asset_id
    flt = dscope.with_scope(dscope.with_project_scope(flt, scope), scope, "employee_id")   # project + karyawan dalam scope
    rows = await get_db().asset_holdings.find(flt, NO_ID).sort([("start_date", -1)]).to_list(1000)
    assets = await _names(ctx.company_id, "assets", [r["asset_id"] for r in rows], None)
    for r in rows:
        a = assets.get(r["asset_id"]) or {}
        r.update({"asset_code": a.get("asset_code"), "asset_name": a.get("name"), "serial_number": a.get("serial_number"),
                  "condition_id": a.get("condition_id")})
    items = await _decorate(ctx.company_id, rows)
    ho_basts = await _names(ctx.company_id, "asset_basts", [r.get("handover_bast_id") for r in items], "system_number")
    for r in items:
        r["bast_number"] = ho_basts.get(r.get("handover_bast_id"))   # nomor BAST Penyerahan asal holding
    return {"items": items, "total": len(items)}


@router.get("/asset-returns/options")
async def return_options(include_employees: bool = True,
                         ctx: AuthContext = Depends(require_permission("asset_return", "view"))):
    """`include_employees=false` (UI CP2.1): karyawan pemegang dicari lewat /asset-returns/employee-search."""
    scope = await dscope.get_scope(ctx)
    db, cid = get_db(), ctx.company_id
    holders = (await db.asset_holdings.find(dscope.with_scope(dscope.with_project_scope(
        {"company_id": cid, "holding_status": ACTIVE}, scope), scope, "employee_id"), NO_ID).to_list(5000)) if include_employees else []
    emps = await _names(cid, "employees", [h["employee_id"] for h in holders], None)
    conds = await db.asset_conditions.find({"company_id": cid, "status": "active"}, NO_ID).sort([("sort_order", 1)]).to_list(200)
    return {"employees": sorted([{"id": e["id"], "full_name": e.get("full_name"), "employee_number": e.get("employee_number")}
                                 for e in emps.values()], key=lambda x: x["full_name"] or ""),
            "conditions": [{"id": c["id"], "name": c.get("name")} for c in conds],
            "ga_pic_name": (await _user_names([ctx.user_id])).get(ctx.user_id)}


@router.get("/asset-returns/employee-search")
async def return_employee_search(q: Optional[str] = None, page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=EMP_SEARCH_MAX),
                                 ctx: AuthContext = Depends(require_permission("asset_return", "view"))):
    """Karyawan yang memegang aset aktif (untuk form Pengembalian), dicari di server + scope 01I."""
    return await _employee_search(ctx, q, page, limit, holders_only=True)


async def _validate_return(ctx: AuthContext, payload: Dict[str, Any]) -> Dict[str, Any]:
    unknown = sorted(k for k in payload if k not in RT_FIELDS)
    if unknown:
        raise _unprocessable(f"Kolom tidak dikenal: {', '.join(unknown)}.")
    scope = await dscope.get_scope(ctx)
    emp = await _employee(ctx, scope, payload.get("employee_id"))
    items = _clean_items(payload.get("items"), "holding_id")
    db, projects = get_db(), set()
    for it in items:
        h = await db.asset_holdings.find_one(dscope.with_project_scope({"company_id": ctx.company_id, "id": it["holding_id"]}, scope), NO_ID)
        if not h:
            raise _not_found()
        if h.get("holding_status") != ACTIVE or h.get("employee_id") != emp["id"]:
            raise _conflict("Aset tidak sedang dipegang aktif oleh karyawan ini.")
        if not it.get("condition_id"):
            raise _unprocessable("Kondisi saat dikembalikan wajib diisi untuk setiap aset.")
        await _master(ctx.company_id, "asset_conditions", it["condition_id"], "Kondisi")
        it["asset_id"] = h["asset_id"]
        projects.add(h.get("project_id"))
    if len(projects) > 1:
        raise _unprocessable("Satu transaksi pengembalian hanya untuk aset dari project yang sama. Pisahkan per project.")
    manual = _text(payload.get("manual_number"), 128)
    return {"employee_id": emp["id"], "return_date": _date(payload.get("return_date"), "Tanggal pengembalian"),
            "project_id": next(iter(projects)), "ga_pic_name": _text(payload.get("ga_pic_name"), 255),
            "manual_number": manual, "manual_number_norm": _norm_manual(manual), "notes": _text(payload.get("notes")),
            "items": items}


async def _return_detail(ctx, doc: Dict[str, Any]) -> Dict[str, Any]:
    db = get_db()
    items = await db.asset_return_items.find({"company_id": ctx.company_id, "return_id": doc["id"]}, NO_ID).sort([("line_no", 1)]).to_list(500)
    assets = await _names(ctx.company_id, "assets", [i["asset_id"] for i in items], None)
    conds = await _names(ctx.company_id, "asset_conditions", [i.get("condition_id") for i in items])
    for i in items:
        a = assets.get(i["asset_id"]) or {}
        i.update({"asset_code": a.get("asset_code"), "asset_name": a.get("name"), "serial_number": a.get("serial_number"),
                  "lifecycle_state": a.get("lifecycle_state"), "condition_name": conds.get(i.get("condition_id"))})
    return await _finish_detail(ctx, doc, items)


@router.get("/asset-returns")
async def list_returns(doc_state: Optional[str] = None, employee_id: Optional[str] = None, q: Optional[str] = None,
                       project_id: Optional[str] = None, page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100),
                       ctx: AuthContext = Depends(require_permission("asset_return", "view"))):
    flt: Dict[str, Any] = {"company_id": ctx.company_id, "status": "active"}
    if doc_state:
        flt["doc_state"] = doc_state
    if employee_id:
        flt["employee_id"] = employee_id
    if project_id:
        flt["project_id"] = project_id
    search = _doc_search(ctx.company_id, q)
    if search is not None:
        flt["$sql"] = [search]
    total, rows = await _list(ctx, "asset_returns", flt, page, limit)
    return _page(total, page, limit, await _decorate(ctx.company_id, rows))


@router.post("/asset-returns", status_code=201)
async def create_return(payload: Dict[str, Any] = Body(...), ctx: AuthContext = Depends(require_permission("asset_return", "create"))):
    data = await _validate_return(ctx, payload)
    items = data.pop("items")
    doc = {**_stamp(ctx.user_id), "company_id": ctx.company_id, "doc_state": DRAFT, "ga_pic_user_id": ctx.user_id,
           "row_version": 1, **data}
    async with transaction() as tx:
        await tx.insert("asset_returns", dict(doc))
        await _write_items(tx, "asset_return_items", "return_id", doc["id"], ctx.company_id, items, ctx.user_id)
    await log_action(ctx, "create", "asset_return", doc["id"], "Draft pengembalian", after={"items": len(items)}, module="asset")
    return await _return_detail(ctx, doc)


@router.get("/asset-returns/{return_id}")
async def get_return(return_id: str, ctx: AuthContext = Depends(require_permission("asset_return", "view"))):
    return await _return_detail(ctx, await _visible(ctx, "asset_returns", return_id))


@router.put("/asset-returns/{return_id}")
async def update_return(return_id: str, payload: Dict[str, Any] = Body(...),
                        ctx: AuthContext = Depends(require_permission("asset_return", "edit"))):
    cur = await _visible(ctx, "asset_returns", return_id)
    if cur.get("doc_state") != DRAFT:
        raise _conflict("Hanya draft pengembalian yang dapat diubah.")
    data = await _validate_return(ctx, payload)
    items = data.pop("items")
    async with transaction() as tx:
        locked = await tx.select_one_for_update("asset_returns", {"company_id": ctx.company_id, "id": return_id})
        if not locked or locked.get("doc_state") != DRAFT:
            raise _conflict("Draft pengembalian sudah tidak dapat diubah.")
        await tx.update("asset_returns", {"company_id": ctx.company_id, "id": return_id},
                        {**data, **_stamp(ctx.user_id, False), "row_version": int(locked.get("row_version") or 1) + 1})
        await _write_items(tx, "asset_return_items", "return_id", return_id, ctx.company_id, items, ctx.user_id)
    await log_action(ctx, "update", "asset_return", return_id, "Draft pengembalian", after={"items": len(items)}, module="asset")
    return await _return_detail(ctx, await _visible(ctx, "asset_returns", return_id))


@router.post("/asset-returns/{return_id}/cancel")
async def cancel_return(return_id: str, ctx: AuthContext = Depends(require_permission("asset_return", "edit"))):
    return await _cancel(ctx, "asset_returns", "asset_return", return_id)


@router.put("/asset-returns/{return_id}/manual-number")
async def return_manual_number(return_id: str, payload: Dict[str, Any] = Body(...),
                               ctx: AuthContext = Depends(require_permission("asset_return", "edit"))):
    return await _edit_manual(ctx, "asset_returns", "asset_return", return_id, payload)


RT_CONFLICT = "Konflik pengembalian bersamaan: aset sedang/sudah diproses transaksi lain. Publish dibatalkan seluruhnya."


async def _return_prepare(ctx: AuthContext, return_date: str):
    pending = await svc.default_status_for(ctx.company_id, "PENDING_INSPECTION")
    if not pending:
        raise _unprocessable("Status aset untuk kategori sistem PENDING_INSPECTION belum dikonfigurasi.")
    prepared = await doc_sequence.prepare(ctx.company_id, SEQ["RETURN"], when=date.fromisoformat(return_date), actor_id=ctx.user_id)
    return pending, prepared


async def _return_finalize(tx, ctx: AuthContext, scope, return_id: str, emp: Dict[str, Any], items: List[Dict[str, Any]],
                           pending: Dict[str, Any], prepared: Dict[str, Any]) -> str:
    """Satu-satunya logika publish pengembalian (Publish draft & Simpan & Publish), di DALAM transaksi pemanggil:
    hanya holding item yang dipilih ditutup (partial return), aset -> PENDING_INSPECTION, BAST-RTN terbit."""
    cid, actor = ctx.company_id, ctx.user_id
    if not items:
        raise _unprocessable("Draft pengembalian tidak memiliki item aset.")
    cur = await tx.select_one_for_update("asset_returns", {"company_id": cid, "id": return_id})
    if not cur or cur.get("doc_state") != DRAFT:
        raise _conflict("Pengembalian ini sudah diterbitkan atau dibatalkan.")
    assets: Dict[str, Dict[str, Any]] = {}
    holdings: Dict[str, Dict[str, Any]] = {}
    for it in sorted(items, key=lambda x: x["asset_id"]):
        a = await tx.select_one_for_update("assets", {"company_id": cid, "id": it["asset_id"]})
        h = await tx.select_one_for_update("asset_holdings", {"company_id": cid, "id": it["holding_id"]})
        if not a or not h or not scope.allows_project(h.get("project_id")):
            raise _conflict("Salah satu aset tidak lagi tersedia dalam cakupan Anda. Publish dibatalkan seluruhnya.")
        if (h.get("holding_status") != ACTIVE or h.get("employee_id") != emp["id"] or h.get("asset_id") != a["id"]
                or h.get("active_lock") != a["id"] or a.get("lifecycle_state") != "IN_USE"):
            raise _conflict(f"Aset {a.get('asset_code')} tidak lagi dipegang aktif oleh karyawan ini. Publish dibatalkan seluruhnya.")
        assets[a["id"]], holdings[h["id"]] = a, h

    async def _taken(candidate):
        return bool(await tx.select_one("asset_basts", {"company_id": cid, "system_number": candidate}))
    number = await doc_sequence.allocate_in_tx(tx, prepared, exists=_taken)
    first_h = holdings[items[0]["holding_id"]]
    snap = await _snapshot_header(tx, ctx, "RETURN", cur, emp, number, cur["return_date"], cur.get("project_id"),
                                  first_h.get("work_location_id"))
    snap["items"] = await _snapshot_items(tx, cid, assets, items)
    bast = {**_stamp(actor), "company_id": cid, "bast_type": "RETURN", "system_number": number,
            "sequence_key": SEQ["RETURN"], "sequence_period": cur["return_date"][:4], "source_type": "RETURN",
            "source_id": return_id, "employee_id": emp["id"], "project_id": cur.get("project_id"),
            "bast_date": cur["return_date"], "manual_number": cur.get("manual_number"),
            "manual_number_norm": cur.get("manual_number_norm"), "doc_state": "ISSUED", "snapshot": snap,
            "issued_at": now(), "issued_by": actor}
    await tx.insert("asset_basts", dict(bast))
    for it in items:
        a, h = assets[it["asset_id"]], holdings[it["holding_id"]]
        await tx.update("asset_holdings", {"company_id": cid, "id": h["id"]},
                        {"holding_status": CLOSED, "end_date": cur["return_date"], "return_id": return_id,
                         "return_bast_id": bast["id"], "return_condition_id": it.get("condition_id"),
                         "accessories_in": it.get("accessories"), "active_lock": None, **_stamp(actor, False)})
        await tx.update("assets", {"company_id": cid, "id": a["id"]},
                        {"lifecycle_state": "PENDING_INSPECTION", "status_id": pending["id"],
                         "condition_id": it.get("condition_id"), "row_version": int(a.get("row_version") or 1) + 1,
                         **_stamp(actor, False)})
        await tx.insert("asset_inspections", {**_stamp(actor), "company_id": cid, "return_id": return_id,
                                              "return_item_id": it["id"], "asset_id": a["id"], "holding_id": h["id"],
                                              "employee_id": emp["id"], "project_id": h.get("project_id"),
                                              "inspection_state": "PENDING"})
        await tx.insert("asset_events", _event(cid, a["id"], "RETURN", actor, from_state="IN_USE", to_state="PENDING_INSPECTION",
                                               condition_id=it.get("condition_id"), status_id=pending["id"],
                                               project_id=h.get("project_id"), employee_id=emp["id"],
                                               holding_id=h["id"], bast_id=bast["id"], changes={"bast_number": number}))
    await tx.update("asset_returns", {"company_id": cid, "id": return_id},
                    {"doc_state": PUBLISHED, "bast_id": bast["id"], "published_at": now(), "published_by": actor,
                     **_stamp(actor, False)})
    return number


@router.post("/asset-returns/{return_id}/publish")
async def publish_return(return_id: str, ctx: AuthContext = Depends(require_permission("asset_return", "publish"))):
    cid = ctx.company_id
    rt = await _visible(ctx, "asset_returns", return_id)
    if rt.get("doc_state") != DRAFT:
        raise _conflict("Pengembalian ini sudah diterbitkan atau dibatalkan.")
    scope = await dscope.get_scope(ctx)
    emp = await _employee(ctx, scope, rt.get("employee_id"))
    items = await get_db().asset_return_items.find({"company_id": cid, "return_id": return_id}, NO_ID).sort([("line_no", 1)]).to_list(500)
    if not items:
        raise _unprocessable("Draft pengembalian tidak memiliki item aset.")
    pending, prepared = await _return_prepare(ctx, rt["return_date"])
    async with _atomic(RT_CONFLICT) as tx:
        number = await _return_finalize(tx, ctx, scope, return_id, emp, items, pending, prepared)
    await log_action(ctx, "publish", "asset_return", return_id, number, after={"items": len(items), "bast": number}, module="asset")
    return await _return_detail(ctx, await _visible(ctx, "asset_returns", return_id))


@router.post("/asset-returns/save-and-publish", status_code=201)
async def save_and_publish_new_return(payload: Dict[str, Any] = Body(...),
                                      ctx: AuthContext = Depends(require_permission("asset_return", "publish"))):
    """Simpan & Publish pengembalian baru dalam SATU transaksi (tanpa draft/holding/BAST parsial bila gagal)."""
    _require_also(ctx, "asset_return", "create")
    data = await _validate_return(ctx, payload)
    items = data.pop("items")
    scope = await dscope.get_scope(ctx)
    emp = await _employee(ctx, scope, data["employee_id"])
    pending, prepared = await _return_prepare(ctx, data["return_date"])
    doc = {**_stamp(ctx.user_id), "company_id": ctx.company_id, "doc_state": DRAFT, "ga_pic_user_id": ctx.user_id,
           "row_version": 1, **data}
    async with _atomic(RT_CONFLICT) as tx:
        await tx.insert("asset_returns", dict(doc))
        rows = await _write_items(tx, "asset_return_items", "return_id", doc["id"], ctx.company_id, items, ctx.user_id)
        number = await _return_finalize(tx, ctx, scope, doc["id"], emp, rows, pending, prepared)
    await log_action(ctx, "create", "asset_return", doc["id"], "Pengembalian (Simpan & Publish)", after={"items": len(rows)}, module="asset")
    await log_action(ctx, "publish", "asset_return", doc["id"], number, after={"items": len(rows), "bast": number}, module="asset")
    return await _return_detail(ctx, await _visible(ctx, "asset_returns", doc["id"]))


@router.post("/asset-returns/{return_id}/save-and-publish")
async def save_and_publish_return(return_id: str, payload: Dict[str, Any] = Body(...),
                                  ctx: AuthContext = Depends(require_permission("asset_return", "publish"))):
    """Simpan & Publish draft pengembalian existing dalam SATU transaksi; gagal -> draft kembali ke versi tersimpan."""
    _require_also(ctx, "asset_return", "edit")
    cur = await _visible(ctx, "asset_returns", return_id)
    if cur.get("doc_state") != DRAFT:
        raise _conflict("Pengembalian ini sudah diterbitkan atau dibatalkan.")
    data = await _validate_return(ctx, payload)
    items = data.pop("items")
    scope = await dscope.get_scope(ctx)
    emp = await _employee(ctx, scope, data["employee_id"])
    pending, prepared = await _return_prepare(ctx, data["return_date"])
    async with _atomic(RT_CONFLICT) as tx:
        locked = await tx.select_one_for_update("asset_returns", {"company_id": ctx.company_id, "id": return_id})
        if not locked or locked.get("doc_state") != DRAFT:
            raise _conflict("Pengembalian ini sudah diterbitkan atau dibatalkan.")
        await tx.update("asset_returns", {"company_id": ctx.company_id, "id": return_id},
                        {**data, **_stamp(ctx.user_id, False), "row_version": int(locked.get("row_version") or 1) + 1})
        rows = await _write_items(tx, "asset_return_items", "return_id", return_id, ctx.company_id, items, ctx.user_id)
        number = await _return_finalize(tx, ctx, scope, return_id, emp, rows, pending, prepared)
    await log_action(ctx, "update", "asset_return", return_id, "Draft pengembalian (Simpan & Publish)", after={"items": len(rows)}, module="asset")
    await log_action(ctx, "publish", "asset_return", return_id, number, after={"items": len(rows), "bast": number}, module="asset")
    return await _return_detail(ctx, await _visible(ctx, "asset_returns", return_id))


# ------------------------------------------------------------------ Pemeriksaan GA (inspection)
INSP_FIELDS = {"final_condition_id", "completeness", "notes", "result_state"}


async def _inspection_view(cid: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    assets = await _names(cid, "assets", [r["asset_id"] for r in rows], None)
    conds = await _names(cid, "asset_conditions", [r.get("final_condition_id") for r in rows]
                         + [a.get("condition_id") for a in assets.values()])
    returns = await _names(cid, "asset_returns", [r["return_id"] for r in rows], None)
    basts = await _names(cid, "asset_basts", [x.get("bast_id") for x in returns.values()], "system_number")
    out = await _decorate(cid, rows)
    for r in out:
        a, rt = assets.get(r["asset_id"]) or {}, returns.get(r["return_id"]) or {}
        r.update({"asset_code": a.get("asset_code"), "asset_name": a.get("name"), "serial_number": a.get("serial_number"),
                  "lifecycle_state": a.get("lifecycle_state"), "returned_condition_name": conds.get(a.get("condition_id")),
                  "final_condition_name": conds.get(r.get("final_condition_id")), "return_date": rt.get("return_date"),
                  "bast_number": basts.get(rt.get("bast_id"))})
    return out


def _clean_inspection(payload: Dict[str, Any]) -> Dict[str, Any]:
    unknown = sorted(k for k in payload if k not in INSP_FIELDS)
    if unknown:
        raise _unprocessable(f"Kolom tidak dikenal: {', '.join(unknown)}.")
    out: Dict[str, Any] = {}
    if "final_condition_id" in payload:
        out["final_condition_id"] = payload.get("final_condition_id") or None
    for k in ("completeness", "notes"):
        if k in payload:
            out[k] = _text(payload.get(k))
    if "result_state" in payload:
        rs = payload.get("result_state") or None
        if rs and rs not in INSPECTION_RESULTS:
            raise _unprocessable("Hasil pemeriksaan harus salah satu dari READY, MAINTENANCE, DAMAGED, LOST.")
        out["result_state"] = rs
    return out


@router.get("/asset-inspections")
async def list_inspections(inspection_state: str = "PENDING", q: Optional[str] = None,
                           page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100),
                           ctx: AuthContext = Depends(require_permission("asset_inspection", "view"))):
    flt: Dict[str, Any] = {"company_id": ctx.company_id, "inspection_state": inspection_state}
    if q and q.strip():
        at, like = get_table("assets"), _like(q.strip())
        asset_ids = sa.select(at.c.id).where(at.c.company_id == ctx.company_id,
                                             sa.or_(at.c.asset_code.like(like), at.c.name.like(like), at.c.serial_number.like(like)))
        emp_ids = _employee_match(ctx.company_id, q)
        flt["$sql"] = [lambda t: sa.or_(t.c.asset_id.in_(asset_ids), t.c.employee_id.in_(emp_ids))]
    total, rows = await _list(ctx, "asset_inspections", flt, page, limit,
                              "completed_at" if inspection_state == "COMPLETED" else "created_at")
    return _page(total, page, limit, await _inspection_view(ctx.company_id, rows))


@router.get("/asset-inspections/{inspection_id}")
async def get_inspection(inspection_id: str, ctx: AuthContext = Depends(require_permission("asset_inspection", "view"))):
    return (await _inspection_view(ctx.company_id, [await _visible(ctx, "asset_inspections", inspection_id)]))[0]


@router.put("/asset-inspections/{inspection_id}")
async def save_inspection(inspection_id: str, payload: Dict[str, Any] = Body(...),
                          ctx: AuthContext = Depends(require_permission("asset_inspection", "view"))):
    cur = await _visible(ctx, "asset_inspections", inspection_id)
    # Input pertama = create; perubahan berikutnya = edit (permission-based, tanpa nama role).
    need = "create" if not cur.get("inspected_by") else "edit"
    if not ctx.has_permission("asset_inspection", need):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Anda tidak memiliki izin untuk mengisi pemeriksaan ini.")
    if cur.get("inspection_state") != "PENDING":
        raise _conflict("Pemeriksaan sudah selesai dan tidak dapat diubah.")
    vals = _clean_inspection(payload)
    if vals.get("final_condition_id"):
        await _master(ctx.company_id, "asset_conditions", vals["final_condition_id"], "Kondisi akhir")
    res = await get_db().asset_inspections.update_one(   # kondisional: tidak pernah menimpa pemeriksaan COMPLETED
        {"company_id": ctx.company_id, "id": inspection_id, "inspection_state": "PENDING"},
        {"$set": {**vals, "inspected_by": ctx.user_id, "inspected_at": now(), **_stamp(ctx.user_id, False)}})
    if not res.matched_count:
        raise _conflict("Pemeriksaan sudah selesai dan tidak dapat diubah.")
    await log_action(ctx, need, "asset_inspection", inspection_id, "Input pemeriksaan", after=vals, module="asset")
    return await get_inspection(inspection_id, ctx)


@router.post("/asset-inspections/{inspection_id}/complete")
async def complete_inspection(inspection_id: str, payload: Dict[str, Any] = Body(default={}),
                              ctx: AuthContext = Depends(require_permission("asset_inspection", "complete"))):
    cid, actor = ctx.company_id, ctx.user_id
    cur = await _visible(ctx, "asset_inspections", inspection_id)
    explicit = _clean_inspection(payload or {})
    vals = {**{k: cur.get(k) for k in INSP_FIELDS}, **explicit}
    if not explicit.get("result_state"):
        # Hasil akhir (termasuk LOST) wajib dipilih eksplisit oleh pemegang izin complete PADA aksi ini;
        # tidak pernah diturunkan otomatis dari draft, kondisi, atau kelengkapan.
        raise _unprocessable("Hasil pemeriksaan wajib dipilih secara eksplisit (READY / MAINTENANCE / DAMAGED / LOST).")
    if not vals.get("final_condition_id"):
        raise _unprocessable("Kondisi akhir wajib diisi.")
    await _master(cid, "asset_conditions", vals["final_condition_id"], "Kondisi akhir")
    scope = await dscope.get_scope(ctx)
    target = await svc.default_status_for(cid, vals["result_state"])
    if not target:
        raise _unprocessable(f"Status aset untuk kategori sistem {vals['result_state']} belum dikonfigurasi.")
    async with _atomic("Konflik pemeriksaan bersamaan: pemeriksaan sedang/sudah diselesaikan.") as tx:
        ins = await tx.select_one_for_update("asset_inspections", {"company_id": cid, "id": inspection_id})
        if not ins or ins.get("inspection_state") != "PENDING" or not scope.allows_project(ins.get("project_id")):
            raise _conflict("Pemeriksaan sudah selesai atau tidak lagi dalam cakupan Anda.")
        a = await tx.select_one_for_update("assets", {"company_id": cid, "id": ins["asset_id"]})
        if not a or a.get("lifecycle_state") != "PENDING_INSPECTION":
            raise _conflict("Aset tidak lagi berstatus Menunggu Pemeriksaan.")
        await tx.update("assets", {"company_id": cid, "id": a["id"]},
                        {"lifecycle_state": vals["result_state"], "status_id": target["id"], "condition_id": vals["final_condition_id"],
                         "row_version": int(a.get("row_version") or 1) + 1, **_stamp(actor, False)})
        await tx.update("asset_inspections", {"company_id": cid, "id": inspection_id},
                        {**vals, "inspection_state": "COMPLETED", "completed_by": actor, "completed_at": now(),
                         "inspected_by": ins.get("inspected_by") or actor, "inspected_at": ins.get("inspected_at") or now(),
                         **_stamp(actor, False)})
        await tx.insert("asset_events", _event(cid, a["id"], "INSPECTION", actor, from_state="PENDING_INSPECTION",
                                               to_state=vals["result_state"], condition_id=vals["final_condition_id"],
                                               status_id=target["id"], project_id=a.get("project_id"),
                                               employee_id=ins.get("employee_id"), holding_id=ins.get("holding_id"),
                                               changes={"inspection_id": inspection_id}, notes=vals.get("notes")))
    await log_action(ctx, "complete", "asset_inspection", inspection_id, vals["result_state"], after=vals, module="asset")
    return await get_inspection(inspection_id, ctx)


# ------------------------------------------------------------------ Dokumen BAST
def _bast_row(b: Dict[str, Any], full: bool = False) -> Dict[str, Any]:
    snap = b.get("snapshot") or {}
    out = {k: b.get(k) for k in ("id", "bast_type", "system_number", "manual_number", "bast_date", "employee_id",
                                 "project_id", "source_type", "source_id", "doc_state", "issued_at", "issued_by")}
    out.update({"employee_name": (snap.get("employee") or {}).get("full_name"),
                "employee_number": (snap.get("employee") or {}).get("employee_number"),
                "project_name": (snap.get("project") or {}).get("name"), "item_count": len(snap.get("items") or [])})
    if full:
        out["snapshot"] = snap
    return out


@router.get("/asset-basts")
async def list_basts(bast_type: Optional[str] = None, q: Optional[str] = None, employee_id: Optional[str] = None,
                     project_id: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None,
                     page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100),
                     ctx: AuthContext = Depends(require_permission("asset_bast", "view"))):
    flt: Dict[str, Any] = {"company_id": ctx.company_id}
    if bast_type:
        flt["bast_type"] = bast_type
    if employee_id:
        flt["employee_id"] = employee_id
    if project_id:
        flt["project_id"] = project_id
    sql = []
    if date_from:
        df = _date(date_from, "Tanggal awal")
        sql.append(lambda t: t.c.bast_date >= df)
    if date_to:
        dt = _date(date_to, "Tanggal akhir")
        sql.append(lambda t: t.c.bast_date <= dt)
    if q and q.strip():
        up = _like(q.strip().upper())
        mn = _like(_norm_manual(q) or "")
        emp_ids = _employee_match(ctx.company_id, q)
        sql.append(lambda t: sa.or_(sa.func.upper(t.c.system_number).like(up), t.c.manual_number_norm.like(mn),
                                    t.c.employee_id.in_(emp_ids)))
    if sql:
        flt["$sql"] = sql
    total, rows = await _list(ctx, "asset_basts", flt, page, limit, "issued_at")
    return _page(total, page, limit, [_bast_row(r) for r in rows])


@router.get("/asset-basts/{bast_id}")
async def get_bast(bast_id: str, ctx: AuthContext = Depends(require_permission("asset_bast", "view"))):
    return _bast_row(await _visible(ctx, "asset_basts", bast_id), full=True)


@router.get("/asset-basts/{bast_id}/pdf")
async def bast_pdf(bast_id: str, inline: bool = False, ctx: AuthContext = Depends(require_permission("asset_bast", "view"))):
    b = await _visible(ctx, "asset_basts", bast_id)
    pdf = build_bast_pdf(b.get("snapshot") or {})   # on-the-fly dari snapshot immutable; tidak disimpan
    fname = (b.get("system_number") or "BAST").replace("/", "-")
    disp = "inline" if inline else "attachment"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'{disp}; filename="{fname}.pdf"', "Cache-Control": "no-store"})
