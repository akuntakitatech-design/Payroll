"""Role Based Access Control catalogue.

Permission key format: "<resource>:<action>".
Actions: view | create | edit | delete | approve | export | config
Nothing is hard-coded per company: role_permissions rows live in the database and
can be edited from the UI. This module only provides the *initial* catalogue used
by the seeder.
"""
from typing import Dict, List

ACTIONS = ["view", "create", "edit", "delete", "approve", "export", "config", "view_own"]

ACTION_LABELS = {
    "view": "Lihat",
    "create": "Tambah",
    "edit": "Ubah",
    "delete": "Hapus",
    "approve": "Setujui",
    "export": "Ekspor",
    "config": "Konfigurasi",
    "view_own": "Lihat Milik Sendiri",
}

# resource_key -> (label_id, module_key, [allowed actions])
RESOURCES: Dict[str, tuple] = {
    "dashboard": ("Dashboard", "hr_core", ["view"]),
    "company": ("Perusahaan", "hr_core", ["view", "create", "edit", "delete", "config", "export"]),
    "branch": ("Cabang", "hr_core", ["view", "create", "edit", "delete", "export"]),
    "work_location": ("Lokasi Kerja", "hr_core", ["view", "create", "edit", "delete", "export"]),
    "department": ("Departemen", "hr_core", ["view", "create", "edit", "delete", "export"]),
    "division": ("Divisi", "hr_core", ["view", "create", "edit", "delete", "export"]),
    "position": ("Jabatan", "hr_core", ["view", "create", "edit", "delete", "export"]),
    "job_grade": ("Grade / Level", "hr_core", ["view", "create", "edit", "delete", "export"]),
    "cost_center": ("Cost Center", "hr_core", ["view", "create", "edit", "delete", "export"]),
    "project": ("Proyek", "hr_core", ["view", "create", "edit", "delete", "export"]),
    "employment_status": ("Status Kepegawaian", "hr_core", ["view", "create", "edit", "delete"]),
    "contract_type": ("Tipe Kontrak", "hr_core", ["view", "create", "edit", "delete"]),
    "certification_type": ("Tipe Sertifikasi", "hr_core", ["view", "create", "edit", "delete"]),
    "document_type": ("Tipe Dokumen", "hr_core", ["view", "create", "edit", "delete"]),
    "document": ("Dokumen", "hr_core", ["view", "create", "edit", "delete", "export"]),
    "user": ("Pengguna", "hr_core", ["view", "create", "edit", "delete", "export"]),
    "role": ("Peran & Hak Akses", "hr_core", ["view", "create", "edit", "delete", "config"]),
    "module": ("Aktivasi Modul", "hr_core", ["view", "config"]),
    "approval_workflow": ("Alur Persetujuan", "hr_core", ["view", "create", "edit", "delete", "config"]),
    "policy": ("Kebijakan Perusahaan", "hr_core", ["view", "create", "edit", "delete", "config"]),
    "audit_log": ("Audit Log", "hr_core", ["view", "export"]),
    "settings": ("Pengaturan Sistem", "hr_core", ["view", "config"]),
    # Future modules - permissions prepared, business logic intentionally not built yet
    "employee": ("Data Karyawan", "employee_core", ["view", "create", "edit", "delete", "export"]),
    "certification": ("Sertifikasi Karyawan", "employee_core", ["view", "create", "edit", "delete", "export"]),
    "recruitment": ("Rekrutmen", "recruitment", ["view", "create", "edit", "delete", "approve", "export"]),
    "contract": ("Kontrak Kerja", "employee_core", ["view", "create", "edit", "delete", "approve"]),
    "attendance": ("Absensi", "attendance", ["view", "create", "edit", "delete", "approve", "export"]),
    "leave": ("Cuti & Lembur", "leave_overtime", ["view", "create", "edit", "delete", "approve", "export"]),
    "performance": ("KPI & Kinerja", "performance", ["view", "create", "edit", "delete", "approve"]),
    "payroll": ("Payroll", "payroll", ["view", "create", "edit", "delete", "approve", "export", "config"]),
    "payroll_component": ("Komponen Gaji", "payroll", ["view", "create", "edit", "delete"]),
    "employee_salary": ("Struktur Gaji Karyawan", "payroll", ["view", "create", "edit", "delete", "export"]),
    "payslip": ("Slip Gaji Saya", "payroll", ["view_own"]),
    "mobilization": ("Mobilisasi", "mobilization", ["view", "create", "edit", "delete", "approve"]),
    "finance_request": ("Permintaan Keuangan", "finance_request", ["view", "create", "edit", "delete", "approve", "export"]),
    "accounting": ("Akuntansi", "accounting", ["view", "create", "edit", "delete", "export"]),
}

MODULES: List[dict] = [
    {"key": "hr_core", "name": "HR Core", "description": "Struktur organisasi, master data, pengguna, audit.", "is_core": True, "icon": "Building2", "sort_order": 1, "status": "available"},
    {"key": "employee_core", "name": "Data Karyawan", "description": "Data induk karyawan, kontrak, sertifikasi.", "is_core": False, "icon": "Users", "sort_order": 2, "status": "available"},
    {"key": "recruitment", "name": "Rekrutmen", "description": "Lowongan, pelamar, tahapan seleksi.", "is_core": False, "icon": "UserPlus", "sort_order": 3, "status": "planned"},
    {"key": "attendance", "name": "Absensi", "description": "Shift, jadwal kerja, absensi GPS, koreksi, rekap, dan persetujuan.", "is_core": False, "icon": "Clock", "sort_order": 4, "status": "available"},
    {"key": "leave_overtime", "name": "Cuti & Lembur", "description": "Pengajuan cuti, izin, sakit, dan lembur dengan saldo berbasis buku besar.", "is_core": False, "icon": "CalendarDays", "sort_order": 5, "status": "available"},
    {"key": "performance", "name": "Kinerja / KPI", "description": "Penilaian kinerja dan KPI.", "is_core": False, "icon": "Target", "sort_order": 6, "status": "planned"},
    {"key": "payroll", "name": "Payroll", "description": "Penggajian bulanan, BPJS, PPh 21 metode TER.", "is_core": False, "icon": "Wallet", "sort_order": 7, "status": "available"},
    {"key": "mobilization", "name": "Mobilisasi", "description": "Penempatan proyek, mobilisasi & demobilisasi.", "is_core": False, "icon": "Plane", "sort_order": 8, "status": "planned"},
    {"key": "finance_request", "name": "Permintaan Keuangan", "description": "Kasbon, reimbursement, permintaan dana.", "is_core": False, "icon": "Receipt", "sort_order": 9, "status": "planned"},
    {"key": "accounting", "name": "Akuntansi", "description": "Modul akuntansi opsional.", "is_core": False, "icon": "BookOpen", "sort_order": 10, "status": "planned"},
]

ROLES: List[dict] = [
    {"key": "super_admin", "name": "Super Admin", "description": "Akses penuh seluruh sistem dan semua perusahaan.", "is_system": True, "scope": "global", "sort_order": 1},
    {"key": "company_owner", "name": "Pemilik Perusahaan", "description": "Akses penuh dalam satu perusahaan.", "is_system": True, "scope": "company", "sort_order": 2},
    {"key": "hr_admin", "name": "HR Admin", "description": "Mengelola master data, karyawan dan dokumen.", "is_system": True, "scope": "company", "sort_order": 3},
    {"key": "hr_manager", "name": "HR Manager", "description": "Menyetujui proses HR dan mengatur kebijakan.", "is_system": True, "scope": "company", "sort_order": 4},
    {"key": "finance", "name": "Finance", "description": "Payroll, permintaan keuangan dan ekspor data.", "is_system": True, "scope": "company", "sort_order": 5},
    {"key": "manager", "name": "Manager", "description": "Menyetujui pengajuan tim dan melihat data unit.", "is_system": True, "scope": "company", "sort_order": 6},
    {"key": "supervisor", "name": "Supervisor", "description": "Persetujuan tingkat pertama untuk tim.", "is_system": True, "scope": "company", "sort_order": 7},
    {"key": "employee", "name": "Karyawan", "description": "Akses self-service karyawan.", "is_system": True, "scope": "company", "sort_order": 8},
]

WILDCARD = "*:*"

MASTER_RESOURCES = [
    "branch", "work_location", "department", "division", "position", "job_grade",
    "cost_center", "project", "employment_status", "contract_type",
    "certification_type", "document_type",
]


def all_permission_keys() -> List[str]:
    keys = []
    for res, (_label, _mod, actions) in RESOURCES.items():
        for act in actions:
            keys.append(f"{res}:{act}")
    return keys


def _crud(resources, actions) -> List[str]:
    out = []
    for r in resources:
        allowed = RESOURCES[r][2]
        for a in actions:
            if a in allowed:
                out.append(f"{r}:{a}")
    return out


def default_role_permissions() -> Dict[str, List[str]]:
    """Initial (editable) permission matrix per role."""
    full_crud = ["view", "create", "edit", "delete", "export"]

    hr_admin = (
        ["dashboard:view", "company:view"]
        + _crud(MASTER_RESOURCES, full_crud)
        + _crud(["document", "employee", "contract", "certification", "recruitment"], full_crud)
        + ["user:view", "user:create", "user:edit", "audit_log:view", "settings:view",
           "approval_workflow:view", "policy:view", "module:view",
           "attendance:view", "leave:view", "mobilization:view", "performance:view",
           # Time Management V1 — HR Admin mengelola shift, jadwal, absensi, cuti & lembur
           "attendance:create", "attendance:edit", "attendance:delete", "attendance:export",
           "leave:create", "leave:edit", "leave:delete", "leave:export",
           "payroll:view", "payroll:create", "payroll:edit", "payroll:export",
           "payroll_component:view", "payroll_component:create", "payroll_component:edit",
           "payroll_component:delete",
           "employee_salary:view", "employee_salary:create", "employee_salary:edit",
           "employee_salary:export", "payslip:view_own"]
    )

    hr_manager = hr_admin + [
        "approval_workflow:create", "approval_workflow:edit", "approval_workflow:delete",
        "approval_workflow:config", "policy:create", "policy:edit", "policy:delete",
        "policy:config", "audit_log:export", "settings:config", "company:edit",
        "leave:approve", "attendance:approve", "contract:approve", "recruitment:approve",
        "mobilization:approve", "performance:approve", "role:view",
        "payroll:approve", "payroll:config", "payroll:delete",
    ]

    finance = [
        "dashboard:view", "company:view", "cost_center:view", "project:view",
        "department:view", "division:view", "position:view", "job_grade:view",
        "branch:view", "work_location:view", "employee:view", "document:view",
        "certification:view",
        "payroll:view", "payroll:create", "payroll:edit", "payroll:approve",
        "payroll:export", "payroll:config",
        "finance_request:view", "finance_request:approve", "finance_request:export",
        "accounting:view", "accounting:export", "audit_log:view",
        "payroll:delete", "payroll_component:view", "payroll_component:create",
        "payroll_component:edit", "payroll_component:delete",
        "employee_salary:view", "employee_salary:create", "employee_salary:edit",
        "employee_salary:export", "payslip:view_own",
    ]

    manager = [
        "dashboard:view", "company:view", "employee:view", "department:view",
        "division:view", "position:view", "project:view", "document:view",
        "certification:view", "contract:view",
        "leave:view", "leave:approve", "attendance:view", "attendance:approve",
        "attendance:create", "leave:create",
        "performance:view", "performance:approve", "mobilization:view",
        "mobilization:approve", "finance_request:view", "finance_request:approve",
        "attendance:export", "leave:export",
        "payslip:view_own",
    ]

    supervisor = [
        "dashboard:view", "employee:view", "leave:view", "leave:approve",
        "attendance:view", "attendance:approve", "performance:view",
        # Time Management V1 — supervisor juga karyawan (absen & ajukan sendiri)
        "attendance:create", "leave:create",
        "mobilization:view", "document:view", "project:view", "certification:view",
        "payslip:view_own",
    ]

    employee = [
        "dashboard:view", "document:view", "document:create",
        "leave:view", "leave:create", "attendance:view",
        # Time Management V1 — absen masuk/pulang & pengajuan koreksi absensi sendiri
        "attendance:create",
        "finance_request:view", "finance_request:create", "performance:view",
        "payslip:view_own",
    ]

    return {
        "super_admin": [WILDCARD],
        "company_owner": [WILDCARD],
        "hr_admin": sorted(set(hr_admin)),
        "hr_manager": sorted(set(hr_manager)),
        "finance": sorted(set(finance)),
        "manager": sorted(set(manager)),
        "supervisor": sorted(set(supervisor)),
        "employee": sorted(set(employee)),
    }


def resource_module(resource: str) -> str:
    entry = RESOURCES.get(resource)
    return entry[1] if entry else "hr_core"
