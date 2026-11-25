"""Pemeriksaan akurasi HR Command Center analytics dengan fake DB (tanpa MariaDB).

Jalankan manual dari folder backend:

    python tests/manual_dashboard_analytics_check.py

Nama berkas sengaja tidak diawali `test_` agar tidak dijalankan otomatis oleh pytest
(script ini berhenti dengan sys.exit dan mencetak laporan panjang).
Memverifikasi: KPI, demografi, organisasi, pergerakan, roster, absensi, payroll,
kompetensi, administrasi, action center, insight, cross-filter, dan gating izin.
"""
import asyncio
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
os.environ.setdefault("DATABASE_URL", "mysql+asyncmy://uji:uji@localhost:3306/uji")

from app.core.config import settings  # noqa: E402
settings.READ_ONLY = False

from app.core import data_scope as dscope  # noqa: E402
from app.core.deps import AuthContext  # noqa: E402
from app.routers.dashboard_analytics import analytics  # noqa: E402

MISSING = object()
failures = []


def check(cond, label, detail=None):
    if cond:
        print(f"  [OK]   {label}")
    else:
        print(f"  [FAIL] {label}" + (f" -> {detail}" if detail is not None else ""))
        failures.append(label)


def _cmp(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return (a > b) - (a < b)
    sa, sb = str(a), str(b)
    return (sa > sb) - (sa < sb)


def _match(row, flt):
    for key, expect in (flt or {}).items():
        if key == "$sql":
            continue
        actual = row.get(key, MISSING)
        if isinstance(expect, dict):
            for op, val in expect.items():
                if op == "$ne":
                    if actual is not MISSING and actual == val:
                        return False
                elif op == "$in":
                    if actual is MISSING or actual not in val:
                        return False
                elif op == "$nin":
                    if actual is not MISSING and actual in val:
                        return False
                elif op == "$gte":
                    if actual is MISSING or actual is None or _cmp(actual, val) < 0:
                        return False
                elif op == "$lte":
                    if actual is MISSING or actual is None or _cmp(actual, val) > 0:
                        return False
                else:
                    raise AssertionError(f"operator belum didukung: {op}")
        else:
            if actual is MISSING or actual != expect:
                return False
    return True


class Cursor:
    def __init__(self, rows):
        self._rows, self._sort, self._limit = list(rows), [], None

    def sort(self, spec, direction=None):
        self._sort = [(spec, direction)] if isinstance(spec, str) else [tuple(s) for s in spec]
        return self

    def limit(self, n):
        self._limit = n
        return self

    async def to_list(self, length=None):
        rows = list(self._rows)
        cap = self._limit if self._limit is not None else length
        return rows[:cap] if cap else rows


class Coll:
    def __init__(self, db, name):
        self._db, self._name = db, name

    def _rows(self):
        return self._db.tables.get(self._name, [])

    def find(self, flt=None, projection=None, **kw):
        self._db.queries.append(self._name)
        return Cursor([dict(r) for r in self._rows() if _match(r, flt)])

    async def find_one(self, flt=None, projection=None, **kw):
        for r in self._rows():
            if _match(r, flt):
                return dict(r)
        return None

    async def count_documents(self, flt=None, **kw):
        return sum(1 for r in self._rows() if _match(r, flt))


class DB:
    def __init__(self, tables):
        self.tables, self.queries = tables, []

    def __getitem__(self, name):
        return Coll(self, name)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return Coll(self, name)


TODAY = date(2026, 11, 25)
START = TODAY.replace(day=1)


def iso(d):
    return d.isoformat()


def age_of(birth, ref=TODAY):
    return ref.year - birth.year - ((ref.month, ref.day) < (birth.month, birth.day))


TABLES = {
    "employees": [
        {"id": "e1", "company_id": "c1", "status": "active", "full_name": "Budi", "gender": "male",
         "birth_date": "1990-06-15", "education": "S1", "marital_status": "kawin", "religion": "islam",
         "join_date": iso(TODAY - timedelta(days=365 * 6)), "branch_id": "b1", "project_id": "p1",
         "department_id": "d1", "division_id": "v1", "position_id": "pos1", "job_grade_id": "g1",
         "cost_center_id": "cc1", "employment_status_id": "es1", "current_employee_status_id": "bs1",
         "province": "Jawa Barat", "user_id": "u1", "photo_path": "p.jpg"},
        {"id": "e2", "company_id": "c1", "status": "active", "full_name": "Sari", "gender": "female",
         "birth_date": "2000-03-01", "education": "SMA", "marital_status": "belum_kawin", "religion": "kristen",
         "join_date": iso(TODAY - timedelta(days=3)), "branch_id": "b1", "project_id": "p2",
         "department_id": "d1", "division_id": "v1", "position_id": "pos1", "job_grade_id": "g1",
         "cost_center_id": "cc1", "employment_status_id": "es1", "current_employee_status_id": "bs1",
         "province": "DKI Jakarta", "photo_path": None},
        {"id": "e3", "company_id": "c1", "status": "inactive", "full_name": "Dedi", "gender": "male",
         "birth_date": None, "education": "S1", "marital_status": None, "religion": "islam",
         "join_date": iso(TODAY - timedelta(days=365 * 11)), "branch_id": "b2", "project_id": None,
         "department_id": "d2", "division_id": "v2", "position_id": "pos2", "job_grade_id": "g2",
         "cost_center_id": "cc2", "employment_status_id": "es2", "current_employee_status_id": "bs2",
         "province": "Jawa Timur", "photo_path": None},
        {"id": "e4", "company_id": "c1", "status": "active", "full_name": "Rina", "gender": "female",
         "birth_date": "1985-12-31", "education": "S1", "marital_status": "janda", "religion": "katolik",
         "join_date": iso(TODAY - timedelta(days=365 * 7)), "branch_id": "b2", "project_id": "p1",
         "department_id": "d2", "division_id": "v2", "position_id": "pos2", "job_grade_id": "g2",
         "cost_center_id": "cc2", "employment_status_id": "es1", "current_employee_status_id": "bs1",
         "province": "Jawa Barat", "photo_path": "q.jpg"},
    ],
    "exit_clearances": [
        {"id": "x1", "company_id": "c1", "status": "active", "employee_id": "e3",
         "case_state": "COMPLETED", "last_working_date": iso(TODAY - timedelta(days=2)),
         "exit_type": "RESIGN", "reason": "Pindah domisili"},
        {"id": "x2", "company_id": "c1", "status": "active", "employee_id": "e2",
         "case_state": "PENDING_APPROVAL", "last_working_date": iso(TODAY + timedelta(days=20)),
         "exit_type": "RESIGN", "reason": "Kontrak selesai"},
    ],
    "employee_family_members": [
        {"company_id": "c1", "status": "active", "employee_id": "e1", "relationship": "istri"},
        {"company_id": "c1", "status": "active", "employee_id": "e1", "relationship": "anak"},
        {"company_id": "c1", "status": "active", "employee_id": "e2", "relationship": "ayah"},
    ],
    "employee_contracts": [
        {"company_id": "c1", "status": "active", "employee_id": "e1", "contract_type_id": "ct1",
         "start_date": iso(TODAY - timedelta(days=300)), "end_date": iso(TODAY + timedelta(days=10))},
        {"company_id": "c1", "status": "active", "employee_id": "e4", "contract_type_id": "ct1",
         "start_date": iso(TODAY - timedelta(days=200)), "end_date": iso(TODAY + timedelta(days=200))},
        {"company_id": "c1", "status": "active", "employee_id": "e3", "contract_type_id": "ct2",
         "start_date": iso(TODAY - timedelta(days=900)), "end_date": iso(TODAY - timedelta(days=30))},
    ],
    "employee_certifications": [
        {"company_id": "c1", "status": "active", "employee_id": "e1", "certification_type_id": "cert1",
         "name": "K3 Umum", "expiry_date": iso(TODAY - timedelta(days=5))},
        {"company_id": "c1", "status": "active", "employee_id": "e4", "certification_type_id": "cert1",
         "name": "K3 Umum", "expiry_date": iso(TODAY + timedelta(days=400))},
    ],
    "documents": [
        {"id": "doc1", "company_id": "c1", "is_deleted": False, "owner_type": "employee", "owner_id": "e1",
         "name": "KTP", "expiry_date": iso(TODAY + timedelta(days=20))},
    ],
    "employee_completeness": [
        {"company_id": "c1", "employee_id": "e1", "score_pct": 60, "completeness_status": "INCOMPLETE",
         "missing_codes": ["bank_account_number", "npwp"]},
        {"company_id": "c1", "employee_id": "e2", "score_pct": 100, "completeness_status": "COMPLETE",
         "missing_codes": []},
    ],
    "employee_assignments": [
        {"company_id": "c1", "status": "active", "employee_id": "e1", "project_id": "p1",
         "start_date": iso(TODAY - timedelta(days=5)), "previous_assignment_id": "a0"},
        {"company_id": "c1", "status": "active", "employee_id": "e2", "project_id": "p2",
         "start_date": iso(TODAY - timedelta(days=40)), "previous_assignment_id": None},
    ],
    "roster_leave_plans": [
        {"company_id": "c1", "status": "active", "employee_id": "e1", "project_id": "p1",
         "plan_status": "CONFIRMED", "off_start": iso(TODAY - timedelta(days=2)),
         "off_end": iso(TODAY + timedelta(days=5)), "replacement_employee_id": None},
        {"company_id": "c1", "status": "active", "employee_id": "e4", "project_id": "p1",
         "plan_status": "PLANNED", "off_start": iso(TODAY + timedelta(days=5)),
         "off_end": iso(TODAY + timedelta(days=15)), "replacement_employee_id": "e2"},
    ],
    "roster_mobilizations": [
        {"company_id": "c1", "status": "active", "employee_id": "e2", "project_id": "p2",
         "depart_date": iso(TODAY + timedelta(days=3)), "return_date": iso(TODAY + timedelta(days=40)),
         "mobilization_state": "SCHEDULED", "approval_state": "PENDING_APPROVAL"},
    ],
    "project_roster_configs": [
        {"company_id": "c1", "project_id": "p1", "pattern_id": "pt1"},
    ],
    "attendances": [
        {"company_id": "c1", "employee_id": "e1", "work_date": iso(TODAY), "attendance_status": "present",
         "actual_work_minutes": 480, "approved_overtime_minutes": 60, "is_valid": True},
        {"company_id": "c1", "employee_id": "e2", "work_date": iso(TODAY), "attendance_status": "late",
         "actual_work_minutes": 450, "approved_overtime_minutes": 0, "is_valid": True},
        {"company_id": "c1", "employee_id": "e4", "work_date": iso(TODAY), "attendance_status": "absent",
         "actual_work_minutes": 0, "approved_overtime_minutes": 0, "is_valid": False},
    ],
    "candidates": [
        {"company_id": "c1", "status": "active", "id": "cand1", "stage_status": "hired",
         "applied_at": iso(TODAY - timedelta(days=30)), "converted_at": iso(TODAY - timedelta(days=10)),
         "employee_id": "e2", "source": "portal"},
        {"company_id": "c1", "status": "active", "id": "cand2", "stage_status": "screening",
         "applied_at": iso(TODAY - timedelta(days=5)), "converted_at": None, "employee_id": None,
         "source": "referral"},
    ],
    "payroll_runs": [
        {"company_id": "c1", "status": "active", "id": "r1", "year": 2026, "month": 10,
         "period_label": "2026-10", "run_status": "PAID",
         "totals": {"gross": 800, "net_pay": 700, "employer_cost": 900, "bpjs_employee": 10,
                    "bpjs_employer": 20, "pph21": 5, "total_deductions": 100},
         "employee_count": 2},
        {"company_id": "c1", "status": "active", "id": "r2", "year": 2026, "month": 11,
         "period_label": "2026-11", "run_status": "APPROVED",
         "totals": {"gross": 1000, "net_pay": 900, "employer_cost": 1100, "bpjs_employee": 12,
                    "bpjs_employer": 24, "pph21": 6, "total_deductions": 120},
         "employee_count": 2},
    ],
    "payroll_items": [
        {"company_id": "c1", "id": "i1", "run_id": "r2", "employee_id": "e1", "totals": {"employer_cost": 600}},
        {"company_id": "c1", "id": "i2", "run_id": "r2", "employee_id": "e4", "totals": {"employer_cost": 500}},
    ],
    "leave_requests": [
        {"company_id": "c1", "employee_id": "e1", "request_status": "pending",
         "start_date": iso(TODAY + timedelta(days=2)), "end_date": iso(TODAY + timedelta(days=3)),
         "leave_type_name": "Cuti Tahunan"},
    ],
    "branches": [{"id": "b1", "company_id": "c1", "name": "Unit Operasional Surabaya"},
                 {"id": "b2", "company_id": "c1", "name": "Unit Operasional Balikpapan"}],
    "work_locations": [{"id": "wl1", "company_id": "c1", "name": "Site A"}],
    "projects": [{"id": "p1", "company_id": "c1", "name": "Proyek Alpha"},
                 {"id": "p2", "company_id": "c1", "name": "Proyek Beta"}],
    "departments": [{"id": "d1", "company_id": "c1", "name": "HRGA"},
                    {"id": "d2", "company_id": "c1", "name": "Operasional"}],
    "divisions": [{"id": "v1", "company_id": "c1", "name": "Divisi HR"},
                  {"id": "v2", "company_id": "c1", "name": "Divisi Ops"}],
    "positions": [{"id": "pos1", "company_id": "c1", "name": "Staff HR"},
                  {"id": "pos2", "company_id": "c1", "name": "Supervisor"}],
    "job_grades": [{"id": "g1", "company_id": "c1", "name": "G1"},
                   {"id": "g2", "company_id": "c1", "name": "G2"}],
    "cost_centers": [{"id": "cc1", "company_id": "c1", "name": "CC HR"},
                     {"id": "cc2", "company_id": "c1", "name": "CC Ops"}],
    "employment_statuses": [{"id": "es1", "company_id": "c1", "name": "PKWTT"},
                            {"id": "es2", "company_id": "c1", "name": "PKWT"}],
    "employee_business_statuses": [{"id": "bs1", "company_id": "c1", "name": "Aktif"},
                                   {"id": "bs2", "company_id": "c1", "name": "Tidak Aktif"}],
    "contract_types": [{"id": "ct1", "company_id": "c1", "name": "PKWT"},
                       {"id": "ct2", "company_id": "c1", "name": "PKWTT"}],
    "roster_patterns": [{"id": "pt1", "company_id": "c1", "name": "28/14"}],
    "certification_types": [{"id": "cert1", "company_id": "c1", "name": "K3"}],
}


def make_ctx(permissions, modules):
    return AuthContext(
        user={"id": "u1", "full_name": "Agus"},
        company={"id": "c1", "name": "PT Uji"},
        role_keys=["hr_admin"],
        permissions=set(permissions),
        modules=set(modules),
        is_super_admin=False,
    )


ALL_MODULES = {"hr_core", "employee_core", "attendance", "leave_overtime", "payroll",
               "recruitment", "mobilization", "asset"}
HR_PERMS = {"dashboard:view", "report:view", "payroll:view", "roster:view",
            "recruitment:view", "certification:view", "employee:view"}


async def run(ctx, **kwargs):
    db = DB({k: [dict(r) for r in v] for k, v in TABLES.items()})
    dscope.get_scope = lambda c: asyncio.sleep(0, result=type("S", (), {
        "is_all": True, "mode": "ALL_TENANT", "project_ids": [], "employee_ids": []})())
    dscope.with_scope = lambda flt, scope, field=None: dict(flt or {})
    dscope.with_project_scope = lambda flt, scope, field="project_id": dict(flt or {})
    import app.routers.dashboard_analytics as mod
    mod.get_db = lambda: db
    return await analytics(date_from=iso(START), date_to=iso(TODAY), ctx=ctx, **kwargs), db


print("== 1. KPI & pergerakan (HR lengkap) ==")
out, db = asyncio.run(run(make_ctx(HR_PERMS, ALL_MODULES)))
print("   DEBUG kpi:", {k["key"]: k["value"] for k in out["kpis"]})
print("   DEBUG headcount:", out["headcount"], "| queries employees:", db.queries.count("employees"))
kpis = {k["key"]: k for k in out["kpis"]}
check(kpis["total_employees"]["value"] == 4, "total karyawan = 4", kpis["total_employees"]["value"])
check(kpis["active_employees"]["value"] == 3, "karyawan aktif = 3", kpis["active_employees"]["value"])
check(kpis["inactive_employees"]["value"] == 1, "karyawan nonaktif = 1", kpis["inactive_employees"]["value"])
check(kpis["joined"]["value"] == 1, "masuk periode = 1", kpis["joined"]["value"])
check(kpis["exited"]["value"] == 1, "keluar periode = 1", kpis["exited"]["value"])
check(out["headcount"] == {"start": 3, "end": 3, "average": 3.0}, "headcount awal/akhir = 3/3", out["headcount"])
check(kpis["turnover"]["value"] == 33.33, "turnover = 33.33% (1/3)", kpis["turnover"]["value"])
check(out["movement"]["net_growth"] == 0, "net growth = 0", out["movement"]["net_growth"])
check(out["movement"]["mutations"] == 1, "mutasi penempatan = 1", out["movement"]["mutations"])
check(len(out["movement"]["trailing"]) == 6, "deret 6 bulan untuk sparkline tersedia",
      len(out["movement"]["trailing"]))
check(out["movement"]["trailing"][-1]["headcount"] == out["headcount"]["end"],
      "headcount deret terakhir = headcount akhir periode", out["movement"]["trailing"][-1])

print("== 2. Demografi ==")
demo = out["demography"]
genders = {i["label"]: i["count"] for i in demo["gender"]}
check(genders.get("Laki-laki") == 2 and genders.get("Perempuan") == 2, "gender 2L/2P", genders)
check(demo["missing"]["birth_date"] == 1, "tanpa tanggal lahir = 1", demo["missing"]["birth_date"])
edu = {i["label"]: i["count"] for i in demo["education"]}
check(edu.get("S1") == 3, "pendidikan S1 = 3", edu)
dep = {i["label"]: i["count"] for i in demo["dependents"]}
check(dep.get("2 tanggungan") == 1 and dep.get("Tanpa tanggungan") == 2 and dep.get("1 tanggungan") == 1,
      "tanggungan 0/1/2 = 2/1/1", dep)
bands = {i["label"]: i["count"] for i in demo["age_bands"]}
check(bands.get("Belum diisi") == 1, "kelompok usia tanpa data = 1", bands)
expected_26_35 = sum(1 for e in TABLES["employees"] if e["birth_date"] and 26 <= age_of(date.fromisoformat(e["birth_date"])) <= 35)
check(bands.get("26–35 tahun") == expected_26_35, f"kelompok 26-35 = {expected_26_35}", bands)

print("== 3. Organisasi & manpower ==")
dims = out["organization"]["dimensions"]
branch = {i["key"]: i for i in dims["branch_id"]["items"]}
check(branch.get("b1", {}).get("count") == 2 and branch.get("b1", {}).get("label") == "Unit Operasional Surabaya",
      "distribusi unit operasional memakai id + label", branch)
check(out["organization"]["coverage"] == {"assigned": 3, "unassigned": 1, "assigned_pct": 75.0},
      "coverage 3 assigned / 1 unassigned", out["organization"]["coverage"])
ctype = {i["key"]: i["count"] for i in dims["contract_type"]["items"]}
check(ctype.get("ct1") == 2 and ctype.get("ct2") == 1 and ctype.get("_none") == 1,
      "tipe kontrak ct1=2, ct2=1, tanpa kontrak=1", ctype)
check(out["availability"]["manpower_plan"]["state"] == "not_supported",
      "manpower plan ditandai not_supported", out["availability"]["manpower_plan"])

print("== 4. Roster, absensi, payroll, kompetensi, administrasi ==")
check(out["roster"]["on_leave"] == 1, "sedang cuti = 1", out["roster"]["on_leave"])
check(out["roster"]["need_confirmation"] == 1, "perlu konfirmasi = 1", out["roster"]["need_confirmation"])
check(out["roster"]["mobilization_pending"] == 1, "mobilisasi pending = 1", out["roster"]["mobilization_pending"])
check(len(out["roster"]["agenda"]) >= 3, "agenda 30 hari terisi", out["roster"]["agenda"])
check(out["attendance"]["present"] == 2, "hadir (present+late) = 2", out["attendance"]["present"])
check(abs(out["attendance"]["attendance_rate_pct"] - 66.7) < 0.1, "attendance rate 66.7%",
      out["attendance"]["attendance_rate_pct"])
check(out["attendance"]["invalid"] == 1, "catatan tidak valid = 1", out["attendance"]["invalid"])
check(out["payroll"]["state"] == "ready", "payroll ready", out["payroll"]["state"])
check(out["payroll"]["gross"] == 1000 and out["payroll"]["employer_cost"] == 1100,
      "payroll run terbaru (Nov) dipakai", out["payroll"])
check(out["payroll"]["outstanding_runs"] == 1, "run belum dibayar = 1", out["payroll"]["outstanding_runs"])
check(out["competency"]["buckets"]["expired"] == 1, "sertifikasi kedaluwarsa = 1",
      out["competency"]["buckets"])
check(out["administration"]["completeness"]["avg_pct"] == 80.0, "rata-rata kelengkapan 80%",
      out["administration"]["completeness"]["avg_pct"])
check(out["administration"]["document_expiry"]["30"] == 1, "dokumen 8-30 hari = 1",
      out["administration"]["document_expiry"])

print("== 5. Action center & insight ==")
keys = {a["key"] for a in out["action_center"]}
check("contracts_30" in keys, "action contracts_30 ada", sorted(keys))
check("certs_expired" in keys, "action certs_expired ada")
check("exit_pending" in keys, "action exit_pending ada")
check("roster_confirm" in keys, "action roster_confirm ada")
check("completeness" in keys, "action completeness ada")
insight_keys = {i["key"] for i in out["insights"]}
check("net_growth" in insight_keys and "turnover" in insight_keys, "insight pertumbuhan + turnover",
      sorted(insight_keys))
check("unassigned" in insight_keys, "insight karyawan belum ditempatkan")
check("payroll_cost" in insight_keys, "insight tren biaya payroll")

print("== 6. Cross-filter & filter master ==")
out_g, _ = asyncio.run(run(make_ctx(HR_PERMS, ALL_MODULES), gender="Laki-laki"))
check({k["key"]: k for k in out_g["kpis"]}["total_employees"]["value"] == 2,
      "filter gender label 'Laki-laki' -> 2 karyawan")
check(out_g["demography"]["gender"] and all(i["label"] == "Laki-laki" for i in out_g["demography"]["gender"]),
      "demografi ikut terfilter", out_g["demography"]["gender"])

out_ct, _ = asyncio.run(run(make_ctx(HR_PERMS, ALL_MODULES), contract_type_id="ct1"))
check({k["key"]: k for k in out_ct["kpis"]}["total_employees"]["value"] == 2,
      "filter tipe kontrak ct1 -> 2 karyawan")

out_rp, _ = asyncio.run(run(make_ctx(HR_PERMS, ALL_MODULES), roster_pattern_id="pt1"))
check({k["key"]: k for k in out_rp["kpis"]}["total_employees"]["value"] == 2,
      "filter pola roster pt1 (project p1) -> 2 karyawan")

print("== 7. Gating izin ==")
out_emp, _ = asyncio.run(run(make_ctx({"dashboard:view"}, {"hr_core", "employee_core"})))
check(out_emp["access"]["people_analytics"] is False, "tanpa report:view -> people_analytics false")
check("demography" not in out_emp, "tanpa izin -> demografi tidak dikirim")
check(out_emp["availability"]["people_analytics"]["state"] == "restricted", "alasan restricted dikirim")
check(out_emp["self"]["state"] == "ready", "ringkasan pribadi tersedia", out_emp["self"])
check("filter_options" not in out_emp, "opsi filter tidak bocor ke karyawan")

out_pay, _ = asyncio.run(run(make_ctx({"dashboard:view", "report:view"}, ALL_MODULES)))
check(out_pay["payroll"]["state"] == "restricted", "tanpa payroll:view -> payroll restricted",
      out_pay["payroll"]["state"])

print("== 8. Modul nonaktif ==")
out_nomod, _ = asyncio.run(run(make_ctx({"dashboard:view", "report:view"}, {"hr_core", "employee_core"})))
check(out_nomod["roster"]["state"] == "inactive", "roster inactive saat modul mati")
check(out_nomod["attendance"]["state"] == "inactive", "absensi inactive saat modul mati")
check(out_nomod["recruitment"]["state"] == "inactive", "rekrutmen inactive saat modul mati")

print()
if failures:
    print(f"GAGAL: {len(failures)} pemeriksaan")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("SEMUA PEMERIKSAAN LULUS")
