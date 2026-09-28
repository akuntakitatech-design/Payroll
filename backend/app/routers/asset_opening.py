"""Phase 2A CP3 - Saldo Awal Aset / Opening Existing Holding.

Untuk aset yang SUDAH dipegang karyawan saat HRGA mulai dipakai - tanpa membuat transaksi Penyerahan palsu.
Alur: MASTER ASSET (READY) -> Opening (DRAFT -> PUBLISHED) -> IN_USE + holding ACTIVE + BAST-EXS/{YYYY}/{SEQ:6}.
- Publish atomik (satu transaksi): kunci aset (FOR UPDATE, urutan stabil), validasi ulang karyawan/scope/aset, aset wajib
  READY & tanpa holding aktif, nomor BAST-EXS (doc_sequence, per company + tahun), snapshot immutable, holding (tabel
  CP2 `asset_holdings`, opening_id), status IN_USE, event OPENING_EXISTING. Satu gagal -> rollback seluruhnya.
- Setelah publish, siklus sama persis dengan CP2 (Pengembalian -> Pemeriksaan). Tidak ada lifecycle kedua.
- `finalize_openings` dipakai bersama oleh Publish draft, Simpan & Publish, dan Impor Saldo Awal massal.
- 01I: list/detail/lookup difilter di SQL; UUID di luar scope -> 404 generik. Otorisasi murni permission efektif.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import sqlalchemy as sa
from fastapi import APIRouter, Body, Depends, Query

from ..core import asset_service as svc
from ..core import data_scope as dscope
from ..core import doc_sequence
from ..core.audit import log_action
from ..core.db import NO_ID, _row_to_doc, get_db, get_table, now, transaction
from ..core.deps import AuthContext, require_permission
from .asset_lifecycle import (ACTIVE, CANCELLED, DRAFT, PUBLISHED, _atomic, _cancel, _clean_items, _conflict, _date,
                              _decorate, _doc_search, _employee, _employee_search, _like, _list, _names, _norm_manual,
                              _not_found, _page, _require_also, _stamp, _text, _unprocessable, _user_names, _visible,
                              _write_items)
from .assets import _event, _master

router = APIRouter(tags=["Manajemen Aset - Saldo Awal"])

SEQ_EXS = "BAST_EXISTING"
OP_FIELDS = {"employee_id", "opening_date", "project_id", "work_location_id", "ga_pic_name", "manual_number", "notes", "items"}
OP_CONFLICT = ("Konflik saldo awal bersamaan: aset sudah memiliki pemegang aktif atau sedang diproses. "
               "Publish dibatalkan seluruhnya.")
EVENT_OPENING = "OPENING_EXISTING"


# ------------------------------------------------------------------ helpers
async def employee_default_project(cid: str, employee_id: str) -> Optional[str]:
    asg = await get_db().employee_assignments.find(
        {"company_id": cid, "employee_id": employee_id, "assignment_status": "ACTIVE"}, NO_ID).to_list(5)
    return next((a.get("project_id") for a in asg if a.get("project_id")), None)


async def validate_opening(ctx: AuthContext, payload: Dict[str, Any]) -> Dict[str, Any]:
    unknown = sorted(k for k in payload if k not in OP_FIELDS)
    if unknown:
        raise _unprocessable(f"Kolom tidak dikenal: {', '.join(unknown)}.")
    scope = await dscope.get_scope(ctx)
    emp = await _employee(ctx, scope, payload.get("employee_id"))
    project_id = payload.get("project_id") or await employee_default_project(ctx.company_id, emp["id"])
    await dscope.ensure_target_project_allowed(ctx, project_id)
    await _master(ctx.company_id, "projects", project_id, "Project")
    await _master(ctx.company_id, "work_locations", payload.get("work_location_id") or None, "Lokasi kerja")
    items = _clean_items(payload.get("items"), "asset_id")
    db = get_db()
    for it in items:
        a = await db.assets.find_one(dscope.with_project_scope({"company_id": ctx.company_id, "id": it["asset_id"]}, scope), NO_ID)
        if not a or a.get("status") == "deleted":
            raise _not_found()
        if a.get("lifecycle_state") != svc.READY:
            raise _conflict(f"Aset {a.get('asset_code')} berstatus {svc.LIFECYCLE_STATES.get(a.get('lifecycle_state'))}. "
                            "Saldo awal hanya untuk aset Siap Pakai (READY) tanpa pemegang aktif.")
        if await db.asset_holdings.count_documents({"company_id": ctx.company_id, "active_lock": a["id"]}):
            raise _conflict(f"Aset {a.get('asset_code')} sudah memiliki pemegang aktif.")
        if not it.get("condition_id"):
            raise _unprocessable(f"Kondisi saat saldo awal wajib dipilih untuk aset {a.get('asset_code')}.")
        await _master(ctx.company_id, "asset_conditions", it["condition_id"], "Kondisi")
    opening_date = _date(payload.get("opening_date"), "Tanggal saldo awal")
    if opening_date > date.today().isoformat():
        raise _unprocessable("Tanggal saldo awal tidak boleh di masa depan.")
    manual = _text(payload.get("manual_number"), 128)
    return {"employee_id": emp["id"], "opening_date": opening_date, "project_id": project_id,
            "work_location_id": payload.get("work_location_id") or None, "ga_pic_name": _text(payload.get("ga_pic_name"), 255),
            "manual_number": manual, "manual_number_norm": _norm_manual(manual), "notes": _text(payload.get("notes")),
            "items": items}


async def prepare_opening(ctx: AuthContext, dates: List[str]):
    """Di luar transaksi: status IN_USE + baris counter BAST-EXS per tahun (tidak mengonsumsi nomor)."""
    in_use = await svc.default_status_for(ctx.company_id, svc.IN_USE)
    if not in_use:
        raise _unprocessable("Status aset untuk kategori sistem IN_USE belum dikonfigurasi.")
    prepared = {}
    for d in sorted({x[:4] for x in dates}):
        prepared[d] = await doc_sequence.prepare(ctx.company_id, SEQ_EXS, when=date(int(d), 1, 1), actor_id=ctx.user_id)
    return in_use, prepared


async def lock_sequences(tx, prepared: Dict[str, Any]) -> None:
    """Kunci baris counter BAST-EXS PALING AWAL di transaksi publish: publish paralel berurutan rapi (tanpa deadlock
    gap-lock antar insert holding/BAST); nomor tetap dialokasikan belakangan oleh allocate_many_in_tx."""
    for key in sorted(prepared):
        await tx.select_one_for_update("document_sequence_counters", prepared[key]["flt"])


async def _lock_rows(tx, table_name: str, cid: str, ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """SELECT ... FOR UPDATE massal dengan urutan id stabil (hindari deadlock)."""
    out: Dict[str, Dict[str, Any]] = {}
    t = get_table(table_name)
    ids = sorted(set(ids))
    for i in range(0, len(ids), 500):
        res = await tx.conn.execute(sa.select(t).where(t.c.company_id == cid, t.c.id.in_(ids[i:i + 500]))
                                    .order_by(t.c.id).with_for_update())
        for row in res.fetchall():
            d = _row_to_doc(row)
            out[d["id"]] = d
    return out


async def _select_in(tx, table_name: str, cid: str, col: str, values: List[str]) -> List[Dict[str, Any]]:
    t = get_table(table_name)
    out: List[Dict[str, Any]] = []
    values = sorted({v for v in values if v})
    for i in range(0, len(values), 500):
        res = await tx.conn.execute(sa.select(t).where(t.c.company_id == cid, getattr(t.c, col).in_(values[i:i + 500])))
        out += [_row_to_doc(r) for r in res.fetchall()]
    return out


async def finalize_openings(tx, ctx: AuthContext, scope, groups: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]],
                            in_use: Dict[str, Any], prepared: Dict[str, Any]) -> List[str]:
    """SATU-SATUNYA logika publish saldo awal, di DALAM transaksi pemanggil. `groups` = [(opening_draft, items)].
    Kunci + validasi ulang seluruh opening/karyawan/aset, nomor BAST-EXS, snapshot, holding, status, event.
    Error apa pun -> exception -> transaksi pemanggil rollback (tidak ada opening parsial)."""
    cid, actor = ctx.company_id, ctx.user_id
    if not groups:
        raise _unprocessable("Tidak ada saldo awal untuk diterbitkan.")
    ops = await _lock_rows(tx, "asset_openings", cid, [g[0]["id"] for g in groups])
    for g in groups:
        cur = ops.get(g[0]["id"])
        if not cur or cur.get("doc_state") != DRAFT:
            raise _conflict("Saldo awal sudah diterbitkan atau dibatalkan.")
        if not g[1]:
            raise _unprocessable("Draft saldo awal tidak memiliki item aset.")
        if not scope.allows_project(cur.get("project_id")):
            raise _conflict("Project saldo awal tidak lagi dalam cakupan Anda. Publish dibatalkan seluruhnya.")
    all_ids = [it["asset_id"] for _, items in groups for it in items]
    if len(all_ids) != len(set(all_ids)):
        raise _conflict("Aset yang sama tidak boleh masuk lebih dari satu saldo awal. Publish dibatalkan seluruhnya.")
    assets = await _lock_rows(tx, "assets", cid, all_ids)
    for aid in all_ids:
        a = assets.get(aid)
        if not a or a.get("status") == "deleted" or not scope.allows_project(a.get("project_id")):
            raise _conflict("Salah satu aset tidak lagi tersedia dalam cakupan Anda. Publish dibatalkan seluruhnya.")
        if a.get("lifecycle_state") != svc.READY:
            raise _conflict(f"Aset {a.get('asset_code')} tidak lagi Siap Pakai (READY). Publish dibatalkan seluruhnya.")
    held = await _select_in(tx, "asset_holdings", cid, "active_lock", all_ids)
    if held:
        code = assets.get(held[0]["asset_id"], {}).get("asset_code")
        raise _conflict(f"Aset {code} sudah memiliki pemegang aktif. Publish dibatalkan seluruhnya.")
    emps = {e["id"]: e for e in await _select_in(tx, "employees", cid, "id", [ops[g[0]["id"]]["employee_id"] for g in groups])}
    for g in groups:
        e = emps.get(ops[g[0]["id"]]["employee_id"])
        if not e or e.get("status") != "active":
            raise _unprocessable("Karyawan tidak lagi aktif.")

    # label master untuk snapshot (sekali muat)
    maps = {coll: {r["id"]: r for r in await _select_in(tx, coll, cid, "id", ids)} for coll, ids in (
        ("asset_categories", [a.get("category_id") for a in assets.values()]),
        ("asset_units", [a.get("unit_id") for a in assets.values()]),
        ("asset_conditions", [it.get("condition_id") for _, items in groups for it in items]),
        ("projects", [ops[g[0]["id"]].get("project_id") for g in groups]),
        ("work_locations", [ops[g[0]["id"]].get("work_location_id") for g in groups]),
        ("positions", [e.get("position_id") for e in emps.values()]))}
    company = await tx.select_one("companies", {"id": cid}) or {}
    issuer = await tx.select_one("users", {"id": actor}) or {}

    by_year: Dict[str, List[Dict[str, Any]]] = {}
    for g in groups:
        by_year.setdefault(ops[g[0]["id"]]["opening_date"][:4], []).append(ops[g[0]["id"]])
    numbers: Dict[str, str] = {}
    for year, docs in by_year.items():
        async def _taken(cands):
            rows = await _select_in(tx, "asset_basts", cid, "system_number", cands)
            return {r["system_number"] for r in rows}
        for doc, num in zip(docs, await doc_sequence.allocate_many_in_tx(tx, prepared[year], len(docs), taken=_taken)):
            numbers[doc["id"]] = num

    ts, issued = now(), now().strftime("%Y-%m-%d %H:%M UTC")
    basts, holdings, events, out = [], [], [], []
    for g in groups:
        cur, items = ops[g[0]["id"]], g[1]
        emp, number = emps[cur["employee_id"]], numbers[cur["id"]]
        name = lambda coll, rid: (maps[coll].get(rid) or {}).get("name")  # noqa: E731
        snap = {"bast_type": "EXISTING", "system_number": number, "manual_number": cur.get("manual_number"),
                "bast_date": cur["opening_date"],
                "company": {k: company.get(k) for k in ("code", "name", "legal_name", "address", "city")},
                "employee": {**{k: emp.get(k) for k in ("id", "full_name", "employee_number", "job_title")},
                             "position": name("positions", emp.get("position_id"))},
                "project": {"id": cur.get("project_id"), "name": name("projects", cur.get("project_id")),
                            "code": (maps["projects"].get(cur.get("project_id")) or {}).get("code")},
                "work_location": {"id": cur.get("work_location_id"), "name": name("work_locations", cur.get("work_location_id"))},
                "ga_pic_name": cur.get("ga_pic_name"), "notes": cur.get("notes"), "issued_at": issued,
                "issued_by_name": issuer.get("full_name") or issuer.get("email"), "items": []}
        for it in sorted(items, key=lambda x: x.get("line_no") or 0):
            a = assets[it["asset_id"]]
            snap["items"].append({"line_no": it.get("line_no"), "asset_id": a["id"], "asset_code": a.get("asset_code"),
                                  "legacy_code": a.get("legacy_code"), "name": a.get("name"),
                                  "category": name("asset_categories", a.get("category_id")), "brand": a.get("brand"),
                                  "model": a.get("model"), "serial_number": a.get("serial_number"),
                                  "unit": name("asset_units", a.get("unit_id")),
                                  "condition": name("asset_conditions", it.get("condition_id")),
                                  "accessories": it.get("accessories"), "item_notes": it.get("item_notes")})
        bast = {**_stamp(actor), "company_id": cid, "bast_type": "EXISTING", "system_number": number,
                "sequence_key": SEQ_EXS, "sequence_period": cur["opening_date"][:4], "source_type": "OPENING",
                "source_id": cur["id"], "employee_id": emp["id"], "project_id": cur.get("project_id"),
                "bast_date": cur["opening_date"], "manual_number": cur.get("manual_number"),
                "manual_number_norm": cur.get("manual_number_norm"), "doc_state": "ISSUED", "snapshot": snap,
                "issued_at": ts, "issued_by": actor}
        basts.append(bast)
        for it in items:
            a = assets[it["asset_id"]]
            h = {**_stamp(actor), "company_id": cid, "asset_id": a["id"], "employee_id": emp["id"], "handover_id": None,
                 "opening_id": cur["id"], "handover_bast_id": bast["id"], "start_date": cur["opening_date"],
                 "project_id": cur.get("project_id"), "work_location_id": cur.get("work_location_id"),
                 "initial_condition_id": it.get("condition_id"), "accessories_out": it.get("accessories"),
                 "holding_status": ACTIVE, "active_lock": a["id"]}
            holdings.append(h)
            events.append(_event(cid, a["id"], EVENT_OPENING, actor, from_state=svc.READY, to_state=svc.IN_USE,
                                 project_id=cur.get("project_id"), work_location_id=cur.get("work_location_id"),
                                 condition_id=it.get("condition_id"), status_id=in_use["id"], employee_id=emp["id"],
                                 holding_id=h["id"], bast_id=bast["id"],
                                 changes={"bast_number": number, "opening_id": cur["id"],
                                          "status": {"from": svc.READY, "to": svc.IN_USE}}))
        out.append(number)
    await tx.insert_many("asset_basts", basts)
    await tx.insert_many("asset_holdings", holdings)
    await tx.insert_many("asset_events", events)
    t_asset = get_table("assets")
    for g in groups:
        cur, bast = ops[g[0]["id"]], next(b for b in basts if b["source_id"] == g[0]["id"])
        for it in g[1]:
            a = assets[it["asset_id"]]
            await tx.conn.execute(sa.update(t_asset).where(t_asset.c.company_id == cid, t_asset.c.id == a["id"]).values(
                lifecycle_state=svc.IN_USE, status_id=in_use["id"], project_id=cur.get("project_id"),
                work_location_id=cur.get("work_location_id") or a.get("work_location_id"), condition_id=it.get("condition_id"),
                row_version=int(a.get("row_version") or 1) + 1, updated_at=ts.replace(tzinfo=None), updated_by=actor))
        await tx.update("asset_openings", {"company_id": cid, "id": cur["id"]},
                        {"doc_state": PUBLISHED, "bast_id": bast["id"], "published_at": ts, "published_by": actor,
                         **_stamp(actor, False)})
    return out


async def _detail(ctx: AuthContext, doc: Dict[str, Any]) -> Dict[str, Any]:
    db = get_db()
    items = await db.asset_opening_items.find({"company_id": ctx.company_id, "opening_id": doc["id"]}, NO_ID).sort([("line_no", 1)]).to_list(1000)
    assets = await _names(ctx.company_id, "assets", [i["asset_id"] for i in items], None)
    conds = await _names(ctx.company_id, "asset_conditions", [i.get("condition_id") for i in items])
    for i in items:
        a = assets.get(i["asset_id"]) or {}
        i.update({"asset_code": a.get("asset_code"), "legacy_code": a.get("legacy_code"), "asset_name": a.get("name"),
                  "serial_number": a.get("serial_number"), "lifecycle_state": a.get("lifecycle_state"),
                  "condition_name": conds.get(i.get("condition_id"))})
    out = (await _decorate(ctx.company_id, [doc]))[0]
    out["items"] = items
    out["bast_snapshot"] = None
    if doc.get("bast_id"):
        b = await db.asset_basts.find_one({"company_id": ctx.company_id, "id": doc["bast_id"]}, NO_ID)
        out["bast_snapshot"] = (b or {}).get("snapshot")
    out["permissions"] = _perms(ctx)
    return out


def _perms(ctx: AuthContext) -> Dict[str, bool]:
    return {k: ctx.has_permission("asset_opening", k) for k in ("view", "create", "edit", "publish")}


# ------------------------------------------------------------------ lookup
@router.get("/asset-openings/options")
async def opening_options(ctx: AuthContext = Depends(require_permission("asset_opening", "view"))):
    scope = await dscope.get_scope(ctx)
    db, cid = get_db(), ctx.company_id
    pflt = {"company_id": cid, "status": "active"}
    if not scope.is_all:
        pflt["id"] = {"$in": sorted(scope.project_ids) or ["-"]}
    projects = await db.projects.find(pflt, NO_ID).sort([("name", 1)]).to_list(1000)
    locs = await db.work_locations.find({"company_id": cid, "status": "active"}, NO_ID).sort([("name", 1)]).to_list(1000)
    conds = await db.asset_conditions.find({"company_id": cid, "status": "active"}, NO_ID).sort([("sort_order", 1)]).to_list(200)
    return {"projects": [{"id": p["id"], "name": p.get("name")} for p in projects],
            "work_locations": [{"id": w["id"], "name": w.get("name")} for w in locs],
            "conditions": [{"id": c["id"], "name": c.get("name")} for c in conds],
            "restricted": not scope.is_all, "permissions": _perms(ctx),
            "ga_pic_name": (await _user_names([ctx.user_id])).get(ctx.user_id)}


@router.get("/asset-openings/employee-search")
async def opening_employee_search(q: Optional[str] = None, page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=50),
                                  ctx: AuthContext = Depends(require_permission("asset_opening", "view"))):
    return await _employee_search(ctx, q, page, limit, holders_only=False)


@router.get("/asset-openings/employee-context")
async def opening_employee_context(employee_id: str, ctx: AuthContext = Depends(require_permission("asset_opening", "view"))):
    """Default project dari assignment aktif karyawan (hanya bila dalam scope 01I)."""
    scope = await dscope.get_scope(ctx)
    emp = await _employee(ctx, scope, employee_id)
    pid = await employee_default_project(ctx.company_id, emp["id"])
    if pid and not scope.allows_project(pid):
        pid = None
    return {"employee_id": emp["id"], "project_id": pid,
            "project_name": (await _names(ctx.company_id, "projects", [pid])).get(pid) if pid else None}


@router.get("/asset-openings/asset-search")
async def opening_asset_search(q: Optional[str] = None, page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=50),
                               ctx: AuthContext = Depends(require_permission("asset_opening", "view"))):
    """Aset READY tanpa pemegang aktif (server-side, berhalaman): kode sistem / kode lama / serial / nama."""
    scope = await dscope.get_scope(ctx)
    cid = ctx.company_id
    h = get_table("asset_holdings")
    held = sa.select(h.c.active_lock).where(h.c.company_id == cid, h.c.active_lock.isnot(None))
    sql = [lambda t: t.c.id.notin_(held)]
    term = (q or "").strip()
    if term:
        like, up = _like(term), _like(svc.norm_code(term) or "")
        sn = _like(svc.norm_serial(term) or "")
        sql.append(lambda t: sa.or_(t.c.asset_code_norm.like(up), t.c.legacy_code_norm.like(up), t.c.name.like(like),
                                    t.c.serial_number_norm.like(sn)))
    flt = dscope.with_project_scope({"company_id": cid, "status": "active", "lifecycle_state": svc.READY, "$sql": sql}, scope)
    db = get_db()
    total = await db.assets.count_documents(flt)
    rows = await db.assets.find(flt, NO_ID).sort([("asset_code_norm", 1)]).skip((page - 1) * limit).limit(limit).to_list(limit)
    return _page(total, page, limit, [{k: r.get(k) for k in ("id", "asset_code", "legacy_code", "name", "serial_number",
                                                              "condition_id", "project_id")} for r in rows])


# ------------------------------------------------------------------ CRUD draft
@router.get("/asset-openings")
async def list_openings(doc_state: Optional[str] = None, q: Optional[str] = None, project_id: Optional[str] = None,
                        page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100),
                        ctx: AuthContext = Depends(require_permission("asset_opening", "view"))):
    flt: Dict[str, Any] = {"company_id": ctx.company_id, "status": "active"}
    if doc_state:
        flt["doc_state"] = doc_state
    if project_id:
        flt["project_id"] = project_id
    search = _doc_search(ctx.company_id, q)
    if search is not None:
        flt["$sql"] = [search]
    total, rows = await _list(ctx, "asset_openings", flt, page, limit)
    counts = await _item_counts(ctx.company_id, [r["id"] for r in rows])
    items = await _decorate(ctx.company_id, rows)
    for r in items:
        r["item_count"] = counts.get(r["id"], 0)
    return _page(total, page, limit, items)


async def _item_counts(cid: str, ids: List[str]) -> Dict[str, int]:
    if not ids:
        return {}
    rows = await get_db().asset_opening_items.find({"company_id": cid, "opening_id": {"$in": ids}}, NO_ID).to_list(len(ids) * 200)
    out: Dict[str, int] = {}
    for r in rows:
        out[r["opening_id"]] = out.get(r["opening_id"], 0) + 1
    return out


def _new_doc(ctx: AuthContext, data: Dict[str, Any], batch_id: Optional[str] = None) -> Dict[str, Any]:
    return {**_stamp(ctx.user_id), "company_id": ctx.company_id, "doc_state": DRAFT, "ga_pic_user_id": ctx.user_id,
            "row_version": 1, "import_batch_id": batch_id, **data}


@router.post("/asset-openings", status_code=201)
async def create_opening(payload: Dict[str, Any] = Body(...), ctx: AuthContext = Depends(require_permission("asset_opening", "create"))):
    data = await validate_opening(ctx, payload)
    items = data.pop("items")
    doc = _new_doc(ctx, data)
    async with transaction() as tx:
        await tx.insert("asset_openings", dict(doc))
        await _write_items(tx, "asset_opening_items", "opening_id", doc["id"], ctx.company_id, items, ctx.user_id)
    await log_action(ctx, "create", "asset_opening", doc["id"], "Draft saldo awal",
                     after={"items": len(items), "employee_id": doc["employee_id"], "project_id": doc.get("project_id")}, module="asset")
    return await _detail(ctx, doc)


@router.get("/asset-openings/{opening_id}")
async def get_opening(opening_id: str, ctx: AuthContext = Depends(require_permission("asset_opening", "view"))):
    return await _detail(ctx, await _visible(ctx, "asset_openings", opening_id))


@router.put("/asset-openings/{opening_id}")
async def update_opening(opening_id: str, payload: Dict[str, Any] = Body(...),
                         ctx: AuthContext = Depends(require_permission("asset_opening", "edit"))):
    cur = await _visible(ctx, "asset_openings", opening_id)
    if cur.get("doc_state") != DRAFT:
        raise _conflict("Hanya draft saldo awal yang dapat diubah.")
    data = await validate_opening(ctx, payload)
    items = data.pop("items")
    async with transaction() as tx:
        locked = await tx.select_one_for_update("asset_openings", {"company_id": ctx.company_id, "id": opening_id})
        if not locked or locked.get("doc_state") != DRAFT:
            raise _conflict("Draft saldo awal sudah tidak dapat diubah.")
        await tx.update("asset_openings", {"company_id": ctx.company_id, "id": opening_id},
                        {**data, **_stamp(ctx.user_id, False), "row_version": int(locked.get("row_version") or 1) + 1})
        await _write_items(tx, "asset_opening_items", "opening_id", opening_id, ctx.company_id, items, ctx.user_id)
    await log_action(ctx, "update", "asset_opening", opening_id, "Draft saldo awal", after={"items": len(items)}, module="asset")
    return await _detail(ctx, await _visible(ctx, "asset_openings", opening_id))


@router.post("/asset-openings/{opening_id}/cancel")
async def cancel_opening(opening_id: str, ctx: AuthContext = Depends(require_permission("asset_opening", "edit"))):
    return await _cancel(ctx, "asset_openings", "asset_opening", opening_id)


# ------------------------------------------------------------------ publish
async def _audit_publish(ctx: AuthContext, opening_id: str, number: str, n_items: int, doc: Dict[str, Any]) -> None:
    await log_action(ctx, "publish", "asset_opening", opening_id, number,
                     after={"items": n_items, "bast": number, "employee_id": doc.get("employee_id"),
                            "project_id": doc.get("project_id"), "status": {"from": svc.READY, "to": svc.IN_USE}},
                     module="asset")


@router.post("/asset-openings/{opening_id}/publish")
async def publish_opening(opening_id: str, ctx: AuthContext = Depends(require_permission("asset_opening", "publish"))):
    cid = ctx.company_id
    op = await _visible(ctx, "asset_openings", opening_id)
    if op.get("doc_state") != DRAFT:
        raise _conflict("Saldo awal ini sudah diterbitkan atau dibatalkan.")
    scope = await dscope.get_scope(ctx)
    await _employee(ctx, scope, op.get("employee_id"))
    await dscope.ensure_target_project_allowed(ctx, op.get("project_id"))
    items = await get_db().asset_opening_items.find({"company_id": cid, "opening_id": opening_id}, NO_ID).sort([("line_no", 1)]).to_list(1000)
    if not items:
        raise _unprocessable("Draft saldo awal tidak memiliki item aset.")
    in_use, prepared = await prepare_opening(ctx, [op["opening_date"]])
    async with _atomic(OP_CONFLICT) as tx:
        await lock_sequences(tx, prepared)
        number = (await finalize_openings(tx, ctx, scope, [(op, items)], in_use, prepared))[0]
    await _audit_publish(ctx, opening_id, number, len(items), op)
    return await _detail(ctx, await _visible(ctx, "asset_openings", opening_id))


@router.post("/asset-openings/save-and-publish", status_code=201)
async def save_and_publish_new_opening(payload: Dict[str, Any] = Body(...),
                                       ctx: AuthContext = Depends(require_permission("asset_opening", "publish"))):
    """Simpan & Publish form baru dalam SATU transaksi: gagal -> tidak ada draft/holding/status/BAST-EXS tersisa."""
    _require_also(ctx, "asset_opening", "create")
    data = await validate_opening(ctx, payload)
    items = data.pop("items")
    scope = await dscope.get_scope(ctx)
    in_use, prepared = await prepare_opening(ctx, [data["opening_date"]])
    doc = _new_doc(ctx, data)
    async with _atomic(OP_CONFLICT) as tx:
        await lock_sequences(tx, prepared)
        await tx.insert("asset_openings", dict(doc))
        rows = await _write_items(tx, "asset_opening_items", "opening_id", doc["id"], ctx.company_id, items, ctx.user_id)
        number = (await finalize_openings(tx, ctx, scope, [(doc, rows)], in_use, prepared))[0]
    await log_action(ctx, "create", "asset_opening", doc["id"], "Saldo awal (Simpan & Publish)", after={"items": len(rows)}, module="asset")
    await _audit_publish(ctx, doc["id"], number, len(rows), doc)
    return await _detail(ctx, await _visible(ctx, "asset_openings", doc["id"]))


@router.post("/asset-openings/{opening_id}/save-and-publish")
async def save_and_publish_opening(opening_id: str, payload: Dict[str, Any] = Body(...),
                                   ctx: AuthContext = Depends(require_permission("asset_opening", "publish"))):
    """Simpan & Publish draft existing: gagal -> draft kembali ke versi tersimpan sebelumnya (rollback)."""
    _require_also(ctx, "asset_opening", "edit")
    cur = await _visible(ctx, "asset_openings", opening_id)
    if cur.get("doc_state") != DRAFT:
        raise _conflict("Saldo awal ini sudah diterbitkan atau dibatalkan.")
    data = await validate_opening(ctx, payload)
    items = data.pop("items")
    scope = await dscope.get_scope(ctx)
    in_use, prepared = await prepare_opening(ctx, [data["opening_date"]])
    async with _atomic(OP_CONFLICT) as tx:
        await lock_sequences(tx, prepared)
        locked = await tx.select_one_for_update("asset_openings", {"company_id": ctx.company_id, "id": opening_id})
        if not locked or locked.get("doc_state") != DRAFT:
            raise _conflict("Saldo awal ini sudah diterbitkan atau dibatalkan.")
        await tx.update("asset_openings", {"company_id": ctx.company_id, "id": opening_id},
                        {**data, **_stamp(ctx.user_id, False), "row_version": int(locked.get("row_version") or 1) + 1})
        rows = await _write_items(tx, "asset_opening_items", "opening_id", opening_id, ctx.company_id, items, ctx.user_id)
        number = (await finalize_openings(tx, ctx, scope, [({**cur, **data}, rows)], in_use, prepared))[0]
    await log_action(ctx, "update", "asset_opening", opening_id, "Draft saldo awal (Simpan & Publish)", after={"items": len(rows)}, module="asset")
    await _audit_publish(ctx, opening_id, number, len(rows), {**cur, **data})
    return await _detail(ctx, await _visible(ctx, "asset_openings", opening_id))


__all__ = ["router", "finalize_openings", "prepare_opening", "lock_sequences", "employee_default_project", "CANCELLED"]
