"""M0009 - Employee Form Builder (Enhancement 01G). Additive only, tenant-safe, runs once.

1. Ledger `schema_migrations`; if m0009 is already recorded -> SKIP.
2. New tables (tenant-scoped `company_id`): `employee_form_sections`, `employee_form_fields`,
   `employee_form_field_scopes`, `employee_custom_field_values`.
3. New NULL column `employee_submission_files.field_key` (attachments for custom file fields).
4. New permission `employee_form:configure`, granted to `tenant_admin` and `hr_admin` (company_owner = wildcard).
No JSON column on `employees`, no DROP/RENAME, no UPDATE of business data, no change to 01F rules/snapshots.
Run: python -m migrations.m0009_employee_form_builder [--apply]
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

MIGRATION_ID = "m0009_employee_form_builder"
TABLES = ["employee_form_sections", "employee_form_fields", "employee_form_field_scopes", "employee_custom_field_values"]
NEW_COLUMNS = [("employee_submission_files", "field_key", "VARCHAR(64)")]
NEW_PERMISSION = "employee_form:configure"
RESOURCE, ACTION = "employee_form", "configure"
GRANT_ROLES = ["tenant_admin", "hr_admin"]
LEDGER_DDL = ("CREATE TABLE IF NOT EXISTS schema_migrations (id VARCHAR(100) NOT NULL PRIMARY KEY,"
              " applied_at DATETIME(6) NOT NULL, summary JSON NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")


async def run(apply: bool) -> dict:
    import sqlalchemy as sa
    from app.core.config import settings
    from app.core.db import audit_fields, close_db, get_db, get_engine, get_table, new_id, now
    from app.core.rbac import ACTION_LABELS, RESOURCES

    if settings.READ_ONLY:
        raise SystemExit("READ_ONLY aktif - migrasi dibatalkan.")
    engine = get_engine()
    plan, created_tables, added_cols, grants = [], [], [], []
    try:
        async with engine.begin() as conn:
            if apply:
                await conn.execute(sa.text(LEDGER_DDL))
            exists = (await conn.execute(sa.text(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'schema_migrations'"))).scalar()
            if exists:
                done = (await conn.execute(sa.text("SELECT applied_at FROM schema_migrations WHERE id = :id"), {"id": MIGRATION_ID})).scalar()
                if done:
                    return {"migration": MIGRATION_ID, "mode": "SKIP", "changes": [f"(sudah diterapkan pada {done} - dilewati)"]}
            for name in TABLES:
                present = (await conn.execute(sa.text(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = :t"),
                    {"t": name})).scalar()
                if present:
                    plan.append(f"(tabel {name} sudah ada)")
                    continue
                plan.append(f"CREATE TABLE {name}")
                created_tables.append(name)
                if apply:
                    await conn.run_sync(lambda c, n=name: get_table(n).create(c, checkfirst=True))
            for table, col, ddl in NEW_COLUMNS:
                present = (await conn.execute(sa.text(
                    "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"),
                    {"t": table, "c": col})).scalar()
                if present:
                    plan.append(f"(kolom {table}.{col} sudah ada)")
                    continue
                plan.append(f"ALTER TABLE {table} ADD COLUMN {col} {ddl} NULL")
                added_cols.append(f"{table}.{col}")
                if apply:
                    await conn.execute(sa.text(f"ALTER TABLE `{table}` ADD COLUMN `{col}` {ddl} NULL"))

        db = get_db()
        label, module_key, _actions = RESOURCES[RESOURCE]
        if not await db.permissions.count_documents({"key": NEW_PERMISSION}):
            plan.append(f"INSERT permissions {NEW_PERMISSION}")
            if apply:
                await db.permissions.insert_one({
                    "id": new_id(), "company_id": None, "status": "active", "key": NEW_PERMISSION,
                    "resource": RESOURCE, "resource_label": label, "action": ACTION,
                    "action_label": ACTION_LABELS[ACTION], "module_key": module_key,
                    "name": f"{ACTION_LABELS[ACTION]} {label}", **audit_fields(None, creating=True),
                })
        for role in GRANT_ROLES:
            if not await db.roles.count_documents({"key": role}):
                plan.append(f"(role {role} tidak ada - grant dilewati)")
                continue
            if not await db.role_permissions.count_documents({"role_key": role, "permission_key": NEW_PERMISSION}):
                plan.append(f"GRANT {NEW_PERMISSION} -> {role}")
                grants.append(role)
                if apply:
                    await db.role_permissions.insert_one({
                        "id": new_id(), "company_id": None, "role_key": role, "permission_key": NEW_PERMISSION,
                        "status": "active", **audit_fields(None, creating=True),
                    })
        summary = {"tables_created": created_tables, "columns_added": added_cols, "permission": NEW_PERMISSION,
                   "granted_roles": grants}
        if apply:
            async with engine.begin() as conn:
                await conn.execute(sa.text("INSERT INTO schema_migrations (id, applied_at, summary) VALUES (:id, :ts, :s)"),
                                   {"id": MIGRATION_ID, "ts": now().replace(tzinfo=None), "s": json.dumps(summary)})
        plan.append(f"RECORD schema_migrations {MIGRATION_ID}")
        return {"migration": MIGRATION_ID, "mode": "APPLY" if apply else "DRY-RUN", "changes": plan}
    finally:
        await close_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true")
    result = asyncio.run(run(parser.parse_args().apply))
    print(result["migration"], result["mode"])
    for line in result["changes"]:
        print(" -", line)
