"""Dashboard aggregation.

Rule followed here: only REAL data is shown. Modules that are not implemented yet
return a `placeholder` state instead of invented numbers.

Catatan kinerja
---------------
Database produksi diakses lewat jaringan publik dengan latensi ~240 ms per
perjalanan. Versi lama menjalankan ~25 query secara BERURUTAN sehingga satu
permintaan dashboard bisa memakan 25-30 detik. Seluruh query yang tidak saling
bergantung kini dijalankan BERSAMAAN memakai ``asyncio.gather``, sehingga
totalnya mendekati satu kali latensi, bukan penjumlahan semuanya.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends

from ..core.db import ASCENDING, DESCENDING, NO_ID, get_db, serialize_list
from ..core.deps import AuthContext, get_auth
from ..core.policy import resolve_config
from ..core.rbac import MODULES

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

# Master data yang dihitung dengan filter status aktif yang sama.
ACTIVE_COUNT_COLLECTIONS = [
    "branches",
    "work_locations",
    "departments",
    "divisions",
    "positions",
    "job_grades",
    "cost_centers",
    "projects",
    "document_types",
    "employment_statuses",
    "contract_types",
    "certification_types",
    "approval_workflows",
]


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

    # ------------------------------------------------------------------
    # Gelombang 1: seluruh query yang tidak saling bergantung, dijalankan
    # bersamaan agar latensi jaringan tidak berakumulasi.
    # ------------------------------------------------------------------
    active_count_tasks = [
        db[coll].count_documents({"company_id": cid, "status": "active"})
        for coll in ACTIVE_COUNT_COLLECTIONS
    ]

    other_tasks = [
        db.documents.count_documents({"company_id": cid, "is_deleted": {"$ne": True}}),
        db.employees.count_documents({"company_id": cid, "status": "active"}),
        db.employee_contracts.count_documents(
            {"company_id": cid, "status": {"$nin": ["deleted", "archived"]}}
        ),
        db.employee_certifications.count_documents(
            {"company_id": cid, "status": {"$nin": ["deleted", "archived"]}}
        ),
        db.company_modules.count_documents({"company_id": cid, "is_active": True}),
        db.config_overrides.count_documents({"company_id": cid, "status": "active"}),
        db.user_company_roles.find({"company_id": cid, "status": "active"}, NO_ID).to_list(5000),
        db.documents.find(
            {"company_id": cid, "is_deleted": {"$ne": True}, "expiry_date": {"$nin": [None, ""]}},
            NO_ID,
        ).to_list(2000),
        db.employee_contracts.find(
            {
                "company_id": cid,
                "status": {"$nin": ["deleted", "archived"]},
                "end_date": {"$nin": [None, ""]},
            },
            NO_ID,
        ).to_list(5000),
        db.employee_certifications.find(
            {
                "company_id": cid,
                "status": {"$nin": ["deleted", "archived"]},
                "expiry_date": {"$nin": [None, ""]},
            },
            NO_ID,
        ).to_list(5000),
        db.projects.find(
            {"company_id": cid, "status": "active", "end_date": {"$nin": [None, ""]}}, NO_ID
        ).to_list(1000),
        db.company_modules.find({"company_id": cid}, NO_ID).to_list(200),
        db.modules.find({}, NO_ID).sort("sort_order", ASCENDING).to_list(200),
        db.audit_logs.find({"company_id": cid}, NO_ID)
        .sort("created_at", DESCENDING)
        .limit(8)
        .to_list(8),
        db.employees.find({"company_id": cid, "status": "active"}, NO_ID).to_list(10000),
        db.departments.find({"company_id": cid, "status": "active"}, NO_ID)
        .sort("name", ASCENDING)
        .to_list(500),
    ]

    gathered = await asyncio.gather(*active_count_tasks, *other_tasks)

    counts: Dict[str, int] = {}
    for idx, coll in enumerate(ACTIVE_COUNT_COLLECTIONS):
        counts[coll] = gathered[idx]

    offset = len(ACTIVE_COUNT_COLLECTIONS)
    (
        documents_count,
        employees_count,
        contracts_count,
        certifications_count,
        active_modules,
        policy_overrides,
        member_rows,
        doc_rows,
        contract_rows_raw,
        cert_rows_raw,
        project_rows_raw,
        module_rows,
        catalog_raw,
        recent_raw,
        employee_rows_raw,
        dept_rows_raw,
    ) = gathered[offset:]

    counts["documents"] = documents_count
    counts["employees"] = employees_count
    counts["contracts"] = contracts_count
    counts["certifications"] = certifications_count
    counts["users"] = len({m["user_id"] for m in member_rows})
    counts["active_modules"] = active_modules
    counts["available_modules"] = len(MODULES)
    counts["policy_overrides"] = policy_overrides

    docs = serialize_list(doc_rows)
    contract_rows = serialize_list(contract_rows_raw)
    cert_rows = serialize_list(cert_rows_raw)
    projects = serialize_list(project_rows_raw)
    catalog = serialize_list(catalog_raw)
    recent = serialize_list(recent_raw)
    employee_rows = serialize_list(employee_rows_raw)
    dept_rows = serialize_list(dept_rows_raw)

    # ------------------------------------------------------------------
    # Gelombang 2: query yang bergantung pada hasil gelombang 1.
    # ------------------------------------------------------------------
    user_ids = list({m["user_id"] for m in member_rows})
    inactive_users = 0
    if user_ids:
        inactive_users = await db.users.count_documents(
            {"id": {"$in": user_ids}, "status": {"$ne": "active"}}
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
    active_keys = {m["module_key"] for m in module_rows if m.get("is_active")} | {"hr_core"}

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

    # ---------------- Distribusi karyawan per departemen (data nyata) -------
    dept_index = {d["id"]: d for d in dept_rows}
    dist_map: Dict[str, int] = {}
    unassigned = 0
    for emp in employee_rows:
        did = emp.get("department_id")
        if did and did in dept_index:
            dist_map[did] = dist_map.get(did, 0) + 1
        else:
            unassigned += 1

    department_distribution = [
        {
            "id": d["id"],
            "name": d.get("name"),
            "code": d.get("code"),
            "count": dist_map.get(d["id"], 0),
        }
        for d in dept_rows
    ]
    department_distribution.sort(key=lambda x: (-x["count"], str(x.get("name") or "")))
    if unassigned:
        department_distribution.append(
            {"id": None, "name": "Tanpa departemen", "code": None, "count": unassigned}
        )

    # Karyawan baru bergabung dalam 30 hari terakhir
    joined_last_30d = 0
    for emp in employee_rows:
        joined = _parse_date(emp.get("join_date"))
        if joined and 0 <= (today - joined).days <= 30:
            joined_last_30d += 1

    # ---------------- KPI utama ---------------------------------------------
    # Catatan kejujuran data: modul Absensi belum memiliki tabel/transaksi,
    # sehingga "Hadir Hari Ini" dikembalikan sebagai unavailable, BUKAN angka karangan.
    attendance_active = "attendance" in active_keys
    kpi = {
        "employees_active": {
            "available": True,
            "value": counts["employees"],
            "meta": f"{len(dept_rows)} departemen · {counts['branches']} cabang",
            "link": "/employees",
            "extra": {"joined_last_30d": joined_last_30d},
        },
        "attendance_today": {
            "available": False,
            "value": None,
            "module_key": "attendance",
            "module_active": attendance_active,
            "reason": (
                "Modul Absensi belum memiliki data kehadiran. Fungsi absensi harian "
                "akan tersedia pada tahap pengembangan berikutnya."
            ),
            "meta": "Modul aktif, data kehadiran belum tersedia"
            if attendance_active
            else "Modul Absensi belum aktif",
            "action_label": "Lihat Aktivasi Modul",
            "link": "/setup/modules",
        },
        "contracts_ending": {
            "available": True,
            "value": len(contracts_expiring),
            "expired": len(contracts_expired),
            "horizon_days": horizon_days,
            "meta": (
                f"{len(contracts_expired)} sudah berakhir"
                if contracts_expired
                else f"Dalam {horizon_days} hari ke depan"
            ),
            "severity": "critical" if contracts_expired else ("warning" if contracts_expiring else "normal"),
            "link": "/reminders?kind=contract",
        },
        "modules_active": {
            "available": True,
            "value": active_modules,
            "total": counts["available_modules"],
            "meta": f"dari {counts['available_modules']} modul tersedia",
            "link": "/setup/modules",
        },
    }

    # ---------------- Ringkasan SDM Hari Ini (data nyata) -------------------
    hr_today = {
        "as_of": today.isoformat(),
        "rows": [
            {
                "key": "employees_active",
                "label": "Karyawan aktif",
                "value": counts["employees"],
                "meta": f"{joined_last_30d} bergabung 30 hari terakhir",
                "tone": "normal",
                "link": "/employees",
            },
            {
                "key": "contracts_total",
                "label": "Kontrak kerja tercatat",
                "value": counts["contracts"],
                "meta": f"{len(contracts_expiring)} berakhir ≤{horizon_days} hari",
                "tone": "warning" if contracts_expiring else "normal",
                "link": "/contracts",
            },
            {
                "key": "contracts_expired",
                "label": "Kontrak sudah berakhir",
                "value": len(contracts_expired),
                "meta": "Perlu diperbarui atau diarsipkan" if contracts_expired else "Semua kontrak masih berlaku",
                "tone": "critical" if contracts_expired else "success",
                "link": "/reminders?kind=contract&state=expired",
            },
            {
                "key": "certifications_attention",
                "label": "Sertifikasi perlu perhatian",
                "value": len(certs_attention),
                "meta": f"Dari {counts['certifications']} sertifikasi tercatat",
                "tone": "warning" if certs_attention else "success",
                "link": "/reminders?kind=certification",
            },
            {
                "key": "documents",
                "label": "Dokumen aktif",
                "value": counts["documents"],
                "meta": f"{len(expiring)} menjelang berakhir · {len(expired)} kedaluwarsa",
                "tone": "critical" if expired else ("warning" if expiring else "normal"),
                "link": "/documents",
            },
            {
                "key": "users",
                "label": "Pengguna sistem",
                "value": counts["users"],
                "meta": f"{counts['policy_overrides']} kebijakan khusus aktif",
                "tone": "normal",
                "link": "/users",
            },
        ],
    }

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
        "kpi": kpi,
        "department_distribution": department_distribution,
        "hr_today": hr_today,
        "pending_approvals": {
            "state": "placeholder",
            "count": 0,
            "note": "Belum ada transaksi yang membutuhkan persetujuan. Kotak persetujuan akan terisi saat modul transaksi aktif.",
        },
        "horizon_days": horizon_days,
    }
