"""m0018_reports_center - Modul 7 Blueprint HRGA: Pusat Laporan & Export.

ADITIF & IDEMPOTEN (pola identik m0015). Tidak mengubah migrasi sebelumnya.
  * Tidak ada perubahan tabel: laporan membaca tabel yang sudah ada.
  * RBAC: permission report:{view,export} + top-up preset role (hanya bila role belum punya
    permission apa pun untuk resource `report`, sehingga hak akses yang sudah diubah manual
    dari UI tidak tertimpa).

Pemakaian (dari folder backend):
    python -m migrations.m0018_reports_center                       # dry-run
    python -m migrations.m0018_reports_center --apply --confirm-db hris_dev
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

MIGRATION_ID = "m0018_reports_center"
NEW_RESOURCES = ("report",)
REQUIRES = ()


async def run(apply: bool, confirm_db=None) -> dict:
    import sqlalchemy as sa
    from app.core.db import _doc_to_row, close_db, get_engine, get_table, new_id, now
    from app.core.rbac import ACTION_LABELS, RESOURCES, default_role_permissions

    db_name = guard(confirm_db)
    engine = get_engine()
    plan = []
    counts = {"permissions": 0, "role_permissions": 0}
    ts = now().replace(tzinfo=None)
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

            async def _insert(table, row):
                if apply:
                    t = get_table(table)
                    await conn.execute(sa.insert(t), [_doc_to_row(t, row, full=True)])

            base = {"company_id": None, "status": "active", "created_at": ts, "updated_at": ts,
                    "created_by": None, "updated_by": None}
            for resource in NEW_RESOURCES:
                label, module_key, actions = RESOURCES[resource]
                for action in actions:
                    key = f"{resource}:{action}"
                    if await _scalar("SELECT COUNT(*) FROM permissions WHERE `key` = :k", k=key):
                        continue
                    counts["permissions"] += 1
                    await _insert("permissions", {**base, "id": new_id(), "key": key, "resource": resource,
                                                  "resource_label": label, "action": action,
                                                  "action_label": ACTION_LABELS[action], "module_key": module_key,
                                                  "name": f"{ACTION_LABELS[action]} {label}"})
            for role_key, keys in default_role_permissions().items():
                if not await _scalar("SELECT COUNT(*) FROM roles WHERE `key` = :k", k=role_key):
                    continue
                for resource in NEW_RESOURCES:
                    rk = [k for k in keys if k.startswith(f"{resource}:")]
                    if not rk or await _scalar("SELECT COUNT(*) FROM role_permissions WHERE role_key = :r"
                                               " AND company_id IS NULL AND permission_key LIKE :p",
                                               r=role_key, p=f"{resource}:%"):
                        continue
                    for key in rk:
                        counts["role_permissions"] += 1
                        await _insert("role_permissions", {**base, "id": new_id(), "role_key": role_key,
                                                           "permission_key": key})
            plan.append(f"RBAC: permissions +{counts['permissions']}, role_permissions +{counts['role_permissions']}")

        summary = dict(counts)
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
