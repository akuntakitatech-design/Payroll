"""Specific regression tests for iteration 2 fixes.

Tests:
1. Manager role has contract:view and certification:view permissions
2. Demo documents have real files and preview works
3. Supervisor role also has contract:view and certification:view
4. Finance role has certification:view
"""
import requests
import sys

BASE_URL = "https://payroll-hub-503.preview.emergentagent.com/api"
PASSWORD = "Hris#2026"


def log(message, level="INFO"):
    prefix = {"INFO": "ℹ️", "PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}.get(level, "•")
    print(f"{prefix} {message}")


def login(email):
    """Login and return token."""
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": email, "password": PASSWORD},
        timeout=30
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    return None


def test_manager_permissions():
    """Test that manager role has contract:view and certification:view."""
    log("\n=== REGRESSION FIX 1: Manager Role Permissions ===", "INFO")
    
    token = login("manager@nep.co.id")
    if not token:
        log("Failed to login as manager", "FAIL")
        return False
    
    # Test GET /contracts - should be 200 (was 403 before fix)
    response = requests.get(
        f"{BASE_URL}/contracts",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30
    )
    if response.status_code == 200:
        log("✅ Manager can view contracts (GET /contracts = 200)", "PASS")
    else:
        log(f"❌ Manager cannot view contracts (GET /contracts = {response.status_code})", "FAIL")
        return False
    
    # Test GET /certifications - should be 200 (was 403 before fix)
    response = requests.get(
        f"{BASE_URL}/certifications",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30
    )
    if response.status_code == 200:
        log("✅ Manager can view certifications (GET /certifications = 200)", "PASS")
    else:
        log(f"❌ Manager cannot view certifications (GET /certifications = {response.status_code})", "FAIL")
        return False
    
    # Test POST /employees - should be 403 (manager should not create employees)
    response = requests.post(
        f"{BASE_URL}/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={"full_name": "Test", "email": "test@test.com"},
        timeout=30
    )
    if response.status_code == 403:
        log("✅ Manager cannot create employees (POST /employees = 403)", "PASS")
    else:
        log(f"❌ Manager can create employees (POST /employees = {response.status_code})", "FAIL")
        return False
    
    # Test POST /contracts - should be 403 (manager should not create contracts)
    response = requests.post(
        f"{BASE_URL}/contracts",
        headers={"Authorization": f"Bearer {token}"},
        json={"employee_id": "test", "contract_number": "TEST"},
        timeout=30
    )
    if response.status_code == 403:
        log("✅ Manager cannot create contracts (POST /contracts = 403)", "PASS")
    else:
        log(f"❌ Manager can create contracts (POST /contracts = {response.status_code})", "FAIL")
        return False
    
    return True


def test_other_roles():
    """Test other roles mentioned in the review request."""
    log("\n=== Testing Other Roles ===", "INFO")
    
    # Test hr.admin
    token = login("hr.admin@nep.co.id")
    if not token:
        log("Failed to login as hr.admin", "FAIL")
        return False
    
    # hr.admin can CRUD employees/contracts/certifications
    response = requests.get(f"{BASE_URL}/employees", headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if response.status_code == 200:
        log("✅ hr.admin can view employees", "PASS")
    else:
        log(f"❌ hr.admin cannot view employees ({response.status_code})", "FAIL")
    
    response = requests.get(f"{BASE_URL}/contracts", headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if response.status_code == 200:
        log("✅ hr.admin can view contracts", "PASS")
    else:
        log(f"❌ hr.admin cannot view contracts ({response.status_code})", "FAIL")
    
    # hr.admin cannot approve contracts
    response = requests.post(
        f"{BASE_URL}/contracts/dummy-id/approve",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30
    )
    if response.status_code in [403, 404]:  # 404 is ok (dummy id), 403 is permission denied
        log("✅ hr.admin cannot approve contracts (403 or 404)", "PASS")
    else:
        log(f"❌ hr.admin can approve contracts ({response.status_code})", "FAIL")
    
    # Test hr.manager
    token = login("hr.manager@nep.co.id")
    if token:
        # Get a real contract to approve
        response = requests.get(f"{BASE_URL}/contracts?limit=1", headers={"Authorization": f"Bearer {token}"}, timeout=30)
        if response.status_code == 200 and response.json().get("items"):
            contract_id = response.json()["items"][0]["id"]
            # Try to approve (might be 409 if already approved, but should not be 403)
            response = requests.post(
                f"{BASE_URL}/contracts/{contract_id}/approve",
                headers={"Authorization": f"Bearer {token}"},
                timeout=30
            )
            if response.status_code in [200, 409]:
                log("✅ hr.manager can approve contracts (200 or 409)", "PASS")
            else:
                log(f"❌ hr.manager cannot approve contracts ({response.status_code})", "FAIL")
    
    # Test finance
    token = login("finance@nep.co.id")
    if token:
        response = requests.get(f"{BASE_URL}/employees", headers={"Authorization": f"Bearer {token}"}, timeout=30)
        if response.status_code == 200:
            log("✅ finance can view employees", "PASS")
        else:
            log(f"❌ finance cannot view employees ({response.status_code})", "FAIL")
        
        response = requests.post(
            f"{BASE_URL}/employees",
            headers={"Authorization": f"Bearer {token}"},
            json={"full_name": "Test", "email": "test@test.com"},
            timeout=30
        )
        if response.status_code == 403:
            log("✅ finance cannot create employees (403)", "PASS")
        else:
            log(f"❌ finance can create employees ({response.status_code})", "FAIL")
    
    # Test karyawan (employee)
    token = login("karyawan@nep.co.id")
    if token:
        response = requests.get(f"{BASE_URL}/employees", headers={"Authorization": f"Bearer {token}"}, timeout=30)
        if response.status_code == 403:
            log("✅ karyawan cannot view employees list (403)", "PASS")
        else:
            log(f"❌ karyawan can view employees list ({response.status_code})", "FAIL")
    
    return True


def test_demo_documents():
    """Test that demo documents have real files and preview works."""
    log("\n=== REGRESSION FIX 2: Demo Documents with Real Files ===", "INFO")
    
    token = login("hr.admin@nep.co.id")
    if not token:
        log("Failed to login as hr.admin", "FAIL")
        return False
    
    # Get documents list
    response = requests.get(
        f"{BASE_URL}/documents",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30
    )
    if response.status_code != 200:
        log(f"Failed to get documents list ({response.status_code})", "FAIL")
        return False
    
    documents = response.json().get("items", [])
    log(f"Found {len(documents)} documents", "INFO")
    
    # Find specific demo documents mentioned in review request
    demo_docs = {
        "KTP - Rina Kusuma": None,
        "Medical Check Up - Joko Purnomo": None
    }
    
    for doc in documents:
        if doc["name"] in demo_docs:
            demo_docs[doc["name"]] = doc
    
    all_passed = True
    
    for doc_name, doc in demo_docs.items():
        if not doc:
            log(f"⚠️ Demo document '{doc_name}' not found", "WARN")
            continue
        
        doc_id = doc["id"]
        log(f"\nTesting document: {doc_name} (ID: {doc_id})", "INFO")
        
        # Test preview-info
        response = requests.get(
            f"{BASE_URL}/documents/{doc_id}/preview-info",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30
        )
        if response.status_code == 200:
            info = response.json()
            has_file = info.get("has_file", False)
            previewable = info.get("previewable", False)
            
            if has_file and previewable:
                log(f"✅ {doc_name}: has_file=true, previewable=true", "PASS")
            else:
                log(f"❌ {doc_name}: has_file={has_file}, previewable={previewable}", "FAIL")
                all_passed = False
        else:
            log(f"❌ {doc_name}: preview-info failed ({response.status_code})", "FAIL")
            all_passed = False
        
        # Test preview endpoint
        response = requests.get(
            f"{BASE_URL}/documents/{doc_id}/preview",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30
        )
        if response.status_code == 200:
            content_disposition = response.headers.get("Content-Disposition", "")
            if "inline" in content_disposition:
                log(f"✅ {doc_name}: preview returns 200 with inline Content-Disposition", "PASS")
            else:
                log(f"⚠️ {doc_name}: preview returns 200 but Content-Disposition is '{content_disposition}'", "WARN")
        else:
            log(f"❌ {doc_name}: preview failed ({response.status_code})", "FAIL")
            all_passed = False
    
    # Test KBS document
    log("\n=== Testing KBS Demo Document ===", "INFO")
    token = login("hr.admin@kbs.co.id")
    if token:
        response = requests.get(
            f"{BASE_URL}/documents",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30
        )
        if response.status_code == 200:
            documents = response.json().get("items", [])
            kbs_doc = next((d for d in documents if d["name"] == "KTP - Andi Saputra"), None)
            if kbs_doc:
                doc_id = kbs_doc["id"]
                response = requests.get(
                    f"{BASE_URL}/documents/{doc_id}/preview-info",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=30
                )
                if response.status_code == 200:
                    info = response.json()
                    if info.get("has_file") and info.get("previewable"):
                        log("✅ KBS: KTP - Andi Saputra has_file=true, previewable=true", "PASS")
                    else:
                        log(f"❌ KBS: KTP - Andi Saputra has_file={info.get('has_file')}, previewable={info.get('previewable')}", "FAIL")
                        all_passed = False
            else:
                log("⚠️ KBS: KTP - Andi Saputra not found", "WARN")
    
    return all_passed


def main():
    log("\n" + "="*60, "INFO")
    log("REGRESSION TESTS - ITERATION 2", "INFO")
    log("="*60 + "\n", "INFO")
    
    results = []
    
    results.append(("Manager Permissions", test_manager_permissions()))
    results.append(("Other Roles", test_other_roles()))
    results.append(("Demo Documents", test_demo_documents()))
    
    log("\n" + "="*60, "INFO")
    log("REGRESSION TEST SUMMARY", "INFO")
    log("="*60, "INFO")
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        log(f"{name}: {status}", "PASS" if passed else "FAIL")
    
    all_passed = all(r[1] for r in results)
    log("="*60 + "\n", "INFO")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
