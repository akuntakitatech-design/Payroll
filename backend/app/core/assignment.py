"""Upgrade 01D - Current Assignment / Penempatan Karyawan (helper bersama).

Aturan:
- satu karyawan = satu profil permanen; penempatan = riwayat di `employee_assignments`;
- maksimal SATU assignment ACTIVE per karyawan (dijaga di backend, dengan row-lock karyawan);
- field legacy `employees.project_id` (+ field organisasi) TETAP dan disinkronkan dari assignment aktif;
- Standby BUKAN jenis assignment (itu Status Karyawan 01B).
"""
from typing import Any, Dict, Optional

from fastapi import HTTPException, status

from .db import NO_ID, audit_fields, new_id
from .tenancy import get_tenant_db

TABLE = "employee_assignments"
ACTIVE, ENDED = "ACTIVE", "ENDED"
# field penempatan (semuanya FK master existing, tenant-scoped)
PLACEMENT_FIELDS: Dict[str, tuple] = {
    "project_id": ("projects", "Proyek"),
    "work_location_id": ("work_locations", "Lokasi kerja / site"),
    "branch_id": ("branches", "Cabang"),
    "department_id": ("departments", "Departemen"),
    "division_id": ("divisions", "Divisi"),
    "position_id": ("positions", "Jabatan"),
    "cost_center_id": ("cost_centers", "Cost center"),
}
# field organisasi (selain project) yang dicerminkan ke assignment aktif saat Edit Karyawan
MIRROR_FIELDS = tuple(f for f in PLACEMENT_FIELDS if f != "project_id")


def _unprocessable(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, msg)


async def validate_placement(company_id: str, data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Semua referensi wajib milik tenant aktif (anti manipulasi API). Return {field: row}."""
    db = get_tenant_db(company_id)
    rows: Dict[str, Dict[str, Any]] = {}
    for field, (coll, label) in PLACEMENT_FIELDS.items():
        value = data.get(field)
        if not value:
            continue
        row = await db[coll].find_one({"company_id": company_id, "id": value, "status": {"$ne": "deleted"}}, NO_ID)
        if not row:
            raise _unprocessable(f"{label} yang dipilih tidak ditemukan pada perusahaan aktif Anda.")
        rows[field] = row
    proj = rows.get("project_id")
    # kombinasi project <-> site: bila project punya lokasi kerja tetap, site harus sama
    if proj and proj.get("work_location_id") and data.get("work_location_id") \
            and data["work_location_id"] != proj["work_location_id"]:
        raise _unprocessable("Lokasi kerja / site tidak sesuai dengan lokasi yang ditetapkan pada project terpilih.")
    div = rows.get("division_id")
    if div and div.get("department_id") and data.get("department_id") and div["department_id"] != data["department_id"]:
        raise _unprocessable("Divisi yang dipilih bukan bagian dari departemen terpilih.")
    return rows


def new_assignment_doc(company_id: str, employee_id: str, data: Dict[str, Any], start_date: Optional[str],
                       source: str, reason: Optional[str], notes: Optional[str], user_id: Optional[str],
                       previous_assignment_id: Optional[str] = None) -> Dict[str, Any]:
    doc = {"id": new_id(), "company_id": company_id, "employee_id": employee_id, "status": "active",
           "assignment_status": ACTIVE, "start_date": start_date, "end_date": None, "source": source,
           "reason": reason, "notes": notes, "previous_assignment_id": previous_assignment_id,
           **audit_fields(user_id)}
    for f in PLACEMENT_FIELDS:
        doc[f] = data.get(f) or None
    return doc


async def active_assignment(company_id: str, employee_id: str) -> Optional[Dict[str, Any]]:
    return await get_tenant_db(company_id)[TABLE].find_one(
        {"company_id": company_id, "employee_id": employee_id, "assignment_status": ACTIVE}, NO_ID)


async def create_initial_for_new_employee(company_id: str, employee: Dict[str, Any], source: str,
                                          user_id: Optional[str], today: str) -> Optional[str]:
    """Karyawan baru yang langsung punya project -> assignment ACTIVE pertama.
    Tanggal mulai = tanggal masuk bila tersedia dan tidak di masa depan, selain itu tanggal pencatatan (hari ini)."""
    if not employee.get("project_id"):
        return None
    join = employee.get("join_date")
    start = join if (join and join <= today) else today
    doc = new_assignment_doc(company_id, employee["id"], employee, start, source,
                             "Penempatan awal saat data karyawan dibuat", None, user_id)
    await get_tenant_db(company_id)[TABLE].insert_one(doc)
    return doc["id"]
