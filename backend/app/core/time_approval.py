"""LAPISAN EKSEKUSI APPROVAL BERSAMA untuk Time Management.

Satu engine dipakai oleh EMPAT jenis dokumen:
  * ``attendance_location``      - Absensi di luar radius
  * ``attendance_correction``    - Koreksi Absensi
  * ``leave``                    - Cuti / Izin / Sakit
  * ``overtime``                 - Lembur

Prinsip:
  * REUSE konfigurasi existing ``approval_workflows`` + ``approval_steps``
    (tidak ada tabel konfigurasi baru, tidak ada engine terpisah per modul).
  * SNAPSHOT langkah workflow saat submit ke ``time_approvals`` sehingga
    perubahan konfigurasi setelahnya tidak mengubah riwayat.
  * SEQUENTIAL: langkah ke-N hanya dapat diputuskan bila langkah sebelumnya
    sudah disetujui.
  * VALIDASI APPROVER di server (role / user / jabatan / atasan langsung).
  * FAIL-CLOSED: bila workflow wajib belum dikonfigurasi, pengajuan DITOLAK.
    Tidak ada fallback diam-diam ke HR Manager.
  * HISTORY dipertahankan: keputusan lama tidak pernah dihapus.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status

from .db import ASCENDING, NO_ID, audit_fields, get_db, new_id, now
from .repo import TenantRepository

# document_kind -> metadata (label Bahasa Indonesia untuk UI)
DOCUMENT_KINDS: Dict[str, Dict[str, str]] = {
    "attendance_location": {
        "label": "Persetujuan Absensi Di Luar Radius",
        "workflow_kind": "attendance",
        "module": "attendance",
        "resource": "attendance",
    },
    "attendance_correction": {
        "label": "Persetujuan Koreksi Absensi",
        "workflow_kind": "attendance_correction",
        "module": "attendance",
        "resource": "attendance",
    },
    "leave": {
        "label": "Persetujuan Cuti / Izin / Sakit",
        "workflow_kind": "leave",
        "module": "leave_overtime",
        "resource": "leave",
    },
    "overtime": {
        "label": "Persetujuan Lembur",
        "workflow_kind": "overtime",
        "module": "leave_overtime",
        "resource": "leave",
    },
}

DECISIONS: Dict[str, Dict[str, str]] = {
    "pending": {"label": "Menunggu Persetujuan", "tone": "warning"},
    "approved": {"label": "Disetujui", "tone": "success"},
    "rejected": {"label": "Ditolak", "tone": "danger"},
    "skipped": {"label": "Tidak Diproses", "tone": "neutral"},
}

SUPPORTED_APPROVER_TYPES = {"role", "user", "position", "supervisor"}


class WorkflowNotConfigured(HTTPException):
    def __init__(self, document_kind: str):
        meta = DOCUMENT_KINDS.get(document_kind, {})
        super().__init__(
            status.HTTP_409_CONFLICT,
            f"{meta.get('label', 'Alur persetujuan')} belum dikonfigurasi. "
            "Buka menu Alur Persetujuan, buat alur untuk jenis dokumen terkait beserta "
            "tahap penyetujunya, lalu ulangi pengajuan.",
        )


# --------------------------------------------------------------------------
# Resolusi workflow existing
# --------------------------------------------------------------------------
async def resolve_workflow(
    company_id: str, document_kind: str
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    meta = DOCUMENT_KINDS.get(document_kind)
    if not meta:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Jenis dokumen persetujuan tidak dikenal.")
    db = get_db()
    workflows = await db.approval_workflows.find(
        {"company_id": company_id, "document_kind": meta["workflow_kind"], "status": "active"}, NO_ID
    ).sort([("is_default", -1), ("created_at", ASCENDING)]).to_list(20)
    if not workflows:
        return None, []
    wf = workflows[0]
    steps = await db.approval_steps.find(
        {"company_id": company_id, "workflow_id": wf["id"], "status": {"$ne": "deleted"}}, NO_ID
    ).sort("step_order", ASCENDING).to_list(50)
    return wf, steps


async def _label_for_step(company_id: str, step: Dict[str, Any]) -> str:
    db = get_db()
    kind = step.get("approver_type")
    if kind == "role":
        role = await db.roles.find_one({"key": step.get("approver_role_key")}, NO_ID)
        return f"Peran: {role['name']}" if role else f"Peran: {step.get('approver_role_key')}"
    if kind == "user":
        user = await db.users.find_one({"id": step.get("approver_user_id")}, NO_ID)
        return f"Pengguna: {user['full_name']}" if user else "Pengguna tertentu"
    if kind == "position":
        pos = await db.positions.find_one(
            {"company_id": company_id, "id": step.get("approver_position_id")}, NO_ID
        )
        return f"Jabatan: {pos['name']}" if pos else "Jabatan tertentu"
    if kind == "supervisor":
        return "Atasan Langsung Pemohon"
    return "Penyetuju"


async def workflow_state(company_id: str, document_kind: str) -> Dict[str, Any]:
    """Untuk UI: apakah alur persetujuan siap dipakai?"""
    wf, steps = await resolve_workflow(company_id, document_kind)
    reasons: List[str] = []
    if not wf:
        reasons.append(
            f"Alur persetujuan untuk {DOCUMENT_KINDS[document_kind]['label']} belum dibuat."
        )
    elif not steps:
        reasons.append("Alur persetujuan sudah ada tetapi belum memiliki tahap penyetuju.")
    else:
        bad = [s for s in steps if s.get("approver_type") not in SUPPORTED_APPROVER_TYPES]
        if bad:
            reasons.append("Ada tahap dengan jenis penyetuju yang belum didukung.")
    labels = []
    if wf and steps:
        labels = [
            {
                "step_order": s.get("step_order"),
                "name": s.get("name"),
                "approver_label": await _label_for_step(company_id, s),
                "is_mandatory": bool(s.get("is_mandatory", True)),
            }
            for s in steps
        ]
    return {
        "document_kind": document_kind,
        "document_label": DOCUMENT_KINDS[document_kind]["label"],
        "ready": not reasons,
        "reasons": reasons,
        "workflow": {"id": wf["id"], "code": wf.get("code"), "name": wf.get("name")} if wf else None,
        "steps": labels,
        "config_route": "/setup/approval-workflows",
    }


# --------------------------------------------------------------------------
# Validasi approver
# --------------------------------------------------------------------------
async def _my_position_ids(company_id: str, user_id: str) -> List[str]:
    db = get_db()
    rows = await db.employees.find(
        {"company_id": company_id, "user_id": user_id, "status": {"$ne": "deleted"}}, NO_ID
    ).to_list(10)
    return [r["position_id"] for r in rows if r.get("position_id")]


async def resolve_supervisor_user_id(company_id: str, employee_id: Optional[str]) -> Optional[str]:
    """Atasan langsung pemohon: kepala departemen karyawan, lalu kepala divisi."""
    if not employee_id:
        return None
    db = get_db()
    emp = await db.employees.find_one({"company_id": company_id, "id": employee_id}, NO_ID)
    if not emp:
        return None
    if emp.get("department_id"):
        dept = await db.departments.find_one({"company_id": company_id, "id": emp["department_id"]}, NO_ID)
        if dept and dept.get("head_user_id"):
            return dept["head_user_id"]
    if emp.get("division_id"):
        div = await db.divisions.find_one({"company_id": company_id, "id": emp["division_id"]}, NO_ID)
        if div and div.get("head_user_id"):
            return div["head_user_id"]
    return None


async def is_step_approver(ctx, row: Dict[str, Any], my_positions: Optional[List[str]] = None) -> bool:
    kind = row.get("approver_type")
    if kind == "user":
        return row.get("approver_user_id") == ctx.user_id
    if kind == "role":
        return row.get("approver_role_key") in set(ctx.role_keys)
    if kind == "position":
        if my_positions is None:
            my_positions = await _my_position_ids(ctx.company_id, ctx.user_id)
        return row.get("approver_position_id") in set(my_positions)
    if kind == "supervisor":
        return row.get("approver_user_id") == ctx.user_id
    return False


# --------------------------------------------------------------------------
# Submit (snapshot)
# --------------------------------------------------------------------------
async def ensure_ready(ctx, document_kind: str, employee_id: Optional[str] = None) -> None:
    """Validasi awal (tanpa menulis) bahwa pengajuan approval untuk dokumen ini
    dapat dibuat: workflow tersedia, jenis penyetuju didukung, atasan langsung
    dapat ditentukan. Dipakai sebelum transaksi absensi disimpan agar tidak ada
    baris 'menunggu persetujuan' yang menggantung tanpa alur approval."""
    wf, steps = await resolve_workflow(ctx.company_id, document_kind)
    if not wf or not steps:
        raise WorkflowNotConfigured(document_kind)
    for step in steps:
        if step.get("approver_type") not in SUPPORTED_APPROVER_TYPES:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Tahap '{step.get('name')}' memakai jenis penyetuju yang belum didukung Time Management.",
            )
    if any(s.get("approver_type") == "supervisor" for s in steps):
        if not await resolve_supervisor_user_id(ctx.company_id, employee_id):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Alur persetujuan memerlukan Atasan Langsung, tetapi atasan karyawan belum dapat "
                "ditentukan. Tetapkan Kepala Departemen/Divisi pada Master Organisasi terlebih dahulu.",
            )


async def next_round(company_id: str, document_kind: str, record_id: str) -> int:
    """Nomor putaran approval berikutnya untuk satu record (histori putaran lama tetap tersimpan)."""
    rows = await rows_for(company_id, document_kind, record_id)
    return max([int(r.get("approval_round") or 1) for r in rows], default=0) + 1


async def submit(
    ctx,
    document_kind: str,
    record_id: str,
    record_label: str,
    employee_id: Optional[str] = None,
    approval_round: int = 1,
) -> List[Dict[str, Any]]:
    """Buat snapshot langkah approval. FAIL-CLOSED bila workflow belum siap."""
    wf, steps = await resolve_workflow(ctx.company_id, document_kind)
    if not wf or not steps:
        raise WorkflowNotConfigured(document_kind)

    db = get_db()
    existing = await db.time_approvals.count_documents({
        "company_id": ctx.company_id, "document_kind": document_kind,
        "record_id": record_id, "approval_round": approval_round,
    })
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Pengajuan persetujuan untuk data ini sudah dibuat.")

    supervisor_id: Optional[str] = None
    if any(s.get("approver_type") == "supervisor" for s in steps):
        supervisor_id = await resolve_supervisor_user_id(ctx.company_id, employee_id)
        if not supervisor_id:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Alur persetujuan memerlukan Atasan Langsung, tetapi atasan karyawan belum dapat "
                "ditentukan. Tetapkan Kepala Departemen/Divisi pada Master Organisasi terlebih dahulu.",
            )

    repo = TenantRepository("time_approvals", ctx.company_id)
    rows: List[Dict[str, Any]] = []
    for step in steps:
        if step.get("approver_type") not in SUPPORTED_APPROVER_TYPES:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Tahap '{step.get('name')}' memakai jenis penyetuju yang belum didukung Time Management.",
            )
        approver_user_id = step.get("approver_user_id")
        if step.get("approver_type") == "supervisor":
            approver_user_id = supervisor_id
        rows.append({
            "id": new_id(),
            "company_id": ctx.company_id,
            "document_kind": document_kind,
            "record_id": record_id,
            "record_label": record_label,
            "employee_id": employee_id,
            "approval_round": approval_round,
            "workflow_id": wf["id"],
            "workflow_code": wf.get("code"),
            "workflow_name": wf.get("name"),
            "workflow_step_id": step["id"],
            "step_order": int(step.get("step_order") or 0),
            "step_name": step.get("name"),
            "approver_type": step.get("approver_type"),
            "approver_role_key": step.get("approver_role_key"),
            "approver_user_id": approver_user_id,
            "approver_position_id": step.get("approver_position_id"),
            "approver_label": await _label_for_step(ctx.company_id, step),
            "is_mandatory": bool(step.get("is_mandatory", True)),
            "decision": "pending",
            "submitted_by": ctx.user_id,
            "submitted_at": now(),
            "status": "active",
            **audit_fields(ctx.user_id),
        })
    await repo.coll.insert_many([dict(r) for r in rows])
    return rows


# --------------------------------------------------------------------------
# Status & keputusan
# --------------------------------------------------------------------------
async def rows_for(company_id: str, document_kind: str, record_id: str) -> List[Dict[str, Any]]:
    db = get_db()
    return await db.time_approvals.find(
        {"company_id": company_id, "document_kind": document_kind, "record_id": record_id}, NO_ID
    ).sort([("approval_round", ASCENDING), ("step_order", ASCENDING)]).to_list(200)


async def state_for(ctx, document_kind: str, record_id: str, approval_round: Optional[int] = None) -> Dict[str, Any]:
    rows = await rows_for(ctx.company_id, document_kind, record_id)
    if approval_round is None:
        approval_round = max([int(r.get("approval_round") or 1) for r in rows], default=1)
    current = [r for r in rows if int(r.get("approval_round") or 1) == approval_round]
    my_positions = await _my_position_ids(ctx.company_id, ctx.user_id)

    items: List[Dict[str, Any]] = []
    prev_ok = True
    for row in current:
        can_act = (
            prev_ok
            and row.get("decision") == "pending"
            and await is_step_approver(ctx, row, my_positions)
        )
        items.append({
            **row,
            "decision_label": DECISIONS.get(row.get("decision") or "pending", {}).get("label", "-"),
            "decision_tone": DECISIONS.get(row.get("decision") or "pending", {}).get("tone", "neutral"),
            "can_decide": bool(can_act),
            "is_current_step": bool(prev_ok and row.get("decision") == "pending"),
        })
        if row.get("decision") != "approved":
            prev_ok = False

    overall = "pending"
    if any(r.get("decision") == "rejected" for r in current):
        overall = "rejected"
    elif current and all(r.get("decision") == "approved" for r in current):
        overall = "approved"
    elif not current:
        overall = "not_submitted"

    return {
        "document_kind": document_kind,
        "record_id": record_id,
        "approval_round": approval_round,
        "overall": overall,
        "overall_label": DECISIONS.get(overall, {}).get("label", "Belum Diajukan"),
        "steps": items,
        "history": [
            {
                **r,
                "decision_label": DECISIONS.get(r.get("decision") or "pending", {}).get("label", "-"),
            }
            for r in rows
            if int(r.get("approval_round") or 1) != approval_round
        ],
    }


async def decide(
    ctx, approval_id: str, decision: str, notes: Optional[str] = None
) -> Dict[str, Any]:
    """Putuskan satu tahap. Sequential + concurrency-safe + preserve history."""
    if decision not in ("approved", "rejected"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Keputusan harus 'Disetujui' atau 'Ditolak'.")

    repo = TenantRepository("time_approvals", ctx.company_id)
    row = await repo.get(approval_id)  # 404 bila lintas perusahaan
    if row.get("decision") != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "Tahap persetujuan ini sudah diputuskan.")

    siblings = await rows_for(ctx.company_id, row["document_kind"], row["record_id"])
    same_round = [
        r for r in siblings if int(r.get("approval_round") or 1) == int(row.get("approval_round") or 1)
    ]
    for prev in same_round:
        if int(prev.get("step_order") or 0) < int(row.get("step_order") or 0) and prev.get("decision") != "approved":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Tahap '{prev.get('step_name')}' harus disetujui terlebih dahulu (persetujuan berjenjang).",
            )

    if not await is_step_approver(ctx, row):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Anda bukan penyetuju untuk tahap ini ({row.get('approver_label')}).",
        )

    db = get_db()
    updated = await db.time_approvals.find_one_and_update(
        {"company_id": ctx.company_id, "id": approval_id, "decision": "pending"},
        {"$set": {
            "decision": decision,
            "decided_by": ctx.user_id,
            "decided_by_name": ctx.user.get("full_name"),
            "decided_at": now(),
            "notes": notes,
            "updated_at": now(),
            "updated_by": ctx.user_id,
        }},
        return_document=True,
    )
    if not updated:
        raise HTTPException(status.HTTP_409_CONFLICT, "Tahap persetujuan ini sudah diputuskan oleh proses lain.")

    if decision == "rejected":
        # Tahap setelahnya tidak diproses, tetapi riwayatnya tetap tersimpan.
        await db.time_approvals.update_many(
            {
                "company_id": ctx.company_id,
                "document_kind": row["document_kind"],
                "record_id": row["record_id"],
                "approval_round": row.get("approval_round"),
                "decision": "pending",
            },
            {"$set": {"decision": "skipped", "updated_at": now(), "updated_by": ctx.user_id}},
        )

    state = await state_for(ctx, row["document_kind"], row["record_id"], int(row.get("approval_round") or 1))
    return {"row": updated, "state": state}


async def pending_for_me(ctx, document_kinds: Optional[List[str]] = None, limit: int = 200) -> List[Dict[str, Any]]:
    """Daftar tahap yang MENUNGGU keputusan saya (sequential-aware)."""
    db = get_db()
    query: Dict[str, Any] = {"company_id": ctx.company_id, "decision": "pending"}
    if document_kinds:
        query["document_kind"] = {"$in": document_kinds}
    rows = await db.time_approvals.find(query, NO_ID).sort("submitted_at", ASCENDING).to_list(1000)
    if not rows:
        return []

    my_positions = await _my_position_ids(ctx.company_id, ctx.user_id)
    # Kelompokkan per (jenis, record, ronde) untuk memeriksa urutan berjenjang.
    grouped: Dict[Tuple[str, str, int], List[Dict[str, Any]]] = {}
    keys = {(r["document_kind"], r["record_id"], int(r.get("approval_round") or 1)) for r in rows}
    for key in keys:
        grouped[key] = [
            r for r in await rows_for(ctx.company_id, key[0], key[1])
            if int(r.get("approval_round") or 1) == key[2]
        ]

    out: List[Dict[str, Any]] = []
    for row in rows:
        key = (row["document_kind"], row["record_id"], int(row.get("approval_round") or 1))
        ordered = sorted(grouped.get(key, []), key=lambda r: int(r.get("step_order") or 0))
        blocked = any(
            int(p.get("step_order") or 0) < int(row.get("step_order") or 0) and p.get("decision") != "approved"
            for p in ordered
        )
        if blocked:
            continue
        if not await is_step_approver(ctx, row, my_positions):
            continue
        out.append(row)
        if len(out) >= limit:
            break
    return out
