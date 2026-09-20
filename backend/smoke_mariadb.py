"""Quick smoke test of the MariaDB adapter through the live API (run: python smoke_mariadb.py)."""
import json
import sys

import requests

BASE = "http://localhost:8001/api"
results = []


def check(name, ok, info=""):
    results.append((name, ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  -> {info}" if info else ""))


def call(method, path, token=None, **kw):
    headers = kw.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.request(method, BASE + path, headers=headers, timeout=60, **kw)
    return r


r = call("POST", "/auth/login", json={"email": "hr.admin@nep.co.id", "password": "Hris#2026"})
check("login", r.status_code == 200, r.text[:200] if r.status_code != 200 else "")
data = r.json()
token = data.get("access_token")
company_id = (data.get("company") or {}).get("id") or data.get("company_id")

r = call("GET", "/auth/me", token)
check("auth/me", r.status_code == 200, r.text[:150] if r.status_code != 200 else "")

endpoints = [
    "/companies", "/master/registry", "/master/branches?page=1&limit=5", "/master/departments?q=a",
    "/master/positions/options", "/employees?page=1&limit=10", "/employees?q=rina", "/users",
    "/roles", "/approval-workflows", "/approval-workflows/catalog", "/documents", "/contracts", "/certifications",
    "/dashboard/summary", "/reminders/expiry", "/audit-logs?limit=20",
    "/payroll/components", "/payroll/salaries", "/payroll/runs", "/payroll/config",
    "/mail/settings", "/mail/reminder/preview", "/mail/reminder/logs",
    "/policies/catalog", "/policies/effective", "/policies/overrides", "/modules", "/payroll/my/payslips",
]
for ep in endpoints:
    r = call("GET", ep, token)
    check(f"GET {ep}", r.status_code in (200, 403), f"{r.status_code} {r.text[:120]}")

# create + update + delete a master record
r = call("POST", "/master/branches", token, json={"code": "SMK-01", "name": "Cabang Smoke", "city": "Jakarta"})
check("POST branch", r.status_code in (200, 201), r.text[:200])
if r.status_code in (200, 201):
    bid = r.json().get("id") or r.json().get("item", {}).get("id")
    r2 = call("PUT", f"/master/branches/{bid}", token, json={"code": "SMK-01", "name": "Cabang Smoke Edit"})
    check("PUT branch", r2.status_code == 200, r2.text[:200])
    r3 = call("GET", f"/master/branches?q=Smoke", token)
    check("search regex branch", r3.status_code == 200 and any("Smoke" in (i.get("name") or "") for i in r3.json().get("items", [])), r3.text[:150])
    r4 = call("POST", "/master/branches", token, json={"code": "SMK-01", "name": "Dup"})
    check("duplicate code -> 409", r4.status_code == 409, r4.status_code)
    r5 = call("DELETE", f"/master/branches/{bid}", token)
    check("DELETE branch", r5.status_code in (200, 204), r5.text[:200])

# employee create (auto number via $inc find_one_and_update)
r = call("POST", "/employees", token, json={"full_name": "Smoke Tester", "gender": "L", "join_date": "2026-01-01"})
check("POST employee ($inc)", r.status_code in (200, 201), r.text[:250])
emp_id = r.json().get("id") if r.status_code in (200, 201) else None
if emp_id:
    r = call("GET", f"/employees/{emp_id}", token)
    check("GET employee detail", r.status_code == 200 and (r.json().get("employee") or r.json()).get("employee_number"), r.text[:150])
    r = call("DELETE", f"/employees/{emp_id}", token)
    check("DELETE employee", r.status_code in (200, 204), r.text[:150])

# payroll run lifecycle (create -> recalc -> submit) uses $push history
r = call("GET", "/payroll/runs", token)
runs = r.json().get("items", r.json()) if r.status_code == 200 else []
check("payroll runs list", r.status_code == 200, f"{len(runs)} runs")
if runs:
    run = runs[0]
    r = call("GET", f"/payroll/runs/{run['id']}", token)
    check("payroll run detail", r.status_code == 200 and isinstance(r.json().get("items", r.json().get("run", {}).get("items", [])), list), r.text[:150])
    r = call("GET", f"/payroll/runs/{run['id']}/export", token)
    check("payroll export excel", r.status_code in (200, 400, 409), r.status_code)

r = call("POST", "/payroll/runs", token, json={"year": 2031, "month": 1})
check("POST payroll run", r.status_code in (200, 201), r.text[:250])
if r.status_code in (200, 201):
    rid = r.json()["id"]
    r = call("POST", f"/payroll/runs/{rid}/submit", token, json={"note": "smoke"})
    check("submit run ($push history)", r.status_code == 200 and len(r.json().get("history", [])) >= 1, r.text[:250])
    r = call("DELETE", f"/payroll/runs/{rid}", token)
    check("DELETE run", r.status_code in (200, 204, 400, 403, 409), r.text[:150])

# superadmin
r = call("POST", "/auth/login", json={"email": "superadmin@hris.id", "password": "Hris#2026"})
check("superadmin login", r.status_code == 200, r.text[:150])
if r.status_code == 200:
    t2 = r.json()["access_token"]
    r = call("GET", "/companies", t2)
    check("superadmin companies", r.status_code == 200 and len(r.json() if isinstance(r.json(), list) else r.json().get("items", [])) >= 2, r.text[:150])

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
sys.exit(1 if failed else 0)
