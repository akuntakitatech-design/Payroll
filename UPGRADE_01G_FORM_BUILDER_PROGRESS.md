# Enhancement 01G — Flexible Employee Form Builder · PROGRESS REPORT

## A. Status

**Enhancement 01G — Flexible Employee Form Builder: LOCKED ✅**

LOCKED per the user's FINAL CLOSING instruction (lock criteria met: targeted drag & drop PASS, cleanup PASS, integrity PASS, no new blocker, no new product regression — see §L). Staging/preview only · **Production Changed: NO** · No push / PR / merge / deploy · 01H not started.

Status legend: DONE · PASS · PARTIAL · FAIL · BELUM DIKERJAKAN. Evidence source: *agent-tested* (script/SQL/browser run by the agent), *testing-agent* (iteration_14), *user-confirmed* (explicit user acceptance).

| Module | Status |
|---|---|
| 01F — Data Completeness | LOCKED ✅ (user-confirmed) |
| 01G — Public Employee Form | LOCKED ✅ |
| Enhancement 01G — Flexible Employee Form Builder | **LOCKED ✅** |
| ↳ Custom Field E2E | **PASS ✅** (browser, agent-tested 24/24, RUN 085945; user asked for it to be recorded as PASS) |
| ↳ Drag & Drop E2E (targeted) | **PASS** (testing-agent iteration_15 + agent verification, §L) |
| ↳ Regression & Restart Verification | **PASS** (agent-tested; previous evidence, not rerun — product code unchanged) |
| ↳ Scoped ZT cleanup | **APPLIED · PASS** (integrity 17/17, §L) · G5 = OUT OF SCOPE / PROTECTED |
| 01H — HR Verification | NOT STARTED |

## B. Scope & locked decisions (unchanged)

Scope: menu Data Karyawan → Form Pembaruan Data; share link + QR (+PNG download); monitoring + project/department/employee-status filters; section/field configuration (show/hide, rename, reorder, move section); custom fields (8 types, Wajib/Anjuran/Opsional); scope per field; desktop+mobile preview; dynamic public form that keeps the 01G flow.
Decisions: core level comes only from 01F (REQUIRED=Wajib, RECOMMENDED=Anjuran, OFF=Tidak Dinilai ≠ Opsional) · 01F REQUIRED > builder hidden · custom has its own level and never enters the 01F score · `employee_form:configure` (tenant_admin + hr_admin; hr_manager excluded) · prefix `cf_`/`cs_` · used fields are deactivated only (no hard delete through the product) · custom files = pending attachment until 01H · no new columns on `employees`; `employee_custom_field_values` is written only by 01H.

## C. Implementation

| Item | Status | Note |
|---|---|---|
| Migration m0009 (4 tables + `employee_submission_files.field_key` + permission/grants) | DONE · PASS | ledger 1×, rerun SKIP, clean-DB test PASS, no schema drift/duplicate index (§G) |
| `core/form_builder.py` (01F levels, scope, layout, validation, reserved-name guard) | DONE | |
| Router `/api/employees/update-form/*` (overview, monitoring, config, sections, layout, fields, scopes, preview) | DONE | monitoring DB-side (SQL aggregate) |
| Reserved/HR-only key + label denylist (status, position, grade, payroll, contract, role, tenant, audit, system…) | DONE · PASS | RK01–RK05 |
| Hidden core rule: REQUIRED→still shown (forced); hidden RECOMMENDED/OFF→not shown/prefilled/accepted (422 `rejected_fields`) | DONE · PASS | P08, H01–H06, SCV4 |
| Public dynamic form (layout + custom in draft/submit + custom file upload) | DONE · PASS | backend P01–P18 + browser E2E |
| Backoffice page `/employees/update-form` + menu Data Karyawan → Form Pembaruan Data | DONE · PASS | E01 + responsive |
| Share link / copy / QR / PNG download | DONE · PASS | QR decoded = official public URL only (5 viewports + PNG) |
| Monitoring UI (5 stat cards + 3 filters) | DONE · PASS | MON1–MON7 + UI |
| Settings UI (sections, fields, custom, scope, drag-drop) | DONE · PASS | drag & drop mouse + keyboard (field + section) proven in the browser, persisted, followed by the public form (§L) |
| Deactivation confirmations (section / hide core / custom field) | DONE · PASS | UX1, UX2, UX3 |
| Forced badge ("Tetap ditampilkan karena diwajibkan aturan kelengkapan") | DONE · PASS | UX2 + H04 |
| Desktop + mobile preview | DONE · PASS | RB-* (preview mobile/desktop without overflow) |

## D. iteration_14.json review (testing agent) — read-only

Raw content: summary "backend 20/20, frontend 100%"; `backend_issues`/`frontend_issues` empty; 20 `passed_tests`; **no numeric total/FAIL/SKIP for the frontend and no duration**; `updated_files: ["/app/backend_test_01g.py"]` (that file is no longer in /app; a copy lives at `/root/tenant_tests/backend_test_01g_iter14.py`, outside the repo); `not_fully_tested`: drag & drop, hide/show confirmation dialogs, forced badge, E2E submission with custom data, QR PNG download, breakpoints (only 1920/768/390); screenshots: 5 (page, QR, settings, preview mobile, public verify).

Gate mapping (iteration_14 only): backoffice reachable CONFIRMED · custom create CONFIRMED (via API) · edit/inactive PARTIAL (only "deactivated after test") · scope PARTIAL (API endpoint only) · public dynamic rendering NOT PROVEN (verify page only) · REQUIRED custom NOT PROVEN · draft/resume NOT PROVEN · submit→PENDING NOT PROVEN · custom value not official NOT PROVEN · custom file pending/private NOT PROVEN · monitoring CONFIRMED · share link PARTIAL (URL display) · QR CONFIRMED (dialog/canvas; not decoded) · preview CONFIRMED (toggle) · RBAC CONFIRMED (employee 403) · tenant isolation NOT PROVEN · responsive PARTIAL (1920/768/390) · PostHog /public/* CONFIRMED (verify page).
Diff: all product files were last modified ≤ 07:53:40, the report at 08:00:07 → **the testing agent changed no product code** (A: none). B (test code): `backend_test_01g.py` (outside the repo). C (artifact): `test_reports/iteration_14.json` (untracked). D (unexpected): none. Sensitive scan of the diff: no credentials/token/password/.env. **Hygiene note:** `iteration_14.json` contains the synthetic NIK + DOB of fixture ZT01G-UI-3251 → do NOT commit as-is (redact first or leave untracked).
Conclusion: iteration_14 is only supporting evidence; the final gates were proven with the agent's own tests below.

## E. Custom Field E2E — PASS ✅ (browser, agent-tested, `/root/tenant_tests/e2e_01g_fb_browser.py`)

Final fixture: **ZT01G-E2E-085945** (RUN 085945; submission `72728b55…`). Record note: the earlier fixture **ZT01G-E2E-2106** only reached "HR created field" (the flow was not finished; the NIK was unknown to the test) → replaced by a run-owned fixture; 2106, 085257, 085735 are included in the cleanup dry-run.
Result **24/24 PASS**: HR (1366px, UI) creates dropdown `cf_zt_e2e_ukuran_baju_085945` Wajib (S/M/L/XL/XXL) + file `cf_zt_e2e_surat_vaksin_085945` Opsional → public verify (390px) → field rendered dynamically with the Wajib marker → REQUIRED empty = Review blocks submit (alert + button disabled) → fill L + upload file → draft DRAFT saved on the server (custom = option value `l`) → reload/resume: value L + file return → KTP/Ijazah documents → Review without block → submit → "Data berhasil dikirim" → **PENDING_HR_VERIFICATION**.
DB proof: custom value only in `submission.proposed.custom` · `employees` fingerprint identical · `employee_custom_field_values` = 0 (employee & global unchanged) · 01F rules/scopes unchanged · 01F score/required_total/required_fulfilled identical · custom file = pending attachment (`purpose=CUSTOM_FIELD`, tied to the submission) · no new official documents · anonymous access to the object rejected (content not served) · storage key never appears in public API responses · PostHog 0 requests / `window.posthog` undefined.
Test corrections during E2E (classification TEST, not product): E08 (by 01G design "Simpan & Lanjutkan" saves a partial draft; REQUIRED is enforced at Review/Submit), E10/D02 (value stored = option value `l`, label `L`), document codes `KTP`/`IJAZAH`, D09 local S3 emulator answers `400 UnsupportedAlgorithm` for unsigned requests (ENVIRONMENT; content still not served).

## F. Testing — actual results

| Area | Result | Evidence |
|---|---|---|
| Form Builder backend suite `test_01g_fb.py` | **88/88 PASS** (RUN 090434) | migration/RBAC/core/custom/reserved/section/scope/tenant/public/hidden/file/monitoring/preview/teardown |
| Custom Field E2E browser | **24/24 PASS** | §E |
| 01F isolation (custom does not enter numerator/denominator) `test_01g_fb_f01_isolation.py` | **4/4 PASS** | custom REQUIRED+RECOMMENDED active → score 61.1 / req 18/11 / rec 7/4 identical; no `cf_*` items; after deactivation identical |
| 01F full `test_01f.py` | **79/79 PASS** (RUN 090439) | |
| 01F concurrency | **not rerun — justified** | diff vs `bb73dbe`: `core/completeness.py`, `core/completeness_mapping.py`, `routers/completeness.py`, m0007, completeness UI = **0 lines changed**; Form Builder only imports/reads the engine; `db.py` only additive (4 new table specs + 1 column + indexes). Latest evidence 34/34 (01G final gate) |
| 01G main `test_01g.py` | **77/77 PASS** (RUN 091044) | first run 76/77: J01 = **TEST FIXTURE** (sample `LIMIT 1` picked a portal link with `token_hash` NULL → EXPLAIN "Impossible WHERE"; with a real value → `ux_public_link_token`, type const). Test fix: filter `token_hash IS NOT NULL` |
| 01G security `test_01g_security.py` | **35/35 PASS** | |
| 01G portal `test_01g_portal.py` | **59/59 PASS** | verify, draft, family, documents, submit, pending, lock |
| 01G analytics static | **9/9 PASS** | |
| Tenant isolation pytest | **1 passed** | |
| Expired session (browser, dynamic form) | **PASS** | EX1: session expired → re-verify screen, token cleared from the browser, server draft (id+version) kept, PostHog 0; backend H01/H02/H03 PASS |
| PostHog /public/* (runtime) | **PASS** | E14, RP-360…1366, EX1 |
| Responsive public 360/390/430/768/1366 | **PASS** (5/5) | no horizontal overflow (verify/step/review), CTA visible, custom dropdown can be opened, upload button ≥44px |
| Responsive backoffice 360/390/430/768/1366 | **PASS** (5/5) | Form Aktif/Monitoring/Pengaturan/Preview mobile+desktop without overflow |
| QR | **PASS** | decoded at 5 viewports + downloaded PNG = official URL `/public/NEP/update-data`, no query/token/PII |
| UX confirmations + forced badge | **PASS** | UX1/UX2/UX3 (UX3 first FAIL = TEST: confirmation appears on Save, by design) |
| Compile esbuild | **PASS** | |
| Production build `yarn build` | **PASS** | 1 old eslint warning in `EmployeeMigrationPage.jsx` (not related, not refactored). The earlier webpack deprecation did not reappear |
| RBAC `employee_form:configure` | **PASS** | M05, R01 403, R02 401, MON4; grants: tenant_admin + hr_admin |

## G. Restart & m0009

- Environment event (ENVIRONMENT): container reset → `payroll-dev-mariadb` FATAL (binary `/usr/sbin/mariadbd` missing). Recovery following `/app/ops/README.md`: reinstall `mariadb-server`/`mariadb-client` (10.11), datadir **not** re-initialized, started through supervisor. Log shows `change buffer is corrupted…` = known infra issue (not touched).
- Clean restart of the backend 1× → `/api/health` healthy, `mariadb:connected`, `read_only:false`; APP_ENV=staging, AUTO_SEED=false, READ_ONLY=false, ENABLE_SCHEDULER=false; no crash loop, no tracebacks, no new 5xx; the startup log did **not** show the warning.
- m0009: ledger **1 row**; normal runner → `SKIP`; the only warning is still `Table 'schema_migrations' already exists` (Note 1050, informational, same as analyzed); no new warning; 5 tables match TABLE_SPECS + INDEX_SPECS, no duplicate indexes; permission 1 row, grants 2.
- Before/after restart (employees, sections, fields, scopes, official custom values, submissions draft/pending, pending files, documents, 01F rules/scopes, ledger, tables, indexes): **delta NONE**.

## H. Scoped ZT cleanup — DRY-RUN (`/root/tenant_tests/cleanup_01g_fb_dryrun.py`, no apply mode) → APPLIED in §L (G5 excluded)

Window `created_at ≥ 2026-09-27 07:00 UTC` (m0009 07:01:59), NEP/KBS only, naming pattern + run id:
| Group | Tenant | Identifier | Rows | Ownership evidence |
|---|---|---|---|---|
| G1 Form Builder suite | NEP 14 / KBS 7 | `ZT01G-FB<RUN>-*`, name `ZT01G FB *` (runs 070424…090434) | 21 employees | test_01g_fb.py pattern |
| G2 testing agent | NEP 1 | `ZT01G-UI-3251` | 1 | iteration_14 `test_employee_created` |
| G3 browser E2E | NEP 4 | `ZT01G-E2E-2106/085257/085735/085945` | 4 | E2E setup |
| G4 01G regression rerun | NEP 11 / KBS 3 | `ZT01G-090739/091044-*`, `ZT01G-S090744-*`, `ZT01G-P090746-*` | 14 | cleanup_01g pattern + run ids of this session |
| G5 01F regression rerun | NEP 6 | `ZT01F-090439-*` + `NEP-0082` (name `ZT01F *`) | 6 | test_01f.py run 090439 (09:04:41–09:04:50) — **cross-module**, see below |
| C1 custom fields | NEP | `cf_zt*` (cf_zt<RUN>, cf_zt_e2e_*, cf_zt_ui_*, cf_ztiso*) — all created within the window, 0 active | 93 | test prefix; no non-`cf_zt` custom fields exist |
| C2 custom sections | NEP | `cs_zt_tambahan_<RUN>` ×7 + `cs_zt_ui_tambahan` | 8 | no system sections |
| C3 scopes of C1 | NEP | — | 18 | |
Dependents of fixture employees: public_links 56, submissions 20 (DRAFT 6 / PENDING 14), submission files 21 (13 custom + 8 documents), completeness 46, status_history 48, family 3, assignments 2, salary_history 2, salaries 1, contracts 1, certifications 1, import_rows 2, candidates 1; official documents 2 (G4 S090744-A comparison doc, G5 ZT01F-090439-01); audit_logs 368; attributable rate-limit rows 8; storage objects owned by fixtures 23.
G5 second level: candidate "ZT01F Kandidat 090439" + offerings 1, interviews 1, status_history 10, approvals 2; import batch 1 (2 rows, all G5).
Ambiguity checks: non-fixture field inside a `cs_zt` section = 0 · `cf_zt` value in a non-fixture submission = 0 · official `cf_zt` values = 0 · CORE config rows (10) = all default values → **PROTECTED, not deleted** · system sections protected.
Storage orphan check (two-way, list/head only): 50 objects vs 40 DB refs → objects without a DB ref 10 (**all pre-existing, not fixtures → not touched**), DB refs without an object 0.
Protected baseline: employees non-fixture REAL 0 / NEP 97 / KBS 3 / CONTOHJASA 0 (NEP includes 84 older ZT look-alikes outside the window → excluded). Counter `employee_id_next_number`: NEP 83, KBS 1, REAL 1, CONTOHJASA 1 (must stay the same).
Items that need a user decision before apply: (1) G5 includes recruitment/import/payroll rows (cross-module) — include or leave for a dedicated 01F cleanup; (2) C1/C2 fixtures are deleted physically via SQL (cleanup of test data, not a product hard delete); (3) audit_logs 368 are deleted following the old cleanup pattern, or kept; (4) verify_ip rate-limit rows from browser runs (real client IP via ingress) cannot be attributed → excluded.

## I. Known non-blockers

1. Server-side enforcement of 01F core REQUIRED at submit is still **existing 01G behavior** (baseline `bb73dbe`: the server enforces only custom REQUIRED; core gaps are gated on the client at Review). Not a Form Builder regression → decision for 01H/hardening.
2. G5 cleanup (ZT01F run 090439: 6 employees + recruitment/import/payroll rows) **deferred** to a dedicated cross-module/01F cleanup — OUT OF SCOPE / PROTECTED, verified unchanged.
3. 10 old storage orphans (objects without a DB ref) **not owned by the Form Builder** — not touched (hash identical before/after).
4. The Cloudflare Insights beacon injected by the preview platform edge is blocked by the 01G public CSP on `/public/*` (console message) — ENVIRONMENT/expected (third-party scripts are not allowed on the public form).
5. The 18 historical `5xx` lines on `/completeness/*` in the access log are all before the first 01G call (01F pre-deadlock-fix era, already documented); 0 `5xx` from today's work.
6. At 360px, long labels in the builder list are truncated (readable via Edit) — polish. `save_layout` not atomic; extra prefill queries (+≈7); dependency on the private 01F helper `_scope_value` — from the code review, NON-BLOCKER.
7. Mouse drag of a section toward a target that is off-screen relies on dnd-kit auto-scroll (standard behavior); precise with the pointer in the viewport and with the keyboard.

## J. Git / Environment

- Branch `feature/upgrade-01g-form-builder` (base `bb73dbe` = origin/main after PR #14).
- Repository hygiene (final): the local-only commits `c083e42`, `a8a6e9c`, `0a3e48c` (never pushed; 0 remote refs) were squashed into **one** commit `feat(hrga): add flexible employee form builder`. The raw `test_reports/iteration_14.json` (synthetic fixture NIK/DOB) and `iteration_15.json` are **not** in the repository/PR history (testing artifacts; their results are documented in §D/§L). The platform's `.gitignore` auto-entries are not included (not related). The inherited `.env.example` / `backend/.env.example` are not touched.
- `frontend/yarn.lock` is included (lockfile for `@dnd-kit/*` + `qrcode.react` in `package.json`).
- Test scripts stay outside the repo (`/root/tenant_tests/`, the same convention as the earlier suites); evidence is summarized in this report.
- Product code: **no changes** since the full regression (the section-collision experiment during the DnD diagnosis was reverted).
- No merge/deploy. **Production Changed: NO**.

## K. Next step

**STOP for user review.** Do not start 01H. No push / PR / merge / deploy. Open for user decision: (1) rewrite local history to drop the unredacted iteration_14 from `a8a6e9c` (or leave it; not pushed); (2) dedicated cleanup for G5/01F cross-module fixtures; (3) hardening: server-side enforcement of core REQUIRED at submit (01H).

## L. FINAL CLOSING (2026-09-27)

**1. Targeted drag & drop E2E.** Run-owned fixture: section `cs_zt_dnd_093356` + `cf_zt_dnd_093356_a` (REQUIRED) / `_b` / `_c` (OPTIONAL).
- Testing agent (`iteration_15.json`, 1366 backoffice + 390 public, no product code changed): field mouse drag C above A → C,A,B → saved → reload persisted; field keyboard drag (Space/ArrowUp/Space) → C,B,A → persisted; A stays Wajib (backoffice + public); public DOM order = C,B,A; 0 overflow; 0 console errors → **CONFIRMED**. The section drag in that report was **NOT PROVEN** (DB `sort_order`/`updated_at` did not change; the report says "step 6" = last) → most likely not saved by the agent.
- Agent verification (`dnd_01g_fb_section.py`): section keyboard drag → save (PUT /layout 200) → reload persisted; section mouse drag with a realistic pointer (inside the viewport, release on the target) → lands exactly next to the target (before `family`, then between `family` and `bank_tax`) → persisted; 0 console errors; public steps follow the saved order: `personal → family → cs_zt_dnd_093356 → bank_tax → bpjs → documents`, fields C,B,A, A = REQUIRED.
- Diagnosis note: an early mouse attempt "overshot" to the start/end of the list — cause = TEST ARTIFACT (the script moved the pointer outside the viewport → dnd-kit auto-scroll). A `pointerWithin` change tried meanwhile was **reverted** (not needed, not kept). Result: **Drag & Drop E2E — PASS**.

**2. Cleanup apply** (`cleanup_01g_fb_apply.py`: `plan` → exact-ID manifest; `apply` → ownership re-validated per ID, deletes only the manifest IDs; no old cleanup script used; counters never written). Scope G1 21 + G2 1 + G3 4 (incl. 2106, 085257, 085735, 085945) + G4 14 = **40 employees** (NEP 30 / KBS 10) + C1/C2/C3. Deleted rows: submission_files 21, update_submissions 20 (DRAFT 6 / PENDING 14), public_links (session/invitation) 61, completeness 40, family 2, status_history 40, documents 1 (G4 comparison doc), form_field_scopes 18, form_fields 96 (`cf_zt*` incl. 3 DnD), form_sections 9 (`cs_zt*` incl. DnD), audit_logs 356 (record_id = target entities), public_rate_limits 8 (attributable), employees 40; **storage objects 22**. G5 = **OUT OF SCOPE / PROTECTED** (not in the manifest).

**3. Integrity check** (`integrity_01g_fb.py`, before vs after) **17/17 PASS**: target employees / fields / sections / scopes / audit / rate / dependents = 0 · 0 orphan rows (all `employee_id` tables) · 0 orphan scopes / fields without a section / files without a submission · 0 `cf_zt` values in any submission · **G5 unchanged** (6 employees, 25 dependents, 1 doc, 14 candidate children, 19 audit, row hash identical) · non-target baseline unchanged (REAL 0 / NEP 103 [97 baseline + 6 G5] / KBS 3 / CONTOHJASA 0, row hash identical) · CORE config + system sections unchanged · non-target custom/official custom values (0)/documents/audit unchanged · **counters unchanged (NEP 83)** · migration ledger unchanged · storage: 50 → 28 (exactly 22 target objects deleted), non-target objects hash identical, **10 old orphans untouched** (hash identical), no new orphans, 0 DB refs without an object.

**4. Post-cleanup smoke** (`smoke_01g_fb_post_cleanup.py`): config/overview/monitoring/preview 200 · config: 0 `cf_zt`/0 `cs_zt`, 23 core, system sections complete · KBS config readable · backoffice 4 tabs open, "Data Pribadi = 17 field", 0 console errors · public portal `/public/NEP/update-data` opens, 0 overflow, PostHog 0; the only console message = platform Cloudflare beacon blocked by the public CSP (ENVIRONMENT/expected) · backend: 0 new 5xx → **PASS**.

**5. Regression = previous evidence (not rerun, product code unchanged):** Form Builder 88/88 · Custom Field E2E 24/24 · 01F 79/79 + isolation 4/4 · 01G 77/77 · security 35/35 · portal 59/59 · analytics 9/9 · tenant pytest PASS · expired browser PASS · responsive 5 viewports PASS · build PASS · restart delta NONE.

**6. Final decision:** drag & drop PASS · cleanup PASS · integrity PASS · no new blocker · no product regression → **Enhancement 01G — Flexible Employee Form Builder: LOCKED ✅**. STOP for review.
