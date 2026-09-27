"""Upgrade 01H - HR Verification: test backend terarah (UPGRADE_01H_HR_VERIFICATION_AUDIT.md §11).

CARA MENJALANKAN (hanya MariaDB development LOKAL):
    cd /app/backend && python3 tests/test_hr_verification_01h.py
    cd /app/backend && python3 -m pytest tests/test_hr_verification_01h.py -q

KEAMANAN TEST
- Guard: APP_ENV=development + host DB loopback + READ_ONLY=false + tanpa kredensial R2. Selain itu test berhenti.
- App dijalankan in-process (httpx ASGITransport); object storage R2 DIGANTI stub in-memory (tidak ada panggilan R2).
- Data uji memakai penanda unik per-run (prefix T01H) di tenant development; tidak menyentuh produksi.
"""
from __future__ import annotations

import asyncio
import pathlib
import secrets
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(pathlib.Path(__file__).resolve().parents[1] / ".env")
import os  # noqa: E402


def _guard() -> None:
    url = urlsplit(os.environ.get("DATABASE_URL", ""))
    if os.environ.get("APP_ENV") != "development" or url.hostname not in {"127.0.0.1", "localhost"}:
        raise SystemExit("DITOLAK: test 01H hanya boleh berjalan pada MariaDB development lokal.")
    if (os.environ.get("READ_ONLY") or "").lower() in ("1", "true", "yes") or os.environ.get("R2_ACCESS_KEY_ID"):
        raise SystemExit("DITOLAK: READ_ONLY aktif atau kredensial R2 terpasang.")


_guard()

import httpx  # noqa: E402

import server  # noqa: E402
from app.core import db as dbm  # noqa: E402
from app.core import hr_verification as HV  # noqa: E402
from app.core import storage as ST  # noqa: E402
from app.core.db import get_db, new_id, now  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.core.tenancy import get_tenant_db  # noqa: E402
from app.routers import employee_update_verification as EUV  # noqa: E402
from app.routers import public_employee_form as PEF  # noqa: E402

# ------------------------------------------------------------------ stub storage (in-memory)
STORE: dict = {}


def _put(path, data, content_type):
    STORE[path] = (data, content_type)
    return {"path": path, "size": len(data), "content_type": content_type, "bucket": "stub"}


def _get(path):
    if path not in STORE:
        raise ST.StorageError("Berkas tidak ditemukan di object storage.")
    return STORE[path]


def _copy(src, dst, content_type=None):
    if src not in STORE:
        raise ST.StorageError("sumber tidak ada")
    STORE[dst] = (STORE[src][0], content_type or STORE[src][1])
    return {"path": dst}


def _delete(path):
    STORE.pop(path, None)


for mod in (ST,):
    mod.put_object, mod.get_object, mod.copy_object, mod.delete_object = _put, _get, _copy, _delete
PEF.put_object, PEF.get_object = _put, _get
EUV.get_object = _get

RUN = secrets.token_hex(3).upper()
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
PDF = b"%PDF-1.4\n" + b"1" * 64
RESULTS: list = []


def check(name: str, cond: bool, info: str = "") -> None:
    RESULTS.append((name, bool(cond), info))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info and not cond else ""))


# ------------------------------------------------------------------ fixture
class Env:
    pass


async def _mk_user(env, role_key, company_id, label):
    db = get_db()
    email = f"t01h.{label}.{RUN.lower()}@kelolakita.dev"
    pw = "T01h-" + secrets.token_urlsafe(12)
    uid = new_id()
    await db.users.insert_one({"id": uid, "company_id": None, "status": "active", "email": email, "full_name": f"T01H {label}",
                               "password_hash": hash_password(pw), "default_company_id": company_id,
                               "must_change_password": False, "is_demo_account": False,
                               "created_at": now(), "updated_at": now()})
    await db.user_company_roles.insert_one({"id": new_id(), "company_id": company_id, "status": "active", "user_id": uid,
                                            "role_key": role_key, "created_at": now(), "updated_at": now()})
    r = await env.c.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _mk_employee(cid, n, **extra):
    tdb = get_tenant_db(cid)
    eid = new_id()
    nik = "3201" + secrets.randbelow(10 ** 12).__str__().zfill(12)
    doc = {"id": eid, "company_id": cid, "status": "active", "employee_number": f"T01H-{RUN}-{n}",
           "full_name": f"Karyawan Uji {n}", "nik": nik, "birth_date": "1990-05-17", "gender": "male",
           "phone": "081200000001", "address": "Jl. Lama No. 1", "bank_account_number": "1234567890",
           "created_at": now(), "updated_at": now(), **extra}
    await tdb.employees.insert_one(doc)
    return doc


async def setup(env):
    db = get_db()
    company = await db.companies.find_one({"code": "DEV"}, {"_id": 0})
    env.cid = company["id"]
    env.tdb = get_tenant_db(env.cid)
    other = {"id": new_id(), "code": f"T{RUN}"[:10], "name": f"PT Lain {RUN}", "status": "active",
             "created_at": now(), "updated_at": now()}
    await db.companies.insert_one(other)
    env.cid_b = other["id"]
    env.hr = await _mk_user(env, "hr_admin", env.cid, "hr")
    env.viewer = await _mk_user(env, "manager", env.cid, "viewer")
    # tipe dokumen & custom field
    dt = await env.tdb.document_types.find_one({"company_id": env.cid, "code": "T01HKTP"}, {"_id": 0})
    if not dt:
        dt = {"id": new_id(), "company_id": env.cid, "status": "active", "code": "T01HKTP", "name": "KTP (uji 01H)",
              "owner_scope": "employee", "allowed_extensions": "pdf,jpg,png", "max_size_mb": 5,
              "created_at": now(), "updated_at": now()}
        await env.tdb.document_types.insert_one(dict(dt))
    env.doc_type = dt
    for key, ftype, opts in (("cf_t01h_baju", "dropdown", [{"value": "M", "label": "M", "active": True},
                                                               {"value": "L", "label": "L", "active": True}]),
                             ("cf_t01h_vaksin", "file", [])):
        if not await env.tdb.employee_form_fields.find_one({"company_id": env.cid, "field_key": key}):
            await env.tdb.employee_form_fields.insert_one({
                "id": new_id(), "company_id": env.cid, "status": "active", "field_key": key, "source": "CUSTOM",
                "section_key": "personal", "sort_order": 900, "visible": True, "label_override": f"Uji {key}",
                "field_type": ftype, "options": opts, "validation": {"allowed_ext": ["pdf"]} if ftype == "file" else {},
                "form_level": "OPTIONAL", "data_version": 1, "created_at": now(), "updated_at": now()})


async def portal_session(env, emp):
    r = await env.c.post("/api/public/employee-form/portal/DEV/verify",
                         json={"employee_number": emp["employee_number"], "nik": emp["nik"], "birth_date": emp["birth_date"]})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


async def submit(env, emp, fields=None, family=None, custom=None, files=(), sess=None):
    sess = sess or await portal_session(env, emp)
    form = (await env.c.get("/api/public/employee-form/form", headers=sess)).json()
    version = (form.get("draft") or {}).get("version") or 0
    body = {"version": version, "fields": fields or {}, "family": family or [], "custom": custom or {}}
    r = await env.c.put("/api/public/employee-form/draft", headers=sess, json=body)
    assert r.status_code == 200, r.text
    version = r.json()["version"]
    for code, name, content, fkey in files:
        data = {"document_type_code": code} if not fkey else {"field_key": fkey}
        r = await env.c.post("/api/public/employee-form/attachments", headers=sess, data=data,
                             files={"file": (name, content, "application/octet-stream")})
        assert r.status_code == 201, r.text
    r = await env.c.post("/api/public/employee-form/submit", headers=sess, json={"version": version})
    assert r.status_code == 200, r.text
    sub = await env.tdb.employee_update_submissions.find_one(
        {"company_id": env.cid, "employee_id": emp["id"], "status": "PENDING_HR_VERIFICATION"}, {"_id": 0})
    return sub, sess


def base(sid):
    return f"/api/employees/update-verifications/{sid}"


# ------------------------------------------------------------------ tests
async def t_approve_full(env):
    emp = await _mk_employee(env.cid, "A", project_id=None)
    fam_upd = {"id": new_id(), "company_id": env.cid, "status": "active", "employee_id": emp["id"], "relationship": "ISTRI",
               "full_name": "Istri Lama", "created_at": now(), "updated_at": now()}
    fam_del = {"id": new_id(), "company_id": env.cid, "status": "active", "employee_id": emp["id"], "relationship": "ANAK",
               "full_name": "Anak Hapus", "created_at": now(), "updated_at": now()}
    for r in (fam_upd, fam_del):
        await env.tdb.employee_family_members.insert_one(dict(r))
    sub, _ = await submit(env, emp,
                          fields={"phone": "081399999999", "bank_account_number": "9876543210", "address": "Jl. Baru No. 9"},
                          family=[{"op": "add", "data": {"relationship": "ANAK", "full_name": "Anak Baru", "nik": "3201999988887777"}},
                                  {"op": "update", "ref": fam_upd["id"], "data": {"relationship": "ISTRI", "full_name": "Istri Baru"}},
                                  {"op": "remove", "ref": fam_del["id"], "reason": "Salah input"}],
                          custom={"cf_t01h_baju": "L"},
                          files=[("T01HKTP", "ktp.pdf", PDF, None), ("PHOTO", "foto.png", PNG, None),
                                 (None, "vaksin.pdf", PDF, "cf_t01h_vaksin")])
    check("approve: submission PENDING dibuat", bool(sub))
    r = await env.c.get("/api/employees/update-verifications/summary", headers=env.hr)
    check("summary 200 + hitungan pending", r.status_code == 200 and r.json()["counts"]["PENDING_HR_VERIFICATION"] >= 1, r.text[:200])
    r = await env.c.get("/api/employees/update-verifications", headers=env.hr, params={"q": emp["employee_number"]})
    row = (r.json().get("items") or [{}])[0]
    check("list: baris + ringkasan perubahan", r.status_code == 200 and row.get("id") == sub["id"]
          and row["changes"].get("contact") == 2 and row["changes"].get("family") == 3 and row["attachments"] == 3, str(row)[:300])
    r = await env.c.get(base(sub["id"]), headers=env.hr)
    d = r.json()
    keys = {i["key"]: i for s in d.get("sections", []) for i in s["items"]}
    check("detail: Data Saat Ini vs Usulan (phone)", keys.get("field:phone", {}).get("current") == "081200000001"
          and keys["field:phone"]["proposed"] == "081399999999" and keys["field:phone"]["state"] == "OK", str(keys.get("field:phone")))
    check("detail: tanpa storage_path", "storage_path" not in r.text and "employee-submissions" not in r.text)
    check("detail: dokumen/foto/custom-file terdeteksi", {"photo", "custom:cf_t01h_vaksin", "custom:cf_t01h_baju"} <= set(keys)
          and any(k.startswith("file:") for k in keys), str(list(keys)))
    fid = d["files"][0]["id"]
    r2 = await env.c.get(f"{base(sub['id'])}/files/{fid}", headers=env.hr)
    check("unduh lampiran HR (no-store)", r2.status_code == 200 and r2.headers.get("cache-control") == "private, no-store")
    before_status, before_project = emp["status"], emp.get("project_id")
    r = await env.c.post(f"{base(sub['id'])}/approve", headers=env.hr, json={"version": d["version"]})
    check("approve 200", r.status_code == 200, r.text[:300])
    e2 = await env.tdb.employees.find_one({"company_id": env.cid, "id": emp["id"]}, {"_id": 0})
    check("core diterapkan", e2["phone"] == "081399999999" and e2["bank_account_number"] == "9876543210" and e2["address"] == "Jl. Baru No. 9")
    check("status/project tidak tersentuh", e2["status"] == before_status and e2.get("project_id") == before_project)
    check("foto dipromosikan ke prefix foto", (e2.get("photo_path") or "").startswith(f"hris-payroll/companies/{env.cid}/employees/{emp['id']}/photo/")
          and e2["photo_path"] in STORE, str(e2.get("photo_path")))
    fam = {f["full_name"]: f for f in await env.tdb.employee_family_members.find({"company_id": env.cid, "employee_id": emp["id"]}, {"_id": 0}).to_list(20)}
    check("keluarga add/update/remove", set(fam) == {"Anak Baru", "Istri Baru"}, str(list(fam)))
    cv = {r["field_key"]: r for r in await env.tdb.employee_custom_field_values.find({"company_id": env.cid, "employee_id": emp["id"]}, {"_id": 0}).to_list(10)}
    check("custom resmi upsert + source_submission_id", cv.get("cf_t01h_baju", {}).get("value") == "L"
          and cv["cf_t01h_baju"]["source_submission_id"] == sub["id"])
    vf = cv.get("cf_t01h_vaksin", {}).get("value") or {}
    check("custom file = referensi (bukan dokumen)", bool(vf.get("files")) and vf["files"][0]["file_name"] == "vaksin.pdf")
    docs = await env.tdb.documents.find({"company_id": env.cid, "owner_type": "employee", "owner_id": emp["id"]}, {"_id": 0}).to_list(10)
    check("dokumen resmi baru (owner benar, objek disalin)", len(docs) == 1 and docs[0]["document_type_id"] == env.doc_type["id"]
          and docs[0]["storage_path"] in STORE and "/documents/" in docs[0]["storage_path"])
    files = await env.tdb.employee_submission_files.find({"company_id": env.cid, "submission_id": sub["id"]}, {"_id": 0}).to_list(10)
    doc_file = next(f for f in files if f["purpose"] == "DOCUMENT")
    check("lampiran PROMOTED + document_id", all(f["status"] == "PROMOTED" for f in files) and doc_file.get("document_id") == docs[0]["id"],
          str([(f["purpose"], f["status"]) for f in files]))
    s2 = await env.tdb.employee_update_submissions.find_one({"id": sub["id"]}, {"_id": 0})
    check("submission APPROVED, open_slot dilepas, completeness_after", s2["status"] == "APPROVED" and s2.get("open_slot") is None
          and HV.jl(s2.get("completeness_after")) is not None and HV.jl(s2.get("review_history"))[-1]["decision"] == "APPROVED")
    ar = HV.jl(s2.get("apply_result"))
    check("apply_result tanpa nilai data", "9876543210" not in str(ar) and "081399999999" not in str(ar))
    audits = await env.tdb.audit_logs.find({"company_id": env.cid, "record_id": {"$in": [emp["id"], sub["id"], docs[0]["id"]]}}, {"_id": 0}).to_list(100)
    acts = {a["action"] for a in audits}
    check("audit trail lengkap", {"employee_update.approved", "update", "family_create", "family_update", "family_delete",
                                  "custom_fields_update", "upload", "photo_upload"} <= acts, str(acts))
    check("audit tanpa nilai sensitif mentah", "9876543210" not in str(audits) and "3201999988887777" not in str(audits))
    r = await env.c.post(f"{base(sub['id'])}/approve", headers=env.hr, json={"version": s2["version"]})
    check("approve ulang pada APPROVED -> 409", r.status_code == 409)
    tl = await env.c.get(f"/api/employees/{emp['id']}/timeline", headers=env.hr)
    check("perubahan muncul di timeline Profile 360", tl.status_code == 200 and any(
        i.get("action") == "update" for i in tl.json()["items"]))
    sess = await portal_session(env, emp)
    f = (await env.c.get("/api/public/employee-form/form", headers=sess)).json()
    check("portal: last_decision APPROVED + boleh pengajuan baru", f["mode"] == "EDIT" and (f.get("last_decision") or {}).get("status") == "APPROVED")
    pre = {c["key"]: c.get("value") for c in f.get("custom_fields", [])}
    check("portal: prefill custom = nilai resmi hasil 01H", pre.get("cf_t01h_baju") == "L", str(pre))
    sub3, _ = await submit(env, emp, custom={"cf_t01h_baju": "M"}, sess=sess)
    d3 = (await env.c.get(base(sub3["id"]), headers=env.hr)).json()
    it = {i["key"]: i for s in d3["sections"] for i in s["items"]}.get("custom:cf_t01h_baju", {})
    check("pengajuan ke-2: current custom = L, usulan = M", it.get("current") == "L" and it.get("proposed") == "M" and it.get("state") == "OK", str(it))
    r = await env.c.post(f"{base(sub3['id'])}/approve", headers=env.hr, json={"version": d3["version"]})
    v3 = await env.tdb.employee_custom_field_values.find_one({"company_id": env.cid, "employee_id": emp["id"], "field_key": "cf_t01h_baju"}, {"_id": 0})
    check("pengajuan ke-2: custom ditimpa via transaksi (tanpa duplikat)", r.status_code == 200 and v3["value"] == "M"
          and await env.tdb.employee_custom_field_values.count_documents({"company_id": env.cid, "employee_id": emp["id"], "field_key": "cf_t01h_baju"}) == 1, r.text[:200])


async def t_reject(env):
    emp = await _mk_employee(env.cid, "R")
    sub, sess = await submit(env, emp, fields={"phone": "081311112222"}, files=[("T01HKTP", "ktp.pdf", PDF, None)])
    r = await env.c.post(f"{base(sub['id'])}/reject", headers=env.hr, json={"version": sub["version"], "reason": ""})
    check("reject tanpa alasan -> 422", r.status_code == 422)
    r = await env.c.post(f"{base(sub['id'])}/reject", headers=env.hr, json={"version": sub["version"], "reason": "Dokumen buram"})
    check("reject 200", r.status_code == 200, r.text[:200])
    e2 = await env.tdb.employees.find_one({"company_id": env.cid, "id": emp["id"]}, {"_id": 0})
    check("reject: master tidak berubah", e2["phone"] == emp["phone"])
    files = await env.tdb.employee_submission_files.find({"company_id": env.cid, "submission_id": sub["id"]}, {"_id": 0}).to_list(10)
    s2 = await env.tdb.employee_update_submissions.find_one({"id": sub["id"]}, {"_id": 0})
    check("reject: file REJECTED + open_slot kosong", all(f["status"] == "REJECTED" for f in files) and s2.get("open_slot") is None)
    f = (await env.c.get("/api/public/employee-form/form", headers=await portal_session(env, emp))).json()
    check("portal: keputusan ditolak + alasan tampil", (f.get("last_decision") or {}).get("reason") == "Dokumen buram" and f["mode"] == "EDIT")
    sub2, _ = await submit(env, emp, fields={"phone": "081333334444"})
    check("reject: karyawan dapat membuat pengajuan baru", sub2 and sub2["id"] != sub["id"])
    await env.c.post(f"{base(sub2['id'])}/reject", headers=env.hr, json={"version": sub2["version"], "reason": "Bersihkan data uji"})


async def t_revision(env):
    emp = await _mk_employee(env.cid, "V")
    sub, _ = await submit(env, emp, fields={"address": "Jl. Revisi 1"})
    r = await env.c.post(f"{base(sub['id'])}/request-revision", headers=env.hr,
                         json={"version": sub["version"], "note": "", "items": []})
    check("revisi tanpa catatan -> 422", r.status_code == 422)
    r = await env.c.post(f"{base(sub['id'])}/request-revision", headers=env.hr,
                         json={"version": sub["version"], "note": "Alamat kurang RT/RW", "items": ["field:nope"]})
    check("revisi item tak dikenal -> 422", r.status_code == 422)
    r = await env.c.post(f"{base(sub['id'])}/request-revision", headers=env.hr,
                         json={"version": sub["version"], "note": "Alamat kurang RT/RW", "items": ["field:address"]})
    check("revisi 200", r.status_code == 200, r.text[:200])
    sess = await portal_session(env, emp)
    f = (await env.c.get("/api/public/employee-form/form", headers=sess)).json()
    check("portal: EDIT + banner revisi (catatan + item)", f["mode"] == "EDIT" and (f.get("revision") or {}).get("note") == "Alamat kurang RT/RW"
          and f["revision"]["items"] == ["field:address"])
    sub2, _ = await submit(env, emp, fields={"address": "Jl. Revisi 1 RT 01/RW 02"}, sess=sess)
    n = await env.tdb.employee_update_submissions.count_documents({"company_id": env.cid, "employee_id": emp["id"]})
    check("kirim ulang: baris SAMA, tanpa duplikat", sub2["id"] == sub["id"] and n == 1 and int(sub2.get("revision_count") or 0) == 1)
    check("kirim ulang: baseline diambil ulang", (HV.jl(sub2["baseline"]) or {}).get("fields", {}).get("address") == emp["address"])
    r = await env.c.post(f"{base(sub['id'])}/approve", headers=env.hr, json={"version": sub2["version"]})
    e2 = await env.tdb.employees.find_one({"company_id": env.cid, "id": emp["id"]}, {"_id": 0})
    check("approve setelah revisi", r.status_code == 200 and e2["address"] == "Jl. Revisi 1 RT 01/RW 02")
    hist = HV.jl((await env.tdb.employee_update_submissions.find_one({"id": sub["id"]}, {"_id": 0}))["review_history"])
    check("riwayat keputusan 2 putaran", [h["decision"] for h in hist] == ["REVISION_REQUESTED", "APPROVED"] and hist[1]["round"] == 2)


async def t_conflict(env):
    for mode in ("keep_current", "use_proposed"):
        emp = await _mk_employee(env.cid, "C" + mode[:4])
        sub, _ = await submit(env, emp, fields={"phone": "081355556666", "address": "Jl. Konflik"})
        r = await env.c.put(f"/api/employees/{emp['id']}", headers=env.hr, json={"phone": "081377778888"})
        assert r.status_code == 200, r.text
        d = (await env.c.get(base(sub["id"]), headers=env.hr)).json()
        check(f"[{mode}] konflik terdeteksi", d["conflicts"] == ["field:phone"] and d["has_conflict"], str(d.get("conflicts")))
        lst = (await env.c.get("/api/employees/update-verifications", headers=env.hr, params={"q": emp["employee_number"]})).json()
        check(f"[{mode}] list flag konflik", lst["items"][0]["has_conflict"] is True)
        r = await env.c.post(f"{base(sub['id'])}/approve", headers=env.hr, json={"version": d["version"]})
        check(f"[{mode}] approve tanpa resolusi -> 409 + daftar konflik", r.status_code == 409 and r.json().get("conflicts") == ["field:phone"], r.text[:200])
        r = await env.c.post(f"{base(sub['id'])}/approve", headers=env.hr,
                             json={"version": d["version"], "resolutions": {"field:address": "use_proposed"}})
        check(f"[{mode}] resolusi utk item non-konflik -> 422", r.status_code == 422)
        r = await env.c.post(f"{base(sub['id'])}/approve", headers=env.hr,
                             json={"version": d["version"], "resolutions": {"field:phone": mode}})
        e2 = await env.tdb.employees.find_one({"company_id": env.cid, "id": emp["id"]}, {"_id": 0})
        exp = "081377778888" if mode == "keep_current" else "081355556666"
        check(f"[{mode}] hasil resolusi diterapkan", r.status_code == 200 and e2["phone"] == exp and e2["address"] == "Jl. Konflik", r.text[:200])


async def t_security(env):
    emp = await _mk_employee(env.cid, "S")
    sub, sess = await submit(env, emp, fields={"phone": "081366667777"})
    r = await env.c.get("/api/employees/update-verifications", headers=env.viewer)
    check("tanpa permission verify -> 403", r.status_code == 403)
    r = await env.c.get("/api/employees/update-verifications")
    check("tanpa token -> 401", r.status_code == 401)
    r = await env.c.post(f"{base(sub['id'])}/approve", headers=sess, json={"version": sub["version"]})
    check("token sesi publik ke endpoint HR -> 401", r.status_code == 401)
    r = await env.c.post(f"{base(sub['id'])}/approve", headers=env.hr, json={"version": sub["version"], "fields": {"status": "inactive"}})
    check("body dengan nilai data (extra) -> 422", r.status_code == 422)
    emp_b = await _mk_employee(env.cid_b, "B")
    sub_b = {"id": new_id(), "company_id": env.cid_b, "status": "PENDING_HR_VERIFICATION", "employee_id": emp_b["id"],
             "source": "PUBLIC_EMPLOYEE_FORM", "open_slot": emp_b["id"], "proposed": {"fields": {"phone": "081300000000"}},
             "baseline": {"fields": {"phone": emp_b["phone"]}}, "version": 2, "created_at": now(), "updated_at": now()}
    await get_tenant_db(env.cid_b).employee_update_submissions.insert_one(dict(sub_b))
    r = await env.c.get(base(sub_b["id"]), headers=env.hr)
    r2 = await env.c.post(f"{base(sub_b['id'])}/approve", headers=env.hr, json={"version": 2})
    check("lintas tenant -> 404 generik", r.status_code == 404 and r2.status_code == 404)
    r = await env.c.post(f"{base(sub['id'])}/approve", headers=env.hr, json={"version": sub["version"] - 1})
    check("versi basi -> 409", r.status_code == 409)
    results = await asyncio.gather(*[env.c.post(f"{base(sub['id'])}/approve", headers=env.hr, json={"version": sub["version"]}) for _ in range(2)])
    codes = sorted(x.status_code for x in results)
    check("race dua HR -> satu 200, satu 409", codes == [200, 409], str(codes))
    draft = {"id": new_id(), "company_id": env.cid, "status": "DRAFT", "employee_id": emp["id"], "source": "PUBLIC_EMPLOYEE_FORM",
             "open_slot": emp["id"], "proposed": {}, "version": 1, "created_at": now(), "updated_at": now()}
    await env.tdb.employee_update_submissions.insert_one(dict(draft))
    r = await env.c.get(base(draft["id"]), headers=env.hr)
    check("DRAFT tidak terlihat di verifikasi -> 404", r.status_code == 404)
    await env.tdb.employee_update_submissions.delete_one({"id": draft["id"]})


async def t_identity_nik(env):
    other = await _mk_employee(env.cid, "N1")
    emp = await _mk_employee(env.cid, "N2")
    sub, _ = await submit(env, emp, fields={"nik": other["nik"]})
    r = await env.c.post(f"{base(sub['id'])}/approve", headers=env.hr, json={"version": sub["version"]})
    check("perubahan identitas tanpa konfirmasi -> 422", r.status_code == 422)
    r = await env.c.post(f"{base(sub['id'])}/approve", headers=env.hr, json={"version": sub["version"], "confirm_identity": True})
    check("NIK duplikat -> 409", r.status_code == 409, r.text[:150])
    await env.c.post(f"{base(sub['id'])}/reject", headers=env.hr, json={"version": sub["version"], "reason": "NIK duplikat"})


async def t_inactive(env):
    emp = await _mk_employee(env.cid, "I")
    sub, _ = await submit(env, emp, fields={"phone": "081399990000"})
    await env.tdb.employees.update_one({"id": emp["id"]}, {"$set": {"status": "inactive"}})
    r = await env.c.post(f"{base(sub['id'])}/approve", headers=env.hr, json={"version": sub["version"]})
    d = (await env.c.get(base(sub["id"]), headers=env.hr)).json()
    check("karyawan nonaktif: approve 409, can_decide false", r.status_code == 409 and d["can_decide"] is False)
    r = await env.c.post(f"{base(sub['id'])}/reject", headers=env.hr, json={"version": sub["version"], "reason": "Karyawan sudah keluar"})
    check("karyawan nonaktif: tolak tetap bisa", r.status_code == 200)


async def t_atomic(env):
    emp = await _mk_employee(env.cid, "T")
    sub, _ = await submit(env, emp, fields={"phone": "081344445555"}, files=[("T01HKTP", "ktp.pdf", PDF, None)])
    keys_before = set(STORE)
    orig = dbm._TxWriter.insert

    async def boom(self, table_name, doc):
        if table_name == "documents":
            raise RuntimeError("simulasi gagal di tengah apply")
        return await orig(self, table_name, doc)

    dbm._TxWriter.insert = boom
    try:
        try:
            await env.c.post(f"{base(sub['id'])}/approve", headers=env.hr, json={"version": sub["version"]})
        except RuntimeError:
            pass
    finally:
        dbm._TxWriter.insert = orig
    e2 = await env.tdb.employees.find_one({"company_id": env.cid, "id": emp["id"]}, {"_id": 0})
    s2 = await env.tdb.employee_update_submissions.find_one({"id": sub["id"]}, {"_id": 0})
    check("gagal di tengah: tanpa perubahan parsial", e2["phone"] == emp["phone"] and s2["status"] == "PENDING_HR_VERIFICATION")
    check("gagal di tengah: salinan objek dibersihkan", set(STORE) == keys_before, str(set(STORE) - keys_before))
    r = await env.c.post(f"{base(sub['id'])}/approve", headers=env.hr, json={"version": sub["version"]})
    check("setelah gagal: approve ulang berhasil", r.status_code == 200, r.text[:150])


async def t_monitoring(env):
    r = await env.c.get("/api/employees/update-form/monitoring", headers=env.hr)
    s = r.json().get("summary", {}) if r.status_code == 200 else {}
    check("monitoring Form Builder: hitungan status 01H", {"revision_requested", "approved", "rejected"} <= set(s), r.text[:200])


async def main():
    env = Env()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://t01h") as c:
        env.c = c
        await setup(env)
        for t in (t_approve_full, t_reject, t_revision, t_conflict, t_security, t_identity_nik, t_inactive, t_atomic, t_monitoring):
            try:
                await t(env)
            except Exception as exc:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                check(f"{t.__name__} (exception)", False, repr(exc)[:200])
    await dbm.close_db()
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n== 01H targeted: {len(RESULTS) - len(failed)}/{len(RESULTS)} PASS ==")
    return failed


def test_hr_verification_01h():
    assert not asyncio.run(main())


if __name__ == "__main__":
    sys.exit(1 if asyncio.run(main()) else 0)
