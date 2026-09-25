import React from "react";
import "@/App.css";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/lib/auth";
import { BrandingProvider } from "@/lib/branding";
import AppShell from "@/components/layout/AppShell";
import LoginPage from "@/pages/LoginPage";
import ChangePasswordRequiredPage from "@/pages/ChangePasswordRequiredPage";
import DashboardPage from "@/pages/DashboardPage";
import CompanyProfilePage from "@/pages/CompanyProfilePage";
import SetupHubPage from "@/pages/SetupHubPage";
import MasterDataPage from "@/pages/MasterDataPage";
import EmployeeStatusMasterPage from "@/pages/EmployeeStatusMasterPage";
import ModuleActivationPage from "@/pages/ModuleActivationPage";
import PoliciesPage from "@/pages/PoliciesPage";
import ApprovalWorkflowPage from "@/pages/ApprovalWorkflowPage";
import UsersPage from "@/pages/UsersPage";
import TenantsPage from "@/pages/platform/TenantsPage";
import PlatformDashboardPage from "@/pages/platform/PlatformDashboardPage";
import TenantDetailPage from "@/pages/platform/TenantDetailPage";
import PlatformBrandingPage from "@/pages/platform/PlatformBrandingPage";
import EmptyState from "@/components/common/EmptyState";
import RolesPage from "@/pages/RolesPage";
import DocumentsPage from "@/pages/DocumentsPage";
import EmployeesPage from "@/pages/EmployeesPage";
import EmployeeDetailPage from "@/pages/EmployeeDetailPage";
import ExpiryCalendarPage from "@/pages/ExpiryCalendarPage";
import AuditLogPage from "@/pages/AuditLogPage";
import SettingsPage from "@/pages/SettingsPage";
import ProfilePage from "@/pages/ProfilePage";
import EmployeeImportPage from "@/pages/EmployeeImportPage";
import EmployeeMigrationPage from "@/pages/EmployeeMigrationPage";
import PayrollRunsPage from "@/pages/PayrollRunsPage";
import PayrollRunDetailPage from "@/pages/PayrollRunDetailPage";
import PayrollComponentsPage from "@/pages/PayrollComponentsPage";
import PayrollConfigPage from "@/pages/PayrollConfigPage";
import EmployeeSalariesPage from "@/pages/EmployeeSalariesPage";
import MyPayslipsPage from "@/pages/MyPayslipsPage";
import MailSettingsPage from "@/pages/MailSettingsPage";
import ModulePlaceholderPage from "@/pages/ModulePlaceholderPage";
import RecruitmentDashboardPage from "@/pages/recruitment/RecruitmentDashboardPage";
import CandidatesPage from "@/pages/recruitment/CandidatesPage";
import CandidateDetailPage from "@/pages/recruitment/CandidateDetailPage";
// Time Management V1 — Absensi
import AttendanceModuleLayout from "@/pages/attendance/AttendanceModuleLayout";
import AttendanceOverviewPage from "@/pages/attendance/AttendanceOverviewPage";
import MyAttendancePage from "@/pages/attendance/MyAttendancePage";
import AttendanceListPage from "@/pages/attendance/AttendanceListPage";
import SchedulesPage from "@/pages/attendance/SchedulesPage";
import AttendanceRecapPage from "@/pages/attendance/AttendanceRecapPage";
import AttendanceApprovalsPage from "@/pages/attendance/AttendanceApprovalsPage";
import TimeImportPage from "@/pages/attendance/TimeImportPage";
import TimeSettingsPage from "@/pages/attendance/TimeSettingsPage";
// Time Management V1 — Cuti & Lembur
import LeaveOvertimeModuleLayout from "@/pages/leave/LeaveOvertimeModuleLayout";
import LeaveOvertimeOverviewPage from "@/pages/leave/LeaveOvertimeOverviewPage";
import LeaveRequestsPage from "@/pages/leave/LeaveRequestsPage";
import OvertimePage from "@/pages/leave/OvertimePage";
import LeaveBalancesPage from "@/pages/leave/LeaveBalancesPage";
import LeaveOvertimeApprovalsPage from "@/pages/leave/LeaveOvertimeApprovalsPage";
import NotFoundPage from "@/pages/NotFoundPage";
import { Loader2, ShieldAlert } from "lucide-react";

const FullPageLoader = () => (
  <div className="flex min-h-screen items-center justify-center bg-background">
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      <Loader2 className="h-5 w-5 animate-spin" /> Memuat aplikasi…
    </div>
  </div>
);

const ProtectedRoute = ({ children }) => {
  const { session, loading } = useAuth();
  const location = useLocation();
  if (loading) return <FullPageLoader />;
  if (!session) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  // Password sementara: wajib ganti password sebelum menggunakan aplikasi (backend juga menolak 403).
  if (session.user?.must_change_password) return <Navigate to="/change-password" replace />;
  return children;
};

/** Halaman /platform/* hanya untuk Platform Admin (backend juga menolak 403). */
const PlatformRoute = ({ children }) => {
  const { isSuperAdmin } = useAuth();
  if (!isSuperAdmin) {
    return (
      <div className="px-4 py-10 sm:px-6" data-testid="platform-forbidden">
        <EmptyState
          icon={ShieldAlert}
          title="Khusus Platform Admin"
          description="Halaman ini hanya dapat diakses oleh Platform Admin. Anda tetap dapat menggunakan dashboard tenant Anda."
        />
      </div>
    );
  }
  return children;
};

const MASTER_ROUTES = [
  "branches",
  "work-locations",
  "departments",
  "divisions",
  "positions",
  "job-grades",
  "cost-centers",
  "projects",
  "employment-statuses",
  "contract-types",
  "certification-types",
  "document-types",
];

const AppRoutes = () => (
  <Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route path="/change-password" element={<ChangePasswordRequiredPage />} />
    <Route
      element={
        <ProtectedRoute>
          <AppShell />
        </ProtectedRoute>
      }
    >
      <Route path="/" element={<DashboardPage />} />
      <Route path="/company" element={<CompanyProfilePage />} />
      <Route path="/setup" element={<SetupHubPage />} />
      {MASTER_ROUTES.map((path) => (
        <Route key={path} path={`/setup/${path}`} element={<MasterDataPage resourcePath={path} />} />
      ))}
      <Route path="/setup/employee-statuses" element={<EmployeeStatusMasterPage />} />
      <Route path="/setup/modules" element={<ModuleActivationPage />} />
      <Route path="/setup/policies" element={<PoliciesPage />} />
      <Route path="/setup/approval-workflows" element={<ApprovalWorkflowPage />} />
      <Route path="/platform" element={<PlatformRoute><PlatformDashboardPage /></PlatformRoute>} />
      <Route path="/platform/tenants" element={<PlatformRoute><TenantsPage /></PlatformRoute>} />
      <Route path="/platform/tenants/:tenantId" element={<PlatformRoute><TenantDetailPage /></PlatformRoute>} />
      <Route path="/platform/branding" element={<PlatformRoute><PlatformBrandingPage /></PlatformRoute>} />
      <Route path="/users" element={<UsersPage />} />
      <Route path="/roles" element={<RolesPage />} />
      <Route path="/documents" element={<DocumentsPage />} />
      <Route path="/employees" element={<EmployeesPage />} />
      <Route path="/employees/import" element={<EmployeeImportPage />} />
      <Route path="/employees/migration" element={<EmployeeMigrationPage />} />
      <Route path="/employees/:employeeId" element={<EmployeeDetailPage />} />
      <Route path="/payroll/runs" element={<PayrollRunsPage />} />
      <Route path="/payroll/runs/:runId" element={<PayrollRunDetailPage />} />
      <Route path="/payroll/components" element={<PayrollComponentsPage />} />
      <Route path="/payroll/salaries" element={<EmployeeSalariesPage />} />
      <Route path="/payroll/config" element={<PayrollConfigPage />} />
      <Route path="/payroll/my-payslips" element={<MyPayslipsPage />} />
      <Route path="/settings/mail" element={<MailSettingsPage />} />
      <Route path="/reminders" element={<ExpiryCalendarPage />} />
      <Route path="/audit-logs" element={<AuditLogPage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="/profile" element={<ProfilePage />} />
      {/* Rekrutmen V1 — route spesifik harus sebelum placeholder generik */}
      <Route path="/modules/recruitment" element={<RecruitmentDashboardPage />} />
      <Route path="/modules/recruitment/candidates" element={<CandidatesPage />} />
      <Route path="/modules/recruitment/candidates/:candidateId" element={<CandidateDetailPage />} />
      {/* Time Management V1 — Absensi (menu existing, tanpa menu baru) */}
      <Route path="/modules/attendance" element={<AttendanceModuleLayout />}>
        <Route index element={<AttendanceOverviewPage />} />
        <Route path="saya" element={<MyAttendancePage />} />
        <Route path="data" element={<AttendanceListPage />} />
        <Route path="jadwal" element={<SchedulesPage />} />
        <Route path="rekap" element={<AttendanceRecapPage />} />
        <Route path="persetujuan" element={<AttendanceApprovalsPage />} />
        <Route path="impor" element={<TimeImportPage />} />
        <Route path="pengaturan" element={<TimeSettingsPage />} />
      </Route>
      {/* Time Management V1 — Cuti & Lembur (menu existing) */}
      <Route path="/modules/leave_overtime" element={<LeaveOvertimeModuleLayout />}>
        <Route index element={<LeaveOvertimeOverviewPage />} />
        <Route path="cuti" element={<LeaveRequestsPage />} />
        <Route path="lembur" element={<OvertimePage />} />
        <Route path="saldo" element={<LeaveBalancesPage />} />
        <Route path="persetujuan" element={<LeaveOvertimeApprovalsPage />} />
      </Route>
      <Route path="/modules/:moduleKey" element={<ModulePlaceholderPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Route>
  </Routes>
);

function App() {
  return (
    <BrowserRouter>
      <BrandingProvider>
        <AuthProvider>
          <AppRoutes />
          <Toaster />
        </AuthProvider>
      </BrandingProvider>
    </BrowserRouter>
  );
}

export default App;
