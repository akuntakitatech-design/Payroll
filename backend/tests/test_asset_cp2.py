"""Phase 2A CP2 - Siklus Penyerahan, Pengembalian & Pemeriksaan Aset + Dokumen BAST: test backend terarah.

CARA MENJALANKAN (hanya MariaDB development LOKAL `hris_dev`):
    cd backend && bash tests/dev_env_run.sh python3 tests/test_asset_cp2.py
    (atau: bash tests/dev_env_run.sh python3 -m pytest tests/test_asset_cp2.py -q)

KEAMANAN TEST
- Guard: APP_ENV=development + host DB loopback + nama DB `hris_dev` (dicek juga lewat SELECT DATABASE()) +
  READ_ONLY=false + tanpa kredensial R2. Abort bila tidak terpenuhi.
- App in-process (httpx ASGITransport); PDF dibuat on-the-fly, tidak ada object storage.
- Semua fixture ditandai penanda unik per-run `T02-<RUN>` (nama company/karyawan/aset/project/user/role) dan hanya
  berada di dua company uji milik run ini. Cleanup (try/finally, setelah SELURUH skenario selesai) hanya menghapus
  baris milik company/user/role run ini, lalu memverifikasi residue = 0 dan orphan CP2 = 0.
- Password akun uji acak per-run di memori, tidak ditulis ke file/log.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import pathlib
import re
import secrets
import sys
import zlib
from datetime import date
from urllib.parse import urlsplit

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(pathlib.Path(__file__).resolve().parents[1] / ".env")


def _guard() -> None:
    url = urlsplit(os.environ.get("DATABASE_URL", ""))
    if (os.environ.get("APP_ENV") != "development" or url.hostname not in {"127.0.0.1", "localhost"}
            or url.path.strip("/") != "hris_dev"):
        raise SystemExit("DITOLAK: test CP2 aset hanya boleh berjalan pada MariaDB development lokal (hris_dev).")
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
MARK = f"T02-{RUN}"
RESULTS: list = []
YEAR = date.today().year
TODAY = date.today().isoformat()
HO_RE = re.compile(rf"^BAST-AST/{YEAR}/\d{{6}}$")
RT_RE = re.compile(rf"^BAST-RTN/{YEAR}/\d{{6}}$")
CP2_RES = ("asset_handover", "asset_return", "asset_inspection", "asset_bast")
CP2_ALL = {f"{r}:{a}" for r, acts in {"asset_handover": ["view", "create", "edit", "publish"],
                                      "asset_return": ["view", "create", "edit", "publish"],
                                      "asset_inspection": ["view", "create", "edit", "complete"],
                                      "asset_bast": ["view"]}.items() for a in acts}
CP2_STAFF = CP2_ALL - {"asset_handover:publish", "asset_return:publish", "asset_inspection:complete"}
CP2_TABLES = ["asset_handovers", "asset_handover_items", "asset_holdings", "asset_returns", "asset_return_items",
              "asset_inspections", "asset_basts"]


def check(name: str, cond: bool, info: str = "") -> None:
    RESULTS.append((name, bool(cond), info))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info and not cond else ""))


class Env:
    pass


# ------------------------------------------------------------------ fixture (semua bertanda MARK)
async def _mk_company(env, suffix):
    doc = {"id": new_id(), "code": f"T2{suffix}{RUN}"[:10], "name": f"PT Uji Siklus {suffix} {MARK}", "status": "active",
           "address": "Jl. Uji No. 1", "created_at": now(), "updated_at": now()}
    await get_db().companies.insert_one(dict(doc))
    env.company_ids.append(doc["id"])
    return doc["id"]


async def _mk_user(env, role_key, company_id, label):
    db = get_db()
    email = f"t02.{label}.{RUN.lower()}@kelolakita.dev"
    pw = "T02-" + secrets.token_urlsafe(12)
    uid = new_id()
    await db.users.insert_one({"id": uid, "company_id": None, "status": "active", "email": email, "full_name": f"{MARK} {label}",
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


async def _mk_employee(env, cid, label, project_id, position_id=None):
    db = get_db()
    eid = new_id()
    await db.employees.insert_one({"id": eid, "company_id": cid, "status": "active", "full_name": f"Kary{label}{RUN}",
                                   "employee_number": f"{label}-{RUN}", "job_title": f"Staf{label}", "position_id": position_id,
                                   "created_at": now(), "updated_at": now()})
    await db.employee_assignments.insert_one({"id": new_id(), "company_id": cid, "status": "active", "employee_id": eid,
                                              "project_id": project_id, "assignment_status": "ACTIVE", "start_date": "2024-01-01",
                                              "created_at": now(), "updated_at": now()})
    return eid


async def _custom_role(env, key_suffix, source_role):
    db = get_db()
    rk = f"t02{key_suffix}_{RUN.lower()}"
    env.roles.append(rk)
    r = await env.c.post("/api/roles", json={"key": rk, "name": f"{key_suffix} {MARK}"}, headers=env.admin)
    assert r.status_code == 201, r.text
    keys = sorted({p["permission_key"] for p in await db.role_permissions.find({"role_key": source_role}, {"_id": 0}).to_list(1000)})
    r = await env.c.put(f"/api/roles/{rk}/permissions", json={"permission_keys": keys}, headers=env.admin)
    assert r.status_code == 200, r.text
    return rk


async def setup(env):
    env.company_ids, env.user_ids, env.roles = [], [], []
    env.cid = await _mk_company(env, "A")
    env.cid_b = await _mk_company(env, "B")
    env.p1, env.p2, env.p3 = [await _mk_ref(env, "projects", env.cid, c) for c in ("P1", "P2", "P3")]
    env.pb = await _mk_ref(env, "projects", env.cid_b, "PB")
    env.wa = await _mk_ref(env, "work_locations", env.cid, "WA")
    env.pos = await _mk_ref(env, "positions", env.cid, "JAB")
    env.admin_id, env.admin = await _mk_user(env, "tenant_admin", env.cid, "admin")
    env.adminb_id, env.adminb = await _mk_user(env, "tenant_admin", env.cid_b, "adminb")
    env.ga_id, env.ga = await _mk_user(env, "ga_admin", env.cid, "gaadmin")          # tanpa baris scope -> ALL_TENANT
    env.gs_id, env.gs = await _mk_user(env, "ga_staff", env.cid, "gastaff")
    env.emp_id, env.emp = await _mk_user(env, "employee", env.cid, "employee")
    env.r1_id, env.r1 = await _mk_user(env, "ga_admin", env.cid, "r1")
    env.r12_id, env.r12 = await _mk_user(env, "ga_admin", env.cid, "r12")
    env.re_id, env.re = await _mk_user(env, "ga_admin", env.cid, "rempty")
    env.rc_id, env.rc = await _mk_user(env, "ga_admin", env.cid, "rchg")
    await _raw_scope(env.cid, env.r1_id, DS.SELECTED_PROJECTS, [env.p1])
    await _raw_scope(env.cid, env.r12_id, DS.SELECTED_PROJECTS, [env.p1, env.p2])
    await _raw_scope(env.cid, env.re_id, DS.SELECTED_PROJECTS, [])
    await _raw_scope(env.cid, env.rc_id, DS.SELECTED_PROJECTS, [env.p1, env.p2])
    for h in (env.admin, env.adminb):
        r = await env.c.put("/api/modules/toggle", json={"module_key": "asset", "is_active": True}, headers=h)
        assert r.status_code == 200, r.text
    env.hrga = (await _mk_user(env, await _custom_role(env, "hrga", "ga_admin"), env.cid, "hrga"))[1]
    env.hrgs = (await _mk_user(env, await _custom_role(env, "hrgs", "ga_staff"), env.cid, "hrgs"))[1]
    env.e1 = await _mk_employee(env, env.cid, "E1", env.p1, env.pos)
    env.e2 = await _mk_employee(env, env.cid, "E2", env.p1)
    env.e3 = await _mk_employee(env, env.cid, "E3", env.p2)
    env.e4 = await _mk_employee(env, env.cid, "E4", env.p3)
    env.eb = await _mk_employee(env, env.cid_b, "EB", env.pb)
    o = (await env.c.get("/api/assets/form-options", headers=env.ga)).json()
    env.alat = next(x for x in o["categories"] if x["code"] == "ALAT")["id"]
    env.cond = {x["code"]: x["id"] for x in o["conditions"]}
    env.st = {x["system_state"]: x["id"] for x in o["statuses"] if x.get("is_default")}
    ob = (await env.c.get("/api/assets/form-options", headers=env.adminb)).json()
    env.alat_b = next(x for x in ob["categories"] if x["code"] == "ALAT")["id"]


async def cleanup(env) -> dict:
    """Hanya baris milik company/user/role run ini (id dicatat saat dibuat; semuanya bertanda MARK)."""
    eng = dbm.get_engine()
    cids, uids, rks = env.company_ids, env.user_ids, env.roles
    async with eng.begin() as conn:
        async def d(sql, **p):
            stmt = sa.text(sql)
            for k, v in p.items():
                if isinstance(v, (list, tuple)):
                    stmt = stmt.bindparams(sa.bindparam(k, expanding=True))
            await conn.execute(stmt, p)
        existing = {r[0] for r in (await conn.execute(sa.text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE()"))).all()}
        # anak dulu (CP2 -> CP1 -> master/karyawan), lalu seluruh tabel tenant lain milik company uji
        ordered = ["asset_inspections", "asset_return_items", "asset_returns", "asset_holdings", "asset_handover_items",
                   "asset_basts", "asset_handovers", "asset_events", "assets"]
        rest = [t for t in dbm.TENANT_COLLECTIONS if t not in ordered]
        if cids:
            for t in ordered + rest:
                if t in existing:
                    await d(f"DELETE FROM `{t}` WHERE company_id IN :c", c=cids)
        if uids:
            await d("DELETE FROM audit_logs WHERE user_id IN :u", u=uids)
            await d("DELETE FROM user_company_roles WHERE user_id IN :u", u=uids)
            await d("DELETE FROM users WHERE id IN :u", u=uids)
        for rk in rks:
            await d("DELETE FROM role_permissions WHERE role_key = :r", r=rk)
            await d("DELETE FROM roles WHERE `key` = :r", r=rk)
        if cids:
            await d("DELETE FROM companies WHERE id IN :c", c=cids)
    return await residue_report(env)


async def residue_report(env) -> dict:
    eng = dbm.get_engine()
    out = {"residue": 0, "orphan": 0, "detail": []}
    async with eng.connect() as conn:
        async def n(sql, **p):
            stmt = sa.text(sql)
            for k, v in p.items():
                if isinstance(v, (list, tuple)):
                    stmt = stmt.bindparams(sa.bindparam(k, expanding=True))
            return (await conn.execute(stmt, p)).scalar() or 0
        existing = {r[0] for r in (await conn.execute(sa.text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE()"))).all()}
        if env.company_ids:
            for t in dbm.TENANT_COLLECTIONS:
                if t in existing:
                    k = await n(f"SELECT COUNT(*) FROM `{t}` WHERE company_id IN :c", c=env.company_ids)
                    if k:
                        out["residue"] += k
                        out["detail"].append(f"{t}={k}")
        like = f"%{MARK}%"
        for sql in ("SELECT COUNT(*) FROM companies WHERE name LIKE :m", "SELECT COUNT(*) FROM users WHERE full_name LIKE :m",
                    "SELECT COUNT(*) FROM roles WHERE name LIKE :m", "SELECT COUNT(*) FROM projects WHERE name LIKE :m",
                    "SELECT COUNT(*) FROM assets WHERE name LIKE :m"):
            k = await n(sql, m=like)
            if k:
                out["residue"] += k
                out["detail"].append(f"{sql[21:40]}={k}")
        k = await n("SELECT COUNT(*) FROM employees WHERE employee_number LIKE :m", m=f"%-{RUN}")
        out["residue"] += k
        orphan_sql = [
            "SELECT COUNT(*) FROM asset_handover_items i LEFT JOIN asset_handovers h ON h.id = i.handover_id WHERE h.id IS NULL",
            "SELECT COUNT(*) FROM asset_return_items i LEFT JOIN asset_returns r ON r.id = i.return_id WHERE r.id IS NULL",
            "SELECT COUNT(*) FROM asset_holdings x LEFT JOIN assets a ON a.id = x.asset_id WHERE a.id IS NULL",
            "SELECT COUNT(*) FROM asset_inspections x LEFT JOIN asset_returns r ON r.id = x.return_id WHERE r.id IS NULL",
            "SELECT COUNT(*) FROM asset_basts b LEFT JOIN asset_handovers h ON h.id = b.source_id "
            "LEFT JOIN asset_returns r ON r.id = b.source_id WHERE h.id IS NULL AND r.id IS NULL",
        ] + [f"SELECT COUNT(*) FROM {t} x LEFT JOIN companies c ON c.id = x.company_id WHERE c.id IS NULL" for t in CP2_TABLES]
        for sql in orphan_sql:
            k = await n(sql)
            if k:
                out["orphan"] += k
                out["detail"].append(f"orphan:{sql[21:70]}={k}")
    return out


# ------------------------------------------------------------------ helpers
async def mk_asset(env, label, project_id, h=None, cat=None):
    r = await env.c.post("/api/assets", json={"name": f"{label} {MARK}", "category_id": cat or env.alat, "project_id": project_id,
                                              "serial_number": f"SN{label}{RUN}"}, headers=h or env.ga)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def ho_body(env, emp, project, assets, **kw):
    return {"employee_id": emp, "handover_date": kw.pop("handover_date", TODAY), "project_id": project,
            "work_location_id": kw.pop("work_location_id", env.wa), "ga_pic_name": kw.pop("ga_pic_name", "PIC GA Uji"),
            "items": [{"asset_id": a, "accessories": "Charger", "item_notes": "ok"} for a in assets], **kw}


async def draft_ho(env, h, emp, project, assets, **kw):
    return await env.c.post("/api/asset-handovers", json=ho_body(env, emp, project, assets, **kw), headers=h)


async def publish_ho(env, h, hid):
    return await env.c.post(f"/api/asset-handovers/{hid}/publish", headers=h)


async def ho_published(env, emp, project, assets, **kw):
    r = await draft_ho(env, env.ga, emp, project, assets, **kw)
    assert r.status_code == 201, r.text
    r = await publish_ho(env, env.ga, r.json()["id"])
    assert r.status_code == 200, r.text
    return r.json()


async def holding_of(env, asset_id):
    return await get_db().asset_holdings.find_one({"company_id": env.cid, "asset_id": asset_id, "holding_status": "ACTIVE"}, {"_id": 0})


async def draft_rt(env, h, emp, holding_ids, cond="BAIK", **kw):
    body = {"employee_id": emp, "return_date": kw.pop("return_date", TODAY), "ga_pic_name": "PIC GA Uji",
            "items": [{"holding_id": x, "condition_id": env.cond[cond], "accessories": "Charger"} for x in holding_ids], **kw}
    return await env.c.post("/api/asset-returns", json=body, headers=h)


async def publish_rt(env, h, rid):
    return await env.c.post(f"/api/asset-returns/{rid}/publish", headers=h)


async def rt_published(env, emp, asset_ids, cond="BAIK"):
    hs = [(await holding_of(env, a))["id"] for a in asset_ids]
    r = await draft_rt(env, env.ga, emp, hs, cond)
    assert r.status_code == 201, r.text
    r = await publish_rt(env, env.ga, r.json()["id"])
    assert r.status_code == 200, r.text
    return r.json()


async def state(env, asset_id, cid=None):
    a = await get_db().assets.find_one({"company_id": cid or env.cid, "id": asset_id}, {"_id": 0})
    return (a or {}).get("lifecycle_state")


async def counter(env, key, year=YEAR, cid=None):
    row = await get_db().document_sequence_counters.find_one(
        {"company_id": cid or env.cid, "sequence_key": key, "period_key": str(year)}, {"_id": 0})
    return int(row["next_value"]) if row else None


async def insp_of(env, asset_id, st="PENDING"):
    return await get_db().asset_inspections.find_one({"company_id": env.cid, "asset_id": asset_id, "inspection_state": st}, {"_id": 0})


async def raw_snapshot(env, bast_id, cid=None):
    b = await get_db().asset_basts.find_one({"company_id": cid or env.cid, "id": bast_id}, {"_id": 0})
    return json.dumps((b or {}).get("snapshot"), sort_keys=True, default=str)


def seq(num: str) -> int:
    return int(num.rsplit("/", 1)[1])


def pdf_text(data: bytes) -> str:
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        raw = m.group(1).strip()
        try:
            if raw.endswith(b"~>"):
                raw = base64.a85decode(raw if raw.startswith(b"<~") else b"<~" + raw, adobe=True)
            out.append(zlib.decompress(raw).decode("latin-1"))
        except Exception:  # noqa: BLE001
            out.append(raw.decode("latin-1", "ignore"))
    return "\n".join(out)


async def total(env, h, path, **params):
    r = await env.c.get(path, params={"limit": 100, **params}, headers=h)
    if r.status_code != 200:
        return -1, []
    return r.json()["total"], r.json()["items"]


# ------------------------------------------------------------------ tests
async def t_rbac_presets(env):
    db = get_db()
    perms = {p["key"] for p in await db.permissions.find({}, {"_id": 0}).to_list(2000) if p["key"].split(":")[0] in CP2_RES}
    check("permission CP2 terdaftar lengkap (13 key)", perms == CP2_ALL, str(sorted(perms)))
    for rk, exp in (("ga_admin", CP2_ALL), ("ga_staff", CP2_STAFF), ("tenant_admin", CP2_ALL)):
        have = {p["permission_key"] for p in await db.role_permissions.find({"role_key": rk}, {"_id": 0}).to_list(2000)}
        got = {k for k in have if k.split(":")[0] in CP2_RES}
        check(f"preset {rk}: izin CP2 sesuai matriks terkunci", got == exp, str(sorted(got)))
    me = (await env.c.get("/api/auth/me", headers=env.gs)).json()
    p = set(me.get("permissions", []))
    check("GA Staff (/auth/me): punya view/create/edit, tanpa publish/complete",
          CP2_STAFF <= p and not ({"asset_handover:publish", "asset_return:publish", "asset_inspection:complete"} & p))
    r = await env.c.get("/api/asset-handovers", headers=env.emp)
    check("role Karyawan tanpa asset_handover:view -> 403", r.status_code == 403, str(r.status_code))
    r = await env.c.get("/api/asset-basts", headers=env.emp)
    check("role Karyawan tanpa asset_bast:view -> 403", r.status_code == 403, str(r.status_code))


async def t_handover_basic(env):
    c = env.c
    env.A = [await mk_asset(env, f"A{i}", env.p1) for i in range(1, 17)]
    env.B2 = [await mk_asset(env, f"B2{i}", env.p2) for i in range(1, 5)]
    env.B3 = [await mk_asset(env, f"B3{i}", env.p3) for i in range(1, 3)]
    env.AN = await mk_asset(env, "AN", None)
    o = (await c.get("/api/asset-handovers/options", headers=env.gs)).json()
    check("options penyerahan (GA Staff): memuat karyawan & hanya aset READY",
          {env.e1, env.e2, env.e3, env.e4} <= {e["id"] for e in o["employees"]} and set(env.A) <= {a["id"] for a in o["assets"]})
    r = await draft_ho(env, env.gs, env.e1, env.p1, env.A[:3], manual_number=f"REF-{RUN}-1")
    check("GA Staff buat draft penyerahan multi-aset (3 aset) -> 201 DRAFT",
          r.status_code == 201 and r.json()["doc_state"] == "DRAFT" and len(r.json()["items"]) == 3, r.text[:200])
    env.h1 = r.json()["id"]
    body = ho_body(env, env.e1, env.p1, env.A[:3], manual_number=f"REF-{RUN}-1", notes="Draft diubah")
    body["items"][0]["accessories"] = "Charger + Tas"
    r = await c.put(f"/api/asset-handovers/{env.h1}", json=body, headers=env.gs)
    check("GA Staff ubah draft penyerahan -> 200 (row_version naik)", r.status_code == 200 and r.json()["row_version"] == 2, r.text[:200])
    r = await publish_ho(env, env.gs, env.h1)
    check("GA Staff publish penyerahan -> 403", r.status_code == 403, str(r.status_code))
    r = await publish_ho(env, env.hrgs, env.h1)
    check("role kustom setara GA Staff publish penyerahan -> 403", r.status_code == 403, str(r.status_code))
    r = await publish_ho(env, env.ga, env.h1)
    j = r.json()
    check("GA Admin publish penyerahan -> 200 PUBLISHED + nomor BAST-AST/{YYYY}/{SEQ:6}",
          r.status_code == 200 and j["doc_state"] == "PUBLISHED" and bool(HO_RE.match(j.get("bast_number") or "")), r.text[:200])
    env.h1_bast = j.get("bast_id")
    env.h1_number = j.get("bast_number")
    check("detail penyerahan terbit memuat snapshot BAST (3 item)", len((j.get("bast_snapshot") or {}).get("items") or []) == 3)
    states = [await state(env, a) for a in env.A[:3]]
    check("publish: seluruh aset -> IN_USE", states == ["IN_USE"] * 3, str(states))
    db = get_db()
    hs = await db.asset_holdings.find({"company_id": env.cid, "handover_id": env.h1}, {"_id": 0}).to_list(10)
    check("publish: 3 holding ACTIVE (active_lock = asset_id, employee, start_date, project, lokasi, kondisi, kelengkapan)",
          len(hs) == 3 and all(h["holding_status"] == "ACTIVE" and h["active_lock"] == h["asset_id"] and h["employee_id"] == env.e1
                               and h["start_date"] == TODAY and h["project_id"] == env.p1 and h["work_location_id"] == env.wa
                               and h["initial_condition_id"] and h["accessories_out"] for h in hs), str(len(hs)))
    ev = await db.asset_events.count_documents({"company_id": env.cid, "event_type": "HANDOVER", "bast_id": env.h1_bast})
    check("publish: event HANDOVER per aset (3) dengan referensi BAST", ev == 3, str(ev))
    r = await c.put(f"/api/asset-handovers/{env.h1}", json=body, headers=env.ga)
    check("penyerahan PUBLISHED tidak dapat diedit -> 409", r.status_code == 409, str(r.status_code))
    r = await c.post(f"/api/asset-handovers/{env.h1}/cancel", headers=env.ga)
    check("penyerahan PUBLISHED tidak dapat dibatalkan -> 409", r.status_code == 409, str(r.status_code))
    r = await publish_ho(env, env.ga, env.h1)
    check("publish ulang penyerahan PUBLISHED -> 409", r.status_code == 409, str(r.status_code))
    logs = await db.audit_logs.count_documents({"company_id": env.cid, "resource": "asset_handover", "record_id": env.h1, "action": "publish"})
    check("audit log publish penyerahan tercatat", logs == 1, str(logs))


async def t_ready_only_atomic(env):
    c = env.c
    r = await draft_ho(env, env.ga, env.e2, env.p1, [env.A[0]])
    check("draft penyerahan dengan aset IN_USE -> 409 (hanya READY)", r.status_code == 409, str(r.status_code))
    r = await draft_ho(env, env.ga, env.e2, env.p1, [env.A[3], env.A[4]])
    check("draft penyerahan 2 aset READY -> 201", r.status_code == 201, r.text[:200])
    hid = r.json()["id"]
    before_ctr = await counter(env, "BAST_HANDOVER")
    r = await c.post(f"/api/assets/{env.A[4]}/status", json={"status_id": env.st["MAINTENANCE"], "reason": "uji atomik"}, headers=env.ga)
    check("CP1: aset item ke-2 diubah ke MAINTENANCE setelah draft", r.status_code == 200, r.text[:200])
    r = await publish_ho(env, env.ga, hid)
    check("publish dengan 1 aset tidak READY -> 409", r.status_code == 409, str(r.status_code))
    db = get_db()
    ok = (await state(env, env.A[3]) == "READY"
          and await db.asset_holdings.count_documents({"company_id": env.cid, "asset_id": env.A[3]}) == 0
          and await db.asset_basts.count_documents({"company_id": env.cid, "source_id": hid}) == 0
          and await db.asset_events.count_documents({"company_id": env.cid, "asset_id": env.A[3], "event_type": "HANDOVER"}) == 0
          and (await db.asset_handovers.find_one({"id": hid}, {"_id": 0}))["doc_state"] == "DRAFT"
          and await counter(env, "BAST_HANDOVER") == before_ctr)
    check("rollback total: aset lain tetap READY, tanpa holding/BAST/event, draft tetap DRAFT, counter tidak maju", ok)
    await c.post(f"/api/assets/{env.A[4]}/status", json={"status_id": env.st["READY"], "reason": "uji atomik pulih"}, headers=env.ga)
    r = await publish_ho(env, env.ga, hid)
    check("setelah aset kembali READY: publish -> 200, nomor berurutan tanpa gap",
          r.status_code == 200 and seq(r.json()["bast_number"]) == seq(env.h1_number) + 1, r.text[:200])
    env.h_a45 = hid


async def t_duplicate_holding(env):
    r1 = await draft_ho(env, env.ga, env.e2, env.p1, [env.A[5]])
    r2 = await draft_ho(env, env.ga, env.e3, env.p1, [env.A[5]])
    check("dua draft untuk aset READY yang sama boleh dibuat", r1.status_code == 201 and r2.status_code == 201)
    a = await publish_ho(env, env.ga, r1.json()["id"])
    b = await publish_ho(env, env.ga, r2.json()["id"])
    n = await get_db().asset_holdings.count_documents({"company_id": env.cid, "asset_id": env.A[5], "holding_status": "ACTIVE"})
    check("publish kedua untuk aset yang sudah punya holding aktif -> 409; tepat 1 holding aktif",
          a.status_code == 200 and b.status_code == 409 and n == 1, f"{a.status_code} {b.status_code} {n}")
    err = None
    try:
        async with dbm.transaction() as tx:
            await tx.insert("asset_holdings", {"id": new_id(), "company_id": env.cid, "status": "active", "asset_id": env.A[5],
                                               "employee_id": env.e3, "holding_status": "ACTIVE", "active_lock": env.A[5]})
    except Exception as exc:  # noqa: BLE001
        err = getattr(exc, "status_code", repr(exc))
    n2 = await get_db().asset_holdings.count_documents({"company_id": env.cid, "asset_id": env.A[5], "holding_status": "ACTIVE"})
    check("DB: unique ux_asset_holding_active menolak holding aktif ke-2 untuk aset sama", err == 409 and n2 == 1, f"{err} {n2}")


async def t_concurrent_handover(env):
    x = (await draft_ho(env, env.ga, env.e2, env.p1, [env.A[6]])).json()["id"]
    y = (await draft_ho(env, env.ga, env.e3, env.p1, [env.A[6]])).json()["id"]
    z = (await draft_ho(env, env.hrga, env.e4, env.p1, [env.A[6]])).json()["id"]
    rs = await asyncio.gather(publish_ho(env, env.ga, x), publish_ho(env, env.ga, y), publish_ho(env, env.hrga, z))
    codes = sorted(r.status_code for r in rs)
    db = get_db()
    n = await db.asset_holdings.count_documents({"company_id": env.cid, "asset_id": env.A[6], "holding_status": "ACTIVE"})
    nb = await db.asset_basts.count_documents({"company_id": env.cid, "source_id": {"$in": [x, y, z]}})
    check("3 publish paralel untuk aset yang sama -> tepat 1 sukses (200), sisanya 409",
          codes == [200, 409, 409], str(codes) + " " + str([r.text[:80] for r in rs if r.status_code not in (200, 409)]))
    check("paralel: tepat 1 holding aktif & 1 BAST untuk aset tersebut", n == 1 and nb == 1, f"{n} {nb}")


async def t_bast_numbering(env):
    c = env.c
    ids = [(await draft_ho(env, env.ga, env.e2, env.p1, [a])).json()["id"] for a in env.A[7:13]]
    start = await counter(env, "BAST_HANDOVER")
    rs = await asyncio.gather(*[publish_ho(env, env.ga, i) for i in ids])
    nums = [r.json().get("bast_number") for r in rs if r.status_code == 200]
    check("6 publish paralel (aset berbeda) -> semua 200", len(nums) == 6, str([r.status_code for r in rs]))
    check("BAST-AST paralel: nomor unik, format valid, berurutan tanpa gap",
          len(set(nums)) == 6 and all(HO_RE.match(n) for n in nums) and sorted(seq(n) for n in nums) == list(range(start, start + 6)),
          str(sorted(nums)))
    db = get_db()
    dup = await db.asset_basts.count_documents({"company_id": env.cid, "system_number": {"$in": nums}})
    check("BAST-AST paralel: tidak ada nomor ganda di DB", dup == 6, str(dup))
    await db.document_sequence_counters.update_one({"company_id": env.cid, "sequence_key": "BAST_HANDOVER", "period_key": str(YEAR)},
                                                   {"$set": {"next_value": 700}})
    j = await ho_published(env, env.e2, env.p1, [env.A[13]])
    cnt = await db.asset_basts.count_documents({"company_id": env.cid, "bast_type": "HANDOVER"})
    check("nomor dari counter (bukan COUNT(*)+1): counter 700 -> 000700 walau jumlah BAST jauh lebih kecil",
          j["bast_number"] == f"BAST-AST/{YEAR}/000700" and cnt < 700, f"{j['bast_number']} count={cnt}")
    j = await ho_published(env, env.e2, env.p1, [env.A[14]], handover_date=f"{YEAR - 1}-07-01")
    check("reset tahunan: tanggal tahun lalu -> BAST-AST/{YYYY-1}/000001", j["bast_number"] == f"BAST-AST/{YEAR - 1}/000001", j["bast_number"])
    ab = await mk_asset(env, "BB1", env.pb, h=env.adminb, cat=env.alat_b)
    r = await c.post("/api/asset-handovers", json={"employee_id": env.eb, "handover_date": TODAY, "project_id": env.pb,
                                                   "items": [{"asset_id": ab}]}, headers=env.adminb)
    r = await publish_ho(env, env.adminb, r.json()["id"])
    check("counter per company: tenant B mulai BAST-AST/{YYYY}/000001", r.status_code == 200 and r.json()["bast_number"] == f"BAST-AST/{YEAR}/000001",
          r.text[:160])
    env.b_ho = r.json()
    env.b_asset = ab


async def t_snapshot_immutable(env):
    c = env.c
    db = get_db()
    raw0 = await raw_snapshot(env, env.h1_bast)
    b0 = (await c.get(f"/api/asset-basts/{env.h1_bast}", headers=env.ga)).json()
    snap = b0["snapshot"]
    check("snapshot BAST memuat company, karyawan (nama/NIK/jabatan), project, lokasi, item (kode/serial/kondisi/kelengkapan)",
          snap["company"]["name"] and snap["employee"]["full_name"] == f"KaryE1{RUN}" and snap["employee"]["position"] == f"JAB {MARK}"
          and snap["employee"]["job_title"] == "StafE1" and snap["project"]["name"] == f"P1 {MARK}" and snap["work_location"]["name"]
          and all(i["asset_code"] and i["serial_number"] and i["condition"] and i["accessories"] for i in snap["items"]), str(snap)[:300])
    await db.employees.update_one({"id": env.e1}, {"$set": {"full_name": f"Diganti{RUN}", "job_title": "JabatanBaru"}})
    await db.assets.update_one({"id": env.A[0]}, {"$set": {"name": f"AsetDiganti {MARK}", "serial_number": f"SNBARU{RUN}"}})
    await db.projects.update_one({"id": env.p1}, {"$set": {"name": f"ProjectBaru {MARK}"}})
    await db.positions.update_one({"id": env.pos}, {"$set": {"name": f"JabBaru {MARK}"}})
    b1 = (await c.get(f"/api/asset-basts/{env.h1_bast}", headers=env.ga)).json()
    check("perubahan master karyawan/aset/project/jabatan TIDAK mengubah snapshot BAST lama",
          b1["snapshot"] == snap and await raw_snapshot(env, env.h1_bast) == raw0)
    r = await c.get(f"/api/asset-basts/{env.h1_bast}/pdf", headers=env.ga)
    txt = pdf_text(r.content)
    check("PDF BAST dibuat dari snapshot: memuat nama lama, bukan nama master terbaru",
          r.status_code == 200 and f"KaryE1{RUN}" in txt and f"Diganti{RUN}" not in txt and f"SNA1{RUN}" in txt
          and f"SNBARU{RUN}" not in txt, f"{r.status_code} len={len(txt)}")
    r = await c.put(f"/api/asset-handovers/{env.h1}/manual-number", json={"manual_number": f"REF-{RUN}-EDIT"}, headers=env.ga)
    logs = await db.audit_logs.count_documents({"company_id": env.cid, "resource": "asset_handover", "record_id": env.h1,
                                                "action": "update_manual_number"})
    check("nomor referensi dokumen terbit dapat diubah (dengan audit), nomor sistem & snapshot tetap",
          r.status_code == 200 and logs == 1 and await raw_snapshot(env, env.h1_bast) == raw0
          and (await c.get(f"/api/asset-basts/{env.h1_bast}", headers=env.ga)).json()["system_number"] == env.h1_number, r.text[:160])
    t, items = await total(env, env.ga, "/api/asset-basts", q=f"ref-{RUN}-edit")
    check("pencarian BAST berdasarkan nomor referensi baru", t == 1 and items[0]["id"] == env.h1_bast, str(t))
    t, items = await total(env, env.ga, "/api/asset-basts", q=env.h1_number)
    check("pencarian BAST berdasarkan nomor sistem", t == 1, str(t))
    r = await draft_ho(env, env.ga, env.e2, env.p1, [env.A[15]], manual_number=f"ref-{RUN}-edit")
    check("nomor referensi duplikat hanya peringatan (draft tetap 201 + warning)",
          r.status_code == 201 and bool(r.json().get("manual_number_warning")), r.text[:160])
    await c.post(f"/api/asset-handovers/{r.json()['id']}/cancel", headers=env.ga)


async def t_partial_return(env):
    c = env.c
    db = get_db()
    ro = (await c.get("/api/asset-returns/options", headers=env.gs)).json()
    check("options pengembalian: karyawan pemegang aktif (E1) tersedia", env.e1 in {e["id"] for e in ro["employees"]})
    t, hs = await total(env, env.gs, "/api/asset-holdings", employee_id=env.e1)
    check("holding aktif E1 = 3 (daftar untuk dipilih)", t == 3, str(t))
    hmap = {h["asset_id"]: h["id"] for h in hs}
    r = await draft_rt(env, env.gs, env.e1, [hmap[env.A[0]]], cond="LECET")
    check("GA Staff buat draft pengembalian parsial (1 dari 3 aset) -> 201 DRAFT",
          r.status_code == 201 and r.json()["doc_state"] == "DRAFT", r.text[:200])
    rid = r.json()["id"]
    body = {"employee_id": env.e1, "return_date": TODAY, "notes": "diubah",
            "items": [{"holding_id": hmap[env.A[0]], "condition_id": env.cond["LECET"], "accessories": "Charger saja"}]}
    r = await c.put(f"/api/asset-returns/{rid}", json=body, headers=env.gs)
    check("GA Staff ubah draft pengembalian -> 200", r.status_code == 200, r.text[:160])
    r = await publish_rt(env, env.gs, rid)
    check("GA Staff publish pengembalian -> 403", r.status_code == 403, str(r.status_code))
    r = await publish_rt(env, env.hrgs, rid)
    check("role kustom setara GA Staff publish pengembalian -> 403", r.status_code == 403, str(r.status_code))
    r = await publish_rt(env, env.ga, rid)
    j = r.json()
    check("GA Admin publish pengembalian -> 200 PUBLISHED + BAST-RTN/{YYYY}/{SEQ:6}",
          r.status_code == 200 and j["doc_state"] == "PUBLISHED" and bool(RT_RE.match(j.get("bast_number") or "")), r.text[:200])
    env.rt1_id, env.r1_bast = rid, j.get("bast_id")
    check("BAST Pengembalian hanya berisi aset yang dikembalikan (1 item)", len((j.get("bast_snapshot") or {}).get("items") or []) == 1)
    st = [await state(env, a) for a in env.A[:3]]
    check("aset dikembalikan -> PENDING_INSPECTION; aset lain tetap IN_USE", st == ["PENDING_INSPECTION", "IN_USE", "IN_USE"], str(st))
    closed = await db.asset_holdings.find_one({"id": hmap[env.A[0]]}, {"_id": 0})
    check("hanya holding yang dikembalikan ditutup (CLOSED, end_date, active_lock NULL, kondisi & kelengkapan kembali)",
          closed["holding_status"] == "CLOSED" and closed["end_date"] == TODAY and closed["active_lock"] is None
          and closed["return_condition_id"] == env.cond["LECET"] and closed["accessories_in"] == "Charger saja"
          and closed["return_bast_id"] == env.r1_bast)
    act = await db.asset_holdings.count_documents({"company_id": env.cid, "handover_id": env.h1, "holding_status": "ACTIVE"})
    ho = (await c.get(f"/api/asset-handovers/{env.h1}", headers=env.ga)).json()
    check("penyerahan asal tetap PUBLISHED dengan 2 aset outstanding", act == 2 and ho["doc_state"] == "PUBLISHED", str(act))
    ins = await insp_of(env, env.A[0])
    b = await db.asset_basts.find_one({"id": env.r1_bast}, {"_id": 0})
    check("BAST Pengembalian terbit saat publish (sebelum pemeriksaan); pemeriksaan PENDING dibuat",
          b and b["bast_type"] == "RETURN" and ins and ins["inspection_state"] == "PENDING")
    r = await c.put(f"/api/asset-returns/{rid}", json=body, headers=env.ga)
    check("pengembalian PUBLISHED tidak dapat diedit -> 409", r.status_code == 409, str(r.status_code))
    r = await publish_rt(env, env.ga, rid)
    check("publish ulang pengembalian -> 409", r.status_code == 409, str(r.status_code))
    r = await draft_rt(env, env.ga, env.e1, [hmap[env.A[0]]])
    check("draft pengembalian untuk holding yang sudah ditutup -> 409", r.status_code == 409, str(r.status_code))
    env.hmap_e1 = hmap


async def t_return_atomic_duplicate(env):
    db = get_db()
    h2, h3 = env.hmap_e1[env.A[1]], env.hmap_e1[env.A[2]]
    r2 = (await draft_rt(env, env.ga, env.e1, [h2, h3])).json()["id"]
    r3 = (await draft_rt(env, env.ga, env.e1, [h3])).json()["id"]
    a = await publish_rt(env, env.ga, r3)
    ctr = await counter(env, "BAST_RETURN")
    b = await publish_rt(env, env.ga, r2)
    check("return kedua atas holding yang sudah dikembalikan -> 409", a.status_code == 200 and b.status_code == 409,
          f"{a.status_code} {b.status_code}")
    ok = (await state(env, env.A[1]) == "IN_USE"
          and (await db.asset_holdings.find_one({"id": h2}, {"_id": 0}))["holding_status"] == "ACTIVE"
          and (await db.asset_returns.find_one({"id": r2}, {"_id": 0}))["doc_state"] == "DRAFT"
          and await db.asset_basts.count_documents({"company_id": env.cid, "source_id": r2}) == 0
          and await db.asset_inspections.count_documents({"company_id": env.cid, "return_id": r2}) == 0
          and await counter(env, "BAST_RETURN") == ctr)
    check("rollback total publish return: aset lain tetap IN_USE + holding aktif, tanpa BAST/pemeriksaan, counter tetap", ok)
    j = await rt_published(env, env.e1, [env.A[1]])
    check("return berikutnya untuk sisa aset -> 200, nomor RTN berurutan", seq(j["bast_number"]) == seq(a.json()["bast_number"]) + 1,
          j["bast_number"])


async def t_concurrent_return(env):
    db = get_db()
    h = (await holding_of(env, env.A[7]))["id"]
    ra = (await draft_rt(env, env.ga, env.e2, [h])).json()["id"]
    rb = (await draft_rt(env, env.hrga, env.e2, [h])).json()["id"]
    rs = await asyncio.gather(publish_rt(env, env.ga, ra), publish_rt(env, env.hrga, rb))
    codes = sorted(r.status_code for r in rs)
    n = await db.asset_inspections.count_documents({"company_id": env.cid, "asset_id": env.A[7]})
    check("2 return paralel atas holding yang sama -> tepat 1 sukses; 1 pemeriksaan", codes == [200, 409] and n == 1, f"{codes} {n}")
    hs = [(await holding_of(env, a))["id"] for a in env.A[8:12]]
    ids = [(await draft_rt(env, env.ga, env.e2, [x])).json()["id"] for x in hs]
    start = await counter(env, "BAST_RETURN")
    rs = await asyncio.gather(*[publish_rt(env, env.ga, i) for i in ids])
    nums = [r.json().get("bast_number") for r in rs if r.status_code == 200]
    check("BAST-RTN paralel (4): semua 200, unik, format valid, berurutan",
          len(nums) == 4 and len(set(nums)) == 4 and all(RT_RE.match(x) for x in nums)
          and sorted(seq(x) for x in nums) == list(range(start, start + 4)), str([r.status_code for r in rs]) + str(nums))


async def t_inspection(env):
    c = env.c
    db = get_db()
    t, items = await total(env, env.ga, "/api/asset-inspections", inspection_state="PENDING")
    check("antrean pemeriksaan hanya aset PENDING_INSPECTION", t >= 6 and all(i["lifecycle_state"] == "PENDING_INSPECTION" for i in items), str(t))
    raw_rt = await raw_snapshot(env, env.r1_bast)
    i1 = (await insp_of(env, env.A[0]))["id"]
    r = await c.put(f"/api/asset-inspections/{i1}", json={"final_condition_id": env.cond["BAIK"], "completeness": "Lengkap",
                                                         "result_state": "LOST", "notes": "draft"}, headers=env.gs)
    check("GA Staff input pemeriksaan (create) -> 200", r.status_code == 200, r.text[:160])
    r = await c.put(f"/api/asset-inspections/{i1}", json={"notes": "diedit"}, headers=env.gs)
    check("GA Staff ubah input pemeriksaan (edit) -> 200", r.status_code == 200 and r.json()["notes"] == "diedit", r.text[:160])
    r = await c.post(f"/api/asset-inspections/{i1}/complete", json={"result_state": "READY"}, headers=env.gs)
    check("GA Staff complete pemeriksaan -> 403", r.status_code == 403, str(r.status_code))
    r = await c.post(f"/api/asset-inspections/{i1}/complete", json={"result_state": "READY"}, headers=env.hrgs)
    check("role kustom setara GA Staff complete -> 403", r.status_code == 403, str(r.status_code))
    r = await c.post(f"/api/asset-inspections/{i1}/complete", json={}, headers=env.ga)
    check("complete tanpa hasil eksplisit pada aksi ini (draft berisi LOST) -> 422; aset tidak jadi LOST",
          r.status_code == 422 and await state(env, env.A[0]) == "PENDING_INSPECTION", str(r.status_code))
    r = await c.post(f"/api/asset-inspections/{i1}/complete", json={"result_state": "DISPOSED"}, headers=env.ga)
    check("hasil di luar READY/MAINTENANCE/DAMAGED/LOST -> 422", r.status_code == 422, str(r.status_code))
    r = await c.post(f"/api/asset-inspections/{i1}/complete", json={"result_state": "READY", "final_condition_id": env.cond["BAIK"]}, headers=env.ga)
    check("complete -> READY: aset READY, pemeriksaan COMPLETED",
          r.status_code == 200 and r.json()["inspection_state"] == "COMPLETED" and await state(env, env.A[0]) == "READY", r.text[:160])
    ev = await db.asset_events.count_documents({"company_id": env.cid, "asset_id": env.A[0], "event_type": "INSPECTION"})
    check("event INSPECTION tercatat", ev == 1, str(ev))
    r = await c.post(f"/api/asset-inspections/{i1}/complete", json={"result_state": "DAMAGED"}, headers=env.ga)
    check("double complete -> 409 (hasil final)", r.status_code == 409 and await state(env, env.A[0]) == "READY", str(r.status_code))
    r = await c.put(f"/api/asset-inspections/{i1}", json={"notes": "ubah setelah final"}, headers=env.gs)
    check("ubah pemeriksaan setelah complete -> 409", r.status_code == 409, str(r.status_code))
    for a, res, cond in ((env.A[8], "MAINTENANCE", "RUSAK_RINGAN"), (env.A[9], "DAMAGED", "RUSAK_BERAT"), (env.A[10], "LOST", "HILANG")):
        iid = (await insp_of(env, a))["id"]
        r = await c.post(f"/api/asset-inspections/{iid}/complete", json={"result_state": res, "final_condition_id": env.cond[cond]},
                         headers=env.ga)
        check(f"complete -> {res}: status aset {res}", r.status_code == 200 and await state(env, a) == res, r.text[:160])
    iid = (await insp_of(env, env.A[11]))["id"]
    await c.put(f"/api/asset-inspections/{iid}", json={"final_condition_id": env.cond["RUSAK_BERAT"], "completeness": "Charger hilang"},
                headers=env.gs)
    r = await c.post(f"/api/asset-inspections/{iid}/complete", json={}, headers=env.ga)
    check("kondisi buruk + kelengkapan kurang TIDAK otomatis LOST (tanpa hasil eksplisit -> 422, tetap PENDING_INSPECTION)",
          r.status_code == 422 and await state(env, env.A[11]) == "PENDING_INSPECTION", str(r.status_code))
    r = await c.post(f"/api/asset-inspections/{iid}/complete", json={"result_state": "MAINTENANCE"}, headers=env.hrga)
    check("role kustom setara GA Admin complete -> 200", r.status_code == 200 and await state(env, env.A[11]) == "MAINTENANCE", r.text[:160])
    t, items = await total(env, env.ga, "/api/asset-inspections", inspection_state="COMPLETED")
    check("riwayat pemeriksaan selesai memuat hasil akhir", t >= 5 and all(i["result_state"] in ("READY", "MAINTENANCE", "DAMAGED", "LOST") for i in items))
    check("hasil pemeriksaan tidak mengubah snapshot BAST Pengembalian", await raw_snapshot(env, env.r1_bast) == raw_rt)
    rt = (await c.get(f"/api/asset-returns/{env.rt1_id}", headers=env.ga)).json()
    check("dokumen pengembalian tetap PUBLISHED setelah pemeriksaan", rt["doc_state"] == "PUBLISHED")


async def t_no_direct_transfer(env):
    c = env.c
    db = get_db()
    r = await draft_ho(env, env.ga, env.e3, env.p1, [env.A[3]])
    check("transfer langsung A->B (aset IN_USE ke karyawan lain) -> 409", r.status_code == 409 and await state(env, env.A[3]) == "IN_USE",
          str(r.status_code))
    r = await draft_ho(env, env.ga, env.e3, env.p1, [env.A[15]])
    hid = r.json()["id"]
    r = await c.put(f"/api/asset-handovers/{hid}", json=ho_body(env, env.e3, env.p1, [env.A[3]]), headers=env.ga)
    check("edit draft memasukkan aset IN_USE -> 409", r.status_code == 409, str(r.status_code))
    await c.post(f"/api/asset-handovers/{hid}/cancel", headers=env.ga)
    r = await c.post(f"/api/assets/{env.A[3]}/status", json={"status_id": env.st["READY"], "reason": "bypass"}, headers=env.ga)
    check("CP1: ubah status manual aset IN_USE -> 409 (tidak bisa bypass)", r.status_code == 409, str(r.status_code))
    paths = {getattr(rt, "path", "") for rt in server.app.routes}
    check("tidak ada endpoint transfer/reassign holding", not [p for p in paths if "transfer" in p and "asset" in p]
          and not [p for p in paths if "asset-holdings/" in p])
    j = await ho_published(env, env.e3, env.p1, [env.A[0]])
    hist = await db.asset_holdings.find({"company_id": env.cid, "asset_id": env.A[0]}, {"_id": 0}).to_list(10)
    check("alur sah: Return -> Inspection READY -> penyerahan baru ke karyawan B -> 200; histori 2 holding (CLOSED E1, ACTIVE E3)",
          j["doc_state"] == "PUBLISHED" and sorted((h["holding_status"], h["employee_id"]) for h in hist)
          == sorted([("CLOSED", env.e1), ("ACTIVE", env.e3)]), str([(h["holding_status"], h["employee_id"]) for h in hist]))
    r = await c.delete(f"/api/assets/{env.A[0]}", headers=env.admin)
    check("aset dengan histori penyerahan tidak dapat dihapus -> 409", r.status_code == 409, str(r.status_code))


async def t_scope(env):
    c = env.c
    db = get_db()
    j2 = await ho_published(env, env.e3, env.p2, [env.B2[0]])
    j3 = await ho_published(env, env.e4, env.p3, [env.B3[0]])
    jn = await ho_published(env, env.e2, None, [env.AN])
    r2 = await rt_published(env, env.e3, [env.B2[0]])
    ins_p2 = (await insp_of(env, env.B2[0]))["id"]
    env.scope_docs = (j2, j3, jn, r2)
    for path, coll in (("/api/asset-handovers", "asset_handovers"), ("/api/asset-returns", "asset_returns"),
                       ("/api/asset-basts", "asset_basts")):
        t, items = await total(env, env.r1, path)
        exp = await db[coll].count_documents({"company_id": env.cid, "project_id": env.p1, **({} if coll == "asset_basts" else {"status": "active"})})
        check(f"SELECTED_PROJECTS [P1] {path}: total SQL = jumlah dokumen P1 saja", t == exp and all(i["project_id"] == env.p1 for i in items),
              f"{t} vs {exp}")
    t, items = await total(env, env.r1, "/api/asset-inspections", inspection_state="PENDING")
    t2, items2 = await total(env, env.r1, "/api/asset-inspections", inspection_state="COMPLETED")
    check("antrean/riwayat pemeriksaan ter-scope [P1]", all(i["project_id"] == env.p1 for i in items + items2) and ins_p2 not in {i["id"] for i in items})
    t, items = await total(env, env.r1, "/api/asset-holdings")
    check("daftar holding ter-scope [P1]", all(i["project_id"] == env.p1 for i in items) and t > 0, str(t))
    for path in ("/api/asset-handovers", "/api/asset-basts", "/api/asset-returns"):
        t, _ = await total(env, env.r1, path, q=r2["bast_number"] if "return" in path else j2["bast_number"])
        tg, _ = await total(env, env.ga, path, q=r2["bast_number"] if "return" in path else j2["bast_number"])
        check(f"pencarian {path} nomor BAST project P2: restricted 0, ALL_TENANT 1", t == 0 and tg == 1, f"{t} {tg}")
    t, items = await total(env, env.r1, "/api/asset-handovers", q=f"KaryE4{RUN}")
    tg, items_g = await total(env, env.ga, "/api/asset-handovers", q=f"KaryE4{RUN}")
    check("pencarian nama karyawan: restricted hanya dokumen project dalam scope (dokumen P3 tidak bocor)",
          all(i["project_id"] == env.p1 for i in items) and j3["id"] not in {i["id"] for i in items}
          and j3["id"] in {i["id"] for i in items_g}, f"{t} {tg}")
    o = (await c.get("/api/asset-handovers/options", headers=env.r1)).json()
    emps = {e["id"] for e in o["employees"]}
    check("selector karyawan ter-scope [P1]: E1,E2 ada; E3,E4 tidak", {env.e1, env.e2} <= emps and not ({env.e3, env.e4} & emps), str(len(emps)))
    check("selector aset ter-scope [P1] & hanya READY", o["assets"] and all(a["project_id"] == env.p1 for a in o["assets"])
          and env.B2[1] not in {a["id"] for a in o["assets"]} and env.AN not in {a["id"] for a in o["assets"]})
    ro = (await c.get("/api/asset-returns/options", headers=env.r1)).json()
    check("selector karyawan pengembalian ter-scope", not ({env.e3, env.e4} & {e["id"] for e in ro["employees"]}))
    for label, path in (("penyerahan P2", f"/api/asset-handovers/{j2['id']}"), ("penyerahan tanpa project", f"/api/asset-handovers/{jn['id']}"),
                        ("BAST P2", f"/api/asset-basts/{j2['bast_id']}"), ("PDF BAST P2", f"/api/asset-basts/{j2['bast_id']}/pdf"),
                        ("pengembalian P2", f"/api/asset-returns/{r2['id']}"), ("pemeriksaan P2", f"/api/asset-inspections/{ins_p2}"),
                        ("UUID acak", f"/api/asset-handovers/{new_id()}")):
        r = await c.get(path, headers=env.r1)
        check(f"UUID di luar scope ({label}) -> 404 generik", r.status_code == 404 and r.json().get("detail") == DS.NOT_FOUND_MSG,
              f"{r.status_code} {r.text[:80]}")
    r = await draft_ho(env, env.r1, env.e3, env.p1, [env.A[15]])
    check("restricted: draft dengan karyawan di luar scope -> 404", r.status_code == 404, str(r.status_code))
    r = await draft_ho(env, env.r1, env.e1, env.p1, [env.B2[1]])
    check("restricted: draft dengan aset di luar scope -> 404", r.status_code == 404, str(r.status_code))
    r = await draft_ho(env, env.r1, env.e1, env.p2, [env.A[15]])
    check("restricted: project tujuan di luar scope -> 403", r.status_code == 403, str(r.status_code))
    r = await draft_ho(env, env.r1, env.e1, None, [env.A[15]])
    check("restricted: project kosong tidak diizinkan -> 403", r.status_code == 403, str(r.status_code))
    t, items = await total(env, env.r12, "/api/asset-handovers")
    projs = {i["project_id"] for i in items}
    exp = await db.asset_handovers.count_documents({"company_id": env.cid, "status": "active", "project_id": {"$in": [env.p1, env.p2]}})
    check("multi-project [P1,P2]: melihat P1+P2, bukan P3/tanpa project", t == exp and env.p2 in projs and projs <= {env.p1, env.p2}, f"{t} {exp}")
    r = await c.get(f"/api/asset-basts/{jn['bast_id']}", headers=env.r12)
    check("project NULL tidak bocor ke restricted user (BAST) -> 404", r.status_code == 404, str(r.status_code))
    for path in ("/api/asset-handovers", "/api/asset-returns", "/api/asset-basts", "/api/asset-holdings", "/api/asset-inspections"):
        t, _ = await total(env, env.re, path)
        check(f"scope kosong {path} -> 0 data", t == 0, str(t))
    o = (await c.get("/api/asset-handovers/options", headers=env.re)).json()
    check("scope kosong: selector karyawan & aset kosong", o["employees"] == [] and o["assets"] == [])
    t, items = await total(env, env.ga, "/api/asset-handovers")
    ids = {i["id"] for i in items}
    check("ALL_TENANT: melihat semua project termasuk tanpa project", {j2["id"], j3["id"], jn["id"]} <= ids)
    # scope berubah setelah draft dibuat -> publish/complete ditolak
    r = await draft_ho(env, env.rc, env.e3, env.p2, [env.B2[1]])
    check("rchg [P1,P2]: draft penyerahan P2 -> 201", r.status_code == 201, r.text[:160])
    hid = r.json()["id"]
    r = await draft_ho(env, env.rc, env.e2, env.p1, [env.A[15]])
    hid_emp = r.json()["id"]
    await db.user_data_scope_items.update_many({"company_id": env.cid, "user_id": env.rc_id, "ref_id": env.p2}, {"$set": {"status": "inactive"}})
    r = await publish_ho(env, env.rc, hid)
    check("scope dipersempit setelah draft: publish penyerahan -> 404, draft tetap, aset tetap READY",
          r.status_code == 404 and (await db.asset_handovers.find_one({"id": hid}, {"_id": 0}))["doc_state"] == "DRAFT"
          and await state(env, env.B2[1]) == "READY", str(r.status_code))
    r = await c.post(f"/api/asset-inspections/{ins_p2}/complete", json={"result_state": "READY"}, headers=env.rc)
    check("scope dipersempit: complete pemeriksaan P2 -> 404, tetap PENDING",
          r.status_code == 404 and (await db.asset_inspections.find_one({"id": ins_p2}, {"_id": 0}))["inspection_state"] == "PENDING",
          str(r.status_code))
    await db.employee_assignments.update_many({"company_id": env.cid, "employee_id": env.e2}, {"$set": {"project_id": env.p3}})
    r = await publish_ho(env, env.rc, hid_emp)
    check("karyawan pindah keluar scope setelah draft: publish -> 404 (scope karyawan dicek ulang)",
          r.status_code == 404 and await state(env, env.A[15]) == "READY", str(r.status_code))
    await db.employee_assignments.update_many({"company_id": env.cid, "employee_id": env.e2}, {"$set": {"project_id": env.p1}})
    h_rt = (await holding_of(env, env.A[12]))["id"]
    r = await draft_rt(env, env.rc, env.e2, [h_rt])
    rid = r.json()["id"]
    await db.asset_holdings.update_one({"id": h_rt}, {"$set": {"project_id": env.p2}})
    await db.asset_returns.update_one({"id": rid}, {"$set": {"project_id": env.p1}})
    r = await publish_rt(env, env.rc, rid)
    check("scope holding berubah setelah draft return: publish -> ditolak (409), holding tetap aktif",
          r.status_code == 409 and (await db.asset_holdings.find_one({"id": h_rt}, {"_id": 0}))["holding_status"] == "ACTIVE", str(r.status_code))
    await db.asset_holdings.update_one({"id": h_rt}, {"$set": {"project_id": env.p1}})


async def t_tenant_isolation(env):
    c = env.c
    j2 = env.scope_docs[0]
    r2 = env.scope_docs[3]
    ins = await get_db().asset_inspections.find_one({"company_id": env.cid}, {"_id": 0})
    for label, path in (("penyerahan", f"/api/asset-handovers/{env.h1}"), ("BAST", f"/api/asset-basts/{j2['bast_id']}"),
                        ("PDF", f"/api/asset-basts/{j2['bast_id']}/pdf"), ("pengembalian", f"/api/asset-returns/{r2['id']}"),
                        ("pemeriksaan", f"/api/asset-inspections/{ins['id']}")):
        r = await c.get(path, headers=env.adminb)
        check(f"tenant B akses {label} tenant A -> 404", r.status_code == 404, str(r.status_code))
    t, items = await total(env, env.adminb, "/api/asset-basts")
    check("tenant B hanya melihat BAST miliknya", t == 1 and items[0]["id"] == env.b_ho["bast_id"], str(t))
    t, items = await total(env, env.adminb, "/api/asset-holdings")
    check("tenant B hanya melihat holding miliknya", t == 1 and items[0]["asset_id"] == env.b_asset, str(t))
    r = await c.post("/api/asset-handovers", json={"employee_id": env.e1, "project_id": env.pb, "items": [{"asset_id": env.b_asset}]},
                     headers=env.adminb)
    check("tenant B memakai karyawan tenant A -> 404", r.status_code == 404, str(r.status_code))
    r = await c.post("/api/asset-handovers", json={"employee_id": env.eb, "project_id": env.pb, "items": [{"asset_id": env.A[15]}]},
                     headers=env.adminb)
    check("tenant B memakai aset tenant A -> 404", r.status_code == 404, str(r.status_code))
    r = await c.get(f"/api/asset-basts/{env.b_ho['bast_id']}", headers=env.ga)
    check("tenant A akses BAST tenant B -> 404", r.status_code == 404, str(r.status_code))


async def t_pdf(env):
    c = env.c
    r = await c.get(f"/api/asset-basts/{env.h1_bast}/pdf", headers=env.gs)
    cd = r.headers.get("content-disposition", "")
    check("PDF BAST Penyerahan (GA Staff asset_bast:view) -> 200 application/pdf, %PDF, attachment",
          r.status_code == 200 and r.headers.get("content-type", "").startswith("application/pdf") and r.content[:4] == b"%PDF"
          and cd.startswith("attachment") and env.h1_number.replace("/", "-") in cd, f"{r.status_code} {cd}")
    r = await c.get(f"/api/asset-basts/{env.h1_bast}/pdf", params={"inline": "true"}, headers=env.gs)
    check("PDF inline (Lihat PDF) -> Content-Disposition inline", r.headers.get("content-disposition", "").startswith("inline"))
    r = await c.get(f"/api/asset-basts/{env.r1_bast}/pdf", headers=env.ga)
    txt = pdf_text(r.content)
    check("PDF BAST Pengembalian dibuat on-the-fly (judul pengembalian)", r.status_code == 200 and "PENGEMBALIAN" in txt, str(r.status_code))
    r = await c.get(f"/api/asset-basts/{env.h1_bast}/pdf", headers=env.emp)
    check("PDF tanpa asset_bast:view -> 403", r.status_code == 403, str(r.status_code))
    cols = set(dbm.TABLE_SPECS["asset_basts"])
    check("tidak ada kolom file/URL/object-storage PDF pada asset_basts (tanpa penyimpanan PDF)",
          not [x for x in cols if any(k in x for k in ("pdf", "file", "url", "r2", "storage", "signed"))], str(cols))
    t, items = await total(env, env.gs, "/api/asset-basts", bast_type="RETURN", date_from=TODAY, date_to=TODAY)
    check("daftar BAST filter tipe + tanggal", t >= 1 and all(i["bast_type"] == "RETURN" for i in items), str(t))


async def main():
    env = Env()
    rep = {"residue": -1, "orphan": -1, "detail": ["cleanup tidak berjalan"]}
    async with dbm.get_engine().connect() as conn:
        dbname = (await conn.execute(sa.text("SELECT DATABASE()"))).scalar()
    if dbname != "hris_dev":
        raise SystemExit(f"DITOLAK: database aktual {dbname!r} bukan hris_dev.")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://t02", timeout=120) as c:
        env.c = c
        try:
            await setup(env)
            for t in (t_rbac_presets, t_handover_basic, t_ready_only_atomic, t_duplicate_holding, t_concurrent_handover,
                      t_bast_numbering, t_snapshot_immutable, t_partial_return, t_return_atomic_duplicate, t_concurrent_return,
                      t_inspection, t_no_direct_transfer, t_scope, t_tenant_isolation, t_pdf):
                try:
                    await t(env)
                except Exception as exc:  # noqa: BLE001
                    import traceback
                    traceback.print_exc()
                    check(f"{t.__name__} (exception)", False, repr(exc)[:200])
        finally:
            rep = await cleanup(env)
    await dbm.close_db()
    check("fixture cleanup: residue 0 (hanya data bertanda run ini)", rep["residue"] == 0, str(rep["detail"]))
    check("fixture cleanup: orphan CP2 0", rep["orphan"] == 0, str(rep["detail"]))
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n== CP2 targeted: {len(RESULTS) - len(failed)}/{len(RESULTS)} PASS ==")
    print(f"Fixture cleanup: {'PASS' if rep['residue'] == 0 and rep['orphan'] == 0 else 'FAIL'} — residue {rep['residue']}, "
          f"orphan {rep['orphan']} (marker {MARK})")
    return failed


def test_asset_cp2():
    assert not asyncio.run(main())


if __name__ == "__main__":
    sys.exit(1 if asyncio.run(main()) else 0)
