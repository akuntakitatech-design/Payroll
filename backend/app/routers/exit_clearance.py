"""Core HR - Exit Clearance (offboarding).

CP1 mencakup:
- Kasus keluar karyawan (nomor otomatis EXIT/{YYYY}/{SEQ:5}) dengan tipe keluar & tanggal kerja terakhir.
- Checklist serah terima lintas bagian (HR, Atasan, GA/Aset, Keuangan, IT, Umum).
- Validasi silang aset: item GA tidak dapat ditutup selama masih ada aset aktif dipegang karyawan, dan
  persetujuan final ditolak bila aset outstanding > 0.
- Persetujuan final mengubah Status Karyawan menjadi kategori TIDAK AKTIF + mencatat riwayat status.

Catatan: persetujuan hanya dapat dilakukan pada/setelah tanggal kerja terakhir agar status karyawan tidak
berubah lebih awal (tanpa penjadwal latar belakang). Pembatalan kasus tidak mengembalikan status karyawan.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from ..core import completeness, data_scope as dscope, doc_sequence
from ..core.audit import build_audit_entry, log_action
from ..core.db import NO_ID, audit_fields, new_id, now, serialize, serialize_list, transaction
from ..core.deps import AuthContext, require_permission
from ..core.employee_status import default_status, history_doc, legacy_for, today_local

router = APIRouter(prefix="/exit-clearance", tags=["Exit Clearance"])

SEQ = "EXIT_CLEARANCE"

DRAFT, PENDING_APPROVAL, COMPLETED, CANCELLED = "DRAFT", "PENDING_APPROVAL", "COMPLETED", "CANCELLED"
CASE_STATES = (DRAFT, PENDING_APPROVAL, COMPLETED, CANCELLED)
OPEN_STATES = (DRAFT, PENDING_APPROVAL)
CLOSED_STATES = (COMPLETED, CANCELLED)

PENDING, DONE, NA = "PENDING", "DONE", "NA"
ITEM_STATES = (PENDING, DONE, NA)

EXIT_TYPES: Dict[str, str] = {
    "RESIGN": "Resign / mengundurkan diri",
    "END_OF_CONTRACT": "Berakhirnya kontrak",
    "TERMINATION": "PHK",
    "RETIREMENT": "Pensiun",
    "OTHER": "Lainnya",
}

CASE_LABELS = {
    DRAFT: "Draft",
    PENDING_APPROVAL: "Menunggu Persetujuan",
    COMPLETED: "Selesai",
    CANCELLED: "Dibatalkan",
}

ITEM_LABELS = {PENDING: "Belum", DONE: "Selesai", NA: "Tidak Berlaku"}

CATEGORY_LABELS = {
    "HR": "HR",
    "ATASAN": "Atasan Langsung",
    "GA": "GA / Aset",
    "FINANCE": "Keuangan",
    "IT": "IT",
    "UMUM": "Umum",
}

# Checklist default. Urutan = urutan tampil (line_no).
DEFAULT_ITEMS: List[tuple] = [
    ("HR", "Serah terima dokumen dan berkas kepegawaian"),
    ("ATASAN", "Serah terima pekerjaan, laporan, dan tanggung jawab"),
    ("GA", "Pengembalian aset dan perlengkapan perusahaan"),
    ("FINANCE", "Penyelesaian kasbon/pinjaman dan administrasi keuangan"),
    ("IT", "Pengembalian akses sistem, email, dan perangkat IT"),
    ("UMUM", "Pengembalian ID card, kunci, dan akses gedung"),
]

_view = require_permission("exit_clearance", "view")
_create = require_permission("exit_clearance", "create")
_edit = require_permission("exit_clearance", "edit")
_delete = require_permission("exit_clearance", "delete")
_approve = require_permission("exit_clearance", "approve")

OUTSTANDING_MSG = (
    "Masih ada {count} aset aktif yang dipegang karyawan. Selesaikan pengembalian aset "
    "(menu Pengembalian & Pemeriksaan) sebelum menutup item GA atau menyetujui exit clearance."
)


def _err(code: int, msg: str) -> HTTPException:
    return HTTPException(code, msg)


def _parse_date(value: Any, label: str) -> date:
    text = str(value or "").strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{label} harus berformat YYYY-MM-DD.") from exc


def _case_public(row: Dict[str, Any], *, progress: Optional[Dict[str, int]] = None,
                 outstanding: int = 0, project_name: Optional[str] = None) -> Dict[str, Any]:
    return {
        "id": row.get("id"),
        "case_number": row.get("case_number"),
        "employee_id": row.get("employee_id"),
        "employee_number": row.get("employee_number"),
        "employee_name": row.get("employee_name"),
        "project_id": row.get("project_id"),
        "project_name": project_name,
        "exit_type": row.get("exit_type"),
        "exit_type_label": EXIT_TYPES.get(row.get("exit_type") or "", row.get("exit_type")),
        "request_date": row.get("request_date"),
        "last_working_date": row.get("last_working_date"),
        "reason": row.get("reason"),
        "notes": row.get("notes"),
        "case_state": row.get("case_state"),
        "case_state_label": CASE_LABELS.get(row.get("case_state") or "", row.get("case_state")),
        "submitted_at": row.get("submitted_at"),
        "decided_at": row.get("decided_at"),
        "decision_note": row.get("decision_note"),
        "completed_at": row.get("completed_at"),
        "cancelled_at": row.get("cancelled_at"),
        "cancel_reason": row.get("cancel_reason"),
        "progress": progress or {"done": 0, "total": 0},
        "outstanding_assets": outstanding,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _item_public(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row.get("id"),
        "line_no": row.get("line_no"),
        "category": row.get("category"),
        "category_label": CATEGORY_LABELS.get(row.get("category") or "", row.get("category")),
        "name": row.get("name"),
        "item_state": row.get("item_state"),
        "item_state_label": ITEM_LABELS.get(row.get("item_state") or "", row.get("item_state")),
        "note": row.get("note"),
        "decided_at": row.get("decided_at"),
        "decided_by": row.get("decided_by"),
    }


async def _case_or_404(ctx: AuthContext, clearance_id: str) -> Dict[str, Any]:
    scope = await dscope.get_scope(ctx)
    flt = dscope.with_scope(
        {"company_id": ctx.company_id, "id": clearance_id, "status": {"$ne": "deleted"}},
        scope, field_name="employee_id",
    )
    row = await ctx.tdb.exit_clearances.find_one(flt, NO_ID)
    if not row:
        raise _err(status.HTTP_404_NOT_FOUND, "Kasus exit clearance tidak ditemukan pada perusahaan aktif Anda.")
    return row


async def _items_for(ctx: AuthContext, clearance_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    if not clearance_ids:
        return {}
    rows = serialize_list(await ctx.tdb.exit_clearance_items.find(
        {"company_id": ctx.company_id, "clearance_id": {"$in": clearance_ids}}, NO_ID,
    ).sort("line_no", 1).to_list(20000))
    out: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(row.get("clearance_id"), []).append(row)
    return out


async def _outstanding_counts(ctx: AuthContext, employee_ids: List[str]) -> Dict[str, int]:
    if not employee_ids:
        return {}
    rows = serialize_list(await ctx.tdb.asset_holdings.find(
        {"company_id": ctx.company_id, "employee_id": {"$in": employee_ids}, "holding_status": "ACTIVE"},
        NO_ID,
    ).to_list(20000))
    counts: Dict[str, int] = {}
    for row in rows:
        counts[row.get("employee_id")] = counts.get(row.get("employee_id"), 0) + 1
    return counts


async def _outstanding_list(ctx: AuthContext, employee_id: str) -> List[Dict[str, Any]]:
    holdings = serialize_list(await ctx.tdb.asset_holdings.find(
        {"company_id": ctx.company_id, "employee_id": employee_id, "holding_status": "ACTIVE"}, NO_ID,
    ).to_list(500))
    if not holdings:
        return []
    asset_ids = [h.get("asset_id") for h in holdings if h.get("asset_id")]
    assets = {a["id"]: a for a in serialize_list(await ctx.tdb.assets.find(
        {"company_id": ctx.company_id, "id": {"$in": asset_ids}}, NO_ID,
    ).to_list(500))}
    out = []
    for h in holdings:
        asset = assets.get(h.get("asset_id")) or {}
        out.append({
            "asset_id": h.get("asset_id"),
            "asset_code": asset.get("asset_code"),
            "asset_name": asset.get("name"),
            "holding_id": h.get("id"),
            "start_date": h.get("start_date"),
        })
    return out


async def _project_names(ctx: AuthContext, project_ids: List[str]) -> Dict[str, str]:
    ids = [p for p in project_ids if p]
    if not ids:
        return {}
    rows = serialize_list(await ctx.tdb.projects.find(
        {"company_id": ctx.company_id, "id": {"$in": ids}}, NO_ID,
    ).to_list(500))
    return {r["id"]: r.get("name") for r in rows}


def _progress(items: List[Dict[str, Any]]) -> Dict[str, int]:
    total = len(items)
    done = sum(1 for i in items if i.get("item_state") in (DONE, NA))
    return {"done": done, "total": total}


async def _taken_number(ctx: AuthContext):
    async def _exists(candidate: str) -> bool:
        return bool(await ctx.tdb.exit_clearances.count_documents(
            {"company_id": ctx.company_id, "case_number": candidate}))
    return _exists


# --------------------------------------------------------------------------- read

@router.get("/summary")
async def exit_summary(ctx: AuthContext = Depends(_view)):
    """Ringkasan jumlah kasus per status (untuk kartu di halaman)."""
    scope = await dscope.get_scope(ctx)
    flt = dscope.with_scope(
        {"company_id": ctx.company_id, "status": {"$ne": "deleted"}}, scope, field_name="employee_id")
    rows = serialize_list(await ctx.tdb.exit_clearances.find(flt, {"case_state": 1}).to_list(20000))
    counts = {state: 0 for state in CASE_STATES}
    for row in rows:
        state = row.get("case_state")
        counts[state] = counts.get(state, 0) + 1
    return {"counts": counts, "total": len(rows)}


@router.get("/candidates")
async def list_candidates(q: Optional[str] = None, ctx: AuthContext = Depends(_view)):
    """Karyawan aktif (dalam cakupan data) yang belum punya kasus exit clearance terbuka."""
    scope = await dscope.get_scope(ctx)
    flt = dscope.with_scope({"company_id": ctx.company_id, "status": "active"}, scope)
    rows = serialize_list(await ctx.tdb.employees.find(flt, NO_ID).sort("full_name", 1).to_list(2000))
    needle = (q or "").strip().lower()
    if needle:
        rows = [
            r for r in rows
            if needle in (r.get("full_name") or "").lower()
            or needle in (r.get("employee_number") or "").lower()
        ]
    open_rows = serialize_list(await ctx.tdb.exit_clearances.find(
        {"company_id": ctx.company_id, "case_state": {"$in": list(OPEN_STATES)}, "status": {"$ne": "deleted"}},
        NO_ID,
    ).to_list(5000))
    open_employee_ids = {r.get("employee_id") for r in open_rows}
    rows = [r for r in rows if r["id"] not in open_employee_ids][:50]
    projects = await _project_names(ctx, [r.get("project_id") for r in rows])
    items = [{
        "id": r["id"],
        "employee_number": r.get("employee_number"),
        "full_name": r.get("full_name"),
        "job_title": r.get("job_title"),
        "join_date": r.get("join_date"),
        "project_id": r.get("project_id"),
        "project_name": projects.get(r.get("project_id")),
    } for r in rows]
    return {"items": items, "total": len(items)}


@router.get("")
async def list_cases(
    case_state: Optional[str] = Query(None, alias="state"),
    q: Optional[str] = None,
    ctx: AuthContext = Depends(_view),
):
    scope = await dscope.get_scope(ctx)
    flt = dscope.with_scope(
        {"company_id": ctx.company_id, "status": {"$ne": "deleted"}}, scope, field_name="employee_id")
    if case_state:
        if case_state not in CASE_STATES:
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Status kasus tidak dikenal.")
        flt["case_state"] = case_state
    rows = serialize_list(await ctx.tdb.exit_clearances.find(flt, NO_ID)
                          .sort("request_date", -1).to_list(2000))
    needle = (q or "").strip().lower()
    if needle:
        rows = [
            r for r in rows
            if needle in (r.get("employee_name") or "").lower()
            or needle in (r.get("employee_number") or "").lower()
            or needle in (r.get("case_number") or "").lower()
        ]
    items_by_case = await _items_for(ctx, [r["id"] for r in rows])
    outstanding = await _outstanding_counts(ctx, [r.get("employee_id") for r in rows])
    projects = await _project_names(ctx, [r.get("project_id") for r in rows])
    items = [
        _case_public(
            r,
            progress=_progress(items_by_case.get(r["id"], [])),
            outstanding=outstanding.get(r.get("employee_id"), 0),
            project_name=projects.get(r.get("project_id")),
        )
        for r in rows
    ]
    return {"items": items, "total": len(items)}


@router.get("/history")
async def exit_history(
    case_state: Optional[str] = Query(None, alias="state"),
    project_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    q: Optional[str] = None,
    ctx: AuthContext = Depends(_view),
):
    """Histori kasus exit yang sudah Selesai atau Dibatalkan (kasus berjalan tidak termasuk)."""
    scope = await dscope.get_scope(ctx)
    flt = dscope.with_scope(
        {"company_id": ctx.company_id, "status": {"$ne": "deleted"},
         "case_state": {"$in": list(CLOSED_STATES)}}, scope, field_name="employee_id")
    if case_state:
        state = case_state.strip().upper()
        if state not in CLOSED_STATES:
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                       "Histori hanya memuat kasus Selesai atau Dibatalkan.")
        flt["case_state"] = state
    if project_id:
        flt["project_id"] = project_id
    if date_from:
        flt["last_working_date"] = {"$gte": _parse_date(date_from, "Tanggal mulai").isoformat()}
    if date_to:
        flt["last_working_date"] = {**(flt.get("last_working_date") or {}),
                                    "$lte": _parse_date(date_to, "Tanggal selesai").isoformat()}
    rows = serialize_list(await ctx.tdb.exit_clearances.find(flt, NO_ID)
                          .sort("last_working_date", -1).to_list(5000))
    needle = (q or "").strip().lower()
    if needle:
        rows = [
            r for r in rows
            if needle in (r.get("employee_name") or "").lower()
            or needle in (r.get("employee_number") or "").lower()
            or needle in (r.get("case_number") or "").lower()
        ]
    items_by_case = await _items_for(ctx, [r["id"] for r in rows])
    outstanding = await _outstanding_counts(ctx, [r.get("employee_id") for r in rows])
    projects = await _project_names(ctx, [r.get("project_id") for r in rows])
    items = [
        _case_public(
            r,
            progress=_progress(items_by_case.get(r["id"], [])),
            outstanding=outstanding.get(r.get("employee_id"), 0),
            project_name=projects.get(r.get("project_id")),
        )
        for r in rows
    ]
    counts = {COMPLETED: 0, CANCELLED: 0}
    for row in rows:
        state = row.get("case_state")
        if state in counts:
            counts[state] += 1
    return {"items": items, "total": len(items), "counts": counts}


@router.get("/{clearance_id}")
async def case_detail(clearance_id: str, ctx: AuthContext = Depends(_view)):
    row = await _case_or_404(ctx, clearance_id)
    employee = await ctx.tdb.employees.find_one(
        {"company_id": ctx.company_id, "id": row.get("employee_id")}, NO_ID) or {}
    status_row = {}
    if employee.get("current_employee_status_id"):
        status_row = await ctx.tdb.employee_business_statuses.find_one(
            {"company_id": ctx.company_id, "id": employee["current_employee_status_id"]}, NO_ID) or {}
    projects = await _project_names(ctx, [row.get("project_id")])
    items = (await _items_for(ctx, [clearance_id])).get(clearance_id, [])
    outstanding = await _outstanding_list(ctx, row.get("employee_id"))
    employee_public = {
        "id": employee.get("id"),
        "employee_number": employee.get("employee_number"),
        "full_name": employee.get("full_name"),
        "job_title": employee.get("job_title"),
        "join_date": employee.get("join_date"),
        "status": employee.get("status"),
        "status_name": status_row.get("name"),
        "status_category": status_row.get("system_category"),
        "project_name": projects.get(employee.get("project_id")),
    }
    return {
        "item": _case_public(row, progress=_progress(items),
                             outstanding=len(outstanding), project_name=projects.get(row.get("project_id"))),
        "items": [_item_public(i) for i in items],
        "employee": employee_public,
        "outstanding_assets": outstanding,
        "categories": [{"value": k, "label": v} for k, v in CATEGORY_LABELS.items()],
    }


# --------------------------------------------------------------------------- write

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_case(payload: Dict[str, Any] = Body(...), ctx: AuthContext = Depends(_create)):
    employee_id = str(payload.get("employee_id") or "").strip()
    if not employee_id:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Karyawan wajib dipilih.")
    employee = await dscope.get_scoped_employee(ctx, employee_id)
    if employee.get("status") != "active":
        raise _err(status.HTTP_409_CONFLICT, "Exit clearance hanya dapat dibuat untuk karyawan aktif.")
    exit_type = str(payload.get("exit_type") or "").strip().upper()
    if exit_type not in EXIT_TYPES:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tipe keluar tidak dikenal.")
    reason = str(payload.get("reason") or "").strip()
    if len(reason) < 3:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Alasan keluar wajib diisi (minimal 3 karakter).")
    if len(reason) > 255:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Alasan keluar maksimal 255 karakter.")
    notes = str(payload.get("notes") or "").strip() or None
    last_working = _parse_date(payload.get("last_working_date"), "Tanggal kerja terakhir")
    join_date = str(employee.get("join_date") or "").strip()
    if join_date and last_working.isoformat() < join_date:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                   "Tanggal kerja terakhir tidak boleh sebelum tanggal bergabung karyawan.")
    existing = await ctx.tdb.exit_clearances.count_documents({
        "company_id": ctx.company_id, "employee_id": employee_id,
        "case_state": {"$in": list(OPEN_STATES)}, "status": {"$ne": "deleted"},
    })
    if existing:
        raise _err(status.HTTP_409_CONFLICT,
                   "Karyawan ini masih memiliki kasus exit clearance yang belum selesai/dibatalkan.")

    today = today_local()
    clearance_id = new_id()
    ts = now()
    prepared = await doc_sequence.prepare(
        ctx.company_id, SEQ, when=date.fromisoformat(today), actor_id=ctx.user_id)
    exists = await _taken_number(ctx)
    case_doc = {
        "id": clearance_id, "company_id": ctx.company_id, "status": "active",
        "employee_id": employee_id,
        "employee_number": employee.get("employee_number"),
        "employee_name": employee.get("full_name"),
        "project_id": employee.get("project_id"),
        "exit_type": exit_type, "request_date": today, "last_working_date": last_working.isoformat(),
        "reason": reason, "notes": notes, "case_state": DRAFT,
        "row_version": 1, **audit_fields(ctx.user_id, creating=True),
    }
    item_docs = [{
        "id": new_id(), "company_id": ctx.company_id, "status": "active", "clearance_id": clearance_id,
        "line_no": idx, "category": category, "name": name, "item_state": PENDING,
        "note": None, "decided_at": None, "decided_by": None,
        "created_at": ts, "updated_at": ts, "created_by": ctx.user_id, "updated_by": ctx.user_id,
    } for idx, (category, name) in enumerate(DEFAULT_ITEMS, start=1)]

    async with transaction() as tx:
        case_doc["case_number"] = await doc_sequence.allocate_in_tx(
            tx, prepared, exists=exists)
        await tx.insert("exit_clearances", case_doc)
        await tx.insert_many("exit_clearance_items", item_docs)

    created = await ctx.tdb.exit_clearances.find_one(
        {"company_id": ctx.company_id, "id": clearance_id}, NO_ID)
    await log_action(ctx, "create", "exit_clearance", clearance_id, created.get("case_number"),
                     after={"employee_id": employee_id, "exit_type": exit_type,
                            "last_working_date": last_working.isoformat()},
                     notes="Kasus exit clearance dibuat")
    return {
        "message": f"Kasus exit clearance {created.get('case_number')} dibuat.",
        "item": _case_public(created),
    }


@router.patch("/{clearance_id}")
async def update_case(clearance_id: str, payload: Dict[str, Any] = Body(...),
                      ctx: AuthContext = Depends(_edit)):
    row = await _case_or_404(ctx, clearance_id)
    if row.get("case_state") != DRAFT:
        raise _err(status.HTTP_409_CONFLICT, "Hanya kasus berstatus Draft yang dapat diubah.")
    changes: Dict[str, Any] = {}
    if payload.get("exit_type") is not None:
        exit_type = str(payload.get("exit_type") or "").strip().upper()
        if exit_type not in EXIT_TYPES:
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tipe keluar tidak dikenal.")
        changes["exit_type"] = exit_type
    if payload.get("last_working_date") is not None:
        last_working = _parse_date(payload.get("last_working_date"), "Tanggal kerja terakhir")
        employee = await ctx.tdb.employees.find_one(
            {"company_id": ctx.company_id, "id": row.get("employee_id")}, NO_ID) or {}
        join_date = str(employee.get("join_date") or "").strip()
        if join_date and last_working.isoformat() < join_date:
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                       "Tanggal kerja terakhir tidak boleh sebelum tanggal bergabung karyawan.")
        changes["last_working_date"] = last_working.isoformat()
    if payload.get("reason") is not None:
        reason = str(payload.get("reason") or "").strip()
        if len(reason) < 3:
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Alasan keluar wajib diisi (minimal 3 karakter).")
        changes["reason"] = reason[:255]
    if "notes" in payload:
        changes["notes"] = str(payload.get("notes") or "").strip() or None
    if not changes:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tidak ada perubahan yang dikirim.")
    changes.update({"row_version": int(row.get("row_version") or 0) + 1,
                    **audit_fields(ctx.user_id, creating=False)})
    await ctx.tdb.exit_clearances.update_one(
        {"company_id": ctx.company_id, "id": clearance_id}, {"$set": changes})
    updated = await ctx.tdb.exit_clearances.find_one(
        {"company_id": ctx.company_id, "id": clearance_id}, NO_ID)
    await log_action(ctx, "update", "exit_clearance", clearance_id, row.get("case_number"),
                     before={"exit_type": row.get("exit_type"),
                             "last_working_date": row.get("last_working_date")},
                     after={k: changes.get(k) for k in
                            ("exit_type", "last_working_date", "reason", "notes") if k in changes},
                     notes="Kasus exit clearance diubah")
    return {"message": "Kasus exit clearance disimpan.", "item": _case_public(updated)}


@router.patch("/{clearance_id}/items/{item_id}")
async def update_item(clearance_id: str, item_id: str, payload: Dict[str, Any] = Body(...),
                      ctx: AuthContext = Depends(_edit)):
    row = await _case_or_404(ctx, clearance_id)
    if row.get("case_state") not in OPEN_STATES:
        raise _err(status.HTTP_409_CONFLICT, "Checklist pada kasus yang sudah selesai/dibatalkan tidak dapat diubah.")
    item = await ctx.tdb.exit_clearance_items.find_one(
        {"company_id": ctx.company_id, "clearance_id": clearance_id, "id": item_id}, NO_ID)
    if not item:
        raise _err(status.HTTP_404_NOT_FOUND, "Item checklist tidak ditemukan.")
    new_state = str(payload.get("item_state") or "").strip().upper()
    if new_state not in ITEM_STATES:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Status item harus PENDING, DONE, atau NA.")
    note = str(payload.get("note") or "").strip() or None
    if new_state == NA and not note:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Catatan wajib diisi bila item ditandai Tidak Berlaku.")
    if item.get("category") == "GA" and new_state == DONE:
        outstanding = await _outstanding_counts(ctx, [row.get("employee_id")])
        count = outstanding.get(row.get("employee_id"), 0)
        if count:
            raise _err(status.HTTP_409_CONFLICT, OUTSTANDING_MSG.format(count=count))
    ts = now()
    await ctx.tdb.exit_clearance_items.update_one(
        {"company_id": ctx.company_id, "id": item_id},
        {"$set": {
            "item_state": new_state, "note": note,
            "decided_at": ts if new_state != PENDING else None,
            "decided_by": ctx.user_id if new_state != PENDING else None,
            "updated_at": ts, "updated_by": ctx.user_id,
        }})
    updated = await ctx.tdb.exit_clearance_items.find_one(
        {"company_id": ctx.company_id, "id": item_id}, NO_ID)
    await log_action(ctx, "update", "exit_clearance", clearance_id, row.get("case_number"),
                     before={"item": item.get("name"), "state": item.get("item_state")},
                     after={"item": item.get("name"), "state": new_state},
                     notes="Item checklist exit clearance diperbarui")
    return {"message": "Item checklist diperbarui.", "item": _item_public(updated)}


@router.post("/{clearance_id}/submit")
async def submit_case(clearance_id: str, ctx: AuthContext = Depends(_edit)):
    row = await _case_or_404(ctx, clearance_id)
    if row.get("case_state") != DRAFT:
        raise _err(status.HTTP_409_CONFLICT, "Hanya kasus Draft yang dapat diajukan.")
    items = (await _items_for(ctx, [clearance_id])).get(clearance_id, [])
    if any(i.get("item_state") == PENDING for i in items):
        raise _err(status.HTTP_409_CONFLICT,
                   "Semua item checklist harus Diputuskan (Selesai/Tidak Berlaku) sebelum diajukan.")
    ts = now()
    await ctx.tdb.exit_clearances.update_one(
        {"company_id": ctx.company_id, "id": clearance_id},
        {"$set": {"case_state": PENDING_APPROVAL, "submitted_at": ts, "submitted_by": ctx.user_id,
                  "row_version": int(row.get("row_version") or 0) + 1,
                  **audit_fields(ctx.user_id, creating=False)}})
    await log_action(ctx, "submit", "exit_clearance", clearance_id, row.get("case_number"),
                     before={"state": DRAFT}, after={"state": PENDING_APPROVAL},
                     notes="Exit clearance diajukan untuk persetujuan")
    return {"message": "Exit clearance diajukan untuk persetujuan."}


@router.post("/{clearance_id}/approve")
async def approve_case(clearance_id: str, payload: Dict[str, Any] = Body(default={}),
                       ctx: AuthContext = Depends(_approve)):
    """Persetujuan final: menutup kasus DAN mengubah Status Karyawan menjadi TIDAK AKTIF.

    Sengaja hanya boleh pada/setelah tanggal kerja terakhir. Tidak ada penjadwal latar belakang pada CP1,
    sehingga status tidak berubah lebih awal.
    """
    row = await _case_or_404(ctx, clearance_id)
    if row.get("case_state") != PENDING_APPROVAL:
        raise _err(status.HTTP_409_CONFLICT, "Hanya kasus Menunggu Persetujuan yang dapat disetujui.")
    today = today_local()
    if str(row.get("last_working_date") or "") > today:
        raise _err(status.HTTP_409_CONFLICT,
                   "Exit clearance baru dapat disetujui pada/setelah tanggal kerja terakhir "
                   f"({row.get('last_working_date')}).")
    items = (await _items_for(ctx, [clearance_id])).get(clearance_id, [])
    if any(i.get("item_state") not in (DONE, NA) for i in items):
        raise _err(status.HTTP_409_CONFLICT,
                   "Semua item checklist harus Selesai/Tidak Berlaku sebelum persetujuan final.")
    outstanding = await _outstanding_counts(ctx, [row.get("employee_id")])
    count = outstanding.get(row.get("employee_id"), 0)
    if count:
        raise _err(status.HTTP_409_CONFLICT, OUTSTANDING_MSG.format(count=count))

    employee_id = row.get("employee_id")
    employee = await ctx.tdb.employees.find_one(
        {"company_id": ctx.company_id, "id": employee_id}, NO_ID)
    if not employee:
        raise _err(status.HTTP_404_NOT_FOUND, "Karyawan pada kasus ini tidak ditemukan.")
    if employee.get("status") != "active":
        raise _err(status.HTTP_409_CONFLICT, "Karyawan sudah tidak aktif; kasus tidak dapat diselesaikan.")
    inactive_status = await default_status(ctx.company_id, "INACTIVE")
    if not inactive_status:
        raise _err(status.HTTP_409_CONFLICT,
                   "Status karyawan kategori TIDAK AKTIF belum tersedia. Atur di Master Status Karyawan.")
    previous = None
    if employee.get("current_employee_status_id"):
        previous = await ctx.tdb.employee_business_statuses.find_one(
            {"company_id": ctx.company_id, "id": employee["current_employee_status_id"]}, NO_ID)
    legacy_before = employee.get("status")
    legacy_after = legacy_for(inactive_status["system_category"])
    note = str(payload.get("note") or "").strip() or None
    actor_name = ctx.user.get("full_name") if ctx.user else None
    hist = history_doc(
        ctx.company_id, employee_id, inactive_status, previous,
        effective_date=row.get("last_working_date"),
        reason=f"Exit clearance {row.get('case_number')}", notes=note, source="SYSTEM",
        actor_id=ctx.user_id, actor_name=actor_name,
        legacy_before=legacy_before, legacy_after=legacy_after,
    )
    audit = build_audit_entry(
        ctx, "approve", "exit_clearance", clearance_id, row.get("case_number"),
        before={"state": PENDING_APPROVAL}, after={"state": COMPLETED,
                                                   "employee_status": inactive_status.get("name")},
        notes=f"Exit clearance {row.get('case_number')} disetujui; karyawan menjadi "
              f"{inactive_status.get('name')} efektif {row.get('last_working_date')}.",
    )
    ts = now()
    async with transaction() as tx:
        locked_case = await tx.select_one_for_update(
            "exit_clearances", {"company_id": ctx.company_id, "id": clearance_id})
        if not locked_case or locked_case.get("case_state") != PENDING_APPROVAL:
            raise _err(status.HTTP_409_CONFLICT,
                       "Status kasus baru saja berubah oleh proses lain. Muat ulang lalu coba lagi.")
        locked_emp = await tx.select_one_for_update(
            "employees", {"company_id": ctx.company_id, "id": employee_id})
        if not locked_emp or locked_emp.get("status") != legacy_before \
                or locked_emp.get("current_employee_status_id") != employee.get("current_employee_status_id"):
            raise _err(status.HTTP_409_CONFLICT,
                       "Status karyawan baru saja diubah oleh proses lain. Muat ulang lalu coba lagi.")
        await tx.update("employees", {"company_id": ctx.company_id, "id": employee_id},
                        {"current_employee_status_id": inactive_status["id"], "status": legacy_after,
                         "updated_at": ts, "updated_by": ctx.user_id})
        await tx.insert("employee_status_history", hist)
        await tx.update("exit_clearances", {"company_id": ctx.company_id, "id": clearance_id},
                        {"case_state": COMPLETED, "decided_at": ts, "decided_by": ctx.user_id,
                         "decision_note": note, "completed_at": ts, "completed_by": ctx.user_id,
                         "row_version": int(row.get("row_version") or 0) + 1,
                         "updated_at": ts, "updated_by": ctx.user_id})
        await tx.insert("audit_logs", audit)
    await completeness.safe_refresh(ctx.company_id, [employee_id], "exit_clearance", ctx.user_id)
    return {
        "message": f"Exit clearance {row.get('case_number')} selesai. {employee.get('full_name')} "
                   f"menjadi {inactive_status.get('name')}.",
        "employee_status": inactive_status.get("name"),
        "employee_status_category": inactive_status.get("system_category"),
        "legacy_status": legacy_after,
    }


@router.post("/{clearance_id}/cancel")
async def cancel_case(clearance_id: str, payload: Dict[str, Any] = Body(...),
                      ctx: AuthContext = Depends(_delete)):
    row = await _case_or_404(ctx, clearance_id)
    if row.get("case_state") == COMPLETED:
        raise _err(status.HTTP_409_CONFLICT, "Kasus yang sudah selesai tidak dapat dibatalkan.")
    if row.get("case_state") == CANCELLED:
        raise _err(status.HTTP_409_CONFLICT, "Kasus sudah dibatalkan.")
    reason = str(payload.get("reason") or "").strip()
    if len(reason) < 3:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Alasan pembatalan wajib diisi (minimal 3 karakter).")
    ts = now()
    await ctx.tdb.exit_clearances.update_one(
        {"company_id": ctx.company_id, "id": clearance_id},
        {"$set": {"case_state": CANCELLED, "cancelled_at": ts, "cancelled_by": ctx.user_id,
                  "cancel_reason": reason[:255],
                  "row_version": int(row.get("row_version") or 0) + 1,
                  **audit_fields(ctx.user_id, creating=False)}})
    await log_action(ctx, "cancel", "exit_clearance", clearance_id, row.get("case_number"),
                     before={"state": row.get("case_state")}, after={"state": CANCELLED},
                     notes=f"Exit clearance dibatalkan: {reason}")
    return {"message": "Kasus exit clearance dibatalkan."}
