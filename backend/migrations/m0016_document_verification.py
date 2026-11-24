"""m0016_document_verification - Modul 3 Blueprint HRGA: Verifikasi Dokumen.

ADITIF & IDEMPOTEN (pola identik m0015). Tidak mengubah migrasi sebelumnya.
  * ALTER documents: verification_state, verification_note, verified_by, verified_by_name, verified_at
    - NULL = dokumen lama (sebelum fitur verifikasi). Diisi VERIFIED oleh backfill di bawah.
  * CREATE INDEX ix_documents_verification (company_id, verification_state) untuk antrean verifikasi.
  * BACKFILL: seluruh dokumen yang sudah ada ditandai VERIFIED (dokumen lama hanya dapat diunggah
    oleh pengguna internal, sehingga dianggap sudah disahkan). Tidak ada yang masuk antrean lama.
  * RBAC: permission document:verify + top-up preset role yang sudah memegang document:delete.

Pemakaian (dari folder backend):
    python -m migrations.m0016_document_verification                       # dry-run
    python -m migrations.m0016_document_verification --apply --confirm-db hris_dev
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

MIGRATION_ID = "m0016_document_verification"
NEW_COLUMNS = {
    "documents": {
        "verification_state": "VARCHAR(64)",
        "verification_note": "TEXT",
        "verified_by": "VARCHAR(36)",
        "verified_by_name": "VARCHAR(255)",
        "verified_at": "DATETIME(6)",
    },
}
NEW_INDEXES = {"documents": {"ix_documents_verification"}}
NEW_PERMISSIONS = ("document:verify",)
# Jangkar: role hanya di-top-up bila sudah memegang hak tulis dokumen (bukan sekadar melihat).
ROLE_ANCHORS = ("document:delete",)
REQUIRES = ()


async def run(apply: bool, confirm_db=None) -> dict:
    import sqlalchemy as sa
    from app.core.db import _doc_to_row, close_db, get_engine, get_table, new_id, now
    from app.core.rbac import ACTION_LABELS, RESOURCES, default_role_permissions

    db_name = guard(confirm_db)
    engine = get_engine()
    plan, added_cols, created_idx = [], [], []
    counts = {"permissions": 0, "role_permissions": 0, "documents_backfilled": 0}
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

            backfill = await _scalar("SELECT COUNT(*) FROM documents WHERE verification_state IS NULL")
            counts["documents_backfilled"] = backfill
            plan.append(f"BACKFILL documents.verification_state = 'VERIFIED' untuk {backfill} dokumen lama")
            if apply and backfill:
                await conn.execute(sa.text(
                    "UPDATE documents SET verification_state = 'VERIFIED' WHERE verification_state IS NULL"))

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
