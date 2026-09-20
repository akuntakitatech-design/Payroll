"""Test isolasi tenant — Tahap 1 penguatan multi-tenancy.

CARA MENJALANKAN
----------------
    cd /app/backend && python3 tests/test_tenant_isolation.py     # mandiri
    cd /app/backend && python3 -m pytest tests/test_tenant_isolation.py -v

KEAMANAN TEST
-------------
Test ini **tidak pernah** menyentuh MariaDB produksi:

* engine SQLite sementara dibuat di berkas temporer lalu dihapus;
* ``app.core.db._engine`` ditunjuk ke engine tersebut hanya di dalam proses
  test (tidak ada berkas ``.env`` yang diubah);
* ``settings.READ_ONLY`` dimatikan hanya di memori proses test, sehingga
  operasi tulis dapat diuji pada SQLite tanpa melonggarkan pengaman apa pun
  pada aplikasi yang berjalan.

Test ditulis memakai ``asyncio.run`` alih-alih ``pytest-asyncio`` agar tidak
menambah dependency baru pada proyek.
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import tempfile
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.core import db as dbm  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.db import GLOBAL_COLLECTIONS, NO_ID, Collection  # noqa: E402
from app.core.tenancy import (  # noqa: E402
    CrossTenantDenied,
    TenantCollection,
    TenantContextMissing,
    get_tenant_db,
    is_tenant_collection,
    unscoped_db,
)

COMPANY_A = "11111111-1111-4111-8111-111111111111"
COMPANY_B = "22222222-2222-4222-8222-222222222222"

_tmp_path: str | None = None


# ==========================================================================
# Penyiapan basis data uji
# ==========================================================================
async def _setup_database() -> None:
    """Bangun SQLite sementara berisi dua perusahaan dan datanya."""
    global _tmp_path

    # Matikan pengaman read-only HANYA di dalam proses test ini.
    settings.READ_ONLY = False

    fd, _tmp_path = tempfile.mkstemp(suffix=".sqlite", prefix="tenant_iso_")
    os.close(fd)

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{_tmp_path}",
        json_serializer=dbm.json_dumps,
    )
    dbm._engine = engine  # arahkan adapter ke basis data uji

    async with engine.begin() as conn:
        await conn.run_sync(dbm.metadata.create_all)

    raw = dbm.Database()

    # -- tabel global: dua perusahaan --------------------------------------
    await raw.companies.insert_one(
        {"id": COMPANY_A, "code": "AAA", "name": "PT Tenant A", "status": "active"}
    )
    await raw.companies.insert_one(
        {"id": COMPANY_B, "code": "BBB", "name": "PT Tenant B", "status": "active"}
    )

    # -- tabel global: pengguna + role lintas perusahaan (pola super admin) -
    await raw.users.insert_one(
        {"id": "user-a", "email": "a@a.id", "full_name": "User A", "status": "active"}
    )
    await raw.users.insert_one(
        {"id": "user-super", "email": "s@s.id", "full_name": "Super", "status": "active"}
    )
    await raw.user_company_roles.insert_one(
        {"id": "ucr-a", "user_id": "user-a", "company_id": COMPANY_A,
         "role_key": "hr_admin", "status": "active"}
    )
    # company_id NULL = role global, semantik existing untuk super_admin
    await raw.user_company_roles.insert_one(
        {"id": "ucr-super", "user_id": "user-super", "company_id": None,
         "role_key": "super_admin", "status": "active"}
    )

    # -- data tenant -------------------------------------------------------
    await raw.employees.insert_one(
        {"id": "emp-a1", "company_id": COMPANY_A, "full_name": "Budi A",
         "nik": "111", "status": "active"}
    )
    await raw.employees.insert_one(
        {"id": "emp-a2", "company_id": COMPANY_A, "full_name": "Citra A",
         "nik": "112", "status": "active"}
    )
    await raw.employees.insert_one(
        {"id": "emp-b1", "company_id": COMPANY_B, "full_name": "Dedi B",
         "nik": "221", "status": "active"}
    )
    await raw.departments.insert_one(
        {"id": "dep-a", "company_id": COMPANY_A, "code": "OPS", "name": "Operasional",
         "status": "active"}
    )
    await raw.departments.insert_one(
        {"id": "dep-b", "company_id": COMPANY_B, "code": "OPS", "name": "Operasional B",
         "status": "active"}
    )
    await raw.payroll_runs.insert_one(
        {"id": "run-a", "company_id": COMPANY_A, "year": 2026, "month": 9,
         "run_status": "draft", "status": "active"}
    )
    await raw.payroll_runs.insert_one(
        {"id": "run-b", "company_id": COMPANY_B, "year": 2026, "month": 9,
         "run_status": "draft", "status": "active"}
    )


async def _teardown_database() -> None:
    if dbm._engine is not None:
        await dbm._engine.dispose()
    dbm._engine = None
    if _tmp_path and os.path.exists(_tmp_path):
        os.remove(_tmp_path)


# ==========================================================================
# 1. Tenant A dapat membaca datanya sendiri
# ==========================================================================
async def _t01_tenant_membaca_data_sendiri() -> None:
    a = get_tenant_db(COMPANY_A)

    rows = await a.employees.find({"status": "active"}, NO_ID).to_list(100)
    assert len(rows) == 2, f"tenant A harus melihat 2 karyawan, dapat {len(rows)}"
    assert {r["full_name"] for r in rows} == {"Budi A", "Citra A"}

    one = await a.employees.find_one({"id": "emp-a1"}, NO_ID)
    assert one is not None and one["full_name"] == "Budi A"

    total = await a.employees.count_documents({"status": "active"})
    assert total == 2, f"count_documents harus 2, dapat {total}"

    niks = await a.employees.distinct("nik", {"status": "active"})
    assert set(niks) == {"111", "112"}, f"distinct bocor: {niks}"


# ==========================================================================
# 2. Tenant A TIDAK dapat membaca data Tenant B
# ==========================================================================
async def _t02_tenant_tidak_membaca_tenant_lain() -> None:
    a = get_tenant_db(COMPANY_A)

    # Mengambil record tenant B berdasarkan id langsung -> tidak ditemukan
    leaked = await a.employees.find_one({"id": "emp-b1"}, NO_ID)
    assert leaked is None, "KEBOCORAN: tenant A dapat membaca karyawan tenant B"

    # find tanpa filter apa pun -> hanya data sendiri
    semua = await a.employees.find({}, NO_ID).to_list(100)
    assert len(semua) == 2, f"find kosong harus tetap ter-scope, dapat {len(semua)}"
    assert all(r["company_id"] == COMPANY_A for r in semua)

    # count seluruh tabel -> hanya data sendiri (bukan 3)
    assert await a.employees.count_documents({}) == 2

    # distinct seluruh tabel -> tidak memuat nilai tenant B
    niks = await a.employees.distinct("nik", {})
    assert "221" not in niks, f"KEBOCORAN lewat distinct: {niks}"

    # $or tidak boleh dipakai untuk melompat keluar dari scope
    via_or = await a.employees.find(
        {"$or": [{"id": "emp-b1"}, {"nik": "221"}]}, NO_ID
    ).to_list(100)
    assert via_or == [], f"KEBOCORAN lewat $or: {via_or}"

    # $in juga tidak boleh bocor
    via_in = await a.employees.find({"id": {"$in": ["emp-a1", "emp-b1"]}}, NO_ID).to_list(100)
    assert len(via_in) == 1 and via_in[0]["id"] == "emp-a1", f"KEBOCORAN lewat $in: {via_in}"


# ==========================================================================
# 3. Tenant A TIDAK dapat update data Tenant B
# ==========================================================================
async def _t03_tenant_tidak_update_tenant_lain() -> None:
    a = get_tenant_db(COMPANY_A)
    raw = dbm.Database()

    res = await a.employees.update_one(
        {"id": "emp-b1"}, {"$set": {"full_name": "DIBAJAK"}}
    )
    assert res.matched_count == 0, "KEBOCORAN: update menyentuh record tenant B"

    korban = await raw.employees.find_one({"id": "emp-b1"}, NO_ID)
    assert korban["full_name"] == "Dedi B", "KEBOCORAN: data tenant B berubah"

    # update_many massal juga tidak boleh menyeberang
    await a.employees.update_many({}, {"$set": {"religion": "X"}})
    korban = await raw.employees.find_one({"id": "emp-b1"}, NO_ID)
    assert korban.get("religion") != "X", "KEBOCORAN: update_many menyentuh tenant B"

    # milik sendiri tetap bisa di-update (tidak over-blocking)
    sendiri = await a.employees.update_one(
        {"id": "emp-a1"}, {"$set": {"full_name": "Budi A Revisi"}}
    )
    assert sendiri.matched_count == 1, "regresi: update data sendiri gagal"

    # find_one_and_update juga ter-scope
    hasil = await a.employees.find_one_and_update(
        {"id": "emp-b1"}, {"$set": {"full_name": "DIBAJAK2"}}
    )
    assert hasil is None, "KEBOCORAN: find_one_and_update menyentuh tenant B"


# ==========================================================================
# 4. Tenant A TIDAK dapat delete data Tenant B
# ==========================================================================
async def _t04_tenant_tidak_delete_tenant_lain() -> None:
    a = get_tenant_db(COMPANY_A)
    raw = dbm.Database()

    res = await a.employees.delete_one({"id": "emp-b1"})
    assert res.deleted_count == 0, "KEBOCORAN: delete_one menghapus record tenant B"
    assert await raw.employees.find_one({"id": "emp-b1"}, NO_ID) is not None

    # delete_many massal hanya boleh mengenai data sendiri
    res = await a.departments.delete_many({})
    assert res.deleted_count == 1, f"delete_many harus 1 (milik A), dapat {res.deleted_count}"
    assert await raw.departments.find_one({"id": "dep-b"}, NO_ID) is not None, \
        "KEBOCORAN: delete_many menghapus departemen tenant B"


# ==========================================================================
# 5. Insert tenant otomatis mendapat company_id yang benar
# ==========================================================================
async def _t05_insert_otomatis_dapat_company_id() -> None:
    a = get_tenant_db(COMPANY_A)
    raw = dbm.Database()

    # insert_one TANPA menyebut company_id sama sekali
    await a.employees.insert_one(
        {"id": "emp-a3", "full_name": "Eka A", "nik": "113", "status": "active"}
    )
    baru = await raw.employees.find_one({"id": "emp-a3"}, NO_ID)
    assert baru["company_id"] == COMPANY_A, \
        f"company_id tidak disuntikkan: {baru['company_id']}"

    # insert_many juga
    await a.employees.insert_many([
        {"id": "emp-a4", "full_name": "Fajar A", "nik": "114", "status": "active"},
        {"id": "emp-a5", "full_name": "Gita A", "nik": "115", "status": "active"},
    ])
    banyak = await raw.employees.find({"id": {"$in": ["emp-a4", "emp-a5"]}}, NO_ID).to_list(10)
    assert len(banyak) == 2
    assert all(r["company_id"] == COMPANY_A for r in banyak)

    # upsert yang membuat baris baru juga harus mendapat company_id
    await a.payroll_runs.update_one(
        {"id": "run-a-baru"},
        {"$set": {"year": 2026, "month": 10, "run_status": "draft", "status": "active"}},
        upsert=True,
    )
    hasil = await raw.payroll_runs.find_one({"id": "run-a-baru"}, NO_ID)
    assert hasil is not None, "upsert gagal membuat baris"
    assert hasil["company_id"] == COMPANY_A, \
        f"upsert tidak menyuntikkan company_id: {hasil['company_id']}"

    # bersihkan agar test lain tidak terganggu
    await raw.employees.delete_many({"id": {"$in": ["emp-a3", "emp-a4", "emp-a5"]}})
    await raw.payroll_runs.delete_many({"id": "run-a-baru"})


# ==========================================================================
# 6. Akses tenant-scoped tanpa konteks perusahaan DITOLAK (fail-safe)
# ==========================================================================
async def _t06_tanpa_konteks_ditolak() -> None:
    for kosong in (None, "", 0):
        try:
            get_tenant_db(kosong)
        except TenantContextMissing as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError(
                f"BAHAYA: konteks kosong ({kosong!r}) tidak ditolak — "
                "ini akan membuka data seluruh perusahaan"
            )

    # TenantCollection langsung pun menolak
    try:
        TenantCollection("employees", None)
    except TenantContextMissing:
        pass
    else:
        raise AssertionError("BAHAYA: TenantCollection menerima company_id kosong")


# ==========================================================================
# 7. GLOBAL_COLLECTIONS tetap bekerja seperti existing
# ==========================================================================
async def _t07_global_collections_tetap_normal() -> None:
    a = get_tenant_db(COMPANY_A)

    # objek yang diberikan untuk tabel global BUKAN TenantCollection
    assert type(a.users) is Collection, "tabel global tidak boleh di-scope"
    assert type(a.companies) is Collection
    assert type(a.roles) is Collection
    assert type(a.user_company_roles) is Collection
    # sedangkan tabel tenant harus ter-scope
    assert isinstance(a.employees, TenantCollection)
    assert isinstance(a.payroll_runs, TenantCollection)

    # Tetap dapat melihat SELURUH perusahaan (dibutuhkan auth & super admin)
    perusahaan = await a.companies.find({}, NO_ID).to_list(10)
    assert len(perusahaan) == 2, f"tabel global companies ter-filter: {len(perusahaan)}"

    pengguna = await a.users.find({}, NO_ID).to_list(10)
    assert len(pengguna) == 2, "tabel global users ter-filter"

    # nama tidak dikenal -> fail-closed (dianggap tenant, tetap ter-scope)
    assert is_tenant_collection("tabel_baru_yang_belum_terdaftar") is True
    for nama in GLOBAL_COLLECTIONS:
        assert is_tenant_collection(nama) is False, f"{nama} seharusnya global"


# ==========================================================================
# 8. Ganti perusahaan (switch-company) tetap bekerja
# ==========================================================================
async def _t08_switch_company_bekerja() -> None:
    a = get_tenant_db(COMPANY_A)
    b = get_tenant_db(COMPANY_B)

    milik_a = await a.employees.find({}, NO_ID).to_list(100)
    milik_b = await b.employees.find({}, NO_ID).to_list(100)

    assert all(r["company_id"] == COMPANY_A for r in milik_a)
    assert all(r["company_id"] == COMPANY_B for r in milik_b)
    assert len(milik_b) == 1 and milik_b[0]["full_name"] == "Dedi B"

    # kedua scope tidak saling mencemari
    ids_a = {r["id"] for r in milik_a}
    ids_b = {r["id"] for r in milik_b}
    assert not (ids_a & ids_b), "scope tenant saling bocor setelah berganti perusahaan"

    # tenant B juga dapat melakukan CRUD atas datanya sendiri
    res = await b.employees.update_one({"id": "emp-b1"}, {"$set": {"job_title": "Staf"}})
    assert res.matched_count == 1, "regresi: tenant B gagal update data sendiri"


# ==========================================================================
# 9. Alur super_admin existing tidak rusak
# ==========================================================================
async def _t09_super_admin_tidak_rusak() -> None:
    raw = dbm.Database()

    # Semantik existing: company_id NULL pada user_company_roles = role global.
    # Tabel ini global sehingga TIDAK di-scope, dan tetap terbaca lewat tdb.
    a = get_tenant_db(COMPANY_A)
    global_roles = await a.user_company_roles.find(
        {"user_id": "user-super", "company_id": None}, NO_ID
    ).to_list(10)
    assert len(global_roles) == 1, "semantik company_id NULL (super admin) rusak"
    assert global_roles[0]["role_key"] == "super_admin"

    # Super admin harus tetap dapat melihat seluruh perusahaan
    semua = await a.companies.find({"status": "active"}, NO_ID).to_list(10)
    assert len(semua) == 2

    # Bypass lintas-tenant yang eksplisit tetap tersedia untuk kode server
    lintas = unscoped_db("uji audit isolasi tenant", actor_user_id="user-super")
    total = await lintas.employees.count_documents({})
    assert total >= 3, "bypass eksplisit harus melihat seluruh tenant"

    # ...dan wajib menyertakan alasan
    try:
        unscoped_db("")
    except ValueError:
        pass
    else:
        raise AssertionError("unscoped_db menerima alasan kosong")

    assert await raw.companies.count_documents({}) == 2


# ==========================================================================
# 10. Alur payroll existing tetap bekerja
# ==========================================================================
async def _t10_payroll_tetap_bekerja() -> None:
    a = get_tenant_db(COMPANY_A)
    b = get_tenant_db(COMPANY_B)

    runs_a = await a.payroll_runs.find({"year": 2026}, NO_ID).to_list(50)
    assert len(runs_a) == 1 and runs_a[0]["id"] == "run-a"

    # payroll tenant lain tidak terlihat maupun bisa diubah
    assert await a.payroll_runs.find_one({"id": "run-b"}, NO_ID) is None
    res = await a.payroll_runs.update_one({"id": "run-b"}, {"$set": {"run_status": "paid"}})
    assert res.matched_count == 0, "KEBOCORAN: payroll tenant B dapat diubah"

    # siklus payroll sendiri berjalan normal (buat -> ubah -> baca -> hapus)
    await a.payroll_items.insert_one(
        {"id": "item-a1", "run_id": "run-a", "employee_id": "emp-a1",
         "full_name": "Budi A", "status": "active"}
    )
    items = await a.payroll_items.find({"run_id": "run-a"}, NO_ID).to_list(50)
    assert len(items) == 1 and items[0]["company_id"] == COMPANY_A

    await a.payroll_runs.update_one({"id": "run-a"}, {"$set": {"run_status": "approved"}})
    run = await a.payroll_runs.find_one({"id": "run-a"}, NO_ID)
    assert run["run_status"] == "approved", "regresi: transisi status payroll gagal"

    # payroll tenant B tetap utuh
    run_b = await b.payroll_runs.find_one({"id": "run-b"}, NO_ID)
    assert run_b["run_status"] == "draft", "KEBOCORAN: payroll tenant B ikut berubah"

    await a.payroll_items.delete_many({"run_id": "run-a"})


# ==========================================================================
# 11. REGRESI KEAMANAN: company_id dari klien tidak boleh menang
# ==========================================================================
async def _t11_company_id_klien_tidak_menang() -> None:
    a = get_tenant_db(COMPANY_A)
    raw = dbm.Database()

    # --- lewat filter query (meniru query parameter / request body) -------
    for operasi in ("find", "find_one", "count_documents"):
        try:
            target = getattr(a.employees, operasi)
            hasil = target({"company_id": COMPANY_B})
            if hasattr(hasil, "to_list"):
                await hasil.to_list(10)
            else:
                await hasil
        except CrossTenantDenied as exc:
            assert exc.status_code == 403
        else:
            raise AssertionError(
                f"BAHAYA: {operasi} menerima company_id tenant B dari klien"
            )

    # --- lewat body insert -------------------------------------------------
    try:
        await a.employees.insert_one(
            {"id": "emp-bajakan", "company_id": COMPANY_B, "full_name": "Penyusup"}
        )
    except CrossTenantDenied:
        pass
    else:
        raise AssertionError("BAHAYA: insert dengan company_id tenant B diterima")
    assert await raw.employees.find_one({"id": "emp-bajakan"}, NO_ID) is None

    # --- lewat update yang mencoba memindahkan record ke tenant lain -------
    try:
        await a.employees.update_one(
            {"company_id": COMPANY_B, "id": "emp-b1"}, {"$set": {"full_name": "X"}}
        )
    except CrossTenantDenied:
        pass
    else:
        raise AssertionError("BAHAYA: update lintas tenant lewat filter diterima")

    # --- lewat upsert ------------------------------------------------------
    try:
        await a.payroll_runs.update_one(
            {"id": "run-selundupan", "company_id": COMPANY_B},
            {"$set": {"year": 2026}},
            upsert=True,
        )
    except CrossTenantDenied:
        pass
    else:
        raise AssertionError("BAHAYA: upsert dengan company_id tenant B diterima")

    # --- lewat delete ------------------------------------------------------
    try:
        await a.employees.delete_many({"company_id": COMPANY_B})
    except CrossTenantDenied:
        pass
    else:
        raise AssertionError("BAHAYA: delete dengan company_id tenant B diterima")

    # --- defense-in-depth: filter company_id yang SAMA tetap diterima ------
    # (router existing masih menuliskan filter manual; itu harus tetap jalan)
    rows = await a.employees.find(
        {"company_id": COMPANY_A, "status": "active"}, NO_ID
    ).to_list(10)
    assert len(rows) == 2, "regresi: filter company_id manual existing malah diblokir"

    await a.employees.insert_one(
        {"id": "emp-a9", "company_id": COMPANY_A, "full_name": "Hadi A", "status": "active"}
    )
    cek = await raw.employees.find_one({"id": "emp-a9"}, NO_ID)
    assert cek["company_id"] == COMPANY_A
    await raw.employees.delete_many({"id": "emp-a9"})


# ==========================================================================
# 12. SQL yang dihasilkan benar-benar memuat batasan company_id
# ==========================================================================
async def _t12_sql_selalu_memuat_company_id() -> None:
    a = get_tenant_db(COMPANY_A)
    contoh = [
        {},
        None,
        {"status": "active"},
        {"$or": [{"full_name": "x"}, {"nik": "y"}]},
        {"$and": [{"status": "active"}]},
        {"nik": {"$regex": "^1"}},
    ]
    for flt in contoh:
        sql = str(a.employees._where(flt))
        assert "company_id" in sql, f"SQL tanpa batasan company_id untuk filter {flt}: {sql}"

    # tabel global justru TIDAK boleh ikut ter-filter
    sql_global = str(a.users._where({"status": "active"}))
    assert "company_id" not in sql_global, f"tabel global ikut ter-scope: {sql_global}"


# ==========================================================================
# Pelari test
# ==========================================================================
TESTS = [
    ("01. Tenant A membaca datanya sendiri", _t01_tenant_membaca_data_sendiri),
    ("02. Tenant A tidak dapat membaca data Tenant B", _t02_tenant_tidak_membaca_tenant_lain),
    ("03. Tenant A tidak dapat update data Tenant B", _t03_tenant_tidak_update_tenant_lain),
    ("04. Tenant A tidak dapat delete data Tenant B", _t04_tenant_tidak_delete_tenant_lain),
    ("05. Insert tenant otomatis mendapat company_id benar", _t05_insert_otomatis_dapat_company_id),
    ("06. Tanpa konteks perusahaan: request ditolak (fail-safe)", _t06_tanpa_konteks_ditolak),
    ("07. GLOBAL_COLLECTIONS tetap bekerja seperti existing", _t07_global_collections_tetap_normal),
    ("08. Ganti perusahaan (switch-company) tetap bekerja", _t08_switch_company_bekerja),
    ("09. Alur super_admin existing tidak rusak", _t09_super_admin_tidak_rusak),
    ("10. Alur payroll existing tetap bekerja", _t10_payroll_tetap_bekerja),
    ("11. company_id dari klien tidak mengalahkan konteks", _t11_company_id_klien_tidak_menang),
    ("12. SQL selalu memuat batasan company_id", _t12_sql_selalu_memuat_company_id),
]


async def _run_all() -> int:
    await _setup_database()
    gagal = 0
    try:
        for nama, fn in TESTS:
            try:
                await fn()
                print(f"  LULUS  {nama}")
            except Exception:
                gagal += 1
                print(f"  GAGAL  {nama}")
                traceback.print_exc()
    finally:
        await _teardown_database()
    return gagal


def test_tenant_isolation() -> None:
    """Entry point untuk pytest."""
    assert asyncio.run(_run_all()) == 0, "ada test isolasi tenant yang gagal"


if __name__ == "__main__":
    print("=" * 70)
    print("TEST ISOLASI TENANT — SQLite sementara (produksi tidak disentuh)")
    print("=" * 70)
    jumlah_gagal = asyncio.run(_run_all())
    print("-" * 70)
    total = len(TESTS)
    print(f"Hasil: {total - jumlah_gagal}/{total} lulus")
    sys.exit(1 if jumlah_gagal else 0)
