"""m0017_mobilization_approval - Modul 4 Blueprint HRGA: Approval Mobilisasi oleh HR Manager.

ADITIF & IDEMPOTEN (pola identik m0016). Tidak mengubah migrasi sebelumnya.
  * ALTER roster_mobilizations: approval_state, approval_note, approved_by, approved_by_name, approved_at
    - NULL = mobilisasi lama (sebelum fitur approval). Diisi APPROVED oleh backfill di bawah agar
      antrean persetujuan tidak terisi data historis.
  * CREATE INDEX ix_roster_mobilization_approval (company_id, approval_state) untuk antrean approval.
  * RBAC: permission roster:approve sudah ada di RESOURCES sejak Modul 4 CP1; migrasi hanya
    memastikan barisnya ada dan memberi top-up ke role yang preset-nya memuat akses tsb.

Pemakaian (dari folder backend):
    python -m migrations.m0017_mobilization_approval                       # dry-run
    python -m migrations.m0017_mobilization_approval --apply --confirm-db hris_dev
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

MIGRATION_ID = "m0017_mobilization_approval"
NEW_COLUMNS = {
    "roster_mobilizations": {
        "approval_state": "VARCHAR(32)",
        "approval_note": "TEXT",
        "approved_by": "VARCHAR(36)",
        "approved_by_name": "VARCHAR(255)",
        "approved_at": "DATETIME(6)",
    },
}
NEW_INDEXES = {"roster_mobilizations": {"ix_roster_mobilization_approval"}}
NEW_PERMISSIONS = ("roster:approve",)
# Jangkar: role hanya di-top-up bila sudah memegang hak tulis roster (bukan sekadar melihat).
ROLE_ANCHORS = ("roster:edit",)
REQUIRES = ()


async def run(apply: bool, confirm_db=None) -> dict:
    import sqlalchemy as sa
    from app.core.db import _doc_to_row, close_db, get_engine, get_table, new_id, now
    from app.core.rbac import ACTION_LABELS, RESOURCES, default_role_permissions

    db_name = guard(confirm_db)
    engine = get_engine()
    plan, added_cols, created_idx = [], [], []
    counts = {"permissions": 0, "role_permissions": 0, "mobilizations_backfilled": 0}
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

            async def _has_index(table, name):
                return await _scalar("SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE()"
                                     " AND table_name = :t AND index_name = :i", t=table, i=name)

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
                for name, unique, cols in specs:
                    if name in names and not await _has_index(table, name):
                        col_sql = ", ".join(f"`{c}`" for c in cols)
                        plan.append(f"CREATE {'UNIQUE ' if unique else ''}INDEX {name} ON {table} ({', '.join(cols)})")
                        created_idx.append(f"{table}.{name}")
                        if apply:
                            await conn.execute(sa.text(f"CREATE {'UNIQUE ' if unique else ''}INDEX `{name}` ON `{table}` ({col_sql})"))

            backfill = await _scalar("SELECT COUNT(*) FROM roster_mobilizations WHERE approval_state IS NULL")
            counts["mobilizations_backfilled"] = backfill
            plan.append(f"BACKFILL roster_mobilizations.approval_state = 'APPROVED' untuk {backfill} mobilisasi lama")
            if apply and backfill:
                await conn.execute(sa.text(
                    "UPDATE roster_mobilizations SET approval_state = 'APPROVED' WHERE approval_state IS NULL"))

            async def _insert(table, row):
                if apply:
                    t = get_table(table)
                    await conn.execute(sa.insert(t), [_doc_to_row(t, row, full=True)])

            base = {"company_id": None, "status": "active", "created_at": ts, "updated_at": ts,
                    "created_by": None, "updated_by": None}
            for key in NEW_PERMISSIONS:
                resource, action = key.split(":", 1)
                label, module_key, _actions = RESOURCES[resource]
                if await _scalar("SELECT COUNT(*) FROM permissions WHERE `key` = :k", k=key):
                    continue
                counts["permissions"] += 1
                await _insert("permissions", {**base, "id": new_id(), "key": key, "resource": resource,
                                              "resource_label": label, "action": action,
                                              "action_label": ACTION_LABELS[action], "module_key": module_key,
                                              "name": f"{ACTION_LABELS[action]} {label}"})
            matrix = default_role_permissions()
            for key in NEW_PERMISSIONS:
                for role_key, keys in matrix.items():
                    if key not in keys:
                        continue
                    if not await _scalar("SELECT COUNT(*) FROM roles WHERE `key` = :k", k=role_key):
                        continue
                    if await _scalar("SELECT COUNT(*) FROM role_permissions WHERE role_key = :r AND company_id IS NULL"
                                     " AND permission_key = :p", r=role_key, p=key):
                        continue
                    anchors = ", ".join(f"'{a}'" for a in ROLE_ANCHORS)
                    has_anchor = await _scalar(
                        f"SELECT COUNT(*) FROM role_permissions WHERE role_key = :r AND company_id IS NULL"
                        f" AND permission_key IN ({anchors})", r=role_key)
                    if not has_anchor:
                        continue
                    counts["role_permissions"] += 1
                    await _insert("role_permissions", {**base, "id": new_id(), "role_key": role_key, "permission_key": key})
            plan.append(f"RBAC: permissions +{counts['permissions']}, role_permissions +{counts['role_permissions']}")

        summary = {"columns_added": added_cols, "indexes_created": created_idx, **counts}
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
