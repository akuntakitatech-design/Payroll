"""Module 4 - Roster Proyek, Cuti Project & Mobilisasi (CP1).

CP1 mencakup:
- Master Pola Roster (via master generic `roster-patterns`).
- Konfigurasi roster per Project (pola, tanggal awal/POH, flag mobilisasi).
- Kalender roster (siklus kerja/off) per project.
- Rencana cuti project H-30 (generate idempoten) + konfirmasi/keputusan H-10.
- Ringkasan per project: aktif, rencana, terkonfirmasi, sedang cuti, akan kembali, replacement.

Belum termasuk (CP2): proses mobilisasi GA, tanggal kembali, dan histori perubahan jadwal.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from ..core import data_scope as dscope
from ..core.audit import log_action
from ..core.db import NO_ID, audit_fields, new_id, now, serialize, serialize_list
from ..core.deps import AuthContext, require_permission
from ..core.employee_status import today_local
from .roster_mobilization import _write_history

router = APIRouter(prefix="/roster", tags=["Roster & Mobilisasi"])

PLANNED, CONFIRMED, POSTPONED = "PLANNED", "CONFIRMED", "POSTPONED"
PLAN_STATUSES = (PLANNED, CONFIRMED, POSTPONED)

_view = require_permission("roster", "view")
_create = require_permission("roster", "create")
_edit = require_permission("roster", "edit")


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


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "ya")


def _pattern_public(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row.get("id"),
        "code": row.get("code"),
        "name": row.get("name"),
        "work_days": row.get("work_days"),
        "off_days": row.get("off_days"),
    }


def _cycle_bounds(start: date, work_days: int, off_days: int, n: int) -> tuple[date, date]:
    cycle = work_days + off_days
    return (
        start + timedelta(days=n * cycle + work_days),
        start + timedelta(days=n * cycle + cycle - 1),
    )


def _cycles_between(start: date, work_days: int, off_days: int, range_start: date, range_end: date):
    if range_end < start:
        return []
    cycle = work_days + off_days
    first = max(0, (range_start - start).days // cycle - 1)
    last = max(0, (range_end - start).days // cycle + 1)
    if last - first > 600:  # pengaman: horizon maksimum ~2 tahun
        last = first + 600
    out = []
    for n in range(first, last + 1):
        off_start, off_end = _cycle_bounds(start, work_days, off_days, n)
        if off_end >= range_start and off_start <= range_end:
            out.append((n, off_start, off_end))
    return out


def _next_cycle(start: date, work_days: int, off_days: int, today: date):
    cycle = work_days + off_days
    n = max(0, (today - start).days // cycle)
    for _ in range(600):
        off_start, off_end = _cycle_bounds(start, work_days, off_days, n)
        if off_end >= today:
            return n, off_start, off_end
        n += 1
    return None


async def _visible_projects(ctx: AuthContext) -> Optional[set]:
    return await dscope.allowed_project_ids(ctx)


async def _project_or_404(ctx: AuthContext, project_id: str) -> Dict[str, Any]:
    project = await ctx.tdb.projects.find_one({"company_id": ctx.company_id, "id": project_id}, NO_ID)
    if not project:
        raise _err(status.HTTP_404_NOT_FOUND, "Project tidak ditemukan pada perusahaan aktif Anda.")
    allowed = await _visible_projects(ctx)
    if allowed is not None and project_id not in allowed:
        raise _err(status.HTTP_404_NOT_FOUND, "Project tidak ditemukan pada perusahaan aktif Anda.")
    return project


async def _pattern_or_422(ctx: AuthContext, pattern_id: Optional[str]) -> Dict[str, Any]:
    if not pattern_id:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pola roster wajib dipilih.")
    pattern = await ctx.tdb.roster_patterns.find_one(
        {"company_id": ctx.company_id, "id": pattern_id, "status": "active"}, NO_ID)
    if not pattern:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pola roster tidak ditemukan / nonaktif.")
    work_days = int(pattern.get("work_days") or 0)
    off_days = int(pattern.get("off_days") or 0)
    if work_days < 1 or off_days < 1:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pola roster harus memiliki hari kerja dan hari off minimal 1.")
    return pattern


def _config_public(config: Optional[Dict[str, Any]], pattern: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not config:
        return None
    return {
        "enabled": bool(config.get("roster_enabled")),
        "pattern_id": config.get("pattern_id"),
        "pattern_name": (pattern or {}).get("name"),
        "pattern_code": (pattern or {}).get("code"),
        "work_days": (pattern or {}).get("work_days"),
        "off_days": (pattern or {}).get("off_days"),
        "start_date": config.get("start_date"),
        "mobilization_enabled": bool(config.get("mobilization_enabled")),
        "notes": config.get("notes"),
    }


async def _active_employees_by_project(ctx: AuthContext, project_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    if not project_ids:
        return {}
    rows = serialize_list(await ctx.tdb.employees.find(
        {"company_id": ctx.company_id, "status": "active", "project_id": {"$in": project_ids}},
        {"id": 1, "full_name": 1, "employee_number": 1, "project_id": 1},
    ).to_list(20000))
    out: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(row.get("project_id"), []).append(row)
    return out


@router.get("/projects")
async def list_roster_projects(ctx: AuthContext = Depends(_view)):
    """Daftar project + konfigurasi roster + pola yang tersedia."""
    allowed = await _visible_projects(ctx)
    query: Dict[str, Any] = {"company_id": ctx.company_id, "status": "active"}
    if allowed is not None:
        query["id"] = {"$in": list(allowed)}
    projects = serialize_list(await ctx.tdb.projects.find(query, NO_ID).sort("name", 1).to_list(2000))
    project_ids = [p["id"] for p in projects]
    configs = {c["project_id"]: c for c in serialize_list(await ctx.tdb.project_roster_configs.find(
        {"company_id": ctx.company_id, "project_id": {"$in": project_ids}}, NO_ID).to_list(2000))}
    patterns = {p["id"]: p for p in serialize_list(await ctx.tdb.roster_patterns.find(
        {"company_id": ctx.company_id}, NO_ID).sort("name", 1).to_list(500))}
    employees = await _active_employees_by_project(ctx, project_ids)
    items = []
    for project in projects:
        config = configs.get(project["id"])
        pattern = patterns.get((config or {}).get("pattern_id") or "")
        items.append({
            "id": project["id"],
            "code": project.get("code"),
            "name": project.get("name"),
            "client_name": project.get("client_name"),
            "active_employees": len(employees.get(project["id"], [])),
            "roster": _config_public(config, pattern),
        })
    return {
        "items": items,
        "patterns": [_pattern_public(p) for p in patterns.values() if p.get("status") == "active"],
        "total": len(items),
    }


@router.put("/projects/{project_id}")
async def upsert_roster_config(project_id: str, payload: Dict[str, Any] = Body(...),
                               ctx: AuthContext = Depends(_edit)):
    """Atur konfigurasi roster project (pola, POH/tanggal awal, flag mobilisasi)."""
    await _project_or_404(ctx, project_id)
    enabled = _flag(payload.get("roster_enabled"))
    pattern = await _pattern_or_422(ctx, payload.get("pattern_id")) if (
        enabled or payload.get("pattern_id")) else None
    start = _parse_date(payload.get("start_date"), "Tanggal awal roster/POH") if payload.get("start_date") else None
    if enabled and start is None:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tanggal awal roster/POH wajib diisi saat roster diaktifkan.")
    fields = {
        "roster_enabled": enabled,
        "pattern_id": (pattern or {}).get("id"),
        "start_date": start.isoformat() if start else None,
        "mobilization_enabled": _flag(payload.get("mobilization_enabled")),
        "notes": (str(payload.get("notes") or "").strip() or None),
    }
    existing = await ctx.tdb.project_roster_configs.find_one(
        {"company_id": ctx.company_id, "project_id": project_id}, NO_ID)
    if existing:
        await ctx.tdb.project_roster_configs.update_one(
            {"company_id": ctx.company_id, "id": existing["id"]},
            {"$set": {**fields, **audit_fields(ctx.user_id, creating=False)}})
        config_id = existing["id"]
    else:
        config_id = new_id()
        await ctx.tdb.project_roster_configs.insert_one({
            "id": config_id, "company_id": ctx.company_id, "project_id": project_id,
            "status": "active", **fields, **audit_fields(ctx.user_id, creating=True),
        })
    after = await ctx.tdb.project_roster_configs.find_one(
        {"company_id": ctx.company_id, "id": config_id}, NO_ID)
    await log_action(ctx, "update", "roster", config_id, f"Konfigurasi roster project {project_id}",
                     after=fields, notes="Konfigurasi roster project diperbarui")
    return {"message": "Konfigurasi roster project disimpan.", "item": _config_public(after, pattern)}


@router.get("/calendar")
async def roster_calendar(
    project_id: str = Query(...),
    month: Optional[str] = Query(None, description="YYYY-MM (default bulan berjalan)"),
    ctx: AuthContext = Depends(_view),
):
    project = await _project_or_404(ctx, project_id)
    config = await ctx.tdb.project_roster_configs.find_one(
        {"company_id": ctx.company_id, "project_id": project_id}, NO_ID)
    if not config or not config.get("roster_enabled"):
        raise _err(status.HTTP_409_CONFLICT, "Roster project belum diaktifkan. Atur konfigurasi roster terlebih dahulu.")
    pattern = await _pattern_or_422(ctx, config.get("pattern_id"))
    start = _parse_date(config.get("start_date"), "Tanggal awal roster/POH")
    today = _today()
    if month:
        try:
            year, mon = (int(x) for x in month.split("-")[:2])
            range_start = date(year, mon, 1)
        except ValueError as exc:
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Bulan harus berformat YYYY-MM.") from exc
    else:
        range_start = today.replace(day=1)
    range_end = (range_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    work_days, off_days = int(pattern["work_days"]), int(pattern["off_days"])
    cycles = _cycles_between(start, work_days, off_days, range_start, range_end)
    employees = (await _active_employees_by_project(ctx, [project_id])).get(project_id, [])
    names = [e.get("full_name") for e in employees][:100]
    return {
        "project": {"id": project["id"], "code": project.get("code"), "name": project.get("name")},
        "pattern": _pattern_public(pattern),
        "start_date": start.isoformat(),
        "month": range_start.strftime("%Y-%m"),
        "active_employees": len(employees),
        "cycles": [
            {
                "cycle_no": n,
                "off_start": off_start.isoformat(),
                "off_end": off_end.isoformat(),
                "employee_count": len(employees),
                "employees": names,
            }
            for n, off_start, off_end in cycles
        ],
    }


@router.get("/summary")
async def roster_summary(project_id: Optional[str] = None, ctx: AuthContext = Depends(_view)):
    """Ringkasan roster per project: aktif, rencana, terkonfirmasi, sedang cuti, akan kembali, replacement."""
    allowed = await _visible_projects(ctx)
    project_ids = [project_id] if project_id else None
    if project_id:
        await _project_or_404(ctx, project_id)
    config_query: Dict[str, Any] = {"company_id": ctx.company_id, "roster_enabled": True}
    if project_ids:
        config_query["project_id"] = {"$in": project_ids}
    elif allowed is not None:
        config_query["project_id"] = {"$in": list(allowed)}
    configs = serialize_list(await ctx.tdb.project_roster_configs.find(config_query, NO_ID).to_list(2000))
    ids = [c["project_id"] for c in configs]
    projects = {p["id"]: p for p in serialize_list(await ctx.tdb.projects.find(
        {"company_id": ctx.company_id, "id": {"$in": ids}}, NO_ID).to_list(2000))}
    employees = await _active_employees_by_project(ctx, ids)
    plans = serialize_list(await ctx.tdb.roster_leave_plans.find(
        {"company_id": ctx.company_id, "project_id": {"$in": ids}, "plan_status": {"$in": [PLANNED, CONFIRMED]}},
        NO_ID,
    ).to_list(20000))
    today = _today()
    soon = today + timedelta(days=7)
    items = []
    totals = {"active_employees": 0, "planned": 0, "confirmed": 0, "on_leave": 0,
              "returning": 0, "replacement_needed": 0, "replacement_assigned": 0}
    for config in configs:
        pid = config["project_id"]
        if pid not in projects:
            continue
        project_plans = [p for p in plans if p.get("project_id") == pid]
        row = {
            "project": {"id": pid, "code": projects[pid].get("code"), "name": projects[pid].get("name")},
            "roster": _config_public(config, None),
            "active_employees": len(employees.get(pid, [])),
            "planned": sum(1 for p in project_plans if p.get("plan_status") == PLANNED
                           and str(p.get("off_start")) >= today.isoformat()),
            "confirmed": sum(1 for p in project_plans if p.get("plan_status") == CONFIRMED
                             and str(p.get("off_end")) >= today.isoformat()),
            "on_leave": sum(1 for p in project_plans if p.get("plan_status") == CONFIRMED
                            and str(p.get("off_start")) <= today.isoformat() <= str(p.get("off_end"))),
            "returning": sum(1 for p in project_plans if p.get("plan_status") == CONFIRMED
                             and str(p.get("off_start")) <= today.isoformat() <= str(p.get("off_end"))
                             and str(p.get("off_end")) <= soon.isoformat()),
            "replacement_needed": sum(1 for p in project_plans if p.get("replacement_needed")
                                      and not p.get("replacement_employee_id")
                                      and str(p.get("off_start")) >= today.isoformat()),
            "replacement_assigned": sum(1 for p in project_plans if p.get("replacement_employee_id")
                                        and str(p.get("off_start")) >= today.isoformat()),
        }
        for key in totals:
            totals[key] += row[key]
        items.append(row)
    return {"items": items, "totals": totals, "today": today.isoformat()}


@router.get("/plans")
async def list_plans(
    project_id: Optional[str] = None,
    plan_status: Optional[str] = Query(None, alias="status"),
    upcoming: bool = False,
    ctx: AuthContext = Depends(_view),
):
    allowed = await _visible_projects(ctx)
    query: Dict[str, Any] = {"company_id": ctx.company_id}
    if project_id:
        await _project_or_404(ctx, project_id)
        query["project_id"] = project_id
    elif allowed is not None:
        query["project_id"] = {"$in": list(allowed)}
    if plan_status:
        if plan_status not in PLAN_STATUSES:
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Status rencana tidak dikenal.")
        query["plan_status"] = plan_status
    today = _today()
    if upcoming:
        query["off_end"] = {"$gte": today.isoformat()}
    rows = serialize_list(await ctx.tdb.roster_leave_plans.find(query, NO_ID).sort("off_start", 1).to_list(2000))
    employee_ids = {r["employee_id"] for r in rows} | {
        r.get("replacement_employee_id") for r in rows if r.get("replacement_employee_id")
    }
    project_ids = {r["project_id"] for r in rows}
    employees = {e["id"]: e for e in serialize_list(await ctx.tdb.employees.find(
        {"company_id": ctx.company_id, "id": {"$in": list(employee_ids)}}, NO_ID).to_list(2000))}
    projects = {p["id"]: p for p in serialize_list(await ctx.tdb.projects.find(
        {"company_id": ctx.company_id, "id": {"$in": list(project_ids)}}, NO_ID).to_list(2000))}
    items = []
    for row in rows:
        emp = employees.get(row.get("employee_id"), {})
        project = projects.get(row.get("project_id"), {})
        off_start = str(row.get("off_start") or "")
        items.append({
            **row,
            "employee_name": emp.get("full_name"),
            "employee_number": emp.get("employee_number"),
            "project_name": project.get("name"),
            "project_code": project.get("code"),
            "replacement_employee_id": row.get("replacement_employee_id"),
            "replacement_employee_name": (employees.get(row.get("replacement_employee_id")) or {}).get(
                "full_name"),
            "days_until": (date.fromisoformat(off_start) - today).days if off_start else None,
        })
    return {"items": items, "total": len(items)}


@router.get("/employees")
async def list_project_employees(project_id: str = Query(...), q: Optional[str] = None,
                                ctx: AuthContext = Depends(_view)):
    """Karyawan aktif pada satu project — dipakai memilih karyawan pengganti.

    Memakai permission roster (bukan employee:view) agar GA yang mengelola roster tetap dapat
    memilih pengganti tanpa harus diberi akses penuh Data Karyawan.
    """
    await _project_or_404(ctx, project_id)
    rows = (await _active_employees_by_project(ctx, [project_id])).get(project_id, [])
    items = [{"id": e["id"], "full_name": e.get("full_name"),
              "employee_number": e.get("employee_number")} for e in rows]
    needle = (q or "").strip().lower()
    if needle:
        items = [i for i in items
                 if needle in (i["full_name"] or "").lower()
                 or needle in (i["employee_number"] or "").lower()]
    items.sort(key=lambda i: (i.get("full_name") or "").lower())
    return {"items": items, "total": len(items)}


@router.post("/plans/generate")
async def generate_plans(payload: Dict[str, Any] = Body(...), ctx: AuthContext = Depends(_create)):
    """Buat rencana cuti project untuk siklus off terdekat dalam horizon H-30 (idempoten)."""
    project_id = str(payload.get("project_id") or "")
    project = await _project_or_404(ctx, project_id)
    horizon_days = int(payload.get("horizon_days") or 30)
    if horizon_days < 1 or horizon_days > 90:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Horizon harus antara 1 dan 90 hari.")
    config = await ctx.tdb.project_roster_configs.find_one(
        {"company_id": ctx.company_id, "project_id": project_id}, NO_ID)
    if not config or not config.get("roster_enabled"):
        raise _err(status.HTTP_409_CONFLICT, "Roster project belum diaktifkan.")
    pattern = await _pattern_or_422(ctx, config.get("pattern_id"))
    start = _parse_date(config.get("start_date"), "Tanggal awal roster/POH")
    today = _today()
    horizon = today + timedelta(days=horizon_days)
    employees = (await _active_employees_by_project(ctx, [project_id])).get(project_id, [])
    existing = serialize_list(await ctx.tdb.roster_leave_plans.find(
        {"company_id": ctx.company_id, "employee_id": {"$in": [e["id"] for e in employees]},
         "off_start": {"$gte": today.isoformat()}}, NO_ID).to_list(20000))
    existing_keys = {(p.get("employee_id"), str(p.get("off_start"))) for p in existing}
    created = 0
    skipped = 0
    for emp in employees:
        nxt = _next_cycle(start, int(pattern["work_days"]), int(pattern["off_days"]), today)
        if not nxt:
            continue
        cycle_no, off_start, off_end = nxt
        if off_start > horizon:
            skipped += 1
            continue
        key = (emp["id"], off_start.isoformat())
        if key in existing_keys:
            skipped += 1
            continue
        await ctx.tdb.roster_leave_plans.insert_one({
            "id": new_id(), "company_id": ctx.company_id, "employee_id": emp["id"],
            "project_id": project_id, "pattern_id": pattern["id"], "cycle_no": cycle_no,
            "off_start": off_start.isoformat(), "off_end": off_end.isoformat(),
            "plan_status": PLANNED, "replacement_needed": True, "status": "active",
            **audit_fields(ctx.user_id, creating=True),
        })
        existing_keys.add(key)
        created += 1
    await log_action(ctx, "create", "roster", project_id, f"Rencana cuti {project.get('name')}",
                     after={"created": created, "skipped": skipped, "horizon_days": horizon_days},
                     notes="Generasi rencana cuti project (H-30)")
    return {
        "message": f"{created} rencana cuti dibuat, {skipped} dilewati.",
        "created": created, "skipped": skipped, "horizon_days": horizon_days,
    }


@router.patch("/plans/{plan_id}")
async def decide_plan(plan_id: str, payload: Dict[str, Any] = Body(...), ctx: AuthContext = Depends(_edit)):
    """Konfirmasi H-10 atau tunda rencana cuti project. Riwayat keputusan disimpan (status + catatan)."""
    plan = await ctx.tdb.roster_leave_plans.find_one(
        {"company_id": ctx.company_id, "id": plan_id}, NO_ID)
    if not plan:
        raise _err(status.HTTP_404_NOT_FOUND, "Rencana cuti tidak ditemukan.")
    await _project_or_404(ctx, plan["project_id"])
    if plan.get("plan_status") != PLANNED:
        raise _err(status.HTTP_409_CONFLICT, "Rencana ini sudah diputuskan.")
    action = str(payload.get("action") or "").upper()
    if action not in ("CONFIRM", "POSTPONE"):
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Aksi harus CONFIRM atau POSTPONE.")
    note = str(payload.get("note") or "").strip()
    if action == "POSTPONE" and len(note) < 3:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Alasan penundaan wajib diisi (minimal 3 karakter).")
    today = _today()
    off_start = _parse_date(plan.get("off_start"), "Tanggal mulai cuti")
    days_until = (off_start - today).days
    if days_until < 0:
        raise _err(status.HTTP_409_CONFLICT, "Jadwal cuti sudah lewat; tidak dapat diputuskan.")
    if days_until > 10:
        raise _err(status.HTTP_409_CONFLICT,
                   f"Konfirmasi H-10 baru dapat dilakukan maksimal 10 hari sebelum cuti (sisa {days_until} hari).")
    new_status = CONFIRMED if action == "CONFIRM" else POSTPONED
    await ctx.tdb.roster_leave_plans.update_one(
        {"company_id": ctx.company_id, "id": plan_id},
        {"$set": {
            "plan_status": new_status, "decided_at": now(), "decided_by": ctx.user_id,
            "decision_note": note or None, **audit_fields(ctx.user_id, creating=False),
        }})
    after = await ctx.tdb.roster_leave_plans.find_one(
        {"company_id": ctx.company_id, "id": plan_id}, NO_ID)
    await log_action(ctx, "approve" if action == "CONFIRM" else "postpone", "roster", plan_id,
                     f"Rencana cuti {plan.get('off_start')}",
                     before={"status": PLANNED}, after={"status": new_status, "note": note or None},
                     notes="Keputusan H-10 rencana cuti project")
    return {"message": "Rencana cuti dikonfirmasi." if action == "CONFIRM" else "Rencana cuti ditunda.",
            "item": serialize(after)}


@router.patch("/plans/{plan_id}/replacement")
async def assign_replacement(plan_id: str, payload: Dict[str, Any] = Body(...),
                             ctx: AuthContext = Depends(_edit)):
    """Tetapkan / ganti / batalkan karyawan pengganti untuk rencana cuti project.

    Pengganti wajib karyawan aktif pada project yang sama dan tidak memiliki rencana cuti
    project yang bertabrakan. Setiap perubahan dicatat di histori jadwal (append-only).
    """
    plan = await ctx.tdb.roster_leave_plans.find_one(
        {"company_id": ctx.company_id, "id": plan_id}, NO_ID)
    if not plan:
        raise _err(status.HTTP_404_NOT_FOUND, "Rencana cuti tidak ditemukan.")
    await _project_or_404(ctx, plan.get("project_id"))
    if plan.get("plan_status") == POSTPONED:
        raise _err(status.HTTP_409_CONFLICT,
                   "Rencana cuti sedang ditunda. Konfirmasi ulang jadwal sebelum menetapkan pengganti.")
    raw = payload.get("employee_id")
    replacement_id = str(raw).strip() if raw else None
    reason = str(payload.get("reason") or "").strip() or None

    current_id = plan.get("replacement_employee_id")
    before: Dict[str, Any] = {"replacement_employee_id": current_id, "replacement_name": None}
    if current_id:
        prev = await ctx.tdb.employees.find_one(
            {"company_id": ctx.company_id, "id": current_id}, NO_ID)
        before["replacement_name"] = (prev or {}).get("full_name")

    if replacement_id:
        if replacement_id == plan.get("employee_id"):
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                       "Karyawan pengganti tidak boleh sama dengan karyawan yang cuti.")
        if replacement_id == current_id:
            raise _err(status.HTTP_409_CONFLICT, "Karyawan ini sudah ditetapkan sebagai pengganti.")
        emp = await ctx.tdb.employees.find_one(
            {"company_id": ctx.company_id, "id": replacement_id}, NO_ID)
        if not emp:
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                       "Karyawan pengganti tidak ditemukan pada perusahaan aktif.")
        if emp.get("status") != "active":
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Karyawan pengganti harus berstatus aktif.")
        if emp.get("project_id") != plan.get("project_id"):
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                       "Karyawan pengganti harus berada pada project yang sama dengan rencana cuti.")
        overlap = await ctx.tdb.roster_leave_plans.find_one({
            "company_id": ctx.company_id, "employee_id": replacement_id,
            "plan_status": {"$in": [PLANNED, CONFIRMED]},
            "off_start": {"$lte": plan.get("off_end")}, "off_end": {"$gte": plan.get("off_start")},
        }, NO_ID)
        if overlap:
            raise _err(status.HTTP_409_CONFLICT,
                       "Karyawan pengganti memiliki rencana cuti project yang bertabrakan pada periode ini.")
    elif not current_id:
        raise _err(status.HTTP_409_CONFLICT, "Belum ada karyawan pengganti yang ditetapkan.")

    patch = {
        "replacement_employee_id": replacement_id,
        "replacement_assigned_at": now() if replacement_id else None,
        "replacement_assigned_by": ctx.user_id if replacement_id else None,
        "replacement_assigned_by_name": (ctx.user or {}).get("full_name") if replacement_id else None,
        **audit_fields(ctx.user_id, creating=False),
    }
    await ctx.tdb.roster_leave_plans.update_one(
        {"company_id": ctx.company_id, "id": plan_id}, {"$set": patch})
    after = await ctx.tdb.roster_leave_plans.find_one(
        {"company_id": ctx.company_id, "id": plan_id}, NO_ID)
    replacement_name = None
    if replacement_id:
        emp = await ctx.tdb.employees.find_one(
            {"company_id": ctx.company_id, "id": replacement_id}, NO_ID)
        replacement_name = (emp or {}).get("full_name")
    after_snapshot = {"replacement_employee_id": replacement_id, "replacement_name": replacement_name}
    await _write_history(ctx, after, None, "REPLACEMENT", before, after_snapshot, reason)
    await log_action(ctx, "update", "roster", plan_id,
                     f"Pengganti cuti {plan.get('off_start')}",
                     before=before, after=after_snapshot,
                     notes=("Pengganti dibatalkan" if not replacement_id
                            else f"Pengganti ditetapkan: {replacement_name}"))
    return {
        "message": (f"Pengganti {replacement_name} ditetapkan." if replacement_id
                    else "Penugasan pengganti dibatalkan."),
        "item": {**serialize(after), "replacement_employee_name": replacement_name},
    }
