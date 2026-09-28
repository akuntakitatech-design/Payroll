"""m0015_asset_documents_employee360 - Phase 2A CP4: Dokumen Transaksi Aset + Employee Asset 360.

ADITIF & IDEMPOTEN (pola identik m0014). Tidak mengubah m0012/m0013/m0014.
  * CREATE TABLE asset_documents (+ index: ux_asset_doc_path, ux_asset_doc_signed, ix_asset_doc_source/employee/asset/bast)
    - metadata saja; file fisik di object storage (R2). Tanpa binary di database.
  * RBAC: permission asset_document:{view,create,delete} + top-up preset role (hanya bila role belum punya resource tsb).
Employee Asset 360 TIDAK membuat tabel baru: dibaca langsung dari holdings/handovers/returns/inspections/openings/BAST/
events/asset_documents (satu sumber kebenaran).

Pemakaian:
    python migrations/m0015_asset_documents_employee360.py                          # dry-run
    python migrations/m0015_asset_documents_employee360.py --apply --confirm-db hris_dev
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

MIGRATION_ID = "m0015_asset_documents_employee360"
NEW_TABLES = ["asset_documents"]
NEW_COLUMNS: dict = {}
NEW_INDEXES: dict = {}
CP4_RESOURCES = ("asset_document",)
REQUIRES = ("m0012_asset_management", "m0013_asset_lifecycle", "m0014_asset_import_opening")


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
            for req in REQUIRES:
                if not (await conn.execute(sa.text("SELECT applied_at FROM schema_migrations WHERE id = :id"), {"id": req})).scalar():
                    raise SystemExit(f"DITOLAK: {req} belum diterapkan pada database ini.")

            async def _scalar(sql, **p):
                return (await conn.execute(sa.text(sql), p)).scalar()

            async def _has_index(table, name):
                return await _scalar("SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE()"
                                     " AND table_name = :t AND index_name = :i", t=table, i=name)

            for name in NEW_TABLES:
                tbl = get_table(name)
                if await _scalar("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = :t", t=name):
                    plan.append(f"(tabel {name} sudah ada)")
                    for idx in sorted(tbl.indexes, key=lambda i: i.name):
                        if not await _has_index(name, idx.name):
                            plan.append(f"CREATE {'UNIQUE ' if idx.unique else ''}INDEX {idx.name} ON {name}")
                            created_idx.append(f"{name}.{idx.name}")
                            if apply:
                                await conn.run_sync(lambda sc, i=idx: i.create(sc))
                    continue
                plan.append(f"CREATE TABLE {name} (+{len(tbl.indexes)} index)")
                created_tables.append(name)
                if apply:
                    await conn.run_sync(lambda sc, t=tbl: t.create(sc, checkfirst=True))

            for table, cols in NEW_COLUMNS.items():
                for col, ddl in cols.items():
                    if await _scalar("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE()"
                                     " AND table_name = :t AND column_name = :c", t=table, c=col):
                        continue
                    plan.append(f"ALTER TABLE {table} ADD COLUMN {col} {ddl} NULL")
                    added_cols.append(f"{table}.{col}")
                    if apply:
                        await conn.execute(sa.text(f"ALTER TABLE `{table}` ADD COLUMN `{col}` {ddl} NULL DEFAULT NULL"))
            for table, names in NEW_INDEXES.items():
                tbl = get_table(table)
                specs = [(i.name, i.unique, [c.name for c in i.columns]) for i in tbl.indexes]
                specs += [(c.name, True, [col.name for col in c.columns]) for c in tbl.constraints
                          if isinstance(c, sa.UniqueConstraint)]
                for name, unique, cols in specs:
                    if name in names and not await _has_index(table, name):
                        col_sql = ", ".join(f"`{c}`" for c in cols)
                        plan.append(f"CREATE {'UNIQUE ' if unique else ''}INDEX {name} ON {table} ({', '.join(cols)})")
                        created_idx.append(f"{table}.{name}")
                        if apply:
                            await conn.execute(sa.text(f"CREATE {'UNIQUE ' if unique else ''}INDEX `{name}` ON `{table}` ({col_sql})"))

            async def _insert(table, row):
                if apply:
                    t = get_table(table)
                    await conn.execute(sa.insert(t), [_doc_to_row(t, row, full=True)])

            base = {"company_id": None, "status": "active", "created_at": ts, "updated_at": ts, "created_by": None, "updated_by": None}
            for resource in CP4_RESOURCES:
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
                for resource in CP4_RESOURCES:   # top-up per resource hanya bila role belum punya apa pun untuk resource tsb.
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
