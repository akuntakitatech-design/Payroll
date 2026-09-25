"""Rekrutmen V1 — Tahap C: konversi kandidat (offering_accepted) menjadi Karyawan.

Prinsip:
  * Memakai struktur Data Karyawan existing (tabel `employees`, EmployeeCreate-compatible
    payload, penomoran `core/employee_numbering.next_employee_number`, validasi referensi
    master yang sama). Tidak ada tabel karyawan baru, tidak menyentuh Payroll / gaji.
  * Otorisasi: modul recruitment + `recruitment:edit`  DAN  modul employee_core +
    `employee:create`. `company_id` payload tidak dipercaya; sumber kebenaran = AuthContext.
  * Idempotent / aman dari double click tanpa transaksi lintas tabel (adapter tidak
    menyediakannya). Pola yang dipakai:
      1) KLAIM  : find_one_and_update kandidat {stage=offering_accepted, employee_id NULL}
                  -> stage=hired, converted_at/by. Klaim gagal => 409 (proses lain / sudah).
      2) BUAT   : insert employee dengan `candidate_id`; UNIQUE (company_id, candidate_id)
                  di DB menjamin tidak pernah ada 2 karyawan untuk 1 kandidat.
      3) TAUTKAN: set candidate.employee_id.
      Gagal di (2) => klaim dikompensasi (kembali offering_accepted, converted_* dibersihkan).
      Gagal di (3) (sangat jarang: crash) => self-heal: pada preview/convert berikutnya,
      kandidat hired tanpa employee_id dicari karyawannya lewat `employees.candidate_id`
      lalu ditautkan; tidak membuat karyawan kedua.
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from ..core.audit import log_action
from ..core.db import NO_ID, ReturnDocument, now, serialize
from ..core.deps import AuthContext
from ..core.employee_numbering import next_employee_number
from ..core.rbac import resource_module
from ..core.recruitment_workflow import stage_label
from ..core.repo import TenantRepository
from ..schemas import CandidateConvertInput
from .employees import EDUCATIONS, GENDERS, REF_FIELDS as EMPLOYEE_REF_FIELDS, _validate_refs
from .recruitment import MODULE, _add_history, _enrich, _perm
from .recruitment_pipeline import (
    DATE_RE,
    _conflict,
    _get_candidate,
    _invalid,
    _label_map,
    _offerings_for,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/recruitment", tags=["Rekrutmen — Konversi Karyawan"])

RES_CANDIDATE = "candidate"
EMPLOYEE_MODULE = resource_module("employee")

# Field kandidat -> field employee (identitas) — disalin apa adanya.
IDENTITY_MAP = [
    ("full_name", "full_name", "Nama lengkap"),
    ("nik", "nik", "NIK"),
    ("birth_place", "birth_place", "Tempat lahir"),
    ("birth_date", "birth_date", "Tanggal lahir"),
    ("gender", "gender", "Jenis kelamin"),
    ("phone", "phone", "No. HP"),
    ("email", "email", "Email"),
    ("address", "address", "Alamat"),
    ("city", "city", "Kota"),
]
# Field offering -> field employee (pekerjaan).
JOB_MAP = [
    ("position_id", "position_id", "Jabatan"),
    ("department_id", "department_id", "Departemen"),
    ("work_location_id", "work_location_id", "Lokasi kerja"),
    ("project_id", "project_id", "Proyek"),
    ("employment_status_id", "employment_status_id", "Status kepegawaian"),
    ("start_date", "join_date", "Tanggal mulai kerja"),
]
# Wajib ada sebelum konversi (selain full_name yang selalu ada pada kandidat).
REQUIRED_EMPLOYEE_FIELDS = [("join_date", "Tanggal mulai kerja"), ("position_id", "Jabatan")]
# Direkomendasikan (tidak memblokir) — ditampilkan sebagai peringatan.
RECOMMENDED_FIELDS = [
    ("nik", "NIK"), ("employment_status_id", "Status kepegawaian"), ("gender", "Jenis kelamin"),
    ("birth_date", "Tanggal lahir"), ("phone", "No. HP"), ("email", "Email"),
]
OVERRIDABLE = ["nik", "join_date", "employment_status_id", "job_title", "gender", "birth_place",
               "birth_date", "phone", "email", "address", "city"]


def _label(list_, key):
    return next((x["label"] for x in list_ if x["key"] == key), key)


# --------------------------------------------------------------------------
# Otorisasi & prasyarat
# --------------------------------------------------------------------------
def _authz_blockers(ctx: AuthContext) -> List[str]:
    reasons = []
    if not ctx.has_module(EMPLOYEE_MODULE):
        reasons.append(f"Modul Data Karyawan belum aktif untuk perusahaan {ctx.company.get('name')}.")
    if not ctx.has_permission("employee", "create"):
        reasons.append("Anda tidak memiliki hak akses membuat Data Karyawan (employee:create).")
    return reasons


def _require_authz(ctx: AuthContext) -> None:
    reasons = _authz_blockers(ctx)
    if reasons:
        raise HTTPException(status.HTTP_403_FORBIDDEN, " ".join(reasons))


async def _accepted_offering(company_id: str, candidate_id: str) -> Optional[Dict[str, Any]]:
    """Offering yang diterima (satu-satunya yang aktif saat offering_accepted)."""
    items = await _offerings_for(company_id, candidate_id)
    return next((o for o in items if o.get("offer_status") == "accepted"), None)


async def _employee_by_candidate(company_id: str, candidate_id: str) -> Optional[Dict[str, Any]]:
    from ..core.tenancy import get_tenant_db
    db = get_tenant_db(company_id)  # tenant-scoped
    row = await db.employees.find_one(
        {"company_id": company_id, "candidate_id": candidate_id, "status": {"$ne": "deleted"}}, NO_ID
    )
    return serialize(row) if row else None


async def _employee_by_id(company_id: str, employee_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not employee_id:
        return None
    from ..core.tenancy import get_tenant_db
    db = get_tenant_db(company_id)  # tenant-scoped
    row = await db.employees.find_one({"company_id": company_id, "id": employee_id}, NO_ID)
    return serialize(row) if row else None


async def _nik_conflict(ctx: AuthContext, nik: Optional[str], exclude_candidate_id: str) -> Optional[Dict[str, Any]]:
    """Karyawan lain pada tenant yang sama dengan NIK identik (bukan hasil konversi kandidat ini)."""
    if not nik:
        return None
    db = ctx.tdb  # tenant-scoped
    row = await db.employees.find_one(
        {"company_id": ctx.company_id, "nik": str(nik).strip(), "status": {"$ne": "deleted"}}, NO_ID
    )
    if not row or row.get("candidate_id") == exclude_candidate_id:
        return None
    row = serialize(row)
    if ctx.has_permission("employee", "view"):
        return {"id": row["id"], "employee_number": row.get("employee_number"), "full_name": row.get("full_name")}
    return {"id": None, "employee_number": None, "full_name": None}


def _employee_summary(emp: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not emp:
        return None
    return {
        "id": emp["id"], "employee_number": emp.get("employee_number"), "full_name": emp.get("full_name"),
        "join_date": emp.get("join_date"), "status": emp.get("status"),
    }


# --------------------------------------------------------------------------
# Mapping kandidat + offering (+ pelengkap) -> payload EmployeeCreate
# --------------------------------------------------------------------------
def _build_employee_payload(candidate: Dict[str, Any], offering: Optional[Dict[str, Any]],
                            overrides: Dict[str, Any]) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    for src, dst, _l in IDENTITY_MAP:
        if candidate.get(src) not in (None, ""):
            data[dst] = candidate[src]
    if offering:
        for src, dst, _l in JOB_MAP:
            if offering.get(src) not in (None, ""):
                data[dst] = offering[src]
    # fallback posisi/departemen/lokasi/proyek dari lamaran bila offering kosong
    for f in ("position_id", "department_id", "work_location_id", "project_id"):
        if not data.get(f) and candidate.get(f):
            data[f] = candidate[f]
    if candidate.get("last_education"):
        data["education"] = candidate["last_education"]
    if not data.get("job_title") and candidate.get("applied_position_title"):
        data["job_title"] = candidate["applied_position_title"]
    for k in OVERRIDABLE:
        v = overrides.get(k)
        if v not in (None, ""):
            data[k] = str(v).strip() if isinstance(v, str) else v
    # catatan asal + pendidikan detail (employee tidak punya kolom jurusan/institusi)
    edu_bits = [b for b in (candidate.get("major"), candidate.get("institution"),
                            f"lulus {candidate['graduation_year']}" if candidate.get("graduation_year") else None) if b]
    notes = [f"Berasal dari Rekrutmen: kandidat {candidate.get('candidate_number')}"]
    if edu_bits:
        notes.append("Pendidikan: " + ", ".join(str(b) for b in edu_bits))
    if overrides.get("notes"):
        notes.append(str(overrides["notes"]).strip())
    data["notes"] = "\n".join(notes)
    data["full_name"] = candidate.get("full_name")
    return data


def _missing_required(data: Dict[str, Any]) -> List[Dict[str, str]]:
    return [{"key": k, "label": l} for k, l in REQUIRED_EMPLOYEE_FIELDS if not data.get(k)]


def _validate_override_formats(data: Dict[str, Any]) -> None:
    for f, label in (("join_date", "Tanggal mulai kerja"), ("birth_date", "Tanggal lahir")):
        if data.get(f) and not DATE_RE.match(str(data[f])):
            raise _invalid(f"{label} harus berformat YYYY-MM-DD.")
    if data.get("gender") and data["gender"] not in {g["key"] for g in GENDERS}:
        raise _invalid("Jenis kelamin tidak valid.")


async def _mapping_rows(company_id: str, candidate: Dict[str, Any], offering: Optional[Dict[str, Any]],
                        data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Baris tampilan preview: label, nilai (sudah dilabeli), sumber."""
    ref_names: Dict[str, Optional[str]] = {}
    for f in ("position_id", "department_id", "work_location_id", "project_id", "employment_status_id"):
        coll = EMPLOYEE_REF_FIELDS[f][0]
        m = await _label_map(company_id, coll, [data.get(f)]) if data.get(f) else {}
        ref_names[f] = m.get(data.get(f))
    identity = []
    for src, dst, label in IDENTITY_MAP:
        val = data.get(dst)
        if dst == "gender" and val:
            val = _label(GENDERS, val)
        identity.append({"key": dst, "label": label, "value": val, "source": "kandidat" if candidate.get(src) else ("pelengkap" if val else None)})
    job = []
    for src, dst, label in JOB_MAP:
        raw = data.get(dst)
        val = ref_names.get(dst, raw) if dst.endswith("_id") else raw
        source = "offering" if offering and offering.get(src) else ("lamaran" if candidate.get(src) else ("pelengkap" if raw else None))
        job.append({"key": dst, "label": label, "value": val, "source": source})
    job.append({"key": "job_title", "label": "Sebutan jabatan", "value": data.get("job_title"), "source": "lamaran" if candidate.get("applied_position_title") else ("pelengkap" if data.get("job_title") else None)})
    education = [
        {"key": "education", "label": "Pendidikan terakhir", "value": _label(EDUCATIONS, candidate.get("last_education")) if candidate.get("last_education") else None, "source": "kandidat"},
        {"key": "major", "label": "Jurusan", "value": candidate.get("major"), "source": "kandidat"},
        {"key": "institution", "label": "Institusi", "value": candidate.get("institution"), "source": "kandidat"},
    ]
    return {"identity": identity, "job": job, "education": education}


# --------------------------------------------------------------------------
# State untuk UI (dipakai preview & pipeline)
# --------------------------------------------------------------------------
async def conversion_state(ctx: AuthContext, candidate: Dict[str, Any]) -> Dict[str, Any]:
    stage = candidate.get("stage_status")
    employee = await _employee_by_id(ctx.company_id, candidate.get("employee_id"))
    if stage == "hired" and not employee:
        # self-heal: karyawan sudah dibuat tetapi tautan belum tersimpan
        employee = await _employee_by_candidate(ctx.company_id, candidate["id"])
        if employee:
            await ctx.tdb.candidates.update_one(
                {"company_id": ctx.company_id, "id": candidate["id"], "employee_id": None},
                {"$set": {"employee_id": employee["id"], "updated_at": now()}},
            )
            candidate["employee_id"] = employee["id"]
    converted_by_name = None
    if candidate.get("converted_by"):
        from ..core.db import get_db
        u = await get_db().users.find_one({"id": candidate["converted_by"]}, NO_ID)
        converted_by_name = (u or {}).get("full_name")
    blockers: List[str] = []
    if stage == "hired":
        blockers.append("Kandidat sudah menjadi karyawan.")
    elif stage != "offering_accepted":
        blockers.append(f"Konversi hanya tersedia setelah offering diterima (saat ini: '{stage_label(stage)}').")
    if candidate.get("employee_id") and stage != "hired":
        blockers.append("Kandidat sudah pernah dikonversi.")
    blockers += _authz_blockers(ctx)
    if not ctx.has_permission("recruitment", "edit"):
        blockers.append("Anda tidak memiliki hak akses Rekrutmen (recruitment:edit).")
    return {
        "is_hired": stage == "hired",
        "can_convert": not blockers,
        "blockers": blockers,
        "employee": _employee_summary(employee),
        "employee_route": f"/employees/{employee['id']}" if employee and ctx.has_permission("employee", "view") else None,
        "converted_at": candidate.get("converted_at"),
        "converted_by": candidate.get("converted_by"),
        "converted_by_name": converted_by_name,
        "incomplete_link": stage == "hired" and not employee,
    }


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------
@router.get("/candidates/{candidate_id}/convert-preview")
async def convert_preview(candidate_id: str, ctx: AuthContext = Depends(_perm("view"))):
    candidate = await _get_candidate(ctx, candidate_id)
    state = await conversion_state(ctx, candidate)
    offering = await _accepted_offering(ctx.company_id, candidate_id)
    blockers = list(state["blockers"])
    if candidate.get("stage_status") == "offering_accepted" and not offering:
        blockers.append("Offering yang diterima tidak ditemukan untuk kandidat ini.")
    data = _build_employee_payload(candidate, offering, {})
    mapping = await _mapping_rows(ctx.company_id, candidate, offering, data)
    missing = _missing_required(data)
    warnings = [{"key": k, "label": l} for k, l in RECOMMENDED_FIELDS if not data.get(k)]
    nik_conflict = await _nik_conflict(ctx, data.get("nik"), candidate_id) if not state["is_hired"] else None
    if nik_conflict:
        blockers.append("NIK sudah digunakan oleh karyawan lain pada perusahaan ini.")
    return {
        **state,
        "can_convert": not blockers,
        "blockers": blockers,
        "offering": {"id": offering["id"], "version": offering.get("version"), "start_date": offering.get("start_date"),
                     "basic_salary": offering.get("basic_salary"), "total_allowances": offering.get("total_allowances")} if offering else None,
        "mapping": mapping,
        "required_missing": missing,
        "warnings": warnings,
        "nik_conflict": nik_conflict,
        "fillable_fields": OVERRIDABLE,
        "salary_note": "Gaji pada offering tidak disalin ke Payroll. Atur gaji karyawan lewat menu Gaji Karyawan existing.",
    }


@router.post("/candidates/{candidate_id}/convert", status_code=status.HTTP_201_CREATED)
async def convert_candidate(candidate_id: str, payload: CandidateConvertInput, ctx: AuthContext = Depends(_perm("edit"))):
    _require_authz(ctx)
    candidate = await _get_candidate(ctx, candidate_id)  # 404 lintas tenant
    stage = candidate.get("stage_status")

    # Sudah dikonversi -> 409 idempotent (tidak membuat karyawan kedua)
    if stage == "hired" or candidate.get("employee_id"):
        state = await conversion_state(ctx, candidate)
        if state["incomplete_link"]:
            raise _conflict("Kandidat tercatat hired tetapi data karyawan belum ditemukan. Hubungi administrator (tidak ada karyawan baru dibuat).")
        emp = state["employee"] or {}
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Kandidat sudah menjadi karyawan ({emp.get('employee_number') or '-'} · {emp.get('full_name') or candidate.get('full_name')}).",
        )
    if stage != "offering_accepted":
        raise _invalid(f"Konversi hanya dapat dilakukan setelah offering diterima (saat ini: '{stage_label(stage)}').")

    offering = await _accepted_offering(ctx.company_id, candidate_id)
    if not offering:
        raise _invalid("Offering yang diterima tidak ditemukan untuk kandidat ini.")

    overrides = payload.model_dump(exclude_none=True)
    overrides.pop("company_id", None)
    data = _build_employee_payload(candidate, offering, overrides)
    _validate_override_formats(data)
    missing = _missing_required(data)
    if missing:
        raise _invalid("Lengkapi data wajib sebelum konversi: " + ", ".join(m["label"] for m in missing) + ".")
    await _validate_refs(ctx.company_id, data)  # validasi master yang sama dengan Data Karyawan (422)
    conflict = await _nik_conflict(ctx, data.get("nik"), candidate_id)
    if conflict:
        detail: Dict[str, Any] = {"message": "NIK sudah digunakan oleh karyawan lain pada perusahaan ini. Karyawan baru tidak dibuat.",
                                  "existing_employee": conflict if conflict.get("id") else None}
        raise HTTPException(status.HTTP_409_CONFLICT, detail)

    db = ctx.tdb  # tenant-scoped
    ts = now()
    # 1) KLAIM (kunci idempotensi): hanya satu pemanggil yang lolos
    claimed = await db.candidates.find_one_and_update(
        {"company_id": ctx.company_id, "id": candidate_id, "stage_status": "offering_accepted",
         "employee_id": None, "status": {"$ne": "deleted"}},
        {"$set": {"stage_status": "hired", "stage_changed_at": ts, "converted_at": ts, "converted_by": ctx.user_id,
                  "updated_at": ts, "updated_by": ctx.user_id}},
        projection=NO_ID,
        return_document=ReturnDocument.AFTER,
    )
    if not claimed:
        raise _conflict("Kandidat sedang/sudah dikonversi oleh proses lain. Muat ulang halaman.")

    # 2) BUAT karyawan (UNIQUE company_id+candidate_id di DB menolak duplikat)
    repo = TenantRepository("employees", ctx.company_id)
    try:
        number = await next_employee_number(ctx.company_id, ctx.company.get("code"))  # mekanisme existing
        data["employee_number"] = number
        data["candidate_id"] = candidate_id
        if data.get("nik"):
            await repo.ensure_unique("nik", data["nik"], label="Nomor KTP")
        # Upgrade 01B: status bisnis default tenant untuk karyawan hasil konversi
        from ..core import employee_status as emp_status
        status_row = await emp_status.prepare_new_employee(ctx.company_id, data)
        employee = await repo.create(data, ctx.user_id)
    except Exception as exc:
        # kompensasi: lepaskan klaim agar kandidat bisa dicoba lagi
        await db.candidates.update_one(
            {"company_id": ctx.company_id, "id": candidate_id, "stage_status": "hired", "employee_id": None},
            {"$set": {"stage_status": "offering_accepted", "converted_at": None, "converted_by": None,
                      "updated_at": now(), "updated_by": ctx.user_id}},
        )
        if isinstance(exc, HTTPException):
            raise
        logger.exception("Konversi kandidat %s gagal saat membuat karyawan", candidate_id)
        raise _conflict("Pembuatan data karyawan gagal; status kandidat dikembalikan. Silakan coba lagi.")

    # 3) TAUTKAN employee_id ke kandidat
    await db.candidates.update_one(
        {"company_id": ctx.company_id, "id": candidate_id, "stage_status": "hired"},
        {"$set": {"employee_id": employee["id"], "updated_at": now(), "updated_by": ctx.user_id}},
    )
    note = f"Dikonversi menjadi karyawan {employee.get('employee_number')} (offering v{offering.get('version')})"
    await _add_history(ctx, candidate_id, "candidate_converted", "offering_accepted", "hired", note)
    # Riwayat awal status bisnis (setelah karyawan tertaut ke kandidat)
    await emp_status.record_initial_history(
        ctx.company_id, employee, status_row, "SYSTEM", ctx.user_id,
        ctx.user.get("full_name") if ctx.user else None, "Status awal dari konversi kandidat",
    )
    # Upgrade 01D: karyawan hasil konversi dengan project -> assignment ACTIVE pertama
    from ..core import assignment as asg
    await asg.create_initial_for_new_employee(ctx.company_id, employee, "RECRUITMENT", ctx.user_id, emp_status.today_local())
    await log_action(ctx, "candidate_converted_to_employee", RES_CANDIDATE, candidate_id, candidate.get("full_name"),
                     before=candidate, after={**claimed, "employee_id": employee["id"]}, module=MODULE, notes=note)
    await log_action(ctx, "employee_created_from_recruitment", "employee", employee["id"], employee.get("full_name"),
                     after=employee, module=EMPLOYEE_MODULE,
                     notes=f"Dari kandidat {candidate.get('candidate_number')} · {candidate.get('full_name')}")

    fresh = await _get_candidate(ctx, candidate_id)
    enriched = (await _enrich(ctx.company_id, [serialize(fresh)]))[0]
    return {
        "message": f"{candidate.get('full_name')} berhasil menjadi karyawan dengan nomor {employee.get('employee_number')}.",
        "candidate": enriched,
        "employee": _employee_summary(serialize(employee)),
        "employee_route": f"/employees/{employee['id']}",
        "conversion": await conversion_state(ctx, fresh),
    }
