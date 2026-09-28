"""Phase 2A CP4 - Dokumen Transaksi Aset + Employee Asset 360.

Dokumen (BAST bertanda tangan, foto kondisi, berita acara, bukti kerusakan/kehilangan, pendukung, lainnya) diunggah dari
transaksi Penyerahan (HANDOVER), Pengembalian (RETURN) atau Saldo Awal (OPENING_EXISTING).
  * File fisik disimpan SATU KALI di object storage (R2); tabel `asset_documents` hanya menyimpan metadata + object key.
    Profil Karyawan (Asset 360) membaca baris yang sama -> tidak ada salinan / upload ulang.
  * Boleh diunggah setelah transaksi PUBLISHED; snapshot BAST (asset_basts.snapshot) TIDAK PERNAH diubah.
  * SIGNED_BAST: maksimal satu versi ACTIVE per transaksi (unik via signed_lock). Ganti = versi baru ACTIVE, versi lama
    SUPERSEDED (tidak dihapus). Dokumen lain: hapus = soft delete (DELETED) + audit trail. Tidak ada hard delete.
  * Otorisasi: permission efektif asset_document:{view,create,delete} (bukan nama role). Scope 01I di SQL: transaksi
    sumber harus terlihat (project scope) & karyawan harus terlihat (employee scope); di luar scope -> 404 generik.
  * Penyimpanan lokal HANYA untuk development/test: aktif bila R2 tidak dikonfigurasi DAN env
    ASSET_DOC_LOCAL_STORAGE_DIR diisi secara eksplisit. Staging/production selalu memakai R2.
"""
from __future__ import annotations

import hashlib
import os
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy.exc import IntegrityError

from ..core import data_scope as dscope
from ..core import storage
from ..core.audit import log_action
from ..core.db import NO_ID, get_db, new_id, now, transaction
from ..core.deps import AuthContext, require_permission
from .asset_lifecycle import _names, _not_found, _user_names

router = APIRouter(tags=["Manajemen Aset - Dokumen & Asset 360"])

SOURCES = {  # source_type -> (tabel transaksi, tabel item, kolom FK item, label)
    "HANDOVER": ("asset_handovers", "asset_handover_items", "handover_id", "Penyerahan Aset"),
    "RETURN": ("asset_returns", "asset_return_items", "return_id", "Pengembalian Aset"),
    "OPENING_EXISTING": ("asset_openings", "asset_opening_items", "opening_id", "Saldo Awal (Opening Existing)"),
}
DOC_TYPES = {
    "SIGNED_BAST": "BAST Ditandatangani",
    "CONDITION_PHOTO": "Foto Kondisi",
    "HANDOVER_REPORT": "Berita Acara / Surat Serah Terima",
    "DAMAGE_OR_LOSS_EVIDENCE": "Bukti Kerusakan / Kehilangan",
    "SUPPORTING_DOCUMENT": "Dokumen Pendukung",
    "OTHER": "Lainnya",
}
ALLOWED = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}
MAX_BYTES = 10 * 1024 * 1024
MAX_PER_SOURCE = 10
ACTIVE, SUPERSEDED, DELETED = "ACTIVE", "SUPERSEDED", "DELETED"
STATUS_LABEL = {ACTIVE: "Aktif", SUPERSEDED: "Digantikan", DELETED: "Dihapus"}


def _err(code: int, msg: str):
    return HTTPException(code, msg)


# ------------------------------------------------------------------ storage (R2; lokal hanya dev bila eksplisit)
def _local_dir() -> Optional[Path]:
    d = (os.environ.get("ASSET_DOC_LOCAL_STORAGE_DIR") or "").strip()
    return Path(d) if d and not storage.storage_configured() else None


def _storage_ready() -> bool:
    return storage.storage_configured() or _local_dir() is not None


def _key(cid: str, doc_id: str, ext: str) -> str:
    return f"{storage.APP_NAME}/companies/{cid}/asset-documents/{doc_id}.{ext}"


def _put(path: str, data: bytes, mime: str) -> None:
    local = _local_dir()
    if local is not None:
        f = local / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
        return
    storage.put_object(path, data, mime)


def _get(path: str) -> bytes:
    local = _local_dir()
    if local is not None:
        f = local / path
        if not f.is_file():
            raise storage.StorageError("Berkas tidak ditemukan.")
        return f.read_bytes()
    return storage.get_object(path)[0]


def _drop(path: str) -> None:
    """Hanya untuk rollback upload yang GAGAL tercatat (file yatim). Dokumen tercatat tidak pernah dihapus fisik."""
    try:
        local = _local_dir()
        if local is not None:
            (local / path).unlink(missing_ok=True)
        else:
            storage.delete_object(path)
    except Exception:  # noqa: BLE001 - best effort
        pass


def _sniff(ext: str, data: bytes) -> bool:
    if ext == "pdf":
        return data[:5] == b"%PDF-"
    if ext == "png":
        return data[:8] == b"\x89PNG\r\n\x1a\n"
    return data[:3] == b"\xff\xd8\xff"


async def _read_file(file: UploadFile) -> Tuple[bytes, str, str]:
    name = os.path.basename((file.filename or "").strip()) or "dokumen"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED:
        raise _err(422, "Format file tidak didukung. Gunakan PDF, JPG, JPEG, atau PNG.")
    data = await file.read(MAX_BYTES + 1)
    if not data:
        raise _err(422, "File kosong.")
    if len(data) > MAX_BYTES:
        raise _err(413, "Ukuran file melebihi batas 10 MB.")
    if not _sniff(ext, data):
        raise _err(422, "Isi file tidak sesuai dengan formatnya (PDF/JPG/PNG).")
    return data, name[:200], ext


# ------------------------------------------------------------------ source & scope
async def _source(ctx: AuthContext, source_type: str, source_id: str) -> Tuple[Dict[str, Any], set]:
    if source_type not in SOURCES:
        raise _err(422, "Jenis transaksi sumber tidak valid.")
    coll, item_coll, fk, _ = SOURCES[source_type]
    scope = await dscope.get_scope(ctx)
    doc = await get_db()[coll].find_one(dscope.with_project_scope({"company_id": ctx.company_id, "id": source_id}, scope), NO_ID)
    if not doc or doc.get("status") == "deleted":
        raise _not_found()
    dscope.assert_project_record_visible(scope, doc)
    emp = await get_db().employees.find_one(dscope.with_scope({"company_id": ctx.company_id, "id": doc.get("employee_id")}, scope),
                                            {"id": 1})
    if not emp:
        raise _not_found()
    items = await get_db()[item_coll].find({"company_id": ctx.company_id, fk: source_id}, {"asset_id": 1}).to_list(1000)
    return doc, {i["asset_id"] for i in items}


async def _visible_doc(ctx: AuthContext, doc_id: str) -> Dict[str, Any]:
    d = await get_db().asset_documents.find_one({"company_id": ctx.company_id, "id": doc_id}, NO_ID)
    if not d:
        raise _not_found()
    await _source(ctx, d["source_type"], d["source_id"])   # 01I: transaksi & karyawan sumber harus terlihat
    return d


async def _decorate(cid: str, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    assets = await _names(cid, "assets", [d.get("asset_id") for d in docs], None)
    basts = await _names(cid, "asset_basts", [d.get("bast_id") for d in docs], "system_number")
    users = await _user_names([d.get("uploaded_by") for d in docs] + [d.get("deleted_by") for d in docs])
    out = []
    for d in docs:
        a = assets.get(d.get("asset_id")) or {}
        out.append({k: d.get(k) for k in ("id", "source_type", "source_id", "bast_id", "employee_id", "asset_id", "document_type",
                                          "document_date", "file_name", "file_extension", "mime_type", "file_size", "notes",
                                          "doc_status", "version_no", "replaces_id", "superseded_by", "superseded_at",
                                          "uploaded_by", "uploaded_at", "deleted_by", "deleted_at", "delete_reason")}
                   | {"document_type_label": DOC_TYPES.get(d.get("document_type")), "status_label": STATUS_LABEL.get(d.get("doc_status")),
                      "source_label": SOURCES[d["source_type"]][3], "asset_code": a.get("asset_code"), "asset_name": a.get("name"),
                      "bast_number": basts.get(d.get("bast_id")), "uploaded_by_name": users.get(d.get("uploaded_by")),
                      "deleted_by_name": users.get(d.get("deleted_by"))})
    return out


def _can(ctx: AuthContext) -> Dict[str, bool]:
    return {a: ctx.has_permission("asset_document", a) for a in ("view", "create", "delete")}


def _public(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in d.items() if k not in ("storage_path", "signed_lock", "file_hash")}


# ------------------------------------------------------------------ endpoints dokumen
@router.get("/asset-documents/options")
async def options(ctx: AuthContext = Depends(require_permission("asset_document", "view"))):
    return {"document_types": [{"code": k, "name": v} for k, v in DOC_TYPES.items()],
            "sources": [{"code": k, "name": v[3]} for k, v in SOURCES.items()],
            "allowed_extensions": sorted(ALLOWED), "max_file_mb": MAX_BYTES // (1024 * 1024), "max_per_source": MAX_PER_SOURCE,
            "storage_ready": _storage_ready(), "can": _can(ctx)}


@router.get("/asset-documents")
async def list_documents(source_type: str = Query(...), source_id: str = Query(...), include_history: bool = Query(False),
                         ctx: AuthContext = Depends(require_permission("asset_document", "view"))):
    await _source(ctx, source_type, source_id)
    flt: Dict[str, Any] = {"company_id": ctx.company_id, "source_type": source_type, "source_id": source_id}
    if not include_history:
        flt["doc_status"] = ACTIVE
    docs = await get_db().asset_documents.find(flt, NO_ID).sort([("uploaded_at", -1)]).to_list(200)
    active = sum(1 for d in docs if d["doc_status"] == ACTIVE) if include_history else len(docs)
    return {"items": await _decorate(ctx.company_id, docs), "active_count": active, "max_per_source": MAX_PER_SOURCE,
            "can": _can(ctx)}


async def _store_new(ctx: AuthContext, *, source_type: str, source_id: str, document_type: str, file: UploadFile,
                     asset_id: Optional[str], document_date: Optional[str], notes: Optional[str],
                     replaces: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not _storage_ready():
        raise _err(503, "Penyimpanan dokumen (object storage) belum dikonfigurasi.")
    if document_type not in DOC_TYPES:
        raise _err(422, "Jenis dokumen tidak valid.")
    src, asset_ids = await _source(ctx, source_type, source_id)
    if src.get("doc_state") == "CANCELLED":
        raise _err(409, "Transaksi sudah dibatalkan; dokumen tidak dapat ditambahkan.")
    if document_type == "SIGNED_BAST" and (src.get("doc_state") != "PUBLISHED" or not src.get("bast_id")):
        raise _err(409, "BAST ditandatangani hanya dapat diunggah setelah transaksi dipublish (BAST terbit).")
    if asset_id and asset_id not in asset_ids:
        raise _err(422, "Aset yang dipilih bukan bagian dari transaksi ini.")
    if document_date:
        try:
            document_date = date.fromisoformat(document_date[:10]).isoformat()
        except ValueError:
            raise _err(422, "Tanggal dokumen tidak valid (format YYYY-MM-DD).") from None
    data, name, ext = await _read_file(file)
    doc_id = new_id()
    path = _key(ctx.company_id, doc_id, ext)
    try:
        _put(path, data, ALLOWED[ext])
    except storage.StorageError as exc:
        raise _err(502, "Gagal menyimpan file ke object storage. Coba lagi.") from exc
    ts = now()
    row = {"id": doc_id, "company_id": ctx.company_id, "status": "active", "created_at": ts, "updated_at": ts,
           "created_by": ctx.user_id, "updated_by": ctx.user_id, "source_type": source_type, "source_id": source_id,
           "bast_id": src.get("bast_id"), "employee_id": src.get("employee_id"), "asset_id": asset_id or None,
           "document_type": document_type, "document_date": document_date or None, "file_name": name, "file_extension": ext,
           "mime_type": ALLOWED[ext], "file_size": len(data), "file_hash": hashlib.sha256(data).hexdigest(), "storage_path": path,
           "notes": (notes or "").strip()[:2000] or None, "doc_status": ACTIVE, "version_no": 1, "replaces_id": None,
           "signed_lock": source_id if document_type == "SIGNED_BAST" else None, "uploaded_by": ctx.user_id, "uploaded_at": ts}
    coll = SOURCES[source_type][0]
    try:
        async with transaction() as tx:
            await tx.select_one_for_update(coll, {"company_id": ctx.company_id, "id": source_id})   # serialisasi kuota
            if replaces:
                cur = await tx.select_one_for_update("asset_documents", {"company_id": ctx.company_id, "id": replaces["id"]})
                if not cur or cur["doc_status"] != ACTIVE:
                    raise _err(409, "Versi BAST ditandatangani ini sudah tidak aktif. Muat ulang halaman.")
                row.update(version_no=int(cur.get("version_no") or 1) + 1, replaces_id=cur["id"])
                await tx.update("asset_documents", {"company_id": ctx.company_id, "id": cur["id"]},
                                {"doc_status": SUPERSEDED, "signed_lock": None, "superseded_by": doc_id, "superseded_at": ts,
                                 "updated_at": ts, "updated_by": ctx.user_id})
            else:
                n = (await tx.conn.execute(
                    sa.text("SELECT COUNT(*) FROM asset_documents WHERE company_id = :c AND source_type = :t"
                                                  " AND source_id = :s AND doc_status = 'ACTIVE'"),
                    {"c": ctx.company_id, "t": source_type, "s": source_id})).scalar()
                if n >= MAX_PER_SOURCE:
                    raise _err(409, f"Maksimal {MAX_PER_SOURCE} dokumen aktif per transaksi.")
            await tx.insert("asset_documents", row)
    except IntegrityError:
        _drop(path)
        raise _err(409, "BAST ditandatangani yang aktif sudah ada untuk transaksi ini. Gunakan 'Ganti Versi'.") from None
    except BaseException:
        _drop(path)
        raise
    label = f"{DOC_TYPES[document_type]} - {name}"
    await log_action(ctx, "replace" if replaces else "upload", "asset_document", doc_id, label, module="asset",
                     before={"replaced_document_id": replaces["id"], "version_no": replaces.get("version_no")} if replaces else None,
                     after={"source_type": source_type, "source_id": source_id, "document_type": document_type,
                            "file_name": name, "file_size": len(data), "version_no": row["version_no"], "asset_id": asset_id})
    return _public((await _decorate(ctx.company_id, [row]))[0])


@router.post("/asset-documents", status_code=201)
async def upload_document(source_type: str = Form(...), source_id: str = Form(...), document_type: str = Form(...),
                          asset_id: Optional[str] = Form(None), document_date: Optional[str] = Form(None),
                          notes: Optional[str] = Form(None), file: UploadFile = File(...),
                          ctx: AuthContext = Depends(require_permission("asset_document", "create"))):
    return await _store_new(ctx, source_type=source_type, source_id=source_id, document_type=document_type, file=file,
                            asset_id=asset_id or None, document_date=document_date or None, notes=notes)


@router.post("/asset-documents/{doc_id}/replace", status_code=201)
async def replace_signed_bast(doc_id: str, file: UploadFile = File(...), document_date: Optional[str] = Form(None),
                              notes: Optional[str] = Form(None),
                              ctx: AuthContext = Depends(require_permission("asset_document", "create"))):
    cur = await _visible_doc(ctx, doc_id)
    if cur["document_type"] != "SIGNED_BAST":
        raise _err(422, "Penggantian versi hanya untuk BAST Ditandatangani.")
    if cur["doc_status"] != ACTIVE:
        raise _err(409, "Hanya versi aktif yang dapat diganti.")
    return await _store_new(ctx, source_type=cur["source_type"], source_id=cur["source_id"], document_type="SIGNED_BAST",
                            file=file, asset_id=cur.get("asset_id"), document_date=document_date or None, notes=notes,
                            replaces=cur)


@router.get("/asset-documents/{doc_id}/file")
async def document_file(doc_id: str, download: bool = Query(False),
                        ctx: AuthContext = Depends(require_permission("asset_document", "view"))):
    d = await _visible_doc(ctx, doc_id)
    if d["doc_status"] == DELETED:
        raise _not_found()
    try:
        data = _get(d["storage_path"])
    except storage.StorageError as exc:
        raise _err(502, "File tidak dapat diambil dari object storage.") from exc
    disp = "attachment" if download else "inline"
    safe = d["file_name"].replace('"', "").encode("ascii", "ignore").decode() or f"dokumen.{d['file_extension']}"
    return Response(content=data, media_type=d["mime_type"],
                    headers={"Content-Disposition": f'{disp}; filename="{safe}"', "Cache-Control": "no-store",
                             "X-Content-Type-Options": "nosniff"})


@router.delete("/asset-documents/{doc_id}")
async def delete_document(doc_id: str, reason: Optional[str] = Query(None, max_length=500),
                          ctx: AuthContext = Depends(require_permission("asset_document", "delete"))):
    d = await _visible_doc(ctx, doc_id)
    if d["document_type"] == "SIGNED_BAST":
        raise _err(409, "BAST ditandatangani tidak dapat dihapus. Gunakan 'Ganti Versi' bila perlu diperbarui.")
    if d["doc_status"] != ACTIVE:
        raise _err(409, "Dokumen sudah tidak aktif.")
    ts = now()
    async with transaction() as tx:
        n = await tx.update("asset_documents", {"company_id": ctx.company_id, "id": doc_id, "doc_status": ACTIVE},
                            {"doc_status": DELETED, "deleted_by": ctx.user_id, "deleted_at": ts,
                             "delete_reason": (reason or "").strip() or None, "updated_at": ts, "updated_by": ctx.user_id})
        if not n:
            raise _err(409, "Dokumen sudah tidak aktif.")
    await log_action(ctx, "delete", "asset_document", doc_id, f"{DOC_TYPES.get(d['document_type'])} - {d['file_name']}",
                     module="asset", before={"doc_status": ACTIVE}, after={"doc_status": DELETED, "reason": reason, "soft_delete": True})
    return {"ok": True, "id": doc_id, "doc_status": DELETED}


# ------------------------------------------------------------------ Employee Asset 360 (read-only, tanpa tabel baru)
@router.get("/employees/{employee_id}/asset-360")
async def employee_asset_360(employee_id: str, ctx: AuthContext = Depends(require_permission("asset", "view"))):
    db, cid = get_db(), ctx.company_id
    scope = await dscope.get_scope(ctx)
    emp = await db.employees.find_one(dscope.with_scope({"company_id": cid, "id": employee_id}, scope), NO_ID)
    if not emp:
        raise _not_found()
    # transaksi karyawan yang terlihat (project scope 01I di SQL)
    tx_docs: Dict[str, List[Dict[str, Any]]] = {}
    for st, (coll, _i, _f, _l) in SOURCES.items():
        tx_docs[st] = await db[coll].find(dscope.with_project_scope({"company_id": cid, "employee_id": employee_id,
                                                                    "doc_state": "PUBLISHED"}, scope), NO_ID).to_list(2000)
    by_id = {st: {d["id"]: d for d in rows} for st, rows in tx_docs.items()}
    holdings = await db.asset_holdings.find({"company_id": cid, "employee_id": employee_id}, NO_ID).to_list(5000)
    holdings = [h for h in holdings if (h.get("handover_id") in by_id["HANDOVER"]) or (h.get("opening_id") in by_id["OPENING_EXISTING"])]
    inspections = await db.asset_inspections.find(dscope.with_project_scope({"company_id": cid, "employee_id": employee_id,
                                                                            "inspection_state": "COMPLETED"}, scope), NO_ID).to_list(5000)
    items: Dict[str, List[Dict[str, Any]]] = {}
    for st, (_c, item_coll, fk, _l) in SOURCES.items():
        ids = list(by_id[st]) or ["-"]
        items[st] = await db[item_coll].find({"company_id": cid, fk: {"$in": ids}}, NO_ID).to_list(20000)
    asset_ids = {h["asset_id"] for h in holdings} | {i["asset_id"] for v in items.values() for i in v} | {i["asset_id"] for i in inspections}
    assets = await _names(cid, "assets", asset_ids, None)
    cats = await _names(cid, "asset_categories", [a.get("category_id") for a in assets.values()])
    all_tx = [d for rows in tx_docs.values() for d in rows]
    projects = await _names(cid, "projects", [d.get("project_id") for d in all_tx] + [h.get("project_id") for h in holdings])
    locs = await _names(cid, "work_locations", [h.get("work_location_id") for h in holdings] + [d.get("work_location_id") for d in all_tx])
    ret_items = {i["id"]: i for i in items["RETURN"]}
    cond_ids = [h.get("initial_condition_id") for h in holdings] + [a.get("condition_id") for a in assets.values()]
    cond_ids += [i.get("condition_id") for v in items.values() for i in v] + [i.get("final_condition_id") for i in inspections]
    conds = await _names(cid, "asset_conditions", cond_ids)
    bast_ids = [d.get("bast_id") for d in all_tx] + [h.get("handover_bast_id") for h in holdings]
    basts = await _names(cid, "asset_basts", bast_ids, "system_number")

    def _asset(aid):
        a = assets.get(aid) or {}
        return {"asset_id": aid, "asset_code": a.get("asset_code"), "asset_name": a.get("name"), "serial_number": a.get("serial_number"),
                "category_name": cats.get(a.get("category_id")), "legacy_code": a.get("legacy_code")}

    current = []
    for h in sorted((h for h in holdings if h.get("holding_status") == "ACTIVE"), key=lambda h: h.get("start_date") or "", reverse=True):
        st = "OPENING_EXISTING" if h.get("opening_id") else "HANDOVER"
        current.append({**_asset(h["asset_id"]), "holding_id": h["id"], "start_date": h.get("start_date"),
                        "initial_condition_name": conds.get(h.get("initial_condition_id")),
                        "current_condition_name": conds.get((assets.get(h["asset_id"]) or {}).get("condition_id")),
                        "accessories": h.get("accessories_out"), "project_name": projects.get(h.get("project_id")),
                        "work_location_name": locs.get(h.get("work_location_id")), "source_type": st,
                        "source_id": h.get("opening_id") or h.get("handover_id"), "bast_id": h.get("handover_bast_id"),
                        "bast_number": basts.get(h.get("handover_bast_id"))})
    history = []
    date_field = {"HANDOVER": "handover_date", "RETURN": "return_date", "OPENING_EXISTING": "opening_date"}
    for st, rows in items.items():
        for it in rows:
            src = by_id[st][it[SOURCES[st][2]]]
            history.append({**_asset(it["asset_id"]), "event_type": st, "date": src.get(date_field[st]), "source_type": st,
                            "source_id": src["id"], "bast_id": src.get("bast_id"), "bast_number": basts.get(src.get("bast_id")),
                            "project_name": projects.get(src.get("project_id")), "condition_before": None,
                            "condition_after": conds.get(it.get("condition_id")), "result_state": None,
                            "notes": it.get("item_notes"), "at": src.get("published_at")})
    for ins in inspections:
        ri = ret_items.get(ins.get("return_item_id")) or {}
        rsrc = by_id["RETURN"].get(ins.get("return_id")) or {}
        history.append({**_asset(ins["asset_id"]), "event_type": "INSPECTION", "date": str(ins.get("completed_at") or "")[:10] or None,
                        "source_type": "RETURN", "source_id": ins.get("return_id"), "inspection_id": ins["id"],
                        "bast_id": rsrc.get("bast_id"), "bast_number": basts.get(rsrc.get("bast_id")),
                        "project_name": projects.get(ins.get("project_id")), "condition_before": conds.get(ri.get("condition_id")),
                        "condition_after": conds.get(ins.get("final_condition_id")), "result_state": ins.get("result_state"),
                        "notes": ins.get("notes"), "at": ins.get("completed_at")})
    order = {"OPENING_EXISTING": 0, "HANDOVER": 1, "RETURN": 2, "INSPECTION": 3}
    history.sort(key=lambda e: (e.get("date") or "", str(e.get("at") or ""), order[e["event_type"]]), reverse=True)
    documents = None
    if ctx.has_permission("asset_document", "view"):
        visible_src = [i for rows in by_id.values() for i in rows] or ["-"]
        docs = await db.asset_documents.find({"company_id": cid, "employee_id": employee_id, "source_id": {"$in": visible_src},
                                              "doc_status": {"$in": [ACTIVE, SUPERSEDED]}}, NO_ID).sort([("uploaded_at", -1)]).to_list(1000)
        documents = await _decorate(cid, docs)
    return {"employee": {"id": emp["id"], "full_name": emp.get("full_name"), "employee_number": emp.get("employee_number")},
            "current": current, "history": history, "documents": documents,
            "can": {"documents": documents is not None, **_can(ctx)}}
