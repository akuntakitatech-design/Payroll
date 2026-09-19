"""Penyusun email pengingat masa berlaku (kontrak, sertifikasi, dokumen).

Murni presentasi + seleksi — pengambilan data dari MongoDB dilakukan di router /
scheduler, sehingga fungsi di sini mudah diuji tanpa database.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .expiry import MONTH_NAMES_ID, days_left, parse_date

DEFAULT_WINDOWS = [90, 60, 30, 7]

KIND_LABELS = {
    "contract": "Kontrak Kerja",
    "certification": "Sertifikasi",
    "document": "Dokumen",
}


def format_date_id(value: Any) -> str:
    parsed = parse_date(value)
    if not parsed:
        return "-"
    return f"{parsed.day:02d} {MONTH_NAMES_ID[parsed.month - 1]} {parsed.year}"


def select_expiring(
    records: List[Dict[str, Any]],
    windows: Optional[List[int]] = None,
    today=None,
    include_expired: bool = True,
) -> List[Dict[str, Any]]:
    """Pilih record yang masa berlakunya jatuh di dalam jendela hari terbesar.

    Setiap record wajib punya `expiry_date`. Hasil diberi `days_left`, `window`
    (jendela terkecil yang memuatnya) dan `urgency`.
    """
    windows = sorted({int(w) for w in (windows or DEFAULT_WINDOWS) if int(w) > 0})
    if not windows:
        return []
    horizon = windows[-1]

    out = []
    for rec in records or []:
        left = days_left(rec.get("expiry_date"), today)
        if left is None:
            continue
        if left < 0:
            if not include_expired:
                continue
            window = 0
            urgency = "expired"
        elif left > horizon:
            continue
        else:
            window = next(w for w in windows if left <= w)
            urgency = "critical" if left <= min(windows) else "warning"
        item = dict(rec)
        item["days_left"] = left
        item["window"] = window
        item["urgency"] = urgency
        out.append(item)

    out.sort(key=lambda r: (r["days_left"], r.get("title") or ""))
    return out


def _row_html(item: Dict[str, Any]) -> str:
    left = item["days_left"]
    if left < 0:
        badge_bg, badge_fg = "#FEE2E2", "#991B1B"
        badge = f"Kedaluwarsa {abs(left)} hari"
    elif left <= 7:
        badge_bg, badge_fg = "#FEE2E2", "#991B1B"
        badge = f"{left} hari lagi"
    elif left <= 30:
        badge_bg, badge_fg = "#FEF3C7", "#92400E"
        badge = f"{left} hari lagi"
    else:
        badge_bg, badge_fg = "#E0F2FE", "#075985"
        badge = f"{left} hari lagi"

    return (
        "<tr>"
        f"<td style=\"padding:9px 10px;border-bottom:1px solid #E2E8F0;font-size:13px;color:#0F172A\">"
        f"<b>{item.get('title') or '-'}</b>"
        f"<div style=\"color:#64748B;font-size:11.5px;margin-top:2px\">{item.get('subtitle') or ''}</div>"
        "</td>"
        f"<td style=\"padding:9px 10px;border-bottom:1px solid #E2E8F0;font-size:12.5px;color:#334155;white-space:nowrap\">"
        f"{format_date_id(item.get('expiry_date'))}</td>"
        f"<td style=\"padding:9px 10px;border-bottom:1px solid #E2E8F0;text-align:right;white-space:nowrap\">"
        f"<span style=\"background:{badge_bg};color:{badge_fg};font-size:11px;font-weight:bold;"
        f"padding:3px 8px;border-radius:999px\">{badge}</span></td>"
        "</tr>"
    )


def _section_html(title: str, items: List[Dict[str, Any]]) -> str:
    if not items:
        return ""
    rows = "".join(_row_html(i) for i in items)
    return (
        f"<h3 style=\"margin:22px 0 8px;font-size:14px;color:#0F5C4F\">{title} "
        f"<span style=\"color:#64748B;font-weight:normal\">({len(items)})</span></h3>"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
        "style=\"border-collapse:collapse;border:1px solid #E2E8F0;border-radius:6px\">"
        f"{rows}</table>"
    )


def build_reminder_digest(
    company_name: str,
    contracts: List[Dict[str, Any]],
    certifications: List[Dict[str, Any]],
    documents: List[Dict[str, Any]],
    windows: Optional[List[int]] = None,
    today=None,
    app_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Susun subjek + body HTML digest pengingat. Kembalikan None-safe dict."""
    sel_contracts = select_expiring(contracts, windows, today)
    sel_certs = select_expiring(certifications, windows, today)
    sel_docs = select_expiring(documents, windows, today)
    total = len(sel_contracts) + len(sel_certs) + len(sel_docs)

    urgent = [i for i in sel_contracts + sel_certs + sel_docs if i["days_left"] < 0]
    subject = (
        f"[{company_name}] {total} item masa berlaku perlu perhatian"
        + (f" — {len(urgent)} sudah kedaluwarsa" if urgent else "")
    )

    sections = (
        _section_html("Kontrak Kerja", sel_contracts)
        + _section_html("Sertifikasi Karyawan", sel_certs)
        + _section_html("Dokumen", sel_docs)
    )

    cta = (
        f"<p style=\"margin:24px 0 0\"><a href=\"{app_url}\" "
        "style=\"background:#0F5C4F;color:#FFFFFF;text-decoration:none;font-size:13px;"
        "font-weight:bold;padding:10px 18px;border-radius:6px;display:inline-block\">"
        "Buka Kalender Masa Berlaku</a></p>"
        if app_url
        else ""
    )

    empty_state = (
        '<p style="margin:20px 0;font-size:13px;color:#475569">'
        "Tidak ada item yang perlu perhatian saat ini.</p>"
    )

    html = (
        "<div style=\"font-family:Arial,Helvetica,sans-serif;background:#FFFFFF;"
        "color:#0F172A;padding:4px 0;max-width:680px\">"
        "<h2 style=\"margin:0 0 4px;font-size:18px;color:#0F5C4F\">Pengingat Masa Berlaku</h2>"
        f"<p style=\"margin:0 0 2px;font-size:13px;color:#334155\"><b>{company_name}</b></p>"
        "<p style=\"margin:0;font-size:12px;color:#64748B\">"
        f"Terdapat <b>{total} item</b> yang masa berlakunya mendekati atau sudah terlewati.</p>"
        f"{sections or empty_state}"
        f"{cta}"
        "<p style=\"margin:26px 0 0;font-size:11px;color:#94A3B8;border-top:1px solid #E2E8F0;"
        "padding-top:12px\">Email otomatis dari sistem HRIS &amp; Payroll. "
        "Atur jadwal dan penerima di menu Pengaturan Sistem.</p>"
        "</div>"
    )

    return {
        "subject": subject,
        "html": html,
        "total": total,
        "counts": {
            "contracts": len(sel_contracts),
            "certifications": len(sel_certs),
            "documents": len(sel_docs),
            "expired": len(urgent),
        },
        "items": {
            "contracts": sel_contracts,
            "certifications": sel_certs,
            "documents": sel_docs,
        },
    }
