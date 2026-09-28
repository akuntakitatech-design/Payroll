"""Upgrade 01I - Role & Data Scope: test backend terarah.

CARA MENJALANKAN (hanya MariaDB development LOKAL `hris_dev`, berisi tenant development kode `DEV`):
    cd backend
    APP_ENV=development READ_ONLY=false ENABLE_SCHEDULER=false R2_ACCESS_KEY_ID= R2_SECRET_ACCESS_KEY= \
    DATABASE_URL='mysql://<user>:<password>@127.0.0.1:3306/hris_dev' \
    python3 tests/test_data_scope_01i.py            # atau: python3 -m pytest tests/test_data_scope_01i.py -q
Variabel yang di-export di shell MENGALAHKAN nilai `backend/.env` (load_dotenv tidak menimpa variabel yang sudah ada),
sehingga test dapat dijalankan walau `backend/.env` menunjuk database lain. Tanpa variabel di atas, guard menolak berjalan.

KEAMANAN TEST
- Guard: APP_ENV=development + host DB loopback + nama DB `hris_dev` + READ_ONLY=false + tanpa kredensial R2.
- App in-process (httpx ASGITransport); storage R2 diganti stub in-memory (tidak ada panggilan R2).
- Data uji memakai penanda unik per-run (T01I-<RUN>) dan DIBERSIHKAN di akhir (termasuk tenant uji ke-2).
- Password akun uji dibuat acak per-run di memori, tidak ditulis ke file/log.
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import secrets
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(pathlib.Path(__file__).resolve().parents[1] / ".env")


def _guard() -> None:
    url = urlsplit(os.environ.get("DATABASE_URL", ""))
    if (os.environ.get("APP_ENV") != "development" or url.hostname not in {"127.0.0.1", "localhost"}
            or url.path.strip("/") != "hris_dev"):
        raise SystemExit("DITOLAK: test 01I hanya boleh berjalan pada MariaDB development lokal (hris_dev).")
    if (os.environ.get("READ_ONLY") or "").lower() in ("1", "true", "yes") or os.environ.get("R2_ACCESS_KEY_ID"):
        raise SystemExit("DITOLAK: READ_ONLY aktif atau kredensial R2 terpasang.")


_guard()

import httpx  # noqa: E402
import sqlalchemy as sa  # noqa: E402

import server  # noqa: E402
from app.core import data_scope as DS  # noqa: E402
from app.core import db as dbm  # noqa: E402
from app.core import storage as ST  # noqa: E402
from app.core.db import get_db, new_id, now  # noqa: E402
from app.core.rbac import PLATFORM_ONLY_PERMISSIONS, all_permission_keys  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.core.tenancy import get_tenant_db  # noqa: E402
from app.routers import employee_update_verification as EUV  # noqa: E402
from app.routers import public_employee_form as PEF  # noqa: E402

STORE: dict = {}


def _put(path, data, content_type):
    STORE[path] = (data, content_type)
    return {"path": path, "size": len(data), "content_type": content_type, "bucket": "stub"}


def _get(path):
    if path not in STORE:
        raise ST.StorageError("Berkas tidak ditemukan di object storage.")
    return STORE[path]


def _copy(src, dst, content_type=None):
    STORE[dst] = (STORE[src][0], content_type or STORE[src][1])
    return {"path": dst}


ST.put_object, ST.get_object, ST.copy_object, ST.delete_object = _put, _get, _copy, lambda p: STORE.pop(p, None)
PEF.put_object, PEF.get_object = _put, _get
EUV.get_object = _get

RUN = secrets.token_hex(3).upper()
from datetime import date, timedelta  # noqa: E402
SOON = (date.today() + timedelta(days=30)).isoformat()
MARK = f"T01I-{RUN}"
RESULTS: list = []


def check(name: str, cond: bool, info: str = "") -> None:
    RESULTS.append((name, bool(cond), info))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info and not cond else ""))


class Env:
    pass


# ------------------------------------------------------------------ fixture
async def _mk_user(env, role_key, company_id, label):
    db = get_db()
    email = f"t01i.{label}.{RUN.lower()}@kelolakita.dev"
    pw = "T01i-" + secrets.token_urlsafe(12)
    uid = new_id()
    await db.users.insert_one({"id": uid, "company_id": None, "status": "active", "email": email, "full_name": f"T01I {label}",
                               "password_hash": hash_password(pw), "default_company_id": company_id,
                               "must_change_password": False, "is_demo_account": False, "created_at": now(), "updated_at": now()})
    await db.user_company_roles.insert_one({"id": new_id(), "company_id": None if role_key == "super_admin" else company_id,
                                            "status": "active", "user_id": uid, "role_key": role_key,
                                            "created_at": now(), "updated_at": now()})
    env.user_ids.append(uid)
    r = await env.c.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return uid, {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _mk_project(env, cid, code):
    doc = {"id": new_id(), "company_id": cid, "status": "active", "code": f"{code}{RUN}"[:20], "name": f"Proyek {code} {RUN}",
           "created_at": now(), "updated_at": now()}
    await get_tenant_db(cid).projects.insert_one(dict(doc))
    env.project_ids.append(doc["id"])
    return doc


async def _mk_employee(env, cid, n, project=None, mirror=None):
    """project -> assignment ACTIVE (sumber otoritatif 01D). mirror -> employees.project_id (boleh berbeda, uji mirror)."""
    tdb = get_tenant_db(cid)
    eid = new_id()
    nik = "3201" + str(secrets.randbelow(10 ** 12)).zfill(12)
    doc = {"id": eid, "company_id": cid, "status": "active", "employee_number": f"{MARK}-{n}", "full_name": f"Karyawan 01I {n}",
           "nik": nik, "birth_date": "1990-05-17", "gender": "male", "phone": "081200000001", "address": "Jl. Uji No. 1",
           "bank_account_number": "1234567890", "project_id": mirror if mirror is not None else (project or {}).get("id"),
           "created_at": now(), "updated_at": now()}
    await tdb.employees.insert_one(dict(doc))
    if project:
        await tdb.employee_assignments.insert_one({
            "id": new_id(), "company_id": cid, "status": "active", "employee_id": eid, "project_id": project["id"],
            "assignment_status": "ACTIVE", "start_date": "2024-01-01", "source": "MANUAL", "reason": "uji 01I",
            "created_at": now(), "updated_at": now()})
    env.employee_ids.append(eid)
    return doc


async def _raw_scope(cid, uid, mode, refs):
    db = get_db()
    sid = new_id()
    await db.user_data_scopes.insert_one({"id": sid, "company_id": cid, "user_id": uid, "mode": mode, "status": "active",
                                          "created_at": now(), "updated_at": now()})
    for ref in refs:
        await db.user_data_scope_items.insert_one({"id": new_id(), "company_id": cid, "scope_id": sid, "user_id": uid,
                                                   "dimension": "project", "ref_id": ref, "status": "active",
                                                   "created_at": now(), "updated_at": now()})


async def setup(env):
    db = get_db()
    env.user_ids, env.project_ids, env.employee_ids = [], [], []
    company = await db.companies.find_one({"code": "DEV"}, {"_id": 0})
    env.cid = company["id"]
    env.tdb = get_tenant_db(env.cid)
    other = {"id": new_id(), "code": f"TI{RUN}"[:10], "name": f"PT Lain 01I {RUN}", "status": "active",
             "created_at": now(), "updated_at": now()}
    await db.companies.insert_one(other)
    env.cid_b = other["id"]
    # project & karyawan
    env.pa, env.pb, env.pc = [await _mk_project(env, env.cid, c) for c in ("PA", "PB", "PC")]
    env.px = await _mk_project(env, env.cid_b, "PX")
    env.eA1 = await _mk_employee(env, env.cid, "A1", env.pa)
    env.eA2 = await _mk_employee(env, env.cid, "A2", env.pa)
    env.eB1 = await _mk_employee(env, env.cid, "B1", env.pb)
    env.eC1 = await _mk_employee(env, env.cid, "C1", env.pc)
    env.eM = await _mk_employee(env, env.cid, "M", env.pc, mirror=env.pa["id"])  # mirror P_A, assignment ACTIVE P_C
    env.eS = await _mk_employee(env, env.cid, "S", None)  # standby / tanpa project
    env.eX = await _mk_employee(env, env.cid_b, "X", env.px)  # tenant lain
    # role khusus uji: semua izin tenant (agar 403 ekspor murni karena cakupan, bukan RBAC)
    env.ops_role = f"t01i_ops_{RUN.lower()}"
    await db.roles.insert_one({"id": new_id(), "company_id": env.cid, "status": "active", "key": env.ops_role, "name": f"Uji 01I {RUN}",
                               "is_system": False, "scope": "company", "created_at": now(), "updated_at": now()})
    for k in sorted(set(all_permission_keys()) - PLATFORM_ONLY_PERMISSIONS):
        await db.role_permissions.insert_one({"id": new_id(), "company_id": None, "status": "active", "role_key": env.ops_role,
                                              "permission_key": k, "created_at": now(), "updated_at": now()})
    env.admin_id, env.admin = await _mk_user(env, "tenant_admin", env.cid, "admin")
    env.hrall_id, env.hrall = await _mk_user(env, "hr_admin", env.cid, "hrall")  # tanpa baris scope -> ALL_TENANT
    env.hra_id, env.hra = await _mk_user(env, "hr_admin", env.cid, "hra")
    env.hrab_id, env.hrab = await _mk_user(env, "hr_admin", env.cid, "hrab")
    env.hrb_id, env.hrb = await _mk_user(env, "hr_admin", env.cid, "hrb")
    env.empty_id, env.empty = await _mk_user(env, "hr_admin", env.cid, "empty")
    env.inv_id, env.inv = await _mk_user(env, "hr_admin", env.cid, "invalid")
    env.rops_id, env.rops = await _mk_user(env, env.ops_role, env.cid, "rops")
    env.aops_id, env.aops = await _mk_user(env, env.ops_role, env.cid, "aops")
    env.platform_id, env.platform = await _mk_user(env, "super_admin", env.cid, "platform")
    env.rev_id, env.rev = await _mk_user(env, "hr_admin", env.cid, "revoke")
    env.ta_id, env.ta = await _mk_user(env, "tenant_admin", env.cid, "ta2")
    await _raw_scope(env.cid, env.empty_id, DS.SELECTED_PROJECTS, [])  # restricted tanpa item
    await _raw_scope(env.cid, env.inv_id, DS.SELECTED_PROJECTS, [env.px["id"], new_id()])  # project tenant lain + tidak ada


async def cleanup(env):
    db = get_db()
    eng = dbm.get_engine()
    emp_ids, uids, pids = env.employee_ids, env.user_ids, env.project_ids
    async with eng.begin() as conn:
        async def d(sql, **p):
            stmt = sa.text(sql)
            for k, v in p.items():
                if isinstance(v, (list, tuple)):
                    stmt = stmt.bindparams(sa.bindparam(k, expanding=True))
            await conn.execute(stmt, p)
        if emp_ids:
            for t in ("employee_assignments", "employee_contracts", "employee_certifications", "employee_completeness",
                      "employee_status_history", "employee_family_members", "employee_custom_field_values"):
                await d(f"DELETE FROM {t} WHERE employee_id IN :ids", ids=emp_ids)
            await d("DELETE FROM employee_submission_files WHERE submission_id IN (SELECT id FROM employee_update_submissions WHERE employee_id IN :ids)", ids=emp_ids)
            for t in ("employee_update_submissions", "employee_public_links"):
                await d(f"DELETE FROM {t} WHERE employee_id IN :ids", ids=emp_ids)
            await d("DELETE FROM documents WHERE owner_id IN :ids", ids=emp_ids)
            await d("DELETE FROM audit_logs WHERE record_id IN :ids", ids=emp_ids + uids)
            await d("DELETE FROM employees WHERE id IN :ids", ids=emp_ids)
        await d("DELETE FROM documents WHERE name LIKE :m", m=f"%{MARK}%")
        await d("DELETE FROM leave_types WHERE name LIKE :m", m=f"%{MARK}%")
        await d("DELETE FROM audit_logs WHERE record_label LIKE :m OR notes LIKE :m", m=f"%{MARK}%")
        if uids:
            await d("DELETE FROM audit_logs WHERE user_id IN :ids", ids=uids)
            await d("DELETE FROM user_data_scope_items WHERE user_id IN :ids", ids=uids)
            await d("DELETE FROM user_data_scopes WHERE user_id IN :ids", ids=uids)
            await d("DELETE FROM user_company_roles WHERE user_id IN :ids", ids=uids)
            await d("DELETE FROM positions WHERE name LIKE :m", m=f"%{MARK}%")
            await d("DELETE FROM users WHERE id IN :ids", ids=uids)
        if pids:
            await d("DELETE FROM projects WHERE id IN :ids", ids=pids)
        await d("DELETE FROM role_permissions WHERE role_key = :r", r=env.ops_role)
        await d("DELETE FROM roles WHERE `key` = :r", r=env.ops_role)
        await d("DELETE FROM audit_logs WHERE company_id = :c", c=env.cid_b)
        await d("DELETE FROM companies WHERE id = :c", c=env.cid_b)
    left = await db.employees.count_documents({"employee_number": {"$regex": MARK}})
    left_u = await db.users.count_documents({"email": {"$regex": f"t01i\\..*\\.{RUN.lower()}@"}})
    print(f"cleanup: sisa karyawan uji={left}, sisa user uji={left_u}")
    return left == 0 and left_u == 0


# ------------------------------------------------------------------ helpers
async def names(env, headers, **params):
    r = await env.c.get("/api/employees", headers=headers, params={"q": MARK, "limit": 100, **params})
    body = r.json() if r.status_code == 200 else {}
    return r.status_code, {i["employee_number"].split("-")[-1] for i in body.get("items", [])}, body.get("total")


async def put_scope(env, uid, mode, pids, headers=None):
    return await env.c.put(f"/api/users/{uid}/data-scope", headers=headers or env.admin, json={"mode": mode, "project_ids": pids})


async def portal_submit(env, emp, phone):
    r = await env.c.post("/api/public/employee-form/portal/DEV/verify",
                         json={"employee_number": emp["employee_number"], "nik": emp["nik"], "birth_date": emp["birth_date"]})
    assert r.status_code == 200, r.text
    sess = {"Authorization": f"Bearer {r.json()['session_token']}"}
    form = (await env.c.get("/api/public/employee-form/form", headers=sess)).json()
    version = (form.get("draft") or {}).get("version") or 0
    r = await env.c.put("/api/public/employee-form/draft", headers=sess, json={"version": version, "fields": {"phone": phone}, "family": [], "custom": {}})
    assert r.status_code == 200, r.text
    r = await env.c.post("/api/public/employee-form/submit", headers=sess, json={"version": r.json()["version"]})
    assert r.status_code == 200, r.text
    return await env.tdb.employee_update_submissions.find_one(
        {"company_id": env.cid, "employee_id": emp["id"], "status": "PENDING_HR_VERIFICATION"}, {"_id": 0})


# ------------------------------------------------------------------ tests
async def t_scope_api(env):
    r = await put_scope(env, env.hra_id, DS.SELECTED_PROJECTS, [env.pa["id"]])
    check("PUT scope hrA = [P_A] -> 200", r.status_code == 200 and r.json()["effective_mode"] == DS.SELECTED_PROJECTS, r.text[:200])
    r = await put_scope(env, env.hrab_id, DS.SELECTED_PROJECTS, [env.pa["id"], env.pb["id"]])
    check("PUT scope hrAB = [P_A,P_B] (multi) -> 200", r.status_code == 200 and r.json()["valid_project_count"] == 2, r.text[:200])
    r = await put_scope(env, env.hrb_id, DS.SELECTED_PROJECTS, [env.pb["id"]])
    check("PUT scope hrB = [P_B] -> 200", r.status_code == 200)
    r = await put_scope(env, env.rops_id, DS.SELECTED_PROJECTS, [env.pa["id"]])
    check("PUT scope rOps = [P_A] -> 200", r.status_code == 200)
    r = await put_scope(env, env.hrall_id, DS.SELECTED_PROJECTS, [env.px["id"]])
    check("PUT scope: project milik tenant lain -> 422", r.status_code == 422, str(r.status_code))
    r = await put_scope(env, env.hrall_id, DS.SELECTED_PROJECTS, [])
    check("PUT scope: Project Tertentu tanpa project -> 422", r.status_code == 422)
    r = await put_scope(env, env.hrall_id, "DEPARTMENT", [])
    check("PUT scope: mode tidak dikenal -> 422", r.status_code == 422)
    r = await put_scope(env, env.admin_id, DS.SELECTED_PROJECTS, [env.pa["id"]])
    check("PUT scope: ubah cakupan diri sendiri -> 403", r.status_code == 403)
    r = await put_scope(env, env.hrall_id, DS.ALL_TENANT, [], headers=env.rops)
    check("PUT scope oleh user restricted (punya user:edit) -> 403", r.status_code == 403, str(r.status_code))
    r = await put_scope(env, env.eX["id"], DS.ALL_TENANT, [])
    check("PUT scope: user bukan anggota tenant -> 404", r.status_code == 404)
    row = await get_db().user_data_scopes.find_one({"company_id": env.cid, "user_id": env.hra_id}, {"_id": 0})
    items = await get_db().user_data_scope_items.find({"scope_id": row["id"]}, {"_id": 0}).to_list(10)
    check("model: scope menyimpan company_id+user_id; item terikat scope_id & company sama",
          row["company_id"] == env.cid and len(items) == 1 and items[0]["company_id"] == env.cid
          and items[0]["ref_id"] == env.pa["id"], str(items)[:200])
    r = await env.c.get("/api/users", headers=env.admin, params={"q": f"{RUN.lower()}", "limit": 100})
    by = {u["id"]: u for u in r.json().get("items", [])}
    check("daftar pengguna: kolom Cakupan (hrA Project Tertentu + nama project)",
          by.get(env.hra_id, {}).get("data_scope", {}).get("mode") == DS.SELECTED_PROJECTS
          and [p["name"] for p in by[env.hra_id]["data_scope"]["projects"]] == [env.pa["name"]], str(by.get(env.hra_id, {}).get("data_scope")))
    check("daftar pengguna: Tenant Admin = Semua Data (peran)", by.get(env.admin_id, {}).get("data_scope", {}).get("full_scope_role") is True)
    check("daftar pengguna: restricted tanpa project valid = Tidak ada akses",
          by.get(env.empty_id, {}).get("data_scope", {}).get("no_access") is True and by.get(env.inv_id, {}).get("data_scope", {}).get("no_access") is True)
    me = (await env.c.get("/api/auth/me", headers=env.hra)).json().get("data_scope") or {}
    check("/auth/me: indikator scope user login", me.get("effective_mode") == DS.SELECTED_PROJECTS and me["projects"][0]["name"] == env.pa["name"], str(me)[:200])
    me = (await env.c.get("/api/users/me/data-scope", headers=env.empty)).json()
    check("/users/me/data-scope: restricted kosong -> no_access (bukan full)", me.get("no_access") is True and me.get("effective_mode") == DS.SELECTED_PROJECTS)


async def t_all_tenant(env):
    code, got, total = await names(env, env.hrall)
    check("ALL_TENANT (tanpa baris scope): semua karyawan company terlihat", code == 200 and got == {"A1", "A2", "B1", "C1", "M", "S"} and total == 6, f"{got} {total}")
    code, got, _ = await names(env, env.admin)
    check("Tenant Admin: full scope", got == {"A1", "A2", "B1", "C1", "M", "S"}, str(got))
    r = await env.c.get(f"/api/employees/{env.eS['id']}", headers=env.hrall)
    check("ALL_TENANT: karyawan standby (tanpa project) dapat diakses", r.status_code == 200)
    r = await env.c.get(f"/api/employees/{env.eX['id']}", headers=env.hrall)
    check("ALL_TENANT: karyawan tenant lain tetap 404 (tenant isolation)", r.status_code == 404)
    await _raw_scope(env.cid, env.admin_id, DS.SELECTED_PROJECTS, [])
    code, got, _ = await names(env, env.admin)
    check("Tenant Admin dengan baris restricted tetap full (aturan peran)", got == {"A1", "A2", "B1", "C1", "M", "S"}, str(got))


async def t_selected(env):
    code, got, total = await names(env, env.hra)
    check("SELECTED satu project: hanya karyawan assignment ACTIVE P_A", code == 200 and got == {"A1", "A2"} and total == 2, f"{got} {total}")
    check("mirror employees.project_id BUKAN sumber scope (M mirror P_A, ACTIVE P_C -> tidak terlihat)", "M" not in got)
    code, got, total = await names(env, env.hrab)
    check("SELECTED multi-project: P_A + P_B", got == {"A1", "A2", "B1"} and total == 3, f"{got} {total}")
    code, got, total = await names(env, env.hra, project_id=env.pb["id"])
    check("filter project di luar cakupan -> 0 (tidak melebar)", got == set() and total == 0)
    r = await env.c.get("/api/employees/stats", headers=env.hra)
    check("stats mengikuti cakupan (total = 2 karyawan P_A)", r.status_code == 200 and r.json()["total"] == 2, r.text[:120])


async def t_direct_uuid(env):
    r = await env.c.get(f"/api/employees/{env.eC1['id']}", headers=env.hra)
    check("direct UUID di luar scope -> 404", r.status_code == 404, str(r.status_code))
    r2 = await env.c.get(f"/api/employees/{new_id()}", headers=env.hra)
    check("404 generik: pesan sama dengan UUID tidak ada", r.status_code == 404 and r.json()["detail"] == r2.json()["detail"])
    r = await env.c.get(f"/api/employees/{env.eA1['id']}", headers=env.hra)
    check("direct UUID dalam scope -> 200", r.status_code == 200)
    for path in ("assignments", "status-history", "family", "timeline", "completeness"):
        r = await env.c.get(f"/api/employees/{env.eC1['id']}/{path}", headers=env.hra)
        check(f"sub-resource /{path} di luar scope -> 404", r.status_code == 404, str(r.status_code))
    r = await env.c.put(f"/api/employees/{env.eC1['id']}", headers=env.hra, json={"phone": "081299990000"})
    check("update employee di luar scope -> 404", r.status_code == 404, str(r.status_code))
    e = await env.tdb.employees.find_one({"id": env.eC1["id"]}, {"_id": 0})
    check("update di luar scope: data tidak berubah", e["phone"] == "081200000001")
    r = await env.c.put(f"/api/employees/{env.eA1['id']}", headers=env.hra, json={"phone": "081299990001"})
    check("update employee dalam scope -> 200", r.status_code == 200, r.text[:150])
    r = await env.c.delete(f"/api/employees/{env.eC1['id']}", headers=env.hra)
    check("delete employee di luar scope -> 404", r.status_code == 404)
    r = await env.c.post(f"/api/employees/{env.eC1['id']}/status-change", headers=env.hra,
                         json={"new_status_id": new_id(), "effective_date": "2024-01-02", "reason": "uji cakupan"})
    check("ubah status di luar scope -> 404", r.status_code == 404, str(r.status_code))


async def t_related(env):
    tdb = env.tdb
    dt = await tdb.document_types.find_one({"company_id": env.cid, "status": "active"}, {"_id": 0})
    docs = {}
    for key, owner_type, owner in (("A1", "employee", env.eA1["id"]), ("C1", "employee", env.eC1["id"]), ("CO", "company", None)):
        d = {"id": new_id(), "company_id": env.cid, "status": "active", "document_type_id": (dt or {}).get("id"),
             "name": f"Dok {key} {MARK}", "owner_type": owner_type, "owner_id": owner, "is_deleted": False,
             "created_at": now(), "updated_at": now()}
        await tdb.documents.insert_one(dict(d))
        docs[key] = d
    r = await env.c.get("/api/documents", headers=env.hra, params={"q": MARK, "limit": 100})
    got = {i["name"].split()[1] for i in r.json().get("items", [])}
    check("dokumen: list restricted hanya dokumen karyawan dalam scope", r.status_code == 200 and got == {"A1"}, str(got))
    r = await env.c.get("/api/documents", headers=env.hrall, params={"q": MARK, "limit": 100})
    check("dokumen: ALL_TENANT melihat semua (termasuk dokumen perusahaan)", {i["name"].split()[1] for i in r.json().get("items", [])} == {"A1", "C1", "CO"})
    r = await env.c.get(f"/api/documents/{docs['C1']['id']}", headers=env.hra)
    check("dokumen karyawan di luar scope -> 404", r.status_code == 404)
    r = await env.c.get(f"/api/documents/{docs['CO']['id']}", headers=env.hra)
    check("dokumen perusahaan untuk restricted -> 404 (fail-closed)", r.status_code == 404)
    r = await env.c.get(f"/api/documents/{docs['A1']['id']}", headers=env.hra)
    check("dokumen dalam scope -> 200", r.status_code == 200)
    ct = {}
    for key, emp in (("A1", env.eA1), ("C1", env.eC1)):
        c = {"id": new_id(), "company_id": env.cid, "status": "active", "employee_id": emp["id"], "contract_number": f"{MARK}-K{key}",
             "start_date": "2024-01-01", "end_date": SOON, "created_at": now(), "updated_at": now()}
        await tdb.employee_contracts.insert_one(dict(c))
        ct[key] = c
    r = await env.c.get("/api/contracts", headers=env.hra, params={"q": MARK, "limit": 100})
    got = {i["contract_number"] for i in r.json().get("items", [])}
    check("kontrak: list restricted hanya dalam scope", r.status_code == 200 and got == {f"{MARK}-KA1"}, str(got))
    r = await env.c.get(f"/api/contracts/{ct['C1']['id']}", headers=env.hra)
    check("kontrak di luar scope -> 404", r.status_code == 404)
    cal = {}
    for who, h in (("hra", env.hra), ("hrall", env.hrall)):
        r = await env.c.get("/api/reminders/expiry", headers=h, params={"kind": "contract", "days": 90})
        cal[who] = {i.get("title") for i in r.json().get("items", []) if MARK in (i.get("title") or "")} if r.status_code == 200 else None
    check("kalender kedaluwarsa: restricted hanya kontrak dalam scope; ALL_TENANT melihat keduanya",
          cal["hra"] == {f"{MARK}-KA1"} and cal["hrall"] == {f"{MARK}-KA1", f"{MARK}-KC1"}, str(cal))
    r = await env.c.get("/api/certifications", headers=env.hra, params={"employee_id": env.eC1["id"]})
    check("sertifikasi: filter employee di luar scope -> 0", r.status_code == 200 and r.json()["total"] == 0)
    r = await env.c.get("/api/completeness/employees", headers=env.hra, params={"q": MARK, "limit": 100})
    ids = {i["employee_id"] for i in r.json().get("items", [])} if r.status_code == 200 else None
    check("kelengkapan 01F: list hanya dalam scope", ids is not None and ids <= {env.eA1["id"], env.eA2["id"]}, str(r.status_code))
    r = await env.c.get("/api/completeness/summary", headers=env.empty)
    check("kelengkapan 01F summary: restricted kosong -> total 0", r.status_code == 200 and r.json()["total"] == 0 and r.json()["not_evaluated"] == 0, r.text[:150])
    r = await env.c.get("/api/employees/update-form/monitoring", headers=env.empty)
    check("monitoring 01G: restricted kosong -> active_employees 0", r.status_code == 200 and r.json()["summary"]["active_employees"] == 0, r.text[:150])
    ra = await env.c.get("/api/employees/update-form/monitoring", headers=env.hra, params={"project_id": env.pa["id"]})
    check("monitoring 01G: restricted = jumlah karyawan P_A (2)", ra.status_code == 200 and ra.json()["summary"]["active_employees"] == 2, ra.text[:150])
    check("monitoring 01G: opsi filter project hanya dalam scope", [p["id"] for p in ra.json()["filters"]["projects"]] == [env.pa["id"]])
    r = await env.c.get("/api/dashboard/summary", headers=env.empty)
    check("dashboard: restricted kosong tidak menampilkan jumlah karyawan tenant", r.status_code == 200, str(r.status_code))


async def t_empty_invalid(env):
    for label, h in (("kosong", env.empty), ("project tidak valid/tenant lain", env.inv)):
        code, got, total = await names(env, h)
        check(f"restricted {label} -> 0 karyawan (fail-closed)", code == 200 and got == set() and total == 0, f"{code} {got} {total}")
        r = await env.c.get(f"/api/employees/{env.eS['id']}", headers=h)
        check(f"restricted {label}: direct UUID -> 404", r.status_code == 404)
    r = await env.c.get("/api/employees/stats", headers=env.empty)
    check("restricted kosong: stats total 0", r.status_code == 200 and r.json()["total"] == 0)
    s = await DS.compute_scope(env.cid, env.inv_id, ["hr_admin"])
    check("engine: project tenant lain tidak pernah dihitung valid", s.restricted and not s.project_ids and s.configured_items == 2)
    await get_db().user_data_scopes.update_one({"company_id": env.cid, "user_id": env.empty_id}, {"$set": {"mode": "BOGUS"}})
    s = await DS.compute_scope(env.cid, env.empty_id, ["hr_admin"])
    check("engine: mode rusak -> fail-closed (bukan ALL_TENANT)", s.restricted and s.has_no_access and s.source == "invalid")


async def t_standby(env):
    for label, h in (("hrA", env.hra), ("hrAB", env.hrab)):
        r = await env.c.get(f"/api/employees/{env.eS['id']}", headers=h)
        check(f"standby tanpa project: restricted {label} -> 404", r.status_code == 404)
    r = await env.c.get(f"/api/employees/{env.eS['id']}", headers=env.hrall)
    check("standby tanpa project: ALL_TENANT -> 200", r.status_code == 200)
    r = await env.c.post("/api/employees", headers=env.hra, json={"full_name": f"Baru {MARK}", "employee_number": f"{MARK}-N1"})
    check("restricted buat karyawan tanpa project -> 403", r.status_code == 403, str(r.status_code))


async def t_transfer(env):
    r = await env.c.post(f"/api/employees/{env.eA1['id']}/assignments/transfer", headers=env.hra,
                         json={"project_id": env.pc["id"], "start_date": "2025-01-01", "reason": "uji tujuan luar cakupan"})
    check("restricted transfer ke project di luar scope -> 403", r.status_code == 403, str(r.status_code))
    before_a = (await env.c.get(f"/api/employees/{env.eA2['id']}", headers=env.hra)).status_code
    before_b = (await env.c.get(f"/api/employees/{env.eA2['id']}", headers=env.hrb)).status_code
    r = await env.c.post(f"/api/employees/{env.eA2['id']}/assignments/transfer", headers=env.admin,
                         json={"project_id": env.pb["id"], "start_date": "2025-01-01", "reason": "Pindah project uji 01I"})
    check("transfer A->B oleh admin -> 201", r.status_code == 201, r.text[:200])
    after_a = (await env.c.get(f"/api/employees/{env.eA2['id']}", headers=env.hra)).status_code
    after_b = (await env.c.get(f"/api/employees/{env.eA2['id']}", headers=env.hrb)).status_code
    check("transfer A->B: sebelum, Admin A 200 / Admin B 404", before_a == 200 and before_b == 404, f"{before_a} {before_b}")
    check("transfer A->B: Admin A kehilangan akses (404)", after_a == 404, str(after_a))
    check("transfer A->B: Admin B mendapat akses (200) seketika", after_b == 200, str(after_b))
    _, got, _ = await names(env, env.hra)
    check("transfer A->B: list Admin A tidak lagi memuat A2", got == {"A1"}, str(got))


async def t_scope_change_immediate(env):
    r = await put_scope(env, env.hra_id, DS.SELECTED_PROJECTS, [env.pc["id"]])
    _, got, _ = await names(env, env.hra)
    check("perubahan scope berlaku seketika (tanpa cache basi): hrA -> [P_C]", r.status_code == 200 and got == {"C1", "M"}, str(got))
    await put_scope(env, env.hra_id, DS.SELECTED_PROJECTS, [env.pa["id"]])


async def t_hr_verification(env):
    sub_c = await portal_submit(env, env.eC1, "081377770001")
    sub_a = await portal_submit(env, env.eA1, "081377770002")
    check("01H: submission uji dibuat", bool(sub_c) and bool(sub_a))
    r = await env.c.get("/api/employees/update-verifications", headers=env.hra, params={"status": "ALL", "q": MARK})
    ids = {i["id"] for i in r.json().get("items", [])}
    check("01H list: restricted hanya submission karyawan dalam scope", r.status_code == 200 and sub_a["id"] in ids and sub_c["id"] not in ids, str(len(ids)))
    r = await env.c.get("/api/employees/update-verifications", headers=env.hrall, params={"status": "ALL", "q": MARK})
    check("01H list: ALL_TENANT melihat keduanya", {sub_a["id"], sub_c["id"]} <= {i["id"] for i in r.json().get("items", [])})
    r = await env.c.get("/api/employees/update-verifications/summary", headers=env.empty)
    check("01H summary: restricted kosong -> 0 pending", r.status_code == 200 and r.json()["pending"] == 0)
    base = f"/api/employees/update-verifications/{sub_c['id']}"
    r = await env.c.get(base, headers=env.hra)
    check("01H detail di luar scope -> 404", r.status_code == 404)
    r = await env.c.post(f"{base}/approve", headers=env.hra, json={"version": sub_c["version"]})
    check("01H approve di luar scope -> ditolak 404", r.status_code == 404)
    r = await env.c.post(f"{base}/reject", headers=env.hra, json={"version": sub_c["version"], "reason": "uji cakupan data"})
    check("01H reject di luar scope -> ditolak 404", r.status_code == 404)
    r = await env.c.post(f"{base}/request-revision", headers=env.hra, json={"version": sub_c["version"], "note": "uji cakupan data"})
    check("01H request-revision di luar scope -> ditolak 404", r.status_code == 404)
    s2 = await env.tdb.employee_update_submissions.find_one({"id": sub_c["id"]}, {"_id": 0})
    e2 = await env.tdb.employees.find_one({"id": env.eC1["id"]}, {"_id": 0})
    check("01H di luar scope: submission tetap PENDING, data karyawan tidak berubah",
          s2["status"] == "PENDING_HR_VERIFICATION" and e2["phone"] == "081200000001")
    r = await env.c.get(f"/api/employees/update-verifications/{sub_a['id']}", headers=env.hra)
    check("01H detail dalam scope -> 200", r.status_code == 200, r.text[:150])
    r = await env.c.post(f"/api/employees/update-verifications/{sub_a['id']}/approve", headers=env.hra, json={"version": r.json().get("version")})
    check("01H approve dalam scope -> 200", r.status_code == 200, r.text[:200])
    # submission mengikuti project SAAT review: pindahkan C1 ke P_A -> hrA kini boleh meninjau
    r = await env.c.post(f"/api/employees/{env.eC1['id']}/assignments/transfer", headers=env.admin,
                         json={"project_id": env.pa["id"], "start_date": "2025-01-01", "reason": "Pindah untuk uji review 01I"})
    r2 = await env.c.get(base, headers=env.hra)
    check("01H mengikuti project karyawan saat review (setelah transfer C->A: 200)", r.status_code == 201 and r2.status_code == 200, f"{r.status_code} {r2.status_code}")


async def t_full_scope_ops(env):
    r = await env.c.get("/api/payroll/runs/" + new_id() + "/export", headers=env.aops)
    base_code = r.status_code
    cases = [("GET", "/api/employees/import/template"), ("GET", "/api/employee-import/template"),
             ("GET", "/api/employee-import/batches"), ("GET", "/api/audit-logs/export"), ("GET", "/api/leave/export"),
             ("GET", "/api/overtime/export"), ("GET", "/api/attendance/recap/export"),
             ("GET", f"/api/payroll/runs/{new_id()}/export"), ("GET", f"/api/payroll/runs/{new_id()}/statutory-report/export"),
             ("POST", "/api/completeness/reevaluate"), ("GET", "/api/employees/update-form/config")]
    for method, path in cases:
        rr = await env.c.request(method, path, headers=env.rops, json={} if method == "POST" else None)
        ra = await env.c.request(method, path, headers=env.aops, json={} if method == "POST" else None)
        check(f"full-scope only {method} {path}: restricted 403 (Cakupan) / ALL bukan 403",
              rr.status_code == 403 and "Cakupan Data" in rr.text and ra.status_code != 403, f"r={rr.status_code} a={ra.status_code}")
    check("payroll export ALL_TENANT dengan run tak ada -> 404 (bukan 403)", base_code == 404, str(base_code))


async def t_engine_sql(env):
    s = await DS.compute_scope(env.cid, env.hrab_id, ["hr_admin"])
    t = dbm.get_table("employees")
    sql = str(DS.employee_scope_clause(s, t.c.id).compile(compile_kwargs={"literal_binds": True}))
    check("engine: filter scope = subquery SQL pada employee_assignments ACTIVE (bukan filter Python)",
          "employee_assignments" in sql and "assignment_status" in sql and "ACTIVE" in sql and env.pa["id"] in sql, sql[:200])
    s_all = await DS.compute_scope(env.cid, env.hrall_id, ["hr_admin"])
    check("engine: ALL_TENANT tanpa klausa tambahan", DS.employee_scope_clause(s_all, t.c.id) is None and DS.scope_filter(s_all) == {})
    # scope per company: user yang sama di tenant B punya konfigurasi sendiri (default ALL_TENANT), tidak ikut tenant A
    await get_db().user_company_roles.insert_one({"id": new_id(), "company_id": env.cid_b, "status": "active", "user_id": env.hrab_id,
                                                  "role_key": "hr_admin", "created_at": now(), "updated_at": now()})
    await DS.set_user_scope(env.cid_b, env.hrab_id, DS.SELECTED_PROJECTS, [env.px["id"]], env.admin_id)
    sa_ = await DS.compute_scope(env.cid, env.hrab_id, ["hr_admin"])
    sb_ = await DS.compute_scope(env.cid_b, env.hrab_id, ["hr_admin"])
    check("scope per company: user sama, konfigurasi berbeda per tenant",
          sa_.project_ids == {env.pa["id"], env.pb["id"]} and sb_.project_ids == {env.px["id"]}, f"{sa_.project_ids} {sb_.project_ids}")
    try:
        await DS.set_user_scope(env.cid, env.hrab_id, DS.SELECTED_PROJECTS, [env.px["id"]], env.admin_id)
        ok = False
    except Exception as exc:  # noqa: BLE001
        ok = getattr(exc, "status_code", None) == 422
    check("engine: project company lain ditolak saat simpan (422)", ok)


async def t_supervisor_out_of_scope(env):
    tdb = env.tdb
    sup = {"id": new_id(), "company_id": env.cid, "status": "active", "code": f"S{RUN}", "name": f"Pos Atasan {MARK}",
           "created_at": now(), "updated_at": now()}
    sub = {"id": new_id(), "company_id": env.cid, "status": "active", "code": f"B{RUN}", "name": f"Pos Staf {MARK}",
           "reports_to_position_id": sup["id"], "created_at": now(), "updated_at": now()}
    for d in (sup, sub):
        await tdb.positions.insert_one(dict(d))
    await tdb.employees.update_one({"id": env.eA1["id"]}, {"$set": {"position_id": sub["id"]}})
    await tdb.employees.update_one({"id": env.eC1["id"]}, {"$set": {"position_id": sup["id"]}})  # atasan di P_C
    r = await env.c.get(f"/api/employees/{env.eA1['id']}", headers=env.hra)
    e = r.json().get("employee", {}) if r.status_code == 200 else {}
    check("atasan di luar scope: profil karyawan tetap 200", r.status_code == 200, str(r.status_code))
    check("atasan di luar scope: nama/identitas atasan TIDAK diekspos",
          e.get("supervisor_name") is None and e.get("supervisor_out_of_scope") is True
          and env.eC1["full_name"] not in r.text and env.eC1["employee_number"] not in r.text, str({k: e.get(k) for k in ("supervisor_name", "supervisor_out_of_scope")}))
    check("atasan di luar scope: marker aman 'Di luar cakupan akses'", e.get("supervisor_name_label") == "Di luar cakupan akses")
    r = await env.c.get(f"/api/employees/{env.eA1['id']}", headers=env.hrall)
    check("atasan: ALL_TENANT tetap melihat nama atasan", r.json()["employee"].get("supervisor_name") == env.eC1["full_name"])
    await tdb.employees.update_one({"id": env.eA1["id"]}, {"$set": {"position_id": None}})
    await tdb.employees.update_one({"id": env.eC1["id"]}, {"$set": {"position_id": None}})


async def t_unscoped_modules(env):
    """Keputusan 01I: SELECTED_PROJECTS -> 403 untuk modul tenant-wide belum scope-aware (Attendance, Cuti/Lembur,
    Payroll, Recruitment, Schedules/Shift, Audit Logs, approval operasional). ALL_TENANT tidak berubah.
    Konfigurasi Approval Workflow company-level tetap RBAC. Endpoint MANDIRI (data milik sendiri) tidak diblokir."""
    rid = new_id()
    cases = [
        # Attendance (list/detail/write/approval operasional)
        ("GET", "/api/attendance", None), ("GET", f"/api/attendance/{rid}", None), ("GET", "/api/attendance/dashboard", None),
        ("GET", "/api/attendance/exceptions", None), ("GET", "/api/attendance/recap", None),
        ("GET", "/api/attendance/corrections", None), ("GET", "/api/attendance/approvals", None),
        ("POST", f"/api/attendance/approvals/{rid}/decide", {"decision": "approved"}),
        ("POST", "/api/attendance/manual", {}), ("GET", "/api/attendance/imports", None),
        # Schedules / Shift / time config
        ("GET", "/api/schedules", None), ("POST", "/api/schedules/bulk", {}), ("GET", "/api/time/shifts", None),
        ("POST", "/api/time/shifts", {}), ("GET", "/api/time/calendar-days", None), ("GET", "/api/time/policies", None),
        ("GET", "/api/time/periods", None),
        # Cuti / Lembur
        ("GET", "/api/leave/requests", None), ("GET", "/api/leave/balances", None), ("GET", "/api/leave/approvals", None),
        ("GET", "/api/leave/ledger?employee_id=" + env.eB1["id"], None), ("GET", "/api/leave/dashboard", None),
        ("POST", "/api/leave/balances/adjust", {}), ("POST", f"/api/leave/requests/{rid}/approvals/{rid}/decide", {"decision": "approved"}),
        ("GET", "/api/overtime/requests", None), ("GET", "/api/overtime/approvals", None),
        ("POST", f"/api/overtime/requests/{rid}/approvals/{rid}/decide", {"decision": "approved"}),
        # Payroll
        ("GET", "/api/payroll/components", None), ("GET", "/api/payroll/runs", None), ("GET", "/api/payroll/salaries", None),
        ("GET", f"/api/payroll/salaries/{env.eA1['id']}", None), ("GET", "/api/payroll/summary", None), ("POST", "/api/payroll/runs", {}),
        # Recruitment (termasuk approval operasional kandidat)
        ("GET", "/api/recruitment/candidates", None), ("GET", f"/api/recruitment/candidates/{rid}", None),
        ("POST", "/api/recruitment/candidates", {}), ("GET", "/api/recruitment/interviewers", None),
        ("POST", f"/api/recruitment/candidates/{rid}/approvals/{rid}/decide", {"decision": "approved"}),
        # Audit Logs + digest pengingat tenant-wide
        ("GET", "/api/audit-logs", None), ("GET", "/api/mail/reminder/preview", None),
    ]
    for method, path, body in cases:
        rr = await env.c.request(method, path, headers=env.rops, json=body)
        ra = await env.c.request(method, path, headers=env.aops, json=body)
        check(f"fail-closed {method} {path.split('?')[0]}: restricted 403 / ALL_TENANT bukan 403",
              rr.status_code == 403 and "Cakupan Data" in rr.text and ra.status_code != 403, f"r={rr.status_code} a={ra.status_code}")
    # Approval Workflow = konfigurasi company-level -> tetap RBAC (tidak diblokir karena scope)
    r = await env.c.get("/api/approval-workflows", headers=env.rops)
    check("Approval Workflow (konfigurasi company-level) tetap RBAC untuk restricted -> 200", r.status_code == 200, str(r.status_code))
    # Endpoint mandiri (milik sendiri) tetap tersedia untuk restricted
    for path in ("/api/attendance/me/today", "/api/attendance/me", "/api/attendance/corrections?mine=true",
                 "/api/leave/requests?mine=true", "/api/leave/balances?mine=true", "/api/overtime/requests?mine=true",
                 "/api/time/leave-types", "/api/payroll/my/payslips"):
        r = await env.c.get(path, headers=env.rops)
        check(f"self-service tetap tersedia untuk restricted: GET {path}", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
    r = await env.c.get("/api/leave/requests?mine=true", headers=env.rops)
    check("self-service mine=true: tidak memuat pengajuan karyawan lain", r.status_code == 200 and r.json().get("total") == 0)
    # Mengajukan untuk karyawan LAIN (cabang HR) tetap 403 untuk restricted walau endpoint self-service
    lt = {"id": new_id(), "company_id": env.cid, "status": "active", "code": f"L{RUN}", "name": f"Cuti Uji {MARK}",
          "category": "annual", "deduct_balance": False, "created_at": now(), "updated_at": now()}
    await env.tdb.leave_types.insert_one(dict(lt))
    body = {"leave_type_id": lt["id"], "start_date": SOON, "end_date": SOON, "reason": "uji 01I", "employee_id": env.eA1["id"]}
    r = await env.c.post("/api/leave/requests", headers=env.rops, json=body)
    check("cuti untuk karyawan lain oleh restricted -> 403 (bahkan karyawan dalam scope)", r.status_code == 403 and "Cakupan Data" in r.text,
          f"{r.status_code} {r.text[:120]}")
    body = {"work_date": date.today().isoformat(), "planned_start_time": "18:00", "planned_end_time": "19:00",
            "reason": "uji 01I", "employee_id": env.eA1["id"]}
    r = await env.c.post("/api/overtime/requests", headers=env.rops, json=body)
    check("lembur untuk karyawan lain oleh restricted -> 403", r.status_code == 403 and "Cakupan Data" in r.text, f"{r.status_code} {r.text[:120]}")
    r = await env.c.post(f"/api/leave/requests/{rid}/cancel", headers=env.rops, json={"reason": "uji 01I"})
    check("batalkan cuti yang tidak ada/bukan milik sendiri oleh restricted -> 404/403 (tidak 200)", r.status_code in (403, 404), str(r.status_code))
    for label, path in (("users", "/api/users"), ("employees", "/api/employees"), ("master projects", "/api/master/projects")):
        r = await env.c.get(path, headers=env.rops)
        check(f"Core HR tetap dapat diakses restricted ({label})", r.status_code == 200, str(r.status_code))


async def t_revoke_readd(env):
    """Keputusan 01I: revoke -> scope+item company tsb dibersihkan (tombstone), company lain utuh. Re-add ->
    SELECTED_PROJECTS kosong ("Tidak ada akses data") -> 0 karyawan -> admin set scope -> akses baru aktif."""
    db = get_db()
    r = await put_scope(env, env.rev_id, DS.SELECTED_PROJECTS, [env.pa["id"]])
    await db.user_company_roles.insert_one({"id": new_id(), "company_id": env.cid_b, "status": "active", "user_id": env.rev_id,
                                            "role_key": "hr_admin", "created_at": now(), "updated_at": now()})
    await DS.set_user_scope(env.cid_b, env.rev_id, DS.SELECTED_PROJECTS, [env.px["id"]], env.admin_id)
    check("revoke: setup scope A=[P_A] & B=[P_X]", r.status_code == 200)
    r = await env.c.delete(f"/api/users/{env.rev_id}", headers=env.admin)
    check("revoke akses company A -> 200", r.status_code == 200, r.text[:150])
    a_row = await db.user_data_scopes.find_one({"company_id": env.cid, "user_id": env.rev_id}, {"_id": 0})
    a_it = await db.user_data_scope_items.count_documents({"company_id": env.cid, "user_id": env.rev_id})
    b_sc = await db.user_data_scopes.count_documents({"company_id": env.cid_b, "user_id": env.rev_id, "status": "active"})
    b_it = await db.user_data_scope_items.count_documents({"company_id": env.cid_b, "user_id": env.rev_id, "status": "active"})
    check("revoke: item company A dihapus & scope dinonaktifkan (tombstone revoked, fail-closed)",
          a_it == 0 and a_row is not None and a_row["status"] == DS.REVOKED and a_row["mode"] == DS.SELECTED_PROJECTS,
          f"{a_row and (a_row.get('status'), a_row.get('mode'))} items={a_it}")
    s_rev = await DS.compute_scope(env.cid, env.rev_id, ["hr_admin"])
    check("revoke: scope efektif company A = tanpa akses (tidak jatuh ke ALL_TENANT)", s_rev.has_no_access)
    check("revoke: scope company B TIDAK disentuh", b_sc == 1 and b_it == 1, f"{b_sc} {b_it}")
    r = await env.c.get("/api/employees", headers=env.rev)
    check("revoke: token lama di company A ditolak (bukan anggota)", r.status_code == 403, str(r.status_code))
    r = await env.c.post(f"/api/users/{env.rev_id}/grant-company-access", headers=env.platform,
                         json={"company_id": env.cid, "role_keys": ["hr_admin"]})
    check("re-add akses company A oleh Platform Admin -> 200", r.status_code == 200, r.text[:150])
    row = await db.user_data_scopes.find_one({"company_id": env.cid, "user_id": env.rev_id}, {"_id": 0})
    items = await db.user_data_scope_items.count_documents({"company_id": env.cid, "user_id": env.rev_id})
    sa_ = await DS.compute_scope(env.cid, env.rev_id, ["hr_admin"])
    check("re-add: SELECTED_PROJECTS kosong (bukan ALL_TENANT, tidak mewarisi P_A)",
          row is not None and row["status"] == "active" and row["mode"] == DS.SELECTED_PROJECTS and items == 0
          and sa_.has_no_access, f"{row and (row.get('status'), row.get('mode'))} items={items}")
    code, got, total = await names(env, env.rev)
    check("re-add: 0 karyawan terlihat", code == 200 and not got and total == 0, f"{code} {got} {total}")
    me = (await env.c.get("/api/users/me/data-scope", headers=env.rev)).json()
    check("re-add: indikator UI = Tidak ada akses data", me.get("no_access") is True and me.get("effective_mode") == DS.SELECTED_PROJECTS)
    r = await env.c.get("/api/users", headers=env.admin, params={"q": f"{RUN.lower()}", "limit": 100})
    lab = {u["id"]: u for u in r.json().get("items", [])}.get(env.rev_id, {}).get("data_scope", {})
    check("re-add: kolom Cakupan daftar pengguna = Tidak ada akses", lab.get("no_access") is True, str(lab)[:150])
    r = await put_scope(env, env.rev_id, DS.SELECTED_PROJECTS, [env.pb["id"]])
    code, got, _ = await names(env, env.rev)
    # catatan: A2 sudah ditransfer ke P_B pada t_transfer -> karyawan P_B = {B1, A2}
    check("re-add: admin set scope [P_B] -> akses baru aktif (hanya karyawan P_B: B1, A2)",
          r.status_code == 200 and got == {"B1", "A2"}, f"{r.status_code} {got}")
    sb_ = await DS.compute_scope(env.cid_b, env.rev_id, ["hr_admin"])
    check("re-add: scope company B tetap [P_X]", sb_.project_ids == {env.px["id"]})
    # jalur re-add ke-2: Platform Admin menambah peran dari Tenant Detail -> juga tanpa akses data
    await env.c.delete(f"/api/users/{env.rev_id}", headers=env.admin)
    email = (await db.users.find_one({"id": env.rev_id}, {"_id": 0, "email": 1}))["email"]
    r = await env.c.post(f"/api/platform/tenants/{env.cid}/users", headers=env.platform,
                         json={"email": email, "role_key": "hr_admin"})
    s2 = await DS.compute_scope(env.cid, env.rev_id, ["hr_admin"])
    it2 = await db.user_data_scope_items.count_documents({"company_id": env.cid, "user_id": env.rev_id})
    check("re-add via Platform Tenant Detail -> SELECTED_PROJECTS kosong (tanpa warisan P_B)",
          r.status_code in (200, 201) and s2.mode == DS.SELECTED_PROJECTS and s2.has_no_access and it2 == 0, f"{r.status_code} {s2.mode} {it2}")
    # revoke via Platform (cabut Tenant Admin, tanpa keanggotaan tersisa) juga membersihkan scope
    await _raw_scope(env.cid, env.ta_id, DS.SELECTED_PROJECTS, [env.pa["id"]])
    r = await env.c.delete(f"/api/platform/tenants/{env.cid}/admins/{env.ta_id}", headers=env.platform)
    row = await db.user_data_scopes.find_one({"company_id": env.cid, "user_id": env.ta_id}, {"_id": 0})
    left_i = await db.user_data_scope_items.count_documents({"company_id": env.cid, "user_id": env.ta_id})
    check("platform cabut Tenant Admin (keanggotaan habis) -> item dihapus + scope revoked",
          r.status_code == 200 and left_i == 0 and row and row["status"] == DS.REVOKED, f"{r.status_code} {row and row.get('status')} {left_i}")


async def main():
    env = Env()
    clean_ok = False
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://t01i") as c:
        env.c = c
        try:
            await setup(env)
            for t in (t_scope_api, t_all_tenant, t_selected, t_direct_uuid, t_related, t_empty_invalid, t_standby,
                      t_supervisor_out_of_scope, t_transfer, t_scope_change_immediate, t_hr_verification, t_full_scope_ops,
                      t_unscoped_modules, t_revoke_readd, t_engine_sql):
                try:
                    await t(env)
                except Exception as exc:  # noqa: BLE001
                    import traceback
                    traceback.print_exc()
                    check(f"{t.__name__} (exception)", False, repr(exc)[:200])
        finally:
            clean_ok = await cleanup(env)
    await dbm.close_db()
    check("cleanup data uji 01I tuntas", clean_ok)
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n== 01I targeted: {len(RESULTS) - len(failed)}/{len(RESULTS)} PASS ==")
    return failed


def test_data_scope_01i():
    assert not asyncio.run(main())


if __name__ == "__main__":
    sys.exit(1 if asyncio.run(main()) else 0)
