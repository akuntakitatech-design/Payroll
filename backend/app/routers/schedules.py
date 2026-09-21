"""Jadwal Kerja: penetapan per karyawan/massal, tampilan bulanan, dan
Import Jadwal Excel (Upload -> Mapping -> Preview -> Validasi -> Simpan).
"""
from __future__ import annotations

import json
from datetime import date as _date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..core.audit import log_action
from ..core.db import ASCENDING, NO_ID, audit_fields, get_db, new_id, now, serialize_list
from ..core.deps import AuthContext, require_permission
from ..core.repo import TenantRepository
from ..core import time_excel as tx
from ..core import time_service as svc
from ..core import timekeeping as tk

router = APIRouter(prefix="/schedules", tags=["Time Management - Jadwal Kerja"])


def _perm(action: str):
    return require_permission("attendance", action, "attendance")


class ScheduleBulkInput(BaseModel):
    employee_ids: List[str] = Field(..., min_length=1)
    date_from: str
    date_to: str
    shift_id: Optional[str] = None
    work_location_id: Optional[str] = None
    is_day_off: bool = False
    weekdays: Optional[List[int]] = None  # 1=Senin .. 7=Minggu
    overwrite_existing: bool = False
    notes: Optional[str] = None


async def _decorate(company_id: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    shifts_by_id, _ = await svc.shift_index(company_id)
    locations_by_id, _ = await svc.location_index(company_id)
    employees_by_id, _ = await svc.employee_index(company_id)
    cal = await tk.calendar_map(company_id, [r["work_date"] for r in rows])
    out: List[Dict[str, Any]] = []
    for r in rows:
        shift = shifts_by_id.get(r.get("shift_id") or "")
        loc = locations_by_id.get(r.get("work_location_id") or "")
        emp = employees_by_id.get(r.get("employee_id") or "")
        day_type = tk.resolve_day_type(r["work_date"], r, cal.get(r["work_date"]))
        out.append({
            **r,
            "employee_name": (emp or {}).get("full_name"),
            "employee_number": (emp or {}).get("employee_number"),
            "department_id": (emp or {}).get("department_id"),
            "shift_name": (shift or {}).get("name"),
            "shift_code": (shift or {}).get("code"),
            "shift_window": ("OFF" if r.get("is_day_off") else
                             f"{(shift or {}).get('start_time') or '-'} - {(shift or {}).get('end_time') or '-'}"),
            "is_overnight": bool((shift or {}).get("is_overnight")),
            "work_location_name": (loc or {}).get("name"),
            "day_type": day_type,
            "day_type_label": tk.DAY_TYPES.get(day_type, "-"),
            "source_label": tk.ATTENDANCE_SOURCES.get(r.get("source") or "", "Manual HR"),
        })
    return out


@router.get("")
async def list_schedules(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    period: Optional[str] = None,
    employee_id: Optional[str] = None,
    department_id: Optional[str] = None,
    work_location_id: Optional[str] = None,
    shift_id: Optional[str] = None,
    ctx: AuthContext = Depends(_perm("view")),
):
    db = get_db()
    if period:
        date_from, date_to = tk.month_bounds(period)
    if not date_from or not date_to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Tentukan Periode atau rentang Tanggal Mulai dan Tanggal Selesai.")
    date_from = tk.parse_date_str(date_from, "Tanggal Mulai")
    date_to = tk.parse_date_str(date_to, "Tanggal Selesai")

    query: Dict[str, Any] = {
        "company_id": ctx.company_id, "status": {"$ne": "deleted"},
        "work_date": {"$gte": date_from, "$lte": date_to},
    }
    scoped_employee = await svc.scope_employee_id(ctx)
    if scoped_employee:
        employee_id, department_id = scoped_employee, None  # karyawan: hanya jadwal sendiri
    if employee_id:
        query["employee_id"] = employee_id
    if work_location_id:
        query["work_location_id"] = work_location_id
    if shift_id:
        query["shift_id"] = shift_id
    if department_id:
        emps = await db.employees.find(
            {"company_id": ctx.company_id, "department_id": department_id}, NO_ID).to_list(2000)
        query["employee_id"] = {"$in": [e["id"] for e in emps] or ["-"]}

    rows = await db.work_schedules.find(query, NO_ID).sort(
        [("work_date", ASCENDING), ("employee_id", ASCENDING)]).to_list(5000)
    items = await _decorate(ctx.company_id, serialize_list(rows))
    calendar = await tk.calendar_map(ctx.company_id, tk.date_range(date_from, date_to))
    return {
        "items": items, "total": len(items), "date_from": date_from, "date_to": date_to,
        "calendar_days": [{**v, "day_type_label": tk.DAY_TYPES.get(v.get("day_type") or "", "-")}
                          for v in calendar.values()],
    }


async def _validate_refs(ctx: AuthContext, shift_id: Optional[str], location_id: Optional[str],
                         is_day_off: bool) -> Dict[str, Any]:
    db = get_db()
    shift = None
    if not is_day_off:
        if not shift_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Shift wajib dipilih kecuali jadwal ditandai OFF.")
        shift = await db.work_shifts.find_one(
            {"company_id": ctx.company_id, "id": shift_id, "status": "active"}, NO_ID)
        if not shift:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Shift tidak ditemukan atau sudah nonaktif.")
    if location_id:
        loc = await db.work_locations.find_one(
            {"company_id": ctx.company_id, "id": location_id, "status": {"$ne": "deleted"}}, NO_ID)
        if not loc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Lokasi Kerja tidak ditemukan.")
    return shift or {}


@router.post("/bulk", status_code=status.HTTP_201_CREATED)
async def assign_bulk(payload: ScheduleBulkInput, ctx: AuthContext = Depends(_perm("create"))):
    svc.require_hr_scope(ctx)
    date_from = tk.parse_date_str(payload.date_from, "Tanggal Mulai")
    date_to = tk.parse_date_str(payload.date_to, "Tanggal Selesai")
    dates = tk.date_range(date_from, date_to)
    if payload.weekdays:
        allowed = {int(w) for w in payload.weekdays}
        dates = [d for d in dates if _date.fromisoformat(d).isoweekday() in allowed]
    if not dates:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Tidak ada tanggal terpilih. Periksa rentang tanggal dan pilihan hari.")

    await tk.assert_period_open(ctx.company_id, *dates)
    shift = await _validate_refs(ctx, payload.shift_id, payload.work_location_id, payload.is_day_off)

    db = get_db()
    employees_by_id, _ = await svc.employee_index(ctx.company_id)
    created = skipped = updated = 0
    problems: List[Dict[str, str]] = []

    for employee_id in payload.employee_ids:
        emp = employees_by_id.get(employee_id)
        if not emp:
            problems.append({"employee_id": employee_id,
                             "message": "Karyawan tidak ditemukan pada perusahaan aktif."})
            continue
        if emp.get("status") != "active":
            problems.append({"employee_id": employee_id,
                             "message": f"{emp.get('full_name')} tidak berstatus aktif."})
            continue
        for work_date in dates:
            existing = await db.work_schedules.find_one(
                {"company_id": ctx.company_id, "employee_id": employee_id, "work_date": work_date}, NO_ID)
            doc = {
                "shift_id": None if payload.is_day_off else payload.shift_id,
                "shift_code": None if payload.is_day_off else shift.get("code"),
                "work_location_id": payload.work_location_id or emp.get("work_location_id"),
                "is_day_off": bool(payload.is_day_off),
                "notes": payload.notes, "source": "manual",
            }
            if existing:
                if not payload.overwrite_existing:
                    skipped += 1
                    continue
                await db.work_schedules.update_one(
                    {"company_id": ctx.company_id, "id": existing["id"]},
                    {"$set": {**doc, "status": "active", "updated_at": now(), "updated_by": ctx.user_id}})
                updated += 1
            else:
                await db.work_schedules.insert_one({
                    "id": new_id(), "company_id": ctx.company_id, "status": "active",
                    "employee_id": employee_id, "work_date": work_date, **doc,
                    **audit_fields(ctx.user_id)})
                created += 1

    await log_action(ctx, "schedule_assign", "attendance", None,
                     f"Jadwal {date_from} s/d {date_to} ({len(payload.employee_ids)} karyawan)",
                     after={"created": created, "updated": updated, "skipped": skipped,
                            "shift_id": payload.shift_id, "is_day_off": payload.is_day_off},
                     module="attendance", notes=payload.notes)
    return {
        "created": created, "updated": updated, "skipped": skipped, "problems": problems,
        "message": f"{created} jadwal dibuat, {updated} diperbarui, {skipped} dilewati karena sudah ada.",
    }


@router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: str, ctx: AuthContext = Depends(_perm("delete"))):
    repo = TenantRepository("work_schedules", ctx.company_id)
    row = await repo.get(schedule_id)
    await tk.assert_period_open(ctx.company_id, row["work_date"])
    db = get_db()
    att = await db.attendances.find_one({
        "company_id": ctx.company_id, "employee_id": row["employee_id"],
        "work_date": row["work_date"], "status": {"$ne": "deleted"}}, NO_ID)
    if att and (att.get("check_in_at") or att.get("check_out_at")):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Jadwal ini sudah memiliki transaksi absensi. "
                            "Koreksi atau hapus absensinya terlebih dahulu.")
    before, after = await repo.update(schedule_id, {"status": "deleted"}, ctx.user_id)
    await log_action(ctx, "delete", "attendance", schedule_id, f"Jadwal {row['work_date']}",
                     before=before, after=after, module="attendance")
    return {"message": "Jadwal berhasil dihapus."}


# ==========================================================================
# IMPORT JADWAL EXCEL
# ==========================================================================
@router.get("/imports/template")
async def schedule_template(ctx: AuthContext = Depends(_perm("create"))):
    svc.require_hr_scope(ctx)
    _, shifts_by_code = await svc.shift_index(ctx.company_id)
    _, locs_by_code = await svc.location_index(ctx.company_id)
    data = tx.build_schedule_template(sorted(shifts_by_code.keys()), sorted(locs_by_code.keys()))
    return Response(content=data,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="Template-Import-Jadwal.xlsx"'})


@router.post("/imports/analyze")
async def analyze_schedule_file(file: UploadFile = File(...), ctx: AuthContext = Depends(_perm("create"))):
    svc.require_hr_scope(ctx)
    """Langkah 1: baca header + contoh baris. TIDAK menulis ke database."""
    headers, rows = tx.read_rows(await file.read())
    return {
        "filename": file.filename, "headers": headers, "total_rows": len(rows),
        "sample_rows": rows[:10],
        "suggested_mapping": tx.guess_mapping(headers, tx.SCHEDULE_FIELD_ALIASES),
        "fields": [{"key": k, "label": v, "required": k in tx.SCHEDULE_REQUIRED_FIELDS}
                   for k, v in tx.SCHEDULE_FIELD_LABELS.items()],
    }


async def _validate_schedule_rows(ctx: AuthContext, rows: List[Dict[str, Any]],
                                  mapping: Dict[str, str], overwrite: bool) -> Dict[str, Any]:
    db = get_db()
    _, employees_by_number = await svc.employee_index(ctx.company_id)
    _, shifts_by_code = await svc.shift_index(ctx.company_id)
    _, locs_by_code = await svc.location_index(ctx.company_id)

    seen = set()
    prepared: List[Dict[str, Any]] = []
    for row in rows:
        errors: List[str] = []

        def get(field: str):
            column = mapping.get(field)
            return row.get(column) if column else None

        number = str(get("employee_number") or "").strip().upper()
        emp = employees_by_number.get(number)
        if not number:
            errors.append("Nomor Karyawan / NIK kosong.")
        elif not emp:
            errors.append(f"Karyawan dengan nomor '{number}' tidak ditemukan pada perusahaan aktif.")
        elif emp.get("status") != "active":
            errors.append(f"Karyawan '{emp.get('full_name')}' tidak berstatus aktif.")

        work_date = None
        raw_date = str(get("work_date") or "").strip()[:10]
        if not raw_date:
            errors.append("Tanggal kosong.")
        else:
            try:
                work_date = tk.parse_date_str(raw_date, "Tanggal")
            except HTTPException as exc:
                errors.append(str(exc.detail))

        is_day_off = tx.truthy(get("is_day_off"))
        shift_code = str(get("shift_code") or "").strip().upper()
        shift = shifts_by_code.get(shift_code) if shift_code else None
        if shift_code and not shift:
            errors.append(f"Kode Shift '{shift_code}' tidak ditemukan.")
        if not is_day_off and not shift:
            errors.append("Kode Shift wajib diisi bila baris bukan OFF.")

        loc_code = str(get("location_code") or "").strip().upper()
        loc = locs_by_code.get(loc_code) if loc_code else None
        if loc_code and not loc:
            errors.append(f"Kode Lokasi Kerja '{loc_code}' tidak ditemukan.")

        duplicate_in_file = False
        if emp and work_date:
            key = (emp["id"], work_date)
            if key in seen:
                duplicate_in_file = True
                errors.append("Baris duplikat di dalam berkas (karyawan & tanggal sama).")
            seen.add(key)

        existing = None
        if emp and work_date and not errors:
            existing = await db.work_schedules.find_one(
                {"company_id": ctx.company_id, "employee_id": emp["id"], "work_date": work_date}, NO_ID)
            closed = await tk.closed_period_keys(ctx.company_id, [tk.period_key_of(work_date)])
            if closed:
                errors.append(f"Periode {tk.period_label_of(closed[0])} sudah ditutup.")

        action = "error" if errors else (("update" if overwrite else "skip") if existing else "create")
        prepared.append({
            "row": row.get("__row__"), "employee_number": number,
            "employee_name": (emp or {}).get("full_name") or str(get("employee_name") or ""),
            "employee_id": (emp or {}).get("id"), "work_date": work_date,
            "shift_code": shift_code or None, "shift_id": (shift or {}).get("id"),
            "location_code": loc_code or None,
            "work_location_id": (loc or {}).get("id") or (emp or {}).get("work_location_id"),
            "is_day_off": is_day_off, "notes": get("note"),
            "duplicate_in_file": duplicate_in_file, "existing": bool(existing),
            "action": action, "errors": errors,
        })

    summary = {
        "total_rows": len(prepared),
        "create_rows": sum(1 for r in prepared if r["action"] == "create"),
        "update_rows": sum(1 for r in prepared if r["action"] == "update"),
        "skipped_rows": sum(1 for r in prepared if r["action"] == "skip"),
        "error_rows": sum(1 for r in prepared if r["action"] == "error"),
    }
    return {"rows": prepared, "summary": summary}


def _mapping_from_form(raw: str, required: List[str], labels: Dict[str, str]) -> Dict[str, str]:
    try:
        mapping = json.loads(raw)
    except Exception:  # noqa: BLE001
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pemetaan kolom tidak valid.")
    for field in required:
        if not mapping.get(field):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"Kolom '{labels[field]}' wajib dipetakan.")
    return mapping


@router.post("/imports/preview")
async def preview_schedule_import(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    overwrite_existing: bool = Form(False),
    ctx: AuthContext = Depends(_perm("create")),
):
    """Langkah 2: validasi penuh TANPA menulis ke database."""
    svc.require_hr_scope(ctx)
    mapping_dict = _mapping_from_form(mapping, tx.SCHEDULE_REQUIRED_FIELDS, tx.SCHEDULE_FIELD_LABELS)
    _, rows = tx.read_rows(await file.read())
    result = await _validate_schedule_rows(ctx, rows, mapping_dict, overwrite_existing)
    return {"filename": file.filename, **result}


@router.post("/imports/commit")
async def commit_schedule_import(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    overwrite_existing: bool = Form(False),
    ctx: AuthContext = Depends(_perm("create")),
):
    """Langkah 3: simpan. Hanya baris valid yang ditulis."""
    svc.require_hr_scope(ctx)
    mapping_dict = _mapping_from_form(mapping, tx.SCHEDULE_REQUIRED_FIELDS, tx.SCHEDULE_FIELD_LABELS)
    _, rows = tx.read_rows(await file.read())
    result = await _validate_schedule_rows(ctx, rows, mapping_dict, overwrite_existing)

    db = get_db()
    batch_id = new_id()
    created = updated = 0
    for r in result["rows"]:
        if r["action"] == "create":
            await db.work_schedules.insert_one({
                "id": new_id(), "company_id": ctx.company_id, "status": "active",
                "employee_id": r["employee_id"], "work_date": r["work_date"],
                "shift_id": r["shift_id"], "shift_code": r["shift_code"],
                "work_location_id": r["work_location_id"], "is_day_off": r["is_day_off"],
                "notes": r["notes"], "source": "excel_import", "import_batch_id": batch_id,
                **audit_fields(ctx.user_id)})
            created += 1
        elif r["action"] == "update":
            await db.work_schedules.update_one(
                {"company_id": ctx.company_id, "employee_id": r["employee_id"], "work_date": r["work_date"]},
                {"$set": {"shift_id": r["shift_id"], "shift_code": r["shift_code"],
                          "work_location_id": r["work_location_id"], "is_day_off": r["is_day_off"],
                          "notes": r["notes"], "source": "excel_import", "import_batch_id": batch_id,
                          "status": "active", "updated_at": now(), "updated_by": ctx.user_id}})
            updated += 1

    batch = {
        "id": batch_id, "company_id": ctx.company_id, "status": "active",
        "import_kind": "schedule", "filename": file.filename, "mapping": mapping_dict,
        "options": {"overwrite_existing": bool(overwrite_existing)},
        "total_rows": result["summary"]["total_rows"], "success_rows": created,
        "updated_rows": updated, "error_rows": result["summary"]["error_rows"],
        "skipped_rows": result["summary"]["skipped_rows"],
        "errors": [{"row": r["row"], "employee_number": r["employee_number"], "errors": r["errors"]}
                   for r in result["rows"] if r["action"] == "error"][:500],
        "imported_by": ctx.user_id, "imported_by_name": ctx.user.get("full_name"),
        "imported_at": now(),
        "period_keys": sorted({tk.period_key_of(r["work_date"]) for r in result["rows"] if r.get("work_date")}),
        **audit_fields(ctx.user_id),
    }
    await db.time_imports.insert_one(dict(batch))
    await log_action(ctx, "import", "attendance", batch_id, f"Import Jadwal: {file.filename}",
                     after=batch, module="attendance")
    return {
        "batch_id": batch_id,
        "summary": {**result["summary"], "created_rows": created, "updated_rows": updated},
        "errors": batch["errors"],
        "message": (f"Import jadwal selesai: {created} dibuat, {updated} diperbarui, "
                    f"{result['summary']['skipped_rows']} dilewati, "
                    f"{result['summary']['error_rows']} gagal."),
    }


@router.get("/imports")
async def list_schedule_imports(ctx: AuthContext = Depends(_perm("view"))):
    svc.require_hr_scope(ctx)
    db = get_db()
    rows = await db.time_imports.find(
        {"company_id": ctx.company_id, "import_kind": "schedule"}, NO_ID
    ).sort("imported_at", -1).to_list(100)
    return {"items": serialize_list(rows), "total": len(rows)}
