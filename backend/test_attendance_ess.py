"""Comprehensive Attendance ESS API Testing for HRIS & Payroll.

Tests all attendance module scenarios as specified in the review request.
"""
import requests
import sys
import uuid
from typing import Dict, Optional, Tuple

BASE_URL = "https://repo-clone-setup-1.preview.emergentagent.com/api"
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

def _demo_password() -> str:
    """Kata sandi akun demo: dari env DEMO_PASSWORD, atau konstanta seed (tidak ditulis ulang di sini)."""
    value = _os.environ.get("DEMO_PASSWORD")
    if value:
        return value
    from app.seed import DEMO_PASSWORD
    return DEMO_PASSWORD

PASSWORD = _demo_password()

# Test accounts
ACCOUNTS = {
    "rina": "karyawan@nep.co.id",  # NEP-0001, LOC-HO Jakarta
    "bambang": "supervisor@nep.co.id",  # NEP-0002, LOC-SITE1 Sangatta
    "hr_admin_nep": "hr.admin@nep.co.id",
    "hr_manager_nep": "hr.manager@nep.co.id",
    "hr_admin_kbs": "hr.admin@kbs.co.id",
    "karyawan_kbs": "karyawan@kbs.co.id",  # KBS-0001
}


class AttendanceAPITester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.tokens: Dict[str, str] = {}
        self.test_data: Dict[str, any] = {}

    def log(self, message: str, level: str = "INFO"):
        prefix = {"INFO": "ℹ️", "PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}.get(level, "•")
        print(f"{prefix} {message}")

    def test(
        self,
        name: str,
        method: str,
        endpoint: str,
        expected_status: int,
        token: Optional[str] = None,
        data: Optional[Dict] = None,
    ) -> Tuple[bool, Optional[Dict]]:
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
                response = requests.post(url, headers=headers, json=data, timeout=30)
            elif method == "PUT":
                response = requests.put(url, headers=headers, json=data, timeout=30)
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
                except ValueError:
                    self.log(f"Response: {response.text[:200]}", "FAIL")

            try:
                return success, response.json() if response.text else {}
            except ValueError:
                return success, {}

        except Exception as e:
            self.tests_failed += 1
            self.log(f"FAIL - Exception: {str(e)}", "FAIL")
            return False, {}

    def login(self, email: str, password: str = PASSWORD) -> Optional[str]:
        """Login and return access token."""
        success, response = self.test(
            f"Login as {email}", "POST", "/auth/login", 200, data={"email": email, "password": password}
        )
        if success and response and "access_token" in response:
            token = response["access_token"]
            self.tokens[email] = token
            return token
        return None

    def check_field(self, data: Dict, field: str, expected_value=None, should_exist=True) -> bool:
        """Check if a field exists and optionally matches expected value."""
        exists = field in data
        if should_exist and not exists:
            self.log(f"FAIL - Field '{field}' not found in response", "FAIL")
            self.tests_failed += 1
            return False
        if expected_value is not None and data.get(field) != expected_value:
            self.log(f"FAIL - Field '{field}' = {data.get(field)}, expected {expected_value}", "FAIL")
            self.tests_failed += 1
            return False
        self.tests_passed += 1
        self.log(f"PASS - Field '{field}' check passed", "PASS")
        return True

    def test_rina_check_in(self):
        """TEST 1: Rina check-in inside radius."""
        self.log("\n=== TEST 1: Rina Check-In (Inside Radius) ===", "INFO")
        
        token = self.tokens.get(ACCOUNTS["rina"]) or self.login(ACCOUNTS["rina"])
        if not token:
            return False

        # Get today status
        success, today = self.test("GET /attendance/me/today", "GET", "/attendance/me/today", 200, token=token)
        if not success:
            return False

        # Verify today status
        self.check_field(today, "linked", True)
        self.check_field(today, "has_schedule", True)
        self.check_field(today, "can_check_in", True)
        
        if today.get("shift"):
            self.check_field(today["shift"], "start_time", "08:00")
        if today.get("work_location"):
            self.check_field(today["work_location"], "code", "LOC-HO")

        # Check-in inside radius
        client_request_id = str(uuid.uuid4())
        success, check_in_response = self.test(
            "POST /attendance/check-in (inside radius)",
            "POST",
            "/attendance/check-in",
            200,
            token=token,
            data={
                "latitude": -6.2267,
                "longitude": 106.8097,
                "accuracy": 12,
                "source": "web",
                "client_request_id": client_request_id,
            },
        )

        if success and check_in_response:
            att = check_in_response.get("attendance", {})
            self.test_data["rina_attendance_id"] = att.get("id")
            self.test_data["rina_check_in_request_id"] = client_request_id
            
            self.check_field(att, "check_in_geofence_result", "inside")
            self.check_field(att, "location_approval_status", "not_required")
            self.check_field(att, "attendance_status", "no_check_out")
            
            # Verify late_minutes > 0 (current time is after 08:15)
            if att.get("late_minutes", 0) > 0:
                self.log(f"PASS - late_minutes = {att.get('late_minutes')} (expected > 0)", "PASS")
                self.tests_passed += 1
            else:
                self.log(f"FAIL - late_minutes = {att.get('late_minutes')}, expected > 0", "FAIL")
                self.tests_failed += 1

        return True

    def test_idempotency(self):
        """TEST 5: Idempotency & double check-in protection."""
        self.log("\n=== TEST 5: Idempotency & Double Check-In ===", "INFO")
        
        token = self.tokens.get(ACCOUNTS["rina"])
        if not token:
            return False

        # Retry with same client_request_id
        success, response = self.test(
            "POST check-in with same client_request_id (idempotent)",
            "POST",
            "/attendance/check-in",
            200,
            token=token,
            data={
                "latitude": -6.2267,
                "longitude": 106.8097,
                "accuracy": 12,
                "source": "web",
                "client_request_id": self.test_data.get("rina_check_in_request_id"),
            },
        )

        if success and response:
            self.check_field(response, "idempotent", True)
            att = response.get("attendance", {})
            if att.get("id") == self.test_data.get("rina_attendance_id"):
                self.log("PASS - Same attendance ID returned (idempotent)", "PASS")
                self.tests_passed += 1
            else:
                self.log("FAIL - Different attendance ID returned", "FAIL")
                self.tests_failed += 1

        # Try check-in with new client_request_id (should be 409)
        self.test(
            "POST check-in with new client_request_id (should be 409)",
            "POST",
            "/attendance/check-in",
            409,
            token=token,
            data={
                "latitude": -6.2267,
                "longitude": 106.8097,
                "accuracy": 12,
                "source": "web",
                "client_request_id": str(uuid.uuid4()),
            },
        )

        # Verify no duplicate in database
        success, att_list = self.test(
            "GET /attendance (verify no duplicate)",
            "GET",
            f"/attendance?work_date=2026-09-21&employee_id={self.test_data.get('rina_employee_id', '')}",
            200,
            token=self.tokens.get(ACCOUNTS["hr_admin_nep"]) or self.login(ACCOUNTS["hr_admin_nep"]),
        )

        if success and att_list:
            total = att_list.get("total", 0)
            if total == 1:
                self.log(f"PASS - Only 1 attendance record found (no duplicate)", "PASS")
                self.tests_passed += 1
            else:
                self.log(f"FAIL - Found {total} attendance records, expected 1", "FAIL")
                self.tests_failed += 1

        return True

    def test_rina_check_out(self):
        """TEST 3: Rina check-out inside radius."""
        self.log("\n=== TEST 3: Rina Check-Out (Inside Radius) ===", "INFO")
        
        token = self.tokens.get(ACCOUNTS["rina"])
        if not token:
            return False

        # Verify can_check_out
        success, today = self.test("GET /attendance/me/today", "GET", "/attendance/me/today", 200, token=token)
        if success:
            self.check_field(today, "can_check_out", True)
            self.check_field(today, "can_check_in", False)

        # Check-out
        client_request_id = str(uuid.uuid4())
        success, response = self.test(
            "POST /attendance/check-out",
            "POST",
            "/attendance/check-out",
            200,
            token=token,
            data={
                "latitude": -6.2267,
                "longitude": 106.8097,
                "accuracy": 12,
                "source": "web",
                "client_request_id": client_request_id,
            },
        )

        if success and response:
            att = response.get("attendance", {})
            self.test_data["rina_check_out_request_id"] = client_request_id
            
            self.check_field(att, "check_out_geofence_result", "inside")
            
            # Verify actual_work_minutes is integer >= 0
            if isinstance(att.get("actual_work_minutes"), int) and att.get("actual_work_minutes", -1) >= 0:
                self.log(f"PASS - actual_work_minutes = {att.get('actual_work_minutes')} (integer >= 0)", "PASS")
                self.tests_passed += 1
            else:
                self.log(f"FAIL - actual_work_minutes = {att.get('actual_work_minutes')}", "FAIL")
                self.tests_failed += 1

            # Verify attendance_status is one of the valid statuses
            valid_statuses = ["present", "late", "early_leave", "late_and_early_leave"]
            if att.get("attendance_status") in valid_statuses:
                self.log(f"PASS - attendance_status = {att.get('attendance_status')}", "PASS")
                self.tests_passed += 1
            else:
                self.log(f"FAIL - attendance_status = {att.get('attendance_status')}, expected one of {valid_statuses}", "FAIL")
                self.tests_failed += 1

        # Test idempotency
        success, response = self.test(
            "POST check-out with same client_request_id (idempotent)",
            "POST",
            "/attendance/check-out",
            200,
            token=token,
            data={
                "latitude": -6.2267,
                "longitude": 106.8097,
                "accuracy": 12,
                "source": "web",
                "client_request_id": client_request_id,
            },
        )

        if success and response:
            self.check_field(response, "idempotent", True)

        # Try check-out again with new ID (should be 409)
        self.test(
            "POST check-out again (should be 409)",
            "POST",
            "/attendance/check-out",
            409,
            token=token,
            data={
                "latitude": -6.2267,
                "longitude": 106.8097,
                "accuracy": 12,
                "source": "web",
                "client_request_id": str(uuid.uuid4()),
            },
        )

        # Verify final status
        success, today = self.test("GET /attendance/me/today (final)", "GET", "/attendance/me/today", 200, token=token)
        if success:
            self.check_field(today, "can_check_in", False)
            self.check_field(today, "can_check_out", False)

        return True

    def test_bambang_no_check_in(self):
        """TEST 6: Bambang check-out without check-in."""
        self.log("\n=== TEST 6: Bambang Check-Out Without Check-In ===", "INFO")
        
        token = self.tokens.get(ACCOUNTS["bambang"]) or self.login(ACCOUNTS["bambang"])
        if not token:
            return False

        # Try check-out without check-in (should be 409)
        self.test(
            "POST check-out without check-in (should be 409)",
            "POST",
            "/attendance/check-out",
            409,
            token=token,
            data={
                "latitude": 0.52,
                "longitude": 117.54,
                "accuracy": 8,
                "source": "web",
                "client_request_id": str(uuid.uuid4()),
            },
        )

        return True

    def test_gps_failed(self):
        """TEST 12: GPS failed - no lat/lng."""
        self.log("\n=== TEST 12: GPS Failed (No Lat/Lng) ===", "INFO")
        
        # Use a fresh account that hasn't checked in yet
        token = self.tokens.get(ACCOUNTS["bambang"])
        if not token:
            return False

        # Try check-in without GPS data (should be 422)
        self.test(
            "POST check-in without lat/lng (should be 422)",
            "POST",
            "/attendance/check-in",
            422,
            token=token,
            data={
                "source": "web",
                "client_request_id": str(uuid.uuid4()),
            },
        )

        return True

    def test_bambang_outside_radius(self):
        """TEST 8: Bambang check-in outside radius."""
        self.log("\n=== TEST 8: Bambang Check-In Outside Radius ===", "INFO")
        
        token = self.tokens.get(ACCOUNTS["bambang"])
        if not token:
            return False

        # Try check-in outside radius without reason_code (should be 422)
        self.test(
            "POST check-in outside radius without reason_code (should be 422)",
            "POST",
            "/attendance/check-in",
            422,
            token=token,
            data={
                "latitude": 0.57,
                "longitude": 117.54,
                "accuracy": 8,
                "source": "web",
                "client_request_id": str(uuid.uuid4()),
            },
        )

        # Try with reason_code='other' but no reason text (should be 422)
        self.test(
            "POST check-in with reason_code='other' but no reason (should be 422)",
            "POST",
            "/attendance/check-in",
            422,
            token=token,
            data={
                "latitude": 0.57,
                "longitude": 117.54,
                "accuracy": 8,
                "reason_code": "other",
                "source": "web",
                "client_request_id": str(uuid.uuid4()),
            },
        )

        # Check-in with proper reason_code and reason
        success, response = self.test(
            "POST check-in outside radius with reason",
            "POST",
            "/attendance/check-in",
            200,
            token=token,
            data={
                "latitude": 0.57,
                "longitude": 117.54,
                "accuracy": 8,
                "reason_code": "business_trip",
                "reason": "Dinas klien",
                "source": "web",
                "client_request_id": str(uuid.uuid4()),
            },
        )

        if success and response:
            att = response.get("attendance", {})
            self.test_data["bambang_attendance_id"] = att.get("id")
            
            self.check_field(att, "attendance_status", "awaiting_location_approval")
            self.check_field(att, "location_approval_for", "check_in")
            self.check_field(att, "check_in_geofence_result", "outside")
            
            # Verify distance > 1000m
            if att.get("check_in_distance_meter", 0) > 1000:
                self.log(f"PASS - check_in_distance_meter = {att.get('check_in_distance_meter')} (> 1000)", "PASS")
                self.tests_passed += 1
            else:
                self.log(f"FAIL - check_in_distance_meter = {att.get('check_in_distance_meter')}", "FAIL")
                self.tests_failed += 1

        return True

    def test_approval_workflow(self):
        """TEST 9: Approve Bambang's location."""
        self.log("\n=== TEST 9: Approval Workflow ===", "INFO")
        
        # Login as supervisor (Bambang is his own supervisor)
        supervisor_token = self.tokens.get(ACCOUNTS["bambang"])
        if not supervisor_token:
            return False

        # Get pending approvals
        success, approvals = self.test(
            "GET /attendance/approvals (supervisor)",
            "GET",
            "/attendance/approvals?document_kind=attendance_location",
            200,
            token=supervisor_token,
        )

        if success and approvals:
            items = approvals.get("items", [])
            if len(items) > 0:
                approval_item = items[0]
                detail = approval_item.get("detail", {})
                
                # Verify detail fields
                self.check_field(detail, "approval_for_label")
                self.check_field(detail, "check_in_latitude")
                self.check_field(detail, "map_url")
                self.check_field(detail, "location_reason_label")
                self.check_field(detail, "timezone", "Asia/Makassar")
                
                # Approve
                approval_id = approval_item.get("approval", {}).get("id")
                if approval_id:
                    success, _ = self.test(
                        "POST /attendance/approvals/{id}/decide (approve)",
                        "POST",
                        f"/attendance/approvals/{approval_id}/decide",
                        200,
                        token=supervisor_token,
                        data={"decision": "approved", "notes": "Approved by supervisor"},
                    )

        # Login as HR admin for 2nd approval
        hr_token = self.tokens.get(ACCOUNTS["hr_admin_nep"]) or self.login(ACCOUNTS["hr_admin_nep"])
        
        # Get pending approvals for HR
        success, approvals = self.test(
            "GET /attendance/approvals (HR admin)",
            "GET",
            "/attendance/approvals?document_kind=attendance_location",
            200,
            token=hr_token,
        )

        if success and approvals:
            items = approvals.get("items", [])
            if len(items) > 0:
                approval_id = items[0].get("approval", {}).get("id")
                if approval_id:
                    success, _ = self.test(
                        "POST /attendance/approvals/{id}/decide (HR approve)",
                        "POST",
                        f"/attendance/approvals/{approval_id}/decide",
                        200,
                        token=hr_token,
                        data={"decision": "approved", "notes": "Approved by HR"},
                    )

        # Verify final status
        if self.test_data.get("bambang_attendance_id"):
            success, att_detail = self.test(
                "GET /attendance/{id} (verify approved)",
                "GET",
                f"/attendance/{self.test_data['bambang_attendance_id']}",
                200,
                token=hr_token,
            )

            if success and att_detail:
                self.check_field(att_detail, "location_approval_status", "approved")
                
                # Verify attendance_status is NOT awaiting_location_approval
                if att_detail.get("attendance_status") != "awaiting_location_approval":
                    self.log(f"PASS - attendance_status = {att_detail.get('attendance_status')} (not awaiting)", "PASS")
                    self.tests_passed += 1
                else:
                    self.log("FAIL - attendance_status still awaiting_location_approval", "FAIL")
                    self.tests_failed += 1

        # Test negative: karyawan@nep tries to decide Bambang's approval (should be 403)
        rina_token = self.tokens.get(ACCOUNTS["rina"])
        if rina_token and approval_id:
            self.test(
                "POST decide approval as karyawan (should be 403)",
                "POST",
                f"/attendance/approvals/{approval_id}/decide",
                403,
                token=rina_token,
                data={"decision": "approved"},
            )

        # Test tenant isolation: hr.admin@kbs tries to decide NEP approval (should be 404)
        kbs_hr_token = self.tokens.get(ACCOUNTS["hr_admin_kbs"]) or self.login(ACCOUNTS["hr_admin_kbs"])
        if kbs_hr_token and approval_id:
            self.test(
                "POST decide approval as KBS HR (should be 404)",
                "POST",
                f"/attendance/approvals/{approval_id}/decide",
                404,
                token=kbs_hr_token,
                data={"decision": "approved"},
            )

        return True

    def test_tenant_isolation(self):
        """TEST 14: Tenant isolation."""
        self.log("\n=== TEST 14: Tenant Isolation ===", "INFO")
        
        kbs_hr_token = self.tokens.get(ACCOUNTS["hr_admin_kbs"]) or self.login(ACCOUNTS["hr_admin_kbs"])
        if not kbs_hr_token:
            return False

        # KBS HR tries to access NEP attendance (should be 404)
        if self.test_data.get("rina_attendance_id"):
            self.test(
                "GET NEP attendance as KBS HR (should be 404)",
                "GET",
                f"/attendance/{self.test_data['rina_attendance_id']}",
                404,
                token=kbs_hr_token,
            )

        # KBS HR GET /attendance should not contain NEP employees
        success, att_list = self.test(
            "GET /attendance as KBS HR",
            "GET",
            "/attendance?work_date=2026-09-21",
            200,
            token=kbs_hr_token,
        )

        if success and att_list:
            items = att_list.get("items", [])
            nep_items = [item for item in items if "NEP-" in item.get("employee_number", "")]
            if len(nep_items) == 0:
                self.log("PASS - No NEP employees in KBS attendance list", "PASS")
                self.tests_passed += 1
            else:
                self.log(f"FAIL - Found {len(nep_items)} NEP employees in KBS list", "FAIL")
                self.tests_failed += 1

        # KBS HR GET /attendance/approvals should not contain NEP records
        success, approvals = self.test(
            "GET /attendance/approvals as KBS HR",
            "GET",
            "/attendance/approvals?document_kind=attendance_location",
            200,
            token=kbs_hr_token,
        )

        if success and approvals:
            items = approvals.get("items", [])
            nep_items = [item for item in items if "NEP-" in item.get("detail", {}).get("employee_number", "")]
            if len(nep_items) == 0:
                self.log("PASS - No NEP approvals in KBS list", "PASS")
                self.tests_passed += 1
            else:
                self.log(f"FAIL - Found {len(nep_items)} NEP approvals in KBS list", "FAIL")
                self.tests_failed += 1

        # karyawan@kbs GET /attendance/me/today should return KBS employee
        kbs_emp_token = self.tokens.get(ACCOUNTS["karyawan_kbs"]) or self.login(ACCOUNTS["karyawan_kbs"])
        if kbs_emp_token:
            success, today = self.test(
                "GET /attendance/me/today as KBS employee",
                "GET",
                "/attendance/me/today",
                200,
                token=kbs_emp_token,
            )

            if success and today:
                self.check_field(today, "linked", True)
                emp = today.get("employee", {})
                if "KBS-" in emp.get("employee_number", ""):
                    self.log(f"PASS - KBS employee {emp.get('employee_number')}", "PASS")
                    self.tests_passed += 1
                else:
                    self.log(f"FAIL - Not a KBS employee: {emp.get('employee_number')}", "FAIL")
                    self.tests_failed += 1

        return True

    def test_employee_scope(self):
        """TEST 15: Employee scope restrictions."""
        self.log("\n=== TEST 15: Employee Scope Restrictions ===", "INFO")
        
        rina_token = self.tokens.get(ACCOUNTS["rina"])
        if not rina_token:
            return False

        # karyawan@nep GET /attendance should only return Rina's records
        success, att_list = self.test(
            "GET /attendance as karyawan (scoped)",
            "GET",
            "/attendance?work_date=2026-09-21",
            200,
            token=rina_token,
        )

        if success and att_list:
            items = att_list.get("items", [])
            # All items should be Rina's (NEP-0001)
            non_rina = [item for item in items if item.get("employee_number") != "NEP-0001"]
            if len(non_rina) == 0:
                self.log(f"PASS - Only Rina's records returned ({len(items)} items)", "PASS")
                self.tests_passed += 1
            else:
                self.log(f"FAIL - Found {len(non_rina)} non-Rina records", "FAIL")
                self.tests_failed += 1

        # karyawan@nep GET /schedules should only return Rina's schedules
        success, schedules = self.test(
            "GET /schedules as karyawan (scoped)",
            "GET",
            "/schedules?period=2026-09",
            200,
            token=rina_token,
        )

        if success and schedules:
            items = schedules.get("items", [])
            non_rina = [item for item in items if item.get("employee_number") != "NEP-0001"]
            if len(non_rina) == 0:
                self.log(f"PASS - Only Rina's schedules returned", "PASS")
                self.tests_passed += 1
            else:
                self.log(f"FAIL - Found {len(non_rina)} non-Rina schedules", "FAIL")
                self.tests_failed += 1

        # karyawan@nep tries to access Bambang's attendance (should be 404)
        if self.test_data.get("bambang_attendance_id"):
            self.test(
                "GET Bambang's attendance as karyawan (should be 404)",
                "GET",
                f"/attendance/{self.test_data['bambang_attendance_id']}",
                404,
                token=rina_token,
            )

        # karyawan@nep tries to POST /schedules/bulk (should be 403)
        self.test(
            "POST /schedules/bulk as karyawan (should be 403)",
            "POST",
            "/schedules/bulk",
            403,
            token=rina_token,
            data={
                "employee_ids": ["some-id"],
                "date_from": "2026-09-22",
                "date_to": "2026-09-22",
                "shift_id": "some-shift",
            },
        )

        # karyawan@nep tries to POST /attendance/manual (should be 403)
        self.test(
            "POST /attendance/manual as karyawan (should be 403)",
            "POST",
            "/attendance/manual",
            403,
            token=rina_token,
            data={
                "employee_id": "some-id",
                "work_date": "2026-09-22",
                "reason": "test",
            },
        )

        # karyawan@nep tries to GET /attendance/imports/template (should be 403)
        self.test(
            "GET /attendance/imports/template as karyawan (should be 403)",
            "GET",
            "/attendance/imports/template",
            403,
            token=rina_token,
        )

        # Verify GET /attendance/me returns only Rina's items with work_location_name & timezone
        success, my_att = self.test(
            "GET /attendance/me as karyawan",
            "GET",
            "/attendance/me?period=2026-09",
            200,
            token=rina_token,
        )

        if success and my_att:
            items = my_att.get("items", [])
            if len(items) > 0:
                first_item = items[0]
                self.check_field(first_item, "work_location_name")
                self.check_field(first_item, "timezone")
                self.check_field(first_item, "employee_number", "NEP-0001")

        return True

    def run_all_tests(self):
        """Run all test suites."""
        self.log("\n" + "=" * 60, "INFO")
        self.log("ATTENDANCE ESS MODULE - BACKEND API TESTING", "INFO")
        self.log("=" * 60 + "\n", "INFO")

        try:
            # Run tests in sequence
            self.test_rina_check_in()
            self.test_idempotency()
            self.test_rina_check_out()
            self.test_bambang_no_check_in()
            self.test_gps_failed()
            self.test_bambang_outside_radius()
            self.test_approval_workflow()
            self.test_tenant_isolation()
            self.test_employee_scope()

        except Exception as e:
            self.log(f"Test suite error: {str(e)}", "FAIL")
            import traceback
            traceback.print_exc()

        # Print summary
        self.log("\n" + "=" * 60, "INFO")
        self.log("TEST SUMMARY", "INFO")
        self.log("=" * 60, "INFO")
        self.log(f"Total tests: {self.tests_run}", "INFO")
        self.log(f"Passed: {self.tests_passed}", "PASS")
        self.log(f"Failed: {self.tests_failed}", "FAIL")
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        self.log(f"Success rate: {success_rate:.1f}%", "INFO")
        self.log("=" * 60 + "\n", "INFO")

        return self.tests_failed == 0


def main():
    tester = AttendanceAPITester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
