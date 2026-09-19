"""Modul Payroll: struktur gaji, komponen, payroll run bulanan, slip gaji.

Perhitungan memakai `app/core/payroll.py` (BPJS + PPh 21 TER PMK 168/2023) yang
sudah diverifikasi lewat `test_core.py`. Seluruh akses data lewat
`TenantRepository` sehingga tidak mungkin lintas perusahaan.
"""
import asyncio
import csv
import io
import logging
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..core.audit import log_action
from ..core.db import NO_ID, get_db, new_id, now, serialize, serialize_list
from ..core.deps import AuthContext, get_auth, require_permission
from ..core.payroll import (
    JKK_RISK_CLASSES,
    MONTH_NAMES_ID,
    StatutoryConfig,
    compute_payslip,
    summarize_run,
)
from ..core.payroll_service import (
    RUN_STATUS_LABELS,
    build_employee_input,
    get_statutory_config,
    load_components,
    load_salaries,
    resolve_own_employee,
    save_statutory_config,
    ytd_accumulation,
)
from ..core.mailer import MailerError, send_email
from ..core.pdf import build_payslip_pdf
from ..core.repo import TenantRepository
from ..core.ter import PTKP_LABELS, PTKP_STATUSES, PTKP_TO_CATEGORY, ptkp_annual
from ..schemas import (
    EmployeeSalaryUpsert,
    PayslipEmailRequest,
    PayrollAdjustmentUpdate,
    PayrollComponentCreate,
    PayrollComponentUpdate,
    PayrollRunCreate,
    PayrollRunDecision,
    StatutoryConfigUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payroll", tags=["Payroll"])

EDITABLE_STATUSES = ("draft", "rejected")


def _period_label(year: int, month: int) -> str:
    return f"{MONTH_NAMES_ID[month - 1]} {year}"


# ==========================================================================
# Katalog & konfigurasi
# ==========================================================================
@router.get("/catalog")
async def catalog(ctx: AuthContext = Depends(require_permission("payroll", "view"))):
    cfg = await get_statutory_config(ctx.company_id)
    return {
        "ptkp_statuses": [
            {
                "value": s,
                "label": f"{s} \u2014 {PTKP_LABELS[s]}",
                "description": PTKP_LABELS[s],
                "ter_category": PTKP_TO_CATEGORY[s],
                "ptkp_annual": ptkp_annual(s),
            }
            for s in PTKP_STATUSES
        ],
        "jkk_risk_classes": [
            {"value": k, "label": v["label"], "rate": v["rate"]}
            for k, v in JKK_RISK_CLASSES.items()
        ],
        "months": [{"value": i + 1, "label": name} for i, name in enumerate(MONTH_NAMES_ID)],
        "component_kinds": [
            {"value": "earning", "label": "Penghasilan"},
            {"value": "deduction", "label": "Potongan"},
        ],
        "component_calcs": [
            {"value": "fixed", "label": "Nominal tetap"},
            {"value": "percent_of_basic", "label": "Persentase gaji pokok"},
        ],
        "run_statuses": [{"value": k, "label": v} for k, v in RUN_STATUS_LABELS.items()],
        "statutory": cfg.to_dict(),
    }


@router.get("/config")
async def get_config(ctx: AuthContext = Depends(require_permission("payroll", "view"))):
    cfg = await get_statutory_config(ctx.company_id)
    return {
        "statutory": cfg.to_dict(),
        "jkk_risk_classes": [
            {"value": k, "label": v["label"], "rate": v["rate"]}
            for k, v in JKK_RISK_CLASSES.items()
        ],
    }


@router.put("/config")
async def update_config(
    payload: StatutoryConfigUpdate,
    ctx: AuthContext = Depends(require_permission("payroll", "config")),
):
    before = (await get_statutory_config(ctx.company_id)).to_dict()
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    if data.get("jkk_risk_class") and data["jkk_risk_class"] not in JKK_RISK_CLASSES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Kelas risiko JKK tidak dikenal. Pilih: {', '.join(JKK_RISK_CLASSES)}.",
        )
    after = await save_statutory_config(ctx.company_id, data, ctx.user_id)
    await log_action(ctx, "update", "payroll", None, "Parameter statutori payroll",
                     before=before, after=after)
    return {"statutory": after}


# ==========================================================================
# Komponen gaji (master)
# ==========================================================================
@router.get("/components")
async def list_components(
    q: Optional[str] = None,
    kind: Optional[str] = None,
    ctx: AuthContext = Depends(require_permission("payroll_component", "view")),
):
    repo = TenantRepository("payroll_components", ctx.company_id)
    filters = {"kind": kind} if kind else None
    result = await repo.list(q=q, search_fields=["name", "code"], filters=filters,
                             page=1, limit=200, sort_by="sort_order", sort_dir="asc")
    return result


@router.post("/components", status_code=status.HTTP_201_CREATED)
async def create_component(
    payload: PayrollComponentCreate,
    ctx: AuthContext = Depends(require_permission("payroll_component", "create")),
):
    repo = TenantRepository("payroll_components", ctx.company_id)
    data = payload.model_dump()
    data["code"] = (data["code"] or "").strip().upper()
    await repo.ensure_unique("code", data["code"], label="Kode komponen")
    created = await repo.create(data, ctx.user_id)
    await log_action(ctx, "create", "payroll", created["id"], created["name"], after=created)
    return created


@router.put("/components/{component_id}")
async def update_component(
    component_id: str,
    payload: PayrollComponentUpdate,
    ctx: AuthContext = Depends(require_permission("payroll_component", "edit")),
):
    repo = TenantRepository("payroll_components", ctx.company_id)
    await repo.get(component_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("code"):
        data["code"] = data["code"].strip().upper()
        await repo.ensure_unique("code", data["code"], exclude_id=component_id,
                                 label="Kode komponen")
    before, after = await repo.update(component_id, data, ctx.user_id)
    await log_action(ctx, "update", "payroll", component_id, after.get("name"),
                     before=before, after=after)
    return after


@router.delete("/components/{component_id}")
async def delete_component(
    component_id: str,
    ctx: AuthContext = Depends(require_permission("payroll_component", "delete")),
):
    db = get_db()
    repo = TenantRepository("payroll_components", ctx.company_id)
    component = await repo.get(component_id)
    used = await db.employee_salaries.count_documents(
        {"company_id": ctx.company_id, "components.component_id": component_id,
         "status": {"$ne": "deleted"}}
    )
    if used:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Komponen ini masih dipakai pada {used} struktur gaji karyawan. "
            "Lepas dari karyawan terlebih dahulu atau nonaktifkan komponennya.",
        )
    before, after = await repo.update(component_id, {"status": "deleted"}, ctx.user_id)
    await log_action(ctx, "delete", "payroll", component_id, component.get("name"),
                     before=before, after=after)
    return {"deleted": True, "id": component_id}


# ==========================================================================
# Struktur gaji karyawan
# ==========================================================================
async def _employee_or_404(company_id: str, employee_id: str) -> Dict[str, Any]:
    db = get_db()
    emp = await db.employees.find_one(
        {"company_id": company_id, "id": employee_id, "status": {"$ne": "deleted"}}, NO_ID
    )
    if not emp:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Karyawan tidak ditemukan pada perusahaan aktif Anda.")
    return emp


@router.get("/salaries")
async def list_salaries(
    q: Optional[str] = None,
    only_unset: bool = False,
    ctx: AuthContext = Depends(require_permission("employee_salary", "view")),
):
    """Daftar karyawan + status kelengkapan struktur gaji."""
    db = get_db()
    cid = ctx.company_id
    query: Dict[str, Any] = {"company_id": cid, "status": {"$ne": "deleted"}}
    if q:
        query["$or"] = [
            {"full_name": {"$regex": q, "$options": "i"}},
            {"employee_number": {"$regex": q, "$options": "i"}},
        ]
    employees = await db.employees.find(query, NO_ID).sort("full_name", 1).to_list(2000)
    salaries = await load_salaries(cid, [e["id"] for e in employees])
    catalog_map = await load_components(cid)

    items = []
    for emp in employees:
        sal = salaries.get(emp["id"])
        comps = [
            {
                "component_id": c.get("component_id"),
                "amount": c.get("amount"),
                "name": (catalog_map.get(c.get("component_id")) or {}).get("name"),
                "kind": (catalog_map.get(c.get("component_id")) or {}).get("kind"),
            }
            for c in ((sal or {}).get("components") or [])
        ]
        entry = {
            "employee_id": emp["id"],
            "employee_number": emp.get("employee_number"),
            "full_name": emp.get("full_name"),
            "job_title": emp.get("job_title"),
            "employee_status": emp.get("status"),
            "has_salary": bool(sal and float(sal.get("basic_salary") or 0) > 0),
            "basic_salary": float((sal or {}).get("basic_salary") or 0),
            "ptkp_status": (sal or {}).get("ptkp_status") or "TK/0",
            "ter_category": PTKP_TO_CATEGORY.get((sal or {}).get("ptkp_status") or "TK/0", "A"),
            "has_npwp": (sal or {}).get("has_npwp"),
            "bpjs_kesehatan_enrolled": (sal or {}).get("bpjs_kesehatan_enrolled", True),
            "bpjs_jht_enrolled": (sal or {}).get("bpjs_jht_enrolled", True),
            "bpjs_jp_enrolled": (sal or {}).get("bpjs_jp_enrolled", True),
            "components": comps,
            "updated_at": (sal or {}).get("updated_at"),
        }
        if only_unset and entry["has_salary"]:
            continue
        items.append(entry)

    return {
        "items": items,
        "total": len(items),
        "unset_count": sum(1 for i in items if not i["has_salary"]),
    }


@router.get("/salaries/{employee_id}")
async def get_salary(
    employee_id: str,
    ctx: AuthContext = Depends(require_permission("employee_salary", "view")),
):
    emp = await _employee_or_404(ctx.company_id, employee_id)
    db = get_db()
    sal = await db.employee_salaries.find_one(
        {"company_id": ctx.company_id, "employee_id": employee_id, "status": {"$ne": "deleted"}},
        NO_ID,
    )
    history = await db.employee_salary_history.find(
        {"company_id": ctx.company_id, "employee_id": employee_id}, NO_ID
    ).sort("created_at", -1).to_list(50)

    # lengkapi komponen dengan nama & nominal efektif agar siap tampil di UI
    if sal and sal.get("components"):
        catalog = {
            c["id"]: c
            for c in await db.payroll_components.find(
                {"company_id": ctx.company_id, "status": {"$ne": "deleted"}}, NO_ID
            ).to_list(500)
        }
        enriched = []
        for row in sal.get("components") or []:
            comp = catalog.get(row.get("component_id")) or {}
            amount = row.get("amount")
            effective = amount if amount is not None else comp.get("default_amount")
            enriched.append({
                **row,
                "name": comp.get("name") or row.get("component_id"),
                "code": comp.get("code"),
                "kind": comp.get("kind"),
                "calc": comp.get("calc"),
                "percent": comp.get("percent"),
                "effective_amount": effective,
                "uses_default": amount is None,
            })
        sal = {**sal, "components": enriched}
    return {
        "employee": {
            "id": emp["id"],
            "full_name": emp.get("full_name"),
            "employee_number": emp.get("employee_number"),
            "job_title": emp.get("job_title"),
            "npwp": emp.get("npwp"),
            "bank_name": emp.get("bank_name"),
            "bank_account_number": emp.get("bank_account_number"),
        },
        "salary": serialize(sal),
        "history": serialize_list(history),
    }


@router.put("/salaries/{employee_id}")
async def upsert_salary(
    employee_id: str,
    payload: EmployeeSalaryUpsert,
    ctx: AuthContext = Depends(require_permission("employee_salary", "edit")),
):
    emp = await _employee_or_404(ctx.company_id, employee_id)
    db = get_db()
    cid = ctx.company_id

    data = payload.model_dump(exclude_unset=True)
    if data.get("ptkp_status") and data["ptkp_status"] not in PTKP_STATUSES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Status PTKP tidak dikenal. Pilih: {', '.join(PTKP_STATUSES)}.",
        )
    if data.get("basic_salary") is not None and float(data["basic_salary"]) < 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Gaji pokok tidak boleh negatif.")

    catalog_map = await load_components(cid)
    for comp in data.get("components") or []:
        if comp.get("component_id") not in catalog_map:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Salah satu komponen gaji tidak ditemukan atau sudah tidak aktif. "
                "Muat ulang halaman lalu coba lagi.",
            )
        if float(comp.get("amount") or 0) < 0:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Nominal komponen tidak boleh negatif.")

    repo = TenantRepository("employee_salaries", cid)
    existing = await db.employee_salaries.find_one(
        {"company_id": cid, "employee_id": employee_id}, NO_ID
    )

    if existing:
        before, after = await repo.update(existing["id"], {**data, "status": "active"}, ctx.user_id)
    else:
        before = None
        after = await repo.create({**data, "employee_id": employee_id}, ctx.user_id)

    # riwayat perubahan gaji
    if not before or float(before.get("basic_salary") or 0) != float(after.get("basic_salary") or 0):
        await db.employee_salary_history.insert_one({
            "id": new_id(),
            "company_id": cid,
            "employee_id": employee_id,
            "basic_salary": float(after.get("basic_salary") or 0),
            "previous_basic_salary": float((before or {}).get("basic_salary") or 0),
            "ptkp_status": after.get("ptkp_status"),
            "effective_date": after.get("effective_date"),
            "notes": after.get("notes"),
            "status": "active",
            "created_at": now(),
            "updated_at": now(),
            "created_by": ctx.user_id,
            "updated_by": ctx.user_id,
        })

    await log_action(ctx, "update" if before else "create", "payroll", employee_id,
                     f"Struktur gaji {emp.get('full_name')}", before=before, after=after)
    return after


# ==========================================================================
# Payroll run
# ==========================================================================
async def _calculate_run(run: Dict[str, Any], ctx: AuthContext) -> Dict[str, Any]:
    """Hitung/hitung-ulang seluruh slip gaji dalam satu run."""
    db = get_db()
    cid = run["company_id"]
    cfg = await get_statutory_config(cid)
    catalog_map = await load_components(cid)

    employees = await db.employees.find(
        {"company_id": cid, "status": "active"}, NO_ID
    ).sort("full_name", 1).to_list(5000)
    salaries = await load_salaries(cid, [e["id"] for e in employees])

    existing_items = {
        i["employee_id"]: i
        for i in await db.payroll_items.find(
            {"company_id": cid, "run_id": run["id"]}, NO_ID
        ).to_list(5000)
    }

    payslips: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    is_final = run["month"] == 12

    for emp in employees:
        prev = existing_items.get(emp["id"]) or {}
        adjustments = prev.get("adjustments") or {}
        emp_input = await build_employee_input(
            cid, emp, salaries.get(emp["id"]), catalog_map, adjustments
        )
        if emp_input.basic_salary <= 0:
            skipped.append({
                "employee_id": emp["id"],
                "full_name": emp.get("full_name"),
                "employee_number": emp.get("employee_number"),
                "reason": "Gaji pokok belum diatur di menu Struktur Gaji.",
            })
            continue

        ytd = (
            await ytd_accumulation(cid, emp["id"], run["year"], run["month"] - 1)
            if is_final
            else {"taxable_gross": 0.0, "pph21": 0.0, "jht_jp": 0.0, "months": 0}
        )

        slip = compute_payslip(
            emp_input, cfg, month=run["month"], year=run["year"],
            ytd_taxable_gross=ytd["taxable_gross"],
            ytd_pph21_withheld=ytd["pph21"],
            ytd_jht_jp_employee=ytd["jht_jp"],
            ytd_months=ytd["months"],
        )
        slip["id"] = prev.get("id") or new_id()
        slip["company_id"] = cid
        slip["run_id"] = run["id"]
        slip["adjustments"] = {
            "working_days": adjustments.get("working_days"),
            "unpaid_days": float(adjustments.get("unpaid_days") or 0),
            "overtime_hours": float(adjustments.get("overtime_hours") or 0),
            "extra_earnings": adjustments.get("extra_earnings") or [],
            "extra_deductions": adjustments.get("extra_deductions") or [],
            "notes": adjustments.get("notes"),
        }
        slip["status"] = "active"
        slip["created_at"] = prev.get("created_at") or now()
        slip["updated_at"] = now()
        slip["created_by"] = prev.get("created_by") or ctx.user_id
        slip["updated_by"] = ctx.user_id
        payslips.append(slip)

    await db.payroll_items.delete_many({"company_id": cid, "run_id": run["id"]})
    if payslips:
        await db.payroll_items.insert_many([dict(p) for p in payslips])

    totals = summarize_run(payslips)
    patch = {
        "totals": totals,
        "employee_count": len(payslips),
        "skipped": skipped,
        "statutory_snapshot": cfg.to_dict(),
        "calculated_at": now(),
        "calculated_by": ctx.user_id,
        "updated_at": now(),
        "updated_by": ctx.user_id,
    }
    await db.payroll_runs.update_one({"company_id": cid, "id": run["id"]}, {"$set": patch})
    return {**run, **patch}


@router.get("/runs")
async def list_runs(
    year: Optional[int] = Query(None, ge=2000, le=2100),
    run_status: Optional[str] = Query(None),
    ctx: AuthContext = Depends(require_permission("payroll", "view")),
):
    db = get_db()
    query: Dict[str, Any] = {"company_id": ctx.company_id, "status": {"$ne": "deleted"}}
    if year:
        query["year"] = year
    if run_status:
        query["run_status"] = run_status
    runs = await db.payroll_runs.find(query, NO_ID).sort(
        [("year", -1), ("month", -1)]
    ).to_list(200)
    for r in runs:
        r["status_label"] = RUN_STATUS_LABELS.get(r.get("run_status"), r.get("run_status"))
    years = sorted({r["year"] for r in runs}, reverse=True)
    return {"items": serialize_list(runs), "total": len(runs), "years": years}


@router.post("/runs", status_code=status.HTTP_201_CREATED)
async def create_run(
    payload: PayrollRunCreate,
    ctx: AuthContext = Depends(require_permission("payroll", "create")),
):
    db = get_db()
    cid = ctx.company_id
    if not 1 <= payload.month <= 12:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Bulan harus antara 1 dan 12.")

    duplicate = await db.payroll_runs.find_one(
        {"company_id": cid, "year": payload.year, "month": payload.month,
         "status": {"$ne": "deleted"}},
        NO_ID,
    )
    if duplicate:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Payroll periode {_period_label(payload.year, payload.month)} sudah ada "
            f"dengan status {RUN_STATUS_LABELS.get(duplicate.get('run_status'), '-')}. "
            "Buka periode tersebut untuk melanjutkan.",
        )

    workflow = await db.approval_workflows.find_one(
        {"company_id": cid, "document_kind": "payroll", "status": {"$ne": "deleted"}}, NO_ID
    )

    repo = TenantRepository("payroll_runs", cid)
    run = await repo.create(
        {
            "year": payload.year,
            "month": payload.month,
            "period_label": _period_label(payload.year, payload.month),
            "run_status": "draft",
            "notes": payload.notes,
            "payment_date": payload.payment_date,
            "workflow_id": (workflow or {}).get("id"),
            "workflow_name": (workflow or {}).get("name"),
            "totals": {},
            "employee_count": 0,
            "skipped": [],
            "history": [],
        },
        ctx.user_id,
    )
    run = await _calculate_run(run, ctx)
    await log_action(ctx, "create", "payroll", run["id"],
                     f"Payroll {run['period_label']}", after=run)
    return {**run, "status_label": RUN_STATUS_LABELS["draft"]}


async def _run_or_404(cid: str, run_id: str) -> Dict[str, Any]:
    repo = TenantRepository("payroll_runs", cid)
    return await repo.get(run_id)


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    ctx: AuthContext = Depends(require_permission("payroll", "view")),
):
    db = get_db()
    run = await _run_or_404(ctx.company_id, run_id)
    items = await db.payroll_items.find(
        {"company_id": ctx.company_id, "run_id": run_id}, NO_ID
    ).sort("full_name", 1).to_list(5000)

    steps = []
    if run.get("workflow_id"):
        steps = await db.approval_steps.find(
            {"company_id": ctx.company_id, "workflow_id": run["workflow_id"]}, NO_ID
        ).sort("step_order", 1).to_list(20)

    return {
        "run": {**run, "status_label": RUN_STATUS_LABELS.get(run.get("run_status"))},
        "items": serialize_list(items),
        "approval_steps": serialize_list(steps),
        "can_edit": run.get("run_status") in EDITABLE_STATUSES,
        "can_submit": run.get("run_status") in EDITABLE_STATUSES and bool(items),
        "can_approve": (
            run.get("run_status") == "pending_approval"
            and ctx.has_permission("payroll", "approve")
        ),
        "can_mark_paid": (
            run.get("run_status") == "approved" and ctx.has_permission("payroll", "edit")
        ),
    }


@router.post("/runs/{run_id}/recalculate")
async def recalculate_run(
    run_id: str,
    ctx: AuthContext = Depends(require_permission("payroll", "edit")),
):
    run = await _run_or_404(ctx.company_id, run_id)
    if run.get("run_status") not in EDITABLE_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Payroll berstatus '{RUN_STATUS_LABELS.get(run.get('run_status'))}' "
            "tidak dapat dihitung ulang. Hanya draf atau yang ditolak yang bisa diubah.",
        )
    updated = await _calculate_run(run, ctx)
    await log_action(ctx, "update", "payroll", run_id,
                     f"Hitung ulang payroll {run['period_label']}")
    return {**updated, "status_label": RUN_STATUS_LABELS.get(updated.get("run_status"))}


@router.put("/runs/{run_id}/items/{item_id}/adjustments")
async def update_adjustments(
    run_id: str,
    item_id: str,
    payload: PayrollAdjustmentUpdate,
    ctx: AuthContext = Depends(require_permission("payroll", "edit")),
):
    """Ubah lembur/absen/tambahan-potongan satu karyawan lalu hitung ulang slipnya."""
    db = get_db()
    cid = ctx.company_id
    run = await _run_or_404(cid, run_id)
    if run.get("run_status") not in EDITABLE_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Penyesuaian hanya bisa diubah saat payroll masih draf atau ditolak.",
        )

    item = await db.payroll_items.find_one({"company_id": cid, "run_id": run_id, "id": item_id}, NO_ID)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Baris slip gaji tidak ditemukan pada periode ini.")

    adj = payload.model_dump(exclude_unset=True)
    if adj.get("unpaid_days") is not None and float(adj["unpaid_days"]) < 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Jumlah hari tidak hadir tidak boleh negatif.")
    if adj.get("overtime_hours") is not None and float(adj["overtime_hours"]) < 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Jam lembur tidak boleh negatif.")
    if adj.get("working_days") is not None and not (1 <= int(adj["working_days"]) <= 31):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Hari kerja harus antara 1 dan 31.")
    for group in ("extra_earnings", "extra_deductions"):
        for entry in adj.get(group) or []:
            if not (entry.get("name") or "").strip():
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                    "Nama komponen tambahan wajib diisi.")
            if float(entry.get("amount") or 0) < 0:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                    "Nominal komponen tambahan tidak boleh negatif.")

    merged = {**(item.get("adjustments") or {}), **adj}
    emp = await _employee_or_404(cid, item["employee_id"])
    cfg = await get_statutory_config(cid)
    catalog_map = await load_components(cid)
    salaries = await load_salaries(cid, [emp["id"]])

    emp_input = await build_employee_input(cid, emp, salaries.get(emp["id"]), catalog_map, merged)
    ytd = (
        await ytd_accumulation(cid, emp["id"], run["year"], run["month"] - 1)
        if run["month"] == 12
        else {"taxable_gross": 0.0, "pph21": 0.0, "jht_jp": 0.0, "months": 0}
    )
    slip = compute_payslip(
        emp_input, cfg, month=run["month"], year=run["year"],
        ytd_taxable_gross=ytd["taxable_gross"], ytd_pph21_withheld=ytd["pph21"],
        ytd_jht_jp_employee=ytd["jht_jp"], ytd_months=ytd["months"],
    )
    slip.update({
        "id": item["id"], "company_id": cid, "run_id": run_id,
        "adjustments": merged, "status": "active",
        "created_at": item.get("created_at"), "created_by": item.get("created_by"),
        "updated_at": now(), "updated_by": ctx.user_id,
    })
    await db.payroll_items.replace_one({"company_id": cid, "id": item["id"]}, dict(slip))

    all_items = await db.payroll_items.find({"company_id": cid, "run_id": run_id}, NO_ID).to_list(5000)
    totals = summarize_run(all_items)
    await db.payroll_runs.update_one(
        {"company_id": cid, "id": run_id},
        {"$set": {"totals": totals, "updated_at": now(), "updated_by": ctx.user_id}},
    )
    await log_action(ctx, "update", "payroll", item["id"],
                     f"Penyesuaian payroll {emp.get('full_name')} \u2014 {run['period_label']}",
                     before=item.get("adjustments"), after=merged)
    return {"item": slip, "totals": totals}


async def _transition(
    ctx: AuthContext, run_id: str, new_status: str, action: str, note: Optional[str] = None
) -> Dict[str, Any]:
    db = get_db()
    cid = ctx.company_id
    run = await _run_or_404(cid, run_id)
    entry = {
        "status": new_status,
        "action": action,
        "note": note,
        "user_id": ctx.user_id,
        "user_name": ctx.user.get("full_name"),
        "at": now(),
    }
    patch: Dict[str, Any] = {
        "run_status": new_status,
        "updated_at": now(),
        "updated_by": ctx.user_id,
        f"{action}_at": now(),
        f"{action}_by": ctx.user_id,
        f"{action}_by_name": ctx.user.get("full_name"),
    }
    if note is not None:
        patch[f"{action}_note"] = note
    await db.payroll_runs.update_one(
        {"company_id": cid, "id": run_id},
        {"$set": patch, "$push": {"history": entry}},
    )
    after = await _run_or_404(cid, run_id)
    await log_action(ctx, action, "payroll", run_id,
                     f"Payroll {run['period_label']}", before=run, after=after, notes=note)
    return {**after, "status_label": RUN_STATUS_LABELS.get(new_status)}


@router.post("/runs/{run_id}/submit")
async def submit_run(
    run_id: str,
    payload: Optional[PayrollRunDecision] = None,
    ctx: AuthContext = Depends(require_permission("payroll", "edit")),
):
    db = get_db()
    run = await _run_or_404(ctx.company_id, run_id)
    if run.get("run_status") not in EDITABLE_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Payroll sudah berstatus '{RUN_STATUS_LABELS.get(run.get('run_status'))}' "
            "sehingga tidak bisa diajukan lagi.",
        )
    count = await db.payroll_items.count_documents({"company_id": ctx.company_id, "run_id": run_id})
    if not count:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Tidak ada slip gaji pada periode ini. Lengkapi struktur gaji karyawan "
            "lalu hitung ulang payroll.",
        )
    return await _transition(ctx, run_id, "pending_approval", "submitted",
                             (payload.note if payload else None))


@router.post("/runs/{run_id}/approve")
async def approve_run(
    run_id: str,
    payload: Optional[PayrollRunDecision] = None,
    ctx: AuthContext = Depends(require_permission("payroll", "approve")),
):
    run = await _run_or_404(ctx.company_id, run_id)
    if run.get("run_status") != "pending_approval":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Hanya payroll yang sedang menunggu persetujuan yang dapat disetujui.",
        )
    if run.get("submitted_by") == ctx.user_id and not ctx.is_super_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Anda mengajukan payroll ini, sehingga persetujuan harus dilakukan "
            "oleh pengguna lain (pemisahan tugas).",
        )
    result = await _transition(ctx, run_id, "approved", "approved",
                               (payload.note if payload else None))
    # Kirim slip gaji otomatis bila diaktifkan pada pengaturan email.
    try:
        smtp = await get_db().smtp_settings.find_one({"company_id": ctx.company_id}, NO_ID) or {}
        if smtp.get("auto_send_payslip") and smtp.get("host"):
            asyncio.create_task(_send_payslips(ctx.company_id, run_id, None, ctx.user_id, "otomatis"))
            result["payslip_email"] = "Pengiriman slip gaji via email dijalankan di latar belakang."
    except Exception as exc:  # noqa: BLE001
        logger.warning("Auto kirim slip gaji gagal dijadwalkan: %s", exc)
    return result


@router.post("/runs/{run_id}/reject")
async def reject_run(
    run_id: str,
    payload: PayrollRunDecision,
    ctx: AuthContext = Depends(require_permission("payroll", "approve")),
):
    run = await _run_or_404(ctx.company_id, run_id)
    if run.get("run_status") != "pending_approval":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Hanya payroll yang sedang menunggu persetujuan yang dapat ditolak.",
        )
    if not (payload.note or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Alasan penolakan wajib diisi agar HR tahu yang perlu diperbaiki.")
    return await _transition(ctx, run_id, "rejected", "rejected", payload.note)


@router.post("/runs/{run_id}/mark-paid")
async def mark_paid(
    run_id: str,
    payload: Optional[PayrollRunDecision] = None,
    ctx: AuthContext = Depends(require_permission("payroll", "edit")),
):
    run = await _run_or_404(ctx.company_id, run_id)
    if run.get("run_status") != "approved":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Payroll harus disetujui terlebih dahulu sebelum ditandai dibayar.")
    return await _transition(ctx, run_id, "paid", "paid", (payload.note if payload else None))


@router.delete("/runs/{run_id}")
async def delete_run(
    run_id: str,
    ctx: AuthContext = Depends(require_permission("payroll", "delete")),
):
    db = get_db()
    run = await _run_or_404(ctx.company_id, run_id)
    if run.get("run_status") in ("approved", "paid"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Payroll yang sudah disetujui atau dibayar tidak dapat dihapus "
            "karena menjadi dasar rekonsiliasi pajak tahunan.",
        )
    await db.payroll_items.delete_many({"company_id": ctx.company_id, "run_id": run_id})
    repo = TenantRepository("payroll_runs", ctx.company_id)
    before, after = await repo.update(run_id, {"status": "deleted"}, ctx.user_id)
    await log_action(ctx, "delete", "payroll", run_id, f"Payroll {run['period_label']}",
                     before=before, after=after)
    return {"deleted": True, "id": run_id}


# ==========================================================================
# Slip gaji PDF & ekspor
# ==========================================================================
async def _payslip_pdf_response(cid: str, item: Dict[str, Any]) -> Response:
    db = get_db()
    company = await db.companies.find_one({"id": cid}, NO_ID) or {}
    generated = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    pdf = build_payslip_pdf(item, company, generated_at=generated)
    period = (item.get("period") or {}).get("label", "").replace(" ", "-")
    name = (item.get("full_name") or "karyawan").replace(" ", "-")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="Slip-Gaji-{name}-{period}.pdf"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/runs/{run_id}/items/{item_id}/payslip")
async def download_payslip(
    run_id: str,
    item_id: str,
    ctx: AuthContext = Depends(require_permission("payroll", "view")),
):
    db = get_db()
    await _run_or_404(ctx.company_id, run_id)
    item = await db.payroll_items.find_one(
        {"company_id": ctx.company_id, "run_id": run_id, "id": item_id}, NO_ID
    )
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Slip gaji tidak ditemukan.")
    return await _payslip_pdf_response(ctx.company_id, item)


# ==========================================================================
# File transfer bank, rekap BPJS & PPh 21, kirim slip via email
# ==========================================================================
PAID_STATUSES = ("approved", "paid")


async def _run_ready_for_disbursement(cid: str, run_id: str) -> Dict[str, Any]:
    run = await _run_or_404(cid, run_id)
    if run.get("run_status") not in PAID_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "File transfer hanya tersedia setelah payroll disetujui. "
            f"Status saat ini: {RUN_STATUS_LABELS.get(run.get('run_status'), '-')}.",
        )
    return run


async def _company_payer(cid: str) -> Dict[str, Any]:
    db = get_db()
    settings = await db.company_settings.find_one({"company_id": cid}, NO_ID) or {}
    company = await db.companies.find_one({"id": cid}, NO_ID) or {}
    return {
        "company_name": company.get("name"),
        "bank_name": settings.get("payroll_bank_name"),
        "account_number": settings.get("payroll_bank_account_number"),
        "account_name": settings.get("payroll_bank_account_name") or company.get("name"),
        "note_template": settings.get("payroll_transfer_note") or "Gaji {periode}",
    }


@router.get("/runs/{run_id}/bank-file/preview")
async def bank_file_preview(
    run_id: str,
    ctx: AuthContext = Depends(require_permission("payroll", "export")),
):
    """Ringkasan sebelum Finance mengunduh file transfer bank."""
    db = get_db()
    run = await _run_ready_for_disbursement(ctx.company_id, run_id)
    items = await db.payroll_items.find(
        {"company_id": ctx.company_id, "run_id": run_id}, NO_ID
    ).sort("full_name", 1).to_list(5000)
    payer = await _company_payer(ctx.company_id)
    ready, missing = [], []
    for it in items:
        row = {
            "item_id": it.get("id"),
            "full_name": it.get("full_name"),
            "employee_number": it.get("employee_number"),
            "bank_name": it.get("bank_name"),
            "bank_account_number": it.get("bank_account_number"),
            "net_pay": float((it.get("totals") or {}).get("net_pay") or 0),
        }
        (ready if row["bank_account_number"] else missing).append(row)
    return {
        "run": {"id": run["id"], "period_label": run.get("period_label"),
                "run_status": run.get("run_status"),
                "status_label": RUN_STATUS_LABELS.get(run.get("run_status")),
                "payment_date": run.get("payment_date")},
        "payer": payer,
        "ready": ready,
        "missing": missing,
        "ready_count": len(ready),
        "missing_count": len(missing),
        "total_amount": round(sum(r["net_pay"] for r in ready), 2),
        "payer_complete": bool(payer.get("bank_name") and payer.get("account_number")),
    }


@router.get("/runs/{run_id}/bank-file")
async def download_bank_file(
    run_id: str,
    fmt: str = Query("csv", pattern="^(csv|txt)$"),
    ctx: AuthContext = Depends(require_permission("payroll", "export")),
):
    """File transfer massal (CSV koma / TXT pipa) siap diunggah ke internet banking."""
    db = get_db()
    run = await _run_ready_for_disbursement(ctx.company_id, run_id)
    items = await db.payroll_items.find(
        {"company_id": ctx.company_id, "run_id": run_id}, NO_ID
    ).sort("full_name", 1).to_list(5000)
    payer = await _company_payer(ctx.company_id)
    note = (payer["note_template"] or "Gaji {periode}").replace(
        "{periode}", run.get("period_label") or ""
    )[:60]

    rows = [["No", "Nama Karyawan", "NIK Karyawan", "Bank", "Nomor Rekening",
             "Nominal", "Berita Transfer"]]
    counter = 0
    total = 0.0
    for it in items:
        account = (it.get("bank_account_number") or "").strip()
        if not account:
            continue
        counter += 1
        amount = float((it.get("totals") or {}).get("net_pay") or 0)
        total += amount
        rows.append([
            str(counter),
            it.get("full_name") or "",
            it.get("employee_number") or "",
            it.get("bank_name") or "",
            account,
            f"{int(round(amount))}",
            note,
        ])
    if counter == 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Tidak ada karyawan dengan nomor rekening pada periode ini. "
            "Lengkapi nomor rekening di data karyawan terlebih dahulu.",
        )

    buf = io.StringIO()
    if fmt == "txt":
        for row in rows:
            buf.write("|".join(row) + "\r\n")
        media = "text/plain; charset=utf-8"
        ext = "txt"
    else:
        writer = csv.writer(buf, delimiter=",", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
        writer.writerows(rows)
        media = "text/csv; charset=utf-8"
        ext = "csv"

    await log_action(ctx, "export", "payroll", run_id,
                     f"File transfer bank {run.get('period_label')}",
                     notes=f"{counter} penerima, total {int(round(total))}")
    period = (run.get("period_label") or "").replace(" ", "-")
    content = "\ufeff" + buf.getvalue()
    return Response(
        content=content.encode("utf-8"),
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="Transfer-Bank-{period}.{ext}"',
            "Cache-Control": "no-store",
        },
    )


def _statutory_rows(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for it in items:
        b = it.get("bpjs") or {}
        tax = it.get("tax") or {}
        totals = it.get("totals") or {}

        def part(key: str, side: str) -> float:
            return float(((b.get(key) or {}).get(side)) or 0)

        rows.append({
            "item_id": it.get("id"),
            "employee_id": it.get("employee_id"),
            "full_name": it.get("full_name"),
            "employee_number": it.get("employee_number"),
            "job_title": it.get("job_title"),
            "basic_salary": float(it.get("basic_salary") or 0),
            "gross": float(totals.get("gross") or 0),
            "kes_employee": part("kesehatan", "employee"),
            "kes_employer": part("kesehatan", "employer"),
            "jht_employee": part("jht", "employee"),
            "jht_employer": part("jht", "employer"),
            "jp_employee": part("jp", "employee"),
            "jp_employer": part("jp", "employer"),
            "jkk_employer": part("jkk", "employer"),
            "jkm_employer": part("jkm", "employer"),
            "bpjs_employee_total": float(totals.get("bpjs_employee") or 0),
            "bpjs_employer_total": float(totals.get("bpjs_employer") or 0),
            "ptkp_status": tax.get("ptkp_status"),
            "ter_category": tax.get("ter_category"),
            "ter_rate_percent": tax.get("ter_rate_percent"),
            "tax_method": tax.get("method_label"),
            "taxable_gross": float(tax.get("taxable_gross") or 0),
            "has_npwp": bool(tax.get("has_npwp")),
            "pph21": float(totals.get("pph21") or 0),
            "net_pay": float(totals.get("net_pay") or 0),
        })
    return rows


SUM_FIELDS = ["gross", "kes_employee", "kes_employer", "jht_employee", "jht_employer",
              "jp_employee", "jp_employer", "jkk_employer", "jkm_employer",
              "bpjs_employee_total", "bpjs_employer_total", "taxable_gross", "pph21",
              "net_pay"]


@router.get("/runs/{run_id}/statutory-report")
async def statutory_report(
    run_id: str,
    ctx: AuthContext = Depends(require_permission("payroll", "view")),
):
    """Rekap iuran BPJS dan PPh 21 per karyawan untuk pelaporan bulanan."""
    db = get_db()
    run = await _run_or_404(ctx.company_id, run_id)
    items = await db.payroll_items.find(
        {"company_id": ctx.company_id, "run_id": run_id}, NO_ID
    ).sort("full_name", 1).to_list(5000)
    rows = _statutory_rows(items)
    totals = {f: round(sum(r[f] for r in rows), 2) for f in SUM_FIELDS}
    return {
        "run": {"id": run["id"], "period_label": run.get("period_label"),
                "run_status": run.get("run_status"),
                "status_label": RUN_STATUS_LABELS.get(run.get("run_status")),
                "payment_date": run.get("payment_date")},
        "statutory": run.get("statutory_snapshot") or {},
        "rows": rows,
        "totals": totals,
        "employee_count": len(rows),
    }


@router.get("/runs/{run_id}/statutory-report/export")
async def export_statutory_report(
    run_id: str,
    ctx: AuthContext = Depends(require_permission("payroll", "export")),
):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    db = get_db()
    run = await _run_or_404(ctx.company_id, run_id)
    items = await db.payroll_items.find(
        {"company_id": ctx.company_id, "run_id": run_id}, NO_ID
    ).sort("full_name", 1).to_list(5000)
    rows = _statutory_rows(items)

    headers = [
        ("No", None), ("Nama Karyawan", "full_name"), ("NIK Karyawan", "employee_number"),
        ("Jabatan", "job_title"), ("Gaji Pokok", "basic_salary"), ("Bruto", "gross"),
        ("BPJS Kes (Pekerja)", "kes_employee"), ("BPJS Kes (Perusahaan)", "kes_employer"),
        ("JHT (Pekerja)", "jht_employee"), ("JHT (Perusahaan)", "jht_employer"),
        ("JP (Pekerja)", "jp_employee"), ("JP (Perusahaan)", "jp_employer"),
        ("JKK (Perusahaan)", "jkk_employer"), ("JKM (Perusahaan)", "jkm_employer"),
        ("Total BPJS Pekerja", "bpjs_employee_total"),
        ("Total BPJS Perusahaan", "bpjs_employer_total"),
        ("Status PTKP", "ptkp_status"), ("Kategori TER", "ter_category"),
        ("Tarif TER (%)", "ter_rate_percent"), ("Metode Pajak", "tax_method"),
        ("Bruto Kena Pajak", "taxable_gross"), ("PPh 21", "pph21"),
        ("Take Home Pay", "net_pay"),
    ]

    wb = Workbook()
    ws = wb.active
    ws.title = "Rekap BPJS & PPh 21"
    ws["A1"] = f"Rekap BPJS & PPh 21 — {run.get('period_label')}"
    ws["A1"].font = Font(bold=True, size=12)
    head_row = 3
    fill = PatternFill("solid", fgColor="0F5C4F")
    for col, (label, _key) in enumerate(headers, start=1):
        cell = ws.cell(row=head_row, column=col, value=label)
        cell.font = Font(bold=True, color="FFFFFF", size=10)
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[cell.column_letter].width = max(12, min(26, len(label) + 4))
    for idx, row in enumerate(rows, start=1):
        for col, (_label, key) in enumerate(headers, start=1):
            ws.cell(row=head_row + idx, column=col,
                    value=idx if key is None else row.get(key))
    total_row = head_row + len(rows) + 1
    ws.cell(row=total_row, column=2, value="TOTAL").font = Font(bold=True)
    for col, (_label, key) in enumerate(headers, start=1):
        if key in SUM_FIELDS:
            cell = ws.cell(row=total_row, column=col,
                           value=round(sum(r[key] for r in rows), 2))
            cell.font = Font(bold=True)
    ws.freeze_panes = f"A{head_row + 1}"

    buf = BytesIO()
    wb.save(buf)
    await log_action(ctx, "export", "payroll", run_id,
                     f"Rekap BPJS & PPh 21 {run.get('period_label')}")
    period = (run.get("period_label") or "").replace(" ", "-")
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="Rekap-BPJS-PPh21-{period}.xlsx"',
            "Cache-Control": "no-store",
        },
    )


def _payslip_email_html(item: Dict[str, Any], company: Dict[str, Any]) -> str:
    totals = item.get("totals") or {}
    period = (item.get("period") or {}).get("label", "")
    return f"""
    <div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#1f2937">
      <p>Yang terhormat <strong>{item.get('full_name', '')}</strong>,</p>
      <p>Berikut kami sampaikan slip gaji Anda untuk periode <strong>{period}</strong>
      pada {company.get('name', 'perusahaan')}. Rincian lengkap terlampir dalam berkas PDF.</p>
      <table cellpadding="6" style="border-collapse:collapse;margin:12px 0">
        <tr><td style="color:#6b7280">Penghasilan bruto</td>
            <td align="right"><strong>Rp {int(round(float(totals.get('gross') or 0))):,}</strong></td></tr>
        <tr><td style="color:#6b7280">Total potongan</td>
            <td align="right">Rp {int(round(float(totals.get('total_deductions') or 0))):,}</td></tr>
        <tr><td style="color:#6b7280">Take home pay</td>
            <td align="right"><strong>Rp {int(round(float(totals.get('net_pay') or 0))):,}</strong></td></tr>
      </table>
      <p style="color:#6b7280;font-size:12px">Email ini dikirim otomatis oleh sistem HRIS.
      Mohon tidak membalas email ini. Bila ada pertanyaan, hubungi bagian HR.</p>
    </div>
    """.replace(",", ".")


async def _send_payslips(
    cid: str,
    run_id: str,
    item_ids: Optional[List[str]],
    user_id: Optional[str],
    trigger: str,
) -> Dict[str, Any]:
    """Kirim slip gaji PDF ke email masing-masing karyawan."""
    db = get_db()
    run = await db.payroll_runs.find_one({"company_id": cid, "id": run_id}, NO_ID)
    if not run:
        return {"sent": 0, "failed": 0, "skipped": 0, "message": "Payroll tidak ditemukan."}
    smtp = await db.smtp_settings.find_one({"company_id": cid}, NO_ID) or {}
    if not smtp.get("host"):
        raise MailerError("Server SMTP belum dikonfigurasi di menu Email & Pengingat.")

    query: Dict[str, Any] = {"company_id": cid, "run_id": run_id}
    if item_ids:
        query["id"] = {"$in": item_ids}
    items = await db.payroll_items.find(query, NO_ID).sort("full_name", 1).to_list(5000)
    company = await db.companies.find_one({"id": cid}, NO_ID) or {}
    emails = {
        e["id"]: (e.get("email") or "").strip()
        for e in await db.employees.find({"company_id": cid}, NO_ID).to_list(5000)
    }
    generated = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    period = (run.get("period_label") or "").replace(" ", "-")

    sent, failed, results = 0, 0, []
    for item in items:
        email = emails.get(item.get("employee_id")) or ""
        entry = {"item_id": item.get("id"), "full_name": item.get("full_name"), "email": email}
        if not email:
            failed += 1
            entry["status"] = "failed"
            entry["error"] = "Karyawan belum memiliki alamat email."
        else:
            try:
                pdf = build_payslip_pdf(item, company, generated_at=generated)
                filename = f"Slip-Gaji-{(item.get('full_name') or '').replace(' ', '-')}-{period}.pdf"
                await asyncio.to_thread(
                    send_email,
                    smtp,
                    [email],
                    f"Slip Gaji {run.get('period_label')} — {company.get('name', '')}".strip(),
                    _payslip_email_html(item, company),
                    None,
                    None,
                    [{"filename": filename, "content": pdf, "mime": "application/pdf"}],
                )
                sent += 1
                entry["status"] = "sent"
            except Exception as exc:  # noqa: BLE001
                failed += 1
                entry["status"] = "failed"
                entry["error"] = str(exc)
        await db.payroll_items.update_one(
            {"company_id": cid, "id": item.get("id")},
            {"$set": {
                "payslip_email_status": entry["status"],
                "payslip_email_at": now(),
                "payslip_email_to": email or None,
                "payslip_email_error": entry.get("error"),
            }},
        )
        results.append(entry)

    summary = f"{sent} slip gaji terkirim, {failed} gagal."
    await db.payslip_email_logs.insert_one({
        "id": new_id(),
        "company_id": cid,
        "run_id": run_id,
        "period_label": run.get("period_label"),
        "trigger": trigger,
        "sent_count": sent,
        "failed_count": failed,
        "summary": summary,
        "status": "sent" if sent and not failed else ("failed" if not sent else "partial"),
        "created_at": now(),
        "created_by": user_id,
    })
    logger.info("Kirim slip gaji %s (%s): %s", run.get("period_label"), trigger, summary)
    return {"sent": sent, "failed": failed, "summary": summary, "results": results}


@router.post("/runs/{run_id}/send-payslips")
async def send_payslips(
    run_id: str,
    payload: Optional[PayslipEmailRequest] = None,
    ctx: AuthContext = Depends(require_permission("payroll", "edit")),
):
    run = await _run_or_404(ctx.company_id, run_id)
    if run.get("run_status") not in PAID_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Slip gaji hanya boleh dikirim setelah payroll disetujui.",
        )
    try:
        result = await _send_payslips(
            ctx.company_id, run_id,
            (payload.item_ids if payload else None),
            ctx.user_id, "manual",
        )
    except MailerError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await log_action(ctx, "export", "payroll", run_id,
                     f"Kirim slip gaji {run.get('period_label')}",
                     notes=result.get("summary"))
    return result


@router.get("/runs/{run_id}/payslip-email-logs")
async def payslip_email_logs(
    run_id: str,
    ctx: AuthContext = Depends(require_permission("payroll", "view")),
):
    db = get_db()
    await _run_or_404(ctx.company_id, run_id)
    logs = await db.payslip_email_logs.find(
        {"company_id": ctx.company_id, "run_id": run_id}, NO_ID
    ).sort("created_at", -1).to_list(50)
    return {"items": serialize_list(logs), "total": len(logs)}


@router.get("/runs/{run_id}/export")
async def export_run(
    run_id: str,
    ctx: AuthContext = Depends(require_permission("payroll", "export")),
):
    """Ekspor rekap payroll ke Excel (untuk transfer bank / arsip Finance)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    db = get_db()
    run = await _run_or_404(ctx.company_id, run_id)
    items = await db.payroll_items.find(
        {"company_id": ctx.company_id, "run_id": run_id}, NO_ID
    ).sort("full_name", 1).to_list(5000)

    wb = Workbook()
    ws = wb.active
    ws.title = "Rekap Payroll"
    headers = [
        "NIK", "Nama Karyawan", "Jabatan", "Status PTKP", "Kategori TER", "Tarif TER (%)",
        "Hari Kerja", "Tidak Hadir", "Jam Lembur", "Gaji Pokok", "Total Bruto",
        "Bruto Kena Pajak", "BPJS Kesehatan", "BPJS JHT", "BPJS JP", "PPh 21",
        "Potongan Lain", "Total Potongan", "Gaji Bersih", "Bank", "No. Rekening",
    ]
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=i, value=h)
        c.font = Font(bold=True, color="FFFFFF", size=10)
        c.fill = PatternFill("solid", fgColor="0F5C4F")
        c.alignment = Alignment(horizontal="center", wrap_text=True)
        ws.column_dimensions[chr(64 + i) if i <= 26 else "A"].width = 18
    ws.freeze_panes = "A2"

    for row, it in enumerate(items, start=2):
        t = it.get("totals") or {}
        tax = it.get("tax") or {}
        bp = it.get("bpjs") or {}
        att = it.get("attendance") or {}
        values = [
            it.get("employee_number"), it.get("full_name"), it.get("job_title"),
            tax.get("ptkp_status"), tax.get("ter_category"), tax.get("ter_rate_percent"),
            att.get("working_days"), att.get("unpaid_days"), att.get("overtime_hours"),
            it.get("basic_salary"), t.get("gross"), t.get("taxable_gross"),
            (bp.get("kesehatan") or {}).get("employee"), (bp.get("jht") or {}).get("employee"),
            (bp.get("jp") or {}).get("employee"), t.get("pph21"),
            t.get("other_deductions"), t.get("total_deductions"), t.get("net_pay"),
            it.get("bank_name"), it.get("bank_account_number"),
        ]
        for i, v in enumerate(values, start=1):
            ws.cell(row=row, column=i, value=v)

    total_row = len(items) + 2
    ws.cell(row=total_row, column=2, value="TOTAL").font = Font(bold=True)
    for col, key in [(11, "gross"), (16, "pph21"), (18, "total_deductions"), (19, "net_pay")]:
        c = ws.cell(row=total_row, column=col, value=(run.get("totals") or {}).get(key))
        c.font = Font(bold=True)

    buf = BytesIO()
    wb.save(buf)
    await log_action(ctx, "export", "payroll", run_id, f"Ekspor payroll {run['period_label']}")
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition":
                f'attachment; filename="Payroll-{run["period_label"].replace(" ", "-")}.xlsx"'
        },
    )


# ==========================================================================
# Self-service karyawan — hanya slip gaji milik sendiri
# ==========================================================================
@router.get("/my/payslips")
async def my_payslips(ctx: AuthContext = Depends(get_auth)):
    """Slip gaji milik pengguna yang login. Hanya periode yang sudah disetujui."""
    if not ctx.has_module("payroll"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Modul Payroll belum diaktifkan untuk perusahaan ini.",
        )
    db = get_db()
    cid = ctx.company_id
    emp = await resolve_own_employee(cid, ctx.user)
    if not emp:
        return {
            "items": [],
            "total": 0,
            "employee": None,
            "message": "Akun Anda belum tertaut ke data karyawan. Hubungi HR untuk menautkannya.",
        }

    runs = {
        r["id"]: r
        for r in await db.payroll_runs.find(
            {"company_id": cid, "run_status": {"$in": ["approved", "paid"]},
             "status": {"$ne": "deleted"}},
            NO_ID,
        ).to_list(300)
    }
    if not runs:
        return {"items": [], "total": 0,
                "employee": {"id": emp["id"], "full_name": emp.get("full_name"),
                             "employee_number": emp.get("employee_number")},
                "message": "Belum ada slip gaji yang diterbitkan."}

    items = await db.payroll_items.find(
        {"company_id": cid, "employee_id": emp["id"], "run_id": {"$in": list(runs)}}, NO_ID
    ).to_list(300)
    items.sort(
        key=lambda i: ((i.get("period") or {}).get("year", 0), (i.get("period") or {}).get("month", 0)),
        reverse=True,
    )
    for i in items:
        run = runs.get(i["run_id"]) or {}
        i["run_status"] = run.get("run_status")
        i["run_status_label"] = RUN_STATUS_LABELS.get(run.get("run_status"))
        i["payment_date"] = run.get("payment_date")

    return {
        "items": serialize_list(items),
        "total": len(items),
        "employee": {"id": emp["id"], "full_name": emp.get("full_name"),
                     "employee_number": emp.get("employee_number"),
                     "job_title": emp.get("job_title")},
        "message": None if items else "Belum ada slip gaji untuk Anda.",
    }


@router.get("/my/payslips/{item_id}/payslip")
async def my_payslip_pdf(item_id: str, ctx: AuthContext = Depends(get_auth)):
    if not ctx.has_module("payroll"):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Modul Payroll belum diaktifkan untuk perusahaan ini.")
    db = get_db()
    cid = ctx.company_id
    emp = await resolve_own_employee(cid, ctx.user)
    if not emp:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Akun Anda belum tertaut ke data karyawan.")
    item = await db.payroll_items.find_one(
        {"company_id": cid, "id": item_id, "employee_id": emp["id"]}, NO_ID
    )
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Slip gaji tidak ditemukan.")
    run = await db.payroll_runs.find_one(
        {"company_id": cid, "id": item["run_id"], "run_status": {"$in": ["approved", "paid"]}},
        NO_ID,
    )
    if not run:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Slip gaji periode ini belum diterbitkan (menunggu persetujuan).",
        )
    return await _payslip_pdf_response(cid, item)


# ==========================================================================
# Ringkasan untuk dashboard
# ==========================================================================
@router.get("/summary")
async def summary(ctx: AuthContext = Depends(require_permission("payroll", "view"))):
    db = get_db()
    cid = ctx.company_id
    latest = await db.payroll_runs.find(
        {"company_id": cid, "status": {"$ne": "deleted"}}, NO_ID
    ).sort([("year", -1), ("month", -1)]).to_list(1)
    pending = await db.payroll_runs.count_documents(
        {"company_id": cid, "run_status": "pending_approval", "status": {"$ne": "deleted"}}
    )
    employees = await db.employees.count_documents({"company_id": cid, "status": "active"})
    with_salary = await db.employee_salaries.count_documents(
        {"company_id": cid, "basic_salary": {"$gt": 0}, "status": {"$ne": "deleted"}}
    )
    run = latest[0] if latest else None
    return {
        "latest_run": {**run, "status_label": RUN_STATUS_LABELS.get(run.get("run_status"))}
        if run else None,
        "pending_approval_count": pending,
        "active_employees": employees,
        "employees_with_salary": with_salary,
        "employees_without_salary": max(0, employees - with_salary),
        "setup_complete": employees > 0 and with_salary >= employees,
    }
