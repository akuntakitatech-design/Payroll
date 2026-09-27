"""Upgrade 01G-A - Public Employee Form (backend foundation).

ALUR RESMI 01G:
  PRIMARY  : Portal publik per tenant (kode perusahaan, immutable) -> Nomor Karyawan + NIK + Tanggal Lahir
             -> sesi publik terbatas -> draft -> submit -> PENDING_HR_VERIFICATION
  OPTIONAL : Undangan/link unik dari HR (exception flow, mis. kebutuhan khusus) - infrastruktur tetap tersedia.
Karyawan tanpa NIK/Tanggal Lahir: verifikasi standar ditolak aman (pesan generik), terlihat HR sebagai
"butuh fallback" (GET /employees/public-form/readiness). Tidak ada bypass link-only / PIN massal.

HR (login internal, RBAC existing - tanpa permission baru):
  GET  /api/employees/public-form/readiness                      kesiapan verifikasi + path portal (employee:view)
  POST /api/employees/{id}/public-form/invitations              buat link (employee:edit) - token mentah tampil SEKALI
  POST /api/employees/{id}/public-form/invitations/regenerate   = buat link baru (link aktif lama otomatis dicabut)
  GET  /api/employees/{id}/public-form/invitations              status link + submission (employee:view) - tanpa token
  POST /api/employees/{id}/public-form/invitations/{lid}/revoke cabut link (employee:edit) - langsung efektif

Publik - portal (PRIMARY):
  GET  /api/public/employee-form/portal/{company_code}          info portal (nama perusahaan) / 404 generik
  POST /api/public/employee-form/portal/{company_code}/verify   Nomor Karyawan + NIK + Tanggal Lahir -> sesi publik

Publik - undangan (OPTIONAL; token di BODY, bukan di URL/path agar tidak tercatat di access log):
  POST /api/public/employee-form/open        cek link (tanpa data karyawan)
  POST /api/public/employee-form/verify      Nomor Karyawan + NIK + Tanggal Lahir -> sesi publik terbatas

Publik - sesi (sama untuk kedua jalur):
  GET  /api/public/employee-form/form        prefill (termasking) + label master + kelengkapan 01F + draft
  PUT  /api/public/employee-form/draft       simpan draft (whitelist field; tidak menyentuh master)
  POST /api/public/employee-form/submit      DRAFT -> PENDING_HR_VERIFICATION (tidak menyentuh master)
  POST /api/public/employee-form/attachments lampiran private (belum dokumen resmi)
  DELETE /api/public/employee-form/attachments/{id}; GET .../attachments/{id}/file
  POST /api/public/employee-form/logout

Approval / apply ke Profile 360 / promosi dokumen / recalculate kelengkapan = Upgrade 01H
(routers/employee_update_verification.py). 01H: REVISION_REQUESTED = pengajuan yang sama dapat diedit & dikirim ulang.
"""
import hashlib
import json
import logging
import os
import re
import secrets
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..core import completeness as engine
from ..core import completeness_mapping as M
from ..core import form_builder as FB
from ..core import public_form as P
from ..core.audit import build_audit_entry, log_action
from ..core.branding_assets import is_tenant_logo_path
from ..core.db import NO_ID, get_db, new_id, now, transaction
from ..core.deps import AuthContext, require_permission
from ..core.sensitive import mask_value
from ..core.storage import APP_NAME, StorageError, get_object, put_object
from ..core.tenancy import get_tenant_db
from ..core.tenant_subscription import tenant_block_reason
from .employee_profile import RELATIONSHIPS, FamilyInput
from .employees import EDUCATIONS, GENDERS, MARITAL_STATUSES, RELIGIONS

logger = logging.getLogger("hris.public_form")

hr_router = APIRouter(prefix="/employees", tags=["public-employee-form"])
_view = require_permission("employee", "view")
_edit = require_permission("employee", "edit")
MODULE = "employee_core"
RESOURCE = "employee_public_form"

ENUMS = {
    "gender": [g["key"] for g in GENDERS],
    "marital": [m["key"] for m in MARITAL_STATUSES],
    "religion": [r["key"] for r in RELIGIONS],
    "education": [e["key"] for e in EDUCATIONS],
}
OPTIONS = {
    "gender": GENDERS, "marital": MARITAL_STATUSES, "religion": RELIGIONS, "education": EDUCATIONS,
    "relationship": [{"key": k, "label": v} for k, v in RELATIONSHIPS.items()],
}
_FIELD_TYPES = {"date": "date", "phone": "tel", "email": "email", "longtext": "textarea", "postal": "digits",
                "nik": "digits", "npwp": "digits", "bank_account": "digits", "bpjs": "digits"}


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"


public_router = APIRouter(prefix="/public/employee-form", tags=["public-employee-form"], dependencies=[Depends(_no_store)])


def _client_ip(request: Request) -> Optional[str]:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return request.client.host if request.client else None


class PublicActor:
    """Aktor audit untuk aksi publik (bukan user HRIS; tidak punya permission apa pun)."""
    user_id = None

    def __init__(self, company_id: str, ip: Optional[str], user_agent: Optional[str]):
        self.company_id = company_id
        self.ip = ip
        self.user_agent = (user_agent or "")[:500] or None
        self.user = {"full_name": "Karyawan (Formulir Publik)", "email": None}


def _serialize_dt(v: Any) -> Any:
    v = P.utc(v) if v is not None and not isinstance(v, str) else v
    return v.isoformat() if hasattr(v, "isoformat") else v


def _json(v: Any) -> Any:
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return None
    return v


def _link_out(link: Dict[str, Any]) -> Dict[str, Any]:
    locked = P.utc(link.get("locked_until"))
    return {
        "id": link["id"], "status": P.link_effective_status(link), "token_hint": link.get("token_hint"),
        "expires_at": _serialize_dt(link.get("expires_at")), "created_at": _serialize_dt(link.get("created_at")),
        "created_by": link.get("created_by"), "last_opened_at": _serialize_dt(link.get("last_opened_at")),
        "verified_at": _serialize_dt(link.get("verified_at")), "submitted_at": _serialize_dt(link.get("submitted_at")),
        "revoked_at": _serialize_dt(link.get("revoked_at")), "revoke_reason": link.get("revoke_reason"),
        "temporarily_locked": bool(locked and locked > now()),
        "total_failed_attempts": int(link.get("total_failed_attempts") or 0),
    }


async def _open_submission(tdb, company_id: str, employee_id: str) -> Optional[Dict[str, Any]]:
    return await tdb.employee_update_submissions.find_one(
        {"company_id": company_id, "employee_id": employee_id, "status": {"$in": list(P.OPEN_SUBMISSION_STATUSES)}}, NO_ID)


def _submission_out(sub: Optional[Dict[str, Any]], files: int = 0) -> Optional[Dict[str, Any]]:
    if not sub:
        return None
    return {"status": sub.get("status"), "status_label": _SUB_LABELS.get(sub.get("status")),
            "draft_saved_at": _serialize_dt(sub.get("draft_saved_at")), "submitted_at": _serialize_dt(sub.get("submitted_at")),
            "changed_fields": _json(sub.get("changed_fields")) or [], "identity_change": bool(sub.get("identity_change")),
            "attachments": files, "source": sub.get("source")}


_SUB_LABELS = {P.DRAFT: "Draft (belum dikirim)", P.PENDING: "Menunggu verifikasi HR",
               P.REVISION: "Perlu perbaikan (diminta HR)", P.APPROVED: "Disetujui HR", P.REJECTED: "Ditolak HR"}


# =================================================================== HR
class InvitationIn(BaseModel):
    expires_in_days: int = Field(P.LINK_DEFAULT_DAYS, ge=P.LINK_MIN_DAYS, le=P.LINK_MAX_DAYS)


class RevokeIn(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)


async def _hr_employee(ctx: AuthContext, employee_id: str) -> Dict[str, Any]:
    emp = await ctx.tdb.employees.find_one({"company_id": ctx.company_id, "id": employee_id, "status": {"$ne": "deleted"}}, NO_ID)
    if not emp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Karyawan tidak ditemukan pada perusahaan aktif Anda.")
    return emp


async def _revoke_active_links(ctx: AuthContext, employee_id: str, reason: str) -> List[str]:
    rows = await ctx.tdb.employee_public_links.find(
        {"company_id": ctx.company_id, "employee_id": employee_id, "status": {"$in": [P.ACTIVE, P.SUBMITTED]},
         "verification_mode": {"$ne": P.MODE_PORTAL}}, NO_ID).to_list(50)
    ids = []
    for link in rows:
        await ctx.tdb.employee_public_links.update_one({"id": link["id"]}, {"$set": {
            "status": P.REVOKED, "revoked_at": now(), "revoked_by": ctx.user_id, "revoke_reason": reason,
            "session_hash": None, "session_expires_at": None, "updated_at": now(), "updated_by": ctx.user_id}})
        await log_action(ctx, "public_link.revoke", RESOURCE, link["id"], None, None,
                         {"employee_id": employee_id, "token_hint": link.get("token_hint"), "reason": reason}, module=MODULE)
        ids.append(link["id"])
    return ids


@hr_router.get("/public-form/readiness")
async def verification_readiness(response: Response, ctx: AuthContext = Depends(_view)):
    """Kesiapan verifikasi portal per karyawan aktif (tanpa nilai NIK/Tanggal Lahir).
    `needs_fallback` = data verifikasi master belum lengkap -> tidak bisa lolos verifikasi standar."""
    _no_store(response)
    company = await get_db().companies.find_one({"id": ctx.company_id}, NO_ID) or {}
    rows = await ctx.tdb.employees.find(
        {"company_id": ctx.company_id, "status": "active"},
        {"_id": 0, "id": 1, "employee_number": 1, "full_name": 1, "nik": 1, "birth_date": 1}).to_list(20000)
    items = []
    for e in rows:
        gaps = P.verification_gaps(e)
        if gaps:
            items.append({"id": e["id"], "employee_number": e.get("employee_number"), "full_name": e.get("full_name"),
                          "verification_missing": gaps})
    items.sort(key=lambda x: (x.get("employee_number") or "", x.get("full_name") or ""))
    code = company.get("code")
    return {"portal_path": P.portal_path(code) if code else None, "company_code": code,
            "total_active": len(rows), "ready": len(rows) - len(items), "needs_fallback": len(items), "items": items[:1000],
            "note": "Karyawan 'needs_fallback' tidak dapat lolos verifikasi standar portal sampai data master dilengkapi "
                    "atau jalur fallback (exception) disepakati."}


@hr_router.post("/{employee_id}/public-form/invitations", status_code=201)
@hr_router.post("/{employee_id}/public-form/invitations/regenerate", status_code=201)
async def create_invitation(employee_id: str, response: Response, body: InvitationIn = InvitationIn(),
                            ctx: AuthContext = Depends(_edit)):
    _no_store(response)
    emp = await _hr_employee(ctx, employee_id)
    if emp.get("status") != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "Link formulir hanya dapat dibuat untuk karyawan berstatus aktif.")
    gaps = P.verification_gaps(emp)
    if gaps:
        return JSONResponse(status_code=422, content={
            "detail": "Data verifikasi karyawan belum lengkap: " + ", ".join(gaps)
                      + ". Lengkapi terlebih dahulu di Profile 360 sebelum membuat link.",
            "verification_missing": gaps})
    sub = await _open_submission(ctx.tdb, ctx.company_id, employee_id)
    if sub and sub.get("status") == P.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Masih ada pengajuan data yang menunggu verifikasi HR untuk karyawan ini. Link baru dapat dibuat setelah pengajuan diproses.")
    await _revoke_active_links(ctx, employee_id, "Diganti dengan link baru")
    token = P.new_token()
    link = {
        "id": new_id(), "company_id": ctx.company_id, "status": P.ACTIVE, "employee_id": employee_id,
        "token_hash": P.token_hash(token), "token_hint": P.token_hint(token), "verification_mode": P.MODE_IDENTITY,
        "expires_at": now() + P.timedelta(days=body.expires_in_days), "failed_attempts": 0, "total_failed_attempts": 0,
        "created_at": now(), "updated_at": now(), "created_by": ctx.user_id, "updated_by": ctx.user_id,
    }
    await ctx.tdb.employee_public_links.insert_one(dict(link))
    await log_action(ctx, "public_link.create", RESOURCE, link["id"], emp.get("employee_number"), None,
                     {"employee_id": employee_id, "token_hint": link["token_hint"], "expires_at": link["expires_at"].isoformat(),
                      "verification_mode": P.MODE_IDENTITY}, module=MODULE)
    return {"invitation": _link_out(link), "token": token, "path": f"/isi-data#{token}",
            "message": "Link formulir dibuat. Salin sekarang - link lengkap hanya ditampilkan sekali."}


@hr_router.get("/{employee_id}/public-form/invitations")
async def get_invitations(employee_id: str, response: Response, ctx: AuthContext = Depends(_view)):
    _no_store(response)
    emp = await _hr_employee(ctx, employee_id)
    links = await ctx.tdb.employee_public_links.find(
        {"company_id": ctx.company_id, "employee_id": employee_id, "verification_mode": {"$ne": P.MODE_PORTAL}},
        NO_ID).sort("created_at", -1).limit(10).to_list(10)
    out = [_link_out(x) for x in links]
    current = next((x for x in out if x["status"] in (P.ACTIVE, P.SUBMITTED)), None)
    sub = await _open_submission(ctx.tdb, ctx.company_id, employee_id)
    files = await ctx.tdb.employee_submission_files.count_documents(
        {"company_id": ctx.company_id, "submission_id": sub["id"], "status": "active"}) if sub else 0
    gaps = P.verification_gaps(emp)
    return {"current": current, "history": out, "submission": _submission_out(sub, files),
            "verification_ready": not gaps, "verification_missing": gaps, "eligible": emp.get("status") == "active"}


@hr_router.post("/{employee_id}/public-form/invitations/{invitation_id}/revoke")
async def revoke_invitation(employee_id: str, invitation_id: str, response: Response, body: RevokeIn = RevokeIn(),
                            ctx: AuthContext = Depends(_edit)):
    _no_store(response)
    await _hr_employee(ctx, employee_id)
    link = await ctx.tdb.employee_public_links.find_one(
        {"company_id": ctx.company_id, "employee_id": employee_id, "id": invitation_id}, NO_ID)
    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link tidak ditemukan.")
    if P.link_effective_status(link) not in (P.ACTIVE, P.SUBMITTED):
        raise HTTPException(status.HTTP_409_CONFLICT, "Link sudah tidak aktif (kedaluwarsa atau sudah dicabut).")
    reason = (body.reason or "").strip() or "Dicabut oleh HR"
    await ctx.tdb.employee_public_links.update_one({"id": invitation_id}, {"$set": {
        "status": P.REVOKED, "revoked_at": now(), "revoked_by": ctx.user_id, "revoke_reason": reason,
        "session_hash": None, "session_expires_at": None, "updated_at": now(), "updated_by": ctx.user_id}})
    await log_action(ctx, "public_link.revoke", RESOURCE, invitation_id, None, None,
                     {"employee_id": employee_id, "token_hint": link.get("token_hint"), "reason": reason}, module=MODULE)
    link = await ctx.tdb.employee_public_links.find_one({"id": invitation_id}, NO_ID)
    return {"invitation": _link_out(link), "message": "Link dicabut. Link dan sesi yang sedang berjalan tidak dapat dipakai lagi."}


# =================================================================== publik: akses link
class TokenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(..., max_length=200)


class VerifyIn(TokenIn):
    employee_number: str = Field(..., max_length=100)
    nik: str = Field(..., max_length=64)
    birth_date: str = Field(..., max_length=32)


def _invalid_link() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, P.MSG_LINK_INVALID)


def _too_many() -> HTTPException:
    return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, P.MSG_TOO_MANY)


async def _resolve_link(token: str, ip: Optional[str]):
    """Link valid + tenant aktif + karyawan aktif, atau HTTP 404 generik (tanpa membedakan penyebab)."""
    link = await P.find_link_by("token_hash", P.token_hash(token)) if 20 <= len(token or "") <= 200 else None
    if not link:
        await P.record_ip_failure(ip)
        raise _invalid_link()
    st = P.link_effective_status(link)
    if st == P.EXPIRED and link.get("status") == P.ACTIVE:
        await get_tenant_db(link["company_id"]).employee_public_links.update_one(
            {"id": link["id"]}, {"$set": {"status": P.EXPIRED, "session_hash": None, "updated_at": now()}})
    if st not in (P.ACTIVE, P.SUBMITTED):
        raise _invalid_link()
    company = await get_db().companies.find_one({"id": link["company_id"]}, NO_ID)
    if not company or tenant_block_reason(company):
        raise _invalid_link()
    tdb = get_tenant_db(link["company_id"])
    emp = await tdb.employees.find_one({"company_id": link["company_id"], "id": link["employee_id"]}, NO_ID)
    if not emp or emp.get("status") != "active":
        raise _invalid_link()
    return link, st, company, emp, tdb


@public_router.post("/open")
async def open_link(body: TokenIn, request: Request):
    ip = _client_ip(request)
    if await P.ip_locked(ip):
        raise _too_many()
    link, st, company, _emp, tdb = await _resolve_link(body.token, ip)
    await tdb.employee_public_links.update_one({"id": link["id"]}, {"$set": {"last_opened_at": now()}})
    return {"status": st, "company": {"name": company.get("name")},
            "verification_fields": [{"key": "employee_number", "label": "Nomor Karyawan"},
                                    {"key": "nik", "label": "NIK KTP"}, {"key": "birth_date", "label": "Tanggal Lahir"}],
            "message": P.MSG_SUBMITTED if st == P.SUBMITTED else None}


@public_router.post("/verify")
async def verify(body: VerifyIn, request: Request):
    ip, ua = _client_ip(request), request.headers.get("user-agent")
    if await P.ip_locked(ip):
        raise _too_many()
    link, st, _company, emp, tdb = await _resolve_link(body.token, ip)
    actor = PublicActor(link["company_id"], ip, ua)
    await P.link_release_expired_lock(link["id"])
    locked = P.utc(link.get("locked_until"))
    if locked and locked > now():
        raise _too_many()
    if not P.identity_matches(emp, body.employee_number, body.nik, body.birth_date):
        attempts, locked_now = await P.record_link_failure(link["id"])
        await P.record_ip_failure(ip)
        if attempts <= P.LINK_MAX_FAILS:
            await log_action(actor, "public_form.verify_failed", RESOURCE, link["id"], None, None,
                             {"attempt": attempts, "token_hint": link.get("token_hint")}, module=MODULE,
                             company_id=link["company_id"])
        if locked_now:
            await log_action(actor, "public_form.locked", RESOURCE, link["id"], None, None,
                             {"lock_minutes": int(P.LINK_LOCK.total_seconds() // 60), "token_hint": link.get("token_hint")},
                             module=MODULE, company_id=link["company_id"])
        raise HTTPException(status.HTTP_400_BAD_REQUEST, P.MSG_VERIFY_FAILED)
    session = P.new_token()
    expires = now() + P.SESSION_ABSOLUTE
    await tdb.employee_public_links.update_one({"id": link["id"]}, {"$set": {
        "failed_attempts": 0, "locked_until": None, "verified_at": now(), "session_hash": P.token_hash(session, "session"),
        "session_expires_at": expires, "session_verified_at": now(), "session_last_seen_at": now(), "updated_at": now()}})
    await log_action(actor, "public_form.verify_success", RESOURCE, link["id"], emp.get("employee_number"), None,
                     {"token_hint": link.get("token_hint")}, module=MODULE, company_id=link["company_id"])
    return {"session_token": session, "expires_at": expires.isoformat(),
            "idle_timeout_minutes": int(P.SESSION_IDLE.total_seconds() // 60), "status": st}


# =================================================================== publik: PORTAL (jalur utama)
_VERIFY_FIELDS = [{"key": "employee_number", "label": "Nomor Karyawan"},
                  {"key": "nik", "label": "NIK KTP"}, {"key": "birth_date", "label": "Tanggal Lahir"}]
# Pembanding dummy agar waktu respons "nomor tidak ada" ~ "nomor ada, data salah" (tanpa short-circuit).
_DUMMY_EMP = {"employee_number": "zz-none", "nik": "0" * 16, "birth_date": "1900-01-01"}


class PortalVerifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_number: str = Field(..., max_length=100)
    nik: str = Field(..., max_length=64)
    birth_date: str = Field(..., max_length=32)


def _portal_invalid() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, P.MSG_PORTAL_INVALID)


async def _resolve_portal(company_code: str, ip: Optional[str]) -> Dict[str, Any]:
    """Tenant dari kode perusahaan publik (unik & immutable). Tidak dikenal / nonaktif / kedaluwarsa -> 404 generik identik."""
    code = P.norm_company_code(company_code)
    company = await get_db().companies.find_one({"code": code}, NO_ID) if code else None
    if not company or tenant_block_reason(company):
        await P.record_ip_failure(ip)
        raise _portal_invalid()
    return company


@public_router.get("/portal/{company_code}")
async def portal_info(company_code: str, request: Request):
    ip = _client_ip(request)
    if await P.ip_locked(ip):
        raise _too_many()
    company = await _resolve_portal(company_code, ip)
    logo = company.get("logo_path")
    return {"flow": "PORTAL", "company": {"name": company.get("name"), "code": company.get("code"),
                                          "has_logo": bool(logo and is_tenant_logo_path(company["id"], logo))},
            "verification_fields": _VERIFY_FIELDS}


@public_router.get("/portal/{company_code}/logo")
async def portal_logo(company_code: str, request: Request):
    """Logo tenant untuk halaman portal (branding existing, read-only). Tanpa logo -> 404."""
    company = await _resolve_portal(company_code, _client_ip(request))
    path = company.get("logo_path")
    if not path or not is_tenant_logo_path(company["id"], path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Logo tidak tersedia.")
    try:
        data, content_type = get_object(path)
    except StorageError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Logo tidak tersedia.") from None
    return Response(content=data, media_type=content_type, headers={
        "Cache-Control": "public, max-age=300", "X-Content-Type-Options": "nosniff"})


@public_router.post("/portal/{company_code}/verify")
async def portal_verify(company_code: str, body: PortalVerifyIn, request: Request):
    ip, ua = _client_ip(request), request.headers.get("user-agent")
    if await P.ip_locked(ip):
        raise _too_many()
    company = await _resolve_portal(company_code, ip)
    cid = company["id"]
    tdb = get_tenant_db(cid)
    tkey = P.target_key(cid, body.employee_number)
    if await P.rate_locked(tkey):
        raise _too_many()  # terkunci sementara - juga bila data yang dimasukkan benar
    actor = PublicActor(cid, ip, ua)
    emp_no = (body.employee_number or "").strip()
    candidates = await tdb.employees.find(
        {"company_id": cid, "employee_number": emp_no, "status": "active"}, NO_ID).to_list(5) if 0 < len(emp_no) <= 64 else []
    matches = [e for e in candidates if P.identity_matches(e, body.employee_number, body.nik, body.birth_date)]
    if not candidates:
        P.identity_matches(_DUMMY_EMP, body.employee_number, body.nik, body.birth_date)
    if len(matches) != 1:
        count, locked_now = await P.record_failure(tkey, "verify_target", P.TARGET_MAX_FAILS, P.TARGET_WINDOW, P.TARGET_LOCK)
        await P.record_ip_failure(ip)
        target = candidates[0] if len(candidates) == 1 else None
        details = {"channel": "PORTAL", "attempt": count, "employee_matched": bool(target),
                   "needs_fallback": bool(target and P.verification_gaps(target))}
        rid, label = (target["id"], target.get("employee_number")) if target else (None, None)
        if count <= P.TARGET_MAX_FAILS:
            await log_action(actor, "public_form.verify_failed", RESOURCE, rid, label, None, details,
                             module=MODULE, company_id=cid)
        if locked_now:
            await log_action(actor, "public_form.locked", RESOURCE, rid, label, None,
                             {"channel": "PORTAL", "lock_minutes": int(P.TARGET_LOCK.total_seconds() // 60)},
                             module=MODULE, company_id=cid)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, P.MSG_VERIFY_FAILED)
    emp = matches[0]
    await P.rate_reset(tkey)
    sub = await _open_submission(tdb, cid, emp["id"])
    st = P.SUBMITTED if sub and sub.get("status") == P.PENDING else P.ACTIVE
    # satu sesi portal aktif per karyawan: sesi portal sebelumnya langsung tidak berlaku
    await tdb.employee_public_links.update_many(
        {"company_id": cid, "employee_id": emp["id"], "verification_mode": P.MODE_PORTAL, "status": {"$in": [P.ACTIVE, P.SUBMITTED]}},
        {"$set": {"session_hash": None, "session_expires_at": None, "updated_at": now()}})
    session, t = P.new_token(), now()
    expires = t + P.SESSION_ABSOLUTE
    row = {"id": new_id(), "company_id": cid, "status": st, "employee_id": emp["id"], "token_hash": None, "token_hint": None,
           "verification_mode": P.MODE_PORTAL, "expires_at": expires, "failed_attempts": 0, "total_failed_attempts": 0,
           "verified_at": t, "session_hash": P.token_hash(session, "session"), "session_expires_at": expires,
           "session_verified_at": t, "session_last_seen_at": t, "submission_id": sub["id"] if st == P.SUBMITTED else None,
           "created_at": t, "updated_at": t}
    await tdb.employee_public_links.insert_one(dict(row))
    await log_action(actor, "public_form.verify_success", RESOURCE, row["id"], emp.get("employee_number"), None,
                     {"channel": "PORTAL", "employee_id": emp["id"]}, module=MODULE, company_id=cid)
    return {"session_token": session, "expires_at": expires.isoformat(),
            "idle_timeout_minutes": int(P.SESSION_IDLE.total_seconds() // 60), "status": st, "flow": "PORTAL"}


# =================================================================== publik: sesi
@dataclass
class PublicSession:
    link: Dict[str, Any]
    status: str
    company: Dict[str, Any]
    employee: Dict[str, Any]
    ip: Optional[str]
    user_agent: Optional[str]

    @property
    def company_id(self) -> str:
        return self.link["company_id"]

    @property
    def employee_id(self) -> str:
        return self.link["employee_id"]

    @property
    def tdb(self):
        return get_tenant_db(self.company_id)

    @property
    def actor(self) -> PublicActor:
        return PublicActor(self.company_id, self.ip, self.user_agent)


def _session_invalid() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, P.MSG_SESSION_INVALID)


async def get_public_session(request: Request) -> PublicSession:
    auth = request.headers.get("authorization") or ""
    raw = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not (20 <= len(raw) <= 200):
        raise _session_invalid()
    link = await P.find_link_by("session_hash", P.token_hash(raw, "session"))
    if not link:
        raise _session_invalid()
    st = P.link_effective_status(link)
    t = now()
    exp, seen = P.utc(link.get("session_expires_at")), P.utc(link.get("session_last_seen_at"))
    if st not in (P.ACTIVE, P.SUBMITTED) or not exp or exp <= t or not seen or seen + P.SESSION_IDLE <= t:
        raise _session_invalid()
    company = await get_db().companies.find_one({"id": link["company_id"]}, NO_ID)
    if not company or tenant_block_reason(company):
        raise _session_invalid()
    tdb = get_tenant_db(link["company_id"])
    emp = await tdb.employees.find_one({"company_id": link["company_id"], "id": link["employee_id"]}, NO_ID)
    if not emp or emp.get("status") != "active":
        raise _session_invalid()
    if seen + P.SESSION_TOUCH_EVERY <= t:
        await tdb.employee_public_links.update_one({"id": link["id"]}, {"$set": {"session_last_seen_at": t}})
    return PublicSession(link, st, company, emp, _client_ip(request), request.headers.get("user-agent"))


@public_router.post("/logout")
async def logout(sess: PublicSession = Depends(get_public_session)):
    await sess.tdb.employee_public_links.update_one({"id": sess.link["id"]}, {"$set": {
        "session_hash": None, "session_expires_at": None, "updated_at": now()}})
    return {"message": "Sesi formulir diakhiri."}


# =================================================================== publik: form
_CONTACT_CODES = {"PERSONAL.PHONE", "PERSONAL.EMAIL", "PERSONAL.ADDRESS_KTP", "PERSONAL.DOMICILE", "PERSONAL.EMERGENCY_CONTACT"}
_OPEN_ITEM = {M.MISSING, M.INVALID, M.EXPIRED, M.UNVERIFIED}
_SECTION_LABELS = dict(P.SECTIONS)


def _section_for(code: str) -> Optional[str]:
    if code in _CONTACT_CODES:
        return "contact"
    if code.startswith("PERSONAL."):
        return "personal"
    if code.startswith("BANK.") or code == "TAX.NPWP":
        return "bank_tax"
    if code.startswith("BPJS."):
        return "bpjs"
    if code.startswith("FAMILY."):
        return "family"
    if code.startswith("DOC."):
        return "documents"
    return None  # EMPLOYMENT/PLACEMENT/CONTRACT/CERT/TAX.PTKP -> dikelola HR


async def _completeness(sess: PublicSession) -> Dict[str, Any]:
    """Kelengkapan resmi = snapshot MASTER 01F. Draft/submission tidak pernah dihitung."""
    rules = await engine.load_rules(sess.company_id)
    by_code = {r.code: r for r in rules["requirements"]}
    flt = {"company_id": sess.company_id, "employee_id": sess.employee_id}
    snap = await sess.tdb.employee_completeness.find_one(flt, NO_ID)
    if not snap or snap.get("is_stale") or snap.get("rules_hash") != rules["rules_hash"]:
        await engine.refresh(sess.company_id, [sess.employee_id], "on_read", None)
        snap = await sess.tdb.employee_completeness.find_one(flt, NO_ID)
    if not snap:
        return {"available": False}
    items, hr_missing = [], 0
    for it in _json(snap.get("items")) or []:
        if it.get("status") not in _OPEN_ITEM or it.get("level") not in (M.REQUIRED, M.RECOMMENDED):
            continue
        section = _section_for(it.get("code", ""))
        if not section:
            hr_missing += 1
            continue
        req = by_code.get(it["code"])
        items.append({"code": it["code"], "label": req.label if req else it["code"], "level": it["level"],
                      "level_label": M.LEVEL_LABELS.get(it["level"]), "status": it["status"],
                      "status_label": M.STATUS_LABELS.get(it["status"]), "section": section,
                      "section_label": _SECTION_LABELS.get(section)})
    items.sort(key=lambda x: (x["level"] != M.REQUIRED, x["section"]))
    return {"available": True, "score_pct": snap.get("score_pct"), "status": snap.get("completeness_status"),
            "required_total": snap.get("required_total"), "required_fulfilled": snap.get("required_fulfilled"),
            "recommended_total": snap.get("recommended_total"), "recommended_fulfilled": snap.get("recommended_fulfilled"),
            "evaluated_at": _serialize_dt(snap.get("evaluated_at")), "missing": items, "hr_managed_missing": hr_missing,
            "note": "Persentase dihitung dari data yang sudah tercatat/terverifikasi HR. Draft dan data yang menunggu verifikasi belum dihitung."}


async def _label(tdb, table: str, company_id: str, rid: Optional[str]) -> Optional[str]:
    if not rid:
        return None
    row = await getattr(tdb, table).find_one({"company_id": company_id, "id": rid}, {"name": 1})
    return row.get("name") if row else None


def _mask_proposed(proposed: Dict[str, Any]) -> Dict[str, Any]:
    fields = {}
    for k, v in (proposed.get("fields") or {}).items():
        fields[k] = {"masked": mask_value(v), "has_value": True} if k in P.SENSITIVE_FIELDS else v
    family = []
    for op in proposed.get("family") or []:
        data = dict(op.get("data") or {})
        if data.get("nik"):
            data["nik"] = mask_value(data["nik"])
        family.append({**op, "data": data or None})
    return {"fields": fields, "family": family, "notes": proposed.get("notes"), "no_npwp": bool(proposed.get("no_npwp")),
            "custom": proposed.get("custom") or {}}


async def _doc_types(sess: PublicSession) -> List[Dict[str, Any]]:
    rows = await sess.tdb.document_types.find({"company_id": sess.company_id, "owner_scope": "employee",
                                               "status": {"$nin": ["deleted", "inactive", "archived"]}}, NO_ID).to_list(200)
    return rows


def _allowed_ext(doc_type: Optional[Dict[str, Any]]) -> List[str]:
    if doc_type is None:
        return sorted(P.PHOTO_EXTENSIONS)
    declared = {e.strip().lower() for e in (doc_type.get("allowed_extensions") or "").split(",") if e.strip()}
    return sorted(P.PUBLIC_EXTENSIONS & declared) if declared else sorted(P.PUBLIC_EXTENSIONS)


def _max_mb(doc_type: Optional[Dict[str, Any]]) -> float:
    declared = float((doc_type or {}).get("max_size_mb") or P.PUBLIC_MAX_MB)
    return min(declared, P.PUBLIC_MAX_MB)


def _file_out(f: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": f["id"], "document_type_code": f.get("document_type_code"), "purpose": f.get("purpose"), "field_key": f.get("field_key"),
            "file_name": f.get("file_name"), "file_size": f.get("file_size"), "mime_type": f.get("mime_type"),
            "uploaded_at": _serialize_dt(f.get("uploaded_at"))}


async def _form_layout(sess: PublicSession):
    """-> (config, layout, visible custom definitions, official custom values). 01F snapshot is only READ here."""
    cfg = await FB.load_config(sess.company_id)
    snap = await sess.tdb.employee_completeness.find_one({"company_id": sess.company_id, "employee_id": sess.employee_id}, NO_ID) or {}
    items = _json(snap.get("items")) or []
    if items:
        levels, forced, forced_sec = FB.levels_from_snapshot(items)
    else:  # no 01F snapshot yet -> conservative: rule-REQUIRED core fields stay visible
        levels, forced, forced_sec = FB.levels_without_snapshot(await engine.load_rules(sess.company_id))
    layout = FB.resolve_layout(cfg, levels, forced, forced_sec, sess.employee, await FB.scope_context(sess.company_id, sess.employee))
    defs = FB.visible_custom(layout, cfg)
    official = {}
    if defs:
        for r in await sess.tdb.employee_custom_field_values.find(
                {"company_id": sess.company_id, "employee_id": sess.employee_id, "status": {"$ne": "deleted"}}, NO_ID).to_list(500):
            official[r["field_key"]] = r.get("value")  # 01H: kolom JSON sudah didekode layer DB (nilai string polos tetap utuh)
    return cfg, layout, defs, official


@public_router.get("/form")
async def get_form(sess: PublicSession = Depends(get_public_session)):
    emp, cid, tdb = sess.employee, sess.company_id, sess.tdb
    sub = await _open_submission(tdb, cid, sess.employee_id)
    read_only = sess.status == P.SUBMITTED or (sub and sub.get("status") == P.PENDING)
    fields = []
    for key, (section, label, validator, sensitive, identity) in P.EDITABLE_FIELDS.items():
        value = emp.get(key)
        item = {"key": key, "label": label, "section": section, "type": _FIELD_TYPES.get(validator, "text"),
                "sensitive": sensitive, "identity": identity, "has_value": value not in (None, "")}
        if validator and validator.startswith("enum:"):
            item["type"], item["options"] = "select", validator[5:]
        if sensitive:
            item["value"], item["masked"] = None, mask_value(value) if value else None
        else:
            item["value"] = value
        fields.append(item)
    family_rows = await tdb.employee_family_members.find(
        {"company_id": cid, "employee_id": sess.employee_id, "status": {"$ne": "deleted"}}, NO_ID).to_list(100)
    family = [{"ref": r["id"], "relationship": r.get("relationship"),
               "relationship_label": RELATIONSHIPS.get(r.get("relationship"), r.get("relationship")),
               "full_name": r.get("full_name"), "nik_masked": mask_value(r.get("nik")) if r.get("nik") else None,
               "birth_place": r.get("birth_place"), "birth_date": r.get("birth_date"), "gender": r.get("gender"),
               "occupation": r.get("occupation"), "is_emergency_contact": bool(r.get("is_emergency_contact")),
               "phone": r.get("phone")} for r in family_rows]
    documents = []
    for dt in await _doc_types(sess):
        has = await tdb.documents.count_documents({"company_id": cid, "owner_type": "employee", "owner_id": sess.employee_id,
                                                   "document_type_id": dt["id"], "is_deleted": {"$ne": True},
                                                   "status": {"$ne": "deleted"}})
        documents.append({"code": dt.get("code"), "name": dt.get("name"), "is_mandatory": bool(dt.get("is_mandatory")),
                          "allowed_extensions": _allowed_ext(dt), "max_size_mb": _max_mb(dt), "has_existing": has > 0})
    documents.append({"code": P.PHOTO_CODE, "name": "Foto profil", "is_mandatory": False,
                      "allowed_extensions": _allowed_ext(None), "max_size_mb": P.PUBLIC_MAX_MB,
                      "has_existing": bool(emp.get("photo_path"))})
    draft = None
    revision, last_decision = None, None
    if sub and sub.get("status") == P.REVISION:  # Upgrade 01H: HR meminta perbaikan -> form dapat diedit lagi
        hist = _json(sub.get("review_history")) or []
        last = hist[-1] if hist else {}
        revision = {"note": sub.get("review_note"), "items": last.get("items") or [],
                    "requested_at": _serialize_dt(sub.get("reviewed_at")), "round": int(sub.get("revision_count") or 0)}
    if not sub:  # Upgrade 01H: keputusan final terakhir (tanpa nilai data)
        rows = await tdb.employee_update_submissions.find(
            {"company_id": cid, "employee_id": sess.employee_id, "status": {"$in": list(P.FINAL_SUBMISSION_STATUSES)}},
            {"_id": 0, "status": 1, "review_note": 1, "reviewed_at": 1}).sort("reviewed_at", -1).limit(1).to_list(1)
        if rows:
            r = rows[0]
            last_decision = {"status": r.get("status"), "status_label": _SUB_LABELS.get(r.get("status")),
                             "reason": r.get("review_note") if r.get("status") == P.REJECTED else None,
                             "decided_at": _serialize_dt(r.get("reviewed_at"))}
    if sub:
        files = await tdb.employee_submission_files.find(
            {"company_id": cid, "submission_id": sub["id"], "status": "active"}, NO_ID).sort("uploaded_at", 1).to_list(50)
        draft = {**_submission_out(sub, len(files)), "version": sub.get("version"),
                 "proposed": _mask_proposed(_json(sub.get("proposed")) or {}), "files": [_file_out(f) for f in files]}
    # Enhancement 01G Form Builder: layout dinamis (section/urutan/label/visibility/scope/custom) per karyawan.
    completeness = await _completeness(sess)
    cfg, layout, custom_defs, official = await _form_layout(sess)
    shown = {i["key"]: i for st in layout["steps"] for i in st["fields"]}
    # Final rule (01G-FB): a core field hidden by the builder and NOT forced by 01F REQUIRED is not sent at all
    # (no editable field, no prefill). Forced REQUIRED fields are always part of the layout.
    fields = [f for f in fields if f["key"] in shown]
    if draft and isinstance(draft.get("proposed"), dict):
        draft["proposed"]["fields"] = {k: v for k, v in (draft["proposed"].get("fields") or {}).items() if k in shown}
    for item in fields:
        lay = shown.get(item["key"])
        if lay:
            item["label"], item["help_text"], item["placeholder"] = lay["label"], lay.get("help_text"), lay.get("placeholder")
    custom_fields = [{"key": k, "label": d["label"], "type": d["type"], "help_text": d.get("help_text"),
                      "placeholder": d.get("placeholder"), "level": d["form_level"], "level_label": FB.LEVEL_LABELS[d["form_level"]],
                      "options": [o for o in d["options"] if o.get("active", True)], "validation": d["validation"],
                      "value": official.get(k)} for k, d in custom_defs.items()]
    view_only = {
        "company_name": sess.company.get("name"), "employee_number": emp.get("employee_number"),
        "position": await _label(tdb, "positions", cid, emp.get("position_id")) or emp.get("job_title"),
        "department": await _label(tdb, "departments", cid, emp.get("department_id")),
        "work_location": await _label(tdb, "work_locations", cid, emp.get("work_location_id")),
        "employment_status": await _label(tdb, "employment_statuses", cid, emp.get("employment_status_id")),
        "join_date": emp.get("join_date"),
    }
    return {"mode": "READ_ONLY" if read_only else "EDIT", "message": P.MSG_SUBMITTED if read_only else None,
            "sections": [{"key": k, "label": v} for k, v in P.SECTIONS], "view_only": view_only, "fields": fields,
            "family": family, "documents": documents, "options": OPTIONS, "completeness": completeness,
            "layout": layout, "custom_fields": custom_fields, "revision": revision, "last_decision": last_decision,
            "draft": draft, "session": {"expires_at": _serialize_dt(sess.link.get("session_expires_at")),
                                        "idle_timeout_minutes": int(P.SESSION_IDLE.total_seconds() // 60)}}


# =================================================================== publik: draft & submit
class FamilyOp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["add", "update", "remove"]
    ref: Optional[str] = Field(None, max_length=64)
    data: Optional[Dict[str, Any]] = None
    reason: Optional[str] = Field(None, max_length=500)


class DraftIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Optional[int] = None
    fields: Dict[str, Any] = Field(default_factory=dict)
    family: List[FamilyOp] = Field(default_factory=list)
    notes: Optional[str] = Field(None, max_length=2000)
    no_npwp: Optional[bool] = None
    custom: Dict[str, Any] = Field(default_factory=dict)  # Enhancement 01G Form Builder (cf_* only)


class SubmitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int


def _reject(detail: str, errors: Optional[Dict[str, str]] = None, **extra) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": detail, "errors": errors or {}, **extra})


def _clean_draft(body: DraftIn, emp: Dict[str, Any], family_ids: set, custom_defs: Optional[Dict[str, Any]] = None,
                 official: Optional[Dict[str, Any]] = None, allowed_core: Optional[set] = None):
    """-> (proposed, errors, rejected_fields). Kosong = tidak ada perubahan (tidak menghapus master).
    Custom answers: only ACTIVE + VISIBLE `cf_*` definitions for this employee; never merged into core/master fields.
    `allowed_core` (Form Builder): core fields in the employee's final layout; a hidden, non-REQUIRED core field is rejected."""
    custom_defs, official = custom_defs or {}, official or {}
    rejected = sorted(k for k in body.fields if k not in P.EDITABLE_FIELDS or (allowed_core is not None and k not in allowed_core))
    if body.no_npwp and allowed_core is not None and "npwp" not in allowed_core:
        rejected.append("no_npwp")
    rejected += sorted(k for k in body.custom if k not in custom_defs or custom_defs[k].get("type") == "file")
    errors: Dict[str, str] = {}
    fields: Dict[str, Any] = {}
    for key, raw in body.fields.items():
        if key in rejected:
            continue
        if raw is not None and not isinstance(raw, (str, int, float)):
            errors[key] = "Format nilai tidak valid."
            continue
        val = P.normalize_value(key, raw)
        if val is None:
            continue
        msg = P.validate_field(key, val, ENUMS)
        if msg:
            errors[key] = msg
            continue
        if P.normalize_value(key, emp.get(key)) == val:
            continue  # sama dengan data saat ini -> bukan perubahan
        fields[key] = val
    if body.no_npwp and fields.get("npwp"):
        errors["npwp"] = "Kosongkan NPWP jika Anda menyatakan tidak memiliki NPWP."
    family: List[Dict[str, Any]] = []
    if len(body.family) > P.MAX_FAMILY_OPS:
        errors["family"] = f"Maksimal {P.MAX_FAMILY_OPS} perubahan data keluarga per pengajuan."
    seen_refs = set()
    for i, op in enumerate(body.family[:P.MAX_FAMILY_OPS]):
        if op.op in ("update", "remove"):
            if not op.ref or op.ref not in family_ids:
                errors[f"family[{i}]"] = "Anggota keluarga tidak ditemukan."
                continue
            if op.ref in seen_refs:
                errors[f"family[{i}]"] = "Anggota keluarga yang sama diubah lebih dari sekali."
                continue
            seen_refs.add(op.ref)
        if op.op == "remove":
            family.append({"op": "remove", "ref": op.ref, "reason": (op.reason or "").strip() or None})
            continue
        data = op.data or {}
        unknown = sorted(k for k in data if k not in P.FAMILY_EDITABLE)
        if unknown:
            errors[f"family[{i}]"] = "Field keluarga tidak dikenal: " + ", ".join(unknown)
            continue
        try:
            fam = FamilyInput(**{k: data.get(k) for k in P.FAMILY_EDITABLE if data.get(k) is not None})
        except ValidationError as exc:
            first = exc.errors()[0]
            loc = first.get("loc", ["?"])[-1]
            errors[f"family[{i}].{loc}"] = str(first.get("msg", "Tidak valid")).replace("Value error, ", "")
            continue
        if fam.phone and not P.V.phone_ok(fam.phone):
            errors[f"family[{i}].phone"] = "Nomor HP tidak valid."
            continue
        clean = {k: v for k, v in fam.model_dump().items() if v not in (None, "")}
        family.append({"op": op.op, "ref": op.ref if op.op == "update" else None, "data": clean})
    custom: Dict[str, Any] = {}
    for key, raw in body.custom.items():
        if key in rejected:
            continue
        val, msg = FB.validate_custom(custom_defs[key], raw)
        if msg:
            errors[key] = msg
            continue
        if val is None or val == official.get(key):
            continue
        custom[key] = val
    proposed = {"fields": fields, "family": family, "notes": (body.notes or "").strip() or None,
                "no_npwp": bool(body.no_npwp), "custom": custom}
    return proposed, errors, rejected


async def _family_ids(sess: PublicSession) -> set:
    rows = await sess.tdb.employee_family_members.find(
        {"company_id": sess.company_id, "employee_id": sess.employee_id, "status": {"$ne": "deleted"}}, {"id": 1}).to_list(200)
    return {r["id"] for r in rows}


def _changed_names(proposed: Dict[str, Any]) -> List[str]:
    names = sorted((proposed.get("fields") or {}).keys()) + sorted((proposed.get("custom") or {}).keys())
    if proposed.get("family"):
        names.append("family")
    if proposed.get("no_npwp"):
        names.append("no_npwp")
    return names


def _ensure_editable(sess: PublicSession, sub: Optional[Dict[str, Any]]) -> None:
    if sess.status == P.SUBMITTED or (sub and sub.get("status") == P.PENDING):
        raise HTTPException(status.HTTP_409_CONFLICT, P.MSG_SUBMITTED)


async def _new_draft(sess: PublicSession, proposed: Dict[str, Any]) -> Dict[str, Any]:
    doc = {"id": new_id(), "company_id": sess.company_id, "status": P.DRAFT, "employee_id": sess.employee_id,
           "link_id": sess.link["id"], "source": P.SOURCE, "open_slot": sess.employee_id, "proposed": proposed,
           "version": 1, "draft_saved_at": now(), "created_at": now(), "updated_at": now()}
    try:
        await sess.tdb.employee_update_submissions.insert_one(dict(doc))
    except HTTPException as exc:
        if exc.status_code == 409:  # unique open_slot: sudah ada draft/pending lain (race)
            raise HTTPException(status.HTTP_409_CONFLICT, "Draft sedang diperbarui dari perangkat lain. Muat ulang formulir.") from None
        raise
    return doc


def _restore_masked(body: "DraftIn", stored: Dict[str, Any]) -> None:
    """Resume draft (01G-B): nilai sensitif draft dikirim ke browser dalam bentuk termasking. Bila klien mengirim
    kembali PERSIS nilai masking dari draft tersimpan, server memakai nilai asli tersimpan (nilai asli tidak pernah
    dikirim ke browser). Nilai baru (tanpa '*') diproses & divalidasi normal."""
    sf = stored.get("fields") or {}
    for k, v in list(body.fields.items()):
        if k in P.SENSITIVE_FIELDS and isinstance(v, str) and "*" in v and sf.get(k) and v == mask_value(sf[k]):
            body.fields[k] = sf[k]
    niks: Dict[str, List[str]] = {}
    for op in stored.get("family") or []:
        n = (op.get("data") or {}).get("nik")
        if n:
            niks.setdefault(mask_value(n), []).append(n)
    for op in body.family:
        n = (op.data or {}).get("nik")
        if isinstance(n, str) and "*" in n and len(niks.get(n, [])) == 1:
            op.data["nik"] = niks[n][0]


@public_router.put("/draft")
async def save_draft(body: DraftIn, sess: PublicSession = Depends(get_public_session)):
    sub = await _open_submission(sess.tdb, sess.company_id, sess.employee_id)
    _ensure_editable(sess, sub)
    if sub:
        _restore_masked(body, _json(sub.get("proposed")) or {})
    cfg, layout, custom_defs, official = await _form_layout(sess)
    proposed, errors, rejected = _clean_draft(body, sess.employee, await _family_ids(sess), custom_defs, official,
                                              FB.shown_core(layout))
    proposed["meta"] = {"form_version": cfg["version"]}
    if rejected:
        return _reject("Field berikut tidak dapat diubah melalui formulir ini: " + ", ".join(rejected) + ".",
                       rejected_fields=rejected)
    if errors:
        return _reject("Periksa kembali isian yang ditandai.", errors)
    if not sub:
        if body.version not in (None, 0):
            raise HTTPException(status.HTTP_409_CONFLICT, "Draft tidak ditemukan. Muat ulang formulir.")
        sub = await _new_draft(sess, proposed)
        version = 1
    else:
        if body.version != sub.get("version"):
            raise HTTPException(status.HTTP_409_CONFLICT, "Draft telah diperbarui dari tab/perangkat lain. Muat ulang formulir.")
        version = int(sub.get("version") or 1) + 1
        res = await sess.tdb.employee_update_submissions.update_one(
            {"id": sub["id"], "status": {"$in": list(P.EDITABLE_SUBMISSION_STATUSES)}, "version": sub.get("version")},
            {"$set": {"proposed": proposed, "version": version, "draft_saved_at": now(), "updated_at": now(),
                      "link_id": sess.link["id"]}})
        if not res.matched_count:
            raise HTTPException(status.HTTP_409_CONFLICT, "Draft telah diperbarui dari tab/perangkat lain. Muat ulang formulir.")
    changed = _changed_names(proposed)
    await log_action(sess.actor, "public_form.draft_saved", RESOURCE, sub["id"], None, None,
                     {"changed_fields": changed, "family_ops": len(proposed["family"]), "version": version},
                     module=MODULE, company_id=sess.company_id)
    return {"message": "Draft tersimpan. Data belum dikirim ke HR.", "version": version,
            "draft_saved_at": now().isoformat(), "changed_fields": changed}


@public_router.post("/submit")
async def submit(body: SubmitIn, sess: PublicSession = Depends(get_public_session)):
    tdb, cid, emp = sess.tdb, sess.company_id, sess.employee
    sub = await _open_submission(tdb, cid, sess.employee_id)
    _ensure_editable(sess, sub)
    if not sub:
        raise HTTPException(status.HTTP_409_CONFLICT, "Belum ada draft. Simpan draft terlebih dahulu.")
    if body.version != sub.get("version"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Draft telah diperbarui dari tab/perangkat lain. Muat ulang formulir.")
    stored = _json(sub.get("proposed")) or {}
    cfg, layout, custom_defs, official = await _form_layout(sess)
    allowed_core = FB.shown_core(layout)
    # answers for fields that HR has since deactivated/hidden (custom, or core not REQUIRED by 01F) are dropped (never applied)
    stored_custom = {k: v for k, v in (stored.get("custom") or {}).items() if k in custom_defs and custom_defs[k].get("type") != "file"}
    stored_fields = {k: v for k, v in (stored.get("fields") or {}).items() if k in allowed_core}
    try:
        again = DraftIn(fields=stored_fields, family=stored.get("family") or [],
                        notes=stored.get("notes"), no_npwp=bool(stored.get("no_npwp")) and "npwp" in allowed_core, custom=stored_custom)
    except ValidationError:
        return _reject("Draft tidak valid. Simpan ulang draft Anda.")
    family_ids = await _family_ids(sess)
    proposed, errors, rejected = _clean_draft(again, emp, family_ids, custom_defs, official, allowed_core)
    if errors or rejected:
        return _reject("Periksa kembali isian yang ditandai sebelum mengirim.", errors)
    active_files = await tdb.employee_submission_files.find(
        {"company_id": cid, "submission_id": sub["id"], "status": "active"}, {"field_key": 1}).to_list(100)
    files = len(active_files)
    file_keys = {f.get("field_key") for f in active_files if f.get("field_key")}
    missing = {}
    for k, d in custom_defs.items():
        if d["form_level"] != "REQUIRED":
            continue
        ok = (k in file_keys) if d["type"] == "file" else (proposed["custom"].get(k) is not None or official.get(k) not in (None, "", []))
        if not ok:
            missing[k] = "Wajib diisi."
    if missing:
        return _reject("Masih ada pertanyaan wajib yang belum diisi.", missing)
    proposed["meta"] = {"form_version": cfg["version"]}
    if not proposed["fields"] and not proposed["family"] and not proposed["no_npwp"] and not proposed["custom"] and not files:
        return _reject("Belum ada perubahan data atau dokumen yang diajukan.")
    baseline_fields = {k: emp.get(k) for k in proposed["fields"]}
    baseline_custom = {k: official.get(k) for k in proposed["custom"]}
    refs = [op["ref"] for op in proposed["family"] if op.get("ref")]
    baseline_family = {}
    if refs:
        rows = await tdb.employee_family_members.find({"company_id": cid, "id": {"$in": refs}}, NO_ID).to_list(100)
        baseline_family = {r["id"]: {k: r.get(k) for k in P.FAMILY_EDITABLE} for r in rows}
    snap = await tdb.employee_completeness.find_one({"company_id": cid, "employee_id": sess.employee_id}, NO_ID) or {}
    changed = _changed_names(proposed)
    identity = any(k in P.IDENTITY_FIELDS and emp.get(k) not in (None, "") for k in proposed["fields"])
    ts = now()
    audit = build_audit_entry(sess.actor, "public_form.submitted", RESOURCE, sub["id"], emp.get("employee_number"), None,
                              {"changed_fields": changed, "family_ops": len(proposed["family"]), "attachments": files,
                               "identity_change": identity, "status": P.PENDING,
                               "resubmission": sub.get("status") == P.REVISION}, module=MODULE, company_id=cid)
    async with transaction() as tx:
        cur = await tx.select_one_for_update("employee_update_submissions", {"id": sub["id"], "company_id": cid})
        if not cur or cur.get("status") not in P.EDITABLE_SUBMISSION_STATUSES or cur.get("version") != body.version:
            raise HTTPException(status.HTTP_409_CONFLICT, "Draft telah berubah atau sudah dikirim. Muat ulang formulir.")
        await tx.update("employee_update_submissions", {"id": sub["id"], "company_id": cid}, {
            "status": P.PENDING, "proposed": proposed, "baseline": {"fields": baseline_fields, "family": baseline_family, "custom": baseline_custom,
                                                          "photo_version": emp.get("photo_version")},  # 01H: deteksi konflik foto
            "changed_fields": changed, "identity_change": identity, "submitted_at": ts, "submit_ip": sess.ip,
            "completeness_before": {"score_pct": snap.get("score_pct"), "status": snap.get("completeness_status"),
                                    "missing_codes": _json(snap.get("missing_codes")) or []},
            "version": int(body.version) + 1, "updated_at": ts, "link_id": sess.link["id"]})
        await tx.update("employee_public_links", {"id": sess.link["id"], "company_id": cid}, {
            "status": P.SUBMITTED, "submitted_at": ts, "submission_id": sub["id"], "updated_at": ts})
        await tx.insert("audit_logs", audit)
    return {"message": P.MSG_SUBMITTED, "status": P.PENDING, "status_label": _SUB_LABELS[P.PENDING],
            "submitted_at": ts.isoformat(), "changed_fields": changed}


# =================================================================== publik: lampiran
_MAGIC = {
    "pdf": lambda b: b.startswith(b"%PDF-"),
    "jpg": lambda b: b[:3] == b"\xff\xd8\xff",
    "jpeg": lambda b: b[:3] == b"\xff\xd8\xff",
    "png": lambda b: b[:8] == b"\x89PNG\r\n\x1a\n",
    "webp": lambda b: b[:4] == b"RIFF" and b[8:12] == b"WEBP",
}
_MIME = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def _safe_name(name: str, ext: str) -> str:
    base = os.path.basename((name or "").replace("\\", "/"))
    stem = re.sub(r"[^A-Za-z0-9._ -]", "_", os.path.splitext(base)[0]).strip(" ._") or "berkas"
    return f"{stem[:100]}.{ext}"


@public_router.post("/attachments", status_code=201)
async def upload_attachment(file: UploadFile = File(...), document_type_code: str = Form("", max_length=64),
                            field_key: Optional[str] = Form(None, max_length=64),
                            sess: PublicSession = Depends(get_public_session)):
    tdb, cid = sess.tdb, sess.company_id
    sub = await _open_submission(tdb, cid, sess.employee_id)
    _ensure_editable(sess, sub)
    code = document_type_code.strip().upper()
    doc_type, custom_def = None, None
    if field_key:  # Enhancement 01G: custom field tipe file -> lampiran PENDING (bukan dokumen resmi)
        _c, _l, custom_defs, _o = await _form_layout(sess)
        custom_def = custom_defs.get(field_key)
        if not custom_def or custom_def.get("type") != "file":
            return _reject("Pertanyaan tidak dikenal.", {"field_key": "Pertanyaan tidak dikenal."})
        code, purpose = field_key, "CUSTOM_FIELD"
    elif not code:
        return _reject("Jenis dokumen tidak dikenal.", {"document_type_code": "Jenis dokumen tidak dikenal."})
    elif code == P.PHOTO_CODE:
        purpose = "PHOTO"
    else:
        purpose = "DOCUMENT"
        doc_type = next((d for d in await _doc_types(sess) if (d.get("code") or "").upper() == code), None)
        if not doc_type:
            return _reject("Jenis dokumen tidak dikenal.", {"document_type_code": "Jenis dokumen tidak dikenal."})
    allowed = _allowed_ext(doc_type)
    max_mb = _max_mb(doc_type)
    if custom_def:
        allowed = sorted(set(custom_def["validation"].get("allowed_ext") or P.PUBLIC_EXTENSIONS) & P.PUBLIC_EXTENSIONS)
        max_mb = min(float(custom_def["validation"].get("max_mb") or P.PUBLIC_MAX_MB), P.PUBLIC_MAX_MB)
    ext = os.path.splitext(file.filename or "")[1].lstrip(".").lower()
    if ext not in allowed:
        return _reject(f"Jenis berkas tidak diizinkan. Gunakan: {', '.join(allowed)}.", {"file": "Jenis berkas tidak diizinkan."})
    max_bytes = int(max_mb * 1024 * 1024)
    data = await file.read(max_bytes + 1)
    if not data:
        return _reject("Berkas kosong.", {"file": "Berkas kosong."})
    if len(data) > max_bytes:
        return _reject(f"Ukuran berkas melebihi batas {max_mb:g} MB.", {"file": "Ukuran berkas terlalu besar."})
    if not _MAGIC[ext](data):
        return _reject("Isi berkas tidak sesuai dengan jenis berkasnya.", {"file": "Isi berkas tidak sesuai."})
    if not sub:
        sub = await _new_draft(sess, {"fields": {}, "family": [], "notes": None, "no_npwp": False, "custom": {}})
    base = {"company_id": cid, "submission_id": sub["id"], "status": "active"}
    if await tdb.employee_submission_files.count_documents(base) >= P.MAX_FILES_PER_SUBMISSION:
        return _reject(f"Maksimal {P.MAX_FILES_PER_SUBMISSION} berkas per pengajuan.")
    if await tdb.employee_submission_files.count_documents({**base, "document_type_code": code}) >= P.MAX_FILES_PER_TYPE:
        return _reject(f"Maksimal {P.MAX_FILES_PER_TYPE} berkas untuk jenis dokumen yang sama.")
    path = f"{APP_NAME}/companies/{cid}/employee-submissions/{sub['id']}/{secrets.token_hex(16)}.{ext}"
    try:
        put_object(path, data, _MIME[ext])
    except StorageError:
        logger.warning("Upload lampiran formulir publik gagal (submission %s).", sub["id"])
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Penyimpanan berkas sedang tidak tersedia. Silakan coba lagi.") from None
    row = {"id": new_id(), "company_id": cid, "status": "active", "submission_id": sub["id"], "employee_id": sess.employee_id,
           "document_type_id": doc_type["id"] if doc_type else None, "document_type_code": code, "purpose": purpose,
           "file_name": _safe_name(file.filename, ext), "file_extension": ext, "mime_type": _MIME[ext], "file_size": len(data),
           "sha256": hashlib.sha256(data).hexdigest(), "storage_path": path, "uploaded_at": now(),
           "field_key": field_key if custom_def else None,
           "created_at": now(), "updated_at": now()}
    await tdb.employee_submission_files.insert_one(dict(row))
    await tdb.employee_update_submissions.update_one({"id": sub["id"]}, {"$set": {"draft_saved_at": now(), "updated_at": now()}})
    await log_action(sess.actor, "public_form.file_uploaded", RESOURCE, sub["id"], None, None,
                     {"document_type_code": code, "extension": ext, "size": len(data)}, module=MODULE, company_id=cid)
    return {"file": _file_out(row), "message": "Berkas terunggah ke draft. Belum menjadi dokumen resmi sebelum diverifikasi HR."}


async def _own_file(sess: PublicSession, file_id: str) -> Dict[str, Any]:
    f = await sess.tdb.employee_submission_files.find_one(
        {"company_id": sess.company_id, "employee_id": sess.employee_id, "id": file_id, "status": "active"}, NO_ID)
    sub = await _open_submission(sess.tdb, sess.company_id, sess.employee_id)
    if not f or not sub or f.get("submission_id") != sub["id"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Berkas tidak ditemukan.")
    return f


@public_router.delete("/attachments/{file_id}")
async def remove_attachment(file_id: str, sess: PublicSession = Depends(get_public_session)):
    sub = await _open_submission(sess.tdb, sess.company_id, sess.employee_id)
    _ensure_editable(sess, sub)
    f = await _own_file(sess, file_id)
    # Objek storage TIDAK dihapus di 01G-A (menunggu kebijakan cleanup yang aman); hanya dilepas dari draft.
    await sess.tdb.employee_submission_files.update_one({"id": f["id"]}, {"$set": {"status": "removed", "updated_at": now()}})
    await log_action(sess.actor, "public_form.file_removed", RESOURCE, f["submission_id"], None, None,
                     {"document_type_code": f.get("document_type_code")}, module=MODULE, company_id=sess.company_id)
    return {"message": "Berkas dilepas dari draft."}


@public_router.get("/attachments/{file_id}/file")
async def download_attachment(file_id: str, sess: PublicSession = Depends(get_public_session)):
    f = await _own_file(sess, file_id)
    try:
        data, _ct = get_object(f["storage_path"])
    except StorageError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Berkas tidak ditemukan.") from None
    return Response(content=data, media_type=f.get("mime_type") or "application/octet-stream", headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
        "Content-Disposition": f'inline; filename="{f.get("file_name") or "berkas"}"'})
