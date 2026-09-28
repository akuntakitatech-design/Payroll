# UPGRADE 01I — ROLE & DATA SCOPE · STEP 1 AUDIT (no code)

Date: 2026-09-27 · Baseline: 01H HR Verification LOCKED (local commit `630ce8b`, not yet pushed) · Production Changed: **NO**
Scope: decide **which employees** a user can see/act on inside a tenant. Authentication, tenant isolation and RBAC are **not** redesigned.
Rule going forward: **CAN_DO_ACTION (permission) AND CAN_ACCESS_EMPLOYEE (data scope)**. Both checks are required, and neither can stand in for the other.

Classification legend: **REUSE** (use as-is) · **MODIFY** (small change to existing) · **NEW** (additive) · **DEFER** (not in 01I).

---

## 1. Existing RBAC architecture (A)

| Item | Finding | Class |
|---|---|---|
| Tables | `roles` (key, name, is_system, scope), `permissions` (resource:action), `role_permissions` (role_key, permission_key), `user_company_roles` (user_id, role_key, company_id; NULL = global), `users` — `app/core/db.py:231-243, 701-705`. All are GLOBAL collections, so they are not tenant-scoped (`tenancy.py:128-135`). | REUSE |
| AuthContext | `app/core/deps.py:28-89`, built in `_base_auth` (`deps.py:214-299`). It carries user, active company, role_keys, the union of role_permissions (`permissions`), active `modules`, `is_super_admin`, and `tdb` (tenant-scoped DB). | MODIFY (add resolved `scope`) |
| Permission dependency | `require_permission(resource, action, module_key)` (`deps.py:322-340`) runs the module gate, then the permission check. The `*:*` wildcard applies to `super_admin` and `company_owner`. | REUSE |
| Platform Admin | Global role `super_admin`. It can access and switch to any tenant (`deps.py:139-160`), and `require_platform_admin()` protects the platform routes. | REUSE (always ALL scope) |
| Tenant admin | `tenant_admin` is a company role with all permissions except company create/delete (`rbac.py:236`). There is no special code path. `company_owner` holds `*:*`. | REUSE (forced ALL scope) |
| Roles in use | `super_admin, tenant_admin, company_owner, hr_admin, hr_manager, finance, manager, supervisor, employee` (`rbac.py:97-107`). All are `is_system`. Custom roles are supported via `POST/PUT /api/roles…` (`users.py:384-426`). | REUSE |
| User ↔ role | Per company via `user_company_roles`. User create/update replaces the rows for `ctx.company_id` (`users.py:165-284`). `grant-company-access` adds roles in another tenant (`users.py:310-346`). | REUSE |
| Existing data restriction | **None.** No project_ids, department_ids, data_scope, or team/manager filter exists anywhere. `supervisor` in approvals is only an approver type (`approvals.py:30`). The only "own" rules are ESS self endpoints (`attendance my_*`, `payroll my_payslips`, `payslip:view_own`). | NEW needed |
| Tenant isolation | `TenantCollection._where()` always injects `company_id` and rejects a foreign company_id with 403, so it is fail-closed (`tenancy.py:141-264`). | REUSE — 01I builds **on top** of it |

**Conclusion (A):** every holder of `employee:view` currently sees **all** employees of the tenant. Scope has to be added as a second, independent layer.

## 2. Authoritative organizational data (B)

| Dimension | Authoritative source | Mirror / legacy | History |
|---|---|---|---|
| Tenant | `employees.company_id` (tenant guard) | — | — |
| **Current project** | `employee_assignments` row with `assignment_status='ACTIVE'` (01D, max 1 per employee, row-locked) | `employees.project_id`. **Mirror kept in sync in the SAME transaction** by `_legacy_sync()` (`employee_assignment.py:91-136`). Direct edits are stripped (`employees.py:483-489`). Ending an assignment sets the mirror to NULL. | `employee_assignments` rows with `ENDED` |
| Department / division / position / work location / branch / cost center | Same ACTIVE assignment (`assignment.PLACEMENT_FIELDS`) | `employees.department_id, division_id, position_id, work_location_id, branch_id, cost_center_id` (same sync) | ENDED assignments |
| Grade / level | `employees.job_grade_id` (not part of assignment) | — | — |
| Employment status (contract type) | `employees.employment_status_id` | — | — |
| Business status (01B: AKTIF / STANDBY / TIDAK_AKTIF…) | `employees.current_employee_status_id` → `employee_business_statuses` | `employees.status` (active/inactive; legacy) | `employee_status_history` |

Key facts:
- **STANDBY is a business status, not an assignment.** A 01B status change does **not** end the assignment (`employee_status.py:288-372`). An employee who is STANDBY but still has an ACTIVE assignment therefore still "belongs" to that project until HR ends the assignment. Only `POST …/assignments/end` clears the project. It can optionally chain a status change.
- **Planned/future assignments are not supported.** A start date later than today is rejected (`employee_assignment.py:56`). A transfer takes effect when it is recorded.
- Recommendation: build scope on the **ACTIVE assignment**, read through the transactionally-synced mirror `employees.project_id`. It is the same value, it is filterable in one SQL predicate, and it needs no join. Any denormalization risk is covered by a consistency test (mirror == ACTIVE assignment). Legacy `employees.status` is **not** used for scope decisions.

## 3. Core HR access inventory (C) — current authorization

Legend: TENANT = tenant guard only · PERM = permission check · SCOPED = data-scoped · UNSCOPED = no scope (all tenant rows)

| Area | Endpoints (prefix /api) | Permission | Today | 01I target |
|---|---|---|---|---|
| Data Karyawan list / stats / catalog | `GET /employees`, `/employees/stats`, `/employees/catalog` | employee:view | PERM + UNSCOPED (project/department are *optional query filters only*) | SCOPED at SQL level |
| Employee detail / update / status patch / delete | `GET/PUT/PATCH/DELETE /employees/{id}` | employee:view/edit/delete | PERM + UNSCOPED (a known UUID works) | SCOPED, 404 when out of scope |
| Create employee | `POST /employees` | employee:create | PERM | Restricted user: initial project required and in scope |
| Profile 360: family, photo, timeline | `/employees/{id}/family…`, `/photo`, `/timeline` | employee:view/edit | UNSCOPED | SCOPED through a shared employee guard |
| 01B status history / change | `GET /employees/{id}/status-history`, `POST /employees/{id}/status-change` | employee:view / employee_status:change | UNSCOPED | SCOPED. Status master CRUD stays tenant config |
| 01D assignments | `GET/POST /employees/{id}/assignments`, `/transfer`, `/end` | employee:view/edit | UNSCOPED | SCOPED. Transfer **target** project must also be in scope |
| 01E import / migration | `/employees/import/*`, `/employee-import/batches…` (+ validation xlsx) | employee:create / employee:import | PERM (tenant-wide batches) | **ALL scope only** (tenant-wide operation) |
| 01F completeness | `GET /completeness/summary`, `/completeness/employees`, `/employees/{id}/completeness`, reevaluate; rules/scopes config | employee:view/edit, employee_completeness:configure | UNSCOPED (the list is an SQL join, so a predicate is easy to add) | Summary/list/detail SCOPED. Config and bulk reevaluate: **ALL scope only** |
| 01G public-form admin (links) + Form Builder monitoring | `public_employee_form` admin endpoints, `GET /employees/update-form/monitoring`, `/overview` | employee:view/edit, employee_form:configure | UNSCOPED | Link generate/revoke and monitoring SCOPED. Form Builder config: **ALL scope only** |
| 01H verification | `GET /employees/update-verifications` (+summary), `GET /{id}`, `/files/{fid}`, `POST approve/reject/request-revision` | employee_form:verify | UNSCOPED. The list loads all submissions of a status, then filters by project **in Python** | SCOPED by the employee's **current** project at SQL level. Every decision re-checks scope |
| Documents (owner_type=employee) | `GET /documents`, `/{id}`, `/preview`, `/download`, `POST`, `PUT`, `DELETE` | document:* | UNSCOPED | Employee-owned docs SCOPED. Company/other owner types unchanged |
| Contracts | `/contracts…` | contract:* | UNSCOPED | SCOPED by employee |
| Certifications | `/certifications…` | certification:* | UNSCOPED | SCOPED by employee |
| Dashboard | `GET /dashboard/summary` | auth only | UNSCOPED employee counts | Counts SCOPED |
| Global search | `GlobalSearch.jsx` navigates to `/employees?q=` and `/documents?q=` | — | Uses the list endpoints | Covered by list scoping (REUSE) |
| Exports touching employees | attendance `/recap/export`, leave `/export`, overtime `/export`, payroll `/runs/{id}/export` and statutory reports, audit `/export`, 01E validation xlsx | *:export | UNSCOPED | See §8 |
| Payroll / leave / attendance / schedules lists | `payroll.py, leave.py, attendance.py, overtime.py, schedules.py` | module perms | UNSCOPED | **DEFER** to their modules, but exports are fail-closed (§8) |

## 4. Write operations (D)

A scoped user can **currently** modify any tenant employee by calling the API directly with a known UUID: `PUT /employees/{id}`, status change, assignment transfer/end, family/photo, documents, contracts, certifications, and 01H approve/reject/revision. The UI hides nothing today, and hiding alone would not be enough. **01I must enforce this in the backend**, in one place per employee-bound route: a shared `get_scoped_employee()` guard, plus an SQL predicate for lists.

## 5. Recommended scope model

**Per user per company. Not per role.** Two "Admin Site" users share a role but have different projects. The same user can have different scopes in different tenants.

| Mode | Meaning |
|---|---|
| `ALL` | All employees of the tenant (default for existing users, which keeps today's behaviour) |
| `PROJECTS` | Only employees whose **current ACTIVE assignment** project is in the user's project list (1..n projects) |

- **Forced ALL:** `super_admin` (platform), `tenant_admin`, `company_owner`. Their scope cannot be restricted, and the UI shows it as locked. HR Pusat simply keeps `ALL`.
- **Fail-closed:**
  - `PROJECTS` with 0 valid projects, or only deleted/inactive projects, returns **no employees**. Scope never widens silently.
  - An unknown mode is treated like PROJECTS-empty.
  - A missing row means ALL. This keeps existing users unchanged and is shown explicitly as "Semua Data Perusahaan" in the UI and in the audit.
- **Department / division / site:** the data model supports them cleanly (masters exist and the dimensions are mirrored from the ACTIVE assignment). They are **DEFER**. The schema below is dimension-generic (`dimension='project'` only in 01I), so they can be added later without redesign or master duplication.
- **Standby / no assignment** (project NULL): visible to ALL-scope users only. A "Tanpa Project" pseudo-scope is DEFER.

## 6. Schema (smallest additive) — NEW, migration `m0011_data_scope` (not yet implemented)

Existing structures cannot hold scope. `users` is global, and `user_company_roles` is role-keyed with no column for data values. The proposal adds two tenant tables, both with `company_id`, so they are auto-guarded by `TenantCollection`:

```
user_data_scopes       (id, company_id, user_id, mode ENUM('ALL','PROJECTS'), status, created_*/updated_*)
                        UNIQUE (company_id, user_id)
user_data_scope_items  (id, company_id, user_id, dimension VARCHAR(32)='project', ref_id VARCHAR(64), status, created_*)
                        UNIQUE (company_id, user_id, dimension, ref_id);  INDEX (company_id, user_id)
```

- There is no duplication of users, projects or assignments. `ref_id` points to `projects.id`. The FK is validated in the API, and a deleted project is ignored, which is fail-closed.
- Index **NEW:** `employees (company_id, project_id)` does not exist today, and every scoped list and count will use it. `employee_assignments (company_id, project_id, assignment_status)` is **DEFER**, because scope reads the mirror.
- Permission: reuse `user:edit` to manage scope (**REUSE**). Every scope change writes an audit entry (`user.data_scope_update`, before/after project list).

## 7. Endpoint enforcement strategy

1. **Resolve once per request** (MODIFY `_base_auth`): one query of the two scope tables for (company, user) gives `ctx.scope = EmployeeScope(all: bool, project_ids: frozenset)`. Forced-ALL roles skip the query. There are no per-row checks and no N+1 queries.
2. **Lists / counts (SQL level):** helper `scope_where(ctx)`.
   - ALL scope: `{}`.
   - PROJECTS scope: `{"project_id": {"$in": [...]}}`.
   - Empty PROJECTS scope: a predicate that matches nothing.
   - This is applied to every `employees` query, and to joined queries such as submissions, completeness, documents, contracts and certifications through an employee join or subquery (`employee_id IN (SELECT id FROM employees WHERE company_id=? AND project_id IN (...))`). Employees are never loaded into Python for filtering. The 01H list's in-Python project filter becomes an SQL predicate (MODIFY).
3. **Detail / sub-resource / write:** dependency `get_scoped_employee(employee_id)` returns the employee or a **404 generic** (not 403, so existence does not leak). It is used by every `/employees/{id}/…` route, and after loading the owning employee for documents, contracts, certifications and 01H submissions.
4. **Tenant-wide operations:** `require_all_scope()` for import/migration, completeness rules/scopes config, bulk reevaluate, Form Builder config, and exports not yet scoped.
5. **Coverage guard:** a test introspects `app.routes` and fails if any route with an `employee_id` path param (or submission/document/contract/certification id) lacks the scoped dependency.

## 8. Export behaviour

- There is no Core HR employee export today, and 01E only produces a batch validation xlsx, which becomes ALL-only. Any future Core HR export must use `scope_where`.
- The attendance / leave / overtime / payroll / audit exports contain employee rows but live in modules outside 01I. To satisfy "export must never contain out-of-scope employees", **restricted (PROJECTS) users get 403** on those exports until each module is scoped (**fail-closed, MODIFY**, one dependency line per export). ALL-scope users are unchanged.

## 9. Transfer / standby / history rules (critical cases)

| Case | Recommendation |
|---|---|
| Employee moves Project A → B | The transfer is recorded in one transaction: the ACTIVE assignment changes and the mirror changes with it. **Admin A loses access immediately at that commit**, and Admin B gains it. There is no scheduled or future transfer, because 01D rejects future dates. |
| STANDBY with no current assignment | Only ALL-scope users (HR Pusat / Tenant Admin) can see the employee. Project admins cannot. STANDBY with an assignment still ACTIVE stays visible to that project's admin until HR ends the assignment. This follows 01D, not the 01B label. |
| Ended assignment | Same as no assignment: tenant-wide users only. |
| History | While the employee is **currently** in scope, a restricted user sees the **full** profile history: all assignments, status history, and 01H history. PT REAL site admins need the context, for example previous sites and prior disciplinary status. After a transfer out, they have **no access at all**, including to the history. Per-project history slicing is DEFER. It adds complexity with little operational value. |
| HR Pusat / Tenant Admin | Tenant-wide (ALL). Tenant admin is forced ALL. |
| Platform Admin Akuntakita | Unchanged: forced ALL inside whichever tenant it switched to. Tenant isolation is untouched. |
| Direct API with an out-of-scope UUID | 404 generic on detail, sub-resources, writes, files and 01H decisions, even when the UI hides the employee. |
| Tenant isolation | Unchanged. Scope is evaluated only after the tenant guard, so it can never widen across tenants. |

## 10. 01H interaction

- A submission follows the employee's **current** assignment, not the project at submission time.
- **Created while in A, moved to B before review:** reviewable by HR users whose scope contains **B**, and by ALL-scope users. Admin A loses it. The verification list, summary counts, detail, file download and approve/reject/revision all use the same predicate. Approve re-checks scope inside the request before the transaction.
- A transfer that makes the placement differ from the baseline does not create an 01H conflict, because assignment fields are not part of the public form. 01H conflict, baseline and identity logic are **unchanged (REUSE)**.
- 01F/01G locked behaviour is unchanged. Only the *set of visible employees* is filtered: monitoring counts, completeness lists, public link management.

## 11. UI proposal

- **Pengguna (UsersPage) → user dialog → new section "Cakupan Data"** (shadcn RadioGroup):
  - `Semua Data Perusahaan`.
  - `Project Tertentu`: a searchable multi-select (Command + Popover) with visible chips/list of the chosen projects, a count, and a validation that at least 1 project is selected.
  - For tenant_admin/company_owner the section is disabled with the text "Peran ini selalu mencakup semua data".
- **Users table:** a new column "Cakupan" showing "Semua data" or "3 project" with a tooltip listing them.
- **Logged-in user awareness:**
  - The Topbar user menu shows "Cakupan data: Semua data perusahaan" or "Project: A, B (+1)".
  - Data Karyawan, 01H and 01F lists show a small info banner "Menampilkan karyawan dalam cakupan Anda (Project A, B)".
  - Project filter dropdowns list only in-scope projects.
- RolesPage is unchanged: roles stay *actions*, scope stays *data*.

## 12. Performance (5–6k active employees)

- One scope query per request, which could be cached on `ctx`.
- Lists and counts use a single SQL predicate `project_id IN (…)` on the new `(company_id, project_id)` index. Joined lists use subquery/join predicates, with no Python-side filtering and no N+1 queries.
- The 01H list currently fetches all open submissions and filters them in Python. It will become SQL-filtered with pagination, as noted in §7.
- No per-row scope calculation, and no new materialized tables.

## 13. Findings summary (REUSE / MODIFY / NEW / DEFER)

- **REUSE:** tenant guard; RBAC tables and `require_permission`; ACTIVE assignment and its synced mirror; project master; 01H/01F/01G logic; global search through the list endpoints; `user:edit` permission.
- **MODIFY:**
  - Backend: `_base_auth` (resolve scope); employees list/detail/write; profile sub-routes; 01B/01D routes; 01F list/summary; 01G link and monitoring routes; 01H list (SQL filter) and decisions; documents/contracts/certifications employee ownership; dashboard counts; exports (fail-closed); import and config routes (ALL-only).
  - Frontend: UsersPage, Topbar, list banners.
- **NEW:** `m0011_data_scope` (2 tables + employees `(company_id, project_id)` index); `EmployeeScope` + `scope_where` + `get_scoped_employee` + `require_all_scope`; scope API (`GET/PUT /api/users/{id}/data-scope`); route-coverage test.
- **DEFER:** department/division/site dimensions; "Tanpa Project" pseudo-scope; per-project history slicing; scoping payroll/leave/attendance lists (their exports are already fail-closed); a planned-assignment effective date.

## 14. Implementation sequence & risk

| Step | Content | Risk |
|---|---|---|
| 1 | m0011 (tables + index), scope resolver in AuthContext, helpers, scope API. No behaviour change for ALL users | Low |
| 2 | Employees list/detail/write, profile, 01B, 01D (transfer target check), dashboard counts | Medium: many routes. Mitigated by the shared guard and the coverage test |
| 3 | 01F / 01G / 01H (SQL filter plus decision re-check), documents/contracts/certifications | Medium: joins on owner/employee |
| 4 | ALL-only guards (import, configs, bulk reevaluate), fail-closed exports | Low |
| 5 | UI: Cakupan Data in UsersPage, Topbar indicator, list banners, scoped project filters | Low |
| 6 | Tests + staging E2E | — |

**Overall risk: MEDIUM-HIGH, because of breadth rather than complexity.** The main danger is a route missed by enforcement. The route-coverage test and 404-by-default guards address it.

## 15. Targeted testing strategy

- **Backend `tests/test_data_scope_01i.py`** (in-process ASGI + local MariaDB, synthetic fixtures), covering this matrix:
  - users: ALL-HR, PROJECTS {A}, PROJECTS {A,B}, PROJECTS {} (fail-closed), tenant_admin (forced ALL), super_admin;
  - employees: in A, in B, standby with no assignment, moved A→B;
  - endpoints: list/count/stats, detail 404, every `/employees/{id}/…` sub-route, update/status/transfer (target out of scope → 403/404), documents/contracts/certifications, 01F summary/list, 01G monitoring/link, 01H list/summary/detail/file/approve/reject/revision, dashboard, exports (403 for restricted), import/config (ALL-only);
  - cross-tenant still 404;
  - mirror == ACTIVE assignment consistency;
  - query-plan check that the index is used, or at least a bounded query count.
- **Route-coverage test** that introspects the routes.
- **Regression:** `test_hr_verification_01h.py` (70/70) and `test_tenant_isolation.py` (12/12). No payroll/recruitment suites.
- **Staging E2E (browser)** after implementation:
  - the Cakupan Data UI;
  - project admin sees only project A;
  - a direct URL to a B employee gives "not found";
  - transfer A→B moves visibility;
  - 01H review follows the current project;
  - exports blocked for restricted users.

**STOP — awaiting review before any code. No push, PR, merge or deploy. 01J not started. Production Changed: NO.**
