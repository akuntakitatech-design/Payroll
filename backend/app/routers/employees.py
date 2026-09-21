"""Modul Data Karyawan (employee_core).

Data induk karyawan lengkap dengan penempatan organisasi, kontrak kerja,
sertifikasi dan dokumen. Semua query lewat TenantRepository sehingga tidak bisa
menembus batas perusahaan.
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from ..core.db import ASCENDING, ReturnDocument

from ..core.audit import log_action
from ..core.db import NO_ID, serialize, serialize_list
from ..core.deps import AuthContext, get_auth, require_permission
from ..core.employee_numbering import next_employee_number
from ..core.expiry import expiry_state
from ..core.policy import resolve_config
from ..core.repo import TenantRepository
from ..core.tenancy import get_tenant_db
from ..schemas import (
    EmployeeCreate,
    EmployeeImportCommit,
    EmployeeUpdate,
    StatusChange,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/employees", tags=["Karyawan"])

# FK field -> (collection, label)
REF_FIELDS: Dict[str, tuple] = {
    "employment_status_id": ("employment_statuses", "Status kepegawaian"),
    "branch_id": ("branches", "Cabang"),
    "work_location_id": ("work_locations", "Lokasi kerja"),
    "department_id": ("departments", "Departemen"),
    "division_id": ("divisions", "Divisi"),
    "position_id": ("positions", "Jabatan"),
    "job_grade_id": ("job_grades", "Grade / Level"),
    "cost_center_id": ("cost_centers", "Cost center"),
    "project_id": ("projects", "Proyek"),
}

GENDERS = [{"key": "male", "label": "Laki-laki"}, {"key": "female", "label": "Perempuan"}]
MARITAL_STATUSES = [
    {"key": "single", "label": "Belum menikah"},
    {"key": "married", "label": "Menikah"},
    {"key": "divorced", "label": "Duda / Janda"},
]
RELIGIONS = [
    {"key": "islam", "label": "Islam"},
    {"key": "kristen", "label": "Kristen"},
    {"key": "katolik", "label": "Katolik"},
    {"key": "hindu", "label": "Hindu"},
    {"key": "buddha", "label": "Buddha"},
    {"key": "konghucu", "label": "Konghucu"},
    {"key": "lainnya", "label": "Lainnya"},
]
EDUCATIONS = [
    {"key": "sd", "label": "SD"},
    {"key": "smp", "label": "SMP"},
    {"key": "sma", "label": "SMA / SMK"},
    {"key": "d3", "label": "Diploma (D3)"},
    {"key": "s1", "label": "Sarjana (S1)"},
    {"key": "s2", "label": "Magister (S2)"},
    {"key": "s3", "label": "Doktor (S3)"},
]

SEARCH_FIELDS = ["full_name", "employee_number", "nik", "email", "phone", "job_title"]


async def _validate_refs(company_id: str, data: Dict[str, Any]) -> None:
    db = get_tenant_db(company_id)  # tenant-scoped
    for field, (collection, label) in REF_FIELDS.items():
        value = data.get(field)
        if not value:
            continue
        exists = await db[collection].count_documents(
            {"company_id": company_id, "id": value, "status": {"$ne": "deleted"}}
        )
        if not exists:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"{label} yang dipilih tidak ditemukan pada perusahaan aktif Anda.",
            )


# Penomoran karyawan dipindahkan ke core/employee_numbering.py (dipakai juga oleh
# Rekrutmen Tahap C). Alias dipertahankan agar pemanggilan di router ini tidak berubah.
_next_employee_number = next_employee_number


async def _label_maps(company_id: str, items: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    db = get_tenant_db(company_id)  # tenant-scoped
    maps: Dict[str, Dict[str, str]] = {}
    for field, (collection, _label) in REF_FIELDS.items():
        ids = {i.get(field) for i in items if i.get(field)}
        if not ids:
            maps[field] = {}
            continue
        rows = await db[collection].find(
            {"company_id": company_id, "id": {"$in": list(ids)}}, NO_ID
        ).to_list(1000)
        maps[field] = {r["id"]: r.get("name") or r.get("code") for r in rows}
    return maps


async def _enrich(company_id: str, items: List[Dict[str, Any]], horizon_days: int) -> List[Dict[str, Any]]:
    if not items:
        return items
    db = get_tenant_db(company_id)  # tenant-scoped
    maps = await _label_maps(company_id, items)
    employee_ids = [i["id"] for i in items]
    contracts = serialize_list(
        await db.employee_contracts.find(
            {
                "company_id": company_id,
                "employee_id": {"$in": employee_ids},
                "status": {"$nin": ["deleted", "archived"]},
            },
            NO_ID,
        ).to_list(5000)
    )
    latest: Dict[str, Dict[str, Any]] = {}
    for c in contracts:
        current = latest.get(c["employee_id"])
        if not current or str(c.get("start_date") or "") > str(current.get("start_date") or ""):
            latest[c["employee_id"]] = c

    type_ids = {c.get("contract_type_id") for c in latest.values() if c.get("contract_type_id")}
    type_names = {
        t["id"]: t.get("name")
        for t in await db.contract_types.find(
            {"company_id": company_id, "id": {"$in": list(type_ids)}}, NO_ID
        ).to_list(500)
    }

    for item in items:
        for field in REF_FIELDS:
            item[f"{field[:-3]}_name"] = maps.get(field, {}).get(item.get(field))
        contract = latest.get(item["id"])
        if contract:
            state = expiry_state(contract.get("end_date"), horizon_days)
            item["active_contract"] = {
                "id": contract["id"],
                "contract_number": contract.get("contract_number"),
                "contract_type_name": type_names.get(contract.get("contract_type_id")),
                "start_date": contract.get("start_date"),
                "end_date": contract.get("end_date"),
                **state,
            }
        else:
            item["active_contract"] = None
    return items


@router.get("/catalog")
async def catalog(ctx: AuthContext = Depends(require_permission("employee", "view"))):
    """Semua pilihan dropdown yang dibutuhkan form karyawan - satu panggilan saja."""
    db = ctx.tdb  # tenant-scoped
    out: Dict[str, Any] = {
        "genders": GENDERS,
        "marital_statuses": MARITAL_STATUSES,
        "religions": RELIGIONS,
        "educations": EDUCATIONS,
    }
    for field, (collection, _label) in REF_FIELDS.items():
        rows = await db[collection].find(
            {"company_id": ctx.company_id, "status": "active"}, NO_ID
        ).sort("name", ASCENDING).to_list(1000)
        out[collection] = [
            {"id": r["id"], "name": r.get("name"), "code": r.get("code")} for r in rows
        ]
    for collection in ("contract_types", "certification_types", "document_types"):
        rows = await db[collection].find(
            {"company_id": ctx.company_id, "status": "active"}, NO_ID
        ).sort("name", ASCENDING).to_list(1000)
        out[collection] = [
            {
                "id": r["id"],
                "name": r.get("name"),
                "code": r.get("code"),
                "default_duration_months": r.get("default_duration_months"),
                "validity_months": r.get("validity_months"),
            }
            for r in rows
        ]
    return out


@router.get("/stats")
async def stats(ctx: AuthContext = Depends(require_permission("employee", "view"))):
    db = ctx.tdb  # tenant-scoped
    cid = ctx.company_id
    reminder = await resolve_config(cid, "contract.expiry_reminder_days")
    horizon = int(reminder.get("value") or 30)

    total = await db.employees.count_documents({"company_id": cid, "status": {"$ne": "deleted"}})
    active = await db.employees.count_documents({"company_id": cid, "status": "active"})
    contracts = serialize_list(
        await db.employee_contracts.find(
            {"company_id": cid, "status": {"$nin": ["deleted", "archived"]}}, NO_ID
        ).to_list(5000)
    )
    expiring = sum(1 for c in contracts if expiry_state(c.get("end_date"), horizon)["state"] == "due_soon")
    expired = sum(1 for c in contracts if expiry_state(c.get("end_date"), horizon)["state"] == "expired")
    certifications = serialize_list(
        await db.employee_certifications.find(
            {"company_id": cid, "status": {"$nin": ["deleted", "archived"]}}, NO_ID
        ).to_list(5000)
    )
    cert_expiring = sum(
        1 for c in certifications if expiry_state(c.get("expiry_date"), horizon)["state"] in ("due_soon", "expired")
    )
    without_contract = 0
    with_contract = {c["employee_id"] for c in contracts}
    active_ids = [
        e["id"]
        for e in await db.employees.find({"company_id": cid, "status": "active"}, NO_ID).to_list(5000)
    ]
    without_contract = len([i for i in active_ids if i not in with_contract])
    return {
        "total": total,
        "active": active,
        "inactive": total - active,
        "contracts": len(contracts),
        "contracts_expiring": expiring,
        "contracts_expired": expired,
        "certifications": len(certifications),
        "certifications_attention": cert_expiring,
        "without_contract": without_contract,
        "horizon_days": horizon,
    }


@router.get("")
async def list_employees(
    q: Optional[str] = None,
    department_id: Optional[str] = None,
    position_id: Optional[str] = None,
    branch_id: Optional[str] = None,
    project_id: Optional[str] = None,
    employment_status_id: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = 1,
    limit: int = 20,
    ctx: AuthContext = Depends(require_permission("employee", "view")),
):
    filters: Dict[str, Any] = {}
    for key, value in (
        ("department_id", department_id),
        ("position_id", position_id),
        ("branch_id", branch_id),
        ("project_id", project_id),
        ("employment_status_id", employment_status_id),
        ("status", status_filter),
    ):
        if value:
            filters[key] = value
    repo = TenantRepository("employees", ctx.company_id)
    result = await repo.list(
        q=q,
        search_fields=SEARCH_FIELDS,
        filters=filters,
        page=page,
        limit=limit,
        sort_by="full_name",
        sort_dir="asc",
    )
    reminder = await resolve_config(ctx.company_id, "contract.expiry_reminder_days")
    horizon = int(reminder.get("value") or 30)
    result["items"] = await _enrich(ctx.company_id, result["items"], horizon)
    return result


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_employee(
    payload: EmployeeCreate,
    ctx: AuthContext = Depends(require_permission("employee", "create")),
):
    data = payload.model_dump(exclude_none=True)
    await _validate_refs(ctx.company_id, data)
    repo = TenantRepository("employees", ctx.company_id)

    number = (data.get("employee_number") or "").strip()
    if number:
        await repo.ensure_unique("employee_number", number, label="NIK karyawan")
    else:
        number = await _next_employee_number(ctx.company_id, ctx.company.get("code"))
    data["employee_number"] = number
    if data.get("nik"):
        await repo.ensure_unique("nik", data["nik"], label="Nomor KTP")

    created = await repo.create(data, ctx.user_id)
    await log_action(ctx, "create", "employee", created["id"], created.get("full_name"), after=created)
    return created


@router.get("/{employee_id}")
async def get_employee(
    employee_id: str, ctx: AuthContext = Depends(require_permission("employee", "view"))
):
    db = ctx.tdb  # tenant-scoped
    cid = ctx.company_id
    repo = TenantRepository("employees", cid)
    employee = await repo.get(employee_id)
    reminder = await resolve_config(cid, "contract.expiry_reminder_days")
    horizon = int(reminder.get("value") or 30)
    enriched = (await _enrich(cid, [employee], horizon))[0]

    contracts = serialize_list(
        await db.employee_contracts.find(
            {"company_id": cid, "employee_id": employee_id, "status": {"$ne": "deleted"}}, NO_ID
        ).sort("start_date", -1).to_list(500)
    )
    ctype_names = {
        t["id"]: t.get("name")
        for t in await db.contract_types.find({"company_id": cid}, NO_ID).to_list(500)
    }
    for c in contracts:
        c["contract_type_name"] = ctype_names.get(c.get("contract_type_id"))
        c.update(expiry_state(c.get("end_date"), horizon))

    certifications = serialize_list(
        await db.employee_certifications.find(
            {"company_id": cid, "employee_id": employee_id, "status": {"$ne": "deleted"}}, NO_ID
        ).sort("expiry_date", 1).to_list(500)
    )
    cert_names = {
        t["id"]: t.get("name")
        for t in await db.certification_types.find({"company_id": cid}, NO_ID).to_list(500)
    }
    for c in certifications:
        c["certification_type_name"] = cert_names.get(c.get("certification_type_id"))
        c.update(expiry_state(c.get("expiry_date"), horizon))

    documents: List[Dict[str, Any]] = []
    if ctx.has_permission("document", "view"):
        documents = serialize_list(
            await db.documents.find(
                {
                    "company_id": cid,
                    "owner_type": "employee",
                    "owner_id": employee_id,
                    "is_deleted": {"$ne": True},
                },
                NO_ID,
            ).sort("created_at", -1).to_list(200)
        )
        doc_type_names = {
            t["id"]: t.get("name")
            for t in await db.document_types.find({"company_id": cid}, NO_ID).to_list(500)
        }
        for d in documents:
            d["document_type_name"] = doc_type_names.get(d.get("document_type_id"))
            d.update(expiry_state(d.get("expiry_date"), horizon))

    return {
        "employee": enriched,
        "contracts": contracts,
        "certifications": certifications,
        "documents": documents,
        "horizon_days": horizon,
    }


@router.put("/{employee_id}")
async def update_employee(
    employee_id: str,
    payload: EmployeeUpdate,
    ctx: AuthContext = Depends(require_permission("employee", "edit")),
):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tidak ada perubahan yang dikirim.")
    await _validate_refs(ctx.company_id, data)
    repo = TenantRepository("employees", ctx.company_id)
    await repo.get(employee_id)
    if data.get("employee_number"):
        await repo.ensure_unique(
            "employee_number", data["employee_number"], exclude_id=employee_id, label="NIK karyawan"
        )
    if data.get("nik"):
        await repo.ensure_unique("nik", data["nik"], exclude_id=employee_id, label="Nomor KTP")
    before, after = await repo.update(employee_id, data, ctx.user_id)
    await log_action(
        ctx, "update", "employee", employee_id, after.get("full_name"), before=before, after=after
    )
    return after


@router.patch("/{employee_id}/status")
async def change_status(
    employee_id: str,
    payload: StatusChange,
    ctx: AuthContext = Depends(require_permission("employee", "edit")),
):
    if payload.status not in ("active", "inactive", "archived"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Status karyawan hanya boleh: active, inactive, atau archived.",
        )
    repo = TenantRepository("employees", ctx.company_id)
    employee = await repo.get(employee_id)
    before, after = await repo.set_status(employee_id, payload.status, ctx.user_id)
    action = "activate" if payload.status == "active" else "deactivate"
    await log_action(
        ctx, action, "employee", employee_id, employee.get("full_name"), before=before, after=after
    )
    return after


@router.delete("/{employee_id}")
async def delete_employee(
    employee_id: str, ctx: AuthContext = Depends(require_permission("employee", "delete"))
):
    db = ctx.tdb  # tenant-scoped
    repo = TenantRepository("employees", ctx.company_id)
    employee = await repo.get(employee_id)
    contracts = await db.employee_contracts.count_documents(
        {"company_id": ctx.company_id, "employee_id": employee_id, "status": {"$ne": "deleted"}}
    )
    if contracts:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Karyawan ini masih memiliki {contracts} kontrak kerja. Nonaktifkan karyawan "
            "atau hapus kontraknya terlebih dahulu agar riwayat tetap konsisten.",
        )
    before, after = await repo.update(employee_id, {"status": "deleted"}, ctx.user_id)
    await log_action(
        ctx, "delete", "employee", employee_id, employee.get("full_name"), before=before, after=after
    )
    return {"message": f"Karyawan '{employee.get('full_name')}' berhasil dihapus."}


# ==========================================================================
# Impor massal dari Excel (template -> validasi -> commit)
# ==========================================================================
IMPORT_MASTER_COLLECTIONS = [
    "employment_statuses", "branches", "work_locations", "departments",
    "divisions", "positions", "job_grades", "cost_centers", "projects",
]

MAX_IMPORT_MB = 5
MAX_IMPORT_ROWS = 500


async def _import_masters(company_id: str) -> Dict[str, List[Dict[str, Any]]]:
    db = get_tenant_db(company_id)  # tenant-scoped
    out: Dict[str, List[Dict[str, Any]]] = {}
    for coll in IMPORT_MASTER_COLLECTIONS:
        out[coll] = await db[coll].find(
            {"company_id": company_id, "status": {"$ne": "deleted"}}, NO_ID
        ).sort("name", ASCENDING).to_list(1000)
    return out


@router.get("/import/template")
async def import_template(
    ctx: AuthContext = Depends(require_permission("employee", "create")),
):
    """Unduh template Excel berisi kolom + sheet referensi master data perusahaan."""
    from fastapi import Response

    from ..core.excel import build_employee_template

    masters = await _import_masters(ctx.company_id)
    content = build_employee_template(masters)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="Template-Impor-Karyawan.xlsx"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/import/columns")
async def import_columns(
    ctx: AuthContext = Depends(require_permission("employee", "create")),
):
    """Metadata kolom template untuk ditampilkan di UI sebelum unggah."""
    from ..core.excel import template_columns

    masters = await _import_masters(ctx.company_id)
    return {
        "columns": template_columns(),
        "master_counts": {k: len(v) for k, v in masters.items()},
        "max_rows": MAX_IMPORT_ROWS,
        "max_size_mb": MAX_IMPORT_MB,
    }


@router.post("/import/validate")
async def import_validate(
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_permission("employee", "create")),
):
    """Dry-run: baca file, validasi tiap baris, kembalikan laporan tanpa menyimpan."""
    from ..core.excel import parse_employee_rows, validate_employee_rows

    raw = await file.read()
    if not raw:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "File yang diunggah kosong.")
    if len(raw) > MAX_IMPORT_MB * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Ukuran file melebihi {MAX_IMPORT_MB} MB. Pecah menjadi beberapa file.",
        )
    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Format file harus .xlsx. Simpan ulang dari Excel bila file Anda .xls atau .csv.",
        )

    try:
        rows = parse_employee_rows(raw)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    if not rows:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Tidak ada baris data yang terbaca. Isi data mulai baris ke-3 pada template.",
        )
    if len(rows) > MAX_IMPORT_ROWS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Maksimal {MAX_IMPORT_ROWS} baris per impor, file Anda berisi {len(rows)} baris.",
        )

    db = ctx.tdb  # tenant-scoped
    cid = ctx.company_id
    existing = await db.employees.find(
        {"company_id": cid, "status": {"$ne": "deleted"}},
        {"_id": 0, "employee_number": 1, "nik": 1},
    ).to_list(10000)

    report = validate_employee_rows(
        rows,
        await _import_masters(cid),
        existing_employee_numbers={e.get("employee_number") for e in existing},
        existing_niks={e.get("nik") for e in existing},
    )
    report["filename"] = file.filename
    return report


@router.post("/import/commit", status_code=status.HTTP_201_CREATED)
async def import_commit(
    payload: EmployeeImportCommit,
    ctx: AuthContext = Depends(require_permission("employee", "create")),
):
    """Simpan baris yang sudah lolos validasi. Baris invalid diabaikan."""
    db = ctx.tdb  # tenant-scoped
    cid = ctx.company_id
    company = await db.companies.find_one({"id": cid}, NO_ID) or {}
    repo = TenantRepository("employees", cid)

    rows = payload.rows or []
    if not rows:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Tidak ada baris yang dikirim untuk diimpor.")
    if len(rows) > MAX_IMPORT_ROWS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Maksimal {MAX_IMPORT_ROWS} baris per impor.")

    created: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []

    for row in rows:
        excel_row = row.get("excel_row")
        data = dict(row.get("payload") or {})
        if not data.get("full_name"):
            failed.append({"excel_row": excel_row, "full_name": None,
                           "error": "Nama Lengkap wajib diisi."})
            continue

        basic_salary = data.pop("basic_salary", None)
        ptkp_status = data.pop("ptkp_status", None)

        try:
            number = (data.get("employee_number") or "").strip() or await _next_employee_number(
                cid, company.get("code")
            )
            data["employee_number"] = number
            await repo.ensure_unique("employee_number", number, label="NIK karyawan")
            if data.get("nik"):
                await repo.ensure_unique("nik", data["nik"], label="Nomor KTP")

            employee = await repo.create(data, ctx.user_id)

            if basic_salary or ptkp_status:
                sal_repo = TenantRepository("employee_salaries", cid)
                await sal_repo.create(
                    {
                        "employee_id": employee["id"],
                        "basic_salary": float(basic_salary or 0),
                        "ptkp_status": ptkp_status or "TK/0",
                        "has_npwp": bool((data.get("npwp") or "").strip()),
                        "bpjs_kesehatan_enrolled": True,
                        "bpjs_jht_enrolled": True,
                        "bpjs_jp_enrolled": True,
                        "components": [],
                        "notes": "Dibuat otomatis dari impor Excel",
                    },
                    ctx.user_id,
                )

            created.append({
                "excel_row": excel_row,
                "id": employee["id"],
                "employee_number": employee["employee_number"],
                "full_name": employee["full_name"],
            })
        except HTTPException as exc:
            failed.append({"excel_row": excel_row, "full_name": data.get("full_name"),
                           "error": exc.detail})
        except Exception as exc:  # noqa: BLE001
            logger.exception("Impor baris %s gagal: %s", excel_row, exc)
            failed.append({"excel_row": excel_row, "full_name": data.get("full_name"),
                           "error": "Terjadi kesalahan tak terduga saat menyimpan baris ini."})

    await log_action(
        ctx, "create", "employee", None, f"Impor Excel {len(created)} karyawan",
        notes=f"{len(created)} berhasil, {len(failed)} gagal",
    )
    return {
        "created_count": len(created),
        "failed_count": len(failed),
        "created": created,
        "failed": failed,
        "summary": (
            f"{len(created)} karyawan berhasil diimpor"
            + (f", {len(failed)} baris gagal." if failed else ".")
        ),
    }
