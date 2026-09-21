"""Penomoran karyawan (employee_number) — helper bersama.

Dipindahkan apa adanya dari routers/employees.py agar dapat dipakai modul lain
(mis. Rekrutmen Tahap C: konversi kandidat -> karyawan) tanpa membuat generator
nomor kedua. Perilaku tidak berubah:
  - counter `company_settings.employee_id_next_number` dinaikkan secara atomik,
  - prefix dari `company_settings.employee_id_prefix`, fallback kode perusahaan / "EMP",
  - slot yang sudah dipakai nomor manual dilewati.
"""
from typing import Optional

from .db import NO_ID, ReturnDocument
from .tenancy import get_tenant_db


async def next_employee_number(company_id: str, code: Optional[str]) -> str:
    db = get_tenant_db(company_id)  # tenant-scoped
    doc = await db.company_settings.find_one_and_update(
        {"company_id": company_id},
        {"$inc": {"employee_id_next_number": 1}},
        projection=NO_ID,
        return_document=ReturnDocument.BEFORE,
    )
    prefix = (doc or {}).get("employee_id_prefix") or code or "EMP"
    number = int((doc or {}).get("employee_id_next_number") or 1)
    candidate = f"{prefix}-{number:04d}"
    # Guard against manual numbers already using the slot
    while await db.employees.count_documents(
        {"company_id": company_id, "employee_number": candidate, "status": {"$ne": "deleted"}}
    ):
        number += 1
        candidate = f"{prefix}-{number:04d}"
    return candidate
