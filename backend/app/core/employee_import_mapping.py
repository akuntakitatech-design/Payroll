"""Upgrade 01E - Mapping Excel TERPUSAT untuk Migrasi / Impor Data Karyawan.

SATU-SATUNYA tempat definisi sheet, header, field target, wajib/opsional, tipe, validator,
lookup master dan flag sensitif. Saat file sensus PT REAL aktual diterima, cukup ubah
daftar di file ini (header alias, kolom baru, baris header/data) tanpa menyentuh engine.

Catatan: mapping ini adalah DRAFT (`MAPPING_VERSION`) dan belum final sampai file sensus
PT REAL aktual diterima.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

MAPPING_VERSION = "01E-draft-1"

# target:
#   employee  -> kolom tabel `employees` (update memakai aturan blank-preserve)
#   placement -> kolom organisasi/penempatan employees (+ service 01D untuk project)
#   status    -> Status Karyawan 01B (lewat helper 01B, bukan mutasi langsung)
#   family    -> `employee_family_members` (01C)
#   meta      -> nilai pendukung (tanggal mulai penempatan, tanggal efektif status, perusahaan, dll.)
#   key       -> business key lintas sheet (nomor karyawan)


@dataclass(frozen=True)
class Col:
    key: str
    headers: Tuple[str, ...]  # headers[0] = judul di template, sisanya alias yang juga diterima
    type: str = "text"  # text|name|date|date_past|digits|email|phone|enum|master|bool
    target: str = "employee"
    required: bool = False  # wajib diisi di setiap baris sheet
    required_new: bool = False  # wajib untuk karyawan BARU saja
    validator: Optional[str] = None  # nama aturan tambahan (lihat DIGIT_RULES / ENUMS)
    master: Optional[str] = None  # kunci lookup master (lihat MASTER_SOURCES)
    sensitive: bool = False  # nilai dimasking di preview/error/audit
    hint: str = ""
    label: str = ""

    @property
    def title(self) -> str:
        return self.label or self.headers[0].rstrip("*").strip()


@dataclass(frozen=True)
class SheetSpec:
    name: str
    kind: str  # info | single (maks 1 baris/karyawan) | multi (banyak baris/karyawan)
    required: bool = False
    columns: Tuple[Col, ...] = field(default_factory=tuple)
    header_row: int = 1
    data_start_row: int = 3  # baris 2 = petunjuk kolom
    description: str = ""


EMP_NO = Col("employee_number", ("Nomor Karyawan*", "NIK Karyawan", "No Karyawan", "No. Karyawan", "Employee Number"),
             target="key", required=True, hint="Business key lintas sheet (wajib, sama persis di semua sheet)")

SHEETS: Tuple[SheetSpec, ...] = (
    SheetSpec("PETUNJUK", "info", description="Petunjuk pengisian (tidak dibaca sebagai data)."),
    SheetSpec("DATA_KARYAWAN", "single", required=True, description="Data pribadi karyawan.", columns=(
        EMP_NO,
        Col("full_name", ("Nama Lengkap*", "Nama", "Nama Karyawan"), "name", required_new=True,
            hint="Wajib untuk karyawan baru, minimal 2 karakter"),
        Col("company", ("Perusahaan", "Nama Perusahaan", "Kode Perusahaan"), "text", target="meta",
            hint="Opsional; bila diisi harus = kode/nama perusahaan aktif"),
        Col("nik", ("NIK KTP", "Nomor KTP", "No KTP"), "digits", validator="nik", sensitive=True,
            hint="16 digit angka"),
        Col("gender", ("Jenis Kelamin",), "enum", validator="gender", hint="L / P"),
        Col("birth_place", ("Tempat Lahir",)),
        Col("birth_date", ("Tanggal Lahir",), "date_past", hint="YYYY-MM-DD"),
        Col("religion", ("Agama",), "enum", validator="religion"),
        Col("marital_status", ("Status Pernikahan",), "enum", validator="marital",
            hint="Belum Menikah / Menikah / Cerai"),
        Col("education", ("Pendidikan Terakhir", "Pendidikan"), "enum", validator="education",
            hint="SD/SMP/SMA/D3/S1/S2/S3"),
        Col("email", ("Email", "Email Pribadi"), "email"),
        Col("phone", ("No. HP", "Telepon", "No HP"), "phone"),
        Col("address", ("Alamat KTP", "Alamat")),
        Col("domicile_address", ("Alamat Domisili",)),
        Col("city", ("Kota",)),
        Col("province", ("Provinsi",)),
        Col("postal_code", ("Kode Pos",)),
        Col("emergency_contact_name", ("Kontak Darurat - Nama", "Nama Kontak Darurat")),
        Col("emergency_contact_phone", ("Kontak Darurat - No. HP", "No HP Kontak Darurat"), "phone"),
        Col("notes", ("Catatan",)),
    )),
    SheetSpec("KEPEGAWAIAN", "single", required=True, description="Kepegawaian, penempatan & status.", columns=(
        EMP_NO,
        Col("employment_status_id", ("Status Kepegawaian",), "master", master="employment_statuses",
            hint="PKWT/PKWTT dsb. (BUKAN Status Karyawan)"),
        Col("join_date", ("Tanggal Masuk",), "date", hint="YYYY-MM-DD"),
        Col("job_title", ("Jabatan (teks)",)),
        Col("position_id", ("Jabatan", "Jabatan (master)"), "master", target="placement", master="positions"),
        Col("department_id", ("Departemen",), "master", target="placement", master="departments"),
        Col("division_id", ("Divisi",), "master", target="placement", master="divisions"),
        Col("branch_id", ("Cabang",), "master", target="placement", master="branches"),
        Col("job_grade_id", ("Grade / Level", "Grade"), "master", master="job_grades"),
        Col("cost_center_id", ("Cost Center",), "master", target="placement", master="cost_centers"),
        Col("project_id", ("Project", "Proyek"), "master", target="placement", master="projects",
            hint="Perubahan project = Pindah Penempatan (01D)"),
        Col("work_location_id", ("Lokasi Kerja / Site", "Lokasi Kerja"), "master", target="placement",
            master="work_locations"),
        Col("placement_start_date", ("Tanggal Mulai Penempatan",), "date_past", target="meta",
            hint="Wajib bila project berubah; kosong = tidak diketahui (tidak dikarang)"),
        Col("employee_status", ("Status Karyawan",), "master", target="status", master="employee_business_statuses",
            hint="Aktif / Standby / Tidak Aktif (01B)"),
        Col("status_effective_date", ("Tanggal Efektif Status",), "date_past", target="meta",
            hint="Wajib bila Status Karyawan berubah"),
        Col("status_reason", ("Alasan Perubahan Status",), target="meta"),
    )),
    SheetSpec("BANK_BPJS", "single", required=True, description="Rekening, NPWP & BPJS (sensitif).", columns=(
        EMP_NO,
        Col("bank_name", ("Nama Bank",)),
        Col("bank_account_number", ("No. Rekening", "Nomor Rekening"), "digits", validator="bank_account",
            sensitive=True),
        Col("bank_account_name", ("Nama Pemilik Rekening",)),
        Col("npwp", ("NPWP",), "digits", validator="npwp", sensitive=True, hint="15/16 digit"),
        Col("bpjs_kesehatan_number", ("No. BPJS Kesehatan",), "digits", validator="bpjs", sensitive=True),
        Col("bpjs_tk_number", ("No. BPJS Ketenagakerjaan",), "digits", validator="bpjs", sensitive=True),
    )),
    SheetSpec("KELUARGA", "multi", required=True, description="Anggota keluarga (boleh banyak baris).", columns=(
        EMP_NO,
        Col("relationship", ("Hubungan*", "Hubungan Keluarga"), "enum", target="family", required=True,
            validator="relationship", hint="Suami/Istri/Anak/Ayah/Ibu/Saudara/Lainnya"),
        Col("full_name", ("Nama Anggota Keluarga*", "Nama"), "name", target="family", required=True),
        Col("nik", ("NIK KTP", "NIK"), "digits", target="family", validator="nik", sensitive=True),
        Col("birth_place", ("Tempat Lahir",), target="family"),
        Col("birth_date", ("Tanggal Lahir",), "date_past", target="family"),
        Col("gender", ("Jenis Kelamin",), "enum", target="family", validator="gender"),
        Col("occupation", ("Pekerjaan",), target="family"),
        Col("phone", ("No. HP",), "phone", target="family"),
        Col("is_emergency_contact", ("Kontak Darurat (Ya/Tidak)", "Kontak Darurat"), "bool", target="family"),
    )),
    SheetSpec("MASTER_REFERENCE", "info", description="Daftar nilai master valid (tidak dibaca sebagai data)."),
)

SHEETS_BY_NAME: Dict[str, SheetSpec] = {s.name: s for s in SHEETS}
DATA_SHEETS: Tuple[SheetSpec, ...] = tuple(s for s in SHEETS if s.kind != "info")

# lookup master -> (tabel, label, filter tambahan)
MASTER_SOURCES: Dict[str, Tuple[str, str]] = {
    "employment_statuses": ("employment_statuses", "Status Kepegawaian"),
    "positions": ("positions", "Jabatan"),
    "departments": ("departments", "Departemen"),
    "divisions": ("divisions", "Divisi"),
    "branches": ("branches", "Cabang"),
    "job_grades": ("job_grades", "Grade / Level"),
    "cost_centers": ("cost_centers", "Cost Center"),
    "projects": ("projects", "Project"),
    "work_locations": ("work_locations", "Lokasi Kerja / Site"),
    "employee_business_statuses": ("employee_business_statuses", "Status Karyawan"),
}

# Nilai enum: input (dinormalisasi lower, tanpa spasi ganda) -> nilai tersimpan (mengikuti UI Profile 360)
ENUMS: Dict[str, Dict[str, str]] = {
    "gender": {"l": "male", "laki-laki": "male", "laki laki": "male", "pria": "male", "male": "male",
               "p": "female", "perempuan": "female", "wanita": "female", "female": "female"},
    "marital": {"belum menikah": "single", "belum kawin": "single", "belum_kawin": "single", "lajang": "single",
                "single": "single", "tk": "single",
                "menikah": "married", "kawin": "married", "married": "married", "k": "married",
                "cerai": "divorced", "duda": "divorced", "janda": "divorced", "cerai hidup": "divorced",
                "cerai mati": "divorced", "divorced": "divorced"},
    "religion": {k: k for k in ("islam", "kristen", "katolik", "hindu", "buddha", "konghucu", "lainnya")}
                | {"protestan": "kristen", "budha": "buddha", "khonghucu": "konghucu"},
    "education": {"sd": "sd", "smp": "smp", "sltp": "smp", "sma": "sma", "smk": "sma", "slta": "sma",
                  "sma/smk": "sma", "d1": "d3", "d2": "d3", "d3": "d3", "diploma": "d3", "d4": "s1",
                  "s1": "s1", "sarjana": "s1", "s2": "s2", "magister": "s2", "s3": "s3", "doktor": "s3"},
    "relationship": {"suami": "SUAMI", "istri": "ISTRI", "anak": "ANAK", "ayah": "AYAH", "ibu": "IBU",
                     "saudara": "SAUDARA", "lainnya": "LAINNYA", "husband": "SUAMI", "wife": "ISTRI"},
}
# enum yang nilai di luar daftar TIDAK error (disimpan apa adanya + warning)
SOFT_ENUMS = {"education"}

# aturan digit: (min, max) atau set panjang
DIGIT_RULES: Dict[str, Tuple[int, int]] = {
    "nik": (16, 16),
    "npwp": (15, 16),
    "bank_account": (5, 30),
    "bpjs": (8, 20),
}

BOOL_TRUE = {"ya", "y", "yes", "true", "1", "benar"}
BOOL_FALSE = {"tidak", "t", "no", "n", "false", "0", "bukan"}

LIMITS = {"max_file_mb": 10, "max_employees": 5000}


def norm_header(text: object) -> str:
    s = str(text or "").replace("*", " ").strip().lower()
    return re.sub(r"\s+", " ", s)


def employee_key(value: object) -> str:
    """Normalisasi business key nomor karyawan untuk pencocokan (case-insensitive, trim)."""
    return re.sub(r"\s+", "", str(value or "")).upper()


def mapping_metadata() -> Dict[str, object]:
    """Metadata mapping untuk UI (sesi berikutnya) / dokumentasi."""
    return {
        "version": MAPPING_VERSION,
        "limits": LIMITS,
        "sheets": [
            {
                "name": s.name, "kind": s.kind, "required": s.required, "description": s.description,
                "header_row": s.header_row, "data_start_row": s.data_start_row,
                "columns": [
                    {"key": c.key, "header": c.headers[0], "aliases": list(c.headers[1:]), "type": c.type,
                     "target": c.target, "required": c.required, "required_new": c.required_new,
                     "validator": c.validator, "master": c.master, "sensitive": c.sensitive, "hint": c.hint}
                    for c in s.columns
                ],
            }
            for s in SHEETS
        ],
    }
