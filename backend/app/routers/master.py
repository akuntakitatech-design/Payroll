"""Generic master-data CRUD driven by the MASTERS registry in app/masters.py."""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status

from ..core.audit import log_action
from ..core.db import NO_ID
from ..core.deps import AuthContext, get_auth
from ..core.repo import TenantRepository, reference_count
from ..core.tenancy import get_tenant_db
from ..masters import BOOLEAN_FIELDS, MASTERS, NUMERIC_FIELDS

router = APIRouter(prefix="/master", tags=["Master Data"])


def _cfg(resource_path: str) -> Dict[str, Any]:
    cfg = MASTERS.get(resource_path)
    if not cfg:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Jenis master data tidak dikenal.")
    return cfg


def _coerce(cfg: Dict[str, Any], payload: Dict[str, Any], partial: bool) -> Dict[str, Any]:
    allowed = set(cfg["fields"]) | {"status"}
    unknown = [k for k in payload if k not in allowed]
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Kolom berikut tidak dikenal untuk {cfg['label']}: {', '.join(unknown)}.",
        )
    data: Dict[str, Any] = {}
    for key, value in payload.items():
        if key in NUMERIC_FIELDS and value not in (None, ""):
            try:
                data[key] = float(value) if "." in str(value) else int(value)
            except (TypeError, ValueError):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    f"Kolom '{key}' harus berupa angka.",
                )
        elif key in BOOLEAN_FIELDS:
            data[key] = bool(value) if value not in (None, "") else False
        elif isinstance(value, str):
            data[key] = value.strip() or None
        else:
            data[key] = value
    if not partial:
        for req in cfg["required"]:
            if not data.get(req):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    f"Kolom '{req}' wajib diisi untuk {cfg['label']}.",
                )
    for req in cfg["required"]:
        if req in data and not data[req]:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Kolom '{req}' wajib diisi untuk {cfg['label']}.",
            )
    if "code" in data and data["code"]:
        data["code"] = str(data["code"]).upper()
    return data


async def _validate_relations(cfg: Dict[str, Any], company_id: str, data: Dict[str, Any], record_id: Optional[str] = None) -> None:
    relations = cfg.get("relations", {})
    db = get_tenant_db(company_id)  # tenant-scoped
    for field, target in relations.items():
        value = data.get(field)
        if not value:
            continue
        if record_id and value == record_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Data tidak boleh mereferensikan dirinya sendiri.",
            )
        exists = await db[target].count_documents(
            {"company_id": company_id, "id": value, "status": {"$ne": "deleted"}}
        )
        if not exists:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Referensi pada kolom '{field}' tidak ditemukan di perusahaan aktif Anda.",
            )


async def _enrich(cfg: Dict[str, Any], company_id: str, items):
    """Attach human readable labels for foreign keys (INPUT ONCE, USE EVERYWHERE)."""
    relations = cfg.get("relations", {})
    if not relations or not items:
        return items
    db = get_tenant_db(company_id)  # tenant-scoped
    caches: Dict[str, Dict[str, str]] = {}
    for field, target in relations.items():
        ids = {i.get(field) for i in items if i.get(field)}
        if not ids:
            continue
        if target not in caches:
            rows = await db[target].find({"company_id": company_id, "id": {"$in": list(ids)}}, NO_ID).to_list(500)
            caches[target] = {r["id"]: r.get("name") for r in rows}
        cache = caches[target]
        for item in items:
            if item.get(field):
                item[f"{field}_name"] = cache.get(item[field])
    return items


@router.get("/registry")
async def registry(ctx: AuthContext = Depends(get_auth)):
    return {
        "items": [
            {
                "path": path,
                "resource": cfg["resource"],
                "label": cfg["label"],
                "fields": cfg["fields"],
                "required": cfg["required"],
                "relations": cfg.get("relations", {}),
            }
            for path, cfg in MASTERS.items()
        ]
    }


@router.get("/{resource_path}")
async def list_master(
    resource_path: str,
    request: Request,
    q: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = 1,
    limit: int = 20,
    sort_by: str = "created_at",
    sort_dir: str = "desc",
    ctx: AuthContext = Depends(get_auth),
):
    cfg = _cfg(resource_path)
    if not ctx.has_permission(cfg["resource"], "view"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Anda tidak memiliki hak akses untuk melihat {cfg['label']}.")
    filters: Dict[str, Any] = {}
    if status_filter:
        filters["status"] = status_filter
    for field in cfg.get("relations", {}):
        value = request.query_params.get(field)
        if value:
            filters[field] = value
    repo = TenantRepository(cfg["collection"], ctx.company_id)
    result = await repo.list(
        q=q, search_fields=cfg["search"], filters=filters, page=page, limit=limit,
        sort_by=sort_by, sort_dir=sort_dir,
    )
    result["items"] = await _enrich(cfg, ctx.company_id, result["items"])
    result["label"] = cfg["label"]
    return result


@router.get("/{resource_path}/options")
async def options_master(resource_path: str, ctx: AuthContext = Depends(get_auth)):
    """Lightweight list for dropdowns - avoids repeated data entry."""
    cfg = _cfg(resource_path)
    repo = TenantRepository(cfg["collection"], ctx.company_id)
    rows = await repo.all(filters={"status": "active"})
    return {
        "items": [
            {"id": r["id"], "code": r.get("code"), "name": r.get("name")} for r in rows
        ]
    }


@router.post("/{resource_path}", status_code=status.HTTP_201_CREATED)
async def create_master(
    resource_path: str, payload: Dict[str, Any] = Body(...), ctx: AuthContext = Depends(get_auth)
):
    cfg = _cfg(resource_path)
    if not ctx.has_permission(cfg["resource"], "create"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Anda tidak memiliki hak akses untuk menambah {cfg['label']}.")
    data = _coerce(cfg, payload, partial=False)
    repo = TenantRepository(cfg["collection"], ctx.company_id)
    for field in cfg.get("unique", []):
        await repo.ensure_unique(field, data.get(field), label=field.upper())
    await _validate_relations(cfg, ctx.company_id, data)
    created = await repo.create(data, ctx.user_id)
    await log_action(ctx, "create", cfg["resource"], created["id"], created.get("name"), after=created)
    return created


@router.get("/{resource_path}/{record_id}")
async def get_master(resource_path: str, record_id: str, ctx: AuthContext = Depends(get_auth)):
    cfg = _cfg(resource_path)
    if not ctx.has_permission(cfg["resource"], "view"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Anda tidak memiliki hak akses untuk data ini.")
    repo = TenantRepository(cfg["collection"], ctx.company_id)
    doc = await repo.get(record_id)
    (await _enrich(cfg, ctx.company_id, [doc]))
    return doc


@router.put("/{resource_path}/{record_id}")
async def update_master(
    resource_path: str,
    record_id: str,
    payload: Dict[str, Any] = Body(...),
    ctx: AuthContext = Depends(get_auth),
):
    cfg = _cfg(resource_path)
    if not ctx.has_permission(cfg["resource"], "edit"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Anda tidak memiliki hak akses untuk mengubah {cfg['label']}.")
    data = _coerce(cfg, payload, partial=True)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tidak ada perubahan yang dikirim.")
    repo = TenantRepository(cfg["collection"], ctx.company_id)
    await repo.get(record_id)
    for field in cfg.get("unique", []):
        if field in data:
            await repo.ensure_unique(field, data[field], exclude_id=record_id, label=field.upper())
    await _validate_relations(cfg, ctx.company_id, data, record_id=record_id)
    before, after = await repo.update(record_id, data, ctx.user_id)
    await log_action(ctx, "update", cfg["resource"], record_id, after.get("name"), before=before, after=after)
    return after


@router.patch("/{resource_path}/{record_id}/status")
async def set_master_status(
    resource_path: str,
    record_id: str,
    payload: Dict[str, Any] = Body(...),
    ctx: AuthContext = Depends(get_auth),
):
    cfg = _cfg(resource_path)
    if not ctx.has_permission(cfg["resource"], "edit"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Anda tidak memiliki hak akses untuk mengubah status data ini.")
    new_status = payload.get("status")
    if new_status not in ("active", "inactive", "archived"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Status harus salah satu dari: active, inactive, archived.",
        )
    repo = TenantRepository(cfg["collection"], ctx.company_id)
    before, after = await repo.set_status(record_id, new_status, ctx.user_id)
    label = {"active": "diaktifkan", "inactive": "dinonaktifkan", "archived": "diarsipkan"}[new_status]
    await log_action(
        ctx, f"status_{new_status}", cfg["resource"], record_id, after.get("name"), before=before, after=after
    )
    return {"message": f"{cfg['label']} '{after.get('name')}' berhasil {label}.", "item": after}


@router.delete("/{resource_path}/{record_id}")
async def delete_master(resource_path: str, record_id: str, ctx: AuthContext = Depends(get_auth)):
    """Hard delete is only allowed when the record is not referenced anywhere."""
    cfg = _cfg(resource_path)
    if not ctx.has_permission(cfg["resource"], "delete"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Anda tidak memiliki hak akses untuk menghapus {cfg['label']}.")
    repo = TenantRepository(cfg["collection"], ctx.company_id)
    doc = await repo.get(record_id)
    for collection, field, label in cfg.get("refs", []):
        used = await reference_count(ctx.company_id, collection, field, record_id)
        if used:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{cfg['label']} '{doc.get('name')}' masih dipakai oleh {used} data {label}. "
                f"Nonaktifkan data ini agar riwayat tetap aman, atau pindahkan {label} tersebut terlebih dahulu.",
            )
    before = await repo.hard_delete(record_id)
    await log_action(ctx, "delete", cfg["resource"], record_id, doc.get("name"), before=before)
    return {"message": f"{cfg['label']} '{doc.get('name')}' berhasil dihapus."}
