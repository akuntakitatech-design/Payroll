"""Jembatan antara mesin payroll (murni) dan database.

Mesin perhitungan ada di `app/core/payroll.py` dan sengaja tidak menyentuh
MongoDB agar mudah diuji. Modul ini yang membaca master data, struktur gaji
karyawan dan parameter statutori perusahaan lalu menyusun input mesin.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .db import NO_ID, get_db
from .payroll import ComponentInput, EmployeeInput, StatutoryConfig

STATUTORY_SETTINGS_KEY = "payroll_statutory"

RUN_STATUSES = ["draft", "pending_approval", "approved", "rejected", "paid"]
RUN_STATUS_LABELS = {
    "draft": "Draf",
    "pending_approval": "Menunggu Persetujuan",
    "approved": "Disetujui",
    "rejected": "Ditolak",
    "paid": "Sudah Dibayar",
}


async def get_statutory_config(company_id: str) -> StatutoryConfig:
    """Parameter BPJS/pajak perusahaan (default = ketentuan 2026 bila belum diatur)."""
    db = get_db()
    settings = await db.company_settings.find_one({"company_id": company_id}, NO_ID) or {}
    return StatutoryConfig.from_dict(settings.get(STATUTORY_SETTINGS_KEY) or {})


async def save_statutory_config(company_id: str, payload: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    from .db import audit_fields

    db = get_db()
    current = await get_statutory_config(company_id)
    merged = {**current.to_dict(), **{k: v for k, v in (payload or {}).items() if v is not None}}
    merged.pop("jkk_employer_rate", None)  # turunan, bukan input
    cfg = StatutoryConfig.from_dict(merged)
    await db.company_settings.update_one(
        {"company_id": company_id},
        {"$set": {STATUTORY_SETTINGS_KEY: cfg.to_dict(), **audit_fields(user_id, creating=False)}},
        upsert=True,
    )
    return cfg.to_dict()


async def load_components(company_id: str) -> Dict[str, Dict[str, Any]]:
    db = get_db()
    rows = await db.payroll_components.find(
        {"company_id": company_id, "status": "active"}, NO_ID
    ).sort("sort_order", 1).to_list(500)
    return {r["id"]: r for r in rows}


def _components_for(
    salary: Dict[str, Any],
    catalog: Dict[str, Dict[str, Any]],
    extra_earnings: Optional[List[Dict[str, Any]]] = None,
    extra_deductions: Optional[List[Dict[str, Any]]] = None,
) -> List[ComponentInput]:
    """Susun komponen tetap karyawan + penyesuaian ad-hoc periode ini."""
    out: List[ComponentInput] = []

    for entry in salary.get("components") or []:
        master = catalog.get(entry.get("component_id"))
        if not master:
            continue
        amount = entry.get("amount")
        if amount is None:
            amount = master.get("default_amount") or 0
        if master.get("calc") == "percent_of_basic":
            amount = float(salary.get("basic_salary") or 0) * float(master.get("percent") or 0) / 100.0
        out.append(
            ComponentInput(
                code=master.get("code") or master["id"][:8],
                name=master.get("name") or "Komponen",
                kind=master.get("kind") or "earning",
                amount=float(amount or 0),
                taxable=bool(master.get("taxable", True)),
                prorate=bool(master.get("prorate", False)),
                include_in_bpjs_base=bool(master.get("include_in_bpjs_base", False)),
            )
        )

    for item in extra_earnings or []:
        out.append(
            ComponentInput(
                code=(item.get("code") or "ADHOC_E").upper()[:20],
                name=item.get("name") or "Tambahan",
                kind="earning",
                amount=float(item.get("amount") or 0),
                taxable=bool(item.get("taxable", True)),
                prorate=False,
                include_in_bpjs_base=False,
            )
        )
    for item in extra_deductions or []:
        out.append(
            ComponentInput(
                code=(item.get("code") or "ADHOC_D").upper()[:20],
                name=item.get("name") or "Potongan",
                kind="deduction",
                amount=float(item.get("amount") or 0),
                taxable=False,
                prorate=False,
            )
        )
    return out


DEFAULT_SALARY = {
    "basic_salary": 0.0,
    "ptkp_status": "TK/0",
    "has_npwp": False,
    "bpjs_kesehatan_enrolled": True,
    "bpjs_jht_enrolled": True,
    "bpjs_jp_enrolled": True,
    "components": [],
}


async def load_salaries(company_id: str, employee_ids: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
    db = get_db()
    query: Dict[str, Any] = {"company_id": company_id, "status": {"$ne": "deleted"}}
    if employee_ids is not None:
        query["employee_id"] = {"$in": employee_ids}
    rows = await db.employee_salaries.find(query, NO_ID).to_list(5000)
    return {r["employee_id"]: r for r in rows}


async def fallback_basic_salary(company_id: str, employee_id: str) -> float:
    """Bila struktur gaji belum diisi, pakai gaji pokok dari kontrak aktif terakhir."""
    db = get_db()
    contract = await db.employee_contracts.find(
        {
            "company_id": company_id,
            "employee_id": employee_id,
            "status": {"$ne": "deleted"},
            "basic_salary": {"$gt": 0},
        },
        NO_ID,
    ).sort("start_date", -1).to_list(1)
    return float(contract[0].get("basic_salary") or 0) if contract else 0.0


async def build_employee_input(
    company_id: str,
    employee: Dict[str, Any],
    salary: Optional[Dict[str, Any]],
    catalog: Dict[str, Dict[str, Any]],
    adjustments: Optional[Dict[str, Any]] = None,
) -> EmployeeInput:
    adjustments = adjustments or {}
    sal = {**DEFAULT_SALARY, **(salary or {})}

    basic = float(sal.get("basic_salary") or 0)
    if basic <= 0:
        basic = await fallback_basic_salary(company_id, employee["id"])

    has_npwp = sal.get("has_npwp")
    if has_npwp is None:
        has_npwp = bool((employee.get("npwp") or "").strip())

    return EmployeeInput(
        employee_id=employee["id"],
        full_name=employee.get("full_name") or "-",
        employee_number=employee.get("employee_number"),
        basic_salary=basic,
        ptkp_status=sal.get("ptkp_status") or "TK/0",
        has_npwp=bool(has_npwp),
        join_date=employee.get("join_date"),
        job_title=employee.get("job_title"),
        bank_name=employee.get("bank_name"),
        bank_account_number=employee.get("bank_account_number"),
        components=_components_for(
            sal, catalog,
            adjustments.get("extra_earnings"),
            adjustments.get("extra_deductions"),
        ),
        working_days=adjustments.get("working_days"),
        unpaid_days=float(adjustments.get("unpaid_days") or 0),
        overtime_hours=float(adjustments.get("overtime_hours") or 0),
        bpjs_kesehatan_enrolled=bool(sal.get("bpjs_kesehatan_enrolled", True)),
        bpjs_jht_enrolled=bool(sal.get("bpjs_jht_enrolled", True)),
        bpjs_jp_enrolled=bool(sal.get("bpjs_jp_enrolled", True)),
    )


async def ytd_accumulation(company_id: str, employee_id: str, year: int, upto_month: int) -> Dict[str, float]:
    """Akumulasi bruto kena pajak, PPh 21 terpotong dan JHT+JP Jan s.d. bulan tertentu.

    Hanya menghitung payroll run yang sudah disetujui/dibayar agar rekonsiliasi
    Desember memakai angka yang benar-benar sudah dipotong.
    """
    db = get_db()
    runs = await db.payroll_runs.find(
        {
            "company_id": company_id,
            "year": year,
            "month": {"$lte": upto_month},
            "status": {"$in": ["approved", "paid"]},
        },
        NO_ID,
    ).to_list(24)
    run_ids = [r["id"] for r in runs]
    if not run_ids:
        return {"taxable_gross": 0.0, "pph21": 0.0, "jht_jp": 0.0, "months": 0}

    items = await db.payroll_items.find(
        {"company_id": company_id, "run_id": {"$in": run_ids}, "employee_id": employee_id},
        NO_ID,
    ).to_list(24)
    return {
        "taxable_gross": float(sum((i.get("tax") or {}).get("taxable_gross") or 0 for i in items)),
        "pph21": float(sum((i.get("totals") or {}).get("pph21") or 0 for i in items)),
        "jht_jp": float(sum(i.get("jht_jp_employee") or 0 for i in items)),
        "months": len(items),
    }


async def resolve_own_employee(company_id: str, user: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Cari data karyawan milik pengguna yang login (untuk self-service slip gaji)."""
    db = get_db()
    emp = await db.employees.find_one(
        {"company_id": company_id, "user_id": user["id"], "status": {"$ne": "deleted"}}, NO_ID
    )
    if emp:
        return emp
    email = (user.get("email") or "").strip().lower()
    if not email:
        return None
    return await db.employees.find_one(
        {"company_id": company_id, "email": email, "status": {"$ne": "deleted"}}, NO_ID
    )
