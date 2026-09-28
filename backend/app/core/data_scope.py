"""Upgrade 01I - Role & Data Scope: SATU-SATUNYA mesin cakupan data karyawan.

RBAC (permission) menjawab "aksi apa yang boleh"; modul ini menjawab "karyawan MANA yang boleh".
Keduanya wajib lulus. Router TIDAK boleh menduplikasi logika di bawah ini.

Aturan (dikunci pada audit 01I):
- Scope berlaku per (company_id, user_id). Satu user di beberapa company dapat punya scope berbeda.
- Mode: ALL_TENANT | SELECTED_PROJECTS.
- Full scope otomatis (tanpa melihat konfigurasi): Platform Admin (super_admin), Tenant Admin, Pemilik Perusahaan.
- Tidak ada baris scope = ALL_TENANT (default m0011; akses existing dipertahankan).
- Akses company dicabut -> item dihapus + baris scope menjadi tombstone (status `revoked`, mode SELECTED_PROJECTS).
  Keanggotaan yang ditambahkan kembali (re-add / grant tanpa pilihan eksplisit) -> SELECTED_PROJECTS TANPA project
  ("Tidak ada akses data") sampai admin mengatur ulang. ALL_TENANT otomatis HANYA untuk user existing saat m0011.
- SELECTED_PROJECTS: hanya karyawan dengan assignment 01D `assignment_status = ACTIVE` pada project yang diizinkan.
  `employees.project_id` hanya mirror kompatibilitas -> TIDAK dipakai sebagai sumber cakupan.
- Fail-closed: mode tidak dikenal, restricted tanpa item, item/project tidak valid -> 0 karyawan (tidak pernah
  jatuh ke ALL_TENANT). Project valid = milik company_id yang sama dan berstatus active/inactive.
- Restricted user tidak melihat karyawan tanpa assignment ACTIVE (standby/tanpa project).
- Filter list/count diterapkan di SQL (subquery), bukan filter Python.
- Scope dihitung ulang setiap request (disimpan hanya di AuthContext request tsb) -> perubahan assignment/scope
  berlaku seketika tanpa cache basi.
- Karyawan di luar scope -> 404 generik (tidak membocorkan keberadaan). Operasi full-scope -> 403.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, List, Optional

import sqlalchemy as sa
from fastapi import HTTPException, status

from .db import NO_ID, audit_fields, get_db, get_table, new_id, transaction

ALL_TENANT = "ALL_TENANT"
SELECTED_PROJECTS = "SELECTED_PROJECTS"
MODES = (ALL_TENANT, SELECTED_PROJECTS)
DIM_PROJECT = "project"
FULL_SCOPE_ROLES = frozenset({"super_admin", "tenant_admin", "company_owner"})
VALID_PROJECT_STATUSES = ("active", "inactive")
REVOKED = "revoked"  # tombstone scope setelah akses company dicabut
NOT_FOUND_MSG = "Data tidak ditemukan pada perusahaan aktif Anda."
FULL_SCOPE_MSG = ("Tindakan ini hanya tersedia untuk pengguna dengan Cakupan Data 'Semua Data Perusahaan'. "
                  "Cakupan Anda dibatasi pada project tertentu.")
OUT_OF_SCOPE_LABEL = "Di luar cakupan akses"
OUT_OF_SCOPE_TARGET_MSG = "Project tujuan berada di luar Cakupan Data Anda."


@dataclass(frozen=True)
class DataScope:
    company_id: str
    user_id: str
    mode: str
    project_ids: FrozenSet[str] = field(default_factory=frozenset)
    source: str = "config"  # role | config | default | invalid
    configured_items: int = 0  # jumlah item aktif yang tersimpan (termasuk yang tidak valid)

    @property
    def is_all(self) -> bool:
        return self.mode == ALL_TENANT

    @property
    def restricted(self) -> bool:
        return not self.is_all

    @property
    def has_no_access(self) -> bool:
        return self.restricted and not self.project_ids

    def allows_project(self, project_id: Optional[str]) -> bool:
        return self.is_all or (bool(project_id) and project_id in self.project_ids)


# ------------------------------------------------------------------ resolve
async def _load_config(company_id: str, user_id: str) -> Dict[str, Any]:
    """Konfigurasi tersimpan (mentah) untuk (company, user). Tidak memeriksa role."""
    db = get_db()
    row = await db.user_data_scopes.find_one({"company_id": company_id, "user_id": user_id}, NO_ID)
    if not row:
        return {"row": None, "items": [], "valid": []}
    items = await db.user_data_scope_items.find({
        "company_id": company_id, "scope_id": row["id"], "user_id": user_id,
        "dimension": DIM_PROJECT, "status": "active",
    }, NO_ID).to_list(2000)
    ref_ids = sorted({i["ref_id"] for i in items if i.get("ref_id")})
    valid: List[str] = []
    if ref_ids:
        rows = await db.projects.find({
            "company_id": company_id, "id": {"$in": ref_ids}, "status": {"$in": list(VALID_PROJECT_STATUSES)},
        }, {"id": 1}).to_list(len(ref_ids))
        valid = sorted({r["id"] for r in rows})
    return {"row": row, "items": items, "valid": valid}


async def compute_scope(company_id: str, user_id: str, role_keys: Iterable[str]) -> DataScope:
    if not company_id or not user_id:
        # Tanpa konteks tenant tidak ada data karyawan yang boleh diakses.
        return DataScope(company_id or "", user_id or "", SELECTED_PROJECTS, frozenset(), "invalid", 0)
    if FULL_SCOPE_ROLES & set(role_keys or []):
        return DataScope(company_id, user_id, ALL_TENANT, frozenset(), "role", 0)
    cfg = await _load_config(company_id, user_id)
    row = cfg["row"]
    if row is None:
        return DataScope(company_id, user_id, ALL_TENANT, frozenset(), "default", 0)
    mode = row.get("mode")
    if row.get("status") != "active" or mode not in MODES:
        return DataScope(company_id, user_id, SELECTED_PROJECTS, frozenset(), "invalid", 0)
    if mode == ALL_TENANT:
        return DataScope(company_id, user_id, ALL_TENANT, frozenset(), "config", 0)
    return DataScope(company_id, user_id, SELECTED_PROJECTS, frozenset(cfg["valid"]), "config", len(cfg["items"]))


async def get_scope(ctx) -> DataScope:
    """Scope caller untuk company aktif; di-memo HANYA pada AuthContext request ini."""
    cached = getattr(ctx, "_data_scope", None)
    if isinstance(cached, DataScope) and cached.company_id == ctx.company_id:
        return cached
    scope = await compute_scope(ctx.company_id, ctx.user_id, ctx.role_keys)
    try:
        object.__setattr__(ctx, "_data_scope", scope)
    except Exception:  # pragma: no cover - ctx tanpa atribut dinamis
        pass
    return scope


# ------------------------------------------------------------------ SQL helpers
def scoped_employee_ids_subquery(scope: DataScope):
    """SELECT employee_id FROM employee_assignments WHERE company=.. AND ACTIVE AND project IN (..)."""
    a = get_table("employee_assignments")
    return sa.select(a.c.employee_id).where(
        a.c.company_id == scope.company_id,
        a.c.assignment_status == "ACTIVE",
        a.c.project_id.in_(sorted(scope.project_ids)),
    )


def employee_scope_clause(scope: DataScope, column):
    """Klausa SQL untuk kolom yang berisi employees.id. None = tanpa batasan (ALL_TENANT)."""
    if scope.is_all:
        return None
    if not scope.project_ids:
        return sa.false()
    return column.in_(scoped_employee_ids_subquery(scope))


def scope_filter(scope: DataScope, field_name: str = "id") -> Dict[str, Any]:
    """Fragmen filter adapter DB (`$sql`) untuk kolom `field_name` yang berisi employees.id.
    Kosong untuk ALL_TENANT. Dapat digabung ke dict filter mana pun (dieksekusi di SQL)."""
    if scope.is_all:
        return {}
    return {"$sql": (lambda t, s=scope, f=field_name: employee_scope_clause(s, t.c[f]))}


def with_scope(flt: Optional[Dict[str, Any]], scope: DataScope, field_name: str = "id") -> Dict[str, Any]:
    out: Dict[str, Any] = dict(flt or {})
    frag = scope_filter(scope, field_name)
    if frag:
        prev = out.get("$sql")
        out["$sql"] = ([*prev] if isinstance(prev, (list, tuple)) else ([prev] if prev else [])) + [frag["$sql"]]
    return out


# ------------------------------------------------------------------ project-scoped records (Phase 2A: aset)
# Record yang punya kolom project_id sendiri (mis. `assets.project_id`). Filosofi sama dengan 01I:
# ALL_TENANT = tanpa batasan; SELECTED_PROJECTS = project_id IN allowed (NULL/tanpa project TIDAK terlihat);
# scope kosong = tidak ada data. Dieksekusi di SQL (fragmen `$sql`), bukan difilter di Python.
def project_scope_clause(scope: DataScope, column):
    if scope.is_all:
        return None
    if not scope.project_ids:
        return sa.false()
    return sa.and_(column.isnot(None), column.in_(sorted(scope.project_ids)))


def with_project_scope(flt: Optional[Dict[str, Any]], scope: DataScope, field_name: str = "project_id") -> Dict[str, Any]:
    out: Dict[str, Any] = dict(flt or {})
    if scope.is_all:
        return out
    frag = (lambda t, s=scope, f=field_name: project_scope_clause(s, t.c[f]))
    prev = out.get("$sql")
    out["$sql"] = ([*prev] if isinstance(prev, (list, tuple)) else ([prev] if prev else [])) + [frag]
    return out


def assert_project_record_visible(scope: DataScope, record: Optional[Dict[str, Any]], field_name: str = "project_id") -> Dict[str, Any]:
    """404 generik bila record tidak ada atau project-nya di luar scope caller (tanpa membocorkan keberadaan)."""
    if not record or not scope.allows_project(record.get(field_name)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MSG)
    return record


# ------------------------------------------------------------------ checks
async def employee_in_scope(scope: DataScope, employee_id: Optional[str]) -> bool:
    if not employee_id:
        return False
    db = get_db()
    flt = with_scope({"company_id": scope.company_id, "id": employee_id}, scope)
    return bool(await db.employees.count_documents(flt))


async def ensure_employee_in_scope(ctx, employee_id: Optional[str]) -> DataScope:
    """404 generik bila karyawan tidak ada di company aktif ATAU di luar scope caller."""
    scope = await get_scope(ctx)
    if not await employee_in_scope(scope, employee_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MSG)
    return scope


async def get_scoped_employee(ctx, employee_id: str, projection=NO_ID) -> Dict[str, Any]:
    scope = await get_scope(ctx)
    doc = await get_db().employees.find_one(with_scope({"company_id": ctx.company_id, "id": employee_id}, scope), projection)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MSG)
    return doc


async def allowed_project_ids(ctx) -> Optional[FrozenSet[str]]:
    """None = semua project (ALL_TENANT); frozenset (bisa kosong) = project yang diizinkan."""
    scope = await get_scope(ctx)
    return None if scope.is_all else scope.project_ids


async def has_all_tenant(ctx) -> bool:
    return (await get_scope(ctx)).is_all


async def require_full_scope(ctx) -> DataScope:
    scope = await get_scope(ctx)
    if scope.restricted:
        raise HTTPException(status.HTTP_403_FORBIDDEN, FULL_SCOPE_MSG)
    return scope


async def ensure_target_project_allowed(ctx, project_id: Optional[str]) -> DataScope:
    """Penempatan/transfer/buat karyawan: project tujuan wajib dalam scope (restricted wajib punya project)."""
    scope = await get_scope(ctx)
    if not scope.allows_project(project_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, OUT_OF_SCOPE_TARGET_MSG)
    return scope


UNSCOPED_MODULE_MSG = ("Modul ini belum mendukung Cakupan Data per project. Akses hanya tersedia untuk pengguna "
                      "dengan Cakupan Data 'Semua Data Perusahaan'.")


async def require_unscoped_module_access(ctx) -> DataScope:
    """Fail-closed untuk modul yang belum punya penegakan cakupan (dipanggil dari require_permission)."""
    scope = await get_scope(ctx)
    if scope.restricted:
        raise HTTPException(status.HTTP_403_FORBIDDEN, UNSCOPED_MODULE_MSG)
    return scope


async def revoke_user_scope(company_id: str, user_id: str, actor_id: Optional[str] = None) -> Dict[str, int]:
    """Akses user ke company dicabut -> SEMUA item (company_id, user_id) dihapus dan baris scope dijadikan
    tombstone `revoked` (mode SELECTED_PROJECTS, fail-closed) secara atomik. Scope user di company lain TIDAK
    disentuh. Tombstone mencegah re-add lewat jalur mana pun jatuh ke default ALL_TENANT (tanpa baris)."""
    if not company_id or not user_id:
        return {"scopes": 0, "items": 0}
    async with transaction() as tx:
        items = await tx.delete("user_data_scope_items", {"company_id": company_id, "user_id": user_id})
        row = await tx.select_one_for_update("user_data_scopes", {"company_id": company_id, "user_id": user_id})
        if row:
            await tx.update("user_data_scopes", {"id": row["id"], "company_id": company_id},
                            {"mode": SELECTED_PROJECTS, "status": REVOKED, **audit_fields(actor_id, creating=False)})
        else:
            await tx.insert("user_data_scopes", {"id": new_id(), "company_id": company_id, "user_id": user_id,
                                                 "mode": SELECTED_PROJECTS, "status": REVOKED,
                                                 **audit_fields(actor_id, creating=True)})
    return {"scopes": 1, "items": int(items or 0)}


async def revoke_if_no_membership(company_id: str, user_id: str, actor_id: Optional[str] = None) -> Optional[Dict[str, int]]:
    """Dipakai setelah pencabutan sebagian peran: bersihkan scope hanya bila user tidak lagi punya
    keanggotaan aktif apa pun di company tsb."""
    if await get_db().user_company_roles.count_documents({"company_id": company_id, "user_id": user_id, "status": "active"}):
        return None
    return await revoke_user_scope(company_id, user_id, actor_id)


def full_scope_dependency(perm_dep):
    """Bungkus dependency `require_permission(...)` agar endpoint tenant-wide (bulk/import/export/config
    lintas karyawan yang belum scope-aware) ditolak 403 untuk user restricted."""
    from fastapi import Depends

    async def _dep(ctx=Depends(perm_dep)):
        await require_full_scope(ctx)
        return ctx

    return _dep


# ------------------------------------------------------------------ admin (manage)
async def describe_scope(company_id: str, user_id: str, role_keys: Iterable[str]) -> Dict[str, Any]:
    """Representasi untuk UI/API (termasuk label project). Tidak berisi data sensitif."""
    effective = await compute_scope(company_id, user_id, role_keys)
    cfg = await _load_config(company_id, user_id)
    row = cfg["row"]
    configured_ids = sorted({i["ref_id"] for i in cfg["items"] if i.get("ref_id")})
    names: Dict[str, Dict[str, Any]] = {}
    if configured_ids:
        rows = await get_db().projects.find({"company_id": company_id, "id": {"$in": configured_ids}},
                                            {"id": 1, "name": 1, "code": 1, "status": 1}).to_list(len(configured_ids))
        names = {r["id"]: r for r in rows}
    projects = [{
        "id": pid, "name": (names.get(pid) or {}).get("name"), "code": (names.get(pid) or {}).get("code"),
        "valid": pid in effective.project_ids or (effective.is_all and pid in cfg["valid"]),
        "status": (names.get(pid) or {}).get("status") or "missing",
    } for pid in configured_ids]
    projects.sort(key=lambda p: ((p["name"] or "~").lower(), p["id"]))
    return {
        "company_id": company_id, "user_id": user_id,
        "configured_mode": (row or {}).get("mode") or ALL_TENANT,
        "configured": row is not None,
        "effective_mode": effective.mode,
        "source": effective.source,
        "full_scope_role": effective.source == "role",
        "no_access": effective.has_no_access,
        "project_ids": configured_ids,
        "projects": projects,
        "valid_project_count": len(effective.project_ids),
        "updated_at": (row or {}).get("updated_at"),
    }


async def set_user_scope(company_id: str, user_id: str, mode: str, project_ids: Optional[List[str]],
                         actor_id: Optional[str]) -> Dict[str, Any]:
    """Simpan scope (company_id, user_id) secara atomik. Validasi: mode dikenal; project milik company yang sama."""
    if mode not in MODES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Mode Cakupan Data tidak dikenal.")
    ids = sorted({str(p).strip() for p in (project_ids or []) if str(p or "").strip()}) if mode == SELECTED_PROJECTS else []
    if mode == SELECTED_PROJECTS:
        if not ids:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pilih minimal satu project untuk Cakupan 'Project Tertentu'.")
        if len(ids) > 500:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Terlalu banyak project dipilih (maks. 500).")
        found = await get_db().projects.find({
            "company_id": company_id, "id": {"$in": ids}, "status": {"$in": list(VALID_PROJECT_STATUSES)},
        }, {"id": 1}).to_list(len(ids))
        if {r["id"] for r in found} != set(ids):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Satu atau lebih project tidak ditemukan / tidak aktif pada perusahaan aktif Anda.")
    db = get_db()
    before = await db.user_data_scopes.find_one({"company_id": company_id, "user_id": user_id}, NO_ID)
    before_items = []
    if before:
        before_items = sorted(i["ref_id"] for i in await db.user_data_scope_items.find(
            {"company_id": company_id, "scope_id": before["id"], "dimension": DIM_PROJECT, "status": "active"}, NO_ID).to_list(2000))
    async with transaction() as tx:
        row = await tx.select_one_for_update("user_data_scopes", {"company_id": company_id, "user_id": user_id})
        if row:
            scope_id = row["id"]
            await tx.update("user_data_scopes", {"id": scope_id, "company_id": company_id},
                            {"mode": mode, "status": "active", **audit_fields(actor_id, creating=False)})
        else:
            scope_id = new_id()
            await tx.insert("user_data_scopes", {"id": scope_id, "company_id": company_id, "user_id": user_id,
                                                 "mode": mode, "status": "active", **audit_fields(actor_id, creating=True)})
        await tx.delete("user_data_scope_items", {"company_id": company_id, "scope_id": scope_id})
        for pid in ids:
            await tx.insert("user_data_scope_items", {"id": new_id(), "company_id": company_id, "scope_id": scope_id,
                                                      "user_id": user_id, "dimension": DIM_PROJECT, "ref_id": pid,
                                                      "status": "active", **audit_fields(actor_id, creating=True)})
    return {"before": {"mode": (before or {}).get("mode") or ALL_TENANT, "project_ids": before_items},
            "after": {"mode": mode, "project_ids": ids}}


async def ensure_default_scope(company_id: str, user_id: str, actor_id: Optional[str]) -> None:
    """Keanggotaan diberikan TANPA pilihan cakupan eksplisit (grant akses company / Platform Admin menambah
    peran). Idempoten:
    - baris aktif sudah ada (user masih anggota) -> tidak diubah;
    - tombstone `revoked` (re-add) atau belum ada baris -> SELECTED_PROJECTS tanpa project = "Tidak ada akses
      data" sampai admin memilih Semua Data Perusahaan / project tertentu. Tidak pernah otomatis ALL_TENANT."""
    db = get_db()
    async with transaction() as tx:
        row = await tx.select_one_for_update("user_data_scopes", {"company_id": company_id, "user_id": user_id})
        if row and row.get("status") == "active":
            return
        if row:
            await tx.delete("user_data_scope_items", {"company_id": company_id, "scope_id": row["id"]})
            await tx.update("user_data_scopes", {"id": row["id"], "company_id": company_id},
                            {"mode": SELECTED_PROJECTS, "status": "active", **audit_fields(actor_id, creating=False)})
            return
    try:
        await db.user_data_scopes.insert_one({"id": new_id(), "company_id": company_id, "user_id": user_id,
                                              "mode": SELECTED_PROJECTS, "status": "active",
                                              **audit_fields(actor_id, creating=True)})
    except HTTPException:  # duplikat karena balapan -> sudah ada, aman
        pass


async def scope_labels_for_users(company_id: str, user_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """Ringkasan scope TERSIMPAN banyak user sekaligus (2 query; tanpa N+1). Role full-scope ditangani pemanggil."""
    if not user_ids:
        return {}
    db = get_db()
    rows = await db.user_data_scopes.find({"company_id": company_id, "user_id": {"$in": user_ids}}, NO_ID).to_list(len(user_ids))
    by_user = {r["user_id"]: r for r in rows}
    scope_ids = [r["id"] for r in rows if r.get("mode") == SELECTED_PROJECTS]
    items = []
    if scope_ids:
        items = await db.user_data_scope_items.find({"company_id": company_id, "scope_id": {"$in": scope_ids},
                                                     "dimension": DIM_PROJECT, "status": "active"}, NO_ID).to_list(20000)
    ref_ids = sorted({i["ref_id"] for i in items})
    projects = {}
    if ref_ids:
        prow = await db.projects.find({"company_id": company_id, "id": {"$in": ref_ids}},
                                      {"id": 1, "name": 1, "status": 1}).to_list(len(ref_ids))
        projects = {p["id"]: p for p in prow}
    out: Dict[str, Dict[str, Any]] = {}
    for uid in user_ids:
        r = by_user.get(uid)
        if r is None:
            out[uid] = {"mode": ALL_TENANT, "projects": [], "no_access": False, "configured": False}
            continue
        if r.get("status") != "active" or r.get("mode") not in MODES:
            out[uid] = {"mode": SELECTED_PROJECTS, "projects": [], "no_access": True, "configured": True}
            continue
        if r["mode"] == ALL_TENANT:
            out[uid] = {"mode": ALL_TENANT, "projects": [], "no_access": False, "configured": True}
            continue
        mine = [i["ref_id"] for i in items if i["scope_id"] == r["id"]]
        valid = [projects[p] for p in mine if p in projects and projects[p].get("status") in VALID_PROJECT_STATUSES]
        out[uid] = {"mode": SELECTED_PROJECTS, "configured": True, "no_access": not valid,
                    "projects": sorted(({"id": p["id"], "name": p.get("name")} for p in valid), key=lambda x: (x["name"] or "").lower())}
    return out
