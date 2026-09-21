"""Smoke test API Time Management V1 (development)."""
import json
import os
import random
import sys
import urllib.request

SUF = random.randint(1, 20)

BASE = "http://localhost:8001/api"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _demo_password() -> str:
    """Kata sandi akun demo: dari env DEMO_PASSWORD, atau konstanta seed (tidak ditulis ulang di sini)."""
    value = os.environ.get("DEMO_PASSWORD")
    if value:
        return value
    from app.seed import DEMO_PASSWORD
    return DEMO_PASSWORD

PWD = _demo_password()
ok = fail = 0


def call(method, path, token=None, body=None, expect=None):
    global ok, fail
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data) as r:
            raw = r.read()
            code = r.status
            try:
                payload = json.loads(raw or b"{}")
            except Exception:
                payload = {"binary_bytes": len(raw)}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw or b"{}")
        except Exception:
            payload = {"raw": raw[:200].decode(errors="ignore")}
        code = e.code
    good = code == (expect or 200) or (expect is None and 200 <= code < 300)
    if good:
        ok += 1
        print(f"  OK  {method} {path} -> {code}")
    else:
        fail += 1
        print(f"  FAIL {method} {path} -> {code} {str(payload)[:400]}")
    return code, payload


def login(email):
    _, p = call("POST", "/auth/login", body={"email": email, "password": PWD})
    return p.get("access_token")


print("== LOGIN ==")
hr = login("hr.admin@nep.co.id")
emp = login("karyawan@nep.co.id")
sup = login("supervisor@nep.co.id")
hrm = login("hr.manager@nep.co.id")
kbs = login("hr.admin@kbs.co.id")

print("== MASTER ==")
_, shifts = call("GET", "/time/shifts", hr)
shift_map = {s["code"]: s["id"] for s in shifts["items"]}
_, lts = call("GET", "/time/leave-types", hr)
lt_map = {s["code"]: s["id"] for s in lts["items"]}
call("GET", "/time/catalog", hr)
call("GET", "/time/policies", hr)

print("== EMPLOYEE / LOCATION ==")
_, emps = call("GET", "/employees?limit=50", hr)
rows = emps.get("items", emps.get("data", []))
rina = next((e for e in rows if "Rina" in (e.get("full_name") or "")), None)
print("   employee:", rina and rina["full_name"], rina and rina.get("id"))
_, locs = call("GET", "/master/work-locations?limit=50", hr)
lrows = locs.get("items", [])
ho = next((l for l in lrows if l.get("code") == "LOC-HO"), None)
print("   location:", ho and ho["code"], ho and (ho.get("latitude"), ho.get("longitude"), ho.get("radius_meter")))

print("== JADWAL (bulk) ==")
dates = ["2026-09-21", "2026-09-22", "2026-09-23"]
call("POST", "/schedules/bulk", hr, {
    "employee_ids": [rina["id"]],
    "date_from": dates[0], "date_to": dates[-1],
    "shift_id": shift_map["SHIFT-P"],
    "work_location_id": ho["id"],
    "overwrite_existing": True,
}, expect=201)
call("GET", f"/schedules?date_from={dates[0]}&date_to={dates[-1]}", hr)
call("GET", "/schedules/imports/template", hr)

print("== ABSENSI SELF ==")
call("GET", "/attendance/me/today", emp)
lat, lon = ho["latitude"], ho["longitude"]
call("POST", "/attendance/check-in", emp,
     {"latitude": lat, "longitude": lon, "accuracy": 10, "note": "Masuk normal"})
call("POST", "/attendance/check-out", emp,
     {"latitude": lat, "longitude": lon, "accuracy": 10})
call("GET", "/attendance/me", emp)
call("GET", "/attendance?page=1&limit=20", hr)
call("GET", "/attendance/dashboard", hr)
call("GET", "/attendance/recap?period_key=2026-09", hr)
call("GET", "/attendance/exceptions?period_key=2026-09", hr)

print("== ABSENSI MANUAL + KOREKSI ==")
_, man = call("POST", "/attendance/manual", hr, {
    "employee_id": rina["id"], "work_date": "2026-09-22",
    "check_in_at": "2026-09-22T09:30:00+07:00",
    "check_out_at": "2026-09-22T16:00:00+07:00",
    "reason": "Absensi manual uji terlambat & pulang cepat",
}, expect=201)
att_id = man.get("id") or (man.get("attendance") or {}).get("id")
print("   manual attendance status:", (man.get("attendance") or man).get("attendance_status"),
      "late:", (man.get("attendance") or man).get("late_minutes"),
      "early:", (man.get("attendance") or man).get("early_leave_minutes"))
_, corr = call("POST", "/attendance/corrections", emp, {
    "work_date": "2026-09-22",
    "correction_type": "wrong_time",
    "proposed_check_in_at": "2026-09-22T08:00:00+07:00",
    "proposed_check_out_at": "2026-09-22T17:00:00+07:00",
    "reason": "Lupa absen, jam sebenarnya 08:00-17:00",
}, expect=201)
call("GET", "/attendance/corrections", hr)
call("GET", "/attendance/approvals", sup)

print("== CUTI ==")
_, lr = call("POST", "/leave/requests", emp, {
    "leave_type_id": lt_map["CT-TAHUNAN"],
    "start_date": f"2026-11-{SUF:02d}", "end_date": f"2026-11-{SUF:02d}",
    "day_part": "full_day", "reason": "Cuti tahunan keluarga",
}, expect=201)
lr_id = lr.get("id") or (lr.get("request") or {}).get("id")
call("GET", "/leave/requests", hr)
call("GET", "/leave/approvals", sup)
call("GET", "/leave/balances", hr)
call("GET", f"/leave/ledger?employee_id={rina['id']}", hr)
call("GET", "/leave/dashboard", hr)

print("== LEMBUR ==")
_, ot = call("POST", "/overtime/requests", emp, {
    "work_date": f"2026-09-{SUF:02d}",
    "planned_start_time": "17:30", "planned_end_time": "20:00",
    "reason": "Menyelesaikan laporan bulanan",
}, expect=201)
call("GET", "/overtime/requests", hr)
call("GET", "/overtime/approvals", sup)

print("== PERIODE ==")
call("GET", "/time/periods", hr)
call("POST", "/time/periods/close", hrm, {"period_key": "2026-08", "notes": "Tutup periode uji"})
code, blocked = call("POST", "/attendance/manual", hr, {
    "employee_id": rina["id"], "work_date": "2026-08-10",
    "check_in_at": "2026-08-10T08:00:00+07:00",
    "check_out_at": "2026-08-10T17:00:00+07:00",
    "reason": "Harus ditolak karena periode tertutup",
}, expect=409)
call("POST", "/time/periods/reopen", hrm, {"period_key": "2026-08", "reason": "Buka kembali untuk uji"})

print("== ISOLASI TENANT ==")
call("GET", f"/attendance/{att_id}", kbs, expect=404)
_, kshifts = call("GET", "/time/shifts", kbs)
print("   KBS shift count:", kshifts["total"], "-> tidak boleh melihat data NEP")

print("== EXPORT ==")
call("GET", "/attendance/recap/export?period_key=2026-09", hr)
call("GET", "/leave/export", hr)
call("GET", "/overtime/export", hr)
call("GET", "/attendance/imports/template", hr)

print(f"\nRINGKASAN: OK={ok} FAIL={fail}")
sys.exit(1 if fail else 0)
