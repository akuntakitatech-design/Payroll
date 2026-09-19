"""Sertifikasi karyawan (bagian modul employee_core)."""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..core.audit import log_action
from ..core.db import NO_ID, get_db
from ..core.deps import AuthContext, require_permission
from ..core.expiry import expiry_state, parse_date
from ..core.policy import resolve_config
from ..core.repo import TenantRepository
from ..schemas import CertificationCreate, CertificationUpdate, StatusChange

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/certifications", tags=["Sertifikasi Karyawan"])


async def _validate(company_id: str, data: Dict[str, Any], require_employee: bool = False) -> None:
    db = get_db()
    if require_employee or data.get("employee_id"):
        emp = await db.employees.count_documents(
            {"company_id": company_id, "id": data.get("employee_id"), "status": {"$ne": "deleted"}}
        )
        if not emp:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Karyawan tidak ditemukan pada perusahaan aktif Anda.",
            )
    if data.get("certification_type_id"):
        exists = await db.certification_types.count_documents(
            {
                "company_id": company_id,
                "id": data["certification_type_id"],
                "status": {"$ne": "deleted"},
            }
        )
        if not exists:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Tipe sertifikasi tidak ditemukan. Buat dulu di menu Setup -> Tipe Sertifikasi.",
            )
    issued = parse_date(data.get("issued_date"))
    expiry = parse_date(data.get("expiry_date"))
    if issued and expiry and expiry < issued:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Tanggal berakhir sertifikat tidak boleh lebih awal dari tanggal terbit.",
        )


async def _enrich(company_id: str, items, horizon_days: int):
    db = get_db()
    emp_ids = {i.get("employee_id") for i in items if i.get("employee_id")}
    employees = {
        e["id"]: e
        for e in await db.employees.find(
            {"company_id": company_id, "id": {"$in": list(emp_ids)}}, NO_ID
        ).to_list(2000)
    }
    types = {
        t["id"]: t.get("name")
        for t in await db.certification_types.find({"company_id": company_id}, NO_ID).to_list(500)
    }
    for item in items:
        emp = employees.get(item.get("employee_id")) or {}
        item["employee_name"] = emp.get("full_name")
        item["employee_number"] = emp.get("employee_number")
        item["certification_type_name"] = types.get(item.get("certification_type_id"))
        item.update(expiry_state(item.get("expiry_date"), horizon_days))
    return items


@router.get("")
async def list_certifications(
    q: Optional[str] = None,
    employee_id: Optional[str] = None,
    certification_type_id: Optional[str] = None,
    expiry: Optional[str] = Query(None, description="expired | due_soon | ok"),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = 1,
    limit: int = 20,
    ctx: AuthContext = Depends(require_permission("certification", "view")),
):
    filters: Dict[str, Any] = {}
    for key, value in (
        ("employee_id", employee_id),
        ("certification_type_id", certification_type_id),
        ("status", status_filter),
    ):
        if value:
            filters[key] = value
    repo = TenantRepository("employee_certifications", ctx.company_id)
    result = await repo.list(
        q=q,
        search_fields=["name", "certificate_number", "issuer"],
        filters=filters,
        page=page,
        limit=limit,
        sort_by="expiry_date",
        sort_dir="asc",
    )
    reminder = await resolve_config(ctx.company_id, "contract.expiry_reminder_days")
    horizon = int(reminder.get("value") or 30)
    result["items"] = await _enrich(ctx.company_id, result["items"], horizon)
    if expiry:
        result["items"] = [i for i in result["items"] if i.get("state") == expiry]
    return result


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_certification(
    payload: CertificationCreate,
    ctx: AuthContext = Depends(require_permission("certification", "create")),
):
    data = payload.model_dump(exclude_none=True)
    await _validate(ctx.company_id, data, require_employee=True)
    repo = TenantRepository("employee_certifications", ctx.company_id)
    created = await repo.create(data, ctx.user_id)
    await log_action(ctx, "create", "certification", created["id"], created.get("name"), after=created)
    return created


@router.get("/{certification_id}")
async def get_certification(
    certification_id: str,
    ctx: AuthContext = Depends(require_permission("certification", "view")),
):
    repo = TenantRepository("employee_certifications", ctx.company_id)
    item = await repo.get(certification_id)
    reminder = await resolve_config(ctx.company_id, "contract.expiry_reminder_days")
    horizon = int(reminder.get("value") or 30)
    return (await _enrich(ctx.company_id, [item], horizon))[0]


@router.put("/{certification_id}")
async def update_certification(
    certification_id: str,
    payload: CertificationUpdate,
    ctx: AuthContext = Depends(require_permission("certification", "edit")),
):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tidak ada perubahan yang dikirim.")
    repo = TenantRepository("employee_certifications", ctx.company_id)
    existing = await repo.get(certification_id)
    await _validate(ctx.company_id, {**existing, **data})
    before, after = await repo.update(certification_id, data, ctx.user_id)
    await log_action(
        ctx,
        "update",
        "certification",
        certification_id,
        after.get("name"),
        before=before,
        after=after,
    )
    return after


@router.patch("/{certification_id}/status")
async def change_status(
    certification_id: str,
    payload: StatusChange,
    ctx: AuthContext = Depends(require_permission("certification", "edit")),
):
    if payload.status not in ("active", "inactive", "archived"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Status sertifikasi hanya boleh: active, inactive, atau archived.",
        )
    repo = TenantRepository("employee_certifications", ctx.company_id)
    item = await repo.get(certification_id)
    before, after = await repo.set_status(certification_id, payload.status, ctx.user_id)
    await log_action(
        ctx,
        "activate" if payload.status == "active" else "deactivate",
        "certification",
        certification_id,
        item.get("name"),
        before=before,
        after=after,
    )
    return after


@router.delete("/{certification_id}")
async def delete_certification(
    certification_id: str,
    ctx: AuthContext = Depends(require_permission("certification", "delete")),
):
    repo = TenantRepository("employee_certifications", ctx.company_id)
    item = await repo.get(certification_id)
    before, after = await repo.update(certification_id, {"status": "deleted"}, ctx.user_id)
    await log_action(
        ctx, "delete", "certification", certification_id, item.get("name"), before=before, after=after
    )
    return {"message": f"Sertifikasi '{item.get('name')}' berhasil dihapus."}
