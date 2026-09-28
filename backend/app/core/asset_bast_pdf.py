"""Phase 2A CP2 - PDF BAST Penyerahan / Pengembalian aset.

PDF dibuat ON-THE-FLY murni dari `asset_basts.snapshot` (immutable sejak terbit). Tidak membaca master karyawan/aset/
project terkini dan tidak disimpan ke object storage -> isi PDF lama tidak berubah bila master diubah kemudian.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, List
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

TITLES = {"HANDOVER": "BERITA ACARA SERAH TERIMA ASET", "RETURN": "BERITA ACARA PENGEMBALIAN ASET"}
SUBTITLES = {"HANDOVER": "Penyerahan aset dari GA kepada karyawan", "RETURN": "Pengembalian aset dari karyawan kepada GA"}


def _p(text: Any, style) -> Paragraph:
    return Paragraph(escape(str(text if text not in (None, "") else "-")), style)


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
    story: List[Any] = [
        _p(company.get("legal_name") or company.get("name"), st["b"]),
        _p(company.get("address"), st["n"]),
        Spacer(1, 4 * mm),
        Paragraph(TITLES.get(btype, "BERITA ACARA"), st["title"]),
        _p(SUBTITLES.get(btype, ""), st["sub"]),
        Spacer(1, 4 * mm),
    ]
    head = [
        [_p("Nomor BAST", st["b"]), _p(snapshot.get("system_number"), st["n"]),
         _p("Tanggal", st["b"]), _p(snapshot.get("bast_date"), st["n"])],
        [_p("No. Referensi", st["b"]), _p(snapshot.get("manual_number"), st["n"]),
         _p("Project", st["b"]), _p((snapshot.get("project") or {}).get("name"), st["n"])],
        [_p("Karyawan", st["b"]), _p(f"{emp.get('full_name') or '-'} ({emp.get('employee_number') or '-'})", st["n"]),
         _p("Lokasi Kerja", st["b"]), _p((snapshot.get("work_location") or {}).get("name"), st["n"])],
        [_p("PIC GA", st["b"]), _p(snapshot.get("ga_pic_name"), st["n"]),
         _p("Catatan", st["b"]), _p(snapshot.get("notes"), st["n"])],
    ]
    t = Table(head, colWidths=[30 * mm, 100 * mm, 30 * mm, 105 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story += [t, Spacer(1, 4 * mm)]

    cond_label = "Kondisi Saat Diserahkan" if btype == "HANDOVER" else "Kondisi Saat Diterima GA"
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
    ]))
    story += [items, Spacer(1, 6 * mm)]

    if btype == "HANDOVER":
        left, right = "Yang Menyerahkan (GA)", "Yang Menerima (Karyawan)"
        lname, rname = snapshot.get("ga_pic_name"), emp.get("full_name")
    else:
        left, right = "Yang Menyerahkan (Karyawan)", "Yang Menerima (GA)"
        lname, rname = emp.get("full_name"), snapshot.get("ga_pic_name")
    sig = Table([[_p(left, st["c"]), _p(right, st["c"])], [Spacer(1, 18 * mm), Spacer(1, 18 * mm)],
                 [_p(f"( {lname or '....................'} )", st["c"]), _p(f"( {rname or '....................'} )", st["c"])]],
                colWidths=[130 * mm, 130 * mm])
    story += [sig, Spacer(1, 3 * mm),
              _p(f"Diterbitkan {snapshot.get('issued_at', '')} oleh {snapshot.get('issued_by_name') or '-'}. "
                 "Dokumen dibuat dari snapshot saat terbit.", st["sub"])]
    doc.build(story)
    return buf.getvalue()
