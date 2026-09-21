"""Quick backend test for Recruitment Tahap B APIs (interview, approval, offering).
Uses existing preview candidates to minimize mutations.
"""
import sys
import requests

sys.path.insert(0, "/app/backend")
from app.seed import DEMO_PASSWORD

BASE_URL = "https://payroll-deploy-check.preview.emergentagent.com/api"
TIMEOUT = 90  # High timeout for remote DB

# Preview candidate IDs from review request
ANDINI_ID = "7f522bd3-c770-4891-adbc-c36d27e00499"  # interview_scheduled
DIMAS_ID = "66e0581a-dafd-4517-bd68-7b4275deaad3"  # awaiting_approval
BAGUS_ID = "25b527a9-7653-4c1c-9fa6-81b6fd1df909"  # offering_accepted
MAYA_ID = "ff722908-851d-46b8-9e15-e0ad28a54bb7"  # offering_declined
RAKA_ID = "23999502-3f8c-4693-a0dc-61f21d74a530"  # rejected

results = {"passed": 0, "failed": 0, "tests": []}

def login(email):
    """Login and return auth headers."""
    try:
        r = requests.post(f"{BASE_URL}/auth/login", 
                         json={"email": email, "password": DEMO_PASSWORD}, 
                         timeout=TIMEOUT)
        r.raise_for_status()
        return {"Authorization": f"Bearer {r.json()['access_token']}"}
    except Exception as e:
        print(f"❌ Login failed for {email}: {e}")
        return None

def test(name, func):
    """Run a test and record result."""
    try:
        func()
        results["passed"] += 1
        results["tests"].append({"name": name, "status": "PASS"})
        print(f"✅ {name}")
        return True
    except AssertionError as e:
        results["failed"] += 1
        results["tests"].append({"name": name, "status": "FAIL", "error": str(e)})
        print(f"❌ {name}: {e}")
        return False
    except Exception as e:
        results["failed"] += 1
        results["tests"].append({"name": name, "status": "ERROR", "error": str(e)})
        print(f"❌ {name}: {e}")
        return False

print("=" * 80)
print("RECRUITMENT TAHAP B - BACKEND API TESTS")
print("=" * 80)

# Login
print("\n[1/6] Authenticating...")
hr = login("hr.admin@nep.co.id")
hrm = login("hr.manager@nep.co.id")
own = login("owner@nep.co.id")
kbs = login("hr.admin@kbs.co.id")

if not all([hr, hrm, own, kbs]):
    print("\n❌ Authentication failed. Cannot proceed.")
    sys.exit(1)

print("✅ All logins successful")

# Test interviewers endpoint
print("\n[2/6] Testing Interviewers API...")
def test_interviewers():
    r = requests.get(f"{BASE_URL}/recruitment/interviewers", headers=hr, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    assert "items" in data, "Response missing 'items'"
    assert len(data["items"]) > 0, "No interviewers found"
test("GET /recruitment/interviewers returns list", test_interviewers)

# Test interviews for Andini (interview_scheduled)
print("\n[3/6] Testing Interviews API...")
def test_interviews():
    r = requests.get(f"{BASE_URL}/recruitment/candidates/{ANDINI_ID}/interviews", headers=hr, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    assert "items" in data, "Response missing 'items'"
    print(f"   Andini has {len(data['items'])} interviews")
test("GET /candidates/{id}/interviews returns list", test_interviews)

# Test approvals for Dimas (awaiting_approval)
print("\n[4/6] Testing Approvals API...")
def test_approvals():
    r = requests.get(f"{BASE_URL}/recruitment/candidates/{DIMAS_ID}/approvals", headers=hr, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    assert "workflow_available" in data, "Response missing 'workflow_available'"
    assert "rounds" in data, "Response missing 'rounds'"
    print(f"   Dimas approval: workflow_available={data['workflow_available']}, rounds={len(data['rounds'])}")
test("GET /candidates/{id}/approvals returns workflow state", test_approvals)

def test_approval_steps():
    r = requests.get(f"{BASE_URL}/recruitment/candidates/{DIMAS_ID}/approvals", headers=hr, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    assert data["workflow_available"] is True, "Workflow not available"
    assert len(data["rounds"]) > 0, "No approval rounds"
    steps = data["rounds"][0]["steps"]
    assert len(steps) == 2, f"Expected 2 steps, got {len(steps)}"
    print(f"   Step 1: {steps[0]['step_name']} ({steps[0]['decision']}), Step 2: {steps[1]['step_name']} ({steps[1]['decision']})")
test("Approval workflow has 2 steps (hr_manager, company_owner)", test_approval_steps)

# Test offerings for Bagus (offering_accepted)
print("\n[5/6] Testing Offerings API...")
def test_offerings():
    r = requests.get(f"{BASE_URL}/recruitment/candidates/{BAGUS_ID}/offerings", headers=hr, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    assert "items" in data, "Response missing 'items'"
    assert "active" in data, "Response missing 'active'"
    print(f"   Bagus has {len(data['items'])} offerings, active={data['active'] is not None}")
test("GET /candidates/{id}/offerings returns list", test_offerings)

def test_offering_accepted():
    r = requests.get(f"{BASE_URL}/recruitment/candidates/{BAGUS_ID}/offerings", headers=hr, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    assert data["active"] is not None, "No active offering"
    assert data["active"]["offer_status"] == "accepted", f"Expected 'accepted', got '{data['active']['offer_status']}'"
    print(f"   Active offering status: {data['active']['offer_status']}")
test("Offering accepted has correct status", test_offering_accepted)

# Test Maya (offering_declined with v2 draft)
def test_maya_offerings():
    r = requests.get(f"{BASE_URL}/recruitment/candidates/{MAYA_ID}/offerings", headers=hr, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    assert len(data["items"]) >= 2, f"Expected at least 2 offerings, got {len(data['items'])}"
    versions = [o["version"] for o in data["items"]]
    assert 2 in versions, f"Version 2 not found in {versions}"
    print(f"   Maya offerings: {len(data['items'])} total, versions={sorted(versions)}")
test("Maya has offering history with v2 draft", test_maya_offerings)

# Test pipeline endpoint (aggregated data)
print("\n[6/6] Testing Pipeline API...")
def test_pipeline():
    r = requests.get(f"{BASE_URL}/recruitment/candidates/{ANDINI_ID}/pipeline", headers=hr, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    assert "candidate" in data, "Response missing 'candidate'"
    assert "interviews" in data, "Response missing 'interviews'"
    assert "approval" in data, "Response missing 'approval'"
    assert "offerings" in data, "Response missing 'offerings'"
    print(f"   Pipeline: {len(data['interviews'])} interviews, {len(data['offerings']['items'])} offerings")
test("GET /candidates/{id}/pipeline returns aggregated data", test_pipeline)

# Test summary endpoint includes Tahap B stats
def test_summary():
    r = requests.get(f"{BASE_URL}/recruitment/summary", headers=hr, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    assert "interview_scheduled" in data, "Response missing 'interview_scheduled'"
    assert "awaiting_approval" in data, "Response missing 'awaiting_approval'"
    assert "approved" in data, "Response missing 'approved'"
    assert "offering" in data, "Response missing 'offering'"
    assert "offering_accepted" in data, "Response missing 'offering_accepted'"
    print(f"   Stats: interview_scheduled={data['interview_scheduled']}, awaiting_approval={data['awaiting_approval']}, approved={data['approved']}, offering_active={data.get('offering_active', 0)}, offering_accepted={data['offering_accepted']}")
test("GET /recruitment/summary includes Tahap B stats", test_summary)

# Test tenant isolation
print("\n[SECURITY] Testing Tenant Isolation...")
def test_isolation_interviews():
    r = requests.get(f"{BASE_URL}/recruitment/candidates/{ANDINI_ID}/interviews", headers=kbs, timeout=TIMEOUT)
    assert r.status_code == 404, f"Expected 404, got {r.status_code}"
    print(f"   KBS access to NEP candidate interviews: {r.status_code}")
test("KBS cannot access NEP candidate interviews (404)", test_isolation_interviews)

def test_isolation_approvals():
    r = requests.get(f"{BASE_URL}/recruitment/candidates/{DIMAS_ID}/approvals", headers=kbs, timeout=TIMEOUT)
    assert r.status_code == 404, f"Expected 404, got {r.status_code}"
test("KBS cannot access NEP candidate approvals (404)", test_isolation_approvals)

def test_isolation_offerings():
    r = requests.get(f"{BASE_URL}/recruitment/candidates/{BAGUS_ID}/offerings", headers=kbs, timeout=TIMEOUT)
    assert r.status_code == 404, f"Expected 404, got {r.status_code}"
test("KBS cannot access NEP candidate offerings (404)", test_isolation_offerings)

# Summary
print("\n" + "=" * 80)
print(f"RESULTS: {results['passed']} passed, {results['failed']} failed")
print("=" * 80)

if results["failed"] > 0:
    print("\nFailed tests:")
    for t in results["tests"]:
        if t["status"] != "PASS":
            print(f"  - {t['name']}: {t.get('error', 'Unknown error')}")

sys.exit(0 if results["failed"] == 0 else 1)
