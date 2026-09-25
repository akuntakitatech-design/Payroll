"""Upgrade 01B - Master Status Karyawan + Ubah Status + Riwayat Status.

Semua endpoint tenant-aware di sisi server (company_id dari AuthContext, bukan dari
request). Status milik tenant lain diperlakukan sebagai "tidak ditemukan".
"""
import re
from datetime import date
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..core.audit import build_audit_entry, log_action
from ..core.db import NO_ID, audit_fields, get_db, new_id, now, serialize, serialize_list, transaction
from ..core.deps import AuthContext, require_permission
from ..core.employee_status import (
    CATEGORIES,
    CATEGORY_ORDER,
    HISTORY,
    TABLE,
    TECHNICAL_LEGACY,
    category_label,
    history_doc,
    is_status_used,
    legacy_for,
    today_local,
    usage_counts,
)

router = APIRouter(tags=["Status Karyawan"])

CODE_RE = re.compile(r"^[A-Z0-9_]{2,32}$")


class StatusMasterCreate(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=2, max_length=100)
    system_category: str
    description: Optional[str] = Field(default=None, max_length=500)
    sort_order: Optional[int] = Field(default=None, ge=0, le=9999)
    is_active: bool = True


class StatusMasterUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=2, max_length=32)
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    system_category: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=500)
    sort_order: Optional[int] = Field(default=None, ge=0, le=9999)


class EmployeeStatusChange(BaseModel):
    new_status_id: str
    effective_date: Optional[str] = None
    reason: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=1000)


def _unprocessable(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, msg)


def _decorate(row: Dict[str, Any], usage: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    row = serialize(row)
    row["system_category_label"] = category_label(row.get("system_category"))
    if usage is not None:
        row["usage_current"] = usage.get("current", 0)
        row["usage_history"] = usage.get("history", 0)
        row["is_used"] = bool(row["usage_current"] or row["usage_history"])
    return row


def _norm_code(code: str) -> str:
    code = (code or "").strip().upper().replace(" ", "_").replace("-", "_")
    if not CODE_RE.match(code):
        raise _unprocessable("Kode status hanya boleh huruf besar, angka, dan garis bawah (2-32 karakter).")
    return code


def _check_category(category: Optional[str]) -> str:
    if category not in CATEGORIES:
        raise _unprocessable("Kategori sistem hanya boleh: AKTIF, STANDBY, atau TIDAK AKTIF.")
    return category


async def _get_master(ctx: AuthContext, status_id: str) -> Dict[str, Any]:
    row = await get_db()[TABLE].find_one({"company_id": ctx.company_id, "id": status_id}, NO_ID)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Status karyawan tidak ditemukan pada perusahaan aktif Anda.")
    return row


async def _ensure_unique(ctx: AuthContext, field: str, value: str, label: str,
                         exclude_id: Optional[str] = None) -> None:
    flt: Dict[str, Any] = {"company_id": ctx.company_id, field: value}
    if exclude_id:
        flt["id"] = {"$ne": exclude_id}
    if await get_db()[TABLE].count_documents(flt):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{label} '{value}' sudah digunakan.")


# ------------------------------------------------------------------ master
@router.get("/employee-statuses/categories")
async def list_categories(ctx: AuthContext = Depends(require_permission("employee", "view"))):
    """3 kategori sistem terkunci (read-only, tidak ada endpoint ubah)."""
    return {"items": [{"key": k, "label": CATEGORIES[k], "locked": True} for k in CATEGORY_ORDER]}


@router.get("/employee-statuses")
async def list_statuses(
    category: Optional[str] = None,
    active: Optional[bool] = None,
    q: Optional[str] = None,
    ctx: AuthContext = Depends(require_permission("employee", "view")),
):
    flt: Dict[str, Any] = {"company_id": ctx.company_id}
    if category:
        flt["system_category"] = _check_category(category)
    if active is not None:
        flt["is_active"] = active
    if q:
        pattern = re.escape(q.strip())
        flt["$or"] = [{"name": {"$regex": pattern, "$options": "i"}},
                      {"code": {"$regex": pattern, "$options": "i"}}]
    rows = await get_db()[TABLE].find(flt, NO_ID).sort([("sort_order", 1), ("name", 1)]).to_list(1000)
    usage = await usage_counts(ctx.company_id, [r["id"] for r in rows])
    items = [_decorate(r, usage.get(r["id"])) for r in rows]
    return {"items": items, "total": len(items)}


@router.post("/employee-statuses", status_code=status.HTTP_201_CREATED)
async def create_status(
    payload: StatusMasterCreate,
    ctx: AuthContext = Depends(require_permission("employee_status", "manage")),
):
    code = _norm_code(payload.code)
    category = _check_category(payload.system_category)
    name = payload.name.strip()
    await _ensure_unique(ctx, "code", code, "Kode status")
    await _ensure_unique(ctx, "name", name, "Nama status")
    sort_order = payload.sort_order
    if sort_order is None:
        last = await get_db()[TABLE].find({"company_id": ctx.company_id}, NO_ID).sort(
            "sort_order", -1).limit(1).to_list(1)
        sort_order = ((last[0].get("sort_order") or 0) + 1) if last else 1
    doc = {
        "id": new_id(), "company_id": ctx.company_id, "code": code, "name": name,
        "system_category": category, "description": (payload.description or "").strip() or None,
        "sort_order": sort_order, "is_active": payload.is_active, "is_default": False,
        "status": "active" if payload.is_active else "inactive",
        **audit_fields(ctx.user_id, creating=True),
    }
    await get_db()[TABLE].insert_one(dict(doc))
    await log_action(ctx, "create", "employee_status", doc["id"], name, after=doc)
    return _decorate(doc, {"current": 0, "history": 0})


@router.put("/employee-statuses/{status_id}")
async def update_status(
    status_id: str,
    payload: StatusMasterUpdate,
    ctx: AuthContext = Depends(require_permission("employee_status", "manage")),
):
    before = await _get_master(ctx, status_id)
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tidak ada perubahan yang dikirim.")
    patch: Dict[str, Any] = {}
    used = await is_status_used(ctx.company_id, status_id)
    if "code" in data and data["code"] is not None:
        code = _norm_code(data["code"])
        if code != before.get("code"):
            if before.get("is_default"):
                raise HTTPException(status.HTTP_409_CONFLICT, "Kode status default tidak dapat diubah.")
            if used:
                raise HTTPException(status.HTTP_409_CONFLICT,
                                    "Kode status yang sudah pernah digunakan tidak dapat diubah.")
            await _ensure_unique(ctx, "code", code, "Kode status", exclude_id=status_id)
            patch["code"] = code
    if "system_category" in data and data["system_category"] is not None:
        category = _check_category(data["system_category"])
        if category != before.get("system_category"):
            if before.get("is_default"):
                raise HTTPException(status.HTTP_409_CONFLICT, "Kategori status default tidak dapat diubah.")
            if used:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "Kategori sistem tidak dapat diubah karena status ini sudah pernah digunakan "
                    "(agar makna riwayat lama tidak berubah). Buat status baru bila perlu.",
                )
            patch["system_category"] = category
    if "name" in data and data["name"] is not None:
        name = data["name"].strip()
        if name != before.get("name"):
            await _ensure_unique(ctx, "name", name, "Nama status", exclude_id=status_id)
            patch["name"] = name
    if "description" in data:
        patch["description"] = (data["description"] or "").strip() or None
    if "sort_order" in data and data["sort_order"] is not None:
        patch["sort_order"] = data["sort_order"]
    if not patch:
        return _decorate(before)
    patch.update(audit_fields(ctx.user_id, creating=False))
    await get_db()[TABLE].update_one({"company_id": ctx.company_id, "id": status_id}, {"$set": patch})
    after = await _get_master(ctx, status_id)
    await log_action(ctx, "update", "employee_status", status_id, after.get("name"), before=before, after=after)
    return _decorate(after)


async def _set_active(ctx: AuthContext, status_id: str, active: bool) -> Dict[str, Any]:
    before = await _get_master(ctx, status_id)
    if not active and before.get("is_default"):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Status default tidak dapat dinonaktifkan karena dipakai sebagai status bawaan.")
    if bool(before.get("is_active")) == active:
        return _decorate(before)
    await get_db()[TABLE].update_one(
        {"company_id": ctx.company_id, "id": status_id},
        {"$set": {"is_active": active, "status": "active" if active else "inactive",
                  **audit_fields(ctx.user_id, creating=False)}},
    )
    after = await _get_master(ctx, status_id)
    await log_action(ctx, "activate" if active else "deactivate", "employee_status", status_id,
                     after.get("name"), before=before, after=after)
    return _decorate(after)


@router.patch("/employee-statuses/{status_id}/activate")
async def activate_status(status_id: str,
                          ctx: AuthContext = Depends(require_permission("employee_status", "manage"))):
    return await _set_active(ctx, status_id, True)


@router.patch("/employee-statuses/{status_id}/deactivate")
async def deactivate_status(status_id: str,
                            ctx: AuthContext = Depends(require_permission("employee_status", "manage"))):
    return await _set_active(ctx, status_id, False)


@router.delete("/employee-statuses/{status_id}")
async def delete_status(status_id: str,
                        ctx: AuthContext = Depends(require_permission("employee_status", "manage"))):
    before = await _get_master(ctx, status_id)
    if before.get("is_default"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Status default tidak dapat dihapus.")
    if await is_status_used(ctx.company_id, status_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Status ini sudah pernah digunakan karyawan sehingga tidak dapat dihapus. Nonaktifkan saja.",
        )
    await get_db()[TABLE].delete_one({"company_id": ctx.company_id, "id": status_id})
    await log_action(ctx, "delete", "employee_status", status_id, before.get("name"), before=before)
    return {"message": f"Status '{before.get('name')}' berhasil dihapus."}


# ------------------------------------------------------------- per karyawan
async def _get_employee(ctx: AuthContext, employee_id: str) -> Dict[str, Any]:
    emp = await get_db().employees.find_one(
        {"company_id": ctx.company_id, "id": employee_id, "status": {"$ne": "deleted"}}, NO_ID
    )
    if not emp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Karyawan tidak ditemukan pada perusahaan aktif Anda.")
    return emp


@router.get("/employees/{employee_id}/status-history")
async def status_history(employee_id: str,
                         ctx: AuthContext = Depends(require_permission("employee", "view"))):
    await _get_employee(ctx, employee_id)
    db = get_db()
    rows = serialize_list(await db[HISTORY].find(
        {"company_id": ctx.company_id, "employee_id": employee_id}, NO_ID
    ).sort([("created_at", -1)]).to_list(1000))
    ids = {r.get(k) for r in rows for k in ("previous_status_id", "new_status_id") if r.get(k)}
    masters = {m["id"]: m for m in await db[TABLE].find(
        {"company_id": ctx.company_id, "id": {"$in": list(ids)}}, NO_ID).to_list(1000)}
    for r in rows:
        for prefix, key in (("previous", "previous_status_id"), ("new", "new_status_id")):
            m = masters.get(r.get(key)) or {}
            r[f"{prefix}_status_name"] = m.get("name")
            r[f"{prefix}_status_code"] = m.get("code")
            r[f"{prefix}_status_is_active"] = m.get("is_active")
            r[f"{prefix}_category_label"] = category_label(r.get(f"{prefix}_category"))
    return {"items": rows, "total": len(rows)}


@router.post("/employees/{employee_id}/status-change")
async def change_employee_status(
    employee_id: str,
    payload: EmployeeStatusChange,
    ctx: AuthContext = Depends(require_permission("employee_status", "change")),
):
    reason = (payload.reason or "").strip()
    notes = (payload.notes or "").strip() or None
    eff = (payload.effective_date or "").strip()
    if not eff:
        raise _unprocessable("Tanggal efektif wajib diisi.")
    try:
        eff_date = date.fromisoformat(eff)
    except ValueError as exc:
        raise _unprocessable("Format tanggal efektif harus YYYY-MM-DD.") from exc
    if eff_date.isoformat() > today_local():
        raise _unprocessable("Tanggal efektif tidak boleh melebihi hari ini.")
    if len(reason) < 3:
        raise _unprocessable("Alasan perubahan status wajib diisi (minimal 3 karakter).")
    if len(reason) > 255:
        raise _unprocessable("Alasan maksimal 255 karakter.")

    employee = await _get_employee(ctx, employee_id)
    if employee.get("status") in TECHNICAL_LEGACY:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Karyawan sedang diarsipkan. Pulihkan dari arsip terlebih dahulu sebelum mengubah status.")
    db = get_db()
    new_status = await db[TABLE].find_one({"company_id": ctx.company_id, "id": payload.new_status_id}, NO_ID)
    if not new_status:
        raise _unprocessable("Status baru tidak ditemukan pada perusahaan aktif Anda.")
    if not new_status.get("is_active"):
        raise _unprocessable("Status baru sedang nonaktif dan tidak dapat dipilih.")
    if new_status["id"] == employee.get("current_employee_status_id"):
        raise _unprocessable("Status baru sama dengan status saat ini.")
    previous = None
    if employee.get("current_employee_status_id"):
        previous = await db[TABLE].find_one(
            {"company_id": ctx.company_id, "id": employee["current_employee_status_id"]}, NO_ID)

    legacy_before = employee.get("status")
    legacy_after = legacy_for(new_status["system_category"])
    actor_name = ctx.user.get("full_name") if ctx.user else None
    hist = history_doc(
        ctx.company_id, employee_id, new_status, previous, effective_date=eff_date.isoformat(),
        reason=reason, notes=notes, source="MANUAL", actor_id=ctx.user_id, actor_name=actor_name,
        legacy_before=legacy_before, legacy_after=legacy_after,
    )
    audit_before = {"status_karyawan": previous.get("name") if previous else None,
                    "kategori": category_label(previous.get("system_category")) if previous else None,
                    "status_legacy": legacy_before}
    audit_after = {"status_karyawan": new_status.get("name"),
                   "kategori": category_label(new_status.get("system_category")),
                   "status_legacy": legacy_after, "tanggal_efektif": eff_date.isoformat()}
    audit = build_audit_entry(
        ctx, "status_change", "employee", employee_id, employee.get("full_name"),
        before=audit_before, after=audit_after,
        notes=f"{audit_before['status_karyawan'] or '-'} -> {new_status.get('name')} "
              f"(efektif {eff_date.isoformat()}). Alasan: {reason}",
    )
    ts = now()
    # SATU transaksi: employee (current + legacy) -> riwayat -> audit. Gagal = rollback semua.
    async with transaction() as tx:
        locked = await tx.select_one_for_update(
            "employees", {"company_id": ctx.company_id, "id": employee_id})
        if not locked or locked.get("current_employee_status_id") != employee.get("current_employee_status_id") \
                or locked.get("status") != legacy_before:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "Status karyawan baru saja diubah oleh proses lain. Muat ulang lalu coba lagi.")
        await tx.update("employees", {"company_id": ctx.company_id, "id": employee_id},
                        {"current_employee_status_id": new_status["id"], "status": legacy_after,
                         "updated_at": ts, "updated_by": ctx.user_id})
        await tx.insert(HISTORY, hist)
        await tx.insert("audit_logs", audit)

    updated = await _get_employee(ctx, employee_id)
    return {
        "message": f"Status {employee.get('full_name')} berhasil diubah menjadi {new_status.get('name')}.",
        "employee_id": employee_id,
        "current_employee_status_id": updated.get("current_employee_status_id"),
        "current_employee_status_name": new_status.get("name"),
        "current_employee_status_category": new_status.get("system_category"),
        "legacy_status": updated.get("status"),
        "history": serialize(hist),
    }
