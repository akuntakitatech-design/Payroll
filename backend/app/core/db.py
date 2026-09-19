"""MongoDB access layer, designed relationally so it can be ported to PostgreSQL/Supabase.

Conventions enforced across every collection:
  - `id`           : UUID4 string primary key (never Mongo's ObjectId)
  - `company_id`   : tenant foreign key on every tenant-owned record
  - `created_at` / `updated_at` : ISO datetimes (UTC)
  - `created_by` / `updated_by` : user_id foreign keys
  - `status`       : active | inactive | archived  (soft delete preferred)
All reads project out `_id` so responses stay JSON-serializable.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, TEXT

from .config import settings

_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None

NO_ID = {"_id": 0}

# --------------------------------------------------------------------------
# Collection catalogue ("tables")
# --------------------------------------------------------------------------
GLOBAL_COLLECTIONS = [
    "companies",
    "users",
    "roles",
    "permissions",
    "modules",
    "user_company_roles",
    "role_permissions",
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
]

ALL_COLLECTIONS = GLOBAL_COLLECTIONS + TENANT_COLLECTIONS


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.MONGO_URL, uuidRepresentation="standard")
    return _client


def get_db() -> AsyncIOMotorDatabase:
    global _db
    if _db is None:
        _db = get_client()[settings.DB_NAME]
    return _db


async def close_db() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client, _db = None, None


async def ensure_indexes() -> None:
    """Create foreign-key style indexes. Mirrors what PK/FK/UNIQUE would be in SQL."""
    db = get_db()

    await db.users.create_index([("email", ASCENDING)], unique=True, name="uq_users_email")
    await db.users.create_index([("id", ASCENDING)], unique=True, name="pk_users")
    await db.companies.create_index([("id", ASCENDING)], unique=True, name="pk_companies")
    await db.companies.create_index([("code", ASCENDING)], unique=True, name="uq_companies_code")
    await db.roles.create_index([("key", ASCENDING)], unique=True, name="uq_roles_key")
    await db.permissions.create_index([("key", ASCENDING)], unique=True, name="uq_permissions_key")
    await db.modules.create_index([("key", ASCENDING)], unique=True, name="uq_modules_key")
    await db.role_permissions.create_index(
        [("role_key", ASCENDING), ("permission_key", ASCENDING)],
        unique=True,
        name="uq_role_permission",
    )
    await db.user_company_roles.create_index(
        [("user_id", ASCENDING), ("company_id", ASCENDING), ("role_key", ASCENDING)],
        unique=True,
        name="uq_user_company_role",
    )
    await db.user_company_roles.create_index([("company_id", ASCENDING)], name="ix_ucr_company")

    for coll in TENANT_COLLECTIONS:
        await db[coll].create_index(
            [("company_id", ASCENDING), ("id", ASCENDING)], unique=True, name="pk_tenant"
        )
        await db[coll].create_index(
            [("company_id", ASCENDING), ("status", ASCENDING)], name="ix_company_status"
        )

    await db.company_modules.create_index(
        [("company_id", ASCENDING), ("module_key", ASCENDING)],
        unique=True,
        name="uq_company_module",
    )
    await db.company_settings.create_index(
        [("company_id", ASCENDING)], unique=True, name="uq_company_settings"
    )
    await db.audit_logs.create_index(
        [("company_id", ASCENDING), ("created_at", DESCENDING)], name="ix_audit_recent"
    )
    await db.audit_logs.create_index(
        [("company_id", ASCENDING), ("module", ASCENDING), ("action", ASCENDING)],
        name="ix_audit_module_action",
    )
    await db.config_overrides.create_index(
        [("company_id", ASCENDING), ("config_key", ASCENDING), ("scope_type", ASCENDING)],
        name="ix_config_lookup",
    )
    await db.approval_steps.create_index(
        [("company_id", ASCENDING), ("workflow_id", ASCENDING), ("step_order", ASCENDING)],
        name="ix_steps_workflow",
    )
    await db.documents.create_index(
        [("company_id", ASCENDING), ("owner_type", ASCENDING), ("owner_id", ASCENDING)],
        name="ix_documents_owner",
    )
    await db.employees.create_index(
        [("company_id", ASCENDING), ("employee_number", ASCENDING)], name="ix_employee_number"
    )
    await db.employees.create_index(
        [("company_id", ASCENDING), ("full_name", ASCENDING)], name="ix_employee_name"
    )
    await db.employees.create_index(
        [("company_id", ASCENDING), ("department_id", ASCENDING)], name="ix_employee_department"
    )
    await db.employee_contracts.create_index(
        [("company_id", ASCENDING), ("employee_id", ASCENDING), ("start_date", DESCENDING)],
        name="ix_contract_employee",
    )
    await db.employee_contracts.create_index(
        [("company_id", ASCENDING), ("end_date", ASCENDING)], name="ix_contract_expiry"
    )
    await db.employee_certifications.create_index(
        [("company_id", ASCENDING), ("employee_id", ASCENDING)], name="ix_cert_employee"
    )
    await db.employee_certifications.create_index(
        [("company_id", ASCENDING), ("expiry_date", ASCENDING)], name="ix_cert_expiry"
    )

    # ---- payroll ----
    await db.payroll_runs.create_index(
        [("company_id", ASCENDING), ("year", DESCENDING), ("month", DESCENDING)],
        name="ix_payroll_period",
    )
    await db.payroll_items.create_index(
        [("company_id", ASCENDING), ("run_id", ASCENDING), ("employee_id", ASCENDING)],
        name="ix_payroll_item_run",
    )
    await db.payroll_items.create_index(
        [("company_id", ASCENDING), ("employee_id", ASCENDING)], name="ix_payroll_item_employee"
    )
    await db.employee_salaries.create_index(
        [("company_id", ASCENDING), ("employee_id", ASCENDING)],
        unique=True,
        name="uq_employee_salary",
    )
    await db.employee_salary_history.create_index(
        [("company_id", ASCENDING), ("employee_id", ASCENDING), ("created_at", DESCENDING)],
        name="ix_salary_history",
    )
    await db.payroll_components.create_index(
        [("company_id", ASCENDING), ("code", ASCENDING)], name="ix_payroll_component_code"
    )
    await db.smtp_settings.create_index(
        [("company_id", ASCENDING)], unique=True, name="uq_smtp_company"
    )
    await db.reminder_settings.create_index(
        [("company_id", ASCENDING)], unique=True, name="uq_reminder_company"
    )
    await db.reminder_logs.create_index(
        [("company_id", ASCENDING), ("created_at", DESCENDING)], name="ix_reminder_log_recent"
    )


def serialize(doc):
    """Make a Mongo document JSON-safe: drop ObjectId `_id`, keep everything else."""
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
