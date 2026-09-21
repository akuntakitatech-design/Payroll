import React from "react";
import "@/App.css";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/lib/auth";
import AppShell from "@/components/layout/AppShell";
import LoginPage from "@/pages/LoginPage";
import DashboardPage from "@/pages/DashboardPage";
import CompanyProfilePage from "@/pages/CompanyProfilePage";
import SetupHubPage from "@/pages/SetupHubPage";
import MasterDataPage from "@/pages/MasterDataPage";
import ModuleActivationPage from "@/pages/ModuleActivationPage";
import PoliciesPage from "@/pages/PoliciesPage";
import ApprovalWorkflowPage from "@/pages/ApprovalWorkflowPage";
import UsersPage from "@/pages/UsersPage";
import RolesPage from "@/pages/RolesPage";
import DocumentsPage from "@/pages/DocumentsPage";
import EmployeesPage from "@/pages/EmployeesPage";
import EmployeeDetailPage from "@/pages/EmployeeDetailPage";
import ExpiryCalendarPage from "@/pages/ExpiryCalendarPage";
import AuditLogPage from "@/pages/AuditLogPage";
import SettingsPage from "@/pages/SettingsPage";
import ProfilePage from "@/pages/ProfilePage";
import EmployeeImportPage from "@/pages/EmployeeImportPage";
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
import { Loader2 } from "lucide-react";

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
      <Route path="/setup/modules" element={<ModuleActivationPage />} />
      <Route path="/setup/policies" element={<PoliciesPage />} />
      <Route path="/setup/approval-workflows" element={<ApprovalWorkflowPage />} />
      <Route path="/users" element={<UsersPage />} />
      <Route path="/roles" element={<RolesPage />} />
      <Route path="/documents" element={<DocumentsPage />} />
      <Route path="/employees" element={<EmployeesPage />} />
      <Route path="/employees/import" element={<EmployeeImportPage />} />
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
      <AuthProvider>
        <AppRoutes />
        <Toaster />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
