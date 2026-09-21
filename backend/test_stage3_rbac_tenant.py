"""
Stage 3 RBAC & Tenant Isolation Testing
Tests role-based access control and multi-tenant data isolation.

Run: cd /app/backend && python test_stage3_rbac_tenant.py
"""
import os
import sys
import requests
import secrets
from datetime import datetime
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
    "companies": [],
    "users": [],
    "employees": [],
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
    
    if APP_ENV != "development":
        print(f"  [CRITICAL] APP_ENV is '{APP_ENV}', not 'development'. ABORTING ALL TESTS.")
        sys.exit(1)
    check("APP_ENV is 'development'", True, f"Verified: {APP_ENV}")
    
    db_parts = urlsplit(DATABASE_URL) if DATABASE_URL else None
    is_loopback = db_parts and (db_parts.hostname in ["127.0.0.1", "localhost", "::1"])
    if not is_loopback:
        print(f"  [CRITICAL] DATABASE_URL hostname is not loopback. ABORTING ALL TESTS.")
        sys.exit(1)
    check("DATABASE_URL uses loopback", True, "Verified loopback hostname")
    
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

def admin_login() -> tuple:
    """Login as admin and return (token, company_id)"""
    print("\n--- Admin Authentication ---")
    
    try:
        r = requests.post(f"{BASE_URL}/auth/login", 
                         json={"email": DEV_ADMIN_EMAIL, "password": DEV_ADMIN_PASSWORD},
                         timeout=10)
        check("Admin login returns 200", r.status_code == 200,
              f"Status: {r.status_code}")
        
        if r.ok:
            data = r.json()
            token = data.get("access_token")
            company_id = data.get("active_company", {}).get("id")
            check("Admin has access_token", bool(token))
            check("Admin has active_company", bool(company_id))
            return token, company_id
    except Exception as e:
        check("Admin login successful", False, str(e)[:100])
    
    return None, None

def create_second_company(admin_token) -> str:
    """Create a temporary second company for tenant isolation testing"""
    print("\n--- Create Second Company ---")
    
    if not admin_token:
        print("  [SKIP] No admin token available")
        return None
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    
    company_data = {
        "name": f"Test Company {timestamp}",
        "code": f"TC{timestamp[-6:]}",
        "email": f"test{timestamp}@example.com",
        "phone": "081234567890",
        "address": "Test Address",
        "status": "active"
    }
    
    try:
        r = requests.post(f"{BASE_URL}/companies", 
                        headers=headers, json=company_data, timeout=10)
        check("POST /api/companies returns 201", r.status_code == 201,
              f"Status: {r.status_code}")
        
        if r.status_code == 201:
            created = r.json()
            company_id = created.get("id")
            CREATED_IDS["companies"].append(company_id)
            check("Second company created", bool(company_id), f"ID: {company_id[:8]}")
            return company_id
    except Exception as e:
        check("Create second company successful", False, str(e)[:100])
    
    return None

def create_low_priv_user(admin_token, company_id) -> tuple:
    """Create a temporary low-privilege user (employee role) for RBAC testing"""
    print("\n--- Create Low-Privilege User ---")
    
    if not admin_token or not company_id:
        print("  [SKIP] No admin token or company_id available")
        return None, None
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    random_password = secrets.token_urlsafe(16)
    
    user_data = {
        "email": f"lowpriv{timestamp}@example.com",
        "password": random_password,
        "full_name": f"Low Priv User {timestamp}",
        "role": "employee",
        "company_id": company_id,
        "status": "active"
    }
    
    try:
        r = requests.post(f"{BASE_URL}/users", 
                        headers=headers, json=user_data, timeout=10)
        check("POST /api/users returns 201", r.status_code == 201,
              f"Status: {r.status_code}")
        
        if r.status_code == 201:
            created = r.json()
            user_id = created.get("id")
            CREATED_IDS["users"].append(user_id)
            check("Low-priv user created", bool(user_id), f"ID: {user_id[:8]}")
            return user_data["email"], random_password
    except Exception as e:
        check("Create low-priv user successful", False, str(e)[:100])
    
    return None, None

def lowpriv_login(email, password) -> str:
    """Login as low-privilege user and return token"""
    print("\n--- Low-Privilege User Authentication ---")
    
    if not email or not password:
        print("  [SKIP] No low-priv credentials available")
        return None
    
    try:
        r = requests.post(f"{BASE_URL}/auth/login", 
                         json={"email": email, "password": password},
                         timeout=10)
        check("Low-priv login returns 200", r.status_code == 200,
              f"Status: {r.status_code}")
        
        if r.ok:
            data = r.json()
            token = data.get("access_token")
            check("Low-priv has access_token", bool(token))
            return token
    except Exception as e:
        check("Low-priv login successful", False, str(e)[:100])
    
    return None

def test_rbac_module_toggle(lowpriv_token):
    """Test that employee role cannot toggle modules"""
    print("\n--- RBAC: Module Toggle Permission ---")
    
    if not lowpriv_token:
        print("  [SKIP] No low-priv token available")
        return
    
    headers = {"Authorization": f"Bearer {lowpriv_token}"}
    
    # Try to toggle a module (should be denied)
    try:
        r = requests.put(f"{BASE_URL}/modules/toggle",
                       headers=headers,
                       json={"module_key": "recruitment", "is_active": False},
                       timeout=10)
        check("Low-priv CANNOT toggle modules (403 or 401)", 
              r.status_code in [401, 403],
              f"Status: {r.status_code}")
    except Exception as e:
        check("Module toggle RBAC test successful", False, str(e)[:100])

def test_tenant_isolation_modules(admin_token, company1_id, company2_id):
    """Test that module changes in one company don't affect another"""
    print("\n--- Tenant Isolation: Module State ---")
    
    if not admin_token or not company1_id or not company2_id:
        print("  [SKIP] Missing required data for tenant isolation test")
        return
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    try:
        # Get original company's module state
        r = requests.get(f"{BASE_URL}/modules", headers=headers, timeout=10)
        if r.ok:
            original_modules = r.json().get("items", [])
            recruitment_original = next((m for m in original_modules if m["key"] == "recruitment"), None)
            original_state = recruitment_original.get("is_active") if recruitment_original else None
            check("Got original company module state", original_state is not None,
                  f"Recruitment active: {original_state}")
            
            # Switch to second company
            r = requests.post(f"{BASE_URL}/auth/switch-company",
                            headers=headers,
                            json={"company_id": company2_id},
                            timeout=10)
            check("Switch to second company returns 200", r.status_code == 200,
                  f"Status: {r.status_code}")
            
            if r.ok:
                new_token = r.json().get("access_token")
                new_headers = {"Authorization": f"Bearer {new_token}"}
                
                # Toggle module in second company
                r = requests.put(f"{BASE_URL}/modules/toggle",
                               headers=new_headers,
                               json={"module_key": "recruitment", "is_active": not original_state},
                               timeout=10)
                check("Toggle module in second company returns 200", r.status_code == 200,
                      f"Status: {r.status_code}")
                
                # Switch back to original company
                r = requests.post(f"{BASE_URL}/auth/switch-company",
                                headers=new_headers,
                                json={"company_id": company1_id},
                                timeout=10)
                check("Switch back to original company returns 200", r.status_code == 200,
                      f"Status: {r.status_code}")
                
                if r.ok:
                    final_token = r.json().get("access_token")
                    final_headers = {"Authorization": f"Bearer {final_token}"}
                    
                    # Verify original company state unchanged
                    r = requests.get(f"{BASE_URL}/modules", headers=final_headers, timeout=10)
                    if r.ok:
                        final_modules = r.json().get("items", [])
                        recruitment_final = next((m for m in final_modules if m["key"] == "recruitment"), None)
                        final_state = recruitment_final.get("is_active") if recruitment_final else None
                        check("Original company module state UNCHANGED", 
                              final_state == original_state,
                              f"Original: {original_state}, Final: {final_state}")
    except Exception as e:
        check("Tenant isolation module test successful", False, str(e)[:100])

def test_cross_company_employee_access(admin_token, company1_id, company2_id):
    """Test that employees from one company cannot be accessed from another"""
    print("\n--- Tenant Isolation: Cross-Company Employee Access ---")
    
    if not admin_token or not company1_id or not company2_id:
        print("  [SKIP] Missing required data for cross-company test")
        return
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    try:
        # Create employee in company 1
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
        
        if r.status_code == 201:
            employee_id = r.json().get("id")
            CREATED_IDS["employees"].append(employee_id)
            check("Created employee in company 1", bool(employee_id), f"ID: {employee_id[:8]}")
            
            # Switch to company 2
            r = requests.post(f"{BASE_URL}/auth/switch-company",
                            headers=headers,
                            json={"company_id": company2_id},
                            timeout=10)
            
            if r.ok:
                company2_token = r.json().get("access_token")
                company2_headers = {"Authorization": f"Bearer {company2_token}"}
                
                # Try to access employee from company 1 (should be denied/not found)
                r = requests.get(f"{BASE_URL}/employees/{employee_id}", 
                               headers=company2_headers, timeout=10)
                check("Cross-company employee access DENIED (404 or 403)", 
                      r.status_code in [403, 404],
                      f"Status: {r.status_code}")
    except Exception as e:
        check("Cross-company employee access test successful", False, str(e)[:100])

def cleanup_fixtures(admin_token):
    """Clean up temporary test fixtures by recorded IDs"""
    print("\n--- Cleanup Temporary Fixtures ---")
    
    if not admin_token:
        print("  [SKIP] No admin token available")
        return
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Clean up employees
    for employee_id in CREATED_IDS["employees"]:
        try:
            r = requests.delete(f"{BASE_URL}/employees/{employee_id}", 
                              headers=headers, timeout=10)
            check(f"Cleanup employee {employee_id[:8]}", r.status_code in [200, 204],
                  f"Status: {r.status_code}")
        except Exception as e:
            check(f"Cleanup employee {employee_id[:8]}", False, str(e)[:100])
    
    # Clean up users
    for user_id in CREATED_IDS["users"]:
        try:
            r = requests.delete(f"{BASE_URL}/users/{user_id}", 
                              headers=headers, timeout=10)
            check(f"Cleanup user {user_id[:8]}", r.status_code in [200, 204],
                  f"Status: {r.status_code}")
        except Exception as e:
            check(f"Cleanup user {user_id[:8]}", False, str(e)[:100])
    
    # Restore the development administrator context before removing test tenants.
    # This helper is strictly local development and only touches recorded fixture IDs.
    from bootstrap_development import verify_development_target
    from sqlalchemy.engine import make_url
    import pymysql
    verify_development_target()
    url = make_url(os.environ['DATABASE_URL'])
    with pymysql.connect(host=url.host, port=url.port or 3306, user=url.username,
                         password=url.password, database=url.database, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT id FROM companies WHERE code=%s', (os.environ['DEV_COMPANY_CODE'],))
            development = cur.fetchone()
            if not development:
                raise RuntimeError('Development tenant missing; refusing cleanup')
            cur.execute('UPDATE users SET default_company_id=%s WHERE email=%s',
                        (development[0], os.environ['DEV_ADMIN_EMAIL']))
            for company_id in CREATED_IDS['companies']:
                cur.execute('SELECT code,name FROM companies WHERE id=%s', (company_id,))
                row = cur.fetchone()
                if not row or not row[0].startswith('TC') or not row[1].startswith('Test Company '):
                    raise RuntimeError('Fixture ownership check failed')
                cur.execute('DELETE FROM company_modules WHERE company_id=%s', (company_id,))
                cur.execute('DELETE FROM company_settings WHERE company_id=%s', (company_id,))
                cur.execute('DELETE FROM companies WHERE id=%s', (company_id,))
            for user_id in CREATED_IDS['users']:
                cur.execute('DELETE FROM user_company_roles WHERE user_id=%s', (user_id,))
                cur.execute('DELETE FROM users WHERE id=%s AND email LIKE %s', (user_id, 'lowpriv%@example.com'))
        conn.commit()
    check('Fixture tenants removed and admin context restored', True)


def main():
    print("=" * 74)
    print(" Stage 3 RBAC & Tenant Isolation Testing")
    print("=" * 74)
    print(f" Backend URL: {BASE_URL}")
    print(f" Environment: {APP_ENV}")
    print("=" * 74)
    
    try:
        # Critical environment checks first
        test_environment_guards()
        test_remote_environment()
        
        # Admin login
        admin_token, company1_id = admin_login()
        
        if not admin_token or not company1_id:
            print("\n[ERROR] Cannot proceed without admin authentication")
            sys.exit(1)
        
        # Create second company for tenant isolation testing
        company2_id = create_second_company(admin_token)
        
        if not company2_id:
            print("\n[ERROR] Cannot proceed without second company")
            sys.exit(1)
        
        # Create low-privilege user for RBAC testing
        lowpriv_email, lowpriv_password = create_low_priv_user(admin_token, company1_id)
        
        if lowpriv_email and lowpriv_password:
            lowpriv_token = lowpriv_login(lowpriv_email, lowpriv_password)
            
            # Test RBAC: employee cannot toggle modules
            test_rbac_module_toggle(lowpriv_token)
        
        # Test tenant isolation: module state
        test_tenant_isolation_modules(admin_token, company1_id, company2_id)
        
        # Test tenant isolation: cross-company employee access
        test_cross_company_employee_access(admin_token, company1_id, company2_id)
        
        # Cleanup temporary fixtures
        cleanup_fixtures(admin_token)
        
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
    
    print(" ALL RBAC & TENANT ISOLATION TESTS PASSED ✓")
    print("=" * 74)
    return 0

if __name__ == "__main__":
    sys.exit(main())
