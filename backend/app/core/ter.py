"""Tarif Efektif Rata-rata (TER) PPh Pasal 21 — PMK 168/2023 (Lampiran).

Tabel di bawah ini dikutip dari Lampiran PMK Nomor 168 Tahun 2023 dan sudah
diverifikasi terhadap dokumen resmi Direktorat Jenderal Pajak:
  - Kategori A : 44 lapisan, bebas potong s.d. Rp5.400.000, puncak >Rp1,4 M = 34%
  - Kategori B : 40 lapisan, bebas potong s.d. Rp6.200.000, puncak >Rp1,405 M = 34%
  - Kategori C : 41 lapisan, bebas potong s.d. Rp6.600.000, puncak >Rp1,419 M = 34%

Setiap entri berbentuk (batas_atas, tarif_desimal). `batas_atas = None` berarti
lapisan terakhir (tanpa batas atas). Pencocokan memakai `bruto <= batas_atas`
karena lapisan resmi ditulis "x.000.001 - y.000.000".

TER hanya dipakai untuk masa pajak Januari–November. Masa pajak terakhir
(Desember) dihitung ulang memakai tarif progresif Pasal 17 (lihat app/core/payroll.py).
"""
from typing import List, Optional, Tuple

Bracket = Tuple[Optional[int], float]

# --------------------------------------------------------------------------
# Kategori A — PTKP TK/0, TK/1, K/0
# --------------------------------------------------------------------------
TER_A: List[Bracket] = [
    (5_400_000, 0.0000),
    (5_650_000, 0.0025),
    (5_950_000, 0.0050),
    (6_300_000, 0.0075),
    (6_750_000, 0.0100),
    (7_500_000, 0.0125),
    (8_550_000, 0.0150),
    (9_650_000, 0.0175),
    (10_050_000, 0.0200),
    (10_350_000, 0.0225),
    (10_700_000, 0.0250),
    (11_050_000, 0.0300),
    (11_600_000, 0.0350),
    (12_500_000, 0.0400),
    (13_750_000, 0.0500),
    (15_100_000, 0.0600),
    (16_950_000, 0.0700),
    (19_750_000, 0.0800),
    (24_150_000, 0.0900),
    (26_450_000, 0.1000),
    (28_000_000, 0.1100),
    (30_050_000, 0.1200),
    (32_400_000, 0.1300),
    (35_400_000, 0.1400),
    (39_100_000, 0.1500),
    (43_850_000, 0.1600),
    (47_800_000, 0.1700),
    (51_400_000, 0.1800),
    (56_300_000, 0.1900),
    (62_200_000, 0.2000),
    (68_600_000, 0.2100),
    (77_500_000, 0.2200),
    (89_000_000, 0.2300),
    (103_000_000, 0.2400),
    (125_000_000, 0.2500),
    (157_000_000, 0.2600),
    (206_000_000, 0.2700),
    (337_000_000, 0.2800),
    (454_000_000, 0.2900),
    (550_000_000, 0.3000),
    (695_000_000, 0.3100),
    (910_000_000, 0.3200),
    (1_400_000_000, 0.3300),
    (None, 0.3400),
]

# --------------------------------------------------------------------------
# Kategori B — PTKP TK/2, TK/3, K/1, K/2
# --------------------------------------------------------------------------
TER_B: List[Bracket] = [
    (6_200_000, 0.0000),
    (6_500_000, 0.0025),
    (6_850_000, 0.0050),
    (7_300_000, 0.0075),
    (9_200_000, 0.0100),
    (10_750_000, 0.0150),
    (11_250_000, 0.0200),
    (11_600_000, 0.0250),
    (12_600_000, 0.0300),
    (13_600_000, 0.0400),
    (14_950_000, 0.0500),
    (16_400_000, 0.0600),
    (18_450_000, 0.0700),
    (21_850_000, 0.0800),
    (26_000_000, 0.0900),
    (27_700_000, 0.1000),
    (29_350_000, 0.1100),
    (31_450_000, 0.1200),
    (33_950_000, 0.1300),
    (37_100_000, 0.1400),
    (41_100_000, 0.1500),
    (45_800_000, 0.1600),
    (49_500_000, 0.1700),
    (53_800_000, 0.1800),
    (58_500_000, 0.1900),
    (64_000_000, 0.2000),
    (71_000_000, 0.2100),
    (80_000_000, 0.2200),
    (93_000_000, 0.2300),
    (109_000_000, 0.2400),
    (129_000_000, 0.2500),
    (163_000_000, 0.2600),
    (211_000_000, 0.2700),
    (374_000_000, 0.2800),
    (459_000_000, 0.2900),
    (555_000_000, 0.3000),
    (704_000_000, 0.3100),
    (957_000_000, 0.3200),
    (1_405_000_000, 0.3300),
    (None, 0.3400),
]

# --------------------------------------------------------------------------
# Kategori C — PTKP K/3
# --------------------------------------------------------------------------
TER_C: List[Bracket] = [
    (6_600_000, 0.0000),
    (6_950_000, 0.0025),
    (7_350_000, 0.0050),
    (7_800_000, 0.0075),
    (8_850_000, 0.0100),
    (9_800_000, 0.0125),
    (10_950_000, 0.0150),
    (11_200_000, 0.0175),
    (12_050_000, 0.0200),
    (12_950_000, 0.0300),
    (14_150_000, 0.0400),
    (15_550_000, 0.0500),
    (17_050_000, 0.0600),
    (19_500_000, 0.0700),
    (22_700_000, 0.0800),
    (26_600_000, 0.0900),
    (28_100_000, 0.1000),
    (30_100_000, 0.1100),
    (32_600_000, 0.1200),
    (35_400_000, 0.1300),
    (38_900_000, 0.1400),
    (43_000_000, 0.1500),
    (47_400_000, 0.1600),
    (51_200_000, 0.1700),
    (55_800_000, 0.1800),
    (60_400_000, 0.1900),
    (66_700_000, 0.2000),
    (74_500_000, 0.2100),
    (83_200_000, 0.2200),
    (95_600_000, 0.2300),
    (110_000_000, 0.2400),
    (134_000_000, 0.2500),
    (169_000_000, 0.2600),
    (221_000_000, 0.2700),
    (390_000_000, 0.2800),
    (463_000_000, 0.2900),
    (561_000_000, 0.3000),
    (709_000_000, 0.3100),
    (965_000_000, 0.3200),
    (1_419_000_000, 0.3300),
    (None, 0.3400),
]

TER_TABLES = {"A": TER_A, "B": TER_B, "C": TER_C}

# PTKP status -> kategori TER (PMK 168/2023 Lampiran)
PTKP_TO_CATEGORY = {
    "TK/0": "A", "TK/1": "A", "K/0": "A",
    "TK/2": "B", "TK/3": "B", "K/1": "B", "K/2": "B",
    "K/3": "C",
}

PTKP_STATUSES = ["TK/0", "TK/1", "TK/2", "TK/3", "K/0", "K/1", "K/2", "K/3"]

PTKP_LABELS = {
    "TK/0": "Tidak Kawin, tanpa tanggungan",
    "TK/1": "Tidak Kawin, 1 tanggungan",
    "TK/2": "Tidak Kawin, 2 tanggungan",
    "TK/3": "Tidak Kawin, 3 tanggungan",
    "K/0": "Kawin, tanpa tanggungan",
    "K/1": "Kawin, 1 tanggungan",
    "K/2": "Kawin, 2 tanggungan",
    "K/3": "Kawin, 3 tanggungan",
}

# Nilai PTKP setahun (UU HPP / PMK 101)
PTKP_BASE = 54_000_000          # wajib pajak sendiri
PTKP_MARRIED = 4_500_000        # tambahan status kawin
PTKP_DEPENDENT = 4_500_000      # tambahan per tanggungan (maks 3)
MAX_DEPENDENTS = 3

# Tarif progresif Pasal 17 UU PPh (untuk rekonsiliasi Desember / setahun)
ARTICLE_17_BRACKETS: List[Bracket] = [
    (60_000_000, 0.05),
    (250_000_000, 0.15),
    (500_000_000, 0.25),
    (5_000_000_000, 0.30),
    (None, 0.35),
]

# Biaya jabatan: 5% dari penghasilan bruto, maksimal Rp500.000/bulan
BIAYA_JABATAN_RATE = 0.05
BIAYA_JABATAN_MONTHLY_CAP = 500_000


class TerError(ValueError):
    pass


def ter_category(ptkp_status: str) -> str:
    """Kategori TER (A/B/C) berdasarkan status PTKP per 1 Januari tahun pajak."""
    key = (ptkp_status or "").strip().upper().replace(" ", "")
    if key not in PTKP_TO_CATEGORY:
        raise TerError(
            f"Status PTKP '{ptkp_status}' tidak dikenal. "
            f"Gunakan salah satu: {', '.join(PTKP_STATUSES)}."
        )
    return PTKP_TO_CATEGORY[key]


def ter_rate(ptkp_status: str, monthly_gross: float) -> float:
    """Tarif efektif bulanan (desimal) untuk penghasilan bruto sebulan."""
    return ter_rate_for_category(ter_category(ptkp_status), monthly_gross)


def ter_rate_for_category(category: str, monthly_gross: float) -> float:
    cat = (category or "").strip().upper()
    table = TER_TABLES.get(cat)
    if table is None:
        raise TerError(f"Kategori TER '{category}' tidak dikenal (pilih A, B, atau C).")
    gross = max(0.0, float(monthly_gross or 0))
    for upper, rate in table:
        if upper is None or gross <= upper:
            return rate
    return table[-1][1]


def ptkp_annual(ptkp_status: str) -> int:
    """Nilai PTKP setahun untuk status tertentu."""
    key = (ptkp_status or "").strip().upper().replace(" ", "")
    if key not in PTKP_TO_CATEGORY:
        raise TerError(f"Status PTKP '{ptkp_status}' tidak dikenal.")
    married = key.startswith("K/")
    dependents = min(int(key.split("/")[1]), MAX_DEPENDENTS)
    total = PTKP_BASE
    if married:
        total += PTKP_MARRIED
    total += dependents * PTKP_DEPENDENT
    return total


def article_17_tax(taxable_income: float) -> float:
    """PPh terutang setahun memakai tarif progresif Pasal 17 UU PPh."""
    remaining = max(0.0, float(taxable_income or 0))
    if remaining <= 0:
        return 0.0
    tax = 0.0
    lower = 0
    for upper, rate in ARTICLE_17_BRACKETS:
        if upper is None:
            tax += remaining * rate
            remaining = 0.0
            break
        span = upper - lower
        portion = min(remaining, span)
        tax += portion * rate
        remaining -= portion
        lower = upper
        if remaining <= 0:
            break
    return tax


def validate_tables() -> None:
    """Sanity check tabel TER: jumlah lapisan, urutan naik, dan lapisan terbuka."""
    expected_counts = {"A": 44, "B": 40, "C": 41}
    for cat, table in TER_TABLES.items():
        if len(table) != expected_counts[cat]:
            raise TerError(
                f"Kategori {cat} harus punya {expected_counts[cat]} lapisan, "
                f"ditemukan {len(table)}."
            )
        if table[-1][0] is not None:
            raise TerError(f"Lapisan terakhir kategori {cat} harus tanpa batas atas.")
        uppers = [u for u, _ in table[:-1]]
        if any(uppers[i] >= uppers[i + 1] for i in range(len(uppers) - 1)):
            raise TerError(f"Batas atas kategori {cat} harus naik monoton.")
        rates = [r for _, r in table]
        if any(rates[i] > rates[i + 1] for i in range(len(rates) - 1)):
            raise TerError(f"Tarif kategori {cat} harus naik monoton.")
        if rates[0] != 0.0:
            raise TerError(f"Lapisan pertama kategori {cat} harus 0%.")
        if rates[-1] != 0.34:
            raise TerError(f"Lapisan terakhir kategori {cat} harus 34%.")
