"""Kalender Masa Berlaku - satu tempat untuk semua pengingat kedaluwarsa
(kontrak kerja, sertifikasi karyawan, dokumen perusahaan).

Hanya menampilkan jenis data yang memang boleh dilihat oleh pengguna
(permission diperiksa per jenis, bukan hanya disembunyikan di UI).
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from ..core.db import NO_ID, get_db, serialize_list
from ..core.deps import AuthContext, get_auth
from ..core.expiry import days_left, expiry_state, month_key, month_label
from ..core.policy import resolve_config

router = APIRouter(prefix="/reminders", tags=["Pengingat Masa Berlaku"])

KIND_LABELS = {
    "contract": "Kontrak Kerja",
    "certification": "Sertifikasi",
    "document": "Dokumen",
}


@router.get("/expiry")
async def expiry_calendar(
    days: int = Query(90, ge=7, le=365),
    kind: Optional[str] = Query(None, description="contract | certification | document"),
    state: Optional[str] = Query(None, description="expired | due_soon"),
    ctx: AuthContext = Depends(get_auth),
):
    db = get_db()
    cid = ctx.company_id
    today = datetime.now(timezone.utc)

    reminder = await resolve_config(cid, "contract.expiry_reminder_days")
    policy_days = int(reminder.get("value") or 30)

    allowed_kinds = []
    if ctx.has_permission("contract", "view") and ctx.has_module("employee_core"):
        allowed_kinds.append("contract")
    if ctx.has_permission("certification", "view") and ctx.has_module("employee_core"):
        allowed_kinds.append("certification")
    if ctx.has_permission("document", "view"):
        allowed_kinds.append("document")

    wanted = [k for k in allowed_kinds if not kind or k == kind]
    items: List[Dict[str, Any]] = []

    employees: Dict[str, Dict[str, Any]] = {}
    if "contract" in wanted or "certification" in wanted:
        employees = {
            e["id"]: e
            for e in await db.employees.find({"company_id": cid}, NO_ID).to_list(5000)
        }

    if "contract" in wanted:
        types = {
            t["id"]: t.get("name")
            for t in await db.contract_types.find({"company_id": cid}, NO_ID).to_list(500)
        }
        rows = serialize_list(
            await db.employee_contracts.find(
                {
                    "company_id": cid,
                    "status": {"$nin": ["deleted", "archived"]},
                    "end_date": {"$nin": [None, ""]},
                },
                NO_ID,
            ).to_list(5000)
        )
        for r in rows:
            emp = employees.get(r.get("employee_id")) or {}
            items.append(
                {
                    "kind": "contract",
                    "kind_label": KIND_LABELS["contract"],
                    "id": r["id"],
                    "title": r.get("contract_number") or "Kontrak kerja",
                    "subtitle": types.get(r.get("contract_type_id")) or "Kontrak kerja",
                    "person_name": emp.get("full_name"),
                    "person_number": emp.get("employee_number"),
                    "link": f"/employees/{r.get('employee_id')}",
                    **expiry_state(r.get("end_date"), policy_days, today),
                }
            )

    if "certification" in wanted:
        types = {
            t["id"]: t.get("name")
            for t in await db.certification_types.find({"company_id": cid}, NO_ID).to_list(500)
        }
        rows = serialize_list(
            await db.employee_certifications.find(
                {
                    "company_id": cid,
                    "status": {"$nin": ["deleted", "archived"]},
                    "expiry_date": {"$nin": [None, ""]},
                },
                NO_ID,
            ).to_list(5000)
        )
        for r in rows:
            emp = employees.get(r.get("employee_id")) or {}
            items.append(
                {
                    "kind": "certification",
                    "kind_label": KIND_LABELS["certification"],
                    "id": r["id"],
                    "title": r.get("name") or types.get(r.get("certification_type_id")) or "Sertifikat",
                    "subtitle": types.get(r.get("certification_type_id")) or "Sertifikasi",
                    "person_name": emp.get("full_name"),
                    "person_number": emp.get("employee_number"),
                    "link": f"/employees/{r.get('employee_id')}",
                    **expiry_state(r.get("expiry_date"), policy_days, today),
                }
            )

    if "document" in wanted:
        types = {
            t["id"]: t.get("name")
            for t in await db.document_types.find({"company_id": cid}, NO_ID).to_list(500)
        }
        rows = serialize_list(
            await db.documents.find(
                {
                    "company_id": cid,
                    "is_deleted": {"$ne": True},
                    "expiry_date": {"$nin": [None, ""]},
                },
                NO_ID,
            ).to_list(5000)
        )
        for r in rows:
            items.append(
                {
                    "kind": "document",
                    "kind_label": KIND_LABELS["document"],
                    "id": r["id"],
                    "title": r.get("name"),
                    "subtitle": types.get(r.get("document_type_id")) or "Dokumen",
                    "person_name": r.get("owner_label"),
                    "person_number": r.get("document_number"),
                    "link": "/documents",
                    **expiry_state(r.get("expiry_date"), policy_days, today),
                }
            )

    summary = {
        "expired": sum(1 for i in items if i["state"] == "expired"),
        "due_soon": sum(1 for i in items if i["state"] == "due_soon"),
        "ok": sum(1 for i in items if i["state"] == "ok"),
        "total": len(items),
        "by_kind": {
            k: sum(1 for i in items if i["kind"] == k and i["state"] in ("expired", "due_soon"))
            for k in KIND_LABELS
        },
    }

    # Kalender: hanya yang kedaluwarsa atau jatuh dalam rentang `days`
    horizon_items = [
        i
        for i in items
        if i["days_left"] is not None and i["days_left"] <= days
    ]
    if state:
        horizon_items = [i for i in horizon_items if i["state"] == state]
    horizon_items.sort(key=lambda x: (x["days_left"] if x["days_left"] is not None else 99999))

    groups: Dict[str, Dict[str, Any]] = {}
    for item in horizon_items:
        key = month_key(item["expiry_date"]) or "tanpa-tanggal"
        group = groups.setdefault(
            key, {"key": key, "label": month_label(key), "items": [], "expired": 0, "due_soon": 0}
        )
        group["items"].append(item)
        if item["state"] == "expired":
            group["expired"] += 1
        elif item["state"] == "due_soon":
            group["due_soon"] += 1

    months = [groups[k] for k in sorted(groups.keys())]

    return {
        "window_days": days,
        "policy_reminder_days": policy_days,
        "available_kinds": [{"key": k, "label": KIND_LABELS[k]} for k in allowed_kinds],
        "summary": summary,
        "items": horizon_items,
        "months": months,
        "generated_at": today,
    }
