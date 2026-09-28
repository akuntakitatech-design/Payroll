"""M0013 - Siklus aset (Phase 2A CP2): Penyerahan, Pemegang, Pengembalian, Pemeriksaan, Dokumen BAST.
Additive only, tenant-safe, idempotent, runs once. m0012 TIDAK diubah.

1. Ledger `schema_migrations`; bila m0013 sudah tercatat -> SKIP.
2. Tabel baru (CREATE IF NOT EXISTS, deklarasi di core/db.py): asset_handovers, asset_handover_items, asset_holdings,
   asset_returns, asset_return_items, asset_inspections, asset_basts (+ index; unique `ux_asset_holding_active`
   = maks. 1 holding ACTIVE per aset, `ux_asset_bast_number` = nomor BAST unik per company).
3. Kolom referensi aditif pada `asset_events`: employee_id, holding_id, bast_id (NULL, hanya bila belum ada).
4. RBAC aditif: permission asset_handover / asset_return / asset_inspection / asset_bast; preset GA Admin (semua) /
   GA Staff (tanpa publish/complete) di-top-up hanya untuk resource yang belum dimiliki role; tidak menimpa kustomisasi.
5. Konfigurasi penomoran BAST_HANDOVER / BAST_RETURN dibuat otomatis saat pertama dipakai (doc_sequence DEFAULTS).
Tidak ada DROP/RENAME/ALTER tipe kolom; tidak mengubah data aset/karyawan/01H/01I.
Guard: default hanya `hris_dev` lokal; target lain wajib `--confirm-db <nama_database>`.
Run: python -m migrations.m0013_asset_lifecycle [--apply] [--confirm-db NAME]
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

from migrations.m0012_asset_management import LEDGER_DDL, guard  # noqa: E402  (guard & ledger DDL identik)

MIGRATION_ID = "m0013_asset_lifecycle"
NEW_TABLES = ["asset_handovers", "asset_handover_items", "asset_holdings", "asset_returns", "asset_return_items",
              "asset_inspections", "asset_basts"]
EVENT_COLUMNS = {"employee_id": "VARCHAR(36)", "holding_id": "VARCHAR(36)", "bast_id": "VARCHAR(36)"}
CP2_RESOURCES = ("asset_handover", "asset_return", "asset_inspection", "asset_bast")


async def run(apply: bool, confirm_db=None) -> dict:
    import sqlalchemy as sa
    from app.core.db import _doc_to_row, close_db, get_engine, get_table, new_id, now
    from app.core.rbac import ACTION_LABELS, RESOURCES, default_role_permissions

    db_name = guard(confirm_db)
    engine = get_engine()
    plan, created_tables, created_idx, added_cols = [], [], [], []
    counts = {"permissions": 0, "role_permissions": 0}
    ts = now().replace(tzinfo=None)
    try:
        async with engine.begin() as conn:
            if apply:
                await conn.execute(sa.text(LEDGER_DDL))
            if (await conn.execute(sa.text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()"
                                           " AND table_name = 'schema_migrations'"))).scalar():
                done = (await conn.execute(sa.text("SELECT applied_at FROM schema_migrations WHERE id = :id"), {"id": MIGRATION_ID})).scalar()
                if done:
                    return {"migration": MIGRATION_ID, "db": db_name, "mode": "SKIP",
                            "changes": [f"(sudah diterapkan pada {done} - dilewati)"]}
            if not (await conn.execute(sa.text("SELECT applied_at FROM schema_migrations WHERE id = 'm0012_asset_management'"))).scalar():
                raise SystemExit("DITOLAK: m0012_asset_management belum diterapkan pada database ini.")

            async def _scalar(sql, **p):
                return (await conn.execute(sa.text(sql), p)).scalar()

            for name in NEW_TABLES:
                tbl = get_table(name)
                if await _scalar("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = :t", t=name):
                    plan.append(f"(tabel {name} sudah ada)")
                    for idx in sorted(tbl.indexes, key=lambda i: i.name):
                        if not await _scalar("SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE()"
                                             " AND table_name = :t AND index_name = :i", t=name, i=idx.name):
                            plan.append(f"CREATE {'UNIQUE ' if idx.unique else ''}INDEX {idx.name} ON {name}")
                            created_idx.append(f"{name}.{idx.name}")
                            if apply:
                                await conn.run_sync(lambda sc, i=idx: i.create(sc))
                    continue
                plan.append(f"CREATE TABLE {name} (+{len(tbl.indexes)} index)")
                created_tables.append(name)
                if apply:
                    await conn.run_sync(lambda sc, t=tbl: t.create(sc, checkfirst=True))

            for col, ddl in EVENT_COLUMNS.items():
                if await _scalar("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE()"
                                 " AND table_name = 'asset_events' AND column_name = :c", c=col):
                    continue
                plan.append(f"ALTER TABLE asset_events ADD COLUMN {col} {ddl} NULL")
                added_cols.append(f"asset_events.{col}")
                if apply:
                    await conn.execute(sa.text(f"ALTER TABLE asset_events ADD COLUMN `{col}` {ddl} NULL DEFAULT NULL"))

            async def _insert(table, row):
                if apply:
                    t = get_table(table)
                    await conn.execute(sa.insert(t), [_doc_to_row(t, row, full=True)])

            base = {"company_id": None, "status": "active", "created_at": ts, "updated_at": ts, "created_by": None, "updated_by": None}
            for resource in CP2_RESOURCES:
                label, module_key, actions = RESOURCES[resource]
                for action in actions:
                    key = f"{resource}:{action}"
                    if await _scalar("SELECT COUNT(*) FROM permissions WHERE `key` = :k", k=key):
                        continue
                    counts["permissions"] += 1
                    await _insert("permissions", {**base, "id": new_id(), "key": key, "resource": resource, "resource_label": label,
                                                  "action": action, "action_label": ACTION_LABELS[action],
                                                  "module_key": module_key, "name": f"{ACTION_LABELS[action]} {label}"})
            for role_key, keys in default_role_permissions().items():
                if not await _scalar("SELECT COUNT(*) FROM roles WHERE `key` = :k", k=role_key):
                    continue
                for resource in CP2_RESOURCES:   # top-up per resource hanya bila role belum punya apa pun untuk resource tsb.
                    rk = [k for k in keys if k.startswith(f"{resource}:")]
                    if not rk or await _scalar("SELECT COUNT(*) FROM role_permissions WHERE role_key = :r AND company_id IS NULL"
                                               " AND permission_key LIKE :p", r=role_key, p=f"{resource}:%"):
                        continue
                    for key in rk:
                        counts["role_permissions"] += 1
                        await _insert("role_permissions", {**base, "id": new_id(), "role_key": role_key, "permission_key": key})
            plan.append(f"RBAC: permissions +{counts['permissions']}, role_permissions +{counts['role_permissions']}")

        summary = {"tables_created": created_tables, "indexes_created": created_idx, "columns_added": added_cols, **counts}
        if apply:
            async with engine.begin() as conn:
                await conn.execute(sa.text("INSERT INTO schema_migrations (id, applied_at, summary) VALUES (:id, :ts, :s)"),
                                   {"id": MIGRATION_ID, "ts": now().replace(tzinfo=None), "s": json.dumps(summary)})
        plan.append(f"RECORD schema_migrations {MIGRATION_ID}")
        return {"migration": MIGRATION_ID, "db": db_name, "mode": "APPLY" if apply else "DRY-RUN", "changes": plan, "summary": summary}
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
