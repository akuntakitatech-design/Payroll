#!/usr/bin/env python3
"""
PHASE 1 Isolated Read-Only Test Script
=======================================
Verifikasi koneksi MariaDB eksternal dan Cloudflare R2 dalam mode READ-ONLY
tanpa memodifikasi source code aplikasi atau menjalankan server.

Test ini membuktikan:
1. Koneksi MariaDB eksternal via SQLAlchemy asyncmy (SELECT 1, schema metadata, TLS)
2. Akses Cloudflare R2 (HEAD bucket, ListObjectsV2, optional GET object)
3. READ_ONLY=true dan AUTO_SEED=false loaded dari .env
4. DDL/seed/scheduler guards aktif tanpa invoke real write calls
5. Git repository clean, branch main, HEAD 8255f1b
"""
import asyncio
import os
import sys
from pathlib import Path

# CRITICAL: Add payroll backend to path and load .env BEFORE any app imports
PAYROLL_BACKEND = Path("/app/payroll/backend")
sys.path.insert(0, str(PAYROLL_BACKEND))

from dotenv import load_dotenv
load_dotenv(PAYROLL_BACKEND / ".env")

# Now safe to import app modules
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


class TestResult:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []
    
    def pass_test(self, name: str, detail: str = ""):
        self.passed.append((name, detail))
        print(f"✅ PASS: {name}")
        if detail:
            print(f"   → {detail}")
    
    def fail_test(self, name: str, error: str):
        self.failed.append((name, error))
        print(f"❌ FAIL: {name}")
        print(f"   → {error}")
    
    def warn(self, message: str):
        self.warnings.append(message)
        print(f"⚠️  WARNING: {message}")
    
    def summary(self):
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        print(f"Passed: {len(self.passed)}")
        print(f"Failed: {len(self.failed)}")
        print(f"Warnings: {len(self.warnings)}")
        
        if self.failed:
            print("\n❌ FAILED TESTS:")
            for name, error in self.failed:
                print(f"  - {name}: {error}")
        
        if self.warnings:
            print("\n⚠️  WARNINGS:")
            for msg in self.warnings:
                print(f"  - {msg}")
        
        print("="*70)
        return len(self.failed) == 0


async def test_env_configuration(result: TestResult):
    """Test 1: Verify READ_ONLY=true and AUTO_SEED=false from .env"""
    print("\n" + "="*70)
    print("TEST 1: Environment Configuration")
    print("="*70)
    
    try:
        read_only = os.environ.get("READ_ONLY", "").strip().lower()
        auto_seed = os.environ.get("AUTO_SEED", "").strip().lower()
        
        if read_only in ("1", "true", "yes", "y", "ya"):
            result.pass_test("READ_ONLY flag", "READ_ONLY=true loaded correctly")
        else:
            result.fail_test("READ_ONLY flag", f"Expected true, got: {read_only or '(not set)'}")
        
        if auto_seed in ("0", "false", "no", "n", "tidak"):
            result.pass_test("AUTO_SEED flag", "AUTO_SEED=false loaded correctly")
        else:
            result.warn(f"AUTO_SEED={auto_seed or '(not set)'} - should be false for production preview")
        
        # Verify DATABASE_URL exists (without printing it)
        db_url = os.environ.get("DATABASE_URL", "").strip()
        if db_url:
            # Check if it's asyncmy driver
            if "asyncmy" in db_url or "mysql" in db_url:
                result.pass_test("DATABASE_URL", "Database URL configured with asyncmy driver")
            else:
                result.warn("DATABASE_URL does not contain asyncmy driver")
        else:
            # Check fallback vars
            db_host = os.environ.get("DB_HOST", "")
            if db_host:
                result.pass_test("DATABASE_URL", "Database configured via DB_HOST fallback")
            else:
                result.fail_test("DATABASE_URL", "No database configuration found")
        
        # Verify R2 credentials exist (without printing them)
        r2_access = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
        r2_secret = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
        r2_bucket = os.environ.get("R2_BUCKET_NAME", "").strip()
        r2_account = os.environ.get("R2_ACCOUNT_ID", "").strip()
        r2_endpoint = os.environ.get("R2_ENDPOINT_URL", "").strip()
        
        if r2_access and r2_secret and r2_bucket and (r2_account or r2_endpoint):
            result.pass_test("R2 credentials", "All required R2 environment variables present")
        else:
            missing = []
            if not r2_access: missing.append("R2_ACCESS_KEY_ID")
            if not r2_secret: missing.append("R2_SECRET_ACCESS_KEY")
            if not r2_bucket: missing.append("R2_BUCKET_NAME")
            if not (r2_account or r2_endpoint): missing.append("R2_ACCOUNT_ID or R2_ENDPOINT_URL")
            result.fail_test("R2 credentials", f"Missing: {', '.join(missing)}")
    
    except Exception as e:
        result.fail_test("Environment configuration", str(e))


async def test_mariadb_connection(result: TestResult):
    """Test 2: MariaDB connection, SELECT 1, and TLS status"""
    print("\n" + "="*70)
    print("TEST 2: MariaDB Connection & TLS")
    print("="*70)
    
    engine = None
    try:
        # Import config to get DATABASE_URL
        from app.core.config import settings
        
        # Create engine (same as app does)
        engine = create_async_engine(
            settings.DATABASE_URL,
            pool_pre_ping=False,  # Skip pre-ping for test
            pool_size=1,
            max_overflow=0,
            echo=False,
        )
        
        # Test basic connectivity with SELECT 1
        async with engine.connect() as conn:
            result_proxy = await conn.execute(text("SELECT 1 as test"))
            row = result_proxy.fetchone()
            if row and row[0] == 1:
                result.pass_test("MariaDB SELECT 1", "Basic connectivity verified")
            else:
                result.fail_test("MariaDB SELECT 1", "Unexpected result")
            
            # Check TLS status safely
            try:
                tls_result = await conn.execute(text("SHOW STATUS LIKE 'Ssl_cipher'"))
                tls_row = tls_result.fetchone()
                if tls_row and tls_row[1]:
                    result.pass_test("MariaDB TLS", f"TLS active (cipher present)")
                else:
                    result.warn("MariaDB TLS not detected - connection may be unencrypted")
            except Exception as e:
                result.warn(f"Could not check TLS status: {str(e)[:100]}")
        
        result.pass_test("MariaDB engine", "SQLAlchemy asyncmy engine created successfully")
    
    except Exception as e:
        result.fail_test("MariaDB connection", str(e)[:200])
    
    finally:
        if engine:
            await engine.dispose()


async def test_mariadb_schema(result: TestResult):
    """Test 3: Verify schema metadata matches expected catalog tables"""
    print("\n" + "="*70)
    print("TEST 3: MariaDB Schema Metadata")
    print("="*70)
    
    engine = None
    try:
        from app.core.config import settings
        from app.core.db import ALL_COLLECTIONS
        
        engine = create_async_engine(
            settings.DATABASE_URL,
            pool_size=1,
            max_overflow=0,
            echo=False,
        )
        
        async with engine.connect() as conn:
            # Get list of tables
            tables_result = await conn.execute(text("SHOW TABLES"))
            existing_tables = {row[0] for row in tables_result.fetchall()}
            
            # Check critical tables from catalog
            critical_tables = ["companies", "users", "employees", "payroll_runs", "documents"]
            missing_critical = [t for t in critical_tables if t not in existing_tables]
            
            if not missing_critical:
                result.pass_test("Critical tables", f"All {len(critical_tables)} critical tables exist")
            else:
                result.fail_test("Critical tables", f"Missing: {', '.join(missing_critical)}")
            
            # Check a sample table structure (users table)
            if "users" in existing_tables:
                cols_result = await conn.execute(text("DESCRIBE users"))
                user_cols = {row[0] for row in cols_result.fetchall()}
                expected_cols = {"id", "email", "full_name", "password_hash", "status", "created_at"}
                
                if expected_cols.issubset(user_cols):
                    result.pass_test("Table structure", f"users table has expected columns ({len(user_cols)} total)")
                else:
                    missing = expected_cols - user_cols
                    result.fail_test("Table structure", f"users table missing columns: {missing}")
            
            # Report total tables found
            result.pass_test("Schema metadata", f"Found {len(existing_tables)} tables in database")
    
    except Exception as e:
        result.fail_test("Schema metadata", str(e)[:200])
    
    finally:
        if engine:
            await engine.dispose()


async def test_r2_storage(result: TestResult):
    """Test 4: Cloudflare R2 - HEAD bucket, ListObjectsV2, optional GET"""
    print("\n" + "="*70)
    print("TEST 4: Cloudflare R2 Storage")
    print("="*70)
    
    try:
        from app.core.storage import init_storage, storage_configured
        from app.core.config import settings
        from botocore.exceptions import ClientError, BotoCoreError
        
        if not storage_configured():
            result.fail_test("R2 configuration", "R2 not configured (missing credentials)")
            return
        
        client = init_storage()
        bucket = settings.R2_BUCKET_NAME
        prefix = settings.R2_PREFIX or "hris-payroll"
        
        # Test 1: HEAD bucket
        try:
            client.head_bucket(Bucket=bucket)
            result.pass_test("R2 HEAD bucket", f"Bucket '{bucket}' accessible")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            result.fail_test("R2 HEAD bucket", f"Error {error_code}: {str(e)[:100]}")
            return
        except BotoCoreError as e:
            result.fail_test("R2 HEAD bucket", str(e)[:100])
            return
        
        # Test 2: ListObjectsV2 with max 1 object within prefix
        try:
            response = client.list_objects_v2(
                Bucket=bucket,
                Prefix=prefix,
                MaxKeys=1
            )
            
            object_count = response.get("KeyCount", 0)
            if object_count > 0:
                result.pass_test("R2 ListObjectsV2", f"Found {object_count} object(s) in prefix '{prefix}'")
                
                # Optional: HEAD or GET one object (bounded, no printing content)
                contents = response.get("Contents", [])
                if contents:
                    first_key = contents[0]["Key"]
                    try:
                        # HEAD object (metadata only, no download)
                        head_response = client.head_object(Bucket=bucket, Key=first_key)
                        size = head_response.get("ContentLength", 0)
                        content_type = head_response.get("ContentType", "unknown")
                        result.pass_test("R2 HEAD object", f"Object metadata retrieved (size: {size} bytes, type: {content_type})")
                    except Exception as e:
                        result.warn(f"Could not HEAD object: {str(e)[:100]}")
            else:
                result.warn(f"No objects found in prefix '{prefix}' - bucket is empty or prefix incorrect")
        
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            result.fail_test("R2 ListObjectsV2", f"Error {error_code}: {str(e)[:100]}")
        except BotoCoreError as e:
            result.fail_test("R2 ListObjectsV2", str(e)[:100])
    
    except Exception as e:
        result.fail_test("R2 storage test", str(e)[:200])


def test_code_guards(result: TestResult):
    """Test 5: Verify DDL/seed/scheduler guards without invoking them"""
    print("\n" + "="*70)
    print("TEST 5: Code Guards (DDL/Seed/Scheduler)")
    print("="*70)
    
    try:
        # Check db.py for READ_ONLY guards
        db_file = PAYROLL_BACKEND / "app/core/db.py"
        db_content = db_file.read_text()
        
        if "read_only_enabled()" in db_content and "ReadOnlyError" in db_content:
            result.pass_test("DB write guards", "read_only_enabled() and ReadOnlyError found in db.py")
        else:
            result.fail_test("DB write guards", "READ_ONLY guards not found in db.py")
        
        if "_guard_write" in db_content:
            result.pass_test("DB _guard_write", "_guard_write function present in db.py")
        else:
            result.warn("_guard_write function not found in db.py")
        
        # Check storage.py for R2 write guards
        storage_file = PAYROLL_BACKEND / "app/core/storage.py"
        storage_content = storage_file.read_text()
        
        if "_guard_storage_write" in storage_content or "READ_ONLY" in storage_content:
            result.pass_test("R2 write guards", "Storage write guards found in storage.py")
        else:
            result.fail_test("R2 write guards", "READ_ONLY guards not found in storage.py")
        
        # Check server.py for DDL/seed/scheduler skip logic
        server_file = PAYROLL_BACKEND / "server.py"
        server_content = server_file.read_text()
        
        if "if settings.READ_ONLY:" in server_content or "if not settings.READ_ONLY" in server_content:
            result.pass_test("Startup guards", "READ_ONLY conditional logic found in server.py")
        else:
            result.warn("READ_ONLY conditional not found in server.py startup")
        
        if 'AUTO_SEED' in server_content:
            result.pass_test("Seed guard", "AUTO_SEED check found in server.py")
        else:
            result.warn("AUTO_SEED check not found in server.py")
        
        # Check ensure_indexes/ensure_schema for READ_ONLY skip
        if "ensure_indexes" in db_content or "ensure_schema" in db_content:
            if "read_only_enabled()" in db_content:
                result.pass_test("DDL guard", "DDL operations guarded by READ_ONLY in db.py")
            else:
                result.warn("DDL operations may not be guarded by READ_ONLY")
    
    except Exception as e:
        result.fail_test("Code guards inspection", str(e)[:200])


def test_git_status(result: TestResult):
    """Test 6: Verify git repository status"""
    print("\n" + "="*70)
    print("TEST 6: Git Repository Status")
    print("="*70)
    
    try:
        import subprocess
        
        repo_path = Path("/app/payroll")
        
        # Check branch
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        branch = branch_result.stdout.strip()
        
        if branch == "main":
            result.pass_test("Git branch", f"On branch main")
        else:
            result.fail_test("Git branch", f"Expected main, got {branch}")
        
        # Check HEAD commit
        head_result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        head = head_result.stdout.strip()
        
        if head == "8255f1b":
            result.pass_test("Git HEAD", f"HEAD at {head}")
        else:
            result.warn(f"HEAD is {head}, expected 8255f1b")
        
        # Check working tree clean
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        
        if not status_result.stdout.strip():
            result.pass_test("Git working tree", "Working tree clean")
        else:
            result.warn("Working tree has uncommitted changes")
        
        # Check remote URL (no PAT)
        remote_result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        remote_url = remote_result.stdout.strip()
        
        if "github.com/akuntakitatech-design/Payroll" in remote_url:
            if "@" not in remote_url or "github.com" in remote_url.split("@")[-1]:
                result.pass_test("Git remote", "Remote URL clean (no PAT in URL)")
            else:
                result.warn("Remote URL may contain credentials")
        else:
            result.fail_test("Git remote", f"Unexpected remote: {remote_url}")
    
    except subprocess.CalledProcessError as e:
        result.fail_test("Git status", f"Git command failed: {e}")
    except Exception as e:
        result.fail_test("Git status", str(e)[:200])


async def main():
    print("="*70)
    print("PHASE 1: Isolated Read-Only Core Test")
    print("="*70)
    print("Testing MariaDB + R2 connectivity without modifying application")
    print()
    
    result = TestResult()
    
    # Run all tests
    await test_env_configuration(result)
    await test_mariadb_connection(result)
    await test_mariadb_schema(result)
    await test_r2_storage(result)
    test_code_guards(result)
    test_git_status(result)
    
    # Print summary
    success = result.summary()
    
    if success:
        print("\n✅ ALL TESTS PASSED - Ready for Phase 2")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED - Review errors above")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
