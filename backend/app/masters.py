"""Master data registry.

One declarative table drives every master-data CRUD endpoint: fields, required
fields, uniqueness, search, relations and safe-delete reference checks.
This keeps behaviour consistent across all 12 master screens.
"""
from typing import Any, Dict, List

MASTERS: Dict[str, Dict[str, Any]] = {
    "branches": {
        "resource": "branch",
        "collection": "branches",
        "label": "Cabang",
        "fields": ["code", "name", "address", "city", "province", "postal_code", "phone", "email", "is_head_office", "notes"],
        "required": ["code", "name"],
        "unique": ["code"],
        "search": ["code", "name", "city"],
        "refs": [
            ("work_locations", "branch_id", "Lokasi Kerja"),
            ("departments", "branch_id", "Departemen"),
            ("projects", "branch_id", "Proyek"),
        ],
    },
    "work-locations": {
        "resource": "work_location",
        "collection": "work_locations",
        "label": "Lokasi Kerja",
        "fields": ["code", "name", "branch_id", "address", "latitude", "longitude", "radius_meter", "location_type", "timezone", "notes"],
        "required": ["code", "name"],
        "unique": ["code"],
        "search": ["code", "name", "address"],
        "relations": {"branch_id": "branches"},
        "refs": [("projects", "work_location_id", "Proyek")],
    },
    "departments": {
        "resource": "department",
        "collection": "departments",
        "label": "Departemen",
        "fields": ["code", "name", "branch_id", "parent_id", "cost_center_id", "head_user_id", "description"],
        "required": ["code", "name"],
        "unique": ["code"],
        "search": ["code", "name"],
        "relations": {"branch_id": "branches", "cost_center_id": "cost_centers", "parent_id": "departments"},
        "refs": [("divisions", "department_id", "Divisi"), ("positions", "department_id", "Jabatan")],
    },
    "divisions": {
        "resource": "division",
        "collection": "divisions",
        "label": "Divisi",
        "fields": ["code", "name", "department_id", "head_user_id", "description"],
        "required": ["code", "name"],
        "unique": ["code"],
        "search": ["code", "name"],
        "relations": {"department_id": "departments"},
        "refs": [("positions", "division_id", "Jabatan")],
    },
    "positions": {
        "resource": "position",
        "collection": "positions",
        "label": "Jabatan",
        "fields": ["code", "name", "department_id", "division_id", "job_grade_id", "reports_to_position_id", "is_supervisory", "description"],
        "required": ["code", "name"],
        "unique": ["code"],
        "search": ["code", "name"],
        "relations": {
            "department_id": "departments",
            "division_id": "divisions",
            "job_grade_id": "job_grades",
            "reports_to_position_id": "positions",
        },
        "refs": [],
    },
    "job-grades": {
        "resource": "job_grade",
        "collection": "job_grades",
        "label": "Grade / Level",
        "fields": ["code", "name", "level", "min_salary", "max_salary", "description"],
        "required": ["code", "name"],
        "unique": ["code"],
        "search": ["code", "name"],
        "refs": [("positions", "job_grade_id", "Jabatan")],
    },
    "cost-centers": {
        "resource": "cost_center",
        "collection": "cost_centers",
        "label": "Cost Center",
        "fields": ["code", "name", "branch_id", "budget_owner_user_id", "description"],
        "required": ["code", "name"],
        "unique": ["code"],
        "search": ["code", "name"],
        "relations": {"branch_id": "branches"},
        "refs": [("projects", "cost_center_id", "Proyek"), ("departments", "cost_center_id", "Departemen")],
    },
    "projects": {
        "resource": "project",
        "collection": "projects",
        "label": "Proyek",
        "fields": ["code", "name", "client_name", "branch_id", "work_location_id", "cost_center_id", "start_date", "end_date", "contract_value", "project_manager_user_id", "description"],
        "required": ["code", "name"],
        "unique": ["code"],
        "search": ["code", "name", "client_name"],
        "relations": {
            "branch_id": "branches",
            "work_location_id": "work_locations",
            "cost_center_id": "cost_centers",
        },
        "refs": [],
    },
    "employment-statuses": {
        "resource": "employment_status",
        "collection": "employment_statuses",
        "label": "Status Kepegawaian",
        "fields": ["code", "name", "is_permanent", "requires_contract", "description"],
        "required": ["code", "name"],
        "unique": ["code"],
        "search": ["code", "name"],
        "refs": [],
    },
    "contract-types": {
        "resource": "contract_type",
        "collection": "contract_types",
        "label": "Tipe Kontrak",
        "fields": ["code", "name", "duration_months", "is_extendable", "max_extension", "description"],
        "required": ["code", "name"],
        "unique": ["code"],
        "search": ["code", "name"],
        "refs": [],
    },
    "certification-types": {
        "resource": "certification_type",
        "collection": "certification_types",
        "label": "Tipe Sertifikasi",
        "fields": ["code", "name", "issuing_body", "validity_months", "is_mandatory", "reminder_days", "description"],
        "required": ["code", "name"],
        "unique": ["code"],
        "search": ["code", "name", "issuing_body"],
        "refs": [],
    },
    "document-types": {
        "resource": "document_type",
        "collection": "document_types",
        "label": "Tipe Dokumen",
        "fields": ["code", "name", "category", "owner_scope", "is_mandatory", "has_expiry", "reminder_days", "allowed_extensions", "max_size_mb", "description"],
        "required": ["code", "name"],
        "unique": ["code"],
        "search": ["code", "name", "category"],
        "refs": [("documents", "document_type_id", "Dokumen")],
    },
}

MASTER_ORDER: List[str] = list(MASTERS.keys())

NUMERIC_FIELDS = {
    "latitude", "longitude", "radius_meter", "level", "min_salary", "max_salary",
    "duration_months", "max_extension", "validity_months", "reminder_days",
    "contract_value", "max_size_mb",
}
BOOLEAN_FIELDS = {
    "is_head_office", "is_supervisory", "is_permanent", "requires_contract",
    "is_extendable", "is_mandatory", "has_expiry",
}
