"""Platform Branding (KelolaKita - HRIS & Payroll).

- Konfigurasi disimpan di tabel global `platform_settings` (key = "branding").
- Baca publik (tanpa login) HANYA untuk field tampilan: dibutuhkan halaman login.
- Ubah konfigurasi/logo/favicon HANYA Platform Admin (dicek di backend).
- Logo platform TERPISAH dari logo tenant (path storage & kolom berbeda).
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field

from ..core.audit import log_action
from ..core.branding_assets import MAX_LOGO_MB, platform_asset_path, read_image_upload
from ..core.db import NO_ID, get_db, new_id, now
from ..core.deps import AuthContext, require_platform_admin
from ..core.storage import StorageError, delete_object, get_object, put_object

public_router = APIRouter(prefix="/public", tags=["Publik - Branding"])
router = APIRouter(prefix="/platform/branding", tags=["Platform - Branding"])

SETTINGS_KEY = "branding"
ASSETS = ("logo", "favicon")

# Nilai awal bila Platform Admin belum mengatur apa pun (bukan hardcode di UI:
# UI selalu membaca dari endpoint ini dan dapat diubah dari halaman Branding Platform).
DEFAULT_BRANDING: Dict[str, Any] = {
    "app_name": "KelolaKita",
    "subtitle": "HRIS & Payroll",
    "tagline": "Satu platform untuk data karyawan, absensi, dan payroll perusahaan Anda.",
    "login_headline": "Kelola SDM dan payroll dengan rapi, dari satu tempat.",
    "login_supporting_text": (
        "Data karyawan terpusat, absensi dan cuti tercatat, payroll dan PPh 21 dihitung "
        "sesuai aturan yang berlaku, dan setiap perusahaan terpisah dengan aman."
    ),
    "support_contact": None,
}
TEXT_FIELDS = tuple(DEFAULT_BRANDING.keys())


class BrandingUpdate(BaseModel):
    app_name: Optional[str] = Field(default=None, min_length=2, max_length=60)
    subtitle: Optional[str] = Field(default=None, max_length=80)
    tagline: Optional[str] = Field(default=None, max_length=200)
    login_headline: Optional[str] = Field(default=None, max_length=160)
    login_supporting_text: Optional[str] = Field(default=None, max_length=500)
    support_contact: Optional[str] = Field(default=None, max_length=160)


async def _load() -> Dict[str, Any]:
    db = get_db()
    row = await db.platform_settings.find_one({"key": SETTINGS_KEY}, NO_ID)
    return (row or {}).get("value") or {}


async def _save(value: Dict[str, Any], user_id: Optional[str]) -> None:
    db = get_db()
    row = await db.platform_settings.find_one({"key": SETTINGS_KEY}, NO_ID)
    if row:
        await db.platform_settings.update_one(
            {"key": SETTINGS_KEY}, {"$set": {"value": value, "updated_at": now(), "updated_by": user_id}}
        )
    else:
        await db.platform_settings.insert_one({
            "id": new_id(), "company_id": None, "key": SETTINGS_KEY, "value": value, "status": "active",
            "created_at": now(), "updated_at": now(), "created_by": user_id, "updated_by": user_id,
        })


def _public_view(stored: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: (stored.get(k) if stored.get(k) not in (None, "") else DEFAULT_BRANDING[k]) for k in TEXT_FIELDS}
    for asset in ASSETS:
        version = stored.get(f"{asset}_version")
        has = bool(stored.get(f"{asset}_path"))
        out[f"has_{asset}"] = has
        out[f"{asset}_url"] = f"/api/public/branding/{asset}?v={version}" if has else None
    out["max_logo_mb"] = MAX_LOGO_MB
    out["updated_at"] = stored.get("updated_at")
    return out


# ------------------------------------------------------------------ publik
@public_router.get("/branding")
async def public_branding():
    return _public_view(await _load())


@public_router.get("/branding/{asset}")
async def public_branding_asset(asset: str):
    if asset not in ASSETS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aset tidak ditemukan.")
    stored = await _load()
    path = stored.get(f"{asset}_path")
    if not path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Logo platform belum diunggah.")
    try:
        data, content_type = get_object(path)
    except StorageError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "public, max-age=300"})


# ------------------------------------------------------------ platform admin
@router.get("")
async def get_branding(ctx: AuthContext = Depends(require_platform_admin())):
    return {**_public_view(await _load()), "defaults": DEFAULT_BRANDING}


@router.put("")
async def update_branding(payload: BrandingUpdate, ctx: AuthContext = Depends(require_platform_admin())):
    stored = await _load()
    before = {k: stored.get(k) for k in TEXT_FIELDS}
    sent = payload.model_dump(exclude_unset=True)
    if not sent:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tidak ada perubahan yang dikirim.")
    for k, v in sent.items():
        stored[k] = v.strip() if isinstance(v, str) and v.strip() else None
    stored["updated_at"] = now().isoformat()
    await _save(stored, ctx.user_id)
    await log_action(ctx, "update", "platform_branding", SETTINGS_KEY, "Branding Platform",
                     before=before, after={k: stored.get(k) for k in TEXT_FIELDS},
                     module="platform", platform_scope=True)
    return _public_view(stored)


@router.post("/{asset}")
async def upload_branding_asset(
    asset: str, file: UploadFile = File(...), ctx: AuthContext = Depends(require_platform_admin())
):
    if asset not in ASSETS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aset branding tidak dikenal.")
    data, ext, mime = await read_image_upload(file)
    stored = await _load()
    old_path = stored.get(f"{asset}_path")
    path = platform_asset_path(asset, ext)
    try:
        put_object(path, data, mime)
    except StorageError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    version = new_id()[:8]
    stored.update({f"{asset}_path": path, f"{asset}_version": version, f"{asset}_content_type": mime,
                   f"{asset}_size": len(data), "updated_at": now().isoformat()})
    await _save(stored, ctx.user_id)
    if old_path and old_path != path:
        delete_object(old_path)
    await log_action(ctx, "replace" if old_path else "upload", "platform_branding", SETTINGS_KEY,
                     f"{'Logo' if asset == 'logo' else 'Favicon'} Platform",
                     before={"path": old_path}, after={"path": path, "size": len(data), "content_type": mime},
                     module="platform", platform_scope=True)
    return _public_view(stored)


@router.delete("/{asset}")
async def delete_branding_asset(asset: str, ctx: AuthContext = Depends(require_platform_admin())):
    if asset not in ASSETS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aset branding tidak dikenal.")
    stored = await _load()
    old_path = stored.get(f"{asset}_path")
    if not old_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Belum ada berkas yang diunggah.")
    for k in ("path", "version", "content_type", "size"):
        stored.pop(f"{asset}_{k}", None)
    stored["updated_at"] = now().isoformat()
    await _save(stored, ctx.user_id)
    delete_object(old_path)
    await log_action(ctx, "delete", "platform_branding", SETTINGS_KEY,
                     f"{'Logo' if asset == 'logo' else 'Favicon'} Platform",
                     before={"path": old_path}, module="platform", platform_scope=True)
    return _public_view(stored)
