"""Phase 2A CP4 - Dokumen Transaksi Aset + Employee Asset 360.

CARA MENJALANKAN (hanya MariaDB development LOKAL `hris_dev`):
    cd backend && bash tests/dev_env_run.sh python3 tests/test_asset_cp4.py

Fixture/guard/cleanup dari test_asset_cp2 (data bertanda run ini saja; residue = 0 & orphan = 0). Penyimpanan file memakai
direktori lokal sementara (ASSET_DOC_LOCAL_STORAGE_DIR) karena R2 sengaja dikosongkan pada environment dev.
Role uji = CUSTOM role dengan izin eksplisit (tanpa nama role sebagai logika).
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

STORE = tempfile.mkdtemp(prefix="cp4_docs_")
os.environ["ASSET_DOC_LOCAL_STORAGE_DIR"] = STORE

import test_asset_cp2 as T  # noqa: E402  (guard hris_dev dijalankan saat import)
import test_asset_cp2_1 as T21  # noqa: E402

import httpx  # noqa: E402
import sqlalchemy as sa  # noqa: E402

import server  # noqa: E402
from app.core import db as dbm  # noqa: E402
from app.core import storage  # noqa: E402
from app.core.db import get_db  # noqa: E402

check, RUN, MARK, TODAY = T.check, T.RUN, T.MARK, T.TODAY
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
DOC_ALL = {f"asset_document:{a}" for a in ("view", "create", "delete")}
VIEWER = ["asset:view", "asset_document:view"]
UPLOADER = VIEWER + ["asset_document:create"]
DELETER = UPLOADER + ["asset_document:delete"]


async def up(env, h, source_type, source_id, doc_type="SUPPORTING_DOCUMENT", name="dok.pdf", data=PDF, **form):
    files = {"file": (name, data, "application/octet-stream")}
    return await env.c.post("/api/asset-documents", headers=h, files=files,
                            data={"source_type": source_type, "source_id": source_id, "document_type": doc_type, **form})


async def lst(env, h, st, sid, hist=False):
    return await env.c.get("/api/asset-documents", params={"source_type": st, "source_id": sid, "include_history": hist}, headers=h)


async def setup4(env):
    await T.setup(env)
    env.v_id, env.v = await T._mk_user(env, await T21._perm_role(env, "mu", VIEWER), env.cid, "docviewer")
    env.u_id, env.u = await T._mk_user(env, await T21._perm_role(env, "nu", UPLOADER), env.cid, "docuploader")
    env.d_id, env.d = await T._mk_user(env, await T21._perm_role(env, "xi", DELETER), env.cid, "docdeleter")
    env.a1, env.a2, env.a3 = [await T.mk_asset(env, f"D{i}", env.p1) for i in (1, 2, 3)]
    env.ho = await T.ho_published(env, env.e1, env.p1, [env.a1, env.a2])
    r = await env.c.post("/api/asset-openings/save-and-publish", headers=env.ga,
                         json={"employee_id": env.e1, "opening_date": TODAY, "items": [{"asset_id": env.a3, "condition_id": env.cond["BAIK"]}]})
    assert r.status_code in (200, 201), r.text
    env.op = r.json()
    env.rt = await T.rt_published(env, env.e1, [env.a1])
    ins = await get_db().asset_inspections.find_one({"company_id": env.cid, "return_id": env.rt["id"]}, {"_id": 0})
    r = await env.c.post(f"/api/asset-inspections/{ins['id']}/complete", headers=env.ga,
                         json={"final_condition_id": env.cond["BAIK"], "result_state": "READY", "completeness": "Lengkap"})
    assert r.status_code == 200, r.text
    r = await T.draft_ho(env, env.ga, env.e2, env.p1, [await T.mk_asset(env, "D4", env.p1)])
    env.ho_draft = r.json()
    env.a5 = await T.mk_asset(env, "D5", env.p2)
    env.ho_p2 = await T.ho_published(env, env.e3, env.p2, [env.a5])


async def t_rbac(env):
    db = get_db()
    perms = {p["key"] for p in await db.permissions.find({}, {"_id": 0}).to_list(3000) if p["key"].startswith("asset_document:")}
    check("permission CP4 terdaftar (asset_document:view/create/delete)", perms == DOC_ALL, str(sorted(perms)))
    for rk, exp in (("ga_admin", DOC_ALL), ("ga_staff", DOC_ALL - {"asset_document:delete"})):
        have = {p["permission_key"] for p in await db.role_permissions.find({"role_key": rk}, {"_id": 0}).to_list(3000)}
        check(f"preset {rk}: izin dokumen sesuai matriks", {k for k in have if k in DOC_ALL} == exp)
    r = await lst(env, env.emp, "HANDOVER", env.ho["id"])
    check("tanpa asset_document:view -> 403 (list)", r.status_code == 403, str(r.status_code))
    r = await up(env, env.v, "HANDOVER", env.ho["id"])
    check("viewer tanpa asset_document:create -> 403 (upload), tanpa data", r.status_code == 403
          and await get_db().asset_documents.count_documents({"company_id": env.cid}) == 0, str(r.status_code))


async def t_upload(env):
    snap_before = (await get_db().asset_basts.find_one({"id": env.ho["bast_id"]}, {"_id": 0}))["snapshot"]
    r = await up(env, env.u, "HANDOVER", env.ho["id"], "HANDOVER_REPORT", "berita acara.pdf", PDF, asset_id=env.a1,
                 document_date=TODAY, notes="Surat serah terima")
    d = r.json()
    env.doc_ho = d
    check("upload PDF ke Penyerahan PUBLISHED (custom role uploader) -> 201, relasi employee/BAST/aset benar",
          r.status_code == 201 and d["employee_id"] == env.e1 and d["bast_id"] == env.ho["bast_id"] and d["asset_id"] == env.a1
          and d["doc_status"] == "ACTIVE" and "storage_path" not in d, r.text[:200])
    r = await up(env, env.u, "RETURN", env.rt["id"], "CONDITION_PHOTO", "foto.jpg", JPG)
    env.doc_rt = r.json()
    check("upload JPG ke Pengembalian -> 201 (employee = yang mengembalikan)", r.status_code == 201 and env.doc_rt["employee_id"] == env.e1, r.text[:160])
    r = await up(env, env.u, "OPENING_EXISTING", env.op["id"], "OTHER", "kondisi.png", PNG)
    env.doc_op = r.json()
    check("upload PNG ke Saldo Awal (OPENING_EXISTING) -> 201", r.status_code == 201 and env.doc_op["bast_id"] == env.op["bast_id"], r.text[:160])
    r = await up(env, env.u, "HANDOVER", env.ho_draft["id"], "SUPPORTING_DOCUMENT", "draft.jpeg", JPG)
    check("upload dokumen pendukung ke Penyerahan DRAFT -> 201", r.status_code == 201, r.text[:160])
    cases = [("txt ditolak", dict(name="a.txt", data=b"hello"), 422), ("ekstensi .pdf isi PNG ditolak (magic bytes)", dict(name="a.pdf", data=PNG), 422),
             ("file > 10 MB ditolak", dict(name="big.pdf", data=PDF + b"0" * (10 * 1024 * 1024)), 413),
             ("file kosong ditolak", dict(name="e.pdf", data=b""), 422),
             ("aset bukan bagian transaksi ditolak", dict(asset_id=env.a3), 422),
             ("jenis dokumen tidak valid ditolak", dict(doc_type="KTP"), 422)]
    n0 = await get_db().asset_documents.count_documents({"company_id": env.cid})
    for label, kw, code in cases:
        r = await up(env, env.u, "HANDOVER", env.ho["id"], **kw)
        check(f"validasi: {label} -> {code}", r.status_code == code, f"{r.status_code} {r.text[:100]}")
    check("validasi gagal tidak menulis metadata / file", await get_db().asset_documents.count_documents({"company_id": env.cid}) == n0
          and sum(1 for _ in pathlib.Path(STORE).rglob("*.*")) == n0)
    r = await up(env, env.u, "HANDOVER", env.ho_draft["id"], "SIGNED_BAST", "ttd.pdf")
    check("SIGNED_BAST pada transaksi DRAFT (BAST belum terbit) -> 409", r.status_code == 409, str(r.status_code))
    snap_after = (await get_db().asset_basts.find_one({"id": env.ho["bast_id"]}, {"_id": 0}))["snapshot"]
    check("upload dokumen tidak mengubah immutable BAST snapshot", snap_before == snap_after)


async def t_list_download(env):
    r = await lst(env, env.v, "HANDOVER", env.ho["id"])
    b = r.json()
    check("list per transaksi (viewer): 1 dokumen aktif + label jenis/uploader/aset", r.status_code == 200 and b["active_count"] == 1
          and b["items"][0]["document_type_label"] == "Berita Acara / Surat Serah Terima" and b["items"][0]["asset_code"]
          and b["items"][0]["uploaded_by_name"] and b["can"] == {"view": True, "create": False, "delete": False}, str(b)[:200])
    r = await env.c.get(f"/api/asset-documents/{env.doc_ho['id']}/file", headers=env.v)
    check("view inline: isi file identik + Content-Disposition inline", r.status_code == 200 and r.content == PDF
          and r.headers["content-disposition"].startswith("inline") and r.headers["content-type"].startswith("application/pdf"))
    r = await env.c.get(f"/api/asset-documents/{env.doc_rt['id']}/file", params={"download": True}, headers=env.v)
    check("download: attachment + isi JPG identik", r.status_code == 200 and r.content == JPG and r.headers["content-disposition"].startswith("attachment"))


async def t_quota(env):
    have = (await lst(env, env.u, "HANDOVER", env.ho["id"])).json()["active_count"]
    codes = [(await up(env, env.u, "HANDOVER", env.ho["id"], name=f"q{i}.pdf")).status_code for i in range(10 - have)]
    r = await up(env, env.u, "HANDOVER", env.ho["id"], name="q11.pdf")
    check("maksimal 10 dokumen aktif per transaksi: ke-11 -> 409", all(c == 201 for c in codes) and r.status_code == 409, f"{codes} {r.status_code}")
    env.quota_ids = [x["id"] for x in (await lst(env, env.u, "HANDOVER", env.ho["id"])).json()["items"] if x["file_name"].startswith("q")]


async def t_delete(env):
    did = env.quota_ids[0]
    r = await env.c.delete(f"/api/asset-documents/{did}", headers=env.u)
    check("hapus tanpa asset_document:delete -> 403", r.status_code == 403, str(r.status_code))
    r = await env.c.delete(f"/api/asset-documents/{did}", params={"reason": "Salah unggah"}, headers=env.d)
    row = await get_db().asset_documents.find_one({"id": did}, {"_id": 0})
    check("soft delete (custom role deleter): baris tetap ada, DELETED + deleted_by/at/reason", r.status_code == 200 and row
          and row["doc_status"] == "DELETED" and row["deleted_by"] == env.d_id and row["delete_reason"] == "Salah unggah")
    check("soft delete: file fisik tidak dihapus", (pathlib.Path(STORE) / row["storage_path"]).is_file())
    act = [x["id"] for x in (await lst(env, env.u, "HANDOVER", env.ho["id"])).json()["items"]]
    hist = {x["id"]: x["doc_status"] for x in (await lst(env, env.u, "HANDOVER", env.ho["id"], True)).json()["items"]}
    check("dokumen terhapus tidak tampil sebagai aktif; tampil di riwayat (include_history)", did not in act and hist.get(did) == "DELETED")
    r = await env.c.get(f"/api/asset-documents/{did}/file", headers=env.v)
    check("file dokumen terhapus -> 404", r.status_code == 404, str(r.status_code))
    r = await env.c.delete(f"/api/asset-documents/{did}", headers=env.d)
    check("hapus ulang dokumen DELETED -> 409", r.status_code == 409, str(r.status_code))
    r = await up(env, env.u, "HANDOVER", env.ho["id"], name="after-delete.pdf")
    check("setelah soft delete kuota tersedia lagi (hanya ACTIVE dihitung)", r.status_code == 201, str(r.status_code))
    logs = await get_db().audit_logs.find({"record_id": did}, {"_id": 0}).to_list(10)
    check("audit trail: upload + delete tercatat", {"upload", "delete"} <= {x.get("action") for x in logs}, str([x.get("action") for x in logs]))


async def t_signed(env):
    snap_before = (await get_db().asset_basts.find_one({"id": env.op["bast_id"]}, {"_id": 0}))["snapshot"]
    r = await up(env, env.u, "OPENING_EXISTING", env.op["id"], "SIGNED_BAST", "bast-ttd-v1.pdf")
    v1 = r.json()
    check("SIGNED_BAST v1 setelah PUBLISHED -> 201 (version 1)", r.status_code == 201 and v1["version_no"] == 1, r.text[:160])
    r = await up(env, env.u, "OPENING_EXISTING", env.op["id"], "SIGNED_BAST", "bast-ttd-dup.pdf")
    check("SIGNED_BAST kedua via upload biasa -> 409 (gunakan Ganti Versi)", r.status_code == 409, str(r.status_code))
    r = await env.c.delete(f"/api/asset-documents/{v1['id']}", headers=env.d)
    check("SIGNED_BAST tidak dapat dihapus -> 409", r.status_code == 409, str(r.status_code))
    r = await env.c.post(f"/api/asset-documents/{v1['id']}/replace", headers=env.u, files={"file": ("bast-ttd-v2.pdf", PDF, "application/pdf")})
    v2 = r.json()
    old = await get_db().asset_documents.find_one({"id": v1["id"]}, {"_id": 0})
    check("Ganti Versi: v2 ACTIVE (version 2, replaces v1); v1 SUPERSEDED (tidak dihapus, superseded_by = v2)",
          r.status_code == 201 and v2["version_no"] == 2 and v2["replaces_id"] == v1["id"] and old["doc_status"] == "SUPERSEDED"
          and old["superseded_by"] == v2["id"] and (pathlib.Path(STORE) / old["storage_path"]).is_file(), r.text[:160])
    r = await env.c.post(f"/api/asset-documents/{v1['id']}/replace", headers=env.u, files={"file": ("x.pdf", PDF, "application/pdf")})
    check("Ganti versi dari versi SUPERSEDED -> 409", r.status_code == 409, str(r.status_code))
    r = await env.c.post(f"/api/asset-documents/{env.doc_op['id']}/replace", headers=env.u, files={"file": ("x.pdf", PDF, "application/pdf")})
    check("Ganti versi untuk dokumen non-SIGNED_BAST -> 422", r.status_code == 422, str(r.status_code))
    hist = (await lst(env, env.v, "OPENING_EXISTING", env.op["id"], True)).json()["items"]
    check("riwayat versi SIGNED_BAST dapat diaudit (v1 SUPERSEDED + v2 ACTIVE)",
          sorted((x["version_no"], x["doc_status"]) for x in hist if x["document_type"] == "SIGNED_BAST") == [(1, "SUPERSEDED"), (2, "ACTIVE")])
    logs = await get_db().audit_logs.find({"record_id": v2["id"]}, {"_id": 0}).to_list(5)
    check("audit trail: replace tercatat", "replace" in {x.get("action") for x in logs})
    snap_after = (await get_db().asset_basts.find_one({"id": env.op["bast_id"]}, {"_id": 0}))["snapshot"]
    check("SIGNED_BAST & penggantian tidak mengubah BAST snapshot", snap_before == snap_after)
    env.v2 = v2


async def t_scope(env):
    r = await up(env, env.ga, "HANDOVER", env.ho_p2["id"], name="p2.pdf")
    env.doc_p2 = r.json()
    check("setup: dokumen pada Penyerahan project P2", r.status_code == 201, r.text[:120])
    r = await lst(env, env.r1, "HANDOVER", env.ho_p2["id"])
    check("01I: list dokumen transaksi di luar scope -> 404", r.status_code == 404, str(r.status_code))
    r = await up(env, env.r1, "HANDOVER", env.ho_p2["id"], name="x.pdf")
    check("01I: upload ke transaksi di luar scope -> 404", r.status_code == 404, str(r.status_code))
    r = await env.c.get(f"/api/asset-documents/{env.doc_p2['id']}/file", headers=env.r1)
    check("01I: file dokumen di luar scope -> 404 generik", r.status_code == 404, str(r.status_code))
    r = await env.c.get(f"/api/employees/{env.e3}/asset-360", headers=env.r1)
    check("01I: Asset 360 karyawan di luar scope -> 404", r.status_code == 404, str(r.status_code))
    r = await env.c.get(f"/api/asset-documents/{env.doc_ho['id']}/file", headers=env.r1)
    check("01I: dokumen dalam scope tetap dapat diakses (restricted P1)", r.status_code == 200, str(r.status_code))
    for path in (f"/api/asset-documents/{env.doc_ho['id']}/file", f"/api/employees/{env.e1}/asset-360"):
        r = await env.c.get(path, headers=env.adminb)
        check(f"tenant lain ditolak: {path.split('/')[2]}", r.status_code in (403, 404), str(r.status_code))
    r = await lst(env, env.adminb, "HANDOVER", env.ho["id"])
    check("tenant lain: list dokumen transaksi -> 403/404", r.status_code in (403, 404), str(r.status_code))


async def t_360(env):
    r = await env.c.get(f"/api/employees/{env.e1}/asset-360", headers=env.v)
    b = r.json()
    cur = {x["asset_id"]: x for x in b.get("current", [])}
    check("360 Aset Saat Ini: a2 (Penyerahan) + a3 (Saldo Awal); a1 sudah dikembalikan tidak tampil",
          r.status_code == 200 and set(cur) == {env.a2, env.a3}, str(list(cur))[:120])
    check("360 Aset Saat Ini: sumber holding + nomor BAST + kategori/serial/proyek",
          cur[env.a2]["source_type"] == "HANDOVER" and cur[env.a2]["bast_number"] == env.ho["bast_number"]
          and cur[env.a3]["source_type"] == "OPENING_EXISTING" and cur[env.a3]["bast_number"] == env.op["bast_number"]
          and cur[env.a2]["category_name"] and cur[env.a2]["serial_number"] and cur[env.a2]["project_name"], str(cur.get(env.a2))[:200])
    ev = sorted((x["event_type"], x["asset_id"]) for x in b["history"])
    exp = sorted([("HANDOVER", env.a1), ("HANDOVER", env.a2), ("OPENING_EXISTING", env.a3), ("RETURN", env.a1), ("INSPECTION", env.a1)])
    check("360 Histori: kronologi Saldo Awal + Penyerahan + Pengembalian + Pemeriksaan", ev == exp, str(ev))
    ins = next(x for x in b["history"] if x["event_type"] == "INSPECTION")
    check("360 Histori Pemeriksaan: kondisi sebelum/sesudah + hasil + nomor BAST-RTN", ins["condition_before"] and ins["condition_after"]
          and ins["result_state"] == "READY" and ins["bast_number"] == env.rt["bast_number"], str(ins)[:200])
    docs = b["documents"] or []
    ids = {x["id"] for x in docs}
    srcs = {x["source_type"] for x in docs}
    check("360 Dokumen Aset: dokumen dari 3 transaksi otomatis tampil (tanpa upload ulang)", srcs == {"HANDOVER", "RETURN", "OPENING_EXISTING"}
          and {env.doc_ho["id"], env.doc_rt["id"], env.doc_op["id"], env.v2["id"]} <= ids, str(srcs))
    check("360 Dokumen Aset: DELETED tidak tampil; SIGNED_BAST SUPERSEDED tetap tampil sebagai riwayat versi",
          env.quota_ids[0] not in ids and any(x["doc_status"] == "SUPERSEDED" for x in docs))
    rows = await get_db().asset_documents.count_documents({"company_id": env.cid})
    files = sum(1 for _ in pathlib.Path(STORE).rglob("*.*"))
    same = {x["id"] for x in (await lst(env, env.v, "HANDOVER", env.ho["id"])).json()["items"]} <= ids
    check("file fisik disimpan sekali: jumlah objek = jumlah baris metadata; profil membaca baris yang sama", rows == files and same,
          f"rows={rows} files={files}")
    rk = await T21._perm_role(env, "omi", ["asset:view"])
    _uid, h = await T._mk_user(env, rk, env.cid, "assetonly")
    r = await env.c.get(f"/api/employees/{env.e1}/asset-360", headers=h)
    check("360 tanpa asset_document:view: aset tampil, dokumen disembunyikan (null)", r.status_code == 200 and r.json()["documents"] is None
          and len(r.json()["current"]) == 2)
    r = await env.c.get(f"/api/employees/{env.e1}/asset-360", headers=env.emp)
    check("360 tanpa asset:view -> 403", r.status_code == 403, str(r.status_code))


async def cp4_orphans() -> int:
    async with dbm.get_engine().connect() as conn:
        q = ("SELECT COUNT(*) FROM asset_documents d LEFT JOIN asset_handovers h ON h.id = d.source_id LEFT JOIN asset_returns r"
             " ON r.id = d.source_id LEFT JOIN asset_openings o ON o.id = d.source_id WHERE h.id IS NULL AND r.id IS NULL AND o.id IS NULL")
        return (await conn.execute(sa.text(q))).scalar() or 0


async def main():
    env = T.Env()
    rep = {"residue": -1, "orphan": -1, "detail": ["cleanup tidak berjalan"]}
    async with dbm.get_engine().connect() as conn:
        dbname = (await conn.execute(sa.text("SELECT DATABASE()"))).scalar()
    if dbname != "hris_dev":
        raise SystemExit(f"DITOLAK: database aktual {dbname!r} bukan hris_dev.")
    check("dev: R2 tidak dikonfigurasi, penyimpanan lokal sementara dipakai", not storage.storage_configured())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://t04", timeout=300) as c:
        env.c = c
        try:
            await setup4(env)
            for t in (t_rbac, t_upload, t_list_download, t_quota, t_delete, t_signed, t_scope, t_360):
                try:
                    await t(env)
                except Exception as exc:  # noqa: BLE001
                    import traceback
                    traceback.print_exc()
                    check(f"{t.__name__} (exception)", False, repr(exc)[:200])
        finally:
            rep = await T.cleanup(env)
    orphan4 = await cp4_orphans()
    await dbm.close_db()
    shutil.rmtree(STORE, ignore_errors=True)
    check("fixture cleanup: residue 0 (hanya data bertanda run ini)", rep["residue"] == 0, str(rep["detail"]))
    check("fixture cleanup: orphan 0 (CP2 + CP4 dokumen)", rep["orphan"] == 0 and orphan4 == 0, f"{rep['detail']} cp4={orphan4}")
    failed = [r for r in T.RESULTS if not r[1]]
    print(f"\n== CP4 targeted: {len(T.RESULTS) - len(failed)}/{len(T.RESULTS)} PASS ==")
    print(f"Fixture cleanup: {'PASS' if rep['residue'] == 0 and rep['orphan'] == 0 and orphan4 == 0 else 'FAIL'} — residue {rep['residue']}, "
          f"orphan {rep['orphan'] + orphan4} (marker {MARK})")
    return failed


def test_asset_cp4():
    assert not asyncio.run(main())


if __name__ == "__main__":
    sys.exit(1 if asyncio.run(main()) else 0)
