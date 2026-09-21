"""Smoke test Rekrutmen Tahap B pada DB DEVELOPMENT (agent-run). Tidak mencetak kredensial.
Membuat kandidat berprefix 'SMOKE-B' lalu menghapus yang bisa dihapus; sisanya dibersihkan via SQL oleh agent.
"""
import os, sys, json, time, concurrent.futures as cf
import requests

sys.path.insert(0, "/app/backend")
from app.seed import DEMO_PASSWORD

B = "http://localhost:8001/api"
T = 90
results = []


def login(email):
    r = requests.post(f"{B}/auth/login", json={"email": email, "password": DEMO_PASSWORD}, timeout=T)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def check(label, r, expect):
    ok = r.status_code in (expect if isinstance(expect, (list, tuple)) else [expect])
    results.append((ok, label, r.status_code))
    print(("PASS" if ok else "FAIL"), f"{label:<60} -> {r.status_code} {r.text[:120]}", flush=True)
    return r


hr = login("hr.admin@nep.co.id")
hrm = login("hr.manager@nep.co.id")
mgr = login("manager@nep.co.id")
own = login("owner@nep.co.id")
fin = login("finance@nep.co.id")
kbs = login("hr.admin@kbs.co.id")
kbs_own = login("owner@kbs.co.id")
print("logins ok", flush=True)

cat = requests.get(f"{B}/recruitment/catalog", headers=hr, timeout=T).json()
interviewers = requests.get(f"{B}/recruitment/interviewers", headers=hr, timeout=T).json()["items"]
print("interviewers:", [(i["email"], i["job_title"]) for i in interviewers][:6], flush=True)
iv_hr = next(i["id"] for i in interviewers if i["email"] == "hr.manager@nep.co.id")
iv_mgr = next(i["id"] for i in interviewers if i["email"] == "manager@nep.co.id")


def new_candidate(name):
    c = requests.post(f"{B}/recruitment/candidates", json={"full_name": name, "position_id": cat["positions"][0]["id"],
                      "department_id": cat["departments"][0]["id"]}, headers=hr, timeout=T).json()
    requests.post(f"{B}/recruitment/candidates/{c['id']}/status", json={"stage_status": "screening"}, headers=hr, timeout=T)
    requests.post(f"{B}/recruitment/candidates/{c['id']}/screening", json={"screening_result": "passed", "screening_score": 80}, headers=hr, timeout=T)
    return c["id"]


def stage(cid, h=hr):
    return requests.get(f"{B}/recruitment/candidates/{cid}", headers=h, timeout=T).json()["candidate"]["stage_status"]


# ------------------------------------------------------------------ INTERVIEW
c1 = new_candidate("SMOKE-B Kandidat Satu")
print("c1 stage:", stage(c1), flush=True)
check("interview sebelum screening_passed ditolak (draft kandidat lain)",
      requests.post(f"{B}/recruitment/candidates/{requests.post(f'{B}/recruitment/candidates', json={'full_name': 'SMOKE-B Draft'}, headers=hr, timeout=T).json()['id']}/interviews",
                    json={"interview_type": "hr", "scheduled_date": "2026-10-01", "interviewer_user_id": iv_hr}, headers=hr, timeout=T), 422)
check("schedule tanggal salah format", requests.post(f"{B}/recruitment/candidates/{c1}/interviews",
      json={"interview_type": "hr", "scheduled_date": "01-10-2026", "interviewer_user_id": iv_hr}, headers=hr, timeout=T), 422)
check("schedule interviewer bukan user perusahaan", requests.post(f"{B}/recruitment/candidates/{c1}/interviews",
      json={"interview_type": "hr", "scheduled_date": "2026-10-01", "interviewer_user_id": "bukan-id"}, headers=hr, timeout=T), 422)
i1 = check("schedule interview HR", requests.post(f"{B}/recruitment/candidates/{c1}/interviews",
      json={"interview_type": "hr", "scheduled_date": "2026-10-01", "start_time": "09:00", "end_time": "10:00",
            "interviewer_user_id": iv_hr, "interview_mode": "onsite", "location": "Kantor Pusat", "company_id": "HACK"}, headers=hr, timeout=T), 201).json()
print("  stage setelah interview 1:", stage(c1), "| interviewer:", i1["interviewer_name"], i1.get("interviewer_title"), flush=True)
i2 = check("schedule interview User (kedua)", requests.post(f"{B}/recruitment/candidates/{c1}/interviews",
      json={"interview_type": "user", "scheduled_date": "2026-10-03", "interviewer_user_id": iv_mgr, "interview_mode": "online",
            "meeting_link": "https://meet.example.com/abc"}, headers=hr, timeout=T), 201).json()
check("reschedule interview 1", requests.put(f"{B}/recruitment/interviews/{i1['id']}", json={"scheduled_date": "2026-10-02"}, headers=hr, timeout=T), 200)
check("complete interview hasil invalid", requests.post(f"{B}/recruitment/interviews/{i1['id']}/complete", json={"result": "maybe"}, headers=hr, timeout=T), 422)
check("complete interview skor 150", requests.post(f"{B}/recruitment/interviews/{i1['id']}/complete", json={"result": "passed", "score": 150}, headers=hr, timeout=T), 422)
check("complete interview 1", requests.post(f"{B}/recruitment/interviews/{i1['id']}/complete",
      json={"result": "passed", "score": 85, "recommendation": "hire", "interviewer_notes": "Baik"}, headers=hr, timeout=T), 200)
st = stage(c1); results.append((st == "interview_scheduled", "stage tetap interview_scheduled (masih ada interview 2)", st)); print("  stage:", st, flush=True)
check("double complete interview 1 -> 409", requests.post(f"{B}/recruitment/interviews/{i1['id']}/complete", json={"result": "passed"}, headers=hr, timeout=T), 409)
check("edit interview completed -> 409", requests.put(f"{B}/recruitment/interviews/{i1['id']}", json={"scheduled_date": "2026-10-05"}, headers=hr, timeout=T), 409)
check("cancel/delete interview completed -> 409", requests.delete(f"{B}/recruitment/interviews/{i1['id']}", headers=hr, timeout=T), 409)
check("submit approval saat masih ada interview scheduled -> 422", requests.post(f"{B}/recruitment/candidates/{c1}/submit-approval", json={}, headers=hr, timeout=T), 422)
check("complete interview 2", requests.post(f"{B}/recruitment/interviews/{i2['id']}/complete", json={"result": "considered", "score": 70}, headers=hr, timeout=T), 200)
st = stage(c1); results.append((st == "interview_done", "stage interview_done setelah semua selesai", st)); print("  stage:", st, flush=True)
i3 = requests.post(f"{B}/recruitment/candidates/{c1}/interviews", json={"interview_type": "final", "scheduled_date": "2026-10-05", "interviewer_user_id": iv_mgr}, headers=hr, timeout=T).json()
st = stage(c1); results.append((st == "interview_scheduled", "interview baru -> kembali interview_scheduled", st))
check("cancel interview 3", requests.post(f"{B}/recruitment/interviews/{i3['id']}/cancel", json={"reason": "Tidak diperlukan"}, headers=hr, timeout=T), 200)
st = stage(c1); results.append((st == "interview_done", "cancel -> kembali interview_done", st)); print("  stage:", st, flush=True)
check("double cancel -> 409", requests.post(f"{B}/recruitment/interviews/{i3['id']}/cancel", json={}, headers=hr, timeout=T), 409)

# ------------------------------------------------------------------ APPROVAL
wfs = requests.get(f"{B}/approval-workflows", headers=own, timeout=T).json()
wfs = wfs["items"] if isinstance(wfs, dict) else wfs
wf = next((w for w in wfs if w.get("document_kind") == "recruitment"), None)
wf_payload = {"code": "WF-REKRUT", "name": "Persetujuan Rekrutmen", "document_kind": "recruitment", "scope_type": "company", "is_default": True,
    "description": "HR Manager -> Direksi",
    "steps": [
        {"step_order": 1, "name": "Verifikasi HR Manager", "approver_type": "role", "approver_role_key": "hr_manager"},
        {"step_order": 2, "name": "Persetujuan Direksi", "approver_type": "role", "approver_role_key": "company_owner"},
    ]}
if wf:
    wf = check("update workflow rekrutmen 2 tahap (API existing, owner)", requests.put(f"{B}/approval-workflows/{wf['id']}", json=wf_payload, headers=own, timeout=T), 200).json()
else:
    wf = check("buat workflow rekrutmen (API existing, owner)", requests.post(f"{B}/approval-workflows", json=wf_payload, headers=own, timeout=T), [200, 201]).json()
# fail-closed: nonaktifkan sementara
check("nonaktifkan workflow", requests.patch(f"{B}/approval-workflows/{wf['id']}/status", json={"status": "inactive"}, headers=own, timeout=T), 200)
a = check("GET approvals (workflow nonaktif)", requests.get(f"{B}/recruitment/candidates/{c1}/approvals", headers=hr, timeout=T), 200).json()
results.append((a["workflow_available"] is False and not a["can_submit"], "workflow_available=false & can_submit=false", a["submit_blockers"]))
check("submit approval tanpa workflow -> 422 fail-closed", requests.post(f"{B}/recruitment/candidates/{c1}/submit-approval", json={}, headers=hr, timeout=T), 422)
results.append((stage(c1) == "interview_done", "stage tidak berubah setelah submit gagal", stage(c1)))
check("aktifkan workflow", requests.patch(f"{B}/approval-workflows/{wf['id']}/status", json={"status": "active"}, headers=own, timeout=T), 200)

check("submit approval oleh KBS terhadap kandidat NEP -> 404", requests.post(f"{B}/recruitment/candidates/{c1}/submit-approval", json={}, headers=kbs, timeout=T), 404)
a = check("submit approval (2 tahap)", requests.post(f"{B}/recruitment/candidates/{c1}/submit-approval", json={"notes": "Mohon persetujuan"}, headers=hr, timeout=T), 200).json()
steps = a["rounds"][0]["steps"]; print("  steps:", [(s["step_order"], s["step_name"], s["approver_label"], s["decision"]) for s in steps], flush=True)
results.append((stage(c1) == "awaiting_approval", "stage awaiting_approval", stage(c1)))
check("submit ganda -> 422/409", requests.post(f"{B}/recruitment/candidates/{c1}/submit-approval", json={}, headers=hr, timeout=T), [409, 422])
s1, s2 = steps[0]["id"], steps[1]["id"]
check("step2 sebelum step1 (owner) -> 422 urutan", requests.post(f"{B}/recruitment/candidates/{c1}/approvals/{s2}/decide", json={"decision": "approved"}, headers=own, timeout=T), 422)
check("step1 oleh finance (tanpa recruitment:approve) -> 403", requests.post(f"{B}/recruitment/candidates/{c1}/approvals/{s1}/decide", json={"decision": "approved"}, headers=fin, timeout=T), 403)
check("step1 oleh hr_admin (bukan hr_manager) -> 403", requests.post(f"{B}/recruitment/candidates/{c1}/approvals/{s1}/decide", json={"decision": "approved"}, headers=hr, timeout=T), 403)
check("step1 oleh owner NEP (punya approve, bukan approver step1) -> 403", requests.post(f"{B}/recruitment/candidates/{c1}/approvals/{s1}/decide", json={"decision": "approved"}, headers=own, timeout=T), 403)
check("step1 oleh owner KBS -> 404 (lintas tenant)", requests.post(f"{B}/recruitment/candidates/{c1}/approvals/{s1}/decide", json={"decision": "approved"}, headers=kbs_own, timeout=T), 404)
check("step1 oleh hr_manager -> 200", requests.post(f"{B}/recruitment/candidates/{c1}/approvals/{s1}/decide", json={"decision": "approved", "notes": "OK"}, headers=hrm, timeout=T), 200)
check("step1 double approve -> 409", requests.post(f"{B}/recruitment/candidates/{c1}/approvals/{s1}/decide", json={"decision": "approved"}, headers=hrm, timeout=T), 409)
results.append((stage(c1) == "awaiting_approval", "stage masih awaiting_approval setelah step1", stage(c1)))
# concurrency: dua request approve step2 bersamaan oleh owner
with cf.ThreadPoolExecutor(2) as ex:
    futs = [ex.submit(requests.post, f"{B}/recruitment/candidates/{c1}/approvals/{s2}/decide", json={"decision": "approved"}, headers=own, timeout=T) for _ in range(2)]
    codes = sorted(f.result().status_code for f in futs)
results.append((codes == [200, 409], "concurrent double approve step2 -> [200,409]", codes)); print("  concurrent codes:", codes, flush=True)
results.append((stage(c1) == "approved", "stage approved", stage(c1))); print("  stage:", stage(c1), flush=True)

# ------------------------------------------------------------------ OFFERING
c_draft = requests.post(f"{B}/recruitment/candidates", json={"full_name": "SMOKE-B Belum Approved"}, headers=hr, timeout=T).json()["id"]
check("offering sebelum approved -> 422", requests.post(f"{B}/recruitment/candidates/{c_draft}/offering", json={}, headers=hr, timeout=T), 422)
o1 = check("buat offering draft (default dari kandidat)", requests.post(f"{B}/recruitment/candidates/{c1}/offering",
      json={"basic_salary": 9000000, "allowances": [{"name": "Transport", "amount": 500000}], "probation_months": 3,
            "employment_status_id": (cat.get("employment_statuses") or [{}])[0].get("id")}, headers=hr, timeout=T), 201).json()
print("  offering v", o1["version"], o1["offer_status"], o1.get("position_name"), o1.get("total_allowances"), flush=True)
check("offering kedua saat aktif -> 409", requests.post(f"{B}/recruitment/candidates/{c1}/offering", json={}, headers=hr, timeout=T), 409)
check("send tanpa start_date -> 422", requests.post(f"{B}/recruitment/offerings/{o1['id']}/send", headers=hr, timeout=T), 422)
check("edit offering draft", requests.put(f"{B}/recruitment/offerings/{o1['id']}", json={"start_date": "2026-11-01", "basic_salary": 9500000}, headers=hr, timeout=T), 200)
check("respond sebelum sent -> 409", requests.post(f"{B}/recruitment/offerings/{o1['id']}/respond", json={"response": "accepted"}, headers=hr, timeout=T), 409)
check("KBS edit offering NEP -> 404", requests.put(f"{B}/recruitment/offerings/{o1['id']}", json={"notes": "x"}, headers=kbs, timeout=T), 404)
check("send offering", requests.post(f"{B}/recruitment/offerings/{o1['id']}/send", headers=hr, timeout=T), 200)
results.append((stage(c1) == "offering", "stage offering", stage(c1)))
check("double send -> 409", requests.post(f"{B}/recruitment/offerings/{o1['id']}/send", headers=hr, timeout=T), 409)
check("edit offering sent -> 409", requests.put(f"{B}/recruitment/offerings/{o1['id']}", json={"notes": "x"}, headers=hr, timeout=T), 409)
check("KBS respond offering NEP -> 404", requests.post(f"{B}/recruitment/offerings/{o1['id']}/respond", json={"response": "accepted"}, headers=kbs, timeout=T), 404)
with cf.ThreadPoolExecutor(2) as ex:
    futs = [ex.submit(requests.post, f"{B}/recruitment/offerings/{o1['id']}/respond", json={"response": "accepted", "response_notes": "Setuju"}, headers=hr, timeout=T) for _ in range(2)]
    codes = sorted(f.result().status_code for f in futs)
results.append((codes == [200, 409], "concurrent double respond -> [200,409]", codes)); print("  concurrent respond:", codes, flush=True)
results.append((stage(c1) == "offering_accepted", "stage offering_accepted", stage(c1)))
check("offering baru saat accepted aktif -> 409", requests.post(f"{B}/recruitment/candidates/{c1}/offering", json={}, headers=hr, timeout=T), 409)

# declined -> versi baru
c2 = new_candidate("SMOKE-B Kandidat Dua")
iv = requests.post(f"{B}/recruitment/candidates/{c2}/interviews", json={"interview_type": "hr", "scheduled_date": "2026-10-01", "interviewer_user_id": iv_hr}, headers=hr, timeout=T).json()
requests.post(f"{B}/recruitment/interviews/{iv['id']}/complete", json={"result": "passed"}, headers=hr, timeout=T)
a2 = requests.post(f"{B}/recruitment/candidates/{c2}/submit-approval", json={}, headers=hr, timeout=T).json()
st2 = a2["rounds"][0]["steps"]
check("reject step1 oleh hr_manager", requests.post(f"{B}/recruitment/candidates/{c2}/approvals/{st2[0]['id']}/decide", json={"decision": "rejected", "notes": "Budget tidak tersedia"}, headers=hrm, timeout=T), 200)
results.append((stage(c2) == "rejected", "stage rejected", stage(c2)))
a2 = requests.get(f"{B}/recruitment/candidates/{c2}/approvals", headers=hr, timeout=T).json()
print("  decisions after reject:", [(s["step_order"], s["decision"]) for s in a2["rounds"][0]["steps"]], flush=True)
results.append(([s["decision"] for s in a2["rounds"][0]["steps"]] == ["rejected", "skipped"], "step2 skipped setelah reject", None))
check("step2 setelah reject -> 409", requests.post(f"{B}/recruitment/candidates/{c2}/approvals/{st2[1]['id']}/decide", json={"decision": "approved"}, headers=own, timeout=T), 409)
check("offering pada rejected -> 422", requests.post(f"{B}/recruitment/candidates/{c2}/offering", json={}, headers=hr, timeout=T), 422)

# ------------------------------------------------------------------ OFFERING declined -> versi baru, cancel sent -> approved
c3 = new_candidate("SMOKE-B Kandidat Tiga")
iv = requests.post(f"{B}/recruitment/candidates/{c3}/interviews", json={"interview_type": "hr", "scheduled_date": "2026-10-01", "interviewer_user_id": iv_hr}, headers=hr, timeout=T).json()
requests.post(f"{B}/recruitment/interviews/{iv['id']}/complete", json={"result": "passed"}, headers=hr, timeout=T)
a3 = requests.post(f"{B}/recruitment/candidates/{c3}/submit-approval", json={}, headers=hr, timeout=T).json()
for st_ in a3["rounds"][0]["steps"]:
    requests.post(f"{B}/recruitment/candidates/{c3}/approvals/{st_['id']}/decide", json={"decision": "approved"}, headers=(hrm if st_["step_order"] == 1 else own), timeout=T)
results.append((stage(c3) == "approved", "c3 approved", stage(c3)))
o3 = requests.post(f"{B}/recruitment/candidates/{c3}/offering", json={"basic_salary": 7000000, "start_date": "2026-11-01"}, headers=hr, timeout=T).json()
check("send offering c3", requests.post(f"{B}/recruitment/offerings/{o3['id']}/send", headers=hr, timeout=T), 200)
check("respond declined", requests.post(f"{B}/recruitment/offerings/{o3['id']}/respond", json={"response": "declined", "response_notes": "Gaji di bawah ekspektasi"}, headers=hr, timeout=T), 200)
results.append((stage(c3) == "offering_declined", "stage offering_declined", stage(c3)))
o3b = check("offering versi baru setelah declined", requests.post(f"{B}/recruitment/candidates/{c3}/offering", json={"basic_salary": 8000000, "start_date": "2026-11-15"}, headers=hr, timeout=T), 201).json()
results.append((o3b.get("version") == 2, "versi offering = 2", o3b.get("version")))
check("send offering v2", requests.post(f"{B}/recruitment/offerings/{o3b['id']}/send", headers=hr, timeout=T), 200)
results.append((stage(c3) == "offering", "stage offering (v2)", stage(c3)))
check("cancel offering sent -> kembali approved", requests.post(f"{B}/recruitment/offerings/{o3b['id']}/cancel", json={"reason": "Revisi paket"}, headers=hr, timeout=T), 200)
results.append((stage(c3) == "approved", "stage approved setelah cancel", stage(c3)))
offs = requests.get(f"{B}/recruitment/candidates/{c3}/offerings", headers=hr, timeout=T).json()
results.append((offs["active"] is None and offs["can_create"] and len(offs["items"]) == 2, "tidak ada offering aktif, boleh buat baru, 2 histori", (offs["active"], offs["can_create"], len(offs["items"]))))

# ------------------------------------------------------------------ tenant isolation baca
check("KBS GET interviews NEP -> 404", requests.get(f"{B}/recruitment/candidates/{c1}/interviews", headers=kbs, timeout=T), 404)
check("KBS PUT interview NEP -> 404", requests.put(f"{B}/recruitment/interviews/{i2['id']}", json={"notes": "x"}, headers=kbs, timeout=T), 404)
check("KBS complete interview NEP -> 404", requests.post(f"{B}/recruitment/interviews/{i2['id']}/complete", json={"result": "passed"}, headers=kbs, timeout=T), 404)
check("KBS GET approvals NEP -> 404", requests.get(f"{B}/recruitment/candidates/{c1}/approvals", headers=kbs, timeout=T), 404)
check("KBS GET offerings NEP -> 404", requests.get(f"{B}/recruitment/candidates/{c1}/offerings", headers=kbs, timeout=T), 404)
check("KBS GET pipeline NEP -> 404", requests.get(f"{B}/recruitment/candidates/{c1}/pipeline", headers=kbs, timeout=T), 404)
p = check("pipeline NEP", requests.get(f"{B}/recruitment/candidates/{c1}/pipeline", headers=hr, timeout=T), 200).json()
print("  pipeline: interviews", len(p["interviews"]), "| approval rounds", len(p["approval"]["rounds"]), "| offerings", len(p["offerings"]["items"]), flush=True)
hist = requests.get(f"{B}/recruitment/candidates/{c1}", headers=hr, timeout=T).json()["history"]
print("  history c1:", [(h["action"], h["to_status"]) for h in hist], flush=True)
logs = requests.get(f"{B}/audit-logs", params={"module": "recruitment", "limit": 40}, headers=hr, timeout=T).json()
acts = sorted({l.get("action") for l in logs.get("items", [])}); print("  audit actions:", acts, flush=True)

# cleanup draft
requests.delete(f"{B}/recruitment/candidates/{c_draft}", headers=hr, timeout=T)
print("\nRESULT", sum(1 for r in results if r[0]), "/", len(results))
for ok, label, extra in results:
    if not ok: print("  FAILED:", label, extra)
print("WF_ID", wf.get("id"), "C1", c1, "C2", c2, "C3", c3)
