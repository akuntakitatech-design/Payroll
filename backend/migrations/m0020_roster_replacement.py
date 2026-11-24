"""m0020_roster_replacement - Modul 4 Blueprint HRGA: Penugasan Karyawan Pengganti.

ADITIF & IDEMPOTEN (pola identik m0019). Tidak mengubah migrasi sebelumnya.
  * ALTER roster_leave_plans: replacement_employee_id, replacement_assigned_at,
    replacement_assigned_by, replacement_assigned_by_name.
  * TIDAK ada backfill: rencana lama otomatis berarti "belum ada pengganti".
  * TIDAK ada perubahan RBAC: penugasan memakai permission `roster:edit` yang sudah ada.

Pemakaian (dari folder backend):
    python -m migrations.m0020_roster_replacement                       # dry-run
    python -m migrations.m0020_roster_replacement --apply --confirm-db hris_dev
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

from migrations.m0012_asset_management import LEDGER_DDL, guard  # noqa: E402  (ledger & guard identik)

MIGRATION_ID = "m0020_roster_replacement"
NEW_COLUMNS = {
    "roster_leave_plans": {
        "replacement_employee_id": "VARCHAR(36)",
        "replacement_assigned_at": "DATETIME(6)",
        "replacement_assigned_by": "VARCHAR(36)",
        "replacement_assigned_by_name": "VARCHAR(255)",
    },
}
REQUIRES = ()


async def run(apply: bool, confirm_db=None) -> dict:
    import sqlalchemy as sa
    from app.core.db import close_db, get_engine, now

    db_name = guard(confirm_db)
    engine = get_engine()
    plan, added_cols = [], []
    try:
        async with engine.begin() as conn:
            if apply:
                await conn.execute(sa.text(LEDGER_DDL))
            if (await conn.execute(sa.text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()"
                                           " AND table_name = 'schema_migrations'"))).scalar():
                done = (await conn.execute(sa.text("SELECT applied_at FROM schema_migrations WHERE id = :id"),
                                           {"id": MIGRATION_ID})).scalar()
                if done:
                    return {"migration": MIGRATION_ID, "db": db_name, "mode": "SKIP",
                            "changes": [f"(sudah diterapkan pada {done} - dilewati)"]}
            for req in REQUIRES:
                if not (await conn.execute(sa.text("SELECT applied_at FROM schema_migrations WHERE id = :id"),
                                           {"id": req})).scalar():
                    raise SystemExit(f"DITOLAK: {req} belum diterapkan pada database ini.")

            async def _scalar(sql, **p):
                return (await conn.execute(sa.text(sql), p)).scalar()

            for table, cols in NEW_COLUMNS.items():
                for col, ddl in cols.items():
                    if await _scalar("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE()"
                                     " AND table_name = :t AND column_name = :c", t=table, c=col):
                        continue
                    plan.append(f"ALTER TABLE {table} ADD COLUMN {col} {ddl} NULL")
                    added_cols.append(f"{table}.{col}")
                    if apply:
                        await conn.execute(sa.text(f"ALTER TABLE `{table}` ADD COLUMN `{col}` {ddl} NULL DEFAULT NULL"))

        summary = {"columns_added": added_cols}
        if apply:
            async with engine.begin() as conn:
                await conn.execute(sa.text("INSERT INTO schema_migrations (id, applied_at, summary) VALUES (:id, :ts, :s)"),
                                   {"id": MIGRATION_ID, "ts": now().replace(tzinfo=None), "s": json.dumps(summary)})
        plan.append(f"RECORD schema_migrations {MIGRATION_ID}")
        return {"migration": MIGRATION_ID, "db": db_name, "mode": "APPLY" if apply else "DRY-RUN",
                "changes": plan, "summary": summary}
    finally:
        await close_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-db", default=None)
    args = parser.parse_args()
    result = asyncio.run(run(args.apply, args.confirm_db))
    print(result["migration"], result["mode"], "db=" + result["db"])
    for line in result["changes"]:
        print(" -", line)
