"""
Schema Verification: Verify database schema remains unchanged (38 tables, 10 modules, 166 permissions)

Run: cd /app/backend && python test_schema_verification.py
"""
import os
import sys
from dotenv import load_dotenv
import pymysql

# Load environment variables
load_dotenv("/app/backend/.env")

DATABASE_URL = os.environ.get("DATABASE_URL")
APP_ENV = os.environ.get("APP_ENV")

# Parse DATABASE_URL
# Format: mysql+asyncmy://user:password@host:port/database
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found")
    sys.exit(1)

# Extract connection details
import re
match = re.match(r'mysql\+asyncmy://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', DATABASE_URL)
if not match:
    print("ERROR: Cannot parse DATABASE_URL")
    sys.exit(1)

user, password, host, port, database = match.groups()

PASS, FAIL = [], []

def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASS.append(name)
        print(f"  [OK]   {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL.append(f"{name} :: {detail}")
        print(f"  [FAIL] {name} — {detail}")

def verify_schema():
    """Verify database schema"""
    print("\n--- Database Schema Verification ---")
    
    try:
        # Connect to database
        conn = pymysql.connect(
            host=host,
            port=int(port),
            user=user,
            password=password,
            database=database,
            charset='utf8mb4'
        )
        cursor = conn.cursor()
        
        # Count tables
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        table_count = len(tables)
        check("Database has 38 tables", table_count == 38,
              f"Found: {table_count} tables")
        
        # List all tables for reference
        if table_count != 38:
            print(f"\n  Tables found ({table_count}):")
            for table in sorted(tables):
                print(f"    - {table[0]}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        check("Schema verification successful", False, str(e)[:200])

def verify_module_catalog():
    """Verify module catalog has 10 modules"""
    print("\n--- Module Catalog Verification ---")
    
    try:
        conn = pymysql.connect(
            host=host,
            port=int(port),
            user=user,
            password=password,
            database=database,
            charset='utf8mb4'
        )
        cursor = conn.cursor()
        
        # Count distinct modules in company_modules for DEVELOPMENT company
        cursor.execute("""
            SELECT COUNT(DISTINCT module_key) 
            FROM company_modules 
            WHERE company_id = (SELECT id FROM companies WHERE code = 'DEVELOPMENT' LIMIT 1)
        """)
        result = cursor.fetchone()
        module_count = result[0] if result else 0
        check("Module catalog has 10 modules", module_count == 10,
              f"Found: {module_count} modules")
        
        # Count active modules (should be 9, accounting off)
        cursor.execute("""
            SELECT COUNT(*) 
            FROM company_modules 
            WHERE company_id = (SELECT id FROM companies WHERE code = 'DEVELOPMENT' LIMIT 1)
            AND is_active = 1
        """)
        result = cursor.fetchone()
        active_count = result[0] if result else 0
        check("9 modules are active (accounting off)", active_count == 9,
              f"Found: {active_count} active modules")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        check("Module catalog verification successful", False, str(e)[:200])

def verify_permissions():
    """Verify permissions catalog"""
    print("\n--- Permissions Catalog Verification ---")
    
    try:
        conn = pymysql.connect(
            host=host,
            port=int(port),
            user=user,
            password=password,
            database=database,
            charset='utf8mb4'
        )
        cursor = conn.cursor()
        
        # Count permissions in permissions table
        cursor.execute("SELECT COUNT(*) FROM permissions")
        result = cursor.fetchone()
        perm_count = result[0] if result else 0
        check("Permissions catalog has 166 permissions", perm_count == 166,
              f"Found: {perm_count} permissions")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        check("Permissions verification successful", False, str(e)[:200])

def main():
    print("=" * 74)
    print(" Schema Verification — Database Structure Integrity")
    print("=" * 74)
    print(f" Environment: {APP_ENV}")
    print(f" Database: {database}")
    print("=" * 74)
    
    from urllib.parse import urlsplit
    if APP_ENV != "development" or urlsplit(DATABASE_URL).hostname not in {"127.0.0.1", "localhost", "::1"}:
        print("[CRITICAL] Schema verification requires a local development database.")
        sys.exit(1)
    if os.environ.get("R2_ACCESS_KEY_ID") or os.environ.get("R2_SECRET_ACCESS_KEY"):
        print("[CRITICAL] Production storage credentials are forbidden in this test.")
        sys.exit(1)
    
    try:
        verify_schema()
        verify_module_catalog()
        verify_permissions()
        
    except Exception as e:
        print(f"\n[ERROR] Unexpected exception: {e}")
        import traceback
        traceback.print_exc()
        FAIL.append(f"Unexpected exception: {str(e)[:100]}")
    
    print("\n" + "=" * 74)
    total = len(PASS) + len(FAIL)
    print(f" RESULTS: {len(PASS)}/{total} checks passed")
    
    if FAIL:
        print(f"\n FAILED ({len(FAIL)}):")
        for f in FAIL:
            print(f"   - {f}")
        print("=" * 74)
        return 1
    
    print(" ALL SCHEMA CHECKS PASSED ✓")
    print("=" * 74)
    return 0

if __name__ == "__main__":
    sys.exit(main())
