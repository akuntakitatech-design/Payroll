# ENHANCEMENT 01G — Flexible Employee Form Builder · Audit & Schema Proposal

**Status: AUDIT DONE · PROPOSAL — STOP for review before migration.**
No code, migration, dependency, or data change has been made. 01H not started. Production Changed: **NO**.

---

## 1. Audit results

### 1.1 Can the 01F completeness rules be reused? → **YES for core field levels, with 4 caveats**
| Aspect | Current state (01F) | Consequence for the Form Builder |
|---|---|---|
| Tables | `completeness_rules (company_id, requirement_code, level, notes)` unique per tenant+code; `completeness_rule_scopes (requirement_code, scope_type, scope_id, scope_label, mode INCLUDE/EXCLUDE, effective_from/to)` | Can be reused **directly** as the source of truth for core field levels. There is no need to store a level copy in the form config. |
| Levels | `REQUIRED` / `RECOMMENDED` / `OFF` (`completeness_mapping.py:17-19`) | "Wajib / Anjuran / Opsional" = REQUIRED / RECOMMENDED / OFF. **Caveat 1:** in the 01F UI, OFF is labelled "Nonaktif". In the Form Builder it will be shown as "Opsional (tidak dihitung kelengkapan)". Field *visibility* is a separate flag, not the OFF level. |
| Scope | 11 dimensions: company, branch, position, project, work_location, department, division, job_grade, employment_status, business_status_category, employee_status; project is read from the active `employee_assignments` (`completeness.py:172-219`) | All the scopes requested (all employees / project / department / level-grade / position / status) **already exist**. The resolver `_scope_value` / `_applicable` can be reused for form field visibility. |
| Granularity | Level is per **requirement code**, not per field. Some codes cover several fields: `PERSONAL.BIRTH` = birth_place + birth_date; `PERSONAL.EMERGENCY_CONTACT` = name + phone; `BANK.ACCOUNT` = bank_name + account_number + account_name | **Caveat 2:** changing the level of one of those fields changes the whole group. The builder will show a badge like "diatur bersama: Rekening Bank (3 field)". |
| Unmapped fields | `city`, `province`, `postal_code` have no 01F code | **Caveat 3:** these 3 fields can only be Opsional (show/hide). No new 01F rule, so there is no parallel completeness rule. |
| Ordering / section / label | Not present in 01F (order = order of the static catalog) | Must come from the new form configuration. |
| Locked status | 01F is LOCKED | **Caveat 4:** the recommendation below does **not** change the 01F engine. The builder only reads rules and writes levels through the existing 01F functions/API (the same audit trail). |

### 1.2 Custom field infrastructure → **DOES NOT EXIST**
- `custom_field`, `field_definition`, `extra_field`, `form_builder`, `form_config`: 0 matches in backend and frontend.
- The `employees` table has **no JSON column** (only typed columns). There is no generic definition + value schema.
- **Conclusion:** a new schema is needed (below). Per the instruction, **STOP before migration**.

### 1.3 Current 01G public form (what needs to become dynamic)
- Backend: `EDITABLE_FIELDS` (23 core fields, `public_form.py:238-262`) is **the only authoritative whitelist**; `FAMILY_EDITABLE` (9 sub-fields); `SECTIONS` personal / contact / family / bank_tax / bpjs / documents.
- Frontend: `STEPS`, `REQ_FIELDS`, and `SECTION_TITLES` are hardcoded (`PublicFormParts.jsx:10-31`). The 6 steps are fixed.
- Draft is stored in `employee_update_submissions.proposed` = `{fields, family, notes, no_npwp}`. Attachments are in `employee_submission_files` (private prefix `employee-submissions/`).
- Review/submit already reads 01F levels (`_completeness()` router `:565-590`).

### 1.4 Supporting infrastructure
- RBAC: permissions are added through an idempotent migration (pattern in `m0007` lines 64-86).
- Navigation: the "Data Karyawan" group is in `lib/nav.js:102-153`. There is no "Form Pembaruan Data" menu yet.
- Drag and drop: **no library installed**. Proposed: `@dnd-kit/core` + `@dnd-kit/sortable` (keyboard accessible), added via `yarn add`.
- Storage: a custom *file* field can reuse the 01G pipeline (extension whitelist, magic bytes, size limit, private prefix).

---

## 2. Design principles (answers to the requirements)
1. **Core fields** = the `EDITABLE_FIELDS` catalog in code (sourced from Profile 360). HR can only show/hide, reorder, move between sections, and change label/help text. **No delete** (no endpoint). If there is no config row, the code default applies.
2. **Core field level** is read and written **only** through `completeness_rules` / `completeness_rule_scopes` (01F). The form config stores **no** level for core fields, so there can be no conflicting rules.
3. **Security whitelist stays authoritative.** The builder can never enable a field outside `EDITABLE_FIELDS`. HR-only fields (status, assignment, grade, payroll, contract, system fields) are not listed in the builder at all.
4. **Custom fields** use a separate namespace (key prefix `cf_`, pattern `^cf_[a-z0-9_]{2,40}$`). They must not collide with core keys or any `employees` column. Answers are stored under `proposed.custom` and in a separate value table, and are **never** merged into `employees` columns.
5. **No hard delete** for fields that have data (a value row, a submission, or an attachment). Only INACTIVE. Delete is allowed only if the field has never been used. `field_key` and `field_type` cannot change once the field has data (except text → textarea).
6. **Visibility vs level:** visibility decides *where the field is asked* (visibility scope), and 01F decides *how important* it is. Guard: a core field that is REQUIRED/RECOMMENDED and applicable to an employee **is always shown**, even if it is hidden in the config. The builder warns about this; the server enforces it.
7. **Rendering is dynamic from the server.** `GET /form` returns a `layout` already resolved per employee (sections → fields → type/label/level/options/validation/value). The frontend only renders it. Family and Documents remain *composite* sections (they can be reordered or hidden, but their inner fields stay fixed). Review is always the last step.

---

## 3. Proposed minimal schema — migration `m0009_employee_form_builder` (additive only)

### 3.1 `employee_form_sections`
| Column | Type | Notes |
|---|---|---|
| id, company_id, status (ACTIVE/INACTIVE), created/updated audit | standard | same as other tables |
| section_key | s64 | system sections: `personal, contact, family, bank_tax, bpjs, documents`; custom sections: `cs_<slug>` |
| label, description | s / t | |
| sort_order | i | |
| is_system | b | system sections cannot be deleted; only hidden if they contain no applicable REQUIRED field |
Unique `(company_id, section_key)`.

### 3.2 `employee_form_fields` (core config + custom definitions)
| Column | Type | Notes |
|---|---|---|
| id, company_id, status (ACTIVE/INACTIVE), audit | standard | |
| field_key | s64 | core: an `EDITABLE_FIELDS` key; custom: `cf_*` |
| source | s32 | `CORE` \| `CUSTOM` |
| section_key, sort_order, visible | s64 / i / b | |
| label_override, help_text, placeholder | s / t / s | label_override also applies to core fields |
| field_type | s32 | CUSTOM only: `text, number, date, dropdown, radio, checkbox, textarea, file` |
| options | j | dropdown/radio/checkbox: `[{value,label,active}]`; options are only deactivated, never deleted |
| validation | j | e.g. `{min,max,max_length,pattern,allowed_ext,max_mb}` (server clamps to the 01G limits) |
| form_level | s32 | **CUSTOM only**: `REQUIRED / RECOMMENDED / OPTIONAL` (see Option 1 in section 4); NULL for CORE |
| data_version | i | optimistic lock |
Unique `(company_id, field_key)`.

### 3.3 `employee_form_field_scopes` (visibility per field; same format as 01F)
`field_key, scope_type, scope_id, scope_label, mode INCLUDE/EXCLUDE` + standard columns. `scope_type` uses **the same list** as 01F `SCOPE_TYPES` and **the same resolver**. Index `(company_id, field_key)`.

### 3.4 `employee_custom_field_values` (official values; extensible, no ALTER on `employees`)
`employee_id, field_key, value (j), value_text (s512, for display/search), source_submission_id (fk, nullable), updated_by` + standard columns. Unique `(company_id, employee_id, field_key)`.
In this enhancement **no process writes to this table yet**. Values become official only through **01H approval** (or HR editing in Profile 360 later). Answers from the public form stay in `employee_update_submissions.proposed.custom` (pending), consistent with the 01G principle.

### 3.5 Small change to existing tables (additive)
- `employee_submission_files` + `field_key s64 NULL`: attachments for custom *file* fields (the storage prefix is still the private `employee-submissions/`).
- `employee_update_submissions.proposed` gets `custom: {cf_key: value}` and `meta.form_version` (a hash of the layout the employee saw, so 01H can render the same form). **No new column.**

### 3.6 Permission
- Recommended: new permission **`employee_form:configure`** (tenant_admin, hr_admin; company_owner via wildcard).
- **Changing a core field level** still also requires `employee_completeness:configure` (because it writes a 01F rule).
- Alternative: reuse `employee_completeness:configure` for everything (no new permission).

---

## 4. Decision needed — custom field levels

| | **Option 1 (recommended)** — custom levels are form-only | Option 2 — custom fields counted in 01F |
|---|---|---|
| How it works | `form_level` in `employee_form_fields` only controls form validation (Wajib = submit blocked; Anjuran = warning). The 01F score does not change. | Add dynamic requirements `CUSTOM.<key>` to the 01F catalog (like `DOC.*`). Levels go into `completeness_rules`. |
| Change to 01F (LOCKED) | **None** | The 01F engine must change (catalog, context loader, check) → 01F needs re-testing and re-locking |
| Consequence | Two domains that do not conflict: 01F = core, form = custom | Because values only exist after 01H, **every employee's completeness score drops immediately** when a custom field is made REQUIRED |
| Recommendation | ✔ now | Consider after 01H is live |

---

## 5. Backoffice (after approval)
**Data Karyawan → Form Pembaruan Data → Pengaturan Form** (`/employees/update-form/settings`; the "Kotak Masuk" tab will belong to 01H)
- Section list (add custom section, rename, activate/deactivate, drag to reorder)
- Fields per section: drag to reorder or move between sections; show/hide; level badge (core = from 01F, with a "diatur bersama" group badge; custom = form_level); scope
- Add / Edit custom field (type, options, validation, help text); activate/deactivate; delete only if never used
- **Preview form**: render the layout as it would appear for a sample employee or a chosen scope (read-only, no public session)
- Guard warnings: a REQUIRED field that is hidden, a section left empty, an invalid key

### Public API impact
- `GET /form` → adds `layout` (the old response shape stays compatible for one transition release)
- `PUT /draft` → accepts `custom`; custom values are validated against **active + visible** definitions for that employee; unknown keys are rejected with 422; custom never affects `fields` or core
- `POST /files` → optional `field_key` for custom file fields

## 6. Proposed phases (after review)
1. **Phase A** — m0009 migration + backend config API + dynamic layout resolver + custom validation + tests (security/tenant/regression 01F/01G).
2. **Phase B** — dynamic public form rendering (6 steps become sections from the config) + custom field inputs (8 types).
3. **Phase C** — backoffice Pengaturan Form (dnd-kit, preview, scope) + UI tests.
4. **Phase D** — final regression 01B–01G, cleanup, report. Status stays **not LOCKED** until reviewed.

## 7. Questions for review
1. Custom levels: **Option 1** (recommended) or Option 2?
2. Permission: new `employee_form:configure`, or reuse `employee_completeness:configure`?
3. Drag and drop: may I add `@dnd-kit/core` + `@dnd-kit/sortable`?
4. Git: 01G is already in PR #14 (open). Should this enhancement be developed on the current local branch and later submitted as a **separate PR stacked on PR #14**? Or should it be added to PR #14?
5. Custom *file* fields in 01G only become pending attachments (they become official only in 01H). Is that correct?
