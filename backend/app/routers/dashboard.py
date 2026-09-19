"""Dashboard aggregation.

Rule followed here: only REAL data is shown. Modules that are not implemented yet
return a `placeholder` state instead of invented numbers.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pymongo import ASCENDING, DESCENDING

from ..core.db import NO_ID, get_db, serialize_list
from ..core.deps import AuthContext, get_auth
from ..core.policy import resolve_config
from ..core.rbac import MODULES

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _parse_date(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value)[:19])
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


@router.get("/summary")
async def summary(ctx: AuthContext = Depends(get_auth)):
    db = get_db()
    cid = ctx.company_id
    today = datetime.now(timezone.utc)

    reminder = await resolve_config(cid, "contract.expiry_reminder_days")
    horizon_days = int(reminder.get("value") or 30)
    horizon = today + timedelta(days=horizon_days)

    counts: Dict[str, int] = {}
    for coll, key in [
        ("branches", "branches"),
        ("work_locations", "work_locations"),
        ("departments", "departments"),
        ("divisions", "divisions"),
        ("positions", "positions"),
        ("job_grades", "job_grades"),
        ("cost_centers", "cost_centers"),
        ("projects", "projects"),
        ("document_types", "document_types"),
        ("employment_statuses", "employment_statuses"),
        ("contract_types", "contract_types"),
        ("certification_types", "certification_types"),
        ("approval_workflows", "approval_workflows"),
    ]:
        counts[key] = await db[coll].count_documents({"company_id": cid, "status": "active"})

    counts["documents"] = await db.documents.count_documents(
        {"company_id": cid, "is_deleted": {"$ne": True}}
    )
    counts["employees"] = await db.employees.count_documents({"company_id": cid, "status": "active"})
    counts["contracts"] = await db.employee_contracts.count_documents(
        {"company_id": cid, "status": {"$nin": ["deleted", "archived"]}}
    )
    counts["certifications"] = await db.employee_certifications.count_documents(
        {"company_id": cid, "status": {"$nin": ["deleted", "archived"]}}
    )
    member_rows = await db.user_company_roles.find(
        {"company_id": cid, "status": "active"}, NO_ID
    ).to_list(5000)
    counts["users"] = len({m["user_id"] for m in member_rows})
    active_modules = await db.company_modules.count_documents({"company_id": cid, "is_active": True})
    counts["active_modules"] = active_modules
    counts["available_modules"] = len(MODULES)
    counts["policy_overrides"] = await db.config_overrides.count_documents(
        {"company_id": cid, "status": "active"}
    )

    # ---------------- Perlu Tindakan (real, actionable, no fake data) ----------
    attention: List[Dict[str, Any]] = []

    setup_missing = [
        ("branches", "Cabang", "/setup/branches"),
        ("departments", "Departemen", "/setup/departments"),
        ("positions", "Jabatan", "/setup/positions"),
        ("job_grades", "Grade / Level", "/setup/job-grades"),
        ("document_types", "Tipe Dokumen", "/setup/document-types"),
    ]
    for key, label, link in setup_missing:
        if counts.get(key, 0) == 0:
            attention.append(
                {
                    "key": f"setup_{key}",
                    "severity": "warning",
                    "title": f"{label} belum diisi",
                    "description": f"Lengkapi master data {label} agar proses HR berikutnya dapat berjalan otomatis.",
                    "action_label": f"Isi {label}",
                    "action_link": link,
                    "count": None,
                }
            )

    if counts["approval_workflows"] == 0:
        attention.append(
            {
                "key": "setup_approval",
                "severity": "warning",
                "title": "Alur persetujuan belum dikonfigurasi",
                "description": "Tentukan siapa yang menyetujui cuti, kontrak, dan permintaan keuangan sebelum modul terkait dipakai.",
                "action_label": "Atur Alur Persetujuan",
                "action_link": "/setup/approval-workflows",
                "count": None,
            }
        )

    docs = serialize_list(
        await db.documents.find(
            {"company_id": cid, "is_deleted": {"$ne": True}, "expiry_date": {"$nin": [None, ""]}}, NO_ID
        ).to_list(2000)
    )
    expired, expiring = [], []
    for d in docs:
        exp = _parse_date(d.get("expiry_date"))
        if not exp:
            continue
        if exp < today:
            expired.append(d)
        elif exp <= horizon:
            expiring.append(d)
    if expired:
        attention.append(
            {
                "key": "documents_expired",
                "severity": "critical",
                "title": f"{len(expired)} dokumen sudah kedaluwarsa",
                "description": "Perbarui dokumen agar kepatuhan perusahaan tetap terjaga.",
                "action_label": "Lihat Dokumen",
                "action_link": "/documents?status=expired",
                "count": len(expired),
            }
        )
    if expiring:
        attention.append(
            {
                "key": "documents_expiring",
                "severity": "warning",
                "title": f"{len(expiring)} dokumen akan kedaluwarsa dalam {horizon_days} hari",
                "description": "Siapkan perpanjangan lebih awal agar tidak mengganggu operasional.",
                "action_label": "Lihat Dokumen",
                "action_link": "/documents",
                "count": len(expiring),
            }
        )

    # ---- Kontrak kerja & sertifikasi karyawan (modul employee_core) ---------
    contract_rows = serialize_list(
        await db.employee_contracts.find(
            {
                "company_id": cid,
                "status": {"$nin": ["deleted", "archived"]},
                "end_date": {"$nin": [None, ""]},
            },
            NO_ID,
        ).to_list(5000)
    )
    contracts_expired = [c for c in contract_rows if (_parse_date(c.get("end_date")) or horizon) < today]
    contracts_expiring = [
        c
        for c in contract_rows
        if (_parse_date(c.get("end_date")) and today <= _parse_date(c.get("end_date")) <= horizon)
    ]
    if contracts_expired:
        attention.append(
            {
                "key": "contracts_expired",
                "severity": "critical",
                "title": f"{len(contracts_expired)} kontrak kerja sudah berakhir",
                "description": "Perbarui atau arsipkan kontrak agar status kepegawaian tetap akurat.",
                "action_label": "Buka Kalender Masa Berlaku",
                "action_link": "/reminders?kind=contract&state=expired",
                "count": len(contracts_expired),
            }
        )
    if contracts_expiring:
        attention.append(
            {
                "key": "contracts_expiring",
                "severity": "warning",
                "title": f"{len(contracts_expiring)} kontrak berakhir dalam {horizon_days} hari",
                "description": "Siapkan perpanjangan atau surat pemberitahuan lebih awal.",
                "action_label": "Buka Kalender Masa Berlaku",
                "action_link": "/reminders?kind=contract",
                "count": len(contracts_expiring),
            }
        )

    cert_rows = serialize_list(
        await db.employee_certifications.find(
            {
                "company_id": cid,
                "status": {"$nin": ["deleted", "archived"]},
                "expiry_date": {"$nin": [None, ""]},
            },
            NO_ID,
        ).to_list(5000)
    )
    certs_attention = [
        c
        for c in cert_rows
        if _parse_date(c.get("expiry_date")) and _parse_date(c.get("expiry_date")) <= horizon
    ]
    if certs_attention:
        attention.append(
            {
                "key": "certifications_attention",
                "severity": "warning",
                "title": f"{len(certs_attention)} sertifikasi karyawan perlu perhatian",
                "description": "Sertifikat yang kedaluwarsa dapat menghambat penempatan karyawan di proyek.",
                "action_label": "Buka Kalender Masa Berlaku",
                "action_link": "/reminders?kind=certification",
                "count": len(certs_attention),
            }
        )

    projects = serialize_list(
        await db.projects.find(
            {"company_id": cid, "status": "active", "end_date": {"$nin": [None, ""]}}, NO_ID
        ).to_list(1000)
    )
    ending_projects = []
    for p in projects:
        end = _parse_date(p.get("end_date"))
        if end and today <= end <= horizon:
            ending_projects.append(
                {"id": p["id"], "code": p.get("code"), "name": p.get("name"), "end_date": p.get("end_date")}
            )
    if ending_projects:
        attention.append(
            {
                "key": "projects_ending",
                "severity": "info",
                "title": f"{len(ending_projects)} proyek berakhir dalam {horizon_days} hari",
                "description": "Rencanakan demobilisasi tim dan perpanjangan kontrak terkait.",
                "action_label": "Lihat Proyek",
                "action_link": "/setup/projects",
                "count": len(ending_projects),
            }
        )

    users_no_role = [m["user_id"] for m in member_rows]
    inactive_users = await db.users.count_documents(
        {"id": {"$in": list(set(users_no_role))}, "status": {"$ne": "active"}}
    )
    if inactive_users:
        attention.append(
            {
                "key": "users_inactive",
                "severity": "info",
                "title": f"{inactive_users} akun pengguna tidak aktif",
                "description": "Tinjau akun yang dinonaktifkan untuk memastikan akses tetap sesuai.",
                "action_label": "Kelola Pengguna",
                "action_link": "/users",
                "count": inactive_users,
            }
        )

    # ---------------- Module cards ------------------------------------------
    module_rows = await db.company_modules.find({"company_id": cid}, NO_ID).to_list(200)
    active_keys = {m["module_key"] for m in module_rows if m.get("is_active")} | {"hr_core"}
    catalog = serialize_list(await db.modules.find({}, NO_ID).sort("sort_order", ASCENDING).to_list(200))

    PLACEHOLDER_COPY = {
        "recruitment": "Pelamar masuk, tahapan seleksi dan persetujuan penawaran kerja.",
        "employee_core": "Data induk karyawan, kontrak kerja dan sertifikasi beserta pengingat masa berlaku.",
        "attendance": "Kehadiran harian, pengecualian absensi, face attendance dan fingerprint.",
        "leave_overtime": "Pengajuan cuti dan lembur yang mengikuti kebijakan tiap unit.",
        "performance": "Siklus penilaian KPI dan kalibrasi kinerja.",
        "payroll": "Perhitungan gaji, BPJS dan PPh 21 beserta status periode payroll.",
        "mobilization": "Penempatan proyek, jadwal mobilisasi dan demobilisasi karyawan.",
        "finance_request": "Kasbon, reimbursement dan permintaan dana dengan persetujuan berjenjang.",
        "accounting": "Jurnal dan integrasi akuntansi opsional.",
    }

    IMPLEMENTED_MODULES = {
        "employee_core": {
            "link": "/employees",
            "note": "Modul aktif dan sudah bisa dipakai: data induk karyawan, kontrak kerja, sertifikasi dan pengingat masa berlaku.",
            "action_label": "Buka Data Karyawan",
        }
    }

    module_cards = []
    for mod in catalog:
        if mod["key"] == "hr_core":
            continue
        is_active = mod["key"] in active_keys
        implemented = IMPLEMENTED_MODULES.get(mod["key"])
        module_cards.append(
            {
                "key": mod["key"],
                "name": mod["name"],
                "icon": mod.get("icon"),
                "is_active": is_active,
                "state": "available" if (implemented and is_active) else "placeholder",
                "link": implemented["link"] if (implemented and is_active) else None,
                "action_label": implemented["action_label"] if (implemented and is_active) else None,
                "description": PLACEHOLDER_COPY.get(mod["key"], mod.get("description")),
                "note": (
                    implemented["note"]
                    if (implemented and is_active)
                    else (
                        "Modul aktif. Fungsi operasional akan tersedia pada tahap pengembangan berikutnya."
                        if is_active
                        else "Modul belum diaktifkan untuk perusahaan ini."
                    )
                ),
            }
        )

    recent = serialize_list(
        await db.audit_logs.find({"company_id": cid}, NO_ID)
        .sort("created_at", DESCENDING)
        .limit(8)
        .to_list(8)
    )

    setup_steps = [
        {"key": "company", "label": "Profil perusahaan", "done": bool(ctx.company.get("address")), "link": "/company"},
        {"key": "branches", "label": "Cabang & lokasi kerja", "done": counts["branches"] > 0, "link": "/setup/branches"},
        {"key": "org", "label": "Struktur organisasi", "done": counts["departments"] > 0 and counts["positions"] > 0, "link": "/setup/departments"},
        {"key": "grades", "label": "Grade & cost center", "done": counts["job_grades"] > 0 and counts["cost_centers"] > 0, "link": "/setup/job-grades"},
        {"key": "documents", "label": "Tipe dokumen", "done": counts["document_types"] > 0, "link": "/setup/document-types"},
        {"key": "approval", "label": "Alur persetujuan", "done": counts["approval_workflows"] > 0, "link": "/setup/approval-workflows"},
        {"key": "users", "label": "Pengguna & hak akses", "done": counts["users"] > 1, "link": "/users"},
        {"key": "modules", "label": "Aktivasi modul", "done": active_modules > 1, "link": "/setup/modules"},
    ]
    done_steps = sum(1 for s in setup_steps if s["done"])

    return {
        "company": {
            "id": ctx.company["id"],
            "name": ctx.company.get("name"),
            "code": ctx.company.get("code"),
            "city": ctx.company.get("city"),
        },
        "greeting_name": ctx.user.get("full_name"),
        "role_keys": ctx.role_keys,
        "counts": counts,
        "attention": attention,
        "module_cards": module_cards,
        "recent_activity": recent,
        "setup_progress": {
            "steps": setup_steps,
            "done": done_steps,
            "total": len(setup_steps),
            "percent": round(done_steps / len(setup_steps) * 100),
        },
        "expiring_documents": [
            {
                "id": d["id"],
                "name": d.get("name"),
                "expiry_date": d.get("expiry_date"),
                "owner_label": d.get("owner_label"),
            }
            for d in sorted(expiring + expired, key=lambda x: str(x.get("expiry_date")))[:6]
        ],
        "ending_projects": ending_projects[:6],
        "pending_approvals": {
            "state": "placeholder",
            "count": 0,
            "note": "Belum ada transaksi yang membutuhkan persetujuan. Kotak persetujuan akan terisi saat modul transaksi aktif.",
        },
        "horizon_days": horizon_days,
    }
