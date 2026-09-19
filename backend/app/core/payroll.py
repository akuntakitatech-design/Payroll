"""Mesin perhitungan payroll (murni, tanpa akses database).

Semua rumus mengikuti regulasi Indonesia:
  - BPJS Kesehatan : batas upah Rp12.000.000; pekerja 1%, pemberi kerja 4%
  - BPJS JHT       : tanpa batas upah; pekerja 2%, pemberi kerja 3,7%
  - BPJS JP        : batas upah Rp11.086.300 (1 Mar 2026); pekerja 1%, pemberi kerja 2%
  - JKK            : pemberi kerja 0,24%–1,74% sesuai kelas risiko
  - JKM            : pemberi kerja 0,3%
  - Lembur         : upah/jam = upah sebulan / 173; jam ke-1 1,5x, jam berikutnya 2x
  - PPh 21         : TER bulanan (Jan–Nov) dan rekonsiliasi Pasal 17 di Desember

Semua parameter statutori bisa ditimpa lewat `StatutoryConfig` sehingga HR dapat
mengubahnya dari menu Kebijakan Perusahaan tanpa mengubah kode.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .ter import (
    BIAYA_JABATAN_MONTHLY_CAP,
    BIAYA_JABATAN_RATE,
    article_17_tax,
    ptkp_annual,
    ter_category,
    ter_rate_for_category,
)

DEFAULT_WORKING_DAYS = 22
OVERTIME_DIVISOR = 173  # PP 35/2021: upah/jam = upah sebulan / 173

JKK_RISK_CLASSES = {
    "sangat_rendah": {"label": "Sangat Rendah", "rate": 0.0024},
    "rendah": {"label": "Rendah", "rate": 0.0054},
    "sedang": {"label": "Sedang", "rate": 0.0089},
    "tinggi": {"label": "Tinggi", "rate": 0.0127},
    "sangat_tinggi": {"label": "Sangat Tinggi", "rate": 0.0174},
}

MONTH_NAMES_ID = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


@dataclass
class StatutoryConfig:
    """Parameter statutori yang dapat diubah HR (default = ketentuan 2026)."""

    bpjs_kes_cap: float = 12_000_000
    bpjs_kes_employee_rate: float = 0.01
    bpjs_kes_employer_rate: float = 0.04

    jht_cap: Optional[float] = None  # tanpa batas
    jht_employee_rate: float = 0.02
    jht_employer_rate: float = 0.037

    jp_cap: float = 11_086_300
    jp_employee_rate: float = 0.01
    jp_employer_rate: float = 0.02

    jkk_risk_class: str = "sedang"
    jkm_employer_rate: float = 0.003

    default_working_days: int = DEFAULT_WORKING_DAYS
    overtime_divisor: int = OVERTIME_DIVISOR
    overtime_first_hour_multiplier: float = 1.5
    overtime_next_hour_multiplier: float = 2.0

    # Tunjangan BPJS yang dibayar pemberi kerja merupakan natura yang menambah
    # penghasilan bruto pekerja untuk keperluan PPh 21.
    employer_bpjs_is_taxable: bool = True
    # Surcharge 20% bagi pekerja tanpa NPWP. Default OFF.
    non_npwp_surcharge: bool = False
    non_npwp_surcharge_rate: float = 0.20

    @property
    def jkk_employer_rate(self) -> float:
        entry = JKK_RISK_CLASSES.get(self.jkk_risk_class) or JKK_RISK_CLASSES["sedang"]
        return entry["rate"]

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "StatutoryConfig":
        data = data or {}
        allowed = {f for f in cls.__dataclass_fields__}  # noqa: SLF001
        return cls(**{k: v for k, v in data.items() if k in allowed and v is not None})

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["jkk_employer_rate"] = self.jkk_employer_rate
        return out


@dataclass
class ComponentInput:
    """Satu komponen gaji (tunjangan atau potongan)."""

    code: str
    name: str
    kind: str  # "earning" | "deduction"
    amount: float = 0.0
    taxable: bool = True
    prorate: bool = False  # ikut dipotong bila ada hari tidak dibayar
    include_in_bpjs_base: bool = False


@dataclass
class EmployeeInput:
    """Data yang dibutuhkan mesin payroll untuk satu karyawan."""

    employee_id: str
    full_name: str
    employee_number: Optional[str] = None
    basic_salary: float = 0.0
    ptkp_status: str = "TK/0"
    has_npwp: bool = True
    join_date: Optional[str] = None
    job_title: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    components: List[ComponentInput] = field(default_factory=list)
    # penyesuaian per periode (diinput HR)
    working_days: Optional[int] = None
    unpaid_days: float = 0.0
    overtime_hours: float = 0.0
    bpjs_kesehatan_enrolled: bool = True
    bpjs_jht_enrolled: bool = True
    bpjs_jp_enrolled: bool = True


def _round_rupiah(value: float) -> float:
    """Rupiah tidak memakai sen — bulatkan ke rupiah terdekat."""
    return float(round(value or 0.0))


def round_down_thousand(value: float) -> float:
    """Penghasilan Kena Pajak dibulatkan ke bawah ke ribuan penuh."""
    return float(int(max(0.0, value or 0.0) // 1000) * 1000)


def overtime_pay(monthly_wage: float, hours: float, cfg: StatutoryConfig) -> float:
    """Upah lembur: jam pertama 1,5x, jam berikutnya 2x dari upah/jam (upah/173)."""
    hours = max(0.0, float(hours or 0))
    if hours <= 0 or monthly_wage <= 0:
        return 0.0
    hourly = float(monthly_wage) / cfg.overtime_divisor
    first = min(hours, 1.0) * cfg.overtime_first_hour_multiplier
    rest = max(0.0, hours - 1.0) * cfg.overtime_next_hour_multiplier
    return _round_rupiah(hourly * (first + rest))


def compute_payslip(
    employee: EmployeeInput,
    cfg: Optional[StatutoryConfig] = None,
    month: int = 1,
    year: int = 2026,
    ytd_taxable_gross: float = 0.0,
    ytd_pph21_withheld: float = 0.0,
    ytd_jht_jp_employee: float = 0.0,
    ytd_months: int = 0,
    is_final_period: Optional[bool] = None,
) -> Dict[str, Any]:
    """Hitung satu slip gaji.

    `is_final_period` default: True bila month == 12 (rekonsiliasi Pasal 17).
    Untuk masa pajak terakhir, argumen `ytd_*` wajib berisi akumulasi Jan–Nov.
    """
    cfg = cfg or StatutoryConfig()
    if is_final_period is None:
        is_final_period = month == 12

    working_days = int(employee.working_days or cfg.default_working_days)
    if working_days <= 0:
        working_days = cfg.default_working_days
    unpaid_days = max(0.0, min(float(employee.unpaid_days or 0), working_days))
    paid_ratio = (working_days - unpaid_days) / working_days if working_days else 1.0

    basic_full = _round_rupiah(employee.basic_salary)
    basic_paid = _round_rupiah(basic_full * paid_ratio)
    absence_deduction = _round_rupiah(basic_full - basic_paid)

    # ---------------- penghasilan ----------------
    earnings: List[Dict[str, Any]] = [
        {
            "code": "BASIC",
            "name": "Gaji Pokok",
            "amount": basic_paid,
            "taxable": True,
            "prorated": unpaid_days > 0,
        }
    ]
    bpjs_base_extra = 0.0
    for comp in employee.components:
        if comp.kind != "earning":
            continue
        amount = _round_rupiah(comp.amount * (paid_ratio if comp.prorate else 1.0))
        if amount == 0:
            continue
        earnings.append(
            {
                "code": comp.code,
                "name": comp.name,
                "amount": amount,
                "taxable": comp.taxable,
                "prorated": comp.prorate and unpaid_days > 0,
            }
        )
        if comp.include_in_bpjs_base:
            bpjs_base_extra += amount

    ot_pay = overtime_pay(basic_full, employee.overtime_hours, cfg)
    if ot_pay > 0:
        earnings.append(
            {
                "code": "OVERTIME",
                "name": f"Lembur ({employee.overtime_hours:g} jam)",
                "amount": ot_pay,
                "taxable": True,
                "prorated": False,
            }
        )

    gross_earnings = _round_rupiah(sum(e["amount"] for e in earnings))
    taxable_earnings = _round_rupiah(sum(e["amount"] for e in earnings if e["taxable"]))

    # ---------------- BPJS ----------------
    bpjs_wage_base = _round_rupiah(basic_paid + bpjs_base_extra)

    kes_base = min(bpjs_wage_base, cfg.bpjs_kes_cap) if employee.bpjs_kesehatan_enrolled else 0.0
    jht_base = (
        min(bpjs_wage_base, cfg.jht_cap) if cfg.jht_cap else bpjs_wage_base
    ) if employee.bpjs_jht_enrolled else 0.0
    jp_base = min(bpjs_wage_base, cfg.jp_cap) if employee.bpjs_jp_enrolled else 0.0

    bpjs = {
        "wage_base": bpjs_wage_base,
        "kesehatan": {
            "base": _round_rupiah(kes_base),
            "capped": bool(employee.bpjs_kesehatan_enrolled and bpjs_wage_base > cfg.bpjs_kes_cap),
            "employee": _round_rupiah(kes_base * cfg.bpjs_kes_employee_rate),
            "employer": _round_rupiah(kes_base * cfg.bpjs_kes_employer_rate),
            "employee_rate": cfg.bpjs_kes_employee_rate,
            "employer_rate": cfg.bpjs_kes_employer_rate,
        },
        "jht": {
            "base": _round_rupiah(jht_base),
            "capped": bool(cfg.jht_cap and employee.bpjs_jht_enrolled and bpjs_wage_base > cfg.jht_cap),
            "employee": _round_rupiah(jht_base * cfg.jht_employee_rate),
            "employer": _round_rupiah(jht_base * cfg.jht_employer_rate),
            "employee_rate": cfg.jht_employee_rate,
            "employer_rate": cfg.jht_employer_rate,
        },
        "jp": {
            "base": _round_rupiah(jp_base),
            "capped": bool(employee.bpjs_jp_enrolled and bpjs_wage_base > cfg.jp_cap),
            "employee": _round_rupiah(jp_base * cfg.jp_employee_rate),
            "employer": _round_rupiah(jp_base * cfg.jp_employer_rate),
            "employee_rate": cfg.jp_employee_rate,
            "employer_rate": cfg.jp_employer_rate,
        },
        "jkk": {
            "base": _round_rupiah(bpjs_wage_base),
            "employee": 0.0,
            "employer": _round_rupiah(bpjs_wage_base * cfg.jkk_employer_rate),
            "employer_rate": cfg.jkk_employer_rate,
            "risk_class": cfg.jkk_risk_class,
            "risk_label": JKK_RISK_CLASSES.get(cfg.jkk_risk_class, {}).get("label", "Sedang"),
        },
        "jkm": {
            "base": _round_rupiah(bpjs_wage_base),
            "employee": 0.0,
            "employer": _round_rupiah(bpjs_wage_base * cfg.jkm_employer_rate),
            "employer_rate": cfg.jkm_employer_rate,
        },
    }
    bpjs_employee_total = _round_rupiah(
        bpjs["kesehatan"]["employee"] + bpjs["jht"]["employee"] + bpjs["jp"]["employee"]
    )
    bpjs_employer_total = _round_rupiah(
        bpjs["kesehatan"]["employer"]
        + bpjs["jht"]["employer"]
        + bpjs["jp"]["employer"]
        + bpjs["jkk"]["employer"]
        + bpjs["jkm"]["employer"]
    )
    # Iuran pemberi kerja yang menjadi natura kena pajak bagi pekerja:
    # BPJS Kesehatan, JKK dan JKM. JHT & JP pemberi kerja tidak kena pajak.
    employer_taxable_benefit = (
        _round_rupiah(
            bpjs["kesehatan"]["employer"] + bpjs["jkk"]["employer"] + bpjs["jkm"]["employer"]
        )
        if cfg.employer_bpjs_is_taxable
        else 0.0
    )
    bpjs["employee_total"] = bpjs_employee_total
    bpjs["employer_total"] = bpjs_employer_total
    bpjs["employer_taxable_benefit"] = employer_taxable_benefit

    # ---------------- PPh 21 ----------------
    taxable_gross = _round_rupiah(taxable_earnings + employer_taxable_benefit)
    jht_jp_employee = _round_rupiah(bpjs["jht"]["employee"] + bpjs["jp"]["employee"])

    category = ter_category(employee.ptkp_status)
    tax: Dict[str, Any] = {
        "method": "ter",
        "method_label": "TER Bulanan (PMK 168/2023)",
        "ptkp_status": employee.ptkp_status,
        "ter_category": category,
        "taxable_gross": taxable_gross,
        "has_npwp": employee.has_npwp,
    }

    if is_final_period:
        annual = compute_december_recalc(
            monthly_taxable_gross=taxable_gross,
            ytd_taxable_gross=ytd_taxable_gross,
            ytd_pph21_withheld=ytd_pph21_withheld,
            monthly_jht_jp_employee=jht_jp_employee,
            ytd_jht_jp_employee=ytd_jht_jp_employee,
            ptkp_status=employee.ptkp_status,
            months_worked=(ytd_months or 11) + 1,
            cfg=cfg,
        )
        tax.update(annual)
        tax["method"] = "article_17_annual"
        tax["method_label"] = "Rekonsiliasi Tahunan Pasal 17 (masa pajak terakhir)"
        pph21 = annual["pph21"]
    else:
        rate = ter_rate_for_category(category, taxable_gross)
        pph21 = _round_rupiah(taxable_gross * rate)
        if cfg.non_npwp_surcharge and not employee.has_npwp:
            surcharge = _round_rupiah(pph21 * cfg.non_npwp_surcharge_rate)
            tax["non_npwp_surcharge"] = surcharge
            pph21 = _round_rupiah(pph21 + surcharge)
        tax["ter_rate"] = rate
        tax["ter_rate_percent"] = round(rate * 100, 4)
        tax["pph21"] = pph21

    # ---------------- potongan ----------------
    deductions: List[Dict[str, Any]] = []
    if absence_deduction > 0:
        deductions.append(
            {
                "code": "ABSENCE",
                "name": f"Potongan Tidak Hadir ({unpaid_days:g} hari)",
                "amount": absence_deduction,
                "group": "absence",
                "informational": True,
            }
        )
    if bpjs["kesehatan"]["employee"] > 0:
        deductions.append({"code": "BPJS_KES", "name": "BPJS Kesehatan (1%)", "amount": bpjs["kesehatan"]["employee"], "group": "bpjs"})
    if bpjs["jht"]["employee"] > 0:
        deductions.append({"code": "BPJS_JHT", "name": "BPJS JHT (2%)", "amount": bpjs["jht"]["employee"], "group": "bpjs"})
    if bpjs["jp"]["employee"] > 0:
        deductions.append({"code": "BPJS_JP", "name": "BPJS Jaminan Pensiun (1%)", "amount": bpjs["jp"]["employee"], "group": "bpjs"})
    if pph21 != 0:
        deductions.append({"code": "PPH21", "name": "PPh Pasal 21", "amount": _round_rupiah(pph21), "group": "tax"})
    for comp in employee.components:
        if comp.kind != "deduction":
            continue
        amount = _round_rupiah(comp.amount * (paid_ratio if comp.prorate else 1.0))
        if amount == 0:
            continue
        deductions.append({"code": comp.code, "name": comp.name, "amount": amount, "group": "other"})

    # potongan tidak hadir sudah tercermin di gaji pokok terproratakan,
    # jadi tidak dijumlahkan lagi (informational only).
    total_deductions = _round_rupiah(
        sum(d["amount"] for d in deductions if not d.get("informational"))
    )
    net_pay = _round_rupiah(gross_earnings - total_deductions)

    return {
        "employee_id": employee.employee_id,
        "employee_number": employee.employee_number,
        "full_name": employee.full_name,
        "job_title": employee.job_title,
        "bank_name": employee.bank_name,
        "bank_account_number": employee.bank_account_number,
        "period": {
            "year": year,
            "month": month,
            "label": f"{MONTH_NAMES_ID[month - 1]} {year}",
            "is_final_period": bool(is_final_period),
        },
        "attendance": {
            "working_days": working_days,
            "unpaid_days": unpaid_days,
            "paid_days": working_days - unpaid_days,
            "paid_ratio": round(paid_ratio, 6),
            "overtime_hours": float(employee.overtime_hours or 0),
        },
        "basic_salary": basic_full,
        "basic_salary_paid": basic_paid,
        "earnings": earnings,
        "deductions": deductions,
        "bpjs": bpjs,
        "tax": tax,
        "totals": {
            "gross": gross_earnings,
            "taxable_gross": taxable_gross,
            "bpjs_employee": bpjs_employee_total,
            "bpjs_employer": bpjs_employer_total,
            "pph21": _round_rupiah(pph21),
            "other_deductions": _round_rupiah(
                sum(d["amount"] for d in deductions if d.get("group") == "other")
            ),
            "total_deductions": total_deductions,
            "net_pay": net_pay,
            "employer_cost": _round_rupiah(gross_earnings + bpjs_employer_total),
        },
        "jht_jp_employee": jht_jp_employee,
    }


def compute_december_recalc(
    monthly_taxable_gross: float,
    ytd_taxable_gross: float,
    ytd_pph21_withheld: float,
    monthly_jht_jp_employee: float,
    ytd_jht_jp_employee: float,
    ptkp_status: str,
    months_worked: int = 12,
    cfg: Optional[StatutoryConfig] = None,
) -> Dict[str, Any]:
    """Rekonsiliasi PPh 21 masa pajak terakhir memakai tarif Pasal 17.

    PPh 21 Desember = PPh terutang setahun − PPh yang sudah dipotong Jan–Nov.
    Nilai negatif berarti kelebihan potong (dikembalikan ke pekerja).
    """
    cfg = cfg or StatutoryConfig()
    months = max(1, min(12, int(months_worked or 12)))

    annual_gross = _round_rupiah(float(ytd_taxable_gross or 0) + float(monthly_taxable_gross or 0))
    biaya_jabatan = _round_rupiah(
        min(annual_gross * BIAYA_JABATAN_RATE, BIAYA_JABATAN_MONTHLY_CAP * months)
    )
    jht_jp_total = _round_rupiah(float(ytd_jht_jp_employee or 0) + float(monthly_jht_jp_employee or 0))
    net_annual = max(0.0, annual_gross - biaya_jabatan - jht_jp_total)

    ptkp = ptkp_annual(ptkp_status)
    pkp = round_down_thousand(max(0.0, net_annual - ptkp))
    annual_tax = _round_rupiah(article_17_tax(pkp))

    if cfg.non_npwp_surcharge:
        pass  # surcharge hanya diterapkan pada pemotongan bulanan

    already = _round_rupiah(ytd_pph21_withheld)
    december_tax = _round_rupiah(annual_tax - already)

    return {
        "pph21": december_tax,
        "annual": {
            "months_worked": months,
            "annual_taxable_gross": annual_gross,
            "biaya_jabatan": biaya_jabatan,
            "jht_jp_employee": jht_jp_total,
            "net_annual_income": _round_rupiah(net_annual),
            "ptkp_status": ptkp_status,
            "ptkp_annual": float(ptkp),
            "pkp": pkp,
            "annual_tax": annual_tax,
            "already_withheld": already,
            "december_adjustment": december_tax,
            "is_refund": december_tax < 0,
        },
    }


def summarize_run(payslips: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Total satu payroll run."""
    def total(path: str) -> float:
        return _round_rupiah(sum((p.get("totals") or {}).get(path, 0) for p in payslips))

    return {
        "employee_count": len(payslips),
        "gross": total("gross"),
        "taxable_gross": total("taxable_gross"),
        "bpjs_employee": total("bpjs_employee"),
        "bpjs_employer": total("bpjs_employer"),
        "pph21": total("pph21"),
        "other_deductions": total("other_deductions"),
        "total_deductions": total("total_deductions"),
        "net_pay": total("net_pay"),
        "employer_cost": total("employer_cost"),
    }


# --------------------------------------------------------------------------
# Angka menjadi kata (untuk slip gaji)
# --------------------------------------------------------------------------
_UNITS = ["", "satu", "dua", "tiga", "empat", "lima", "enam", "tujuh", "delapan", "sembilan",
          "sepuluh", "sebelas"]


def number_to_words_id(value: float) -> str:
    """Konversi angka ke kata Bahasa Indonesia (untuk slip gaji)."""
    n = int(abs(round(value or 0)))
    prefix = "minus " if (value or 0) < 0 else ""

    def helper(num: int) -> str:
        if num < 12:
            return _UNITS[num]
        if num < 20:
            return helper(num - 10) + " belas"
        if num < 100:
            return helper(num // 10) + " puluh" + ((" " + helper(num % 10)) if num % 10 else "")
        if num < 200:
            return "seratus" + ((" " + helper(num - 100)) if num > 100 else "")
        if num < 1000:
            return helper(num // 100) + " ratus" + ((" " + helper(num % 100)) if num % 100 else "")
        if num < 2000:
            return "seribu" + ((" " + helper(num - 1000)) if num > 1000 else "")
        if num < 1_000_000:
            return helper(num // 1000) + " ribu" + ((" " + helper(num % 1000)) if num % 1000 else "")
        if num < 1_000_000_000:
            return helper(num // 1_000_000) + " juta" + ((" " + helper(num % 1_000_000)) if num % 1_000_000 else "")
        if num < 1_000_000_000_000:
            return helper(num // 1_000_000_000) + " miliar" + ((" " + helper(num % 1_000_000_000)) if num % 1_000_000_000 else "")
        return helper(num // 1_000_000_000_000) + " triliun" + (
            (" " + helper(num % 1_000_000_000_000)) if num % 1_000_000_000_000 else ""
        )

    if n == 0:
        return "nol rupiah"
    words = " ".join(helper(n).split())
    return f"{prefix}{words} rupiah"
