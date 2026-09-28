"""M0011 - Role & Data Scope (Upgrade 01I). Additive only, tenant-safe, runs once.

1. Ledger `schema_migrations`; if m0011 is already recorded -> SKIP (no duplicate rows).
2. New tables (CREATE IF NOT EXISTS via metadata):
   - `user_data_scopes`      : one row per (company_id, user_id); mode ALL_TENANT | SELECTED_PROJECTS.
   - `user_data_scope_items` : project items bound to the parent scope (scope_id) + the same company_id.
3. New indexes (only if missing):
   - employees(company_id, project_id)                                   -> ix_employee_project
   - employee_assignments(company_id, assignment_status, project_id, employee_id) -> ix_employee_assignment_project
4. Default scope ALL_TENANT for every EXISTING active membership (user_company_roles with a company_id),
   one row per (company_id, user_id). Never cross-company, never for global-only (platform) memberships.
No DROP/RENAME, no change to employees / employee_assignments / roles / permissions data.
Run: python -m migrations.m0011_role_data_scope [--apply]
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

MIGRATION_ID = "m0011_role_data_scope"
NEW_TABLES = ["user_data_scopes", "user_data_scope_items"]
NEW_INDEXES = [
    ("employees", "ix_employee_project"),
    ("employee_assignments", "ix_employee_assignment_project"),
]
LEDGER_DDL = ("CREATE TABLE IF NOT EXISTS schema_migrations (id VARCHAR(100) NOT NULL PRIMARY KEY,"
              " applied_at DATETIME(6) NOT NULL, summary JSON NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")


async def run(apply: bool) -> dict:
    import sqlalchemy as sa
    from app.core.config import settings
    from app.core.db import close_db, get_engine, get_table, new_id, now

    if settings.READ_ONLY:
        raise SystemExit("READ_ONLY aktif - migrasi dibatalkan.")
    engine = get_engine()
    plan, created_tables, created_idx = [], [], []
    defaults = 0
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

            async def _table_exists(name: str) -> bool:
                return bool((await conn.execute(sa.text(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = :t"),
                    {"t": name})).scalar())

            for name in NEW_TABLES:
                if await _table_exists(name):
                    plan.append(f"(tabel {name} sudah ada)")
                else:
                    plan.append(f"CREATE TABLE {name}")
                    created_tables.append(name)
                    if apply:
                        tbl = get_table(name)
                        await conn.run_sync(lambda sc, t=tbl: t.create(sc, checkfirst=True))

            for table_name, idx_name in NEW_INDEXES:
                present = (await conn.execute(sa.text(
                    "SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = :t AND index_name = :i"),
                    {"t": table_name, "i": idx_name})).scalar()
                if present:
                    plan.append(f"(index {table_name}.{idx_name} sudah ada)")
                    continue
                idx = next(i for i in get_table(table_name).indexes if i.name == idx_name)
                plan.append(f"CREATE INDEX {idx_name} ON {table_name} ({', '.join(c.name for c in idx.columns)})")
                created_idx.append(f"{table_name}.{idx_name}")
                if apply:
                    await conn.run_sync(lambda sc, i=idx: i.create(sc))

            # Default ALL_TENANT: per (company_id, user_id) dari keanggotaan tenant yang aktif.
            members = (await conn.execute(sa.text(
                "SELECT DISTINCT ucr.company_id, ucr.user_id FROM user_company_roles ucr"
                " JOIN companies c ON c.id = ucr.company_id"
                " WHERE ucr.company_id IS NOT NULL AND ucr.user_id IS NOT NULL AND ucr.status = 'active'"))).fetchall()
            have = set()
            if await _table_exists("user_data_scopes"):
                have = {(r[0], r[1]) for r in (await conn.execute(sa.text(
                    "SELECT company_id, user_id FROM user_data_scopes"))).fetchall()}
            todo = [(cid, uid) for cid, uid in members if (cid, uid) not in have]
            plan.append(f"INSERT user_data_scopes ALL_TENANT x{len(todo)} (keanggotaan aktif: {len(members)}, sudah ada: {len(members) - len(todo)})")
            if apply and todo:
                ts = now().replace(tzinfo=None)
                scopes = get_table("user_data_scopes")
                await conn.execute(sa.insert(scopes), [{
                    "id": new_id(), "company_id": cid, "user_id": uid, "mode": "ALL_TENANT", "status": "active",
                    "notes": "Default m0011 (akses existing dipertahankan)", "created_at": ts, "updated_at": ts,
                    "created_by": None, "updated_by": None,
                } for cid, uid in todo])
            defaults = len(todo)

        summary = {"tables_created": created_tables, "indexes_created": created_idx, "default_all_tenant": defaults}
        if apply:
            async with engine.begin() as conn:
                await conn.execute(sa.text("INSERT INTO schema_migrations (id, applied_at, summary) VALUES (:id, :ts, :s)"),
                                   {"id": MIGRATION_ID, "ts": now().replace(tzinfo=None), "s": json.dumps(summary)})
        plan.append(f"RECORD schema_migrations {MIGRATION_ID}")
        return {"migration": MIGRATION_ID, "mode": "APPLY" if apply else "DRY-RUN", "changes": plan, "summary": summary}
    finally:
        await close_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true")
    result = asyncio.run(run(parser.parse_args().apply))
    print(result["migration"], result["mode"])
    for line in result["changes"]:
        print(" -", line)
