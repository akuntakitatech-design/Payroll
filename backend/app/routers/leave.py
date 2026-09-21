"""CUTI / IZIN / SAKIT: pengajuan, saldo berbasis ledger, persetujuan bersama,
pembatalan dengan reversal, dan ekspor.
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

router = APIRouter(prefix="/leave", tags=["Time Management - Cuti/Izin/Sakit"])


def _perm(action: str):
    return require_permission("leave", action, "leave_overtime")


class LeaveRequestInput(BaseModel):
    leave_type_id: str
    start_date: str
    end_date: str
    day_part: str = "full_day"
    reason: str = Field(..., min_length=3)
    contact_during_leave: Optional[str] = None
    document_id: Optional[str] = None
    employee_id: Optional[str] = None  # HR mengajukan untuk karyawan lain


class DecisionInput(BaseModel):
    decision: str
    notes: Optional[str] = None


class CancelInput(BaseModel):
    reason: str = Field(..., min_length=3)


class AdjustInput(BaseModel):
    employee_id: str
    leave_type_id: str
    year: int
    days: float
    reason: str = Field(..., min_length=3)


def _decorate(row: Dict[str, Any]) -> Dict[str, Any]:
    state = tk.REQUEST_STATUSES.get(row.get("request_status") or "", {})
    return {
        **row,
        "request_status_label": state.get("label", "-"),
        "request_status_tone": state.get("tone", "neutral"),
        "day_part_label": tk.DAY_PARTS.get(row.get("day_part") or "full_day", "-"),
        "leave_category_label": tk.LEAVE_CATEGORIES.get(row.get("leave_category") or "", "-"),
        "recap_status": tk.LEAVE_CATEGORY_TO_STATUS.get(row.get("leave_category") or "", "leave"),
        "recap_status_label": tk.status_label(
            tk.LEAVE_CATEGORY_TO_STATUS.get(row.get("leave_category") or "", "leave")),
    }


async def _leave_type(ctx: AuthContext, type_id: str) -> Dict[str, Any]:
    db = get_db()
    row = await db.leave_types.find_one(
        {"company_id": ctx.company_id, "id": type_id, "status": "active"}, NO_ID)
    if not row:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Jenis cuti tidak ditemukan atau sudah nonaktif.")
    return row


@router.post("/requests", status_code=status.HTTP_201_CREATED)
async def create_request(payload: LeaveRequestInput, ctx: AuthContext = Depends(_perm("create"))):
    if payload.day_part not in tk.DAY_PARTS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pilihan Sehari Penuh / Setengah Hari tidak dikenal.")
    start_date = tk.parse_date_str(payload.start_date, "Tanggal Mulai")
    end_date = tk.parse_date_str(payload.end_date, "Tanggal Selesai")
    leave_type = await _leave_type(ctx, payload.leave_type_id)

    if payload.employee_id and payload.employee_id != (await svc.my_employee(ctx, required=False) or {}).get("id"):
        if not ctx.has_permission("leave", "edit"):
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "Anda tidak berhak mengajukan cuti untuk karyawan lain.")
        employee = await svc.get_employee(ctx.company_id, payload.employee_id)
    else:
        employee = await svc.my_employee(ctx)

    await tk.assert_period_open(ctx.company_id, start_date, end_date)
    policies = await tk.get_time_policies(ctx.company_id)

    if payload.day_part != "full_day":
        if not leave_type.get("allow_half_day"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"Jenis cuti {leave_type.get('name')} tidak mengizinkan setengah hari.")
        if start_date != end_date:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Setengah hari hanya berlaku untuk satu tanggal.")
    if leave_type.get("attachment_required") and not payload.document_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Jenis cuti {leave_type.get('name')} mewajibkan lampiran (mis. surat dokter).")

    notice = int(leave_type.get("minimum_notice_days") or 0)
    if notice:
        from datetime import date as _d, timedelta as _td
        today = tk.now_utc().astimezone(tk.tz_for(ctx.company)).date()
        if _d.fromisoformat(start_date) < today + _td(days=notice):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"Pengajuan {leave_type.get('name')} harus dilakukan minimal {notice} hari sebelumnya.")

    breakdown = await svc.leave_day_breakdown(ctx.company, employee, start_date, end_date,
                                              payload.day_part, policies["leave"])
    if breakdown["working_days"] <= 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Rentang tanggal tidak mengandung hari kerja, sehingga tidak ada hari cuti yang dihitung.")
    max_days = leave_type.get("maximum_consecutive_days")
    if max_days and breakdown["working_days"] > float(max_days):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Maksimal {max_days} hari kerja berurutan untuk {leave_type.get('name')}.")

    db = get_db()
    overlap = await db.leave_requests.find_one({
        "company_id": ctx.company_id, "employee_id": employee["id"],
        "request_status": {"$in": ["pending", "approved"]},
        "start_date": {"$lte": end_date}, "end_date": {"$gte": start_date}}, NO_ID)
    if overlap:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Sudah ada pengajuan {overlap.get('leave_type_name')} "
                            f"({overlap.get('start_date')} s/d {overlap.get('end_date')}) yang bertumpuk.")
    if payload.day_part == "full_day":
        ot = await db.overtime_requests.find_one({
            "company_id": ctx.company_id, "employee_id": employee["id"],
            "work_date": {"$gte": start_date, "$lte": end_date},
            "request_status": {"$in": ["pending", "approved"]}}, NO_ID)
        if ot:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"Ada pengajuan lembur pada {ot.get('work_date')} yang bertabrakan "
                                "dengan cuti sehari penuh.")

    conflicts = []
    real = await db.attendances.find({
        "company_id": ctx.company_id, "employee_id": employee["id"],
        "work_date": {"$gte": start_date, "$lte": end_date},
        "check_in_at": {"$ne": None}, "status": {"$ne": "deleted"}}, NO_ID).to_list(100)
    for a in real:
        conflicts.append({"work_date": a["work_date"],
                          "message": "Sudah ada absensi nyata pada tanggal ini; absensi tidak ditimpa."})

    deduct = bool(leave_type.get("deduct_balance"))
    if deduct:
        year = int(start_date[:4])
        balance = await svc.ensure_entitlement(ctx, employee, leave_type, year)
        if balance["available_days"] < breakdown["working_days"]:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Saldo {leave_type.get('name')} tidak cukup: tersedia "
                f"{balance['available_days']} hari, diajukan {breakdown['working_days']} hari.")

    repo = TenantRepository("leave_requests", ctx.company_id)
    created = await repo.create({
        "employee_id": employee["id"], "employee_number": employee.get("employee_number"),
        "employee_name": employee.get("full_name"),
        "leave_type_id": leave_type["id"], "leave_type_code": leave_type.get("code"),
        "leave_type_name": leave_type.get("name"), "leave_category": leave_type.get("category"),
        "start_date": start_date, "end_date": end_date, "day_part": payload.day_part,
        "requested_days": breakdown["calendar_days"], "working_days": breakdown["working_days"],
        "day_breakdown": breakdown["breakdown"], "period_keys": breakdown["period_keys"],
        "reason": payload.reason, "contact_during_leave": payload.contact_during_leave,
        "document_id": payload.document_id, "request_status": "pending",
        "deduct_balance": deduct, "is_paid": bool(leave_type.get("is_paid")),
        "submitted_by": ctx.user_id, "submitted_at": now(), "conflict_notes": conflicts,
    }, ctx.user_id)

    await ta.submit(ctx, "leave", created["id"],
                    f"{leave_type.get('name')} {employee.get('full_name')} "
                    f"({start_date} s/d {end_date})", employee["id"])
    if deduct:
        await svc.recalc_balance(ctx.company_id, employee, leave_type, int(start_date[:4]))
    await log_action(ctx, "leave_submit", "leave", created["id"],
                     f"Pengajuan {leave_type.get('name')} {employee.get('full_name')}",
                     after=created, module="leave_overtime", notes=payload.reason)
    return {"request": _decorate(created), "breakdown": breakdown, "conflicts": conflicts,
            "message": "Pengajuan terkirim dan menunggu persetujuan."}


@router.get("/requests")
async def list_requests(
    request_status: Optional[str] = None,
    employee_id: Optional[str] = None,
    leave_type_id: Optional[str] = None,
    period: Optional[str] = None,
    mine: bool = False,
    ctx: AuthContext = Depends(_perm("view")),
):
    db = get_db()
    query: Dict[str, Any] = {"company_id": ctx.company_id, "status": {"$ne": "deleted"}}
    if request_status:
        query["request_status"] = request_status
    if leave_type_id:
        query["leave_type_id"] = leave_type_id
    if period:
        f, t = tk.month_bounds(period)
        query["start_date"] = {"$lte": t}
        query["end_date"] = {"$gte": f}
    if mine:
        emp = await svc.my_employee(ctx, required=False)
        query["employee_id"] = emp["id"] if emp else "-"
    elif employee_id:
        query["employee_id"] = employee_id
    rows = await db.leave_requests.find(query, NO_ID).sort("submitted_at", -1).to_list(600)
    items = []
    for r in serialize_list(rows):
        items.append({**_decorate(r), "approval": await ta.state_for(ctx, "leave", r["id"])})
    return {"items": items, "total": len(items)}


@router.get("/approvals")
async def pending_approvals(ctx: AuthContext = Depends(_perm("view"))):
    rows = await ta.pending_for_me(ctx, ["leave"])
    db = get_db()
    items = []
    for row in rows:
        req = await db.leave_requests.find_one({"company_id": ctx.company_id, "id": row["record_id"]}, NO_ID)
        items.append({"approval": {**row, "document_label": ta.DOCUMENT_KINDS["leave"]["label"]},
                      "detail": _decorate(req) if req else {}})
    return {"items": items, "total": len(items)}


@router.post("/requests/{request_id}/approvals/{approval_id}/decide")
async def decide(request_id: str, approval_id: str, payload: DecisionInput,
                 ctx: AuthContext = Depends(_perm("approve"))):
    db = get_db()
    repo = TenantRepository("leave_requests", ctx.company_id)
    req = await repo.get(request_id)
    if req.get("request_status") != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "Pengajuan ini sudah tidak berstatus menunggu persetujuan.")
    await tk.assert_period_open(ctx.company_id, req["start_date"], req["end_date"])

    result = await ta.decide(ctx, approval_id, payload.decision, payload.notes)
    overall = result["state"]["overall"]
    if overall in ("approved", "rejected"):
        before, after = await repo.update(request_id, {
            "request_status": overall, "decided_by": ctx.user_id,
            "decided_at": now(), "decision_notes": payload.notes}, ctx.user_id)
        employee = await svc.get_employee(ctx.company_id, req["employee_id"])
        leave_type = await db.leave_types.find_one(
            {"company_id": ctx.company_id, "id": req["leave_type_id"]}, NO_ID)
        if overall == "approved" and req.get("deduct_balance") and leave_type:
            await svc.add_ledger(ctx, employee, leave_type, int(req["start_date"][:4]), "usage",
                                 float(req.get("working_days") or 0), "leave_request", request_id,
                                 notes=f"Cuti disetujui {req['start_date']} s/d {req['end_date']}.",
                                 effective_date=req["start_date"])
        elif leave_type:
            await svc.recalc_balance(ctx.company_id, employee, leave_type, int(req["start_date"][:4]))
        # Rekap kehadiran ikut berubah tanpa membuat absensi palsu.
        await svc.recompute_range(ctx.company, req["employee_id"],
                                  tk.date_range(req["start_date"], req["end_date"]))
        await log_action(ctx, f"leave_{overall}", "leave", request_id,
                         f"{req.get('leave_type_name')} {req.get('employee_name')}",
                         before=before, after=after, module="leave_overtime", notes=payload.notes)
    return {"state": result["state"], "overall": overall,
            "message": "Disetujui." if payload.decision == "approved" else "Ditolak."}


@router.post("/requests/{request_id}/cancel")
async def cancel_request(request_id: str, payload: CancelInput, ctx: AuthContext = Depends(_perm("create"))):
    db = get_db()
    repo = TenantRepository("leave_requests", ctx.company_id)
    req = await repo.get(request_id)
    if req.get("request_status") not in ("pending", "approved"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Pengajuan ini tidak dapat dibatalkan.")
    me = await svc.my_employee(ctx, required=False)
    if (not me or me["id"] != req["employee_id"]) and not ctx.has_permission("leave", "edit"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Anda tidak berhak membatalkan pengajuan ini.")
    await tk.assert_period_open(ctx.company_id, req["start_date"], req["end_date"])
    policies = await tk.get_time_policies(ctx.company_id)
    if req["request_status"] == "approved" and not policies["leave"].get("allow_cancel_after_approved"):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Kebijakan perusahaan tidak mengizinkan pembatalan cuti yang sudah disetujui.")

    before, after = await repo.update(request_id, {
        "request_status": "cancelled", "cancelled_by": ctx.user_id,
        "cancelled_at": now(), "cancel_reason": payload.reason}, ctx.user_id)

    employee = await svc.get_employee(ctx.company_id, req["employee_id"])
    leave_type = await db.leave_types.find_one(
        {"company_id": ctx.company_id, "id": req["leave_type_id"]}, NO_ID)
    if leave_type:
        if req["request_status"] == "approved" and req.get("deduct_balance"):
            await svc.add_ledger(ctx, employee, leave_type, int(req["start_date"][:4]), "reversal",
                                 float(req.get("working_days") or 0), "leave_cancel", request_id,
                                 notes=f"Pembatalan cuti: {payload.reason}",
                                 effective_date=req["start_date"])
        else:
            await svc.recalc_balance(ctx.company_id, employee, leave_type, int(req["start_date"][:4]))
    await svc.recompute_range(ctx.company, req["employee_id"],
                              tk.date_range(req["start_date"], req["end_date"]))
    await log_action(ctx, "leave_cancel", "leave", request_id,
                     f"Pembatalan {req.get('leave_type_name')} {req.get('employee_name')}",
                     before=before, after=after, module="leave_overtime", notes=payload.reason)
    return {"request": _decorate(after), "message": "Pengajuan dibatalkan; saldo dikembalikan melalui reversal."}


# ------------------------------------------------------------------ saldo
@router.get("/balances")
async def list_balances(
    year: Optional[int] = None,
    employee_id: Optional[str] = None,
    mine: bool = False,
    ctx: AuthContext = Depends(_perm("view")),
):
    db = get_db()
    year = int(year or tk.now_utc().astimezone(tk.tz_for(ctx.company)).year)
    leave_types = await db.leave_types.find(
        {"company_id": ctx.company_id, "status": "active", "deduct_balance": True}, NO_ID
    ).sort("sort_order", ASCENDING).to_list(50)
    emp_q: Dict[str, Any] = {"company_id": ctx.company_id, "status": "active"}
    if mine:
        me = await svc.my_employee(ctx, required=False)
        emp_q["id"] = me["id"] if me else "-"
    elif employee_id:
        emp_q["id"] = employee_id
    employees = await db.employees.find(emp_q, NO_ID).sort("full_name", ASCENDING).to_list(1000)

    items = []
    for emp in employees:
        for lt in leave_types:
            await svc.ensure_entitlement(ctx, emp, lt, year)
            bal = await db.leave_balances.find_one({
                "company_id": ctx.company_id, "employee_id": emp["id"],
                "leave_type_id": lt["id"], "year": year}, NO_ID)
            if bal:
                items.append({**bal, "leave_type_name": lt.get("name"),
                              "employee_number": emp.get("employee_number"),
                              "has_problem": float(bal.get("available_days") or 0) < 0})
    return {"year": year, "items": items, "total": len(items),
            "leave_types": [{"id": t["id"], "name": t.get("name"), "code": t.get("code")} for t in leave_types]}


@router.get("/ledger")
async def list_ledger(
    employee_id: str,
    leave_type_id: Optional[str] = None,
    year: Optional[int] = None,
    ctx: AuthContext = Depends(_perm("view")),
):
    db = get_db()
    query: Dict[str, Any] = {"company_id": ctx.company_id, "employee_id": employee_id, "status": "active"}
    if leave_type_id:
        query["leave_type_id"] = leave_type_id
    if year:
        query["year"] = int(year)
    rows = await db.leave_ledger.find(query, NO_ID).sort("created_at", -1).to_list(500)
    return {"items": [{**r, "movement_label": svc.MOVEMENTS.get(r.get("movement_type") or "", "-")}
                      for r in serialize_list(rows)], "total": len(rows)}


@router.post("/balances/adjust")
async def adjust_balance(payload: AdjustInput, ctx: AuthContext = Depends(_perm("edit"))):
    if float(payload.days) == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Jumlah penyesuaian tidak boleh nol.")
    employee = await svc.get_employee(ctx.company_id, payload.employee_id)
    leave_type = await _leave_type(ctx, payload.leave_type_id)
    entry = await svc.add_ledger(ctx, employee, leave_type, int(payload.year), "adjustment",
                                 float(payload.days), "manual_adjustment", None,
                                 notes=payload.reason, effective_date=f"{int(payload.year)}-01-01")
    balance = await svc.recalc_balance(ctx.company_id, employee, leave_type, int(payload.year))
    await log_action(ctx, "leave_balance_adjust", "leave", entry["id"],
                     f"Penyesuaian saldo {leave_type.get('name')} {employee.get('full_name')}",
                     after=entry, module="leave_overtime", notes=payload.reason)
    return {"entry": entry, "balance": balance,
            "message": f"Saldo disesuaikan {payload.days} hari beserta alasan dan jejak audit."}


# ------------------------------------------------------------------ dashboard & ekspor
@router.get("/dashboard")
async def dashboard(ctx: AuthContext = Depends(_perm("view"))):
    db = get_db()
    tz = tk.tz_for(ctx.company)
    today = tk.now_utc().astimezone(tz).date().isoformat()
    period = tk.period_key_of(today)
    month_from, month_to = tk.month_bounds(period)

    pending_leave = await db.leave_requests.find(
        {"company_id": ctx.company_id, "request_status": "pending"}, NO_ID).sort("start_date", ASCENDING).to_list(200)
    on_leave = await db.leave_requests.find(
        {"company_id": ctx.company_id, "request_status": "approved",
         "start_date": {"$lte": today}, "end_date": {"$gte": today}}, NO_ID).to_list(200)
    upcoming = await db.leave_requests.find(
        {"company_id": ctx.company_id, "request_status": "approved",
         "start_date": {"$gt": today}}, NO_ID).sort("start_date", ASCENDING).to_list(100)
    balance_problems = await db.leave_balances.find(
        {"company_id": ctx.company_id, "available_days": {"$lt": 0}}, NO_ID).to_list(100)
    pending_ot = await db.overtime_requests.find(
        {"company_id": ctx.company_id, "request_status": "pending"}, NO_ID).sort("work_date", ASCENDING).to_list(200)
    approved_ot = await db.overtime_requests.find(
        {"company_id": ctx.company_id, "request_status": "approved",
         "work_date": {"$gte": month_from, "$lte": month_to}}, NO_ID).to_list(500)

    return {
        "today": today, "period": period, "period_label": tk.period_label_of(period),
        "counters": {
            "pending_leave": len(pending_leave), "on_leave_today": len(on_leave),
            "upcoming_leave": len(upcoming), "balance_problems": len(balance_problems),
            "pending_overtime": len(pending_ot), "approved_overtime": len(approved_ot),
            "approved_overtime_minutes": sum(int(o.get("approved_minutes") or 0) for o in approved_ot),
        },
        "pending_leave": [_decorate(r) for r in serialize_list(pending_leave)][:20],
        "on_leave_today": [_decorate(r) for r in serialize_list(on_leave)][:20],
        "upcoming_leave": [_decorate(r) for r in serialize_list(upcoming)][:20],
        "balance_problems": serialize_list(balance_problems)[:20],
        "pending_overtime": serialize_list(pending_ot)[:20],
    }


LEAVE_COLUMNS = [
    {"key": "employee_number", "label": "Nomor Karyawan"},
    {"key": "employee_name", "label": "Nama Karyawan"},
    {"key": "leave_type_name", "label": "Jenis Cuti"},
    {"key": "leave_category_label", "label": "Kategori"},
    {"key": "start_date", "label": "Tanggal Mulai"},
    {"key": "end_date", "label": "Tanggal Selesai"},
    {"key": "day_part_label", "label": "Durasi Hari"},
    {"key": "working_days", "label": "Hari Kerja"},
    {"key": "request_status_label", "label": "Status"},
    {"key": "reason", "label": "Alasan"},
    {"key": "decision_notes", "label": "Catatan Persetujuan"},
]


@router.get("/export")
async def export_leave(
    period: Optional[str] = None,
    request_status: Optional[str] = None,
    leave_type_id: Optional[str] = None,
    ctx: AuthContext = Depends(_perm("export")),
):
    db = get_db()
    query: Dict[str, Any] = {"company_id": ctx.company_id, "status": {"$ne": "deleted"}}
    if request_status:
        query["request_status"] = request_status
    if leave_type_id:
        query["leave_type_id"] = leave_type_id
    label = "Semua Periode"
    if period:
        f, t = tk.month_bounds(period)
        query["start_date"] = {"$lte": t}
        query["end_date"] = {"$gte": f}
        label = tk.period_label_of(period)
    rows = [_decorate(r) for r in serialize_list(
        await db.leave_requests.find(query, NO_ID).sort("start_date", ASCENDING).to_list(5000))]
    blob = tx.export_sheet("Cuti Izin Sakit", LEAVE_COLUMNS, rows,
                           meta=[("Perusahaan", ctx.company.get("name")), ("Periode", label),
                                 ("Jumlah Pengajuan", str(len(rows)))])
    await log_action(ctx, "export", "leave", None, f"Ekspor Cuti/Izin/Sakit {label}", module="leave_overtime")
    return Response(content=blob,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="Cuti-Izin-Sakit.xlsx"'})
