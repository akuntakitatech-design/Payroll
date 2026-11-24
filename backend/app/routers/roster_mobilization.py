"""Module 4 CP2 - Roster & Mobilisasi (GA).

CP2 mencakup:
- Mobilisasi GA per rencana cuti project: moda transport, tanggal/jam berangkat dan kembali,
  carrier/tiket, titik jemput/tujuan, akomodasi, serta pembatalan perjalanan.
- Halaman data "Karyawan Akan Kembali": karyawan yang sedang cuti project dan tanggal kembalinya.
- Histori perubahan jadwal (append-only): perubahan tanggal/jam/moda tercatat beserta alasan,
  pelaku, dan data sebelum/sesudah.
- Approval HR Manager: mobilisasi yang dibuat/diubah GA berstatus PENDING_APPROVAL sampai
disetujui (APPROVED) atau ditolak (REJECTED) oleh pemegang permission `roster:approve`.

Hanya rencana cuti berstatus CONFIRMED (keputusan H-10) yang dapat dimobilisasi. Tanggal berangkat
dan kembali wajib berada di dalam periode off rencana cuti agar karyawan kembali sebelum hari kerja.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from ..core import data_scope as dscope
from ..core.audit import log_action
from ..core.db import NO_ID, audit_fields, new_id, now, serialize_list
from ..core.deps import AuthContext, require_permission
from ..core.employee_status import today_local

router = APIRouter(prefix="/roster", tags=["Roster & Mobilisasi"])

CONFIRMED = "CONFIRMED"

MODE_LABELS: Dict[str, str] = {
    "PESAWAT": "Pesawat",
    "KAPAL": "Kapal Laut",
    "BUS": "Bus",
    "MOBIL": "Mobil / Travel",
    "KERETA": "Kereta",
    "LAINNYA": "Lainnya",
}

TRAVEL_STATES = ("NOT_SET", "PLANNED", "DEPARTED", "RETURNED", "CANCELLED")

STATE_LABELS: Dict[str, str] = {
    "NOT_SET": "Belum diatur",
    "PLANNED": "Direncanakan",
    "DEPARTED": "Sedang di perjalanan/cuti",
    "RETURNED": "Sudah kembali",
    "CANCELLED": "Dibatalkan",
}

CHANGE_LABELS: Dict[str, str] = {
    "CREATED": "Mobilisasi dibuat",
    "UPDATED": "Data mobilisasi diubah",
    "SCHEDULE_CHANGED": "Jadwal diubah",
    "CANCELLED": "Mobilisasi dibatalkan",
    "APPROVED": "Mobilisasi disetujui HR",
    "REJECTED": "Mobilisasi ditolak HR",
    "REPLACEMENT": "Karyawan pengganti ditetapkan",
}

# Approval GA -> HR Manager (Blueprint Modul 4). Data lama tanpa nilai dianggap APPROVED.
PENDING_APPROVAL = "PENDING_APPROVAL"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
APPROVAL_STATES = (PENDING_APPROVAL, APPROVED, REJECTED)
APPROVAL_LABELS: Dict[str, str] = {
    PENDING_APPROVAL: "Menunggu Persetujuan HR",
    APPROVED: "Disetujui HR",
    REJECTED: "Ditolak HR",
}

SCHEDULE_FIELDS = (
    "depart_date", "depart_time", "depart_mode",
    "return_date", "return_time", "return_mode",
)

TRAVEL_FIELDS = SCHEDULE_FIELDS + (
    "depart_carrier", "depart_ticket", "depart_from", "depart_to",
    "return_carrier", "return_ticket", "return_from", "return_to",
    "accommodation", "notes",
)

TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

_view = require_permission("roster", "view")
_edit = require_permission("roster", "edit")
_approve = require_permission("roster", "approve")


def _err(code: int, msg: str) -> HTTPException:
    return HTTPException(code, msg)


def _today() -> date:
    return date.fromisoformat(today_local())


def _parse_date(value: Any, label: str) -> date:
    text = str(value or "").strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{label} harus berformat YYYY-MM-DD.") from exc


def _parse_time(value: Any, label: str) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    text = text[:5]
    if not TIME_RE.match(text):
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{label} harus berformat HH:MM.")
    return text


def _mode(value: Any, label: str) -> str:
    text = str(value or "").strip().upper()
    if text not in MODE_LABELS:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                   f"{label} tidak dikenal. Pilihan: {', '.join(MODE_LABELS)}.")
    return text


def _text(value: Any, limit: int = 255) -> Optional[str]:
    text = str(value or "").strip()
    return text[:limit] or None


async def _visible_projects(ctx: AuthContext) -> Optional[set]:
    return await dscope.allowed_project_ids(ctx)


async def _project_or_404(ctx: AuthContext, project_id: str) -> Dict[str, Any]:
    project = await ctx.tdb.projects.find_one(
        {"company_id": ctx.company_id, "id": project_id}, NO_ID)
    if not project:
        raise _err(status.HTTP_404_NOT_FOUND, "Project tidak ditemukan pada perusahaan aktif Anda.")
    allowed = await _visible_projects(ctx)
    if allowed is not None and project_id not in allowed:
        raise _err(status.HTTP_404_NOT_FOUND, "Project tidak ditemukan pada perusahaan aktif Anda.")
    return project


def _travel_state(mob: Optional[Dict[str, Any]], today: date) -> str:
    if not mob:
        return "NOT_SET"
    if mob.get("mobilization_state") == "CANCELLED":
        return "CANCELLED"
    return_date = str(mob.get("return_date") or "")[:10]
    depart_date = str(mob.get("depart_date") or "")[:10]
    if return_date and return_date < today.isoformat():
        return "RETURNED"
    if depart_date and depart_date <= today.isoformat():
        return "DEPARTED"
    return "PLANNED"


def _approval_state(mob: Optional[Dict[str, Any]]) -> str:
    """Mobilisasi lama (sebelum fitur approval) dianggap sudah disetujui."""
    if not mob:
        return ""
    return str(mob.get("approval_state") or APPROVED)


def _mob_public(mob: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not mob:
        return None
    return {
        "id": mob.get("id"),
        "plan_id": mob.get("plan_id"),
        "depart_date": mob.get("depart_date"),
        "depart_time": mob.get("depart_time"),
        "depart_mode": mob.get("depart_mode"),
        "depart_mode_label": MODE_LABELS.get(mob.get("depart_mode") or "", mob.get("depart_mode")),
        "depart_carrier": mob.get("depart_carrier"),
        "depart_ticket": mob.get("depart_ticket"),
        "depart_from": mob.get("depart_from"),
        "depart_to": mob.get("depart_to"),
        "return_date": mob.get("return_date"),
        "return_time": mob.get("return_time"),
        "return_mode": mob.get("return_mode"),
        "return_mode_label": MODE_LABELS.get(mob.get("return_mode") or "", mob.get("return_mode")),
        "return_carrier": mob.get("return_carrier"),
        "return_ticket": mob.get("return_ticket"),
        "return_from": mob.get("return_from"),
        "return_to": mob.get("return_to"),
        "accommodation": mob.get("accommodation"),
        "notes": mob.get("notes"),
        "mobilization_state": mob.get("mobilization_state"),
        "cancel_reason": mob.get("cancel_reason"),
        "cancelled_at": mob.get("cancelled_at"),
        "approval_state": _approval_state(mob),
        "approval_state_label": APPROVAL_LABELS.get(_approval_state(mob), _approval_state(mob)),
        "approval_note": mob.get("approval_note"),
        "approved_by": mob.get("approved_by"),
        "approved_by_name": mob.get("approved_by_name"),
        "approved_at": mob.get("approved_at"),
        "updated_at": mob.get("updated_at"),
    }


async def _plan_or_404(ctx: AuthContext, plan_id: str) -> Dict[str, Any]:
    plan = await ctx.tdb.roster_leave_plans.find_one(
        {"company_id": ctx.company_id, "id": plan_id}, NO_ID)
    if not plan:
        raise _err(status.HTTP_404_NOT_FOUND, "Rencana cuti tidak ditemukan.")
    await _project_or_404(ctx, plan.get("project_id"))
    return plan


async def _confirmed_plans(ctx: AuthContext, *, project_id: Optional[str], include_past: bool,
                           days_ahead: Optional[int] = None) -> List[Dict[str, Any]]:
    today = _today()
    flt: Dict[str, Any] = {"company_id": ctx.company_id, "plan_status": CONFIRMED}
    if project_id:
        await _project_or_404(ctx, project_id)
        flt["project_id"] = project_id
    else:
        allowed = await _visible_projects(ctx)
        if allowed is not None:
            flt["project_id"] = {"$in": list(allowed)}
    if days_ahead is not None:
        flt["off_end"] = {"$gte": today.isoformat(),
                          "$lte": (today + timedelta(days=days_ahead)).isoformat()}
    elif not include_past:
        flt["off_end"] = {"$gte": today.isoformat()}
    return serialize_list(await ctx.tdb.roster_leave_plans.find(flt, NO_ID).to_list(5000))


async def _mobilizations_by_plan(ctx: AuthContext, plan_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    if not plan_ids:
        return {}
    rows = serialize_list(await ctx.tdb.roster_mobilizations.find(
        {"company_id": ctx.company_id, "plan_id": {"$in": plan_ids}}, NO_ID).to_list(5000))
    return {r["plan_id"]: r for r in rows}


async def _employee_map(ctx: AuthContext, employee_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    ids = [e for e in employee_ids if e]
    if not ids:
        return {}
    rows = serialize_list(await ctx.tdb.employees.find(
        {"company_id": ctx.company_id, "id": {"$in": ids}}, NO_ID).to_list(5000))
    return {r["id"]: r for r in rows}


async def _project_map(ctx: AuthContext, project_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    ids = [p for p in project_ids if p]
    if not ids:
        return {}
    rows = serialize_list(await ctx.tdb.projects.find(
        {"company_id": ctx.company_id, "id": {"$in": ids}}, NO_ID).to_list(2000))
    return {r["id"]: r for r in rows}


def _plan_row(plan: Dict[str, Any], mob: Optional[Dict[str, Any]], employee: Dict[str, Any],
              project: Dict[str, Any], today: date) -> Dict[str, Any]:
    state = _travel_state(mob, today)
    depart_date = str((mob or {}).get("depart_date") or "")[:10] or None
    return_date = str((mob or {}).get("return_date") or "")[:10] or None
    return {
        "plan_id": plan.get("id"),
        "project_id": plan.get("project_id"),
        "project_name": project.get("name"),
        "project_code": project.get("code"),
        "employee_id": plan.get("employee_id"),
        "employee_name": employee.get("full_name"),
        "employee_number": employee.get("employee_number"),
        "off_start": plan.get("off_start"),
        "off_end": plan.get("off_end"),
        "plan_status": plan.get("plan_status"),
        "mobilization": _mob_public(mob),
        "travel_state": state,
        "travel_state_label": STATE_LABELS.get(state, state),
        "days_until_depart": (date.fromisoformat(depart_date) - today).days if depart_date else None,
        "days_until_return": (date.fromisoformat(return_date) - today).days if return_date else None,
    }


async def _snapshot_for_plan(ctx: AuthContext, plan: Dict[str, Any], mob: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    employee = await ctx.tdb.employees.find_one(
        {"company_id": ctx.company_id, "id": plan.get("employee_id")}, NO_ID) or {}
    project = await ctx.tdb.projects.find_one(
        {"company_id": ctx.company_id, "id": plan.get("project_id")}, NO_ID) or {}
    return {
        "plan_id": plan.get("id"),
        "mobilization_id": (mob or {}).get("id"),
        "project_id": plan.get("project_id"),
        "employee_id": plan.get("employee_id"),
        "employee_name": employee.get("full_name"),
        "project_name": project.get("name"),
    }


async def _write_history(ctx: AuthContext, plan: Dict[str, Any], mob: Optional[Dict[str, Any]],
                         change_type: str, before_data: Optional[Dict[str, Any]],
                         after_data: Optional[Dict[str, Any]], reason: Optional[str]) -> None:
    base = await _snapshot_for_plan(ctx, plan, mob)
    await ctx.tdb.roster_schedule_changes.insert_one({
        "id": new_id(), "company_id": ctx.company_id, "status": "active",
        **base, "change_type": change_type,
        "before_data": before_data, "after_data": after_data,
        "reason": reason, "changed_by": ctx.user_id,
        "changed_by_name": (ctx.user or {}).get("full_name"),
        "changed_at": now(), **audit_fields(ctx.user_id, creating=True),
    })


def _travel_values(mob: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {field: (mob or {}).get(field) for field in TRAVEL_FIELDS}


# --------------------------------------------------------------------------- read

@router.get("/mobilizations")
async def list_mobilizations(
    project_id: Optional[str] = None,
    travel_state: Optional[str] = Query(None, alias="state"),
    approval_state: Optional[str] = Query(None, description="PENDING_APPROVAL | APPROVED | REJECTED"),
    q: Optional[str] = None,
    include_past: bool = False,
    ctx: AuthContext = Depends(_view),
):
    """Daftar rencana cuti terkonfirmasi beserta data mobilisasi GA (termasuk yang belum diatur)."""
    if travel_state and travel_state.upper() not in TRAVEL_STATES:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Status perjalanan tidak dikenal.")
    wanted_approval = ""
    if approval_state:
        wanted_approval = approval_state.strip().upper()
        if wanted_approval not in APPROVAL_STATES:
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                       "Status persetujuan tidak dikenal. Pilihan: Menunggu Persetujuan HR, Disetujui HR, Ditolak HR.")
    plans = await _confirmed_plans(ctx, project_id=project_id, include_past=include_past)
    mobs = await _mobilizations_by_plan(ctx, [p["id"] for p in plans])
    employees = await _employee_map(ctx, [p.get("employee_id") for p in plans])
    projects = await _project_map(ctx, [p.get("project_id") for p in plans])
    today = _today()
    rows = [
        _plan_row(p, mobs.get(p["id"]), employees.get(p.get("employee_id")) or {},
                  projects.get(p.get("project_id")) or {}, today)
        for p in plans
    ]
    needle = (q or "").strip().lower()
    if needle:
        rows = [r for r in rows
                if needle in (r.get("employee_name") or "").lower()
                or needle in (r.get("employee_number") or "").lower()]
    counts = {key: 0 for key in TRAVEL_STATES}
    for row in rows:
        counts[row["travel_state"]] = counts.get(row["travel_state"], 0) + 1
    approval_counts = {key: 0 for key in APPROVAL_STATES}
    for row in rows:
        mob = row.get("mobilization")
        if mob:
            approval_counts[mob["approval_state"]] = approval_counts.get(mob["approval_state"], 0) + 1
    if travel_state:
        rows = [r for r in rows if r["travel_state"] == travel_state.upper()]
    if wanted_approval:
        rows = [r for r in rows
                if (r.get("mobilization") or {}).get("approval_state") == wanted_approval]
    rows.sort(key=lambda r: (
        1 if not r.get("mobilization") else 0,
        (r.get("mobilization") or {}).get("depart_date") or r.get("off_start") or "",
        r.get("employee_name") or "",
    ))
    return {"items": rows, "total": len(rows), "counts": counts, "approval_counts": approval_counts,
            "approval_states": [{"value": k, "label": v} for k, v in APPROVAL_LABELS.items()],
            "modes": [{"value": k, "label": v} for k, v in MODE_LABELS.items()]}


@router.get("/returning")
async def list_returning(
    days: int = Query(14, ge=1, le=60),
    project_id: Optional[str] = None,
    ctx: AuthContext = Depends(_view),
):
    """Karyawan yang sedang cuti project dan/atau akan kembali dalam N hari ke depan."""
    plans = await _confirmed_plans(ctx, project_id=project_id, include_past=False, days_ahead=days)
    mobs = await _mobilizations_by_plan(ctx, [p["id"] for p in plans])
    employees = await _employee_map(ctx, [p.get("employee_id") for p in plans])
    projects = await _project_map(ctx, [p.get("project_id") for p in plans])
    today = _today()
    horizon = (today + timedelta(days=days)).isoformat()
    rows = []
    for plan in plans:
        mob = mobs.get(plan["id"])
        row = _plan_row(plan, mob, employees.get(plan.get("employee_id")) or {},
                        projects.get(plan.get("project_id")) or {}, today)
        return_date = (row.get("mobilization") or {}).get("return_date") or plan.get("off_end")
        if not return_date or return_date < today.isoformat() or return_date > horizon:
            continue
        row["return_date"] = return_date
        row["days_until_return"] = (date.fromisoformat(return_date[:10]) - today).days
        row["on_leave"] = str(plan.get("off_start") or "") <= today.isoformat() <= str(plan.get("off_end") or "")
        row["transport_ready"] = bool(mob) and (mob or {}).get("mobilization_state") != "CANCELLED" \
            and _approval_state(mob) == APPROVED
        rows.append(row)
    rows.sort(key=lambda r: (r["return_date"], r.get("employee_name") or ""))
    counts = {
        "total": len(rows),
        "on_leave": sum(1 for r in rows if r["on_leave"]),
        "due_today": sum(1 for r in rows if r["days_until_return"] == 0),
        "due_7d": sum(1 for r in rows if r["days_until_return"] <= 7),
        "transport_missing": sum(1 for r in rows if not r["transport_ready"]),
    }
    return {"items": rows, "counts": counts, "days": days, "today": today.isoformat()}


@router.get("/schedule-changes")
async def list_schedule_changes(
    plan_id: Optional[str] = None,
    project_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    ctx: AuthContext = Depends(_view),
):
    """Histori perubahan jadwal mobilisasi (append-only), terbaru lebih dulu."""
    flt: Dict[str, Any] = {"company_id": ctx.company_id}
    if plan_id:
        plan = await _plan_or_404(ctx, plan_id)
        flt["plan_id"] = plan["id"]
    elif project_id:
        await _project_or_404(ctx, project_id)
        flt["project_id"] = project_id
    else:
        allowed = await _visible_projects(ctx)
        if allowed is not None:
            flt["project_id"] = {"$in": list(allowed)}
    rows = serialize_list(await ctx.tdb.roster_schedule_changes.find(flt, NO_ID)
                          .sort("changed_at", -1).to_list(limit))
    for row in rows:
        row["change_type_label"] = CHANGE_LABELS.get(row.get("change_type") or "", row.get("change_type"))
        before = row.get("before_data") or {}
        after = row.get("after_data") or {}
        if before.get("depart_mode"):
            before["depart_mode_label"] = MODE_LABELS.get(before["depart_mode"], before["depart_mode"])
        if before.get("return_mode"):
            before["return_mode_label"] = MODE_LABELS.get(before["return_mode"], before["return_mode"])
        if after.get("depart_mode"):
            after["depart_mode_label"] = MODE_LABELS.get(after["depart_mode"], after["depart_mode"])
        if after.get("return_mode"):
            after["return_mode_label"] = MODE_LABELS.get(after["return_mode"], after["return_mode"])
    return {"items": rows, "total": len(rows)}


# --------------------------------------------------------------------------- write

@router.put("/mobilizations/{plan_id}")
async def upsert_mobilization(plan_id: str, payload: Dict[str, Any] = Body(...),
                              ctx: AuthContext = Depends(_edit)):
    """Atur/ubah mobilisasi GA untuk rencana cuti terkonfirmasi.

    Perubahan tanggal/jam mengubah jadwal karyawan sehingga WAJIB menyertakan alasan; seluruh perubahan
    tercatat di histori jadwal.
    """
    plan = await _plan_or_404(ctx, plan_id)
    if plan.get("plan_status") != CONFIRMED:
        raise _err(status.HTTP_409_CONFLICT,
                   "Mobilisasi hanya dapat diatur untuk rencana cuti yang sudah dikonfirmasi (H-10).")
    off_start = _parse_date(plan.get("off_start"), "Tanggal mulai cuti")
    off_end = _parse_date(plan.get("off_end"), "Tanggal selesai cuti")
    depart_date = _parse_date(payload.get("depart_date"), "Tanggal berangkat")
    return_date = _parse_date(payload.get("return_date"), "Tanggal kembali")
    if not (off_start <= depart_date <= off_end):
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                   f"Tanggal berangkat harus di dalam periode off ({off_start.isoformat()} s.d. {off_end.isoformat()}).")
    if not (depart_date <= return_date <= off_end):
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                   "Tanggal kembali harus setelah tanggal berangkat dan tidak melewati akhir periode off "
                   f"({off_end.isoformat()}).")
    values = {
        "depart_date": depart_date.isoformat(),
        "depart_time": _parse_time(payload.get("depart_time"), "Jam berangkat"),
        "depart_mode": _mode(payload.get("depart_mode"), "Moda keberangkatan"),
        "depart_carrier": _text(payload.get("depart_carrier"), 120),
        "depart_ticket": _text(payload.get("depart_ticket"), 64),
        "depart_from": _text(payload.get("depart_from"), 120),
        "depart_to": _text(payload.get("depart_to"), 120),
        "return_date": return_date.isoformat(),
        "return_time": _parse_time(payload.get("return_time"), "Jam kembali"),
        "return_mode": _mode(payload.get("return_mode"), "Moda kepulangan"),
        "return_carrier": _text(payload.get("return_carrier"), 120),
        "return_ticket": _text(payload.get("return_ticket"), 64),
        "return_from": _text(payload.get("return_from"), 120),
        "return_to": _text(payload.get("return_to"), 120),
        "accommodation": _text(payload.get("accommodation"), 2000),
        "notes": _text(payload.get("notes"), 2000),
    }
    existing = await ctx.tdb.roster_mobilizations.find_one(
        {"company_id": ctx.company_id, "plan_id": plan_id}, NO_ID)
    reason = _text(payload.get("reason"), 255)
    before_values = _travel_values(existing)
    schedule_changed = bool(existing) and any(
        before_values.get(f) != values.get(f) for f in SCHEDULE_FIELDS)
    if schedule_changed and (not reason or len(reason) < 3):
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                   "Alasan perubahan jadwal wajib diisi (minimal 3 karakter).")
    # Approval GA -> HR Manager: perubahan oleh GA mengembalikan mobilisasi ke antrean persetujuan.
    # Pemegang `roster:approve` yang mengubah sendiri langsung disetujui.
    can_approve = ctx.has_permission("roster", "approve")
    approval_fields: Dict[str, Any] = {
        "approval_state": APPROVED if can_approve else PENDING_APPROVAL,
        "approval_note": None,
        "approved_by": ctx.user_id if can_approve else None,
        "approved_by_name": (ctx.user or {}).get("full_name") if can_approve else None,
        "approved_at": now() if can_approve else None,
    }
    if existing:
        await ctx.tdb.roster_mobilizations.update_one(
            {"company_id": ctx.company_id, "id": existing["id"]},
            {"$set": {**values, **approval_fields, "mobilization_state": "PLANNED",
                      "cancelled_at": None, "cancelled_by": None, "cancel_reason": None,
                      **audit_fields(ctx.user_id, creating=False)}})
        mobilization_id = existing["id"]
    else:
        mobilization_id = new_id()
        await ctx.tdb.roster_mobilizations.insert_one({
            "id": mobilization_id, "company_id": ctx.company_id, "status": "active",
            "plan_id": plan_id, "project_id": plan.get("project_id"),
            "employee_id": plan.get("employee_id"), **values,
            "mobilization_state": "PLANNED", **approval_fields,
            **audit_fields(ctx.user_id, creating=True),
        })
    after = await ctx.tdb.roster_mobilizations.find_one(
        {"company_id": ctx.company_id, "id": mobilization_id}, NO_ID)
    change_type = "CREATED" if not existing else ("SCHEDULE_CHANGED" if schedule_changed else "UPDATED")
    if not existing or schedule_changed or before_values != _travel_values(after):
        await _write_history(ctx, plan, after, change_type,
                             before_values if existing else None, _travel_values(after), reason)
    await log_action(ctx, "update", "roster", mobilization_id,
                     f"Mobilisasi {plan.get('employee_id')}",
                     before=before_values if existing else None,
                     after=_travel_values(after),
                     notes=f"{CHANGE_LABELS.get(change_type, change_type)}"
                           + (f": {reason}" if reason else ""))
    return {"message": "Mobilisasi disimpan." if can_approve
                       else "Mobilisasi disimpan dan menunggu persetujuan HR Manager.",
            "item": _mob_public(after), "change_type": change_type}


@router.post("/mobilizations/{plan_id}/cancel")
async def cancel_mobilization(plan_id: str, payload: Dict[str, Any] = Body(...),
                              ctx: AuthContext = Depends(_edit)):
    """Batalkan perjalanan (mis. tiket dibatalkan). Rencana cuti tetap berlaku."""
    plan = await _plan_or_404(ctx, plan_id)
    mob = await ctx.tdb.roster_mobilizations.find_one(
        {"company_id": ctx.company_id, "plan_id": plan_id}, NO_ID)
    if not mob:
        raise _err(status.HTTP_404_NOT_FOUND, "Mobilisasi belum diatur untuk rencana cuti ini.")
    today = _today()
    if mob.get("mobilization_state") == "CANCELLED":
        raise _err(status.HTTP_409_CONFLICT, "Mobilisasi sudah dibatalkan.")
    if _travel_state(mob, today) == "RETURNED":
        raise _err(status.HTTP_409_CONFLICT, "Perjalanan sudah selesai dan tidak dapat dibatalkan.")
    reason = _text(payload.get("reason"), 255)
    if not reason or len(reason) < 3:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                   "Alasan pembatalan wajib diisi (minimal 3 karakter).")
    await ctx.tdb.roster_mobilizations.update_one(
        {"company_id": ctx.company_id, "id": mob["id"]},
        {"$set": {"mobilization_state": "CANCELLED", "cancelled_at": now(),
                  "cancelled_by": ctx.user_id, "cancel_reason": reason,
                  **audit_fields(ctx.user_id, creating=False)}})
    after = await ctx.tdb.roster_mobilizations.find_one(
        {"company_id": ctx.company_id, "id": mob["id"]}, NO_ID)
    await _write_history(ctx, plan, after, "CANCELLED", _travel_values(mob), _travel_values(after), reason)
    await log_action(ctx, "cancel", "roster", mob["id"],
                     f"Mobilisasi {plan.get('employee_id')}",
                     before={"state": "PLANNED"}, after={"state": "CANCELLED"},
                     notes=f"Mobilisasi dibatalkan: {reason}")
    return {"message": "Mobilisasi dibatalkan.", "item": _mob_public(after)}


@router.post("/mobilizations/{plan_id}/approve")
async def approve_mobilization(plan_id: str, payload: Dict[str, Any] = Body(default={}),
                               ctx: AuthContext = Depends(_approve)):
    """Setujui mobilisasi yang diajukan GA (Blueprint Modul 4: GA -> approval HR Manager)."""
    plan = await _plan_or_404(ctx, plan_id)
    mob = await ctx.tdb.roster_mobilizations.find_one(
        {"company_id": ctx.company_id, "plan_id": plan_id}, NO_ID)
    if not mob:
        raise _err(status.HTTP_404_NOT_FOUND, "Mobilisasi belum diatur untuk rencana cuti ini.")
    if mob.get("mobilization_state") == "CANCELLED":
        raise _err(status.HTTP_409_CONFLICT, "Mobilisasi sudah dibatalkan dan tidak perlu disetujui.")
    if _approval_state(mob) == APPROVED:
        raise _err(status.HTTP_409_CONFLICT, "Mobilisasi ini sudah disetujui.")
    if _travel_state(mob, _today()) == "RETURNED":
        raise _err(status.HTTP_409_CONFLICT, "Perjalanan sudah selesai; persetujuan tidak dapat diberikan.")
    note = _text(payload.get("note"), 500)
    before = {"approval_state": _approval_state(mob), "approval_note": mob.get("approval_note"),
              "approved_by_name": mob.get("approved_by_name")}
    await ctx.tdb.roster_mobilizations.update_one(
        {"company_id": ctx.company_id, "id": mob["id"]},
        {"$set": {"approval_state": APPROVED, "approval_note": note,
                  "approved_by": ctx.user_id, "approved_by_name": (ctx.user or {}).get("full_name"),
                  "approved_at": now(), **audit_fields(ctx.user_id, creating=False)}})
    after = await ctx.tdb.roster_mobilizations.find_one(
        {"company_id": ctx.company_id, "id": mob["id"]}, NO_ID)
    after_snapshot = {"approval_state": APPROVED, "approval_note": note,
                      "approved_by_name": after.get("approved_by_name")}
    await _write_history(ctx, plan, after, "APPROVED", before, after_snapshot, note)
    await log_action(ctx, "approve", "roster", mob["id"], f"Mobilisasi {plan.get('employee_id')}",
                     before=before, after={"approval_state": APPROVED},
                     notes=note or "Mobilisasi disetujui HR Manager.")
    return {"message": "Mobilisasi disetujui.", "item": _mob_public(after)}


@router.post("/mobilizations/{plan_id}/reject")
async def reject_mobilization(plan_id: str, payload: Dict[str, Any] = Body(default={}),
                              ctx: AuthContext = Depends(_approve)):
    """Tolak mobilisasi disertai alasan; GA dapat memperbaiki lalu mengajukan ulang."""
    reason = _text(payload.get("reason"), 500)
    if not reason or len(reason) < 3:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                   "Alasan penolakan wajib diisi (minimal 3 karakter).")
    plan = await _plan_or_404(ctx, plan_id)
    mob = await ctx.tdb.roster_mobilizations.find_one(
        {"company_id": ctx.company_id, "plan_id": plan_id}, NO_ID)
    if not mob:
        raise _err(status.HTTP_404_NOT_FOUND, "Mobilisasi belum diatur untuk rencana cuti ini.")
    if mob.get("mobilization_state") == "CANCELLED":
        raise _err(status.HTTP_409_CONFLICT, "Mobilisasi sudah dibatalkan.")
    if _approval_state(mob) == REJECTED:
        raise _err(status.HTTP_409_CONFLICT, "Mobilisasi ini sudah ditolak.")
    before = {"approval_state": _approval_state(mob), "approval_note": mob.get("approval_note"),
              "approved_by_name": mob.get("approved_by_name")}
    await ctx.tdb.roster_mobilizations.update_one(
        {"company_id": ctx.company_id, "id": mob["id"]},
        {"$set": {"approval_state": REJECTED, "approval_note": reason,
                  "approved_by": ctx.user_id, "approved_by_name": (ctx.user or {}).get("full_name"),
                  "approved_at": now(), **audit_fields(ctx.user_id, creating=False)}})
    after = await ctx.tdb.roster_mobilizations.find_one(
        {"company_id": ctx.company_id, "id": mob["id"]}, NO_ID)
    after_snapshot = {"approval_state": REJECTED, "approval_note": reason,
                      "approved_by_name": after.get("approved_by_name")}
    await _write_history(ctx, plan, after, "REJECTED", before, after_snapshot, reason)
    await log_action(ctx, "reject", "roster", mob["id"], f"Mobilisasi {plan.get('employee_id')}",
                     before=before, after={"approval_state": REJECTED},
                     notes=f"Mobilisasi ditolak: {reason}")
    return {"message": "Mobilisasi ditolak. GA dapat memperbaiki jadwal lalu mengajukan ulang.",
            "item": _mob_public(after)}
