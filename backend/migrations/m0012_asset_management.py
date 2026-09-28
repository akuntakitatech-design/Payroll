"""M0012 - Manajemen Aset foundation (Phase 2A CP1). Additive only, tenant-safe, idempotent, runs once.

1. Ledger `schema_migrations`; if m0012 is already recorded -> SKIP (no duplicate rows).
2. New tables (CREATE IF NOT EXISTS via metadata, declared in core/db.py):
   asset_categories, asset_units, asset_conditions, asset_statuses, assets, asset_events,
   document_sequence_configs, document_sequence_counters.
   (Tabel CP2+ - holding, BAST, BAST item, impor/saldo awal - TIDAK dibuat di sini; menyusul aditif di m0013+.)
3. Indexes for the tables above (only if missing).
4. RBAC seed (global, aditif, tidak menimpa kustomisasi tenant):
   - module catalog row `asset` "Manajemen Aset" (non-core);
   - permissions asset:*, asset_value:*, asset_master:*;
   - preset roles `ga_admin` / `ga_staff` (+ default permissions only if the role has no permission rows yet);
   - top-up asset permissions to existing roles ONLY if that role has no permission for that resource yet.
5. Master default per company ONLY for companies whose `asset` module is already active (normally none; seeding
   otherwise happens when the module is activated). Existing codes are never overwritten.
No DROP/RENAME/ALTER of existing tables, no change to employees / projects / masters / 01H / 01I data.

Guard: by default runs ONLY on local development DB `hris_dev` (host 127.0.0.1/localhost, APP_ENV=development).
Other targets require an explicit `--confirm-db <database_name>` equal to the connected database (for a later,
separately authorised rollout).
Run: python -m migrations.m0012_asset_management [--apply] [--confirm-db NAME]
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

MIGRATION_ID = "m0012_asset_management"
NEW_TABLES = ["asset_units", "asset_categories", "asset_conditions", "asset_statuses", "assets", "asset_events",
              "document_sequence_configs", "document_sequence_counters"]
ASSET_RESOURCES = ("asset", "asset_value", "asset_master")
DEV_DB = "hris_dev"
LEDGER_DDL = ("CREATE TABLE IF NOT EXISTS schema_migrations (id VARCHAR(100) NOT NULL PRIMARY KEY,"
              " applied_at DATETIME(6) NOT NULL, summary JSON NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")


def guard(confirm_db):
    from app.core.config import settings

    url = urlsplit(settings.DATABASE_URL.replace("+asyncmy", ""))
    db_name = url.path.strip("/")
    is_local_dev = (os.environ.get("APP_ENV") == "development" and url.hostname in {"127.0.0.1", "localhost"}
                    and db_name == DEV_DB)
    if settings.READ_ONLY:
        raise SystemExit("READ_ONLY aktif - migrasi dibatalkan.")
    if not is_local_dev and confirm_db != db_name:
        raise SystemExit(f"DITOLAK: target database '{db_name}' bukan {DEV_DB} lokal. "
                         "Rollout ke target lain wajib instruksi terpisah + --confirm-db <nama_database>.")
    return db_name


async def run(apply: bool, confirm_db=None) -> dict:
    import sqlalchemy as sa
    from app.core.db import _doc_to_row, close_db, get_engine, get_table, new_id, now
    from app.core.rbac import ACTION_LABELS, MODULES, RESOURCES, ROLES, default_role_permissions

    db_name = guard(confirm_db)
    engine = get_engine()
    plan, created_tables, created_idx = [], [], []
    counts = {"permissions": 0, "roles": 0, "role_permissions": 0, "modules": 0, "company_seeds": 0}
    ts = now().replace(tzinfo=None)
    try:
        async with engine.begin() as conn:
            if apply:
                await conn.execute(sa.text(LEDGER_DDL))
            exists = (await conn.execute(sa.text(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'schema_migrations'"))).scalar()
            if exists:
                done = (await conn.execute(sa.text("SELECT applied_at FROM schema_migrations WHERE id = :id"), {"id": MIGRATION_ID})).scalar()
                if done:
                    return {"migration": MIGRATION_ID, "db": db_name, "mode": "SKIP",
                            "changes": [f"(sudah diterapkan pada {done} - dilewati)"]}

            async def _scalar(sql, **p):
                return (await conn.execute(sa.text(sql), p)).scalar()

            # ---- tables + indexes
            for name in NEW_TABLES:
                tbl = get_table(name)
                if await _scalar("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = :t", t=name):
                    plan.append(f"(tabel {name} sudah ada)")
                else:
                    plan.append(f"CREATE TABLE {name}")
                    created_tables.append(name)
                    if apply:
                        await conn.run_sync(lambda sc, t=tbl: t.create(sc, checkfirst=True))
                    continue  # index ikut dibuat bersama tabel
                for idx in sorted(tbl.indexes, key=lambda i: i.name):
                    if await _scalar("SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE()"
                                     " AND table_name = :t AND index_name = :i", t=name, i=idx.name):
                        continue
                    plan.append(f"CREATE {'UNIQUE ' if idx.unique else ''}INDEX {idx.name} ON {name} ({', '.join(c.name for c in idx.columns)})")
                    created_idx.append(f"{name}.{idx.name}")
                    if apply:
                        await conn.run_sync(lambda sc, i=idx: i.create(sc))

            # ---- RBAC (global rows, company_id NULL; aditif)
            async def _insert(table, row):
                if apply:
                    t = get_table(table)
                    await conn.execute(sa.insert(t), [_doc_to_row(t, row, full=True)])

            base = {"company_id": None, "status": "active", "created_at": ts, "updated_at": ts, "created_by": None, "updated_by": None}
            mod = next(m for m in MODULES if m["key"] == "asset")
            if not await _scalar("SELECT COUNT(*) FROM modules WHERE `key` = 'asset'"):
                counts["modules"] += 1
                await _insert("modules", {**base, "id": new_id(), **mod})
            for resource in ASSET_RESOURCES:
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
            for role in ROLES:
                if role["key"] in ("ga_admin", "ga_staff") and not await _scalar("SELECT COUNT(*) FROM roles WHERE `key` = :k", k=role["key"]):
                    counts["roles"] += 1
                    await _insert("roles", {**base, "id": new_id(), **role})
            matrix = default_role_permissions()
            for role_key, keys in matrix.items():
                if not await _scalar("SELECT COUNT(*) FROM roles WHERE `key` = :k", k=role_key) and role_key not in ("ga_admin", "ga_staff"):
                    continue  # role belum ada di DB ini -> bukan urusan m0012
                have_any = await _scalar("SELECT COUNT(*) FROM role_permissions WHERE role_key = :r", r=role_key)
                if role_key in ("ga_admin", "ga_staff") and not have_any:
                    wanted = list(keys)  # preset penuh untuk role baru
                else:
                    wanted = []
                    for resource in ASSET_RESOURCES:  # top-up per resource, hanya bila role belum punya apa pun
                        rk = [k for k in keys if k.startswith(f"{resource}:")]
                        if rk and not await _scalar("SELECT COUNT(*) FROM role_permissions WHERE role_key = :r AND permission_key LIKE :p",
                                                    r=role_key, p=f"{resource}:%"):
                            wanted += rk
                for key in wanted:
                    counts["role_permissions"] += 1
                    await _insert("role_permissions", {**base, "id": new_id(), "role_key": role_key, "permission_key": key})
            plan.append(f"RBAC: module +{counts['modules']}, permissions +{counts['permissions']}, roles +{counts['roles']}, "
                        f"role_permissions +{counts['role_permissions']}")

            companies = [r[0] for r in (await conn.execute(sa.text(
                "SELECT company_id FROM company_modules WHERE module_key = 'asset' AND is_active = 1"))).fetchall()]
            counts["company_seeds"] = len(companies)
            plan.append(f"SEED master default aset untuk {len(companies)} company dengan modul aset aktif")

        if apply and companies:
            from app.core.asset_service import seed_defaults
            for cid in companies:
                await seed_defaults(cid, None)

        summary = {"tables_created": created_tables, "indexes_created": created_idx, **counts}
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
