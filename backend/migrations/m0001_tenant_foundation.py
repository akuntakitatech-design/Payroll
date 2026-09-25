"""M0001 - Tenant Foundation Minimal (DATA ONLY, tanpa perubahan skema).

Perubahan (semuanya idempotent):
1. Role global `super_admin` diberi label eksplisit "Platform Admin" (hanya jika
   masih berlabel bawaan "Super Admin"; label yang sudah diubah manual dibiarkan).
2. Role sistem baru `tenant_admin` (scope tenant) ditambahkan bila belum ada.
3. Hak akses `tenant_admin` = semua permission tenant KECUALI siklus hidup tenant
   (`company:create`, `company:delete`). Hanya diisi jika role belum punya
   permission sama sekali (tidak menimpa perubahan manual dari UI).

Tidak ada tabel/kolom baru. Tidak ada UPDATE/DELETE data bisnis.
"""
import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

MIGRATION_ID = "m0001_tenant_foundation"


async def run(apply: bool) -> dict:
    from app.core.db import NO_ID, audit_fields, close_db, get_db, new_id
    from app.core.rbac import PLATFORM_ADMIN_ROLE, ROLES, TENANT_ADMIN_ROLE, default_role_permissions

    db = get_db()
    plan = []
    try:
        role_defs = {r["key"]: r for r in ROLES}

        # 1) Label Platform Admin
        sa = await db.roles.find_one({"key": PLATFORM_ADMIN_ROLE}, NO_ID)
        want = role_defs[PLATFORM_ADMIN_ROLE]
        if sa and sa.get("name") == "Super Admin":
            plan.append("UPDATE roles.super_admin name -> 'Platform Admin'")
            if apply:
                await db.roles.update_one(
                    {"key": PLATFORM_ADMIN_ROLE},
                    {"$set": {"name": want["name"], "description": want["description"],
                              **audit_fields(None, creating=False)}},
                )

        # 2) Role tenant_admin
        ta = await db.roles.find_one({"key": TENANT_ADMIN_ROLE}, NO_ID)
        if not ta:
            plan.append("INSERT roles.tenant_admin")
            if apply:
                await db.roles.insert_one({
                    "id": new_id(), "company_id": None, "status": "active",
                    **role_defs[TENANT_ADMIN_ROLE], **audit_fields(None, creating=True),
                })

        # 3) Permission tenant_admin
        has_perm = await db.role_permissions.count_documents({"role_key": TENANT_ADMIN_ROLE})
        if not has_perm:
            keys = default_role_permissions()[TENANT_ADMIN_ROLE]
            valid = {p["key"] for p in await db.permissions.find({}, NO_ID).to_list(5000)}
            keys = [k for k in keys if k in valid]
            plan.append(f"INSERT role_permissions tenant_admin x{len(keys)}")
            if apply:
                for key in keys:
                    await db.role_permissions.insert_one({
                        "id": new_id(), "company_id": None, "role_key": TENANT_ADMIN_ROLE,
                        "permission_key": key, "status": "active", **audit_fields(None, creating=True),
                    })
    finally:
        await close_db()
    return {"migration": MIGRATION_ID, "mode": "APPLY" if apply else "DRY-RUN",
            "changes": plan or ["(tidak ada - sudah terpasang)"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Terapkan perubahan (default dry-run).")
    result = asyncio.run(run(parser.parse_args().apply))
    print(result["migration"], result["mode"])
    for line in result["changes"]:
        print(" -", line)
