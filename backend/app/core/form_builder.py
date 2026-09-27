"""Enhancement 01G - Flexible Employee Form Builder (core logic).

Principles:
- CORE field = the 01G whitelist `public_form.EDITABLE_FIELDS` (sourced from Profile 360). The config can only change
  section / order / visible / label / help text. A core field can never be deleted and the whitelist stays authoritative.
- Core field level comes ONLY from 01F (completeness snapshot/rules): REQUIRED=Wajib, RECOMMENDED=Anjuran,
  OFF / NOT_APPLICABLE = "Tidak Dinilai". A core field that is REQUIRED + applicable for the employee is ALWAYS shown.
- CUSTOM field = `cf_*` definition + form_level REQUIRED/RECOMMENDED/OPTIONAL (form validation only; NOT part of the 01F score).
- Scope = decides who a field is shown to (same semantics as 01F scopes: EXCLUDE first, INCLUDE if any). It never changes 01F rules.
"""
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from . import completeness as engine
from . import completeness_mapping as M
from . import public_form as P
from .db import NO_ID, get_table
from .tenancy import get_tenant_db

# section: key, label, kind (fields | family | documents)
SYSTEM_SECTIONS: List[Tuple[str, str, str]] = [
    ("personal", "Data Pribadi", "fields"), ("family", "Keluarga", "family"), ("bank_tax", "Bank & Pajak", "fields"),
    ("bpjs", "BPJS", "fields"), ("documents", "Dokumen", "documents"),
]
SYSTEM_KEYS = {s[0] for s in SYSTEM_SECTIONS}
SECTION_KIND = {s[0]: s[2] for s in SYSTEM_SECTIONS}
# the 01G "contact" section is shown in the Data Pribadi step (same as the 01G-B UI) -> default section personal
CORE_DEFAULT_SECTION = {k: ("personal" if v[0] in ("personal", "contact") else v[0]) for k, v in P.EDITABLE_FIELDS.items()}
CUSTOM_TYPES = ("text", "number", "date", "dropdown", "radio", "checkbox", "textarea", "file")
OPTION_TYPES = ("dropdown", "radio", "checkbox")
CUSTOM_LEVELS = ("REQUIRED", "RECOMMENDED", "OPTIONAL")
LEVEL_LABELS = {"REQUIRED": "Wajib", "RECOMMENDED": "Anjuran", "OFF": "Tidak Dinilai", "NOT_APPLICABLE": "Tidak Dinilai",
                "OPTIONAL": "Opsional"}
FIELD_KEY_RE = re.compile(r"^cf_[a-z0-9_]{2,40}$")
SECTION_KEY_RE = re.compile(r"^cs_[a-z0-9_]{2,40}$")
SCOPE_TYPES = {k: v for k, v in M.SCOPE_TYPES.items()}  # identical semantics to 01F
TEXT_MAX, TEXTAREA_MAX, MAX_OPTIONS, MAX_CUSTOM_FIELDS = 255, 2000, 50, 100

# 01F requirement code <-> core field (grouped levels, e.g. BANK.ACCOUNT = 3 fields)
FIELD_CODE: Dict[str, str] = {}
CODE_FIELDS: Dict[str, List[str]] = {}
for _r in M.STATIC_REQUIREMENTS:
    for _f in (_r.fields or []):
        if _f in P.EDITABLE_FIELDS:
            FIELD_CODE[_f] = _r.code
            CODE_FIELDS.setdefault(_r.code, []).append(_f)
_REQ_LABEL = {r.code: r.label for r in M.STATIC_REQUIREMENTS}
_SECTION_OPEN_PREFIX = {"family": "FAMILY.", "documents": "DOC."}


def reserved_keys() -> Set[str]:
    cols = set(get_table("employees").c.keys())
    return cols | set(P.EDITABLE_FIELDS) | set(P.FAMILY_EDITABLE) | {"fields", "family", "custom", "notes", "no_npwp", "meta"}


# Protected names (backend-authoritative). A custom field must never look like an HR-only / system attribute.
# HARD token anywhere in key/label -> rejected (payroll, contract, RBAC, tenant, audit, technical).
PROTECTED_HARD = {"salary", "salaries", "gaji", "payroll", "upah", "wage", "wages", "contract", "contracts", "kontrak", "role", "roles",
                  "permission", "permissions", "password", "token", "secret", "tenant", "tenants", "created", "updated", "deleted",
                  "archived", "audit", "system", "uuid"}
# SOFT tokens: rejected only when the name consists ONLY of these words (e.g. cf_status, cf_employee_status,
# "Status Karyawan", "Jabatan", "Grade") - "Status Vaksin" / "Golongan Darah" / "Ukuran Baju" stay allowed.
PROTECTED_SOFT = {"status", "employee", "employment", "karyawan", "pegawai", "kepegawaian", "emp", "current", "project", "projects",
                  "proyek", "assignment", "assignments", "penempatan", "placement", "position", "positions", "jabatan", "grade",
                  "grades", "job", "level", "levels", "company", "perusahaan", "id", "ids", "by", "at", "is", "active", "aktif",
                  "state", "type", "tipe", "kode", "code", "user", "users", "karir"}


def protected_name(name: str) -> Optional[str]:
    """-> reason if `name` (key without `cf_`, or a label) collides with a reserved / HR-only / system name, else None."""
    s = slug(name)
    if not s:
        return None
    tokens = [t for t in s.split("_") if t]
    if s in reserved_keys() or s in {"company_id", "tenant_id"} or "company_id" in s or "tenant_id" in s:
        return "bentrok dengan field inti/sistem"
    hard = sorted(set(tokens) & PROTECTED_HARD)
    if hard:
        return f"memakai istilah yang dilindungi ({', '.join(hard)})"
    if all(t in PROTECTED_SOFT for t in tokens):
        return "memakai nama atribut HR (status/penempatan/jabatan/grade) yang hanya dikelola HR"
    return None


def core_labels() -> Set[str]:
    return {slug(v[1]) for v in P.EDITABLE_FIELDS.values()}


def _rows_by(rows: List[Dict[str, Any]], key: str) -> Dict[str, Dict[str, Any]]:
    return {r[key]: r for r in rows if r.get(key)}


def _j(v: Any) -> Any:
    if isinstance(v, (str, bytes)):
        try:
            return json.loads(v)
        except ValueError:
            return None
    return v


async def load_config(company_id: str) -> Dict[str, Any]:
    tdb = get_tenant_db(company_id)
    q = {"company_id": company_id, "status": {"$ne": "deleted"}}
    srows = _rows_by(await tdb.employee_form_sections.find(q, NO_ID).to_list(500), "section_key")
    frows = _rows_by(await tdb.employee_form_fields.find(q, NO_ID).to_list(1000), "field_key")
    scopes: Dict[str, List[Dict[str, Any]]] = {}
    for s in await tdb.employee_form_field_scopes.find(q, NO_ID).to_list(5000):
        scopes.setdefault(s["field_key"], []).append(s)
    sections = []
    for i, (key, label, kind) in enumerate(SYSTEM_SECTIONS):
        r = srows.get(key) or {}
        sections.append({"key": key, "label": r.get("label") or label, "default_label": label, "kind": kind, "is_system": True,
                         "description": r.get("description"), "active": (r.get("status") or "active") == "active",
                         "sort_order": r.get("sort_order") if r.get("sort_order") is not None else i * 10})
    for key, r in srows.items():
        if key in SYSTEM_KEYS:
            continue
        sections.append({"key": key, "label": r.get("label") or key, "default_label": None, "kind": "fields", "is_system": False,
                         "description": r.get("description"), "active": r.get("status") == "active",
                         "sort_order": r.get("sort_order") or 0})
    sections.sort(key=lambda s: (s["sort_order"], s["key"]))
    valid_sections = {s["key"] for s in sections if s["kind"] == "fields"}
    fields = []
    for i, (key, (sec, label, validator, sensitive, _identity)) in enumerate(P.EDITABLE_FIELDS.items()):
        r = frows.get(key) or {}
        section = r.get("section_key") if r.get("section_key") in valid_sections else CORE_DEFAULT_SECTION[key]
        fields.append({"key": key, "source": "CORE", "section": section, "default_section": CORE_DEFAULT_SECTION[key],
                       "sort_order": r.get("sort_order") if r.get("sort_order") is not None else i * 10,
                       "visible": r.get("visible") is not False, "active": True, "label": r.get("label_override") or label,
                       "default_label": label, "label_override": r.get("label_override"), "help_text": r.get("help_text"),
                       "placeholder": r.get("placeholder"), "sensitive": sensitive, "requirement_code": FIELD_CODE.get(key),
                       "requirement_label": _REQ_LABEL.get(FIELD_CODE.get(key)),
                       "grouped_with": [f for f in CODE_FIELDS.get(FIELD_CODE.get(key), []) if f != key],
                       "data_version": r.get("data_version") or 0})
    for key, r in frows.items():
        if r.get("source") != "CUSTOM":
            continue
        section = r.get("section_key") if r.get("section_key") in valid_sections else "personal"
        fields.append({"key": key, "source": "CUSTOM", "section": section, "sort_order": r.get("sort_order") or 0,
                       "visible": r.get("visible") is not False, "active": r.get("status") == "active",
                       "label": r.get("label_override") or key, "help_text": r.get("help_text"), "placeholder": r.get("placeholder"),
                       "type": r.get("field_type"), "options": _j(r.get("options")) or [], "validation": _j(r.get("validation")) or {},
                       "form_level": r.get("form_level") or "OPTIONAL", "data_version": r.get("data_version") or 0})
    fields.sort(key=lambda f: (f["sort_order"], f["key"]))
    sig = json.dumps({"s": [(s["key"], s["label"], s["active"], s["sort_order"]) for s in sections],
                      "f": [(f["key"], f["section"], f["sort_order"], f["visible"], f["active"], f["label"], f.get("form_level"),
                             f.get("type"), json.dumps(f.get("options"), sort_keys=True)) for f in fields],
                      "sc": sorted((k, s.get("scope_type"), s.get("scope_id") or "", s.get("mode")) for k, v in scopes.items() for s in v)},
                     default=str)
    return {"sections": sections, "fields": fields, "scopes": scopes, "version": hashlib.sha256(sig.encode()).hexdigest()[:16]}


# ------------------------------------------------------------------ levels (read-only from 01F)
def levels_from_rules(rules: Dict[str, Any]) -> Dict[str, str]:
    """Default 01F level per core field (without employee context) - for the backoffice / generic preview."""
    by = {r.code: r for r in rules["requirements"]}
    out = {}
    for f, code in FIELD_CODE.items():
        req = by.get(code)
        out[f] = rules["levels"].get(code) or (req.default_level if req else M.OFF)
    return out


def levels_from_snapshot(items: List[Dict[str, Any]]) -> Tuple[Dict[str, str], Set[str], Set[str]]:
    """-> (level per core field, forced core fields, forced composite sections) from the employee's 01F snapshot."""
    levels, forced, forced_sections = {}, set(), set()
    for it in items or []:
        code, level, st = it.get("code") or "", it.get("level"), it.get("status")
        applicable = st not in (M.NA, M.OFF) and level in (M.REQUIRED, M.RECOMMENDED)
        for f in CODE_FIELDS.get(code, []):
            levels[f] = level if applicable else "NOT_APPLICABLE"
            if applicable and level == M.REQUIRED:
                forced.add(f)
        for sec, prefix in _SECTION_OPEN_PREFIX.items():
            if code.startswith(prefix) and applicable and level == M.REQUIRED and st != M.COMPLETE:
                forced_sections.add(sec)
    return levels, forced, forced_sections


def levels_without_snapshot(rules: Dict[str, Any]) -> Tuple[Dict[str, str], Set[str], Set[str]]:
    """No 01F snapshot for the employee (yet): conservative - every core field REQUIRED by the rules is forced visible."""
    levels = levels_from_rules(rules)
    return levels, {f for f, lv in levels.items() if lv == M.REQUIRED}, set()


def shown_core(layout: Dict[str, Any]) -> Set[str]:
    """Core field keys the employee may see/edit (final public schema = source of truth)."""
    return {i["key"] for st in layout["steps"] for i in st["fields"] if i["source"] == "CORE"}


# ------------------------------------------------------------------ scope (same semantics as 01F _applicable)
async def scope_context(company_id: str, emp: Dict[str, Any]) -> Dict[str, Any]:
    tdb = get_tenant_db(company_id)
    a = await tdb.employee_assignments.find_one({"company_id": company_id, "employee_id": emp["id"], "assignment_status": "ACTIVE"}, NO_ID)
    cats = {s["id"]: s.get("system_category") for s in
            await tdb.employee_business_statuses.find({"company_id": company_id}, NO_ID).to_list(500)}
    return {"assign": {emp["id"]: a} if a else {}, "business_category": cats}


def scope_visible(scopes: List[Dict[str, Any]], emp: Optional[Dict[str, Any]], ctx: Optional[Dict[str, Any]]) -> bool:
    if not scopes:
        return True
    if emp is None:  # generic preview: a field with scopes is shown as "by scope"
        return True

    def match(s):
        return s.get("scope_type") == "company" or (engine._scope_value(emp, ctx, s.get("scope_type")) or "") == (s.get("scope_id") or "-")
    if any(s.get("mode") == "EXCLUDE" and match(s) for s in scopes):
        return False
    inc = [s for s in scopes if s.get("mode") == "INCLUDE"]
    return any(match(s) for s in inc) if inc else True


# ------------------------------------------------------------------ layout
def resolve_layout(cfg: Dict[str, Any], levels: Dict[str, str], forced: Set[str], forced_sections: Set[str],
                   emp: Optional[Dict[str, Any]] = None, ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    by_section: Dict[str, List[Dict[str, Any]]] = {}
    for f in cfg["fields"]:
        if not f["active"]:
            continue
        is_forced = f["source"] == "CORE" and f["key"] in forced
        shown = f["visible"] and scope_visible(cfg["scopes"].get(f["key"], []), emp, ctx)
        if not (shown or is_forced):
            continue
        item = {"key": f["key"], "source": f["source"], "label": f["label"], "help_text": f.get("help_text"),
                "placeholder": f.get("placeholder"), "forced": bool(is_forced and not shown),
                "scoped": bool(cfg["scopes"].get(f["key"]))}
        if f["source"] == "CORE":
            lv = levels.get(f["key"], "NOT_APPLICABLE")
            item.update({"level": lv, "level_label": LEVEL_LABELS.get(lv, "Tidak Dinilai"), "requirement_code": f.get("requirement_code")})
        else:
            item.update({"type": f["type"], "level": f["form_level"], "level_label": LEVEL_LABELS[f["form_level"]],
                         "options": [o for o in f["options"] if o.get("active", True)], "validation": f["validation"]})
        by_section.setdefault(f["section"], []).append(item)
    steps = []
    for s in cfg["sections"]:
        content = by_section.get(s["key"], [])
        has_forced = any(i["source"] == "CORE" and i["key"] in forced for i in content) or s["key"] in forced_sections
        if s["kind"] == "fields" and not content:
            continue
        if not s["active"] and not has_forced:
            continue
        steps.append({"key": s["key"], "label": s["label"], "kind": s["kind"], "description": s.get("description"),
                      "fields": content if s["kind"] == "fields" else [], "forced": not s["active"]})
    return {"version": cfg["version"], "steps": steps}


def visible_custom(layout: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    keys = {i["key"] for st in layout["steps"] for i in st["fields"] if i["source"] == "CUSTOM"}
    return {f["key"]: f for f in cfg["fields"] if f["source"] == "CUSTOM" and f["key"] in keys}


# ------------------------------------------------------------------ custom value validation
def validate_custom(defn: Dict[str, Any], raw: Any) -> Tuple[Any, Optional[str]]:
    """-> (normalized value | None if empty, error message | None)."""
    t, v = defn.get("type"), defn.get("validation") or {}
    if t == "file":
        return None, "Unggah berkas melalui tombol unggah."
    if raw is None or (isinstance(raw, str) and not raw.strip()) or raw == []:
        return None, None
    opts = [o.get("value") for o in defn.get("options") or [] if o.get("active", True)]
    if t in ("text", "textarea"):
        if not isinstance(raw, (str, int, float)) or isinstance(raw, bool):
            return None, "Format nilai tidak valid."
        s = str(raw).strip()
        cap = TEXT_MAX if t == "text" else TEXTAREA_MAX
        mx = min(int(v.get("max_length") or cap), cap)
        return (s, None) if len(s) <= mx else (None, f"Maksimal {mx} karakter.")
    if t == "number":
        try:
            n = float(str(raw).replace(",", ".")) if not isinstance(raw, bool) else None
        except ValueError:
            n = None
        if n is None or n != n or abs(n) > 1e12:
            return None, "Harus berupa angka."
        if v.get("min") is not None and n < float(v["min"]):
            return None, f"Minimal {v['min']}."
        if v.get("max") is not None and n > float(v["max"]):
            return None, f"Maksimal {v['max']}."
        return (int(n) if n.is_integer() else n), None
    if t == "date":
        d = P.norm_date(str(raw))
        return (d, None) if d else (None, "Format tanggal tidak valid.")
    if t in ("dropdown", "radio"):
        return (raw, None) if isinstance(raw, str) and raw in opts else (None, "Pilihan tidak valid.")
    if t == "checkbox":
        if not opts:
            if isinstance(raw, bool):
                return (True if raw else None), None
            return None, "Format nilai tidak valid."
        if not isinstance(raw, list) or not all(isinstance(x, str) and x in opts for x in raw) or len(raw) > MAX_OPTIONS:
            return None, "Pilihan tidak valid."
        return sorted(set(raw), key=opts.index) or None, None
    return None, "Jenis field tidak dikenal."


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")[:40]
