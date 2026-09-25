"""Upgrade 01D - Current Assignment / Penempatan: Tetapkan, Pindah, Akhiri + riwayat.

RBAC existing: employee:view (lihat) / employee:edit (ubah). Tanpa permission baru.
Semua perubahan dalam SATU transaksi DB (assignment lama ditutup + baru dibuat + sinkron legacy + audit).
Opsi ubah Status Karyawan saat Akhiri Penempatan memakai flow 01B (`change_employee_status`) sehingga
riwayat status + audit 01B tetap tercatat.
"""
from datetime import date, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..core import assignment as asg
from ..core.audit import build_audit_entry
from ..core.db import NO_ID, now, serialize, serialize_list, transaction
from ..core.deps import AuthContext, require_permission
from ..core.employee_status import today_local
from ..core.repo import TenantRepository
from .employee_status import EmployeeStatusChange, change_employee_status

router = APIRouter(prefix="/employees", tags=["employee-assignment"])


class PlacementIn(BaseModel):
    project_id: Optional[str] = None
    work_location_id: Optional[str] = None
    branch_id: Optional[str] = None
    department_id: Optional[str] = None
    division_id: Optional[str] = None
    position_id: Optional[str] = None
    cost_center_id: Optional[str] = None
    start_date: str
    reason: str = Field(min_length=3, max_length=255)
    notes: Optional[str] = Field(None, max_length=1000)


class EndIn(BaseModel):
    end_date: str
    reason: str = Field(min_length=3, max_length=255)
    notes: Optional[str] = Field(None, max_length=1000)
    # opsional: ubah Status Karyawan lewat flow 01B (mis. ke status kategori STANDBY). None = status tetap.
    change_status_id: Optional[str] = None


def _err(msg: str, code: int = status.HTTP_422_UNPROCESSABLE_ENTITY) -> HTTPException:
    return HTTPException(code, msg)


def _check_date(value: str, label: str, not_before: Optional[str] = None) -> str:
    try:
        d = date.fromisoformat((value or "").strip()).isoformat()
    except ValueError as exc:
        raise _err(f"Format {label} harus YYYY-MM-DD.") from exc
    if d > today_local():
        raise _err(f"{label.capitalize()} tidak boleh melebihi hari ini (penempatan terjadwal belum didukung).")
    if not_before and d < not_before:
        raise _err(f"{label.capitalize()} tidak boleh sebelum tanggal mulai penempatan saat ini ({not_before}).")
    return d


async def _employee(ctx: AuthContext, employee_id: str) -> Dict[str, Any]:
    emp = await TenantRepository("employees", ctx.company_id).get(employee_id)
    if emp.get("status") == "deleted":
        raise _err("Data tidak ditemukan pada perusahaan aktif Anda.", status.HTTP_404_NOT_FOUND)
    if emp.get("status") == "archived":
        raise _err("Karyawan sedang diarsipkan. Pulihkan dari arsip terlebih dahulu.", status.HTTP_409_CONFLICT)
    return emp


async def _names(ctx: AuthContext, rows):
    db, cid = ctx.tdb, ctx.company_id
    maps = {}
    for f, (coll, _l) in asg.PLACEMENT_FIELDS.items():
        ids = list({r.get(f) for r in rows if r.get(f)})
        maps[f] = {m["id"]: m.get("name") for m in await db[coll].find({"company_id": cid, "id": {"$in": ids}}, NO_ID).to_list(1000)} if ids else {}
    for r in rows:
        for f in asg.PLACEMENT_FIELDS:
            r[f.replace("_id", "_name")] = maps[f].get(r.get(f))
        r["company_name"] = (ctx.company or {}).get("name")
    return rows


def _label(row: Optional[Dict[str, Any]]) -> Optional[str]:
    if not row:
        return None
    return " / ".join(x for x in (row.get("project_name") or "(tanpa project)", row.get("work_location_name")) if x)


def _legacy_sync(doc: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Compatibility bridge: employees.* mengikuti assignment aktif. Tanpa assignment aktif -> project_id NULL,
    field organisasi lain (departemen/jabatan/lokasi) dibiarkan agar modul lama (mis. geofence absensi) tetap jalan."""
    if not doc:
        return {"project_id": None}
    return {f: doc.get(f) for f in asg.PLACEMENT_FIELDS}


@router.get("/{employee_id}/assignments")
async def list_assignments(employee_id: str, ctx: AuthContext = Depends(require_permission("employee", "view"))):
    await TenantRepository("employees", ctx.company_id).get(employee_id)
    rows = serialize_list(await ctx.tdb[asg.TABLE].find(
        {"company_id": ctx.company_id, "employee_id": employee_id}, NO_ID).sort("created_at", -1).to_list(500))
    await _names(ctx, rows)
    current = next((r for r in rows if r.get("assignment_status") == asg.ACTIVE), None)
    return {"current": current, "items": rows}


async def _write(ctx: AuthContext, emp: Dict[str, Any], old: Optional[Dict[str, Any]], old_end: Optional[Dict[str, Any]],
                 new_doc: Optional[Dict[str, Any]], action: str, notes: str) -> None:
    """SATU transaksi: lock karyawan -> tutup assignment lama -> buat baru -> sinkron legacy -> audit."""
    cid, eid = ctx.company_id, emp["id"]
    names_old = (await _names(ctx, [dict(old)]))[0] if old else None
    names_new = (await _names(ctx, [dict(new_doc)]))[0] if new_doc else None
    audit = build_audit_entry(
        ctx, action, "employee", eid, emp.get("full_name"),
        before={"penempatan": _label(names_old), "assignment_id": (old or {}).get("id"),
                "mulai": (old or {}).get("start_date")} if old else None,
        after={"penempatan": _label(names_new), "assignment_id": (new_doc or {}).get("id"),
               "mulai": (new_doc or {}).get("start_date"),
               "berakhir_sebelumnya": (old_end or {}).get("end_date")},
        notes=notes)
    async with transaction() as tx:
        locked = await tx.select_one_for_update("employees", {"company_id": cid, "id": eid})
        if not locked:
            raise _err("Data tidak ditemukan pada perusahaan aktif Anda.", status.HTTP_404_NOT_FOUND)
        current = await tx.select_one_for_update(asg.TABLE, {"company_id": cid, "employee_id": eid, "assignment_status": asg.ACTIVE})
        if (current or {}).get("id") != (old or {}).get("id"):
            raise _err("Penempatan karyawan baru saja diubah oleh proses lain. Muat ulang lalu coba lagi.", status.HTTP_409_CONFLICT)
        if old and old_end:
            await tx.update(asg.TABLE, {"company_id": cid, "id": old["id"]}, old_end)
        if new_doc:
            await tx.insert(asg.TABLE, new_doc)
        await tx.update("employees", {"company_id": cid, "id": eid},
                        {**_legacy_sync(new_doc if new_doc else None), "updated_at": now(), "updated_by": ctx.user_id})
        await tx.insert("audit_logs", audit)


def _placement(payload: PlacementIn, emp: Dict[str, Any]) -> Dict[str, Any]:
    """Field yang TIDAK dikirim mewarisi data organisasi karyawan saat ini (agar pemanggil API tidak
    mengosongkan departemen/jabatan tanpa sengaja). Field yang dikirim eksplisit `null` = dikosongkan.
    Project & lokasi kerja selalu mengikuti payload (inti penempatan)."""
    sent = payload.model_fields_set
    data = {}
    for f in asg.PLACEMENT_FIELDS:
        if f in sent or f in ("project_id", "work_location_id"):
            data[f] = getattr(payload, f) or None
        else:
            data[f] = emp.get(f) or None
    if not data.get("project_id") and not data.get("work_location_id"):
        raise _err("Pilih minimal Project atau Lokasi kerja / site.")
    return data


@router.post("/{employee_id}/assignments", status_code=status.HTTP_201_CREATED)
async def assign(employee_id: str, payload: PlacementIn, ctx: AuthContext = Depends(require_permission("employee", "edit"))):
    """Tetapkan Penempatan: hanya bila karyawan belum punya assignment ACTIVE."""
    emp = await _employee(ctx, employee_id)
    data = _placement(payload, emp)
    await asg.validate_placement(ctx.company_id, data)
    start = _check_date(payload.start_date, "tanggal mulai")
    if await asg.active_assignment(ctx.company_id, employee_id):
        raise _err("Karyawan sudah memiliki penempatan aktif. Gunakan 'Pindah Penempatan'.", status.HTTP_409_CONFLICT)
    doc = asg.new_assignment_doc(ctx.company_id, employee_id, data, start, "MANUAL", payload.reason.strip(),
                                 payload.notes, ctx.user_id)
    await _write(ctx, emp, None, None, doc, "assignment_create", f"Penempatan ditetapkan (mulai {start}). Alasan: {payload.reason.strip()}")
    return {"message": "Penempatan berhasil ditetapkan.", "assignment": serialize(doc)}


@router.post("/{employee_id}/assignments/transfer", status_code=status.HTTP_201_CREATED)
async def transfer(employee_id: str, payload: PlacementIn, ctx: AuthContext = Depends(require_permission("employee", "edit"))):
    """Pindah Penempatan: assignment lama ENDED (end_date = sehari sebelum mulai baru; bila itu jatuh sebelum
    tanggal mulai lama, end_date = tanggal mulai baru), assignment baru ACTIVE. Satu transaksi."""
    emp = await _employee(ctx, employee_id)
    old = await asg.active_assignment(ctx.company_id, employee_id)
    if not old:
        raise _err("Karyawan belum memiliki penempatan aktif. Gunakan 'Tetapkan Penempatan'.", status.HTTP_409_CONFLICT)
    data = _placement(payload, emp)
    await asg.validate_placement(ctx.company_id, data)
    start = _check_date(payload.start_date, "tanggal mulai", not_before=old.get("start_date"))
    prev_day = (date.fromisoformat(start) - timedelta(days=1)).isoformat()
    old_end_date = prev_day if (not old.get("start_date") or prev_day >= old["start_date"]) else start
    if all((data.get(f) or None) == (old.get(f) or None) for f in asg.PLACEMENT_FIELDS):
        raise _err("Penempatan baru sama dengan penempatan saat ini.")
    reason = payload.reason.strip()
    old_end = {"assignment_status": asg.ENDED, "end_date": old_end_date, "end_reason": f"Pindah penempatan: {reason}",
               "ended_by": ctx.user_id, "updated_at": now(), "updated_by": ctx.user_id}
    doc = asg.new_assignment_doc(ctx.company_id, employee_id, data, start, "TRANSFER", reason, payload.notes,
                                 ctx.user_id, previous_assignment_id=old["id"])
    await _write(ctx, emp, old, old_end, doc, "assignment_transfer", f"Pindah penempatan (efektif {start}). Alasan: {reason}")
    return {"message": "Penempatan berhasil dipindahkan.", "assignment": serialize(doc)}


@router.post("/{employee_id}/assignments/end")
async def end(employee_id: str, payload: EndIn, ctx: AuthContext = Depends(require_permission("employee", "edit"))):
    """Akhiri Penempatan: tidak ada assignment ACTIVE setelahnya; tidak membuat assignment baru otomatis."""
    emp = await _employee(ctx, employee_id)
    old = await asg.active_assignment(ctx.company_id, employee_id)
    if not old:
        raise _err("Karyawan tidak memiliki penempatan aktif.", status.HTTP_409_CONFLICT)
    end_date = _check_date(payload.end_date, "tanggal akhir", not_before=old.get("start_date"))
    reason = payload.reason.strip()
    status_payload = None
    if payload.change_status_id:
        if not ctx.has_permission("employee_status", "change"):
            raise _err("Anda tidak memiliki izin mengubah Status Karyawan.", status.HTTP_403_FORBIDDEN)
        # validasi status SEBELUM assignment ditutup (flow 01B yang sama dipakai setelahnya)
        st = await ctx.tdb.employee_business_statuses.find_one(
            {"company_id": ctx.company_id, "id": payload.change_status_id}, NO_ID)
        if not st or not st.get("is_active"):
            raise _err("Status karyawan tujuan tidak ditemukan / nonaktif pada perusahaan aktif Anda.")
        if st["id"] == emp.get("current_employee_status_id"):
            raise _err("Status karyawan tujuan sama dengan status saat ini.")
        status_payload = EmployeeStatusChange(new_status_id=st["id"], effective_date=end_date,
                                              reason=f"Penempatan berakhir: {reason}"[:255], notes=payload.notes)
    old_end = {"assignment_status": asg.ENDED, "end_date": end_date, "end_reason": reason, "end_notes": payload.notes,
               "ended_by": ctx.user_id, "updated_at": now(), "updated_by": ctx.user_id}
    await _write(ctx, emp, old, old_end, None, "assignment_end", f"Penempatan diakhiri (efektif {end_date}). Alasan: {reason}")
    status_result, status_error = None, None
    if status_payload:
        # flow 01B yang sama (riwayat status + audit 01B). Sudah divalidasi di atas; bila tetap gagal,
        # penempatan tetap berakhir dan pesan dikembalikan agar HR bisa mengulang lewat "Ubah Status".
        try:
            status_result = await change_employee_status(employee_id, status_payload, ctx)
        except HTTPException as exc:
            status_error = str(exc.detail)
    msg = "Penempatan berhasil diakhiri."
    if status_error:
        msg += f" Status karyawan TIDAK diubah: {status_error} Silakan ulangi lewat 'Ubah Status'."
    return {"message": msg, "status_change": status_result, "status_change_error": status_error}
