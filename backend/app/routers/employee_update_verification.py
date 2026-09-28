"""Upgrade 01H - HR Verification (Verifikasi Pembaruan Data).

Semua endpoint: login internal (JWT) + permission `employee_form:verify`, tenant-scoped (ctx.tdb), backend authoritative.
Body keputusan TIDAK menerima nilai data (extra="forbid"); nilai yang diterapkan selalu diambil dari `proposed`
tersimpan dan divalidasi ulang di server. Token sesi formulir publik bukan JWT -> 401.

  GET  /api/employees/update-verifications/summary
  GET  /api/employees/update-verifications                       daftar (filter status/project/departemen/cari/tanggal)
  GET  /api/employees/update-verifications/{id}                  detail: Data Saat Ini vs Data Usulan + konflik
  GET  /api/employees/update-verifications/{id}/files/{file_id}  lampiran private (no-store; tanpa storage key)
  POST /api/employees/update-verifications/{id}/approve          {version, resolutions, confirm_identity, note}
  POST /api/employees/update-verifications/{id}/reject           {version, reason}
  POST /api/employees/update-verifications/{id}/request-revision {version, note, items}
"""
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core import data_scope as dscope  # Upgrade 01I
from ..core import hr_verification as HV
from ..core import public_form as P
from ..core.db import NO_ID
from ..core.deps import AuthContext, require_permission
from ..core.sensitive import can_view_sensitive
from ..core.storage import StorageError, get_object

router = APIRouter(prefix="/employees/update-verifications", tags=["employee-update-verification"])
_verify = require_permission("employee_form", "verify")


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"


# ------------------------------------------------------------------ schemas
class ApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int
    resolutions: Dict[str, Literal["use_proposed", "keep_current"]] = Field(default_factory=dict)
    confirm_identity: bool = False
    note: Optional[str] = Field(None, max_length=2000)


class RejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int
    reason: str = Field(..., max_length=2000)

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) < 5:
            raise ValueError("Alasan penolakan wajib diisi (minimal 5 karakter).")
        return v


class RevisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int
    note: str = Field(..., max_length=2000)
    items: List[str] = Field(default_factory=list, max_length=100)

    @field_validator("note")
    @classmethod
    def _note(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) < 5:
            raise ValueError("Catatan perbaikan wajib diisi (minimal 5 karakter).")
        return v


# ------------------------------------------------------------------ helpers
async def _labels(tdb, table: str, cid: str, ids) -> Dict[str, str]:
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    rows = await tdb[table].find({"company_id": cid, "id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1, "code": 1}).to_list(len(ids))
    return {r["id"]: r.get("name") or r.get("code") or r["id"] for r in rows}


async def _active_projects(tdb, cid: str, eids: List[str]) -> Dict[str, str]:
    if not eids:
        return {}
    rows = await tdb.employee_assignments.find({"company_id": cid, "employee_id": {"$in": eids}, "assignment_status": "ACTIVE"},
                                               {"_id": 0, "employee_id": 1, "project_id": 1}).to_list(len(eids) * 2)
    return {r["employee_id"]: r.get("project_id") for r in rows if r.get("project_id")}


def _file_out(f: Dict[str, Any], doc_types: Dict[str, Any], existing: Dict[str, int]) -> Dict[str, Any]:
    dt = doc_types.get(f.get("document_type_id")) or {}
    return {"id": f["id"], "purpose": f.get("purpose"), "document_type_code": f.get("document_type_code"),
            "document_type_name": dt.get("name"), "field_key": f.get("field_key"), "file_name": f.get("file_name"),
            "mime_type": f.get("mime_type"), "file_size": f.get("file_size"), "uploaded_at": HV.iso(f.get("uploaded_at")),
            "status": f.get("status"), "document_id": f.get("document_id"),
            "existing_count": existing.get(f.get("document_type_id"), 0) if f.get("purpose") == "DOCUMENT" else None}


async def _scoped_submission(ctx: AuthContext, submission_id: str) -> Dict[str, Any]:
    """Upgrade 01I: submission hanya dapat diakses bila karyawannya SAAT INI berada dalam cakupan caller
    (assignment ACTIVE 01D saat review, bukan project saat pengajuan dibuat). Di luar cakupan -> 404 generik."""
    sub = await HV.get_submission(ctx.tdb, ctx.company_id, submission_id)
    scope = await dscope.get_scope(ctx)
    if not await dscope.employee_in_scope(scope, sub.get("employee_id")):
        raise HTTPException(status.HTTP_404_NOT_FOUND, dscope.NOT_FOUND_MSG)
    return sub


# ------------------------------------------------------------------ endpoints
@router.get("/summary")
async def summary(response: Response, ctx: AuthContext = Depends(_verify)):
    _no_store(response)
    scope = await dscope.get_scope(ctx)  # Upgrade 01I - hitungan per status di SQL, mengikuti cakupan
    counts = {s: 0 for s in HV.REVIEW_STATUSES}
    for st in HV.REVIEW_STATUSES:
        counts[st] = await ctx.tdb.employee_update_submissions.count_documents(
            dscope.with_scope({"company_id": ctx.company_id, "status": st}, scope, "employee_id"))
    return {"counts": counts, "labels": HV.STATUS_LABELS, "pending": counts[P.PENDING]}


@router.get("")
async def list_verifications(response: Response,
                             status_filter: str = Query(P.PENDING, alias="status", max_length=40),
                             project_id: Optional[str] = Query(None, max_length=64),
                             department_id: Optional[str] = Query(None, max_length=64),
                             q: Optional[str] = Query(None, max_length=100),
                             date_from: Optional[str] = Query(None, max_length=10),
                             date_to: Optional[str] = Query(None, max_length=10),
                             page: int = Query(1, ge=1, le=10000), page_size: int = Query(25, ge=1, le=100),
                             ctx: AuthContext = Depends(_verify)):
    _no_store(response)
    cid, tdb = ctx.company_id, ctx.tdb
    statuses = list(HV.REVIEW_STATUSES) if status_filter == "ALL" else [status_filter]
    if any(s not in HV.REVIEW_STATUSES for s in statuses):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Filter status tidak dikenal.")
    scope = await dscope.get_scope(ctx)  # Upgrade 01I - cakupan diterapkan di query DB (subquery assignment ACTIVE)
    subs = await tdb.employee_update_submissions.find(
        dscope.with_scope({"company_id": cid, "status": {"$in": statuses}}, scope, "employee_id"), NO_ID) \
        .sort("submitted_at", -1).to_list(5000)
    eids = list({s["employee_id"] for s in subs})
    emps = {e["id"]: e for e in await tdb.employees.find({"company_id": cid, "id": {"$in": eids}}, NO_ID).to_list(len(eids) or 1)} if eids else {}
    active_proj = await _active_projects(tdb, cid, eids)
    rows = []
    needle = (q or "").strip().casefold()
    for s in subs:
        e = emps.get(s["employee_id"]) or {}
        proj = active_proj.get(s["employee_id"]) or e.get("project_id")
        if project_id and proj != project_id:
            continue
        if department_id and e.get("department_id") != department_id:
            continue
        if needle and needle not in (e.get("full_name") or "").casefold() and needle not in (e.get("employee_number") or "").casefold():
            continue
        sub_day = (HV.iso(s.get("submitted_at")) or "")[:10]
        if date_from and sub_day and sub_day < date_from:
            continue
        if date_to and sub_day and sub_day > date_to:
            continue
        rows.append((s, e, proj))
    total = len(rows)
    page_rows = rows[(page - 1) * page_size: page * page_size]
    pids = [p for _s, _e, p in page_rows]
    proj_labels = await _labels(tdb, "projects", cid, pids)
    dept_labels = await _labels(tdb, "departments", cid, [e.get("department_id") for _s, e, _p in page_rows])
    cfg = None
    items = []
    for s, e, proj in page_rows:
        files = await tdb.employee_submission_files.find(
            {"company_id": cid, "submission_id": s["id"], "status": {"$ne": "removed"}}, {"_id": 0, "id": 1}).to_list(100)
        has_conflict = False
        if s.get("status") == P.PENDING:
            if cfg is None:
                from ..core import form_builder as FB
                cfg = await FB.load_config(cid)
            ev = HV.evaluate(s, await HV.load_context(tdb, cid, s, cfg))
            has_conflict = bool(ev["conflicts"])
        items.append({"id": s["id"], "status": s.get("status"), "status_label": HV.STATUS_LABELS.get(s.get("status")),
                      "employee": {"id": s["employee_id"], "employee_number": e.get("employee_number"), "full_name": e.get("full_name"),
                                   "status": e.get("status")},
                      "project": proj_labels.get(proj), "department": dept_labels.get(e.get("department_id")),
                      "submitted_at": HV.iso(s.get("submitted_at")), "reviewed_at": HV.iso(s.get("reviewed_at")),
                      "reviewed_by_name": s.get("reviewed_by_name"), "revision_count": int(s.get("revision_count") or 0),
                      "changes": HV.change_summary(s, files), "attachments": len(files),
                      "identity_change": bool(s.get("identity_change")), "has_conflict": has_conflict})
    projects = await tdb.projects.find({"company_id": cid, "status": {"$nin": ["deleted"]}}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)
    if scope.restricted:  # Upgrade 01I - opsi filter hanya project dalam cakupan
        projects = [p for p in projects if p["id"] in scope.project_ids]
    depts = await tdb.departments.find({"company_id": cid, "status": {"$nin": ["deleted"]}}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)
    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "section_labels": HV.SECTION_LABELS, "status_labels": HV.STATUS_LABELS,
            "filters": {"projects": sorted([{"id": p["id"], "label": p.get("name") or p["id"]} for p in projects], key=lambda x: x["label"]),
                        "departments": sorted([{"id": d["id"], "label": d.get("name") or d["id"]} for d in depts], key=lambda x: x["label"])}}


async def _detail(ctx: AuthContext, sub: Dict[str, Any]) -> Dict[str, Any]:
    cid, tdb = ctx.company_id, ctx.tdb
    data = await HV.load_context(tdb, cid, sub)
    enums, labels = HV._enums_and_labels()
    ev = HV.decided_view(HV.evaluate(sub, data, enums), sub, data["files"])
    full = can_view_sensitive(ctx)
    emp = data["emp"]
    proj = (await _active_projects(tdb, cid, [sub["employee_id"]])).get(sub["employee_id"]) or emp.get("project_id")
    snap = await tdb.employee_completeness.find_one({"company_id": cid, "employee_id": sub["employee_id"]}, NO_ID) or {}
    sections = []
    items = HV.present_items(ev["items"], full, labels)
    for key, label in HV.SECTION_ORDER:
        sec_items = [i for i in items if i["section"] == key]
        if sec_items:
            sections.append({"key": key, "label": label, "items": sec_items,
                             "changed": sum(1 for i in sec_items if i["state"] in (HV.OK, HV.CONFLICT))})
    can_decide = sub.get("status") == P.PENDING and emp.get("status") == "active"
    return {
        "id": sub["id"], "status": sub.get("status"), "status_label": HV.STATUS_LABELS.get(sub.get("status")),
        "version": sub.get("version"), "source": sub.get("source"),
        "employee": {"id": emp.get("id"), "employee_number": emp.get("employee_number"), "full_name": emp.get("full_name"),
                     "status": emp.get("status"), "has_photo": bool(emp.get("photo_path")),
                     "project": (await _labels(tdb, "projects", cid, [proj])).get(proj),
                     "department": (await _labels(tdb, "departments", cid, [emp.get("department_id")])).get(emp.get("department_id")),
                     "position": (await _labels(tdb, "positions", cid, [emp.get("position_id")])).get(emp.get("position_id")) or emp.get("job_title")},
        "submitted_at": HV.iso(sub.get("submitted_at")), "draft_saved_at": HV.iso(sub.get("draft_saved_at")),
        "identity_change": bool(sub.get("identity_change")),
        "identity_fields": [i["field"] for i in ev["items"] if i["kind"] == "field" and i.get("identity") and i["state"] in (HV.OK, HV.CONFLICT)],
        "revision_count": int(sub.get("revision_count") or 0), "review_note": sub.get("review_note"),
        "reviewed_by_name": sub.get("reviewed_by_name"), "reviewed_at": HV.iso(sub.get("reviewed_at")),
        "sections": sections, "conflicts": ev["conflicts"], "has_conflict": bool(ev["conflicts"]),
        "notes": ev["notes"], "no_npwp": ev["no_npwp"],
        "files": [_file_out(f, data["doc_types"], data["existing_docs"]) for f in data["files"]],
        "completeness": {"before": HV.jl(sub.get("completeness_before")), "after": HV.jl(sub.get("completeness_after")),
                         "current": {"score_pct": snap.get("score_pct"), "status": snap.get("completeness_status")}},
        "history": HV.jl(sub.get("review_history")) or [], "apply_result": HV.jl(sub.get("apply_result")),
        "can_decide": can_decide, "sensitive_masked": not full,
        "employee_inactive": emp.get("status") != "active",
    }


@router.get("/{submission_id}")
async def get_verification(submission_id: str, response: Response, ctx: AuthContext = Depends(_verify)):
    _no_store(response)
    sub = await _scoped_submission(ctx, submission_id)  # Upgrade 01I
    return await _detail(ctx, sub)


@router.get("/{submission_id}/files/{file_id}")
async def get_file(submission_id: str, file_id: str, ctx: AuthContext = Depends(_verify)):
    sub = await _scoped_submission(ctx, submission_id)  # Upgrade 01I
    f = await ctx.tdb.employee_submission_files.find_one(
        {"company_id": ctx.company_id, "submission_id": sub["id"], "id": file_id, "status": {"$ne": "removed"}}, NO_ID)
    if not f:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Berkas tidak ditemukan.")
    try:
        data, _ct = get_object(f["storage_path"])
    except StorageError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Berkas tidak tersedia di penyimpanan.") from None
    name = (f.get("file_name") or "berkas").replace('"', "")
    return Response(content=data, media_type=f.get("mime_type") or "application/octet-stream", headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
        "Content-Disposition": f'inline; filename="{name}"'})


@router.post("/{submission_id}/approve")
async def approve(submission_id: str, body: ApproveIn, response: Response, ctx: AuthContext = Depends(_verify)):
    _no_store(response)
    sub = await _scoped_submission(ctx, submission_id)  # Upgrade 01I
    try:
        result = await HV.approve(ctx, sub, body.version, dict(body.resolutions), body.confirm_identity,
                                  (body.note or "").strip() or None)
    except HV.UnresolvedConflicts as exc:
        return JSONResponse(status_code=409, content={"detail": exc.message, "conflicts": exc.conflicts})
    sub = await HV.get_submission(ctx.tdb, ctx.company_id, submission_id)
    return {"message": "Pengajuan disetujui dan data resmi karyawan telah diperbarui.", "result": result,
            "submission": await _detail(ctx, sub)}


@router.post("/{submission_id}/reject")
async def reject(submission_id: str, body: RejectIn, response: Response, ctx: AuthContext = Depends(_verify)):
    _no_store(response)
    sub = await _scoped_submission(ctx, submission_id)  # Upgrade 01I
    await HV.reject(ctx, sub, body.version, body.reason)
    sub = await HV.get_submission(ctx.tdb, ctx.company_id, submission_id)
    return {"message": "Pengajuan ditolak. Tidak ada data resmi yang diubah.", "submission": await _detail(ctx, sub)}


@router.post("/{submission_id}/request-revision")
async def request_revision(submission_id: str, body: RevisionIn, response: Response, ctx: AuthContext = Depends(_verify)):
    _no_store(response)
    sub = await _scoped_submission(ctx, submission_id)  # Upgrade 01I
    if body.items:
        data = await HV.load_context(ctx.tdb, ctx.company_id, sub)
        keys = {i["key"] for i in HV.evaluate(sub, data)["items"]}
        unknown = sorted(set(body.items) - keys)
        if unknown:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Item yang ditandai tidak dikenal: " + ", ".join(unknown[:5]) + ".")
    await HV.request_revision(ctx, sub, body.version, body.note, sorted(set(body.items)))
    sub = await HV.get_submission(ctx.tdb, ctx.company_id, submission_id)
    return {"message": "Permintaan perbaikan dikirim. Karyawan dapat memperbaiki pengajuan melalui portal.",
            "submission": await _detail(ctx, sub)}
