"""Authentication / authorization dependencies.

Every tenant-owned endpoint depends on `get_auth` which resolves:
  - the authenticated user
  - the ACTIVE company (from the JWT claim) and verifies membership
  - the effective permission set for that user in that company
  - the activated modules of that company

Authorization is enforced on the BACKEND. The frontend only *hides* menus.
"""
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .db import NO_ID, get_db
from .rbac import WILDCARD, resource_module
from .security import decode_token
from .tenancy import TenantDatabase, get_tenant_db

bearer = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    user: Dict[str, Any]
    company: Optional[Dict[str, Any]] = None
    role_keys: List[str] = field(default_factory=list)
    permissions: Set[str] = field(default_factory=set)
    modules: Set[str] = field(default_factory=set)
    is_super_admin: bool = False
    request: Optional[Request] = None

    @property
    def user_id(self) -> str:
        return self.user["id"]

    @property
    def company_id(self) -> Optional[str]:
        return self.company["id"] if self.company else None

    @property
    def tdb(self) -> TenantDatabase:
        """Accessor database yang terikat pada perusahaan aktif.

        Dipakai sebagai pengganti ``get_db()`` di dalam endpoint tenant.
        Setiap query ke tabel tenant otomatis ter-filter ``company_id``,
        setiap insert otomatis memperoleh ``company_id`` yang benar, dan
        update/delete tidak dapat menyentuh record perusahaan lain.

        Tabel global (users, companies, roles, permissions, modules, ...)
        tetap dilayani tanpa scope sehingga autentikasi, RBAC, dan alur
        super admin berjalan persis seperti sebelumnya.

        Bersifat *fail-safe*: bila tidak ada perusahaan aktif pada konteks,
        mengakses property ini akan menolak request (HTTP 400) — bukan
        mengembalikan database tanpa filter.
        """
        return get_tenant_db(self.company_id)

    def has_permission(self, resource: str, action: str) -> bool:
        if WILDCARD in self.permissions:
            return True
        return f"{resource}:{action}" in self.permissions

    def has_module(self, module_key: str) -> bool:
        return module_key in self.modules

    @property
    def ip(self) -> Optional[str]:
        if not self.request:
            return None
        fwd = self.request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
        return self.request.client.host if self.request.client else None

    @property
    def user_agent(self) -> Optional[str]:
        return self.request.headers.get("user-agent") if self.request else None


async def effective_permissions(user_id: str, company_id: Optional[str]) -> Dict[str, Any]:
    """Resolve role keys + permission keys for a user inside a company."""
    db = get_db()
    query: Dict[str, Any] = {"user_id": user_id, "status": "active"}
    memberships = await db.user_company_roles.find(query, NO_ID).to_list(500)
    return await _permissions_from_memberships(memberships, company_id)


async def _permissions_from_memberships(
    memberships: List[Dict[str, Any]], company_id: Optional[str]
) -> Dict[str, Any]:
    """Bagian murni-hitung + satu query izin, dipisah agar `memberships`
    dapat diambil bersamaan dengan query lain (lihat `_base_auth`)."""
    db = get_db()
    global_roles = [m["role_key"] for m in memberships if m.get("company_id") is None]
    company_roles = (
        [m["role_key"] for m in memberships if m.get("company_id") == company_id]
        if company_id
        else []
    )
    role_keys = sorted(set(global_roles + company_roles))

    perms: Set[str] = set()
    if role_keys:
        rows = await db.role_permissions.find({"role_key": {"$in": role_keys}}, NO_ID).to_list(5000)
        perms = {r["permission_key"] for r in rows}

    return {
        "role_keys": role_keys,
        "permissions": perms,
        "is_super_admin": "super_admin" in global_roles,
        "memberships": memberships,
    }


async def company_modules(company_id: Optional[str]) -> Set[str]:
    if not company_id:
        return set()
    db = get_db()
    rows = await db.company_modules.find(
        {"company_id": company_id, "is_active": True}, NO_ID
    ).to_list(200)
    keys = {r["module_key"] for r in rows}
    keys.add("hr_core")  # core module can never be switched off
    return keys


async def accessible_companies(user_id: str) -> List[Dict[str, Any]]:
    db = get_db()
    info = await effective_permissions(user_id, None)
    if info["is_super_admin"]:
        return await db.companies.find({"status": {"$ne": "archived"}}, NO_ID).sort("name", 1).to_list(500)
    ids = sorted({m["company_id"] for m in info["memberships"] if m.get("company_id")})
    if not ids:
        return []
    return await db.companies.find(
        {"id": {"$in": ids}, "status": {"$ne": "archived"}}, NO_ID
    ).sort("name", 1).to_list(500)


async def _base_auth(
    request: Request, creds: Optional[HTTPAuthorizationCredentials]
) -> AuthContext:
    if creds is None or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token tidak ditemukan. Silakan login kembali.")
    try:
        payload = decode_token(creds.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesi Anda telah berakhir. Silakan login kembali.")
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token tidak valid.")

    if payload.get("typ") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jenis token tidak sesuai.")

    db = get_db()
    company_id = payload.get("active_company_id")

    # Gelombang 1: pengguna, keanggotaan, perusahaan aktif, dan modul
    # perusahaan tidak saling bergantung -> diambil BERSAMAAN.
    wave1 = [
        db.users.find_one({"id": payload.get("sub")}, NO_ID),
        db.user_company_roles.find({"user_id": payload.get("sub"), "status": "active"}, NO_ID).to_list(500),
    ]
    if company_id:
        wave1.append(db.companies.find_one({"id": company_id}, NO_ID))
        wave1.append(
            db.company_modules.find({"company_id": company_id, "is_active": True}, NO_ID).to_list(200)
        )

    results = await asyncio.gather(*wave1)
    user = results[0]
    memberships = results[1]
    company = results[2] if company_id else None
    module_rows = results[3] if company_id else []

    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Pengguna tidak ditemukan.")
    if user.get("status") != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Akun Anda tidak aktif. Hubungi administrator.")

    # Gelombang 2: izin bergantung pada daftar peran hasil gelombang 1.
    info = await _permissions_from_memberships(memberships, company_id)

    if company_id:
        allowed_ids = {m["company_id"] for m in info["memberships"] if m.get("company_id")}
        if not info["is_super_admin"] and company_id not in allowed_ids:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Anda tidak memiliki akses ke perusahaan ini. Silakan pilih perusahaan lain.",
            )
        if not company:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Perusahaan tidak ditemukan.")
        if company.get("status") == "archived":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Perusahaan ini sudah diarsipkan.")

    modules: Set[str] = set()
    if company_id:
        modules = {r["module_key"] for r in module_rows}
        modules.add("hr_core")  # modul inti tidak dapat dimatikan

    return AuthContext(
        user=user,
        company=company,
        role_keys=info["role_keys"],
        permissions=info["permissions"],
        modules=modules,
        is_super_admin=info["is_super_admin"],
        request=request,
    )


async def get_auth_optional_company(
    request: Request, creds: HTTPAuthorizationCredentials = Depends(bearer)
) -> AuthContext:
    """Authenticated, but an active company is not required (login/switcher/profile)."""
    return await _base_auth(request, creds)


async def get_auth(
    request: Request, creds: HTTPAuthorizationCredentials = Depends(bearer)
) -> AuthContext:
    """Authenticated AND scoped to an active company (tenant context required)."""
    ctx = await _base_auth(request, creds)
    if ctx.company is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Perusahaan aktif belum dipilih. Gunakan pemilih perusahaan terlebih dahulu.",
        )
    return ctx


def require_permission(resource: str, action: str, module_key: Optional[str] = None):
    """Dependency factory: enforces module activation + permission."""
    needed_module = module_key or resource_module(resource)

    async def _dep(ctx: AuthContext = Depends(get_auth)) -> AuthContext:
        if not ctx.has_module(needed_module):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Modul terkait belum diaktifkan untuk perusahaan {ctx.company.get('name')}. "
                "Aktifkan modul di menu Aktivasi Modul.",
            )
        if not ctx.has_permission(resource, action):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Anda tidak memiliki hak akses untuk tindakan ini.",
            )
        return ctx

    return _dep


def require_super_admin():
    async def _dep(ctx: AuthContext = Depends(get_auth_optional_company)) -> AuthContext:
        if not ctx.is_super_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Super Admin yang dapat melakukan ini.")
        return ctx

    return _dep
