from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from ..core.audit import log_action
from ..core.db import NO_ID, audit_fields, get_db, new_id, serialize, serialize_list
from ..core.deps import AuthContext, get_auth, require_permission
from ..core.repo import TenantRepository
from ..schemas import ApprovalWorkflowInput

router = APIRouter(prefix="/approval-workflows", tags=["Alur Persetujuan"])

DOCUMENT_KINDS = [
    {"key": "recruitment", "label": "Rekrutmen", "module": "recruitment"},
    {"key": "contract", "label": "Kontrak Kerja", "module": "employee_core"},
    {"key": "leave", "label": "Cuti", "module": "leave_overtime"},
    {"key": "overtime", "label": "Lembur", "module": "leave_overtime"},
    {"key": "mobilization", "label": "Mobilisasi", "module": "mobilization"},
    {"key": "expense", "label": "Reimbursement / Biaya", "module": "finance_request"},
    {"key": "payroll", "label": "Payroll", "module": "payroll"},
    {"key": "finance_request", "label": "Permintaan Keuangan", "module": "finance_request"},
]

APPROVER_TYPES = [
    {"key": "role", "label": "Berdasarkan Peran"},
    {"key": "user", "label": "Pengguna Tertentu"},
    {"key": "position", "label": "Berdasarkan Jabatan"},
    {"key": "supervisor", "label": "Atasan Langsung Pemohon"},
]

SCOPE_TYPES = [
    {"key": "company", "label": "Seluruh Perusahaan"},
    {"key": "branch", "label": "Cabang Tertentu"},
    {"key": "division", "label": "Divisi Tertentu"},
    {"key": "project", "label": "Proyek Tertentu"},
]


@router.get("/catalog")
async def catalog(ctx: AuthContext = Depends(get_auth)):
    db = get_db()
    roles = serialize_list(await db.roles.find({"status": "active"}, NO_ID).sort("sort_order", 1).to_list(100))
    return {
        "document_kinds": DOCUMENT_KINDS,
        "approver_types": APPROVER_TYPES,
        "scope_types": SCOPE_TYPES,
        "roles": [{"key": r["key"], "name": r["name"]} for r in roles],
    }


async def _with_steps(company_id: str, workflows: List[Dict[str, Any]]):
    db = get_db()
    ids = [w["id"] for w in workflows]
    if not ids:
        return workflows
    rows = serialize_list(
        await db.approval_steps.find(
            {"company_id": company_id, "workflow_id": {"$in": ids}, "status": {"$ne": "deleted"}}, NO_ID
        )
        .sort("step_order", 1)
        .to_list(2000)
    )
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for s in rows:
        grouped.setdefault(s["workflow_id"], []).append(s)
    for w in workflows:
        w["steps"] = sorted(grouped.get(w["id"], []), key=lambda x: x.get("step_order", 0))
        w["step_count"] = len(w["steps"])
    return workflows


def _validate_steps(steps) -> None:
    if not steps:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Alur persetujuan harus memiliki minimal satu tahap penyetuju.",
        )
    orders = [s.step_order for s in steps]
    if len(set(orders)) != len(orders):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Urutan tahap tidak boleh duplikat. Pastikan setiap tahap memiliki nomor urut berbeda.",
        )
    for s in steps:
        if s.approver_type == "role" and not s.approver_role_key:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Tahap '{s.name}' memakai tipe penyetuju Peran, jadi peran penyetuju wajib dipilih.",
            )
        if s.approver_type == "user" and not s.approver_user_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Tahap '{s.name}' memakai tipe penyetuju Pengguna, jadi pengguna penyetuju wajib dipilih.",
            )
        if s.approver_type == "position" and not s.approver_position_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Tahap '{s.name}' memakai tipe penyetuju Jabatan, jadi jabatan penyetuju wajib dipilih.",
            )


@router.get("")
async def list_workflows(
    q: Optional[str] = None,
    document_kind: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = 1,
    limit: int = 20,
    ctx: AuthContext = Depends(require_permission("approval_workflow", "view")),
):
    filters: Dict[str, Any] = {}
    if document_kind:
        filters["document_kind"] = document_kind
    if status_filter:
        filters["status"] = status_filter
    repo = TenantRepository("approval_workflows", ctx.company_id)
    result = await repo.list(
        q=q, search_fields=["code", "name", "document_kind"], filters=filters, page=page, limit=limit
    )
    result["items"] = await _with_steps(ctx.company_id, result["items"])
    return result


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_workflow(
    payload: ApprovalWorkflowInput,
    ctx: AuthContext = Depends(require_permission("approval_workflow", "create")),
):
    _validate_steps(payload.steps)
    repo = TenantRepository("approval_workflows", ctx.company_id)
    await repo.ensure_unique("code", payload.code.upper(), label="Kode alur")
    data = payload.model_dump(exclude={"steps"})
    data["code"] = payload.code.upper()
    created = await repo.create(data, ctx.user_id)

    db = get_db()
    for step in payload.steps:
        doc = {
            "id": new_id(),
            "company_id": ctx.company_id,
            "workflow_id": created["id"],
            "status": "active",
            **step.model_dump(),
            **audit_fields(ctx.user_id, creating=True),
        }
        await db.approval_steps.insert_one(dict(doc))
    out = (await _with_steps(ctx.company_id, [created]))[0]
    await log_action(ctx, "create", "approval_workflow", created["id"], created["name"], after=out)
    return out


@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: str, ctx: AuthContext = Depends(require_permission("approval_workflow", "view"))
):
    repo = TenantRepository("approval_workflows", ctx.company_id)
    doc = await repo.get(workflow_id)
    return (await _with_steps(ctx.company_id, [doc]))[0]


@router.put("/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    payload: ApprovalWorkflowInput,
    ctx: AuthContext = Depends(require_permission("approval_workflow", "edit")),
):
    _validate_steps(payload.steps)
    repo = TenantRepository("approval_workflows", ctx.company_id)
    existing = await repo.get(workflow_id)
    before = (await _with_steps(ctx.company_id, [dict(existing)]))[0]
    await repo.ensure_unique("code", payload.code.upper(), exclude_id=workflow_id, label="Kode alur")
    data = payload.model_dump(exclude={"steps"})
    data["code"] = payload.code.upper()
    await repo.update(workflow_id, data, ctx.user_id)

    db = get_db()
    await db.approval_steps.delete_many({"company_id": ctx.company_id, "workflow_id": workflow_id})
    for step in payload.steps:
        doc = {
            "id": new_id(),
            "company_id": ctx.company_id,
            "workflow_id": workflow_id,
            "status": "active",
            **step.model_dump(),
            **audit_fields(ctx.user_id, creating=True),
        }
        await db.approval_steps.insert_one(dict(doc))
    after = (await _with_steps(ctx.company_id, [await repo.get(workflow_id)]))[0]
    await log_action(
        ctx, "update", "approval_workflow", workflow_id, after.get("name"), before=before, after=after
    )
    return after


@router.patch("/{workflow_id}/status")
async def set_workflow_status(
    workflow_id: str,
    payload: Dict[str, Any] = Body(...),
    ctx: AuthContext = Depends(require_permission("approval_workflow", "edit")),
):
    new_status = payload.get("status")
    if new_status not in ("active", "inactive", "archived"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Status tidak valid.")
    repo = TenantRepository("approval_workflows", ctx.company_id)
    before, after = await repo.set_status(workflow_id, new_status, ctx.user_id)
    await log_action(
        ctx, f"status_{new_status}", "approval_workflow", workflow_id, after.get("name"),
        before=before, after=after,
    )
    label = {"active": "diaktifkan", "inactive": "dinonaktifkan", "archived": "diarsipkan"}[new_status]
    return {"message": f"Alur persetujuan '{after.get('name')}' berhasil {label}.", "item": after}


@router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: str, ctx: AuthContext = Depends(require_permission("approval_workflow", "delete"))
):
    repo = TenantRepository("approval_workflows", ctx.company_id)
    doc = await repo.get(workflow_id)
    db = get_db()
    await db.approval_steps.delete_many({"company_id": ctx.company_id, "workflow_id": workflow_id})
    before = await repo.hard_delete(workflow_id)
    await log_action(ctx, "delete", "approval_workflow", workflow_id, doc.get("name"), before=before)
    return {"message": f"Alur persetujuan '{doc.get('name')}' berhasil dihapus."}
