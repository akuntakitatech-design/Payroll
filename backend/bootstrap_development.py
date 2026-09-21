"""Bootstrap idempoten khusus development; tidak membuat data bisnis contoh."""
import asyncio
import os
from urllib.parse import urlsplit
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / '.env')


def verify_development_target():
    url = urlsplit(os.environ.get('DATABASE_URL', ''))
    expected = os.environ.get('DEVELOPMENT_DB_NAME')
    if os.environ.get('APP_ENV') != 'development' or url.hostname not in {'127.0.0.1', 'localhost'}:
        raise RuntimeError('Bootstrap hanya diizinkan pada MariaDB development lokal.')
    if not expected or url.path.lstrip('/') != expected:
        raise RuntimeError('Nama database tidak sesuai konfigurasi development.')
    if os.environ.get('AUTO_SEED', '').lower() != 'false':
        raise RuntimeError('AUTO_SEED harus false; data bisnis contoh tidak diperlukan.')
    if os.environ.get('R2_ACCESS_KEY_ID') or os.environ.get('R2_SECRET_ACCESS_KEY'):
        raise RuntimeError('Bootstrap ini tidak boleh menggunakan kredensial R2.')


async def main():
    verify_development_target()
    from app.core.db import get_db, ensure_indexes, new_id, audit_fields, close_db
    from app.core.rbac import MODULES, ROLES, RESOURCES, ACTION_LABELS, default_role_permissions
    from app.core.security import hash_password
    from app.routers.companies import seed_company_modules, ensure_company_settings

    email = os.environ['DEV_ADMIN_EMAIL']
    password = os.environ['DEV_ADMIN_PASSWORD']
    code = os.environ['DEV_COMPANY_CODE']
    name = os.environ['DEV_COMPANY_NAME']
    if len(password) < 16:
        raise RuntimeError('Kata sandi development minimal 16 karakter.')
    db = get_db()

    async def insert_missing(table, query, values):
        old = await db[table].find_one(query)
        if old:
            return old
        doc = {'id': new_id(), 'company_id': None, 'status': 'active', **values, **audit_fields(None)}
        await db[table].insert_one(doc)
        return doc

    try:
        await ensure_indexes()
        for role in ROLES:
            await insert_missing('roles', {'key': role['key']}, role)
        for module in MODULES:
            await insert_missing('modules', {'key': module['key']}, module)
        for resource, (label, module, actions) in RESOURCES.items():
            for action in actions:
                key = f'{resource}:{action}'
                await insert_missing('permissions', {'key': key}, {
                    'key': key, 'resource': resource, 'resource_label': label,
                    'action': action, 'action_label': ACTION_LABELS[action],
                    'module_key': module, 'name': f'{ACTION_LABELS[action]} {label}',
                })
        await insert_missing('permissions', {'key': '*:*'}, {
            'key': '*:*', 'resource': '*', 'resource_label': 'Semua Modul',
            'action': '*', 'action_label': 'Semua Tindakan', 'module_key': 'hr_core', 'name': 'Akses Penuh',
        })
        for role, permissions in default_role_permissions().items():
            # Jangan mengubah matriks yang sudah dikonfigurasi administrator.
            if await db.role_permissions.count_documents({'role_key': role}):
                continue
            for permission in permissions:
                await insert_missing('role_permissions', {'role_key': role, 'permission_key': permission},
                                     {'role_key': role, 'permission_key': permission})
        company = await insert_missing('companies', {'code': code}, {
            'code': code, 'name': name, 'legal_name': name, 'timezone': 'Asia/Jakarta', 'currency': 'IDR',
        })
        await seed_company_modules(company['id'], [m['key'] for m in MODULES if m['key'] != 'accounting'], None)
        await ensure_company_settings(company['id'], None)
        user = await insert_missing('users', {'email': email}, {
            'email': email, 'full_name': 'Super Admin DEVELOPMENT',
            'password_hash': hash_password(password), 'default_company_id': company['id'],
            'must_change_password': False, 'is_demo_account': False,
        })
        await insert_missing('user_company_roles', {'user_id': user['id'], 'role_key': 'super_admin', 'company_id': None},
                             {'user_id': user['id'], 'role_key': 'super_admin', 'company_id': None})
        print('Bootstrap development selesai: katalog existing, tenant development, dan admin. Tidak ada data bisnis contoh.')
    finally:
        await close_db()


if __name__ == '__main__':
    asyncio.run(main())
