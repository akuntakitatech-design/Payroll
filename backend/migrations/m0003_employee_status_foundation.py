"""M0003 - Employee Status Foundation (Upgrade 01B). Additive, tenant-safe, sekali jalan.

Perubahan:
1. Ledger `schema_migrations` (dibuat bila belum ada). Jika m0003 sudah tercatat,
   migrasi di-SKIP seluruhnya (berjalan sekali).
2. Skema additive (idempotent; startup schema-sync existing juga dapat membuatnya
   kosong lebih dulu - migrasi hanya memastikan):
   - tabel `employee_business_statuses` (master status bisnis per tenant)
   - tabel `employee_status_history` (riwayat, append-only)
   - kolom nullable `employees.current_employee_status_id` + index
3. Permission baru `employee_status:manage` & `employee_status:change`, diberikan ke
   role tenant_admin dan hr_admin (company_owner = wildcard, sudah tercakup).
   Grant hanya ditambahkan bila belum ada (tidak menimpa perubahan manual).
4. Per tenant: 3 status default (AKTIF/STANDBY/TIDAK_AKTIF) bila belum ada.
5. Backfill karyawan yang belum punya status bisnis:
   active -> Aktif; inactive -> Tidak Aktif; archived/deleted -> Tidak Aktif TANPA
   mengubah `employees.status` (arsip tetap arsip, terhapus tetap terhapus).
   Riwayat awal source=LEGACY_BASELINE, effective_date NULL (tidak mengarang tanggal).
   Nilai legacy lain -> tidak dipetakan, dilaporkan.

Tidak ada DROP/RENAME/ubah tipe. `employment_status_id` tidak disentuh.
Jalankan: python -m migrations.m0003_employee_status_foundation [--apply]
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

MIGRATION_ID = "m0003_employee_status_foundation"
NEW_TABLES = ["employee_business_statuses", "employee_status_history"]
NEW_PERMISSIONS = ["employee_status:manage", "employee_status:change"]
GRANT_ROLES = ["tenant_admin", "hr_admin"]

LEDGER_DDL = (
    "CREATE TABLE IF NOT EXISTS schema_migrations ("
    " id VARCHAR(100) NOT NULL PRIMARY KEY,"
    " applied_at DATETIME(6) NOT NULL,"
    " summary JSON NULL"
    ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
)


async def run(apply: bool) -> dict:
    import sqlalchemy as sa
    from app.core.config import settings
    from app.core.db import audit_fields, close_db, get_db, get_engine, get_table, new_id, now
    from app.core.employee_status import backfill_company, ensure_default_statuses
    from app.core.rbac import ACTION_LABELS, RESOURCES

    if settings.READ_ONLY:
        raise SystemExit("READ_ONLY aktif - migrasi dibatalkan.")
    db = get_db()
    engine = get_engine()
    plan = []
    summary: dict = {}
    try:
        # 1) Ledger
        async with engine.begin() as conn:
            exists = (await conn.execute(sa.text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = 'schema_migrations'"))).scalar()
            if exists:
                done = (await conn.execute(sa.text(
                    "SELECT applied_at FROM schema_migrations WHERE id = :id"), {"id": MIGRATION_ID})).scalar()
                if done:
                    return {"migration": MIGRATION_ID, "mode": "SKIP",
                            "changes": [f"(sudah diterapkan pada {done} - dilewati)"]}
            else:
                plan.append("CREATE TABLE schema_migrations (ledger)")
                if apply:
                    await conn.execute(sa.text(LEDGER_DDL))

        # 2) Skema additive
        async with engine.begin() as conn:
            for name in NEW_TABLES:
                present = (await conn.execute(sa.text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = DATABASE() AND table_name = :t"), {"t": name})).scalar()
                if not present:
                    plan.append(f"CREATE TABLE {name}")
                    if apply:
                        await conn.run_sync(lambda c, n=name: get_table(n).create(c, checkfirst=True))
            col = (await conn.execute(sa.text(
                "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() "
                "AND table_name = 'employees' AND column_name = 'current_employee_status_id'"))).scalar()
            if not col:
                plan.append("ALTER TABLE employees ADD COLUMN current_employee_status_id VARCHAR(36) NULL")
                if apply:
                    await conn.execute(sa.text(
                        "ALTER TABLE employees ADD COLUMN IF NOT EXISTS current_employee_status_id VARCHAR(36) NULL"))
            idx = (await conn.execute(sa.text(
                "SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() "
                "AND table_name = 'employees' AND index_name = 'ix_employee_current_status'"))).scalar()
            if not idx:
                plan.append("CREATE INDEX ix_employee_current_status ON employees(company_id, current_employee_status_id)")
                if apply:
                    await conn.execute(sa.text(
                        "CREATE INDEX IF NOT EXISTS ix_employee_current_status "
                        "ON employees (company_id, current_employee_status_id)"))

        if not apply and plan and any(p.startswith(("CREATE TABLE employee", "ALTER TABLE employees")) for p in plan):
            plan.append("(data step dihitung setelah skema tersedia - jalankan --apply)")
            return {"migration": MIGRATION_ID, "mode": "DRY-RUN", "changes": plan}

        # 3) Permission + grant
        label, module_key, _actions = RESOURCES["employee_status"]
        for key in NEW_PERMISSIONS:
            action = key.split(":", 1)[1]
            if not await db.permissions.count_documents({"key": key}):
                plan.append(f"INSERT permissions {key}")
                if apply:
                    await db.permissions.insert_one({
                        "id": new_id(), "company_id": None, "status": "active", "key": key,
                        "resource": "employee_status", "resource_label": label, "action": action,
                        "action_label": ACTION_LABELS[action], "module_key": module_key,
                        "name": f"{ACTION_LABELS[action]} {label}", **audit_fields(None, creating=True),
                    })
        for role in GRANT_ROLES:
            if not await db.roles.count_documents({"key": role}):
                plan.append(f"(role {role} tidak ada - grant dilewati)")
                continue
            for key in NEW_PERMISSIONS:
                if not await db.role_permissions.count_documents({"role_key": role, "permission_key": key}):
                    plan.append(f"GRANT {key} -> {role}")
                    if apply:
                        await db.role_permissions.insert_one({
                            "id": new_id(), "company_id": None, "role_key": role, "permission_key": key,
                            "status": "active", **audit_fields(None, creating=True),
                        })

        # 4) + 5) Default status + backfill per tenant
        companies = await db.companies.find({}, {"_id": 0, "id": 1, "code": 1}).to_list(10000)
        tenants = []
        for comp in companies:
            created = await ensure_default_statuses(comp["id"], None, apply=apply)
            if created:
                plan.append(f"INSERT default status {comp.get('code')}: {', '.join(created)}")
            if apply:
                result = await backfill_company(comp["id"], apply=True)
            else:
                # dry-run: hitung kandidat backfill tanpa menulis
                rows = await db.employees.find(
                    {"company_id": comp["id"], "current_employee_status_id": None},
                    {"_id": 0, "status": 1}).to_list(100000)
                counts: dict = {}
                for r in rows:
                    counts[r.get("status")] = counts.get(r.get("status"), 0) + 1
                result = {"backfilled_by_legacy": counts, "unmapped": []}
            if result["backfilled_by_legacy"] or result["unmapped"]:
                plan.append(f"BACKFILL {comp.get('code')}: {result['backfilled_by_legacy']}"
                            + (f" | TIDAK DIPETAKAN: {len(result['unmapped'])}" if result["unmapped"] else ""))
            tenants.append({"code": comp.get("code"), "defaults_created": created, **{
                k: result[k] for k in ("backfilled_by_legacy", "unmapped")}})
        summary = {"tenants": tenants}

        # Ledger: tandai selesai
        if apply:
            async with engine.begin() as conn:
                await conn.execute(sa.text(
                    "INSERT INTO schema_migrations (id, applied_at, summary) VALUES (:id, :ts, :s)"),
                    {"id": MIGRATION_ID, "ts": now().replace(tzinfo=None), "s": json.dumps(summary, default=str)})
            plan.append(f"RECORD schema_migrations {MIGRATION_ID}")
    finally:
        await close_db()
    return {"migration": MIGRATION_ID, "mode": "APPLY" if apply else "DRY-RUN",
            "changes": plan or ["(tidak ada perubahan)"], "summary": summary}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Terapkan perubahan (default dry-run).")
    result = asyncio.run(run(parser.parse_args().apply))
    print(result["migration"], result["mode"])
    for line in result["changes"]:
        print(" -", line)
