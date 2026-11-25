"""HR Command Center & People Analytics — agregasi server-side.

Prinsip:
- Semua angka dihitung dari tabel nyata. Tidak ada data dummy.
- Data mentah karyawan tidak dikirim ke frontend; hanya hasil agregasi.
- Modul, permission, dan Cakupan Data (01I) ditegakkan di backend.
- Bagian yang sumber datanya belum ada dikembalikan sebagai `not_supported`
  beserta alasannya, bukan angka tebakan.
"""
import asyncio
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, Query, Response

from ..core import data_scope as dscope
from ..core.db import NO_ID, get_db, serialize_list
from ..core.deps import AuthContext, require_permission
from ..core.employee_status import today_local

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

AGE_BANDS: List[Tuple[int, Optional[int], str]] = [
    (0, 17, "< 18 tahun"),
    (18, 25, "18–25 tahun"),
    (26, 35, "26–35 tahun"),
    (36, 45, "36–45 tahun"),
    (46, 55, "46–55 tahun"),
    (56, None, "> 55 tahun"),
]
TENURE_BANDS: List[Tuple[int, Optional[int], str]] = [
    (0, 0, "< 1 tahun"),
    (1, 2, "1–2 tahun"),
    (3, 5, "3–5 tahun"),
    (6, 10, "6–10 tahun"),
    (11, None, "> 10 tahun"),
]
GENDERS = {"male": "Laki-laki", "female": "Perempuan"}
MARITAL = {"belum_kawin": "Belum Kawin", "kawin": "Kawin", "duda": "Duda", "janda": "Janda"}
RELIGION = {"islam": "Islam", "kristen": "Kristen", "katolik": "Katolik", "hindu": "Hindu",
            "buddha": "Buddha", "konghucu": "Konghucu", "lainnya": "Lainnya"}
MISSING = "Belum diisi"

# Klik grafik mengirim LABEL ("Laki-laki"), sedangkan data mentah memakai kode ("male").
GENDER_CODES = {v.lower(): k for k, v in GENDERS.items()}
MARITAL_CODES = {v.lower(): k for k, v in MARITAL.items()}
RELIGION_CODES = {v.lower(): k for k, v in RELIGION.items()}

EXIT_STATES_CLOSED = ("COMPLETED",)
EXIT_STATES_OPEN = ("DRAFT", "PENDING_APPROVAL", "APPROVED")

EMP_PROJECTION = {
    "id": 1, "employee_number": 1, "full_name": 1, "gender": 1, "birth_date": 1,
    "marital_status": 1, "religion": 1, "education": 1, "join_date": 1, "status": 1,
    "employment_status_id": 1, "branch_id": 1, "work_location_id": 1, "department_id": 1,
    "division_id": 1, "position_id": 1, "job_grade_id": 1, "cost_center_id": 1,
    "project_id": 1, "city": 1, "province": 1, "user_id": 1, "photo_path": 1,
    "current_employee_status_id": 1,
}


# --------------------------------------------------------------------------- util
def _pdate(value: Any) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _today() -> date:
    return date.fromisoformat(today_local())


def _pct(part: int, total: int) -> float:
    return round((part / total) * 100, 1) if total else 0.0


def _delta(cur: float, prev: float) -> Optional[float]:
    if prev in (None, 0):
        return None if not cur else 100.0
    return round(((cur - prev) / prev) * 100, 1)


def _age(dob: Optional[date], ref: date) -> Optional[int]:
    if not dob:
        return None
    years = ref.year - dob.year - ((ref.month, ref.day) < (dob.month, dob.day))
    return years if years >= 0 else None


def _band(value: Optional[int], bands: List[Tuple[int, Optional[int], str]]) -> str:
    if value is None:
        return MISSING
    for low, high, label in bands:
        if value >= low and (high is None or value <= high):
            return label
    return MISSING


def _generation(dob: Optional[date]) -> str:
    if not dob:
        return MISSING
    year = dob.year
    if year >= 2013:
        return "Gen Alpha"
    if year >= 1997:
        return "Gen Z"
    if year >= 1981:
        return "Milenial"
    if year >= 1965:
        return "Gen X"
    return "Baby Boomer"


def _counter(pairs: List[Tuple[str, int]]) -> List[Dict[str, Any]]:
    total = sum(n for _, n in pairs)
    return [{"key": k, "label": k, "count": n, "pct": _pct(n, total)} for k, n in pairs]


def _grouped(values: List[Optional[str]], labels: Dict[str, str],
             order: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = {}
    for raw in values:
        key = str(raw or "").strip().lower()
        label = labels.get(key, raw.strip() if raw else MISSING) or MISSING
        if not raw:
            label = MISSING
        counts[label] = counts.get(label, 0) + 1
    pairs = [(k, v) for k, v in counts.items()]
    if order:
        rank = {label: i for i, label in enumerate(order)}
        pairs.sort(key=lambda x: (rank.get(x[0], len(order)), -x[1]))
    else:
        pairs.sort(key=lambda x: (-x[1], x[0]))
    return _counter(pairs)


def _top(values: List[Optional[str]], limit: int = 10, missing_label: str = MISSING) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = {}
    for raw in values:
        label = (str(raw).strip() if raw else "") or missing_label
        counts[label] = counts.get(label, 0) + 1
    pairs = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    head = [(k, v) for k, v in pairs[:limit]]
    rest = sum(v for _, v in pairs[limit:])
    total = sum(counts.values())
    out = [{"key": k, "label": k, "count": v, "pct": _pct(v, total)} for k, v in head]
    if rest:
        out.append({"key": "_other", "label": "Lainnya", "count": rest, "pct": _pct(rest, total)})
    return out


def _mode_period(date_from: Optional[date], date_to: Optional[date]) -> Tuple[date, date]:
    if date_from and date_to:
        return (date_from, date_to) if date_from <= date_to else (date_to, date_from)
    today = _today()
    return today.replace(day=1), today


def _shift_period(start: date, end: date) -> Tuple[date, date]:
    span = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    return prev_end - timedelta(days=span - 1), prev_end


def _months_between(start: date, end: date, cap: int = 24) -> List[str]:
    out: List[str] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month) and len(out) < cap:
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def _labels(rows: List[Dict[str, Any]], field: str = "name") -> Dict[str, str]:
    return {r["id"]: (r.get(field) or r.get("code") or r["id"]) for r in rows if r.get("id")}


# --------------------------------------------------------------------------- endpoint
@router.get("/analytics")
async def analytics(
    category: str = Query("summary"),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    branch_id: Optional[str] = None,
    work_location_id: Optional[str] = None,
    project_id: Optional[str] = None,
    department_id: Optional[str] = None,
    division_id: Optional[str] = None,
    position_id: Optional[str] = None,
    job_grade_id: Optional[str] = None,
    cost_center_id: Optional[str] = None,
    employment_status_id: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    contract_type_id: Optional[str] = None,
    roster_pattern_id: Optional[str] = None,
    gender: Optional[str] = None,
    age_band: Optional[str] = None,
    education: Optional[str] = None,
    marital_status: Optional[str] = None,
    religion: Optional[str] = None,
    ctx: AuthContext = Depends(require_permission("dashboard", "view")),
):
    db = get_db()
    cid = ctx.company_id
    today = _today()

    # Panggilan internal (mis. /analytics/export) tidak melewati FastAPI, sehingga nilai
    # default `Query(...)` bisa berupa objek. Normalkan agar filter tidak rusak.
    def _s(value: Any) -> Optional[str]:
        return value if isinstance(value, str) and value.strip() else None

    category = category if isinstance(category, str) and category else "summary"
    date_from, date_to = _s(date_from), _s(date_to)
    (branch_id, work_location_id, project_id, department_id, division_id, position_id,
     job_grade_id, cost_center_id, employment_status_id, status_filter, contract_type_id,
     roster_pattern_id, gender, age_band, education, marital_status, religion) = (
        _s(branch_id), _s(work_location_id), _s(project_id), _s(department_id), _s(division_id),
        _s(position_id), _s(job_grade_id), _s(cost_center_id), _s(employment_status_id),
        _s(status_filter), _s(contract_type_id), _s(roster_pattern_id), _s(gender), _s(age_band),
        _s(education), _s(marital_status), _s(religion),
    )

    start, end = _mode_period(_pdate(date_from), _pdate(date_to))
    prev_start, prev_end = _shift_period(start, end)

    can_people = ctx.has_permission("report", "view")
    can_payroll = ctx.has_module("payroll") and ctx.has_permission("payroll", "view")
    scope = await dscope.get_scope(ctx)

    # ---------- filter tambahan yang butuh pra-query ----------
    contract_employee_ids: Optional[List[str]] = None
    if contract_type_id:
        rows = await db.employee_contracts.find(
            {"company_id": cid, "contract_type_id": contract_type_id,
             "status": {"$nin": ["deleted", "archived"]}}, {"employee_id": 1}).to_list(20000)
        contract_employee_ids = list({r["employee_id"] for r in rows if r.get("employee_id")})
        if not contract_employee_ids:
            contract_employee_ids = ["-"]

    pattern_project_ids: Optional[List[str]] = None
    if roster_pattern_id:
        rows = await db.project_roster_configs.find(
            {"company_id": cid, "pattern_id": roster_pattern_id}, {"project_id": 1}).to_list(5000)
        pattern_project_ids = list({r["project_id"] for r in rows if r.get("project_id")})
        if not pattern_project_ids:
            pattern_project_ids = ["-"]

    emp_flt: Dict[str, Any] = {"company_id": cid, "status": {"$ne": "deleted"}}
    for key, value in (("branch_id", branch_id), ("work_location_id", work_location_id),
                       ("project_id", project_id), ("department_id", department_id),
                       ("division_id", division_id), ("position_id", position_id),
                       ("job_grade_id", job_grade_id), ("cost_center_id", cost_center_id),
                       ("employment_status_id", employment_status_id)):
        if value:
            emp_flt[key] = value
    # Arsip dan baris terhapus tidak pernah dihitung sebagai karyawan.
    if status_filter:
        emp_flt["status"] = status_filter
    else:
        emp_flt["status"] = {"$nin": ["archived", "deleted"]}
    if contract_employee_ids is not None:
        emp_flt["id"] = {"$in": contract_employee_ids}
    if pattern_project_ids is not None:
        emp_flt["project_id"] = {"$in": pattern_project_ids}

    emp_flt = dscope.with_scope(emp_flt, scope, "id")

    # ---------- gelombang 1: data dasar ----------
    async def _list(coll, flt, proj=None, limit=20000):
        return serialize_list(await db[coll].find(flt, proj).to_list(limit))

    tasks = [
        _list("employees", emp_flt, EMP_PROJECTION, 50000),
        _list("exit_clearances", dscope.with_scope(
            {"company_id": cid, "status": {"$ne": "deleted"}}, scope, "employee_id"),
            {"employee_id": 1, "last_working_date": 1, "case_state": 1, "exit_type": 1, "reason": 1}, 20000),
        _list("employee_family_members", {"company_id": cid, "status": {"$ne": "deleted"}},
              {"employee_id": 1, "relationship": 1}, 50000),
    ]
    employees, exits, family = await asyncio.gather(*tasks)

    # ---------- filter atribut personal (cross-filter) ----------
    def _keep(row: Dict[str, Any]) -> bool:
        if gender:
            want = GENDER_CODES.get(str(gender).strip().lower(), str(gender).strip().lower())
            if str(row.get("gender") or "").strip().lower() != want:
                return False
        if education and (str(row.get("education") or "").strip() or MISSING) != education:
            return False
        if marital_status:
            want = MARITAL_CODES.get(str(marital_status).strip().lower(), str(marital_status).strip().lower())
            if str(row.get("marital_status") or "").strip().lower() != want:
                return False
        if religion:
            want = RELIGION_CODES.get(str(religion).strip().lower(), str(religion).strip().lower())
            if str(row.get("religion") or "").strip().lower() != want:
                return False
        if age_band and _band(_age(_pdate(row.get("birth_date")), today), AGE_BANDS) != age_band:
            return False
        return True

    employees = [r for r in employees if _keep(r)]

    # ---------- headcount & periode ----------
    exit_map: Dict[str, date] = {}
    for ex in exits:
        if (ex.get("case_state") or "").upper() in EXIT_STATES_CLOSED:
            d = _pdate(ex.get("last_working_date"))
            if d:
                exit_map[ex["employee_id"]] = min(d, exit_map.get(ex["employee_id"], d))

    def _headcount(at: date) -> int:
        n = 0
        for row in employees:
            joined = _pdate(row.get("join_date"))
            if joined and joined > at:
                continue
            exited = exit_map.get(row["id"])
            if exited and exited <= at:
                continue
            n += 1
        return n

    total = len(employees)
    active = sum(1 for r in employees if (r.get("status") or "") == "active")
    joined = sum(1 for r in employees if (jd := _pdate(r.get("join_date"))) and start <= jd <= end)
    prev_joined = sum(1 for r in employees if (jd := _pdate(r.get("join_date"))) and prev_start <= jd <= prev_end)
    exited = sum(1 for d in exit_map.values() if start <= d <= end)
    prev_exited = sum(1 for d in exit_map.values() if prev_start <= d <= prev_end)
    hc_start, hc_end = _headcount(start), _headcount(end)
    prev_hc_start, prev_hc_end = _headcount(prev_start), _headcount(prev_end)
    avg_hc = (hc_start + hc_end) / 2 if (hc_start or hc_end) else 0
    prev_avg = (prev_hc_start + prev_hc_end) / 2 if (prev_hc_start or prev_hc_end) else 0
    turnover = round((exited / avg_hc) * 100, 2) if avg_hc else 0.0
    prev_turnover = round((prev_exited / prev_avg) * 100, 2) if prev_avg else 0.0

    ages = [a for a in (_age(_pdate(r.get("birth_date")), today) for r in employees) if a is not None]
    tenures = []
    for r in employees:
        jd = _pdate(r.get("join_date"))
        if jd:
            tenures.append((today - jd).days / 365.25)
    avg_age = round(sum(ages) / len(ages), 1) if ages else None
    avg_tenure = round(sum(tenures) / len(tenures), 1) if tenures else None

    def _kpi(key, label, value, prev=None, unit="count", good_when="up", link=None, tooltip=None,
             available=True, note=None):
        return {"key": key, "label": label, "value": value, "prev": prev, "delta_pct": _delta(value, prev),
                "unit": unit, "good_when": good_when, "link": link, "tooltip": tooltip,
                "available": available, "note": note}

    kpis = [
        _kpi("total_employees", "Total Karyawan", total, prev_hc_end, link="/employees",
             tooltip="Jumlah karyawan aktif dan nonaktif pada filter aktif (tanpa arsip)."),
        _kpi("active_employees", "Karyawan Aktif", active, None, link="/employees?status=active",
             tooltip="Karyawan dengan status data aktif pada filter aktif."),
        _kpi("inactive_employees", "Karyawan Nonaktif", total - active, None, link="/employees?status=inactive",
             good_when="down", tooltip="Karyawan yang tidak lagi aktif."),
        _kpi("joined", "Masuk Periode", joined, prev_joined, link="/employees/import",
             tooltip=f"Tanggal masuk antara {start.isoformat()} dan {end.isoformat()}."),
        _kpi("exited", "Keluar Periode", exited, prev_exited, good_when="down",
             link="/employees/exit-clearance/history",
             tooltip="Exit clearance berstatus selesai dengan tanggal kerja terakhir pada periode."),
        _kpi("turnover", "Turnover Rate", turnover, prev_turnover, unit="percent", good_when="down",
             link="/reports?type=exit",
             tooltip="Karyawan keluar ÷ rata-rata headcount awal & akhir periode × 100."),
    ]
    extra_kpis = [
        _kpi("retention", "Retention Rate", round(100 - turnover, 2) if avg_hc else None, None, unit="percent"),
        _kpi("avg_age", "Rata-rata Usia", avg_age, None, unit="year",
             available=avg_age is not None, note=None if avg_age is not None else "Tanggal lahir belum lengkap."),
        _kpi("avg_tenure", "Rata-rata Masa Kerja", avg_tenure, None, unit="year",
             available=avg_tenure is not None),
    ]

    result: Dict[str, Any] = {
        "as_of": today.isoformat(),
        "category": category,
        "period": {"from": start.isoformat(), "to": end.isoformat(),
                   "previous_from": prev_start.isoformat(), "previous_to": prev_end.isoformat()},
        "filters": {"applied": {k: v for k, v in {
            "branch_id": branch_id, "work_location_id": work_location_id, "project_id": project_id,
            "department_id": department_id, "division_id": division_id, "position_id": position_id,
            "job_grade_id": job_grade_id, "cost_center_id": cost_center_id,
            "employment_status_id": employment_status_id, "status": status_filter,
            "contract_type_id": contract_type_id, "roster_pattern_id": roster_pattern_id,
            "gender": gender, "age_band": age_band, "education": education,
            "marital_status": marital_status, "religion": religion,
        }.items() if v}},
        "access": {"people_analytics": can_people, "payroll_cost": can_payroll},
        "kpis": kpis,
        "kpi_extra": extra_kpis,
        "headcount": {"start": hc_start, "end": hc_end, "average": round(avg_hc, 1)},
        "availability": {},
    }

    if not can_people:
        # Tanpa izin analitik lintas karyawan: hanya ringkasan pribadi.
        result["availability"]["people_analytics"] = {
            "state": "restricted",
            "note": "Analitik agregat karyawan memerlukan izin Laporan (report:view).",
        }
        result["self"] = await _self_section(db, ctx, today)
        return result

    # ---------- gelombang 2: data analitik ----------
    months = _months_between(start, end)
    leave_flt = dscope.with_scope({"company_id": cid, "status": {"$ne": "deleted"}}, scope, "employee_id")
    mob_flt = dscope.with_scope({"company_id": cid, "status": {"$ne": "deleted"}}, scope, "employee_id")

    wave2 = [
        _list("branches", {"company_id": cid}, {"id": 1, "name": 1, "code": 1}, 2000),
        _list("work_locations", {"company_id": cid}, {"id": 1, "name": 1, "code": 1}, 5000),
        _list("projects", {"company_id": cid}, {"id": 1, "name": 1, "code": 1}, 5000),
        _list("departments", {"company_id": cid}, {"id": 1, "name": 1, "code": 1}, 5000),
        _list("divisions", {"company_id": cid}, {"id": 1, "name": 1, "code": 1}, 5000),
        _list("positions", {"company_id": cid}, {"id": 1, "name": 1, "code": 1}, 10000),
        _list("job_grades", {"company_id": cid}, {"id": 1, "name": 1, "code": 1}, 2000),
        _list("cost_centers", {"company_id": cid}, {"id": 1, "name": 1, "code": 1}, 5000),
        _list("employment_statuses", {"company_id": cid}, {"id": 1, "name": 1, "code": 1}, 2000),
        _list("employee_business_statuses", {"company_id": cid}, {"id": 1, "name": 1}, 2000),
        _list("contract_types", {"company_id": cid}, {"id": 1, "name": 1, "code": 1}, 2000),
        _list("roster_patterns", {"company_id": cid}, {"id": 1, "name": 1, "code": 1}, 2000),
        _list("employee_contracts", dscope.with_scope(
            {"company_id": cid, "status": {"$nin": ["deleted", "archived"]}}, scope, "employee_id"),
            {"employee_id": 1, "contract_type_id": 1, "start_date": 1, "end_date": 1}, 50000),
        _list("employee_certifications", dscope.with_scope(
            {"company_id": cid, "status": {"$nin": ["deleted", "archived"]}}, scope, "employee_id"),
            {"employee_id": 1, "certification_type_id": 1, "name": 1, "expiry_date": 1}, 50000),
        _list("certification_types", {"company_id": cid}, {"id": 1, "name": 1}, 2000),
        _list("documents", dscope.with_scope(
            {"company_id": cid, "is_deleted": {"$ne": True}, "owner_type": "employee",
             "expiry_date": {"$nin": [None, ""]}}, scope, "owner_id"),
            {"owner_id": 1, "owner_label": 1, "expiry_date": 1, "name": 1}, 50000),
        _list("employee_completeness", {"company_id": cid},
              {"employee_id": 1, "score_pct": 1, "completeness_status": 1, "missing_codes": 1}, 50000),
        _list("employee_assignments", dscope.with_scope(
            {"company_id": cid, "status": {"$ne": "deleted"}}, scope, "employee_id"),
            {"employee_id": 1, "project_id": 1, "start_date": 1, "end_date": 1,
             "previous_assignment_id": 1, "reason": 1}, 50000),
        _list("roster_leave_plans", leave_flt,
              {"employee_id": 1, "project_id": 1, "off_start": 1, "off_end": 1, "plan_status": 1,
               "replacement_employee_id": 1}, 20000),
        _list("roster_mobilizations", mob_flt,
              {"employee_id": 1, "project_id": 1, "depart_date": 1, "return_date": 1,
               "mobilization_state": 1, "approval_state": 1}, 20000),
    ]
    (
        branch_rows, loc_rows, proj_rows, dept_rows, div_rows, pos_rows, grade_rows, cc_rows,
        empstatus_rows, bizstatus_rows, ctype_rows, pattern_rows, contracts, certs, certtype_rows,
        doc_rows, completeness_rows, assignment_rows, plan_rows, mob_rows,
    ) = await asyncio.gather(*wave2)

    maps = {
        "branch_id": _labels(branch_rows), "work_location_id": _labels(loc_rows),
        "project_id": _labels(proj_rows), "department_id": _labels(dept_rows),
        "division_id": _labels(div_rows), "position_id": _labels(pos_rows),
        "job_grade_id": _labels(grade_rows), "cost_center_id": _labels(cc_rows),
        "employment_status_id": _labels(empstatus_rows),
        "current_employee_status_id": _labels(bizstatus_rows),
        "contract_type_id": _labels(ctype_rows), "roster_pattern_id": _labels(pattern_rows),
    }

    # Opsi filter global — hanya untuk pengguna berizin analitik (tidak membocorkan master ke karyawan).
    def _opts(rows: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        items = [{"id": r["id"], "label": r.get("name") or r.get("code") or r["id"]}
                 for r in rows if r.get("id")]
        return sorted(items, key=lambda x: str(x["label"]).lower())

    result["filter_options"] = {
        "branches": _opts(branch_rows),
        "work_locations": _opts(loc_rows),
        "projects": _opts(proj_rows),
        "departments": _opts(dept_rows),
        "divisions": _opts(div_rows),
        "positions": _opts(pos_rows),
        "job_grades": _opts(grade_rows),
        "cost_centers": _opts(cc_rows),
        "employment_statuses": _opts(empstatus_rows),
        "contract_types": _opts(ctype_rows),
        "roster_patterns": _opts(pattern_rows),
    }

    # ---------- demografi ----------
    result["demography"] = {
        "basis": total,
        "gender": _grouped([r.get("gender") for r in employees], GENDERS, ["Laki-laki", "Perempuan", MISSING]),
        "age_bands": _grouped([_band(_age(_pdate(r.get("birth_date")), today), AGE_BANDS) for r in employees],
                              {}, [label for _, _, label in AGE_BANDS] + [MISSING]),
        "generation": _grouped([_generation(_pdate(r.get("birth_date"))) for r in employees], {},
                               ["Gen Z", "Milenial", "Gen X", "Baby Boomer", "Gen Alpha", MISSING]),
        "marital_status": _grouped([r.get("marital_status") for r in employees], MARITAL,
                                   ["Belum Kawin", "Kawin", "Duda", "Janda", MISSING]),
        "religion": _grouped([r.get("religion") for r in employees], RELIGION,
                             list(RELIGION.values()) + [MISSING]),
        "education": _top([r.get("education") for r in employees], 8),
        "tenure_bands": _grouped([_band(int(t), TENURE_BANDS) if t is not None else MISSING for t in tenures],
                                 {}, [label for _, _, label in TENURE_BANDS] + [MISSING]),
        "province": _top([r.get("province") or r.get("city") for r in employees], 10),
        "avg_age": avg_age,
        "avg_tenure": avg_tenure,
        "missing": {
            "birth_date": sum(1 for r in employees if not r.get("birth_date")),
            "gender": sum(1 for r in employees if not r.get("gender")),
            "education": sum(1 for r in employees if not r.get("education")),
            "religion": sum(1 for r in employees if not r.get("religion")),
            "marital_status": sum(1 for r in employees if not r.get("marital_status")),
            "photo": sum(1 for r in employees if not r.get("photo_path")),
        },
    }
    # tanggungan keluarga dari tabel nyata
    counts: Dict[str, int] = {}
    for fam in family:
        eid = fam.get("employee_id")
        if eid:
            counts[eid] = counts.get(eid, 0) + 1
    dependents = [counts.get(r["id"], 0) for r in employees]
    depend_buckets = {"0": 0, "1": 0, "2": 0, "3+": 0}
    for n in dependents:
        depend_buckets["0" if n == 0 else "1" if n == 1 else "2" if n == 2 else "3+"] += 1
    result["demography"]["dependents"] = [
        {"key": k, "label": {"0": "Tanpa tanggungan", "1": "1 tanggungan", "2": "2 tanggungan",
                             "3+": "3+ tanggungan"}[k], "count": v, "pct": _pct(v, len(employees))}
        for k, v in depend_buckets.items()
    ]
    result["availability"]["citizenship"] = {
        "state": "not_supported",
        "note": "Field kewarganegaraan belum ada pada master karyawan.",
    }
    result["availability"]["blood_type"] = {
        "state": "not_supported",
        "note": "Data golongan darah tidak disimpan pada master karyawan.",
    }

    # ---------- organisasi ----------
    def _dist(field: str) -> List[Dict[str, Any]]:
        """Distribusi per dimensi dengan KEY = id master (agar bisa dipakai sebagai filter)."""
        label_map = maps.get(field, {})
        counts: Dict[str, int] = {}
        for r in employees:
            raw = r.get(field)
            key = raw or "_none"
            counts[key] = counts.get(key, 0) + 1
        total = len(employees)
        items = []
        for key, n in sorted(counts.items(), key=lambda x: (-x[1], str(x[0]))):
            label = MISSING if key == "_none" else (label_map.get(key) or key)
            items.append({"key": key, "label": label, "count": n, "pct": _pct(n, total)})
        return items

    contract_by_emp: Dict[str, List[Dict[str, Any]]] = {}
    for c in contracts:
        contract_by_emp.setdefault(c.get("employee_id"), []).append(c)

    ctype_counts: Dict[str, int] = {}
    for r in employees:
        rows_c = contract_by_emp.get(r["id"]) or []
        raw = rows_c[0].get("contract_type_id") if rows_c else None
        key = raw or "_none"
        ctype_counts[key] = ctype_counts.get(key, 0) + 1
    ctype_total = len(employees)
    ctype_dist = [
        {"key": key, "label": (MISSING if key == "_none" else (maps["contract_type_id"].get(key) or key)),
         "count": n, "pct": _pct(n, ctype_total)}
        for key, n in sorted(ctype_counts.items(), key=lambda x: (-x[1], str(x[0])))
    ]

    pattern_by_project = None  # placeholder dihapus
    assigned = sum(1 for r in employees if r.get("project_id"))
    result["organization"] = {
        "basis": total,
        "dimensions": {
            "branch_id": {"label": "Unit Operasional", "items": _dist("branch_id"), "field": "branch_id"},
            "work_location_id": {"label": "Lokasi Kerja", "items": _dist("work_location_id"), "field": "work_location_id"},
            "project_id": {"label": "Proyek", "items": _dist("project_id"), "field": "project_id"},
            "department_id": {"label": "Departemen", "items": _dist("department_id"), "field": "department_id"},
            "division_id": {"label": "Divisi", "items": _dist("division_id"), "field": "division_id"},
            "position_id": {"label": "Jabatan", "items": _dist("position_id"), "field": "position_id"},
            "job_grade_id": {"label": "Grade / Level", "items": _dist("job_grade_id"), "field": "job_grade_id"},
            "cost_center_id": {"label": "Cost Center", "items": _dist("cost_center_id"), "field": "cost_center_id"},
            "employment_status_id": {"label": "Status Kepegawaian", "items": _dist("employment_status_id"), "field": "employment_status_id"},
            "business_status": {"label": "Status Karyawan", "items": _dist("current_employee_status_id"), "field": "current_employee_status_id"},
            "contract_type": {"label": "Tipe Kontrak", "items": ctype_dist, "field": None},
        },
        "coverage": {
            "assigned": assigned,
            "unassigned": total - assigned,
            "assigned_pct": _pct(assigned, total),
        },
    }
    result["organization"]["dimensions"]["roster_pattern"] = {
        "label": "Pola Roster", "items": [], "field": None,
        "state": "not_supported",
        "note": "Pola roster melekat pada project, bukan pada karyawan. Lihat modul Roster untuk konfigurasi per project.",
    }
    result["availability"]["manpower_plan"] = {
        "state": "not_supported",
        "note": "Belum ada tabel manpower plan/request. Angka Plan vs Actual tidak dapat dihitung tanpa data rencana.",
    }

    # ---------- pergerakan ----------
    trend = []
    for m in months:
        j = sum(1 for r in employees if (jd := _pdate(r.get("join_date"))) and jd.isoformat()[:7] == m)
        e = sum(1 for d in exit_map.values() if d.isoformat()[:7] == m)
        trend.append({"month": m, "joined": j, "exited": e, "net": j - e})

    exit_types = _grouped([ex.get("exit_type") for ex in exits
                           if (ex.get("case_state") or "").upper() in EXIT_STATES_CLOSED
                           and start <= (_pdate(ex.get("last_working_date")) or date.min) <= end], {}, None)
    exit_reasons = _top([ex.get("reason") for ex in exits
                         if (ex.get("case_state") or "").upper() in EXIT_STATES_CLOSED
                         and start <= (_pdate(ex.get("last_working_date")) or date.min) <= end], 6)

    mutations = sum(1 for a in assignment_rows
                    if (sd := _pdate(a.get("start_date"))) and start <= sd <= end and a.get("previous_assignment_id"))
    new_placements = sum(1 for a in assignment_rows
                         if (sd := _pdate(a.get("start_date"))) and start <= sd <= end and not a.get("previous_assignment_id"))

    result["movement"] = {
        "period_months": months,
        "trend": trend,
        "joined": joined,
        "exited": exited,
        "net_growth": joined - exited,
        "turnover_pct": turnover,
        "previous_turnover_pct": prev_turnover,
        "retention_pct": round(100 - turnover, 2) if avg_hc else None,
        "mutations": mutations,
        "new_placements": new_placements,
        "exits_by_type": exit_types,
        "exits_by_reason": exit_reasons,
        "not_supported": {"promotion": "Riwayat promosi/demosi belum memiliki tabel tersendiri."},
    }

    # ---------- rekrutmen ----------
    recruitment_block: Dict[str, Any] = {"state": "inactive"}
    if ctx.has_module("recruitment") and ctx.has_permission("recruitment", "view"):
        cand_rows = await _list("candidates", {"company_id": cid, "status": {"$ne": "deleted"}},
                                {"id": 1, "stage_status": 1, "applied_at": 1, "source": 1,
                                 "converted_at": 1, "employee_id": 1}, 50000)
        stage_labels = {
            "draft": "Draft", "screening": "Screening", "screening_passed": "Lolos Screening",
            "screening_failed": "Tidak Lolos", "interview_scheduled": "Interview Dijadwalkan",
            "interview_done": "Interview Selesai", "awaiting_approval": "Menunggu Approval",
            "approved": "Disetujui", "rejected": "Ditolak", "offering": "Offering",
            "offering_accepted": "Offering Diterima", "offering_declined": "Offering Ditolak",
            "hired": "Menjadi Karyawan",
        }
        in_period = [c for c in cand_rows
                     if (ap := _pdate(c.get("applied_at"))) and start <= ap <= end]
        hired = [c for c in cand_rows if c.get("employee_id") or (c.get("stage_status") == "hired")]
        tth = []
        for c in hired:
            ap, cv = _pdate(c.get("applied_at")), _pdate(c.get("converted_at"))
            if ap and cv and cv >= ap:
                tth.append((cv - ap).days)
        recruitment_block = {
            "state": "ready" if cand_rows else "no_data",
            "total_candidates": len(in_period),
            "pipeline": sum(1 for c in cand_rows if (c.get("stage_status") or "") in {
                "draft", "screening", "screening_passed", "interview_scheduled", "interview_done",
                "awaiting_approval", "approved", "offering", "offering_accepted"}),
            "hired": len(hired),
            "time_to_hire_days": round(sum(tth) / len(tth), 1) if tth else None,
            "funnel": _grouped([c.get("stage_status") for c in cand_rows], stage_labels,
                               ["draft", "screening", "screening_passed", "interview_scheduled",
                                "interview_done", "awaiting_approval", "approved", "offering",
                                "offering_accepted", "hired"]),
            "sources": _top([c.get("source") for c in in_period], 8),
            "not_supported": {"fulfillment_rate": "Belum ada tabel manpower request sebagai penyebut."},
        }
    result["recruitment"] = recruitment_block

    # ---------- roster & cuti ----------
    roster_block: Dict[str, Any] = {"state": "inactive"}
    if ctx.has_module("mobilization") and ctx.has_permission("roster", "view"):
        iso = today.isoformat()
        on_leave = [p for p in plan_rows if p.get("plan_status") == "CONFIRMED"
                    and str(p.get("off_start")) <= iso <= str(p.get("off_end"))]
        upcoming7 = [p for p in plan_rows if p.get("plan_status") in ("PLANNED", "CONFIRMED")
                     and iso < str(p.get("off_start")) <= (today + timedelta(days=7)).isoformat()]
        upcoming30 = [p for p in plan_rows if p.get("plan_status") in ("PLANNED", "CONFIRMED")
                      and iso < str(p.get("off_start")) <= (today + timedelta(days=30)).isoformat()]
        need_confirm = [p for p in plan_rows if p.get("plan_status") == "PLANNED"
                        and str(p.get("off_start")) <= (today + timedelta(days=10)).isoformat()]
        returning7 = [p for p in plan_rows if p.get("plan_status") == "CONFIRMED"
                      and iso < str(p.get("off_end")) <= (today + timedelta(days=7)).isoformat()]
        mob_pending = [m for m in mob_rows if (m.get("approval_state") or "APPROVED") == "PENDING_APPROVAL"
                       and (m.get("mobilization_state") or "") != "CANCELLED"]
        mob7 = [m for m in mob_rows if (m.get("mobilization_state") or "") != "CANCELLED"
                and (dd := _pdate(m.get("depart_date"))) and today <= dd <= today + timedelta(days=7)]
        agenda = []
        for p in plan_rows:
            if p.get("plan_status") not in ("PLANNED", "CONFIRMED"):
                continue
            s = _pdate(p.get("off_start"))
            if s and today <= s <= today + timedelta(days=30):
                agenda.append({"kind": "leave_start", "date": s.isoformat(),
                               "label": "Mulai cuti project", "project_id": p.get("project_id"),
                               "employee_id": p.get("employee_id")})
            e = _pdate(p.get("off_end"))
            if e and today <= e <= today + timedelta(days=30):
                agenda.append({"kind": "leave_end", "date": e.isoformat(),
                               "label": "Kembali bekerja", "project_id": p.get("project_id"),
                               "employee_id": p.get("employee_id")})
        for m in mob_rows:
            for field, kind, label in (("depart_date", "mobilization", "Mobilisasi berangkat"),
                                       ("return_date", "demobilization", "Demobilisasi pulang")):
                d = _pdate(m.get(field))
                if d and today <= d <= today + timedelta(days=30):
                    agenda.append({"kind": kind, "date": d.isoformat(), "label": label,
                                   "project_id": m.get("project_id"), "employee_id": m.get("employee_id")})
        agenda.sort(key=lambda x: x["date"])
        roster_block = {
            "state": "ready",
            "on_leave": len(on_leave),
            "upcoming_7": len(upcoming7),
            "upcoming_30": len(upcoming30),
            "need_confirmation": len(need_confirm),
            "returning_7": len(returning7),
            "mobilization_pending": len(mob_pending),
            "mobilization_7": len(mob7),
            "replacement_assigned": sum(1 for p in on_leave if p.get("replacement_employee_id")),
            "replacement_missing": sum(1 for p in on_leave if not p.get("replacement_employee_id")),
            "agenda": agenda[:40],
        }
    result["roster"] = roster_block

    # ---------- absensi ----------
    attendance_block: Dict[str, Any] = {"state": "inactive"}
    if ctx.has_module("attendance"):
        att_rows = await _list("attendances", {"company_id": cid,
                                               "work_date": {"$gte": start.isoformat(),
                                                             "$lte": end.isoformat()}},
                               {"attendance_status": 1, "late_minutes": 1, "actual_work_minutes": 1,
                                "approved_overtime_minutes": 1, "is_valid": 1}, 200000)
        if not att_rows:
            attendance_block = {"state": "no_data",
                                "note": "Belum ada catatan kehadiran pada periode ini."}
        else:
            cnt: Dict[str, int] = {}
            for a in att_rows:
                k = a.get("attendance_status") or "no_schedule"
                cnt[k] = cnt.get(k, 0) + 1
            worked = [a for a in att_rows if a.get("attendance_status") not in ("day_off", "holiday", "no_schedule")]
            present = sum(cnt.get(k, 0) for k in ("present", "late", "early_leave", "late_and_early_leave"))
            attendance_block = {
                "state": "ready",
                "basis": len(worked),
                "present": present,
                "late": cnt.get("late", 0) + cnt.get("late_and_early_leave", 0),
                "absent": cnt.get("absent", 0),
                "leave": cnt.get("leave", 0) + cnt.get("unpaid_leave", 0),
                "permission": cnt.get("permission", 0),
                "sick": cnt.get("sick", 0),
                "no_check_out": cnt.get("no_check_out", 0),
                "awaiting_location_approval": cnt.get("awaiting_location_approval", 0),
                "attendance_rate_pct": _pct(present, len(worked)) if worked else None,
                "work_minutes": sum(int(a.get("actual_work_minutes") or 0) for a in att_rows),
                "overtime_minutes": sum(int(a.get("approved_overtime_minutes") or 0) for a in att_rows),
                "invalid": sum(1 for a in att_rows if a.get("is_valid") is False),
                "by_status": _grouped([a.get("attendance_status") for a in att_rows], {}, None),
            }
    result["attendance"] = attendance_block

    # ---------- payroll ----------
    payroll_block: Dict[str, Any] = {"state": "restricted" if ctx.has_module("payroll") else "inactive"}
    if can_payroll:
        runs = await _list("payroll_runs", {"company_id": cid, "status": {"$ne": "deleted"}},
                           {"id": 1, "year": 1, "month": 1, "period_label": 1, "run_status": 1,
                            "totals": 1, "employee_count": 1, "payment_date": 1}, 500)
        runs = [r for r in runs if (r.get("run_status") or "").lower() not in ("deleted", "draft", "cancelled")]
        runs.sort(key=lambda r: (int(r.get("year") or 0), int(r.get("month") or 0)))
        if not runs:
            payroll_block = {"state": "no_data",
                             "note": "Belum ada payroll run yang dihitung."}
        else:
            latest = runs[-1]
            totals = latest.get("totals") or {}
            emp_by_branch = {r["id"]: maps["branch_id"].get(r.get("branch_id")) for r in employees}
            items = await _list("payroll_items", {"company_id": cid, "run_id": latest["id"]},
                                {"employee_id": 1, "totals": 1}, 50000)
            by_unit: Dict[str, float] = {}
            for it in items:
                unit = emp_by_branch.get(it.get("employee_id")) or MISSING
                by_unit[unit] = by_unit.get(unit, 0) + float((it.get("totals") or {}).get("employer_cost") or 0)
            trend = [{"period": r.get("period_label"),
                      "employer_cost": float((r.get("totals") or {}).get("employer_cost") or 0),
                      "gross": float((r.get("totals") or {}).get("gross") or 0)}
                     for r in runs[-6:]]
            payroll_block = {
                "state": "ready",
                "period": latest.get("period_label"),
                "run_status": (latest.get("run_status") or "").upper(),
                "employee_count": latest.get("employee_count"),
                "gross": float(totals.get("gross") or 0),
                "net_pay": float(totals.get("net_pay") or 0),
                "bpjs_employee": float(totals.get("bpjs_employee") or 0),
                "bpjs_employer": float(totals.get("bpjs_employer") or 0),
                "pph21": float(totals.get("pph21") or 0),
                "total_deductions": float(totals.get("total_deductions") or 0),
                "employer_cost": float(totals.get("employer_cost") or 0),
                "by_unit": [{"label": k, "value": round(v)} for k, v in
                            sorted(by_unit.items(), key=lambda x: -x[1])[:10]],
                "trend": trend,
                "outstanding_runs": sum(1 for r in runs
                                        if (r.get("run_status") or "").upper() not in ("PAID",)),
            }
    result["payroll"] = payroll_block

    # ---------- kompetensi ----------
    cert_buckets = {"active": 0, "expiring_90": 0, "expired": 0, "no_expiry": 0}
    cert_rows = [c for c in certs if c.get("employee_id") in {r["id"] for r in employees}]
    for c in cert_rows:
        exp = _pdate(c.get("expiry_date"))
        if not exp:
            cert_buckets["no_expiry"] += 1
        elif exp < today:
            cert_buckets["expired"] += 1
        elif exp <= today + timedelta(days=90):
            cert_buckets["expiring_90"] += 1
        else:
            cert_buckets["active"] += 1
    cert_type_map = _labels(certtype_rows)
    result["competency"] = {
        "state": "ready",
        "total": len(cert_rows),
        "buckets": cert_buckets,
        "by_type": _top([cert_type_map.get(c.get("certification_type_id")) or c.get("name")
                          for c in cert_rows], 10),
        "not_supported": {"training": "Belum ada tabel pelatihan/riwayat training."},
    }

    # ---------- administrasi & kepatuhan ----------
    comp_by_emp = None  # tidak dipakai; kelengkapan dihitung agregat
    scores = [float(c.get("score_pct") or 0) for c in completeness_rows
              if c.get("employee_id") in {r["id"] for r in employees}]
    status_counts: Dict[str, int] = {}
    for c in completeness_rows:
        if c.get("employee_id") in {r["id"] for r in employees}:
            k = c.get("completeness_status") or MISSING
            status_counts[k] = status_counts.get(k, 0) + 1
    missing_counter: Dict[str, int] = {}
    for c in completeness_rows:
        for code in (c.get("missing_codes") or []):
            missing_counter[code] = missing_counter.get(code, 0) + 1
    top_missing = sorted(missing_counter.items(), key=lambda x: -x[1])[:8]

    def _bucket_expiry(dates: List[date]) -> Dict[str, int]:
        out = {"7": 0, "30": 0, "60": 0, "90": 0, "expired": 0}
        for d in dates:
            delta = (d - today).days
            if delta < 0:
                out["expired"] += 1
            elif delta <= 7:
                out["7"] += 1
            elif delta <= 30:
                out["30"] += 1
            elif delta <= 60:
                out["60"] += 1
            elif delta <= 90:
                out["90"] += 1
        return out

    doc_dates = [d for d in (_pdate(x.get("expiry_date")) for x in doc_rows) if d]
    contract_dates = [d for d in (_pdate(c.get("end_date")) for c in contracts) if d]
    result["administration"] = {
        "state": "ready" if employees else "no_data",
        "completeness": {
            "evaluated": len(scores),
            "avg_pct": round(sum(scores) / len(scores), 1) if scores else None,
            "by_status": [{"key": k, "label": k, "count": v, "pct": _pct(v, len(scores))}
                          for k, v in sorted(status_counts.items(), key=lambda x: -x[1])],
            "top_missing": [{"code": k, "label": k, "count": v} for k, v in top_missing],
            "not_evaluated": total - len(scores),
        },
        "document_expiry": _bucket_expiry(doc_dates),
        "contract_expiry": _bucket_expiry(contract_dates),
    }
    # Profil administratif: butuh kolom yang tidak ada di proyeksi dasar.
    extra_rows = await _list("employees", emp_flt,
                             {"id": 1, "bank_account_number": 1, "npwp": 1,
                              "bpjs_kesehatan_number": 1, "emergency_contact_name": 1}, 50000)
    result["administration"]["profile"] = {
        "without_photo": sum(1 for r in employees if not r.get("photo_path")),
        "without_bank": sum(1 for r in extra_rows if not r.get("bank_account_number")),
        "without_npwp": sum(1 for r in extra_rows if not r.get("npwp")),
        "without_bpjs": sum(1 for r in extra_rows if not r.get("bpjs_kesehatan_number")),
        "without_emergency_contact": sum(1 for r in extra_rows if not r.get("emergency_contact_name")),
    }

    # ---------- action center ----------
    iso = today.isoformat()
    horizon30 = (today + timedelta(days=30)).isoformat()
    pending_exit = [e for e in exits if (e.get("case_state") or "").upper() == "PENDING_APPROVAL"]
    overdue_exit = [e for e in pending_exit if str(e.get("last_working_date") or "") <= iso]
    contracts_30 = [c for c in contracts if (d := _pdate(c.get("end_date"))) and today <= d <= today + timedelta(days=30)]
    contracts_expired = [c for c in contracts if (d := _pdate(c.get("end_date"))) and d < today]
    certs_30 = [c for c in cert_rows if (d := _pdate(c.get("expiry_date"))) and today <= d <= today + timedelta(days=30)]
    certs_expired = [c for c in cert_rows if (d := _pdate(c.get("expiry_date"))) and d < today]
    docs_30 = [d for d in doc_dates if today <= d <= today + timedelta(days=30)]
    docs_expired = [d for d in doc_dates if d < today]
    incomplete = total - len(scores)
    low_completeness = sum(1 for c in completeness_rows
                           if c.get("employee_id") in {r["id"] for r in employees}
                           and float(c.get("score_pct") or 0) < 80)

    action = [
        ("exit_overdue", "Exit clearance melewati tanggal kerja", len(overdue_exit), "critical",
         "/employees/exit-clearance", "Belum disetujui padahal tanggal kerja terakhir sudah lewat."),
        ("exit_pending", "Exit clearance menunggu persetujuan", len(pending_exit), "warning",
         "/employees/exit-clearance", "Periksa checklist serah terima."),
        ("contracts_expired", "Kontrak sudah berakhir", len(contracts_expired), "critical",
         "/reminders?kind=contract&state=expired", "Perbarui atau arsipkan kontrak."),
        ("contracts_30", "Kontrak berakhir ≤ 30 hari", len(contracts_30), "warning",
         "/reminders?kind=contract", "Siapkan perpanjangan."),
        ("certs_expired", "Sertifikasi kedaluwarsa", len(certs_expired), "critical",
         "/reminders?kind=certification", "Sertifikat kedaluwarsa menghambat penempatan."),
        ("certs_30", "Sertifikasi berakhir ≤ 30 hari", len(certs_30), "warning",
         "/reminders?kind=certification", "Jadwalkan perpanjangan."),
        ("docs_expired", "Dokumen kedaluwarsa", len(docs_expired), "warning",
         "/documents?status=expired", "Perbarui dokumen karyawan."),
        ("docs_30", "Dokumen berakhir ≤ 30 hari", len(docs_30), "info",
         "/documents", "Siapkan pembaruan."),
        ("roster_confirm", "Konfirmasi rencana cuti project", len(need_confirm) if isinstance(roster_block, dict) and roster_block.get("state") == "ready" else 0,
         "warning", "/modules/mobilization/rencana", "Konfirmasi H-10 sesuai kebijakan."),
        ("completeness", "Data karyawan belum lengkap", low_completeness, "warning",
         "/employees/completeness", "Kelengkapan data di bawah 80%."),
        ("completeness_missing", "Belum dievaluasi kelengkapan", incomplete, "info",
         "/employees/completeness", "Jalankan evaluasi kelengkapan data."),
    ]
    result["action_center"] = [
        {"key": k, "title": t, "count": n, "severity": s, "link": l, "description": d,
         "state": "overdue" if k == "exit_overdue" and n else ("critical" if s == "critical" and n else s)}
        for k, t, n, s, l, d in action if n
    ]

    # ---------- executive insight (rule-based) ----------
    insights: List[Dict[str, Any]] = []
    if joined or exited:
        direction = "bertambah" if joined - exited > 0 else ("berkurang" if joined - exited < 0 else "stabil")
        insights.append({
            "key": "net_growth", "severity": "info",
            "text": (f"Tenaga kerja {direction}: {joined} masuk dan {exited} keluar "
                     f"pada {start.strftime('%d/%m/%Y')}–{end.strftime('%d/%m/%Y')} "
                     f"(net {joined - exited:+d})."),
            "source": "employees.join_date, exit_clearances", "link": "/reports?type=exit",
        })
    if prev_turnover or turnover:
        trend_word = "naik" if turnover > prev_turnover else ("turun" if turnover < prev_turnover else "tetap")
        insights.append({
            "key": "turnover", "severity": "warning" if turnover > prev_turnover else "success",
            "text": f"Turnover rate {turnover}% ({trend_word} dari {prev_turnover}% pada periode sebelumnya).",
            "source": "exit_clearances, employees.join_date", "link": "/reports?type=exit",
        })
    if result["organization"]["coverage"]["unassigned"]:
        insights.append({
            "key": "unassigned", "severity": "warning",
            "text": (f"{result['organization']['coverage']['unassigned']} karyawan belum memiliki project "
                     "penempatan (manpower tidak teralokasi)."),
            "source": "employees.project_id", "link": "/employees?tab=penempatan",
        })
    if low_completeness:
        insights.append({
            "key": "completeness", "severity": "warning",
            "text": f"{low_completeness} karyawan memiliki kelengkapan data di bawah 80%.",
            "source": "employee_completeness", "link": "/employees/completeness",
        })
    expiring_total = len(contracts_30) + len(certs_30) + len(docs_30)
    if expiring_total:
        insights.append({
            "key": "expiring", "severity": "warning",
            "text": (f"{expiring_total} dokumen/kontrak/sertifikasi berakhir dalam 30 hari "
                     f"(kontrak {len(contracts_30)}, sertifikasi {len(certs_30)}, dokumen {len(docs_30)})."),
            "source": "employee_contracts, employee_certifications, documents", "link": "/reminders",
        })
    if isinstance(payroll_block, dict) and payroll_block.get("state") == "ready":
        trend = payroll_block["trend"]
        if len(trend) >= 2 and trend[-2]["employer_cost"]:
            change = _delta(trend[-1]["employer_cost"], trend[-2]["employer_cost"])
            insights.append({
                "key": "payroll_cost", "severity": "info",
                "text": (f"Biaya tenaga kerja {payroll_block['period']} "
                         f"{'naik' if (change or 0) > 0 else 'turun'} {abs(change or 0)}% "
                         "dibanding periode payroll sebelumnya."),
                "source": "payroll_runs.totals", "link": "/payroll/runs",
            })
    result["insights"] = insights
    result["self"] = await _self_section(db, ctx, today)
    return result


async def _self_section(db, ctx: AuthContext, today: date) -> Dict[str, Any]:
    """Ringkasan pribadi: dipakai karyawan tanpa izin analitik lintas karyawan."""
    emp = await db.employees.find_one({"company_id": ctx.company_id, "user_id": ctx.user_id,
                                       "status": {"$ne": "deleted"}}, NO_ID)
    if not emp:
        return {"state": "unavailable", "note": "Akun ini tidak terhubung ke data karyawan."}
    eid = emp["id"]
    month_start = today.replace(day=1).isoformat()
    att = serialize_list(await db.attendances.find(
        {"company_id": ctx.company_id, "employee_id": eid, "work_date": {"$gte": month_start}},
        {"attendance_status": 1, "late_minutes": 1}).to_list(5000))
    present = sum(1 for a in att if a.get("attendance_status") in
                  ("present", "late", "early_leave", "late_and_early_leave"))
    late = sum(1 for a in att if a.get("attendance_status") in ("late", "late_and_early_leave"))
    leaves = serialize_list(await db.leave_requests.find(
        {"company_id": ctx.company_id, "employee_id": eid, "request_status": "pending"},
        {"start_date": 1, "end_date": 1, "leave_type_name": 1}).to_list(100))
    docs = serialize_list(await db.documents.find(
        {"company_id": ctx.company_id, "owner_type": "employee", "owner_id": eid,
         "is_deleted": {"$ne": True}, "expiry_date": {"$nin": [None, ""]}},
        {"name": 1, "expiry_date": 1}).to_list(200))
    horizon = (today + timedelta(days=90)).isoformat()
    expiring = [d for d in docs if str(d.get("expiry_date")) <= horizon]
    comp = await db.employee_completeness.find_one(
        {"company_id": ctx.company_id, "employee_id": eid}, {"score_pct": 1})
    return {
        "state": "ready",
        "employee": {"id": eid, "name": emp.get("full_name"), "number": emp.get("employee_number")},
        "attendance_month": {"present": present, "late": late, "records": len(att)},
        "pending_leave": len(leaves),
        "documents_expiring_90": len(expiring),
        "completeness_pct": (comp or {}).get("score_pct"),
    }


@router.get("/analytics/export")
async def analytics_export(
    category: str = "summary",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    ctx: AuthContext = Depends(require_permission("dashboard", "view")),
):
    """Ekspor Excel dari angka dashboard (KPI, demografi, organisasi, pergerakan, action center)."""
    from io import BytesIO

    from openpyxl import Workbook

    data = await analytics(category=category, date_from=date_from, date_to=date_to, ctx=ctx)
    wb = Workbook()
    ws = wb.active
    ws.title = "KPI"
    ws.append(["Indikator", "Nilai", "Sebelumnya", "Perubahan (%)"])
    for k in data["kpis"] + data["kpi_extra"]:
        ws.append([k["label"], k["value"], k["prev"], k["delta_pct"]])

    demo = data.get("demography")
    if demo:
        ws2 = wb.create_sheet("Demografi")
        ws2.append(["Analisis", "Kategori", "Jumlah", "%"])
        for key, label in (("gender", "Jenis Kelamin"), ("age_bands", "Kelompok Usia"),
                           ("generation", "Generasi"), ("marital_status", "Status Pernikahan"),
                           ("religion", "Agama"), ("education", "Pendidikan"),
                           ("tenure_bands", "Masa Kerja"), ("province", "Domisili"),
                           ("dependents", "Tanggungan")):
            for item in demo.get(key) or []:
                ws2.append([label, item.get("label"), item.get("count"), item.get("pct")])

    org = data.get("organization")
    if org:
        ws3 = wb.create_sheet("Organisasi")
        ws3.append(["Dimensi", "Kategori", "Jumlah", "%"])
        for dim in (org.get("dimensions") or {}).values():
            for item in dim.get("items") or []:
                ws3.append([dim.get("label"), item.get("label"), item.get("count"), item.get("pct")])

    mv = data.get("movement")
    if mv:
        ws4 = wb.create_sheet("Pergerakan")
        ws4.append(["Bulan", "Masuk", "Keluar", "Net"])
        for row in mv.get("trend") or []:
            ws4.append([row["month"], row["joined"], row["exited"], row["net"]])

    ws5 = wb.create_sheet("Action Center")
    ws5.append(["Tindakan", "Jumlah", "Tingkat", "Tautan"])
    for item in data.get("action_center") or []:
        ws5.append([item["title"], item["count"], item["severity"], item["link"]])

    ws6 = wb.create_sheet("Insight")
    ws6.append(["Insight", "Sumber data"])
    for item in data.get("insights") or []:
        ws6.append([item["text"], item["source"]])

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    filename = f"dashboard-{category}-{data['period']['from']}_{data['period']['to']}.xlsx"
    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
