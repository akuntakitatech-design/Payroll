"""Kontrak kerja karyawan (bagian modul employee_core)."""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..core.audit import log_action
from ..core.db import NO_ID, get_db, now, serialize, serialize_list
from ..core.deps import AuthContext, require_permission
from ..core.expiry import expiry_state, parse_date
from ..core.policy import resolve_config
from ..core.repo import TenantRepository
from ..schemas import (
    ContractCreate,
    ContractRenewRequest,
    ContractUpdate,
    StatusChange,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/contracts", tags=["Kontrak Kerja"])


async def _employee(company_id: str, employee_id: str) -> Dict[str, Any]:
    db = get_db()
    emp = await db.employees.find_one(
        {"company_id": company_id, "id": employee_id, "status": {"$ne": "deleted"}}, NO_ID
    )
    if not emp:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Karyawan tidak ditemukan pada perusahaan aktif Anda.",
        )
    return emp


async def _validate(company_id: str, data: Dict[str, Any]) -> None:
    db = get_db()
    if data.get("contract_type_id"):
        exists = await db.contract_types.count_documents(
            {"company_id": company_id, "id": data["contract_type_id"], "status": {"$ne": "deleted"}}
        )
        if not exists:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Tipe kontrak tidak ditemukan. Buat dulu di menu Setup -> Tipe Kontrak.",
            )
    start = parse_date(data.get("start_date"))
    end = parse_date(data.get("end_date"))
    if start and end and end < start:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Tanggal berakhir kontrak tidak boleh lebih awal dari tanggal mulai.",
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
        for t in await db.contract_types.find({"company_id": company_id}, NO_ID).to_list(500)
    }
    for item in items:
        emp = employees.get(item.get("employee_id")) or {}
        item["employee_name"] = emp.get("full_name")
        item["employee_number"] = emp.get("employee_number")
        item["contract_type_name"] = types.get(item.get("contract_type_id"))
        item.update(expiry_state(item.get("end_date"), horizon_days))
    return items


@router.get("")
async def list_contracts(
    q: Optional[str] = None,
    employee_id: Optional[str] = None,
    contract_type_id: Optional[str] = None,
    expiry: Optional[str] = Query(None, description="expired | due_soon | ok"),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = 1,
    limit: int = 20,
    ctx: AuthContext = Depends(require_permission("contract", "view")),
):
    filters: Dict[str, Any] = {}
    for key, value in (
        ("employee_id", employee_id),
        ("contract_type_id", contract_type_id),
        ("status", status_filter),
    ):
        if value:
            filters[key] = value
    repo = TenantRepository("employee_contracts", ctx.company_id)
    result = await repo.list(
        q=q,
        search_fields=["contract_number", "notes"],
        filters=filters,
        page=page,
        limit=limit,
        sort_by="start_date",
        sort_dir="desc",
    )
    reminder = await resolve_config(ctx.company_id, "contract.expiry_reminder_days")
    horizon = int(reminder.get("value") or 30)
    result["items"] = await _enrich(ctx.company_id, result["items"], horizon)
    if expiry:
        result["items"] = [i for i in result["items"] if i.get("state") == expiry]
    return result


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_contract(
    payload: ContractCreate,
    ctx: AuthContext = Depends(require_permission("contract", "create")),
):
    data = payload.model_dump(exclude_none=True)
    employee = await _employee(ctx.company_id, data["employee_id"])
    await _validate(ctx.company_id, data)
    repo = TenantRepository("employee_contracts", ctx.company_id)
    if data.get("contract_number"):
        await repo.ensure_unique("contract_number", data["contract_number"], label="Nomor kontrak")
    data.setdefault("approval_state", "draft")
    created = await repo.create(data, ctx.user_id)
    created["employee_name"] = employee.get("full_name")
    await log_action(
        ctx,
        "create",
        "contract",
        created["id"],
        f"{created.get('contract_number') or 'Kontrak'} - {employee.get('full_name')}",
        after=created,
    )
    return created


@router.get("/{contract_id}")
async def get_contract(
    contract_id: str, ctx: AuthContext = Depends(require_permission("contract", "view"))
):
    repo = TenantRepository("employee_contracts", ctx.company_id)
    item = await repo.get(contract_id)
    reminder = await resolve_config(ctx.company_id, "contract.expiry_reminder_days")
    horizon = int(reminder.get("value") or 30)
    return (await _enrich(ctx.company_id, [item], horizon))[0]


@router.put("/{contract_id}")
async def update_contract(
    contract_id: str,
    payload: ContractUpdate,
    ctx: AuthContext = Depends(require_permission("contract", "edit")),
):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tidak ada perubahan yang dikirim.")
    repo = TenantRepository("employee_contracts", ctx.company_id)
    existing = await repo.get(contract_id)
    merged = {**existing, **data}
    await _validate(ctx.company_id, merged)
    if data.get("contract_number"):
        await repo.ensure_unique(
            "contract_number", data["contract_number"], exclude_id=contract_id, label="Nomor kontrak"
        )
    before, after = await repo.update(contract_id, data, ctx.user_id)
    await log_action(
        ctx, "update", "contract", contract_id, after.get("contract_number"), before=before, after=after
    )
    return after


@router.post("/{contract_id}/approve")
async def approve_contract(
    contract_id: str, ctx: AuthContext = Depends(require_permission("contract", "approve"))
):
    repo = TenantRepository("employee_contracts", ctx.company_id)
    contract = await repo.get(contract_id)
    if contract.get("approval_state") == "approved":
        raise HTTPException(status.HTTP_409_CONFLICT, "Kontrak ini sudah disetujui sebelumnya.")
    before, after = await repo.update(
        contract_id,
        {
            "approval_state": "approved",
            "approved_by": ctx.user_id,
            "approved_by_name": ctx.user.get("full_name"),
            "approved_at": now(),
        },
        ctx.user_id,
    )
    await log_action(
        ctx, "approve", "contract", contract_id, contract.get("contract_number"), before=before, after=after
    )
    return after


@router.patch("/{contract_id}/status")
async def change_status(
    contract_id: str,
    payload: StatusChange,
    ctx: AuthContext = Depends(require_permission("contract", "edit")),
):
    if payload.status not in ("active", "inactive", "archived"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Status kontrak hanya boleh: active, inactive, atau archived.",
        )
    repo = TenantRepository("employee_contracts", ctx.company_id)
    contract = await repo.get(contract_id)
    before, after = await repo.set_status(contract_id, payload.status, ctx.user_id)
    await log_action(
        ctx,
        "activate" if payload.status == "active" else "deactivate",
        "contract",
        contract_id,
        contract.get("contract_number"),
        before=before,
        after=after,
    )
    return after


@router.delete("/{contract_id}")
async def delete_contract(
    contract_id: str, ctx: AuthContext = Depends(require_permission("contract", "delete"))
):
    repo = TenantRepository("employee_contracts", ctx.company_id)
    contract = await repo.get(contract_id)
    before, after = await repo.update(contract_id, {"status": "deleted"}, ctx.user_id)
    await log_action(
        ctx, "delete", "contract", contract_id, contract.get("contract_number"), before=before, after=after
    )
    return {"message": "Kontrak kerja berhasil dihapus dari daftar aktif."}


# ==========================================================================
# Perpanjangan kontrak 1 klik
# ==========================================================================
def _add_months(iso_date: str, months: int) -> Optional[str]:
    base = parse_date(iso_date)
    if not base:
        return None
    year = base.year + (base.month - 1 + months) // 12
    month = (base.month - 1 + months) % 12 + 1
    day = base.day
    while day > 28:
        try:
            return base.replace(year=year, month=month, day=day).date().isoformat()
        except ValueError:
            day -= 1
    return base.replace(year=year, month=month, day=day).date().isoformat()


def _duration_months(contract_type: Dict[str, Any], contract: Dict[str, Any]) -> int:
    """Durasi perpanjangan: dari tipe kontrak, atau dari panjang kontrak sebelumnya."""
    for key in ("duration_months", "default_duration_months", "months"):
        value = (contract_type or {}).get(key)
        if value:
            try:
                return max(1, int(value))
            except (TypeError, ValueError):
                pass
    start = parse_date(contract.get("start_date"))
    end = parse_date(contract.get("end_date"))
    if start and end:
        months = (end.year - start.year) * 12 + (end.month - start.month)
        if months >= 1:
            return months
    return 12


@router.get("/{contract_id}/renew-preview")
async def renew_preview(
    contract_id: str,
    ctx: AuthContext = Depends(require_permission("contract", "create")),
):
    """Nilai awal formulir perpanjangan, sudah terisi dari kontrak berjalan."""
    db = get_db()
    cid = ctx.company_id
    repo = TenantRepository("employee_contracts", cid)
    contract = await repo.get(contract_id)
    employee = await _employee(cid, contract["employee_id"])

    ctype = await db.contract_types.find_one(
        {"company_id": cid, "id": contract.get("contract_type_id")}, NO_ID
    ) or {}
    months = _duration_months(ctype, contract)

    end = parse_date(contract.get("end_date"))
    if end:
        new_start = (end.date().toordinal() + 1)
        from datetime import date as _date

        new_start_iso = _date.fromordinal(new_start).isoformat()
    else:
        new_start_iso = datetime.now(timezone.utc).date().isoformat()

    existing_renewal = await db.employee_contracts.find_one(
        {"company_id": cid, "previous_contract_id": contract_id, "status": {"$ne": "deleted"}},
        NO_ID,
    )

    types = await db.contract_types.find(
        {"company_id": cid, "status": {"$ne": "deleted"}}, NO_ID
    ).sort("name", 1).to_list(200)

    sequence = await db.employee_contracts.count_documents(
        {"company_id": cid, "employee_id": contract["employee_id"], "status": {"$ne": "deleted"}}
    )
    year = datetime.now(timezone.utc).year
    prefix = (ctype.get("code") or "PKWT").upper()
    company = await db.companies.find_one({"id": cid}, NO_ID) or {}

    return {
        "previous_contract": serialize(contract),
        "employee": {
            "id": employee["id"],
            "full_name": employee.get("full_name"),
            "employee_number": employee.get("employee_number"),
            "job_title": employee.get("job_title"),
        },
        "contract_types": serialize_list(types),
        "already_renewed": serialize(existing_renewal),
        "defaults": {
            "contract_type_id": contract.get("contract_type_id"),
            "start_date": new_start_iso,
            "end_date": _add_months(new_start_iso, months),
            "duration_months": months,
            "position_id": contract.get("position_id"),
            "basic_salary": contract.get("basic_salary"),
            "allowance": contract.get("allowance"),
            "contract_number": f"{prefix}/{company.get('code') or 'CO'}/{year}/"
                               f"{sequence + 1:04d}",
            "notes": f"Perpanjangan dari kontrak {contract.get('contract_number') or '-'}",
        },
    }


@router.post("/{contract_id}/renew", status_code=status.HTTP_201_CREATED)
async def renew_contract(
    contract_id: str,
    payload: ContractRenewRequest,
    ctx: AuthContext = Depends(require_permission("contract", "create")),
):
    """Buat kontrak penerus dalam satu langkah dan tandai kontrak lama sebagai diperpanjang."""
    db = get_db()
    cid = ctx.company_id
    repo = TenantRepository("employee_contracts", cid)
    previous = await repo.get(contract_id)
    employee = await _employee(cid, previous["employee_id"])

    existing_renewal = await db.employee_contracts.find_one(
        {"company_id": cid, "previous_contract_id": contract_id, "status": {"$ne": "deleted"}},
        NO_ID,
    )
    if existing_renewal:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Kontrak ini sudah pernah diperpanjang dengan nomor "
            f"'{existing_renewal.get('contract_number') or '-'}'. "
            "Perpanjang kontrak terbaru bila ingin memperpanjang lagi.",
        )

    data = payload.model_dump(exclude_unset=True)
    archive_previous = data.pop("archive_previous", True)
    data["employee_id"] = previous["employee_id"]
    data.setdefault("contract_type_id", previous.get("contract_type_id"))
    data.setdefault("position_id", previous.get("position_id"))
    data.setdefault("basic_salary", previous.get("basic_salary"))
    data.setdefault("allowance", previous.get("allowance"))
    if not data.get("contract_type_id"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Tipe kontrak wajib dipilih untuk perpanjangan.")

    await _validate(cid, data)

    prev_end = parse_date(previous.get("end_date"))
    new_start = parse_date(data.get("start_date"))
    if prev_end and new_start and new_start.date() <= prev_end.date():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Tanggal mulai perpanjangan harus setelah tanggal berakhir kontrak sebelumnya "
            f"({prev_end.date().isoformat()}).",
        )

    if data.get("contract_number"):
        await repo.ensure_unique("contract_number", data["contract_number"],
                                 label="Nomor kontrak")

    data["previous_contract_id"] = contract_id
    data["is_renewal"] = True
    data["approval_state"] = "draft"
    created = await repo.create(data, ctx.user_id)

    prev_patch: Dict[str, Any] = {
        "renewed_by_contract_id": created["id"],
        "renewed_at": now(),
        "renewal_state": "renewed",
    }
    if archive_previous:
        prev_patch["status"] = "archived"
    before, after = await repo.update(contract_id, prev_patch, ctx.user_id)

    await log_action(
        ctx, "create", "contract", created["id"],
        f"Perpanjangan kontrak {employee.get('full_name')}",
        after=created,
        notes=f"Perpanjangan dari kontrak {previous.get('contract_number') or contract_id}",
    )
    await log_action(ctx, "update", "contract", contract_id,
                     f"Kontrak {previous.get('contract_number') or '-'} diperpanjang",
                     before=before, after=after)

    return {
        "contract": created,
        "previous_contract": after,
        "employee": {
            "id": employee["id"],
            "full_name": employee.get("full_name"),
            "employee_number": employee.get("employee_number"),
        },
        "message": f"Kontrak {employee.get('full_name')} berhasil diperpanjang "
                   f"sampai {created.get('end_date') or 'tanpa batas waktu'}.",
    }
