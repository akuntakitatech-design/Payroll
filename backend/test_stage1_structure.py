"""
Stage 1 Structure Testing: Module activation, system mode, and regression tests
Tests ONLY structure and metadata, NOT detailed business logic.

Run: cd /app/backend && python test_stage1_structure.py
"""
import os
import sys
import requests
from datetime import datetime

# Load credentials from .env FIRST
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

# Load frontend .env for REACT_APP_BACKEND_URL
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

def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASS.append(name)
        print(f"  [OK]   {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL.append(f"{name} :: {detail}")
        print(f"  [FAIL] {name} — {detail}")

def test_environment_guards():
    """MANDATORY: Verify environment is development with correct configuration - FAIL CLOSED"""
    print("\n--- Environment Guards (CRITICAL) ---")
    
    # FAIL CLOSED: Exit immediately if not development
    if APP_ENV != "development":
        print(f"  [CRITICAL] APP_ENV is '{APP_ENV}', not 'development'. ABORTING ALL TESTS.")
        sys.exit(1)
    check("APP_ENV is 'development'", True, f"Verified: {APP_ENV}")
    
    # FAIL CLOSED: Exit if not loopback
    from urllib.parse import urlsplit
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
        print(f"  [CRITICAL] R2 credentials present: {[k for k, v in r2_keys.items() if v]}. ABORTING ALL TESTS.")
        sys.exit(1)
    check("R2 keys are empty (development)", True, "Verified empty R2 credentials")
    
    # FAIL CLOSED: Exit if credentials missing
    if not DEV_ADMIN_EMAIL or not DEV_ADMIN_PASSWORD:
        print(f"  [CRITICAL] DEV_ADMIN_EMAIL or DEV_ADMIN_PASSWORD missing. ABORTING ALL TESTS.")
        sys.exit(1)
    check("DEV_ADMIN_EMAIL loaded from .env", True, "Verified")
    check("DEV_ADMIN_PASSWORD loaded from .env", True, "Verified")

def test_system_mode():
    """Test /api/system/mode endpoint returns correct development info - FAIL CLOSED"""
    print("\n--- System Mode Endpoint ---")
    
    try:
        r = requests.get(f"{BASE_URL}/system/mode", timeout=10)
        check("GET /api/system/mode returns 200", r.status_code == 200, 
              f"Status: {r.status_code}")
        
        if r.ok:
            data = r.json()
            check("Response has 'environment' field", "environment" in data,
                  f"Keys: {list(data.keys())}")
            
            # FAIL CLOSED: Remote must be development before mutations
            remote_env = data.get("environment")
            if remote_env != "development":
                print(f"  [CRITICAL] Remote /api/system/mode environment is '{remote_env}', not 'development'. ABORTING ALL TESTS.")
                sys.exit(1)
            check("Remote environment is 'development'", True, f"Verified: {remote_env}")
            
            check("Response has 'read_only' field", "read_only" in data)
            check("Response has 'database' field", "database" in data)
            check("Database is 'mariadb'", data.get("database") == "mariadb",
                  f"Got: {data.get('database')}")
            check("Response has 'storage' field", "storage" in data)
            check("Storage is 'not-configured' (R2 dev not setup)", 
                  data.get("storage") == "not-configured",
                  f"Got: {data.get('storage')}")
        else:
            raise RuntimeError("Remote environment could not be verified")
    except Exception:
        print("[CRITICAL] Remote environment unverified. ABORTING ALL TESTS.")
        sys.exit(1)

def test_login():
    """Test login with development credentials - NO UNSAFE DIAGNOSTICS"""
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
            check("Login response has 'active_company' object", "active_company" in data)
            
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
                            company = data.get("active_company", {})
                            check("Switched to DEVELOPMENT company", True,
                                  f"Code: {company.get('code')}")
            
            check("Company code is 'DEVELOPMENT'", 
                  company.get("code") == "DEVELOPMENT",
                  f"Got: {company.get('code')}")
            check("Company name contains 'DEVELOPMENT'",
                  "DEVELOPMENT" in company.get("name", ""),
                  f"Got: {company.get('name')}")
            
            return token
    except Exception as e:
        check("Login successful", False, str(e)[:100])
    
    return None

def test_module_catalog(token):
    """Test GET /api/modules returns correct module catalog"""
    print("\n--- Module Catalog ---")
    
    if not token:
        print("  [SKIP] No auth token available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        r = requests.get(f"{BASE_URL}/modules", headers=headers, timeout=10)
        check("GET /api/modules returns 200", r.status_code == 200,
              f"Status: {r.status_code}")
        
        if r.ok:
            data = r.json()
            items = data.get("items", [])
            
            check("Module catalog has 10 modules", len(items) == 10,
                  f"Got: {len(items)} modules")
            
            # Check for expected modules
            module_keys = {m["key"] for m in items}
            expected_keys = {
                "hr_core", "employee_core", "payroll",
                "recruitment", "attendance", "leave_overtime",
                "performance", "mobilization", "finance_request",
                "accounting"
            }
            check("All 10 expected modules present", 
                  module_keys == expected_keys,
                  f"Missing: {expected_keys - module_keys}, Extra: {module_keys - expected_keys}")
            
            # Count active modules
            active_modules = [m for m in items if m.get("is_active")]
            check("9 modules are active (accounting off)", 
                  len(active_modules) == 9,
                  f"Got: {len(active_modules)} active")
            
            # Check accounting is off
            accounting = next((m for m in items if m["key"] == "accounting"), None)
            if accounting:
                check("Accounting module is inactive", 
                      not accounting.get("is_active"),
                      f"is_active: {accounting.get('is_active')}")
            
            # Check 6 new modules are present
            new_modules = ["recruitment", "attendance", "leave_overtime", 
                          "performance", "mobilization", "finance_request"]
            for key in new_modules:
                mod = next((m for m in items if m["key"] == key), None)
                check(f"Module '{key}' exists in catalog", mod is not None)
                if mod:
                    check(f"Module '{key}' has required fields",
                          all(k in mod for k in ["key", "name", "description", "is_active"]))
            
            # Check HR Core is marked as core and always active
            hr_core = next((m for m in items if m["key"] == "hr_core"), None)
            if hr_core:
                check("HR Core is marked as core module",
                      hr_core.get("is_core") is True)
                check("HR Core cannot be toggled",
                      hr_core.get("can_toggle") is False)
                check("HR Core is active",
                      hr_core.get("is_active") is True)
            
            return items
    except Exception as e:
        check("GET /api/modules successful", False, str(e)[:100])
    
    return []

def test_module_toggle(token, modules):
    """Test module activation/deactivation - NO RAW AUTH RESPONSES"""
    print("\n--- Module Toggle ---")
    
    if not token or not modules:
        print("  [SKIP] No auth token or modules available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Find a non-core module that can be toggled (use recruitment)
    test_module = next((m for m in modules if m["key"] == "recruitment"), None)
    
    if not test_module:
        check("Test module 'recruitment' found", False, "Module not in catalog")
        return
    
    original_state = test_module.get("is_active")
    
    try:
        # Test deactivating
        if original_state:
            r = requests.put(f"{BASE_URL}/modules/toggle",
                           headers=headers,
                           json={"module_key": "recruitment", "is_active": False},
                           timeout=10)
            check("PUT /api/modules/toggle (deactivate) returns 200", 
                  r.status_code == 200,
                  f"Status: {r.status_code}")
            
            if r.ok:
                data = r.json()
                check("Toggle response has 'message' field", "message" in data)
                check("Toggle response has 'item' field", "item" in data)
                if "item" in data:
                    check("Module is now inactive", 
                          data["item"].get("is_active") is False)
        
        # Test activating
        r = requests.put(f"{BASE_URL}/modules/toggle",
                       headers=headers,
                       json={"module_key": "recruitment", "is_active": True},
                       timeout=10)
        check("PUT /api/modules/toggle (activate) returns 200",
              r.status_code == 200,
              f"Status: {r.status_code}")
        
        if r.ok:
            data = r.json()
            if "item" in data:
                check("Module is now active",
                      data["item"].get("is_active") is True)
                check("activated_at timestamp is set",
                      data["item"].get("activated_at") is not None)
        
        # Test that HR Core cannot be deactivated
        r = requests.put(f"{BASE_URL}/modules/toggle",
                       headers=headers,
                       json={"module_key": "hr_core", "is_active": False},
                       timeout=10)
        check("HR Core cannot be deactivated (400 or 409)",
              r.status_code in [400, 409],
              f"Status: {r.status_code}")
        
        # Test invalid module key
        r = requests.put(f"{BASE_URL}/modules/toggle",
                       headers=headers,
                       json={"module_key": "nonexistent_module", "is_active": True},
                       timeout=10)
        check("Invalid module key returns 404",
              r.status_code == 404,
              f"Status: {r.status_code}")
        
    except Exception as e:
        check("Module toggle tests successful", False, str(e)[:100])

def test_existing_endpoints_regression(token):
    """Regression test: Verify existing endpoints still work"""
    print("\n--- Existing Endpoints Regression ---")
    
    if not token:
        print("  [SKIP] No auth token available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test key existing endpoints
    endpoints = [
        ("/health", "GET", None),
        ("/auth/me", "GET", None),
        ("/dashboard/summary", "GET", None),
        ("/employees", "GET", None),
        ("/companies", "GET", None),
    ]
    
    for path, method, _ in endpoints:
        try:
            if method == "GET":
                r = requests.get(f"{BASE_URL}{path}", headers=headers, timeout=10)
            
            check(f"{method} {path} returns 200", 
                  r.status_code == 200,
                  f"Status: {r.status_code}")
        except Exception as e:
            check(f"{method} {path} successful", False, str(e)[:100])

def test_health_check():
    """Test health check endpoint"""
    print("\n--- Health Check ---")
    
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=10)
        check("GET /api/health returns 200", r.status_code == 200,
              f"Status: {r.status_code}")
        
        if r.ok:
            data = r.json()
            check("Health response has 'status' field", "status" in data)
            check("Health status is 'healthy'", 
                  data.get("status") == "healthy",
                  f"Got: {data.get('status')}")
            check("Health response has 'database' field", "database" in data)
            check("Database is connected",
                  "connected" in data.get("database", ""),
                  f"Got: {data.get('database')}")
    except Exception as e:
        check("Health check successful", False, str(e)[:100])

def main():
    print("=" * 74)
    print(" Stage 1 Structure Testing — Module Activation & System Mode")
    print("=" * 74)
    print(f" Backend URL: {BASE_URL}")
    print(f" Environment: {APP_ENV}")
    print("=" * 74)
    
    try:
        # Critical environment checks first
        test_environment_guards()
        
        # Test health and system mode (no auth required)
        test_health_check()
        test_system_mode()
        
        # Test authentication
        token = test_login()
        
        # Test module functionality
        modules = test_module_catalog(token)
        test_module_toggle(token, modules)
        
        # Regression tests
        test_existing_endpoints_regression(token)
        
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
    
    print(" ALL BACKEND TESTS PASSED ✓")
    print("=" * 74)
    return 0

if __name__ == "__main__":
    sys.exit(main())
