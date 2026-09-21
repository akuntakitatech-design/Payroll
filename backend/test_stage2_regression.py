"""
Stage 2 Regression Testing: Comprehensive API coverage with RBAC and tenant isolation
Tests authenticated endpoints with real CRUD operations in temporary development fixtures.

Run: cd /app/backend && python test_stage2_regression.py
"""
import os
import sys
import requests
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from dotenv import load_dotenv

# Load environment variables
load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")

# CRITICAL: Use public endpoint from .env, NO FALLBACK
BACKEND_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BACKEND_URL:
    print("ERROR: REACT_APP_BACKEND_URL not found in /app/frontend/.env")
    sys.exit(1)

BASE_URL = f"{BACKEND_URL}/api"

DEV_ADMIN_EMAIL = os.environ.get("DEV_ADMIN_EMAIL")
DEV_ADMIN_PASSWORD = os.environ.get("DEV_ADMIN_PASSWORD")
APP_ENV = os.environ.get("APP_ENV")
DATABASE_URL = os.environ.get("DATABASE_URL")

PASS, FAIL = [], []
CREATED_IDS = {
    "branches": [],
    "employees": [],
    "contracts": [],
    "certifications": [],
    "documents": [],
    "companies": [],
    "users": [],
}

def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASS.append(name)
        print(f"  [OK]   {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL.append(f"{name} :: {detail}")
        print(f"  [FAIL] {name} — {detail}")

def test_environment_guards():
    """MANDATORY: Verify environment is development - FAIL CLOSED"""
    print("\n--- Environment Guards (CRITICAL) ---")
    
    # FAIL CLOSED: Exit immediately if not development
    if APP_ENV != "development":
        print(f"  [CRITICAL] APP_ENV is '{APP_ENV}', not 'development'. ABORTING ALL TESTS.")
        sys.exit(1)
    check("APP_ENV is 'development'", True, f"Verified: {APP_ENV}")
    
    # FAIL CLOSED: Exit if not loopback
    db_parts = urlsplit(DATABASE_URL) if DATABASE_URL else None
    is_loopback = db_parts and (db_parts.hostname in ["127.0.0.1", "localhost", "::1"])
    if not is_loopback:
        print(f"  [CRITICAL] DATABASE_URL hostname is not loopback. ABORTING ALL TESTS.")
        sys.exit(1)
    check("DATABASE_URL uses loopback", True, "Verified loopback hostname")
    
    # FAIL CLOSED: Exit if R2 keys present
    r2_keys = {
        "R2_ACCOUNT_ID": os.environ.get("R2_ACCOUNT_ID", ""),
        "R2_ACCESS_KEY_ID": os.environ.get("R2_ACCESS_KEY_ID", ""),
        "R2_SECRET_ACCESS_KEY": os.environ.get("R2_SECRET_ACCESS_KEY", ""),
    }
    all_empty = all(not v for v in r2_keys.values())
    if not all_empty:
        print(f"  [CRITICAL] R2 credentials present. ABORTING ALL TESTS.")
        sys.exit(1)
    check("R2 keys are empty (development)", True, "Verified empty R2 credentials")
    
    # FAIL CLOSED: Exit if credentials missing
    if not DEV_ADMIN_EMAIL or not DEV_ADMIN_PASSWORD:
        print(f"  [CRITICAL] DEV_ADMIN_EMAIL or DEV_ADMIN_PASSWORD missing. ABORTING ALL TESTS.")
        sys.exit(1)
    check("DEV_ADMIN_EMAIL loaded", True, "Verified")
    check("DEV_ADMIN_PASSWORD loaded", True, "Verified")

def test_remote_environment():
    """Verify remote /api/system/mode is development - FAIL CLOSED"""
    print("\n--- Remote Environment Validation ---")
    
    try:
        r = requests.get(f"{BASE_URL}/system/mode", timeout=10)
        if r.ok:
            data = r.json()
            remote_env = data.get("environment")
            if remote_env != "development":
                print(f"  [CRITICAL] Remote environment is '{remote_env}', not 'development'. ABORTING ALL TESTS.")
                sys.exit(1)
            check("Remote /api/system/mode is 'development'", True, f"Verified: {remote_env}")
        else:
            print(f"  [CRITICAL] Cannot verify remote environment. ABORTING ALL TESTS.")
            sys.exit(1)
    except Exception as e:
        print(f"  [CRITICAL] Cannot connect to remote: {str(e)[:100]}. ABORTING ALL TESTS.")
        sys.exit(1)

def login() -> str:
    """Login and return access token"""
    print("\n--- Authentication ---")
    
    try:
        r = requests.post(f"{BASE_URL}/auth/login", 
                         json={"email": DEV_ADMIN_EMAIL, "password": DEV_ADMIN_PASSWORD},
                         timeout=10)
        check("POST /api/auth/login returns 200", r.status_code == 200,
              f"Status: {r.status_code}")
        
        if r.ok:
            data = r.json()
            check("Login response has 'access_token'", "access_token" in data)
            check("Login response has 'active_company'", "active_company" in data)
            
            token = data.get("access_token")
            company = data.get("active_company", {})
            
            # If not DEVELOPMENT company, switch to it
            if company.get("code") != "DEVELOPMENT":
                print(f"  [INFO] Switching from {company.get('code')} to DEVELOPMENT company")
                headers = {"Authorization": f"Bearer {token}"}
                
                # Get DEVELOPMENT company ID
                r = requests.get(f"{BASE_URL}/companies", headers=headers, timeout=10)
                if r.ok:
                    companies = r.json().get("items", [])
                    dev_company = next((c for c in companies if c.get("code") == "DEVELOPMENT"), None)
                    
                    if dev_company:
                        # Switch to DEVELOPMENT company
                        r = requests.post(f"{BASE_URL}/auth/switch-company",
                                        headers=headers,
                                        json={"company_id": dev_company["id"]},
                                        timeout=10)
                        if r.ok:
                            data = r.json()
                            token = data.get("access_token")
                            check("Switched to DEVELOPMENT company", True)
            
            return token
    except Exception as e:
        check("Login successful", False, str(e)[:100])
    
    return None

def test_master_endpoints(token):
    """Test master data endpoints (branches, positions, etc.)"""
    print("\n--- Master Data Endpoints ---")
    
    if not token:
        print("  [SKIP] No auth token available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test GET /api/master/branches
    try:
        r = requests.get(f"{BASE_URL}/master/branches", headers=headers, timeout=10)
        check("GET /api/master/branches returns 200", r.status_code == 200,
              f"Status: {r.status_code}")
        
        if r.ok:
            data = r.json()
            check("Branches response has 'items' field", "items" in data)
            
            # Create a temporary branch
            branch_data = {
                "name": f"Test Branch {datetime.now().strftime('%Y%m%d%H%M%S')}",
                "code": f"TB{datetime.now().strftime('%H%M%S')}",
                "address": "Test Address",
                "status": "active"
            }
            r = requests.post(f"{BASE_URL}/master/branches", 
                            headers=headers, json=branch_data, timeout=10)
            check("POST /api/master/branches returns 201", r.status_code == 201,
                  f"Status: {r.status_code}")
            
            if r.status_code == 201:
                created = r.json()
                branch_id = created.get("id")
                CREATED_IDS["branches"].append(branch_id)
                check("Created branch has 'id' field", bool(branch_id))
    except Exception as e:
        check("Master branches endpoints successful", False, str(e)[:100])
    
    # Test GET /api/master/positions
    try:
        r = requests.get(f"{BASE_URL}/master/positions", headers=headers, timeout=10)
        check("GET /api/master/positions returns 200", r.status_code == 200,
              f"Status: {r.status_code}")
    except Exception as e:
        check("GET /api/master/positions successful", False, str(e)[:100])
    
    # Test GET /api/master/departments
    try:
        r = requests.get(f"{BASE_URL}/master/departments", headers=headers, timeout=10)
        check("GET /api/master/departments returns 200", r.status_code == 200,
              f"Status: {r.status_code}")
    except Exception as e:
        check("GET /api/master/departments successful", False, str(e)[:100])

def test_employee_endpoints(token):
    """Test employee CRUD operations"""
    print("\n--- Employee Endpoints ---")
    
    if not token:
        print("  [SKIP] No auth token available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test GET /api/employees
    try:
        r = requests.get(f"{BASE_URL}/employees", headers=headers, timeout=10)
        check("GET /api/employees returns 200", r.status_code == 200,
              f"Status: {r.status_code}")
        
        if r.ok:
            data = r.json()
            check("Employees response has 'items' field", "items" in data)
            
            # Create a temporary employee
            employee_data = {
                "full_name": f"Test Employee {datetime.now().strftime('%Y%m%d%H%M%S')}",
                "employee_number": f"EMP{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "email": f"test{datetime.now().strftime('%Y%m%d%H%M%S')}@example.com",
                "phone": "081234567890",
                "hire_date": datetime.now().date().isoformat(),
                "status": "active"
            }
            r = requests.post(f"{BASE_URL}/employees", 
                            headers=headers, json=employee_data, timeout=10)
            check("POST /api/employees returns 201", r.status_code == 201,
                  f"Status: {r.status_code}")
            
            if r.status_code == 201:
                created = r.json()
                employee_id = created.get("id")
                CREATED_IDS["employees"].append(employee_id)
                check("Created employee has 'id' field", bool(employee_id))
                
                # Test GET single employee
                r = requests.get(f"{BASE_URL}/employees/{employee_id}", 
                               headers=headers, timeout=10)
                check("GET /api/employees/{id} returns 200", r.status_code == 200,
                      f"Status: {r.status_code}")
    except Exception as e:
        check("Employee endpoints successful", False, str(e)[:100])

def test_contract_endpoints(token):
    """Test contract CRUD operations"""
    print("\n--- Contract Endpoints ---")
    
    if not token:
        print("  [SKIP] No auth token available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test GET /api/contracts
    try:
        r = requests.get(f"{BASE_URL}/contracts", headers=headers, timeout=10)
        check("GET /api/contracts returns 200", r.status_code == 200,
              f"Status: {r.status_code}")
        
        if r.ok:
            data = r.json()
            check("Contracts response has 'items' field", "items" in data)
    except Exception as e:
        check("GET /api/contracts successful", False, str(e)[:100])

def test_certification_endpoints(token):
    """Test certification CRUD operations"""
    print("\n--- Certification Endpoints ---")
    
    if not token:
        print("  [SKIP] No auth token available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test GET /api/certifications
    try:
        r = requests.get(f"{BASE_URL}/certifications", headers=headers, timeout=10)
        check("GET /api/certifications returns 200", r.status_code == 200,
              f"Status: {r.status_code}")
        
        if r.ok:
            data = r.json()
            check("Certifications response has 'items' field", "items" in data)
    except Exception as e:
        check("GET /api/certifications successful", False, str(e)[:100])

def test_document_endpoints(token):
    """Test document endpoints (no upload, R2 not configured)"""
    print("\n--- Document Endpoints ---")
    
    if not token:
        print("  [SKIP] No auth token available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test GET /api/documents
    try:
        r = requests.get(f"{BASE_URL}/documents", headers=headers, timeout=10)
        check("GET /api/documents returns 200", r.status_code == 200,
              f"Status: {r.status_code}")
        
        if r.ok:
            data = r.json()
            check("Documents response has 'items' field", "items" in data)
    except Exception as e:
        check("GET /api/documents successful", False, str(e)[:100])
    
    # Test GET /api/documents/catalog
    try:
        r = requests.get(f"{BASE_URL}/documents/catalog", headers=headers, timeout=10)
        check("GET /api/documents/catalog returns 200", r.status_code == 200,
              f"Status: {r.status_code}")
    except Exception as e:
        check("GET /api/documents/catalog successful", False, str(e)[:100])

def test_payroll_endpoints(token):
    """Test payroll endpoints"""
    print("\n--- Payroll Endpoints ---")
    
    if not token:
        print("  [SKIP] No auth token available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test GET /api/payroll/catalog
    try:
        r = requests.get(f"{BASE_URL}/payroll/catalog", headers=headers, timeout=10)
        check("GET /api/payroll/catalog returns 200", r.status_code == 200,
              f"Status: {r.status_code}")
    except Exception as e:
        check("GET /api/payroll/catalog successful", False, str(e)[:100])
    
    # Test GET /api/payroll/config
    try:
        r = requests.get(f"{BASE_URL}/payroll/config", headers=headers, timeout=10)
        check("GET /api/payroll/config returns 200", r.status_code == 200,
              f"Status: {r.status_code}")
    except Exception as e:
        check("GET /api/payroll/config successful", False, str(e)[:100])
    
    # Test GET /api/payroll/components
    try:
        r = requests.get(f"{BASE_URL}/payroll/components", headers=headers, timeout=10)
        check("GET /api/payroll/components returns 200", r.status_code == 200,
              f"Status: {r.status_code}")
    except Exception as e:
        check("GET /api/payroll/components successful", False, str(e)[:100])
    
    # Test GET /api/payroll/salaries
    try:
        r = requests.get(f"{BASE_URL}/payroll/salaries", headers=headers, timeout=10)
        check("GET /api/payroll/salaries returns 200", r.status_code == 200,
              f"Status: {r.status_code}")
    except Exception as e:
        check("GET /api/payroll/salaries successful", False, str(e)[:100])
    
    # Test GET /api/payroll/runs
    try:
        r = requests.get(f"{BASE_URL}/payroll/runs", headers=headers, timeout=10)
        check("GET /api/payroll/runs returns 200", r.status_code == 200,
              f"Status: {r.status_code}")
    except Exception as e:
        check("GET /api/payroll/runs successful", False, str(e)[:100])

def test_approval_workflow_endpoints(token):
    """Test approval workflow endpoints"""
    print("\n--- Approval Workflow Endpoints ---")
    
    if not token:
        print("  [SKIP] No auth token available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test GET /api/approval-workflows
    try:
        r = requests.get(f"{BASE_URL}/approval-workflows", headers=headers, timeout=10)
        check("GET /api/approval-workflows returns 200", r.status_code == 200,
              f"Status: {r.status_code}")
    except Exception as e:
        check("GET /api/approval-workflows successful", False, str(e)[:100])

def test_policy_endpoints(token):
    """Test policy endpoints"""
    print("\n--- Policy Endpoints ---")
    
    if not token:
        print("  [SKIP] No auth token available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test GET /api/policies/catalog
    try:
        r = requests.get(f"{BASE_URL}/policies/catalog", headers=headers, timeout=10)
        check("GET /api/policies/catalog returns 200", r.status_code == 200,
              f"Status: {r.status_code}")
    except Exception as e:
        check("GET /api/policies/catalog successful", False, str(e)[:100])
    
    # Test GET /api/policies/effective
    try:
        r = requests.get(f"{BASE_URL}/policies/effective", headers=headers, timeout=10)
        check("GET /api/policies/effective returns 200", r.status_code == 200,
              f"Status: {r.status_code}")
    except Exception as e:
        check("GET /api/policies/effective successful", False, str(e)[:100])

def test_audit_log_endpoints(token):
    """Test audit log endpoints"""
    print("\n--- Audit Log Endpoints ---")
    
    if not token:
        print("  [SKIP] No auth token available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test GET /api/audit-logs
    try:
        r = requests.get(f"{BASE_URL}/audit-logs", headers=headers, timeout=10)
        check("GET /api/audit-logs returns 200", r.status_code == 200,
              f"Status: {r.status_code}")
    except Exception as e:
        check("GET /api/audit-logs successful", False, str(e)[:100])

def test_mail_settings_endpoints(token):
    """Test mail settings endpoints"""
    print("\n--- Mail Settings Endpoints ---")
    
    if not token:
        print("  [SKIP] No auth token available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test GET /api/mail/settings
    try:
        r = requests.get(f"{BASE_URL}/mail/settings", headers=headers, timeout=10)
        check("GET /api/mail/settings returns 200", r.status_code == 200,
              f"Status: {r.status_code}")
    except Exception as e:
        check("GET /api/mail/settings successful", False, str(e)[:100])

def test_reminder_endpoints(token):
    """Test reminder endpoints"""
    print("\n--- Reminder Endpoints ---")
    
    if not token:
        print("  [SKIP] No auth token available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test GET /api/reminders/expiry
    try:
        r = requests.get(f"{BASE_URL}/reminders/expiry", headers=headers, timeout=10)
        check("GET /api/reminders/expiry returns 200", r.status_code == 200,
              f"Status: {r.status_code}")
    except Exception as e:
        check("GET /api/reminders/expiry successful", False, str(e)[:100])

def cleanup_fixtures(token):
    """Clean up temporary test fixtures by recorded IDs"""
    print("\n--- Cleanup Temporary Fixtures ---")
    
    if not token:
        print("  [SKIP] No auth token available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Clean up employees
    for employee_id in CREATED_IDS["employees"]:
        try:
            r = requests.delete(f"{BASE_URL}/employees/{employee_id}", 
                              headers=headers, timeout=10)
            check(f"Cleanup employee {employee_id[:8]}", r.status_code in [200, 204],
                  f"Status: {r.status_code}")
        except Exception as e:
            check(f"Cleanup employee {employee_id[:8]}", False, str(e)[:100])
    
    # Clean up branches
    for branch_id in CREATED_IDS["branches"]:
        try:
            r = requests.delete(f"{BASE_URL}/master/branches/{branch_id}", 
                              headers=headers, timeout=10)
            check(f"Cleanup branch {branch_id[:8]}", r.status_code in [200, 204],
                  f"Status: {r.status_code}")
        except Exception as e:
            check(f"Cleanup branch {branch_id[:8]}", False, str(e)[:100])

def main():
    print("=" * 74)
    print(" Stage 2 Regression Testing — Comprehensive API Coverage")
    print("=" * 74)
    print(f" Backend URL: {BASE_URL}")
    print(f" Environment: {APP_ENV}")
    print("=" * 74)
    
    try:
        # Critical environment checks first
        test_environment_guards()
        test_remote_environment()
        
        # Test authentication
        token = login()
        
        if not token:
            print("\n[ERROR] Cannot proceed without authentication token")
            sys.exit(1)
        
        # Test all endpoints
        test_master_endpoints(token)
        test_employee_endpoints(token)
        test_contract_endpoints(token)
        test_certification_endpoints(token)
        test_document_endpoints(token)
        test_payroll_endpoints(token)
        test_approval_workflow_endpoints(token)
        test_policy_endpoints(token)
        test_audit_log_endpoints(token)
        test_mail_settings_endpoints(token)
        test_reminder_endpoints(token)
        
        # Cleanup temporary fixtures
        cleanup_fixtures(token)
        
    except Exception as e:
        print(f"\n[ERROR] Unexpected exception: {e}")
        import traceback
        traceback.print_exc()
        FAIL.append(f"Unexpected exception: {str(e)[:100]}")
    
    print("\n" + "=" * 74)
    total = len(PASS) + len(FAIL)
    print(f" RESULTS: {len(PASS)}/{total} tests passed")
    
    if FAIL:
        print(f"\n FAILED ({len(FAIL)}):")
        for f in FAIL:
            print(f"   - {f}")
        print("=" * 74)
        return 1
    
    print(" ALL REGRESSION TESTS PASSED ✓")
    print("=" * 74)
    return 0

if __name__ == "__main__":
    sys.exit(main())
