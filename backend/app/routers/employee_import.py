"""Upgrade 01E - Migrasi / Impor Data Karyawan (Excel 6 sheet) - backend.

Semua endpoint memakai permission khusus `employee:import` (tidak diturunkan dari employee:create/edit)
dan tenant-scoped (company_id dari token). Endpoint impor LAMA (`/api/employees/import/*`) tetap ada
dan tidak diubah.

Alur: POST /batches (upload -> analyze -> validate, simpan metadata + hasil analisis masking; data bisnis
TIDAK diubah) -> GET /batches/{id}/rows (preview) -> POST /batches/{id}/commit (unggah ulang file yang
sama; hash harus cocok; commit transaksional per karyawan). File Excel mentah tidak pernah disimpan.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from starlette.concurrency import run_in_threadpool

from ..core import employee_import as engine
from ..core.audit import log_action
from ..core.db import NO_ID, new_id, now, serialize, serialize_list, audit_fields
from ..core.deps import AuthContext, require_permission
from ..core.employee_import_mapping import MAPPING_VERSION, employee_key, mapping_metadata

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/employee-import", tags=["employee-import"])

BATCHES, ROWS = "employee_import_batches", "employee_import_rows"
COMMITTED_STATES = ("COMMITTED", "PARTIAL")
_perm = require_permission("employee", "import")


async def _batch(ctx: AuthContext, batch_id: str) -> Dict[str, Any]:
    row = await ctx.tdb[BATCHES].find_one({"company_id": ctx.company_id, "id": batch_id}, NO_ID)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch impor tidak ditemukan pada perusahaan aktif Anda.")
    return row


async def _duplicate_committed(ctx: AuthContext, fhash: str, exclude_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    flt: Dict[str, Any] = {"company_id": ctx.company_id, "file_hash": fhash, "batch_status": {"$in": list(COMMITTED_STATES)}}
    if exclude_id:
        flt["id"] = {"$ne": exclude_id}
    return await ctx.tdb[BATCHES].find_one(flt, NO_ID)


def _public(batch: Dict[str, Any]) -> Dict[str, Any]:
    out = serialize(batch)
    out.pop("extra", None)
    return out


@router.get("/template")
async def download_template(ctx: AuthContext = Depends(_perm)):
    lctx = await engine.load_context(ctx.company_id)
    content = await run_in_threadpool(engine.build_template, lctx["masters"], lctx["company"])
    return Response(content=content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="Template-Migrasi-Karyawan-01E.xlsx"',
                             "Cache-Control": "no-store"})


@router.get("/mapping")
async def get_mapping(ctx: AuthContext = Depends(_perm)):
    return mapping_metadata()


@router.post("/batches", status_code=status.HTTP_201_CREATED)
async def upload_and_analyze(file: UploadFile = File(...), ctx: AuthContext = Depends(_perm)):
    """Upload -> Analyze -> Validate. READ-ONLY terhadap data bisnis; hanya menulis tabel impor + audit."""
    raw = await file.read()
    engine.check_limits(raw, file.filename)
    parsed, header_errors, header_warnings = await run_in_threadpool(engine.parse_workbook, raw)
    engine.validate_parsed(parsed, header_errors)
    entities, _lctx = await engine.analyze(ctx.company_id, parsed)
    counts = engine.summarize(entities)
    fhash = engine.file_hash(raw)
    dup = await _duplicate_committed(ctx, fhash)
    warnings = list(header_warnings)
    if dup:
        warnings.append(f"File yang sama persis sudah pernah di-commit (batch {dup.get('batch_number')}). "
                        "Commit ulang memerlukan konfirmasi eksplisit.")
    ts = now()
    batch = {
        "id": new_id(), "company_id": ctx.company_id, "status": "active",
        "batch_number": f"IMP-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{new_id()[:4].upper()}",
        "batch_status": "ANALYZED", "file_name": (file.filename or "")[:255], "file_hash": fhash, "file_size": len(raw),
        "mapping_version": MAPPING_VERSION, "total_employees": len(entities),
        "count_new": counts["NEW"], "count_update": counts["UPDATE"], "count_unchanged": counts["UNCHANGED"],
        "count_conflict": counts["CONFLICT"], "count_error": counts["ERROR"], "committed_count": 0, "failed_count": 0,
        "skipped_count": 0, "uploaded_by": ctx.user_id, "uploaded_by_name": ctx.user.get("full_name") if ctx.user else None,
        "analyzed_at": ts, "duplicate_of_batch_id": (dup or {}).get("id"), "warnings": warnings,
        **audit_fields(ctx.user_id),
    }
    await ctx.tdb[BATCHES].insert_one(dict(batch))
    docs = [engine.row_doc(ctx.company_id, batch["id"], e, ctx.user_id) for e in entities]
    for i in range(0, len(docs), 500):
        await ctx.tdb[ROWS].insert_many(docs[i:i + 500])
    await log_action(ctx, "import_analyze", "employee", batch["id"], batch["batch_number"],
                     after={"file": batch["file_name"], "total": len(entities), **counts},
                     notes=f"Analisis impor Excel {batch['batch_number']} (belum mengubah data karyawan)")
    return {"batch": _public(batch), "duplicate_committed_batch": _public(dup) if dup else None}


@router.get("/batches")
async def list_batches(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100),
                       ctx: AuthContext = Depends(_perm)):
    flt = {"company_id": ctx.company_id}
    total = await ctx.tdb[BATCHES].count_documents(flt)
    items = await ctx.tdb[BATCHES].find(flt, NO_ID).sort("created_at", -1).skip((page - 1) * limit).limit(limit).to_list(limit)
    return {"items": [_public(b) for b in items], "total": total, "page": page, "limit": limit}


@router.get("/batches/{batch_id}")
async def get_batch(batch_id: str, ctx: AuthContext = Depends(_perm)):
    return {"batch": _public(await _batch(ctx, batch_id))}


@router.get("/batches/{batch_id}/rows")
async def preview_rows(batch_id: str, row_class: Optional[str] = Query(None), commit_status: Optional[str] = Query(None),
                       q: Optional[str] = Query(None),
                       page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=500),
                       ctx: AuthContext = Depends(_perm)):
    """Preview hasil analisis (nilai sensitif sudah dimasking saat disimpan)."""
    await _batch(ctx, batch_id)
    flt: Dict[str, Any] = {"company_id": ctx.company_id, "batch_id": batch_id}
    if row_class:
        flt["row_class"] = row_class.upper()
    if commit_status:
        flt["commit_status"] = commit_status.upper()
    if q and q.strip():
        term = re.escape(q.strip()[:64])
        flt["$or"] = [{"employee_number": {"$regex": term, "$options": "i"}}, {"full_name": {"$regex": term, "$options": "i"}}]
    total = await ctx.tdb[ROWS].count_documents(flt)
    rows = await ctx.tdb[ROWS].find(flt, NO_ID).sort("seq", 1).skip((page - 1) * limit).limit(limit).to_list(limit)
    items = serialize_list(rows)
    for r in items:
        r.pop("extra", None)
    return {"items": items, "total": total, "page": page, "limit": limit}


@router.get("/batches/{batch_id}/validation-result")
async def download_validation_result(batch_id: str, ctx: AuthContext = Depends(_perm)):
    """Unduh hasil validasi/error (Excel). Read-only; nilai sensitif tetap dimasking."""
    batch = await _batch(ctx, batch_id)
    rows = await ctx.tdb[ROWS].find({"company_id": ctx.company_id, "batch_id": batch_id}, NO_ID).sort("seq", 1).to_list(200000)
    content = await run_in_threadpool(engine.build_validation_result, batch, rows)
    return Response(content=content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="Hasil-Validasi-{batch.get("batch_number")}.xlsx"',
                             "Cache-Control": "no-store"})


@router.post("/batches/{batch_id}/cancel")
async def cancel_batch(batch_id: str, ctx: AuthContext = Depends(_perm)):
    await _batch(ctx, batch_id)
    res = await ctx.tdb[BATCHES].update_one({"company_id": ctx.company_id, "id": batch_id, "batch_status": "ANALYZED"},
                                            {"$set": {"batch_status": "CANCELLED", "updated_at": now(), "updated_by": ctx.user_id}})
    if not res.modified_count:
        raise HTTPException(status.HTTP_409_CONFLICT, "Hanya batch berstatus ANALYZED yang dapat dibatalkan.")
    await log_action(ctx, "import_cancel", "employee", batch_id, None, notes="Batch impor dibatalkan")
    return {"message": "Batch impor dibatalkan."}


@router.post("/batches/{batch_id}/commit")
async def commit_batch(batch_id: str, file: UploadFile = File(...), confirm_duplicate: bool = Form(False),
                       ctx: AuthContext = Depends(_perm)):
    """Commit eksplisit. File yang sama wajib diunggah ulang (hash dicocokkan; file mentah tidak disimpan).
    Setiap karyawan NEW/UPDATE disimpan dalam transaksinya sendiri; gagal = rollback karyawan tsb saja."""
    batch = await _batch(ctx, batch_id)
    if batch.get("batch_status") != "ANALYZED":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Batch berstatus {batch.get('batch_status')}; tidak dapat di-commit.")
    raw = await file.read()
    engine.check_limits(raw, file.filename)
    if engine.file_hash(raw) != batch.get("file_hash"):
        raise HTTPException(status.HTTP_409_CONFLICT, "File berbeda dengan file yang dianalisis pada batch ini. Unggah file yang sama.")
    dup = await _duplicate_committed(ctx, batch["file_hash"], exclude_id=batch_id)
    if dup and not confirm_duplicate:
        raise HTTPException(status.HTTP_409_CONFLICT, {
            "message": f"File yang sama sudah pernah di-commit (batch {dup.get('batch_number')}). "
                       "Kirim confirm_duplicate=true bila memang ingin commit ulang.",
            "duplicate_of_batch_id": dup.get("id")})
    lock = await ctx.tdb[BATCHES].update_one({"company_id": ctx.company_id, "id": batch_id, "batch_status": "ANALYZED"},
                                             {"$set": {"batch_status": "COMMITTING", "updated_at": now(), "updated_by": ctx.user_id}})
    if not lock.modified_count:
        raise HTTPException(status.HTTP_409_CONFLICT, "Batch sedang/sudah diproses oleh permintaan lain.")
    committed = failed = 0
    final_status = "FAILED"
    try:
        parsed, header_errors, _w = await run_in_threadpool(engine.parse_workbook, raw)
        engine.validate_parsed(parsed, header_errors)
        entities, lctx = await engine.analyze(ctx.company_id, parsed)
        fresh = {employee_key(e["employee_number"]) if not e["key"].startswith("#") else e["key"]: e for e in entities}
        pending = await ctx.tdb[ROWS].find({"company_id": ctx.company_id, "batch_id": batch_id, "commit_status": "PENDING"},
                                           NO_ID).sort("seq", 1).to_list(100000)
        for row in pending:
            ent = fresh.get(employee_key(row["employee_number"]))
            upd: Dict[str, Any] = {"updated_at": now(), "updated_by": ctx.user_id}
            if not ent or ent["row_class"] != row["row_class"] or ent["change_signature"] != row.get("change_signature"):
                upd.update({"commit_status": "FAILED",
                            "commit_error": "Data berubah sejak analisis (klasifikasi/perubahan berbeda). Unggah & analisis ulang."})
                failed += 1
            else:
                try:
                    res = await engine.apply_entity(ctx, ent, lctx, batch)
                    upd.update({"commit_status": "COMMITTED", "committed_at": now(), "employee_id": res["employee_id"],
                                "commit_error": None})
                    committed += 1
                except engine.ImportRowError as exc:
                    upd.update({"commit_status": "FAILED", "commit_error": str(exc)})
                    failed += 1
                except HTTPException as exc:
                    detail = exc.detail if isinstance(exc.detail, str) else "Gagal menyimpan karyawan ini."
                    upd.update({"commit_status": "FAILED", "commit_error": detail[:500]})
                    failed += 1
                except Exception as exc:  # noqa: BLE001
                    # hanya tipe error yang dicatat (pesan DB bisa memuat nilai sensitif)
                    logger.error("Commit impor batch=%s seq=%s gagal: %s", batch_id, row.get("seq"), type(exc).__name__)
                    upd.update({"commit_status": "FAILED",
                                "commit_error": "Terjadi kesalahan saat menyimpan; seluruh perubahan karyawan ini dibatalkan."})
                    failed += 1
            await ctx.tdb[ROWS].update_one({"company_id": ctx.company_id, "id": row["id"]}, {"$set": upd})
        final_status = "COMMITTED" if failed == 0 else ("PARTIAL" if committed else "FAILED")
    finally:
        skipped = await ctx.tdb[ROWS].count_documents({"company_id": ctx.company_id, "batch_id": batch_id,
                                                       "commit_status": "SKIPPED"})
        await ctx.tdb[BATCHES].update_one({"company_id": ctx.company_id, "id": batch_id}, {"$set": {
            "batch_status": final_status, "committed_count": committed, "failed_count": failed, "skipped_count": skipped,
            "committed_at": now(), "committed_by": ctx.user_id,
            "committed_by_name": ctx.user.get("full_name") if ctx.user else None,
            "updated_at": now(), "updated_by": ctx.user_id}})
    await log_action(ctx, "import_commit", "employee", batch_id, batch.get("batch_number"),
                     after={"status": final_status, "committed": committed, "failed": failed, "skipped": skipped},
                     notes=f"Commit impor Excel {batch.get('batch_number')}: {committed} berhasil, {failed} gagal, {skipped} dilewati")
    return {"batch": _public(await _batch(ctx, batch_id)),
            "summary": f"{committed} karyawan disimpan, {failed} gagal, {skipped} dilewati (UNCHANGED/CONFLICT/ERROR)."}
