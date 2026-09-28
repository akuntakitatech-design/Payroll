"""Phase 2A CP1 - Manajemen Aset: test backend terarah.

CARA MENJALANKAN (hanya MariaDB development LOKAL `hris_dev`):
    cd backend && bash tests/dev_env_run.sh python3 tests/test_asset_cp1.py
    (atau: bash tests/dev_env_run.sh python3 -m pytest tests/test_asset_cp1.py -q)

KEAMANAN TEST
- Guard: APP_ENV=development + host DB loopback + nama DB `hris_dev` + READ_ONLY=false + tanpa kredensial R2.
- App in-process (httpx ASGITransport); tidak ada panggilan object storage.
- Dua tenant uji baru (penanda unik per-run TAST-<RUN>) dibuat lalu DIBERSIHKAN di akhir. Tenant existing tidak diubah.
- Password akun uji acak per-run di memori, tidak ditulis ke file/log.
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import re
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
        raise SystemExit("DITOLAK: test CP1 aset hanya boleh berjalan pada MariaDB development lokal (hris_dev).")
    if (os.environ.get("READ_ONLY") or "").lower() in ("1", "true", "yes") or os.environ.get("R2_ACCESS_KEY_ID"):
        raise SystemExit("DITOLAK: READ_ONLY aktif atau kredensial R2 terpasang.")


_guard()

import httpx  # noqa: E402
import sqlalchemy as sa  # noqa: E402

import server  # noqa: E402
from app.core import data_scope as DS  # noqa: E402
from app.core import db as dbm  # noqa: E402
from app.core.db import get_db, new_id, now  # noqa: E402
from app.core.security import hash_password  # noqa: E402

RUN = secrets.token_hex(3).upper()
MARK = f"TAST-{RUN}"
RESULTS: list = []
AUTO_RE = re.compile(r"^AST-\d{6}$")
GA_ADMIN_EXPECTED = {"asset:view", "asset:create", "asset:edit", "asset:delete", "asset_value:view", "asset_value:edit",
                     "asset_master:view", "asset_master:create", "asset_master:edit", "asset_master:delete"}
GA_STAFF_EXPECTED = {"asset:view", "asset:create", "asset:edit", "asset_master:view"}
CP1_RESOURCES = {"asset", "asset_value", "asset_master"}


def check(name: str, cond: bool, info: str = "") -> None:
    RESULTS.append((name, bool(cond), info))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info and not cond else ""))


class Env:
    pass


# ------------------------------------------------------------------ fixture
async def _mk_company(env, suffix):
    doc = {"id": new_id(), "code": f"TA{suffix}{RUN}"[:10], "name": f"PT Uji Aset {suffix} {MARK}", "status": "active",
           "created_at": now(), "updated_at": now()}
    await get_db().companies.insert_one(dict(doc))
    env.company_ids.append(doc["id"])
    return doc["id"]


async def _mk_user(env, role_key, company_id, label):
    db = get_db()
    email = f"tast.{label}.{RUN.lower()}@kelolakita.dev"
    pw = "Tast-" + secrets.token_urlsafe(12)
    uid = new_id()
    await db.users.insert_one({"id": uid, "company_id": None, "status": "active", "email": email, "full_name": f"TAST {label}",
                               "password_hash": hash_password(pw), "default_company_id": company_id,
                               "must_change_password": False, "is_demo_account": False, "created_at": now(), "updated_at": now()})
    await db.user_company_roles.insert_one({"id": new_id(), "company_id": company_id, "status": "active", "user_id": uid,
                                            "role_key": role_key, "created_at": now(), "updated_at": now()})
    env.user_ids.append(uid)
    r = await env.c.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return uid, {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _mk_ref(env, coll, cid, code):
    doc = {"id": new_id(), "company_id": cid, "status": "active", "code": f"{code}{RUN}"[:20], "name": f"{code} {MARK}",
           "created_at": now(), "updated_at": now()}
    await get_db()[coll].insert_one(dict(doc))
    env.refs.append((coll, doc["id"]))
    return doc["id"]


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
    env.company_ids, env.user_ids, env.refs, env.roles = [], [], [], []
    env.cid = await _mk_company(env, "A")
    env.cid_b = await _mk_company(env, "B")
    env.pa1, env.pa2, env.pa3 = [await _mk_ref(env, "projects", env.cid, c) for c in ("PA1", "PA2", "PA3")]
    env.pb1 = await _mk_ref(env, "projects", env.cid_b, "PB1")
    env.wa = await _mk_ref(env, "work_locations", env.cid, "WA")
    env.wa2 = await _mk_ref(env, "work_locations", env.cid, "WA2")
    env.wb = await _mk_ref(env, "work_locations", env.cid_b, "WB")
    env.admin_id, env.admin = await _mk_user(env, "tenant_admin", env.cid, "admin")
    env.adminb_id, env.adminb = await _mk_user(env, "tenant_admin", env.cid_b, "adminb")
    env.ga_id, env.ga = await _mk_user(env, "ga_admin", env.cid, "gaadmin")        # tanpa baris scope -> ALL_TENANT
    env.gs_id, env.gs = await _mk_user(env, "ga_staff", env.cid, "gastaff")
    env.hr_id, env.hr = await _mk_user(env, "hr_admin", env.cid, "hradmin")
    env.emp_id, env.emp = await _mk_user(env, "employee", env.cid, "employee")
    env.ra_id, env.ra = await _mk_user(env, "ga_admin", env.cid, "ra")
    env.rab_id, env.rab = await _mk_user(env, "ga_admin", env.cid, "rab")
    env.re_id, env.re = await _mk_user(env, "ga_admin", env.cid, "rempty")
    await _raw_scope(env.cid, env.ra_id, DS.SELECTED_PROJECTS, [env.pa1])
    await _raw_scope(env.cid, env.rab_id, DS.SELECTED_PROJECTS, [env.pa1, env.pa2])
    await _raw_scope(env.cid, env.re_id, DS.SELECTED_PROJECTS, [])


async def cleanup(env) -> bool:
    eng = dbm.get_engine()
    cids = env.company_ids
    uids = env.user_ids
    async with eng.begin() as conn:
        async def d(sql, **p):
            stmt = sa.text(sql)
            for k, v in p.items():
                if isinstance(v, (list, tuple)):
                    stmt = stmt.bindparams(sa.bindparam(k, expanding=True))
            await conn.execute(stmt, p)
        for t in ("assets", "asset_events", "asset_categories", "asset_units", "asset_conditions", "asset_statuses",
                  "document_sequence_configs", "document_sequence_counters", "company_modules", "audit_logs",
                  "user_data_scope_items", "user_data_scopes", "user_company_roles", "projects", "work_locations",
                  "company_settings"):
            await d(f"DELETE FROM {t} WHERE company_id IN :c", c=cids)
        await d("DELETE FROM audit_logs WHERE user_id IN :u", u=uids)
        await d("DELETE FROM user_company_roles WHERE user_id IN :u", u=uids)
        await d("DELETE FROM users WHERE id IN :u", u=uids)
        for rk in env.roles:
            await d("DELETE FROM role_permissions WHERE role_key = :r", r=rk)
            await d("DELETE FROM roles WHERE `key` = :r", r=rk)
        await d("DELETE FROM companies WHERE id IN :c", c=cids)
    db = get_db()
    left = 0
    for t in ("assets", "asset_events", "asset_categories", "asset_statuses", "document_sequence_counters", "projects", "audit_logs"):
        left += await db[t].count_documents({"company_id": {"$in": cids}})
    left += await db.users.count_documents({"id": {"$in": uids}}) + await db.companies.count_documents({"id": {"$in": cids}})
    return left == 0


# ------------------------------------------------------------------ helpers
async def opts(env, h):
    r = await env.c.get("/api/assets/form-options", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def by_code(items, code):
    return next(i for i in items if i["code"] == code)


async def create(env, h, **kw):
    return await env.c.post("/api/assets", json=kw, headers=h)


# ------------------------------------------------------------------ tests
async def t_module_activation(env):
    c = env.c
    r = await c.get("/api/assets", headers=env.admin)
    check("modul nonaktif: GET /api/assets -> 403", r.status_code == 403, str(r.status_code))
    r = await c.get("/api/master/asset-categories", headers=env.admin)
    check("modul nonaktif: master aset -> 403", r.status_code == 403, str(r.status_code))
    me = (await c.get("/api/auth/me", headers=env.ga)).json()
    check("modul nonaktif: /auth/me tanpa modul asset", "asset" not in me.get("modules", []))
    for cid, h in ((env.cid, env.admin), (env.cid_b, env.adminb)):
        r = await c.put("/api/modules/toggle", json={"module_key": "asset", "is_active": True}, headers=h)
        check(f"aktivasi modul asset ({'A' if cid == env.cid else 'B'}) -> 200", r.status_code == 200, r.text[:200])
    db = get_db()
    counts = {t: await db[t].count_documents({"company_id": env.cid}) for t in ("asset_categories", "asset_units", "asset_conditions", "asset_statuses")}
    check("seed default: 7 kategori, 6 satuan, 5 kondisi, 7 status", counts == {"asset_categories": 7, "asset_units": 6,
                                                                                "asset_conditions": 5, "asset_statuses": 7}, str(counts))
    await c.put("/api/modules/toggle", json={"module_key": "asset", "is_active": False}, headers=env.admin)
    r = await c.get("/api/assets", headers=env.ga)
    check("modul dinonaktifkan lagi -> GA Admin 403", r.status_code == 403, str(r.status_code))
    await c.put("/api/modules/toggle", json={"module_key": "asset", "is_active": True}, headers=env.admin)
    counts2 = {t: await db[t].count_documents({"company_id": env.cid}) for t in counts}
    check("aktivasi ulang: seed idempoten (tanpa duplikat)", counts2 == counts, str(counts2))
    me = (await c.get("/api/auth/me", headers=env.ga)).json()
    check("modul aktif: /auth/me memuat modul asset + izin aset GA Admin",
          "asset" in me.get("modules", []) and GA_ADMIN_EXPECTED <= set(me.get("permissions", [])))
    for st in ["READY", "IN_USE", "PENDING_INSPECTION", "MAINTENANCE", "DAMAGED", "LOST", "DISPOSED"]:
        n = await db.asset_statuses.count_documents({"company_id": env.cid, "system_state": st, "is_default": True, "status": "active"})
        if n != 1:
            check(f"seed: tepat 1 default aktif untuk {st}", False, str(n))
            return
    check("seed: tiap kategori sistem punya tepat 1 status default aktif", True)
    cfg = await db.document_sequence_configs.find_one({"company_id": env.cid, "sequence_key": "ASSET_CODE"}, {"_id": 0})
    check("konfigurasi kode aset default = AST-{SEQ:6} (NEVER)", cfg and cfg["format"] == "AST-{SEQ:6}" and cfg["reset_policy"] == "NEVER")
    env.o = await opts(env, env.ga)
    env.cat_laptop = by_code(env.o["categories"], "LAPTOP")
    env.cat_alat = by_code(env.o["categories"], "ALAT")
    env.unit = by_code(env.o["units"], "UNIT")
    env.cond_baik = by_code(env.o["conditions"], "BAIK")
    env.st = {s["code"]: s for s in env.o["statuses"]}


async def t_rbac_presets(env):
    db = get_db()
    for rk, exp in (("ga_admin", GA_ADMIN_EXPECTED), ("ga_staff", GA_STAFF_EXPECTED)):
        have = {p["permission_key"] for p in await db.role_permissions.find({"role_key": rk}, {"_id": 0}).to_list(500)}
        # CP2 menambah resource siklus (asset_handover/return/inspection/bast; diuji exact di test_asset_cp2.py);
        # matriks resource CP1 tetap harus identik.
        cp1 = {k for k in have if k.split(":")[0] in CP1_RESOURCES}
        check(f"preset {rk}: izin aset sesuai matriks", cp1 == exp, str(sorted(cp1)))
    role = await db.roles.find_one({"key": "ga_staff"}, {"_id": 0})
    check("preset GA Staff/GA Admin adalah role sistem (is_system)", role and role.get("is_system") is True)
    c = env.c
    r = await c.get("/api/assets", headers=env.emp)
    check("RBAC: role Karyawan tanpa asset:view -> 403", r.status_code == 403, str(r.status_code))
    r = await c.get("/api/assets", headers=env.hr)
    check("RBAC: HR Admin (asset:view) -> list 200", r.status_code == 200, str(r.status_code))
    r = await create(env, env.hr, name=f"Uji HR {MARK}", category_id=env.cat_alat["id"])
    check("RBAC: HR Admin tanpa asset:create -> 403", r.status_code == 403, str(r.status_code))
    r = await create(env, env.gs, name=f"Bor {MARK}", category_id=env.cat_alat["id"], project_id=env.pa1)
    check("RBAC: GA Staff create -> 201", r.status_code == 201, r.text[:200])
    env.gs_asset = r.json()
    r = await c.delete(f"/api/assets/{env.gs_asset['id']}", headers=env.gs)
    check("RBAC: GA Staff tanpa asset:delete -> 403", r.status_code == 403, str(r.status_code))
    r = await c.post("/api/master/asset-units", json={"code": f"U{RUN}", "name": "Unit uji"}, headers=env.gs)
    check("RBAC: GA Staff tanpa asset_master:create -> 403", r.status_code == 403, str(r.status_code))
    r = await c.get("/api/master/asset-units", headers=env.gs)
    check("RBAC: GA Staff asset_master:view -> 200", r.status_code == 200, str(r.status_code))
    r = await create(env, env.gs, name=f"Bor2 {MARK}", category_id=env.cat_alat["id"], project_id=env.pa1, acquisition_value="1000")
    check("RBAC: GA Staff isi nilai perolehan tanpa asset_value:edit -> 403", r.status_code == 403, str(r.status_code))
    # role kustom "HRGA Admin" dengan izin identik GA Admin (lewat API matriks izin)
    rk = f"hrga_admin_{RUN.lower()}"
    env.roles.append(rk)
    r = await c.post("/api/roles", json={"key": rk, "name": f"HRGA Admin {MARK}"}, headers=env.admin)
    check("role kustom HRGA Admin dibuat tenant admin -> 201", r.status_code == 201, r.text[:200])
    ga_keys = sorted({p["permission_key"] for p in await db.role_permissions.find({"role_key": "ga_admin"}, {"_id": 0}).to_list(500)})
    r = await c.put(f"/api/roles/{rk}/permissions", json={"permission_keys": ga_keys}, headers=env.admin)
    check("role kustom HRGA Admin diberi izin = GA Admin -> 200", r.status_code == 200, r.text[:200])
    env.hrga_id, env.hrga = await _mk_user(env, rk, env.cid, "hrga")
    outcomes = {}
    for label, h in (("ga", env.ga), ("hrga", env.hrga)):
        r1 = await create(env, h, name=f"Laptop {label} {MARK}", category_id=env.cat_laptop["id"], serial_number=f"SN-{label}-{RUN}",
                          project_id=env.pa2, acquisition_value="7500000.25")
        aid = r1.json().get("id")
        r2 = await c.get(f"/api/assets/{aid}", headers=h)
        r3 = await c.put(f"/api/assets/{aid}", json={"brand": "Lenovo", "acquisition_value": "7600000.00"}, headers=h)
        r4 = await c.post("/api/master/asset-units", json={"code": f"{label.upper()}{RUN}", "name": f"Unit {label}"}, headers=h)
        r5 = await c.delete(f"/api/assets/{aid}", headers=h)
        outcomes[label] = (r1.status_code, r2.status_code, r2.json().get("acquisition_value"), r3.status_code,
                           r4.status_code, r5.status_code)
    check("role kustom HRGA Admin berperilaku identik GA Admin (tanpa cek nama role)",
          outcomes["ga"][:2] == outcomes["hrga"][:2] and outcomes["ga"][3:] == outcomes["hrga"][3:] == (200, 201, 200)
          and outcomes["ga"][0] == 201 and outcomes["hrga"][2] == "7500000.25", str(outcomes))


async def t_masters(env):
    c = env.c
    r = await c.post("/api/master/asset-categories", json={"code": f"C{RUN}", "name": f"Server {MARK}", "code_prefix": "SRV",
                                                          "serial_number_required": True, "default_unit_id": env.unit["id"]}, headers=env.ga)
    check("master kategori: buat dengan serial_number_required -> 201", r.status_code == 201 and r.json().get("serial_number_required") is True, r.text[:200])
    r = await c.post("/api/master/asset-categories", json={"code": f"CX{RUN}", "name": "X", "default_unit_id": new_id()}, headers=env.ga)
    check("master kategori: satuan default tenant lain/tidak ada -> 422", r.status_code == 422, str(r.status_code))
    r = await c.post("/api/master/asset-statuses", json={"code": f"S{RUN}", "name": "Salah", "system_state": "BORROWED"}, headers=env.ga)
    check("master status: kategori sistem di luar 7 nilai tetap -> 422", r.status_code == 422, str(r.status_code))
    ready = env.st["READY"]
    r = await c.patch(f"/api/master/asset-statuses/{ready['id']}/status", json={"status": "inactive"}, headers=env.ga)
    check("master status: nonaktifkan status default -> 422", r.status_code == 422, str(r.status_code))
    r = await c.delete(f"/api/master/asset-statuses/{env.st['LOST']['id']}", headers=env.ga)
    check("master status: hapus status default/terakhir kategori sistem -> 422", r.status_code == 422, str(r.status_code))
    r = await c.put(f"/api/master/asset-statuses/{ready['id']}", json={"is_default": False}, headers=env.ga)
    check("master status: lepas default tanpa pengganti -> 422", r.status_code == 422, str(r.status_code))
    r = await c.put(f"/api/master/asset-statuses/{ready['id']}", json={"status": "inactive"}, headers=env.ga)
    check("master status: nonaktifkan default lewat PUT juga ditolak -> 422", r.status_code == 422, str(r.status_code))
    r = await c.post("/api/master/asset-statuses", json={"code": f"GUDANG{RUN}", "name": "Di Gudang", "system_state": "READY",
                                                        "is_default": True, "color": "success"}, headers=env.ga)
    check("master status: label tenant baru untuk READY sebagai default -> 201", r.status_code == 201, r.text[:200])
    env.st_gudang = r.json()
    db = get_db()
    n = await db.asset_statuses.count_documents({"company_id": env.cid, "system_state": "READY", "is_default": True})
    old = await db.asset_statuses.find_one({"id": ready["id"]}, {"_id": 0})
    check("master status: default lama otomatis dilepas (tepat 1 default READY)", n == 1 and old["is_default"] is False, str(n))
    r = await c.put(f"/api/master/asset-statuses/{env.gs_asset['status_id']}", json={"system_state": "DAMAGED"}, headers=env.ga)
    check("master status: ubah kategori sistem status yang dipakai aset -> 409", r.status_code == 409, str(r.status_code))
    r = await c.put(f"/api/master/asset-statuses/{env.st_gudang['id']}", json={"name": "Gudang Pusat"}, headers=env.ga)
    check("master status: ganti label (nama) diperbolehkan -> 200", r.status_code == 200, str(r.status_code))
    r = await c.post("/api/master/asset-units", json={"code": f"PAL{RUN}", "name": "Palet"}, headers=env.ga)
    ok = r.status_code == 201
    r = await c.post("/api/master/asset-units", json={"code": f"pal{RUN}", "name": "Palet 2"}, headers=env.ga)
    check("master satuan: kode unik per company (case-insensitive) -> 409 pada duplikat", ok and r.status_code == 409, str(r.status_code))
    r = await c.post("/api/master/asset-units", json={"code": f"PAL{RUN}", "name": "Palet"}, headers=env.adminb)
    check("master satuan: kode sama di tenant lain boleh -> 201", r.status_code == 201, str(r.status_code))
    audit = await db.audit_logs.count_documents({"company_id": env.cid, "resource": "asset_master"})
    check("audit log: perubahan master aset tercatat (resource asset_master)", audit >= 4, str(audit))
    env.o = await opts(env, env.ga)
    env.st = {s["code"]: s for s in env.o["statuses"]}


async def t_crud_identity(env):
    c = env.c
    r = await create(env, env.ga, name=f"Meja {MARK}", category_id=env.cat_alat["id"], project_id=env.pa1, work_location_id=env.wa)
    a = r.json()
    check("create kode kosong -> kode otomatis format AST-000000", r.status_code == 201 and AUTO_RE.match(a.get("asset_code") or ""), r.text[:200])
    check("create: satuan default dari kategori + kondisi default Baik + status default READY",
          a.get("unit_id") == env.cat_alat["default_unit_id"] and a.get("condition_id") == env.cond_baik["id"]
          and a.get("lifecycle_state") == "READY" and a.get("status_id") == env.st_gudang["id"], str(a)[:300])
    check("create: tidak ada field kuantitas pada aset (1 kode = 1 unit)", "quantity" not in a and "qty" not in a)
    r = await create(env, env.ga, asset_code=f"  inv-{RUN}-001 ", name=f"Kursi {MARK}", category_id=env.cat_alat["id"], project_id=env.pa1)
    check("create kode manual -> disimpan (trim) + 201", r.status_code == 201 and r.json()["asset_code"] == f"inv-{RUN}-001", r.text[:200])
    env.manual = r.json()
    r = await create(env, env.ga, asset_code=f"INV-{RUN}-001", name="Duplikat", category_id=env.cat_alat["id"], project_id=env.pa1)
    check("kode manual duplikat (beda huruf besar/kecil) di company sama -> 409", r.status_code == 409, str(r.status_code))
    ob = await opts(env, env.adminb)
    r = await create(env, env.adminb, asset_code=f"INV-{RUN}-001", name="Tenant B", category_id=by_code(ob["categories"], "ALAT")["id"])
    check("kode sama di tenant lain -> 201", r.status_code == 201, r.text[:200])
    env.asset_b = r.json()
    r = await create(env, env.ga, name=f"Laptop X {MARK}", category_id=env.cat_laptop["id"], project_id=env.pa1)
    check("kategori wajib SN tanpa serial -> 422", r.status_code == 422, str(r.status_code))
    r = await create(env, env.ga, name=f"Laptop A {MARK}", category_id=env.cat_laptop["id"], project_id=env.pa1, serial_number=f"ab 12-{RUN}")
    check("kategori wajib SN dengan serial -> 201", r.status_code == 201, r.text[:200])
    env.laptop = r.json()
    r = await create(env, env.ga, name="Dup SN", category_id=env.cat_laptop["id"], project_id=env.pa1, serial_number=f"AB12-{RUN}")
    check("serial duplikat (normalisasi spasi/huruf) di company sama -> 409", r.status_code == 409, str(r.status_code))
    r = await create(env, env.adminb, name="SN tenant B", category_id=by_code(ob["categories"], "LAPTOP")["id"], serial_number=f"AB12-{RUN}")
    check("serial sama di tenant lain tidak konflik -> 201", r.status_code == 201, r.text[:200])
    # Kontrak default numbering: create otomatis pertama di company baru (tenant B) = AST-000001 (sequence mulai 1, per company).
    check("company baru: kode otomatis pertama = AST-000001", r.status_code == 201 and r.json().get("asset_code") == "AST-000001",
          r.text[:200])
    r = await create(env, env.ga, name=f"Palu {MARK}", category_id=env.cat_alat["id"], project_id=env.pa1)
    r2 = await create(env, env.ga, name=f"Palu2 {MARK}", category_id=env.cat_alat["id"], project_id=env.pa1)
    check("serial kosong boleh berganda (kategori tanpa wajib SN)", r.status_code == 201 and r2.status_code == 201)
    r = await create(env, env.ga, name="In use", category_id=env.cat_alat["id"], project_id=env.pa1, status_id=env.st["IN_USE"]["id"])
    check("status berkategori IN_USE tidak bisa dipilih manual saat create -> 422", r.status_code == 422, str(r.status_code))
    r = await create(env, env.ga, name="Pending", category_id=env.cat_alat["id"], project_id=env.pa1, status_id=env.st["PENDING_INSPECTION"]["id"])
    check("status berkategori PENDING_INSPECTION tidak bisa dipilih manual -> 422", r.status_code == 422, str(r.status_code))
    r = await create(env, env.ga, name="Qty", category_id=env.cat_alat["id"], project_id=env.pa1, quantity=5)
    check("field tak dikenal (quantity) ditolak -> 422", r.status_code == 422, str(r.status_code))
    # tanggal / tahun perolehan
    r = await create(env, env.ga, name="Tgl", category_id=env.cat_alat["id"], project_id=env.pa1, acquisition_date="2023-05-01", acquisition_year=2022)
    check("tanggal & tahun perolehan tidak konsisten -> 422", r.status_code == 422, str(r.status_code))
    r = await create(env, env.ga, name=f"Thn {MARK}", category_id=env.cat_alat["id"], project_id=env.pa1, acquisition_year=2020)
    check("tahun perolehan tanpa tanggal -> 201", r.status_code == 201 and r.json().get("acquisition_year") == 2020, r.text[:200])
    r = await create(env, env.ga, name=f"Tgl2 {MARK}", category_id=env.cat_alat["id"], project_id=env.pa1, acquisition_date="2021-03-04")
    t2 = r.json()
    check("tanggal perolehan -> tahun otomatis mengikuti", r.status_code == 201 and t2.get("acquisition_year") == 2021, r.text[:200])
    r = await c.put(f"/api/assets/{t2['id']}", json={"acquisition_date": None}, headers=env.ga)
    check("tanggal dikosongkan -> tahun TIDAK ikut terhapus", r.status_code == 200 and r.json().get("acquisition_date") is None
          and r.json().get("acquisition_year") == 2021, r.text[:200])
    r = await create(env, env.ga, name="Future", category_id=env.cat_alat["id"], project_id=env.pa1, acquisition_date="2999-01-01")
    check("tanggal perolehan di masa depan -> 422", r.status_code == 422, str(r.status_code))
    # validasi project / lokasi tenant-safe
    r = await create(env, env.ga, name="PB", category_id=env.cat_alat["id"], project_id=env.pb1)
    check("project milik tenant lain -> 422", r.status_code == 422, str(r.status_code))
    r = await create(env, env.ga, name="WB", category_id=env.cat_alat["id"], project_id=env.pa1, work_location_id=env.wb)
    check("lokasi kerja milik tenant lain -> 422", r.status_code == 422, str(r.status_code))
    r = await create(env, env.ga, name="CatB", category_id=by_code(ob["categories"], "ALAT")["id"], project_id=env.pa1)
    check("kategori milik tenant lain -> 422", r.status_code == 422, str(r.status_code))
    r = await c.get(f"/api/assets/{env.asset_b['id']}", headers=env.ga)
    check("tenant isolation: UUID aset tenant lain -> 404", r.status_code == 404, str(r.status_code))
    r = await c.put(f"/api/assets/{env.asset_b['id']}", json={"name": "hack"}, headers=env.ga)
    check("tenant isolation: ubah aset tenant lain -> 404", r.status_code == 404, str(r.status_code))
    lst = (await c.get("/api/assets", params={"q": f"INV-{RUN}-001"}, headers=env.ga)).json()
    check("tenant isolation: list hanya aset company aktif", lst["total"] == 1 and lst["items"][0]["id"] == env.manual["id"], str(lst["total"]))
    # kode: bisa diubah hanya sebelum ada histori selain CREATED
    r = await c.put(f"/api/assets/{env.manual['id']}", json={"asset_code": f"INV-{RUN}-01A"}, headers=env.ga)
    check("ubah kode saat histori hanya CREATED -> 200", r.status_code == 200 and r.json()["asset_code"] == f"INV-{RUN}-01A", r.text[:200])
    r = await c.put(f"/api/assets/{env.manual['id']}", json={"asset_code": f"INV-{RUN}-01B"}, headers=env.ga)
    check("ubah kode setelah ada histori lain -> 409 (kode existing tidak berubah diam-diam)", r.status_code == 409, str(r.status_code))
    r = await c.put(f"/api/assets/{env.laptop['id']}", json={"asset_code": f"INV-{RUN}-01A"}, headers=env.ga)
    check("ubah kode ke kode yang sudah dipakai -> 409", r.status_code == 409, str(r.status_code))
    r = await c.put(f"/api/assets/{env.laptop['id']}", json={"project_id": env.pa2}, headers=env.ga)
    check("PUT tidak boleh mengubah project (wajib lewat Relokasi) -> 422", r.status_code == 422, str(r.status_code))
    r = await c.put(f"/api/assets/{env.laptop['id']}", json={"serial_number": ""}, headers=env.ga)
    check("mengosongkan serial pada kategori wajib SN -> 422", r.status_code == 422, str(r.status_code))


async def t_value(env):
    c, db = env.c, get_db()
    big = "1234567890123456.78"
    r = await create(env, env.ga, name=f"Genset {MARK}", category_id=env.cat_alat["id"], project_id=env.pa1, acquisition_value="15000000.5")
    a = r.json()
    check("nilai perolehan disimpan presisi 2 desimal (15000000.50)", r.status_code == 201 and a.get("acquisition_value") == "15000000.50", r.text[:200])
    env.valued = a
    r = await create(env, env.ga, name=f"Alat berat {MARK}", category_id=env.cat_alat["id"], project_id=env.pa1, acquisition_value=big)
    d = (await c.get(f"/api/assets/{r.json()['id']}", headers=env.ga)).json()
    check("round-trip DECIMAL(18,2) nilai besar tanpa kehilangan presisi", d.get("acquisition_value") == big, str(d.get("acquisition_value")))
    raw = await db.assets.find_one({"id": d["id"]}, {"_id": 0})
    from decimal import Decimal
    check("DB menyimpan Decimal (bukan float)", isinstance(raw["acquisition_value"], Decimal) and str(raw["acquisition_value"]) == big,
          type(raw["acquisition_value"]).__name__)
    for bad in ("12.345", "-1", "abc", "99999999999999999.00"):
        r = await create(env, env.ga, name="bad", category_id=env.cat_alat["id"], project_id=env.pa1, acquisition_value=bad)
        if r.status_code != 422:
            check(f"nilai perolehan tidak valid '{bad}' -> 422", False, str(r.status_code))
            break
    else:
        check("nilai perolehan tidak valid (>2 desimal / negatif / bukan angka / melebihi batas) -> 422", True)
    r = await c.get(f"/api/assets/{a['id']}", headers=env.gs)
    check("GA Staff (tanpa asset_value:view): detail TANPA key acquisition_value", r.status_code == 200 and "acquisition_value" not in r.json(), r.text[:200])
    r = await c.get(f"/api/assets/{a['id']}", headers=env.hr)
    check("HR Admin (tanpa asset_value:view): detail TANPA nilai", "acquisition_value" not in r.json())
    lst = (await c.get("/api/assets", headers=env.ga)).json()
    check("list tidak pernah menyertakan nilai perolehan (bahkan GA Admin)", all("acquisition_value" not in i for i in lst["items"]))
    lst = (await c.get("/api/assets", params={"q": "15000000"}, headers=env.gs)).json()
    check("pencarian tidak membocorkan nilai (q=nilai tidak mencocokkan)", lst["total"] == 0, str(lst["total"]))
    r = await c.put(f"/api/assets/{a['id']}", json={"acquisition_value": "1"}, headers=env.gs)
    check("GA Staff ubah nilai perolehan -> 403", r.status_code == 403, str(r.status_code))
    r = await c.put(f"/api/assets/{a['id']}", json={"name": f"Genset besar {MARK}"}, headers=env.gs)
    check("GA Staff ubah field lain -> 200 tanpa nilai di respons", r.status_code == 200 and "acquisition_value" not in r.json(), str(r.status_code))
    r = await c.put(f"/api/assets/{a['id']}", json={"acquisition_value": "16000000.00"}, headers=env.ga)
    check("GA Admin ubah nilai -> 200", r.status_code == 200 and r.json()["acquisition_value"] == "16000000.00", r.text[:200])
    _fin_id, fin = await _mk_user(env, "finance", env.cid, "finance")
    r = await c.get(f"/api/assets/{a['id']}", headers=fin)
    check("Finance (asset_value:view) melihat nilai", r.status_code == 200 and r.json().get("acquisition_value") == "16000000.00", r.text[:200])
    eng = dbm.get_engine()
    async with eng.connect() as conn:
        leak = (await conn.execute(sa.text(
            "SELECT COUNT(*) FROM audit_logs WHERE company_id = :c AND (CAST(before_value AS CHAR) LIKE '%15000000%' OR CAST(after_value AS CHAR) LIKE '%15000000%'"
            " OR CAST(after_value AS CHAR) LIKE '%16000000%' OR CAST(before_value AS CHAR) LIKE '%1234567890123456%' OR CAST(after_value AS CHAR) LIKE '%1234567890123456%'"
            " OR notes LIKE '%16000000%')"), {"c": env.cid})).scalar()
        ev_leak = (await conn.execute(sa.text(
            "SELECT COUNT(*) FROM asset_events WHERE company_id = :c AND (CAST(changes AS CHAR) LIKE '%16000000%' OR CAST(changes AS CHAR) LIKE '%15000000%')"),
            {"c": env.cid})).scalar()
    check("audit log & event TIDAK menyimpan nilai perolehan mentah", leak == 0 and ev_leak == 0, f"{leak}/{ev_leak}")
    upd = await db.audit_logs.find_one({"company_id": env.cid, "resource": "asset", "action": "update", "record_id": a["id"],
                                        "notes": {"$regex": "Nilai perolehan"}}, {"_id": 0})
    check("audit log mencatat PERUBAHAN nilai perolehan (tanpa angka)", bool(upd))


async def t_concurrency(env):
    db = get_db()
    ctr = await db.document_sequence_counters.find_one({"company_id": env.cid, "sequence_key": "ASSET_CODE"}, {"_id": 0})
    start = int(ctr["next_value"])
    # kode manual yang sama dengan kandidat otomatis berikutnya -> otomatis harus melewatinya
    taken = f"AST-{start:06d}"
    r = await create(env, env.ga, asset_code=taken, name=f"Manual bentrok {MARK}", category_id=env.cat_alat["id"], project_id=env.pa1)
    check("kode manual berpola AST-xxxxxx diterima", r.status_code == 201, r.text[:200])
    n = 12
    rs = await asyncio.gather(*[create(env, env.ga, name=f"Paralel {i} {MARK}", category_id=env.cat_alat["id"], project_id=env.pa1)
                                for i in range(n)])
    codes = [x.json().get("asset_code") for x in rs if x.status_code == 201]
    check(f"{n} create paralel -> semua 201", len(codes) == n, str([x.status_code for x in rs]))
    check("create paralel -> kode otomatis unik (tanpa duplikat)", len(set(codes)) == n and all(AUTO_RE.match(x) for x in codes), str(codes))
    check("kode otomatis melewati kode manual yang sudah dipakai", taken not in codes)
    ctr2 = await db.document_sequence_counters.find_one({"company_id": env.cid, "sequence_key": "ASSET_CODE"}, {"_id": 0})
    nums = sorted(int(x[4:]) for x in codes)
    check("counter maju tepat (tanpa gap selain kode yang dilewati)", int(ctr2["next_value"]) == start + n + 1 and nums == list(range(start + 1, start + n + 1)),
          f"{start} -> {ctr2['next_value']} {nums[:3]}")
    rows = await db.document_sequence_counters.count_documents({"company_id": env.cid, "sequence_key": "ASSET_CODE"})
    check("satu baris counter per company (tidak terduplikasi saat balapan)", rows == 1, str(rows))
    # tenant B memakai counter sendiri
    ob = await opts(env, env.adminb)
    ctr_b = await db.document_sequence_counters.find_one({"company_id": env.cid_b, "sequence_key": "ASSET_CODE"}, {"_id": 0})
    r = await create(env, env.adminb, name="B auto", category_id=by_code(ob["categories"], "ALAT")["id"])
    check("counter per company: tenant B memakai counter sendiri (tidak ikut counter A)",
          r.status_code == 201 and r.json()["asset_code"] == f"AST-{int(ctr_b['next_value']):06d}" and int(ctr_b["next_value"]) < start,
          r.text[:120])
    # concurrency lintas-company paralel
    rs = await asyncio.gather(*[create(env, h, name=f"X {i}", category_id=cat) for i, (h, cat) in enumerate(
        [(env.ga, env.cat_alat["id"])] * 3 + [(env.adminb, by_code(ob["categories"], "ALAT")["id"])] * 3)], return_exceptions=True)
    ok = [x for x in rs if not isinstance(x, Exception) and x.status_code == 201]
    check("create paralel lintas company -> tanpa error", len(ok) == 6, str([getattr(x, "status_code", x) for x in rs]))


async def t_scope(env):
    c = env.c
    env.a1 = (await create(env, env.ga, name=f"Scope PA1 {MARK}", category_id=env.cat_alat["id"], project_id=env.pa1)).json()
    env.a2 = (await create(env, env.ga, name=f"Scope PA2 {MARK}", category_id=env.cat_alat["id"], project_id=env.pa2)).json()
    env.a3 = (await create(env, env.ga, name=f"Scope PA3 {MARK}", category_id=env.cat_alat["id"], project_id=env.pa3)).json()
    r = await create(env, env.ga, name=f"Scope NONE {MARK}", category_id=env.cat_alat["id"])
    env.an = r.json()
    check("ALL_TENANT: create aset tanpa project -> 201", r.status_code == 201, r.text[:200])
    db = get_db()
    total_all = await db.assets.count_documents({"company_id": env.cid})
    by_p = {p: await db.assets.count_documents({"company_id": env.cid, "project_id": p}) for p in (env.pa1, env.pa2, env.pa3)}
    none_n = await db.assets.count_documents({"company_id": env.cid, "project_id": None})

    async def total(h, **params):
        r = await c.get("/api/assets", params={"limit": 100, **params}, headers=h)
        return r.json()["total"], r.json()["items"]

    t, _ = await total(env.ga)
    check("ALL_TENANT (GA Admin tanpa baris scope) melihat semua aset company", t == total_all, f"{t} vs {total_all}")
    t, _ = await total(env.admin)
    check("Tenant Admin melihat semua aset company", t == total_all)
    t, items = await total(env.ra)
    check("SELECTED_PROJECTS (1 project) hanya aset project tsb (count SQL)", t == by_p[env.pa1] and all(i["project_id"] == env.pa1 for i in items),
          f"{t} vs {by_p[env.pa1]}")
    t, items = await total(env.rab)
    check("SELECTED_PROJECTS multi-project hanya aset PA1+PA2", t == by_p[env.pa1] + by_p[env.pa2] and {i["project_id"] for i in items} <= {env.pa1, env.pa2})
    t, items = await total(env.re)
    check("restricted scope kosong -> 0 aset", t == 0 and items == [])
    check("aset tanpa project tidak terlihat oleh restricted", all(i["id"] != env.an["id"] for i in (await total(env.rab))[1]))
    t, _ = await total(env.ra, project_id="none")
    check("filter 'tanpa project' oleh restricted -> 0", t == 0)
    t, _ = await total(env.ga, project_id="none")
    check("filter 'tanpa project' oleh ALL_TENANT -> sesuai DB", t == none_n, f"{t} vs {none_n}")
    t, _ = await total(env.ra, project_id=env.pa3)
    check("filter project di luar scope oleh restricted -> 0 (bukan bocor)", t == 0)
    t, _ = await total(env.ra, q=f"Scope PA3 {MARK}")
    check("pencarian restricted tidak menembus scope", t == 0)
    r1 = await c.get(f"/api/assets/{env.a3['id']}", headers=env.ra)
    r2 = await c.get(f"/api/assets/{new_id()}", headers=env.ra)
    check("UUID di luar scope -> 404 generik (sama dengan UUID tidak ada)", r1.status_code == 404 and r2.status_code == 404
          and r1.json() == r2.json(), f"{r1.status_code} {r1.text[:80]} | {r2.text[:80]}")
    r = await c.get(f"/api/assets/{env.an['id']}", headers=env.ra)
    check("UUID aset tanpa project oleh restricted -> 404", r.status_code == 404)
    outs = [
        (await c.put(f"/api/assets/{env.a3['id']}", json={"name": "x"}, headers=env.ra)).status_code,
        (await c.post(f"/api/assets/{env.a3['id']}/status", json={"status_id": env.st["MAINTENANCE"]["id"], "reason": "x"}, headers=env.ra)).status_code,
        (await c.post(f"/api/assets/{env.a3['id']}/relocate", json={"project_id": env.pa1}, headers=env.ra)).status_code,
        (await c.delete(f"/api/assets/{env.a3['id']}", headers=env.ra)).status_code,
    ]
    check("edit/ubah status/relokasi/hapus aset di luar scope -> 404", outs == [404, 404, 404, 404], str(outs))
    r = await create(env, env.ra, name="Out", category_id=env.cat_alat["id"], project_id=env.pa3)
    check("create ke project di luar scope -> 403", r.status_code == 403, str(r.status_code))
    r = await create(env, env.ra, name="NoProj", category_id=env.cat_alat["id"])
    check("restricted create tanpa project -> 403", r.status_code == 403, str(r.status_code))
    r = await create(env, env.ra, name=f"In {MARK}", category_id=env.cat_alat["id"], project_id=env.pa1)
    check("restricted create ke project dalam scope -> 201", r.status_code == 201, r.text[:200])
    r = await c.post(f"/api/assets/{env.a1['id']}/relocate", json={"project_id": env.pa3}, headers=env.ra)
    check("relokasi dari project dalam scope ke luar scope -> 403", r.status_code == 403, str(r.status_code))
    r = await c.post(f"/api/assets/{env.a1['id']}/relocate", json={"project_id": None}, headers=env.ra)
    check("restricted memindah aset menjadi tanpa project -> 403", r.status_code == 403, str(r.status_code))
    r = await c.post(f"/api/assets/{env.a1['id']}/relocate", json={"project_id": env.pa2}, headers=env.rab)
    check("relokasi antar project dalam scope (multi) -> 200", r.status_code == 200 and r.json()["project_id"] == env.pa2, r.text[:200])
    o = await opts(env, env.ra)
    check("form-options project untuk restricted hanya project dalam scope", [p["id"] for p in o["projects"]] == [env.pa1], str(len(o["projects"])))
    o = await opts(env, env.re)
    check("form-options project untuk scope kosong -> tidak ada project", o["projects"] == [])
    r = await c.get("/api/master/asset-categories", headers=env.ra)
    check("restricted tetap bisa melihat master (konfigurasi company-level, RBAC saja)", r.status_code == 200)
    r = await c.get(f"/api/assets/{env.a1['id']}", headers=env.adminb)
    check("tenant lain (Tenant Admin B) UUID aset A -> 404", r.status_code == 404)
    # SQL-level: filter scope dikompilasi ke klausa SQL (bukan filter Python)
    scope = await DS.compute_scope(env.cid, env.rab_id, ["ga_admin"])
    flt = DS.with_project_scope({"company_id": env.cid}, scope)
    sql = str(dbm.compile_filter(dbm.get_table("assets"), flt).compile(compile_kwargs={"literal_binds": True}))
    check("scope aset dikompilasi ke SQL (project_id IN (...) AND IS NOT NULL)", "project_id IN" in sql and "IS NOT NULL" in sql and env.pa1 in sql, sql[:200])
    empty = await DS.compute_scope(env.cid, env.re_id, ["ga_admin"])
    sql = str(dbm.compile_filter(dbm.get_table("assets"), DS.with_project_scope({"company_id": env.cid}, empty)).compile(compile_kwargs={"literal_binds": True}))
    check("scope kosong dikompilasi ke SQL false", "false" in sql.lower() or "0 = 1" in sql or "1 != 1" in sql, sql[:200])


async def t_lifecycle_events_audit(env):
    c, db = env.c, get_db()
    aid = env.a2["id"]
    r = await c.post(f"/api/assets/{aid}/status", json={"status_id": env.st["MAINTENANCE"]["id"]}, headers=env.ga)
    check("ubah status tanpa alasan -> 422", r.status_code == 422, str(r.status_code))
    r = await c.post(f"/api/assets/{aid}/status", json={"status_id": env.st["MAINTENANCE"]["id"], "reason": "Servis rutin"}, headers=env.gs)
    check("READY -> MAINTENANCE (GA Staff) -> 200", r.status_code == 200 and r.json()["lifecycle_state"] == "MAINTENANCE", r.text[:200])
    r = await c.post(f"/api/assets/{aid}/relocate", json={"project_id": env.pa1}, headers=env.ga)
    check("relokasi aset non-READY -> 409", r.status_code == 409, str(r.status_code))
    r = await c.post(f"/api/assets/{aid}/status", json={"status_id": env.st["LOST"]["id"], "reason": "x"}, headers=env.ga)
    check("MAINTENANCE -> LOST (tidak ada di blueprint) -> 409", r.status_code == 409, str(r.status_code))
    r = await c.post(f"/api/assets/{aid}/status", json={"status_id": env.st["IN_USE"]["id"], "reason": "x"}, headers=env.ga)
    check("ubah manual ke IN_USE -> 409", r.status_code == 409, str(r.status_code))
    r = await c.post(f"/api/assets/{aid}/status", json={"status_id": env.st["DISPOSED"]["id"], "reason": "Tidak ekonomis"}, headers=env.ga)
    check("MAINTENANCE -> DISPOSED -> 200", r.status_code == 200 and r.json()["lifecycle_state"] == "DISPOSED")
    r = await c.post(f"/api/assets/{aid}/status", json={"status_id": env.st["MAINTENANCE"]["id"], "reason": "Batal"}, headers=env.gs)
    check("DISPOSED terminal: pembatalan tanpa asset:delete -> 409", r.status_code == 409, str(r.status_code))
    r = await c.post(f"/api/assets/{aid}/status", json={"status_id": env.st_gudang["id"], "reason": "Batal"}, headers=env.ga)
    check("pembatalan DISPOSED hanya ke status sebelumnya (bukan READY) -> 409", r.status_code == 409, str(r.status_code))
    r = await c.post(f"/api/assets/{aid}/status", json={"status_id": env.st["MAINTENANCE"]["id"], "reason": "Salah input"}, headers=env.ga)
    check("pembatalan DISPOSED oleh asset:delete ke status sebelumnya -> 200", r.status_code == 200 and r.json()["lifecycle_state"] == "MAINTENANCE", r.text[:200])
    r = await c.post(f"/api/assets/{aid}/status", json={"status_id": env.st["READY"]["id"], "reason": "Selesai servis"}, headers=env.ga)
    check("MAINTENANCE -> READY (label READY non-default) -> 200", r.status_code == 200 and r.json()["lifecycle_state"] == "READY")
    r = await c.post(f"/api/assets/{aid}/status", json={"status_id": env.st_gudang["id"], "reason": "Label"}, headers=env.ga)
    check("ganti label dalam kategori sistem yang sama (READY->READY) -> 200", r.status_code == 200 and r.json()["status_id"] == env.st_gudang["id"])
    r = await c.post(f"/api/assets/{aid}/relocate", json={"project_id": env.pa3, "work_location_id": env.wa2, "notes": "Pindah gudang"}, headers=env.ga)
    check("relokasi READY -> 200", r.status_code == 200 and r.json()["project_id"] == env.pa3 and r.json()["work_location_id"] == env.wa2, r.text[:200])
    r = await c.put(f"/api/assets/{aid}", json={"condition_id": by_code(env.o["conditions"], "LECET")["id"], "model": "T14"}, headers=env.ga)
    check("ubah kondisi + model -> 200", r.status_code == 200)
    d = (await c.get(f"/api/assets/{aid}", headers=env.ga)).json()
    types = [e["event_type"] for e in d["events"]]
    check("histori event memuat CREATED, UPDATED, STATUS_CHANGE, RELOCATION",
          {"CREATED", "UPDATED", "STATUS_CHANGE", "RELOCATION"} <= set(types), str(types))
    check("event dasar hanya jenis CP1 (tanpa HANDOVER/RETURN/BAST)", set(types) <= {"CREATED", "UPDATED", "STATUS_CHANGE", "RELOCATION"})
    st_ev = next(e for e in d["events"] if e["event_type"] == "STATUS_CHANGE" and e["to_state"] == "DISPOSED")
    check("event status mencatat from/to state + alasan + aktor", st_ev["from_state"] == "MAINTENANCE" and st_ev["notes"] == "Tidak ekonomis" and st_ev["actor_name"])
    check("detail: kode tidak dapat diubah lagi (code_editable false)", d["code_editable"] is False)
    acts = {a["action"] for a in await db.audit_logs.find({"company_id": env.cid, "resource": "asset", "record_id": aid}, {"_id": 0}).to_list(100)}
    check("audit log aset: create/update/status_change/relocate", {"create", "update", "status_change", "relocate"} <= acts, str(acts))
    one = await db.audit_logs.find_one({"company_id": env.cid, "resource": "asset", "record_id": aid, "action": "relocate"}, {"_id": 0})
    check("audit log memuat aktor, company, kode aset, timestamp", one and one.get("user_id") == env.ga_id and one.get("record_label") == env.a2["asset_code"]
          and one.get("created_at"), str({k: one.get(k) for k in ("user_id", "record_label")}) if one else "none")
    # filter & pagination
    r = await c.get("/api/assets", params={"status_id": env.st_gudang["id"], "project_id": env.pa3, "work_location_id": env.wa2,
                                           "category_id": env.cat_alat["id"], "unit_id": env.unit["id"],
                                           "condition_id": by_code(env.o["conditions"], "LECET")["id"]}, headers=env.ga)
    check("filter gabungan (status+project+lokasi+kategori+satuan+kondisi)", r.json()["total"] == 1 and r.json()["items"][0]["id"] == aid, str(r.json()["total"]))
    r = await c.get("/api/assets", params={"lifecycle_state": "READY", "q": "T14"}, headers=env.ga)
    check("cari merk/model + filter kategori sistem", r.json()["total"] == 1)
    r = await c.get("/api/assets", params={"q": f"ab12-{RUN}"}, headers=env.ga)
    check("cari serial number (normalisasi)", r.json()["total"] == 1 and r.json()["items"][0]["id"] == env.laptop["id"])
    r = await c.get("/api/assets", params={"q": env.a1["asset_code"].lower()}, headers=env.ga)
    check("cari kode aset (case-insensitive)", r.json()["total"] == 1)
    p1 = (await c.get("/api/assets", params={"limit": 5, "page": 1, "sort_by": "asset_code", "sort_dir": "asc"}, headers=env.ga)).json()
    p2 = (await c.get("/api/assets", params={"limit": 5, "page": 2, "sort_by": "asset_code", "sort_dir": "asc"}, headers=env.ga)).json()
    check("pagination server-side (halaman berbeda, total sama)", len(p1["items"]) == 5 and p1["total"] == p2["total"]
          and not ({i["id"] for i in p1["items"]} & {i["id"] for i in p2["items"]}))
    check("list memuat label (kategori, satuan, project, lokasi, kondisi, status)",
          all(k in p1["items"][0] for k in ("category_name", "unit_name", "project_name", "work_location_name", "condition_name", "status_name")))
    # hapus
    r = await c.delete(f"/api/assets/{env.an['id']}", headers=env.ga)
    r2 = await c.get(f"/api/assets/{env.an['id']}", headers=env.ga)
    del_log = await db.audit_logs.count_documents({"company_id": env.cid, "resource": "asset", "record_id": env.an["id"], "action": "delete"})
    check("hapus aset (asset:delete) -> 200, lalu 404, audit tercatat", r.status_code == 200 and r2.status_code == 404 and del_log == 1)
    # tidak ada endpoint di luar lingkup (CP2 lifecycle sah sejak Phase 2A CP2; import/export/opening/dashboard tetap terlarang)
    paths = {getattr(rt, "path", "") for rt in server.app.routes}
    out_scope = [p for p in paths if any(x in p for x in ("asset-import", "/assets/import", "/assets/export", "asset-export",
                                                         "opening", "asset-dashboard", "/assets/dashboard"))]
    check("tidak ada endpoint di luar lingkup (import/export/opening holding/dashboard aset)", out_scope == [], str(out_scope))


async def main():
    env = Env()
    clean_ok = False
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://tast") as c:
        env.c = c
        try:
            await setup(env)
            for t in (t_module_activation, t_rbac_presets, t_masters, t_crud_identity, t_value, t_concurrency, t_scope,
                      t_lifecycle_events_audit):
                try:
                    await t(env)
                except Exception as exc:  # noqa: BLE001
                    import traceback
                    traceback.print_exc()
                    check(f"{t.__name__} (exception)", False, repr(exc)[:200])
        finally:
            clean_ok = await cleanup(env)
    await dbm.close_db()
    check("cleanup data uji CP1 tuntas", clean_ok)
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n== CP1 Manajemen Aset targeted: {len(RESULTS) - len(failed)}/{len(RESULTS)} PASS ==")
    return failed


def test_asset_cp1():
    assert not asyncio.run(main())


if __name__ == "__main__":
    sys.exit(1 if asyncio.run(main()) else 0)
