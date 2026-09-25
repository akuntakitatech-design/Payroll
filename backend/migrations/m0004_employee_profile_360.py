"""M0004 - Employee Profile 360 (Upgrade 01C). Additive, tenant-safe, sekali jalan.

Perubahan (hanya STRUKTUR, tanpa data):
1. Ledger `schema_migrations` (dibuat bila belum ada). Jika m0004 sudah tercatat, SKIP.
2. Tabel `employee_family_members` (anggota keluarga repeatable, tenant-scoped `company_id`).
3. Kolom nullable baru di `employees`: `domicile_address`, `province`, `postal_code`,
   `photo_path`, `photo_version`. (Alamat KTP = `address`, email pribadi = `email` existing.)

TIDAK ada backfill data keluarga: field legacy `emergency_contact_name/phone` tidak memuat
hubungan keluarga yang pasti, jadi dipertahankan apa adanya dan dilaporkan (tidak dikarang).
Tidak ada DROP/RENAME/ubah tipe. Jalankan: python -m migrations.m0004_employee_profile_360 [--apply]
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

MIGRATION_ID = "m0004_employee_profile_360"
NEW_TABLES = ["employee_family_members"]
NEW_EMPLOYEE_COLUMNS = {
    "domicile_address": "TEXT NULL",
    "province": "VARCHAR(255) NULL",
    "postal_code": "VARCHAR(32) NULL",
    "photo_path": "VARCHAR(512) NULL",
    "photo_version": "VARCHAR(32) NULL",
}
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
    from app.core.db import close_db, get_engine, get_table, now

    if settings.READ_ONLY:
        raise SystemExit("READ_ONLY aktif - migrasi dibatalkan.")
    engine = get_engine()
    plan = []
    try:
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

        async with engine.begin() as conn:
            for name in NEW_TABLES:
                present = (await conn.execute(sa.text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = DATABASE() AND table_name = :t"), {"t": name})).scalar()
                if present:
                    plan.append(f"(tabel {name} sudah ada - tidak diubah)")
                else:
                    plan.append(f"CREATE TABLE {name}")
                    if apply:
                        await conn.run_sync(lambda c, n=name: get_table(n).create(c, checkfirst=True))
            for col, ddl in NEW_EMPLOYEE_COLUMNS.items():
                present = (await conn.execute(sa.text(
                    "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() "
                    "AND table_name = 'employees' AND column_name = :c"), {"c": col})).scalar()
                if present:
                    plan.append(f"(kolom employees.{col} sudah ada - tidak diubah)")
                else:
                    plan.append(f"ALTER TABLE employees ADD COLUMN {col} {ddl}")
                    if apply:
                        await conn.execute(sa.text(f"ALTER TABLE employees ADD COLUMN IF NOT EXISTS {col} {ddl}"))
            fam_rows = 0
            if apply or not any(p == "CREATE TABLE employee_family_members" for p in plan):
                fam_rows = (await conn.execute(sa.text("SELECT COUNT(*) FROM employee_family_members"))).scalar()
            plan.append(f"(backfill keluarga: TIDAK dilakukan - tidak ada sumber legacy yang pasti; baris saat ini: {fam_rows})")

        summary = {"tables": NEW_TABLES, "employee_columns": list(NEW_EMPLOYEE_COLUMNS), "family_backfill": 0}
        if apply:
            async with engine.begin() as conn:
                await conn.execute(sa.text(
                    "INSERT INTO schema_migrations (id, applied_at, summary) VALUES (:id, :ts, :s)"),
                    {"id": MIGRATION_ID, "ts": now().replace(tzinfo=None), "s": json.dumps(summary)})
        plan.append(f"RECORD schema_migrations {MIGRATION_ID}")
        return {"migration": MIGRATION_ID, "mode": "APPLY" if apply else "DRY-RUN", "changes": plan}
    finally:
        await close_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Terapkan perubahan (default dry-run).")
    result = asyncio.run(run(parser.parse_args().apply))
    print(result["migration"], result["mode"])
    for line in result["changes"]:
        print(" -", line)
