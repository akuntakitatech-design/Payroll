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
