import {
  LayoutDashboard,
  Building2,
  Users,
  ShieldCheck,
  FileText,
  History,
  Settings,
  SlidersHorizontal,
  GitBranch,
  Boxes,
  MapPin,
  Network,
  Layers,
  BriefcaseBusiness,
  BadgeCheck,
  Wallet,
  FolderKanban,
  FileSignature,
  Award,
  UserPlus,
  Clock,
  CalendarDays,
  Target,
  Plane,
  Receipt,
  BookOpen,
  IdCard,
  CalendarClock,
  Banknote,
  Coins,
  Percent,
  MailCheck,
  Palette,
  Gauge,
  UserCheck,
} from "lucide-react";

/**
 * Navigation is gated twice: by permission AND by module activation.
 * The backend enforces the same rules - the UI only hides what is irrelevant.
 */
export const NAV_GROUPS = [
  {
    key: "platform",
    label: "Platform",
    items: [
      // Khusus Platform Admin (backend tetap menolak 403 untuk selain itu).
      { key: "platform-console", label: "Konsol Platform", to: "/platform", icon: Gauge, resource: null, platformOnly: true },
    ],
  },
  {
    key: "overview",
    label: "Ringkasan",
    items: [
      { key: "dashboard", label: "Dashboard", to: "/", icon: LayoutDashboard, resource: "dashboard", action: "view" },
      { key: "company", label: "Profil Perusahaan", to: "/company", icon: Building2, resource: "company", action: "view" },
    ],
  },
  {
    key: "organization",
    label: "Organisasi",
    items: [
      { key: "setup", label: "Pusat Setup", to: "/setup", icon: SlidersHorizontal, resource: "company", action: "view" },
      { key: "branches", label: "Cabang", to: "/setup/branches", icon: Network, resource: "branch", action: "view" },
      { key: "work-locations", label: "Lokasi Kerja", to: "/setup/work-locations", icon: MapPin, resource: "work_location", action: "view" },
      { key: "departments", label: "Departemen", to: "/setup/departments", icon: Layers, resource: "department", action: "view" },
      { key: "divisions", label: "Divisi", to: "/setup/divisions", icon: GitBranch, resource: "division", action: "view" },
      { key: "positions", label: "Jabatan", to: "/setup/positions", icon: BriefcaseBusiness, resource: "position", action: "view" },
      { key: "job-grades", label: "Grade / Level", to: "/setup/job-grades", icon: BadgeCheck, resource: "job_grade", action: "view" },
      { key: "cost-centers", label: "Cost Center", to: "/setup/cost-centers", icon: Wallet, resource: "cost_center", action: "view" },
      { key: "projects", label: "Proyek", to: "/setup/projects", icon: FolderKanban, resource: "project", action: "view" },
    ],
  },
  {
    key: "reference",
    label: "Data Referensi",
    items: [
      { key: "employment-statuses", label: "Status Kepegawaian", to: "/setup/employment-statuses", icon: IdCard, resource: "employment_status", action: "view" },
      { key: "employee-statuses", label: "Status Karyawan", to: "/setup/employee-statuses", icon: UserCheck, resource: "employee", action: "view" },
      { key: "contract-types", label: "Tipe Kontrak", to: "/setup/contract-types", icon: FileSignature, resource: "contract_type", action: "view" },
      { key: "certification-types", label: "Tipe Sertifikasi", to: "/setup/certification-types", icon: Award, resource: "certification_type", action: "view" },
      { key: "document-types", label: "Tipe Dokumen", to: "/setup/document-types", icon: FileText, resource: "document_type", action: "view" },
    ],
  },
  {
    key: "configuration",
    label: "Konfigurasi",
    items: [
      { key: "modules", label: "Aktivasi Modul", to: "/setup/modules", icon: Boxes, resource: "module", action: "view" },
      { key: "policies", label: "Kebijakan Perusahaan", to: "/setup/policies", icon: SlidersHorizontal, resource: "policy", action: "view" },
      { key: "approval-workflows", label: "Alur Persetujuan", to: "/setup/approval-workflows", icon: GitBranch, resource: "approval_workflow", action: "view" },
      { key: "settings", label: "Pengaturan Sistem", to: "/settings", icon: Settings, resource: "settings", action: "view" },
      { key: "mail-settings", label: "Email & Pengingat", to: "/settings/mail", icon: MailCheck, resource: "settings", action: "view" },
    ],
  },
  {
    key: "employee",
    label: "Kepegawaian",
    items: [
      { key: "employees", label: "Data Karyawan", to: "/employees", icon: Users, resource: "employee", action: "view", module: "employee_core" },
      { key: "reminders", label: "Kalender Masa Berlaku", to: "/reminders", icon: CalendarClock, resource: "document", action: "view" },
    ],
  },
  {
    key: "payroll",
    label: "Payroll & Pajak",
    items: [
      { key: "payroll-runs", label: "Payroll Bulanan", to: "/payroll/runs", icon: Wallet, resource: "payroll", action: "view", module: "payroll" },
      { key: "employee-salaries", label: "Struktur Gaji", to: "/payroll/salaries", icon: Banknote, resource: "employee_salary", action: "view", module: "payroll" },
      { key: "payroll-components", label: "Komponen Gaji", to: "/payroll/components", icon: Coins, resource: "payroll_component", action: "view", module: "payroll" },
      { key: "payroll-config", label: "BPJS & PPh 21", to: "/payroll/config", icon: Percent, resource: "payroll", action: "view", module: "payroll" },
      { key: "my-payslips", label: "Slip Gaji Saya", to: "/payroll/my-payslips", icon: Receipt, resource: null, module: "payroll" },
    ],
  },
  {
    key: "documents",
    label: "Dokumen",
    items: [
      { key: "documents", label: "Arsip Dokumen", to: "/documents", icon: FileText, resource: "document", action: "view" },
    ],
  },
  {
    key: "security",
    label: "Keamanan & Audit",
    items: [
      { key: "users", label: "Pengguna", to: "/users", icon: Users, resource: "user", action: "view" },
      { key: "roles", label: "Peran & Hak Akses", to: "/roles", icon: ShieldCheck, resource: "role", action: "view" },
      { key: "audit-logs", label: "Audit Log", to: "/audit-logs", icon: History, resource: "audit_log", action: "view" },
    ],
  },
  {
    key: "future",
    label: "Modul HR",
    items: [
      { key: "employee_core", label: "Data Karyawan", to: "/employees", icon: Users, resource: "employee", action: "view", module: "employee_core", hidden: true },
      { key: "recruitment", label: "Rekrutmen", to: "/modules/recruitment", icon: UserPlus, resource: "recruitment", action: "view", module: "recruitment" },
      { key: "attendance", label: "Absensi", to: "/modules/attendance", icon: Clock, resource: "attendance", action: "view", module: "attendance" },
      { key: "leave_overtime", label: "Cuti & Lembur", to: "/modules/leave_overtime", icon: CalendarDays, resource: "leave", action: "view", module: "leave_overtime" },
      { key: "performance", label: "Kinerja / KPI", to: "/modules/performance", icon: Target, resource: "performance", action: "view", module: "performance" },
      { key: "payroll", label: "Payroll", to: "/payroll/runs", icon: Wallet, resource: "payroll", action: "view", module: "payroll", hidden: true },
      { key: "mobilization", label: "Mobilisasi", to: "/modules/mobilization", icon: Plane, resource: "mobilization", action: "view", module: "mobilization" },
      { key: "finance_request", label: "Permintaan Keuangan", to: "/modules/finance_request", icon: Receipt, resource: "finance_request", action: "view", module: "finance_request" },
      { key: "accounting", label: "Akuntansi", to: "/modules/accounting", icon: BookOpen, resource: "accounting", action: "view", module: "accounting" },
    ],
  },
];

export const MODULE_INFO = {
  employee_core: {
    name: "Data Karyawan",
    icon: Users,
    summary: "Data induk karyawan, kontrak kerja, dan sertifikasi dalam satu tempat.",
    features: [
      "Data pribadi, keluarga, pendidikan, dan riwayat jabatan",
      "Kontrak kerja beserta pengingat masa berakhir",
      "Sertifikasi wajib dan masa berlakunya",
      "Dokumen karyawan (KTP, ijazah, medical) terhubung otomatis",
    ],
  },
  recruitment: {
    name: "Rekrutmen",
    icon: UserPlus,
    summary: "Kelola lowongan, pelamar, dan tahapan seleksi sampai penawaran kerja.",
    features: [
      "Permintaan tenaga kerja (manpower request) dengan persetujuan",
      "Database pelamar beserta CV",
      "Tahapan seleksi, interview, dan hasil",
      "Konversi pelamar menjadi karyawan tanpa input ulang",
    ],
  },
  attendance: {
    name: "Absensi",
    icon: Clock,
    summary: "Kehadiran harian dengan pendekatan berbasis pengecualian.",
    features: [
      "Shift, jadwal kerja, dan hari libur",
      "Face attendance dan integrasi fingerprint",
      "Hanya pengecualian yang perlu ditindak (terlambat, tidak absen)",
      "Rekap otomatis sebagai dasar payroll",
    ],
  },
  leave_overtime: {
    name: "Cuti & Lembur",
    icon: CalendarDays,
    summary: "Pengajuan cuti dan lembur yang mengikuti kebijakan tiap unit.",
    features: [
      "Kuota cuti mengikuti kebijakan perusahaan/cabang/proyek",
      "Pengajuan dari ponsel oleh karyawan",
      "Persetujuan berjenjang sesuai alur yang Anda atur",
      "Saldo cuti terhitung otomatis",
    ],
  },
  performance: {
    name: "Kinerja / KPI",
    icon: Target,
    summary: "Siklus penilaian kinerja dan KPI yang terukur.",
    features: [
      "Template KPI per jabatan",
      "Periode penilaian dan kalibrasi",
      "Penilaian mandiri dan penilaian atasan",
      "Rekap hasil untuk keputusan promosi",
    ],
  },
  payroll: {
    name: "Payroll",
    icon: Wallet,
    summary: "Penggajian lengkap dengan BPJS dan PPh 21 Indonesia.",
    features: [
      "Komponen gaji, tunjangan, dan potongan",
      "Perhitungan BPJS Kesehatan & Ketenagakerjaan",
      "PPh 21 sesuai peraturan terbaru",
      "Slip gaji dan bank transfer file",
    ],
  },
  mobilization: {
    name: "Mobilisasi",
    icon: Plane,
    summary: "Penempatan proyek, mobilisasi, dan demobilisasi karyawan.",
    features: [
      "Penempatan karyawan ke proyek dan lokasi kerja",
      "Jadwal mobilisasi, tiket, dan akomodasi",
      "Validasi kontrak & sertifikasi sebelum diberangkatkan",
      "Proses demobilisasi dan pengembalian aset",
    ],
  },
  finance_request: {
    name: "Permintaan Keuangan",
    icon: Receipt,
    summary: "Kasbon, reimbursement, dan permintaan dana dengan persetujuan.",
    features: [
      "Pengajuan kasbon dan cash advance karyawan",
      "Reimbursement dengan lampiran kwitansi",
      "Persetujuan berjenjang sampai Finance",
      "Pemotongan otomatis pada payroll",
    ],
  },
  accounting: {
    name: "Akuntansi",
    icon: BookOpen,
    summary: "Modul akuntansi opsional untuk pencatatan jurnal.",
    features: [
      "Chart of account dan jurnal umum",
      "Posting otomatis dari payroll dan permintaan dana",
      "Laporan dasar keuangan",
      "Integrasi cost center dan proyek",
    ],
  },
};

/** Sidebar khusus Platform Admin (mode platform: /platform/*). */
export const PLATFORM_NAV = [
  {
    key: "platform-main",
    label: "Konsol Platform",
    items: [
      { key: "platform-dashboard", label: "Platform Dashboard", to: "/platform", icon: Gauge, end: true },
      { key: "platform-tenants", label: "Tenant Registry", to: "/platform/tenants", icon: Building2 },
    ],
  },
  {
    key: "platform-settings",
    label: "Pengaturan Platform",
    items: [{ key: "platform-branding", label: "Branding Platform", to: "/platform/branding", icon: Palette }],
  },
];

export const filterNav = ({ can, hasModule, isPlatformAdmin = false }) =>
  NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter(
      (item) =>
        !item.hidden &&
        (!item.platformOnly || isPlatformAdmin) &&
        (!item.resource || can(item.resource, item.action || "view")) &&
        hasModule(item.module)
    ),
  })).filter((group) => group.items.length > 0);
