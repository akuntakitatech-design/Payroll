"""Data preview Rekrutmen Tahap B pada DB DEVELOPMENT (NEP). Agent-run, tidak mencetak kredensial.
Skenario:
  Bagus Prakoso      : reset snapshot lama -> approval 2 tahap disetujui -> offering dikirim -> diterima
  Andini Putri Lestari: 2 interview (HR selesai, User terjadwal) -> interview_scheduled
  Dimas Aryo Wibowo  : screening -> interview -> approval tahap 1 disetujui -> menunggu Direksi
  Raka Pratama Nugroho (baru): approval ditolak Direksi -> rejected
  Maya Salsabila (baru): approved -> offering v1 ditolak kandidat -> offering v2 draft
"""
import os, sys, requests
from urllib.parse import urlparse
import pymysql
from dotenv import load_dotenv

sys.path.insert(0, "/app/backend")
from app.seed import DEMO_PASSWORD

load_dotenv("/app/backend/.env", override=True)
assert os.environ.get("APP_ENV") == "development"
B = "http://localhost:8001/api"; T = 120


def login(email):
    r = requests.post(f"{B}/auth/login", json={"email": email, "password": DEMO_PASSWORD}, timeout=T)
    r.raise_for_status(); return {"Authorization": f"Bearer {r.json()['access_token']}"}


def call(method, path, h, ok=(200, 201), **kw):
    r = requests.request(method, f"{B}{path}", headers=h, timeout=T, **kw)
    if r.status_code not in ok:
        print("  !!", method, path, r.status_code, r.text[:160], flush=True)
    return r.json() if r.content else {}


hr = login("hr.admin@nep.co.id"); hrm = login("hr.manager@nep.co.id"); own = login("owner@nep.co.id")
print("login ok", flush=True)
cat = call("GET", "/recruitment/catalog", hr)
interviewers = {i["email"]: i["id"] for i in call("GET", "/recruitment/interviewers", hr)["items"]}
iv_hr, iv_mgr, iv_own = interviewers["hr.manager@nep.co.id"], interviewers["manager@nep.co.id"], interviewers["owner@nep.co.id"]
cands = {c["full_name"]: c for c in call("GET", "/recruitment/candidates", hr, params={"limit": 100})["items"]}
pos = {p["name"]: p["id"] for p in cat["positions"]}
dept = {d["name"]: d["id"] for d in cat["departments"]}
emp_status = (cat.get("employment_statuses") or [{}])[0].get("id")


def stage(cid):
    return call("GET", f"/recruitment/candidates/{cid}", hr)["candidate"]["stage_status"]


def ensure_candidate(name, **extra):
    if name in cands:
        return cands[name]["id"]
    c = call("POST", "/recruitment/candidates", hr, json={"full_name": name, **extra})
    cands[name] = c
    return c["id"]


def to_screening_passed(cid, score=82, notes="Kualifikasi sesuai, pengalaman relevan."):
    st = stage(cid)
    if st == "draft":
        call("POST", f"/recruitment/candidates/{cid}/status", hr, json={"stage_status": "screening", "notes": "Screening dimulai oleh HR"}); st = "screening"
    if st == "screening":
        call("POST", f"/recruitment/candidates/{cid}/screening", hr, json={"screening_result": "passed", "screening_score": score, "screening_recommendation": "recommended", "screening_notes": notes}, ok=(200, 201, 422))


def interview(cid, itype, date, who, mode="onsite", start="09:00", end="10:00", **extra):
    body = {"interview_type": itype, "scheduled_date": date, "start_time": start, "end_time": end, "interviewer_user_id": who, "interview_mode": mode}
    body.update({"location": "Kantor Pusat NEP, Ruang Rapat 2"} if mode == "onsite" else {"meeting_link": "https://meet.google.com/nep-interview"})
    body.update(extra)
    return call("POST", f"/recruitment/candidates/{cid}/interviews", hr, json=body)


def complete(iid, result="passed", score=85, rec="hire", notes="Komunikasi baik, jawaban teknis tepat."):
    return call("POST", f"/recruitment/interviews/{iid}/complete", hr, json={"result": result, "score": score, "recommendation": rec, "interviewer_notes": notes})


def submit(cid, notes="Mohon persetujuan untuk melanjutkan ke offering."):
    a = call("POST", f"/recruitment/candidates/{cid}/submit-approval", hr, json={"notes": notes})
    return a["rounds"][-1]["steps"]


def decide(cid, step, decision, h, notes):
    return call("POST", f"/recruitment/candidates/{cid}/approvals/{step['id']}/decide", h, json={"decision": decision, "notes": notes})


# --- 0) Reset snapshot lama Bagus Prakoso (3 tahap, memuat role tanpa izin approve) -> interview_done
bagus = cands["Bagus Prakoso"]["id"]
if stage(bagus) == "awaiting_approval":
    u = urlparse(os.environ["DATABASE_URL"])
    conn = pymysql.connect(host=u.hostname, port=u.port, user=u.username, password=u.password, database=u.path.lstrip("/"), autocommit=True)
    cur = conn.cursor()
    cur.execute("DELETE FROM candidate_approvals WHERE candidate_id=%s", (bagus,))
    cur.execute("DELETE FROM candidate_status_history WHERE candidate_id=%s AND action='approval_submit'", (bagus,))
    cur.execute("UPDATE candidates SET stage_status='interview_done', approval_round=0 WHERE id=%s", (bagus,))
    conn.close()
    print("Bagus direset ke interview_done", flush=True)

# --- 1) Bagus Prakoso: happy path sampai offering diterima
if stage(bagus) == "interview_done":
    steps = submit(bagus)
    decide(bagus, steps[0], "approved", hrm, "Hasil interview konsisten, lanjut ke Direksi.")
    decide(bagus, steps[1], "approved", own, "Disetujui. Siapkan offering sesuai budget.")
if stage(bagus) == "approved":
    o = call("POST", f"/recruitment/candidates/{bagus}/offering", hr, json={
        "basic_salary": 8500000, "start_date": "2026-11-02", "probation_months": 3, "employment_status_id": emp_status,
        "allowances": [{"name": "Tunjangan Transport", "amount": 600000}, {"name": "Tunjangan Makan", "amount": 500000}],
        "notes": "BPJS Kesehatan & Ketenagakerjaan sesuai ketentuan. Evaluasi setelah masa percobaan."})
    call("POST", f"/recruitment/offerings/{o['id']}/send", hr)
    call("POST", f"/recruitment/offerings/{o['id']}/respond", hr, json={"response": "accepted", "responded_at": "2026-09-25", "response_notes": "Kandidat menandatangani offering letter."})
print("Bagus:", stage(bagus), flush=True)

# --- 2) Andini: dua interview, satu selesai satu terjadwal
andini = cands["Andini Putri Lestari"]["id"]
if stage(andini) == "screening_passed":
    i1 = interview(andini, "hr", "2026-09-23", iv_hr, "onsite", "10:00", "11:00", notes="Bawa dokumen asli.")
    complete(i1["id"], "passed", 88, "hire", "Motivasi tinggi, ekspektasi gaji sesuai range.")
    interview(andini, "user", "2026-09-30", iv_mgr, "online", "13:00", "14:00")
print("Andini:", stage(andini), flush=True)

# --- 3) Dimas: menunggu approval Direksi (tahap 1 sudah disetujui)
dimas = cands["Dimas Aryo Wibowo"]["id"]
to_screening_passed(dimas, 78, "Pengalaman lapangan 5 tahun, sertifikasi K3 aktif.")
if stage(dimas) == "screening_passed":
    i = interview(dimas, "user", "2026-09-24", iv_mgr, "onsite", "14:00", "15:00")
    complete(i["id"], "passed", 80, "hire", "Paham prosedur keselamatan kerja di site.")
if stage(dimas) == "interview_done":
    steps = submit(dimas, "Kebutuhan site supervisor proyek baru, mohon dipercepat.")
    decide(dimas, steps[0], "approved", hrm, "Verifikasi dokumen lengkap.")
print("Dimas:", stage(dimas), flush=True)

# --- 4) Raka: ditolak Direksi
raka = ensure_candidate("Raka Pratama Nugroho", position_id=pos.get("Payroll Officer") or cat["positions"][0]["id"],
                        department_id=dept.get("Human Resources") or cat["departments"][0]["id"], source="job_portal",
                        email="raka.pratama@example.com", phone="081234567801", applied_at="2026-09-12", expected_salary=7500000,
                        last_education="s1", major="Akuntansi", institution="Universitas Brawijaya", experience_years=3)
to_screening_passed(raka, 75, "Pengalaman payroll 3 tahun, perlu konfirmasi kemampuan PPh 21.")
if stage(raka) == "screening_passed":
    i = interview(raka, "hr", "2026-09-22", iv_hr, "online", "09:00", "10:00")
    complete(i["id"], "considered", 68, "consider", "Pemahaman PPh 21 masih dasar.")
if stage(raka) == "interview_done":
    steps = submit(raka, "Kandidat cukup, mohon pertimbangan.")
    decide(raka, steps[0], "approved", hrm, "Layak dipertimbangkan dengan catatan.")
    decide(raka, steps[1], "rejected", own, "Kompetensi PPh 21 belum memenuhi kebutuhan tim payroll.")
print("Raka:", stage(raka), flush=True)

# --- 5) Maya: offering v1 ditolak kandidat -> v2 draft
maya = ensure_candidate("Maya Salsabila", position_id=pos.get("HR Staff") or cat["positions"][0]["id"],
                        department_id=dept.get("Human Resources") or cat["departments"][0]["id"], source="referral",
                        email="maya.salsabila@example.com", phone="081234567802", applied_at="2026-09-08", expected_salary=6500000,
                        last_education="s1", major="Psikologi", institution="Universitas Indonesia", experience_years=2)
to_screening_passed(maya, 86, "Referensi internal, pengalaman rekrutmen 2 tahun.")
if stage(maya) == "screening_passed":
    i = interview(maya, "hr", "2026-09-19", iv_hr, "onsite", "09:00", "10:00")
    complete(i["id"], "passed", 90, "hire", "Sangat komunikatif.")
    i2 = interview(maya, "final", "2026-09-20", iv_own, "onsite", "15:00", "15:45")
    complete(i2["id"], "passed", 84, "hire", "Cocok dengan budaya perusahaan.")
if stage(maya) == "interview_done":
    steps = submit(maya)
    decide(maya, steps[0], "approved", hrm, "Lanjut.")
    decide(maya, steps[1], "approved", own, "Setuju.")
if stage(maya) == "approved":
    o = call("POST", f"/recruitment/candidates/{maya}/offering", hr, json={"basic_salary": 5800000, "start_date": "2026-10-15", "probation_months": 3, "employment_status_id": emp_status})
    call("POST", f"/recruitment/offerings/{o['id']}/send", hr)
    call("POST", f"/recruitment/offerings/{o['id']}/respond", hr, json={"response": "declined", "responded_at": "2026-09-21", "response_notes": "Gaji pokok di bawah ekspektasi (Rp 6,5 juta)."})
if stage(maya) == "offering_declined":
    call("POST", f"/recruitment/candidates/{maya}/offering", hr, json={"basic_salary": 6300000, "start_date": "2026-10-20", "probation_months": 3, "employment_status_id": emp_status,
                                                                       "allowances": [{"name": "Tunjangan Transport", "amount": 400000}], "notes": "Revisi paket setelah negosiasi."})
print("Maya:", stage(maya), flush=True)
print("SELESAI", flush=True)
