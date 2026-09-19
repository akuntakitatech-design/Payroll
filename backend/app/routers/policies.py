from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from ..core.audit import log_action
from ..core.db import NO_ID, get_db, serialize, serialize_list
from ..core.deps import AuthContext, get_auth, require_permission
from ..core.policy import (
    POLICY_GROUPS,
    POLICY_INDEX,
    SCOPE_LABELS,
    SCOPE_PRECEDENCE,
    resolve_config,
)
from ..core.repo import TenantRepository
from ..schemas import ConfigOverrideInput

router = APIRouter(prefix="/policies", tags=["Kebijakan Perusahaan"])

SCOPE_COLLECTION = {
    "branch": "branches",
    "division": "divisions",
    "project": "projects",
}


@router.get("/catalog")
async def catalog(ctx: AuthContext = Depends(require_permission("policy", "view"))):
    return {
        "groups": POLICY_GROUPS,
        "scopes": [
            {"key": k, "label": SCOPE_LABELS[k], "precedence": v}
            for k, v in sorted(SCOPE_PRECEDENCE.items(), key=lambda x: x[1])
        ],
        "active_modules": sorted(ctx.modules),
    }


@router.get("/effective")
async def effective_policies(
    branch_id: Optional[str] = None,
    division_id: Optional[str] = None,
    project_id: Optional[str] = None,
    employee_id: Optional[str] = None,
    ctx: AuthContext = Depends(require_permission("policy", "view")),
):
    """Resolved values following: Perusahaan -> Cabang -> Divisi -> Proyek -> Karyawan."""
    context = {
        "branch_id": branch_id,
        "division_id": division_id,
        "project_id": project_id,
        "employee_id": employee_id,
    }
    groups: List[Dict[str, Any]] = []
    for group in POLICY_GROUPS:
        policies = []
        for policy in group["policies"]:
            resolved = await resolve_config(ctx.company_id, policy["key"], context)
            policies.append({**policy, **resolved})
        groups.append({**group, "policies": policies, "module_active": group["module"] in ctx.modules})
    return {"groups": groups, "context": context}


@router.get("/overrides")
async def list_overrides(
    config_key: Optional[str] = None,
    scope_type: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    ctx: AuthContext = Depends(require_permission("policy", "view")),
):
    filters: Dict[str, Any] = {}
    if config_key:
        filters["config_key"] = config_key
    if scope_type:
        filters["scope_type"] = scope_type
    repo = TenantRepository("config_overrides", ctx.company_id)
    result = await repo.list(
        filters=filters, page=page, limit=limit, search_fields=["config_key", "scope_label"]
    )
    for item in result["items"]:
        definition = POLICY_INDEX.get(item.get("config_key"), {})
        item["policy_name"] = definition.get("name", item.get("config_key"))
        item["policy_type"] = definition.get("type", "text")
        item["unit"] = definition.get("unit")
        item["group_name"] = definition.get("group_name")
        item["scope_label_text"] = SCOPE_LABELS.get(item.get("scope_type"), item.get("scope_type"))
    return result


async def _validate_scope(ctx: AuthContext, payload: ConfigOverrideInput) -> Optional[str]:
    if payload.scope_type not in SCOPE_PRECEDENCE:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Cakupan kebijakan harus salah satu dari: " + ", ".join(SCOPE_PRECEDENCE.keys()),
        )
    if payload.scope_type == "company":
        return None
    if not payload.scope_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Cakupan '{SCOPE_LABELS[payload.scope_type]}' membutuhkan pilihan data spesifik.",
        )
    collection = SCOPE_COLLECTION.get(payload.scope_type)
    if collection:
        db = get_db()
        row = serialize(
            await db[collection].find_one({"company_id": ctx.company_id, "id": payload.scope_id}, NO_ID)
        )
        if not row:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"{SCOPE_LABELS[payload.scope_type]} yang dipilih tidak ditemukan di perusahaan aktif Anda.",
            )
        return row.get("name")
    return payload.scope_label


@router.post("/overrides", status_code=status.HTTP_201_CREATED)
async def create_override(
    payload: ConfigOverrideInput, ctx: AuthContext = Depends(require_permission("policy", "config"))
):
    if payload.config_key not in POLICY_INDEX:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Kebijakan '{payload.config_key}' tidak dikenal.",
        )
    label = await _validate_scope(ctx, payload)
    db = get_db()
    duplicate = await db.config_overrides.count_documents(
        {
            "company_id": ctx.company_id,
            "config_key": payload.config_key,
            "scope_type": payload.scope_type,
            "scope_id": payload.scope_id,
            "status": "active",
        }
    )
    if duplicate:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Kebijakan ini sudah memiliki nilai pada cakupan tersebut. Ubah nilai yang ada agar tidak bertabrakan.",
        )
    data = payload.model_dump()
    data["scope_label"] = payload.scope_label or label
    repo = TenantRepository("config_overrides", ctx.company_id)
    created = await repo.create(data, ctx.user_id)
    await log_action(
        ctx, "create", "policy", created["id"],
        POLICY_INDEX[payload.config_key]["name"], after=created,
    )
    return created


@router.put("/overrides/{override_id}")
async def update_override(
    override_id: str,
    payload: Dict[str, Any] = Body(...),
    ctx: AuthContext = Depends(require_permission("policy", "config")),
):
    allowed = {"value", "effective_from", "effective_to", "notes", "status", "scope_label"}
    data = {k: v for k, v in payload.items() if k in allowed}
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tidak ada perubahan yang dikirim.")
    repo = TenantRepository("config_overrides", ctx.company_id)
    before, after = await repo.update(override_id, data, ctx.user_id)
    await log_action(
        ctx, "update", "policy", override_id,
        POLICY_INDEX.get(after.get("config_key"), {}).get("name"), before=before, after=after,
    )
    return after


@router.delete("/overrides/{override_id}")
async def delete_override(
    override_id: str, ctx: AuthContext = Depends(require_permission("policy", "delete"))
):
    repo = TenantRepository("config_overrides", ctx.company_id)
    doc = await repo.get(override_id)
    before = await repo.hard_delete(override_id)
    await log_action(
        ctx, "delete", "policy", override_id,
        POLICY_INDEX.get(doc.get("config_key"), {}).get("name"), before=before,
    )
    return {"message": "Nilai kebijakan berhasil dihapus. Sistem kembali memakai aturan yang lebih umum."}


@router.get("/resolve")
async def resolve_single(
    config_key: str,
    branch_id: Optional[str] = None,
    division_id: Optional[str] = None,
    project_id: Optional[str] = None,
    employee_id: Optional[str] = None,
    ctx: AuthContext = Depends(require_permission("policy", "view")),
):
    resolved = await resolve_config(
        ctx.company_id,
        config_key,
        {
            "branch_id": branch_id,
            "division_id": division_id,
            "project_id": project_id,
            "employee_id": employee_id,
        },
    )
    return {**POLICY_INDEX.get(config_key, {}), **resolved}
