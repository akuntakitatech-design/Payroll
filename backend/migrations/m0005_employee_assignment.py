"""M0005 - Current Assignment / Penempatan Karyawan (Upgrade 01D). Additive, tenant-safe, sekali jalan.

1. Ledger `schema_migrations`; jika m0005 sudah tercatat -> SKIP.
2. Tabel `employee_assignments` (tenant-scoped `company_id`).
3. Backfill: setiap karyawan (non-deleted) yang punya `project_id` dan belum punya assignment ->
   1 assignment ACTIVE, source=LEGACY_BASELINE, start_date=NULL (tanggal penempatan lama tidak diketahui,
   TIDAK dikarang), field organisasi disalin dari data karyawan saat ini.
Tidak ada DROP/RENAME; `employees.project_id` tetap ada. Jalankan: python -m migrations.m0005_employee_assignment [--apply]
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

MIGRATION_ID = "m0005_employee_assignment"
LEDGER_DDL = ("CREATE TABLE IF NOT EXISTS schema_migrations (id VARCHAR(100) NOT NULL PRIMARY KEY,"
              " applied_at DATETIME(6) NOT NULL, summary JSON NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")


async def run(apply: bool) -> dict:
    import sqlalchemy as sa
    from app.core.config import settings
    from app.core.db import close_db, get_engine, get_table, get_db, NO_ID, now
    from app.core import assignment as asg

    if settings.READ_ONLY:
        raise SystemExit("READ_ONLY aktif - migrasi dibatalkan.")
    engine = get_engine()
    plan = []
    try:
        async with engine.begin() as conn:
            await conn.execute(sa.text(LEDGER_DDL)) if apply else None
            exists = (await conn.execute(sa.text(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'schema_migrations'"))).scalar()
            if exists:
                done = (await conn.execute(sa.text("SELECT applied_at FROM schema_migrations WHERE id = :id"), {"id": MIGRATION_ID})).scalar()
                if done:
                    return {"migration": MIGRATION_ID, "mode": "SKIP", "changes": [f"(sudah diterapkan pada {done} - dilewati)"]}
            present = (await conn.execute(sa.text(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'employee_assignments'"))).scalar()
            plan.append("(tabel employee_assignments sudah ada)" if present else "CREATE TABLE employee_assignments")
            if apply and not present:
                await conn.run_sync(lambda c: get_table("employee_assignments").create(c, checkfirst=True))
        db = get_db()
        emps = await db.employees.find({"project_id": {"$ne": None}, "status": {"$ne": "deleted"}}, NO_ID).to_list(100000)
        created = 0
        for e in emps:
            if not e.get("project_id"):
                continue
            if present or apply:
                has = await db.employee_assignments.count_documents({"company_id": e["company_id"], "employee_id": e["id"]}) if (present or apply) else 0
                if has:
                    continue
            created += 1
            if apply:
                doc = asg.new_assignment_doc(e["company_id"], e["id"], e, None, "LEGACY_BASELINE",
                                             "Baseline migrasi 01D dari employees.project_id", None, None)
                await db.employee_assignments.insert_one(doc)
        plan.append(f"BACKFILL {created} assignment ACTIVE (source=LEGACY_BASELINE, start_date=NULL)")
        summary = {"table": "employee_assignments", "legacy_baseline_created": created}
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
