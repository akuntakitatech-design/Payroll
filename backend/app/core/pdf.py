"""Slip gaji PDF (reportlab). Dipakai HR maupun self-service karyawan."""
from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .payroll import number_to_words_id

INK = colors.HexColor("#0F172A")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#E2E8F0")
BRAND = colors.HexColor("#0F5C4F")
ZEBRA = colors.HexColor("#F8FAFC")


def _money(value: Any) -> str:
    try:
        num = float(value or 0)
    except (TypeError, ValueError):
        return "-"
    sign = "-" if num < 0 else ""
    return f"{sign}Rp {abs(num):,.0f}".replace(",", ".")


def _styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Normal"], fontName="Helvetica-Bold",
                                fontSize=15, leading=19, textColor=INK),
        "sub": ParagraphStyle("s", parent=base["Normal"], fontName="Helvetica",
                              fontSize=9, leading=12, textColor=MUTED),
        "h2": ParagraphStyle("h2", parent=base["Normal"], fontName="Helvetica-Bold",
                             fontSize=9.5, leading=13, textColor=BRAND),
        "cell": ParagraphStyle("c", parent=base["Normal"], fontName="Helvetica",
                               fontSize=8.5, leading=11.5, textColor=INK),
        "cellb": ParagraphStyle("cb", parent=base["Normal"], fontName="Helvetica-Bold",
                                fontSize=8.5, leading=11.5, textColor=INK),
        "num": ParagraphStyle("n", parent=base["Normal"], fontName="Helvetica",
                              fontSize=8.5, leading=11.5, textColor=INK, alignment=TA_RIGHT),
        "numb": ParagraphStyle("nb", parent=base["Normal"], fontName="Helvetica-Bold",
                               fontSize=8.5, leading=11.5, textColor=INK, alignment=TA_RIGHT),
        "foot": ParagraphStyle("f", parent=base["Normal"], fontName="Helvetica-Oblique",
                               fontSize=7.5, leading=10, textColor=MUTED, alignment=TA_CENTER),
    }


def _kv_table(rows, st, col_widths):
    data = [[Paragraph(str(k), st["sub"]), Paragraph(str(v or "-"), st["cell"])] for k, v in rows]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _amount_table(title, rows, total_label, total_value, st, width):
    data = [[Paragraph(title, st["h2"]), Paragraph("Jumlah", st["numb"])]]
    for r in rows:
        data.append([Paragraph(r["name"], st["cell"]), Paragraph(_money(r["amount"]), st["num"])])
    if not rows:
        data.append([Paragraph("Tidak ada", st["cell"]), Paragraph(_money(0), st["num"])])
    data.append([Paragraph(total_label, st["cellb"]), Paragraph(_money(total_value), st["numb"])])

    t = Table(data, colWidths=[width * 0.62, width * 0.38])
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, BRAND),
        ("LINEABOVE", (0, -1), (-1, -1), 0.6, LINE),
        ("BACKGROUND", (0, -1), (-1, -1), ZEBRA),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
    ]
    for i in range(1, len(data) - 1):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), ZEBRA))
    t.setStyle(TableStyle(style))
    return t


def build_payslip_pdf(
    payslip: Dict[str, Any],
    company: Optional[Dict[str, Any]] = None,
    generated_at: Optional[str] = None,
) -> bytes:
    """Render satu slip gaji menjadi PDF dan kembalikan bytes-nya."""
    company = company or {}
    st = _styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
        title=f"Slip Gaji - {payslip.get('full_name', '')}",
        author=company.get("name") or "HRIS & Payroll Suite",
    )
    width = doc.width
    period = payslip.get("period") or {}
    totals = payslip.get("totals") or {}
    tax = payslip.get("tax") or {}
    bpjs = payslip.get("bpjs") or {}
    att = payslip.get("attendance") or {}

    story = []

    # ---- header ----
    header = Table(
        [[
            Paragraph(
                f"<b>{company.get('name') or 'Perusahaan'}</b><br/>"
                f"{company.get('address') or ''}<br/>{company.get('city') or ''}",
                st["sub"],
            ),
            Paragraph(
                "SLIP GAJI<br/>"
                f"<font size=9 color='#64748B'>Periode {period.get('label', '-')}</font>",
                ParagraphStyle("r", parent=st["title"], alignment=TA_RIGHT),
            ),
        ]],
        colWidths=[width * 0.58, width * 0.42],
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LINEBELOW", (0, 0), (-1, 0), 1.2, BRAND),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
    ]))
    story += [header, Spacer(1, 8)]

    # ---- identitas ----
    left = _kv_table([
        ("Nama Karyawan", payslip.get("full_name")),
        ("NIK Karyawan", payslip.get("employee_number")),
        ("Jabatan", payslip.get("job_title")),
    ], st, [width * 0.17, width * 0.31])
    right = _kv_table([
        ("Status PTKP", f"{tax.get('ptkp_status', '-')} (TER {tax.get('ter_category', '-')})"),
        ("Hari Kerja", f"{att.get('paid_days', '-')} / {att.get('working_days', '-')} hari"),
        ("Bank", f"{payslip.get('bank_name') or '-'} {payslip.get('bank_account_number') or ''}".strip()),
    ], st, [width * 0.17, width * 0.31])
    ident = Table([[left, right]], colWidths=[width * 0.5, width * 0.5])
    ident.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (0, 0), 8),
        ("LEFTPADDING", (1, 0), (1, 0), 8),
    ]))
    story += [ident, Spacer(1, 10)]

    # ---- penghasilan & potongan ----
    col_w = (width - 8) / 2
    earn_t = _amount_table(
        "PENGHASILAN", payslip.get("earnings") or [],
        "Total Penghasilan (Bruto)", totals.get("gross"), st, col_w,
    )
    ded_rows = [d for d in (payslip.get("deductions") or []) if not d.get("informational")]
    ded_t = _amount_table(
        "POTONGAN", ded_rows, "Total Potongan", totals.get("total_deductions"), st, col_w,
    )
    two = Table([[earn_t, ded_t]], colWidths=[col_w, col_w])
    two.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 8),
        ("RIGHTPADDING", (1, 0), (1, 0), 0),
    ]))
    story += [two, Spacer(1, 10)]

    # ---- take home pay ----
    net = totals.get("net_pay") or 0
    net_t = Table(
        [[
            Paragraph("<b>GAJI BERSIH (TAKE HOME PAY)</b><br/>"
                      f"<font size=7.5 color='#475569'>{number_to_words_id(net).capitalize()}</font>",
                      st["cell"]),
            Paragraph(f"<b>{_money(net)}</b>",
                      ParagraphStyle("big", parent=st["numb"], fontSize=13, leading=17)),
        ]],
        colWidths=[width * 0.6, width * 0.4],
    )
    net_t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ECFDF5")),
        ("BOX", (0, 0), (-1, -1), 0.8, BRAND),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story += [net_t, Spacer(1, 12)]

    # ---- rincian pajak ----
    tax_rows = [
        ("Metode Perhitungan", tax.get("method_label")),
        ("Penghasilan Bruto Kena Pajak", _money(tax.get("taxable_gross"))),
    ]
    if tax.get("method") == "ter":
        tax_rows.append(("Kategori / Tarif TER",
                         f"TER {tax.get('ter_category')} — {tax.get('ter_rate_percent', 0)}%"))
    else:
        ann = tax.get("annual") or {}
        tax_rows += [
            ("Bruto Setahun", _money(ann.get("annual_taxable_gross"))),
            ("Biaya Jabatan", _money(ann.get("biaya_jabatan"))),
            ("Iuran JHT + JP Pekerja", _money(ann.get("jht_jp_employee"))),
            (f"PTKP ({ann.get('ptkp_status')})", _money(ann.get("ptkp_annual"))),
            ("Penghasilan Kena Pajak", _money(ann.get("pkp"))),
            ("PPh 21 Setahun (Pasal 17)", _money(ann.get("annual_tax"))),
            ("Sudah Dipotong Jan–Nov", _money(ann.get("already_withheld"))),
        ]
    if tax.get("non_npwp_surcharge"):
        tax_rows.append(("Tambahan 20% tanpa NPWP", _money(tax.get("non_npwp_surcharge"))))
    tax_rows.append(("PPh 21 Masa Ini", _money(totals.get("pph21"))))

    bpjs_rows = [
        ("Dasar Upah BPJS", _money(bpjs.get("wage_base"))),
        ("BPJS Kesehatan (4%)", _money((bpjs.get("kesehatan") or {}).get("employer"))),
        ("BPJS JHT (3,7%)", _money((bpjs.get("jht") or {}).get("employer"))),
        ("BPJS JP (2%)", _money((bpjs.get("jp") or {}).get("employer"))),
        (f"JKK ({(bpjs.get('jkk') or {}).get('risk_label', '-')})",
         _money((bpjs.get("jkk") or {}).get("employer"))),
        ("JKM (0,3%)", _money((bpjs.get("jkm") or {}).get("employer"))),
        ("Total Iuran Pemberi Kerja", _money(totals.get("bpjs_employer"))),
    ]

    detail = Table(
        [[
            Table([[Paragraph("RINCIAN PPh PASAL 21", st["h2"])],
                   [_kv_table(tax_rows, st, [col_w * 0.55, col_w * 0.42])]],
                  colWidths=[col_w]),
            Table([[Paragraph("IURAN DITANGGUNG PERUSAHAAN", st["h2"])],
                   [_kv_table(bpjs_rows, st, [col_w * 0.55, col_w * 0.42])]],
                  colWidths=[col_w]),
        ]],
        colWidths=[col_w, col_w],
    )
    detail.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story += [detail, Spacer(1, 14)]

    story.append(Paragraph(
        "Dokumen ini dihasilkan otomatis oleh sistem HRIS &amp; Payroll dan bersifat rahasia. "
        f"Dicetak pada {generated_at or '-'}.",
        st["foot"],
    ))

    doc.build(story)
    return buf.getvalue()
