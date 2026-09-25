"""M0002 - Tenant Subscription / Expiry (SCHEMA ADDITIVE, tanpa ubah data bisnis).

Menambahkan kolom NULLABLE pada tabel existing `companies` (tidak ada tabel baru):
  - subscription_start_date  VARCHAR(32)  (YYYY-MM-DD)
  - subscription_end_date    VARCHAR(32)  (YYYY-MM-DD)
  - grace_period_days        INT
  - subscription_notes       TEXT

Status masa layanan (ACTIVE / GRACE / EXPIRED) TIDAK disimpan - dihitung dari
tanggal (lihat app/core/tenant_subscription.py). Status operasional tetap di
kolom existing `companies.status`.

Kompatibilitas: semua tenant existing mendapat NULL -> dianggap "tanpa batas /
legacy active" sehingga TIDAK ada tenant yang terblokir oleh migration ini.

Idempotent: kolom yang sudah ada dilewati (setara dengan sinkronisasi skema
otomatis aplikasi saat startup). Default dry-run; gunakan --apply untuk menerapkan.
"""
import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

MIGRATION_ID = "m0002_tenant_subscription"
COLUMNS = [
    ("subscription_start_date", "VARCHAR(32)"),
    ("subscription_end_date", "VARCHAR(32)"),
    ("grace_period_days", "INT"),
    ("subscription_notes", "TEXT"),
]


async def run(apply: bool) -> dict:
    from sqlalchemy import text

    from app.core.db import close_db, get_engine

    plan = []
    try:
        async with get_engine().begin() as conn:
            rows = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = 'companies'"
            ))
            existing = {r[0] for r in rows}
            for name, ddl in COLUMNS:
                if name in existing:
                    continue
                plan.append(f"ALTER TABLE companies ADD COLUMN {name} {ddl} NULL")
                if apply:
                    await conn.execute(text(f"ALTER TABLE `companies` ADD COLUMN IF NOT EXISTS `{name}` {ddl} NULL"))
    finally:
        await close_db()
    return {"migration": MIGRATION_ID, "mode": "APPLY" if apply else "DRY-RUN",
            "changes": plan or ["(tidak ada - kolom sudah terpasang)"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Terapkan perubahan (default dry-run).")
    result = asyncio.run(run(parser.parse_args().apply))
    print(result["migration"], result["mode"])
    for line in result["changes"]:
        print(" -", line)
