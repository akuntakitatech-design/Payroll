"""
Core POC Development Testing Script
====================================
Verifies runtime environment, database schema, bootstrap idempotence,
and basic API authentication for the development MariaDB setup.

CRITICAL: This script ONLY tests development environment.
- Never loads /app/payroll/backend/.env or /root/.payroll-secrets
- Never makes production calls
- Reads credentials from /app/backend/.env only
"""
import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

# Add backend to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

import requests
from dotenv import load_dotenv

# Load development environment
load_dotenv(Path(__file__).parent.parent / 'backend' / '.env')


class DevelopmentCoreTest:
    """Isolated test suite for development environment validation."""
    
    def __init__(self):
        self.base_url = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8001')
        if not self.base_url.startswith('http'):
            # Fallback for testing
            self.base_url = 'http://localhost:8001'
        self.api_url = f"{self.base_url}/api"
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []
        
    def log_test(self, name: str, passed: bool, message: str = ""):
        """Log test result."""
        self.tests_run += 1
        if passed:
            self.tests_passed += 1
            print(f"✅ PASS: {name}")
            if message:
                print(f"   → {message}")
        else:
            self.tests_failed += 1
            self.failures.append(f"{name}: {message}")
            print(f"❌ FAIL: {name}")
            print(f"   → {message}")
    
    def test_environment_variables(self):
        """Test 1: Verify runtime environment configuration."""
        print("\n" + "="*70)
        print("TEST 1: Runtime Environment Variables")
        print("="*70)
        
        # APP_ENV must be development
        app_env = os.environ.get('APP_ENV', '')
        self.log_test(
            "APP_ENV=development",
            app_env == 'development',
            f"Found: {app_env}"
        )
        
        # DATABASE_URL must be loopback
        db_url = os.environ.get('DATABASE_URL', '')
        parsed = urlsplit(db_url)
        is_loopback = parsed.hostname in {'127.0.0.1', 'localhost'}
        self.log_test(
            "DATABASE_URL uses loopback (127.0.0.1 or localhost)",
            is_loopback,
            f"Host: {parsed.hostname}"
        )
        
        # R2 credentials must be empty
        r2_keys = [
            'R2_ACCESS_KEY_ID',
            'R2_SECRET_ACCESS_KEY',
            'R2_ACCOUNT_ID',
            'R2_ENDPOINT_URL'
        ]
        r2_empty = all(not os.environ.get(key, '').strip() for key in r2_keys)
        self.log_test(
            "R2 credentials all empty",
            r2_empty,
            "All R2 environment variables are empty" if r2_empty else "Some R2 variables are set"
        )
        
        # AUTO_SEED must be false
        auto_seed = os.environ.get('AUTO_SEED', 'true').lower()
        self.log_test(
            "AUTO_SEED=false",
            auto_seed == 'false',
            f"Found: {auto_seed}"
        )
        
        # ENABLE_SCHEDULER must be false
        enable_scheduler = os.environ.get('ENABLE_SCHEDULER', 'true').lower()
        self.log_test(
            "ENABLE_SCHEDULER=false",
            enable_scheduler == 'false',
            f"Found: {enable_scheduler}"
        )
        
        # Verify development credentials exist (but don't print them)
        dev_email = os.environ.get('DEV_ADMIN_EMAIL', '')
        dev_password = os.environ.get('DEV_ADMIN_PASSWORD', '')
        self.log_test(
            "DEV_ADMIN_EMAIL exists",
            bool(dev_email),
            "Credential present" if dev_email else "Missing"
        )
        self.log_test(
            "DEV_ADMIN_PASSWORD exists",
            bool(dev_password),
            "Credential present" if dev_password else "Missing"
        )
    
    async def test_database_connection(self):
        """Test 2: Verify MariaDB connection and schema."""
        print("\n" + "="*70)
        print("TEST 2: MariaDB Connection and Schema")
        print("="*70)
        
        try:
            from app.core.db import get_db, get_engine, ALL_COLLECTIONS
            
            # Test SELECT 1
            db = get_db()
            result = await db.command("ping")
            self.log_test(
                "MariaDB SELECT 1 (ping)",
                result.get('ok') == 1,
                "Database connection successful"
            )
            
            # Verify 38 tables exist
            engine = get_engine()
            async with engine.connect() as conn:
                result = await conn.execute(
                    __import__('sqlalchemy').text(
                        "SELECT COUNT(*) FROM information_schema.tables "
                        "WHERE table_schema = DATABASE()"
                    )
                )
                table_count = result.scalar()
                self.log_test(
                    "38 existing tables present",
                    table_count == 38,
                    f"Found {table_count} tables (expected 38)"
                )
                
                # Verify all expected collections are tables
                result = await conn.execute(
                    __import__('sqlalchemy').text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = DATABASE()"
                    )
                )
                existing_tables = {row[0] for row in result.fetchall()}
                missing_tables = set(ALL_COLLECTIONS) - existing_tables
                self.log_test(
                    "All catalog tables exist",
                    len(missing_tables) == 0,
                    f"Missing: {missing_tables}" if missing_tables else "All tables present"
                )
            
        except Exception as e:
            self.log_test(
                "Database connection",
                False,
                f"Error: {str(e)}"
            )
    
    async def test_rbac_catalog(self):
        """Test 3: Verify RBAC catalog and module structure."""
        print("\n" + "="*70)
        print("TEST 3: RBAC Catalog and Modules")
        print("="*70)
        
        try:
            from app.core.db import get_db
            
            db = get_db()
            
            # Count modules (should be 10)
            module_count = await db.modules.count_documents({})
            self.log_test(
                "10 modules in catalog",
                module_count == 10,
                f"Found {module_count} modules (expected 10)"
            )
            
            # Verify module keys
            modules = await db.modules.find({}).to_list(None)
            module_keys = {m['key'] for m in modules}
            expected_modules = {
                'hr_core', 'employee_core', 'payroll', 'recruitment',
                'attendance', 'leave_overtime', 'performance',
                'mobilization', 'finance_request', 'accounting'
            }
            self.log_test(
                "Expected module keys present",
                module_keys == expected_modules,
                f"Modules: {sorted(module_keys)}"
            )
            
            # Count roles
            role_count = await db.roles.count_documents({})
            self.log_test(
                "Roles catalog exists",
                role_count > 0,
                f"Found {role_count} roles"
            )
            
            # Count permissions
            permission_count = await db.permissions.count_documents({})
            self.log_test(
                "Permissions catalog exists",
                permission_count > 0,
                f"Found {permission_count} permissions"
            )
            
            # Verify role_permissions exist
            role_perm_count = await db.role_permissions.count_documents({})
            self.log_test(
                "Role permissions matrix exists",
                role_perm_count > 0,
                f"Found {role_perm_count} role-permission mappings"
            )
            
        except Exception as e:
            self.log_test(
                "RBAC catalog verification",
                False,
                f"Error: {str(e)}"
            )
    
    async def test_development_tenant(self):
        """Test 4: Verify development tenant and admin account."""
        print("\n" + "="*70)
        print("TEST 4: Development Tenant and Admin")
        print("="*70)
        
        try:
            from app.core.db import get_db
            
            db = get_db()
            
            # Verify exactly 1 company (development tenant)
            company_count = await db.companies.count_documents({})
            self.log_test(
                "Exactly 1 development tenant",
                company_count == 1,
                f"Found {company_count} companies (expected 1)"
            )
            
            # Verify company code is DEVELOPMENT
            dev_company = await db.companies.find_one({'code': 'DEVELOPMENT'})
            self.log_test(
                "Development company exists",
                dev_company is not None,
                f"Company: {dev_company.get('name') if dev_company else 'Not found'}"
            )
            
            # Verify exactly 1 user (dev admin)
            user_count = await db.users.count_documents({})
            self.log_test(
                "Exactly 1 admin user",
                user_count == 1,
                f"Found {user_count} users (expected 1)"
            )
            
            # Verify dev admin email
            dev_email = os.environ.get('DEV_ADMIN_EMAIL', '')
            dev_user = await db.users.find_one({'email': dev_email})
            self.log_test(
                "Dev admin account exists",
                dev_user is not None,
                f"User: {dev_user.get('full_name') if dev_user else 'Not found'}"
            )
            
            # Verify user has super_admin role
            if dev_user:
                user_role = await db.user_company_roles.find_one({
                    'user_id': dev_user['id'],
                    'role_key': 'super_admin'
                })
                self.log_test(
                    "Dev admin has super_admin role",
                    user_role is not None,
                    "Role assignment verified"
                )
            
            # Verify company modules (9 active, accounting off)
            if dev_company:
                company_modules = await db.company_modules.find({
                    'company_id': dev_company['id']
                }).to_list(None)
                active_modules = [m for m in company_modules if m.get('is_active')]
                accounting_module = await db.company_modules.find_one({
                    'company_id': dev_company['id'],
                    'module_key': 'accounting'
                })
                
                self.log_test(
                    "9 modules active (accounting off)",
                    len(active_modules) == 9,
                    f"Active: {len(active_modules)}, Accounting active: {accounting_module.get('is_active') if accounting_module else 'N/A'}"
                )
            
        except Exception as e:
            self.log_test(
                "Development tenant verification",
                False,
                f"Error: {str(e)}"
            )
    
    async def test_no_demo_data(self):
        """Test 5: Verify no demo business data exists."""
        print("\n" + "="*70)
        print("TEST 5: No Demo Business Data")
        print("="*70)
        
        try:
            from app.core.db import get_db
            
            db = get_db()
            
            # No employees
            employee_count = await db.employees.count_documents({})
            self.log_test(
                "No demo employees",
                employee_count == 0,
                f"Found {employee_count} employees (expected 0)"
            )
            
            # No payroll runs
            payroll_count = await db.payroll_runs.count_documents({})
            self.log_test(
                "No demo payroll runs",
                payroll_count == 0,
                f"Found {payroll_count} payroll runs (expected 0)"
            )
            
            # No documents
            document_count = await db.documents.count_documents({})
            self.log_test(
                "No demo documents",
                document_count == 0,
                f"Found {document_count} documents (expected 0)"
            )
            
            # No contracts
            contract_count = await db.employee_contracts.count_documents({})
            self.log_test(
                "No demo contracts",
                contract_count == 0,
                f"Found {contract_count} contracts (expected 0)"
            )
            
            # No certifications
            cert_count = await db.employee_certifications.count_documents({})
            self.log_test(
                "No demo certifications",
                cert_count == 0,
                f"Found {cert_count} certifications (expected 0)"
            )
            
        except Exception as e:
            self.log_test(
                "Demo data verification",
                False,
                f"Error: {str(e)}"
            )
    
    async def test_bootstrap_idempotence(self):
        """Test 6: Run bootstrap twice to verify idempotence."""
        print("\n" + "="*70)
        print("TEST 6: Bootstrap Idempotence")
        print("="*70)
        
        try:
            from app.core.db import get_db
            
            db = get_db()
            
            # Get counts before first bootstrap
            counts_before = {
                'companies': await db.companies.count_documents({}),
                'users': await db.users.count_documents({}),
                'modules': await db.modules.count_documents({}),
                'roles': await db.roles.count_documents({}),
                'permissions': await db.permissions.count_documents({})
            }
            
            # Get admin password hash before
            dev_email = os.environ.get('DEV_ADMIN_EMAIL', '')
            user_before = await db.users.find_one({'email': dev_email})
            password_hash_before = user_before.get('password_hash') if user_before else None
            
            print(f"\n📊 Counts before bootstrap:")
            for key, val in counts_before.items():
                print(f"   {key}: {val}")
            
            # Run bootstrap first time
            print("\n🔄 Running bootstrap (1st time)...")
            import subprocess
            result1 = subprocess.run(
                ['python', '/app/backend/bootstrap_development.py'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result1.returncode != 0:
                self.log_test(
                    "Bootstrap execution (1st run)",
                    False,
                    f"Exit code: {result1.returncode}, Error: {result1.stderr[:200]}"
                )
                return
            else:
                print(f"   Output: {result1.stdout.strip()}")
            
            # Get counts after first bootstrap
            counts_after_1 = {
                'companies': await db.companies.count_documents({}),
                'users': await db.users.count_documents({}),
                'modules': await db.modules.count_documents({}),
                'roles': await db.roles.count_documents({}),
                'permissions': await db.permissions.count_documents({})
            }
            
            print(f"\n📊 Counts after 1st bootstrap:")
            for key, val in counts_after_1.items():
                print(f"   {key}: {val}")
            
            # Run bootstrap second time
            print("\n🔄 Running bootstrap (2nd time)...")
            result2 = subprocess.run(
                ['python', '/app/backend/bootstrap_development.py'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result2.returncode != 0:
                self.log_test(
                    "Bootstrap execution (2nd run)",
                    False,
                    f"Exit code: {result2.returncode}, Error: {result2.stderr[:200]}"
                )
                return
            else:
                print(f"   Output: {result2.stdout.strip()}")
            
            # Get counts after second bootstrap
            counts_after_2 = {
                'companies': await db.companies.count_documents({}),
                'users': await db.users.count_documents({}),
                'modules': await db.modules.count_documents({}),
                'roles': await db.roles.count_documents({}),
                'permissions': await db.permissions.count_documents({})
            }
            
            # Get admin password hash after
            user_after = await db.users.find_one({'email': dev_email})
            password_hash_after = user_after.get('password_hash') if user_after else None
            
            print(f"\n📊 Counts after 2nd bootstrap:")
            for key, val in counts_after_2.items():
                print(f"   {key}: {val}")
            
            # Verify counts didn't change
            counts_unchanged = counts_after_1 == counts_after_2
            self.log_test(
                "Bootstrap idempotence (counts unchanged)",
                counts_unchanged,
                "All counts remain the same" if counts_unchanged else f"Changed: {counts_after_1} → {counts_after_2}"
            )
            
            # Verify password hash didn't change
            password_unchanged = password_hash_before == password_hash_after
            self.log_test(
                "Admin password not reset",
                password_unchanged,
                "Password hash unchanged" if password_unchanged else "Password hash changed!"
            )
            
            # Verify still exactly 1 company and 1 user
            self.log_test(
                "Still exactly 1 company",
                counts_after_2['companies'] == 1,
                f"Companies: {counts_after_2['companies']}"
            )
            
            self.log_test(
                "Still exactly 1 user",
                counts_after_2['users'] == 1,
                f"Users: {counts_after_2['users']}"
            )
            
        except Exception as e:
            self.log_test(
                "Bootstrap idempotence test",
                False,
                f"Error: {str(e)}"
            )
    
    def test_api_login(self):
        """Test 7: Authenticate with dev credentials."""
        print("\n" + "="*70)
        print("TEST 7: API Authentication")
        print("="*70)
        
        try:
            dev_email = os.environ.get('DEV_ADMIN_EMAIL', '')
            dev_password = os.environ.get('DEV_ADMIN_PASSWORD', '')
            
            # Login
            response = requests.post(
                f"{self.api_url}/auth/login",
                json={
                    'email': dev_email,
                    'password': dev_password
                },
                timeout=10
            )
            
            self.log_test(
                "Login API returns 200",
                response.status_code == 200,
                f"Status: {response.status_code}"
            )
            
            if response.status_code == 200:
                data = response.json()
                self.token = data.get('access_token')
                
                self.log_test(
                    "Access token received",
                    bool(self.token),
                    "Token present (not printed for security)"
                )
                
                self.log_test(
                    "User data in response",
                    'user' in data,
                    f"User: {data.get('user', {}).get('full_name', 'N/A')}"
                )
            else:
                print(f"   Response: {response.text[:200]}")
                
        except Exception as e:
            self.log_test(
                "API login",
                False,
                f"Error: {str(e)}"
            )
    
    def test_api_auth_me(self):
        """Test 8: GET /api/auth/me."""
        print("\n" + "="*70)
        print("TEST 8: GET /api/auth/me")
        print("="*70)
        
        if not self.token:
            self.log_test(
                "GET /api/auth/me",
                False,
                "No token available (login failed)"
            )
            return
        
        try:
            response = requests.get(
                f"{self.api_url}/auth/me",
                headers={'Authorization': f'Bearer {self.token}'},
                timeout=10
            )
            
            self.log_test(
                "GET /api/auth/me returns 200",
                response.status_code == 200,
                f"Status: {response.status_code}"
            )
            
            if response.status_code == 200:
                data = response.json()
                user = data.get('user', {})
                company = data.get('active_company', {})
                
                self.log_test(
                    "User data returned",
                    'email' in user,
                    f"Email: {user.get('email', 'N/A')}"
                )
                
                self.log_test(
                    "Company data returned",
                    'name' in company,
                    f"Company: {company.get('name', 'N/A')}"
                )
            else:
                print(f"   Response: {response.text[:200]}")
                
        except Exception as e:
            self.log_test(
                "GET /api/auth/me",
                False,
                f"Error: {str(e)}"
            )
    
    def test_api_dashboard(self):
        """Test 9: GET /api/dashboard/summary."""
        print("\n" + "="*70)
        print("TEST 9: GET /api/dashboard/summary")
        print("="*70)
        
        if not self.token:
            self.log_test(
                "GET /api/dashboard/summary",
                False,
                "No token available (login failed)"
            )
            return
        
        try:
            response = requests.get(
                f"{self.api_url}/dashboard/summary",
                headers={'Authorization': f'Bearer {self.token}'},
                timeout=10
            )
            
            self.log_test(
                "GET /api/dashboard/summary returns 200",
                response.status_code == 200,
                f"Status: {response.status_code}"
            )
            
            if response.status_code == 200:
                data = response.json()
                counts = data.get('counts', {})
                
                # Verify employee count is 0
                employee_count = counts.get('employees', -1)
                self.log_test(
                    "Dashboard shows 0 employees",
                    employee_count == 0,
                    f"Employees: {employee_count}"
                )
                
                # Verify contracts count is 0
                contracts_count = counts.get('contracts', -1)
                self.log_test(
                    "Dashboard shows 0 contracts",
                    contracts_count == 0,
                    f"Contracts: {contracts_count}"
                )
            else:
                print(f"   Response: {response.text[:200]}")
                
        except Exception as e:
            self.log_test(
                "GET /api/dashboard/summary",
                False,
                f"Error: {str(e)}"
            )
    
    def test_api_employees_list(self):
        """Test 10: GET /api/employees (should be empty)."""
        print("\n" + "="*70)
        print("TEST 10: GET /api/employees (empty list)")
        print("="*70)
        
        if not self.token:
            self.log_test(
                "GET /api/employees",
                False,
                "No token available (login failed)"
            )
            return
        
        try:
            response = requests.get(
                f"{self.api_url}/employees",
                headers={'Authorization': f'Bearer {self.token}'},
                timeout=10
            )
            
            self.log_test(
                "GET /api/employees returns 200",
                response.status_code == 200,
                f"Status: {response.status_code}"
            )
            
            if response.status_code == 200:
                data = response.json()
                employees = data if isinstance(data, list) else data.get('data', [])
                
                self.log_test(
                    "Employee list is empty",
                    len(employees) == 0,
                    f"Found {len(employees)} employees (expected 0)"
                )
            else:
                print(f"   Response: {response.text[:200]}")
                
        except Exception as e:
            self.log_test(
                "GET /api/employees",
                False,
                f"Error: {str(e)}"
            )
    
    def test_api_payroll_list(self):
        """Test 11: GET /api/payroll/runs (should be empty)."""
        print("\n" + "="*70)
        print("TEST 11: GET /api/payroll/runs (empty list)")
        print("="*70)
        
        if not self.token:
            self.log_test(
                "GET /api/payroll/runs",
                False,
                "No token available (login failed)"
            )
            return
        
        try:
            response = requests.get(
                f"{self.api_url}/payroll/runs",
                headers={'Authorization': f'Bearer {self.token}'},
                timeout=10
            )
            
            self.log_test(
                "GET /api/payroll/runs returns 200",
                response.status_code == 200,
                f"Status: {response.status_code}"
            )
            
            if response.status_code == 200:
                data = response.json()
                runs = data if isinstance(data, list) else data.get('data', [])
                
                self.log_test(
                    "Payroll runs list is empty",
                    len(runs) == 0,
                    f"Found {len(runs)} payroll runs (expected 0)"
                )
            else:
                print(f"   Response: {response.text[:200]}")
                
        except Exception as e:
            self.log_test(
                "GET /api/payroll/runs",
                False,
                f"Error: {str(e)}"
            )
    
    def test_supervisor_mariadb(self):
        """Test 12: Verify supervisor MariaDB service is running."""
        print("\n" + "="*70)
        print("TEST 12: Supervisor MariaDB Service")
        print("="*70)
        
        try:
            import subprocess
            result = subprocess.run(
                ['sudo', 'supervisorctl', 'status', 'payroll-dev-mariadb'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            output = result.stdout.strip()
            is_running = 'RUNNING' in output
            
            self.log_test(
                "payroll-dev-mariadb service RUNNING",
                is_running,
                output
            )
            
            # Verify loopback binding
            if is_running:
                # Check if MariaDB is listening on 127.0.0.1:3306
                netstat_result = subprocess.run(
                    ['ss', '-tlnp'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                is_loopback = '127.0.0.1:3306' in netstat_result.stdout
                self.log_test(
                    "MariaDB listening on loopback:3306",
                    is_loopback,
                    "127.0.0.1:3306 found in netstat" if is_loopback else "Not found on loopback"
                )
            
            # Verify datadir persistence
            datadir = Path('/app/.local-data/mariadb/data')
            self.log_test(
                "MariaDB datadir exists",
                datadir.exists(),
                f"Path: {datadir}"
            )
            
        except Exception as e:
            self.log_test(
                "Supervisor MariaDB verification",
                False,
                f"Error: {str(e)}"
            )
    
    def test_backend_health(self):
        """Test 13: Verify backend health endpoint."""
        print("\n" + "="*70)
        print("TEST 13: Backend Health Check")
        print("="*70)
        
        try:
            response = requests.get(
                f"{self.api_url}/health",
                timeout=10
            )
            
            self.log_test(
                "GET /api/health returns 200",
                response.status_code == 200,
                f"Status: {response.status_code}"
            )
            
            if response.status_code == 200:
                data = response.json()
                
                self.log_test(
                    "Health status is healthy",
                    data.get('status') == 'healthy',
                    f"Status: {data.get('status')}"
                )
                
                self.log_test(
                    "Database connected",
                    'connected' in data.get('database', ''),
                    f"Database: {data.get('database')}"
                )
                
                self.log_test(
                    "READ_ONLY is false",
                    data.get('read_only') == False,
                    f"READ_ONLY: {data.get('read_only')}"
                )
            else:
                print(f"   Response: {response.text[:200]}")
                
        except Exception as e:
            self.log_test(
                "Backend health check",
                False,
                f"Error: {str(e)}"
            )
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        print(f"Total tests: {self.tests_run}")
        print(f"✅ Passed: {self.tests_passed}")
        print(f"❌ Failed: {self.tests_failed}")
        
        if self.failures:
            print("\n❌ FAILURES:")
            for i, failure in enumerate(self.failures, 1):
                print(f"{i}. {failure}")
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"\nSuccess rate: {success_rate:.1f}%")
        
        if self.tests_failed == 0:
            print("\n🎉 ALL TESTS PASSED!")
            return 0
        else:
            print(f"\n⚠️  {self.tests_failed} test(s) failed")
            return 1


async def run_async_tests(tester):
    """Run all async tests."""
    await tester.test_database_connection()
    await tester.test_rbac_catalog()
    await tester.test_development_tenant()
    await tester.test_no_demo_data()
    await tester.test_bootstrap_idempotence()


def main():
    """Main test runner."""
    print("="*70)
    print("DEVELOPMENT CORE POC TEST SUITE")
    print("="*70)
    print("Testing development MariaDB environment")
    print("No production calls will be made")
    print("="*70)
    
    tester = DevelopmentCoreTest()
    
    # Test 1: Environment variables (sync)
    tester.test_environment_variables()
    
    # Tests 2-6: Database tests (async)
    asyncio.run(run_async_tests(tester))
    
    # Tests 7-11: API tests (sync)
    tester.test_api_login()
    tester.test_api_auth_me()
    tester.test_api_dashboard()
    tester.test_api_employees_list()
    tester.test_api_payroll_list()
    
    # Tests 12-13: Infrastructure tests (sync)
    tester.test_supervisor_mariadb()
    tester.test_backend_health()
    
    # Print summary
    exit_code = tester.print_summary()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
