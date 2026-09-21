"""Smoke test Rekrutmen Tahap C (konversi kandidat -> karyawan) pada DB DEVELOPMENT. Agent-run.
Membuat kandidat 'SMOKE-C *' + karyawan hasil konversi; dibersihkan via _cleanup_recruitment_test_data.py "SMOKE-C%".
Tidak mencetak kredensial.
"""
import os, sys, json, concurrent.futures as cf
import requests

sys.path.insert(0, "/app/backend")
from app.seed import DEMO_PASSWORD

B = "http://localhost:8001/api"; T = 120
results = []


def login(email):
    r = requests.post(f"{B}/auth/login", json={"email": email, "password": DEMO_PASSWORD}, timeout=T)
    r.raise_for_status(); return {"Authorization": f"Bearer {r.json()['access_token']}"}


def check(label, r, expect):
    ok = r.status_code in (expect if isinstance(expect, (list, tuple)) else [expect])
    results.append((ok, label, r.status_code))
    print(("PASS" if ok else "FAIL"), f"{label:<62} -> {r.status_code} {r.text[:130]}", flush=True)
    return r


def expect(cond, label, extra=None):
    results.append((bool(cond), label, extra)); print(("PASS" if cond else "FAIL"), label, "" if cond else extra, flush=True)


hr = login("hr.admin@nep.co.id"); hrm = login("hr.manager@nep.co.id"); own = login("owner@nep.co.id")
fin = login("finance@nep.co.id"); mgr = login("manager@nep.co.id"); kbs_own = login("owner@kbs.co.id")
print("logins ok", flush=True)
cat = requests.get(f"{B}/recruitment/catalog", headers=hr, timeout=T).json()
interviewers = {i["email"]: i["id"] for i in requests.get(f"{B}/recruitment/interviewers", headers=hr, timeout=T).json()["items"]}
iv_hr = interviewers["hr.manager@nep.co.id"]
emp_status = (cat.get("employment_statuses") or [{}])[0].get("id")


def stage(cid, h=hr):
    return requests.get(f"{B}/recruitment/candidates/{cid}", headers=h, timeout=T).json()["candidate"]


def to_accepted(name, **extra):
    """Kandidat baru -> screening passed -> interview -> approval (2 tahap) -> offering diterima."""
    c = requests.post(f"{B}/recruitment/candidates", json={"full_name": name, "position_id": cat["positions"][0]["id"],
                      "department_id": cat["departments"][0]["id"], **extra}, headers=hr, timeout=T).json()
    cid = c["id"]
    requests.post(f"{B}/recruitment/candidates/{cid}/status", json={"stage_status": "screening"}, headers=hr, timeout=T)
    requests.post(f"{B}/recruitment/candidates/{cid}/screening", json={"screening_result": "passed", "screening_score": 80}, headers=hr, timeout=T)
    iv = requests.post(f"{B}/recruitment/candidates/{cid}/interviews", json={"interview_type": "hr", "scheduled_date": "2026-10-01", "interviewer_user_id": iv_hr}, headers=hr, timeout=T).json()
    requests.post(f"{B}/recruitment/interviews/{iv['id']}/complete", json={"result": "passed", "score": 85}, headers=hr, timeout=T)
    a = requests.post(f"{B}/recruitment/candidates/{cid}/submit-approval", json={}, headers=hr, timeout=T).json()
    for st in a["rounds"][0]["steps"]:
        requests.post(f"{B}/recruitment/candidates/{cid}/approvals/{st['id']}/decide", json={"decision": "approved"},
                      headers=(hrm if st["step_order"] == 1 else own), timeout=T)
    o = requests.post(f"{B}/recruitment/candidates/{cid}/offering", json={"basic_salary": 7000000, "start_date": "2026-11-03", "employment_status_id": emp_status}, headers=hr, timeout=T).json()
    requests.post(f"{B}/recruitment/offerings/{o['id']}/send", headers=hr, timeout=T)
    requests.post(f"{B}/recruitment/offerings/{o['id']}/respond", json={"response": "accepted"}, headers=hr, timeout=T)
    return cid


# ------------------------------------------------------------------ FAILURE: status belum offering_accepted
c_draft = requests.post(f"{B}/recruitment/candidates", json={"full_name": "SMOKE-C Draft"}, headers=hr, timeout=T).json()["id"]
check("convert kandidat draft -> 422", requests.post(f"{B}/recruitment/candidates/{c_draft}/convert", json={}, headers=hr, timeout=T), 422)
p = check("preview kandidat draft -> 200 (can_convert=false)", requests.get(f"{B}/recruitment/candidates/{c_draft}/convert-preview", headers=hr, timeout=T), 200).json()
expect(p["can_convert"] is False and p["blockers"], "preview draft: blockers terisi", p["blockers"])
check("convert kandidat tidak ada -> 404", requests.post(f"{B}/recruitment/candidates/tidak-ada/convert", json={}, headers=hr, timeout=T), 404)

# ------------------------------------------------------------------ kandidat siap (offering_accepted) dengan NIK
c1 = to_accepted("SMOKE-C Kandidat Satu", nik="3175011201900001", gender="male", birth_date="1990-01-12", phone="0811111111", email="smokec1@example.com")
expect(stage(c1)["stage_status"] == "offering_accepted", "c1 offering_accepted", stage(c1)["stage_status"])
expect(stage(c1)["can_convert"] is True, "c1 can_convert flag true")

# offering belum accepted (kandidat approved dengan offering sent) -> 422
c_sent = to_accepted("SMOKE-C Offering Terkirim")  # dulu jadi accepted; buat variasi: batalkan? tidak bisa. gunakan jalur approved+sent:
# jalur khusus: kandidat approved dengan offering sent
c2 = requests.post(f"{B}/recruitment/candidates", json={"full_name": "SMOKE-C Offering Sent", "position_id": cat["positions"][0]["id"]}, headers=hr, timeout=T).json()["id"]
requests.post(f"{B}/recruitment/candidates/{c2}/status", json={"stage_status": "screening"}, headers=hr, timeout=T)
requests.post(f"{B}/recruitment/candidates/{c2}/screening", json={"screening_result": "passed"}, headers=hr, timeout=T)
iv = requests.post(f"{B}/recruitment/candidates/{c2}/interviews", json={"interview_type": "hr", "scheduled_date": "2026-10-01", "interviewer_user_id": iv_hr}, headers=hr, timeout=T).json()
requests.post(f"{B}/recruitment/interviews/{iv['id']}/complete", json={"result": "passed"}, headers=hr, timeout=T)
a = requests.post(f"{B}/recruitment/candidates/{c2}/submit-approval", json={}, headers=hr, timeout=T).json()
for st in a["rounds"][0]["steps"]:
    requests.post(f"{B}/recruitment/candidates/{c2}/approvals/{st['id']}/decide", json={"decision": "approved"}, headers=(hrm if st["step_order"] == 1 else own), timeout=T)
o2 = requests.post(f"{B}/recruitment/candidates/{c2}/offering", json={"basic_salary": 7000000, "start_date": "2026-11-03"}, headers=hr, timeout=T).json()
requests.post(f"{B}/recruitment/offerings/{o2['id']}/send", headers=hr, timeout=T)
check("convert saat offering masih 'sent' -> 422", requests.post(f"{B}/recruitment/candidates/{c2}/convert", json={}, headers=hr, timeout=T), 422)

# ------------------------------------------------------------------ PERMISSION
check("convert oleh finance (tanpa recruitment:edit) -> 403", requests.post(f"{B}/recruitment/candidates/{c1}/convert", json={}, headers=fin, timeout=T), 403)
check("convert oleh manager (tanpa recruitment & employee) -> 403", requests.post(f"{B}/recruitment/candidates/{c1}/convert", json={}, headers=mgr, timeout=T), 403)
# hr_manager punya recruitment:edit + employee:create -> boleh; hr_admin juga (full crud employee). Uji employee:create kurang:
# buat pengguna? tidak mengubah akun demo. Uji lewat role matrix: cek preview blockers untuk user tanpa employee:create tidak tersedia pada akun demo NEP.
print("  (catatan) semua akun demo NEP dengan recruitment:edit juga punya employee:create; uji negatif employee:create dilakukan lewat unit fungsi _authz_blockers", flush=True)

# ------------------------------------------------------------------ TENANT
check("owner KBS convert kandidat NEP -> 404", requests.post(f"{B}/recruitment/candidates/{c1}/convert", json={}, headers=kbs_own, timeout=T), 404)
check("owner KBS preview kandidat NEP -> 404", requests.get(f"{B}/recruitment/candidates/{c1}/convert-preview", headers=kbs_own, timeout=T), 404)

# ------------------------------------------------------------------ NIK DUPLICATE
emp_dup = requests.post(f"{B}/employees", json={"full_name": "SMOKE-C Karyawan NIK Sama", "nik": "3175011201900001"}, headers=hr, timeout=T)
check("buat karyawan pembanding dengan NIK sama (API Data Karyawan existing)", emp_dup, 201)
emp_dup_id = emp_dup.json()["id"]
r = check("convert c1 dengan NIK duplikat -> 409", requests.post(f"{B}/recruitment/candidates/{c1}/convert", json={}, headers=hr, timeout=T), 409)
d = r.json().get("detail")
expect(isinstance(d, dict) and d.get("existing_employee", {}).get("id") == emp_dup_id, "409 memuat existing_employee (user punya employee:view)", d)
expect(stage(c1)["stage_status"] == "offering_accepted" and not stage(c1).get("employee_id"), "c1 tetap offering_accepted setelah 409 NIK", stage(c1)["stage_status"])
p = requests.get(f"{B}/recruitment/candidates/{c1}/convert-preview", headers=hr, timeout=T).json()
expect(p["nik_conflict"] and p["can_convert"] is False, "preview menandai nik_conflict", p.get("nik_conflict"))
# hapus karyawan pembanding (soft delete) agar konversi bisa lanjut
check("hapus karyawan pembanding", requests.delete(f"{B}/employees/{emp_dup_id}", headers=hr, timeout=T), 200)

# ------------------------------------------------------------------ PAYLOAD company_id palsu + field wajib
p = requests.get(f"{B}/recruitment/candidates/{c1}/convert-preview", headers=hr, timeout=T).json()
expect(p["can_convert"] is True and not p["required_missing"], "preview c1 siap (tanpa field wajib kurang)", (p["blockers"], p["required_missing"]))
print("  mapping job:", [(m["label"], m["value"], m["source"]) for m in p["mapping"]["job"]], flush=True)

# ------------------------------------------------------------------ DOUBLE CONVERSION (konkuren)
with cf.ThreadPoolExecutor(3) as ex:
    futs = [ex.submit(requests.post, f"{B}/recruitment/candidates/{c1}/convert", json={"company_id": "HACK-KBS", "notes": "dari smoke"}, headers=hr, timeout=T) for _ in range(3)]
    rs = [f.result() for f in futs]
codes = sorted(r.status_code for r in rs)
expect(codes == [201, 409, 409], "3 convert konkuren -> [201, 409, 409]", codes)
ok = next(r for r in rs if r.status_code == 201).json()
emp_id = ok["employee"]["id"]; emp_no = ok["employee"]["employee_number"]
print("  employee:", emp_no, emp_id, "| route:", ok["employee_route"], flush=True)
check("retry convert setelah sukses -> 409", requests.post(f"{B}/recruitment/candidates/{c1}/convert", json={}, headers=hr, timeout=T), 409)
c = stage(c1)
expect(c["stage_status"] == "hired" and c["employee_id"] == emp_id and c.get("converted_at") and c.get("converted_by"), "kandidat hired + employee_id/converted_at/converted_by", (c["stage_status"], c.get("employee_id")))
emps = requests.get(f"{B}/employees", params={"q": "SMOKE-C Kandidat Satu", "limit": 50}, headers=hr, timeout=T).json()
items = [e for e in emps.get("items", []) if e.get("candidate_id") == c1]
expect(len(items) == 1, "hanya SATU karyawan untuk kandidat ini", len(items))
emp = requests.get(f"{B}/employees/{emp_id}", headers=hr, timeout=T).json()
emp = emp.get("employee", emp)
expect(emp.get("candidate_id") == c1 and emp.get("company_id") == c["company_id"], "employee.candidate_id menunjuk kandidat & tenant sama", (emp.get("candidate_id"), emp.get("company_id")))
expect(emp.get("join_date") == "2026-11-03" and emp.get("position_id") == cat["positions"][0]["id"] and emp.get("nik") == "3175011201900001", "employee join_date/position/nik dari offering & kandidat", (emp.get("join_date"), emp.get("nik")))
expect(emp.get("employment_status_id") == emp_status, "employment_status dari offering", emp.get("employment_status_id"))
sal = requests.get(f"{B}/payroll/salaries/{emp_id}", headers=hr, timeout=T)
print("  cek salary endpoint:", sal.status_code, sal.text[:160], flush=True)
sj = sal.json() if sal.status_code == 200 else {}
expect(sal.status_code == 200 and not sj.get("salary") and not sj.get("history"), "tidak ada employee_salaries otomatis (salary kosong)", sal.text[:120])

# ------------------------------------------------------------------ READ-ONLY setelah hired
check("PUT kandidat hired -> 409", requests.put(f"{B}/recruitment/candidates/{c1}", json={"full_name": "Ubah"}, headers=hr, timeout=T), 409)
check("DELETE kandidat hired -> 4xx", requests.delete(f"{B}/recruitment/candidates/{c1}", headers=hr, timeout=T), [409, 422])
check("status manual hired -> 4xx", requests.post(f"{B}/recruitment/candidates/{c1}/status", json={"stage_status": "screening"}, headers=hr, timeout=T), [409, 422])
check("interview pada hired -> 422", requests.post(f"{B}/recruitment/candidates/{c1}/interviews", json={"interview_type": "hr", "scheduled_date": "2026-12-01", "interviewer_user_id": iv_hr}, headers=hr, timeout=T), 422)
check("submit approval pada hired -> 422", requests.post(f"{B}/recruitment/candidates/{c1}/submit-approval", json={}, headers=hr, timeout=T), 422)
check("offering baru pada hired -> 4xx", requests.post(f"{B}/recruitment/candidates/{c1}/offering", json={}, headers=hr, timeout=T), [409, 422])
doc_types = requests.get(f"{B}/documents/catalog", headers=hr, timeout=T).json().get("document_types") or []
if doc_types:
    files = {"file": ("cv.txt", b"smoke", "text/plain")}
    data = {"document_type_id": doc_types[0]["id"], "name": "SMOKE-C CV", "owner_type": "applicant", "owner_id": c1}
    check("upload dokumen kandidat hired -> 409/422", requests.post(f"{B}/documents", files=files, data=data, headers=hr, timeout=T), [409, 422])

# ------------------------------------------------------------------ HISTORY & AUDIT
hist = requests.get(f"{B}/recruitment/candidates/{c1}", headers=hr, timeout=T).json()["history"]
h0 = hist[0]
expect(h0["action"] == "candidate_converted" and h0["from_status"] == "offering_accepted" and h0["to_status"] == "hired" and h0.get("changed_by_name"), "history offering_accepted -> hired (Jadikan Karyawan)", (h0["action"], h0["from_status"], h0["to_status"]))
logs = requests.get(f"{B}/audit-logs", params={"limit": 50}, headers=hr, timeout=T).json().get("items", [])
acts = {l.get("action") for l in logs}
expect("candidate_converted_to_employee" in acts and "employee_created_from_recruitment" in acts, "audit log 2 aksi konversi", sorted(a for a in acts if "convert" in a or "recruitment" in a))

# pipeline conversion state
pl = requests.get(f"{B}/recruitment/candidates/{c1}/pipeline", headers=hr, timeout=T).json()
expect(pl["conversion"]["is_hired"] and pl["conversion"]["employee"]["employee_number"] == emp_no and pl["conversion"]["converted_by_name"], "pipeline.conversion lengkap", pl["conversion"])
check("owner KBS GET employee hasil konversi NEP -> 404", requests.get(f"{B}/employees/{emp_id}", headers=kbs_own, timeout=T), 404)

# ------------------------------------------------------------------ FIELD WAJIB KURANG (start_date tidak mungkin kosong pada offering sent; uji lewat override format)
check("override join_date format salah -> 422", requests.post(f"{B}/recruitment/candidates/{c_sent}/convert", json={"join_date": "03-11-2026"}, headers=hr, timeout=T), 422)
check("override gender tidak valid -> 422", requests.post(f"{B}/recruitment/candidates/{c_sent}/convert", json={"gender": "x"}, headers=hr, timeout=T), 422)
check("override employment_status_id tidak ada -> 422", requests.post(f"{B}/recruitment/candidates/{c_sent}/convert", json={"employment_status_id": "bukan-id"}, headers=hr, timeout=T), 422)
expect(stage(c_sent)["stage_status"] == "offering_accepted", "c_sent tetap offering_accepted setelah 422", stage(c_sent)["stage_status"])
# konversi c_sent dengan pelengkap NIK (kandidat tanpa NIK)
r = check("convert c_sent dengan pelengkap nik -> 201", requests.post(f"{B}/recruitment/candidates/{c_sent}/convert", json={"nik": "3175019999990002", "gender": "female"}, headers=hr, timeout=T), 201)
e2 = requests.get(f"{B}/employees/{r.json()['employee']['id']}", headers=hr, timeout=T).json()
e2 = e2.get("employee", e2)
expect(e2.get("nik") == "3175019999990002" and e2.get("gender") == "female", "pelengkap nik/gender tersimpan di employee", (e2.get("nik"), e2.get("gender")))

# cleanup kandidat draft
requests.delete(f"{B}/recruitment/candidates/{c_draft}", headers=hr, timeout=T)
print("\nRESULT", sum(1 for r in results if r[0]), "/", len(results))
for ok_, label, extra in results:
    if not ok_: print("  FAILED:", label, extra)
