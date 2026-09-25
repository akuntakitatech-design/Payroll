"""Upgrade 01C - Employee Profile 360: keluarga (repeatable), foto profil, dan timeline riwayat.

Semua endpoint tenant-aware (company_id dari token, bukan dari klien) dan memakai RBAC existing:
employee:view -> lihat; employee:edit -> ubah. Tidak ada permission baru.
Status Karyawan (01B) TIDAK dapat diubah di sini (hanya lewat Ubah Status).
"""
import re
from datetime import date
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field, field_validator

from ..core.audit import log_action
from ..core.branding_assets import read_image_upload
from ..core.db import NO_ID, new_id
from ..core.deps import AuthContext, require_permission
from ..core.repo import TenantRepository
from ..core.sensitive import can_view_sensitive, mask_value
from ..core.storage import APP_NAME, StorageError, delete_object, get_object, put_object

router = APIRouter(prefix="/employees", tags=["employee-profile"])

RELATIONSHIPS = {
    "SUAMI": "Suami", "ISTRI": "Istri", "ANAK": "Anak", "AYAH": "Ayah",
    "IBU": "Ibu", "SAUDARA": "Saudara", "LAINNYA": "Lainnya",
}
GENDERS = {"male", "female"}
FAMILY_FIELDS = ("relationship", "full_name", "nik", "birth_place", "birth_date", "gender",
                 "occupation", "is_emergency_contact", "phone", "notes")


class FamilyInput(BaseModel):
    relationship: str
    full_name: str = Field(min_length=2, max_length=255)
    nik: Optional[str] = None
    birth_place: Optional[str] = Field(None, max_length=255)
    birth_date: Optional[str] = None
    gender: Optional[str] = None
    occupation: Optional[str] = Field(None, max_length=255)
    is_emergency_contact: bool = False
    phone: Optional[str] = Field(None, max_length=32)
    notes: Optional[str] = Field(None, max_length=1000)

    @field_validator("relationship")
    @classmethod
    def _rel(cls, v: str) -> str:
        v = (v or "").strip().upper()
        if v not in RELATIONSHIPS:
            raise ValueError("Hubungan keluarga tidak dikenal.")
        return v

    @field_validator("full_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) < 2:
            raise ValueError("Nama wajib diisi (minimal 2 karakter).")
        return v

    @field_validator("nik")
    @classmethod
    def _nik(cls, v: Optional[str]) -> Optional[str]:
        v = (v or "").strip() or None
        if v and not re.fullmatch(r"\d{16}", v):
            raise ValueError("NIK harus 16 digit angka.")
        return v

    @field_validator("birth_date")
    @classmethod
    def _dob(cls, v: Optional[str]) -> Optional[str]:
        v = (v or "").strip() or None
        if v:
            try:
                d = date.fromisoformat(v)
            except ValueError as exc:
                raise ValueError("Format tanggal lahir harus YYYY-MM-DD.") from exc
            if d > date.today():
                raise ValueError("Tanggal lahir tidak boleh di masa depan.")
        return v

    @field_validator("gender")
    @classmethod
    def _gender(cls, v: Optional[str]) -> Optional[str]:
        v = (v or "").strip() or None
        if v and v not in GENDERS:
            raise ValueError("Jenis kelamin tidak dikenal.")
        return v


async def _employee(ctx: AuthContext, employee_id: str) -> Dict[str, Any]:
    emp = await TenantRepository("employees", ctx.company_id).get(employee_id)
    if emp.get("status") == "deleted":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Data tidak ditemukan pada perusahaan aktif Anda.")
    return emp


def _family_out(row: Dict[str, Any], full: bool) -> Dict[str, Any]:
    out = {k: row.get(k) for k in ("id", "employee_id", *FAMILY_FIELDS, "created_at", "updated_at")}
    out["is_emergency_contact"] = bool(out.get("is_emergency_contact"))
    out["relationship_label"] = RELATIONSHIPS.get(row.get("relationship"), row.get("relationship"))
    if not full and out.get("nik"):
        out["nik"] = mask_value(out["nik"])
    return out


# ------------------------------------------------------------------ keluarga
@router.get("/{employee_id}/family")
async def list_family(employee_id: str, ctx: AuthContext = Depends(require_permission("employee", "view"))):
    await _employee(ctx, employee_id)
    rows = await ctx.tdb.employee_family_members.find(
        {"company_id": ctx.company_id, "employee_id": employee_id, "status": {"$ne": "deleted"}}, NO_ID
    ).sort("created_at", 1).to_list(200)
    full = can_view_sensitive(ctx)
    return {"items": [_family_out(r, full) for r in rows], "relationships": [
        {"value": k, "label": v} for k, v in RELATIONSHIPS.items()], "sensitive_masked": not full}


@router.post("/{employee_id}/family", status_code=status.HTTP_201_CREATED)
async def add_family(employee_id: str, payload: FamilyInput,
                     ctx: AuthContext = Depends(require_permission("employee", "edit"))):
    emp = await _employee(ctx, employee_id)
    data = payload.model_dump()
    data["employee_id"] = employee_id
    created = await TenantRepository("employee_family_members", ctx.company_id).create(data, ctx.user_id)
    await log_action(ctx, "family_create", "employee", employee_id, emp.get("full_name"),
                     after=_family_out(created, True), notes="Data keluarga ditambah")
    return _family_out(created, True)


async def _family_row(ctx: AuthContext, employee_id: str, family_id: str) -> Dict[str, Any]:
    row = await TenantRepository("employee_family_members", ctx.company_id).get(family_id)
    if row.get("employee_id") != employee_id or row.get("status") == "deleted":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Data tidak ditemukan pada perusahaan aktif Anda.")
    return row


@router.put("/{employee_id}/family/{family_id}")
async def update_family(employee_id: str, family_id: str, payload: FamilyInput,
                        ctx: AuthContext = Depends(require_permission("employee", "edit"))):
    emp = await _employee(ctx, employee_id)
    await _family_row(ctx, employee_id, family_id)
    before, after = await TenantRepository("employee_family_members", ctx.company_id).update(
        family_id, payload.model_dump(), ctx.user_id)
    await log_action(ctx, "family_update", "employee", employee_id, emp.get("full_name"),
                     before=_family_out(before, True), after=_family_out(after, True), notes="Data keluarga diubah")
    return _family_out(after, True)


@router.delete("/{employee_id}/family/{family_id}")
async def delete_family(employee_id: str, family_id: str,
                        ctx: AuthContext = Depends(require_permission("employee", "edit"))):
    emp = await _employee(ctx, employee_id)
    await _family_row(ctx, employee_id, family_id)
    before = await TenantRepository("employee_family_members", ctx.company_id).hard_delete(family_id)
    await log_action(ctx, "family_delete", "employee", employee_id, emp.get("full_name"),
                     before=_family_out(before, True), notes="Data keluarga dihapus")
    return {"message": "Data keluarga dihapus."}


# ------------------------------------------------------------------ foto profil
def _photo_prefix(company_id: str, employee_id: str) -> str:
    return f"{APP_NAME}/companies/{company_id}/employees/{employee_id}/photo/"


@router.get("/{employee_id}/photo")
async def get_photo(employee_id: str, ctx: AuthContext = Depends(require_permission("employee", "view"))):
    emp = await _employee(ctx, employee_id)
    path = emp.get("photo_path")
    if not path or not path.startswith(_photo_prefix(ctx.company_id, employee_id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Karyawan belum memiliki foto profil.")
    try:
        data, content_type = get_object(path)
    except StorageError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "private, max-age=300"})


@router.post("/{employee_id}/photo")
async def upload_photo(employee_id: str, file: UploadFile = File(...),
                       ctx: AuthContext = Depends(require_permission("employee", "edit"))):
    emp = await _employee(ctx, employee_id)
    data, ext, mime = await read_image_upload(file)  # JPG/PNG/WEBP, maks 10 MB, cek signature
    path = f"{_photo_prefix(ctx.company_id, employee_id)}{new_id()}.{ext}"
    try:
        put_object(path, data, mime)
    except StorageError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    old = emp.get("photo_path")
    version = new_id()[:8]
    await TenantRepository("employees", ctx.company_id).update(
        employee_id, {"photo_path": path, "photo_version": version}, ctx.user_id)
    if old and old != path and old.startswith(_photo_prefix(ctx.company_id, employee_id)):
        delete_object(old)
    await log_action(ctx, "photo_replace" if old else "photo_upload", "employee", employee_id,
                     emp.get("full_name"), before={"photo": bool(old)},
                     after={"photo": True, "size": len(data), "content_type": mime}, notes="Foto profil diperbarui")
    return {"message": "Foto profil berhasil disimpan.",
            "photo_url": f"/api/employees/{employee_id}/photo?v={version}"}


@router.delete("/{employee_id}/photo")
async def delete_photo(employee_id: str, ctx: AuthContext = Depends(require_permission("employee", "edit"))):
    emp = await _employee(ctx, employee_id)
    old = emp.get("photo_path")
    if not old:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Karyawan belum memiliki foto profil.")
    await TenantRepository("employees", ctx.company_id).update(
        employee_id, {"photo_path": None, "photo_version": None}, ctx.user_id)
    if old.startswith(_photo_prefix(ctx.company_id, employee_id)):
        delete_object(old)
    await log_action(ctx, "photo_delete", "employee", employee_id, emp.get("full_name"),
                     before={"photo": True}, after={"photo": False}, notes="Foto profil dihapus")
    return {"message": "Foto profil dihapus."}


# ------------------------------------------------------------------ timeline (dari audit existing)
TIMELINE_RESOURCES = ("employee", "contract", "certification", "document")


@router.get("/{employee_id}/timeline")
async def timeline(employee_id: str, ctx: AuthContext = Depends(require_permission("employee", "view"))):
    """Peristiwa nyata dari audit log existing (tanpa nilai before/after, tanpa data karangan)."""
    await _employee(ctx, employee_id)
    db, cid = ctx.tdb, ctx.company_id
    ids = {employee_id}
    for coll, q in (("employee_contracts", {"employee_id": employee_id}),
                    ("employee_certifications", {"employee_id": employee_id}),
                    ("documents", {"owner_type": "employee", "owner_id": employee_id})):
        ids |= {r["id"] for r in await db[coll].find({"company_id": cid, **q}, {"_id": 0, "id": 1}).to_list(2000)}
    rows = await db.audit_logs.find(
        {"company_id": cid, "record_id": {"$in": list(ids)}, "resource": {"$in": list(TIMELINE_RESOURCES)}},
        {"_id": 0, "id": 1, "action": 1, "resource": 1, "record_label": 1, "user_name": 1,
         "created_at": 1, "notes": 1, "changed_fields": 1},
    ).sort("created_at", -1).to_list(200)
    return {"items": rows}
