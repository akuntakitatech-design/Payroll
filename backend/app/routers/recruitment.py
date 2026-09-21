"""Modul Rekrutmen V1 — Tahap A (recruitment).

Kandidat, screening HR, riwayat status, dan ringkasan dashboard.
Semua query lewat TenantRepository / ctx.tdb sehingga tidak dapat menembus
batas perusahaan. company_id selalu berasal dari konteks autentikasi —
nilai company_id pada payload/query diabaikan (fail-closed).

Belum ada pada tahap ini: interview, approval transaksi, offering,
konversi ke karyawan, impor Excel.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..core.audit import log_action
from ..core.db import ASCENDING, DESCENDING, NO_ID, now, serialize, serialize_list
from ..core.deps import AuthContext, require_permission
from ..core.recruitment_workflow import (
    ACTIVE_STAGES,
    APPROVAL_DECISIONS,
    INTERVIEW_ALLOWED_STAGES,
    INTERVIEW_MODES,
    INTERVIEW_RECOMMENDATIONS,
    INTERVIEW_RESULTS,
    INTERVIEW_TYPES,
    OFFER_STATUSES,
    OFFERING_ALLOWED_STAGES,
    SCREENING_RECOMMENDATIONS,
    SCREENING_RESULTS,
    SOURCES,
    STAGES,
    active_stage_catalog,
    allowed_next,
    assert_deletable,
    assert_transition,
    stage_catalog,
    stage_label,
    DELETABLE_STAGES,
)
from ..core.repo import TenantRepository
from ..core.tenancy import get_tenant_db
from ..routers.employees import EDUCATIONS, GENDERS
from ..schemas import (
    CandidateCreate,
    CandidateScreening,
    CandidateStageChange,
    CandidateUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/recruitment", tags=["Rekrutmen"])

MODULE = "recruitment"
RESOURCE = "candidate"  # resource untuk audit log; permission tetap memakai "recruitment"

# FK -> (collection master existing, label) — tidak ada master duplikat.
REF_FIELDS: Dict[str, tuple] = {
    "position_id": ("positions", "Jabatan"),
    "department_id": ("departments", "Departemen"),
    "work_location_id": ("work_locations", "Lokasi kerja"),
    "project_id": ("projects", "Proyek"),
}

SEARCH_FIELDS = ["full_name", "candidate_number", "nik", "email", "phone"]

# Field yang TIDAK boleh diubah lewat create/update umum (hanya lewat endpoint proses).
PROTECTED_FIELDS = {
    "company_id", "id", "status", "stage_status", "stage_changed_at", "rejection_reason",
    "screening_result", "screening_score", "screening_notes", "screening_recommendation",
    "screened_by", "screened_by_name", "screened_at", "employee_id", "converted_at", "converted_by",
    "created_at", "created_by", "updated_at", "updated_by",
}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _perm(action: str):
    return require_permission("recruitment", action, MODULE)


def _clean(data: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in data.items() if k not in PROTECTED_FIELDS}
    for key in ("full_name", "nik", "email", "phone", "candidate_number"):
        if isinstance(out.get(key), str):
            out[key] = out[key].strip()
    if out.get("email"):
        out["email"] = out["email"].lower()
    return out


def _validate_enums(data: Dict[str, Any]) -> None:
    checks = (
        ("source", {s["key"] for s in SOURCES}, "Sumber kandidat"),
        ("gender", {g["key"] for g in GENDERS}, "Jenis kelamin"),
        ("last_education", {e["key"] for e in EDUCATIONS}, "Pendidikan terakhir"),
    )
    for field, allowed, label in checks:
        value = data.get(field)
        if value and value not in allowed:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{label} '{value}' tidak dikenal.")


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


async def _next_candidate_number(company_id: str) -> str:
    """Nomor kandidat per perusahaan: CND-<tahun>-<urut 4 digit>. Aman dari
    tabrakan lewat pengecekan ulang + unique index (company_id, candidate_number)."""
    db = get_tenant_db(company_id)  # tenant-scoped
    year = now().year
    prefix = f"CND-{year}-"
    seq = await db.candidates.count_documents(
        {"company_id": company_id, "candidate_number": {"$regex": f"^{prefix}"}}
    ) + 1
    number = f"{prefix}{seq:04d}"
    while await db.candidates.count_documents({"company_id": company_id, "candidate_number": number}):
        seq += 1
        number = f"{prefix}{seq:04d}"
    return number


async def _label_maps(company_id: str, items: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    db = get_tenant_db(company_id)  # tenant-scoped
    maps: Dict[str, Dict[str, str]] = {}
    pending: List[tuple] = []
    for field, (collection, _label) in REF_FIELDS.items():
        ids = {i.get(field) for i in items if i.get(field)}
        if not ids:
            maps[field] = {}
            continue
        pending.append((field, db[collection].find(
            {"company_id": company_id, "id": {"$in": list(ids)}}, NO_ID
        ).to_list(1000)))
    # Query master dijalankan bersamaan: DB jauh -> satu perjalanan jaringan, bukan empat.
    results = await asyncio.gather(*[coro for _f, coro in pending])
    for (field, _c), rows in zip(pending, results):
        maps[field] = {r["id"]: r.get("name") or r.get("code") for r in rows}
    return maps


async def _enrich(company_id: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not items:
        return items
    maps = await _label_maps(company_id, items)
    source_labels = {s["key"]: s["label"] for s in SOURCES}
    for item in items:
        for field in REF_FIELDS:
            item[f"{field[:-3]}_name"] = maps.get(field, {}).get(item.get(field))
        stage = item.get("stage_status") or "draft"
        item["stage_label"] = stage_label(stage)
        item["stage_tone"] = STAGES.get(stage, {}).get("tone", "neutral")
        item["source_label"] = source_labels.get(item.get("source"), item.get("source"))
        item["allowed_next"] = allowed_next(stage)
        item["can_screen"] = stage == "screening"
        item["can_delete"] = stage in DELETABLE_STAGES
        item["can_schedule_interview"] = stage in INTERVIEW_ALLOWED_STAGES
        item["can_submit_approval"] = stage == "interview_done"
        item["can_create_offering"] = stage in OFFERING_ALLOWED_STAGES
        item["can_convert"] = stage == "offering_accepted" and not item.get("employee_id")
        item["is_hired"] = stage == "hired"
        item["screening_result_label"] = SCREENING_RESULTS.get(item.get("screening_result") or "", {}).get("label")
        item["screening_recommendation_label"] = SCREENING_RECOMMENDATIONS.get(
            item.get("screening_recommendation") or ""
        )
    return items


async def _add_history(
    ctx: AuthContext,
    candidate_id: str,
    action: str,
    from_status: Optional[str],
    to_status: Optional[str],
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    repo = TenantRepository("candidate_status_history", ctx.company_id)
    return await repo.create(
        {
            "candidate_id": candidate_id,
            "action": action,
            "from_status": from_status,
            "to_status": to_status,
            "notes": notes,
            "changed_by": ctx.user_id,
            "changed_by_name": ctx.user.get("full_name"),
            "changed_at": now(),
        },
        ctx.user_id,
    )


async def _history_for(company_id: str, candidate_id: str, limit: int = 200) -> List[Dict[str, Any]]:
    db = get_tenant_db(company_id)  # tenant-scoped
    rows = await db.candidate_status_history.find(
        {"company_id": company_id, "candidate_id": candidate_id}, NO_ID
    ).sort([("changed_at", DESCENDING), ("created_at", DESCENDING)]).to_list(limit)
    for r in rows:
        r["from_label"] = stage_label(r.get("from_status")) if r.get("from_status") else None
        r["to_label"] = stage_label(r.get("to_status")) if r.get("to_status") else None
    return serialize_list(rows)


# --------------------------------------------------------------------------
# catalog & summary
# --------------------------------------------------------------------------
@router.get("/catalog")
async def catalog(ctx: AuthContext = Depends(_perm("view"))):
    """Semua pilihan dropdown form kandidat — satu panggilan."""
    db = ctx.tdb  # tenant-scoped
    out: Dict[str, Any] = {
        "stages": stage_catalog(),
        "active_stages": active_stage_catalog(),
        "sources": SOURCES,
        "genders": GENDERS,
        "educations": EDUCATIONS,
        "screening_results": [{"key": k, "label": v["label"]} for k, v in SCREENING_RESULTS.items()],
        "screening_recommendations": [{"key": k, "label": v} for k, v in SCREENING_RECOMMENDATIONS.items()],
        # Tahap B
        "interview_types": INTERVIEW_TYPES,
        "interview_modes": INTERVIEW_MODES,
        "interview_results": [{"key": k, "label": v["label"], "tone": v["tone"]} for k, v in INTERVIEW_RESULTS.items()],
        "interview_recommendations": [{"key": k, "label": v} for k, v in INTERVIEW_RECOMMENDATIONS.items()],
        "offer_statuses": [{"key": k, "label": v["label"], "tone": v["tone"]} for k, v in OFFER_STATUSES.items()],
        "approval_decisions": [{"key": k, "label": v["label"], "tone": v["tone"]} for k, v in APPROVAL_DECISIONS.items()],
    }
    # master tambahan untuk offering (status kepegawaian) — reuse master existing
    rows = await db.employment_statuses.find(
        {"company_id": ctx.company_id, "status": "active"}, NO_ID
    ).sort("name", ASCENDING).to_list(1000)
    out["employment_statuses"] = [{"id": r["id"], "name": r.get("name"), "code": r.get("code")} for r in rows]
    collections = [collection for _f, (collection, _l) in REF_FIELDS.items()]
    results = await asyncio.gather(*[
        db[collection].find({"company_id": ctx.company_id, "status": "active"}, NO_ID)
        .sort("name", ASCENDING).to_list(1000)
        for collection in collections
    ])
    for collection, rows in zip(collections, results):
        out[collection] = [{"id": r["id"], "name": r.get("name"), "code": r.get("code")} for r in rows]
    return out


@router.get("/summary")
async def summary(ctx: AuthContext = Depends(_perm("view"))):
    db = ctx.tdb  # tenant-scoped
    cid = ctx.company_id
    base = {"company_id": cid, "status": {"$ne": "deleted"}}

    stage_keys = (
        "draft", "screening", "screening_passed", "screening_failed",
        "interview_scheduled", "interview_done", "awaiting_approval", "approved", "rejected",
        "offering", "offering_accepted", "offering_declined",
    )
    # Semua hitungan + daftar terbaru dijalankan bersamaan (pola sama dengan dashboard.py).
    gathered = await asyncio.gather(
        *[db.candidates.count_documents({**base, "stage_status": key}) for key in stage_keys],
        db.candidates.count_documents(base),
        db.candidates.count_documents({**base, "stage_status": {"$in": ACTIVE_STAGES}}),
        db.candidates.find(base, NO_ID).sort([("created_at", DESCENDING)]).to_list(6),
        db.candidate_status_history.find({"company_id": cid}, NO_ID)
        .sort([("changed_at", DESCENDING)])
        .to_list(10),
    )
    counts: Dict[str, int] = dict(zip(stage_keys, gathered[: len(stage_keys)]))
    total, active = gathered[len(stage_keys)], gathered[len(stage_keys) + 1]
    recent = serialize_list(gathered[len(stage_keys) + 2])
    activity = serialize_list(gathered[len(stage_keys) + 3])
    await _enrich(cid, recent)
    cand_ids = {a.get("candidate_id") for a in activity if a.get("candidate_id")}
    names: Dict[str, Dict[str, Any]] = {}
    if cand_ids:
        for c in await db.candidates.find(
            {"company_id": cid, "id": {"$in": list(cand_ids)}}, NO_ID
        ).to_list(len(cand_ids)):
            names[c["id"]] = c
    for a in activity:
        c = names.get(a.get("candidate_id")) or {}
        a["candidate_name"] = c.get("full_name")
        a["candidate_number"] = c.get("candidate_number")
        a["from_label"] = stage_label(a.get("from_status")) if a.get("from_status") else None
        a["to_label"] = stage_label(a.get("to_status")) if a.get("to_status") else None

    return {
        "total": total,
        "active": active,
        **counts,
        "interview_active": counts["interview_scheduled"] + counts["interview_done"],
        "offering_active": counts["offering"],
        "recent_candidates": recent,
        "recent_activity": activity,
    }


# --------------------------------------------------------------------------
# kandidat CRUD
# --------------------------------------------------------------------------
@router.get("/candidates")
async def list_candidates(
    q: Optional[str] = None,
    stage_status: Optional[str] = None,
    position_id: Optional[str] = None,
    department_id: Optional[str] = None,
    work_location_id: Optional[str] = None,
    project_id: Optional[str] = None,
    source: Optional[str] = None,
    applied_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    applied_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    page: int = 1,
    limit: int = 20,
    ctx: AuthContext = Depends(_perm("view")),
):
    filters: Dict[str, Any] = {}
    for key, value in (
        ("stage_status", stage_status),
        ("position_id", position_id),
        ("department_id", department_id),
        ("work_location_id", work_location_id),
        ("project_id", project_id),
        ("source", source),
    ):
        if value:
            filters[key] = value
    if applied_from or applied_to:
        rng: Dict[str, Any] = {}
        if applied_from:
            rng["$gte"] = applied_from
        if applied_to:
            rng["$lte"] = applied_to
        filters["applied_at"] = rng

    repo = TenantRepository("candidates", ctx.company_id)
    result = await repo.list(
        q=q, search_fields=SEARCH_FIELDS, filters=filters, page=page, limit=limit
    )
    result["items"] = await _enrich(ctx.company_id, serialize_list(result["items"]))
    return result


@router.post("/candidates", status_code=status.HTTP_201_CREATED)
async def create_candidate(payload: CandidateCreate, ctx: AuthContext = Depends(_perm("create"))):
    data = _clean(payload.model_dump(exclude_none=True))
    _validate_enums(data)
    await _validate_refs(ctx.company_id, data)
    repo = TenantRepository("candidates", ctx.company_id)

    number = (data.get("candidate_number") or "").strip()
    if number:
        await repo.ensure_unique("candidate_number", number, label="Nomor kandidat")
    else:
        number = await _next_candidate_number(ctx.company_id)
    data["candidate_number"] = number
    if data.get("nik"):
        await repo.ensure_unique("nik", data["nik"], label="NIK")
    data.setdefault("source", "manual")
    data.setdefault("applied_at", now().date().isoformat())
    data["stage_status"] = "draft"
    data["stage_changed_at"] = now()

    created = await repo.create(data, ctx.user_id)
    await _add_history(ctx, created["id"], "create", None, "draft", "Kandidat dibuat")
    await log_action(
        ctx, "create", RESOURCE, created["id"], created.get("full_name"),
        after=created, module=MODULE, notes=f"Kandidat {number} dibuat",
    )
    return (await _enrich(ctx.company_id, [serialize(created)]))[0]


@router.get("/candidates/{candidate_id}")
async def get_candidate(candidate_id: str, ctx: AuthContext = Depends(_perm("view"))):
    db = ctx.tdb  # tenant-scoped
    cid = ctx.company_id
    repo = TenantRepository("candidates", cid)
    candidate = await repo.get(candidate_id)
    if candidate.get("status") == "deleted":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kandidat sudah dihapus.")
    enriched, history, document_count = await asyncio.gather(
        _enrich(cid, [serialize(candidate)]),
        _history_for(cid, candidate_id),
        db.documents.count_documents(
            {
                "company_id": cid,
                "owner_type": "applicant",
                "owner_id": candidate_id,
                "status": {"$ne": "deleted"},
                "is_deleted": {"$ne": True},
            }
        ),
    )
    return {"candidate": enriched[0], "history": history, "document_count": document_count}


@router.put("/candidates/{candidate_id}")
async def update_candidate(
    candidate_id: str, payload: CandidateUpdate, ctx: AuthContext = Depends(_perm("edit"))
):
    repo = TenantRepository("candidates", ctx.company_id)
    current = await repo.get(candidate_id)
    if current.get("status") == "deleted":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kandidat sudah dihapus.")
    if current.get("stage_status") == "hired":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Kandidat sudah menjadi karyawan; ubah datanya melalui modul Data Karyawan.",
        )
    data = _clean(payload.model_dump(exclude_unset=True))
    if not data:
        return (await _enrich(ctx.company_id, [serialize(current)]))[0]
    _validate_enums(data)
    await _validate_refs(ctx.company_id, data)
    if data.get("candidate_number"):
        await repo.ensure_unique(
            "candidate_number", data["candidate_number"], exclude_id=candidate_id, label="Nomor kandidat"
        )
    if data.get("nik"):
        await repo.ensure_unique("nik", data["nik"], exclude_id=candidate_id, label="NIK")

    before, after = await repo.update(candidate_id, data, ctx.user_id)
    await log_action(
        ctx, "update", RESOURCE, candidate_id, after.get("full_name"),
        before=before, after=after, module=MODULE,
    )
    return (await _enrich(ctx.company_id, [serialize(after)]))[0]


@router.delete("/candidates/{candidate_id}")
async def delete_candidate(candidate_id: str, ctx: AuthContext = Depends(_perm("delete"))):
    """Soft-delete. Hanya kandidat Draft atau Tidak Lolos yang boleh dihapus;
    record tetap tersimpan (status='deleted') sehingga riwayat dan audit tetap utuh."""
    repo = TenantRepository("candidates", ctx.company_id)
    candidate = await repo.get(candidate_id)
    if candidate.get("status") == "deleted":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kandidat sudah dihapus.")
    assert_deletable(candidate.get("stage_status"))

    before, after = await repo.update(candidate_id, {"status": "deleted"}, ctx.user_id)
    await _add_history(
        ctx, candidate_id, "delete", candidate.get("stage_status"), candidate.get("stage_status"),
        "Kandidat dihapus (soft-delete)",
    )
    await log_action(
        ctx, "delete", RESOURCE, candidate_id, candidate.get("full_name"),
        before=before, after=after, module=MODULE,
    )
    return {"message": f"Kandidat '{candidate.get('full_name')}' berhasil dihapus."}


# --------------------------------------------------------------------------
# proses: status & screening
# --------------------------------------------------------------------------
@router.post("/candidates/{candidate_id}/status")
async def change_stage(
    candidate_id: str, payload: CandidateStageChange, ctx: AuthContext = Depends(_perm("edit"))
):
    repo = TenantRepository("candidates", ctx.company_id)
    candidate = await repo.get(candidate_id)
    if candidate.get("status") == "deleted":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kandidat sudah dihapus.")
    current = candidate.get("stage_status") or "draft"
    target = payload.stage_status
    assert_transition(current, target, via_endpoint=False)

    before, after = await repo.update(
        candidate_id, {"stage_status": target, "stage_changed_at": now()}, ctx.user_id
    )
    await _add_history(ctx, candidate_id, "status_change", current, target, payload.notes)
    await log_action(
        ctx, "status_change", RESOURCE, candidate_id, candidate.get("full_name"),
        before={"stage_status": current}, after={"stage_status": target},
        module=MODULE, notes=payload.notes,
    )
    return (await _enrich(ctx.company_id, [serialize(after)]))[0]


@router.post("/candidates/{candidate_id}/screening")
async def submit_screening(
    candidate_id: str, payload: CandidateScreening, ctx: AuthContext = Depends(_perm("edit"))
):
    repo = TenantRepository("candidates", ctx.company_id)
    candidate = await repo.get(candidate_id)
    if candidate.get("status") == "deleted":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kandidat sudah dihapus.")
    current = candidate.get("stage_status") or "draft"
    if current != "screening":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Screening hanya dapat diisi saat kandidat berstatus 'Screening' (saat ini: '{stage_label(current)}'). "
            "Mulai screening terlebih dahulu.",
        )
    result = SCREENING_RESULTS.get(payload.screening_result)
    if not result:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Hasil screening harus 'passed' atau 'failed'.")
    if payload.screening_recommendation and payload.screening_recommendation not in SCREENING_RECOMMENDATIONS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Rekomendasi screening tidak dikenal.")
    target = result["to_stage"]
    assert_transition(current, target, via_endpoint=True)

    patch = {
        "screening_result": payload.screening_result,
        "screening_score": payload.screening_score,
        "screening_notes": payload.screening_notes,
        "screening_recommendation": payload.screening_recommendation,
        "screened_by": ctx.user_id,
        "screened_by_name": ctx.user.get("full_name"),
        "screened_at": now(),
        "stage_status": target,
        "stage_changed_at": now(),
    }
    before, after = await repo.update(candidate_id, patch, ctx.user_id)
    summary_note = f"Hasil: {result['label']}"
    if payload.screening_score is not None:
        summary_note += f" · Skor {payload.screening_score}"
    if payload.screening_notes:
        summary_note += f" · {payload.screening_notes}"
    await _add_history(ctx, candidate_id, "screening", current, target, summary_note)
    await log_action(
        ctx, "screening", RESOURCE, candidate_id, candidate.get("full_name"),
        before=before, after=after, module=MODULE, notes=summary_note,
    )
    return (await _enrich(ctx.company_id, [serialize(after)]))[0]


@router.get("/candidates/{candidate_id}/history")
async def candidate_history(candidate_id: str, ctx: AuthContext = Depends(_perm("view"))):
    repo = TenantRepository("candidates", ctx.company_id)
    await repo.get(candidate_id)  # 404 bila bukan milik tenant aktif
    return {"items": await _history_for(ctx.company_id, candidate_id)}
