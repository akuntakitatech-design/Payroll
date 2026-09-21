"""Smoke test API — Absensi ESS (Alur Operasional Karyawan), DEVELOPMENT.

Menguji: jadwal hari ini, Absen Masuk/Pulang GPS (dalam & luar radius), idempotensi,
proteksi double, approval lokasi (setujui/tolak), GPS Saja, GPS gagal, scope karyawan,
tenant isolation, serta kalkulasi menit (unit) untuk telat/pulang cepat/overnight.

Dijalankan manual: python smoke_ess.py   (kata sandi demo dari env DEMO_PASSWORD / konstanta seed, tidak dicetak)
"""
import json
import os
import sys
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BASE = "http://localhost:8001/api"

def _demo_password() -> str:
    """Kata sandi akun demo: dari env DEMO_PASSWORD, atau konstanta seed (tidak ditulis ulang di sini)."""
    value = os.environ.get("DEMO_PASSWORD")
    if value:
        return value
    from app.seed import DEMO_PASSWORD
    return DEMO_PASSWORD

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
PWD = _demo_password()
ok = fail = 0


def call(method, path, token=None, body=None, expect=None, quiet=False):
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
            payload = json.loads(raw or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw or b"{}")
        except Exception:  # noqa: BLE001
            payload = {"raw": raw[:200].decode(errors="ignore")}
        code = e.code
    good = code == expect if expect else 200 <= code < 300
    if good:
        ok += 1
        if not quiet:
            print(f"  OK   {method} {path} -> {code}")
    else:
        fail += 1
        print(f"  FAIL {method} {path} -> {code} (harap {expect or '2xx'}) {str(payload)[:300]}")
    return code, payload


def check(cond, label):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK   {label}")
    else:
        fail += 1
        print(f"  FAIL {label}")


def login(email):
    _, p = call("POST", "/auth/login", body={"email": email, "password": PWD}, quiet=True)
    return p.get("access_token")


# --------------------------------------------------------------------------
print("== UNIT: kalkulasi menit (timekeeping) ==")
from app.core import timekeeping as tk  # noqa: E402

tz = ZoneInfo("Asia/Jakarta")
shift_p = {"start_time": "08:00", "end_time": "17:00", "break_start": "12:00", "break_end": "13:00",
           "late_tolerance_minutes": 15, "early_leave_tolerance_minutes": 0}
shift_m = {"start_time": "23:00", "end_time": "07:00", "break_start": "03:00", "break_end": "04:00",
           "late_tolerance_minutes": 10, "early_leave_tolerance_minutes": 0}


def local(d, hhmm):
    h, m = map(int, hhmm.split(":"))
    return datetime(d.year, d.month, d.day, h, m, tzinfo=tz).astimezone(timezone.utc)


d0 = date(2026, 9, 21)
m = tk.compute_attendance_metrics(shift_p, d0.isoformat(), tz, local(d0, "08:10"), local(d0, "17:00"))
check(m["late_minutes"] == 0 and m["early_leave_minutes"] == 0, f"TEST1 normal 08:10 (toleransi 15) -> late=0 ({m['late_minutes']})")
m = tk.compute_attendance_metrics(shift_p, d0.isoformat(), tz, local(d0, "08:40"), local(d0, "17:00"))
# Konvensi existing: menit terlambat dihitung setelah toleransi (40 - 15 = 25).
check(m["late_minutes"] == 25, f"TEST2 terlambat 08:40 (toleransi 15) -> late_minutes=25 ({m['late_minutes']})")
check(m["actual_work_minutes"] == (17 * 60 - 8 * 60 - 40) - 60,
      f"TEST3 actual_work_minutes dikurangi istirahat 60m ({m['actual_work_minutes']})")
m = tk.compute_attendance_metrics(shift_p, d0.isoformat(), tz, local(d0, "08:00"), local(d0, "16:30"))
check(m["early_leave_minutes"] == 30, f"TEST4 pulang cepat 16:30 -> early_leave_minutes=30 ({m['early_leave_minutes']})")
check(tk.shift_is_overnight(shift_m), "TEST13 shift 23:00-07:00 terdeteksi overnight")
m = tk.compute_attendance_metrics(shift_m, d0.isoformat(), tz, local(d0, "23:05"), local(d0 + timedelta(days=1), "07:00"))
check(m["late_minutes"] == 0 and m["actual_work_minutes"] == 8 * 60 - 60 - 5,
      f"TEST13 overnight satu shift: late=0, actual={m['actual_work_minutes']} (harap 415)")
check(m["scheduled_minutes"] == 8 * 60 - 60, f"TEST13 scheduled_minutes overnight = 420 ({m['scheduled_minutes']})")

# Haversine
d = tk.haversine_meters(-6.2265, 106.8097, -6.2265, 106.8107)
check(100 < d < 120, f"Haversine ~110 m untuk 0.001 deg longitude ({d:.1f})")

# --------------------------------------------------------------------------
print("== LOGIN ==")
hr = login("hr.admin@nep.co.id")
emp = login("karyawan@nep.co.id")
sup = login("supervisor@nep.co.id")
kbs_hr = login("hr.admin@kbs.co.id")
kbs_emp = login("karyawan@kbs.co.id")
check(all([hr, emp, sup, kbs_hr, kbs_emp]), "Semua akun demo berhasil login")

print("== MASTER & JADWAL (HR) ==")
_, shifts = call("GET", "/time/shifts", hr)
shift_map = {s["code"]: s["id"] for s in shifts["items"]}
_, locs = call("GET", "/master/work-locations?limit=50", hr)
loc_map = {l["code"]: l for l in locs["items"]}
ho = loc_map["LOC-HO"]
check(ho.get("attendance_location_policy") == "outside_requires_approval", "LOC-HO policy = outside_requires_approval")

_, emps = call("GET", "/employees?limit=100", hr)
emp_map = {e["employee_number"]: e for e in emps["items"]}
rina = emp_map["NEP-0001"]
bambang = emp_map["NEP-0002"]

today = datetime.now(tz).date()
first = today.replace(day=1)
nxt = (first + timedelta(days=40)).replace(day=1)
last_next = (nxt + timedelta(days=40)).replace(day=1) - timedelta(days=1)
code, _ = call("POST", "/schedules/bulk", hr, {
    "employee_ids": [rina["id"], bambang["id"]], "date_from": first.isoformat(),
    "date_to": last_next.isoformat(), "shift_id": shift_map["SHIFT-P"],
    "weekdays": [1, 2, 3, 4, 5], "overwrite_existing": False,
    "notes": "Jadwal DEVELOPMENT untuk uji Absensi ESS"}, expect=201)

# Karyawan tidak boleh membuat jadwal / input manual / impor
call("POST", "/schedules/bulk", emp, {"employee_ids": [rina["id"]], "date_from": today.isoformat(),
                                       "date_to": today.isoformat(), "shift_id": shift_map["SHIFT-P"]}, expect=403)
call("POST", "/attendance/manual", emp, {"employee_id": rina["id"], "work_date": today.isoformat(),
                                          "check_in_at": f"{today} 08:00", "reason": "coba"}, expect=403)
call("GET", "/attendance/imports/template", emp, expect=403)

# Bersihkan absensi hari ini untuk Rina & Bambang (agar skenario dapat diulang) — via HR delete tidak ada,
# jadi gunakan endpoint list + cek; skenario mengasumsikan belum ada absensi hari ini.
_, mine = call("GET", "/attendance/me/today", emp)
check(mine.get("linked") is True and mine.get("has_schedule") is True, "Rina: /me/today linked & has_schedule")
check(mine.get("today_status", {}).get("label") in ("Belum Absen", "Hadir", "Terlambat", "Belum Absen Pulang",
                                                     "Menunggu Persetujuan Lokasi", "Pulang Cepat",
                                                     "Terlambat & Pulang Cepat", "Lokasi Ditolak"),
      f"Rina: today_status backend = {mine.get('today_status', {}).get('label')}")
check(mine.get("shift", {}) and mine["shift"].get("start_time") == "08:00", "Rina: shift hari ini SHIFT-P 08:00")
check(mine.get("work_location", {}).get("code") == "LOC-HO", "Rina: lokasi kerja LOC-HO")

fresh = mine.get("attendance") is None
if not fresh:
    print("  INFO Rina sudah punya absensi hari ini; skenario check-in dilewati (lihat idempotensi/double).")

print("== TEST 12: GPS tidak tersedia -> ditolak, tidak dibuat absensi palsu ==")
call("POST", "/attendance/check-in", emp, {"source": "web"}, expect=422 if fresh else 409)

print("== TEST 6: Absen Pulang tanpa Absen Masuk -> ditolak ==")
if fresh:
    call("POST", "/attendance/check-out", emp, {"latitude": ho["latitude"], "longitude": ho["longitude"],
                                                 "accuracy": 10, "source": "web"}, expect=409)

print("== TEST 1/7: Absen Masuk dalam radius + idempotensi + double ==")
rid = str(uuid.uuid4())
body_in = {"latitude": float(ho["latitude"]) + 0.0002, "longitude": float(ho["longitude"]), "accuracy": 12,
           "location_captured_at": datetime.now(timezone.utc).isoformat(), "source": "web", "client_request_id": rid}
if fresh:
    code, r1 = call("POST", "/attendance/check-in", emp, body_in)
    att = r1.get("attendance", {})
    check(att.get("check_in_geofence_result") == "inside", f"geofence_result inside (jarak {att.get('check_in_distance_meter')} m)")
    check(att.get("location_approval_status") == "not_required", "tidak perlu persetujuan lokasi")
    check(att.get("attendance_status") == "no_check_out", "status setelah masuk = Belum Absen Pulang")
    check(att.get("check_in_at") is not None, "check_in_at diisi waktu server")
    # retry dengan kunci sama -> 200 idempotent, record sama
    code, r2 = call("POST", "/attendance/check-in", emp, body_in)
    check(r2.get("idempotent") is True and r2.get("attendance", {}).get("id") == att.get("id"),
          "TEST5 retry client_request_id sama -> record sama (idempotent)")
# double dengan kunci berbeda -> 409
call("POST", "/attendance/check-in", emp, {**body_in, "client_request_id": str(uuid.uuid4())}, expect=409)
_, lst = call("GET", f"/attendance?work_date={today}&employee_id={rina['id']}", hr)
check(lst.get("total") == 1, f"TEST5 hanya 1 baris absensi Rina hari ini ({lst.get('total')})")

print("== TEST 3: Absen Pulang normal ==")
_, t2 = call("GET", "/attendance/me/today", emp)
if t2.get("can_check_out"):
    rid_out = str(uuid.uuid4())
    body_out = {**body_in, "client_request_id": rid_out}
    code, r3 = call("POST", "/attendance/check-out", emp, body_out)
    att = r3.get("attendance", {})
    check(att.get("check_out_at") is not None, "check_out_at diisi waktu server")
    check(att.get("check_out_geofence_result") == "inside", "geofence pulang inside")
    check(isinstance(att.get("actual_work_minutes"), int), f"actual_work_minutes dihitung ({att.get('actual_work_minutes')})")
    code, r4 = call("POST", "/attendance/check-out", emp, body_out)
    check(r4.get("idempotent") is True, "retry Absen Pulang kunci sama -> idempotent")
    call("POST", "/attendance/check-out", emp, {**body_in, "client_request_id": str(uuid.uuid4())}, expect=409)
_, t3 = call("GET", "/attendance/me/today", emp)
check(t3.get("can_check_in") is False and t3.get("can_check_out") is False, "setelah lengkap: tidak ada aksi absen tersisa")

print("== TEST 8/9: Luar radius (Bambang, LOC-SITE1) -> Menunggu Persetujuan -> approve ==")
_, bt = call("GET", "/attendance/me/today", sup)
site = loc_map["LOC-SITE1"]
if bt.get("attendance") is None:
    far = {"latitude": float(site["latitude"]) + 0.05, "longitude": float(site["longitude"]), "accuracy": 8, "source": "web"}
    # tanpa alasan -> 422
    call("POST", "/attendance/check-in", sup, {**far, "client_request_id": str(uuid.uuid4())}, expect=422)
    # alasan Lainnya tanpa keterangan -> 422
    call("POST", "/attendance/check-in", sup, {**far, "reason_code": "other", "reason": "", "client_request_id": str(uuid.uuid4())}, expect=422)
    code, r5 = call("POST", "/attendance/check-in", sup, {**far, "reason_code": "business_trip",
                                                          "reason": "Dinas ke kantor klien Samarinda",
                                                          "client_request_id": str(uuid.uuid4())})
    att = r5.get("attendance", {})
    check(att.get("attendance_status") == "awaiting_location_approval", "status = Menunggu Persetujuan Lokasi")
    check(att.get("location_approval_for") == "check_in", "approval_for = check_in")
    check(att.get("check_in_distance_meter", 0) > 1000, f"jarak tersimpan ({att.get('check_in_distance_meter')} m)")
    bambang_att_id = att.get("id")
else:
    bambang_att_id = bt["attendance"]["id"]
    print("  INFO Bambang sudah punya absensi hari ini.")

# Supervisor (atasan Bambang = dirinya sendiri) melihat daftar persetujuan
_, appr = call("GET", "/attendance/approvals?document_kind=attendance_location", sup)
target = next((i for i in appr.get("items", []) if i["detail"].get("id") == bambang_att_id), None)
if bt.get("attendance") is None:
    check(target is not None, "pengajuan lokasi muncul di Persetujuan Absensi (tahap Atasan)")
if target:
    d = target["detail"]
    check(d.get("approval_for_label") in ("Absen Masuk", "Absen Masuk & Pulang"), f"jenis absen tampil: {d.get('approval_for_label')}")
    check(d.get("check_in_latitude") is not None and d.get("map_url"), "GPS aktual + map link tersedia untuk penyetuju")
    check(d.get("location_reason_label") == "Dinas Luar", "alasan karyawan tampil (Dinas Luar)")
    call("POST", f"/attendance/approvals/{target['approval']['id']}/decide", sup, {"decision": "approved", "notes": "OK"})
# tahap 2: HR Admin (penyetuju sesuai Konfigurasi Alur Persetujuan)
_, appr2 = call("GET", "/attendance/approvals?document_kind=attendance_location", hr)
t2h = next((i for i in appr2.get("items", []) if i["detail"].get("id") == bambang_att_id), None)
if t2h:
    check(True, "tahap 2 (HR Admin) menerima pengajuan")
    call("POST", f"/attendance/approvals/{t2h['approval']['id']}/decide", kbs_hr, {"decision": "approved"}, expect=404)  # tenant lain
    call("POST", f"/attendance/approvals/{t2h['approval']['id']}/decide", emp, {"decision": "approved"}, expect=403)  # bukan penyetuju
    call("POST", f"/attendance/approvals/{t2h['approval']['id']}/decide", hr, {"decision": "approved", "notes": "Disetujui HR"})
_, det = call("GET", f"/attendance/{bambang_att_id}", hr)
a = det.get("attendance", {})
if bt.get("attendance") is None:  # hanya valid pada run pertama hari ini
    check(a.get("location_approval_status") == "approved" and a.get("attendance_status") != "awaiting_location_approval",
          f"TEST9 setelah approve: valid, status={a.get('attendance_status_label')}")
    check(len(det.get("approval", {}).get("steps", [])) >= 2 and all(
        st.get("decision") == "approved" for st in det["approval"]["steps"]), "histori approval 2 tahap tersimpan")
else:
    print(f"  INFO status Bambang saat ini: {a.get('attendance_status_label')} (run ulang)")

print("== TEST 10: Absen Pulang luar radius -> putaran approval baru -> TOLAK -> Lokasi Ditolak, histori tetap ==")
_, bt2 = call("GET", "/attendance/me/today", sup)
if bt2.get("can_check_out"):
    far_out = {"latitude": float(site["latitude"]) + 0.03, "longitude": float(site["longitude"]), "accuracy": 9,
               "source": "web", "client_request_id": str(uuid.uuid4())}
    call("POST", "/attendance/check-out", sup, far_out, expect=422)  # alasan wajib
    code, r6 = call("POST", "/attendance/check-out", sup, {**far_out, "reason_code": "field_duty",
                                                           "reason": "Langsung pulang dari lokasi survei"})
    att = r6.get("attendance", {})
    check(att.get("location_approval_status") == "pending" and att.get("location_approval_for") == "check_out",
          f"Absen Pulang luar radius -> pending untuk check_out (round {att.get('location_approval_round')})")
    check(att.get("check_out_location_reason_code") == "field_duty", "alasan pulang tersimpan terpisah")
    check(att.get("check_out_distance_meter", 0) > 1000, "jarak pulang tersimpan")
    _, ap = call("GET", "/attendance/approvals?document_kind=attendance_location", sup)
    t = next((i for i in ap.get("items", []) if i["detail"].get("id") == bambang_att_id), None)
    check(t is not None and t["detail"].get("approval_for") == "check_out", "penyetuju melihat pengajuan jenis Absen Pulang")
    if t:
        check(t["detail"].get("check_out_map_url") and t["detail"].get("check_out_accuracy") == 9,
              "detail pulang: map link + akurasi tampil")
        call("POST", f"/attendance/approvals/{t['approval']['id']}/decide", sup, {"decision": "approved", "notes": "OK"})
    _, ap2 = call("GET", "/attendance/approvals?document_kind=attendance_location", hr)
    t2 = next((i for i in ap2.get("items", []) if i["detail"].get("id") == bambang_att_id), None)
    if t2:
        call("POST", f"/attendance/approvals/{t2['approval']['id']}/decide", hr,
             {"decision": "rejected", "notes": "Tidak ada penugasan lapangan hari ini"})
    _, det2 = call("GET", f"/attendance/{bambang_att_id}", hr)
    a2 = det2.get("attendance", {})
    check(a2.get("attendance_status") == "location_rejected" and a2.get("attendance_status_label") == "Lokasi Ditolak",
          f"TEST10 status = {a2.get('attendance_status_label')}")
    check(a2.get("check_in_at") and a2.get("check_out_at") and a2.get("is_valid") is False,
          "TEST10 histori absensi tetap tersimpan (masuk & pulang), is_valid=false")
    check(len(det2.get("approval", {}).get("history", [])) >= 2, "histori putaran approval sebelumnya tetap ada")
    _, hist_b = call("GET", "/attendance/me", sup)
    check(any(i["id"] == bambang_att_id and i["attendance_status"] == "location_rejected" for i in hist_b.get("items", [])),
          "karyawan melihat status Lokasi Ditolak di riwayatnya")
else:
    print("  INFO Bambang sudah Absen Pulang; TEST10 dilewati pada run ulang.")

print("== TEST 15/14: scope karyawan & tenant ==")
_, own = call("GET", f"/attendance?work_date={today}", emp)
check(all(i["employee_id"] == rina["id"] for i in own.get("items", [])) and own.get("total", 0) <= 1,
      "TEST15 karyawan hanya melihat baris dirinya di GET /attendance")
_, own_sched = call("GET", f"/schedules?period={today.strftime('%Y-%m')}", emp)
check(all(i["employee_id"] == rina["id"] for i in own_sched.get("items", [])), "TEST15 karyawan hanya melihat jadwal sendiri")
call("GET", f"/attendance/{bambang_att_id}", emp, expect=404)  # bukan miliknya
_, hist = call("GET", "/attendance/me", emp)
check(all(i["employee_id"] == rina["id"] for i in hist.get("items", [])), "TEST16 riwayat /me hanya milik sendiri")
check(all("work_location_name" in i for i in hist.get("items", [])), "riwayat memuat lokasi kerja")
call("GET", f"/attendance/{bambang_att_id}", kbs_hr, expect=404)  # tenant lain
_, kbs_list = call("GET", f"/attendance?work_date={today}", kbs_hr)
check(all(i["employee_id"] not in (rina["id"], bambang["id"]) for i in kbs_list.get("items", [])),
      "TEST14 KBS tidak melihat absensi NEP")
_, kbs_appr = call("GET", "/attendance/approvals", kbs_hr)
check(all(i["detail"].get("id") != bambang_att_id for i in kbs_appr.get("items", [])), "TEST14 approval NEP tidak bocor ke KBS")

print("== TEST 11: GPS Saja (ubah policy LOC-WH, karyawan lapangan) ==")
wh = loc_map["LOC-WH"]
call("PUT", f"/master/work-locations/{wh['id']}", hr, {"attendance_location_policy": "gps_only"})
_, wh2 = call("GET", f"/master/work-locations/{wh['id']}", hr)
check(wh2.get("attendance_location_policy") == "gps_only", "Master Lokasi Kerja menyimpan policy gps_only")
pol = tk.evaluate_geofence({**wh2}, {"default_geofence_policy": "outside_requires_approval",
                                     "default_radius_meter": 150, "gps_accuracy_max_meter": 150},
                           float(wh2["latitude"]) + 0.2, float(wh2["longitude"]), 10)
check(pol["requires_approval"] is False and pol["blocked"] is False and pol["geofence_result"] == "inside",
      f"gps_only: jauh {pol['distance_meter']:.0f} m tetap diterima tanpa persetujuan")
call("PUT", f"/master/work-locations/{wh['id']}", hr, {"attendance_location_policy": "outside_requires_approval"})
# Dalam Radius Wajib memblokir
pol2 = tk.evaluate_geofence({**wh2, "attendance_location_policy": "inside_required"},
                            {"default_radius_meter": 150, "gps_accuracy_max_meter": 150},
                            float(wh2["latitude"]) + 0.2, float(wh2["longitude"]), 10)
check(pol2["blocked"] is True, "inside_required: di luar radius diblokir")
pol3 = tk.evaluate_geofence({**wh2, "geofence_enabled": False}, {"default_radius_meter": 150}, None, None, None)
check(pol3["blocked"] is False and pol3["policy"] == "disabled", "geofence_enabled=false -> Tanpa Geofence")

print("== AUDIT LOG ==")
_, logs = call("GET", "/audit-logs?module=attendance&limit=50", hr)
acts = {l.get("action") for l in logs.get("items", [])}
check("check_in" in acts and "check_out" in acts, f"audit check_in/check_out tercatat ({sorted(acts)[:8]})")
check("check_in_outside_radius" in acts or "geofence_approved" in acts, "audit luar radius / persetujuan lokasi tercatat")

print(f"\nRINGKASAN: OK={ok} FAIL={fail}")
sys.exit(1 if fail else 0)
