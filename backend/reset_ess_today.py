"""Reset data uji Absensi ESS untuk HARI INI (DEVELOPMENT saja).

Menghapus baris attendances hari ini milik karyawan demo NEP-0001 / NEP-0002 / KBS-0001
beserta baris time_approvals `attendance_location` yang merujuk ke record tersebut,
agar skenario Absen Masuk/Pulang dapat diuji ulang dari awal. Audit log TIDAK dihapus.
"""
import asyncio
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.dirname(__file__))
from app.core.db import NO_ID, get_db  # noqa: E402

DEMO_NUMBERS = ("NEP-0001", "NEP-0002", "KBS-0001")


async def main() -> None:
    if os.environ.get("APP_ENV", "development") != "development":
        raise SystemExit("Hanya untuk APP_ENV=development.")
    db = get_db()
    today = datetime.now(ZoneInfo("Asia/Jakarta")).date().isoformat()
    dates = sys.argv[1:] or [today]
    emps = await db.employees.find({"employee_number": {"$in": list(DEMO_NUMBERS)}}, NO_ID).to_list(10)
    ids = [e["id"] for e in emps]
    rows = await db.attendances.find({"employee_id": {"$in": ids}, "work_date": {"$in": dates}}, NO_ID).to_list(50)
    att_ids = [r["id"] for r in rows]
    if att_ids:
        res_a = await db.time_approvals.delete_many({"document_kind": "attendance_location", "record_id": {"$in": att_ids}})
        res_b = await db.attendances.delete_many({"id": {"$in": att_ids}})
        print(f"attendances dihapus: {res_b.deleted_count}, approval lokasi dihapus: {res_a.deleted_count} (tanggal {dates})")
    else:
        print(f"Tidak ada absensi demo pada {dates}.")


asyncio.run(main())
