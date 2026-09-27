# UPGRADE 01G — Public Employee Form · Progress Report (01G-A Backend + 01G-B Public UI + Final Verification)

## **UPGRADE 01G — PUBLIC EMPLOYEE FORM: LOCKED ✅**
All blocking gates below were agent-tested and PASS. This is **waiting for user review**. **01H has NOT been started.** Production Changed: **NO** · no push / PR / merge / deploy · no product code change in the final gate (git: `backend/` and `frontend/` are identical to HEAD `b3e6480`).

### F.0 Final gate — summary (2026-09-26 → 2026-09-27, staging `hris_staging`, branch `feature/upgrade-01g-public-employee-form`)
Status labels: **PASS** = run in this final gate and passed · **PREVIOUS EVIDENCE** = older result, not re-run now · **NOT RUN** = not done.

| # | Gate | Status | Evidence |
|---|---|---|---|
| 1 | 01G backend main / security / portal | **PASS** | `test_01g.py` 77/77 · `test_01g_security.py` 35/35 · `test_01g_portal.py` 59/59 (final gate, before the environment recycle; no code change since) |
| 2 | Analytics absent on `/public/*` | **PASS** | static 9/9; browser (after restart): `window.posthog` undefined, 0 PostHog resources/requests, `emergent-main.js` not loaded; inline `posthog` text exists only in the gated loader/comment and is never run |
| 3 | Tenant / security isolation | **PASS** | `pytest tests/test_tenant_isolation.py` 1 passed (2 warnings); cross-tenant verify rejected (it30); public token → 401 on internal endpoints (it30); HR-only injection → 422 (it30) |
| 4 | Old-module regression | **PASS** | 01B 43/43 + 21/21 · 01C (`test_01c_on01d.py`) 43/43 + carry 34/34 · 01D 48/48 (first run failed = **FIXTURE** collision `ZT01D-A` 409, not a product bug) · 01E 63/63 + UI 31/31 · 01F 79/79 · 01F concurrency 34/34 (3,000 `ZT01F-C` fixtures, 0 HTTP 5xx, 0 deadlock; fixtures dry-run → apply cleaned) |
| 5 | Browser critical flow (testing_agent_v3 iteration_30) | **PASS** | verify → draft → family → documents → review → submit → pending; master unchanged (hash); fallback, rate limit, cross-tenant |
| 6 | Expired session 1366×768 | **PASS** (retest) | see F.1 |
| 7 | 1366×768 "partial" in iteration_30 | **RESOLVED** | see F.2 |
| 8 | Performance 6k / 10k | **PASS** | see F.3 |
| 9 | Cleanup perf + ZT01G, storage orphan check | **PASS** | see F.4 |
| 10 | Restart sanity | **PASS** | see F.5 |

### F.1 Expired session at 1366×768 — PASS · earlier timeout classified **TEST**
- Earlier timeout (waiting for `public-expired`): the step after the forced expiry was **"Simpan & Lanjutkan" with no changes**. That makes no server call (a clean step change is client-only), so the app had no way to see the expiry. Reproduced: expire → Next with no edits → API calls `[]`, the UI moves to "Langkah 2 dari 6", no error, no spinner. **Classification: TEST** (the wait condition did not match the real behaviour). Product code change: **none**.
- Correct reproduction (fixture `ZT01G-U1153-E`, session expired in the backend with `ui01gb_tool.py expire`):
  - A — edit a field → "Simpan & Lanjutkan" → `PUT /draft 401` → `public-expired` visible, exact text "Sesi Anda telah berakhir. Silakan verifikasi kembali untuk melanjutkan.", **Verifikasi Ulang** button visible, token removed from sessionStorage, path stays `/public/NEP/update-data` (not the internal login), no horizontal scroll.
  - B — re-verify (the draft banner appears again) → expire → reload → `GET /form 401` → expired screen, token removed, no `kk_pef` key in localStorage, `window.posthog` undefined.
  - Backend draft before, after A and after B: `[DRAFT v2]` → unchanged. The draft was **not deleted** and **no new draft** was created.
- Screenshots: `/tmp/exp1366_A.png`, `/tmp/exp1366_B.png`. Console: only the CSP block of the Cloudflare beacon plus the expected 401 resource messages.
- Environment note: at the start of this retest the container had been recycled. `payroll-dev-mariadb` was FATAL (binary not yet available when supervisor autostarted it) and the backend startup had failed after 30 DB retries. Recovery: `supervisorctl start payroll-dev-mariadb` (existing datadir, no re-init) + one backend restart. This is classified **ENVIRONMENT**, is not related to 01G, and happened before the restart-sanity step.

### F.2 iteration_30 "1366x768 partial" — RESOLVED · **INCOMPLETE TEST COVERAGE**
- Exact reason: iteration_30 lists "RESPONSIVE - 1366x768: Desktop layout verified (**partial due to session timeout**)". No 1366 screenshot was captured (only 360 screenshots), and the scenario was not finished. No UI bug, layout issue or selector error was reported (`ui_bugs: []`, `design_issues: []`). The report's "SESSION EXPIRED" entry only confirms the helper expired 1 session. It does not confirm the UI state (now covered by F.1).
- Retest 1366×768 (full walkthrough, fixture E, no edits): verify, welcome, steps 1–6 (Data Pribadi, Keluarga, Bank & Pajak, BPJS, Dokumen, Review). All show no horizontal scroll, the CTA is visible and the form width is 736 px. The family dialog is centred (x=439, w=486, inside the viewport). Review shows Kirim disabled while REQUIRED gaps remain (correct). 0 write calls, 0 5xx. Product code change: **none**. 1366×768 = **PASS**.
- Note: iteration_30.json contains synthetic fixture NIK/DOB (test data only, now deleted). The file is untracked and must not be committed.

### F.3 Performance — PASS (actual dataset sizes)
Script `/root/tenant_tests/perf_01g.py` (staging, synthetic `ZT01G-PF-*`, tenant NEP). Latencies are measured backend-local (`127.0.0.1:8001`).

| Metric | 6k run (6,000 perf + 106 existing = **6,106** NEP employees) | 10k run (10,000 perf + 106 = **10,106**) |
|---|---|---|
| portal_resolve (seq n=100) median / p95 | 6.9 / 8.4 ms | 7.9 / 11.6 ms |
| verify_success (seq n=100) | 23.2 / 28.8 ms | 23.4 / 28.2 ms |
| verify_fail_generic (n=20) | 23.7 / 26.1 ms | 20.7 / 22.8 ms |
| prefill_form (n=100) | 79.4 / 96.7 ms | 78.0 / 92.3 ms |
| draft_write / draft_read (n=100) | 21.0/26.0 · 43.0/52.2 ms | 20.7/25.1 · 41.4/51.7 ms |
| submit (n=50 / 54) | 24.0 / 28.6 ms | 23.8 / 29.6 ms |
| pending_lookup (n=50 / 54) | 42.9 / 54.7 ms | 40.2 / 50.8 ms |
| logout (n=100) | 13.2 / 16.6 ms | 13.3 / 15.7 ms |
| **Concurrency** 25 workers, 250 full flows | 27.7 s, 59.0 req/s | 26.8 s, 60.6 req/s |
| conc verify_success (n=250) | 311.4 / 356.2 ms | 307.8 / 348.8 ms |
| conc prefill_form (n=250) | 933.7 / 1087.2 ms | 911.1 / 1077.0 ms |
| conc draft_write (n=250) · submit (n=129 / 124) | 246.3/298.5 · 285.7/332.4 ms | 239.3/285.4 · 283.7/319.8 ms |
| **Error rate (all endpoints, seq + conc)** | **0 %** | **0 %** |

- Query count per request (instrumented) is **identical at 6k and 10k** (no N+1 growth with data size): portal 2, verify 9, prefill 36 (35 SELECT), draft_write 7, draft_read 20, submit 11, pending 20, failed verify 9.
- EXPLAIN on all 108 SELECTs: **0 full scans** (>200 rows). Identity lookup: `employees ref ix_employee_number rows=1`, `companies const uq_companies_code`, `employee_update_submissions ref ix_submission_employee`.
- Non-blocking optimisation candidate: prefill makes about 35 SELECTs (fixed per request, not per data row). Under 25 concurrent workers, p95 is about 1.08 s. This is acceptable for a form open. A future improvement could batch the reference-data lookups.
- The first EXPLAIN formatter error (`'>' not supported between str and int`) was a **TEST script** issue. It was fixed and re-run.

### F.4 Cleanup (perf 6k/10k + ZT01G only) — PASS
- Script `/root/tenant_tests/cleanup_01g_final_v4.py` (ZT01G-only, chunked, default DRY-RUN). Ownership: `employee_number 'ZT01G-%' AND full_name 'ZT01G %'`, NEP/KBS, created ≥ 01G start. It asserts that no ambiguous `ZT01G-*` row exists with another name. **Not used:** `cleanup_01d.py --apply` (it resets the NEP counter) and `cleanup_01g_final_session.py` (its scope includes ZT01B–F).
- Dry-run = apply: employees **10,018** (10,000 perf + 18 UI/regression ZT01G; NEP 10,015, KBS 3), public links 1,612, submissions 1,061, submission files 7, completeness 1,071, status_history 18, family 2, master documents 1, audit_logs 3,348 (record_id = deleted entities + anonymous `public_form.*` rows labelled with a ZT01G number), public_rate_limits 116 (01G-only table; 0 rows before the final session; all rows created ≥ session start), storage objects 8 (7 `employee-submissions/` + 1 document). A second dry-run shows **0**.
- Before → after: employees 10,120 → 102 · documents 11 → 10 · completeness 1,167 → 96 · family 26 → 24 · audit 6,033 → 2,685 · 01G tables → 0 · storage 31 → 23 objects (`employee-submissions/` 7 → 0).
- Storage orphan check (both directions): DB document/submission reference without an object = **0 / 0**. Objects without a DB reference = **13, all pre-existing and unchanged** (documents 8, branding 2, logo 1, favicon 1, employees 1; mostly logo/branding referenced from company settings, not from `documents`). None are 01G, none were touched.
- Protected data: non-ZT01G baseline = **unchanged** (`ui01gb_tool.py baseline-check`: employees 102, family 24, documents 10, completeness 96, 72 tables = the baseline saved before the final UI fixtures). Counters (`company_settings.employee_id_next_number`) are **identical** before and after (NEP 82; it increased only through normal employee creation by the regression suites and was never reset). ZT01B 8 / ZT01C 5 / ZT01D 5 / ZT01DG 5 / ZT01E 43 / ZT01F 18 fixtures are **kept (out of scope)**.
- Retained on purpose: 170 anonymous `public_form.verify_failed/locked` audit rows with `record_id NULL` **and** `record_label NULL`. They cannot be linked to a fixture and contain no NIK/DOB/token. They are the audit trail.
- Note: the snapshot query for documents now uses COALESCE, because a pre-existing employee document with `owner_id NULL` caused a SQL NULL counting artifact (9 vs 10). There was no data change.

### F.5 Restart sanity — PASS
- Before: snapshot `snap_01g_final_pre_restart.json` (row counts for all 72 tables, non-ZT01G baseline per tenant, counters, migration ledger, storage).
- `supervisorctl restart backend` **exactly once** (MariaDB / S3 / frontend not restarted in this step). Result: RUNNING, clean startup log (DB connected, schema & indexes ready, pool 10/10, storage ready), 0 traceback/error, `/api/health` = `{"status":"healthy","database":"mariadb:connected","read_only":false}`.
- Env: `APP_ENV=staging`, `READ_ONLY=false`, `AUTO_SEED=false`, `ENABLE_SCHEDULER=false`.
- Migration: `python -m migrations.m0008_public_employee_form` (dry-run and `--apply`) → **`m0008_public_employee_form SKIP`** (applied on 2026-09-26 07:32:25). The ledger still has 1 m0008 row (6 rows in total) and there is no schema mutation.
- After-restart snapshot vs before: **table deltas = {}**, non-ZT01G equal, counters equal, migrations equal, storage equal. No auto-seed, no fixture came back.
- Portal smoke (preview URL, 1366, after the restart): `/public/NEP/update-data` opens without login; company "PT Nusantara Energi Prima" resolved; verify page shown; one valid verification (temporary synthetic `ZT01G-PF-00000`) → welcome; session only in sessionStorage (localStorage empty); no internal `/auth` or `/employees` calls (outside ProtectedRoute); `window.posthog` undefined, 0 PostHog requests; Keluar → `POST /logout 200`, server session cleared, token removed. The first smoke attempt showed no `/logout` request because the script ended before the in-flight request finished (**TEST**). The re-run confirmed it.
- The smoke fixture was cleaned with v4 (dry-run → apply: 1 employee, 2 links, 1 completeness, 2 audit). The final snapshot vs pre-restart: **table deltas = {}**, counters, migrations and storage all equal.

### F.6 Known non-blocking notes
1. Session expiry is detected on the next server call (save/submit/reload/upload). A clean step change without edits does not call the server. Unsaved edits made after expiry are lost; the saved draft is safe (see B.9-2).
2. Prefill = about 35 SELECTs per request (constant, see F.3). Optimisation candidate, not a blocker.
3. The Cloudflare beacon (preview edge) is CSP-blocked on `/public/*`. Production headers must be re-checked at deploy time (separate task).
4. The 13 pre-existing storage objects without a `documents` reference (branding/logo/older documents) are not related to 01G.

### F.7 BELUM DIKERJAKAN (out of scope for 01G)
**01H HR Verification** (inbox / compare / approve / reject / request revision / apply to master) · invitation/fallback UI · payroll/attendance integration · WhatsApp/email · push / PR / merge / deploy.

---

## (History) 01G-B PUBLIC EMPLOYEE FORM UI — DONE · PASS (agent-tested)
(Kept as history. The status at the time, "01G NOT LOCKED", is replaced by the final gate above.)

- Date: 2026-09-26 · Environment: **staging** (`APP_ENV=staging`, `AUTO_SEED=false`, `READ_ONLY=false`, `ENABLE_SCHEDULER=false`, DB `hris_staging` @ 127.0.0.1, local S3 storage). No production fallback.
- Branch `feature/upgrade-01g-public-employee-form` (no checkout). HEAD `5ee1bd8` (platform auto-commit). The 01G-B changes below are **not committed by the agent**.
- **Production Changed: NO** · No push / PR / merge / deploy. All results are **agent-tested** (not yet confirmed by the user).

### B.0 Flow built (PRIMARY only, as decided)
`/public/{companyCode}/update-data` → Verification (Nomor Karyawan + NIK KTP + Tanggal Lahir) → Welcome + Kelengkapan (01F master) → **6 steps** (1 Data Pribadi [Identitas + Kontak & Alamat] · 2 Keluarga · 3 Bank & Pajak · 4 BPJS · 5 Dokumen · 6 Review) → Submit → `PENDING_HR_VERIFICATION` → "Menunggu verifikasi HR".
Invitation `/isi-data` remains **backend-only** (endpoint/schema/token/tests unchanged). There is **no** separate invitation UI and **no** mass PIN/OTP.

### B.1 Files changed (01G-B)
| File | Change |
|---|---|
| `frontend/public/index.html` | Analytics guard for **all `/public/*`** (+ `/isi-data`): route flag is set BEFORE any analytics script; `emergent-main.js` and the PostHog loader/`posthog.init` run only when NOT public; public-only CSP meta (script/connect limited to the app/backend origin) |
| `frontend/src/App.js` | `/public/:companyCode/update-data` + `/public/*` (generic "not available" page) OUTSIDE `BrandingProvider/AuthProvider/ProtectedRoute`; the internal app (providers + ProtectedRoute + Toaster) is unchanged, now wrapped as `InternalApp` on `/*` |
| `frontend/src/lib/publicFormApi.js` (new) | Separate fetch client (no HRIS token/interceptor, `credentials: omit`, `no-store`, `no-referrer`); session token ONLY in `sessionStorage` key `kk_pef_session:<CODE>`; analytics layer 2 (`enforcePublicAnalyticsOff`) |
| `frontend/src/pages/public/PublicEmployeeFormPage.jsx` (new) | Main flow: verify, welcome, stepper, draft/autosave (3 s debounce, only when something changed), resume, review, submit, pending, expired, fallback |
| `frontend/src/components/public-form/{PublicFormParts,FamilySection,DocumentsSection,ReviewSection}.jsx` (new) | Shell/branding, stepper, completeness card, fields, family cards + full-screen dialog, document upload (camera/gallery/file, replace/remove), review |
| `backend/app/routers/public_employee_form.py` | 01G-B support only (+41 lines): `_restore_masked` (resume a draft that has masked sensitive values) + `GET /public/employee-form/portal/{code}/logo` (existing tenant logo, read-only, public) + `has_logo`. No refactor of 01G-A or 01B–01F |

Not touched: `.env`, `.env.example`, `backend/.env.example` (inherited changes kept as they were), 01B–01F modules, migrations (no schema change: 72 tables, m0008 unchanged).

### B.2 Analytics `/public/*` — DONE · PASS
- **How public routes are detected:** inline script in `<head>`: `window.__KK_PUBLIC_FORM__ = /^\/(public|isi-data)(\/|$)/i.test(location.pathname)`. It runs **before** any analytics script. This covers every `/public/*` path, not only `update-data`. Internal routes such as `/public-holiday` or `/employees/public` do NOT match.
- **Layer 1 (primary):** on public routes, `emergent-main.js` is not written and the PostHog loader + `posthog.init` do not run. PostHog is **never loaded or initialised** (this is not "load, then opt out").
- **Layer 1b:** a CSP meta is added only on public routes. It blocks third-party scripts/beacons injected outside the app source. Proof: the Cloudflare Insights beacon (injected by the preview edge) was blocked by CSP.
- **Layer 2:** `enforcePublicAnalyticsOff()` on mount. If a PostHog instance already exists (for example after SPA navigation from an internal page), it calls `opt_out_capturing()` + `stopSessionRecording()`. If the document was loaded on an internal route, it does a full reload so `index.html` decides again, before the user types anything. Proof: after SPA navigation from `/login` to `/public/NEP/update-data`, `window.posthog` is `undefined`.
- **Evidence:** static check `test_01gb_analytics_static.py` **9/9 PASS**. Browser: on `/public/*`, **0** requests to `ap.emergent.sh` / `assets.emergent.sh` / `*.posthog.com`, and `window.posthog` stays `undefined` through verify, failed verify, step changes, draft save, upload, review and submit (testing_agent_v3 iteration 28 + 29 + screenshot tool). The Cloudflare beacon appears only as a **CSP-blocked** attempt.
- **Internal routes are not affected:** on `/login`, `window.posthog` is an object and there are 7–8 requests to `ap.emergent.sh` (config, flags, recorder…). There is no CSP on internal routes.
- Not sent to analytics: NIK, DOB, bank account number, NPWP, BPJS, public session token, invitation token, form/draft values, document metadata.
- Note: the **Emergent dev overlay** (`/__emergent_overlay__/recorder.js`, rrweb with `maskAllInputs: true`, in-memory buffer, same-origin) is injected by the **preview dev server only** (`craco` `isDevServer`). It is not part of the production build and is not PostHog. It was not disabled because that would change platform tooling for the whole preview.

### B.3 Frontend review (endpoint · token · logging · data-testid) — DONE · PASS
- Endpoints used (all under `/api/public/employee-form`): `GET /portal/{code}`, `GET /portal/{code}/logo`, `POST /portal/{code}/verify`, `GET /form`, `PUT /draft`, `POST /submit`, `POST /attachments`, `DELETE /attachments/{id}`, `POST /logout`. No internal/HR endpoint, no hardcoded tenant/company ID (`:companyCode` = existing public `companies.code`). The unused invitation calls were removed from the UI client.
- Error handling: 400 (generic verify failure), 401 (expired → expired screen + token removed), 404 (portal not available), 409 (already submitted), 422 (field errors / `rejected_fields` / file errors), 429 (friendly message, no thresholds).
- Token: stored only in `sessionStorage` (`kk_pef_session:NEP`). Not in localStorage, cookies, URL, query or hash. Removed on expiry, logout and after submit. Internal HRIS auth keys (localStorage) are untouched.
- `console.*` / debug dump in 01G-B files: **none** (grep). Browser console has no NIK/DOB/bank/token values (testing agent).
- data-testid: semantic and stable (`public-verify-*`, `public-step-counter`, `public-section-*`, `public-next-button`, `public-completeness-*`, `public-family-*`, `public-doc-*`, `public-review-*`, `public-submit-button`, `public-submitted`, `public-pending(-text)`, `public-expired`, `public-reverify-button`, …).
- The UI only renders fields from the backend `EDITABLE_FIELDS` whitelist. The backend whitelist stays authoritative (injection test below).
- Fixes made during review: 7 steps reduced to **6** as specified; the fallback text now exactly matches the specification; the friendly 429 message; select fields whose master value is not a valid option now show the "Pilih" placeholder; step navigation scrolls straight to the top; the step % indicator was removed so it is not confused with the Kelengkapan %; "Ganti" document = upload the new file, then remove the old pending file.

### B.4 Route + compile — DONE · PASS
esbuild bundle **PASS**, webpack "Compiled successfully". `/login` and `/employees` still go through ProtectedRoute (redirect to `/login` when not logged in).

### B.5 Browser / UI test results
Fixtures: synthetic ZT01G employees, tenant NEP (+1 KBS) — A, B (already PENDING), E, L, N (no NIK), D (no DOB), X (KBS, same number as A).

| # | Scenario | Result | Source |
|---|---|---|---|
| 1 | Portal opens without login; branding (name + logo); unknown code → generic message; `/public/foo` → "not available"; internal routes stay protected | PASS | it28 |
| 2 | Verification success → welcome + 01F master completeness; token only in sessionStorage | PASS | it28 + screenshot |
| 3 | Wrong number / NIK / DOB → identical generic message; client-side NIK validation | PASS | it28 |
| 4 | Rate limit: friendly message, no thresholds; correct data refused while locked | PASS | it29 |
| 5 | Fallback: no NIK / no DOB → after ≥2 failures "Data Anda belum dapat diverifikasi melalui form ini. Silakan hubungi HR/Admin Site." (field not revealed, no bypass) | PASS | it28 + it29 |
| 6 | 6 steps "Langkah X dari 6"; HR-only fields do not appear | PASS | it28 |
| 7 | Draft save "Tersimpan", debounced autosave, master unchanged | PASS | it29 |
| 8 | Resume after reload; session expiry → "Sesi Anda telah berakhir…" + Verifikasi Ulang, token removed, backend draft kept (1 DRAFT), values back after re-verify; reload with expired token → expired screen | PASS | it29 + screenshot (agent) |
| 9 | Family: cards, full-screen dialog on mobile, add / edit / remove-undo, persists; master family unchanged | PASS | it28 + it29 |
| 10 | Documents: invalid extension, oversized, spoofed MIME (server), valid upload, replace (1 row), remove; master documents unchanged | PASS | it29 |
| 11 | Review: REQUIRED blocks + "Lengkapi sekarang", RECOMMENDED does not block, declaration checkbox, submit disabled until valid | PASS | it29 |
| 12 | Submit → `PENDING_HR_VERIFICATION`; master_hash / family / documents / 01F score **identical** before and after | PASS | it29 + helper |
| 13 | Pending: "Data Anda sudah dikirim pada [tanggal]. Saat ini sedang menunggu verifikasi HR.", read-only, no second draft | PASS | it28 + it29 |
| 14 | Tenant isolation: A on KBS → rejected; X on NEP → rejected; X on KBS → only X (KBS) | PASS | it28 + curl |
| 15 | Public token on internal endpoints (`/api/employees`, `/api/auth/me`, `/api/companies/current`, `/api/employees/{id}`) → 401; logout → token invalid | PASS | curl (agent) |
| 16 | HR-only injection (`employment_status_id`, `position_id`, `basic_salary`, `ptkp_status`) → 422 `rejected_fields`, master unchanged | PASS | curl (agent) |
| 17 | Analytics off on all public actions; still on for internal routes | PASS | it28 + it29 + screenshot |
| 18 | Sensitive data not in console/URL | PASS | it28 + it29 |

testing_agent_v3: iteration_28 — 20 passed, 0 fail (6 scenarios skipped → re-run); iteration_29 — 7 required scenarios: 6 PASS + 1 PARTIAL (session expiry: the agent re-verified instead of triggering a 401). The main agent then re-tested expiry directly: **PASS**. Total: **18/18 scenarios PASS, 0 FAIL, 0 SKIP**. No product bug found; the testing agent changed no files.

### B.6 Responsive QA — PASS
| Viewport | Verify | Welcome | Data Pribadi | Family dialog | Dokumen | Review | Horizontal scroll |
|---|---|---|---|---|---|---|---|
| 360×740 | PASS | PASS | PASS (CTA visible) | PASS full-screen, "Simpan" visible | PASS | PASS | none |
| 390×844 | PASS | PASS | PASS | PASS | PASS | PASS | none |
| 430×932 | PASS | PASS | PASS | PASS full-screen | PASS | PASS | none |
| 768×1024 | PASS | PASS | PASS | PASS centred, inside the viewport | PASS | PASS | none |
| 1366×768 | PASS | PASS | PASS | PASS centred | PASS | PASS | none |
Screenshots (screenshot tool, agent): verify, welcome, Data Pribadi, Keluarga + dialog, Dokumen, Review, Sesi berakhir, Pending/Submitted (testing agent).

### B.7 Backend regression (after 01G-B, 2026-09-26 11:26)
| Suite | Result |
|---|---|
| `test_01g.py` (main) | **77/77 PASS** |
| `test_01g_security.py` | **35/35 PASS** |
| `test_01g_portal.py` (primary portal) | **59/59 PASS** |
| `tests/test_tenant_isolation.py` | **1 passed**, 2 warnings |
| ruff (F, E9, B006, B904) router + core | All checks passed; `py_compile` OK |
| Analytics static check | **9/9 PASS** |
Raw tokens in test logs: 0. 01C (43/43) and 01F (79/79) were not re-run: 01G-B only changes the public UI and the public router (logo/masked restore). The latest evidence is from 01G-A.

### B.8 Cleanup ZT01G — DONE (dry-run → apply)
- Dry-run: 18 ZT01G employees (NEP 15, KBS 3: UI fixtures + fixtures from the backend suite reruns) + 35 links, 8 submissions, 8 pending files, 18 status_history, 18 completeness snapshots, 2 family, 1 master document (owned by a ZT01G employee), 123 audit rows (record_id = ZT01G entities), 34 rate-limit rows, 9 storage objects. Ownership: `employee_number 'ZT01G-%' AND full_name 'ZT01G %'`, created after 01G-A started, NEP/KBS only.
- Apply → a second dry-run shows **0**. 01G tables (links / submissions / files / rate limits) = **0**; `employee-submissions/` objects = **0**.
- Baseline (non-ZT01G): employees 71, family 19, documents 8, completeness 69, schema 72 tables → **unchanged**. NEP 66 / KBS 3 employees (equal to before the UI fixtures). Counter not reset. Health OK.
- Retained (not provably owned by a ZT01G entity): **141** `public_form.verify_failed/locked` audit rows with `record_id NULL` (failed attempts against employee numbers that do not exist, from 01G-A + 01G-B; 29 of them from this session). They contain no NIK/DOB/token. Kept as the audit trail, same practice as 01G-A.
- Helper note: `ui01gb_tool.py baseline-check` once showed documents 7 vs 8 before apply. This was a SQL NULL artifact (a pre-existing employee document with `owner_id NULL`), not a data change. The query now uses COALESCE, and the result after cleanup is `unchanged: True`.
- Test helpers (outside the repo): `/root/tenant_tests/ui01gb_fixture.py`, `ui01gb_tool.py`, `test_01gb_analytics_static.py`, `state_01gb_ui.json`.

### B.9 Known limitations
1. NIK/DOB fallback = generic message only (as decided). An exception invitation UI is **BELUM DIKERJAKAN** (needs a decision).
2. Unsaved edits (not yet autosaved) are lost when the session expires. The saved draft is safe.
3. On the welcome screen, "Lokasi kerja / site" only appears when the master has `work_location`.
4. Radix Select: when the master value is not a valid option (e.g. an old code), the field shows "Pilih" and is marked as needing completion (following 01F).
5. The Cloudflare beacon is injected by the preview edge (outside the source code). On public routes it is blocked by CSP. Production must be re-checked at deploy time (separate task).
6. Dev overlay rrweb (preview only) — see B.2.
7. Final performance/load test (5,000–6,000 employees) is **BELUM DIKERJAKAN**. The portal design does not need per-employee links.

### B.10 BELUM DIKERJAKAN
Final performance/load 01G · final verification/LOCK 01G · UI for the fallback/invitation exception · **01H HR Verification** (inbox/compare/approve/reject/apply-to-master) · push/PR/merge/deploy (not done).

---

# (History) Progress Report 01G-A (Backend Foundation + Adjustment: Public Portal)

## **01G-A BACKEND — READY FOR 01G-B UI**
The primary flow (Public Portal + Nomor Karyawan + NIK + Tanggal Lahir) and the optional flow (invitation) are implemented and **all agent-tested suites PASS**.
**01G is NOT fully complete**: 01G-B (public mobile UI), visual QA, full performance/load, final testing_agent_v3, final verification/LOCK, and 01H are still **BELUM DIKERJAKAN**.

- Date: 2026-09-26 · Environment: **staging** (`APP_ENV=staging`, DB `127.0.0.1:3306/hris_staging`, storage `s3-staging-local`, `AUTO_SEED=false`, `READ_ONLY=false`, `ENABLE_SCHEDULER=false`)
- Branch: `feature/upgrade-01g-public-employee-form` (local). Latest commit `0de261d` (platform auto-commit of the first 01G-A checkpoint). Adjustment changes (`public_form.py`, `public_employee_form.py`, this report, plan.md) are not yet committed by the agent.
- **Production Changed: NO** · No push / PR / merge / deploy.
- All results are **agent-tested** (not yet user-confirmed).

Status legend: **DONE** (built) · **PASS** (tested, passed) · **FAIL** (tested, failed) · **BELUM DIKERJAKAN** (not done yet).

---

## 0. Official 01G flow (after the adjustment)

| Flow | Path | Status |
|---|---|---|
| **PRIMARY** | Public Portal per tenant → Nomor Karyawan + NIK KTP + Tanggal Lahir → limited public session → Draft → Submit → `PENDING_HR_VERIFICATION` | DONE · PASS |
| **OPTIONAL / EXCEPTION** | Unique HR invitation/link (existing 01G-A infrastructure, not removed) → same 3-factor verification → same session | DONE · PASS (unchanged) |
| **Fallback** for employees without NIK/DOB | Design only (§5); standard verification is **safely rejected**; flagged `needs_fallback` for HR | Implementation **BELUM DIKERJAKAN** (pending decision) |

HR no longer has to create a link for every employee. HR shares **one portal address per company**.

## 1. Summary

| Area | Status |
|---|---|
| Public portal + tenant resolve (company code) | DONE · PASS |
| Primary identity verification (3 factors) | DONE · PASS |
| Rate limit / brute force (per target + per IP + per link) | DONE · PASS |
| Public session (portal & invitation) | DONE · PASS |
| Invitation = optional flow | DONE · PASS (behaviour unchanged) |
| Employees without NIK/DOB (safe rejection + `needs_fallback` flag) | DONE · PASS · fallback implementation BELUM DIKERJAKAN |
| Whitelist / prefill / draft / submit / 1 pending / attachments | DONE · PASS (unchanged, re-tested via portal) |
| No master mutation before 01H · 01F snapshot unchanged | PASS |
| Audit / log safety | DONE · PASS |
| Migration/schema | **No schema change & no new migration** for the adjustment (m0008 stays as-is: ledger 1x, SKIP) |
| Tenant isolation · RBAC/auth/documents | PASS |
| Regression 01C · 01F | PASS |
| Cleanup (ZT01G + scoped 01C) | DONE |
| 01G-B UI, visual QA, full perf/load, final testing_agent_v3, final verification/LOCK, 01H | **BELUM DIKERJAKAN** |

No outstanding **FAIL**. All interim failures during testing were classified as **TEST ISSUE** and fixed in the tests (§14).

---

## 2. Changed files

| File | Status | Contents |
|---|---|---|
| `backend/migrations/m0008_public_employee_form.py` | committed (0de261d) | Additive migration (4 tables) — **not changed** by the adjustment |
| `backend/app/core/db.py` | committed (0de261d) | 4 table definitions — **not changed** by the adjustment |
| `backend/server.py` | committed (0de261d) | Router wiring — **not changed** by the adjustment |
| `backend/app/core/public_form.py` | modified (+52/-12) | `MODE_PORTAL`, target lock (tenant + Nomor Karyawan), generic rate-limit helpers (`rate_locked`, `record_failure`, `rate_reset`), `norm_company_code`, `portal_path`; the IP wrapper keeps the same behaviour |
| `backend/app/routers/public_employee_form.py` | modified (+138) | Portal endpoints, HR readiness endpoint, the HR invitation list excludes portal session rows, docstring for the official flow |
| `plan.md`, this report | modified | Documentation |

Not ours / not committed: `.env.example`, `backend/.env.example`. The frontend is **not touched**.
Test tooling (outside the repo, `/root/tenant_tests/`): `test_01g.py`, `test_01g_security.py`, **new** `test_01g_portal.py`, `cleanup_01g.py` (v3), `cleanup_01c_scoped_01g.py`.

## 3. Public portal — DONE · PASS
- Endpoints (unauthenticated, headers `Cache-Control: no-store`, `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`):
  - `GET  /api/public/employee-form/portal/{company_code}` → `{flow: "PORTAL", company: {name, code}, verification_fields}`
  - `POST /api/public/employee-form/portal/{company_code}/verify` → body `{employee_number, nik, birth_date}` → limited session
- **Company resolve reuses the existing mechanism**: `companies.code` — globally unique (`uq_companies_code`), pattern `^[A-Za-z0-9_-]{2,20}$`, stored in uppercase, **immutable** (`TenantUpdate` rejects code changes with 400). There is no separate slug column and **no new architecture/schema** was added.
- The URL contains **no internal tenant/company ID**. Portal frontend path (for 01G-B): **`/public/{CODE}/update-data`** (e.g. `/public/NEP/update-data`, `/public/REAL/update-data`), available to HR via `portal_path`.
- Unknown code / invalid format / internal UUID / tenant inactive or expired (`tenant_block_reason`) → **404 with an identical generic message**: "Portal pembaruan data tidak tersedia. Silakan hubungi HR perusahaan Anda." Failed resolves count toward the IP limit (anti-enumeration).
- Case-insensitive code (`nep` = `NEP`).
- Tests: P01–P06 PASS.

## 4. Primary identity verification — DONE · PASS
- Nomor Karyawan + NIK KTP + Tanggal Lahir must **all** match **the same active employee in the resolved tenant** (`employees` query scoped to `company_id` + `employee_number` + `status=active`; comparison without short-circuit, `hmac.compare_digest`). Success only if **exactly one** employee matches.
- Lenient normalization: lowercase/spaces in Nomor Karyawan, spaces in NIK, dates `YYYY-MM-DD` / `DD-MM-YYYY`.
- Every failure (wrong number, wrong NIK, wrong DOB, number not found, employee data incomplete) → **HTTP 400 with an identical body**: "Data verifikasi belum sesuai. Silakan periksa kembali data yang Anda masukkan." It never says which factor was wrong. When the number is not found, a dummy comparison is run so response times stay similar.
- Cross-tenant: identical Nomor Karyawan in NEP & KBS → NEP portal + KBS employee data is rejected (and vice versa); each portal only produces a session for its own tenant's employee.
- Tests: V01–V07, X01–X04 PASS.

## 5. Employees with incomplete NIK/DOB — DONE (safe rejection) · fallback BELUM DIKERJAKAN
- Standard verification for employees without NIK (16 digits) / without DOB → **rejected with the generic message** (whatever values are entered), **no session is created**.
- **Internal flag (not visible publicly):** audit `public_form.verify_failed` records `needs_fallback: true` when the Nomor Karyawan matches an employee whose verification data is incomplete.
- **New HR endpoint:** `GET /api/employees/public-form/readiness` (RBAC `employee:view`, no new permission) → `portal_path`, `total_active`, `ready`, `needs_fallback`, and a list of employees needing a fallback + the missing data. **No NIK/DOB values are included**.
- **No link-only bypass:** creating an invitation for these employees is still **422** + list of missing data. There are **no mass PINs**.
- **Proposed fallback design (not implemented, pending decision):** reuse the existing invitation infrastructure **only for exception employees** — HR creates an invitation with a special verification mode (e.g. `HR_ASSISTED`) + a second factor delivered separately by HR (one-time code per exception employee, short-lived, hash-only, same lock/audit). No schema rewrite is needed (the `verification_mode` column already exists). Preferred alternative: HR completes NIK/DOB in Profile 360 so the employee can use the portal normally.
- Tests: N01–N08 PASS.

## 6. Rate limit / brute force — DONE · PASS
| Layer | Rule | Storage |
|---|---|---|
| Per target (portal) | tenant + Nomor Karyawan being tried: 5 failures / 15 minutes → locked 15 minutes (429, even when the data is correct). Applies **the same whether or not the number exists** (anti-enumeration). Counter reset after success. | `public_rate_limits` scope `verify_target`, key = SHA-256 (tenant + number), **no raw values** |
| Per IP (portal + invitation) | 20 failures / 15 minutes → locked 15 minutes (verify & portal resolve) | `public_rate_limits` scope `verify_ip`, key = IP hash |
| Per link (invitation) | 5 failures → locked 15 minutes (unchanged) | `employee_public_links` |
- DB-backed & atomic (upsert), consistent across processes; the lock is always temporary. The 429 message contains no thresholds/durations. The same number in another tenant is not affected.
- Audit `public_form.locked` (channel PORTAL) without input values.
- Tests: R01–R10 (portal), B05–B11 (invitation) PASS.

## 7. Public session — DONE · PASS
- Portal: an opaque 256-bit token; the session row reuses `employee_public_links` with `verification_mode='PORTAL_3F'`, **`token_hash = NULL`** (there is no invitation token, so it cannot be "opened" as a link), and only `session_hash` stored. Idle 30 minutes, absolute 2 hours, checked **on every request** (tenant blocked / employee inactive → 401).
- **One active portal session per employee**: re-verifying invalidates the previous portal session immediately. Invitation sessions are a separate channel.
- The session only accesses the **verified employee**. It cannot be used on internal HR endpoints (`/auth/me`, `/employees`, `/documents`, `/audit-logs`, invitations, readiness, `/completeness/summary`), cannot write through internal endpoints, and cannot be exchanged for an internal JWT.
- Portal session rows **do not appear** as invitations in the HR list/history, and are not revoked when HR creates an exception invitation.
- Re-verifying while a submission is pending → session status `SUBMITTED`, form `mode: READ_ONLY`.
- Tests: S01–S06, M05, U01–U11, L01–L02 PASS.

## 8. Invitation = OPTIONAL / EXCEPTION flow — DONE · PASS (unchanged)
- The infrastructure is **not removed** and there is **no schema rewrite**: create/status/revoke/regenerate, 256-bit token (hash-only), URL fragment `/isi-data#…`, 3-factor verification, per-link lock — behaviour is identical to the first 01G-A checkpoint (`test_01g.py` 77/77).
- Cross-channel: a draft saved through an invitation session is visible in the portal session (1 draft/pending per employee, `open_slot`).
- Tests: I01–I04 + the full `test_01g.py` PASS.

## 9. Existing behaviour after a session is established — PASS (re-tested via portal)
- Prefill (masked), employee-editable whitelist, HR-only fields → 422, draft versioning, private pending attachments, submit → `PENDING_HR_VERIFICATION` (`source = PUBLIC_EMPLOYEE_FORM`, `link_id` = portal session row), **one active pending submission** (draft/submit/upload after that → 409; HR cannot create an invitation while pending → 409).
- **No master mutation before 01H**: master employee, family, and documents identical after draft + attachment + submit via the portal.
- **01F completeness master unchanged** by draft/submit (identical snapshot).
- Tests: M01–M09 + C/D/E/G series in `test_01g.py` PASS.

## 10. Audit / log safety — DONE · PASS
- Events: `public_form.verify_success` / `verify_failed` / `locked` with `channel: "PORTAL"` (+ existing invitation events). No raw session/invitation token, NIK, date of birth, or form values in the audit, the `employee_public_links` table, or the backend log (checked against the actual values used in the tests).
- The access log contains only `/portal/{CODE}/verify` (company code) — verification data is in the body, not the URL.
- Test log hygiene: one interim test run printed a fixture session token in a local test log file (`/root/tenant_tests/g01_portal_run2.log`) through a FAIL message → the log was **redacted** immediately, the fixture session was **invalidated/deleted** by cleanup, and the test now **auto-redacts** tokens in every output (run 3 & 4: 0 tokens). This did not come from product code.
- Tests: A01–A05, S01–S03, I01–I04 (test_01g) PASS.

## 11. Analytics / PostHog — requirement for 01G-B (backend: no analytics)
- The backend sends nothing to analytics. The primary flow has **no token in the URL** (session token in memory/Authorization header only; the portal path contains only the company code).
- **Mandatory 01G-B requirement** (frontend, not built yet): `frontend/public/index.html` initialises PostHog with **`session_recording`** (rrweb) + autocapture, and loads `emergent-main.js`, on every route. Across **all** public employee form routes (`/public/*`, `/isi-data`):
  - PostHog must **not be initialised** (or `opt_out_capturing()` + `stopSessionRecording()` before the page renders) — no pageviews, autocapture, or session recording;
  - no NIK/DOB/form values/session token may be sent to analytics/console/URL/localStorage;
  - sensitive inputs are marked `ph-no-capture` / `data-private` as a second layer.

## 12. Migration / schema — DONE · PASS (no change for the adjustment)
- The adjustment requires **no schema change and no new migration**: portal sessions reuse `employee_public_links` (`verification_mode`, nullable `token_hash`), target locks reuse `public_rate_limits` (`scope` column). Tables stay at 72, ledger 6 migrations.
- m0008 (from the first checkpoint): runner DRY-RUN/`--apply`/rerun = SKIP, ledger exactly 1 row, fingerprint identical, 0 duplicate permissions, columns = ORM. Honest note: the 4 m0008 tables had already been created by the startup schema sync (`create_all(checkfirst)`) before m0008 recorded the ledger.

## 13. Tenant isolation · RBAC · auth · documents — PASS
- `pytest /app/backend/tests/test_tenant_isolation.py` → **1 passed** (12/12 sub-checks).
- Portal cross-tenant X01–X04, invitation cross-tenant A08/F01–F04/R04 PASS.
- `test_01g_security.py` **35/35** (RBAC invitation endpoints, internal auth vs public session, pending attachments same/cross-tenant, master documents not overwritten, MIME/extension/size, private storage).
- Readiness RBAC: `employee:view` 200, no permission 403, no auth 401 (N06).

## 14. Test results (agent-tested, 2026-09-26, after the adjustment)
| Suite | Result |
|---|---|
| `test_01g_portal.py` (new, portal) | **59/59 PASS** (run 093050) |
| `test_01g.py` (full 01G, invitation flow + session/draft/submit/attachments) | **77/77 PASS** (run 093124) |
| `test_01g_security.py` | **35/35 PASS** (run 093131) |
| `pytest test_tenant_isolation.py` | **1 passed (12/12)** |
| 01C `test_01c_on01d.py` (targeted Profile 360) | **43/43 PASS** |
| 01F `test_01f.py` (01F integration gate) | **79/79 PASS** (run 093140) |
| 01G ↔ 01F integration (C08/D10/G04 + portal M03) | PASS |
| 01B, 01D, 01E, 01F concurrency | not rerun after the adjustment (01E 63/63 & tenant regression 134/134 PASS after the first 01G-A; the adjustment does not touch those code paths) |

Interim portal test failures (all **TEST ISSUE**, not product):
1. Run 1 (51/59 + crash): the test's main IP exceeded the IP limit of 20 failures (including 4 failed portal resolves, which count by design) → subsequent 429s. This was **correct product behaviour**; the test was fixed to use a separate IP per test group.
2. Run 2 (53/59): the test used relationship `"spouse"` (valid key: `ISTRI`) → the draft was correctly rejected with 422, with knock-on failures in M04–M09.
3. Run 3 (58/59): the test read `read_only`; the existing contract is `mode: "READ_ONLY"` (the same as `test_01g.py` G07).
First checkpoint (for reference): 01C 36/43 = TEST ISSUE (old pre-01D suite variant) → 43/43 on the canonical variant.

## 15. Cleanup — DONE (scoped)
- **ZT01G** (`cleanup_01g.py` v3; ownership: employee_number `ZT01G-%` + name `ZT01G %`, NEP/KBS, created ≥ 07:30 + IPs/target numbers recorded in `state_01g_portal_<RUN>.json` (run 092727 reconstructed deterministically from the test code) + key `127.0.0.1` from the agent's manual curl checks):
  - Adjustment round (total of 4 applies): all portal/security/main 01G fixtures removed. Last apply: employees 11, links 16, submissions 5, files 4, family 1, status_history 11, completeness 11, documents 1, audit 74, rate limit 34, storage 5.
  - After: the 4 01G tables = **0 rows**, `public_rate_limits` = **0**, 0 objects under `employee-submissions/`, repeat dry-run empty.
- **01C** (`cleanup_01c_scoped_01g.py`, ownership = IDs in `state_01c.json` + run window 09:31:30–09:31:45): employees 3 + child rows, documents 1 (+1 object), audit 29 (the dry-run's 57 was double counting). Generic login audits kept.
- **Baseline**: non-ZT employees NEP 13 / KBS 3 — **unchanged** at every checkpoint. Tables 72, 6 migrations. The NEP counter is **not reset manually** (62, from normal increments).
- **BELUM DIKERJAKAN (outside scope, not touched):** 12 `ZT01F*` employees (the 01F runs at 07:43 & 09:31), 5 `ZT01E*` employees, 6 import batches, tenant regression tenants `ZTA3AU0`/`ZTB3AU0` + 3 users → final cleanup (existing scripts `cleanup_01f.py` etc. must be reviewed for scope first).

## 16. Known limitations / notes
1. **Fallback for employees without NIK/DOB — BELUM DIKERJAKAN** (design in §5, decision required). The share of employees who are currently "needs_fallback" can be checked by HR via the readiness endpoint.
2. **Shared IP / CGNAT:** employees at the same site/Wi-Fi or on a mobile operator's CGNAT share an IP. The IP limit (20 failures/15 minutes) could temporarily block other employees if there are many typos. The per-target lock is the primary control. Parameters are code constants — tune them for PT REAL before go-live if needed.
3. The company code is public (not a secret) — the portal shows the company name. Unknown codes produce an identical generic 404 + count toward the IP limit.
4. Portal session rows (`employee_public_links`, `PORTAL_3F`) accumulate one per successful verification; there is no retention/cleanup job yet (the same applies to old drafts & orphaned attachments).
5. X-Forwarded-For can be spoofed → the IP limit is a secondary layer.
6. Design deviations vs audit proposal 15.2 (from the first checkpoint): RBAC reuses `employee:view`/`employee:edit`; opaque token + hash session (not a JWT); 4 tables.
7. Link/portal delivery: HR shares the portal address manually; email/WhatsApp not integrated.
8. `token_hint` (last 4 characters of the invitation token) — negligible impact.
9. The backend log contains 18 old HTTP 500s on `/completeness/reevaluate` from before 01G (note, not a blocker).
10. MariaDB staging "change buffer is corrupted" — separate infrastructure task, not touched.
11. Test tooling: `test_01c.py` (pre-01D) is stale → use `test_01c_on01d.py`.

## 17. BELUM DIKERJAKAN
- **01G-B** public mobile UI final: portal page `/public/{CODE}/update-data` (verification, form, draft, upload, submit, read-only status), optional invitation page `/isi-data`, HR panel (portal address + readiness + invitation status) — including the §11 analytics requirement.
- **Responsive visual QA** (mobile/tablet/desktop).
- **Full performance/load** tests (including portal verification load & the shared-IP scenario).
- **Final `testing_agent_v3`** for 01G.
- **Final cleanup** (including other suites' fixtures, §15) + restart x2.
- **Final verification / LOCK 01G.**
- **01H — HR Verification** (inbox, compare, approve/reject/reopen, apply-to-master, recalculate completeness).
- Fallback verification implementation (§5) — pending a decision.

## 18. Git / environment
- Branch `feature/upgrade-01g-public-employee-form`; the platform auto-commit `0de261d` contains the first 01G-A checkpoint (not rewritten). Adjustment changes are uncommitted by the agent. Nothing staged by the agent. No reset/rebase/stash.
- No push / PR / merge / deploy. **Production Changed: NO.**

**01G-A BACKEND — READY FOR 01G-B UI. STOP — waiting for user review. 01G-B / 01H not started.**
