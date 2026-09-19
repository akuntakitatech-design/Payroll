"""Pengiriman email via SMTP kantor.

Konfigurasi SMTP disimpan per perusahaan di MongoDB (koleksi `smtp_settings`).
Password bersifat write-only: tidak pernah dikembalikan oleh API dan tidak
pernah masuk ke log.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SECURITY_MODES = ["starttls", "ssl", "none"]


class MailerError(RuntimeError):
    pass


class SmtpConfig:
    def __init__(self, data: Optional[Dict[str, Any]] = None):
        data = data or {}
        self.host = (data.get("host") or "").strip()
        raw_port = data.get("port")
        try:
            self.port = 587 if raw_port is None or raw_port == "" else int(raw_port)
        except (TypeError, ValueError):
            self.port = -1  # ditolak oleh validate()
        self.username = (data.get("username") or "").strip()
        self.password = data.get("password") or ""
        self.security = (data.get("security") or "starttls").strip().lower()
        self.from_email = (data.get("from_email") or self.username or "").strip()
        self.from_name = (data.get("from_name") or "HRIS & Payroll").strip()
        self.timeout = int(data.get("timeout") or 20)
        self.is_enabled = bool(data.get("is_enabled", True))

    def validate(self) -> None:
        if not self.host:
            raise MailerError("Host SMTP belum diisi.")
        if not (0 < self.port < 65536):
            raise MailerError("Port SMTP tidak valid.")
        if self.security not in SECURITY_MODES:
            raise MailerError(
                f"Mode keamanan '{self.security}' tidak dikenal (pilih starttls, ssl, atau none)."
            )
        if not self.from_email:
            raise MailerError("Alamat email pengirim (from) belum diisi.")

    def masked(self) -> Dict[str, Any]:
        """Versi aman untuk dikirim ke frontend — tanpa password."""
        return {
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "security": self.security,
            "from_email": self.from_email,
            "from_name": self.from_name,
            "timeout": self.timeout,
            "is_enabled": self.is_enabled,
            "has_password": bool(self.password),
        }


def _connect(cfg: SmtpConfig):
    if cfg.security == "ssl":
        context = ssl.create_default_context()
        server = smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=cfg.timeout, context=context)
    else:
        server = smtplib.SMTP(cfg.host, cfg.port, timeout=cfg.timeout)
        if cfg.security == "starttls":
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
    if cfg.username and cfg.password:
        server.login(cfg.username, cfg.password)
    return server


def send_email(
    config: Dict[str, Any] | SmtpConfig,
    to: List[str],
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    cc: Optional[List[str]] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Kirim satu email HTML. Mengembalikan ringkasan hasil pengiriman."""
    cfg = config if isinstance(config, SmtpConfig) else SmtpConfig(config)
    cfg.validate()

    recipients = [r.strip() for r in (to or []) if r and r.strip()]
    cc_list = [r.strip() for r in (cc or []) if r and r.strip()]
    if not recipients:
        raise MailerError("Daftar penerima email masih kosong.")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((cfg.from_name, cfg.from_email))
    msg["To"] = ", ".join(recipients)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=cfg.from_email.split("@")[-1] or "hris.local")
    msg.set_content(text_body or _html_to_text(html_body))
    msg.add_alternative(html_body, subtype="html")

    for att in attachments or []:
        content = att.get("content")
        if not content:
            continue
        mime = (att.get("mime") or "application/pdf").split("/", 1)
        msg.add_attachment(
            content,
            maintype=mime[0],
            subtype=mime[1] if len(mime) > 1 else "octet-stream",
            filename=att.get("filename") or "lampiran.pdf",
        )

    try:
        server = _connect(cfg)
    except Exception as exc:  # noqa: BLE001
        raise MailerError(f"Gagal terhubung ke server SMTP {cfg.host}:{cfg.port} — {exc}") from exc

    try:
        server.send_message(msg, to_addrs=recipients + cc_list)
    except Exception as exc:  # noqa: BLE001
        raise MailerError(f"Gagal mengirim email — {exc}") from exc
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001
            pass

    logger.info("Email terkirim ke %s subjek '%s'", recipients, subject)
    return {
        "sent": True,
        "recipients": recipients,
        "cc": cc_list,
        "subject": subject,
        "message_id": msg["Message-ID"],
    }


def send_test_email(config: Dict[str, Any], to: List[str]) -> Dict[str, Any]:
    html = """
    <div style="font-family:Arial,Helvetica,sans-serif;color:#0F172A;font-size:14px">
      <h2 style="margin:0 0 8px;color:#0F5C4F">Konfigurasi SMTP berhasil</h2>
      <p style="margin:0 0 12px;color:#475569">
        Email ini dikirim dari sistem HRIS &amp; Payroll untuk memastikan pengaturan
        SMTP perusahaan Anda sudah benar. Jika Anda menerima email ini, pengingat
        masa berlaku kontrak, sertifikasi dan dokumen akan terkirim normal.
      </p>
      <p style="margin:0;color:#64748B;font-size:12px">Pesan uji otomatis — tidak perlu dibalas.</p>
    </div>
    """
    return send_email(config, to, "Uji Koneksi SMTP — HRIS & Payroll", html)


def _html_to_text(html: str) -> str:
    import re

    text = re.sub(r"<br\s*/?>", "\n", html or "")
    text = re.sub(r"</(p|div|tr|h1|h2|h3|li)>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())
