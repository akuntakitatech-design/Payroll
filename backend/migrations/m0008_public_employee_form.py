"""M0008 - Public Employee Form (Upgrade 01G-A). Additive, tenant-safe, sekali jalan.

1. Ledger `schema_migrations`; jika m0008 sudah tercatat -> SKIP.
2. Tabel baru:
   - `employee_public_links`       (tenant) link undangan: HANYA hash token + sesi publik terbatas per link
   - `employee_update_submissions` (tenant) draft + submission (DRAFT -> PENDING_HR_VERIFICATION)
   - `employee_submission_files`   (tenant) lampiran submission (private; belum menjadi dokumen resmi)
   - `public_rate_limits`          (global) counter percobaan gagal per IP (kunci = hash)
Tidak ada permission baru (memakai `employee:view` / `employee:edit` existing), tidak ada
DROP/RENAME/ALTER tabel lama, tidak ada UPDATE data bisnis, tidak ada backfill.
Jalankan: python -m migrations.m0008_public_employee_form [--apply]
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

MIGRATION_ID = "m0008_public_employee_form"
TABLES = ["employee_public_links", "employee_update_submissions", "employee_submission_files", "public_rate_limits"]
LEDGER_DDL = ("CREATE TABLE IF NOT EXISTS schema_migrations (id VARCHAR(100) NOT NULL PRIMARY KEY,"
              " applied_at DATETIME(6) NOT NULL, summary JSON NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")


async def run(apply: bool) -> dict:
    import sqlalchemy as sa
    from app.core.config import settings
    from app.core.db import close_db, get_engine, get_table, now

    if settings.READ_ONLY:
        raise SystemExit("READ_ONLY aktif - migrasi dibatalkan.")
    engine = get_engine()
    plan, created_tables = [], []
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
        summary = {"tables_created": created_tables, "permission": None}
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
    args = parser.parse_args()
    result = asyncio.run(run(args.apply))
    print(result["migration"], result["mode"])
    for line in result["changes"]:
        print(" -", line)
