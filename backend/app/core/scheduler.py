"""Penjadwal pengingat masa berlaku (APScheduler).

Satu job harian memeriksa seluruh perusahaan yang mengaktifkan pengingat, lalu
mengirim digest email lewat SMTP perusahaan masing-masing. Idempoten: satu
perusahaan hanya dikirim sekali per hari (dicatat di `reminder_logs`).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .db import NO_ID, get_db, new_id, now
from .mailer import MailerError, send_email
from .reminder_mail import DEFAULT_WINDOWS, build_reminder_digest

logger = logging.getLogger("hris.scheduler")
JAKARTA_TZ = "Asia/Jakarta"

_scheduler: Optional[AsyncIOScheduler] = None

DEFAULT_REMINDER_SETTINGS = {
    "is_enabled": False,
    "windows": DEFAULT_WINDOWS,
    "recipients": [],
    "send_hour": 7,
    "send_minute": 0,
    "include_expired": True,
    "include_contracts": True,
    "include_certifications": True,
    "include_documents": True,
    "skip_when_empty": True,
}


async def get_reminder_settings(company_id: str) -> Dict[str, Any]:
    db = get_db()
    doc = await db.reminder_settings.find_one({"company_id": company_id}, NO_ID)
    merged = {**DEFAULT_REMINDER_SETTINGS, **(doc or {})}
    merged["company_id"] = company_id
    windows = sorted({int(w) for w in (merged.get("windows") or DEFAULT_WINDOWS) if int(w) > 0},
                     reverse=True)
    merged["windows"] = windows or DEFAULT_WINDOWS
    merged["recipients"] = [r for r in (merged.get("recipients") or []) if r]
    return merged


async def get_smtp_settings(company_id: str, include_password: bool = False) -> Dict[str, Any]:
    db = get_db()
    doc = await db.smtp_settings.find_one({"company_id": company_id}, NO_ID) or {}
    if not include_password:
        doc = {k: v for k, v in doc.items() if k != "password"}
    return doc


async def collect_expiring_records(company_id: str, settings: Dict[str, Any]) -> Dict[str, List[Dict]]:
    """Ambil kontrak/sertifikasi/dokumen beserta label siap tampil di email."""
    db = get_db()
    base = {"company_id": company_id, "status": {"$ne": "deleted"}}

    employees = {
        e["id"]: e
        for e in await db.employees.find(base, NO_ID).to_list(5000)
    }

    def emp_label(eid: Optional[str]) -> str:
        emp = employees.get(eid or "")
        if not emp:
            return ""
        parts = [p for p in [emp.get("employee_number"), emp.get("job_title")] if p]
        return " \u00b7 ".join(parts)

    contracts: List[Dict[str, Any]] = []
    if settings.get("include_contracts", True):
        types = {t["id"]: t for t in await db.contract_types.find(base, NO_ID).to_list(500)}
        for c in await db.employee_contracts.find(
            {**base, "end_date": {"$ne": None}}, NO_ID
        ).to_list(5000):
            emp = employees.get(c.get("employee_id") or "")
            ctype = types.get(c.get("contract_type_id") or "", {})
            contracts.append({
                "id": c["id"],
                "employee_id": c.get("employee_id"),
                "title": f"{ctype.get('name') or 'Kontrak'} \u2014 {(emp or {}).get('full_name') or '-'}",
                "subtitle": emp_label(c.get("employee_id")) or (c.get("contract_number") or ""),
                "expiry_date": c.get("end_date"),
            })

    certifications: List[Dict[str, Any]] = []
    if settings.get("include_certifications", True):
        ctypes = {t["id"]: t for t in await db.certification_types.find(base, NO_ID).to_list(500)}
        for s in await db.employee_certifications.find(
            {**base, "expiry_date": {"$ne": None}}, NO_ID
        ).to_list(5000):
            emp = employees.get(s.get("employee_id") or "")
            stype = ctypes.get(s.get("certification_type_id") or "", {})
            certifications.append({
                "id": s["id"],
                "employee_id": s.get("employee_id"),
                "title": f"{s.get('name') or stype.get('name') or 'Sertifikasi'} \u2014 "
                         f"{(emp or {}).get('full_name') or '-'}",
                "subtitle": emp_label(s.get("employee_id")),
                "expiry_date": s.get("expiry_date"),
            })

    documents: List[Dict[str, Any]] = []
    if settings.get("include_documents", True):
        dtypes = {t["id"]: t for t in await db.document_types.find(base, NO_ID).to_list(500)}
        for d in await db.documents.find({**base, "expiry_date": {"$ne": None}}, NO_ID).to_list(5000):
            dtype = dtypes.get(d.get("document_type_id") or "", {})
            documents.append({
                "id": d["id"],
                "title": d.get("name") or "Dokumen",
                "subtitle": dtype.get("name") or "",
                "expiry_date": d.get("expiry_date"),
            })

    return {"contracts": contracts, "certifications": certifications, "documents": documents}


async def run_reminder_for_company(
    company: Dict[str, Any],
    trigger: str = "scheduled",
    user_id: Optional[str] = None,
    force: bool = False,
    app_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Susun & kirim digest pengingat untuk satu perusahaan. Selalu mencatat log."""
    db = get_db()
    cid = company["id"]
    settings = await get_reminder_settings(cid)
    smtp = await get_smtp_settings(cid, include_password=True)

    log: Dict[str, Any] = {
        "id": new_id(),
        "company_id": cid,
        "trigger": trigger,
        "status": "skipped",
        "message": "",
        "recipients": settings.get("recipients") or [],
        "item_count": 0,
        "counts": {},
        "subject": None,
        "created_at": now(),
        "updated_at": now(),
        "created_by": user_id,
        "updated_by": user_id,
    }

    async def finish(status_: str, message: str) -> Dict[str, Any]:
        log["status"] = status_
        log["message"] = message
        await db.reminder_logs.insert_one(dict(log))
        return {k: v for k, v in log.items() if k != "_id"}

    if not force and not settings.get("is_enabled"):
        return await finish("skipped", "Pengingat email dinonaktifkan untuk perusahaan ini.")
    if not settings.get("recipients"):
        return await finish("failed", "Daftar penerima email masih kosong.")
    if not smtp.get("host"):
        return await finish("failed", "Pengaturan SMTP belum diisi.")

    if not force:
        today = datetime.now(timezone.utc).date().isoformat()
        already = await db.reminder_logs.count_documents({
            "company_id": cid,
            "trigger": "scheduled",
            "status": "sent",
            "sent_date": today,
        })
        if already:
            return await finish("skipped", "Digest terjadwal hari ini sudah terkirim.")

    records = await collect_expiring_records(cid, settings)
    digest = build_reminder_digest(
        company_name=company.get("name") or "Perusahaan",
        contracts=records["contracts"],
        certifications=records["certifications"],
        documents=records["documents"],
        windows=settings["windows"],
        app_url=app_url,
    )
    log["item_count"] = digest["total"]
    log["counts"] = digest["counts"]
    log["subject"] = digest["subject"]

    if digest["total"] == 0 and settings.get("skip_when_empty", True) and trigger == "scheduled":
        return await finish("skipped", "Tidak ada item yang perlu diingatkan hari ini.")

    try:
        await asyncio.to_thread(
            send_email, smtp, settings["recipients"], digest["subject"], digest["html"]
        )
    except MailerError as exc:
        return await finish("failed", str(exc))
    except Exception as exc:  # noqa: BLE001
        return await finish("failed", f"Kesalahan tak terduga saat mengirim email: {exc}")

    log["sent_date"] = datetime.now(timezone.utc).date().isoformat()
    return await finish("sent", f"Digest terkirim ke {len(settings['recipients'])} penerima.")


async def reminder_sweep() -> Dict[str, Any]:
    """Job harian: periksa semua perusahaan yang jadwalnya jatuh pada jam ini."""
    db = get_db()
    hour = datetime.now(tz=_tz()).hour
    companies = await db.companies.find({"status": {"$ne": "archived"}}, NO_ID).to_list(500)
    results = []
    for company in companies:
        settings = await get_reminder_settings(company["id"])
        if not settings.get("is_enabled"):
            continue
        if int(settings.get("send_hour", 7)) != hour:
            continue
        try:
            res = await run_reminder_for_company(company, trigger="scheduled")
            results.append({"company": company.get("code"), "status": res["status"],
                            "message": res["message"]})
        except Exception as exc:  # noqa: BLE001
            logger.exception("Pengingat gagal untuk %s: %s", company.get("code"), exc)
            results.append({"company": company.get("code"), "status": "failed",
                            "message": str(exc)})
    if results:
        logger.info("Sweep pengingat jam %02d:00 WIB -> %s", hour, results)
    return {"hour": hour, "results": results}


def _tz():
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(JAKARTA_TZ)
    except Exception:  # noqa: BLE001
        return timezone.utc


def start_scheduler() -> Optional[AsyncIOScheduler]:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    try:
        scheduler = AsyncIOScheduler(timezone=JAKARTA_TZ)
        scheduler.add_job(
            reminder_sweep,
            CronTrigger(minute=0, timezone=JAKARTA_TZ),
            id="expiry_reminder_sweep",
            name="Pengingat masa berlaku (per jam, kirim sesuai jadwal perusahaan)",
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
            max_instances=1,
        )
        scheduler.start()
        _scheduler = scheduler
        logger.info("Penjadwal pengingat aktif (zona %s).", JAKARTA_TZ)
        return scheduler
    except Exception as exc:  # noqa: BLE001
        logger.warning("Penjadwal pengingat gagal dimulai: %s", exc)
        return None


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:  # noqa: BLE001
            pass
        _scheduler = None


def scheduler_status() -> Dict[str, Any]:
    if _scheduler is None:
        return {"running": False, "timezone": JAKARTA_TZ, "jobs": []}
    return {
        "running": _scheduler.running,
        "timezone": JAKARTA_TZ,
        "jobs": [
            {
                "id": j.id,
                "name": j.name,
                "next_run": j.next_run_time.isoformat() if j.next_run_time else None,
            }
            for j in _scheduler.get_jobs()
        ],
    }
