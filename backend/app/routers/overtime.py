"""LEMBUR: Pengajuan/Rencana -> Persetujuan -> Attendance Actual -> Lembur Final.

Tahap ini TIDAK menghitung nominal upah lembur dan TIDAK mengubah Payroll.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..core.audit import log_action
from ..core.db import ASCENDING, NO_ID, get_db, now, serialize_list
from ..core.deps import AuthContext, require_permission
from ..core.repo import TenantRepository
from ..core import time_approval as ta
from ..core import time_excel as tx
from ..core import time_service as svc
from ..core import timekeeping as tk

router = APIRouter(prefix="/overtime", tags=["Time Management - Lembur"])


def _perm(action: str):
    return require_permission("leave", action, "leave_overtime")


class OvertimeInput(BaseModel):
    work_date: str
    planned_start_time: str
    planned_end_time: str
    reason: str = Field(..., min_length=3)
    overtime_category: str = "operational"
    project_id: Optional[str] = None
    work_location_id: Optional[str] = None
    notes: Optional[str] = None
    employee_id: Optional[str] = None


class DecisionInput(BaseModel):
    decision: str
    notes: Optional[str] = None
    approved_minutes: Optional[int] = None


class CancelInput(BaseModel):
    reason: str = Field(..., min_length=3)


def _decorate(row: Dict[str, Any]) -> Dict[str, Any]:
    state = tk.REQUEST_STATUSES.get(row.get("request_status") or "", {})
    return {
        **row,
        "request_status_label": state.get("label", "-"),
        "request_status_tone": state.get("tone", "neutral"),
        "day_category_label": tk.OVERTIME_DAY_CATEGORIES.get(row.get("day_category") or "", "-"),
        "overtime_category_label": tk.OVERTIME_CATEGORIES.get(row.get("overtime_category") or "", "-"),
        "requested_label": tk.minutes_to_hhmm(row.get("requested_minutes")),
        "actual_label": tk.minutes_to_hhmm(row.get("actual_minutes")),
        "approved_label": tk.minutes_to_hhmm(row.get("approved_minutes")),
    }


@router.post("/requests", status_code=status.HTTP_201_CREATED)
async def create_request(payload: OvertimeInput, ctx: AuthContext = Depends(_perm("create"))):
    if payload.overtime_category not in tk.OVERTIME_CATEGORIES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Kategori lembur tidak dikenal.")
    work_date = tk.parse_date_str(payload.work_date, "Tanggal")
    start_time = tk.parse_time_str(payload.planned_start_time, "Jam Mulai Rencana")
    end_time = tk.parse_time_str(payload.planned_end_time, "Jam Selesai Rencana")
    await tk.assert_period_open(ctx.company_id, work_date)

    me = await svc.my_employee(ctx, required=False)
    if payload.employee_id and (not me or payload.employee_id != me["id"]):
        if not ctx.has_permission("leave", "edit"):
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "Anda tidak berhak mengajukan lembur untuk karyawan lain.")
        employee = await svc.get_employee(ctx.company_id, payload.employee_id)
    else:
        employee = await svc.my_employee(ctx)

    policies = await tk.get_time_policies(ctx.company_id)
    ot_policy = policies["overtime"]
    from datetime import date as _d
    today = tk.now_utc().astimezone(tk.tz_for(ctx.company)).date()
    is_retro = _d.fromisoformat(work_date) < today
    if is_retro and not ot_policy.get("retroactive_allowed"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Kebijakan perusahaan tidak mengizinkan pengajuan lembur untuk tanggal yang sudah lewat.")

    start_m, end_m = tk.time_to_minutes(start_time), tk.time_to_minutes(end_time)
    minutes = end_m - start_m
    if minutes <= 0:
        minutes += 24 * 60  # lembur lintas tengah malam
    max_day = int(ot_policy.get("max_minutes_per_day") or 0)
    if max_day and minutes > max_day:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Rencana lembur {tk.minutes_to_hhmm(minutes)} melebihi batas "
                            f"{tk.minutes_to_hhmm(max_day)} per hari.")

    context = await svc.resolve_context(ctx.company, employee, work_date)
    day_category = ("holiday" if context["day_type"] in tk.HOLIDAY_DAY_TYPES
                    else "day_off" if context["day_type"] == "weekly_off" else "workday")

    db = get_db()
    dup = await db.overtime_requests.find_one({
        "company_id": ctx.company_id, "employee_id": employee["id"], "work_date": work_date,
        "request_status": {"$in": ["pending", "approved"]}}, NO_ID)
    if dup:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Sudah ada pengajuan lembur aktif untuk karyawan dan tanggal ini.")
    leave = await db.leave_requests.find_one({
        "company_id": ctx.company_id, "employee_id": employee["id"],
        "request_status": {"$in": ["pending", "approved"]}, "day_part": "full_day",
        "start_date": {"$lte": work_date}, "end_date": {"$gte": work_date}}, NO_ID)
    if leave:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Tanggal ini bertabrakan dengan {leave.get('leave_type_name')} sehari penuh.")

    repo = TenantRepository("overtime_requests", ctx.company_id)
    created = await repo.create({
        "employee_id": employee["id"], "employee_number": employee.get("employee_number"),
        "employee_name": employee.get("full_name"), "work_date": work_date,
        "period_key": tk.period_key_of(work_date), "day_category": day_category,
        "planned_start_time": start_time, "planned_end_time": end_time,
        "requested_minutes": minutes, "actual_minutes": 0, "approved_minutes": 0,
        "overtime_category": payload.overtime_category, "project_id": payload.project_id,
        "work_location_id": payload.work_location_id or (context.get("work_location") or {}).get("id"),
        "reason": payload.reason, "notes": payload.notes, "is_retroactive": is_retro,
        "request_status": "pending", "submitted_by": ctx.user_id, "submitted_at": now(),
    }, ctx.user_id)

    await ta.submit(ctx, "overtime", created["id"],
                    f"Lembur {employee.get('full_name')} {work_date}", employee["id"])
    await log_action(ctx, "overtime_submit", "leave", created["id"],
                     f"Pengajuan Lembur {employee.get('full_name')} {work_date}",
                     after=created, module="leave_overtime", notes=payload.reason)
    return {"request": _decorate(created), "message": "Pengajuan lembur terkirim dan menunggu persetujuan."}


@router.get("/requests")
async def list_requests(
    request_status: Optional[str] = None,
    employee_id: Optional[str] = None,
    period: Optional[str] = None,
    mine: bool = False,
    ctx: AuthContext = Depends(_perm("view")),
):
    db = get_db()
    query: Dict[str, Any] = {"company_id": ctx.company_id, "status": {"$ne": "deleted"}}
    if request_status:
        query["request_status"] = request_status
    if period:
        f, t = tk.month_bounds(period)
        query["work_date"] = {"$gte": f, "$lte": t}
    if mine:
        me = await svc.my_employee(ctx, required=False)
        query["employee_id"] = me["id"] if me else "-"
    elif employee_id:
        query["employee_id"] = employee_id
    rows = await db.overtime_requests.find(query, NO_ID).sort("work_date", -1).to_list(600)
    policies = await tk.get_time_policies(ctx.company_id)
    items = []
    for r in serialize_list(rows):
        actual = await svc.compute_actual_overtime(ctx.company, r, policies["overtime"])
        items.append({**_decorate(r), "actual_preview": actual,
                      "approval": await ta.state_for(ctx, "overtime", r["id"])})
    return {"items": items, "total": len(items), "policy": policies["overtime"]}


@router.get("/approvals")
async def pending_approvals(ctx: AuthContext = Depends(_perm("view"))):
    rows = await ta.pending_for_me(ctx, ["overtime"])
    db = get_db()
    policies = await tk.get_time_policies(ctx.company_id)
    items = []
    for row in rows:
        req = await db.overtime_requests.find_one({"company_id": ctx.company_id, "id": row["record_id"]}, NO_ID)
        detail = {}
        if req:
            actual = await svc.compute_actual_overtime(ctx.company, req, policies["overtime"])
            detail = {**_decorate(req), "actual_preview": actual}
        items.append({"approval": {**row, "document_label": ta.DOCUMENT_KINDS["overtime"]["label"]},
                      "detail": detail})
    return {"items": items, "total": len(items)}


@router.post("/requests/{request_id}/refresh-actual")
async def refresh_actual(request_id: str, ctx: AuthContext = Depends(_perm("view"))):
    repo = TenantRepository("overtime_requests", ctx.company_id)
    req = await repo.get(request_id)
    policies = await tk.get_time_policies(ctx.company_id)
    actual = await svc.compute_actual_overtime(ctx.company, req, policies["overtime"])
    before, after = await repo.update(request_id, {
        "actual_minutes": actual["actual_minutes"], "rounded_minutes": actual["rounded_minutes"],
        "attendance_id": actual["attendance_id"]}, ctx.user_id)
    return {"request": _decorate(after), "actual": actual, "message": actual["note"]}


@router.post("/requests/{request_id}/approvals/{approval_id}/decide")
async def decide(request_id: str, approval_id: str, payload: DecisionInput,
                 ctx: AuthContext = Depends(_perm("approve"))):
    repo = TenantRepository("overtime_requests", ctx.company_id)
    req = await repo.get(request_id)
    if req.get("request_status") != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "Pengajuan lembur ini sudah diputuskan.")
    await tk.assert_period_open(ctx.company_id, req["work_date"])

    policies = await tk.get_time_policies(ctx.company_id)
    actual = await svc.compute_actual_overtime(ctx.company, req, policies["overtime"])
    result = await ta.decide(ctx, approval_id, payload.decision, payload.notes)
    overall = result["state"]["overall"]

    if overall == "approved":
        # Final selalu approved_minutes. Aktual lebih kecil -> tidak otomatis
        # membayar rencana; aktual lebih besar -> kelebihan tidak otomatis disetujui.
        candidate = min(int(req.get("requested_minutes") or 0), int(actual["rounded_minutes"] or 0))
        if payload.approved_minutes is not None:
            requested = int(payload.approved_minutes)
            if requested < 0:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                    "Menit lembur disetujui tidak boleh negatif.")
            ceiling = max(int(req.get("requested_minutes") or 0), int(actual["rounded_minutes"] or 0))
            if requested > ceiling:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    f"Menit disetujui tidak boleh melebihi rencana maupun aktual "
                    f"(maksimal {tk.minutes_to_hhmm(ceiling)}).")
            candidate = requested
        before, after = await repo.update(request_id, {
            "request_status": "approved", "actual_minutes": actual["actual_minutes"],
            "rounded_minutes": actual["rounded_minutes"], "approved_minutes": candidate,
            "attendance_id": actual["attendance_id"], "decided_by": ctx.user_id,
            "decided_at": now(), "decision_notes": payload.notes}, ctx.user_id)
    elif overall == "rejected":
        before, after = await repo.update(request_id, {
            "request_status": "rejected", "approved_minutes": 0,
            "actual_minutes": actual["actual_minutes"], "decided_by": ctx.user_id,
            "decided_at": now(), "decision_notes": payload.notes}, ctx.user_id)
    else:
        return {"state": result["state"], "overall": overall,
                "message": "Keputusan tersimpan; masih menunggu tahap persetujuan berikutnya."}

    await svc.recompute_range(ctx.company, req["employee_id"], [req["work_date"]])
    await log_action(ctx, f"overtime_{overall}", "leave", request_id,
                     f"Lembur {req.get('employee_name')} {req.get('work_date')}",
                     before=before, after=after, module="leave_overtime", notes=payload.notes)
    return {"request": _decorate(after), "state": result["state"], "overall": overall,
            "actual": actual,
            "message": (f"Lembur disetujui {tk.minutes_to_hhmm(after.get('approved_minutes'))}."
                        if overall == "approved" else "Lembur ditolak.")}


@router.post("/requests/{request_id}/cancel")
async def cancel_request(request_id: str, payload: CancelInput, ctx: AuthContext = Depends(_perm("create"))):
    repo = TenantRepository("overtime_requests", ctx.company_id)
    req = await repo.get(request_id)
    if req.get("request_status") not in ("pending", "approved"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Pengajuan lembur ini tidak dapat dibatalkan.")
    me = await svc.my_employee(ctx, required=False)
    if (not me or me["id"] != req["employee_id"]) and not ctx.has_permission("leave", "edit"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Anda tidak berhak membatalkan pengajuan ini.")
    await tk.assert_period_open(ctx.company_id, req["work_date"])
    before, after = await repo.update(request_id, {
        "request_status": "cancelled", "approved_minutes": 0, "cancelled_by": ctx.user_id,
        "cancelled_at": now(), "cancel_reason": payload.reason}, ctx.user_id)
    await svc.recompute_range(ctx.company, req["employee_id"], [req["work_date"]])
    await log_action(ctx, "overtime_cancel", "leave", request_id,
                     f"Pembatalan Lembur {req.get('employee_name')} {req.get('work_date')}",
                     before=before, after=after, module="leave_overtime", notes=payload.reason)
    return {"request": _decorate(after), "message": "Pengajuan lembur dibatalkan."}


OVERTIME_COLUMNS = [
    {"key": "employee_number", "label": "Nomor Karyawan"},
    {"key": "employee_name", "label": "Nama Karyawan"},
    {"key": "work_date", "label": "Tanggal"},
    {"key": "day_category_label", "label": "Jenis Hari"},
    {"key": "planned_start_time", "label": "Jam Mulai Rencana"},
    {"key": "planned_end_time", "label": "Jam Selesai Rencana"},
    {"key": "requested_minutes", "label": "Menit Diajukan"},
    {"key": "actual_minutes", "label": "Menit Aktual"},
    {"key": "approved_minutes", "label": "Menit Disetujui"},
    {"key": "overtime_category_label", "label": "Kategori"},
    {"key": "request_status_label", "label": "Status"},
    {"key": "reason", "label": "Alasan"},
]


@router.get("/export")
async def export_overtime(
    period: Optional[str] = None,
    request_status: Optional[str] = None,
    ctx: AuthContext = Depends(_perm("export")),
):
    db = get_db()
    query: Dict[str, Any] = {"company_id": ctx.company_id, "status": {"$ne": "deleted"}}
    if request_status:
        query["request_status"] = request_status
    label = "Semua Periode"
    if period:
        f, t = tk.month_bounds(period)
        query["work_date"] = {"$gte": f, "$lte": t}
        label = tk.period_label_of(period)
    rows = [_decorate(r) for r in serialize_list(
        await db.overtime_requests.find(query, NO_ID).sort("work_date", ASCENDING).to_list(5000))]
    blob = tx.export_sheet("Lembur", OVERTIME_COLUMNS, rows,
                           meta=[("Perusahaan", ctx.company.get("name")), ("Periode", label),
                                 ("Jumlah Pengajuan", str(len(rows)))])
    await log_action(ctx, "export", "leave", None, f"Ekspor Lembur {label}", module="leave_overtime")
    return Response(content=blob,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="Lembur.xlsx"'})
