"""Pengaturan email (SMTP) & pengingat masa berlaku otomatis.

Password SMTP bersifat write-only: disimpan di database namun TIDAK PERNAH
dikembalikan oleh endpoint GET apa pun.
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ..core.audit import log_action
from ..core.db import NO_ID, audit_fields, get_db, new_id, now, serialize_list
from ..core.deps import AuthContext, require_permission
from ..core.mailer import SECURITY_MODES, MailerError, SmtpConfig, send_test_email
from ..core.reminder_mail import DEFAULT_WINDOWS
from ..core.scheduler import (
    DEFAULT_REMINDER_SETTINGS,
    collect_expiring_records,
    get_reminder_settings,
    run_reminder_for_company,
    scheduler_status,
)
from ..schemas import ReminderSettingsUpdate, SmtpSettingsUpdate, SmtpTestRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mail", tags=["Email & Pengingat"])


def _app_url(request: Request) -> Optional[str]:
    origin = request.headers.get("origin") or request.headers.get("referer")
    if not origin:
        return None
    return origin.rstrip("/") + "/expiry-calendar"


@router.get("/settings")
async def get_settings(ctx: AuthContext = Depends(require_permission("settings", "view"))):
    db = get_db()
    cid = ctx.company_id
    raw = await db.smtp_settings.find_one({"company_id": cid}, NO_ID) or {}
    smtp = SmtpConfig(raw).masked() if raw.get("host") else {
        **SmtpConfig({}).masked(), "host": "", "username": "", "from_email": "",
        "has_password": False,
    }
    smtp["is_configured"] = bool(raw.get("host"))
    reminder = await get_reminder_settings(cid)
    return {
        "smtp": smtp,
        "reminder": reminder,
        "security_modes": [
            {"value": "starttls", "label": "STARTTLS (umumnya port 587)"},
            {"value": "ssl", "label": "SSL/TLS (umumnya port 465)"},
            {"value": "none", "label": "Tanpa enkripsi (tidak disarankan)"},
        ],
        "default_windows": DEFAULT_WINDOWS,
        "scheduler": scheduler_status(),
    }


@router.put("/settings/smtp")
async def update_smtp(
    payload: SmtpSettingsUpdate,
    ctx: AuthContext = Depends(require_permission("settings", "config")),
):
    db = get_db()
    cid = ctx.company_id
    data = payload.model_dump(exclude_unset=True)

    existing = await db.smtp_settings.find_one({"company_id": cid}, NO_ID) or {}
    # password kosong = biarkan password lama
    if not (data.get("password") or "").strip():
        data.pop("password", None)

    merged = {**existing, **data}
    if merged.get("security") and merged["security"] not in SECURITY_MODES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Mode keamanan tidak dikenal. Pilih: {', '.join(SECURITY_MODES)}.",
        )
    try:
        SmtpConfig(merged).validate()
    except MailerError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    patch = {k: v for k, v in data.items()}
    patch["company_id"] = cid
    patch["status"] = "active"
    patch.update(audit_fields(ctx.user_id, creating=not existing))
    if not existing:
        patch["id"] = new_id()

    await db.smtp_settings.update_one({"company_id": cid}, {"$set": patch}, upsert=True)

    safe_before = {k: v for k, v in existing.items() if k != "password"}
    safe_after = SmtpConfig({**merged}).masked()
    await log_action(ctx, "config", "settings", None, "Pengaturan SMTP",
                     before=safe_before, after=safe_after,
                     notes="Password diubah" if data.get("password") else None)
    return {"smtp": {**safe_after, "is_configured": True}}


@router.post("/settings/smtp/test")
async def test_smtp(
    payload: SmtpTestRequest,
    ctx: AuthContext = Depends(require_permission("settings", "config")),
):
    """Kirim email uji ke alamat yang diberikan memakai konfigurasi tersimpan."""
    import asyncio

    db = get_db()
    cid = ctx.company_id
    raw = await db.smtp_settings.find_one({"company_id": cid}, NO_ID) or {}
    if not raw.get("host"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Simpan pengaturan SMTP terlebih dahulu sebelum mengirim email uji.",
        )
    recipient = (payload.to or ctx.user.get("email") or "").strip()
    if not recipient:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Alamat email tujuan uji belum diisi.")
    try:
        result = await asyncio.to_thread(send_test_email, raw, [recipient])
    except MailerError as exc:
        await log_action(ctx, "config", "settings", None, "Uji SMTP gagal",
                         notes=str(exc))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await log_action(ctx, "config", "settings", None, "Uji SMTP berhasil",
                     notes=f"Email uji dikirim ke {recipient}")
    return {
        "sent": True,
        "recipient": recipient,
        "message": f"Email uji berhasil dikirim ke {recipient}. Periksa kotak masuk Anda.",
        "message_id": result.get("message_id"),
    }


@router.put("/settings/reminder")
async def update_reminder(
    payload: ReminderSettingsUpdate,
    ctx: AuthContext = Depends(require_permission("settings", "config")),
):
    db = get_db()
    cid = ctx.company_id
    data = payload.model_dump(exclude_unset=True)

    if data.get("windows") is not None:
        windows = sorted({int(w) for w in data["windows"] if 1 <= int(w) <= 365}, reverse=True)
        if not windows:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Minimal satu jendela pengingat (1\u2013365 hari) harus diisi.",
            )
        data["windows"] = windows

    if data.get("recipients") is not None:
        import re

        cleaned = []
        for email in data["recipients"]:
            email = (email or "").strip().lower()
            if not email:
                continue
            if not re.match(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$", email):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                    f"Alamat email penerima '{email}' tidak valid.")
            if email not in cleaned:
                cleaned.append(email)
        data["recipients"] = cleaned

    if data.get("send_hour") is not None and not 0 <= int(data["send_hour"]) <= 23:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Jam kirim harus antara 0 dan 23 (WIB).")

    if data.get("is_enabled"):
        merged_recipients = data.get("recipients")
        if merged_recipients is None:
            merged_recipients = (await get_reminder_settings(cid)).get("recipients") or []
        if not merged_recipients:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Tambahkan minimal satu penerima email sebelum mengaktifkan pengingat.",
            )
        smtp = await db.smtp_settings.find_one({"company_id": cid}, NO_ID) or {}
        if not smtp.get("host"):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Konfigurasi SMTP dulu sebelum mengaktifkan pengingat otomatis.",
            )

    before = await get_reminder_settings(cid)
    patch = {**data, "company_id": cid, "status": "active"}
    patch.update(audit_fields(ctx.user_id, creating=False))
    existing = await db.reminder_settings.find_one({"company_id": cid}, NO_ID)
    if not existing:
        patch["id"] = new_id()
        patch = {**DEFAULT_REMINDER_SETTINGS, **patch}
    await db.reminder_settings.update_one({"company_id": cid}, {"$set": patch}, upsert=True)

    after = await get_reminder_settings(cid)
    await log_action(ctx, "config", "settings", None, "Pengaturan pengingat masa berlaku",
                     before=before, after=after)
    return {"reminder": after}


@router.get("/reminder/preview")
async def preview_reminder(ctx: AuthContext = Depends(require_permission("settings", "view"))):
    """Pratinjau isi digest tanpa mengirim email."""
    from ..core.reminder_mail import build_reminder_digest

    db = get_db()
    cid = ctx.company_id
    settings = await get_reminder_settings(cid)
    company = await db.companies.find_one({"id": cid}, NO_ID) or {}
    records = await collect_expiring_records(cid, settings)
    digest = build_reminder_digest(
        company_name=company.get("name") or "Perusahaan",
        contracts=records["contracts"],
        certifications=records["certifications"],
        documents=records["documents"],
        windows=settings["windows"],
    )
    return {
        "subject": digest["subject"],
        "html": digest["html"],
        "total": digest["total"],
        "counts": digest["counts"],
        "items": digest["items"],
        "recipients": settings["recipients"],
        "windows": settings["windows"],
    }


@router.post("/reminder/send-now")
async def send_now(
    request: Request,
    ctx: AuthContext = Depends(require_permission("settings", "config")),
):
    """Kirim digest pengingat sekarang (mengabaikan jadwal & status aktif)."""
    db = get_db()
    company = await db.companies.find_one({"id": ctx.company_id}, NO_ID)
    if not company:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Perusahaan tidak ditemukan.")

    result = await run_reminder_for_company(
        company, trigger="manual", user_id=ctx.user_id, force=True,
        app_url=_app_url(request),
    )
    await log_action(ctx, "config", "settings", None, "Kirim pengingat manual",
                     notes=f"{result['status']}: {result['message']}")
    if result["status"] == "failed":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, result["message"])
    return result


@router.get("/reminder/logs")
async def reminder_logs(
    limit: int = Query(50, ge=1, le=200),
    ctx: AuthContext = Depends(require_permission("settings", "view")),
):
    db = get_db()
    logs = await db.reminder_logs.find(
        {"company_id": ctx.company_id}, NO_ID
    ).sort("created_at", -1).to_list(limit)
    return {
        "items": serialize_list(logs),
        "total": len(logs),
        "sent_count": sum(1 for l in logs if l.get("status") == "sent"),
        "failed_count": sum(1 for l in logs if l.get("status") == "failed"),
    }
