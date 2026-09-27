"""Upgrade 01F - Katalog requirement Kelengkapan Data (SATU sumber terpusat).

Isi katalog = DEFAULT AWAL (audit 01F §4). Level efektif per tenant dapat diubah lewat tabel
`completeness_rules` dan applicability lewat `completeness_rule_scopes`; tidak ada logic kelengkapan
di router. Requirement dinamis dibentuk dari master existing:
  - DOC.<kode>  : document_types owner_scope='employee' (default WAJIB bila is_mandatory)
  - CERT.<kode> : certification_types (default WAJIB bila is_mandatory) - HANYA berlaku bila ada scope
                  INCLUDE yang cocok (keputusan user: sertifikasi tanpa scope bisnis jelas tidak boleh
                  membuat mass incomplete).
Hasil evaluasi hanya menyimpan kode/status - TIDAK pernah nilai field (termasuk nilai sensitif).
"""
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

CATALOG_VERSION = "01F.1"

REQUIRED, RECOMMENDED, OFF = "REQUIRED", "RECOMMENDED", "OFF"
LEVELS = (REQUIRED, RECOMMENDED, OFF)
LEVEL_LABELS = {REQUIRED: "Wajib", RECOMMENDED: "Anjuran", OFF: "Nonaktif"}

# status per item
COMPLETE, MISSING, INVALID, EXPIRED, UNVERIFIED, NA = "COMPLETE", "MISSING", "INVALID", "EXPIRED", "UNVERIFIED", "NOT_APPLICABLE"
STATUS_LABELS = {COMPLETE: "Lengkap", MISSING: "Belum diisi", INVALID: "Format tidak valid", EXPIRED: "Kedaluwarsa",
                 UNVERIFIED: "Belum dikonfirmasi", NA: "Tidak berlaku", OFF: "Nonaktif"}

LENGKAP, BELUM_LENGKAP, EXCLUDED = "LENGKAP", "BELUM_LENGKAP", "EXCLUDED"

CATEGORIES: List[Tuple[str, str, str]] = [  # key, label, tab Profile 360
    ("PERSONAL", "Data Pribadi", "personal"),
    ("EMPLOYMENT", "Kepegawaian", "employment"),
    ("PLACEMENT", "Penempatan", "placement"),
    ("BANK_TAX", "Bank & Pajak", "bank"),
    ("BPJS", "BPJS", "bpjs"),
    ("FAMILY", "Keluarga", "family"),
    ("DOCUMENT", "Dokumen", "documents"),
    ("CONTRACT", "Kontrak", "contracts"),
    ("CERTIFICATION", "Sertifikasi", "certifications"),
]
CATEGORY_KEYS = {c[0] for c in CATEGORIES}

# Kondisi applicability default (dievaluasi oleh engine)
APPLICABILITY = {
    "all": "Semua karyawan aktif",
    "active_category": "Status karyawan kategori Aktif (bukan Standby)",
    "has_npwp": "Data gaji: memiliki NPWP",
    "has_salary": "Memiliki data gaji",
    "bpjs_kes": "Terdaftar BPJS Kesehatan (data gaji)",
    "bpjs_tk": "Terdaftar BPJS Ketenagakerjaan JHT/JP (data gaji)",
    "married": "Status pernikahan: Menikah",
    "requires_contract": "Status kepegawaian mewajibkan kontrak",
    "scoped_only": "Hanya untuk scope yang ditentukan (jabatan/proyek/dll.)",
}

# scope applicability yang didukung completeness_rule_scopes
SCOPE_TYPES = {
    "company": "Seluruh perusahaan",
    "branch": "Cabang",
    "position": "Jabatan",
    "project": "Proyek",
    "work_location": "Lokasi kerja / site",
    "department": "Departemen",
    "division": "Divisi",
    "job_grade": "Grade / Level",
    "employment_status": "Status kepegawaian",
    "business_status_category": "Kategori status karyawan (01B)",
    "employee_status": "Status karyawan (01B) spesifik",
}
SCOPE_MODES = ("INCLUDE", "EXCLUDE")


@dataclass
class Requirement:
    code: str
    category: str
    label: str
    check: str                    # field | all_fields | emergency | assignment | ptkp | spouse | document | contract | certification
    fields: Tuple[str, ...] = ()
    validators: Tuple[Optional[str], ...] = ()
    sensitive: bool = False
    default_level: str = REQUIRED
    applicability: str = "all"
    ref_id: Optional[str] = None   # id master untuk DOC./CERT.
    source: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def public(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("validators", None)
        d["fields"] = list(self.fields)
        return d


def _f(code, cat, label, fields, validators=(), sensitive=False, level=REQUIRED, app="all", check="field", source=""):
    fields = tuple(fields) if isinstance(fields, (list, tuple)) else (fields,)
    validators = tuple(validators) if isinstance(validators, (list, tuple)) else (validators,)
    return Requirement(code, cat, label, check if len(fields) == 1 or check != "field" else "all_fields", fields,
                       validators, sensitive, level, app, source=source or "employees." + ", ".join(fields))


STATIC_REQUIREMENTS: List[Requirement] = [
    _f("PERSONAL.FULL_NAME", "PERSONAL", "Nama lengkap", "full_name", "min2"),
    _f("PERSONAL.NIK", "PERSONAL", "NIK KTP", "nik", "nik", sensitive=True),
    _f("PERSONAL.GENDER", "PERSONAL", "Jenis kelamin", "gender", "enum:gender"),
    _f("PERSONAL.BIRTH", "PERSONAL", "Tempat & tanggal lahir", ("birth_place", "birth_date"), (None, "date")),
    _f("PERSONAL.MARITAL", "PERSONAL", "Status pernikahan", "marital_status", "enum:marital"),
    _f("PERSONAL.RELIGION", "PERSONAL", "Agama", "religion", None, level=RECOMMENDED),
    _f("PERSONAL.EDUCATION", "PERSONAL", "Pendidikan terakhir", "education", None, level=RECOMMENDED),
    _f("PERSONAL.PHONE", "PERSONAL", "No. HP", "phone", "phone"),
    _f("PERSONAL.EMAIL", "PERSONAL", "Email", "email", "email", level=RECOMMENDED),
    _f("PERSONAL.ADDRESS_KTP", "PERSONAL", "Alamat KTP", "address", None),
    _f("PERSONAL.DOMICILE", "PERSONAL", "Alamat domisili", "domicile_address", None, level=RECOMMENDED),
    Requirement("PERSONAL.EMERGENCY_CONTACT", "PERSONAL", "Kontak darurat", "emergency",
                ("emergency_contact_name", "emergency_contact_phone"), source="employees.emergency_contact_* atau keluarga (kontak darurat)"),
    Requirement("PERSONAL.PHOTO", "PERSONAL", "Foto profil", "field", ("photo_path",), (None,),
                default_level=RECOMMENDED, source="employees.photo_path"),
    _f("EMPLOYMENT.JOIN_DATE", "EMPLOYMENT", "Tanggal bergabung", "join_date", "date"),
    _f("EMPLOYMENT.STATUS_TYPE", "EMPLOYMENT", "Status kepegawaian", "employment_status_id", None),
    _f("EMPLOYMENT.BUSINESS_STATUS", "EMPLOYMENT", "Status karyawan (01B)", "current_employee_status_id", None),
    _f("EMPLOYMENT.POSITION", "EMPLOYMENT", "Jabatan", "position_id", None),
    _f("EMPLOYMENT.GRADE", "EMPLOYMENT", "Grade / Level", "job_grade_id", None, level=RECOMMENDED),
    _f("EMPLOYMENT.ORG_UNIT", "EMPLOYMENT", "Departemen", "department_id", None),
    _f("EMPLOYMENT.COST_CENTER", "EMPLOYMENT", "Cost center", "cost_center_id", None, level=RECOMMENDED),
    Requirement("PLACEMENT.ACTIVE", "PLACEMENT", "Penempatan aktif", "assignment", applicability="active_category",
                source="employee_assignments (ACTIVE)"),
    _f("PLACEMENT.WORK_LOCATION", "PLACEMENT", "Lokasi kerja / site", "work_location_id", None, app="active_category"),
    _f("BANK.ACCOUNT", "BANK_TAX", "Rekening bank", ("bank_name", "bank_account_number", "bank_account_name"),
       (None, "bank_account", None), sensitive=True),
    _f("TAX.NPWP", "BANK_TAX", "NPWP", "npwp", "npwp", sensitive=True, app="has_npwp"),
    Requirement("TAX.PTKP", "BANK_TAX", "Status PTKP (terkonfirmasi)", "ptkp", default_level=RECOMMENDED,
                applicability="has_salary", source="employee_salaries.ptkp_status (TK/0 bawaan = belum dikonfirmasi)"),
    _f("BPJS.KESEHATAN", "BPJS", "No. BPJS Kesehatan", "bpjs_kesehatan_number", "bpjs", sensitive=True, app="bpjs_kes"),
    _f("BPJS.TK", "BPJS", "No. BPJS Ketenagakerjaan", "bpjs_tk_number", "bpjs", sensitive=True, app="bpjs_tk"),
    Requirement("FAMILY.SPOUSE", "FAMILY", "Data pasangan", "spouse", applicability="married",
                source="employee_family_members (SUAMI/ISTRI)"),
    Requirement("CONTRACT.ACTIVE", "CONTRACT", "Kontrak aktif", "contract", applicability="requires_contract",
                source="employee_contracts (aktif & belum lewat masa berlaku)"),
]
STATIC_CODES = {r.code for r in STATIC_REQUIREMENTS}


def dynamic_requirements(document_types: List[Dict[str, Any]], certification_types: List[Dict[str, Any]]) -> List[Requirement]:
    out: List[Requirement] = []
    for t in document_types:
        if (t.get("owner_scope") or "employee") != "employee" or t.get("status") in ("deleted", "inactive", "archived"):
            continue
        out.append(Requirement(f"DOC.{(t.get('code') or t['id']).upper()}", "DOCUMENT", f"Dokumen {t.get('name') or t.get('code')}",
                               "document", default_level=REQUIRED if t.get("is_mandatory") else OFF, ref_id=t["id"],
                               source="documents (owner karyawan)", extra={"has_expiry": bool(t.get("has_expiry"))}))
    for t in certification_types:
        if t.get("status") in ("deleted", "inactive", "archived"):
            continue
        out.append(Requirement(f"CERT.{(t.get('code') or t['id']).upper()}", "CERTIFICATION",
                               f"Sertifikasi {t.get('name') or t.get('code')}", "certification",
                               default_level=REQUIRED if t.get("is_mandatory") else OFF, applicability="scoped_only",
                               ref_id=t["id"], source="employee_certifications"))
    return out


def catalog_metadata() -> Dict[str, Any]:
    return {"version": CATALOG_VERSION, "levels": LEVEL_LABELS, "statuses": STATUS_LABELS,
            "categories": [{"key": k, "label": l, "tab": t} for k, l, t in CATEGORIES],
            "applicability": APPLICABILITY, "scope_types": SCOPE_TYPES, "scope_modes": list(SCOPE_MODES)}
