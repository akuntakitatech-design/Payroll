from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)
    company_id: Optional[str] = None


class RefreshRequest(BaseModel):
    refresh_token: str


class SwitchCompanyRequest(BaseModel):
    company_id: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class CompanyCreate(BaseModel):
    code: str = Field(min_length=2, max_length=20)
    name: str = Field(min_length=2)
    legal_name: Optional[str] = None
    npwp: Optional[str] = None
    industry: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    postal_code: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    timezone: str = "Asia/Jakarta"
    currency: str = "IDR"
    fiscal_year_start_month: int = 1
    modules: Optional[List[str]] = None


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    legal_name: Optional[str] = None
    npwp: Optional[str] = None
    industry: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    postal_code: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    timezone: Optional[str] = None
    currency: Optional[str] = None
    fiscal_year_start_month: Optional[int] = None
    status: Optional[str] = None


class CompanySettingsUpdate(BaseModel):
    employee_id_prefix: Optional[str] = None
    employee_id_next_number: Optional[int] = None
    date_format: Optional[str] = None
    number_format: Optional[str] = None
    default_language: Optional[str] = None
    week_start: Optional[str] = None
    notification_email: Optional[EmailStr] = None
    enable_email_notification: Optional[bool] = None
    enable_audit_retention_days: Optional[int] = None
    require_two_factor: Optional[bool] = None
    password_min_length: Optional[int] = None
    session_timeout_minutes: Optional[int] = None
    payroll_bank_name: Optional[str] = None
    payroll_bank_account_number: Optional[str] = None
    payroll_bank_account_name: Optional[str] = None
    payroll_transfer_note: Optional[str] = None


class ModuleToggleRequest(BaseModel):
    module_key: str
    is_active: bool
    notes: Optional[str] = None


class UserCompanyRoleInput(BaseModel):
    company_id: str
    role_keys: List[str] = Field(min_length=1)


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2)
    password: str = Field(min_length=8)
    phone: Optional[str] = None
    job_title: Optional[str] = None
    employee_number: Optional[str] = None
    role_keys: List[str] = Field(default_factory=list)
    is_super_admin: bool = False


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    job_title: Optional[str] = None
    employee_number: Optional[str] = None
    status: Optional[str] = None
    role_keys: Optional[List[str]] = None
    password: Optional[str] = None


class RoleCreate(BaseModel):
    key: str = Field(min_length=2, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=2)
    description: Optional[str] = None


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class RolePermissionUpdate(BaseModel):
    permission_keys: List[str]


class ApprovalStepInput(BaseModel):
    step_order: int
    name: str
    approver_type: str = "role"  # role | user | position | supervisor
    approver_role_key: Optional[str] = None
    approver_user_id: Optional[str] = None
    approver_position_id: Optional[str] = None
    is_mandatory: bool = True
    allow_delegation: bool = True
    sla_days: Optional[int] = None
    condition_note: Optional[str] = None


class ApprovalWorkflowInput(BaseModel):
    code: str = Field(min_length=2)
    name: str = Field(min_length=2)
    document_kind: str  # recruitment | contract | leave | overtime | mobilization | expense | payroll | finance_request
    scope_type: str = "company"
    scope_id: Optional[str] = None
    description: Optional[str] = None
    is_default: bool = False
    steps: List[ApprovalStepInput] = Field(default_factory=list)


class DocumentCreate(BaseModel):
    document_type_id: str
    name: str
    owner_type: str = "company"  # company | employee | project | contract | invoice | other
    owner_id: Optional[str] = None
    owner_label: Optional[str] = None
    document_number: Optional[str] = None
    issued_date: Optional[str] = None
    expiry_date: Optional[str] = None
    notes: Optional[str] = None


class DocumentUpdate(BaseModel):
    name: Optional[str] = None
    document_type_id: Optional[str] = None
    owner_type: Optional[str] = None
    owner_id: Optional[str] = None
    owner_label: Optional[str] = None
    document_number: Optional[str] = None
    issued_date: Optional[str] = None
    expiry_date: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class EmployeeCreate(BaseModel):
    full_name: str = Field(min_length=2)
    employee_number: Optional[str] = None
    nik: Optional[str] = None
    npwp: Optional[str] = None
    gender: Optional[str] = None
    birth_place: Optional[str] = None
    birth_date: Optional[str] = None
    marital_status: Optional[str] = None
    religion: Optional[str] = None
    education: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    # penempatan organisasi
    job_title: Optional[str] = None
    join_date: Optional[str] = None
    employment_status_id: Optional[str] = None
    branch_id: Optional[str] = None
    work_location_id: Optional[str] = None
    department_id: Optional[str] = None
    division_id: Optional[str] = None
    position_id: Optional[str] = None
    job_grade_id: Optional[str] = None
    cost_center_id: Optional[str] = None
    project_id: Optional[str] = None
    # payroll & jaminan sosial (data induk saja, tanpa perhitungan)
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_account_name: Optional[str] = None
    bpjs_kesehatan_number: Optional[str] = None
    bpjs_tk_number: Optional[str] = None
    notes: Optional[str] = None


class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    employee_number: Optional[str] = None
    nik: Optional[str] = None
    npwp: Optional[str] = None
    gender: Optional[str] = None
    birth_place: Optional[str] = None
    birth_date: Optional[str] = None
    marital_status: Optional[str] = None
    religion: Optional[str] = None
    education: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    job_title: Optional[str] = None
    join_date: Optional[str] = None
    employment_status_id: Optional[str] = None
    branch_id: Optional[str] = None
    work_location_id: Optional[str] = None
    department_id: Optional[str] = None
    division_id: Optional[str] = None
    position_id: Optional[str] = None
    job_grade_id: Optional[str] = None
    cost_center_id: Optional[str] = None
    project_id: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_account_name: Optional[str] = None
    bpjs_kesehatan_number: Optional[str] = None
    bpjs_tk_number: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class ContractCreate(BaseModel):
    employee_id: str
    contract_type_id: str
    contract_number: Optional[str] = None
    start_date: str
    end_date: Optional[str] = None
    position_id: Optional[str] = None
    basic_salary: Optional[float] = None
    allowance: Optional[float] = None
    notes: Optional[str] = None


class ContractUpdate(BaseModel):
    contract_type_id: Optional[str] = None
    contract_number: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    position_id: Optional[str] = None
    basic_salary: Optional[float] = None
    allowance: Optional[float] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class CertificationCreate(BaseModel):
    employee_id: str
    certification_type_id: str
    name: str = Field(min_length=2)
    certificate_number: Optional[str] = None
    issuer: Optional[str] = None
    issued_date: Optional[str] = None
    expiry_date: Optional[str] = None
    notes: Optional[str] = None


class CertificationUpdate(BaseModel):
    certification_type_id: Optional[str] = None
    name: Optional[str] = None
    certificate_number: Optional[str] = None
    issuer: Optional[str] = None
    issued_date: Optional[str] = None
    expiry_date: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class ConfigOverrideInput(BaseModel):
    config_key: str
    scope_type: str  # company | branch | division | project | employee
    scope_id: Optional[str] = None
    scope_label: Optional[str] = None
    value: Any
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    notes: Optional[str] = None


class StatusChange(BaseModel):
    status: str


# ==========================================================================
# Payroll
# ==========================================================================
class PayrollComponentCreate(BaseModel):
    code: str = Field(min_length=2, max_length=20)
    name: str = Field(min_length=2)
    kind: str = Field(default="earning", pattern="^(earning|deduction)$")
    calc: str = Field(default="fixed", pattern="^(fixed|percent_of_basic)$")
    default_amount: float = 0
    percent: float = 0
    taxable: bool = True
    prorate: bool = False
    include_in_bpjs_base: bool = False
    sort_order: int = 100
    description: Optional[str] = None


class PayrollComponentUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    kind: Optional[str] = Field(default=None, pattern="^(earning|deduction)$")
    calc: Optional[str] = Field(default=None, pattern="^(fixed|percent_of_basic)$")
    default_amount: Optional[float] = None
    percent: Optional[float] = None
    taxable: Optional[bool] = None
    prorate: Optional[bool] = None
    include_in_bpjs_base: Optional[bool] = None
    sort_order: Optional[int] = None
    description: Optional[str] = None
    status: Optional[str] = None


class SalaryComponentEntry(BaseModel):
    component_id: str
    amount: Optional[float] = None


class EmployeeSalaryUpsert(BaseModel):
    basic_salary: float = Field(default=0, ge=0)
    ptkp_status: str = "TK/0"
    has_npwp: Optional[bool] = None
    bpjs_kesehatan_enrolled: bool = True
    bpjs_jht_enrolled: bool = True
    bpjs_jp_enrolled: bool = True
    components: List[SalaryComponentEntry] = Field(default_factory=list)
    effective_date: Optional[str] = None
    notes: Optional[str] = None


class PayrollRunCreate(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    payment_date: Optional[str] = None
    notes: Optional[str] = None


class PayrollRunDecision(BaseModel):
    note: Optional[str] = None


class AdhocComponent(BaseModel):
    code: Optional[str] = None
    name: str
    amount: float = 0
    taxable: bool = True


class PayrollAdjustmentUpdate(BaseModel):
    working_days: Optional[int] = None
    unpaid_days: Optional[float] = None
    overtime_hours: Optional[float] = None
    extra_earnings: Optional[List[AdhocComponent]] = None
    extra_deductions: Optional[List[AdhocComponent]] = None
    notes: Optional[str] = None


class StatutoryConfigUpdate(BaseModel):
    bpjs_kes_cap: Optional[float] = Field(default=None, ge=0)
    bpjs_kes_employee_rate: Optional[float] = Field(default=None, ge=0, le=1)
    bpjs_kes_employer_rate: Optional[float] = Field(default=None, ge=0, le=1)
    jht_employee_rate: Optional[float] = Field(default=None, ge=0, le=1)
    jht_employer_rate: Optional[float] = Field(default=None, ge=0, le=1)
    jp_cap: Optional[float] = Field(default=None, ge=0)
    jp_employee_rate: Optional[float] = Field(default=None, ge=0, le=1)
    jp_employer_rate: Optional[float] = Field(default=None, ge=0, le=1)
    jkk_risk_class: Optional[str] = None
    jkm_employer_rate: Optional[float] = Field(default=None, ge=0, le=1)
    default_working_days: Optional[int] = Field(default=None, ge=1, le=31)
    employer_bpjs_is_taxable: Optional[bool] = None
    non_npwp_surcharge: Optional[bool] = None


# ==========================================================================
# Email (SMTP) & pengingat
# ==========================================================================
class SmtpSettingsUpdate(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    username: Optional[str] = None
    password: Optional[str] = None
    security: Optional[str] = Field(default=None, pattern="^(starttls|ssl|none)$")
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    is_enabled: Optional[bool] = None
    auto_send_payslip: Optional[bool] = None


class PayslipEmailRequest(BaseModel):
    item_ids: Optional[List[str]] = None


class SmtpTestRequest(BaseModel):
    to: Optional[str] = None


class ReminderSettingsUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    windows: Optional[List[int]] = None
    recipients: Optional[List[str]] = None
    send_hour: Optional[int] = Field(default=None, ge=0, le=23)
    send_minute: Optional[int] = Field(default=None, ge=0, le=59)
    include_expired: Optional[bool] = None
    include_contracts: Optional[bool] = None
    include_certifications: Optional[bool] = None
    include_documents: Optional[bool] = None
    skip_when_empty: Optional[bool] = None


# ==========================================================================
# Perpanjangan kontrak & impor Excel
# ==========================================================================
class ContractRenewRequest(BaseModel):
    start_date: str
    end_date: Optional[str] = None
    contract_type_id: Optional[str] = None
    contract_number: Optional[str] = None
    position_id: Optional[str] = None
    basic_salary: Optional[float] = None
    allowance: Optional[float] = None
    notes: Optional[str] = None
    archive_previous: bool = True


class EmployeeImportCommit(BaseModel):
    rows: List[Dict[str, Any]]


# ==========================================================================
# Rekrutmen V1 — Tahap A (kandidat, screening, riwayat status)
# company_id / stage_status / screening_* TIDAK diterima dari payload;
# semuanya ditentukan server dari konteks tenant dan state machine.
# ==========================================================================
class CandidateBase(BaseModel):
    # identitas
    nik: Optional[str] = None
    birth_place: Optional[str] = None
    birth_date: Optional[str] = None
    gender: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    city: Optional[str] = None
    # lamaran
    position_id: Optional[str] = None
    department_id: Optional[str] = None
    work_location_id: Optional[str] = None
    project_id: Optional[str] = None
    applied_position_title: Optional[str] = None
    source: Optional[str] = None
    source_detail: Optional[str] = None
    applied_at: Optional[str] = None
    expected_salary: Optional[float] = Field(default=None, ge=0)
    available_from: Optional[str] = None
    # pendidikan & pengalaman
    last_education: Optional[str] = None
    major: Optional[str] = None
    institution: Optional[str] = None
    graduation_year: Optional[int] = Field(default=None, ge=1950, le=2100)
    last_company: Optional[str] = None
    last_position: Optional[str] = None
    experience_years: Optional[float] = Field(default=None, ge=0, le=60)
    notes: Optional[str] = None


class CandidateCreate(CandidateBase):
    full_name: str = Field(min_length=2, max_length=255)
    candidate_number: Optional[str] = Field(default=None, max_length=64)


class CandidateUpdate(CandidateBase):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    candidate_number: Optional[str] = Field(default=None, max_length=64)


class CandidateStageChange(BaseModel):
    stage_status: str
    notes: Optional[str] = None


class CandidateScreening(BaseModel):
    screening_result: str  # passed | failed
    screening_score: Optional[int] = Field(default=None, ge=0, le=100)
    screening_notes: Optional[str] = None
    screening_recommendation: Optional[str] = None  # recommended | consider | not_recommended


# ==========================================================================
# Rekrutmen V1 — Tahap B (interview, approval, offering)
# ==========================================================================
class InterviewCreate(BaseModel):
    interview_type: str  # key dari katalog INTERVIEW_TYPES
    interview_type_label: Optional[str] = Field(default=None, max_length=255)  # untuk "other"
    scheduled_date: str  # YYYY-MM-DD
    start_time: Optional[str] = Field(default=None, max_length=8)  # HH:MM
    end_time: Optional[str] = Field(default=None, max_length=8)
    interviewer_user_id: str
    interview_mode: str = "onsite"  # onsite | online
    location: Optional[str] = Field(default=None, max_length=255)
    meeting_link: Optional[str] = Field(default=None, max_length=512)
    notes: Optional[str] = None


class InterviewUpdate(BaseModel):
    interview_type: Optional[str] = None
    interview_type_label: Optional[str] = Field(default=None, max_length=255)
    scheduled_date: Optional[str] = None
    start_time: Optional[str] = Field(default=None, max_length=8)
    end_time: Optional[str] = Field(default=None, max_length=8)
    interviewer_user_id: Optional[str] = None
    interview_mode: Optional[str] = None
    location: Optional[str] = Field(default=None, max_length=255)
    meeting_link: Optional[str] = Field(default=None, max_length=512)
    notes: Optional[str] = None


class InterviewComplete(BaseModel):
    result: str  # passed | considered | failed
    score: Optional[int] = Field(default=None, ge=0, le=100)
    recommendation: Optional[str] = None  # hire | consider | no_hire
    interviewer_notes: Optional[str] = None


class InterviewCancel(BaseModel):
    reason: Optional[str] = None


class ApprovalSubmit(BaseModel):
    notes: Optional[str] = None


class ApprovalDecide(BaseModel):
    decision: str  # approved | rejected
    notes: Optional[str] = None


class OfferingBase(BaseModel):
    position_id: Optional[str] = None
    department_id: Optional[str] = None
    work_location_id: Optional[str] = None
    project_id: Optional[str] = None
    employment_status_id: Optional[str] = None
    start_date: Optional[str] = None
    basic_salary: Optional[float] = Field(default=None, ge=0)
    allowances: Optional[List[Dict[str, Any]]] = None  # [{"name": str, "amount": float}]
    probation_months: Optional[int] = Field(default=None, ge=0, le=24)
    notes: Optional[str] = None


class OfferingCreate(OfferingBase):
    pass


class OfferingUpdate(OfferingBase):
    pass


class OfferingRespond(BaseModel):
    response: str  # accepted | declined
    response_notes: Optional[str] = None
    responded_at: Optional[str] = None  # YYYY-MM-DD (tanggal konfirmasi kandidat)


class OfferingCancel(BaseModel):
    reason: Optional[str] = None
