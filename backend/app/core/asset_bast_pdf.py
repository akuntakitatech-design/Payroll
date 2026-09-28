"""Phase 2A CP2 - PDF BAST Penyerahan / Pengembalian aset.

PDF dibuat ON-THE-FLY murni dari `asset_basts.snapshot` (immutable sejak terbit). Tidak membaca master karyawan/aset/
project terkini dan tidak disimpan ke object storage -> isi PDF lama tidak berubah bila master diubah kemudian.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

TITLES = {"HANDOVER": "BERITA ACARA SERAH TERIMA ASET", "RETURN": "BERITA ACARA PENGEMBALIAN ASET",
          "EXISTING": "DOKUMEN SALDO AWAL / EXISTING HOLDING ASET"}
SUBTITLES = {"HANDOVER": "Penyerahan aset dari GA kepada karyawan", "RETURN": "Pengembalian aset dari karyawan kepada GA",
             "EXISTING": "Pencatatan awal aset yang sudah dipegang karyawan - BUKAN penyerahan baru"}
# Phase 2A CP3 - pernyataan wajib pada dokumen Saldo Awal (Existing Holding).
EXISTING_STATEMENT = "Aset telah berada dalam penguasaan karyawan pada saat pencatatan awal sistem."


BULAN = ("Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober",
         "November", "Desember")
WIB = timezone(timedelta(hours=7), "WIB")   # Asia/Jakarta (tanpa DST)


def _p(text: Any, style) -> Paragraph:
    return Paragraph(escape(str(text if text not in (None, "") else "-")), style)


def format_tanggal(value: Any) -> Optional[str]:
    """'2026-09-28' -> '28 September 2026' (format Indonesia). Nilai tak dikenal dikembalikan apa adanya."""
    if not value:
        return None
    try:
        d = date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value)
    return f"{d.day} {BULAN[d.month - 1]} {d.year}"


def format_waktu_wib(value: Any) -> Optional[str]:
    """Snapshot `issued_at` ('YYYY-MM-DD HH:MM UTC' atau ISO) -> '28 September 2026, 15:34 WIB'.
    Hanya format tampilan; snapshot tetap apa adanya (immutable)."""
    if not value:
        return None
    raw = str(value).strip()
    dt = None
    for fmt in ("%Y-%m-%d %H:%M UTC", "%Y-%m-%d %H:%M:%S UTC"):
        try:
            dt = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            break
        except ValueError:
            continue
    if dt is None:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return raw
    local = dt.astimezone(WIB)
    return f"{format_tanggal(local.date().isoformat())}, {local:%H:%M} WIB"


def company_address(company: Dict[str, Any]) -> Optional[str]:
    """Alamat + kota digabung secara natural; None bila keduanya kosong (baris alamat disembunyikan)."""
    parts = [str(x).strip() for x in (company.get("address"), company.get("city")) if x and str(x).strip() not in ("", "-")]
    return ", ".join(parts) or None


def build_bast_pdf(snapshot: Dict[str, Any]) -> bytes:
    base = getSampleStyleSheet()
    st = {
        "title": ParagraphStyle("t", parent=base["Title"], fontSize=14, leading=18, alignment=TA_CENTER, spaceAfter=2),
        "sub": ParagraphStyle("s", parent=base["Normal"], fontSize=9, alignment=TA_CENTER, textColor=colors.HexColor("#555555")),
        "n": ParagraphStyle("n", parent=base["Normal"], fontSize=8.5, leading=11),
        "b": ParagraphStyle("b", parent=base["Normal"], fontSize=8.5, leading=11, fontName="Helvetica-Bold"),
        "c": ParagraphStyle("c", parent=base["Normal"], fontSize=8.5, leading=11, alignment=TA_CENTER),
    }
    btype = snapshot.get("bast_type", "HANDOVER")
    company = snapshot.get("company") or {}
    emp = snapshot.get("employee") or {}
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm,
                            bottomMargin=12 * mm, title=f"{snapshot.get('system_number', '')}")
    story: List[Any] = [_p(company.get("legal_name") or company.get("name"), st["b"])]
    addr = company_address(company)
    if addr:   # alamat kosong -> baris disembunyikan (tanpa '-' berdiri sendiri)
        story.append(_p(addr, st["n"]))
    story += [
        Spacer(1, 4 * mm),
        Paragraph(TITLES.get(btype, "BERITA ACARA"), st["title"]),
        _p(SUBTITLES.get(btype, ""), st["sub"]),
        Spacer(1, 4 * mm),
    ]
    head = [
        [_p("Nomor BAST", st["b"]), _p(snapshot.get("system_number"), st["n"]),
         _p("Tanggal Saldo Awal" if btype == "EXISTING" else "Tanggal", st["b"]), _p(format_tanggal(snapshot.get("bast_date")), st["n"])],
        [_p("No. Referensi", st["b"]), _p(snapshot.get("manual_number"), st["n"]),
         _p("Project", st["b"]), _p((snapshot.get("project") or {}).get("name"), st["n"])],
        [_p("Karyawan", st["b"]), _p(f"{emp.get('full_name') or '-'} ({emp.get('employee_number') or '-'})", st["n"]),
         _p("Lokasi Kerja", st["b"]), _p((snapshot.get("work_location") or {}).get("name"), st["n"])],
        [_p("PIC GA", st["b"]), _p(snapshot.get("ga_pic_name"), st["n"]),
         _p("Catatan", st["b"]), _p(snapshot.get("notes"), st["n"])],
    ]
    t = Table(head, colWidths=[30 * mm, 100 * mm, 30 * mm, 105 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                           ("TOPPADDING", (0, 0), (-1, -1), 2), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [t, Spacer(1, 4 * mm)]

    cond_label = {"HANDOVER": "Kondisi Saat Diserahkan", "EXISTING": "Kondisi Saat Saldo Awal"}.get(btype, "Kondisi Saat Diterima GA")
    if btype == "EXISTING":
        story += [_p(EXISTING_STATEMENT + " Dokumen ini mencatat saldo awal pemegang aset dan tidak menggantikan "
                     "berita acara serah terima di masa lalu.", st["n"]), Spacer(1, 3 * mm)]
    rows = [[_p(h, st["b"]) for h in ("No", "Kode Aset", "Nama Aset", "Merk / Tipe", "Serial Number", "Satuan",
                                         cond_label, "Kelengkapan", "Catatan")]]
    for it in snapshot.get("items") or []:
        rows.append([_p(it.get("line_no"), st["c"]), _p(it.get("asset_code"), st["n"]), _p(it.get("name"), st["n"]),
                     _p(" / ".join(x for x in (it.get("brand"), it.get("model")) if x) or "-", st["n"]),
                     _p(it.get("serial_number"), st["n"]), _p(it.get("unit"), st["n"]), _p(it.get("condition"), st["n"]),
                     _p(it.get("accessories"), st["n"]), _p(it.get("item_notes"), st["n"])])
    items = Table(rows, colWidths=[10 * mm, 28 * mm, 45 * mm, 35 * mm, 32 * mm, 18 * mm, 32 * mm, 36 * mm, 33 * mm],
                  repeatRows=1)
    items.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa5b1")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef3")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story += [items, Spacer(1, 8 * mm)]

    if btype == "HANDOVER":
        left, right = "Yang Menyerahkan (GA)", "Yang Menerima (Karyawan)"
        lname, rname = snapshot.get("ga_pic_name"), emp.get("full_name")
    elif btype == "EXISTING":
        left, right = "Dicatat oleh (GA)", "Pemegang Aset (Karyawan)"
        lname, rname = snapshot.get("ga_pic_name"), emp.get("full_name")
    else:
        left, right = "Yang Menyerahkan (Karyawan)", "Yang Menerima (GA)"
        lname, rname = emp.get("full_name"), snapshot.get("ga_pic_name")
    sig = Table([[_p(left, st["c"]), _p(right, st["c"])], [Spacer(1, 18 * mm), Spacer(1, 18 * mm)],
                 [_p(f"( {lname or '....................'} )", st["c"]), _p(f"( {rname or '....................'} )", st["c"])]],
                colWidths=[130 * mm, 130 * mm])
    story += [sig, Spacer(1, 3 * mm),
              _p(f"Diterbitkan {format_waktu_wib(snapshot.get('issued_at')) or '-'} oleh {snapshot.get('issued_by_name') or '-'}. "
                 "Dokumen dibuat dari snapshot saat terbit.", st["sub"])]
    doc.build(story)
    return buf.getvalue()
