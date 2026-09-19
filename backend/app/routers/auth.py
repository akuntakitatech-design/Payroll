from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..core.audit import log_action, log_auth_event
from ..core.config import settings
from ..core.db import NO_ID, get_db, now
from ..core.deps import (
    AuthContext,
    accessible_companies,
    company_modules,
    effective_permissions,
    get_auth_optional_company,
)
from ..core.policy import POLICY_GROUPS
from ..core.rbac import RESOURCES, WILDCARD
from ..core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from ..schemas import ChangePasswordRequest, LoginRequest, RefreshRequest, SwitchCompanyRequest

router = APIRouter(prefix="/auth", tags=["Autentikasi"])


def _client_ip(request: Request) -> Optional[str]:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def _public_user(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        k: v
        for k, v in user.items()
        if k not in ("password_hash", "_id", "failed_login_attempts", "locked_until")
    }


async def build_session(user: Dict[str, Any], company_id: Optional[str]) -> Dict[str, Any]:
    info = await effective_permissions(user["id"], company_id)
    companies = await accessible_companies(user["id"])
    modules = await company_modules(company_id)
    db = get_db()
    company = await db.companies.find_one({"id": company_id}, NO_ID) if company_id else None
    return {
        "access_token": create_access_token(user["id"], company_id),
        "refresh_token": create_refresh_token(user["id"]),
        "token_type": "bearer",
        "user": _public_user(user),
        "active_company": company,
        "companies": companies,
        "role_keys": info["role_keys"],
        "permissions": sorted(info["permissions"]),
        "is_super_admin": info["is_super_admin"],
        "modules": sorted(modules),
    }


@router.post("/login")
async def login(payload: LoginRequest, request: Request):
    db = get_db()
    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email})
    ip, ua = _client_ip(request), request.headers.get("user-agent")

    if not user:
        await log_auth_event("login_failed", None, email, ip, ua, notes="Email tidak terdaftar")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email atau kata sandi salah.")

    locked_until = user.get("locked_until")
    if locked_until:
        if isinstance(locked_until, str):
            try:
                locked_until = datetime.fromisoformat(locked_until)
            except Exception:
                locked_until = None
        if locked_until and locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until and locked_until > datetime.now(timezone.utc):
            mins = max(1, int((locked_until - datetime.now(timezone.utc)).total_seconds() // 60) + 1)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Akun terkunci sementara karena terlalu banyak percobaan login. Coba lagi dalam {mins} menit.",
            )

    if not verify_password(payload.password, user.get("password_hash", "")):
        attempts = int(user.get("failed_login_attempts") or 0) + 1
        patch: Dict[str, Any] = {"failed_login_attempts": attempts, "updated_at": now()}
        if attempts >= settings.LOGIN_MAX_ATTEMPTS:
            patch["locked_until"] = datetime.now(timezone.utc) + timedelta(
                minutes=settings.LOGIN_LOCK_MINUTES
            )
            patch["failed_login_attempts"] = 0
        await db.users.update_one({"id": user["id"]}, {"$set": patch})
        # Attribute the failed attempt to the user's home company so company
        # administrators can actually see suspicious activity in their audit log.
        await log_auth_event(
            "login_failed",
            user,
            email,
            ip,
            ua,
            company_id=user.get("default_company_id"),
            notes="Kata sandi salah",
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email atau kata sandi salah.")

    if user.get("status") != "active":
        await log_auth_event(
            "login_blocked", user, email, ip, ua,
            company_id=user.get("default_company_id"), notes="Akun tidak aktif",
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Akun Anda tidak aktif. Hubungi administrator.")

    companies = await accessible_companies(user["id"])
    company_id = payload.company_id
    allowed_ids = [c["id"] for c in companies]
    if company_id and company_id not in allowed_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Anda tidak memiliki akses ke perusahaan tersebut.")
    if not company_id:
        preferred = user.get("default_company_id")
        company_id = preferred if preferred in allowed_ids else (allowed_ids[0] if allowed_ids else None)

    await db.users.update_one(
        {"id": user["id"]},
        {
            "$set": {
                "last_login_at": now(),
                "failed_login_attempts": 0,
                "locked_until": None,
                "default_company_id": company_id,
                "updated_at": now(),
            }
        },
    )
    user = await db.users.find_one({"id": user["id"]}, NO_ID)
    await log_auth_event("login", user, email, ip, ua, company_id=company_id)
    return await build_session(user, company_id)


@router.post("/refresh")
async def refresh(payload: RefreshRequest):
    try:
        data = decode_token(payload.refresh_token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesi Anda telah berakhir. Silakan login kembali.")
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token tidak valid.")
    if data.get("typ") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jenis token tidak sesuai.")
    db = get_db()
    user = await db.users.find_one({"id": data.get("sub")}, NO_ID)
    if not user or user.get("status") != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Pengguna tidak aktif.")
    return await build_session(user, user.get("default_company_id"))


@router.get("/me")
async def me(ctx: AuthContext = Depends(get_auth_optional_company)):
    companies = await accessible_companies(ctx.user_id)
    return {
        "user": _public_user(ctx.user),
        "active_company": ctx.company,
        "companies": companies,
        "role_keys": ctx.role_keys,
        "permissions": sorted(ctx.permissions),
        "is_super_admin": ctx.is_super_admin,
        "modules": sorted(ctx.modules),
    }


@router.get("/my-companies")
async def my_companies(ctx: AuthContext = Depends(get_auth_optional_company)):
    companies = await accessible_companies(ctx.user_id)
    db = get_db()
    out = []
    for c in companies:
        info = await effective_permissions(ctx.user_id, c["id"])
        mods = await company_modules(c["id"])
        out.append(
            {
                **c,
                "my_roles": info["role_keys"],
                "active_modules": sorted(mods),
                "is_active_company": c["id"] == ctx.company_id,
            }
        )
    return {"items": out, "total": len(out), "active_company_id": ctx.company_id}


@router.post("/switch-company")
async def switch_company(payload: SwitchCompanyRequest, ctx: AuthContext = Depends(get_auth_optional_company)):
    companies = await accessible_companies(ctx.user_id)
    if payload.company_id not in [c["id"] for c in companies]:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Anda tidak memiliki akses ke perusahaan tersebut. Hubungi administrator untuk meminta akses.",
        )
    db = get_db()
    await db.users.update_one(
        {"id": ctx.user_id}, {"$set": {"default_company_id": payload.company_id, "updated_at": now()}}
    )
    user = await db.users.find_one({"id": ctx.user_id}, NO_ID)
    await log_action(
        ctx,
        action="switch_company",
        resource="company",
        record_id=payload.company_id,
        company_id=payload.company_id,
        notes="Pengguna berganti perusahaan aktif",
    )
    return await build_session(user, payload.company_id)


@router.post("/change-password")
async def change_password(payload: ChangePasswordRequest, ctx: AuthContext = Depends(get_auth_optional_company)):
    db = get_db()
    full = await db.users.find_one({"id": ctx.user_id})
    if not verify_password(payload.current_password, full.get("password_hash", "")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kata sandi saat ini tidak sesuai.")
    await db.users.update_one(
        {"id": ctx.user_id},
        {"$set": {"password_hash": hash_password(payload.new_password), "updated_at": now()}},
    )
    await log_action(ctx, "change_password", "user", record_id=ctx.user_id, record_label=ctx.user.get("email"))
    return {"message": "Kata sandi berhasil diperbarui."}


@router.post("/logout")
async def logout(ctx: AuthContext = Depends(get_auth_optional_company)):
    await log_action(ctx, "logout", "user", record_id=ctx.user_id, record_label=ctx.user.get("email"))
    return {"message": "Anda telah keluar dari sistem."}


@router.get("/catalog")
async def catalog(ctx: AuthContext = Depends(get_auth_optional_company)):
    """Static catalogue used by the Roles & Permissions and Policy screens."""
    return {
        "resources": [
            {"key": k, "label": v[0], "module": v[1], "actions": v[2]} for k, v in RESOURCES.items()
        ],
        "policy_groups": POLICY_GROUPS,
        "wildcard": WILDCARD,
    }
