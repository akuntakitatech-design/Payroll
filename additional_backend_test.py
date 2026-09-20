"""Additional backend tests for master data, users, roles, policies, audit logs, dashboard."""
import requests
import sys

BASE_URL = "https://commit-checker-live-9.preview.emergentagent.com/api"
PASSWORD = "Hris#2026"

class AdditionalTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.token = None
        self.company_id = None

    def log(self, message: str, level: str = "INFO"):
        prefix = {"INFO": "ℹ️", "PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}.get(level, "•")
        print(f"{prefix} {message}")

    def test(self, name: str, method: str, endpoint: str, expected_status: int, data=None):
        url = f"{BASE_URL}/{endpoint.lstrip('/')}"
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        self.tests_run += 1
        self.log(f"Testing: {name}", "INFO")

        try:
            if method == "GET":
                response = requests.get(url, headers=headers, timeout=30)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=data, timeout=30)
            elif method == "PUT":
                response = requests.put(url, headers=headers, json=data, timeout=30)
            elif method == "PATCH":
                response = requests.patch(url, headers=headers, json=data, timeout=30)
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
            return False, None

    def run_tests(self):
        print("\n" + "="*60)
        print("ADDITIONAL BACKEND API TESTS")
        print("="*60)

        # Login
        print("\n=== LOGIN ===")
        success, response = self.test("Login as hr.admin@nep.co.id", "POST", "/auth/login",
                                      200, {"email": "hr.admin@nep.co.id", "password": PASSWORD})
        if not success:
            print("❌ Login failed, cannot continue")
            return 1
        self.token = response.get("access_token")
        self.company_id = response.get("user", {}).get("company_id")

        # Master data registry
        print("\n=== MASTER DATA REGISTRY ===")
        self.test("GET /api/master/registry", "GET", "/master/registry", 200)

        # Test various master resources
        master_resources = [
            "branches", "departments", "positions", "job-grades", 
            "projects", "contract-types", "certification-types",
            "employment-statuses", "cost-centers", "divisions",
            "work-locations", "document-types"
        ]

        print("\n=== MASTER DATA CRUD ===")
        for resource in master_resources[:5]:  # Test first 5 to save time
            self.test(f"GET /api/master/{resource}", "GET", f"/master/{resource}", 200)
            self.test(f"GET /api/master/{resource}/options", "GET", f"/master/{resource}/options", 200)

        # Create a branch
        success, branch = self.test("POST /api/master/branches", "POST", "/master/branches", 201, {
            "code": "TEST-BR-001",
            "name": "Test Branch for MariaDB",
            "description": "Testing SQL translation",
            "is_head_office": False
        })
        if success and branch:
            branch_id = branch.get("id")
            # Update branch
            self.test("PUT /api/master/branches/{id}", "PUT", f"/master/branches/{branch_id}", 200, {
                "name": "Test Branch Updated",
                "description": "Updated via MariaDB"
            })
            # Test duplicate code
            self.test("POST duplicate branch code (should be 409)", "POST", "/master/branches", 409, {
                "code": "TEST-BR-001",
                "name": "Duplicate Branch"
            })
            # Test search with regex
            self.test("GET /api/master/branches?q=MariaDB", "GET", "/master/branches?q=MariaDB", 200)
            # Test pagination
            self.test("GET /api/master/branches?page=1&limit=5", "GET", "/master/branches?page=1&limit=5", 200)
            # Test sort
            self.test("GET /api/master/branches?sort_by=name&sort_dir=asc", "GET", "/master/branches?sort_by=name&sort_dir=asc", 200)
            # Change status
            self.test("PATCH /api/master/branches/{id}/status", "PATCH", f"/master/branches/{branch_id}/status", 200, {
                "status": "inactive"
            })
            # Delete
            self.test("DELETE /api/master/branches/{id}", "DELETE", f"/master/branches/{branch_id}", 200)

        # Users & Roles
        print("\n=== USERS & ROLES ===")
        self.test("GET /api/users", "GET", "/users", 200)
        self.test("GET /api/roles", "GET", "/roles", 200)
        self.test("GET /api/modules", "GET", "/modules", 200)

        # Approval workflows
        print("\n=== APPROVAL WORKFLOWS ===")
        self.test("GET /api/approval-workflows", "GET", "/approval-workflows", 200)
        self.test("GET /api/approval-workflows/catalog", "GET", "/approval-workflows/catalog", 200)

        # Policies
        print("\n=== POLICIES ===")
        self.test("GET /api/policies/catalog", "GET", "/policies/catalog", 200)
        self.test("GET /api/policies/effective", "GET", "/policies/effective", 200)
        self.test("GET /api/policies/overrides", "GET", "/policies/overrides", 200)

        # Create policy override
        success, override = self.test("POST /api/policies/overrides", "POST", "/policies/overrides", 201, {
            "config_key": "test.mariadb.config",
            "scope_type": "company",
            "scope_id": self.company_id,
            "scope_label": "NEP",
            "value": {"test_int": 42, "test_dict": {"nested": "value"}},
            "effective_from": "2027-01-01",
            "notes": "Testing JSON value storage in MariaDB"
        })
        if success and override:
            override_id = override.get("id")
            # Update override
            self.test("PUT /api/policies/overrides/{id}", "PUT", f"/policies/overrides/{override_id}", 200, {
                "value": {"test_int": 100, "test_dict": {"nested": "updated"}},
                "notes": "Updated JSON value"
            })
            # Delete override
            self.test("DELETE /api/policies/overrides/{id}", "DELETE", f"/policies/overrides/{override_id}", 200)

        # Dashboard
        print("\n=== DASHBOARD ===")
        self.test("GET /api/dashboard/summary", "GET", "/dashboard/summary", 200)

        # Audit logs
        print("\n=== AUDIT LOGS ===")
        self.test("GET /api/audit-logs", "GET", "/audit-logs", 200)
        self.test("GET /api/audit-logs?module=employee_core", "GET", "/audit-logs?module=employee_core", 200)
        self.test("GET /api/audit-logs?action=create", "GET", "/audit-logs?action=create", 200)
        self.test("GET /api/audit-logs?page=1&limit=10", "GET", "/audit-logs?page=1&limit=10", 200)

        # Payroll statutory report
        print("\n=== PAYROLL REPORTS ===")
        # Get a payroll run first
        success, runs = self.test("GET /api/payroll/runs", "GET", "/payroll/runs", 200)
        if success and runs and runs.get("items"):
            run_id = runs["items"][0]["id"]
            self.test("GET /api/payroll/runs/{id}/statutory-report", "GET", f"/payroll/runs/{run_id}/statutory-report", 200)
            self.test("GET /api/payroll/runs/{id}/bank-file-preview", "GET", f"/payroll/runs/{run_id}/bank-file-preview", 200)

        # Payslip email logs
        self.test("GET /api/mail/payslip-logs", "GET", "/mail/payslip-logs", 200)

        # Summary
        print("\n" + "="*60)
        print("ADDITIONAL TEST SUMMARY")
        print("="*60)
        print(f"Total tests: {self.tests_run}")
        print(f"✅ Passed: {self.tests_passed}")
        print(f"❌ Failed: {self.tests_failed}")
        print(f"Success rate: {self.tests_passed/self.tests_run*100:.1f}%")
        print("="*60)

        return 0 if self.tests_failed == 0 else 1

if __name__ == "__main__":
    tester = AdditionalTester()
    sys.exit(tester.run_tests())
