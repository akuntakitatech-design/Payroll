"""Validasi & penyimpanan aset branding (logo platform, favicon platform, logo tenant).

Semua berkas disimpan lewat storage engine existing (app/core/storage.py) -
di staging ini endpoint S3 lokal, BUKAN R2 produksi. Path dipisah tegas:

  Platform : {R2_PREFIX}/platform/branding/{asset}/{uuid}.{ext}
  Tenant   : {R2_PREFIX}/companies/{company_id}/branding/logo/{uuid}.{ext}

Validasi dilakukan di backend (frontend juga memvalidasi, tetapi backend adalah
sumber kebenaran): ekstensi, MIME, signature byte (magic number), dan ukuran.
"""
from typing import Tuple

from fastapi import HTTPException, UploadFile, status

from .db import new_id
from .storage import APP_NAME

MAX_LOGO_MB = 10
MAX_LOGO_BYTES = MAX_LOGO_MB * 1024 * 1024

ALLOWED_IMAGE_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}
ALLOWED_MIME = {"image/png", "image/jpeg", "image/jpg", "image/pjpeg", "image/webp"}
ALLOWED_LABEL = "PNG, JPG, JPEG, atau WEBP"


def _detect(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return ""


async def read_image_upload(file: UploadFile) -> Tuple[bytes, str, str]:
    """Baca & validasi gambar logo. Return (data, ext, mime). Raise 413/415/422."""
    name = (file.filename or "").strip()
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Format berkas tidak didukung. Gunakan {ALLOWED_LABEL}.",
        )
    mime = (file.content_type or "").lower()
    if mime and mime not in ALLOWED_MIME and mime != "application/octet-stream":
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Tipe berkas '{mime}' tidak didukung. Gunakan {ALLOWED_LABEL}.",
        )
    # Baca maksimal batas + 1 byte agar berkas besar tidak dimuat seluruhnya ke memori.
    data = await file.read(MAX_LOGO_BYTES + 1)
    if len(data) > MAX_LOGO_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Ukuran berkas melebihi batas {MAX_LOGO_MB} MB.",
        )
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Berkas kosong.")
    detected = _detect(data)
    expected = "jpeg" if ext in ("jpg", "jpeg") else ext
    if detected != expected:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Isi berkas bukan gambar {ext.upper()} yang valid. Gunakan {ALLOWED_LABEL}.",
        )
    return data, ext, ALLOWED_IMAGE_TYPES[ext]


def platform_asset_path(asset: str, ext: str) -> str:
    return f"{APP_NAME}/platform/branding/{asset}/{new_id()}.{ext}"


def tenant_logo_path(company_id: str, ext: str) -> str:
    return f"{APP_NAME}/companies/{company_id}/branding/logo/{new_id()}.{ext}"


def is_tenant_logo_path(company_id: str, path: str) -> bool:
    """Pengaman tambahan: logo tenant hanya boleh berada di prefix tenant itu sendiri."""
    return bool(path) and path.startswith(f"{APP_NAME}/companies/{company_id}/branding/logo/")
