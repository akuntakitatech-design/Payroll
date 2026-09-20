"""Penguatan isolasi tenant (Tahap 1 SaaS) — enforcement terpusat di data access layer.

LATAR MASALAH
-------------
Sebelum modul ini, isolasi antar perusahaan bergantung pada disiplin developer
menuliskan ``{"company_id": ctx.company_id}`` secara manual pada SETIAP query.
Satu query yang lupa filter berarti kebocoran data lintas perusahaan.

PENDEKATAN
----------
Modul ini menambahkan lapisan *tenant-aware* di atas adapter Mongo-style yang
sudah ada (``app/core/db.py``) **tanpa mengubah satu baris pun** di dalamnya:

* ``db.py`` sama sekali tidak disentuh — modul ini hanya mengimpor kelas
  ``Collection`` lalu menurunkannya (subclass).
* Tetap memakai SQLAlchemy Core. Tidak ada ORM baru, tidak ada Alembic.
* Tetap 100% kompatibel dengan pola Mongo-style (``find``, ``find_one``,
  ``update_one``, ``$or``, ``$regex``, ``$in``, upsert, dan seterusnya).

MENGAPA ``_where()`` ADALAH TITIK ENFORCEMENT YANG TEPAT
-------------------------------------------------------
Di ``db.py``, satu metode ``Collection._where()`` melayani SELURUH pencocokan
baris. Menguncinya berarti mengunci semua jalur baca sekaligus jalur
update/delete:

==============================  ============================================
Operasi                         Jalur menuju ``_where()``
==============================  ============================================
``find`` / ``find_one``         ``_select()``            → ``_where()``
``count_documents``             langsung                  → ``_where()``
``distinct``                    langsung                  → ``_where()``
``update_one`` / ``update_many``  ``_update()``  → ``_find_ids()`` → ``_where()``
``replace_one``                 ``_find_ids()``           → ``_where()``
``find_one_and_update``         ``_find_ids()``           → ``_where()``
``delete_one``                  ``_find_ids()``           → ``_where()``
``delete_many``                 langsung                  → ``_where()``
==============================  ============================================

Selain itu ``compile_filter()`` menggabungkan seluruh key tingkat-atas dengan
``AND``. Jadi menyuntikkan ``company_id`` pada tingkat atas tetap aman bahkan
bila query mengandung ``$or`` / ``$and`` / ``$nor`` — sub-klausa tidak mungkin
memperluas jangkauan ke perusahaan lain.

Jalur INSERT tidak melewati ``_where()``, sehingga ditangani terpisah:
``insert_one``, ``insert_many``, ``_upsert_doc`` (dipakai upsert
``update_*``/``find_one_and_update``), dan jalur upsert ``replace_one``.

PRINSIP KEAMANAN
----------------
**Authenticated context adalah satu-satunya sumber kebenaran untuk
``company_id``.** Nilai ``company_id`` yang datang dari request body, query
parameter, form, atau state frontend TIDAK PERNAH dipercaya:

* bila nilainya sama dengan konteks → diterima (mendukung *defense-in-depth*,
  sehingga filter manual existing di router tetap boleh dipertahankan);
* bila nilainya berbeda → request **ditolak** dengan HTTP 403, bukan
  di-diam-diamkan;
* bila konteks perusahaan tidak ada → request **ditolak** dengan HTTP 400,
  bukan membuka seluruh data (*fail-safe*, bukan *fail-open*).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from fastapi import HTTPException, status

from .db import (
    GLOBAL_COLLECTIONS,
    TENANT_COLLECTIONS,
    Collection,
    Database,
    InsertManyResult,
    InsertOneResult,
    UpdateResult,
    get_db,
)

logger = logging.getLogger("hris.tenancy")

# Penanda "key tidak ada", agar `company_id: None` yang eksplisit dapat
# dibedakan dari `company_id` yang memang tidak disertakan.
_MISSING = object()

__all__ = [
    "TenantContextMissing",
    "CrossTenantDenied",
    "TenantCollection",
    "TenantDatabase",
    "get_tenant_db",
    "unscoped_db",
    "is_tenant_collection",
]


# --------------------------------------------------------------------------
# Kesalahan
# --------------------------------------------------------------------------
class TenantContextMissing(HTTPException):
    """Tabel tenant diakses tanpa konteks perusahaan aktif.

    Sengaja *fail-safe*: menolak request, BUKAN menjatuhkan filter (yang
    justru akan membuka data seluruh perusahaan).
    """

    def __init__(self, collection: str):
        super().__init__(
            status.HTTP_400_BAD_REQUEST,
            "Konteks perusahaan aktif tidak ditemukan. "
            f"Akses ke data '{collection}' ditolak demi keamanan.",
        )


class CrossTenantDenied(HTTPException):
    """Upaya menyentuh data perusahaan lain, atau memaksa company_id lain."""

    def __init__(self, collection: str, attempted: Any, allowed: str):
        super().__init__(
            status.HTTP_403_FORBIDDEN,
            "Akses lintas perusahaan ditolak. "
            f"Data '{collection}' hanya dapat diakses pada perusahaan aktif Anda.",
        )
        # Detail teknis hanya untuk log server — tidak dibocorkan ke klien.
        self.attempted_company_id = attempted
        self.allowed_company_id = allowed


def is_tenant_collection(name: str) -> bool:
    """True bila tabel wajib di-scope ke perusahaan.

    *Fail-closed*: nama yang tidak dikenal (misalnya tabel baru yang belum
    terdaftar) diperlakukan sebagai tabel tenant sehingga tetap ter-scope,
    bukan terbuka.
    """
    return name not in GLOBAL_COLLECTIONS


# --------------------------------------------------------------------------
# Collection ter-scope
# --------------------------------------------------------------------------
class TenantCollection(Collection):
    """``Collection`` yang setiap operasinya terikat pada satu perusahaan.

    Seluruh API publik ``Collection`` tetap sama, sehingga router existing
    hanya perlu mengganti sumber objek ``db`` tanpa mengubah cara memanggil
    query sama sekali.
    """

    def __init__(self, name: str, company_id: Optional[str]):
        if not company_id:
            raise TenantContextMissing(name)
        super().__init__(name)
        self.company_id: str = company_id

    # ---- inti enforcement ----------------------------------------------
    def _assert_allowed(self, claimed: Any) -> None:
        """Validasi company_id yang datang dari pemanggil."""
        if claimed == self.company_id:
            return  # filter manual existing (defense-in-depth) — diizinkan
        logger.warning(
            "Upaya akses lintas tenant ditolak: tabel=%s diminta=%r diizinkan=%s",
            self.name,
            claimed,
            self.company_id,
        )
        raise CrossTenantDenied(self.name, claimed, self.company_id)

    def _scoped_filter(self, flt: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Pasang filter ``company_id`` pada tingkat atas query.

        ``compile_filter`` menggabungkan key tingkat atas dengan ``AND``,
        sehingga hasilnya selalu ``(... query asli ...) AND company_id = <aktif>``
        meskipun query asli memakai ``$or``/``$and``/``$nor``.
        """
        scoped: Dict[str, Any] = dict(flt or {})
        claimed = scoped.pop("company_id", _MISSING)
        if claimed is not _MISSING:
            self._assert_allowed(claimed)
        scoped["company_id"] = self.company_id
        return scoped

    def _scoped_doc(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Paksa ``company_id`` pada dokumen yang akan ditulis."""
        out: Dict[str, Any] = dict(doc or {})
        claimed = out.pop("company_id", _MISSING)
        if claimed is not _MISSING:
            self._assert_allowed(claimed)
        out["company_id"] = self.company_id
        return out

    # ---- pengikatan jalur BACA + UPDATE/DELETE --------------------------
    def _where(self, flt):
        # Satu override ini mengunci: find, find_one, count_documents,
        # distinct, delete_many, serta _find_ids yang dipakai oleh
        # update_one/update_many/replace_one/find_one_and_update/delete_one.
        return super()._where(self._scoped_filter(flt))

    # ---- pengikatan jalur INSERT ---------------------------------------
    async def insert_one(self, doc: Dict[str, Any]) -> InsertOneResult:
        return await super().insert_one(self._scoped_doc(doc))

    async def insert_many(self, docs: Iterable[Dict[str, Any]]) -> InsertManyResult:
        return await super().insert_many([self._scoped_doc(d) for d in docs])

    # ---- pengikatan jalur UPSERT ---------------------------------------
    def _upsert_doc(self, flt: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
        # Dipakai oleh update_one/update_many/find_one_and_update saat
        # upsert=True dan tidak ada baris yang cocok.
        doc = super()._upsert_doc(flt or {}, update)
        return self._scoped_doc(doc)

    async def replace_one(
        self, flt, replacement: Dict[str, Any], upsert: bool = False
    ) -> UpdateResult:
        # Jalur upsert replace_one menulis `replacement` secara langsung,
        # jadi dokumennya perlu di-scope lebih dulu.
        return await super().replace_one(flt, self._scoped_doc(replacement), upsert)


# --------------------------------------------------------------------------
# Facade database ter-scope
# --------------------------------------------------------------------------
class TenantDatabase:
    """Pengganti ``Database`` yang sadar tenant.

    * Tabel **tenant** → ``TenantCollection`` (otomatis ter-scope).
    * Tabel **global** (``GLOBAL_COLLECTIONS``: companies, users, roles,
      permissions, modules, role_permissions, user_company_roles) →
      ``Collection`` biasa, berperilaku persis seperti sekarang sehingga
      autentikasi, RBAC, dan alur super admin tidak terpengaruh.

    Dengan begitu satu objek ``db`` dapat menggantikan ``get_db()`` di dalam
    router tanpa memecah query global apa pun.
    """

    __slots__ = ("company_id",)

    def __init__(self, company_id: Optional[str]):
        if not company_id:
            # Fail-safe di titik paling awal: tanpa konteks perusahaan,
            # objek database ter-scope tidak boleh terbentuk sama sekali.
            raise TenantContextMissing("<tenant-scoped>")
        self.company_id: str = company_id

    def __getitem__(self, name: str) -> Collection:
        if is_tenant_collection(name):
            return TenantCollection(name, self.company_id)
        return Collection(name)

    def __getattr__(self, name: str) -> Collection:
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]

    # Diteruskan agar sepadan dengan Database untuk pemeriksaan kesehatan.
    async def command(self, cmd: Any) -> Dict[str, Any]:
        return await get_db().command(cmd)

    @property
    def tenant_collections(self) -> List[str]:
        return list(TENANT_COLLECTIONS)

    def __repr__(self) -> str:  # pragma: no cover - bantuan debug
        return f"<TenantDatabase company_id={self.company_id}>"


def get_tenant_db(company_id: Optional[str]) -> TenantDatabase:
    """Bangun accessor database yang terikat pada satu perusahaan.

    Menolak (HTTP 400) bila ``company_id`` kosong — *fail-safe*.
    """
    return TenantDatabase(company_id)


# --------------------------------------------------------------------------
# Bypass platform yang eksplisit
# --------------------------------------------------------------------------
def unscoped_db(reason: str, *, actor_user_id: Optional[str] = None) -> Database:
    """Akses database LINTAS PERUSAHAAN — pakai dengan sangat hati-hati.

    Ini adalah satu-satunya jalur bypass yang disediakan, dan sengaja dibuat:

    * **eksplisit** — namanya menyatakan bahaya, dan ``reason`` wajib diisi;
    * **terlacak** — setiap pemanggilan dicatat ke log server;
    * **tidak terjangkau dari request** — tidak pernah dilekatkan pada
      ``AuthContext``, tidak ada parameter HTTP yang dapat memicunya, dan
      tidak ada role tenant yang bisa memintanya. Hanya kode server yang
      memang lintas-tenant (proses latar, pemeriksaan kesehatan, dan kelak
      Platform Console) yang boleh memanggilnya.

    Catatan: ``get_db()`` existing tetap tidak berubah demi kompatibilitas
    dengan seluruh flow yang belum dimigrasikan. Fungsi ini adalah pintu
    resmi yang dianjurkan untuk kebutuhan lintas-tenant yang sah, agar
    niatnya terbaca jelas di dalam kode.
    """
    if not reason or not str(reason).strip():
        raise ValueError(
            "unscoped_db() memerlukan alasan yang jelas untuk keperluan audit."
        )
    logger.info(
        "AKSES DATABASE LINTAS-TENANT: %s (aktor=%s)", reason, actor_user_id or "sistem"
    )
    return get_db()
