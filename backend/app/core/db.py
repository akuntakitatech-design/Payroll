"""MariaDB access layer (SQLAlchemy Core + asyncmy).

The application was originally written against MongoDB (Motor). To keep the
business logic in the routers untouched, this module exposes a *Mongo-shaped*
async API (``db.users.find_one({...})``, ``update_one({...}, {"$set": ...})`` …)
that is translated to plain SQL against real MariaDB tables.

Conventions enforced across every table:
  - `id`           : UUID4 string primary key (CHAR(36))
  - `company_id`   : tenant foreign key on every tenant-owned record
  - `created_at` / `updated_at` : DATETIME(6) in UTC
  - `created_by` / `updated_by` : user_id foreign keys
  - `status`       : active | inactive | archived  (soft delete preferred)
  - nested objects / arrays are stored as JSON columns
  - `extra`        : JSON catch-all for any key that has no dedicated column
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    and_,
    func,
    or_,
    text,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .config import settings

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Mongo compatibility constants
# --------------------------------------------------------------------------
ASCENDING = 1
DESCENDING = -1
NO_ID = {"_id": 0}  # accepted for compatibility, ignored


class ReturnDocument:
    BEFORE = False
    AFTER = True


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------
# Table catalogue
# --------------------------------------------------------------------------
GLOBAL_COLLECTIONS = [
    "companies",
    "users",
    "roles",
    "permissions",
    "modules",
    "user_company_roles",
    "role_permissions",
    # Tenant Foundation Final - pengaturan global platform (branding KelolaKita).
    # Key/value JSON; bukan data tenant sehingga tidak memakai company_id.
    "platform_settings",
]

TENANT_COLLECTIONS = [
    "company_settings",
    "branches",
    "work_locations",
    "departments",
    "divisions",
    "positions",
    "job_grades",
    "cost_centers",
    "projects",
    "employment_statuses",
    "contract_types",
    "certification_types",
    "document_types",
    "documents",
    "employees",
    "employee_contracts",
    "employee_certifications",
    "company_modules",
    "approval_workflows",
    "approval_steps",
    "config_overrides",
    "audit_logs",
    "payroll_components",
    "employee_salaries",
    "employee_salary_history",
    "payroll_runs",
    "payroll_items",
    "smtp_settings",
    "reminder_settings",
    "reminder_logs",
    "payslip_email_logs",
    # Rekrutmen V1 (Tahap A): kandidat + riwayat status. Dokumen kandidat
    # memakai tabel `documents` existing dengan owner_type="applicant".
    "candidates",
    "candidate_status_history",
    # Rekrutmen V1 (Tahap B): interview, instance approval (snapshot dari
    # approval_workflows/approval_steps existing), offering.
    "candidate_interviews",
    "candidate_approvals",
    "candidate_offerings",
    # ------------------------------------------------------------------
    # Time Management V1 (Absensi + Cuti/Izin/Sakit + Lembur)
    # Satu fondasi bersama: kalender kerja, shift, jadwal, absensi,
    # approval bersama, cuti, lembur, dan tutup periode.
    # Lampiran tetap memakai tabel `documents` existing.
    # ------------------------------------------------------------------
    "work_shifts",
    "work_calendar_days",
    "work_schedules",
    "attendances",
    "attendance_corrections",
    "time_imports",
    "time_approvals",
    "time_policies",
    "time_periods",
    "leave_types",
    "leave_requests",
    "leave_ledger",
    "leave_balances",
    "overtime_requests",
    # ------------------------------------------------------------------
    # Upgrade 01B - Status Karyawan (status bisnis tenant) + riwayatnya.
    # Terpisah dari `employment_statuses` (status hubungan kerja: PKWT/PKWTT).
    # ------------------------------------------------------------------
    "employee_business_statuses",
    "employee_status_history",
    # Upgrade 01C - anggota keluarga karyawan (repeatable, bukan kolom anak_1/anak_2)
    "employee_family_members",
    # Upgrade 01D - penempatan karyawan (current + riwayat)
    "employee_assignments",
    # Upgrade 01E - migrasi/impor Excel karyawan (metadata batch + hasil analisis per karyawan).
    # Tidak menyimpan file Excel mentah; nilai sensitif di hasil analisis selalu dimasking.
    "employee_import_batches",
    "employee_import_rows",
]

ALL_COLLECTIONS = GLOBAL_COLLECTIONS + TENANT_COLLECTIONS

# type codes used in the compact column specs below
_TYPES = {
    "id": lambda: String(36),
    "fk": lambda: String(36),
    "s": lambda: String(255),
    "s512": lambda: String(512),
    "s64": lambda: String(64),
    "s32": lambda: String(32),  # ISO date strings (YYYY-MM-DD)
    "t": lambda: Text,
    "i": lambda: Integer,
    "bi": lambda: BigInteger,
    "f": lambda: mysql.DOUBLE(),
    "b": lambda: Boolean,
    "dt": lambda: mysql.DATETIME(fsp=6),
    "j": lambda: JSON,
}

COMMON = {
    "company_id": "fk",
    "status": "s64",
    "created_at": "dt",
    "updated_at": "dt",
    "created_by": "fk",
    "updated_by": "fk",
}

MASTER = {"code": "s", "name": "s", "description": "t"}

TABLE_SPECS: Dict[str, Dict[str, str]] = {
    "companies": {
        "code": "s", "name": "s", "legal_name": "s", "npwp": "s64", "industry": "s",
        "address": "t", "city": "s", "province": "s", "postal_code": "s64", "phone": "s64",
        "email": "s", "website": "s", "logo_url": "t", "timezone": "s64", "currency": "s64",
        "fiscal_year_start_month": "i",
        # Tenant Foundation - masa berlaku layanan (additive, nullable; status dihitung, tidak disimpan)
        "subscription_start_date": "s32", "subscription_end_date": "s32", "grace_period_days": "i",
        "subscription_notes": "t",
        # Tenant Foundation Final - PIC tenant (email utama tenant = kolom existing `email`)
        # dan kunci objek logo tenant di storage (logo_url existing tetap dipakai untuk tampilan).
        "pic_name": "s", "pic_phone": "s64", "logo_path": "s512",
    },
    "users": {
        "email": "s", "full_name": "s", "password_hash": "s", "phone": "s64", "job_title": "s",
        "employee_number": "s64", "default_company_id": "fk", "last_login_at": "dt",
        "failed_login_attempts": "i", "locked_until": "dt", "must_change_password": "b",
        "is_demo_account": "b",
    },
    "roles": {"key": "s64", "name": "s", "description": "t", "is_system": "b", "scope": "s64", "sort_order": "i"},
    "permissions": {
        "key": "s", "resource": "s64", "resource_label": "s", "action": "s64", "action_label": "s",
        "module_key": "s64", "name": "s",
    },
    "modules": {"key": "s64", "name": "s", "description": "t", "is_core": "b", "icon": "s64", "sort_order": "i"},
    "user_company_roles": {"user_id": "fk", "role_key": "s64"},
    "role_permissions": {"role_key": "s64", "permission_key": "s"},
    "platform_settings": {"key": "s64", "value": "j"},
    "company_settings": {
        "employee_id_prefix": "s64", "employee_id_next_number": "i", "date_format": "s64",
        "number_format": "s64", "default_language": "s64", "week_start": "s64",
        "notification_email": "s", "enable_email_notification": "b", "enable_audit_retention_days": "i",
        "require_two_factor": "b", "password_min_length": "i", "session_timeout_minutes": "i",
        "payroll_bank_name": "s", "payroll_bank_account_number": "s64", "payroll_bank_account_name": "s",
        "payroll_transfer_note": "t", "payroll_statutory": "j",
    },
    "branches": {
        **MASTER, "address": "t", "city": "s", "province": "s", "postal_code": "s64", "phone": "s64",
        "email": "s", "is_head_office": "b", "notes": "t",
    },
    "work_locations": {
        **MASTER, "branch_id": "fk", "address": "t", "latitude": "f", "longitude": "f", "radius_meter": "f",
        "location_type": "s64", "timezone": "s64", "notes": "t",
        # Time Management V1 — konfigurasi geofence absensi (per lokasi kerja).
        "geofence_enabled": "b", "attendance_location_policy": "s32", "gps_accuracy_max_meter": "f",
    },
    "departments": {**MASTER, "branch_id": "fk", "parent_id": "fk", "cost_center_id": "fk", "head_user_id": "fk"},
    "divisions": {**MASTER, "department_id": "fk", "head_user_id": "fk"},
    "positions": {
        **MASTER, "department_id": "fk", "division_id": "fk", "job_grade_id": "fk",
        "reports_to_position_id": "fk", "is_supervisory": "b",
    },
    "job_grades": {**MASTER, "level": "i", "min_salary": "f", "max_salary": "f"},
    "cost_centers": {**MASTER, "branch_id": "fk", "budget_owner_user_id": "fk"},
    "projects": {
        **MASTER, "client_name": "s", "branch_id": "fk", "work_location_id": "fk", "cost_center_id": "fk",
        "start_date": "s32", "end_date": "s32", "contract_value": "f", "project_manager_user_id": "fk",
    },
    "employment_statuses": {**MASTER, "is_permanent": "b", "requires_contract": "b"},
    "contract_types": {**MASTER, "duration_months": "i", "is_extendable": "b", "max_extension": "i"},
    "certification_types": {
        **MASTER, "issuing_body": "s", "validity_months": "i", "is_mandatory": "b", "reminder_days": "i",
    },
    "document_types": {
        **MASTER, "category": "s64", "owner_scope": "s64", "is_mandatory": "b", "has_expiry": "b",
        "reminder_days": "i", "allowed_extensions": "s", "max_size_mb": "f",
    },
    "documents": {
        "document_type_id": "fk", "name": "s", "owner_type": "s64", "owner_id": "fk", "owner_label": "s",
        "document_number": "s", "issued_date": "s32", "expiry_date": "s32", "notes": "t",
        "file_name": "s", "storage_path": "s512", "file_size": "bi", "file_extension": "s64",
        "mime_type": "s", "is_deleted": "b", "version": "i", "is_demo_data": "b",
    },
    "employees": {
        "full_name": "s", "employee_number": "s64", "nik": "s64", "npwp": "s64", "gender": "s64",
        "birth_place": "s", "birth_date": "s32", "marital_status": "s64", "religion": "s64",
        "education": "s64", "email": "s", "phone": "s64", "address": "t", "city": "s",
        "emergency_contact_name": "s", "emergency_contact_phone": "s64", "job_title": "s",
        "join_date": "s32", "employment_status_id": "fk", "branch_id": "fk", "work_location_id": "fk",
        "department_id": "fk", "division_id": "fk", "position_id": "fk", "job_grade_id": "fk",
        "cost_center_id": "fk", "project_id": "fk", "bank_name": "s", "bank_account_number": "s64",
        "bank_account_name": "s", "bpjs_kesehatan_number": "s64", "bpjs_tk_number": "s64",
        "notes": "t", "user_id": "fk", "is_demo_data": "b",
        # Rekrutmen Tahap C: jejak asal karyawan (kandidat) — unik per perusahaan
        "candidate_id": "fk",
        # Upgrade 01B: status bisnis saat ini -> employee_business_statuses.id
        # (field legacy `status` active/inactive/archived tetap dipertahankan).
        "current_employee_status_id": "fk",
        # Upgrade 01C - Profile 360 (alamat KTP = `address`, email pribadi = `email`)
        "domicile_address": "t", "province": "s", "postal_code": "s32",
        # Upgrade 01C - foto profil (object storage tenant-aware, disajikan lewat proxy API)
        "photo_path": "s512", "photo_version": "s32",
    },
    "employee_contracts": {
        "employee_id": "fk", "contract_type_id": "fk", "contract_number": "s", "start_date": "s32",
        "end_date": "s32", "position_id": "fk", "basic_salary": "f", "allowance": "f", "notes": "t",
        "approval_state": "s64", "is_demo_data": "b",
    },
    "employee_certifications": {
        "employee_id": "fk", "certification_type_id": "fk", "name": "s", "certificate_number": "s",
        "issuer": "s", "issued_date": "s32", "expiry_date": "s32", "notes": "t", "is_demo_data": "b",
    },
    "company_modules": {"module_key": "s64", "is_active": "b", "activated_at": "dt", "deactivated_at": "dt", "notes": "t"},
    "approval_workflows": {
        "code": "s", "name": "s", "document_kind": "s64", "scope_type": "s64", "scope_id": "fk",
        "description": "t", "is_default": "b", "step_count": "i", "is_demo_data": "b",
    },
    "approval_steps": {
        "workflow_id": "fk", "step_order": "i", "name": "s", "approver_type": "s64",
        "approver_role_key": "s64", "approver_user_id": "fk", "approver_position_id": "fk",
        "is_mandatory": "b", "allow_delegation": "b", "sla_days": "i", "condition_note": "t",
        "is_demo_data": "b",
    },
    "config_overrides": {
        "config_key": "s", "scope_type": "s64", "scope_id": "fk", "scope_label": "s", "value": "j",
        "effective_from": "s32", "effective_to": "s32", "notes": "t",
    },
    "audit_logs": {
        "user_id": "fk", "user_name": "s", "user_email": "s", "module": "s64", "resource": "s64",
        "action": "s64", "record_id": "fk", "record_label": "s", "before_value": "j", "after_value": "j",
        "changed_fields": "j", "notes": "t", "ip_address": "s64", "user_agent": "t",
    },
    "payroll_components": {
        "code": "s64", "name": "s", "kind": "s64", "calc": "s64", "default_amount": "f", "percent": "f",
        "taxable": "b", "prorate": "b", "include_in_bpjs_base": "b", "sort_order": "i",
        "description": "t", "is_demo_data": "b",
    },
    "employee_salaries": {
        "employee_id": "fk", "basic_salary": "f", "ptkp_status": "s64", "has_npwp": "b",
        "bpjs_kesehatan_enrolled": "b", "bpjs_jht_enrolled": "b", "bpjs_jp_enrolled": "b",
        "components": "j", "effective_date": "s32", "notes": "t", "is_demo_data": "b",
    },
    "employee_salary_history": {
        "employee_id": "fk", "basic_salary": "f", "previous_basic_salary": "f", "ptkp_status": "s64",
        "effective_date": "s32", "notes": "t",
    },
    "payroll_runs": {
        "year": "i", "month": "i", "period_label": "s", "run_status": "s64", "notes": "t",
        "payment_date": "s32", "workflow_id": "fk", "workflow_name": "s", "totals": "j",
        "employee_count": "i", "skipped": "j", "history": "j", "statutory_snapshot": "j",
        "calculated_at": "dt", "calculated_by": "fk",
        "submitted_at": "dt", "submitted_by": "fk", "submitted_by_name": "s", "submitted_note": "t",
        "approved_at": "dt", "approved_by": "fk", "approved_by_name": "s", "approved_note": "t",
        "rejected_at": "dt", "rejected_by": "fk", "rejected_by_name": "s", "rejected_note": "t",
        "paid_at": "dt", "paid_by": "fk", "paid_by_name": "s", "paid_note": "t",
    },
    "payroll_items": {
        "run_id": "fk", "employee_id": "fk", "employee_number": "s64", "full_name": "s", "job_title": "s",
        "bank_name": "s", "bank_account_number": "s64", "period": "j", "attendance": "j",
        "basic_salary": "f", "basic_salary_paid": "f", "earnings": "j", "deductions": "j", "bpjs": "j",
        "tax": "j", "totals": "j", "adjustments": "j", "payslip_email_status": "s64",
        "payslip_email_at": "dt", "payslip_email_to": "s", "payslip_email_error": "t",
    },
    "smtp_settings": {
        "host": "s", "port": "i", "username": "s", "password": "s", "security": "s64", "from_email": "s",
        "from_name": "s", "is_enabled": "b", "auto_send_payslip": "b",
    },
    "reminder_settings": {
        "is_enabled": "b", "windows": "j", "recipients": "j", "send_hour": "i", "send_minute": "i",
        "include_expired": "b", "include_contracts": "b", "include_certifications": "b",
        "include_documents": "b", "skip_when_empty": "b",
    },
    "reminder_logs": {"trigger": "s64", "message": "t", "recipients": "j", "item_count": "i", "counts": "j", "subject": "s"},
    "payslip_email_logs": {"run_id": "fk", "period_label": "s", "trigger": "s64", "sent_count": "i", "failed_count": "i", "summary": "t"},
    # ------------------------------------------------------------------ Rekrutmen V1
    # `status` (COMMON) = status record (active/deleted); `stage_status` = tahapan pipeline.
    "candidates": {
        # identitas
        "candidate_number": "s64", "full_name": "s", "nik": "s64", "birth_place": "s", "birth_date": "s32",
        "gender": "s64", "phone": "s64", "email": "s", "address": "t", "city": "s",
        # lamaran (FK ke master existing, tanpa master duplikat)
        "position_id": "fk", "department_id": "fk", "work_location_id": "fk", "project_id": "fk",
        "applied_position_title": "s", "source": "s64", "source_detail": "s", "applied_at": "s32",
        "expected_salary": "f", "available_from": "s32",
        # pendidikan & pengalaman
        "last_education": "s64", "major": "s", "institution": "s", "graduation_year": "i",
        "last_company": "s", "last_position": "s", "experience_years": "f",
        # pipeline
        "stage_status": "s64", "stage_changed_at": "dt", "rejection_reason": "t",
        # screening
        "screening_result": "s64", "screening_score": "i", "screening_notes": "t",
        "screening_recommendation": "s64", "screened_by": "fk", "screened_by_name": "s", "screened_at": "dt",
        # konversi (dipakai tahap berikutnya; disiapkan agar tidak perlu ALTER lagi)
        "employee_id": "fk", "converted_at": "dt", "converted_by": "fk",
        # approval (Tahap B): ronde approval aktif; naik bila kelak ada resubmit
        "approval_round": "i",
        "notes": "t", "is_demo_data": "b",
    },
    # Upgrade 01B - master status bisnis per tenant. system_category terkunci:
    # ACTIVE | STANDBY | INACTIVE (UI: AKTIF | STANDBY | TIDAK AKTIF).
    "employee_business_statuses": {
        **MASTER, "system_category": "s32", "is_active": "b", "is_default": "b", "sort_order": "i",
    },
    # Upgrade 01B - riwayat perubahan status karyawan (append-only).
    # source: MANUAL | LEGACY_BASELINE | IMPORT | SYSTEM
    "employee_status_history": {
        "employee_id": "fk", "previous_status_id": "fk", "new_status_id": "fk",
        "previous_category": "s32", "new_category": "s32", "effective_date": "s32",
        "reason": "s512", "notes": "t", "source": "s32", "changed_by": "fk", "changed_by_name": "s",
        "legacy_status_before": "s64", "legacy_status_after": "s64",
    },
    # Upgrade 01C - anggota keluarga (repeatable). relationship: SUAMI|ISTRI|ANAK|AYAH|IBU|SAUDARA|LAINNYA
    "employee_family_members": {
        "employee_id": "fk", "relationship": "s32", "full_name": "s", "nik": "s64",
        "birth_place": "s", "birth_date": "s32", "gender": "s64", "occupation": "s",
        "is_emergency_contact": "b", "phone": "s64", "notes": "t",
    },
    # Upgrade 01D - penempatan. assignment_status: ACTIVE | ENDED (kolom `status` generik tetap 'active').
    # source: LEGACY_BASELINE | MANUAL | TRANSFER | EMPLOYEE_CREATE | IMPORT | RECRUITMENT
    "employee_assignments": {
        "employee_id": "fk", "project_id": "fk", "work_location_id": "fk", "branch_id": "fk",
        "department_id": "fk", "division_id": "fk", "position_id": "fk", "cost_center_id": "fk",
        "start_date": "s32", "end_date": "s32", "assignment_status": "s32", "source": "s32",
        "reason": "s512", "notes": "t", "end_reason": "s512", "end_notes": "t", "ended_by": "fk",
        "previous_assignment_id": "fk",
    },
    # Upgrade 01E - batch impor. batch_status: ANALYZED | COMMITTING | COMMITTED | PARTIAL | FAILED | CANCELLED
    "employee_import_batches": {
        "batch_number": "s64", "batch_status": "s32", "file_name": "s", "file_hash": "s64", "file_size": "i",
        "mapping_version": "s64", "total_employees": "i", "count_new": "i", "count_update": "i",
        "count_unchanged": "i", "count_conflict": "i", "count_error": "i", "committed_count": "i",
        "failed_count": "i", "skipped_count": "i", "uploaded_by": "fk", "uploaded_by_name": "s",
        "analyzed_at": "dt", "committed_at": "dt", "committed_by": "fk", "committed_by_name": "s",
        "duplicate_of_batch_id": "fk", "warnings": "j", "notes": "t",
    },
    # Upgrade 01E - hasil analisis per karyawan (business key = nomor karyawan).
    # row_class: NEW | UPDATE | UNCHANGED | CONFLICT | ERROR ; commit_status: PENDING | COMMITTED | FAILED | SKIPPED
    "employee_import_rows": {
        "batch_id": "fk", "employee_number": "s64", "employee_id": "fk", "full_name": "s", "row_class": "s32",
        "commit_status": "s32", "source_rows": "j", "changes": "j", "errors": "j", "warnings": "j",
        "change_signature": "s64", "commit_error": "t", "committed_at": "dt", "seq": "i",
    },
    "candidate_status_history": {
        "candidate_id": "fk", "action": "s64", "from_status": "s64", "to_status": "s64",
        "notes": "t", "changed_by": "fk", "changed_by_name": "s", "changed_at": "dt",
    },
    # `status` (COMMON) = status record; `interview_status` = scheduled|completed|cancelled
    "candidate_interviews": {
        "candidate_id": "fk", "interview_type": "s64", "interview_type_label": "s", "sequence": "i",
        "scheduled_date": "s32", "start_time": "s32", "end_time": "s32",
        "interviewer_user_id": "fk", "interviewer_name": "s", "interviewer_title": "s",
        "interview_mode": "s32", "location": "s", "meeting_link": "s512", "notes": "t",
        "score": "i", "recommendation": "s32", "result": "s32", "interviewer_notes": "t",
        "interview_status": "s32", "completed_at": "dt", "completed_by": "fk",
        "cancelled_at": "dt", "cancelled_by": "fk", "cancel_reason": "t",
    },
    # Snapshot langkah workflow saat submit; konfigurasi asli tidak diubah.
    "candidate_approvals": {
        "candidate_id": "fk", "approval_round": "i", "workflow_id": "fk", "workflow_code": "s64",
        "workflow_name": "s", "workflow_step_id": "fk", "step_order": "i", "step_name": "s",
        "approver_type": "s32", "approver_role_key": "s64", "approver_user_id": "fk",
        "approver_position_id": "fk", "approver_label": "s", "is_mandatory": "b",
        "decision": "s32", "decided_by": "fk", "decided_by_name": "s", "decided_at": "dt", "notes": "t",
        "submitted_by": "fk", "submitted_at": "dt",
    },
    # Satu offering aktif per kandidat: active_flag = 1 (aktif) atau NULL, dijaga unique index.
    "candidate_offerings": {
        "candidate_id": "fk", "version": "i", "active_flag": "i",
        "position_id": "fk", "department_id": "fk", "work_location_id": "fk", "project_id": "fk",
        "employment_status_id": "fk", "start_date": "s32", "basic_salary": "f", "allowances": "j",
        "probation_months": "i", "notes": "t", "offer_status": "s32",
        "offered_at": "dt", "offered_by": "fk", "responded_at": "dt", "responded_by": "fk",
        "response_notes": "t", "response_date": "s32", "cancelled_at": "dt", "cancelled_by": "fk", "cancel_reason": "t",
    },
    # ======================================================================
    # TIME MANAGEMENT V1
    # ======================================================================
    # Master shift per perusahaan. Overnight = jam pulang <= jam masuk.
    "work_shifts": {
        **MASTER, "start_time": "s32", "end_time": "s32", "break_start": "s32", "break_end": "s32",
        "late_tolerance_minutes": "i", "early_leave_tolerance_minutes": "i",
        "is_overnight": "b", "is_day_off": "b", "sort_order": "i",
    },
    # Kalender kerja: tanggal khusus (libur nasional / libur perusahaan /
    # cuti bersama / hari kerja pengganti). Hari OFF rutin berasal dari jadwal.
    "work_calendar_days": {
        "calendar_date": "s32", "day_type": "s32", "name": "s", "notes": "t",
    },
    # Jadwal kerja per karyawan per tanggal — sumber konteks bersama
    # (shift + lokasi kerja + hari kerja) untuk Absensi, Cuti, dan Lembur.
    "work_schedules": {
        "employee_id": "fk", "work_date": "s32", "shift_id": "fk", "shift_code": "s64",
        "work_location_id": "fk", "is_day_off": "b", "notes": "t",
        "source": "s32", "import_batch_id": "fk",
    },
    # Transaksi absensi. Satu baris per karyawan per work_date.
    "attendances": {
        "employee_id": "fk", "employee_number": "s64", "employee_name": "s",
        "work_date": "s32", "period_key": "s32",
        "schedule_id": "fk", "shift_id": "fk", "shift_code": "s64", "shift_name": "s",
        "work_location_id": "fk", "is_day_off": "b", "day_type": "s32",
        "scheduled_start_at": "dt", "scheduled_end_at": "dt", "scheduled_minutes": "i",
        "check_in_at": "dt", "check_out_at": "dt",
        "check_in_source": "s32", "check_out_source": "s32",
        "check_in_latitude": "f", "check_in_longitude": "f", "check_in_accuracy": "f",
        "check_in_location_captured_at": "dt",
        "check_out_latitude": "f", "check_out_longitude": "f", "check_out_accuracy": "f",
        "check_out_location_captured_at": "dt",
        "check_in_distance_meter": "f", "check_out_distance_meter": "f",
        "configured_radius_meter": "f", "geofence_policy": "s32",
        "check_in_geofence_result": "s32", "check_out_geofence_result": "s32",
        "location_approval_status": "s32", "location_reason_code": "s32", "location_reason": "t",
        "location_decided_by": "fk", "location_decided_at": "dt", "location_decision_notes": "t",
        # ESS Absensi: persetujuan lokasi per peristiwa (masuk/pulang), alasan pulang terpisah,
        # dan kunci idempotensi agar retry/double-click tidak menghasilkan transaksi ganda.
        "location_approval_for": "s32", "location_approval_round": "i",
        "check_out_location_reason_code": "s32", "check_out_location_reason": "t",
        "check_in_request_id": "s64", "check_out_request_id": "s64",
        "check_in_client_captured_at": "dt", "check_out_client_captured_at": "dt",
        "actual_work_minutes": "i", "late_minutes": "i", "early_leave_minutes": "i",
        "attendance_status": "s32", "is_valid": "b",
        "note": "t", "source": "s32", "import_batch_id": "fk",
        "manual_reason": "t", "corrected_by": "fk", "corrected_at": "dt", "correction_reason": "t",
        "leave_request_id": "fk", "leave_type_code": "s64",
        "approved_overtime_minutes": "i",
    },
    # Pengajuan koreksi absensi (karyawan) + koreksi manual HR.
    "attendance_corrections": {
        "employee_id": "fk", "employee_name": "s", "attendance_id": "fk", "work_date": "s32",
        "period_key": "s32", "correction_type": "s32",
        "current_check_in_at": "dt", "current_check_out_at": "dt",
        "proposed_check_in_at": "dt", "proposed_check_out_at": "dt",
        "reason": "t", "document_id": "fk", "request_status": "s32",
        "submitted_by": "fk", "submitted_at": "dt",
        "decided_by": "fk", "decided_at": "dt", "decision_notes": "t",
        "applied_at": "dt", "before_value": "j", "after_value": "j",
    },
    # Batch import Excel (absensi & jadwal) — dapat ditelusuri.
    "time_imports": {
        "import_kind": "s32", "filename": "s", "mapping": "j", "options": "j",
        "total_rows": "i", "success_rows": "i", "error_rows": "i", "skipped_rows": "i",
        "updated_rows": "i", "errors": "j", "imported_by": "fk", "imported_by_name": "s",
        "imported_at": "dt", "period_keys": "j",
    },
    # LAPISAN EKSEKUSI APPROVAL BERSAMA Time Management.
    # Snapshot dari approval_workflows/approval_steps existing saat submit.
    "time_approvals": {
        "document_kind": "s32", "record_id": "fk", "record_label": "s",
        "employee_id": "fk", "approval_round": "i",
        "workflow_id": "fk", "workflow_code": "s64", "workflow_name": "s",
        "workflow_step_id": "fk", "step_order": "i", "step_name": "s",
        "approver_type": "s32", "approver_role_key": "s64", "approver_user_id": "fk",
        "approver_position_id": "fk", "approver_label": "s", "is_mandatory": "b",
        "decision": "s32", "decided_by": "fk", "decided_by_name": "s", "decided_at": "dt",
        "notes": "t", "submitted_by": "fk", "submitted_at": "dt",
    },
    # Kebijakan Time Management per perusahaan (satu baris per perusahaan).
    "time_policies": {
        "attendance": "j", "overtime": "j", "leave": "j",
    },
    # Tutup / Buka Kembali Periode (per perusahaan per bulan).
    "time_periods": {
        "period_key": "s32", "period_label": "s", "period_status": "s32",
        "closed_by": "fk", "closed_by_name": "s", "closed_at": "dt", "close_notes": "t",
        "reopened_by": "fk", "reopened_by_name": "s", "reopened_at": "dt", "reopen_reason": "t",
        "history": "j",
    },
    # Master jenis cuti / izin / sakit (configurable per perusahaan).
    "leave_types": {
        **MASTER, "category": "s32", "deduct_balance": "b", "is_paid": "b",
        "attachment_required": "b", "approval_required": "b", "allow_half_day": "b",
        "minimum_notice_days": "i", "maximum_consecutive_days": "i",
        "default_quota_days": "f", "sort_order": "i", "color": "s32",
    },
    # Pengajuan cuti / izin / sakit (satu fondasi untuk ketiga tipe).
    "leave_requests": {
        "employee_id": "fk", "employee_number": "s64", "employee_name": "s",
        "leave_type_id": "fk", "leave_type_code": "s64", "leave_type_name": "s",
        "leave_category": "s32", "start_date": "s32", "end_date": "s32",
        "day_part": "s32", "requested_days": "f", "working_days": "f", "day_breakdown": "j",
        "period_keys": "j", "reason": "t", "contact_during_leave": "s",
        "document_id": "fk", "request_status": "s32",
        "deduct_balance": "b", "is_paid": "b",
        "submitted_by": "fk", "submitted_at": "dt",
        "decided_by": "fk", "decided_at": "dt", "decision_notes": "t",
        "cancelled_by": "fk", "cancelled_at": "dt", "cancel_reason": "t",
        "conflict_notes": "j",
    },
    # Buku besar saldo cuti — setiap pergerakan tercatat & dapat diaudit.
    "leave_ledger": {
        "employee_id": "fk", "employee_name": "s", "leave_type_id": "fk", "leave_type_code": "s64",
        "year": "i", "movement_type": "s32", "days": "f", "balance_after": "f",
        "reference_type": "s32", "reference_id": "fk", "notes": "t",
        "effective_date": "s32", "created_by_name": "s",
    },
    # Ringkasan saldo (diturunkan dari ledger; dipakai untuk tampilan cepat).
    "leave_balances": {
        "employee_id": "fk", "employee_name": "s", "leave_type_id": "fk", "leave_type_code": "s64",
        "year": "i", "entitlement_days": "f", "used_days": "f", "pending_days": "f",
        "adjustment_days": "f", "carry_forward_days": "f", "available_days": "f",
        "recalculated_at": "dt",
    },
    # Lembur: rencana -> persetujuan -> aktual -> approved_minutes final.
    "overtime_requests": {
        "employee_id": "fk", "employee_number": "s64", "employee_name": "s",
        "work_date": "s32", "period_key": "s32", "day_category": "s32",
        "planned_start_at": "dt", "planned_end_at": "dt",
        "planned_start_time": "s32", "planned_end_time": "s32",
        "requested_minutes": "i", "actual_minutes": "i", "approved_minutes": "i",
        "rounded_minutes": "i", "overtime_category": "s32",
        "project_id": "fk", "work_location_id": "fk", "reason": "t", "notes": "t",
        "is_retroactive": "b", "request_status": "s32",
        "submitted_by": "fk", "submitted_at": "dt",
        "decided_by": "fk", "decided_at": "dt", "decision_notes": "t",
        "cancelled_by": "fk", "cancelled_at": "dt", "cancel_reason": "t",
        "attendance_id": "fk",
    },
}

# (index_name, [columns], unique)
INDEX_SPECS: Dict[str, List[Tuple[str, List[str], bool]]] = {
    "users": [("uq_users_email", ["email"], True)],
    "companies": [("uq_companies_code", ["code"], True)],
    "platform_settings": [("uq_platform_settings_key", ["key"], True)],
    "roles": [("uq_roles_key", ["key"], True)],
    "permissions": [("uq_permissions_key", ["key"], True)],
    "modules": [("uq_modules_key", ["key"], True)],
    "role_permissions": [("uq_role_permission", ["role_key", "permission_key"], True)],
    "user_company_roles": [
        ("uq_user_company_role", ["user_id", "company_id", "role_key"], True),
        ("ix_ucr_company", ["company_id"], False),
    ],
    "company_modules": [("uq_company_module", ["company_id", "module_key"], True)],
    "company_settings": [("uq_company_settings", ["company_id"], True)],
    "audit_logs": [
        ("ix_audit_recent", ["company_id", "created_at"], False),
        ("ix_audit_module_action", ["company_id", "module", "action"], False),
    ],
    "config_overrides": [("ix_config_lookup", ["company_id", "config_key", "scope_type"], False)],
    "approval_steps": [("ix_steps_workflow", ["company_id", "workflow_id", "step_order"], False)],
    "documents": [("ix_documents_owner", ["company_id", "owner_type", "owner_id"], False)],
    "employees": [
        ("ix_employee_current_status", ["company_id", "current_employee_status_id"], False),
        ("ix_employee_number", ["company_id", "employee_number"], False),
        ("ix_employee_name", ["company_id", "full_name"], False),
        ("ix_employee_department", ["company_id", "department_id"], False),
        # Satu kandidat hanya boleh menjadi satu karyawan (NULL dibolehkan untuk karyawan non-rekrutmen)
        ("uq_employee_candidate", ["company_id", "candidate_id"], True),
    ],
    "employee_contracts": [
        ("ix_contract_employee", ["company_id", "employee_id", "start_date"], False),
        ("ix_contract_expiry", ["company_id", "end_date"], False),
    ],
    "employee_certifications": [
        ("ix_cert_employee", ["company_id", "employee_id"], False),
        ("ix_cert_expiry", ["company_id", "expiry_date"], False),
    ],
    "payroll_runs": [("ix_payroll_period", ["company_id", "year", "month"], False)],
    "payroll_items": [
        ("ix_payroll_item_run", ["company_id", "run_id", "employee_id"], False),
        ("ix_payroll_item_employee", ["company_id", "employee_id"], False),
    ],
    "employee_salaries": [("uq_employee_salary", ["company_id", "employee_id"], True)],
    "employee_salary_history": [("ix_salary_history", ["company_id", "employee_id", "created_at"], False)],
    "payroll_components": [("ix_payroll_component_code", ["company_id", "code"], False)],
    "smtp_settings": [("uq_smtp_company", ["company_id"], True)],
    "reminder_settings": [("uq_reminder_company", ["company_id"], True)],
    "reminder_logs": [("ix_reminder_log_recent", ["company_id", "created_at"], False)],
    "payslip_email_logs": [("ix_payslip_log_run", ["company_id", "run_id"], False)],
    "candidates": [
        ("uq_candidate_number", ["company_id", "candidate_number"], True),
        ("ix_candidate_stage", ["company_id", "stage_status"], False),
        ("ix_candidate_position", ["company_id", "position_id"], False),
        ("ix_candidate_nik", ["company_id", "nik"], False),
        ("ix_candidate_name", ["company_id", "full_name"], False),
        ("ix_candidate_employee", ["company_id", "employee_id"], False),
    ],
    "employee_business_statuses": [
        ("ux_employee_business_status_code", ["company_id", "code"], True),
    ],
    "employee_status_history": [
        ("ix_employee_status_history", ["company_id", "employee_id", "created_at"], False),
    ],
    "employee_family_members": [
        ("ix_employee_family_employee", ["company_id", "employee_id"], False),
    ],
    "employee_assignments": [
        ("ix_employee_assignment_employee", ["company_id", "employee_id", "assignment_status"], False),
    ],
    "employee_import_batches": [
        ("ix_employee_import_batch_recent", ["company_id", "created_at"], False),
        ("ix_employee_import_batch_hash", ["company_id", "file_hash"], False),
    ],
    "employee_import_rows": [
        ("ix_employee_import_row_batch", ["company_id", "batch_id", "seq"], False),
        ("ix_employee_import_row_class", ["company_id", "batch_id", "row_class"], False),
    ],
    "candidate_status_history": [
        ("ix_candidate_history", ["company_id", "candidate_id", "changed_at"], False),
    ],
    "candidate_interviews": [
        ("ix_interview_candidate", ["company_id", "candidate_id", "scheduled_date"], False),
        ("ix_interview_status", ["company_id", "interview_status", "scheduled_date"], False),
        ("ix_interview_interviewer", ["company_id", "interviewer_user_id"], False),
    ],
    "candidate_approvals": [
        ("uq_candidate_approval_step", ["company_id", "candidate_id", "approval_round", "step_order"], True),
        ("ix_candidate_approval_pending", ["company_id", "decision", "approver_role_key"], False),
    ],
    "candidate_offerings": [
        ("uq_candidate_offering_version", ["company_id", "candidate_id", "version"], True),
        ("uq_candidate_offering_active", ["company_id", "candidate_id", "active_flag"], True),
        ("ix_candidate_offering_status", ["company_id", "offer_status"], False),
    ],
    # ---------------------- TIME MANAGEMENT V1 ----------------------
    "work_shifts": [("uq_work_shift_code", ["company_id", "code"], True)],
    "work_calendar_days": [("uq_calendar_day", ["company_id", "calendar_date"], True)],
    "work_schedules": [
        # Satu jadwal per karyawan per tanggal (anti duplikasi + concurrency-safe).
        ("uq_schedule_employee_date", ["company_id", "employee_id", "work_date"], True),
        ("ix_schedule_date", ["company_id", "work_date"], False),
    ],
    "attendances": [
        # Satu absensi per karyawan per work_date -> mencegah double check-in.
        ("uq_attendance_employee_date", ["company_id", "employee_id", "work_date"], True),
        ("ix_attendance_date", ["company_id", "work_date"], False),
        ("ix_attendance_period", ["company_id", "period_key"], False),
        ("ix_attendance_status", ["company_id", "attendance_status"], False),
        ("ix_attendance_location_approval", ["company_id", "location_approval_status"], False),
    ],
    "attendance_corrections": [
        ("ix_correction_employee", ["company_id", "employee_id", "work_date"], False),
        ("ix_correction_status", ["company_id", "request_status"], False),
    ],
    "time_imports": [("ix_time_import_kind", ["company_id", "import_kind", "imported_at"], False)],
    "time_approvals": [
        ("uq_time_approval_step", ["company_id", "document_kind", "record_id", "approval_round", "step_order"], True),
        ("ix_time_approval_pending", ["company_id", "document_kind", "decision"], False),
        ("ix_time_approval_record", ["company_id", "record_id"], False),
    ],
    "time_policies": [("uq_time_policy_company", ["company_id"], True)],
    "time_periods": [("uq_time_period", ["company_id", "period_key"], True)],
    "leave_types": [("uq_leave_type_code", ["company_id", "code"], True)],
    "leave_requests": [
        ("ix_leave_employee", ["company_id", "employee_id", "start_date"], False),
        ("ix_leave_status", ["company_id", "request_status"], False),
    ],
    "leave_ledger": [
        ("ix_leave_ledger_lookup", ["company_id", "employee_id", "leave_type_id", "year"], False),
    ],
    "leave_balances": [
        ("uq_leave_balance", ["company_id", "employee_id", "leave_type_id", "year"], True),
    ],
    "overtime_requests": [
        ("ix_overtime_employee", ["company_id", "employee_id", "work_date"], False),
        ("ix_overtime_status", ["company_id", "request_status"], False),
        ("ix_overtime_period", ["company_id", "period_key"], False),
    ],
}

metadata = MetaData()
_tables: Dict[str, Table] = {}


def _build_tables() -> None:
    for name in ALL_COLLECTIONS:
        spec = TABLE_SPECS.get(name, {})
        cols: List[Column] = [Column("id", String(36), primary_key=True)]
        for cname, code in {**COMMON, **spec}.items():
            cols.append(Column(cname, _TYPES[code]()))
        cols.append(Column("extra", JSON, nullable=True))
        constraints: List[Any] = []
        for idx_name, idx_cols, unique in INDEX_SPECS.get(name, []):
            if unique:
                constraints.append(UniqueConstraint(*idx_cols, name=idx_name))
            else:
                constraints.append(Index(idx_name, *idx_cols))
        if name in TENANT_COLLECTIONS and not any(
            c.name == "ix_company_status" for c in constraints if isinstance(c, Index)
        ):
            constraints.append(Index(f"ix_{name}_company_status", "company_id", "status"))
        _tables[name] = Table(
            name,
            metadata,
            *cols,
            *constraints,
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
            mysql_engine="InnoDB",
        )


_build_tables()


def get_table(name: str) -> Table:
    try:
        return _tables[name]
    except KeyError as exc:
        raise KeyError(f"Tabel '{name}' belum terdaftar pada katalog database (app/core/db.py).") from exc


# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------
_engine: Optional[AsyncEngine] = None


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, (set, tuple)):
        return list(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", "ignore")
    return str(obj)


def json_dumps(value: Any) -> str:
    return json.dumps(value, default=_json_default, ensure_ascii=False)


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        # pool_pre_ping menambah satu perjalanan jaringan pada SETIAP pengambilan
        # koneksi. Untuk database yang jauh (latensi ~240 ms) biayanya besar,
        # sehingga dapat dimatikan lewat DB_POOL_PRE_PING=false. Koneksi basi
        # tetap ditangani oleh pool_recycle.
        _engine = create_async_engine(
            settings.DATABASE_URL,
            pool_pre_ping=settings.DB_POOL_PRE_PING,
            pool_recycle=1800,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            json_serializer=json_dumps,
            json_deserializer=json.loads,
            echo=False,
        )
    return _engine


async def close_db() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
    _engine = None


async def warm_pool(size: Optional[int] = None) -> int:
    """Buka sejumlah koneksi sekaligus lalu kembalikan ke pool.

    Membuka koneksi baru ke MariaDB yang jauh memakan ~1,5 detik (TCP +
    handshake autentikasi = beberapa perjalanan jaringan), sedangkan query
    pada koneksi yang sudah ada hanya ~250 ms. Tanpa pemanasan, permintaan
    pertama yang menjalankan banyak query bersamaan harus membuat puluhan
    koneksi sekaligus dan terasa sangat lambat.

    Koneksi dibuat BERSAMAAN sehingga pemanasan hanya memakan waktu selama
    satu kali pembuatan koneksi, lalu dipakai ulang oleh seluruh permintaan.
    """
    target = int(size or settings.DB_POOL_SIZE)
    engine = get_engine()

    async def _open():
        conn = await engine.connect()
        await conn.execute(text("SELECT 1"))
        return conn

    conns = await asyncio.gather(*[_open() for _ in range(target)], return_exceptions=True)
    ready = [c for c in conns if not isinstance(c, BaseException)]
    # close() mengembalikan koneksi ke pool (bukan memutus koneksi fisik).
    await asyncio.gather(*[c.close() for c in ready], return_exceptions=True)
    logger.info("Kolam koneksi MariaDB dipanaskan: %s/%s koneksi siap.", len(ready), target)
    return len(ready)


# --------------------------------------------------------------------------
# Value coercion
# --------------------------------------------------------------------------
def _to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _parse_datetime(value: str) -> Optional[datetime]:
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return _to_utc_naive(datetime.fromisoformat(raw))
    except ValueError:
        return None


def _coerce_in(column: Column, value: Any) -> Any:
    """Python value -> DB value for a given column."""
    if value is None:
        return None
    t = column.type
    if isinstance(t, (mysql.DATETIME, sa.DateTime)):
        if isinstance(value, datetime):
            return _to_utc_naive(value)
        if isinstance(value, date):
            return datetime(value.year, value.month, value.day)
        if isinstance(value, str):
            return _parse_datetime(value)
        return None
    if isinstance(t, Boolean):
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "y", "ya")
        return bool(value)
    if isinstance(t, (Integer, BigInteger)):
        if isinstance(value, bool):
            return int(value)
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None
    if isinstance(t, (mysql.DOUBLE, sa.Float, sa.Numeric)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if isinstance(t, JSON):
        return value
    # String / Text
    if isinstance(value, (dict, list)):
        return json_dumps(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _doc_to_row(table: Table, doc: Dict[str, Any], full: bool = False) -> Dict[str, Any]:
    """Split a Mongo-style document into column values + `extra` JSON."""
    row: Dict[str, Any] = {}
    extra: Dict[str, Any] = {}
    for key, value in doc.items():
        if key == "_id":
            continue
        if key in table.c and key != "extra":
            row[key] = _coerce_in(table.c[key], value)
        elif key == "extra" and isinstance(value, dict):
            extra.update(value)
        else:
            extra[key] = value
    if full:
        for col in table.c:
            if col.name not in row and col.name != "extra":
                row[col.name] = None
    row["extra"] = extra or None
    return row


def _row_to_doc(row: Any) -> Dict[str, Any]:
    data = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
    extra = data.pop("extra", None)
    if isinstance(extra, str):
        try:
            extra = json.loads(extra)
        except ValueError:
            extra = None
    out: Dict[str, Any] = {}
    if isinstance(extra, dict):
        out.update(extra)
    out.update(data)
    return out


_JSON_COLUMNS_CACHE: Dict[str, set] = {
    name: {c.name for c in t.c if isinstance(c.type, JSON)} for name, t in _tables.items()
}


def _normalise_json_values(table: Table, doc: Dict[str, Any]) -> Dict[str, Any]:
    """asyncmy returns JSON columns as str on MariaDB; decode them."""
    for cname in _JSON_COLUMNS_CACHE[table.name]:
        val = doc.get(cname)
        if isinstance(val, (str, bytes)):
            try:
                doc[cname] = json.loads(val)
            except (ValueError, TypeError):
                pass
    return doc


# --------------------------------------------------------------------------
# Query translation
# --------------------------------------------------------------------------
_OPERATORS = {"$ne", "$in", "$nin", "$regex", "$options", "$gt", "$gte", "$lt", "$lte", "$exists", "$eq", "$not"}


def _is_operator_dict(value: Any) -> bool:
    return isinstance(value, dict) and bool(value) and all(str(k).startswith("$") for k in value.keys())


class _Field:
    """Resolved reference to a document field: real column, JSON sub-path, or `extra`."""

    def __init__(self, table: Table, key: str):
        self.table = table
        self.key = key
        self.column: Optional[Column] = None
        self.json_root: Optional[Column] = None
        self.json_path: Optional[str] = None
        if key in table.c and key != "extra":
            self.column = table.c[key]
        elif "." in key:
            root, rest = key.split(".", 1)
            if root in table.c and isinstance(table.c[root].type, JSON):
                self.json_root = table.c[root]
                self.json_path = rest
            else:
                self.json_root = table.c["extra"]
                self.json_path = key
        else:
            self.json_root = table.c["extra"]
            self.json_path = key

    # SQL expression usable for comparisons / sorting
    def expr(self):
        if self.column is not None:
            return self.column
        return func.json_unquote(func.json_extract(self.json_root, f"$.{self.json_path}"))

    def coerce(self, value: Any) -> Any:
        if self.column is not None:
            return _coerce_in(self.column, value)
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return value if value is None else (value if isinstance(value, (int, float)) else str(value))

    def is_null(self):
        if self.column is not None:
            return self.column.is_(None)
        return or_(
            self.json_root.is_(None),
            func.json_extract(self.json_root, f"$.{self.json_path}").is_(None),
            func.json_type(func.json_extract(self.json_root, f"$.{self.json_path}")) == "NULL",
        )

    def not_null(self):
        if self.column is not None:
            return self.column.isnot(None)
        return and_(
            self.json_root.isnot(None),
            func.json_extract(self.json_root, f"$.{self.json_path}").isnot(None),
            func.json_type(func.json_extract(self.json_root, f"$.{self.json_path}")) != "NULL",
        )

    def equals(self, value: Any):
        if value is None:
            return self.is_null()
        if self.column is not None:
            return self.column == self.coerce(value)
        # JSON path: match scalar `$.path` OR element inside an array of objects `$[*].path`
        clauses = [self.expr() == self.coerce(value)]
        if isinstance(value, str):
            clauses.append(
                func.json_search(self.json_root, "one", value, None, f"$[*].{self.json_path}").isnot(None)
            )
            clauses.append(
                func.json_search(self.json_root, "one", value, None, f"$.{self.json_path}").isnot(None)
            )
        return or_(*clauses)


def _regex_clause(field: _Field, pattern: str, options: str = ""):
    try:
        re.compile(pattern)
        valid = True
    except re.error:
        valid = False
    expr = field.expr()
    if not valid:
        escaped = pattern.replace("%", r"\%").replace("_", r"\_")
        return expr.like(f"%{escaped}%")
    if "i" in (options or ""):
        return func.lower(expr).op("REGEXP")(func.lower(pattern))
    return expr.op("REGEXP")(pattern)


def compile_filter(table: Table, flt: Optional[Dict[str, Any]]):
    if not flt:
        return sa.true()
    clauses = []
    for key, value in flt.items():
        if key == "$or":
            subs = [compile_filter(table, sub) for sub in (value or [])]
            clauses.append(or_(*subs) if subs else sa.false())
            continue
        if key == "$and":
            subs = [compile_filter(table, sub) for sub in (value or [])]
            clauses.append(and_(*subs) if subs else sa.true())
            continue
        if key == "$nor":
            subs = [compile_filter(table, sub) for sub in (value or [])]
            clauses.append(sa.not_(or_(*subs)) if subs else sa.true())
            continue
        if key == "_id":
            key = "id"
        field = _Field(table, key)
        if _is_operator_dict(value):
            options = value.get("$options", "")
            for op, operand in value.items():
                if op == "$options":
                    continue
                if op == "$eq":
                    clauses.append(field.equals(operand))
                elif op == "$ne":
                    if operand is None:
                        clauses.append(field.not_null())
                    else:
                        clauses.append(or_(field.expr() != field.coerce(operand), field.is_null()))
                elif op == "$in":
                    items = list(operand or [])
                    has_null = any(v is None for v in items)
                    vals = [field.coerce(v) for v in items if v is not None]
                    sub = []
                    if vals:
                        sub.append(field.expr().in_(vals))
                    if has_null:
                        sub.append(field.is_null())
                    clauses.append(or_(*sub) if sub else sa.false())
                elif op == "$nin":
                    items = list(operand or [])
                    has_null = any(v is None for v in items)
                    vals = [field.coerce(v) for v in items if v is not None]
                    if vals and has_null:
                        clauses.append(and_(field.expr().notin_(vals), field.not_null()))
                    elif vals:
                        clauses.append(or_(field.expr().notin_(vals), field.is_null()))
                    elif has_null:
                        clauses.append(field.not_null())
                elif op == "$regex":
                    clauses.append(_regex_clause(field, str(operand), options))
                elif op == "$gt":
                    clauses.append(field.expr() > field.coerce(operand))
                elif op == "$gte":
                    clauses.append(field.expr() >= field.coerce(operand))
                elif op == "$lt":
                    clauses.append(field.expr() < field.coerce(operand))
                elif op == "$lte":
                    clauses.append(field.expr() <= field.coerce(operand))
                elif op == "$exists":
                    clauses.append(field.not_null() if operand else field.is_null())
                elif op == "$not":
                    clauses.append(sa.not_(compile_filter(table, {key: operand})))
                else:
                    raise ValueError(f"Operator query '{op}' belum didukung oleh adapter MariaDB.")
        else:
            clauses.append(field.equals(value))
    return and_(*clauses) if clauses else sa.true()


def _sort_clauses(table: Table, sort_spec: Optional[List[Tuple[str, int]]]):
    out = []
    for key, direction in sort_spec or []:
        field = _Field(table, key)
        expr = field.expr()
        out.append(expr.desc() if int(direction) < 0 else expr.asc())
    return out


def _apply_projection(doc: Dict[str, Any], projection: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not projection:
        return doc
    inclusive = [k for k, v in projection.items() if v and k != "_id"]
    if inclusive:
        keep = set(inclusive) | {"id"}
        return {k: v for k, v in doc.items() if k in keep}
    exclusive = {k for k, v in projection.items() if not v}
    return {k: v for k, v in doc.items() if k not in exclusive}


# --------------------------------------------------------------------------
# Result objects (subset of pymongo's)
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# READ-ONLY guard (lindungi database produksi dari perubahan)
# --------------------------------------------------------------------------
class ReadOnlyError(HTTPException):
    def __init__(self, table: str, op: str):
        super().__init__(
            status_code=423,
            detail=(
                f"Mode HANYA-BACA aktif: operasi '{op}' pada data '{table}' diblokir. "
                "Live preview ini terhubung langsung ke database PRODUKSI, "
                "sehingga semua perubahan data dinonaktifkan untuk melindungi data asli Anda."
            ),
        )


def read_only_enabled() -> bool:
    return bool(getattr(settings, "READ_ONLY", False))


def _guard_write(table_name: str, op: str) -> bool:
    """Return True bila operasi tulis harus di-no-op (silent), raise bila harus diblokir."""
    if not read_only_enabled():
        return False
    if table_name in getattr(settings, "READ_ONLY_SILENT_TABLES", set()):
        logger.debug("READ-ONLY: %s pada '%s' di-abaikan (silent no-op).", op, table_name)
        return True
    raise ReadOnlyError(table_name, op)


class InsertOneResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id
        self.acknowledged = True


class InsertManyResult:
    def __init__(self, inserted_ids):
        self.inserted_ids = inserted_ids
        self.acknowledged = True


class UpdateResult:
    def __init__(self, matched: int, modified: int, upserted_id=None):
        self.matched_count = matched
        self.modified_count = modified
        self.upserted_id = upserted_id
        self.acknowledged = True


class DeleteResult:
    def __init__(self, deleted: int):
        self.deleted_count = deleted
        self.acknowledged = True


def _duplicate_http(exc: IntegrityError) -> HTTPException:
    return HTTPException(
        409,
        "Data duplikat: nilai unik (kode/email/kunci) sudah digunakan. Gunakan nilai lain.",
    )


# --------------------------------------------------------------------------
# Cursor
# --------------------------------------------------------------------------
class Cursor:
    def __init__(self, collection: "Collection", flt: Optional[Dict[str, Any]], projection=None):
        self._coll = collection
        self._filter = flt or {}
        self._projection = projection
        self._sort: List[Tuple[str, int]] = []
        self._skip = 0
        self._limit: Optional[int] = None
        self._buffer: Optional[List[Dict[str, Any]]] = None

    def sort(self, key_or_list, direction: Optional[int] = None) -> "Cursor":
        if isinstance(key_or_list, str):
            self._sort = [(key_or_list, direction if direction is not None else ASCENDING)]
        else:
            self._sort = [(k, d) for k, d in key_or_list]
        return self

    def skip(self, n: int) -> "Cursor":
        self._skip = max(0, int(n or 0))
        return self

    def limit(self, n: int) -> "Cursor":
        self._limit = int(n) if n else None
        return self

    async def to_list(self, length: Optional[int] = None) -> List[Dict[str, Any]]:
        limit = self._limit
        if length is not None:
            limit = min(limit, int(length)) if limit else int(length)
        return await self._coll._select(self._filter, self._projection, self._sort, self._skip, limit)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._buffer is None:
            self._buffer = await self.to_list()
        if not self._buffer:
            raise StopAsyncIteration
        return self._buffer.pop(0)


# --------------------------------------------------------------------------
# Collection
# --------------------------------------------------------------------------
class Collection:
    def __init__(self, name: str):
        self.name = name
        self.table = get_table(name)

    # ---- helpers -------------------------------------------------------
    def _where(self, flt):
        return compile_filter(self.table, flt)

    def _doc(self, row) -> Dict[str, Any]:
        return _normalise_json_values(self.table, _row_to_doc(row))

    async def _select(self, flt, projection, sort_spec, skip, limit) -> List[Dict[str, Any]]:
        stmt = sa.select(self.table).where(self._where(flt))
        if sort_spec:
            stmt = stmt.order_by(*_sort_clauses(self.table, sort_spec))
        if skip:
            stmt = stmt.offset(skip)
        if limit is not None:
            stmt = stmt.limit(limit)
        async with get_engine().connect() as conn:
            result = await conn.execute(stmt)
            rows = result.fetchall()
        return [_apply_projection(self._doc(r), projection) for r in rows]

    async def _find_ids(self, conn, flt, limit: Optional[int] = None, for_update: bool = False) -> List[str]:
        stmt = sa.select(self.table.c.id).where(self._where(flt))
        if limit:
            stmt = stmt.limit(limit)
        if for_update:
            stmt = stmt.with_for_update()
        result = await conn.execute(stmt)
        return [r[0] for r in result.fetchall()]

    def _build_update_values(
        self, update: Dict[str, Any], current: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Translate {$set,$inc,$push,$unset,$addToSet} into column values.

        For `extra`/JSON sub-paths and $push we merge in Python using `current`
        (the row read inside the same transaction)."""
        table = self.table
        values: Dict[str, Any] = {}
        extra_patch: Dict[str, Any] = {}
        extra_remove: List[str] = []
        json_patches: Dict[str, Any] = {}  # json column -> new python value
        current = current or {}

        def _json_current(col: str):
            if col in json_patches:
                return json_patches[col]
            return current.get(col)

        def _set_path(container: Any, path: str, value: Any):
            parts = path.split(".")
            node = container if isinstance(container, dict) else {}
            root = node
            for p in parts[:-1]:
                nxt = node.get(p)
                if not isinstance(nxt, dict):
                    nxt = {}
                    node[p] = nxt
                node = nxt
            node[parts[-1]] = value
            return root

        for op, payload in update.items():
            if op == "$set":
                for key, value in (payload or {}).items():
                    if key == "_id":
                        continue
                    if key in table.c and key != "extra":
                        values[key] = _coerce_in(table.c[key], value)
                    elif "." in key:
                        root, rest = key.split(".", 1)
                        if root in table.c and isinstance(table.c[root].type, JSON):
                            json_patches[root] = _set_path(_json_current(root) or {}, rest, value)
                        else:
                            extra_patch[root] = _set_path(dict((current.get(root) or {})), rest, value)
                    else:
                        extra_patch[key] = value
            elif op == "$setOnInsert":
                continue  # handled by caller on insert
            elif op == "$unset":
                for key in (payload or {}).keys():
                    if key in table.c and key != "extra":
                        values[key] = None
                    else:
                        extra_remove.append(key)
            elif op == "$inc":
                for key, amount in (payload or {}).items():
                    if key in table.c:
                        col = table.c[key]
                        values[key] = func.coalesce(col, 0) + amount
                    else:
                        extra_patch[key] = (current.get(key) or 0) + amount
            elif op in ("$push", "$addToSet"):
                for key, item in (payload or {}).items():
                    if key in table.c and isinstance(table.c[key].type, JSON):
                        arr = list(_json_current(key) or [])
                        if op == "$push" or item not in arr:
                            arr.append(item)
                        json_patches[key] = arr
                    else:
                        arr = list(current.get(key) or [])
                        if op == "$push" or item not in arr:
                            arr.append(item)
                        extra_patch[key] = arr
            elif op == "$pull":
                for key, item in (payload or {}).items():
                    if key in table.c and isinstance(table.c[key].type, JSON):
                        json_patches[key] = [x for x in (_json_current(key) or []) if x != item]
                    else:
                        extra_patch[key] = [x for x in (current.get(key) or []) if x != item]
            elif op.startswith("$"):
                raise ValueError(f"Operator update '{op}' belum didukung oleh adapter MariaDB.")

        for col, val in json_patches.items():
            values[col] = val

        if extra_patch or extra_remove:
            known = {c.name for c in table.c}
            base = {k: v for k, v in current.items() if k not in known}
            base.update(extra_patch)
            for k in extra_remove:
                base.pop(k, None)
            values["extra"] = base or None
        return values

    def _needs_current(self, update: Dict[str, Any]) -> bool:
        table = self.table
        for op, payload in update.items():
            if op in ("$push", "$addToSet", "$pull"):
                return True
            for key in (payload or {}).keys() if isinstance(payload, dict) else []:
                if key not in table.c or "." in key:
                    return True
                if op == "$inc" and key not in table.c:
                    return True
        return False

    def _upsert_doc(self, flt: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
        doc: Dict[str, Any] = {}
        for k, v in (flt or {}).items():
            if not str(k).startswith("$") and not _is_operator_dict(v):
                doc[k] = v
        doc.update(update.get("$setOnInsert") or {})
        doc.update(update.get("$set") or {})
        for k, v in (update.get("$inc") or {}).items():
            doc[k] = (doc.get(k) or 0) + v
        for k, v in (update.get("$push") or {}).items():
            doc[k] = list(doc.get(k) or []) + [v]
        doc.setdefault("id", new_id())
        return doc

    # ---- public API ----------------------------------------------------
    def find(self, flt: Optional[Dict[str, Any]] = None, projection=None, **kwargs) -> Cursor:
        cur = Cursor(self, flt, projection)
        if kwargs.get("sort"):
            cur.sort(kwargs["sort"])
        if kwargs.get("skip"):
            cur.skip(kwargs["skip"])
        if kwargs.get("limit"):
            cur.limit(kwargs["limit"])
        return cur

    async def find_one(self, flt: Optional[Dict[str, Any]] = None, projection=None, **kwargs) -> Optional[Dict[str, Any]]:
        sort_spec = kwargs.get("sort")
        rows = await self._select(flt, projection, [tuple(s) for s in sort_spec] if sort_spec else None, 0, 1)
        return rows[0] if rows else None

    async def count_documents(self, flt: Optional[Dict[str, Any]] = None, **kwargs) -> int:
        stmt = sa.select(func.count()).select_from(self.table).where(self._where(flt))
        async with get_engine().connect() as conn:
            result = await conn.execute(stmt)
            return int(result.scalar() or 0)

    async def estimated_document_count(self) -> int:
        return await self.count_documents({})

    async def distinct(self, key: str, flt: Optional[Dict[str, Any]] = None) -> List[Any]:
        field = _Field(self.table, key)
        stmt = sa.select(field.expr()).where(self._where(flt)).distinct()
        async with get_engine().connect() as conn:
            result = await conn.execute(stmt)
            return [r[0] for r in result.fetchall() if r[0] is not None]

    async def insert_one(self, doc: Dict[str, Any]) -> InsertOneResult:
        if "id" not in doc or not doc["id"]:
            doc["id"] = new_id()
        if _guard_write(self.name, "insert_one"):
            return InsertOneResult(doc["id"])
        row = _doc_to_row(self.table, doc)
        try:
            async with get_engine().begin() as conn:
                await conn.execute(sa.insert(self.table).values(**row))
        except IntegrityError as exc:
            raise _duplicate_http(exc) from exc
        return InsertOneResult(doc["id"])

    async def insert_many(self, docs: Iterable[Dict[str, Any]]) -> InsertManyResult:
        docs = list(docs)
        if not docs:
            return InsertManyResult([])
        for _d in docs:
            if not _d.get("id"):
                _d["id"] = new_id()
        if _guard_write(self.name, "insert_many"):
            return InsertManyResult([d["id"] for d in docs])
        rows = []
        for d in docs:
            if not d.get("id"):
                d["id"] = new_id()
            rows.append(_doc_to_row(self.table, d, full=True))
        try:
            async with get_engine().begin() as conn:
                await conn.execute(sa.insert(self.table), rows)
        except IntegrityError as exc:
            raise _duplicate_http(exc) from exc
        return InsertManyResult([d["id"] for d in docs])

    async def _update(self, flt, update, upsert: bool, many: bool) -> UpdateResult:
        table = self.table
        if _guard_write(self.name, "update_many" if many else "update_one"):
            return UpdateResult(0, 0, None)
        try:
            async with get_engine().begin() as conn:
                ids = await self._find_ids(conn, flt, None if many else 1, for_update=True)
                if not ids:
                    if upsert:
                        doc = self._upsert_doc(flt or {}, update)
                        await conn.execute(sa.insert(table).values(**_doc_to_row(table, doc)))
                        return UpdateResult(0, 0, doc["id"])
                    return UpdateResult(0, 0, None)
                if self._needs_current(update):
                    modified = 0
                    for rid in ids:
                        res = await conn.execute(sa.select(table).where(table.c.id == rid))
                        current = self._doc(res.fetchone())
                        values = self._build_update_values(update, current)
                        if values:
                            await conn.execute(sa.update(table).where(table.c.id == rid).values(**values))
                            modified += 1
                    return UpdateResult(len(ids), modified, None)
                values = self._build_update_values(update)
                if not values:
                    return UpdateResult(len(ids), 0, None)
                res = await conn.execute(sa.update(table).where(table.c.id.in_(ids)).values(**values))
                return UpdateResult(len(ids), res.rowcount if res.rowcount is not None else len(ids), None)
        except IntegrityError as exc:
            raise _duplicate_http(exc) from exc

    async def update_one(self, flt, update, upsert: bool = False, **kwargs) -> UpdateResult:
        return await self._update(flt, update, upsert, many=False)

    async def update_many(self, flt, update, upsert: bool = False, **kwargs) -> UpdateResult:
        return await self._update(flt, update, upsert, many=True)

    async def replace_one(self, flt, replacement: Dict[str, Any], upsert: bool = False) -> UpdateResult:
        table = self.table
        if _guard_write(self.name, "replace_one"):
            return UpdateResult(0, 0, None)
        try:
            async with get_engine().begin() as conn:
                ids = await self._find_ids(conn, flt, 1, for_update=True)
                if not ids:
                    if upsert:
                        doc = dict(replacement)
                        doc.setdefault("id", new_id())
                        await conn.execute(sa.insert(table).values(**_doc_to_row(table, doc)))
                        return UpdateResult(0, 0, doc["id"])
                    return UpdateResult(0, 0, None)
                doc = dict(replacement)
                doc["id"] = ids[0]
                row = _doc_to_row(table, doc, full=True)
                row.pop("id", None)
                await conn.execute(sa.update(table).where(table.c.id == ids[0]).values(**row))
                return UpdateResult(1, 1, None)
        except IntegrityError as exc:
            raise _duplicate_http(exc) from exc

    async def find_one_and_update(
        self,
        flt,
        update,
        projection=None,
        return_document: bool = ReturnDocument.BEFORE,
        upsert: bool = False,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        table = self.table
        if _guard_write(self.name, "find_one_and_update"):
            return await self.find_one(flt, projection)
        try:
            async with get_engine().begin() as conn:
                ids = await self._find_ids(conn, flt, 1, for_update=True)
                if not ids:
                    if not upsert:
                        return None
                    doc = self._upsert_doc(flt or {}, update)
                    await conn.execute(sa.insert(table).values(**_doc_to_row(table, doc)))
                    return _apply_projection(doc, projection) if return_document else None
                rid = ids[0]
                res = await conn.execute(sa.select(table).where(table.c.id == rid))
                before = self._doc(res.fetchone())
                values = self._build_update_values(update, before)
                if values:
                    await conn.execute(sa.update(table).where(table.c.id == rid).values(**values))
                if not return_document:
                    return _apply_projection(before, projection)
                res = await conn.execute(sa.select(table).where(table.c.id == rid))
                return _apply_projection(self._doc(res.fetchone()), projection)
        except IntegrityError as exc:
            raise _duplicate_http(exc) from exc

    async def delete_one(self, flt) -> DeleteResult:
        table = self.table
        if _guard_write(self.name, "delete_one"):
            return DeleteResult(0)
        async with get_engine().begin() as conn:
            ids = await self._find_ids(conn, flt, 1)
            if not ids:
                return DeleteResult(0)
            await conn.execute(sa.delete(table).where(table.c.id == ids[0]))
            return DeleteResult(1)

    async def delete_many(self, flt) -> DeleteResult:
        if _guard_write(self.name, "delete_many"):
            return DeleteResult(0)
        async with get_engine().begin() as conn:
            res = await conn.execute(sa.delete(self.table).where(self._where(flt)))
            return DeleteResult(res.rowcount or 0)

    async def create_index(self, *args, **kwargs) -> str:  # compatibility no-op
        return kwargs.get("name", "index")


# --------------------------------------------------------------------------
# Database facade
# --------------------------------------------------------------------------
class Database:
    def __getitem__(self, name: str) -> Collection:
        return Collection(name)

    def __getattr__(self, name: str) -> Collection:
        if name.startswith("_"):
            raise AttributeError(name)
        return Collection(name)

    async def command(self, cmd: Any) -> Dict[str, Any]:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"ok": 1}

    async def execute(self, sql: str, params: Optional[Dict[str, Any]] = None):
        if read_only_enabled() and not sql.lstrip().lower().startswith(("select", "show", "describe", "explain")):
            raise ReadOnlyError("database", "execute")
        async with get_engine().begin() as conn:
            return await conn.execute(text(sql), params or {})


_db = Database()


def get_db() -> Database:
    return _db


# --------------------------------------------------------------------------
# Schema management
# --------------------------------------------------------------------------
def _sync_schema(sync_conn) -> None:
    """Create missing tables, then add any columns that are missing in existing tables."""
    metadata.create_all(sync_conn, checkfirst=True)
    inspector = sa.inspect(sync_conn)
    dialect = sync_conn.dialect
    for table in metadata.sorted_tables:
        existing = {c["name"] for c in inspector.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing:
                continue
            ddl_type = col.type.compile(dialect=dialect)
            sync_conn.execute(text(f"ALTER TABLE `{table.name}` ADD COLUMN `{col.name}` {ddl_type} NULL"))
            logger.info("Kolom baru ditambahkan: %s.%s", table.name, col.name)
        existing_idx = {i["name"] for i in inspector.get_indexes(table.name)}
        existing_uq = {u["name"] for u in inspector.get_unique_constraints(table.name)}
        for idx in table.indexes:
            if idx.name not in existing_idx:
                idx.create(sync_conn)
        for cons in table.constraints:
            if isinstance(cons, UniqueConstraint) and cons.name and cons.name not in existing_idx | existing_uq:
                cols = ", ".join(f"`{c.name}`" for c in cons.columns)
                sync_conn.execute(text(f"ALTER TABLE `{table.name}` ADD UNIQUE `{cons.name}` ({cols})"))


async def ensure_indexes() -> None:
    """Create tables / indexes (SQL equivalent of the former Mongo index bootstrap)."""
    if read_only_enabled():
        logger.warning("READ-ONLY aktif: sinkronisasi skema/DDL dilewati (skema produksi tidak disentuh).")
        return
    async with get_engine().begin() as conn:
        await conn.run_sync(_sync_schema)


ensure_schema = ensure_indexes


# --------------------------------------------------------------------------
# Serialization helpers (kept for compatibility with existing routers)
# --------------------------------------------------------------------------
def serialize(doc):
    if doc is None:
        return None
    out = {}
    for key, value in doc.items():
        if key == "_id":
            continue
        out[key] = serialize(value) if isinstance(value, dict) else value
    return out


def serialize_list(docs):
    return [serialize(d) for d in (docs or [])]


def audit_fields(user_id: Optional[str], creating: bool = True) -> Dict[str, Any]:
    ts = now()
    if creating:
        return {"created_at": ts, "updated_at": ts, "created_by": user_id, "updated_by": user_id}
    return {"updated_at": ts, "updated_by": user_id}


# ---------------------------------------------------------------- transaksi
class _TxWriter:
    """Penulis multi-tabel dalam SATU transaksi DB (dipakai alur yang wajib atomik,
    mis. Ubah Status Karyawan: employee + riwayat + audit). Jika satu langkah gagal,
    seluruh perubahan di-rollback oleh ``transaction()``."""

    def __init__(self, conn):
        self.conn = conn

    async def select_one_for_update(self, table_name: str, flt: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        table = get_table(table_name)
        res = await self.conn.execute(
            sa.select(table).where(compile_filter(table, flt)).limit(1).with_for_update()
        )
        row = res.fetchone()
        return _row_to_doc(row) if row is not None else None

    async def insert(self, table_name: str, doc: Dict[str, Any]) -> str:
        table = get_table(table_name)
        if not doc.get("id"):
            doc["id"] = new_id()
        await self.conn.execute(sa.insert(table).values(**_doc_to_row(table, doc)))
        return doc["id"]

    async def update(self, table_name: str, flt: Dict[str, Any], values: Dict[str, Any]) -> int:
        table = get_table(table_name)
        row = {k: v for k, v in _doc_to_row(table, values).items() if k in values}
        res = await self.conn.execute(sa.update(table).where(compile_filter(table, flt)).values(**row))
        return res.rowcount or 0


@asynccontextmanager
async def transaction():
    if read_only_enabled():
        raise ReadOnlyError("multi-tabel", "transaction")
    try:
        async with get_engine().begin() as conn:
            yield _TxWriter(conn)
    except IntegrityError as exc:
        raise _duplicate_http(exc) from exc
