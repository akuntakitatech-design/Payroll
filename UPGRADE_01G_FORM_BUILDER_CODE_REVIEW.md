# Enhancement 01G — Flexible Employee Form Builder · CODE REVIEW + m0009 WARNING INVESTIGATION

Status of the enhancement: **IN PROGRESS** (this review does NOT mark any part as LOCKED).
Date: 2026-09-27 · Environment: staging/preview (APP_ENV=staging, READ_ONLY=false, AUTO_SEED=false, ENABLE_SCHEDULER=false) · **Production Changed: NO** · No push / PR / merge / deploy · 01H not started.
All claims here were **tested by the agent** (not confirmed by the user).

---

## 1. Baseline & scope

| Item | Value |
|---|---|
| Active branch | `feature/upgrade-01g-form-builder` |
| Baseline (HEAD, no new commits) | `bb73dbe` — Merge pull request #14 (01F + 01G) |
| PR #15 (docs) | not reused / not touched |
| Inherited changes (`.env.example`, `backend/.env.example`) | not modified by this enhancement (not in the current worktree diff) |

Code that belongs to this enhancement (`git diff bb73dbe` + untracked files):

| Kind | File | Change |
|---|---|---|
| Migration | `backend/migrations/m0009_employee_form_builder.py` | NEW (117 lines) |
| Backend | `backend/app/core/form_builder.py` | NEW (257 lines) — config, 01F levels, scope, layout, custom validation |
| Backend | `backend/app/routers/employee_form_builder.py` | NEW (452 lines) — backoffice API `/api/employees/update-form/*` |
| Backend | `backend/app/routers/public_employee_form.py` | MOD (+98/−19) — dynamic layout, `custom` in draft/submit, custom file upload |
| Backend | `backend/app/core/db.py` | MOD (+30) — 4 table specs, `employee_submission_files.field_key`, indexes |
| Backend | `backend/app/core/rbac.py` | MOD (+6) — resource `employee_form:configure`; hr_manager excluded |
| Backend | `backend/server.py` | MOD (+2) — router wiring |
| Frontend | `frontend/src/components/employee-form/FormBuilderSettings.jsx` | NEW (332 lines) — **not wired to any route yet** |
| Frontend | `frontend/src/components/public-form/CustomFieldInput.jsx` | NEW (104 lines) |
| Frontend | `frontend/src/pages/public/PublicEmployeeFormPage.jsx` | MOD — steps come from the server `layout` |
| Frontend | `frontend/src/components/public-form/ReviewSection.jsx` | MOD — gets `steps` as a prop |
| Frontend | `frontend/src/lib/publicFormApi.js` | MOD — `upload(..., fieldKey)` |
| Dependencies | `frontend/package.json`, `yarn.lock` | `@dnd-kit/core 6.3.1`, `@dnd-kit/sortable 10.0.0`, `@dnd-kit/utilities 3.2.2`, `qrcode.react 4.2.0` (yarn) |
| Tests (outside the repo) | `/root/tenant_tests/test_01g_fb.py` | targeted backend suite |
| Docs | `UPGRADE_01G_FORM_BUILDER_AUDIT.md`, `plan.md`, this file, `UPGRADE_01G_FORM_BUILDER_PROGRESS.md` | |

Classification legend: BUG · SECURITY · DATA INTEGRITY · PERFORMANCE · MAINTAINABILITY · TEST ISSUE · NON-BLOCKER · OK

---

## 2. m0009 warning — investigation (diagnosis first, based on evidence)

### 2.1 Exact text
```
Table 'schema_migrations' already exists
```
It goes to stderr on every `python -m migrations.m0009_employee_form_builder --apply` (both APPLY and SKIP).

### 2.2 Source (proven)
1. m0009 runs `LEDGER_DDL` = `CREATE TABLE IF NOT EXISTS schema_migrations ...` (apply mode, line 46).
2. When the table already exists, MariaDB does not raise an error. It returns **Note 1050**. Direct check: `SHOW WARNINGS` → `[('Note', 1050, "Table 'schema_migrations' already exists")]`.
3. The `asyncmy` driver (`cursors.pyx:512-520`, `_show_warnings`) runs `SHOW WARNINGS` after any statement with `warning_count > 0` and passes the message to `logger.warning(msg)`. With no logging handler configured in the CLI, Python's lastResort handler prints it to stderr.
4. Same mechanism elsewhere: **m0008** (01G, LOCKED) prints the same line when re-run with `--apply`. So do m0007 and the temp-DB test (`DROP DATABASE IF EXISTS` → "Can't drop database ...; database doesn't exist", also a Note).

### 2.3 Not the source (checked)
Duplicate table, index or column; FK; index length; nullable/default mismatch; enum/string size; JSON/text; duplicate grant; schema drift. The staging `SHOW CREATE TABLE` output for all 4 tables is identical to the result on the clean temp DB (column types, `ux_form_section_key`, `ux_form_field_key`, `ix_form_field_scope`, `ux_custom_value_emp_key`, `ix_*_company_status`). `permissions` has exactly 1 row for `employee_form:configure`. `role_permissions` has exactly 1 row each for hr_admin and tenant_admin.

### 2.4 Related finding: startup sync side effect
The staging ledger records `m0009 {"tables_created": [], "columns_added": [], ...}`. Cause, from the backend log: after the `db.py` edit, hot reload ran `ensure_schema()`/`_sync_schema` (`metadata.create_all` + ADD COLUMN) at **06:57:30–31**:
`Kolom baru ditambahkan: employee_submission_files.field_key`. Table `create_time` = 06:57:30. m0009 was applied at **07:01:59**, found the objects already there, and recorded only the permission/grant.
This pattern existed before this enhancement (m0008 ledger: `tables_created: []`). It is not new and not a mismatch.

### 2.5 Migration verification on a temporary clean DB (staging not touched)
DB `test_m0009_clean` (allowed by the PUBLIC `test\_%` grant). Baseline = current metadata minus the m0009 objects, plus ledger m0003–m0008 and roles. Temp DB dropped afterwards.

| Stage | Result |
|---|---|
| baseline | 0 m0009 tables, `field_key` column missing, permission 0, grants none, no ledger |
| dry-run | lists 4×CREATE, 1×ALTER, INSERT permission, 2×GRANT, RECORD · **no changes** (state stays the same) · stderr empty |
| `--apply` | 4 tables + column + permission 1 + grants tenant_admin/hr_admin 1 each + ledger with complete `tables_created`/`columns_added` · stderr = only the Note 1050 line |
| rerun `--apply` | `SKIP (sudah diterapkan …)` · state identical (no duplicate table/index/permission/grant, no data mutation) |

Staging: m0009 recorded **exactly once** in `schema_migrations`. Rerun through the normal runner → **SKIP**.

### 2.6 Classification
- `Table 'schema_migrations' already exists` → **HARMLESS / EXPECTED**. It is a MariaDB Note 1050 for `CREATE TABLE IF NOT EXISTS`, surfaced by the asyncmy driver logger. It is not an error and not a schema mismatch. The same thing happens on m0007/m0008.
- Empty ledger `tables_created` on staging → **STARTUP SYNC SIDE EFFECT** (pre-existing design). Non-blocker. The clean-DB test proves m0009 creates the objects itself when startup sync has not run first.
- Neither is a PRODUCT BLOCKER. No migration code changes needed. (Optional later, cosmetic: suppress the Note in the CLI. Not done, to avoid changing the migration pattern shared with m0007/m0008.)

### 2.7 Other backend-log events (classified)
- `Application startup failed … Can't connect to MySQL server (111)` in the log **before 05:47:36**, i.e. before any change from this enhancement (`db.py`/`rbac.py` changed at ≈06:57). Cause: MariaDB was not running yet at container boot. This is the documented infra issue ("supervisor payroll-dev-mariadb can go FATAL at boot"). → **ENVIRONMENT**. The next start (05:47:36) succeeded. Not related to m0009.

---

## 3. Line-by-line review — backend

### 3.1 `migrations/m0009_employee_form_builder.py` — **OK**
- Additive only (CREATE TABLE via metadata `checkfirst`, ADD COLUMN NULL, INSERT permission, INSERT grant). No DROP/RENAME, no business-data UPDATE, no JSON column on `employees`.
- Each step is idempotent (checks information_schema / count before writing). Ledger SKIP at the start. `READ_ONLY` guard present. `close_db()` in `finally`.
- Note (NON-BLOCKER): the DDL block and the permission/ledger block are not a single transaction. MariaDB DDL auto-commits anyway, and each step is idempotent, so a partial failure can simply be re-run.
- Grant `tenant_admin` + `hr_admin`. `company_owner` = wildcard. `tenant_admin` also gets it through `all_permission_keys()` in `rbac.py`. Consistent.

### 3.2 `core/db.py` (diff) — **OK**
- 4 tables in `TENANT_COLLECTIONS` (company_id filter enforced by the tenant layer).
- Unique `(company_id, section_key)`, `(company_id, field_key)`, `(company_id, employee_id, field_key)` → duplicate protection at DB level. A race condition produces a 409 from the db layer (existing pattern).
- `employee_custom_field_values` is a separate table. **No new column on `employees`** (test M04 PASS).

### 3.3 `core/rbac.py` (diff) — **OK**
- Resource `employee_form` action `configure` (permission key comes from the existing framework, not hardcoded per role). hr_admin ✔, hr_manager explicitly excluded (same as `employee_completeness:configure`), tenant_admin through all keys, company_owner through wildcard.

### 3.4 `core/form_builder.py`
| Area | Finding | Class |
|---|---|---|
| Core fields | Taken only from the whitelist `P.EDITABLE_FIELDS` (01G). HR-only fields (status, assignment/project, position, grade, payroll, contract) are **not in the catalog** → cannot be configured (C05 404, R05) | OK · SECURITY |
| Core level | Read-only from 01F (`levels_from_rules` / `levels_from_snapshot`). OFF / not applicable → `NOT_APPLICABLE` → label "Tidak Dinilai" (never "Opsional") | OK |
| REQUIRED override | `forced` = 01F snapshot items that are applicable + REQUIRED. In `resolve_layout`: `shown or is_forced` → a hidden core field / inactive section still shows (`forced: true`). Enforced by the backend/schema response, not the frontend | OK |
| Scope | Same semantics as 01F `_applicable`: EXCLUDE first, INCLUDE = any. Reuses `engine._scope_value` (read-only, private helper of the 01F engine). Scope never writes 01F rules | OK · MAINTAINABILITY (dependency on a private 01F helper; any change to that helper must be regression-tested) |
| Custom key | Regex `^cf_[a-z0-9_]{2,40}$`, plus `reserved_keys()` (employees columns + core whitelist + family + structural keys) | OK (structural) |
| Custom key — HR semantics | No **semantic** denylist yet. A key such as `cf_status_karyawan` / `cf_grade` / `cf_gaji` is still accepted. It **cannot** change master data (custom values only go to `proposed.custom`; officialization = 01H into a separate table). But the user's requirement asks for rejecting keys/labels that collide with status/assignment/position/grade/payroll/contract/system fields | SECURITY (hardening, not exploitable today) → **open item, backend phase** |
| `validate_custom` | Per-type validation: text ≤255 / textarea ≤2000, number (NaN/inf/min/max), date (`norm_date`), dropdown/radio only from active options, checkbox list only from options, file rejected through the dict (must go through upload) | OK |
| `load_config` | 3 queries/request, bounded by to_list | OK · PERFORMANCE (NON-BLOCKER) |

### 3.5 `routers/employee_form_builder.py`
| Area | Finding | Class |
|---|---|---|
| Prefix/RBAC | `/api/employees/update-form/*`. overview/monitoring = `employee:view`; config/preview/mutations = `employee_form:configure`. Tests: R01 403 employee user, R02 401 no login, MON4 403 | OK |
| Tenant | All queries use `ctx.company_id` / `ctx.tdb`. Scope ref must belong to the active tenant (SC02). Preview of another tenant's employee → 404 (PV3). KBS cannot edit NEP fields (SC04) | OK |
| SQL safety | `_field_has_data` builds the JSON path with an f-string, but `key` is validated first by `FIELD_KEY_RE` (lowercase letters/digits/_ only) | OK (note) |
| Core field guard | Core field only accepts label/help/placeholder/visible/section. `form_level`/`type` → 422 (C02, C03) | OK |
| **Explicit null** | `PUT /fields/{key}` with `{"visible": null}` / `{"section_key": null}` / `{"form_level": null}` was accepted and **stored as NULL**, silently falling back to defaults. Also, creating a core row from a label change stored `visible = NULL` (staging evidence: `phone.visible = NULL`) | **BUG (low) · DATA INTEGRITY → FIXED** (§5) |
| Inactive vs delete | No hard delete for custom fields/sections (only `status=inactive`). Old options kept as inactive (K07). Type locked once data exists (F06). Scopes = soft delete `status=deleted` | OK |
| Duplicates | Duplicate key → 409 (K04). Duplicate scope → 409. Section key auto-suffix | OK |
| `save_layout` | Validates section/field/duplicates first, then N upserts **without a transaction**. A failure midway can leave a partial order (repairable by re-saving) | MAINTAINABILITY · NON-BLOCKER |
| Monitoring | Loads all active employees (≤200k) + all submissions (≤500k) into Python and filters/aggregates there. **Not DB-side aggregation** (no N+1, but O(N) memory/transfer). Status semantics match the 01G state (DRAFT/PENDING/submitted_at) | **PERFORMANCE → open item, backend phase** |
| Audit | `log_action` for every mutation (section/field/scope/layout) with before/after, no sensitive values | OK |
| Sensitive logging | No logger for values/tokens | OK |
| Custom update | `data_version` goes up on every custom PUT even with no real change | NON-BLOCKER |

### 3.6 `routers/public_employee_form.py` (diff)
| Area | Finding | Class |
|---|---|---|
| `_form_layout` | Reads config + 01F snapshot (**read-only**) + scope context + official custom values (tenant + employee from the session) | OK |
| `get_form` | Returns `layout` + `custom_fields` + label override. Public session only (no internal auth) | OK |
| Draft custom | Only keys in `custom_defs` (active + visible + in scope for this employee) and not file type. Others → `rejected_fields` 422 (P12, P14, P15). Blank / same as official → no change (blank ≠ delete) | OK |
| Submit | Custom answers re-validated against the current definitions. Fields deactivated/hidden since the draft are **dropped** (never applied). Custom REQUIRED (incl. file) blocks submit (F02). `baseline.custom` stored. `meta.form_version` stored | OK |
| Officialization | Submit does **not** write `employee_custom_field_values`, employees, family, documents, or 01F (P18: master fingerprint unchanged, custom values = 0) | OK · DATA INTEGRITY |
| Custom file upload | `field_key` must be an active file-type definition for this employee (F05). Ext/size limited to the intersection with the public whitelist. Magic bytes checked (existing). Private path `…/employee-submissions/{sub}/{random}.{ext}`, `purpose=CUSTOM_FIELD`, **not** an official document (F04). Download only through the public session of the owner (`_own_file`) | OK · SECURITY |
| Hidden core field | The builder only affects the **UI/layout**. The server whitelist still accepts hidden core fields in a draft, and `get_form.fields` still sends the prefill of hidden core fields to the browser (existing 01G behaviour). Not a privilege-escalation risk (the field is already in the employee-editable whitelist), but it is data minimisation / consistency | DATA INTEGRITY (minor) → **open item/decision, backend phase** |
| Custom REQUIRED file | Checks only this submission's files (no official value until 01H) | NON-BLOCKER (note for 01H) |
| Prefill queries | +≈7 SELECTs on `/form` (config 3, snapshot 1 — also read by `_completeness`, so a duplicate —, scope 2, custom values 1) | PERFORMANCE · NON-BLOCKER |
| Existing 01G flow | verify/session/expired/pending/`_ensure_editable`/masking/version conflict **unchanged** | OK |

### 3.7 `server.py` — **OK** (only includes the router, placed with the other routers).

---

## 4. Line-by-line review — frontend

### 4.1 `pages/public/PublicEmployeeFormPage.jsx` (diff)
- Steps come from `form.layout.steps` (+ Review). Fallback to the old `STEPS` if `layout` is missing (backward compatible). Rendered by `kind`: fields / family / documents / review. **OK**
- Frontend does **not** compute core requirements. Badges come from 01F completeness (existing), custom levels come from the schema. **OK**
- Custom payload: only visible definitions, not files, empty values not sent, compared with the official value. Resume: `cvals` taken from `draft.proposed.custom`. **OK**
- Review: `stepFor` maps completeness items to dynamic steps. Custom REQUIRED blocks, RECOMMENDED warns, OPTIONAL is ignored. `focusError` sends the user to the right step. **OK**
- Documents step filters out custom-field files (`!f.field_key`). **OK**
- Minor: if the configuration changes while the session is open and `step > steps.length`, the `?.` guards prevent a crash, but the progress label becomes empty. **NON-BLOCKER**
- PostHog: `enforcePublicAnalyticsOff` and the `index.html` guard untouched. No `console.log` of values/tokens (grep: 0). **OK** (runtime verification = UI/regression phase)
- Status: **not browser-tested yet** after these changes (compile PASS only).

### 4.2 `components/public-form/CustomFieldInput.jsx`
- 8 types rendered with Shadcn (Input/Textarea/Select/RadioGroup/Checkbox/Button). `aria-invalid`, `aria-describedby`, `role="alert"` for errors. `data-testid` on controls/options/upload/error. Touch targets `min-h-12`/`h-12`. **OK**
- No `dangerouslySetInnerHTML`. Labels/help text rendered as text (React escaping). **OK**
- File type: `accept` from `allowed_ext`, upload status (spinner), remove. The "pending until verified by HR" note is shown. Replace = remove + upload (no special replace button). **NON-BLOCKER**

### 4.3 `components/public-form/ReviewSection.jsx` — **OK** (only takes `steps` as a prop).
### 4.4 `lib/publicFormApi.js` — **OK** (`field_key` OR `document_type_code`).

### 4.5 `components/employee-form/FormBuilderSettings.jsx`
| Area | Finding | Class |
|---|---|---|
| Wiring | **Not imported by any page/route** (grep) → no menu entry `Data Karyawan → Form Pembaruan Data` yet | BELUM DIKERJAKAN (backoffice phase) |
| Active form / share link / QR / monitoring UI | Missing (backend `overview`/`monitoring` exists) | BELUM DIKERJAKAN |
| Drag & drop | @dnd-kit sections + fields per section, KeyboardSensor (keyboard-accessible handle, aria-label). Nested DndContext → needs a browser test. Moving a field to another section only through the Edit dialog (not cross-section drag) | PARTIAL · TEST PENDING |
| Deactivation | The section switch / custom field "Aktif" apply **without confirmation**. The requirement asks for confirmation | UX gap → backoffice phase |
| Forced indicator | A hidden core field that is REQUIRED in 01F has no "tetap tampil (Wajib 01F)" badge in the list (only a general note) | UX gap → backoffice phase |
| Preview | Generic preview only as a list. No desktop/mobile preview and no per-employee selection in the UI (backend supports `employee_id`) | PARTIAL |
| Scope UI | Shows master labels (code + name), not raw IDs. "Semua Karyawan" = no scope | OK |
| Security | No `console.log`, no raw response dump, errors through `errorMessage` + toast | OK |
| Compile | esbuild bundle of this file **PASS** (as a standalone entry) | PASS |

---

## 5. Changes made during the review (minimal fix)

1. `employee_form_builder.py` — `PUT /fields/{key}`: explicit `null` for `label, visible, active, section_key, type, form_level, options, validation` is rejected with **422** ("Nilai tidak boleh kosong: …"). `label_override`/`help_text`/`placeholder` = null is still allowed (reset to default).
2. `employee_form_builder.py` — when a field config row is first created by an update, `visible` is now carried from the current state (so it is no longer NULL).
3. Test hygiene (`/root/tenant_tests/test_01g_fb.py`, outside the repo): (a) at the start, leftover test-owned config from earlier runs (`cf_zt*`, `cs_zt*`) is **deactivated through the API** (no delete); (b) new check **N01** (explicit null → 422; `label_override: null` → 200).

No changes to the 01F engine, the 01G security flow, the migration, or the frontend.

## 6. Test rerun

| Run | Result | Note |
|---|---|---|
| esbuild `src/index.js` (bundle) | PASS | FormBuilderSettings not in the bundle yet (not wired) → compiled separately: PASS |
| `test_01g_fb.py` rerun #1 (after the fix, before test hygiene) | 65/67 | FAIL P16/P17 → **TEST FIXTURE**: REQUIRED custom fields `cf_zt070424_hobi`/`_mcu` from the **previous** run were still active in NEP, so the new employee was correctly blocked from submitting (product behaviour correct) |
| `test_01g_fb.py` rerun #2 (after test hygiene + N01) | **68/68 PASS** (RUN=073411) | includes M01–M05 migration/RBAC, C/K/S/SC config, P01–P18 public, F01–F06 file, MON1–4, PV1–3, ISO1–2, F01F (no 01F mutation), LOG1 |
| 01F / 01G regression | not re-run | Not affected by the fix: only `employee_form_builder.py` (backoffice config endpoint) changed. The 01F engine, `public_employee_form.py` and the frontend did not change in this review. Full regression = verification phase |
| `/api/health` after the tests | healthy, `mariadb:connected`, read_only false | backend.err: no new traceback after the tests |

## 7. Blocker / non-blocker summary

**Blocker:** none for continuing development.

**Open items (must be finished before final review):**
1. SECURITY-hardening: semantic denylist for custom keys/labels (status/employment/assignment/project/position/grade/level/payroll/salary/contract/system/audit).
2. PERFORMANCE: monitoring must aggregate/filter DB-side (COUNT/GROUP BY + JOIN assignment).
3. DATA INTEGRITY decision: hidden core fields → ignore on the server + do not send their prefill to the browser (except forced REQUIRED fields).
4. Full backend test coverage: hidden+RECOMMENDED / hidden+OFF / scope-specific REQUIRED, all scope types (project/grade/position/employee_status), exact monitoring counts + project/status filters, resume, file tenant isolation.
5. Backoffice UI (menu, active form, copy/share, QR + download, monitoring, deactivation confirmation, forced badge, desktop/mobile preview) = not built yet.
6. Browser QA of the dynamic public form + PostHog runtime check + viewports 360/390–430/tablet/1366.
7. Full 01F/01G regression + scoped ZT cleanup. Note: the test **mutated NEP config** (CORE rows sort/section from the layout test, `cs_zt_*` sections, `cf_zt*` fields — 21 inactive + 9 active from the last run, `cf_zt*` scopes, ZT submissions containing custom: 1 DRAFT + 2 PENDING, 3 pending custom-field files). This must go into the scoped cleanup dry-run.

**Non-blocker notes:** non-atomic `save_layout`; `data_version` bumped without a real change; extra prefill queries; dependency on the private `engine._scope_value` helper; custom REQUIRED file requires re-upload after 01H; progress label when the config changes mid-session.

## 8. Is the Form Builder safe to continue?

**YES — safe to continue to the "Finish backend" phase.** The m0009 warning is proven HARMLESS/EXPECTED (Note 1050 via the asyncmy logger). m0009 is idempotent (clean DB: apply → SKIP, no duplicates). There is no schema drift. The data-integrity principles hold (custom values do not touch `employees`; draft/submit are not official; 01F is not mutated; OFF ≠ OPTIONAL). The one real bug found (explicit null) was fixed with a minimal change and re-tested 68/68.

Enhancement 01G — Flexible Employee Form Builder: **IN PROGRESS**. Production Changed: **NO**.
