"""Idempotent seeder: roles, permissions, modules, 2 demo companies, demo users,
master data, approval workflows and policy overrides (for inheritance demo).

Run:  python -m app.seed
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .core.db import NO_ID, audit_fields, ensure_indexes, get_db, new_id, now
from .core.rbac import ACTION_LABELS, MODULES, RESOURCES, ROLES, default_role_permissions
from .core.security import hash_password

DEMO_PASSWORD = "Hris#2026"

COMPANIES = [
    {
        "code": "NEP",
        "name": "PT Nusantara Energi Prima",
        "legal_name": "PT Nusantara Energi Prima",
        "npwp": "01.234.567.8-091.000",
        "industry": "Energi & Konstruksi",
        "address": "Jl. Jenderal Sudirman Kav. 52-53, Gedung Menara Prima Lt. 18",
        "city": "Jakarta Selatan",
        "province": "DKI Jakarta",
        "postal_code": "12190",
        "phone": "021-51401234",
        "email": "hrd@nusantaraenergi.co.id",
        "website": "https://nusantaraenergi.co.id",
        "modules": [
            "employee_core", "recruitment", "attendance", "leave_overtime",
            "performance", "payroll", "mobilization", "finance_request",
        ],
    },
    {
        "code": "KBS",
        "name": "PT Karya Bangun Sejahtera",
        "legal_name": "PT Karya Bangun Sejahtera",
        "npwp": "02.345.678.9-012.000",
        "industry": "Kontraktor Sipil",
        "address": "Jl. Raya Darmo Permai III No. 21",
        "city": "Surabaya",
        "province": "Jawa Timur",
        "postal_code": "60226",
        "phone": "031-7340088",
        "email": "hrd@karyabangun.co.id",
        "website": "https://karyabangun.co.id",
        "modules": ["employee_core", "attendance", "leave_overtime", "payroll"],
    },
]

DEMO_USERS = [
    # email, name, job title, roles per company code, global super admin
    ("superadmin@hris.id", "Super Administrator", "System Administrator", {}, True),
    ("owner@nep.co.id", "Bapak Hendra Wijaya", "Direktur Utama", {"NEP": ["company_owner"]}, False),
    ("hr.admin@nep.co.id", "Siti Rahmawati", "HR Administrator", {"NEP": ["hr_admin"]}, False),
    ("hr.manager@nep.co.id", "Dewi Kartika", "HR Manager", {"NEP": ["hr_manager"]}, False),
    ("finance@nep.co.id", "Agus Prasetyo", "Finance Manager", {"NEP": ["finance"]}, False),
    ("manager@nep.co.id", "Rudi Hartono", "Operation Manager", {"NEP": ["manager"]}, False),
    ("supervisor@nep.co.id", "Bambang Setiawan", "Site Supervisor", {"NEP": ["supervisor"]}, False),
    ("karyawan@nep.co.id", "Rina Kusuma", "Staff Administrasi", {"NEP": ["employee"]}, False),
    ("owner@kbs.co.id", "Ibu Maria Tanujaya", "Direktur", {"KBS": ["company_owner"]}, False),
    ("hr.admin@kbs.co.id", "Yusuf Maulana", "HR Administrator", {"KBS": ["hr_admin"]}, False),
    ("karyawan@kbs.co.id", "Andi Saputra", "Teknisi", {"KBS": ["employee"]}, False),
    (
        "hr.multi@hris.id",
        "Laila Fitriani",
        "Group HR Business Partner",
        {"NEP": ["hr_admin"], "KBS": ["hr_manager"]},
        False,
    ),
]

MASTER_SEED: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
    "NEP": {
        "branches": [
            {"code": "HO", "name": "Head Office Jakarta", "city": "Jakarta Selatan", "province": "DKI Jakarta", "is_head_office": True, "address": "Menara Prima Lt. 18"},
            {"code": "BLK", "name": "Cabang Balikpapan", "city": "Balikpapan", "province": "Kalimantan Timur", "is_head_office": False, "address": "Jl. MT Haryono No. 88"},
            {"code": "SBY", "name": "Cabang Surabaya", "city": "Surabaya", "province": "Jawa Timur", "is_head_office": False, "address": "Jl. Basuki Rahmat No. 12"},
        ],
        "job_grades": [
            {"code": "G1", "name": "Staff", "level": 1, "min_salary": 5000000, "max_salary": 8000000},
            {"code": "G2", "name": "Senior Staff", "level": 2, "min_salary": 8000000, "max_salary": 12000000},
            {"code": "G3", "name": "Supervisor", "level": 3, "min_salary": 12000000, "max_salary": 18000000},
            {"code": "G4", "name": "Manager", "level": 4, "min_salary": 18000000, "max_salary": 30000000},
            {"code": "G5", "name": "General Manager", "level": 5, "min_salary": 30000000, "max_salary": 50000000},
        ],
        "cost_centers": [
            {"code": "CC-HO", "name": "Overhead Kantor Pusat", "branch_code": "HO"},
            {"code": "CC-PRJ", "name": "Biaya Proyek Langsung", "branch_code": "BLK"},
            {"code": "CC-MKT", "name": "Pemasaran & Tender", "branch_code": "HO"},
        ],
        "work_locations": [
            {"code": "LOC-HO", "name": "Kantor Pusat Jakarta", "branch_code": "HO", "location_type": "office", "address": "Menara Prima Lt. 18", "radius_meter": 150},
            {"code": "LOC-SITE1", "name": "Site Sangatta", "branch_code": "BLK", "location_type": "project_site", "address": "Sangatta, Kutai Timur", "radius_meter": 500},
            {"code": "LOC-WH", "name": "Gudang Surabaya", "branch_code": "SBY", "location_type": "warehouse", "address": "Margomulyo Industri", "radius_meter": 200},
        ],
        "departments": [
            {"code": "DEP-HR", "name": "Human Capital", "branch_code": "HO", "cost_center_code": "CC-HO"},
            {"code": "DEP-FIN", "name": "Finance & Accounting", "branch_code": "HO", "cost_center_code": "CC-HO"},
            {"code": "DEP-OPS", "name": "Operations", "branch_code": "BLK", "cost_center_code": "CC-PRJ"},
            {"code": "DEP-HSE", "name": "HSE", "branch_code": "BLK", "cost_center_code": "CC-PRJ"},
        ],
        "divisions": [
            {"code": "DIV-REC", "name": "Recruitment & People Dev", "department_code": "DEP-HR"},
            {"code": "DIV-PAY", "name": "Payroll & Benefit", "department_code": "DEP-HR"},
            {"code": "DIV-ENG", "name": "Engineering", "department_code": "DEP-OPS"},
            {"code": "DIV-MNT", "name": "Maintenance", "department_code": "DEP-OPS"},
        ],
        "positions": [
            {"code": "POS-HRM", "name": "HR Manager", "department_code": "DEP-HR", "division_code": "DIV-REC", "grade_code": "G4", "is_supervisory": True},
            {"code": "POS-HRS", "name": "HR Staff", "department_code": "DEP-HR", "division_code": "DIV-REC", "grade_code": "G1", "is_supervisory": False},
            {"code": "POS-PAY", "name": "Payroll Officer", "department_code": "DEP-HR", "division_code": "DIV-PAY", "grade_code": "G2", "is_supervisory": False},
            {"code": "POS-SPV", "name": "Site Supervisor", "department_code": "DEP-OPS", "division_code": "DIV-ENG", "grade_code": "G3", "is_supervisory": True},
            {"code": "POS-TEK", "name": "Teknisi Mekanik", "department_code": "DEP-OPS", "division_code": "DIV-MNT", "grade_code": "G1", "is_supervisory": False},
        ],
        "projects": [
            {"code": "PRJ-001", "name": "EPC Gas Plant Sangatta", "client_name": "PT Energi Timur", "branch_code": "BLK", "cost_center_code": "CC-PRJ", "start_date": "2025-06-01", "end_date": "2026-12-31", "contract_value": 185000000000},
            {"code": "PRJ-002", "name": "Maintenance Kilang Surabaya", "client_name": "PT Kilang Nusantara", "branch_code": "SBY", "cost_center_code": "CC-PRJ", "start_date": "2025-01-15", "end_date": "2026-03-31", "contract_value": 42000000000},
        ],
        "employment_statuses": [
            {"code": "PKWTT", "name": "Karyawan Tetap (PKWTT)", "is_permanent": True, "requires_contract": False},
            {"code": "PKWT", "name": "Kontrak (PKWT)", "is_permanent": False, "requires_contract": True},
            {"code": "HARIAN", "name": "Harian Lepas", "is_permanent": False, "requires_contract": True},
            {"code": "MAGANG", "name": "Magang / Internship", "is_permanent": False, "requires_contract": True},
        ],
        "contract_types": [
            {"code": "PKWT-6", "name": "PKWT 6 Bulan", "duration_months": 6, "is_extendable": True, "max_extension": 2},
            {"code": "PKWT-12", "name": "PKWT 12 Bulan", "duration_months": 12, "is_extendable": True, "max_extension": 2},
            {"code": "PROB-3", "name": "Masa Percobaan 3 Bulan", "duration_months": 3, "is_extendable": False, "max_extension": 0},
        ],
        "certification_types": [
            {"code": "K3-UMUM", "name": "Ahli K3 Umum", "issuing_body": "Kemnaker RI", "validity_months": 36, "is_mandatory": True, "reminder_days": 60},
            {"code": "SIO-CRANE", "name": "SIO Operator Crane", "issuing_body": "Kemnaker RI", "validity_months": 24, "is_mandatory": True, "reminder_days": 45},
            {"code": "BOSIET", "name": "BOSIET Offshore Safety", "issuing_body": "OPITO", "validity_months": 48, "is_mandatory": False, "reminder_days": 90},
        ],
        "document_types": [
            {"code": "CV", "name": "Curriculum Vitae", "category": "Rekrutmen", "owner_scope": "applicant", "is_mandatory": True, "has_expiry": False, "allowed_extensions": "pdf,doc,docx", "max_size_mb": 5},
            {"code": "KTP", "name": "KTP", "category": "Identitas", "owner_scope": "employee", "is_mandatory": True, "has_expiry": False, "allowed_extensions": "pdf,jpg,jpeg,png", "max_size_mb": 3},
            {"code": "IJAZAH", "name": "Ijazah", "category": "Pendidikan", "owner_scope": "employee", "is_mandatory": True, "has_expiry": False, "allowed_extensions": "pdf,jpg,jpeg,png", "max_size_mb": 5},
            {"code": "SERTIF", "name": "Sertifikat Kompetensi", "category": "Sertifikasi", "owner_scope": "certification", "is_mandatory": False, "has_expiry": True, "reminder_days": 60, "allowed_extensions": "pdf,jpg,jpeg,png", "max_size_mb": 5},
            {"code": "KONTRAK", "name": "Kontrak Kerja", "category": "Kontrak", "owner_scope": "contract", "is_mandatory": True, "has_expiry": True, "reminder_days": 30, "allowed_extensions": "pdf", "max_size_mb": 10},
            {"code": "MCU", "name": "Hasil Medical Check Up", "category": "Medis", "owner_scope": "employee", "is_mandatory": False, "has_expiry": True, "reminder_days": 30, "allowed_extensions": "pdf", "max_size_mb": 10},
            {"code": "INV", "name": "Invoice", "category": "Keuangan", "owner_scope": "invoice", "is_mandatory": False, "has_expiry": False, "allowed_extensions": "pdf,jpg,jpeg,png", "max_size_mb": 5},
            {"code": "TIKET", "name": "Tiket Perjalanan", "category": "Keuangan", "owner_scope": "travel", "is_mandatory": False, "has_expiry": False, "allowed_extensions": "pdf,jpg,jpeg,png", "max_size_mb": 5},
            {"code": "KWITANSI", "name": "Kwitansi / Bukti Bayar", "category": "Keuangan", "owner_scope": "receipt", "is_mandatory": False, "has_expiry": False, "allowed_extensions": "pdf,jpg,jpeg,png", "max_size_mb": 5},
        ],
    },
    "KBS": {
        "branches": [
            {"code": "HO", "name": "Kantor Pusat Surabaya", "city": "Surabaya", "province": "Jawa Timur", "is_head_office": True, "address": "Darmo Permai III No. 21"},
            {"code": "MLG", "name": "Cabang Malang", "city": "Malang", "province": "Jawa Timur", "is_head_office": False, "address": "Jl. Soekarno Hatta No. 9"},
        ],
        "job_grades": [
            {"code": "L1", "name": "Pelaksana", "level": 1, "min_salary": 4500000, "max_salary": 7000000},
            {"code": "L2", "name": "Koordinator", "level": 2, "min_salary": 7000000, "max_salary": 11000000},
            {"code": "L3", "name": "Manajer", "level": 3, "min_salary": 11000000, "max_salary": 20000000},
        ],
        "cost_centers": [
            {"code": "CC-OPS", "name": "Operasional Proyek", "branch_code": "HO"},
            {"code": "CC-ADM", "name": "Administrasi Umum", "branch_code": "HO"},
        ],
        "work_locations": [
            {"code": "LOC-HO", "name": "Kantor Pusat", "branch_code": "HO", "location_type": "office", "radius_meter": 100},
            {"code": "LOC-PRJ", "name": "Proyek Jalan Tol Malang", "branch_code": "MLG", "location_type": "project_site", "radius_meter": 800},
        ],
        "departments": [
            {"code": "DEP-HRD", "name": "HRD & GA", "branch_code": "HO", "cost_center_code": "CC-ADM"},
            {"code": "DEP-TEK", "name": "Teknik", "branch_code": "HO", "cost_center_code": "CC-OPS"},
        ],
        "divisions": [
            {"code": "DIV-PER", "name": "Personalia", "department_code": "DEP-HRD"},
            {"code": "DIV-SIP", "name": "Sipil", "department_code": "DEP-TEK"},
        ],
        "positions": [
            {"code": "POS-PER", "name": "Staff Personalia", "department_code": "DEP-HRD", "division_code": "DIV-PER", "grade_code": "L1", "is_supervisory": False},
            {"code": "POS-SIP", "name": "Site Engineer", "department_code": "DEP-TEK", "division_code": "DIV-SIP", "grade_code": "L2", "is_supervisory": True},
        ],
        "projects": [
            {"code": "PRJ-TOL", "name": "Pelebaran Jalan Tol Malang", "client_name": "Dinas PUPR Jatim", "branch_code": "MLG", "cost_center_code": "CC-OPS", "start_date": "2025-09-01", "end_date": "2026-08-31", "contract_value": 64000000000},
        ],
        "employment_statuses": [
            {"code": "TETAP", "name": "Karyawan Tetap", "is_permanent": True, "requires_contract": False},
            {"code": "PKWT", "name": "Kontrak (PKWT)", "is_permanent": False, "requires_contract": True},
        ],
        "contract_types": [
            {"code": "PKWT-12", "name": "PKWT 12 Bulan", "duration_months": 12, "is_extendable": True, "max_extension": 1},
        ],
        "certification_types": [
            {"code": "SKA", "name": "SKA Ahli Teknik Jalan", "issuing_body": "LPJK", "validity_months": 36, "is_mandatory": True, "reminder_days": 60},
        ],
        "document_types": [
            {"code": "KTP", "name": "KTP", "category": "Identitas", "owner_scope": "employee", "is_mandatory": True, "has_expiry": False, "allowed_extensions": "pdf,jpg,jpeg,png", "max_size_mb": 3},
            {"code": "KONTRAK", "name": "Kontrak Kerja", "category": "Kontrak", "owner_scope": "contract", "is_mandatory": True, "has_expiry": True, "reminder_days": 30, "allowed_extensions": "pdf", "max_size_mb": 10},
            {"code": "SERTIF", "name": "Sertifikat Kompetensi", "category": "Sertifikasi", "owner_scope": "certification", "is_mandatory": False, "has_expiry": True, "reminder_days": 60, "allowed_extensions": "pdf,jpg,jpeg,png", "max_size_mb": 5},
        ],
    },
}

PAYROLL_WORKFLOW = {
    "code": "WF-PAYROLL",
    "name": "Persetujuan Payroll Bulanan",
    "document_kind": "payroll",
    "is_default": True,
    "description": "HR menyusun -> HR Manager verifikasi -> Finance/Direksi menyetujui",
    "steps": [
        {"step_order": 1, "name": "Penyusunan HR", "approver_type": "role", "approver_role_key": "hr_admin", "sla_days": 2},
        {"step_order": 2, "name": "Verifikasi HR Manager", "approver_type": "role", "approver_role_key": "hr_manager", "sla_days": 1},
        {"step_order": 3, "name": "Persetujuan Finance", "approver_type": "role", "approver_role_key": "finance", "sla_days": 1},
    ],
}

PAYROLL_COMPONENT_SEED = [
    {"code": "TJ-JAB", "name": "Tunjangan Jabatan", "kind": "earning", "calc": "fixed",
     "default_amount": 1500000, "taxable": True, "prorate": False,
     "include_in_bpjs_base": True, "sort_order": 10,
     "description": "Tunjangan tetap berdasarkan jabatan, ikut dasar perhitungan BPJS."},
    {"code": "TJ-TRP", "name": "Tunjangan Transport", "kind": "earning", "calc": "fixed",
     "default_amount": 750000, "taxable": True, "prorate": True,
     "include_in_bpjs_base": False, "sort_order": 20,
     "description": "Dibayar per hari kerja, dipotong bila tidak hadir tanpa upah."},
    {"code": "TJ-MKN", "name": "Tunjangan Makan", "kind": "earning", "calc": "fixed",
     "default_amount": 660000, "taxable": True, "prorate": True,
     "include_in_bpjs_base": False, "sort_order": 30,
     "description": "Tunjangan makan harian, ikut proporsi kehadiran."},
    {"code": "TJ-KOM", "name": "Tunjangan Komunikasi", "kind": "earning", "calc": "fixed",
     "default_amount": 300000, "taxable": True, "prorate": False,
     "include_in_bpjs_base": False, "sort_order": 40,
     "description": "Pulsa dan paket data."},
    {"code": "RMB-MED", "name": "Reimburse Kesehatan", "kind": "earning", "calc": "fixed",
     "default_amount": 0, "taxable": False, "prorate": False,
     "include_in_bpjs_base": False, "sort_order": 50,
     "description": "Penggantian biaya, bukan objek PPh 21."},
    {"code": "POT-KOP", "name": "Potongan Koperasi", "kind": "deduction", "calc": "fixed",
     "default_amount": 100000, "taxable": False, "prorate": False,
     "include_in_bpjs_base": False, "sort_order": 60,
     "description": "Simpanan wajib koperasi karyawan."},
    {"code": "POT-PINJ", "name": "Angsuran Pinjaman", "kind": "deduction", "calc": "fixed",
     "default_amount": 0, "taxable": False, "prorate": False,
     "include_in_bpjs_base": False, "sort_order": 70,
     "description": "Angsuran pinjaman karyawan per bulan."},
]

# NIK karyawan -> (gaji pokok, status PTKP, kode komponen tetap)
SALARY_SEED = {
    "NEP-0001": (7500000, "K/1", ["TJ-TRP", "TJ-MKN"]),
    "NEP-0002": (12000000, "K/3", ["TJ-JAB", "TJ-TRP"]),
    "NEP-0003": (9500000, "TK/0", ["TJ-MKN", "TJ-KOM"]),
    "NEP-0004": (8000000, "TK/2", ["TJ-TRP", "TJ-MKN", "POT-KOP"]),
    "NEP-0005": (11000000, "K/0", ["TJ-JAB", "TJ-KOM"]),
    "KBS-0001": (6800000, "TK/1", ["TJ-MKN"]),
    "KBS-0002": (10500000, "K/2", ["TJ-JAB", "TJ-TRP"]),
    "KBS-0003": (5200000, "TK/0", ["TJ-MKN"]),
}

# email pengguna -> nama karyawan yang ditautkan (self-service slip gaji)
EMPLOYEE_USER_LINKS = {
    "karyawan@nep.co.id": "Rina Kusuma",
    "supervisor@nep.co.id": "Bambang Setiawan",
    "karyawan@kbs.co.id": "Andi Saputra",
}

WORKFLOW_SEED = {
    "NEP": [
        {
            "code": "WF-CUTI",
            "name": "Persetujuan Cuti Karyawan",
            "document_kind": "leave",
            "is_default": True,
            "description": "Pemohon -> Supervisor -> Manager -> HR",
            "steps": [
                {"step_order": 1, "name": "Persetujuan Supervisor", "approver_type": "role", "approver_role_key": "supervisor", "sla_days": 1},
                {"step_order": 2, "name": "Persetujuan Manager", "approver_type": "role", "approver_role_key": "manager", "sla_days": 2},
                {"step_order": 3, "name": "Verifikasi HR", "approver_type": "role", "approver_role_key": "hr_admin", "sla_days": 1},
            ],
        },
        {
            "code": "WF-KONTRAK",
            "name": "Persetujuan Kontrak Kerja",
            "document_kind": "contract",
            "is_default": True,
            "description": "HR -> HR Manager -> Direksi",
            "steps": [
                {"step_order": 1, "name": "Penyusunan HR", "approver_type": "role", "approver_role_key": "hr_admin", "sla_days": 2},
                {"step_order": 2, "name": "Persetujuan HR Manager", "approver_type": "role", "approver_role_key": "hr_manager", "sla_days": 2},
                {"step_order": 3, "name": "Persetujuan Direksi", "approver_type": "role", "approver_role_key": "company_owner", "sla_days": 3},
            ],
        },
        {
            "code": "WF-KASBON",
            "name": "Permintaan Kasbon / Dana",
            "document_kind": "finance_request",
            "is_default": True,
            "description": "Pemohon -> Manager -> Finance",
            "steps": [
                {"step_order": 1, "name": "Persetujuan Manager", "approver_type": "role", "approver_role_key": "manager", "sla_days": 1},
                {"step_order": 2, "name": "Verifikasi Finance", "approver_type": "role", "approver_role_key": "finance", "sla_days": 2},
            ],
        },
    ],
    "KBS": [
        {
            "code": "WF-CUTI",
            "name": "Persetujuan Cuti",
            "document_kind": "leave",
            "is_default": True,
            "description": "Pemohon -> Atasan Langsung -> HR",
            "steps": [
                {"step_order": 1, "name": "Atasan Langsung", "approver_type": "supervisor", "sla_days": 1},
                {"step_order": 2, "name": "Verifikasi HR", "approver_type": "role", "approver_role_key": "hr_admin", "sla_days": 2},
            ],
        }
    ],
}

# Resource baru yang ditambahkan setelah rilis pertama (untuk top-up hak akses role)
NEW_RESOURCES_TOPUP = [
    "certification", "contract",
    "payroll", "payroll_component", "employee_salary", "payslip",
]

# Data karyawan demo (modul employee_core). Offset hari dibuat relatif terhadap hari ini
# agar demo pengingat masa berlaku selalu relevan.
EMPLOYEE_SEED: Dict[str, List[Dict[str, Any]]] = {
    "NEP": [
        {
            "employee_number": "NEP-0001",
            "full_name": "Rina Kusuma",
            "nik": "3174056709900002",
            "gender": "female",
            "birth_place": "Jakarta",
            "birth_date": "1990-09-27",
            "marital_status": "married",
            "religion": "islam",
            "education": "s1",
            "email": "rina.kusuma@nusantaraenergi.co.id",
            "phone": "0812-1100-2201",
            "address": "Jl. Kebagusan Raya No. 12",
            "city": "Jakarta Selatan",
            "job_title": "Staff Administrasi HR",
            "join_date": "2024-03-01",
            "branch_code": "HO",
            "work_location_code": "LOC-HO",
            "department_code": "DEP-HR",
            "division_code": "DIV-REC",
            "position_code": "POS-HRS",
            "grade_code": "G1",
            "cost_center_code": "CC-HO",
            "employment_status_code": "PKWT",
            "bank_name": "Bank Mandiri",
            "bank_account_number": "1370099887711",
            "bank_account_name": "Rina Kusuma",
            "bpjs_kesehatan_number": "0001234567890",
            "bpjs_tk_number": "22001234567",
            "contracts": [
                {
                    "type_code": "PKWT-12",
                    "number": "PKWT/NEP/2025/0001",
                    "start_offset": -330,
                    "end_offset": 28,
                    "basic_salary": 6500000,
                    "allowance": 1500000,
                    "approval_state": "approved",
                }
            ],
            "certifications": [
                {
                    "type_code": "K3-UMUM",
                    "name": "Ahli K3 Umum",
                    "number": "K3U/2023/11890",
                    "issuer": "Kemnaker RI",
                    "issued_offset": -720,
                    "expiry_offset": 20,
                }
            ],
        },
        {
            "employee_number": "NEP-0002",
            "full_name": "Bambang Setiawan",
            "nik": "6471021203850001",
            "gender": "male",
            "birth_place": "Balikpapan",
            "birth_date": "1985-03-12",
            "marital_status": "married",
            "religion": "islam",
            "education": "d3",
            "email": "bambang.setiawan@nusantaraenergi.co.id",
            "phone": "0813-5522-8890",
            "city": "Balikpapan",
            "job_title": "Site Supervisor",
            "join_date": "2019-07-15",
            "branch_code": "BLK",
            "work_location_code": "LOC-SITE1",
            "department_code": "DEP-OPS",
            "division_code": "DIV-ENG",
            "position_code": "POS-SPV",
            "grade_code": "G3",
            "cost_center_code": "CC-PRJ",
            "project_code": "PRJ-001",
            "employment_status_code": "PKWTT",
            "bank_name": "Bank BNI",
            "bank_account_number": "0223344556",
            "bank_account_name": "Bambang Setiawan",
            "contracts": [
                {
                    "type_code": "PKWT-12",
                    "number": "PKWTT/NEP/2019/0011",
                    "start_offset": -2400,
                    "end_offset": None,
                    "basic_salary": 14500000,
                    "allowance": 4500000,
                    "approval_state": "approved",
                }
            ],
            "certifications": [
                {
                    "type_code": "SIO-CRANE",
                    "name": "SIO Operator Crane Kelas 1",
                    "number": "SIO/CR/2022/4410",
                    "issuer": "Kemnaker RI",
                    "issued_offset": -900,
                    "expiry_offset": -12,
                },
                {
                    "type_code": "BOSIET",
                    "name": "BOSIET Offshore Safety",
                    "number": "OPITO/9932",
                    "issuer": "OPITO",
                    "issued_offset": -400,
                    "expiry_offset": 560,
                },
            ],
        },
        {
            "employee_number": "NEP-0003",
            "full_name": "Sari Puspita",
            "nik": "3276014508930003",
            "gender": "female",
            "birth_place": "Bogor",
            "birth_date": "1993-08-05",
            "marital_status": "single",
            "religion": "kristen",
            "education": "s1",
            "email": "sari.puspita@nusantaraenergi.co.id",
            "phone": "0811-2233-4455",
            "city": "Depok",
            "job_title": "Payroll Officer",
            "join_date": "2022-01-10",
            "branch_code": "HO",
            "work_location_code": "LOC-HO",
            "department_code": "DEP-HR",
            "division_code": "DIV-PAY",
            "position_code": "POS-PAY",
            "grade_code": "G2",
            "cost_center_code": "CC-HO",
            "employment_status_code": "PKWTT",
            "bank_name": "Bank BCA",
            "bank_account_number": "5220998877",
            "bank_account_name": "Sari Puspita",
            "contracts": [
                {
                    "type_code": "PKWT-12",
                    "number": "PKWTT/NEP/2022/0033",
                    "start_offset": -1450,
                    "end_offset": None,
                    "basic_salary": 9500000,
                    "allowance": 2000000,
                    "approval_state": "approved",
                }
            ],
            "certifications": [],
        },
        {
            "employee_number": "NEP-0004",
            "full_name": "Joko Purnomo",
            "nik": "6471030507960004",
            "gender": "male",
            "birth_place": "Samarinda",
            "birth_date": "1996-07-05",
            "marital_status": "single",
            "religion": "islam",
            "education": "sma",
            "email": "joko.purnomo@nusantaraenergi.co.id",
            "phone": "0852-7788-1122",
            "city": "Sangatta",
            "job_title": "Teknisi Mekanik",
            "join_date": "2025-02-03",
            "branch_code": "BLK",
            "work_location_code": "LOC-SITE1",
            "department_code": "DEP-OPS",
            "division_code": "DIV-MNT",
            "position_code": "POS-TEK",
            "grade_code": "G1",
            "cost_center_code": "CC-PRJ",
            "project_code": "PRJ-001",
            "employment_status_code": "PKWT",
            "contracts": [
                {
                    "type_code": "PKWT-6",
                    "number": "PKWT/NEP/2026/0044",
                    "start_offset": -120,
                    "end_offset": 62,
                    "basic_salary": 5800000,
                    "allowance": 2200000,
                    "approval_state": "draft",
                }
            ],
            "certifications": [
                {
                    "type_code": "K3-UMUM",
                    "name": "Ahli K3 Umum",
                    "number": "K3U/2025/23110",
                    "issuer": "Kemnaker RI",
                    "issued_offset": -300,
                    "expiry_offset": 780,
                }
            ],
        },
        {
            "employee_number": "NEP-0005",
            "full_name": "Dewi Anggraini",
            "nik": "3173042209920005",
            "gender": "female",
            "birth_place": "Surabaya",
            "birth_date": "1992-09-22",
            "marital_status": "married",
            "religion": "hindu",
            "education": "s2",
            "email": "dewi.anggraini@nusantaraenergi.co.id",
            "phone": "0819-3344-5566",
            "city": "Jakarta Barat",
            "job_title": "HSE Officer",
            "join_date": "2023-05-22",
            "branch_code": "BLK",
            "work_location_code": "LOC-SITE1",
            "department_code": "DEP-HSE",
            "position_code": "POS-SPV",
            "grade_code": "G3",
            "cost_center_code": "CC-PRJ",
            "employment_status_code": "PKWT",
            "status": "inactive",
            "contracts": [
                {
                    "type_code": "PKWT-12",
                    "number": "PKWT/NEP/2025/0055",
                    "start_offset": -420,
                    "end_offset": -55,
                    "basic_salary": 11000000,
                    "allowance": 3000000,
                    "approval_state": "approved",
                }
            ],
            "certifications": [],
        },
    ],
    "KBS": [
        {
            "employee_number": "KBS-0001",
            "full_name": "Andi Saputra",
            "nik": "3578011102910001",
            "gender": "male",
            "birth_place": "Surabaya",
            "birth_date": "1991-02-11",
            "marital_status": "married",
            "religion": "islam",
            "education": "d3",
            "email": "andi.saputra@karyabangun.co.id",
            "phone": "0856-1122-3344",
            "city": "Surabaya",
            "job_title": "Teknisi Sipil",
            "join_date": "2023-04-03",
            "branch_code": "HO",
            "work_location_code": "LOC-HO",
            "department_code": "DEP-TEK",
            "division_code": "DIV-SIP",
            "position_code": "POS-SIP",
            "grade_code": "L2",
            "cost_center_code": "CC-OPS",
            "employment_status_code": "PKWT",
            "contracts": [
                {
                    "type_code": "PKWT-12",
                    "number": "PKWT/KBS/2025/0001",
                    "start_offset": -300,
                    "end_offset": 45,
                    "basic_salary": 8200000,
                    "allowance": 1800000,
                    "approval_state": "approved",
                }
            ],
            "certifications": [
                {
                    "type_code": "SKA",
                    "name": "SKA Ahli Teknik Jalan - Muda",
                    "number": "SKA/JT/2024/7781",
                    "issuer": "LPJK",
                    "issued_offset": -500,
                    "expiry_offset": 40,
                }
            ],
        },
        {
            "employee_number": "KBS-0002",
            "full_name": "Ratna Wulandari",
            "nik": "3578022803940002",
            "gender": "female",
            "birth_place": "Malang",
            "birth_date": "1994-03-28",
            "marital_status": "single",
            "religion": "katolik",
            "education": "s1",
            "email": "ratna.wulandari@karyabangun.co.id",
            "phone": "0857-9988-7766",
            "city": "Surabaya",
            "job_title": "Staff Personalia",
            "join_date": "2024-08-19",
            "branch_code": "HO",
            "work_location_code": "LOC-HO",
            "department_code": "DEP-HRD",
            "division_code": "DIV-PER",
            "position_code": "POS-PER",
            "grade_code": "L1",
            "cost_center_code": "CC-ADM",
            "employment_status_code": "TETAP",
            "contracts": [
                {
                    "type_code": "PKWT-12",
                    "number": "TETAP/KBS/2024/0002",
                    "start_offset": -560,
                    "end_offset": None,
                    "basic_salary": 6100000,
                    "allowance": 1200000,
                    "approval_state": "approved",
                }
            ],
            "certifications": [],
        },
        {
            "employee_number": "KBS-0003",
            "full_name": "Hendri Kurniawan",
            "nik": "3507031507880003",
            "gender": "male",
            "birth_place": "Malang",
            "birth_date": "1988-07-15",
            "marital_status": "married",
            "religion": "islam",
            "education": "s1",
            "email": "hendri.kurniawan@karyabangun.co.id",
            "phone": "0813-4455-6677",
            "city": "Malang",
            "job_title": "Site Engineer",
            "join_date": "2021-11-01",
            "branch_code": "MLG",
            "work_location_code": "LOC-PRJ",
            "department_code": "DEP-TEK",
            "division_code": "DIV-SIP",
            "position_code": "POS-SIP",
            "grade_code": "L2",
            "cost_center_code": "CC-OPS",
            "project_code": "PRJ-TOL",
            "employment_status_code": "PKWT",
            "contracts": [
                {
                    "type_code": "PKWT-12",
                    "number": "PKWT/KBS/2026/0003",
                    "start_offset": -60,
                    "end_offset": 300,
                    "basic_salary": 10500000,
                    "allowance": 2500000,
                    "approval_state": "approved",
                }
            ],
            "certifications": [
                {
                    "type_code": "SKA",
                    "name": "SKA Ahli Teknik Jalan - Madya",
                    "number": "SKA/JT/2023/5512",
                    "issuer": "LPJK",
                    "issued_offset": -800,
                    "expiry_offset": 200,
                }
            ],
        },
    ],
}

STEP_DEFAULTS = {
    "approver_user_id": None,
    "approver_position_id": None,
    "is_mandatory": True,
    "allow_delegation": True,
    "sla_days": None,
    "condition_note": None,
}


async def _upsert(collection: str, filter_q: Dict[str, Any], doc: Dict[str, Any], user_id: Optional[str] = None) -> Dict[str, Any]:
    db = get_db()
    existing = await db[collection].find_one(filter_q, NO_ID)
    if existing:
        return existing
    payload = {"id": new_id(), "status": "active", **doc}
    payload.update(audit_fields(user_id, creating=True))
    await db[collection].insert_one(dict(payload))
    return {k: v for k, v in payload.items() if k != "_id"}


async def seed_rbac() -> None:
    db = get_db()
    for role in ROLES:
        await _upsert("roles", {"key": role["key"]}, {"company_id": None, **role})

    for resource, (label, module_key, actions) in RESOURCES.items():
        for action in actions:
            key = f"{resource}:{action}"
            await _upsert(
                "permissions",
                {"key": key},
                {
                    "company_id": None,
                    "key": key,
                    "resource": resource,
                    "resource_label": label,
                    "action": action,
                    "action_label": ACTION_LABELS[action],
                    "module_key": module_key,
                    "name": f"{ACTION_LABELS[action]} {label}",
                },
            )
    await _upsert(
        "permissions",
        {"key": "*:*"},
        {
            "company_id": None,
            "key": "*:*",
            "resource": "*",
            "resource_label": "Semua Modul",
            "action": "*",
            "action_label": "Semua Tindakan",
            "module_key": "hr_core",
            "name": "Akses Penuh",
        },
    )

    matrix = default_role_permissions()
    for role_key, keys in matrix.items():
        if await db.role_permissions.count_documents({"role_key": role_key}):
            continue
        for key in keys:
            await db.role_permissions.insert_one(
                {
                    "id": new_id(),
                    "company_id": None,
                    "role_key": role_key,
                    "permission_key": key,
                    "status": "active",
                    **audit_fields(None, creating=True),
                }
            )

    # Top-up untuk resource yang baru ditambahkan setelah database pertama dibuat.
    # Hanya diisi jika role belum punya permission apa pun untuk resource tersebut,
    # sehingga hak akses yang sudah diubah manual dari UI tidak tertimpa.
    for resource in NEW_RESOURCES_TOPUP:
        for role_key, keys in matrix.items():
            wanted = [k for k in keys if k.startswith(f"{resource}:")]
            if not wanted:
                continue
            existing = await db.role_permissions.count_documents(
                {"role_key": role_key, "permission_key": {"$regex": f"^{resource}:"}}
            )
            if existing:
                continue
            for key in wanted:
                await db.role_permissions.insert_one(
                    {
                        "id": new_id(),
                        "company_id": None,
                        "role_key": role_key,
                        "permission_key": key,
                        "status": "active",
                        **audit_fields(None, creating=True),
                    }
                )

    for module in MODULES:
        await _upsert("modules", {"key": module["key"]}, {"company_id": None, **module})


async def seed_companies() -> Dict[str, str]:
    db = get_db()
    ids: Dict[str, str] = {}
    for spec in COMPANIES:
        modules = spec.pop("modules", [])
        existing = await db.companies.find_one({"code": spec["code"]}, NO_ID)
        if existing:
            company_id = existing["id"]
        else:
            company_id = new_id()
            doc = {
                "id": company_id,
                "company_id": company_id,
                "status": "active",
                "timezone": "Asia/Jakarta",
                "currency": "IDR",
                "fiscal_year_start_month": 1,
                "logo_url": None,
                **spec,
                **audit_fields(None, creating=True),
            }
            await db.companies.insert_one(dict(doc))
        ids[spec["code"]] = company_id
        spec["modules"] = modules

        for module in MODULES:
            await _upsert(
                "company_modules",
                {"company_id": company_id, "module_key": module["key"]},
                {
                    "company_id": company_id,
                    "module_key": module["key"],
                    "is_active": module["is_core"] or module["key"] in modules,
                    "activated_at": now(),
                    "notes": None,
                },
            )
        await _upsert(
            "company_settings",
            {"company_id": company_id},
            {
                "company_id": company_id,
                "employee_id_prefix": spec["code"],
                "employee_id_next_number": 1,
                "date_format": "DD/MM/YYYY",
                "number_format": "1.000,00",
                "default_language": "id",
                "week_start": "monday",
                "notification_email": spec.get("email"),
                "enable_email_notification": True,
                "enable_audit_retention_days": 730,
                "require_two_factor": False,
                "password_min_length": 8,
                "session_timeout_minutes": 480,
            },
        )
    return ids


async def seed_users(company_ids: Dict[str, str]) -> None:
    db = get_db()
    for email, name, job_title, role_map, is_super in DEMO_USERS:
        existing = await db.users.find_one({"email": email}, NO_ID)
        if existing:
            user_id = existing["id"]
        else:
            user_id = new_id()
            default_company = None
            for code in role_map:
                default_company = company_ids.get(code)
                break
            if is_super:
                default_company = company_ids.get("NEP")
            await db.users.insert_one(
                {
                    "id": user_id,
                    "company_id": None,
                    "email": email,
                    "full_name": name,
                    "password_hash": hash_password(DEMO_PASSWORD),
                    "phone": None,
                    "job_title": job_title,
                    "employee_number": None,
                    "status": "active",
                    "default_company_id": default_company,
                    "last_login_at": None,
                    "failed_login_attempts": 0,
                    "locked_until": None,
                    "must_change_password": False,
                    "is_demo_account": True,
                    **audit_fields(None, creating=True),
                }
            )
        if is_super:
            await _upsert(
                "user_company_roles",
                {"user_id": user_id, "company_id": None, "role_key": "super_admin"},
                {"user_id": user_id, "company_id": None, "role_key": "super_admin"},
            )
        for code, roles in role_map.items():
            cid = company_ids.get(code)
            if not cid:
                continue
            for role_key in roles:
                await _upsert(
                    "user_company_roles",
                    {"user_id": user_id, "company_id": cid, "role_key": role_key},
                    {"user_id": user_id, "company_id": cid, "role_key": role_key},
                )


async def seed_master(company_ids: Dict[str, str]) -> None:
    db = get_db()
    for code, groups in MASTER_SEED.items():
        cid = company_ids[code]
        lookup: Dict[str, Dict[str, str]] = {}

        async def put(collection: str, rows: List[Dict[str, Any]], transform=None):
            mapping: Dict[str, str] = {}
            for row in rows:
                data = dict(row)
                if transform:
                    data = transform(data)
                doc = await _upsert(
                    collection,
                    {"company_id": cid, "code": data["code"]},
                    {"company_id": cid, **data},
                )
                mapping[data["code"]] = doc["id"]
            lookup[collection] = mapping
            return mapping

        branches = await put("branches", groups["branches"])
        grades = await put("job_grades", groups["job_grades"])
        cost_centers = await put(
            "cost_centers",
            groups["cost_centers"],
            lambda d: {**{k: v for k, v in d.items() if k != "branch_code"}, "branch_id": branches.get(d.get("branch_code"))},
        )
        await put(
            "work_locations",
            groups["work_locations"],
            lambda d: {**{k: v for k, v in d.items() if k != "branch_code"}, "branch_id": branches.get(d.get("branch_code"))},
        )
        departments = await put(
            "departments",
            groups["departments"],
            lambda d: {
                **{k: v for k, v in d.items() if k not in ("branch_code", "cost_center_code")},
                "branch_id": branches.get(d.get("branch_code")),
                "cost_center_id": cost_centers.get(d.get("cost_center_code")),
            },
        )
        divisions = await put(
            "divisions",
            groups["divisions"],
            lambda d: {
                **{k: v for k, v in d.items() if k != "department_code"},
                "department_id": departments.get(d.get("department_code")),
            },
        )
        await put(
            "positions",
            groups["positions"],
            lambda d: {
                **{k: v for k, v in d.items() if k not in ("department_code", "division_code", "grade_code")},
                "department_id": departments.get(d.get("department_code")),
                "division_id": divisions.get(d.get("division_code")),
                "job_grade_id": grades.get(d.get("grade_code")),
            },
        )
        await put(
            "projects",
            groups["projects"],
            lambda d: {
                **{k: v for k, v in d.items() if k not in ("branch_code", "cost_center_code")},
                "branch_id": branches.get(d.get("branch_code")),
                "cost_center_id": cost_centers.get(d.get("cost_center_code")),
            },
        )
        await put("employment_statuses", groups["employment_statuses"])
        await put("contract_types", groups["contract_types"])
        await put("certification_types", groups["certification_types"])
        await put("document_types", groups["document_types"])

        # ---- approval workflows
        for wf in WORKFLOW_SEED.get(code, []):
            steps = wf.get("steps", [])
            doc = await _upsert(
                "approval_workflows",
                {"company_id": cid, "code": wf["code"]},
                {
                    "company_id": cid,
                    "code": wf["code"],
                    "name": wf["name"],
                    "document_kind": wf["document_kind"],
                    "scope_type": "company",
                    "scope_id": None,
                    "description": wf.get("description"),
                    "is_default": wf.get("is_default", False),
                },
            )
            if await db.approval_steps.count_documents({"company_id": cid, "workflow_id": doc["id"]}):
                continue
            for step in steps:
                await db.approval_steps.insert_one(
                    {
                        "id": new_id(),
                        "company_id": cid,
                        "workflow_id": doc["id"],
                        "status": "active",
                        **STEP_DEFAULTS,
                        **step,
                        **audit_fields(None, creating=True),
                    }
                )

        # ---- policy overrides demonstrating inheritance
        if code == "NEP":
            overrides = [
                {"config_key": "leave.annual_quota_days", "scope_type": "company", "scope_id": None, "scope_label": "Default Perusahaan", "value": 12},
                {"config_key": "leave.annual_quota_days", "scope_type": "branch", "scope_id": branches.get("BLK"), "scope_label": "Cabang Balikpapan", "value": 14},
                {"config_key": "leave.annual_quota_days", "scope_type": "project", "scope_id": lookup["projects"].get("PRJ-001"), "scope_label": "EPC Gas Plant Sangatta", "value": 18},
                {"config_key": "attendance.late_tolerance_minutes", "scope_type": "company", "scope_id": None, "scope_label": "Default Perusahaan", "value": 10},
                {"config_key": "attendance.late_tolerance_minutes", "scope_type": "branch", "scope_id": branches.get("BLK"), "scope_label": "Cabang Balikpapan", "value": 20},
                {"config_key": "payroll.cut_off_day", "scope_type": "company", "scope_id": None, "scope_label": "Default Perusahaan", "value": 25},
                {"config_key": "contract.expiry_reminder_days", "scope_type": "company", "scope_id": None, "scope_label": "Default Perusahaan", "value": 45},
            ]
        else:
            overrides = [
                {"config_key": "leave.annual_quota_days", "scope_type": "company", "scope_id": None, "scope_label": "Default Perusahaan", "value": 12},
                {"config_key": "attendance.work_hours_per_day", "scope_type": "company", "scope_id": None, "scope_label": "Default Perusahaan", "value": 8},
            ]
        for ov in overrides:
            await _upsert(
                "config_overrides",
                {
                    "company_id": cid,
                    "config_key": ov["config_key"],
                    "scope_type": ov["scope_type"],
                    "scope_id": ov["scope_id"],
                },
                {
                    "company_id": cid,
                    "effective_from": None,
                    "effective_to": None,
                    "notes": None,
                    **ov,
                },
            )


async def seed_employees(company_ids: Dict[str, str]) -> None:
    """Karyawan demo + kontrak + sertifikasi (modul employee_core)."""
    db = get_db()
    today = datetime.now(timezone.utc).date()

    def iso(offset: Optional[int]) -> Optional[str]:
        if offset is None:
            return None
        return (today + timedelta(days=offset)).isoformat()

    for code, employees in EMPLOYEE_SEED.items():
        cid = company_ids.get(code)
        if not cid:
            continue

        async def code_map(collection: str) -> Dict[str, str]:
            rows = await db[collection].find({"company_id": cid}, NO_ID).to_list(2000)
            return {r.get("code"): r["id"] for r in rows if r.get("code")}

        maps = {
            "branches": await code_map("branches"),
            "work_locations": await code_map("work_locations"),
            "departments": await code_map("departments"),
            "divisions": await code_map("divisions"),
            "positions": await code_map("positions"),
            "job_grades": await code_map("job_grades"),
            "cost_centers": await code_map("cost_centers"),
            "projects": await code_map("projects"),
            "employment_statuses": await code_map("employment_statuses"),
            "contract_types": await code_map("contract_types"),
            "certification_types": await code_map("certification_types"),
        }

        for spec in employees:
            contracts = spec.get("contracts", [])
            certifications = spec.get("certifications", [])
            data = {
                k: v
                for k, v in spec.items()
                if k not in ("contracts", "certifications")
                and not k.endswith("_code")
            }
            data.update(
                {
                    "company_id": cid,
                    "branch_id": maps["branches"].get(spec.get("branch_code")),
                    "work_location_id": maps["work_locations"].get(spec.get("work_location_code")),
                    "department_id": maps["departments"].get(spec.get("department_code")),
                    "division_id": maps["divisions"].get(spec.get("division_code")),
                    "position_id": maps["positions"].get(spec.get("position_code")),
                    "job_grade_id": maps["job_grades"].get(spec.get("grade_code")),
                    "cost_center_id": maps["cost_centers"].get(spec.get("cost_center_code")),
                    "project_id": maps["projects"].get(spec.get("project_code")),
                    "employment_status_id": maps["employment_statuses"].get(
                        spec.get("employment_status_code")
                    ),
                    "is_demo_data": True,
                }
            )
            employee = await _upsert(
                "employees",
                {"company_id": cid, "employee_number": spec["employee_number"]},
                data,
            )

            for c in contracts:
                await _upsert(
                    "employee_contracts",
                    {"company_id": cid, "contract_number": c["number"]},
                    {
                        "company_id": cid,
                        "employee_id": employee["id"],
                        "contract_type_id": maps["contract_types"].get(c["type_code"]),
                        "contract_number": c["number"],
                        "start_date": iso(c.get("start_offset")),
                        "end_date": iso(c.get("end_offset")),
                        "position_id": maps["positions"].get(spec.get("position_code")),
                        "basic_salary": c.get("basic_salary"),
                        "allowance": c.get("allowance"),
                        "approval_state": c.get("approval_state", "draft"),
                        "notes": None,
                        "is_demo_data": True,
                    },
                )

            for s in certifications:
                await _upsert(
                    "employee_certifications",
                    {"company_id": cid, "employee_id": employee["id"], "name": s["name"]},
                    {
                        "company_id": cid,
                        "employee_id": employee["id"],
                        "certification_type_id": maps["certification_types"].get(s["type_code"]),
                        "name": s["name"],
                        "certificate_number": s.get("number"),
                        "issuer": s.get("issuer"),
                        "issued_date": iso(s.get("issued_offset")),
                        "expiry_date": iso(s.get("expiry_offset")),
                        "notes": None,
                        "is_demo_data": True,
                    },
                )


DEMO_DOCUMENTS = {
    "NEP": [
        {
            "type_code": "KTP",
            "name": "KTP - Rina Kusuma",
            "employee_number": "NEP-0001",
            "document_number": "3174056709900002",
            "file_name": "ktp-rina-kusuma.png",
            "ext": "png",
            "expiry_offset": None,
        },
        {
            "type_code": "MCU",
            "name": "Medical Check Up - Joko Purnomo",
            "employee_number": "NEP-0004",
            "document_number": "MCU/2026/0102",
            "file_name": "mcu-joko-purnomo.pdf",
            "ext": "pdf",
            "expiry_offset": 18,
            "pdf_lines": [
                "PT Nusantara Energi Prima",
                "Nama: Joko Purnomo (NEP-0004)",
                "Jenis pemeriksaan: Medical Check Up tahunan",
                "Hasil: Fit to work",
                "Dokumen contoh untuk mencoba fitur pratinjau dokumen.",
            ],
        },
    ],
    "KBS": [
        {
            "type_code": "KTP",
            "name": "KTP - Andi Saputra",
            "employee_number": "KBS-0001",
            "document_number": "3578011102910001",
            "file_name": "ktp-andi-saputra.png",
            "ext": "png",
            "expiry_offset": None,
        },
    ],
}


async def seed_demo_documents(company_ids: Dict[str, str]) -> None:
    """Dokumen contoh dengan berkas nyata di object storage agar fitur pratinjau\n    langsung bisa dicoba. Aman dijalankan berulang (idempotent).\n    """
    from .core.demo_files import pdf_bytes, png_bytes
    from .core.storage import guess_mime, object_path, put_object

    db = get_db()
    today = datetime.now(timezone.utc).date()

    for code, specs in DEMO_DOCUMENTS.items():
        cid = company_ids.get(code)
        if not cid:
            continue
        for spec in specs:
            existing = await db.documents.find_one(
                {"company_id": cid, "name": spec["name"]}, NO_ID
            )
            if existing and existing.get("storage_path"):
                continue
            doc_type = await db.document_types.find_one(
                {"company_id": cid, "code": spec["type_code"]}, NO_ID
            )
            employee = await db.employees.find_one(
                {"company_id": cid, "employee_number": spec["employee_number"]}, NO_ID
            )
            if not doc_type or not employee:
                continue
            payload = (
                png_bytes()
                if spec["ext"] == "png"
                else pdf_bytes(spec["name"], spec.get("pdf_lines") or [])
            )
            file_id = new_id()
            path = object_path(cid, file_id, spec["ext"])
            content_type = guess_mime(spec["ext"])
            try:
                result = put_object(path, payload, content_type)
            except Exception:  # noqa: BLE001 - storage opsional saat seeding
                continue
            data = {
                "company_id": cid,
                "document_type_id": doc_type["id"],
                "name": spec["name"],
                "owner_type": "employee",
                "owner_id": employee["id"],
                "owner_label": employee.get("full_name"),
                "document_number": spec.get("document_number"),
                "issued_date": None,
                "expiry_date": (
                    (today + timedelta(days=spec["expiry_offset"])).isoformat()
                    if spec.get("expiry_offset") is not None
                    else None
                ),
                "notes": "Dokumen contoh untuk mencoba fitur pratinjau.",
                "file_name": spec["file_name"],
                "storage_path": result.get("path", path),
                "file_size": result.get("size", len(payload)),
                "file_extension": spec["ext"],
                "mime_type": content_type,
                "is_deleted": False,
                "version": 1,
                "is_demo_data": True,
            }
            if existing:
                await db.documents.update_one(
                    {"company_id": cid, "id": existing["id"]},
                    {"$set": {**data, **audit_fields(None, creating=False)}},
                )
            else:
                await _upsert("documents", {"company_id": cid, "name": spec["name"]}, data)


async def seed_payroll(company_ids: Dict[str, str]) -> None:
    """Modul Payroll: komponen gaji, struktur gaji karyawan, alur persetujuan,
    tautan akun karyawan, dan default pengaturan pengingat. Idempoten."""
    db = get_db()

    for code, cid in company_ids.items():
        # --- pastikan modul payroll aktif (modul ini baru dirilis) ---
        await db.company_modules.update_one(
            {"company_id": cid, "module_key": "payroll"},
            {
                "$set": {"is_active": True, "activated_at": now(), "updated_at": now()},
                "$setOnInsert": {
                    "id": new_id(), "company_id": cid, "module_key": "payroll",
                    "notes": None, "status": "active", "created_at": now(),
                    "created_by": None, "updated_by": None,
                },
            },
            upsert=True,
        )

        # --- komponen gaji ---
        component_ids: Dict[str, str] = {}
        for comp in PAYROLL_COMPONENT_SEED:
            doc = await _upsert(
                "payroll_components",
                {"company_id": cid, "code": comp["code"]},
                {"company_id": cid, **comp, "percent": 0, "is_demo_data": True},
            )
            component_ids[comp["code"]] = doc["id"]

        # --- alur persetujuan payroll ---
        wf = await _upsert(
            "approval_workflows",
            {"company_id": cid, "code": PAYROLL_WORKFLOW["code"]},
            {
                "company_id": cid,
                "code": PAYROLL_WORKFLOW["code"],
                "name": PAYROLL_WORKFLOW["name"],
                "document_kind": PAYROLL_WORKFLOW["document_kind"],
                "description": PAYROLL_WORKFLOW["description"],
                "is_default": True,
                "step_count": len(PAYROLL_WORKFLOW["steps"]),
                "is_demo_data": True,
            },
        )
        for step in PAYROLL_WORKFLOW["steps"]:
            await _upsert(
                "approval_steps",
                {"company_id": cid, "workflow_id": wf["id"], "step_order": step["step_order"]},
                {"company_id": cid, "workflow_id": wf["id"], **step, "is_demo_data": True},
            )

        # --- struktur gaji per karyawan ---
        employees = await db.employees.find(
            {"company_id": cid, "status": {"$ne": "deleted"}}, NO_ID
        ).to_list(1000)
        for emp in employees:
            spec = SALARY_SEED.get(emp.get("employee_number"))
            if not spec:
                continue
            basic, ptkp, comp_codes = spec
            await _upsert(
                "employee_salaries",
                {"company_id": cid, "employee_id": emp["id"]},
                {
                    "company_id": cid,
                    "employee_id": emp["id"],
                    "basic_salary": basic,
                    "ptkp_status": ptkp,
                    "has_npwp": bool((emp.get("npwp") or "").strip()),
                    "bpjs_kesehatan_enrolled": True,
                    "bpjs_jht_enrolled": True,
                    "bpjs_jp_enrolled": True,
                    "components": [
                        {"component_id": component_ids[c], "amount": None}
                        for c in comp_codes
                        if c in component_ids
                    ],
                    "effective_date": emp.get("join_date"),
                    "notes": "Data demo struktur gaji",
                    "is_demo_data": True,
                },
            )

        # --- default pengaturan pengingat (belum aktif, SMTP belum diisi) ---
        existing_reminder = await db.reminder_settings.find_one({"company_id": cid}, NO_ID)
        if not existing_reminder:
            company = await db.companies.find_one({"id": cid}, NO_ID) or {}
            await db.reminder_settings.insert_one({
                "id": new_id(),
                "company_id": cid,
                "is_enabled": False,
                "windows": [90, 60, 30, 7],
                "recipients": [company.get("email")] if company.get("email") else [],
                "send_hour": 7,
                "send_minute": 0,
                "include_expired": True,
                "include_contracts": True,
                "include_certifications": True,
                "include_documents": True,
                "skip_when_empty": True,
                "status": "active",
                "created_at": now(),
                "updated_at": now(),
                "created_by": None,
                "updated_by": None,
            })

    # --- tautkan akun pengguna ke data karyawan (self-service slip gaji) ---
    for email, employee_name in EMPLOYEE_USER_LINKS.items():
        user = await db.users.find_one({"email": email}, NO_ID)
        if not user:
            continue
        await db.employees.update_many(
            {"full_name": employee_name, "status": {"$ne": "deleted"}},
            {"$set": {"user_id": user["id"], "updated_at": now()}},
        )


async def run_seed() -> Dict[str, Any]:
    await ensure_indexes()
    await seed_rbac()
    company_ids = await seed_companies()
    await seed_users(company_ids)
    await seed_master(company_ids)
    await seed_employees(company_ids)
    await seed_demo_documents(company_ids)
    await seed_payroll(company_ids)
    # Time Management V1 — master shift, kalender, jenis cuti, geofence, alur persetujuan, saldo cuti
    from .seed_time import seed_time_management

    await seed_time_management(company_ids)
    return {"companies": company_ids, "password": DEMO_PASSWORD, "users": [u[0] for u in DEMO_USERS]}


if __name__ == "__main__":
    result = asyncio.run(run_seed())
    print("Seed selesai:", result)
