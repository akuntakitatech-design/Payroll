"""Phase 2A CP1 - Manajemen Aset: Master Aset (Daftar Aset).

Cakupan CP1 (ASSET_BAST_FINAL_BLUEPRINT.md): CRUD master aset, kode manual/otomatis (concurrency-safe), serial unik per
company, tanggal/tahun/nilai perolehan, project & lokasi kerja (master existing), kondisi, status (kategori sistem
stabil), Ubah Status manual, Relokasi manual, detail + histori event dasar, audit log.
TIDAK ada pemegang/penyerahan/pengembalian/pemeriksaan/BAST/impor/export di CP1.

Keamanan:
- Modul `asset` wajib aktif + permission (`require_permission`); tidak ada cek nama role.
- 01I Data Scope di SQL: ALL_TENANT = semua aset company; SELECTED_PROJECTS = `assets.project_id IN allowed`
  (aset tanpa project tidak terlihat); UUID di luar scope -> 404 generik; project tujuan di luar scope -> 403.
- `acquisition_value` hanya dikirim bila `asset_value:view`; mengisi/mengubah butuh `asset_value:edit`.
  Audit log & event tidak pernah menyimpan nilai mentahnya.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from ..core import asset_service as svc
from ..core import data_scope as dscope
from ..core import doc_sequence
from ..core.audit import log_action
from ..core.db import NO_ID, get_db, new_id, now, transaction
from ..core.deps import AuthContext, require_permission

router = APIRouter(prefix="/assets", tags=["Manajemen Aset"])

CREATE_FIELDS = {"asset_code", "name", "category_id", "unit_id", "brand", "model", "serial_number", "acquisition_date",
                 "acquisition_year", "acquisition_value", "project_id", "work_location_id", "condition_id",
                 "status_id", "notes"}
# Project/lokasi -> aksi Relokasi; status -> aksi Ubah Status (blueprint §3 "Aturan edit").
UPDATE_FIELDS = CREATE_FIELDS - {"project_id", "work_location_id", "status_id"}
SORTABLE = {"asset_code": "asset_code_norm", "name": "name", "created_at": "created_at", "updated_at": "updated_at",
            "lifecycle_state": "lifecycle_state"}
EVENT_LIMIT = 100


# ------------------------------------------------------------------ helpers
def _reject_unknown(payload: Dict[str, Any], allowed: set, hint: str = "") -> None:
    unknown = sorted(k for k in payload if k not in allowed)
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Kolom tidak dikenal / tidak dapat diubah di sini: {', '.join(unknown)}.{hint}")


async def _master(company_id: str, coll: str, record_id: Optional[str], label: str, *, require_active: bool = True):
    if not record_id:
        return None
    row = await get_db()[coll].find_one({"company_id": company_id, "id": record_id}, NO_ID)
    if not row or row.get("status") == "deleted" or (require_active and row.get("status") != "active"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{label} tidak ditemukan atau tidak aktif di perusahaan aktif Anda.")
    return row


async def _get_visible_asset(ctx: AuthContext, asset_id: str) -> Dict[str, Any]:
    scope = await dscope.get_scope(ctx)
    flt = dscope.with_project_scope({"company_id": ctx.company_id, "id": asset_id}, scope)
    doc = await get_db().assets.find_one(flt, NO_ID)
    return dscope.assert_project_record_visible(scope, doc)


async def _ensure_code_free(company_id: str, code_norm: str, exclude_id: Optional[str] = None) -> None:
    flt: Dict[str, Any] = {"company_id": company_id, "asset_code_norm": code_norm}
    if exclude_id:
        flt["id"] = {"$ne": exclude_id}
    if await get_db().assets.count_documents(flt):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Kode aset '{code_norm}' sudah digunakan di perusahaan ini.")


async def _ensure_serial_free(company_id: str, serial_norm: Optional[str], exclude_id: Optional[str] = None) -> None:
    if not serial_norm:
        return
    flt: Dict[str, Any] = {"company_id": company_id, "serial_number_norm": serial_norm}
    if exclude_id:
        flt["id"] = {"$ne": exclude_id}
    if await get_db().assets.count_documents(flt):
        raise HTTPException(status.HTTP_409_CONFLICT, "Serial number sudah terdaftar pada aset lain di perusahaan ini.")


def _event(company_id: str, asset_id: str, event_type: str, actor: Optional[str], **kw) -> Dict[str, Any]:
    ts = now()
    return {"id": new_id(), "company_id": company_id, "status": "active", "asset_id": asset_id, "event_type": event_type,
            "event_at": ts, "actor_user_id": actor, "created_at": ts, "updated_at": ts, "created_by": actor,
            "updated_by": actor, **kw}


def _changes(before: Dict[str, Any], after: Dict[str, Any], fields) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for f in fields:
        b, a = before.get(f), after.get(f)
        if f == "acquisition_value":
            if svc.format_value(b) != svc.format_value(a):
                out[f] = {"changed": True}  # nilai sensitif: hanya penanda
            continue
        if b != a:
            out[f] = {"from": b, "to": a}
    return out


async def _present_one(ctx: AuthContext, doc: Dict[str, Any], include_value: bool = True) -> Dict[str, Any]:
    maps = await svc.label_maps(ctx.company_id, [doc])
    return svc.present(doc, maps, can_view_value=ctx.has_permission("asset_value", "view"), include_value=include_value)


# ------------------------------------------------------------------ opsi form
@router.get("/form-options")
async def form_options(ctx: AuthContext = Depends(require_permission("asset", "view"))):
    """Semua pilihan master untuk form/filter Daftar Aset dalam satu panggilan. Project difilter scope 01I."""
    db = get_db()
    cid = ctx.company_id
    scope = await dscope.get_scope(ctx)
    active = {"company_id": cid, "status": "active"}

    async def rows(coll: str, fields: List[str], flt: Optional[Dict[str, Any]] = None):
        data = await db[coll].find(flt or active, NO_ID).to_list(2000)
        data.sort(key=lambda r: (r.get("sort_order") or 0, (r.get("name") or "").lower()))
        return [{k: r.get(k) for k in ["id", "code", "name", *fields]} for r in data]

    projects = await rows("projects", [], dscope.with_project_scope(dict(active), scope, "id"))
    return {
        "categories": await rows("asset_categories", ["code_prefix", "serial_number_required", "default_unit_id"]),
        "units": await rows("asset_units", []),
        "conditions": await rows("asset_conditions", ["is_usable", "severity"]),
        "statuses": [dict(s, manual_selectable=s["system_state"] in svc.MANUAL_STATES)
                     for s in await rows("asset_statuses", ["system_state", "is_default", "color"])],
        "projects": projects,
        "work_locations": await rows("work_locations", []),
        "lifecycle_states": [{"key": k, "label": v, "manual_selectable": k in svc.MANUAL_STATES}
                             for k, v in svc.LIFECYCLE_STATES.items()],
        "scope": {"mode": scope.mode, "all_tenant": scope.is_all},
        "permissions": {
            "create": ctx.has_permission("asset", "create"), "edit": ctx.has_permission("asset", "edit"),
            "delete": ctx.has_permission("asset", "delete"),
            "value_view": ctx.has_permission("asset_value", "view"),
            "value_edit": ctx.has_permission("asset_value", "edit"),
        },
    }


# ------------------------------------------------------------------ list
@router.get("")
async def list_assets(
    q: Optional[str] = None,
    category_id: Optional[str] = None,
    unit_id: Optional[str] = None,
    status_id: Optional[str] = None,
    lifecycle_state: Optional[str] = None,
    condition_id: Optional[str] = None,
    project_id: Optional[str] = Query(None, description="UUID project, atau 'none' untuk aset tanpa project"),
    work_location_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = "created_at",
    sort_dir: str = "desc",
    ctx: AuthContext = Depends(require_permission("asset", "view")),
):
    scope = await dscope.get_scope(ctx)
    flt: Dict[str, Any] = {"company_id": ctx.company_id}
    for field, value in (("category_id", category_id), ("unit_id", unit_id), ("status_id", status_id),
                         ("condition_id", condition_id), ("work_location_id", work_location_id)):
        if value:
            flt[field] = value
    if lifecycle_state:
        if lifecycle_state not in svc.LIFECYCLE_STATES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Kategori status sistem tidak dikenal.")
        flt["lifecycle_state"] = lifecycle_state
    if project_id == "none":
        flt["project_id"] = None  # hanya bermakna untuk ALL_TENANT; restricted tetap 0 lewat scope SQL
    elif project_id:
        flt["project_id"] = project_id
    sql = []
    if q and q.strip():
        term = q.strip()
        like = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        up = "%" + svc.norm_code(term).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        sn = svc.norm_serial(term) or ""
        sn_like = "%" + sn.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        sql.append(lambda t: sa.or_(t.c.asset_code_norm.like(up), t.c.name.like(like), t.c.serial_number_norm.like(sn_like),
                                    t.c.brand.like(like), t.c.model.like(like)))
    if sql:
        flt["$sql"] = sql
    flt = dscope.with_project_scope(flt, scope)  # 01I - di SQL (list + count memakai filter yang sama)
    db = get_db()
    total = await db.assets.count_documents(flt)
    col = SORTABLE.get(sort_by, "created_at")
    rows = await (db.assets.find(flt, NO_ID).sort([(col, 1 if sort_dir == "asc" else -1), ("id", 1)])
                  .skip((page - 1) * limit).limit(limit).to_list(limit))
    maps = await svc.label_maps(ctx.company_id, rows)
    # List TIDAK pernah menampilkan nilai perolehan (blueprint §3); detail menampilkannya bila berizin.
    items = [svc.present(r, maps, can_view_value=False, include_value=False) for r in rows]
    return {"items": items, "total": total, "page": page, "limit": limit,
            "pages": (total + limit - 1) // limit if total else 0}


# ------------------------------------------------------------------ create
@router.post("", status_code=status.HTTP_201_CREATED)
async def create_asset(payload: Dict[str, Any] = Body(...), ctx: AuthContext = Depends(require_permission("asset", "create"))):
    _reject_unknown(payload, CREATE_FIELDS)
    cid = ctx.company_id
    if payload.get("acquisition_value") not in (None, "") and not ctx.has_permission("asset_value", "edit"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Anda tidak memiliki hak akses untuk mengisi nilai perolehan.")
    name = svc.clean_text(payload.get("name"))
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nama aset wajib diisi.")
    category = await _master(cid, "asset_categories", payload.get("category_id"), "Kategori")
    if not category:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Kategori wajib dipilih.")
    unit = await _master(cid, "asset_units", payload.get("unit_id") or category.get("default_unit_id"), "Satuan")
    if not unit:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Satuan wajib dipilih.")
    condition = await _master(cid, "asset_conditions", payload.get("condition_id"), "Kondisi")
    if not condition:
        condition = await get_db().asset_conditions.find_one(
            {"company_id": cid, "code": svc.DEFAULT_CONDITION_CODE, "status": "active"}, NO_ID)
        if not condition:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Kondisi wajib dipilih.")
    st = await _master(cid, "asset_statuses", payload.get("status_id"), "Status")
    if not st:
        st = await svc.default_status_for(cid, svc.READY)
        if not st:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Status wajib dipilih.")
    if st.get("system_state") not in svc.MANUAL_STATES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Status berkategori Dipakai / Menunggu Pemeriksaan hanya dapat terjadi lewat transaksi.")
    project_id = payload.get("project_id") or None
    await _master(cid, "projects", project_id, "Project")
    if project_id or (await dscope.get_scope(ctx)).restricted:
        await dscope.ensure_target_project_allowed(ctx, project_id)  # restricted wajib project dalam scope
    work_location_id = payload.get("work_location_id") or None
    await _master(cid, "work_locations", work_location_id, "Lokasi kerja")
    serial = svc.clean_text(payload.get("serial_number"))
    serial_norm = svc.norm_serial(serial)
    if category.get("serial_number_required") and not serial_norm:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Serial number wajib diisi untuk kategori {category.get('name')}.")
    await _ensure_serial_free(cid, serial_norm)
    acq = svc.parse_acquisition(payload.get("acquisition_date"), payload.get("acquisition_year"))
    value = svc.parse_value(payload.get("acquisition_value"))
    manual_code = svc.clean_text(payload.get("asset_code"), 64)
    code_norm = svc.norm_code(manual_code)
    if code_norm:
        await _ensure_code_free(cid, code_norm)

    doc: Dict[str, Any] = {
        "id": new_id(), "company_id": cid, "status": "active", "name": name,
        "category_id": category["id"], "unit_id": unit["id"], "brand": svc.clean_text(payload.get("brand")),
        "model": svc.clean_text(payload.get("model")), "serial_number": serial, "serial_number_norm": serial_norm,
        **acq, "acquisition_value": value, "project_id": project_id, "work_location_id": work_location_id,
        "condition_id": condition["id"], "status_id": st["id"], "lifecycle_state": st["system_state"],
        "notes": svc.clean_text(payload.get("notes"), 5000), "source": "UI", "row_version": 1,
        "created_at": now(), "updated_at": now(), "created_by": ctx.user_id, "updated_by": ctx.user_id,
    }
    prepared = None if code_norm else await doc_sequence.prepare(cid, svc.ASSET_CODE_SEQ, actor_id=ctx.user_id)
    async with transaction() as tx:  # alokasi kode + insert aset + event CREATED = satu transaksi atomik
        if not code_norm:
            async def _taken(candidate: str) -> bool:
                return bool(await tx.select_one("assets", {"company_id": cid, "asset_code_norm": svc.norm_code(candidate)}))
            code = await doc_sequence.allocate_in_tx(tx, prepared, exists=_taken)
            doc["asset_code"], doc["asset_code_norm"] = code, svc.norm_code(code)
        else:
            doc["asset_code"], doc["asset_code_norm"] = manual_code, code_norm
        await tx.insert("assets", dict(doc))
        await tx.insert("asset_events", _event(cid, doc["id"], "CREATED", ctx.user_id, to_state=doc["lifecycle_state"],
                                               project_id=project_id, work_location_id=work_location_id,
                                               condition_id=doc["condition_id"], status_id=doc["status_id"],
                                               changes={"asset_code_mode": "MANUAL" if code_norm else "AUTO"}))
    await log_action(ctx, "create", "asset", doc["id"], doc["asset_code"], after=svc.audit_view(doc), module="asset")
    saved = await get_db().assets.find_one({"company_id": cid, "id": doc["id"]}, NO_ID)
    return await _present_one(ctx, saved)


# ------------------------------------------------------------------ detail
@router.get("/{asset_id}")
async def get_asset(asset_id: str, ctx: AuthContext = Depends(require_permission("asset", "view"))):
    doc = await _get_visible_asset(ctx, asset_id)
    out = await _present_one(ctx, doc)
    events = await (get_db().asset_events.find({"company_id": ctx.company_id, "asset_id": asset_id}, NO_ID)
                    .sort([("event_at", -1), ("id", 1)]).limit(EVENT_LIMIT).to_list(EVENT_LIMIT))
    actor_ids = sorted({e.get("actor_user_id") for e in events if e.get("actor_user_id")})
    users = {u["id"]: u.get("full_name") for u in await get_db().users.find({"id": {"$in": actor_ids}}, {"id": 1, "full_name": 1}).to_list(len(actor_ids) + 1)} if actor_ids else {}
    out["events"] = [{
        "id": e["id"], "event_type": e.get("event_type"), "event_at": e.get("event_at"),
        "actor_name": users.get(e.get("actor_user_id")), "from_state": e.get("from_state"), "to_state": e.get("to_state"),
        "changes": e.get("changes") or {}, "notes": e.get("notes"),
    } for e in events]
    out["code_editable"] = not any(e.get("event_type") != "CREATED" for e in events)
    return out


# ------------------------------------------------------------------ update (field master)
@router.put("/{asset_id}")
async def update_asset(asset_id: str, payload: Dict[str, Any] = Body(...),
                       ctx: AuthContext = Depends(require_permission("asset", "edit"))):
    _reject_unknown(payload, UPDATE_FIELDS, " Gunakan aksi Relokasi untuk project/lokasi dan Ubah Status untuk status.")
    if not payload:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tidak ada perubahan yang dikirim.")
    cid = ctx.company_id
    before = await _get_visible_asset(ctx, asset_id)
    if "acquisition_value" in payload and not ctx.has_permission("asset_value", "edit"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Anda tidak memiliki hak akses untuk mengubah nilai perolehan.")
    patch: Dict[str, Any] = {}
    if "name" in payload:
        patch["name"] = svc.clean_text(payload.get("name"))
        if not patch["name"]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nama aset wajib diisi.")
    for f in ("brand", "model"):
        if f in payload:
            patch[f] = svc.clean_text(payload.get(f))
    if "notes" in payload:
        patch["notes"] = svc.clean_text(payload.get("notes"), 5000)
    category = None
    if "category_id" in payload and payload["category_id"] != before.get("category_id"):
        category = await _master(cid, "asset_categories", payload.get("category_id"), "Kategori")
        if not category:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Kategori wajib dipilih.")
        patch["category_id"] = category["id"]
    if "unit_id" in payload and payload["unit_id"] != before.get("unit_id"):
        unit = await _master(cid, "asset_units", payload.get("unit_id"), "Satuan")
        if not unit:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Satuan wajib dipilih.")
        patch["unit_id"] = unit["id"]
    if "condition_id" in payload and payload["condition_id"] != before.get("condition_id"):
        if before.get("lifecycle_state") in svc.TRANSACTION_LOCKED:
            raise HTTPException(status.HTTP_409_CONFLICT, "Kondisi aset yang sedang dipakai/menunggu pemeriksaan hanya berubah lewat transaksi.")
        cond = await _master(cid, "asset_conditions", payload.get("condition_id"), "Kondisi")
        if not cond:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Kondisi wajib dipilih.")
        patch["condition_id"] = cond["id"]
    if "serial_number" in payload:
        patch["serial_number"] = svc.clean_text(payload.get("serial_number"))
        patch["serial_number_norm"] = svc.norm_serial(patch["serial_number"])
        if patch["serial_number_norm"] != before.get("serial_number_norm"):
            await _ensure_serial_free(cid, patch["serial_number_norm"], exclude_id=asset_id)
    cat_doc = category or await get_db().asset_categories.find_one({"company_id": cid, "id": before.get("category_id")}, NO_ID)
    final_serial = patch.get("serial_number_norm", before.get("serial_number_norm"))
    if (cat_doc or {}).get("serial_number_required") and not final_serial:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Serial number wajib diisi untuk kategori {(cat_doc or {}).get('name')}.")
    if "acquisition_date" in payload or "acquisition_year" in payload:
        patch.update(svc.parse_acquisition(payload.get("acquisition_date"), payload.get("acquisition_year"), current=before,
                                           date_given="acquisition_date" in payload, year_given="acquisition_year" in payload))
    if "acquisition_value" in payload:
        patch["acquisition_value"] = svc.parse_value(payload.get("acquisition_value"))
    if "asset_code" in payload:
        new_code = svc.clean_text(payload.get("asset_code"), 64)
        new_norm = svc.norm_code(new_code)
        if not new_norm:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Kode aset tidak boleh dikosongkan.")
        if new_norm != before.get("asset_code_norm"):
            other = await get_db().asset_events.count_documents(
                {"company_id": cid, "asset_id": asset_id, "event_type": {"$ne": "CREATED"}})
            if other:
                raise HTTPException(status.HTTP_409_CONFLICT, "Kode aset tidak dapat diubah karena aset sudah memiliki histori selain pembuatan.")
            await _ensure_code_free(cid, new_norm, exclude_id=asset_id)
            patch["asset_code"], patch["asset_code_norm"] = new_code, new_norm
    changes = _changes(before, {**before, **patch}, [k for k in patch if not k.endswith("_norm")])
    if not changes:
        return await _present_one(ctx, before)
    async with transaction() as tx:
        cur = await tx.select_one_for_update("assets", {"company_id": cid, "id": asset_id})
        if not cur:
            raise HTTPException(status.HTTP_404_NOT_FOUND, dscope.NOT_FOUND_MSG)
        await tx.update("assets", {"company_id": cid, "id": asset_id},
                        {**patch, "row_version": int(cur.get("row_version") or 1) + 1, "updated_at": now(), "updated_by": ctx.user_id})
        await tx.insert("asset_events", _event(cid, asset_id, "UPDATED", ctx.user_id, changes=changes,
                                               condition_id=patch.get("condition_id")))
    after = await get_db().assets.find_one({"company_id": cid, "id": asset_id}, NO_ID)
    notes = "Nilai perolehan diubah (nilai tidak dicatat)." if "acquisition_value" in changes else None
    await log_action(ctx, "update", "asset", asset_id, after.get("asset_code"), before=svc.audit_view(before),
                     after=svc.audit_view(after), module="asset", notes=notes)
    return await _present_one(ctx, after)


# ------------------------------------------------------------------ ubah status manual
@router.post("/{asset_id}/status")
async def change_status(asset_id: str, payload: Dict[str, Any] = Body(...),
                        ctx: AuthContext = Depends(require_permission("asset", "edit"))):
    _reject_unknown(payload, {"status_id", "reason"})
    cid = ctx.company_id
    before = await _get_visible_asset(ctx, asset_id)
    reason = svc.clean_text(payload.get("reason"), 1000)
    if not reason:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Alasan perubahan status wajib diisi.")
    target = await _master(cid, "asset_statuses", payload.get("status_id"), "Status")
    if not target:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Status tujuan wajib dipilih.")
    from_state, to_state = before.get("lifecycle_state"), target.get("system_state")
    revert_target = None
    if from_state == svc.DISPOSED and to_state != svc.DISPOSED:
        last = await (get_db().asset_events.find({"company_id": cid, "asset_id": asset_id, "to_state": svc.DISPOSED,
                                                  "event_type": {"$in": ["STATUS_CHANGE", "CREATED"]}}, NO_ID)
                      .sort([("event_at", -1)]).limit(1).to_list(1))
        revert_target = (last[0].get("from_state") if last else None) or svc.READY
    svc.check_transition(from_state, to_state, can_revert_disposal=ctx.has_permission("asset", "delete"),
                         revert_target=revert_target)
    if target["id"] == before.get("status_id"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Status tujuan sama dengan status saat ini.")
    async with transaction() as tx:
        cur = await tx.select_one_for_update("assets", {"company_id": cid, "id": asset_id})
        if not cur or cur.get("lifecycle_state") != from_state:
            raise HTTPException(status.HTTP_409_CONFLICT, "Status aset berubah bersamaan. Muat ulang lalu coba lagi.")
        await tx.update("assets", {"company_id": cid, "id": asset_id},
                        {"status_id": target["id"], "lifecycle_state": to_state,
                         "row_version": int(cur.get("row_version") or 1) + 1, "updated_at": now(), "updated_by": ctx.user_id})
        await tx.insert("asset_events", _event(cid, asset_id, "STATUS_CHANGE", ctx.user_id, from_state=from_state,
                                               to_state=to_state, status_id=target["id"], notes=reason,
                                               changes={"status_id": {"from": before.get("status_id"), "to": target["id"]}}))
    after = await get_db().assets.find_one({"company_id": cid, "id": asset_id}, NO_ID)
    await log_action(ctx, "status_change", "asset", asset_id, after.get("asset_code"), before=svc.audit_view(before),
                     after=svc.audit_view(after), module="asset", notes=reason)
    return await _present_one(ctx, after)


# ------------------------------------------------------------------ relokasi manual (READY saja)
@router.post("/{asset_id}/relocate")
async def relocate(asset_id: str, payload: Dict[str, Any] = Body(...),
                   ctx: AuthContext = Depends(require_permission("asset", "edit"))):
    _reject_unknown(payload, {"project_id", "work_location_id", "notes"})
    cid = ctx.company_id
    before = await _get_visible_asset(ctx, asset_id)
    if before.get("lifecycle_state") != svc.READY:
        raise HTTPException(status.HTTP_409_CONFLICT, "Relokasi hanya dapat dilakukan untuk aset berstatus Siap Pakai.")
    project_id = payload.get("project_id", before.get("project_id")) or None
    work_location_id = payload.get("work_location_id", before.get("work_location_id")) or None
    if project_id == before.get("project_id") and work_location_id == before.get("work_location_id"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Project/lokasi tujuan sama dengan saat ini.")
    if project_id != before.get("project_id"):
        await _master(cid, "projects", project_id, "Project")
    if project_id or (await dscope.get_scope(ctx)).restricted:
        await dscope.ensure_target_project_allowed(ctx, project_id)  # restricted wajib project dalam scope
    if work_location_id != before.get("work_location_id"):
        await _master(cid, "work_locations", work_location_id, "Lokasi kerja")
    notes = svc.clean_text(payload.get("notes"), 1000)
    changes = _changes(before, {**before, "project_id": project_id, "work_location_id": work_location_id},
                       ["project_id", "work_location_id"])
    async with transaction() as tx:
        cur = await tx.select_one_for_update("assets", {"company_id": cid, "id": asset_id})
        if not cur or cur.get("lifecycle_state") != svc.READY:
            raise HTTPException(status.HTTP_409_CONFLICT, "Status aset berubah bersamaan. Muat ulang lalu coba lagi.")
        await tx.update("assets", {"company_id": cid, "id": asset_id},
                        {"project_id": project_id, "work_location_id": work_location_id,
                         "row_version": int(cur.get("row_version") or 1) + 1, "updated_at": now(), "updated_by": ctx.user_id})
        await tx.insert("asset_events", _event(cid, asset_id, "RELOCATION", ctx.user_id, from_state=svc.READY,
                                               to_state=svc.READY, project_id=project_id,
                                               work_location_id=work_location_id, changes=changes, notes=notes))
    after = await get_db().assets.find_one({"company_id": cid, "id": asset_id}, NO_ID)
    await log_action(ctx, "relocate", "asset", asset_id, after.get("asset_code"), before=svc.audit_view(before),
                     after=svc.audit_view(after), module="asset", notes=notes)
    return await _present_one(ctx, after)


# ------------------------------------------------------------------ hapus
@router.delete("/{asset_id}")
async def delete_asset(asset_id: str, ctx: AuthContext = Depends(require_permission("asset", "delete"))):
    """Hapus hanya bila aset belum pernah bertransaksi (CP1 belum punya transaksi; aset IN_USE/PENDING ditolak).
    Aset yang sudah tidak dipakai sebaiknya diubah ke status berkategori Dihapuskan (DISPOSED).
    Histori event tetap tersimpan (append-only); audit log mencatat penghapusan tanpa nilai perolehan."""
    cid = ctx.company_id
    before = await _get_visible_asset(ctx, asset_id)
    if before.get("lifecycle_state") in svc.TRANSACTION_LOCKED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Aset yang sedang dipakai/menunggu pemeriksaan tidak dapat dihapus.")
    if await get_db().asset_holdings.count_documents({"company_id": ctx.company_id, "asset_id": asset_id}):
        # CP2: aset yang pernah bertransaksi (punya histori pemegang/BAST) tidak dapat dihapus.
        raise HTTPException(status.HTTP_409_CONFLICT, "Aset yang sudah memiliki histori penyerahan tidak dapat dihapus.")
    async with transaction() as tx:
        await tx.delete("assets", {"company_id": cid, "id": asset_id})
    await log_action(ctx, "delete", "asset", asset_id, before.get("asset_code"), before=svc.audit_view(before), module="asset")
    return {"message": f"Aset {before.get('asset_code')} berhasil dihapus."}
