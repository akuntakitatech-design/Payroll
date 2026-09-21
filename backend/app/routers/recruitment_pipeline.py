"""Modul Rekrutmen V1 — Tahap B (interview, approval, offering).

Dibangun di atas Tahap A (app/routers/recruitment.py) tanpa mengubahnya.
Semua query lewat TenantRepository / ctx.tdb (tenant-scoped, fail-closed).

Integritas / concurrency:
- Setiap perubahan state memakai ``find_one_and_update`` bersyarat
  (SELECT ... FOR UPDATE di dalam transaksi adapter). Bila filter state tidak
  cocok lagi (sudah diproses request lain), hasilnya None -> HTTP 409.
- Unique index: (company, candidate, round, step_order) untuk approval;
  (company, candidate, active_flag) untuk satu offering aktif.

Approval TIDAK memakai engine baru: konfigurasi dibaca dari
approval_workflows/approval_steps existing (document_kind="recruitment") dan
di-snapshot ke candidate_approvals saat submit. Tanpa workflow -> fail-closed.
"""
import asyncio
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status

from ..core.audit import log_action
from ..core.db import ASCENDING, DESCENDING, NO_ID, ReturnDocument, get_db, now, serialize, serialize_list
from ..core.deps import AuthContext
from ..core.recruitment_workflow import (
    APPROVAL_DECISIONS,
    INTERVIEW_ALLOWED_STAGES,
    INTERVIEW_MODES,
    INTERVIEW_RECOMMENDATIONS,
    INTERVIEW_RESULTS,
    INTERVIEW_STATUSES,
    INTERVIEW_TYPES,
    OFFER_STATUSES,
    OFFERING_ALLOWED_STAGES,
    SUPPORTED_APPROVER_TYPES,
    stage_label,
)
from ..core.repo import TenantRepository
from ..core.tenancy import get_tenant_db
from ..schemas import (
    ApprovalDecide,
    ApprovalSubmit,
    InterviewCancel,
    InterviewComplete,
    InterviewCreate,
    InterviewUpdate,
    OfferingCancel,
    OfferingCreate,
    OfferingRespond,
    OfferingUpdate,
)
from .recruitment import MODULE, _add_history, _enrich, _perm

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/recruitment", tags=["Rekrutmen — Proses"])

RES_INTERVIEW = "candidate_interview"
RES_APPROVAL = "candidate_approval"
RES_OFFERING = "candidate_offering"

OFFERING_REF_FIELDS: Dict[str, tuple] = {
    "position_id": ("positions", "Jabatan"),
    "department_id": ("departments", "Departemen"),
    "work_location_id": ("work_locations", "Lokasi kerja"),
    "project_id": ("projects", "Proyek"),
    "employment_status_id": ("employment_statuses", "Status kepegawaian"),
}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")


# --------------------------------------------------------------------------
# helpers umum
# --------------------------------------------------------------------------
def _conflict(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, msg)


def _invalid(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, msg)


async def _get_candidate(ctx: AuthContext, candidate_id: str) -> Dict[str, Any]:
    repo = TenantRepository("candidates", ctx.company_id)
    candidate = await repo.get(candidate_id)  # 404 bila bukan milik tenant aktif
    if candidate.get("status") == "deleted":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kandidat sudah dihapus.")
    return candidate


async def _claim_stage(
    ctx: AuthContext,
    candidate_id: str,
    expected: Any,
    target: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Ubah stage kandidat secara atomik hanya bila stage saat ini == expected.
    expected boleh string atau {"$in": [...]}. None -> 409."""
    db = ctx.tdb  # tenant-scoped
    patch = {"stage_status": target, "stage_changed_at": now(), "updated_at": now(), "updated_by": ctx.user_id}
    if extra:
        patch.update(extra)
    after = await db.candidates.find_one_and_update(
        {"company_id": ctx.company_id, "id": candidate_id, "stage_status": expected, "status": {"$ne": "deleted"}},
        {"$set": patch},
        projection=NO_ID,
        return_document=ReturnDocument.AFTER,
    )
    if not after:
        raise _conflict(
            "Status kandidat sudah berubah oleh proses lain. Muat ulang halaman lalu coba lagi."
        )
    return serialize(after)


def _validate_date(value: Optional[str], label: str, required: bool = False) -> None:
    if value in (None, ""):
        if required:
            raise _invalid(f"{label} wajib diisi (format YYYY-MM-DD).")
        return
    if not DATE_RE.match(str(value)):
        raise _invalid(f"{label} harus berformat YYYY-MM-DD.")


def _validate_time(value: Optional[str], label: str) -> None:
    if value in (None, ""):
        return
    if not TIME_RE.match(str(value)):
        raise _invalid(f"{label} harus berformat HH:MM.")


async def _label_map(company_id: str, collection: str, ids: List[str]) -> Dict[str, str]:
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    db = get_tenant_db(company_id)  # tenant-scoped
    rows = await db[collection].find({"company_id": company_id, "id": {"$in": ids}}, NO_ID).to_list(1000)
    return {r["id"]: r.get("name") or r.get("code") for r in rows}


# --------------------------------------------------------------------------
# INTERVIEWER (reuse users existing + peran per perusahaan)
# --------------------------------------------------------------------------
async def _company_users(company_id: str) -> List[Dict[str, Any]]:
    """Pengguna yang mempunyai peran pada perusahaan aktif (user_company_roles)."""
    db = get_db()
    roles = await db.user_company_roles.find({"company_id": company_id}, NO_ID).to_list(5000)
    by_user: Dict[str, List[str]] = {}
    for r in roles:
        by_user.setdefault(r["user_id"], []).append(r.get("role_key"))
    if not by_user:
        return []
    users = await db.users.find(
        {"id": {"$in": list(by_user.keys())}, "status": {"$ne": "deleted"}}, NO_ID
    ).sort("full_name", ASCENDING).to_list(5000)
    # jabatan dari data karyawan (employees.user_id) bila tersedia, tanpa master baru
    tdb = get_tenant_db(company_id)  # tenant-scoped
    employees = await tdb.employees.find(
        {"company_id": company_id, "user_id": {"$in": list(by_user.keys())}, "status": {"$ne": "deleted"}}, NO_ID
    ).to_list(5000)
    pos_names = await _label_map(company_id, "positions", [e.get("position_id") for e in employees])
    emp_by_user = {e["user_id"]: e for e in employees if e.get("user_id")}
    out = []
    for u in users:
        emp = emp_by_user.get(u["id"]) or {}
        title = pos_names.get(emp.get("position_id")) or emp.get("job_title") or u.get("job_title")
        out.append(
            {
                "id": u["id"],
                "full_name": u.get("full_name"),
                "email": u.get("email"),
                "job_title": title,
                "position_id": emp.get("position_id"),
                "employee_id": emp.get("id"),
                "role_keys": sorted(set(by_user.get(u["id"], []))),
            }
        )
    return out


async def _interviewer_info(company_id: str, user_id: str) -> Dict[str, Any]:
    for u in await _company_users(company_id):
        if u["id"] == user_id:
            return u
    raise _invalid("Interviewer yang dipilih tidak terdaftar pada perusahaan aktif Anda.")


@router.get("/interviewers")
async def list_interviewers(ctx: AuthContext = Depends(_perm("view"))):
    return {"items": await _company_users(ctx.company_id)}


# --------------------------------------------------------------------------
# INTERVIEW
# --------------------------------------------------------------------------
def _decorate_interview(item: Dict[str, Any]) -> Dict[str, Any]:
    st = INTERVIEW_STATUSES.get(item.get("interview_status") or "", {})
    item["interview_status_label"] = st.get("label", item.get("interview_status"))
    item["interview_status_tone"] = st.get("tone", "neutral")
    res = INTERVIEW_RESULTS.get(item.get("result") or "", {})
    item["result_label"] = res.get("label")
    item["result_tone"] = res.get("tone")
    item["recommendation_label"] = INTERVIEW_RECOMMENDATIONS.get(item.get("recommendation") or "")
    if not item.get("interview_type_label"):
        item["interview_type_label"] = next(
            (t["label"] for t in INTERVIEW_TYPES if t["key"] == item.get("interview_type")), item.get("interview_type")
        )
    item["interview_mode_label"] = next(
        (m["label"] for m in INTERVIEW_MODES if m["key"] == item.get("interview_mode")), item.get("interview_mode")
    )
    item["can_edit"] = item.get("interview_status") == "scheduled"
    item["can_complete"] = item.get("interview_status") == "scheduled"
    item["can_cancel"] = item.get("interview_status") == "scheduled"
    return item


async def _interviews_for(company_id: str, candidate_id: str) -> List[Dict[str, Any]]:
    db = get_tenant_db(company_id)  # tenant-scoped
    rows = await db.candidate_interviews.find(
        {"company_id": company_id, "candidate_id": candidate_id, "status": {"$ne": "deleted"}}, NO_ID
    ).sort([("sequence", ASCENDING), ("created_at", ASCENDING)]).to_list(500)
    return [_decorate_interview(r) for r in serialize_list(rows)]


async def _recompute_interview_stage(ctx: AuthContext, candidate: Dict[str, Any], action: str, notes: str) -> Dict[str, Any]:
    """Stage kandidat mengikuti keadaan SELURUH interview aktif:
    ada yang terjadwal -> interview_scheduled; semua selesai -> interview_done;
    tidak ada interview aktif -> screening_passed."""
    current = candidate.get("stage_status")
    if current not in INTERVIEW_ALLOWED_STAGES:
        return candidate
    interviews = await _interviews_for(ctx.company_id, candidate["id"])
    active = [i for i in interviews if i.get("interview_status") != "cancelled"]
    if any(i.get("interview_status") == "scheduled" for i in active):
        target = "interview_scheduled"
    elif any(i.get("interview_status") == "completed" for i in active):
        target = "interview_done"
    else:
        target = "screening_passed"
    if target == current:
        return candidate
    after = await _claim_stage(ctx, candidate["id"], current, target)
    await _add_history(ctx, candidate["id"], action, current, target, notes)
    return after


def _clean_interview(data: Dict[str, Any]) -> Dict[str, Any]:
    type_keys = {t["key"] for t in INTERVIEW_TYPES}
    if "interview_type" in data and data["interview_type"] not in type_keys:
        raise _invalid("Jenis interview tidak dikenal.")
    if "interview_mode" in data and data["interview_mode"] not in {m["key"] for m in INTERVIEW_MODES}:
        raise _invalid("Metode interview harus 'onsite' atau 'online'.")
    _validate_date(data.get("scheduled_date"), "Tanggal interview", required="scheduled_date" in data)
    _validate_time(data.get("start_time"), "Jam mulai")
    _validate_time(data.get("end_time"), "Jam selesai")
    if data.get("start_time") and data.get("end_time") and data["end_time"] <= data["start_time"]:
        raise _invalid("Jam selesai harus setelah jam mulai.")
    if data.get("interview_type") and data["interview_type"] != "other":
        data["interview_type_label"] = next(t["label"] for t in INTERVIEW_TYPES if t["key"] == data["interview_type"])
    elif data.get("interview_type") == "other" and not (data.get("interview_type_label") or "").strip():
        raise _invalid("Isi nama jenis interview untuk tipe 'Lainnya'.")
    return data


@router.get("/candidates/{candidate_id}/interviews")
async def list_interviews(candidate_id: str, ctx: AuthContext = Depends(_perm("view"))):
    await _get_candidate(ctx, candidate_id)
    return {"items": await _interviews_for(ctx.company_id, candidate_id)}


@router.post("/candidates/{candidate_id}/interviews", status_code=status.HTTP_201_CREATED)
async def schedule_interview(
    candidate_id: str, payload: InterviewCreate, ctx: AuthContext = Depends(_perm("create"))
):
    candidate = await _get_candidate(ctx, candidate_id)
    current = candidate.get("stage_status")
    if current not in INTERVIEW_ALLOWED_STAGES:
        raise _invalid(
            f"Interview hanya dapat dijadwalkan setelah kandidat lolos screening (saat ini: '{stage_label(current)}')."
        )
    data = _clean_interview(payload.model_dump(exclude_none=True))
    interviewer = await _interviewer_info(ctx.company_id, data["interviewer_user_id"])
    data["interviewer_name"] = interviewer.get("full_name")
    data["interviewer_title"] = interviewer.get("job_title")
    repo = TenantRepository("candidate_interviews", ctx.company_id)
    existing = await repo.count({"candidate_id": candidate_id, "status": {"$ne": "deleted"}})
    data["candidate_id"] = candidate_id
    data["sequence"] = existing + 1
    data["interview_status"] = "scheduled"
    created = await repo.create(data, ctx.user_id)

    if current != "interview_scheduled":
        await _claim_stage(ctx, candidate_id, current, "interview_scheduled")
        await _add_history(
            ctx, candidate_id, "interview_scheduled", current, "interview_scheduled",
            f"{data.get('interview_type_label')} dijadwalkan {data['scheduled_date']} · {interviewer.get('full_name')}",
        )
    await log_action(
        ctx, "interview_schedule", RES_INTERVIEW, created["id"], candidate.get("full_name"),
        after=created, module=MODULE,
        notes=f"{data.get('interview_type_label')} · {data['scheduled_date']} · {interviewer.get('full_name')}",
    )
    return _decorate_interview(serialize(created))


async def _get_interview(ctx: AuthContext, interview_id: str) -> Dict[str, Any]:
    repo = TenantRepository("candidate_interviews", ctx.company_id)
    item = await repo.get(interview_id)  # 404 lintas tenant
    if item.get("status") == "deleted":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview tidak ditemukan.")
    return item


@router.put("/interviews/{interview_id}")
async def update_interview(interview_id: str, payload: InterviewUpdate, ctx: AuthContext = Depends(_perm("edit"))):
    item = await _get_interview(ctx, interview_id)
    if item.get("interview_status") != "scheduled":
        raise _conflict("Hanya interview berstatus Terjadwal yang dapat diubah / dijadwalkan ulang.")
    data = payload.model_dump(exclude_unset=True)
    data = {k: v for k, v in data.items() if v is not None}
    if not data:
        return _decorate_interview(serialize(item))
    data = _clean_interview(data)
    merged = {**item, **data}
    if merged.get("start_time") and merged.get("end_time") and merged["end_time"] <= merged["start_time"]:
        raise _invalid("Jam selesai harus setelah jam mulai.")
    if data.get("interviewer_user_id"):
        interviewer = await _interviewer_info(ctx.company_id, data["interviewer_user_id"])
        data["interviewer_name"] = interviewer.get("full_name")
        data["interviewer_title"] = interviewer.get("job_title")
    repo = TenantRepository("candidate_interviews", ctx.company_id)
    before, after = await repo.update(interview_id, data, ctx.user_id)
    candidate = await _get_candidate(ctx, item["candidate_id"])
    rescheduled = "scheduled_date" in data and data["scheduled_date"] != before.get("scheduled_date")
    await log_action(
        ctx, "interview_update", RES_INTERVIEW, interview_id, candidate.get("full_name"),
        before=before, after=after, module=MODULE,
        notes=("Reschedule ke " + data["scheduled_date"]) if rescheduled else None,
    )
    return _decorate_interview(serialize(after))


@router.post("/interviews/{interview_id}/complete")
async def complete_interview(interview_id: str, payload: InterviewComplete, ctx: AuthContext = Depends(_perm("edit"))):
    item = await _get_interview(ctx, interview_id)
    if payload.result not in INTERVIEW_RESULTS:
        raise _invalid("Hasil interview harus 'passed', 'considered', atau 'failed'.")
    if payload.recommendation and payload.recommendation not in INTERVIEW_RECOMMENDATIONS:
        raise _invalid("Rekomendasi interview tidak dikenal.")
    candidate = await _get_candidate(ctx, item["candidate_id"])
    db = ctx.tdb  # tenant-scoped
    after = await db.candidate_interviews.find_one_and_update(
        {"company_id": ctx.company_id, "id": interview_id, "interview_status": "scheduled"},
        {
            "$set": {
                "interview_status": "completed",
                "result": payload.result,
                "score": payload.score,
                "recommendation": payload.recommendation,
                "interviewer_notes": payload.interviewer_notes,
                "completed_at": now(),
                "completed_by": ctx.user_id,
                "updated_at": now(),
                "updated_by": ctx.user_id,
            }
        },
        projection=NO_ID,
        return_document=ReturnDocument.AFTER,
    )
    if not after:
        raise _conflict("Interview ini sudah diselesaikan atau dibatalkan sebelumnya.")
    label = INTERVIEW_RESULTS[payload.result]["label"]
    note = f"{after.get('interview_type_label')} selesai · Hasil: {label}"
    if payload.score is not None:
        note += f" · Skor {payload.score}"
    await _recompute_interview_stage(ctx, candidate, "interview_completed", note)
    await log_action(
        ctx, "interview_complete", RES_INTERVIEW, interview_id, candidate.get("full_name"),
        before=item, after=after, module=MODULE, notes=note,
    )
    return _decorate_interview(serialize(after))


async def _cancel_interview(ctx: AuthContext, interview_id: str, reason: Optional[str]) -> Dict[str, Any]:
    item = await _get_interview(ctx, interview_id)
    if item.get("interview_status") == "completed":
        raise _conflict("Interview yang sudah selesai tidak dapat dibatalkan atau dihapus (jejak seleksi dipertahankan).")
    candidate = await _get_candidate(ctx, item["candidate_id"])
    db = ctx.tdb  # tenant-scoped
    after = await db.candidate_interviews.find_one_and_update(
        {"company_id": ctx.company_id, "id": interview_id, "interview_status": "scheduled"},
        {"$set": {
            "interview_status": "cancelled", "cancel_reason": reason, "cancelled_at": now(),
            "cancelled_by": ctx.user_id, "updated_at": now(), "updated_by": ctx.user_id,
        }},
        projection=NO_ID,
        return_document=ReturnDocument.AFTER,
    )
    if not after:
        raise _conflict("Interview ini sudah dibatalkan sebelumnya.")
    note = f"{after.get('interview_type_label')} dibatalkan" + (f" · {reason}" if reason else "")
    await _recompute_interview_stage(ctx, candidate, "interview_cancelled", note)
    await log_action(
        ctx, "interview_cancel", RES_INTERVIEW, interview_id, candidate.get("full_name"),
        before=item, after=after, module=MODULE, notes=note,
    )
    return _decorate_interview(serialize(after))


@router.post("/interviews/{interview_id}/cancel")
async def cancel_interview(interview_id: str, payload: InterviewCancel, ctx: AuthContext = Depends(_perm("edit"))):
    return await _cancel_interview(ctx, interview_id, payload.reason)


@router.delete("/interviews/{interview_id}")
async def delete_interview(interview_id: str, ctx: AuthContext = Depends(_perm("edit"))):
    """Pola aman: DELETE = batalkan (soft). Interview selesai tidak bisa dihapus."""
    item = await _cancel_interview(ctx, interview_id, "Dibatalkan oleh HR")
    return {"message": "Interview dibatalkan.", "item": item}


# --------------------------------------------------------------------------
# APPROVAL (reuse approval_workflows / approval_steps existing)
# --------------------------------------------------------------------------
async def _resolve_workflow(company_id: str) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    db = get_tenant_db(company_id)  # tenant-scoped
    workflows = await db.approval_workflows.find(
        {"company_id": company_id, "document_kind": "recruitment", "status": "active"}, NO_ID
    ).sort([("is_default", DESCENDING), ("created_at", ASCENDING)]).to_list(50)
    if not workflows:
        return None, []
    wf = workflows[0]
    steps = await db.approval_steps.find(
        {"company_id": company_id, "workflow_id": wf["id"], "status": {"$ne": "deleted"}}, NO_ID
    ).sort("step_order", ASCENDING).to_list(100)
    return serialize(wf), serialize_list(steps)


async def _approver_labels(company_id: str, steps: List[Dict[str, Any]]) -> Dict[str, str]:
    """Label penyetuju untuk snapshot/UI: nama peran, nama pengguna, atau nama jabatan."""
    db = get_db()
    role_keys = [s.get("approver_role_key") for s in steps if s.get("approver_type") == "role"]
    user_ids = [s.get("approver_user_id") for s in steps if s.get("approver_type") == "user"]
    pos_ids = [s.get("approver_position_id") for s in steps if s.get("approver_type") == "position"]
    roles, users, positions = await asyncio.gather(
        db.roles.find({"key": {"$in": [k for k in role_keys if k]}}, NO_ID).to_list(100) if role_keys else asyncio.sleep(0, []),
        db.users.find({"id": {"$in": [u for u in user_ids if u]}}, NO_ID).to_list(100) if user_ids else asyncio.sleep(0, []),
        _label_map(company_id, "positions", pos_ids) if pos_ids else asyncio.sleep(0, {}),
    )
    role_names = {r["key"]: r.get("name") or r["key"] for r in (roles or [])}
    user_names = {u["id"]: u.get("full_name") or u.get("email") for u in (users or [])}
    out: Dict[str, str] = {}
    for s in steps:
        t = s.get("approver_type")
        if t == "role":
            out[s["id"]] = role_names.get(s.get("approver_role_key"), s.get("approver_role_key") or "-")
        elif t == "user":
            out[s["id"]] = user_names.get(s.get("approver_user_id"), "Pengguna")
        elif t == "position":
            out[s["id"]] = (positions or {}).get(s.get("approver_position_id"), "Jabatan")
        else:
            out[s["id"]] = s.get("approver_type") or "-"
    return out


async def _my_position_ids(ctx: AuthContext) -> List[str]:
    db = ctx.tdb  # tenant-scoped
    rows = await db.employees.find(
        {"company_id": ctx.company_id, "user_id": ctx.user_id, "status": {"$ne": "deleted"}}, NO_ID
    ).to_list(10)
    return [r.get("position_id") for r in rows if r.get("position_id")]


async def _is_step_approver(ctx: AuthContext, step: Dict[str, Any], my_positions: Optional[List[str]] = None) -> bool:
    """Cocokkan pengguna dengan approver step: peran pada perusahaan aktif,
    pengguna tertentu, atau jabatan (lewat employees.user_id). Wildcard permission
    TIDAK membuat pengguna menjadi approver."""
    t = step.get("approver_type")
    if t == "role":
        return bool(step.get("approver_role_key")) and step["approver_role_key"] in (ctx.role_keys or [])
    if t == "user":
        return step.get("approver_user_id") == ctx.user_id
    if t == "position":
        positions = my_positions if my_positions is not None else await _my_position_ids(ctx)
        return bool(step.get("approver_position_id")) and step["approver_position_id"] in positions
    return False


async def _approval_rows(company_id: str, candidate_id: str) -> List[Dict[str, Any]]:
    db = get_tenant_db(company_id)  # tenant-scoped
    rows = await db.candidate_approvals.find(
        {"company_id": company_id, "candidate_id": candidate_id}, NO_ID
    ).sort([("approval_round", ASCENDING), ("step_order", ASCENDING)]).to_list(500)
    return serialize_list(rows)


async def _approval_state(ctx: AuthContext, candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Status approval kandidat untuk UI: workflow tersedia?, ronde, langkah, aksi saya."""
    cid = ctx.company_id
    (wf, steps), rows, my_positions = await asyncio.gather(
        _resolve_workflow(cid), _approval_rows(cid, candidate["id"]), _my_position_ids(ctx)
    )
    stage = candidate.get("stage_status")
    current_round = int(candidate.get("approval_round") or 0)

    rounds: Dict[int, List[Dict[str, Any]]] = {}
    for r in rows:
        rounds.setdefault(int(r.get("approval_round") or 1), []).append(r)

    actionable_id = None
    for rnd, items in rounds.items():
        prev_ok = True
        for it in items:
            d = APPROVAL_DECISIONS.get(it.get("decision") or "pending", {})
            it["decision_label"] = d.get("label", it.get("decision"))
            it["decision_tone"] = d.get("tone", "neutral")
            it["is_current"] = (
                rnd == current_round and stage == "awaiting_approval" and it.get("decision") == "pending" and prev_ok
            )
            it["i_am_approver"] = await _is_step_approver(ctx, it, my_positions)
            it["can_decide"] = bool(it["is_current"] and it["i_am_approver"] and ctx.has_permission("recruitment", "approve"))
            if it["can_decide"] and not actionable_id:
                actionable_id = it["id"]
            if it.get("decision") != "approved":
                prev_ok = False

    # kelayakan submit (untuk pesan UI; validasi ulang dilakukan saat submit)
    reasons: List[str] = []
    if stage != "interview_done":
        reasons.append(f"Kandidat harus berstatus 'Interview Selesai' (saat ini: '{stage_label(stage)}').")
    if not wf:
        reasons.append("Workflow approval Recruitment belum dikonfigurasi.")
    elif not steps:
        reasons.append("Workflow approval Recruitment belum memiliki tahap penyetuju.")
    else:
        bad = [s for s in steps if s.get("approver_type") not in SUPPORTED_APPROVER_TYPES]
        if bad:
            reasons.append(
                "Tahap '" + bad[0].get("name", "") + "' memakai tipe penyetuju yang tidak berlaku untuk rekrutmen."
            )
    labels = await _approver_labels(cid, steps) if steps else {}
    return {
        "workflow_available": bool(wf and steps),
        "workflow": {
            "id": wf["id"], "code": wf.get("code"), "name": wf.get("name"),
            "steps": [
                {
                    "id": s["id"], "step_order": s.get("step_order"), "name": s.get("name"),
                    "approver_type": s.get("approver_type"), "approver_label": labels.get(s["id"]),
                    "is_mandatory": s.get("is_mandatory", True),
                }
                for s in steps
            ],
        } if wf else None,
        "can_submit": not reasons and ctx.has_permission("recruitment", "edit"),
        "submit_blockers": reasons,
        "current_round": current_round,
        "rounds": [{"round": rnd, "steps": items} for rnd, items in sorted(rounds.items())],
        "actionable_step_id": actionable_id,
        "config_route": "/setup/approval-workflows",
    }


@router.get("/candidates/{candidate_id}/approvals")
async def list_approvals(candidate_id: str, ctx: AuthContext = Depends(_perm("view"))):
    candidate = await _get_candidate(ctx, candidate_id)
    return await _approval_state(ctx, candidate)


@router.post("/candidates/{candidate_id}/submit-approval")
async def submit_approval(candidate_id: str, payload: ApprovalSubmit, ctx: AuthContext = Depends(_perm("edit"))):
    candidate = await _get_candidate(ctx, candidate_id)
    stage = candidate.get("stage_status")
    if stage != "interview_done":
        raise _invalid(
            "Kandidat hanya dapat diajukan approval setelah lolos screening dan seluruh interview selesai "
            f"(saat ini: '{stage_label(stage)}')."
        )
    interviews = await _interviews_for(ctx.company_id, candidate_id)
    if any(i.get("interview_status") == "scheduled" for i in interviews):
        raise _invalid("Masih ada interview terjadwal yang belum diselesaikan atau dibatalkan.")
    if not any(i.get("interview_status") == "completed" for i in interviews):
        raise _invalid("Minimal satu interview harus diselesaikan sebelum pengajuan approval.")

    wf, steps = await _resolve_workflow(ctx.company_id)
    if not wf or not steps:
        # FAIL-CLOSED: tidak ada fallback approver otomatis.
        raise _invalid(
            "Workflow approval Recruitment belum dikonfigurasi. Atur pada menu Alur Persetujuan "
            "(jenis dokumen: Rekrutmen) sebelum mengajukan kandidat."
        )
    for s in steps:
        if s.get("approver_type") not in SUPPORTED_APPROVER_TYPES:
            raise _invalid(
                f"Tahap '{s.get('name')}' memakai tipe penyetuju '{s.get('approver_type')}' yang tidak dapat "
                "dipetakan pada rekrutmen. Ubah konfigurasi workflow terlebih dahulu."
            )
    db = ctx.tdb  # tenant-scoped
    pending = await db.candidate_approvals.count_documents(
        {"company_id": ctx.company_id, "candidate_id": candidate_id, "decision": "pending"}
    )
    if pending:
        raise _conflict("Kandidat masih memiliki approval yang sedang berjalan.")

    new_round = int(candidate.get("approval_round") or 0) + 1
    # Klaim stage secara atomik -> mencegah submit ganda.
    await _claim_stage(ctx, candidate_id, "interview_done", "awaiting_approval", {"approval_round": new_round})

    labels = await _approver_labels(ctx.company_id, steps)
    repo = TenantRepository("candidate_approvals", ctx.company_id)
    created = []
    for s in steps:
        created.append(await repo.create(
            {
                "candidate_id": candidate_id,
                "approval_round": new_round,
                "workflow_id": wf["id"],
                "workflow_code": wf.get("code"),
                "workflow_name": wf.get("name"),
                "workflow_step_id": s["id"],
                "step_order": s.get("step_order"),
                "step_name": s.get("name"),
                "approver_type": s.get("approver_type"),
                "approver_role_key": s.get("approver_role_key"),
                "approver_user_id": s.get("approver_user_id"),
                "approver_position_id": s.get("approver_position_id"),
                "approver_label": labels.get(s["id"]),
                "is_mandatory": s.get("is_mandatory", True),
                "decision": "pending",
                "submitted_by": ctx.user_id,
                "submitted_at": now(),
                "notes": None,
            },
            ctx.user_id,
        ))
    note = f"Diajukan ke workflow {wf.get('name')} ({len(steps)} tahap)" + (f" · {payload.notes}" if payload.notes else "")
    await _add_history(ctx, candidate_id, "approval_submit", "interview_done", "awaiting_approval", note)
    await log_action(
        ctx, "approval_submit", RES_APPROVAL, candidate_id, candidate.get("full_name"),
        after={"round": new_round, "workflow_id": wf["id"], "steps": len(created)}, module=MODULE, notes=note,
    )
    return await _approval_state(ctx, await _get_candidate(ctx, candidate_id))


@router.post("/candidates/{candidate_id}/approvals/{approval_id}/decide")
async def decide_approval(
    candidate_id: str, approval_id: str, payload: ApprovalDecide, ctx: AuthContext = Depends(_perm("approve"))
):
    if payload.decision not in ("approved", "rejected"):
        raise _invalid("Keputusan harus 'approved' atau 'rejected'.")
    candidate = await _get_candidate(ctx, candidate_id)
    repo = TenantRepository("candidate_approvals", ctx.company_id)
    step = await repo.get(approval_id)  # 404 lintas tenant
    if step.get("candidate_id") != candidate_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tahap approval tidak ditemukan pada kandidat ini.")
    if candidate.get("stage_status") != "awaiting_approval":
        raise _conflict(f"Kandidat tidak sedang menunggu approval (status: '{stage_label(candidate.get('stage_status'))}').")
    if int(step.get("approval_round") or 0) != int(candidate.get("approval_round") or 0):
        raise _conflict("Tahap ini berasal dari ronde approval yang sudah tidak aktif.")
    if step.get("decision") != "pending":
        raise _conflict("Tahap approval ini sudah diputuskan.")

    rows = await _approval_rows(ctx.company_id, candidate_id)
    same_round = [r for r in rows if int(r.get("approval_round") or 0) == int(step.get("approval_round") or 0)]
    for r in same_round:
        if int(r.get("step_order") or 0) < int(step.get("step_order") or 0) and r.get("decision") != "approved":
            raise _invalid(
                f"Tahap '{r.get('step_name')}' (urutan {r.get('step_order')}) harus disetujui terlebih dahulu."
            )
    # Validasi approver: permission recruitment:approve saja tidak cukup.
    if not await _is_step_approver(ctx, step):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Anda bukan penyetuju tahap '{step.get('step_name')}' ({step.get('approver_label') or step.get('approver_type')}).",
        )

    db = ctx.tdb  # tenant-scoped
    after = await db.candidate_approvals.find_one_and_update(
        {"company_id": ctx.company_id, "id": approval_id, "decision": "pending"},
        {"$set": {
            "decision": payload.decision, "decided_by": ctx.user_id,
            "decided_by_name": ctx.user.get("full_name"), "decided_at": now(), "notes": payload.notes,
            "updated_at": now(), "updated_by": ctx.user_id,
        }},
        projection=NO_ID,
        return_document=ReturnDocument.AFTER,
    )
    if not after:
        raise _conflict("Tahap approval ini sudah diputuskan oleh proses lain.")

    step_note = f"Tahap {step.get('step_order')} · {step.get('step_name')}" + (f" · {payload.notes}" if payload.notes else "")
    if payload.decision == "rejected":
        await db.candidate_approvals.update_many(
            {"company_id": ctx.company_id, "candidate_id": candidate_id,
             "approval_round": step.get("approval_round"), "decision": "pending"},
            {"$set": {"decision": "skipped", "updated_at": now(), "updated_by": ctx.user_id}},
        )
        await _claim_stage(ctx, candidate_id, "awaiting_approval", "rejected", {"rejection_reason": payload.notes})
        await _add_history(ctx, candidate_id, "approval_rejected", "awaiting_approval", "rejected", "Ditolak pada " + step_note)
        await log_action(ctx, "reject", RES_APPROVAL, approval_id, candidate.get("full_name"),
                         before=step, after=after, module=MODULE, notes=step_note)
    else:
        remaining = await db.candidate_approvals.count_documents(
            {"company_id": ctx.company_id, "candidate_id": candidate_id,
             "approval_round": step.get("approval_round"), "decision": "pending"}
        )
        if remaining == 0:
            await _claim_stage(ctx, candidate_id, "awaiting_approval", "approved")
            await _add_history(ctx, candidate_id, "approval_approved", "awaiting_approval", "approved",
                               "Seluruh tahap approval disetujui · terakhir: " + step_note)
        await log_action(ctx, "approve", RES_APPROVAL, approval_id, candidate.get("full_name"),
                         before=step, after=after, module=MODULE, notes=step_note)
    return await _approval_state(ctx, await _get_candidate(ctx, candidate_id))


# --------------------------------------------------------------------------
# OFFERING
# --------------------------------------------------------------------------
async def _validate_offering_refs(company_id: str, data: Dict[str, Any]) -> None:
    db = get_tenant_db(company_id)  # tenant-scoped
    for field, (collection, label) in OFFERING_REF_FIELDS.items():
        value = data.get(field)
        if not value:
            continue
        exists = await db[collection].count_documents(
            {"company_id": company_id, "id": value, "status": {"$ne": "deleted"}}
        )
        if not exists:
            raise _invalid(f"{label} yang dipilih tidak ditemukan pada perusahaan aktif Anda.")


def _clean_offering(data: Dict[str, Any]) -> Dict[str, Any]:
    _validate_date(data.get("start_date"), "Tanggal mulai kerja")
    allowances = data.get("allowances")
    if allowances is not None:
        cleaned = []
        for a in allowances:
            name = str((a or {}).get("name") or "").strip()
            try:
                amount = float((a or {}).get("amount") or 0)
            except (TypeError, ValueError):
                raise _invalid("Nominal tunjangan harus berupa angka.")
            if not name:
                raise _invalid("Nama tunjangan wajib diisi.")
            if amount < 0:
                raise _invalid("Nominal tunjangan tidak boleh negatif.")
            cleaned.append({"name": name, "amount": amount})
        data["allowances"] = cleaned
    return data


async def _decorate_offerings(company_id: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not items:
        return items
    maps = dict(zip(
        OFFERING_REF_FIELDS.keys(),
        await asyncio.gather(*[
            _label_map(company_id, coll, [i.get(field) for i in items])
            for field, (coll, _l) in OFFERING_REF_FIELDS.items()
        ]),
    ))
    for it in items:
        for field in OFFERING_REF_FIELDS:
            it[f"{field[:-3]}_name"] = maps[field].get(it.get(field))
        st = OFFER_STATUSES.get(it.get("offer_status") or "", {})
        it["offer_status_label"] = st.get("label", it.get("offer_status"))
        it["offer_status_tone"] = st.get("tone", "neutral")
        it["total_allowances"] = float(sum((a.get("amount") or 0) for a in (it.get("allowances") or [])))
        it["is_active"] = it.get("active_flag") == 1
        it["can_edit"] = it.get("offer_status") == "draft"
        it["can_send"] = it.get("offer_status") == "draft"
        it["can_respond"] = it.get("offer_status") == "sent"
        it["can_cancel"] = it.get("offer_status") in ("draft", "sent")
    return items


async def _offerings_for(company_id: str, candidate_id: str) -> List[Dict[str, Any]]:
    db = get_tenant_db(company_id)  # tenant-scoped
    rows = await db.candidate_offerings.find(
        {"company_id": company_id, "candidate_id": candidate_id, "status": {"$ne": "deleted"}}, NO_ID
    ).sort([("version", DESCENDING)]).to_list(100)
    return await _decorate_offerings(company_id, serialize_list(rows))


def _offering_blockers(candidate: Dict[str, Any], offerings: List[Dict[str, Any]]) -> List[str]:
    reasons = []
    stage = candidate.get("stage_status")
    if stage not in OFFERING_ALLOWED_STAGES:
        if stage in ("offering", "offering_accepted"):
            reasons.append("Kandidat sudah memiliki offering aktif.")
        else:
            reasons.append(f"Offering hanya dapat dibuat setelah kandidat disetujui (saat ini: '{stage_label(stage)}').")
    if any(o.get("is_active") for o in offerings):
        reasons.append("Masih ada offering aktif; batalkan atau selesaikan terlebih dahulu.")
    return reasons


@router.get("/candidates/{candidate_id}/offerings")
async def list_offerings(candidate_id: str, ctx: AuthContext = Depends(_perm("view"))):
    candidate = await _get_candidate(ctx, candidate_id)
    items = await _offerings_for(ctx.company_id, candidate_id)
    blockers = _offering_blockers(candidate, items)
    return {
        "items": items,
        "active": next((o for o in items if o.get("is_active")), None),
        "can_create": not blockers and ctx.has_permission("recruitment", "create"),
        "create_blockers": blockers,
    }


async def _get_offering(ctx: AuthContext, offering_id: str) -> Dict[str, Any]:
    repo = TenantRepository("candidate_offerings", ctx.company_id)
    item = await repo.get(offering_id)  # 404 lintas tenant
    if item.get("status") == "deleted":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Offering tidak ditemukan.")
    return item


@router.post("/candidates/{candidate_id}/offering", status_code=status.HTTP_201_CREATED)
async def create_offering(candidate_id: str, payload: OfferingCreate, ctx: AuthContext = Depends(_perm("create"))):
    candidate = await _get_candidate(ctx, candidate_id)
    existing = await _offerings_for(ctx.company_id, candidate_id)
    blockers = _offering_blockers(candidate, existing)
    if blockers:
        raise HTTPException(status.HTTP_409_CONFLICT if "aktif" in blockers[0] else status.HTTP_422_UNPROCESSABLE_ENTITY, blockers[0])
    data = _clean_offering(payload.model_dump(exclude_none=True))
    # default dari data kandidat (tanpa input ulang)
    for field in ("position_id", "department_id", "work_location_id", "project_id"):
        data.setdefault(field, candidate.get(field))
    data = {k: v for k, v in data.items() if v not in (None, "")}
    await _validate_offering_refs(ctx.company_id, data)
    data["candidate_id"] = candidate_id
    data["version"] = len(existing) + 1
    data["active_flag"] = 1  # unique index menjamin satu offering aktif
    data["offer_status"] = "draft"
    repo = TenantRepository("candidate_offerings", ctx.company_id)
    created = await repo.create(data, ctx.user_id)  # IntegrityError -> 409 oleh adapter
    await log_action(ctx, "offering_create", RES_OFFERING, created["id"], candidate.get("full_name"),
                     after=created, module=MODULE, notes=f"Offering v{data['version']} (draft)")
    return (await _decorate_offerings(ctx.company_id, [serialize(created)]))[0]


@router.put("/offerings/{offering_id}")
async def update_offering(offering_id: str, payload: OfferingUpdate, ctx: AuthContext = Depends(_perm("edit"))):
    item = await _get_offering(ctx, offering_id)
    if item.get("offer_status") != "draft":
        raise _conflict("Hanya offering berstatus Draft yang dapat diubah. Batalkan dan buat versi baru bila perlu.")
    data = _clean_offering({k: v for k, v in payload.model_dump(exclude_unset=True).items()})
    if not data:
        return (await _decorate_offerings(ctx.company_id, [serialize(item)]))[0]
    await _validate_offering_refs(ctx.company_id, data)
    repo = TenantRepository("candidate_offerings", ctx.company_id)
    before, after = await repo.update(offering_id, data, ctx.user_id)
    candidate = await _get_candidate(ctx, item["candidate_id"])
    await log_action(ctx, "offering_update", RES_OFFERING, offering_id, candidate.get("full_name"),
                     before=before, after=after, module=MODULE)
    return (await _decorate_offerings(ctx.company_id, [serialize(after)]))[0]


@router.post("/offerings/{offering_id}/send")
async def send_offering(offering_id: str, ctx: AuthContext = Depends(_perm("edit"))):
    item = await _get_offering(ctx, offering_id)
    if item.get("offer_status") != "draft":
        raise _conflict("Hanya offering Draft yang dapat dikirim.")
    candidate = await _get_candidate(ctx, item["candidate_id"])
    stage = candidate.get("stage_status")
    if stage not in OFFERING_ALLOWED_STAGES:
        raise _invalid(f"Offering tidak dapat dikirim pada status kandidat '{stage_label(stage)}'.")
    if not item.get("start_date") or item.get("basic_salary") in (None, 0):
        raise _invalid("Lengkapi tanggal mulai kerja dan gaji pokok sebelum offering dikirim.")
    db = ctx.tdb  # tenant-scoped
    # 1) klaim stage kandidat (approved|offering_declined -> offering)
    await _claim_stage(ctx, candidate["id"], {"$in": sorted(OFFERING_ALLOWED_STAGES)}, "offering")
    # 2) klaim offering draft -> sent
    after = await db.candidate_offerings.find_one_and_update(
        {"company_id": ctx.company_id, "id": offering_id, "offer_status": "draft"},
        {"$set": {"offer_status": "sent", "offered_at": now(), "offered_by": ctx.user_id,
                  "updated_at": now(), "updated_by": ctx.user_id}},
        projection=NO_ID,
        return_document=ReturnDocument.AFTER,
    )
    if not after:
        # kembalikan stage agar konsisten (offering sudah bukan draft)
        await _claim_stage(ctx, candidate["id"], "offering", stage)
        raise _conflict("Offering ini sudah dikirim atau dibatalkan oleh proses lain.")
    note = f"Offering v{item.get('version')} dikirim ke kandidat"
    await _add_history(ctx, candidate["id"], "offering_sent", stage, "offering", note)
    await log_action(ctx, "offering_send", RES_OFFERING, offering_id, candidate.get("full_name"),
                     before=item, after=after, module=MODULE, notes=note)
    return (await _decorate_offerings(ctx.company_id, [serialize(after)]))[0]


@router.post("/offerings/{offering_id}/respond")
async def respond_offering(offering_id: str, payload: OfferingRespond, ctx: AuthContext = Depends(_perm("edit"))):
    if payload.response not in ("accepted", "declined"):
        raise _invalid("Respons harus 'accepted' atau 'declined'.")
    _validate_date(payload.responded_at, "Tanggal respons")
    item = await _get_offering(ctx, offering_id)
    if item.get("offer_status") != "sent":
        raise _conflict("Respons hanya dapat dicatat untuk offering yang sudah dikirim.")
    candidate = await _get_candidate(ctx, item["candidate_id"])
    if candidate.get("stage_status") != "offering":
        raise _conflict(f"Kandidat tidak berada pada tahap Offering (status: '{stage_label(candidate.get('stage_status'))}').")
    db = ctx.tdb  # tenant-scoped
    patch: Dict[str, Any] = {
        "offer_status": payload.response, "responded_at": now(), "responded_by": ctx.user_id,
        "response_notes": payload.response_notes, "updated_at": now(), "updated_by": ctx.user_id,
    }
    if payload.responded_at:
        patch["response_date"] = payload.responded_at
    if payload.response == "declined":
        patch["active_flag"] = None  # lepaskan slot offering aktif agar versi baru bisa dibuat
    after = await db.candidate_offerings.find_one_and_update(
        {"company_id": ctx.company_id, "id": offering_id, "offer_status": "sent"},
        {"$set": patch},
        projection=NO_ID,
        return_document=ReturnDocument.AFTER,
    )
    if not after:
        raise _conflict("Respons offering ini sudah dicatat sebelumnya.")
    target = "offering_accepted" if payload.response == "accepted" else "offering_declined"
    await _claim_stage(ctx, candidate["id"], "offering", target)
    label = OFFER_STATUSES[payload.response]["label"]
    note = f"Offering v{item.get('version')} {label.lower()} oleh kandidat" + (f" · {payload.response_notes}" if payload.response_notes else "")
    await _add_history(ctx, candidate["id"], f"offering_{payload.response}", "offering", target, note)
    action = "offering_accept" if payload.response == "accepted" else "offering_decline"
    await log_action(ctx, action, RES_OFFERING, offering_id, candidate.get("full_name"),
                     before=item, after=after, module=MODULE, notes=note)
    return (await _decorate_offerings(ctx.company_id, [serialize(after)]))[0]


@router.post("/offerings/{offering_id}/cancel")
async def cancel_offering(offering_id: str, payload: OfferingCancel, ctx: AuthContext = Depends(_perm("edit"))):
    item = await _get_offering(ctx, offering_id)
    if item.get("offer_status") not in ("draft", "sent"):
        raise _conflict("Hanya offering Draft atau Terkirim yang dapat dibatalkan.")
    candidate = await _get_candidate(ctx, item["candidate_id"])
    db = ctx.tdb  # tenant-scoped
    after = await db.candidate_offerings.find_one_and_update(
        {"company_id": ctx.company_id, "id": offering_id, "offer_status": {"$in": ["draft", "sent"]}},
        {"$set": {"offer_status": "cancelled", "active_flag": None, "cancelled_at": now(),
                  "cancelled_by": ctx.user_id, "cancel_reason": payload.reason,
                  "updated_at": now(), "updated_by": ctx.user_id}},
        projection=NO_ID,
        return_document=ReturnDocument.AFTER,
    )
    if not after:
        raise _conflict("Offering ini sudah tidak dapat dibatalkan.")
    note = f"Offering v{item.get('version')} dibatalkan" + (f" · {payload.reason}" if payload.reason else "")
    if item.get("offer_status") == "sent" and candidate.get("stage_status") == "offering":
        # offering terkirim dibatalkan -> kandidat kembali ke Disetujui
        await _claim_stage(ctx, candidate["id"], "offering", "approved")
        await _add_history(ctx, candidate["id"], "offering_cancelled", "offering", "approved", note)
    await log_action(ctx, "offering_cancel", RES_OFFERING, offering_id, candidate.get("full_name"),
                     before=item, after=after, module=MODULE, notes=note)
    return (await _decorate_offerings(ctx.company_id, [serialize(after)]))[0]


# --------------------------------------------------------------------------
# Agregat untuk halaman detail (satu panggilan -> hemat latensi)
# --------------------------------------------------------------------------
@router.get("/candidates/{candidate_id}/pipeline")
async def candidate_pipeline(candidate_id: str, ctx: AuthContext = Depends(_perm("view"))):
    candidate = await _get_candidate(ctx, candidate_id)
    interviews, approval, offerings = await asyncio.gather(
        _interviews_for(ctx.company_id, candidate_id),
        _approval_state(ctx, candidate),
        _offerings_for(ctx.company_id, candidate_id),
    )
    blockers = _offering_blockers(candidate, offerings)
    enriched = (await _enrich(ctx.company_id, [serialize(candidate)]))[0]
    from .recruitment_conversion import conversion_state  # impor lokal: hindari siklus impor
    conversion = await conversion_state(ctx, candidate)
    return {
        "candidate": enriched,
        "conversion": conversion,
        "interviews": interviews,
        "can_schedule_interview": candidate.get("stage_status") in INTERVIEW_ALLOWED_STAGES
        and ctx.has_permission("recruitment", "create"),
        "approval": approval,
        "offerings": {
            "items": offerings,
            "active": next((o for o in offerings if o.get("is_active")), None),
            "can_create": not blockers and ctx.has_permission("recruitment", "create"),
            "create_blockers": blockers,
        },
    }
