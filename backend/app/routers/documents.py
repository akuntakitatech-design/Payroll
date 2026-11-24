import logging

from sqlalchemy import false as sa_false  # Upgrade 01I
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status

from ..core import completeness  # Upgrade 01F
from ..core.audit import log_action
from ..core.config import settings
from ..core.db import NO_ID, get_db, new_id, now, serialize, serialize_list
from ..core.deps import AuthContext, get_auth, require_permission
from ..core import data_scope as dscope  # Upgrade 01I
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

# Modul 3 Blueprint HRGA - verifikasi dokumen oleh HR.
PENDING = "PENDING"
VERIFIED = "VERIFIED"
REJECTED = "REJECTED"
VERIFICATION_STATES = (PENDING, VERIFIED, REJECTED)
VERIFICATION_LABELS = {PENDING: "Menunggu Verifikasi", VERIFIED: "Terverifikasi", REJECTED: "Ditolak"}


def _verification_state(row: Dict[str, Any]) -> str:
    """Dokumen lama (sebelum fitur verifikasi) dianggap sudah terverifikasi."""
    return row.get("verification_state") or VERIFIED


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
    verification_state: Optional[str] = Query(None, description="PENDING | VERIFIED | REJECTED"),
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
    if verification_state:
        state = verification_state.strip().upper()
        if state not in VERIFICATION_STATES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Status verifikasi tidak dikenal. Pilihan: Menunggu Verifikasi, Terverifikasi, Ditolak.")
        filters["verification_state"] = state
    filters = await _scoped_doc_filters(ctx, filters)  # Upgrade 01I
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
        item["verification_state"] = _verification_state(item)
        item["verification_state_label"] = VERIFICATION_LABELS.get(item["verification_state"], item["verification_state"])
    return result


@router.get("/verification-summary")
async def verification_summary(ctx: AuthContext = Depends(require_permission("document", "view"))):
    """Jumlah dokumen per status verifikasi (dasar kartu antrean verifikasi)."""
    scope_filters = await _scoped_doc_filters(ctx, {"is_deleted": False})
    rows = serialize_list(await get_db().documents.find(
        scope_filters, {"verification_state": 1, "is_deleted": 1}).to_list(200000))
    counts = {state: 0 for state in VERIFICATION_STATES}
    total = 0
    for row in rows:
        if row.get("is_deleted"):
            continue
        total += 1
        state = _verification_state(row)
        counts[state] = counts.get(state, 0) + 1
    return {"counts": counts, "total": total}


async def _scoped_doc_filters(ctx: AuthContext, filters: Dict[str, Any]) -> Dict[str, Any]:
    """Upgrade 01I: user restricted hanya melihat dokumen KARYAWAN dalam cakupannya (di SQL).
    Dokumen perusahaan/kandidat tidak termasuk cakupan project -> tidak ditampilkan (fail-closed)."""
    scope = await dscope.get_scope(ctx)
    if scope.is_all:
        return filters
    if filters.get("owner_type") not in (None, "employee"):
        return {**filters, "$sql": lambda t: sa_false()}
    return dscope.with_scope({**filters, "owner_type": "employee"}, scope, "owner_id")


async def _ensure_doc_in_scope(ctx: AuthContext, doc: Optional[Dict[str, Any]]) -> None:
    """Upgrade 01I: dokumen di luar cakupan -> 404 generik (sama dengan tidak ada)."""
    scope = await dscope.get_scope(ctx)
    if scope.is_all or not doc:
        return
    if doc.get("owner_type") != "employee" or not await dscope.employee_in_scope(scope, doc.get("owner_id")):
        raise HTTPException(status.HTTP_404_NOT_FOUND, dscope.NOT_FOUND_MSG)


async def _ensure_owner_writable_in_scope(ctx: AuthContext, owner_type: Optional[str], owner_id: Optional[str]) -> None:
    scope = await dscope.get_scope(ctx)
    if scope.is_all:
        return
    if owner_type != "employee":
        raise HTTPException(status.HTTP_403_FORBIDDEN, dscope.FULL_SCOPE_MSG)
    await dscope.ensure_employee_in_scope(ctx, owner_id)


async def _assert_applicant_writable(ctx: AuthContext, owner_type: Optional[str], owner_id: Optional[str]) -> None:
    """Rekrutmen Tahap C: dokumen kandidat yang sudah menjadi karyawan bersifat read-only."""
    if owner_type != "applicant" or not owner_id:
        return
    cand = await ctx.tdb.candidates.find_one(
        {"company_id": ctx.company_id, "id": owner_id}, NO_ID
    )
    if cand and (cand.get("stage_status") == "hired" or cand.get("employee_id")):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Kandidat sudah menjadi karyawan; dokumen kandidat bersifat read-only. Kelola dokumen lewat Data Karyawan.",
        )


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
    await _ensure_owner_writable_in_scope(ctx, owner_type, owner_id)  # Upgrade 01I
    await _assert_applicant_writable(ctx, owner_type, owner_id)
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
    # Modul 3: pengunggah yang memegang `document:verify` (HR) langsung dianggap mengesahkan
    # dokumennya sendiri; pengunggah lain masuk antrean verifikasi.
    can_verify = ctx.has_permission("document", "verify")
    verification_state = VERIFIED if can_verify else PENDING
    verified_fields: Dict[str, Any] = {}
    if verification_state == VERIFIED:
        verified_fields = {
            "verified_by": ctx.user_id,
            "verified_by_name": (ctx.user or {}).get("full_name"),
            "verified_at": now(),
        }
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
            "verification_state": verification_state,
            "verification_note": None,
            **verified_fields,
        },
        ctx.user_id,
    )
    created["document_type_name"] = doc_type.get("name")
    created["verification_state_label"] = VERIFICATION_LABELS.get(verification_state, verification_state)
    await log_action(ctx, "upload", "document", created["id"], created["name"], after=created)
    await completeness.safe_refresh(ctx.company_id, [created.get("owner_id") if created.get("owner_type") == "employee" else None], "document", ctx.user_id)  # Upgrade 01F
    return created


@router.get("/{document_id}")
async def get_document(document_id: str, ctx: AuthContext = Depends(require_permission("document", "view"))):
    repo = TenantRepository("documents", ctx.company_id)
    doc = await repo.get(document_id)
    await _ensure_doc_in_scope(ctx, doc)  # Upgrade 01I
    return doc


async def _verifiable_doc(ctx: AuthContext, document_id: str) -> Dict[str, Any]:
    """Ambil dokumen + pastikan masih dapat diputuskan verifikasinya."""
    repo = TenantRepository("documents", ctx.company_id)
    doc = await repo.get(document_id)
    await _ensure_doc_in_scope(ctx, doc)  # Upgrade 01I
    if doc.get("is_deleted") or doc.get("status") == "archived":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Dokumen yang sudah diarsipkan tidak dapat diverifikasi.")
    return doc


@router.post("/{document_id}/verify")
async def verify_document(document_id: str, payload: Dict[str, Any] = Body(default={}),
                         ctx: AuthContext = Depends(require_permission("document", "verify"))):
    """Sahkan dokumen (status Terverifikasi)."""
    doc = await _verifiable_doc(ctx, document_id)
    if _verification_state(doc) == VERIFIED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Dokumen ini sudah terverifikasi.")
    note = str(payload.get("note") or "").strip() or None
    if note and len(note) > 500:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Catatan verifikasi maksimal 500 karakter.")
    fields = {
        "verification_state": VERIFIED,
        "verification_note": note,
        "verified_by": ctx.user_id,
        "verified_by_name": (ctx.user or {}).get("full_name"),
        "verified_at": now(),
    }
    repo = TenantRepository("documents", ctx.company_id)
    before, after = await repo.update(document_id, fields, ctx.user_id)
    await log_action(ctx, "verify", "document", document_id, doc.get("name"), before=before, after=after)
    return {"message": "Dokumen berhasil diverifikasi.", "verification_state": VERIFIED,
            "verification_state_label": VERIFICATION_LABELS[VERIFIED]}


@router.post("/{document_id}/reject")
async def reject_document(document_id: str, payload: Dict[str, Any] = Body(default={}),
                         ctx: AuthContext = Depends(require_permission("document", "verify"))):
    """Tolak dokumen disertai alasan yang akan dibaca pemilik dokumen."""
    reason = str(payload.get("reason") or "").strip()
    if len(reason) < 3:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Alasan penolakan wajib diisi (minimal 3 karakter).")
    if len(reason) > 500:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Alasan penolakan maksimal 500 karakter.")
    doc = await _verifiable_doc(ctx, document_id)
    if _verification_state(doc) == REJECTED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Dokumen ini sudah ditolak.")
    fields = {
        "verification_state": REJECTED,
        "verification_note": reason,
        "verified_by": ctx.user_id,
        "verified_by_name": (ctx.user or {}).get("full_name"),
        "verified_at": now(),
    }
    repo = TenantRepository("documents", ctx.company_id)
    before, after = await repo.update(document_id, fields, ctx.user_id)
    await log_action(ctx, "reject", "document", document_id, doc.get("name"), before=before, after=after)
    return {"message": "Dokumen ditolak. Pemilik dokumen dapat mengunggah ulang berkas yang benar.",
            "verification_state": REJECTED, "verification_state_label": VERIFICATION_LABELS[REJECTED]}


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
    await _ensure_doc_in_scope(ctx, doc)  # Upgrade 01I
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
    await _ensure_doc_in_scope(ctx, doc)  # Upgrade 01I
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
    existing = await repo.get(document_id)
    await _ensure_doc_in_scope(ctx, existing)  # Upgrade 01I
    await _assert_applicant_writable(ctx, existing.get("owner_type"), existing.get("owner_id"))
    before, after = await repo.update(document_id, data, ctx.user_id)
    await log_action(ctx, "update", "document", document_id, after.get("name"), before=before, after=after)
    await completeness.safe_refresh(ctx.company_id, [after.get("owner_id") if after.get("owner_type") == "employee" else None], "document", ctx.user_id)  # Upgrade 01F
    return after


@router.delete("/{document_id}")
async def delete_document(
    document_id: str, ctx: AuthContext = Depends(require_permission("document", "delete"))
):
    """Soft delete - object storage has no delete API, and history must stay auditable."""
    repo = TenantRepository("documents", ctx.company_id)
    doc = await repo.get(document_id)
    await _ensure_doc_in_scope(ctx, doc)  # Upgrade 01I
    await _assert_applicant_writable(ctx, doc.get("owner_type"), doc.get("owner_id"))
    before, after = await repo.update(
        document_id, {"is_deleted": True, "status": "archived"}, ctx.user_id
    )
    await log_action(ctx, "delete", "document", document_id, doc.get("name"), before=before, after=after)
    await completeness.safe_refresh(ctx.company_id, [doc.get("owner_id") if doc.get("owner_type") == "employee" else None], "document", ctx.user_id)  # Upgrade 01F
    return {"message": f"Dokumen '{doc.get('name')}' berhasil dihapus dari daftar aktif."}
