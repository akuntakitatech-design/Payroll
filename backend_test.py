"""Comprehensive backend API testing for HRIS & Payroll SaaS.

Tests:
- Auth (login, JWT, company switching)
- Tenant isolation (CRITICAL)
- Employee CRUD + validation
- Contracts CRUD + approval
- Certifications CRUD
- Reminders/expiry calendar
- Document preview
- RBAC per role
- Module gating
"""
import requests
import sys
from typing import Dict, Optional, Tuple

BASE_URL = "https://github-payroll-build.preview.emergentagent.com/api"
PASSWORD = "Hris#2026"

# Test accounts
ACCOUNTS = {
    "superadmin": "superadmin@hris.id",
    "owner_nep": "owner@nep.co.id",
    "hr_admin_nep": "hr.admin@nep.co.id",
    "hr_manager_nep": "hr.manager@nep.co.id",
    "finance_nep": "finance@nep.co.id",
    "manager_nep": "manager@nep.co.id",
    "karyawan_nep": "karyawan@nep.co.id",
    "hr_admin_kbs": "hr.admin@kbs.co.id",
    "hr_multi": "hr.multi@hris.id",
}


class APITester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.tokens: Dict[str, str] = {}
        self.companies: Dict[str, Dict] = {}
        self.test_data: Dict[str, any] = {}

    def log(self, message: str, level: str = "INFO"):
        prefix = {
            "INFO": "ℹ️",
            "PASS": "✅",
            "FAIL": "❌",
            "WARN": "⚠️",
        }.get(level, "•")
        print(f"{prefix} {message}")

    def test(self, name: str, method: str, endpoint: str, expected_status: int,
             token: Optional[str] = None, data: Optional[Dict] = None,
             json_data: Optional[Dict] = None, files: Optional[Dict] = None) -> Tuple[bool, Optional[Dict]]:
        """Execute a single API test."""
        url = f"{BASE_URL}/{endpoint.lstrip('/')}"
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        self.tests_run += 1
        self.log(f"Testing: {name}", "INFO")

        try:
            if method == "GET":
                response = requests.get(url, headers=headers, timeout=30)
            elif method == "POST":
                if files:
                    headers.pop("Content-Type", None)
                    response = requests.post(url, headers=headers, data=data, files=files, timeout=30)
                else:
                    response = requests.post(url, headers=headers, json=json_data or data, timeout=30)
            elif method == "PUT":
                response = requests.put(url, headers=headers, json=json_data or data, timeout=30)
            elif method == "PATCH":
                response = requests.patch(url, headers=headers, json=json_data or data, timeout=30)
            elif method == "DELETE":
                response = requests.delete(url, headers=headers, timeout=30)
            else:
                self.log(f"Unknown method: {method}", "FAIL")
                self.tests_failed += 1
                return False, None

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"PASS - Status: {response.status_code}", "PASS")
            else:
                self.tests_failed += 1
                self.log(f"FAIL - Expected {expected_status}, got {response.status_code}", "FAIL")
                try:
                    self.log(f"Response: {response.json()}", "FAIL")
                except:
                    self.log(f"Response: {response.text[:200]}", "FAIL")

            try:
                return success, response.json() if response.text else {}
            except:
                return success, {}

        except Exception as e:
            self.tests_failed += 1
            self.log(f"FAIL - Exception: {str(e)}", "FAIL")
            return False, {}

    def login(self, email: str, password: str = PASSWORD) -> Optional[str]:
        """Login and return access token."""
        success, response = self.test(
            f"Login as {email}",
            "POST",
            "/auth/login",
            200,
            json_data={"email": email, "password": password}
        )
        if success and response and "access_token" in response:
            token = response["access_token"]
            self.tokens[email] = token
            if "company" in response and response["company"]:
                self.companies[email] = response["company"]
            return token
        return None

    def switch_company(self, token: str, company_id: str) -> Optional[str]:
        """Switch active company and return new token."""
        success, response = self.test(
            f"Switch to company {company_id}",
            "POST",
            "/auth/switch-company",
            200,
            token=token,
            json_data={"company_id": company_id}
        )
        if success and response and "access_token" in response:
            return response["access_token"]
        return None

    def test_auth(self):
        """Test authentication flows."""
        self.log("\n=== TESTING AUTH ===", "INFO")

        # Test login with valid credentials
        token = self.login(ACCOUNTS["hr_admin_nep"])
        if not token:
            self.log("Login failed - cannot continue", "FAIL")
            return False

        # Test invalid password
        self.test(
            "Login with invalid password",
            "POST",
            "/auth/login",
            401,
            json_data={"email": ACCOUNTS["hr_admin_nep"], "password": "wrongpassword"}
        )

        # Test /auth/me
        self.test(
            "Get current user info",
            "GET",
            "/auth/me",
            200,
            token=token
        )

        # Test company switching with hr.multi
        multi_token = self.login(ACCOUNTS["hr_multi"])
        if multi_token:
            success, response = self.test(
                "Get accessible companies",
                "GET",
                "/auth/my-companies",
                200,
                token=multi_token
            )
            if success and response and "items" in response:
                companies = response["items"]
                if len(companies) >= 2:
                    # Switch to second company
                    second_company = companies[1]
                    self.switch_company(multi_token, second_company["id"])

        return True

    def test_tenant_isolation(self):
        """CRITICAL: Test that tenant isolation is enforced."""
        self.log("\n=== TESTING TENANT ISOLATION (CRITICAL) ===", "INFO")

        # Login as hr.multi who has access to both NEP and KBS
        multi_token = self.login(ACCOUNTS["hr_multi"])
        if not multi_token:
            self.log("Cannot test tenant isolation - login failed", "FAIL")
            return False

        # Get companies
        success, response = self.test(
            "Get accessible companies for hr.multi",
            "GET",
            "/auth/my-companies",
            200,
            token=multi_token
        )

        if not success or not response or "items" not in response:
            self.log("Cannot get companies", "FAIL")
            return False

        companies = response["items"]
        nep_company = next((c for c in companies if "Nusantara" in c.get("name", "")), None)
        kbs_company = next((c for c in companies if "Karya" in c.get("name", "")), None)

        if not nep_company or not kbs_company:
            self.log("Cannot find both NEP and KBS companies", "FAIL")
            return False

        # Switch to KBS and get an employee ID
        kbs_token = self.switch_company(multi_token, kbs_company["id"])
        if not kbs_token:
            self.log("Failed to switch to KBS", "FAIL")
            return False
            
        success, response = self.test(
            "Get employees in KBS",
            "GET",
            "/employees?limit=1",
            200,
            token=kbs_token
        )

        kbs_employee_id = None
        if success and response and "items" in response and len(response["items"]) > 0:
            kbs_employee_id = response["items"][0]["id"]
            self.log(f"KBS employee ID: {kbs_employee_id}", "INFO")

        # Switch to NEP with FRESH token
        nep_token = self.switch_company(kbs_token, nep_company["id"])
        if not nep_token:
            self.log("Failed to switch to NEP", "FAIL")
            return False

        # Try to access KBS employee while active company is NEP - should be 404
        if kbs_employee_id:
            self.test(
                "ISOLATION: Access KBS employee from NEP context (should be 404)",
                "GET",
                f"/employees/{kbs_employee_id}",
                404,
                token=nep_token
            )

            # Try to update KBS employee from NEP context - should be 404
            self.test(
                "ISOLATION: Update KBS employee from NEP context (should be 404)",
                "PUT",
                f"/employees/{kbs_employee_id}",
                404,
                token=nep_token,
                json_data={"notes": "This should not work"}
            )

            # Try to delete KBS employee from NEP context - should be 404
            self.test(
                "ISOLATION: Delete KBS employee from NEP context (should be 404)",
                "DELETE",
                f"/employees/{kbs_employee_id}",
                404,
                token=nep_token
            )

        return True

    def test_employees(self):
        """Test employee CRUD operations."""
        self.log("\n=== TESTING EMPLOYEES ===", "INFO")

        token = self.tokens.get(ACCOUNTS["hr_admin_nep"]) or self.login(ACCOUNTS["hr_admin_nep"])
        if not token:
            return False

        # Get catalog
        success, catalog = self.test(
            "Get employee catalog",
            "GET",
            "/employees/catalog",
            200,
            token=token
        )

        # Get stats
        self.test(
            "Get employee stats",
            "GET",
            "/employees/stats",
            200,
            token=token
        )

        # List employees
        success, response = self.test(
            "List employees",
            "GET",
            "/employees?page=1&limit=10",
            200,
            token=token
        )

        # Create employee with auto employee_number
        success, response = self.test(
            "Create employee (auto employee_number)",
            "POST",
            "/employees",
            201,
            token=token,
            json_data={
                "full_name": "Test Employee Auto",
                "email": f"test.auto.{self.tests_run}@test.com",
                "gender": "male",
                "marital_status": "single"
            }
        )

        if success and response:
            employee_id = response.get("id")
            self.test_data["employee_id"] = employee_id
            self.log(f"Created employee with auto NIK: {response.get('employee_number')}", "INFO")

            # Get employee detail
            self.test(
                "Get employee detail",
                "GET",
                f"/employees/{employee_id}",
                200,
                token=token
            )

            # Update employee
            self.test(
                "Update employee",
                "PUT",
                f"/employees/{employee_id}",
                200,
                token=token,
                json_data={"phone": "081234567890"}
            )

            # Change status
            self.test(
                "Change employee status to inactive",
                "PATCH",
                f"/employees/{employee_id}/status",
                200,
                token=token,
                json_data={"status": "inactive"}
            )

        # Test duplicate employee_number
        success, response = self.test(
            "Create employee with manual employee_number",
            "POST",
            "/employees",
            201,
            token=token,
            json_data={
                "full_name": "Test Employee Manual",
                "employee_number": f"TEST-{self.tests_run}",
                "email": f"test.manual.{self.tests_run}@test.com",
                "gender": "female"
            }
        )

        if success and response:
            dup_number = response.get("employee_number")
            # Try to create with same employee_number - should be 409
            self.test(
                "Create employee with duplicate employee_number (should be 409)",
                "POST",
                "/employees",
                409,
                token=token,
                json_data={
                    "full_name": "Duplicate Test",
                    "employee_number": dup_number,
                    "email": f"test.dup.{self.tests_run}@test.com"
                }
            )

        # Test invalid FK - should be 422
        self.test(
            "Create employee with invalid department_id (should be 422)",
            "POST",
            "/employees",
            422,
            token=token,
            json_data={
                "full_name": "Invalid FK Test",
                "email": f"test.invalid.{self.tests_run}@test.com",
                "department_id": "invalid-department-id-12345"
            }
        )

        return True

    def test_contracts(self):
        """Test contract CRUD and approval."""
        self.log("\n=== TESTING CONTRACTS ===", "INFO")

        token = self.tokens.get(ACCOUNTS["hr_admin_nep"]) or self.login(ACCOUNTS["hr_admin_nep"])
        if not token:
            return False

        employee_id = self.test_data.get("employee_id")
        if not employee_id:
            # Get first employee
            success, response = self.test(
                "Get employees for contract test",
                "GET",
                "/employees?limit=1",
                200,
                token=token
            )
            if success and response and "items" in response and len(response["items"]) > 0:
                employee_id = response["items"][0]["id"]

        if not employee_id:
            self.log("No employee available for contract test", "WARN")
            return False

        # Get catalog to find contract type
        success, catalog = self.test(
            "Get catalog for contract types",
            "GET",
            "/employees/catalog",
            200,
            token=token
        )

        contract_type_id = None
        if success and catalog and "contract_types" in catalog and len(catalog["contract_types"]) > 0:
            contract_type_id = catalog["contract_types"][0]["id"]

        # Create contract
        success, response = self.test(
            "Create contract",
            "POST",
            "/contracts",
            201,
            token=token,
            json_data={
                "employee_id": employee_id,
                "contract_type_id": contract_type_id,
                "contract_number": f"CTR-TEST-{self.tests_run}",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31"
            }
        )

        if success and response:
            contract_id = response.get("id")
            self.test_data["contract_id"] = contract_id

            # Get contract detail
            self.test(
                "Get contract detail",
                "GET",
                f"/contracts/{contract_id}",
                200,
                token=token
            )

            # Update contract
            self.test(
                "Update contract",
                "PUT",
                f"/contracts/{contract_id}",
                200,
                token=token,
                json_data={"notes": "Updated contract notes"}
            )

            # Test approval (hr_admin should NOT have approve permission)
            self.test(
                "Approve contract as hr_admin (should be 403)",
                "POST",
                f"/contracts/{contract_id}/approve",
                403,
                token=token
            )

            # Login as hr_manager who has approve permission
            manager_token = self.login(ACCOUNTS["hr_manager_nep"])
            if manager_token:
                self.test(
                    "Approve contract as hr_manager",
                    "POST",
                    f"/contracts/{contract_id}/approve",
                    200,
                    token=manager_token
                )

                # Try to approve again - should be 409
                self.test(
                    "Approve already approved contract (should be 409)",
                    "POST",
                    f"/contracts/{contract_id}/approve",
                    409,
                    token=manager_token
                )

        # Test validation: end_date earlier than start_date
        self.test(
            "Create contract with end_date before start_date (should be 422)",
            "POST",
            "/contracts",
            422,
            token=token,
            json_data={
                "employee_id": employee_id,
                "contract_type_id": contract_type_id,
                "start_date": "2026-12-31",
                "end_date": "2026-01-01"
            }
        )

        # Test unknown contract_type
        self.test(
            "Create contract with unknown contract_type (should be 422)",
            "POST",
            "/contracts",
            422,
            token=token,
            json_data={
                "employee_id": employee_id,
                "contract_type_id": "invalid-contract-type-12345",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31"
            }
        )

        # List contracts
        self.test(
            "List contracts",
            "GET",
            "/contracts?page=1&limit=10",
            200,
            token=token
        )

        return True

    def test_certifications(self):
        """Test certification CRUD."""
        self.log("\n=== TESTING CERTIFICATIONS ===", "INFO")

        token = self.tokens.get(ACCOUNTS["hr_admin_nep"]) or self.login(ACCOUNTS["hr_admin_nep"])
        if not token:
            return False

        employee_id = self.test_data.get("employee_id")
        if not employee_id:
            success, response = self.test(
                "Get employees for certification test",
                "GET",
                "/employees?limit=1",
                200,
                token=token
            )
            if success and response and "items" in response and len(response["items"]) > 0:
                employee_id = response["items"][0]["id"]

        if not employee_id:
            self.log("No employee available for certification test", "WARN")
            return False

        # Get catalog
        success, catalog = self.test(
            "Get catalog for certification types",
            "GET",
            "/employees/catalog",
            200,
            token=token
        )

        cert_type_id = None
        if success and catalog and "certification_types" in catalog and len(catalog["certification_types"]) > 0:
            cert_type_id = catalog["certification_types"][0]["id"]

        # Create certification
        success, response = self.test(
            "Create certification",
            "POST",
            "/certifications",
            201,
            token=token,
            json_data={
                "employee_id": employee_id,
                "certification_type_id": cert_type_id,
                "name": f"Test Certification {self.tests_run}",
                "certificate_number": f"CERT-{self.tests_run}",
                "issued_date": "2025-01-01",
                "expiry_date": "2027-01-01",
                "issuer": "Test Issuer"
            }
        )

        if success and response:
            cert_id = response.get("id")

            # Get certification detail
            self.test(
                "Get certification detail",
                "GET",
                f"/certifications/{cert_id}",
                200,
                token=token
            )

            # Update certification
            self.test(
                "Update certification",
                "PUT",
                f"/certifications/{cert_id}",
                200,
                token=token,
                json_data={"notes": "Updated certification notes"}
            )

            # Change status
            self.test(
                "Change certification status",
                "PATCH",
                f"/certifications/{cert_id}/status",
                200,
                token=token,
                json_data={"status": "inactive"}
            )

            # Delete certification
            self.test(
                "Delete certification",
                "DELETE",
                f"/certifications/{cert_id}",
                200,
                token=token
            )

        # Test validation: expiry earlier than issued
        self.test(
            "Create certification with expiry before issued (should be 422)",
            "POST",
            "/certifications",
            422,
            token=token,
            json_data={
                "employee_id": employee_id,
                "certification_type_id": cert_type_id,
                "name": "Invalid Cert",
                "issued_date": "2027-01-01",
                "expiry_date": "2025-01-01"
            }
        )

        # Test unknown certification type
        self.test(
            "Create certification with unknown type (should be 422)",
            "POST",
            "/certifications",
            422,
            token=token,
            json_data={
                "employee_id": employee_id,
                "certification_type_id": "invalid-cert-type-12345",
                "name": "Invalid Type Cert"
            }
        )

        # List certifications
        self.test(
            "List certifications",
            "GET",
            "/certifications?page=1&limit=10",
            200,
            token=token
        )

        return True

    def test_reminders(self):
        """Test expiry reminders endpoint."""
        self.log("\n=== TESTING REMINDERS ===", "INFO")

        token = self.tokens.get(ACCOUNTS["hr_admin_nep"]) or self.login(ACCOUNTS["hr_admin_nep"])
        if not token:
            return False

        # Get reminders with default params
        success, response = self.test(
            "Get expiry reminders (default)",
            "GET",
            "/reminders/expiry",
            200,
            token=token
        )

        if success and response:
            self.log(f"Summary: {response.get('summary')}", "INFO")
            self.log(f"Available kinds: {response.get('available_kinds')}", "INFO")

        # Get reminders for contracts only
        self.test(
            "Get expiry reminders (contracts only)",
            "GET",
            "/reminders/expiry?kind=contract&days=90",
            200,
            token=token
        )

        # Get reminders for certifications only
        self.test(
            "Get expiry reminders (certifications only)",
            "GET",
            "/reminders/expiry?kind=certification&days=90",
            200,
            token=token
        )

        # Get expired items only
        self.test(
            "Get expired items only",
            "GET",
            "/reminders/expiry?state=expired&days=365",
            200,
            token=token
        )

        # Get due soon items only
        self.test(
            "Get due soon items only",
            "GET",
            "/reminders/expiry?state=due_soon&days=90",
            200,
            token=token
        )

        # Test with finance role (should only see employee and certification, not contract)
        finance_token = self.login(ACCOUNTS["finance_nep"])
        if finance_token:
            success, response = self.test(
                "Get reminders as finance (limited kinds)",
                "GET",
                "/reminders/expiry",
                200,
                token=finance_token
            )
            if success and response:
                available = response.get("available_kinds", [])
                self.log(f"Finance available kinds: {available}", "INFO")

        return True

    def test_documents(self):
        """Test document operations including preview."""
        self.log("\n=== TESTING DOCUMENTS ===", "INFO")

        token = self.tokens.get(ACCOUNTS["hr_admin_nep"]) or self.login(ACCOUNTS["hr_admin_nep"])
        if not token:
            return False

        # Get catalog
        success, catalog = self.test(
            "Get document catalog",
            "GET",
            "/documents/catalog",
            200,
            token=token
        )

        # List documents
        success, response = self.test(
            "List documents",
            "GET",
            "/documents?page=1&limit=10",
            200,
            token=token
        )

        # Get a document ID for preview test
        doc_id = None
        if success and response and "items" in response and len(response["items"]) > 0:
            doc_id = response["items"][0]["id"]

        if doc_id:
            # Get preview info
            success, preview_info = self.test(
                "Get document preview info",
                "GET",
                f"/documents/{doc_id}/preview-info",
                200,
                token=token
            )

            if success and preview_info:
                self.log(f"Preview kind: {preview_info.get('preview_kind')}", "INFO")
                self.log(f"Previewable: {preview_info.get('previewable')}", "INFO")

            # Get preview (should return file inline)
            self.test(
                "Get document preview",
                "GET",
                f"/documents/{doc_id}/preview",
                200,
                token=token
            )

            # Get document detail
            self.test(
                "Get document detail",
                "GET",
                f"/documents/{doc_id}",
                200,
                token=token
            )

        return True

    def test_rbac(self):
        """Test RBAC enforcement per role."""
        self.log("\n=== TESTING RBAC ===", "INFO")

        # Test finance role (should have view only for employees)
        finance_token = self.login(ACCOUNTS["finance_nep"])
        if finance_token:
            # Finance can view employees
            self.test(
                "Finance: View employees (allowed)",
                "GET",
                "/employees?limit=5",
                200,
                token=finance_token
            )

            # Finance cannot create employees
            self.test(
                "Finance: Create employee (should be 403)",
                "POST",
                "/employees",
                403,
                token=finance_token,
                json_data={
                    "full_name": "Should Not Work",
                    "email": "shouldnotwork@test.com"
                }
            )

        # Test manager role
        manager_token = self.login(ACCOUNTS["manager_nep"])
        if manager_token:
            # Manager can view employees
            self.test(
                "Manager: View employees (allowed)",
                "GET",
                "/employees?limit=5",
                200,
                token=manager_token
            )

            # Manager can view contracts
            self.test(
                "Manager: View contracts (allowed)",
                "GET",
                "/contracts?limit=5",
                200,
                token=manager_token
            )

            # Manager cannot create employees
            self.test(
                "Manager: Create employee (should be 403)",
                "POST",
                "/employees",
                403,
                token=manager_token,
                json_data={
                    "full_name": "Should Not Work",
                    "email": "shouldnotwork@test.com"
                }
            )

        # Test karyawan (employee) role
        karyawan_token = self.login(ACCOUNTS["karyawan_nep"])
        if karyawan_token:
            # Employee cannot view employees list
            self.test(
                "Employee: View employees (should be 403)",
                "GET",
                "/employees",
                403,
                token=karyawan_token
            )

            # Employee can view documents
            self.test(
                "Employee: View documents (allowed)",
                "GET",
                "/documents?limit=5",
                200,
                token=karyawan_token
            )

        # Test superadmin (wildcard permissions)
        superadmin_token = self.login(ACCOUNTS["superadmin"])
        if superadmin_token:
            # Superadmin can access everything
            self.test(
                "Superadmin: View employees (allowed)",
                "GET",
                "/employees?limit=5",
                200,
                token=superadmin_token
            )

        return True

    def test_module_gating(self):
        """Test module activation gating."""
        self.log("\n=== TESTING MODULE GATING ===", "INFO")

        # This test would require deactivating employee_core module
        # and verifying that employee endpoints return 403
        # For now, just verify that with module active, endpoints work

        token = self.tokens.get(ACCOUNTS["hr_admin_nep"]) or self.login(ACCOUNTS["hr_admin_nep"])
        if not token:
            return False

        # With employee_core active, should work
        self.test(
            "Access employees with employee_core active",
            "GET",
            "/employees?limit=1",
            200,
            token=token
        )

        self.log("Note: Full module gating test requires deactivating module via UI", "WARN")
        return True

    def test_delete_employee_with_contracts(self):
        """Test that employee with contracts cannot be deleted."""
        self.log("\n=== TESTING DELETE CONSTRAINTS ===", "INFO")

        token = self.tokens.get(ACCOUNTS["hr_admin_nep"]) or self.login(ACCOUNTS["hr_admin_nep"])
        if not token:
            return False

        employee_id = self.test_data.get("employee_id")
        contract_id = self.test_data.get("contract_id")

        if employee_id and contract_id:
            # Try to delete employee with contracts - should be 409
            self.test(
                "Delete employee with contracts (should be 409)",
                "DELETE",
                f"/employees/{employee_id}",
                409,
                token=token
            )

        return True

    def test_payroll_catalog_config(self):
        """Test payroll catalog and configuration endpoints."""
        self.log("\n=== TESTING PAYROLL CATALOG & CONFIG ===", "INFO")
        
        token = self.tokens.get(ACCOUNTS["hr_admin_nep"]) or self.login(ACCOUNTS["hr_admin_nep"])
        if not token:
            return False
        
        # GET /api/payroll/catalog
        success, data = self.test(
            "GET /api/payroll/catalog",
            "GET",
            "/payroll/catalog",
            200,
            token=token
        )
        if success and data:
            self.log(f"Catalog contains: ptkp_statuses, jkk_risk_classes, months, component_kinds", "INFO")
        
        # GET /api/payroll/config
        success, data = self.test(
            "GET /api/payroll/config",
            "GET",
            "/payroll/config",
            200,
            token=token
        )
        
        # PUT /api/payroll/config (requires payroll:config permission - use owner)
        owner_token = self.tokens.get(ACCOUNTS["owner_nep"]) or self.login(ACCOUNTS["owner_nep"])
        if owner_token:
            success, data = self.test(
                "PUT /api/payroll/config (update BPJS rates)",
                "PUT",
                "/payroll/config",
                200,
                token=owner_token,
                json_data={
                    "bpjs_kes_employee_rate": 0.01,
                    "jkk_risk_class": "sedang"
                }
            )
        
        return True
    
    def test_payroll_components(self):
        """Test payroll components CRUD."""
        self.log("\n=== TESTING PAYROLL COMPONENTS CRUD ===", "INFO")
        
        token = self.tokens.get(ACCOUNTS["hr_admin_nep"]) or self.login(ACCOUNTS["hr_admin_nep"])
        if not token:
            return False
        
        # GET /api/payroll/components
        success, data = self.test(
            "GET /api/payroll/components",
            "GET",
            "/payroll/components",
            200,
            token=token
        )
        
        # POST /api/payroll/components
        success, component = self.test(
            "POST /api/payroll/components (create earning)",
            "POST",
            "/payroll/components",
            201,
            token=token,
            json_data={
                "code": "TEST_ALLOW",
                "name": "Tunjangan Test",
                "kind": "earning",
                "calc": "fixed",
                "default_amount": 500000,
                "taxable": True,
                "prorate": False
            }
        )
        if success and component:
            component_id = component.get("id")
            self.test_data["payroll_component_id"] = component_id
            
            # PUT /api/payroll/components/{id}
            self.test(
                "PUT /api/payroll/components/{id}",
                "PUT",
                f"/payroll/components/{component_id}",
                200,
                token=token,
                json_data={"default_amount": 600000}
            )
            
            # DELETE /api/payroll/components/{id}
            self.test(
                "DELETE /api/payroll/components/{id}",
                "DELETE",
                f"/payroll/components/{component_id}",
                200,
                token=token
            )
        
        return True
    
    def test_payroll_salaries(self):
        """Test employee salary structure endpoints."""
        self.log("\n=== TESTING PAYROLL SALARY STRUCTURE ===", "INFO")
        
        token = self.tokens.get(ACCOUNTS["hr_admin_nep"]) or self.login(ACCOUNTS["hr_admin_nep"])
        if not token:
            return False
        
        # GET /api/payroll/salaries
        success, data = self.test(
            "GET /api/payroll/salaries",
            "GET",
            "/payroll/salaries",
            200,
            token=token
        )
        
        employee_id = self.test_data.get("employee_id")
        if employee_id:
            # GET /api/payroll/salaries/{employee_id}
            success, salary_data = self.test(
                "GET /api/payroll/salaries/{employee_id}",
                "GET",
                f"/payroll/salaries/{employee_id}",
                200,
                token=token
            )
            
            # PUT /api/payroll/salaries/{employee_id}
            self.test(
                "PUT /api/payroll/salaries/{employee_id}",
                "PUT",
                f"/payroll/salaries/{employee_id}",
                200,
                token=token,
                json_data={
                    "basic_salary": 8000000,
                    "ptkp_status": "TK/0",
                    "has_npwp": True,
                    "bpjs_kesehatan_enrolled": True,
                    "bpjs_jht_enrolled": True,
                    "bpjs_jp_enrolled": True,
                    "components": []
                }
            )
        
        return True
    
    def test_payroll_run_lifecycle(self):
        """Test complete payroll run lifecycle."""
        self.log("\n=== TESTING PAYROLL RUN LIFECYCLE ===", "INFO")
        
        hr_token = self.tokens.get(ACCOUNTS["hr_admin_nep"]) or self.login(ACCOUNTS["hr_admin_nep"])
        if not hr_token:
            return False
        
        # GET /api/payroll/runs
        success, data = self.test(
            "GET /api/payroll/runs",
            "GET",
            "/payroll/runs",
            200,
            token=hr_token
        )
        
        # POST /api/payroll/runs (create new run for 2027 to avoid conflicts)
        success, run = self.test(
            "POST /api/payroll/runs (create January 2027)",
            "POST",
            "/payroll/runs",
            201,
            token=hr_token,
            json_data={
                "year": 2027,
                "month": 1,
                "payment_date": "2027-02-05",
                "notes": "Test payroll run"
            }
        )
        
        if not success or not run:
            self.log("Failed to create payroll run, skipping lifecycle tests", "WARN")
            return False
        
        run_id = run.get("id")
        self.test_data["payroll_run_id"] = run_id
        self.log(f"Created payroll run: {run_id}", "INFO")
        
        # GET /api/payroll/runs/{id}
        success, run_detail = self.test(
            "GET /api/payroll/runs/{id}",
            "GET",
            f"/payroll/runs/{run_id}",
            200,
            token=hr_token
        )
        
        if success and run_detail:
            items = run_detail.get("items", [])
            if items:
                item_id = items[0].get("id")
                employee_id = items[0].get("employee_id")
                
                # PUT /api/payroll/runs/{id}/items/{item_id}/adjustments
                self.test(
                    "PUT adjustments (overtime + unpaid days)",
                    "PUT",
                    f"/payroll/runs/{run_id}/items/{item_id}/adjustments",
                    200,
                    token=hr_token,
                    json_data={
                        "overtime_hours": 10,
                        "unpaid_days": 2,
                        "extra_earnings": [{"name": "Bonus", "amount": 500000}],
                        "extra_deductions": [{"name": "Pinjaman", "amount": 200000}]
                    }
                )
        
        # POST /api/payroll/runs/{id}/recalculate
        self.test(
            "POST /api/payroll/runs/{id}/recalculate",
            "POST",
            f"/payroll/runs/{run_id}/recalculate",
            200,
            token=hr_token
        )
        
        # POST /api/payroll/runs/{id}/submit
        self.test(
            "POST /api/payroll/runs/{id}/submit",
            "POST",
            f"/payroll/runs/{run_id}/submit",
            200,
            token=hr_token,
            json_data={"note": "Ready for approval"}
        )
        
        # POST /api/payroll/runs/{id}/approve (use hr.manager)
        manager_token = self.tokens.get(ACCOUNTS["hr_manager_nep"]) or self.login(ACCOUNTS["hr_manager_nep"])
        if manager_token:
            # Test self-approval rejection first
            self.test(
                "POST approve by same submitter (should be 403)",
                "POST",
                f"/payroll/runs/{run_id}/approve",
                403,
                token=hr_token,
                json_data={"note": "Approved"}
            )
            
            # Approve with different user
            success, _ = self.test(
                "POST /api/payroll/runs/{id}/approve (by hr.manager)",
                "POST",
                f"/payroll/runs/{run_id}/approve",
                200,
                token=manager_token,
                json_data={"note": "Approved by manager"}
            )
            
            if success:
                # POST /api/payroll/runs/{id}/mark-paid
                self.test(
                    "POST /api/payroll/runs/{id}/mark-paid",
                    "POST",
                    f"/payroll/runs/{run_id}/mark-paid",
                    200,
                    token=hr_token,
                    json_data={"note": "Payment completed"}
                )
        
        # Test reject flow with another run
        success, run2 = self.test(
            "POST /api/payroll/runs (create February 2027 for reject test)",
            "POST",
            "/payroll/runs",
            201,
            token=hr_token,
            json_data={
                "year": 2027,
                "month": 2,
                "payment_date": "2027-03-05"
            }
        )
        
        if success and run2:
            run2_id = run2.get("id")
            # Submit
            self.test(
                "Submit February run",
                "POST",
                f"/payroll/runs/{run2_id}/submit",
                200,
                token=hr_token
            )
            
            # Reject (note is mandatory)
            self.test(
                "POST reject without note (should be 422)",
                "POST",
                f"/payroll/runs/{run2_id}/reject",
                422,
                token=manager_token,
                json_data={}
            )
            
            self.test(
                "POST /api/payroll/runs/{id}/reject (with note)",
                "POST",
                f"/payroll/runs/{run2_id}/reject",
                200,
                token=manager_token,
                json_data={"note": "Please fix overtime calculations"}
            )
            
            # DELETE rejected run (should work)
            self.test(
                "DELETE /api/payroll/runs/{id} (rejected run)",
                "DELETE",
                f"/payroll/runs/{run2_id}",
                200,
                token=hr_token
            )
        
        # Try to delete approved/paid run (should be 409)
        if run_id:
            self.test(
                "DELETE approved/paid run (should be 409)",
                "DELETE",
                f"/payroll/runs/{run_id}",
                409,
                token=hr_token
            )
        
        return True
    
    def test_payroll_pdf_export(self):
        """Test payslip PDF and Excel export."""
        self.log("\n=== TESTING PAYSLIP PDF & EXPORT ===", "INFO")
        
        token = self.tokens.get(ACCOUNTS["hr_admin_nep"]) or self.login(ACCOUNTS["hr_admin_nep"])
        if not token:
            return False
        
        run_id = self.test_data.get("payroll_run_id")
        if not run_id:
            self.log("No payroll run available, skipping PDF/export tests", "WARN")
            return True
        
        # Get run detail to find an item
        success, run_detail = self.test(
            "GET run detail for PDF test",
            "GET",
            f"/payroll/runs/{run_id}",
            200,
            token=token
        )
        
        if success and run_detail:
            items = run_detail.get("items", [])
            if items:
                item_id = items[0].get("id")
                
                # GET /api/payroll/runs/{id}/items/{item_id}/payslip (PDF)
                url = f"{BASE_URL}/payroll/runs/{run_id}/items/{item_id}/payslip"
                headers = {"Authorization": f"Bearer {token}"}
                response = requests.get(url, headers=headers, timeout=30)
                
                self.tests_run += 1
                if response.status_code == 200 and response.headers.get("content-type") == "application/pdf":
                    self.tests_passed += 1
                    self.log("PASS - Payslip PDF download", "PASS")
                else:
                    self.tests_failed += 1
                    self.log(f"FAIL - Payslip PDF: {response.status_code}", "FAIL")
        
        # GET /api/payroll/runs/{id}/export (Excel)
        url = f"{BASE_URL}/payroll/runs/{run_id}/export"
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(url, headers=headers, timeout=30)
        
        self.tests_run += 1
        if response.status_code == 200 and "spreadsheet" in response.headers.get("content-type", ""):
            self.tests_passed += 1
            self.log("PASS - Payroll Excel export", "PASS")
        else:
            self.tests_failed += 1
            self.log(f"FAIL - Excel export: {response.status_code}", "FAIL")
        
        return True
    
    def test_payroll_self_service(self):
        """Test employee self-service payslip endpoints."""
        self.log("\n=== TESTING PAYROLL SELF-SERVICE ===", "INFO")
        
        # Login as employee
        emp_token = self.tokens.get(ACCOUNTS["karyawan_nep"]) or self.login(ACCOUNTS["karyawan_nep"])
        if not emp_token:
            return False
        
        # GET /api/payroll/my/payslips
        success, data = self.test(
            "GET /api/payroll/my/payslips (as employee)",
            "GET",
            "/payroll/my/payslips",
            200,
            token=emp_token
        )
        
        if success and data:
            items = data.get("items", [])
            if items:
                item_id = items[0].get("id")
                
                # GET /api/payroll/my/payslips/{item_id}/payslip (PDF)
                url = f"{BASE_URL}/payroll/my/payslips/{item_id}/payslip"
                headers = {"Authorization": f"Bearer {emp_token}"}
                response = requests.get(url, headers=headers, timeout=30)
                
                self.tests_run += 1
                if response.status_code == 200:
                    self.tests_passed += 1
                    self.log("PASS - Employee can download own payslip", "PASS")
                else:
                    self.tests_failed += 1
                    self.log(f"FAIL - Employee payslip download: {response.status_code}", "FAIL")
        
        # Test that employee CANNOT access HR payroll endpoints
        self.test(
            "Employee access to /api/payroll/runs (should be 403)",
            "GET",
            "/payroll/runs",
            403,
            token=emp_token
        )
        
        # Test that employee cannot access other employee's slip
        hr_token = self.tokens.get(ACCOUNTS["hr_admin_nep"]) or self.login(ACCOUNTS["hr_admin_nep"])
        if hr_token:
            # Get a payslip item from HR view
            success, run_data = self.test(
                "HR: Get payroll runs",
                "GET",
                "/payroll/runs?limit=1",
                200,
                token=hr_token
            )
            if success and run_data:
                runs = run_data.get("items", [])
                if runs:
                    run_id = runs[0].get("id")
                    success, run_detail = self.test(
                        "HR: Get run detail",
                        "GET",
                        f"/payroll/runs/{run_id}",
                        200,
                        token=hr_token
                    )
                    if success and run_detail:
                        items = run_detail.get("items", [])
                        # Find an item that's NOT the employee's
                        for item in items:
                            if item.get("employee_id") != data.get("employee", {}).get("id"):
                                other_item_id = item.get("id")
                                # Try to access with employee token
                                self.test(
                                    "Employee access other's payslip (should be 404)",
                                    "GET",
                                    f"/payroll/my/payslips/{other_item_id}/payslip",
                                    404,
                                    token=emp_token
                                )
                                break
        
        return True
    
    def test_contract_renewal(self):
        """Test contract renewal endpoints."""
        self.log("\n=== TESTING CONTRACT RENEWAL ===", "INFO")
        
        token = self.tokens.get(ACCOUNTS["hr_admin_nep"]) or self.login(ACCOUNTS["hr_admin_nep"])
        if not token:
            return False
        
        contract_id = self.test_data.get("contract_id")
        if not contract_id:
            self.log("No contract available for renewal test", "WARN")
            return True
        
        # GET /api/contracts/{id}/renew-preview
        success, preview = self.test(
            "GET /api/contracts/{id}/renew-preview",
            "GET",
            f"/contracts/{contract_id}/renew-preview",
            200,
            token=token
        )
        
        if success and preview:
            defaults = preview.get("defaults", {})
            
            # POST /api/contracts/{id}/renew with invalid start_date (before end_date)
            self.test(
                "POST renew with start_date before end_date (should be 422)",
                "POST",
                f"/contracts/{contract_id}/renew",
                422,
                token=token,
                json_data={
                    "start_date": "2025-01-01",
                    "end_date": "2025-12-31",
                    "contract_number": "TEST-RENEW-001"
                }
            )
            
            # POST /api/contracts/{id}/renew with valid data
            import time
            unique_suffix = str(int(time.time()))[-6:]
            success, renewed = self.test(
                "POST /api/contracts/{id}/renew (valid)",
                "POST",
                f"/contracts/{contract_id}/renew",
                201,
                token=token,
                json_data={
                    "start_date": defaults.get("start_date"),
                    "end_date": defaults.get("end_date"),
                    "contract_number": f"RENEW-TEST-{unique_suffix}",
                    "basic_salary": defaults.get("basic_salary"),
                    "archive_previous": True
                }
            )
            
            if success and renewed:
                new_contract_id = renewed.get("contract", {}).get("id")
                self.test_data["renewed_contract_id"] = new_contract_id
                
                # Try to renew again (should be 409)
                self.test(
                    "POST renew already renewed contract (should be 409)",
                    "POST",
                    f"/contracts/{contract_id}/renew",
                    409,
                    token=token,
                    json_data={
                        "start_date": defaults.get("start_date"),
                        "end_date": defaults.get("end_date")
                    }
                )
        
        return True
    
    def test_employee_import(self):
        """Test employee Excel import endpoints."""
        self.log("\n=== TESTING EMPLOYEE EXCEL IMPORT ===", "INFO")
        
        token = self.tokens.get(ACCOUNTS["hr_admin_nep"]) or self.login(ACCOUNTS["hr_admin_nep"])
        if not token:
            return False
        
        # GET /api/employees/import/template
        url = f"{BASE_URL}/employees/import/template"
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(url, headers=headers, timeout=30)
        
        self.tests_run += 1
        if response.status_code == 200 and "spreadsheet" in response.headers.get("content-type", ""):
            self.tests_passed += 1
            self.log("PASS - Download import template", "PASS")
            template_content = response.content
        else:
            self.tests_failed += 1
            self.log(f"FAIL - Template download: {response.status_code}", "FAIL")
            return False
        
        # GET /api/employees/import/columns
        success, columns = self.test(
            "GET /api/employees/import/columns",
            "GET",
            "/employees/import/columns",
            200,
            token=token
        )
        
        # Create a test Excel file with valid and invalid rows
        from io import BytesIO
        from openpyxl import load_workbook
        
        wb = load_workbook(BytesIO(template_content))
        ws = wb.active
        
        # Add test rows (row 3 onwards, row 2 is header)
        ws.append([
            "TEST-IMP-001",  # employee_number
            "Test Import Valid",  # full_name
            "test.import1@test.com",  # email
            "081234567890",  # phone
            "male",  # gender
            "1990-01-01",  # birth_date
            "",  # nik
            "",  # npwp
            "Staff",  # job_title
            "2027-01-01",  # join_date
            "",  # branch
            "",  # department
            "",  # position
            5000000,  # basic_salary
            "TK/0"  # ptkp_status
        ])
        
        ws.append([
            "TEST-IMP-002",
            "Test Import Valid 2",
            "test.import2@test.com",
            "081234567891",
            "female",
            "1992-05-15",
            "",
            "",
            "Manager",
            "2027-01-15",
            "",
            "",
            "",
            7000000,
            "K/1"
        ])
        
        # Invalid row (missing full_name)
        ws.append([
            "TEST-IMP-003",
            "",  # empty full_name
            "test.import3@test.com",
            "",
            "male",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            ""
        ])
        
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        
        # POST /api/employees/import/validate
        url = f"{BASE_URL}/employees/import/validate"
        headers = {"Authorization": f"Bearer {token}"}
        files = {"file": ("test_import.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        response = requests.post(url, headers=headers, files=files, timeout=30)
        
        self.tests_run += 1
        if response.status_code == 200:
            self.tests_passed += 1
            self.log("PASS - Validate import file", "PASS")
            validation = response.json()
            valid_rows = validation.get("valid_rows", [])
            invalid_rows = validation.get("invalid_rows", [])
            self.log(f"Valid: {len(valid_rows)}, Invalid: {len(invalid_rows)}", "INFO")
            
            # POST /api/employees/import/commit (only valid rows)
            if valid_rows:
                success, result = self.test(
                    "POST /api/employees/import/commit",
                    "POST",
                    "/employees/import/commit",
                    201,
                    token=token,
                    json_data={"rows": valid_rows}
                )
                if success:
                    self.log(f"Imported {result.get('created_count')} employees", "INFO")
        else:
            self.tests_failed += 1
            self.log(f"FAIL - Validate import: {response.status_code}", "FAIL")
        
        return True
    
    def test_mail_settings(self):
        """Test mail settings and reminder endpoints."""
        self.log("\n=== TESTING MAIL SETTINGS & REMINDERS ===", "INFO")
        
        # Use owner token (has settings:config permission)
        token = self.tokens.get(ACCOUNTS["owner_nep"]) or self.login(ACCOUNTS["owner_nep"])
        if not token:
            return False
        
        # GET /api/mail/settings
        success, settings = self.test(
            "GET /api/mail/settings",
            "GET",
            "/mail/settings",
            200,
            token=token
        )
        
        if success and settings:
            smtp = settings.get("smtp", {})
            # Verify password is NOT returned
            if "password" in smtp:
                self.log("FAIL - Password should not be returned in GET", "FAIL")
                self.tests_failed += 1
            else:
                self.log("PASS - Password correctly masked", "PASS")
                self.tests_passed += 1
            self.tests_run += 1
        
        # PUT /api/mail/settings/smtp
        success, _ = self.test(
            "PUT /api/mail/settings/smtp",
            "PUT",
            "/mail/settings/smtp",
            200,
            token=token,
            json_data={
                "host": "smtp.nusantaraenergi.co.id",
                "port": 587,
                "username": "noreply@nep.co.id",
                "password": "test_password_123",
                "from_email": "noreply@nep.co.id",
                "from_name": "NEP HRIS",
                "security": "starttls"
            }
        )
        
        # PUT /api/mail/settings/reminder
        success, _ = self.test(
            "PUT /api/mail/settings/reminder (enable without recipients - should be 422)",
            "PUT",
            "/mail/settings/reminder",
            422,
            token=token,
            json_data={
                "is_enabled": True,
                "recipients": []
            }
        )
        
        success, _ = self.test(
            "PUT /api/mail/settings/reminder (valid)",
            "PUT",
            "/mail/settings/reminder",
            200,
            token=token,
            json_data={
                "is_enabled": False,
                "recipients": ["hr@nep.co.id", "admin@nep.co.id"],
                "windows": [7, 14, 30],
                "send_hour": 9
            }
        )
        
        # GET /api/mail/reminder/preview
        success, preview = self.test(
            "GET /api/mail/reminder/preview",
            "GET",
            "/mail/reminder/preview",
            200,
            token=token
        )
        
        # GET /api/mail/reminder/logs
        success, logs = self.test(
            "GET /api/mail/reminder/logs",
            "GET",
            "/mail/reminder/logs",
            200,
            token=token
        )
        
        # POST /api/mail/settings/smtp/test (will fail with demo SMTP but should return proper error)
        success, result = self.test(
            "POST /api/mail/settings/smtp/test (expect 400 with demo SMTP)",
            "POST",
            "/mail/settings/smtp/test",
            400,
            token=token,
            json_data={"to": "test@example.com"}
        )
        
        # POST /api/mail/reminder/send-now (will fail with demo SMTP)
        success, result = self.test(
            "POST /api/mail/reminder/send-now (expect 400 with demo SMTP)",
            "POST",
            "/mail/reminder/send-now",
            400,
            token=token
        )
        
        return True
    
    def test_payroll_tenant_isolation(self):
        """Test tenant isolation for payroll endpoints."""
        self.log("\n=== TESTING PAYROLL TENANT ISOLATION ===", "INFO")
        
        # Login to NEP and create a payroll run
        nep_token = self.tokens.get(ACCOUNTS["hr_admin_nep"]) or self.login(ACCOUNTS["hr_admin_nep"])
        if not nep_token:
            return False
        
        # Get NEP payroll run
        success, nep_runs = self.test(
            "NEP: Get payroll runs",
            "GET",
            "/payroll/runs?limit=1",
            200,
            token=nep_token
        )
        
        if not success or not nep_runs or not nep_runs.get("items"):
            self.log("No NEP payroll runs available for isolation test", "WARN")
            return True
        
        nep_run_id = nep_runs["items"][0]["id"]
        
        # Get NEP employee salary
        success, nep_salaries = self.test(
            "NEP: Get employee salaries",
            "GET",
            "/payroll/salaries?limit=1",
            200,
            token=nep_token
        )
        
        nep_employee_id = None
        if success and nep_salaries and nep_salaries.get("items"):
            nep_employee_id = nep_salaries["items"][0]["employee_id"]
        
        # Login to KBS with FRESH token
        kbs_token = self.login(ACCOUNTS["hr_admin_kbs"])
        if not kbs_token:
            return False
        
        # KBS should NOT be able to access NEP payroll run
        self.test(
            "KBS: Access NEP payroll run (should be 404)",
            "GET",
            f"/payroll/runs/{nep_run_id}",
            404,
            token=kbs_token
        )
        
        # KBS should NOT be able to access NEP employee salary
        if nep_employee_id:
            self.test(
                "KBS: Access NEP employee salary (should be 404)",
                "GET",
                f"/payroll/salaries/{nep_employee_id}",
                404,
                token=kbs_token
            )
            
            self.test(
                "KBS: Update NEP employee salary (should be 404)",
                "PUT",
                f"/payroll/salaries/{nep_employee_id}",
                404,
                token=kbs_token,
                json_data={"basic_salary": 9999999}
            )
        
        # KBS should NOT be able to access NEP contract renewal
        if self.test_data.get("contract_id"):
            self.test(
                "KBS: Access NEP contract renewal preview (should be 404)",
                "GET",
                f"/contracts/{self.test_data['contract_id']}/renew-preview",
                404,
                token=kbs_token
            )
        
        return True

    def run_all_tests(self):
        """Run all test suites."""
        self.log("\n" + "="*60, "INFO")
        self.log("HRIS & PAYROLL SAAS - BACKEND API TESTING", "INFO")
        self.log("="*60 + "\n", "INFO")

        try:
            self.test_auth()
            self.test_tenant_isolation()
            self.test_employees()
            self.test_contracts()
            self.test_certifications()
            self.test_reminders()
            self.test_documents()
            self.test_rbac()
            self.test_module_gating()
            self.test_delete_employee_with_contracts()
            
            # NEW PAYROLL TESTS
            self.test_payroll_catalog_config()
            self.test_payroll_components()
            self.test_payroll_salaries()
            self.test_payroll_run_lifecycle()
            self.test_payroll_pdf_export()
            self.test_payroll_self_service()
            self.test_contract_renewal()
            self.test_employee_import()
            self.test_mail_settings()
            self.test_payroll_tenant_isolation()

        except Exception as e:
            self.log(f"Test suite error: {str(e)}", "FAIL")
            import traceback
            traceback.print_exc()

        # Print summary
        self.log("\n" + "="*60, "INFO")
        self.log("TEST SUMMARY", "INFO")
        self.log("="*60, "INFO")
        self.log(f"Total tests: {self.tests_run}", "INFO")
        self.log(f"Passed: {self.tests_passed}", "PASS")
        self.log(f"Failed: {self.tests_failed}", "FAIL")
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        self.log(f"Success rate: {success_rate:.1f}%", "INFO")
        self.log("="*60 + "\n", "INFO")

        return self.tests_failed == 0


def main():
    tester = APITester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
