"""Phase 2A CP2.1 - Finalisasi Transaksi Aset & UX: Simpan & Publish atomik, otorisasi murni permission, pencarian
karyawan server-side (01I), format PDF BAST.

CARA MENJALANKAN (hanya MariaDB development LOKAL `hris_dev`):
    cd backend && bash tests/dev_env_run.sh python3 tests/test_asset_cp2_1.py

Memakai ulang guard + fixture + cleanup bertanda run dari test_asset_cp2 (company/user/role/karyawan/aset milik run
ini saja; cleanup memverifikasi residue = 0 dan orphan = 0). Role uji dibuat sebagai CUSTOM role dengan set izin
eksplisit (nama role tidak dipakai sebagai logika otorisasi).
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import test_asset_cp2 as T  # noqa: E402  (guard hris_dev dijalankan saat import)

import httpx  # noqa: E402
import sqlalchemy as sa  # noqa: E402

import server  # noqa: E402
from app.core import db as dbm  # noqa: E402
from app.core.asset_bast_pdf import company_address, format_tanggal, format_waktu_wib  # noqa: E402
from app.core.db import get_db, new_id, now  # noqa: E402

check, RUN, MARK, YEAR, TODAY = T.check, T.RUN, T.MARK, T.YEAR, T.TODAY

VIEWS = ["asset:view", "asset_master:view", "asset_bast:view", "asset_handover:view", "asset_return:view"]
DRAFTER = VIEWS + ["asset_handover:create", "asset_handover:edit", "asset_return:create", "asset_return:edit"]
FINALIZER = DRAFTER + ["asset_handover:publish", "asset_return:publish"]
PUBLISH_ONLY = VIEWS + ["asset_handover:publish", "asset_return:publish"]


async def _perm_role(env, suffix, keys):
    """Custom role dengan set izin eksplisit - nama role acak, tidak mirip preset GA."""
    rk = f"t21{suffix}_{RUN.lower()}"
    env.roles.append(rk)
    r = await env.c.post("/api/roles", json={"key": rk, "name": f"Peran {suffix} {MARK}"}, headers=env.admin)
    assert r.status_code == 201, r.text
    r = await env.c.put(f"/api/roles/{rk}/permissions", json={"permission_keys": sorted(keys)}, headers=env.admin)
    assert r.status_code == 200, r.text
    return rk


async def setup21(env):
    await T.setup(env)
    env.dr = (await T._mk_user(env, await _perm_role(env, "zeta", DRAFTER), env.cid, "drafter"))[1]
    env.fz = (await T._mk_user(env, await _perm_role(env, "omega", FINALIZER), env.cid, "finalizer"))[1]
    env.po = (await T._mk_user(env, await _perm_role(env, "sigma", PUBLISH_ONLY), env.cid, "pubonly"))[1]


async def counter(env, key):
    row = await get_db().document_sequence_counters.find_one(
        {"company_id": env.cid, "sequence_key": key, "period_key": str(YEAR)}, {"_id": 0})
    # baris counter dibuat idempoten oleh doc_sequence.prepare dengan next_value = 1 (belum ada nomor terpakai)
    return int((row or {}).get("next_value") or 1)


async def n(env, coll, **flt):
    return await get_db()[coll].count_documents({"company_id": env.cid, **flt})


async def snapshot_counts(env):
    return {c: await n(env, c) for c in ("asset_handovers", "asset_handover_items", "asset_holdings", "asset_basts",
                                         "asset_returns", "asset_return_items", "asset_inspections", "asset_events")}


async def fake_active_holding(env, asset_id, emp):
    """State inkonsisten buatan (aset READY tetapi ada holding ACTIVE) agar publish gagal DI DALAM transaksi."""
    hid = new_id()
    await get_db().asset_holdings.insert_one({"id": hid, "company_id": env.cid, "status": "active", "asset_id": asset_id,
                                              "employee_id": emp, "start_date": TODAY, "holding_status": "ACTIVE",
                                              "active_lock": asset_id, "created_at": now(), "updated_at": now()})
    return hid


# ------------------------------------------------------------------ permission (tanpa nama role)
async def t_permission(env):
    a1 = await T.mk_asset(env, "PM1", env.p1)
    body = T.ho_body(env, env.e1, env.p1, [a1], notes=f"perm {MARK}")
    r = await env.c.post("/api/asset-handovers", json=body, headers=env.dr)
    check("izin create/edit tanpa publish: Simpan Draft penyerahan -> 201 DRAFT", r.status_code == 201 and r.json()["doc_state"] == "DRAFT", r.text[:150])
    draft = r.json()["id"]
    before = await snapshot_counts(env)
    r = await env.c.post("/api/asset-handovers/save-and-publish", json=body, headers=env.dr)
    check("izin create/edit tanpa publish: Simpan & Publish (baru) -> 403", r.status_code == 403, r.status_code)
    r = await env.c.post(f"/api/asset-handovers/{draft}/save-and-publish", json=body, headers=env.dr)
    check("izin create/edit tanpa publish: Simpan & Publish (draft) -> 403", r.status_code == 403, r.status_code)
    r = await env.c.post(f"/api/asset-handovers/{draft}/publish", headers=env.dr)
    check("izin create/edit tanpa publish: Publish draft -> 403", r.status_code == 403, r.status_code)
    check("403 tidak meninggalkan efek (tanpa draft/holding/BAST baru, aset tetap READY)",
          await snapshot_counts(env) == before and await T.state(env, a1) == "READY")
    r = await env.c.post("/api/asset-handovers/save-and-publish", json=body, headers=env.po)
    check("izin publish tanpa create: Simpan & Publish (baru) -> 403 (butuh create + publish)", r.status_code == 403, r.status_code)
    r = await env.c.post(f"/api/asset-handovers/{draft}/save-and-publish", json=body, headers=env.po)
    check("izin publish tanpa edit: Simpan & Publish (draft) -> 403 (butuh edit + publish)", r.status_code == 403, r.status_code)
    r = await env.c.post(f"/api/asset-handovers/{draft}/publish", headers=env.po)
    check("izin publish tanpa create/edit: Publish draft existing -> 200", r.status_code == 200 and r.json()["doc_state"] == "PUBLISHED", r.text[:150])
    a2 = await T.mk_asset(env, "PM2", env.p1)
    r = await env.c.post("/api/asset-handovers/save-and-publish", json=T.ho_body(env, env.e2, env.p1, [a2]), headers=env.fz)
    check("custom role berizin create+publish (nama role bukan GA): Simpan & Publish -> 201", r.status_code == 201, r.text[:150])
    r = await env.c.post("/api/asset-returns/save-and-publish", json={"employee_id": env.e2, "items": []}, headers=env.dr)
    check("pengembalian: izin create/edit tanpa publish: Simpan & Publish -> 403", r.status_code == 403, r.status_code)


# ------------------------------------------------------------------ penyerahan
async def t_handover(env):
    a1, a2 = await T.mk_asset(env, "HA1", env.p1), await T.mk_asset(env, "HA2", env.p1)
    r = await env.c.post("/api/asset-handovers", json=T.ho_body(env, env.e1, env.p1, [a1, a2], notes="draft v1"), headers=env.dr)
    check("penyerahan: Simpan Draft 2 aset -> 201, aset tetap READY",
          r.status_code == 201 and await T.state(env, a1) == "READY" and await T.state(env, a2) == "READY", r.text[:150])
    d1 = r.json()["id"]
    c0 = await counter(env, "BAST_HANDOVER")
    r = await env.c.post(f"/api/asset-handovers/{d1}/save-and-publish",
                         json=T.ho_body(env, env.e1, env.p1, [a1, a2], notes="draft v2 final"), headers=env.fz)
    ok = r.status_code == 200
    d = r.json() if ok else {}
    check("penyerahan: Simpan & Publish draft existing -> PUBLISHED + BAST-AST", ok and d["doc_state"] == "PUBLISHED"
          and bool(T.HO_RE.match(d.get("bast_number") or "")), r.text[:200])
    check("penyerahan: perubahan form ikut tersimpan saat Simpan & Publish (catatan v2 di dokumen & snapshot)",
          ok and d.get("notes") == "draft v2 final" and (d.get("bast_snapshot") or {}).get("notes") == "draft v2 final")
    check("penyerahan: nomor BAST dialokasikan tepat satu", await counter(env, "BAST_HANDOVER") == c0 + 1)
    h1, h2 = await T.holding_of(env, a1), await T.holding_of(env, a2)
    check("penyerahan: kedua aset IN_USE + holding ACTIVE (active_lock = asset_id) ke karyawan",
          await T.state(env, a1) == "IN_USE" and await T.state(env, a2) == "IN_USE" and h1 and h2
          and h1["employee_id"] == env.e1 and h1["active_lock"] == a1 and h2["active_lock"] == a2)
    a3 = await T.mk_asset(env, "HA3", env.p1)
    r = await env.c.post("/api/asset-handovers/save-and-publish", json=T.ho_body(env, env.e2, env.p1, [a3]), headers=env.fz)
    check("penyerahan: Simpan & Publish form baru -> 201 PUBLISHED (tanpa berhenti di draft)",
          r.status_code == 201 and r.json()["doc_state"] == "PUBLISHED" and await T.state(env, a3) == "IN_USE", r.text[:150])
    a4 = await T.mk_asset(env, "HA4", env.p1)
    r = await env.c.post("/api/asset-handovers", json=T.ho_body(env, env.e2, env.p1, [a4]), headers=env.dr)
    r = await env.c.post(f"/api/asset-handovers/{r.json()['id']}/publish", headers=env.fz)
    check("penyerahan: Publish draft existing (alur CP2) tetap berfungsi", r.status_code == 200 and r.json()["doc_state"] == "PUBLISHED", r.text[:150])
    r = await env.c.post("/api/asset-handovers/save-and-publish", json=T.ho_body(env, env.e3, env.p2, [a3]), headers=env.fz)
    check("penyerahan: Simpan & Publish aset IN_USE ke karyawan lain ditolak (tanpa transfer A->B)", r.status_code == 409, r.status_code)


# ------------------------------------------------------------------ atomicity
async def t_atomic(env):
    a1 = await T.mk_asset(env, "AT1", env.p1)
    fake = await fake_active_holding(env, a1, env.e4)
    before, c0 = await snapshot_counts(env), await counter(env, "BAST_HANDOVER")
    r = await env.c.post("/api/asset-handovers/save-and-publish",
                         json=T.ho_body(env, env.e1, env.p1, [a1], notes=f"atomic-new {MARK}"), headers=env.fz)
    check("atomik (form baru): publish gagal di dalam transaksi -> 409", r.status_code == 409, f"{r.status_code} {r.text[:120]}")
    check("atomik (form baru): tidak ada draft tersisa", await n(env, "asset_handovers", notes=f"atomic-new {MARK}") == 0)
    after = await snapshot_counts(env)
    check("atomik (form baru): tidak ada item/holding/BAST/event parsial", after == before, f"{before} -> {after}")
    check("atomik (form baru): nomor BAST tidak terpakai (counter tetap)", await counter(env, "BAST_HANDOVER") == c0)
    check("atomik (form baru): status aset tidak berubah (READY)", await T.state(env, a1) == "READY")

    a2 = await T.mk_asset(env, "AT2", env.p1)
    r = await env.c.post("/api/asset-handovers", json=T.ho_body(env, env.e1, env.p1, [a2], notes="persisted v1"), headers=env.dr)
    did = r.json()["id"]
    persisted = await get_db().asset_handovers.find_one({"company_id": env.cid, "id": did}, {"_id": 0})
    before, c0 = await snapshot_counts(env), await counter(env, "BAST_HANDOVER")
    r = await env.c.post(f"/api/asset-handovers/{did}/save-and-publish",
                         json=T.ho_body(env, env.e2, env.p1, [a1], notes="attempt v2"), headers=env.fz)
    check("atomik (draft existing): publish gagal -> 409", r.status_code == 409, f"{r.status_code} {r.text[:120]}")
    cur = await get_db().asset_handovers.find_one({"company_id": env.cid, "id": did}, {"_id": 0})
    items = await get_db().asset_handover_items.find({"company_id": env.cid, "handover_id": did}, {"_id": 0}).to_list(10)
    check("atomik (draft existing): draft kembali ke versi tersimpan (catatan/karyawan/row_version/item)",
          cur["doc_state"] == "DRAFT" and cur["notes"] == "persisted v1" and cur["employee_id"] == env.e1
          and cur.get("row_version") == persisted.get("row_version") and [i["asset_id"] for i in items] == [a2])
    check("atomik (draft existing): tanpa holding/BAST/counter parsial",
          await snapshot_counts(env) == before and await counter(env, "BAST_HANDOVER") == c0)
    await get_db().asset_holdings.delete_one({"company_id": env.cid, "id": fake})
    r = await env.c.post(f"/api/asset-handovers/{did}/save-and-publish",
                         json=T.ho_body(env, env.e1, env.p1, [a2], notes="retry ok"), headers=env.fz)
    check("atomik: setelah diperbaiki, Simpan & Publish ulang berhasil", r.status_code == 200 and r.json()["doc_state"] == "PUBLISHED", r.text[:150])

    # pengembalian: aset dirusak state-nya di luar alur -> finalisasi gagal di dalam transaksi
    a3 = await T.mk_asset(env, "AT3", env.p1)
    await T.ho_published(env, env.e3, env.p1, [a3])
    h3 = await T.holding_of(env, a3)
    await get_db().assets.update_one({"company_id": env.cid, "id": a3}, {"$set": {"lifecycle_state": "MAINTENANCE"}})
    before, c0 = await snapshot_counts(env), await counter(env, "BAST_RETURN")
    r = await env.c.post("/api/asset-returns/save-and-publish", json={"employee_id": env.e3, "notes": f"atomic-rt {MARK}", "items": [
        {"holding_id": h3["id"], "condition_id": env.cond["BAIK"]}]}, headers=env.fz)
    check("atomik pengembalian: finalisasi gagal -> 409", r.status_code == 409, f"{r.status_code} {r.text[:120]}")
    h3b = await get_db().asset_holdings.find_one({"company_id": env.cid, "id": h3["id"]}, {"_id": 0})
    after, c1 = await snapshot_counts(env), await counter(env, "BAST_RETURN")
    check("atomik pengembalian: tanpa return/inspeksi/BAST parsial, holding tetap ACTIVE, counter tetap",
          after == before and c1 == c0 and h3b["holding_status"] == "ACTIVE" and h3b["active_lock"] == a3,
          f"{before} -> {after}; counter {c0} -> {c1}; holding {h3b['holding_status']}")
    await get_db().assets.update_one({"company_id": env.cid, "id": a3}, {"$set": {"lifecycle_state": "IN_USE"}})


# ------------------------------------------------------------------ pengembalian
async def t_return(env):
    a1, a2, a3 = [await T.mk_asset(env, f"RT{i}", env.p1) for i in (1, 2, 3)]
    await T.ho_published(env, env.e2, env.p1, [a1, a2, a3])
    h1, h2, h3 = [(await T.holding_of(env, a))["id"] for a in (a1, a2, a3)]
    r = await T.draft_rt(env, env.dr, env.e2, [h1])
    check("pengembalian: Simpan Draft (izin create) -> 201 DRAFT, aset tetap IN_USE",
          r.status_code == 201 and r.json()["doc_state"] == "DRAFT" and await T.state(env, a1) == "IN_USE", r.text[:150])
    draft = r.json()["id"]
    r = await env.c.post(f"/api/asset-returns/{draft}/save-and-publish", json={"employee_id": env.e2, "notes": "rt v2", "items": [
        {"holding_id": h1, "condition_id": env.cond["BAIK"], "accessories": "Charger"}]}, headers=env.fz)
    ok = r.status_code == 200
    check("pengembalian: Simpan & Publish draft existing -> PUBLISHED + BAST-RTN",
          ok and r.json()["doc_state"] == "PUBLISHED" and bool(T.RT_RE.match(r.json().get("bast_number") or "")), r.text[:200])
    c0 = await counter(env, "BAST_RETURN")
    r = await env.c.post("/api/asset-returns/save-and-publish", json={"employee_id": env.e2, "items": [
        {"holding_id": h2, "condition_id": env.cond["BAIK"]}]}, headers=env.fz)
    check("pengembalian: Simpan & Publish form baru (partial 1 dari 2 sisa) -> 201 PUBLISHED",
          r.status_code == 201 and r.json()["doc_state"] == "PUBLISHED" and await counter(env, "BAST_RETURN") == c0 + 1, r.text[:150])
    db = get_db()
    hh = {x["id"]: x for x in await db.asset_holdings.find({"company_id": env.cid, "id": {"$in": [h1, h2, h3]}}, {"_id": 0}).to_list(5)}
    check("partial return: hanya holding terpilih ditutup (active_lock NULL); holding lain tetap ACTIVE",
          hh[h1]["holding_status"] == "CLOSED" and hh[h2]["holding_status"] == "CLOSED" and hh[h1]["active_lock"] is None
          and hh[h3]["holding_status"] == "ACTIVE" and hh[h3]["active_lock"] == a3)
    check("partial return: aset kembali -> PENDING_INSPECTION, aset tidak dikembalikan tetap IN_USE",
          await T.state(env, a1) == "PENDING_INSPECTION" and await T.state(env, a2) == "PENDING_INSPECTION" and await T.state(env, a3) == "IN_USE")
    check("partial return: inspeksi PENDING dibuat untuk tiap aset kembali",
          await n(env, "asset_inspections", asset_id={"$in": [a1, a2]}, inspection_state="PENDING") == 2)


# ------------------------------------------------------------------ pencarian karyawan
async def t_employee_search(env):
    c = env.c

    async def s(h, path="/api/asset-handovers/employee-search", **p):
        r = await c.get(path, params=p, headers=h)
        return r.status_code, (r.json() if r.status_code == 200 else {})

    st, d = await s(env.ga, q=f"KaryE1{RUN}")
    check("employee search: cari berdasarkan nama", st == 200 and [x["id"] for x in d["items"]] == [env.e1], str(d)[:150])
    st, d = await s(env.ga, q=f"E3-{RUN}")
    check("employee search: cari berdasarkan nomor karyawan", st == 200 and [x["id"] for x in d["items"]] == [env.e3], str(d)[:150])
    check("employee search: hasil memuat nomor, nama, proyek aktif",
          d["items"] and d["items"][0]["employee_number"] == f"E3-{RUN}" and d["items"][0]["project_name"])
    st, d = await s(env.ga, q=RUN, limit=2)
    st2, d2 = await s(env.ga, q=RUN, limit=2, page=2)
    check("employee search: limit + pagination (tanpa memuat seluruh karyawan)",
          st == 200 and len(d["items"]) == 2 and d["total"] >= 4 and d["pages"] >= 2 and st2 == 200
          and not ({x["id"] for x in d["items"]} & {x["id"] for x in d2["items"]}), f"{d.get('total')} {d.get('pages')}")
    st, _ = await s(env.ga, q=RUN, limit=500)
    check("employee search: limit dibatasi maksimum (limit=500 -> 422)", st == 422, st)
    st, d = await s(env.r1, q=RUN)
    ids = {x["id"] for x in d.get("items", [])}
    check("employee search 01I: user scope P1 hanya menemukan karyawan P1", st == 200 and ids == {env.e1, env.e2}, str(ids))
    st, d = await s(env.r1, q=f"E3-{RUN}")
    check("employee search 01I: karyawan di luar scope tidak bocor (by nomor)", st == 200 and d["total"] == 0 and not d["items"])
    st, d = await s(env.re, q=RUN)
    check("employee search 01I: scope kosong -> tidak ada karyawan", st == 200 and d["total"] == 0)
    st, d = await s(env.ga, q=f"EB-{RUN}")
    check("employee search: karyawan tenant lain tidak ditemukan", st == 200 and d["total"] == 0)
    st, d = await s(env.emp, q=RUN)
    check("employee search: tanpa izin asset_handover:view -> 403", st == 403, st)
    st, d = await s(env.ga, path="/api/asset-returns/employee-search", q=RUN)
    holders = {x["id"]: x.get("active_holdings") for x in d.get("items", [])}
    check("employee search pengembalian: hanya karyawan pemegang aset aktif (+ jumlah aset)",
          st == 200 and env.e2 in holders and holders[env.e2] >= 1 and env.e4 not in holders, str(holders)[:200])
    st, d = await s(env.r1, path="/api/asset-returns/employee-search", q=f"E3-{RUN}")
    check("employee search pengembalian 01I: pemegang di luar scope tidak bocor", st == 200 and d["total"] == 0)
    o = (await c.get("/api/asset-handovers/options", params={"include_employees": "false"}, headers=env.ga)).json()
    ro = (await c.get("/api/asset-returns/options", params={"include_employees": "false"}, headers=env.ga)).json()
    check("options include_employees=false: daftar karyawan tidak dikirim ke browser", o["employees"] == [] and ro["employees"] == []
          and len(o["assets"]) >= 0 and ro["conditions"])


# ------------------------------------------------------------------ PDF
async def t_pdf_format(env):
    check("format tanggal Indonesia: 2026-09-28 -> 28 September 2026", format_tanggal("2026-09-28") == "28 September 2026")
    check("waktu terbit WIB (UTC+7), termasuk lintas hari",
          format_waktu_wib("2026-09-28 08:34 UTC") == "28 September 2026, 15:34 WIB"
          and format_waktu_wib("2026-12-31 20:00 UTC") == "1 Januari 2027, 03:00 WIB")
    check("alamat kosong disembunyikan; alamat + kota digabung natural",
          company_address({"address": None, "city": ""}) is None and company_address({"address": "-", "city": None}) is None
          and company_address({"address": "Jl. A", "city": "Jakarta"}) == "Jl. A, Jakarta")
    a1 = await T.mk_asset(env, "PDF1", env.p1)
    d = await T.ho_published(env, env.e1, env.p1, [a1])
    b = await get_db().asset_basts.find_one({"company_id": env.cid, "id": d["bast_id"]}, {"_id": 0})
    raw_before = T.json.dumps(b["snapshot"], sort_keys=True, default=str)
    r = await env.c.get(f"/api/asset-basts/{d['bast_id']}/pdf", headers=env.ga)
    txt = T.pdf_text(r.content)
    y, m, dd = TODAY.split("-")
    check("PDF: tanggal BAST format Indonesia", r.status_code == 200 and format_tanggal(TODAY) in txt, format_tanggal(TODAY))
    check("PDF: waktu terbit dalam WIB (bukan UTC mentah)", "WIB" in txt and " UTC" not in txt)
    b2 = await get_db().asset_basts.find_one({"company_id": env.cid, "id": d["bast_id"]}, {"_id": 0})
    check("PDF: snapshot BAST tetap immutable (format hanya saat render)",
          T.json.dumps(b2["snapshot"], sort_keys=True, default=str) == raw_before and "UTC" in b2["snapshot"]["issued_at"])
    await get_db().companies.update_one({"id": env.cid}, {"$set": {"address": None}})
    a2 = await T.mk_asset(env, "PDF2", env.p1)
    d2 = await T.ho_published(env, env.e2, env.p1, [a2])
    r = await env.c.get(f"/api/asset-basts/{d2['bast_id']}/pdf", headers=env.ga)
    txt2 = T.pdf_text(r.content)
    check("PDF: alamat perusahaan kosong -> tidak ada '-' berdiri sendiri di bawah nama perusahaan",
          r.status_code == 200 and "(-) Tj" not in txt2.split("BERITA ACARA")[0])


async def main():
    env = T.Env()
    rep = {"residue": -1, "orphan": -1, "detail": ["cleanup tidak berjalan"]}
    async with dbm.get_engine().connect() as conn:
        dbname = (await conn.execute(sa.text("SELECT DATABASE()"))).scalar()
    if dbname != "hris_dev":
        raise SystemExit(f"DITOLAK: database aktual {dbname!r} bukan hris_dev.")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://t21", timeout=120) as c:
        env.c = c
        try:
            await setup21(env)
            for t in (t_permission, t_handover, t_atomic, t_return, t_employee_search, t_pdf_format):
                try:
                    await t(env)
                except Exception as exc:  # noqa: BLE001
                    import traceback
                    traceback.print_exc()
                    check(f"{t.__name__} (exception)", False, repr(exc)[:200])
        finally:
            rep = await T.cleanup(env)
    await dbm.close_db()
    check("fixture cleanup: residue 0 (hanya data bertanda run ini)", rep["residue"] == 0, str(rep["detail"]))
    check("fixture cleanup: orphan 0", rep["orphan"] == 0, str(rep["detail"]))
    failed = [r for r in T.RESULTS if not r[1]]
    print(f"\n== CP2.1 targeted: {len(T.RESULTS) - len(failed)}/{len(T.RESULTS)} PASS ==")
    print(f"Fixture cleanup: {'PASS' if rep['residue'] == 0 and rep['orphan'] == 0 else 'FAIL'} — residue {rep['residue']}, "
          f"orphan {rep['orphan']} (marker {MARK})")
    return failed


def test_asset_cp2_1():
    assert not asyncio.run(main())


if __name__ == "__main__":
    sys.exit(1 if asyncio.run(main()) else 0)
