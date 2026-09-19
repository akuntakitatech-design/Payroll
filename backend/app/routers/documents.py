import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status

from ..core.audit import log_action
from ..core.config import settings
from ..core.db import NO_ID, get_db, new_id, serialize, serialize_list
from ..core.deps import AuthContext, get_auth, require_permission
from ..core.repo import TenantRepository
from ..core.storage import StorageError, get_object, guess_mime, object_path, put_object
from ..schemas import DocumentUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["Dokumen"])

OWNER_TYPES = [
    {"key": "company", "label": "Perusahaan"},
    {"key": "employee", "label": "Karyawan"},
    {"key": "applicant", "label": "Pelamar"},
    {"key": "contract", "label": "Kontrak Kerja"},
    {"key": "project", "label": "Proyek"},
    {"key": "certification", "label": "Sertifikasi"},
    {"key": "invoice", "label": "Invoice"},
    {"key": "travel", "label": "Tiket / Perjalanan"},
    {"key": "receipt", "label": "Kwitansi / Bukti Bayar"},
    {"key": "medical", "label": "Dokumen Medis"},
    {"key": "other", "label": "Lainnya"},
]


@router.get("/catalog")
async def catalog(ctx: AuthContext = Depends(get_auth)):
    db = get_db()
    types = serialize_list(
        await db.document_types.find({"company_id": ctx.company_id, "status": "active"}, NO_ID)
        .sort("name", 1)
        .to_list(500)
    )
    return {"owner_types": OWNER_TYPES, "document_types": types, "max_size_mb": settings.MAX_UPLOAD_MB}


@router.get("")
async def list_documents(
    q: Optional[str] = None,
    document_type_id: Optional[str] = None,
    owner_type: Optional[str] = None,
    owner_id: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = 1,
    limit: int = 20,
    ctx: AuthContext = Depends(require_permission("document", "view")),
):
    filters: Dict[str, Any] = {}
    for key, value in (
        ("document_type_id", document_type_id),
        ("owner_type", owner_type),
        ("owner_id", owner_id),
        ("status", status_filter),
    ):
        if value:
            filters[key] = value
    repo = TenantRepository("documents", ctx.company_id)
    result = await repo.list(
        q=q,
        search_fields=["name", "document_number", "owner_label", "file_name"],
        filters=filters,
        page=page,
        limit=limit,
    )
    db = get_db()
    type_ids = {i.get("document_type_id") for i in result["items"] if i.get("document_type_id")}
    types = {
        t["id"]: t
        for t in await db.document_types.find(
            {"company_id": ctx.company_id, "id": {"$in": list(type_ids)}}, NO_ID
        ).to_list(500)
    }
    for item in result["items"]:
        t = types.get(item.get("document_type_id")) or {}
        item["document_type_name"] = t.get("name")
        item["document_type_category"] = t.get("category")
    return result


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    document_type_id: str = Form(...),
    name: str = Form(...),
    owner_type: str = Form("company"),
    owner_id: Optional[str] = Form(None),
    owner_label: Optional[str] = Form(None),
    document_number: Optional[str] = Form(None),
    issued_date: Optional[str] = Form(None),
    expiry_date: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    ctx: AuthContext = Depends(require_permission("document", "create")),
):
    db = get_db()
    doc_type = serialize(
        await db.document_types.find_one({"company_id": ctx.company_id, "id": document_type_id}, NO_ID)
    )
    if not doc_type:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Tipe dokumen tidak ditemukan. Buat tipe dokumen terlebih dahulu di menu Tipe Dokumen.",
        )

    ext = Path(file.filename or "").suffix.lower().lstrip(".")
    allowed = doc_type.get("allowed_extensions")
    if allowed:
        allowed_list = [a.strip().lower().lstrip(".") for a in str(allowed).split(",") if a.strip()]
        if allowed_list and ext not in allowed_list:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Format berkas '.{ext}' tidak diizinkan untuk tipe {doc_type.get('name')}. "
                f"Format yang diizinkan: {', '.join(allowed_list)}.",
            )

    max_mb = int(doc_type.get("max_size_mb") or settings.MAX_UPLOAD_MB)
    payload = await file.read()
    if len(payload) == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Berkas yang diunggah kosong.")
    if len(payload) > max_mb * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Ukuran berkas melebihi batas {max_mb} MB untuk tipe {doc_type.get('name')}.",
        )

    file_id = new_id()
    path = object_path(ctx.company_id, file_id, ext)
    content_type = guess_mime(ext, file.content_type)
    try:
        result = put_object(path, payload, content_type)
    except StorageError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Upload ke object storage gagal")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Penyimpanan berkas sedang tidak tersedia. Coba unggah kembali beberapa saat lagi.",
        ) from exc

    repo = TenantRepository("documents", ctx.company_id)
    created = await repo.create(
        {
            "document_type_id": document_type_id,
            "name": name.strip(),
            "owner_type": owner_type,
            "owner_id": owner_id,
            "owner_label": owner_label,
            "document_number": document_number,
            "issued_date": issued_date,
            "expiry_date": expiry_date,
            "notes": notes,
            "file_name": file.filename,
            "storage_path": result.get("path", path),
            "file_size": result.get("size", len(payload)),
            "file_extension": ext,
            "mime_type": content_type,
            "is_deleted": False,
            "version": 1,
        },
        ctx.user_id,
    )
    created["document_type_name"] = doc_type.get("name")
    await log_action(ctx, "upload", "document", created["id"], created["name"], after=created)
    return created


@router.get("/{document_id}")
async def get_document(document_id: str, ctx: AuthContext = Depends(require_permission("document", "view"))):
    repo = TenantRepository("documents", ctx.company_id)
    return await repo.get(document_id)


PREVIEWABLE = {
    "pdf", "png", "jpg", "jpeg", "webp", "gif", "bmp", "svg", "txt", "csv", "json",
}


def _previewable(doc: Dict[str, Any]) -> bool:
    ext = (doc.get("file_extension") or "").lower()
    mime = (doc.get("mime_type") or "").lower()
    return ext in PREVIEWABLE or mime.startswith("image/") or mime in (
        "application/pdf",
        "text/plain",
        "text/csv",
        "application/json",
    )


async def _fetch_file(document_id: str, ctx: AuthContext):
    repo = TenantRepository("documents", ctx.company_id)
    doc = await repo.get(document_id)
    if not doc.get("storage_path") or doc.get("is_deleted"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dokumen ini belum memiliki berkas terlampir.")
    try:
        data, content_type = get_object(doc["storage_path"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("Gagal mengambil berkas dari object storage")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Berkas tidak dapat diambil dari penyimpanan saat ini. Coba lagi beberapa saat.",
        ) from exc
    return doc, data, content_type


@router.get("/{document_id}/preview-info")
async def preview_info(
    document_id: str, ctx: AuthContext = Depends(require_permission("document", "view"))
):
    """Metadata ringan untuk menampilkan pratinjau di layar tanpa mengunduh berkas."""
    repo = TenantRepository("documents", ctx.company_id)
    doc = await repo.get(document_id)
    ext = (doc.get("file_extension") or "").lower()
    mime = (doc.get("mime_type") or "").lower()
    if mime.startswith("image/") or ext in {"png", "jpg", "jpeg", "webp", "gif", "bmp", "svg"}:
        kind = "image"
    elif mime == "application/pdf" or ext == "pdf":
        kind = "pdf"
    elif mime.startswith("text/") or ext in {"txt", "csv", "json"}:
        kind = "text"
    else:
        kind = "unsupported"
    has_file = bool(doc.get("storage_path")) and not doc.get("is_deleted")
    return {
        "id": doc["id"],
        "name": doc.get("name"),
        "file_name": doc.get("file_name"),
        "file_size": doc.get("file_size"),
        "mime_type": doc.get("mime_type"),
        "file_extension": ext,
        "expiry_date": doc.get("expiry_date"),
        "issued_date": doc.get("issued_date"),
        "document_number": doc.get("document_number"),
        "owner_label": doc.get("owner_label"),
        "owner_type": doc.get("owner_type"),
        "notes": doc.get("notes"),
        "status": doc.get("status"),
        "preview_kind": kind,
        "previewable": _previewable(doc) and has_file,
        "has_file": has_file,
        "unavailable_reason": None if has_file else "Berkas tidak lagi tersedia di penyimpanan.",
    }


@router.get("/{document_id}/preview")
async def preview_document(
    document_id: str, ctx: AuthContext = Depends(require_permission("document", "view"))
):
    """Tampilkan berkas langsung di layar (inline), tanpa memaksa pengguna mengunduh."""
    doc, data, content_type = await _fetch_file(document_id, ctx)
    filename = doc.get("file_name") or f"{doc['name']}.{doc.get('file_extension') or 'bin'}"
    return Response(
        content=data,
        media_type=doc.get("mime_type") or content_type,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "private, max-age=60",
        },
    )


@router.get("/{document_id}/download")
async def download_document(
    document_id: str, ctx: AuthContext = Depends(require_permission("document", "view"))
):
    doc, data, content_type = await _fetch_file(document_id, ctx)
    filename = doc.get("file_name") or f"{doc['name']}.{doc.get('file_extension') or 'bin'}"
    return Response(
        content=data,
        media_type=doc.get("mime_type") or content_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.put("/{document_id}")
async def update_document(
    document_id: str,
    payload: DocumentUpdate,
    ctx: AuthContext = Depends(require_permission("document", "edit")),
):
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tidak ada perubahan yang dikirim.")
    repo = TenantRepository("documents", ctx.company_id)
    before, after = await repo.update(document_id, data, ctx.user_id)
    await log_action(ctx, "update", "document", document_id, after.get("name"), before=before, after=after)
    return after


@router.delete("/{document_id}")
async def delete_document(
    document_id: str, ctx: AuthContext = Depends(require_permission("document", "delete"))
):
    """Soft delete - object storage has no delete API, and history must stay auditable."""
    repo = TenantRepository("documents", ctx.company_id)
    doc = await repo.get(document_id)
    before, after = await repo.update(
        document_id, {"is_deleted": True, "status": "archived"}, ctx.user_id
    )
    await log_action(ctx, "delete", "document", document_id, doc.get("name"), before=before, after=after)
    return {"message": f"Dokumen '{doc.get('name')}' berhasil dihapus dari daftar aktif."}
