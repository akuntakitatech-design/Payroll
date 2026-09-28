# Tenant Foundation Final (KelolaKita — HRIS & Payroll) — Plan (STATUS UPDATE)

## 1) Objectives
- Menyelesaikan pekerjaan fitur secara **staging/preview saja** sesuai scope upgrade yang sedang aktif.
- Mengikuti alur kerja yang konsisten:
  - **Safety Gate → Coding (staging/preview) → Compile/Build → Test → Visual QA → Secret Scan → Testing Agent → Laporan → STOP**.

Batasan utama (wajib):
- **STAGING ONLY**.
- **Tidak deploy production**.
- **Tidak ubah database production**.
- **Tidak push/PR/merge/deploy** untuk upgrade yang sedang aktif, kecuali bila user instruksikan.

Batasan tambahan (untuk fase upgrade saat ini):
- **Tidak mulai 01F** (Data Completeness) atau scope beyond.
- **Tidak menghapus / memodifikasi data baseline / PT REAL / legacy / 01B–01D**.
- Semua test fixture upgrade 01E **harus prefix `ZT01E`**.
- Tenant **`ZT01B170909`**: **jangan disentuh** (catat sebagai existing test tenant di luar scope 01E-B).

### Update fokus (fase saat ini) — 2026-09-27
**Enhancement 01G — Flexible Employee Form Builder: LOCKED ✅** (see §15.4e). 01F LOCKED ✅ · 01G LOCKED ✅ · 01H LOCKED ✅ (see §16.7).  **01I — Role & Data Scope: LOCKED ✅** (see Phase 17 §17.3). Branch `feature/upgrade-01g-form-builder`. Production Changed: NO.

(Historical focus, older phases:)
1) **01C Employee Profile 360** — **COMPLETED & LOCKED**.
2) **01D Current Assignment / Penempatan Karyawan** — **COMPLETED** (agent-tested) — sebelumnya STOP menunggu review.
3) **01E Employee Migration (Excel Import)**:
   - **01E-A Backend-first checkpoint: DONE (agent-tested)**.
   - **01E-B UI & Finalization: IN PROGRESS**.

Status fase ringkas (jujur berdasarkan kondisi terkini):
- Tenant Foundation / Platform Branding / Subscription: **SELESAI**.
- Upgrade 01B: **SELESAI** (commit lokal `2198b7e`; tidak di-push).
- Upgrade 01C: **SELESAI & LOCKED** (laporan tersedia).
- Upgrade 01D: **SELESAI** (laporan tersedia).
- Upgrade 01E:
  - **Backend-first checkpoint: DONE** (commit lokal `d66bbe9`, core tests 01E `63/63` agent-tested).
  - **01E overall: NOT COMPLETE** (UI, perf, visual QA, clean regressions, testing_agent_v3, cleanup ZT01E final, restart evidence, final report).

---

## 2) Implementation Steps

### Phase 1 — Environment & Core Workflow POC (Isolation) (COMPLETED)
Core historis: “Time events + policy + approval + period lock + tenant isolation”.
- Status historis Time Management V1: **COMPLETED** (bukan fokus aktif saat ini).

---

### Phase 2 — V1 App Development (Backend) (COMPLETED)
- Status historis Time Management backend: **COMPLETED**.

---

### Phase 3 — V1 App Development (Frontend) (COMPLETED)
- Status historis Time Management frontend: **COMPLETED**.

---

### Phase 4 — Testing & Validation (agent + regression) (COMPLETED)
- Status historis Time Management testing: **COMPLETED**.

---

### Phase 5 — R2 DEVELOPMENT (Attachment) (BLOCKED — Menunggu User)
- Status historis Time Management R2 DEV: **BLOCKED**.

---

### Phase 6 — Preview + Handover + STOP (STOP — Menunggu Review User)
- Status historis Time Management preview: **IN PROGRESS**.
- Untuk tenant foundation final: **STOP** (semua output final sudah dibuat).

---

### Phase 7 — Absensi ESS (Alur Operasional Karyawan) (COMPLETED — menunggu uji & approval user)
- Status historis Absensi ESS: **COMPLETED** (development-tested; belum user-accepted).

---

### Phase 8 — Tenant Foundation (Staging Only) (COMPLETED — foundation + subscription)
Fase ini mengikuti instruksi user:
- **Hanya staging/live preview**.
- **Tidak menyentuh production**.
- **Tidak deploy**.

#### 8.1 Arsitektur & aturan (baseline)
- Tenant = baris pada tabel existing **`companies`** (reuse).
- Membership/role per tenant = tabel existing **`user_company_roles`**.
- **Platform Admin** = role global `super_admin` (membership `company_id = NULL`).
- **Tenant Admin** = role sistem `tenant_admin` (scope company/tenant).
- Soft-disable tenant menggunakan `companies.status = inactive`.

#### 8.2 Backend — Tenant Foundation Minimal
- Router platform: `/api/platform/tenants`.
- Guard platform & tenant.

#### 8.3 Migration
- `backend/migrations/m0001_tenant_foundation.py`.

#### 8.4 Frontend
- Menu platform: Platform → Tenant Management.

#### 8.5 Test plan
- Test 1–7 tenant foundation: **PASS**.

---

### Phase 8b — Tenant Subscription / Expiry (COMPLETED — agent-tested)
- Migration: `backend/migrations/m0002_tenant_subscription.py`.
- Guard expired + banner.
- Test 8–14: **PASS**.

---

### Phase 9 — FINAL TASK: Tenant Foundation UI, Platform Branding & Tenant Branding (Staging Only) (COMPLETED — agent-tested)
- Runtime safety gate: **DONE**.
- Platform branding configurable: **DONE**.
- Login UI 2 kolom: **DONE**.
- Platform shell (dashboard/registry/detail): **DONE**.
- Tenant provisioning wizard: **DONE**.
- Password sementara enforcement + reset password: **DONE**.
- Tenant logo upload: **DONE**.
- Regression + Visual QA + Secret scan + Testing agent + report: **DONE**.

Catatan:
- PR Tenant Foundation sudah dibuat: **PR #12** (branch `feature/tenant-foundation-minimal`), status open.
- Data buatan user di preview terkait branding dibiarkan sesuai keputusan user (bukan dihapus oleh agent).

---

### Phase 10 — Upgrade 01B: Master Status Karyawan + Status History (Staging Only) (COMPLETED — menunggu review user)
Fase ini **terpisah** dari PR Tenant Foundation dan **berjalan di branch lokal**.

#### 10.1 Branching / commit policy (01B)
- Commit final 01B dibuat **lokal saja**:
  - commit: `2198b7e`
  - message: `Upgrade 01B (Master Status Karyawan + Riwayat Status): selesai diuji, berhenti untuk review Anda`
- Tidak ada push/PR/merge/deploy.
- Perubahan `.env.example` dan `backend/.env.example` **tetap sebagai working tree changes** dan **dikecualikan** dari commit sampai ada instruksi eksplisit.

#### 10.2 Runtime safety gate (WAJIB)
Verifikasi environment aman sebelum coding/testing:
- DB: `hris_staging` @ `127.0.0.1:3306`.
- `AUTO_SEED=false`.
- Storage: endpoint staging lokal.

**Status: PASS**.

---

### Phase 11 — Upgrade 01C: Employee Profile 360 (Staging Only) (**COMPLETED & LOCKED**)
Ringkas:
- Profile 360 11 tab + family repeatable + foto profil tenant-aware + masking sensitif.
- Laporan: `/app/UPGRADE_01C_EMPLOYEE_PROFILE_360_REPORT.md`.

**Status fase 01C: COMPLETED & LOCKED.**

---

### Phase 12 — Upgrade 01D: Current Assignment / Penempatan Karyawan (Staging Only) (**COMPLETED — agent-tested**)
Ringkas:
- `employee_assignments` tenant-safe, max 1 ACTIVE, legacy bridge `employees.project_id`.
- Laporan: `/app/UPGRADE_01D_CURRENT_ASSIGNMENT_REPORT.md`.

**Status fase 01D: COMPLETED (agent-tested) — menunggu review user.**

---

### Phase 13 — Upgrade 01E: Employee Migration (Excel Import) (Staging Only)

#### 13.1 Permanent constraints (01E)
- **Staging only**; tidak ada akses/ubah production DB atau production storage.
- **Tidak push/PR/merge/deploy**.
- **Tidak mulai 01F**.
- Endpoint import lama **harus dipertahankan**.
- **Blank cell tidak boleh overwrite** nilai DB yang sudah nonblank.
- **NIK collision** dengan employee lain → **CONFLICT**.
- **Commit harus eksplisit** (setelah upload/analyze/preview).
- Commit **per employee** dalam transaksi terpisah; partial batch success diperbolehkan.
- Integrasi wajib:
  - status bisnis via **01B workflow/service**
  - assignment/placement via **01D assignment service/aturan**
- Family: matching aman + rerun tidak menduplikasi; jika identitas tidak pasti → warning/review.
- Sensitif (rekening/NPWP/BPJS/NIK): tidak bocor ke log/audit/preview tanpa kebutuhan.

#### 13.2 Runtime safety gate (WAJIB sebelum kerja 01E)
- DB: `hris_staging` @ `127.0.0.1`.
- `AUTO_SEED=false`.
- Storage: `s3-staging-local`.

**Status: DONE (PASS, agent-tested).**

---

## 13.A — Upgrade 01E-A: Backend-first checkpoint (DONE)
**Status bucket:**
- DONE: ✅
- IN PROGRESS: —
- TODO: —
- BLOCKED: —

**Checkpoint evidence (agent-tested):**
- Commit lokal: `d66bbe9` (01E backend checkpoint).
- Test suite: `/root/tenant_tests/test_01e.py` **63/63 PASS**.

**Endpoint kontrak backend 01E (existing + digunakan UI):**
Semua endpoint **tenant-scoped** (company_id dari token) dan require permission **`employee:import`**.
- `GET  /api/employee-import/template`
- `GET  /api/employee-import/mapping`
- `POST /api/employee-import/batches` (multipart `file`) → `201` → `{ batch, duplicate_committed_batch? }`
- `GET  /api/employee-import/batches?page=&limit=`
- `GET  /api/employee-import/batches/{id}`
- `GET  /api/employee-import/batches/{id}/rows?row_class=&commit_status=&q=&page=&limit=`
- `POST /api/employee-import/batches/{id}/cancel` (hanya jika `ANALYZED`, selain itu `409`)
- `POST /api/employee-import/batches/{id}/commit` (multipart `file` + `confirm_duplicate`)
  - `409` bila hash mismatch / duplicate committed tanpa confirm / status batch bukan `ANALYZED`.
  - Cross-tenant batch: **404/denied**.

---

## 13.B — Upgrade 01E-B: UI & Finalization (IN PROGRESS)
Fase ini menyelesaikan UI end-to-end + finalization gates. **Jangan menandai 01E complete** sebelum seluruh 01E-B selesai dan direview.

### 13.B.0 Review hasil awal (DONE)
**Scope review yang diwajibkan user:** page UI baru + kontrak endpoint + git diff.

**Hasil temuan review (jujur):**

**(1) Git diff sejak checkpoint `d66bbe9`:**
- **UNTRACKED:** `frontend/src/pages/EmployeeMigrationPage.jsx` (halaman UI baru).
- **MODIFIED (backend additive, belum di-commit):**
  - `backend/app/core/employee_import.py`
  - `backend/app/routers/employee_import.py`
  - Perubahan ini bersifat **additive untuk kebutuhan UI**:
    - Penambahan `field` pada item error/warning (agar output download validasi memenuhi kolom “Field”).
    - Penambahan parameter query `q` untuk pencarian pada preview rows.
    - Endpoint download hasil validasi: `GET /api/employee-import/batches/{id}/validation-result` + builder Excel `build_validation_result()`.
- **MODIFIED (HARUS DI-EXCLUDE dari commit):**
  - `.env.example` dan `backend/.env.example` (perubahan dokumentasi `AUTO_SEED=false`).

**Catatan wajib:** `.env.example` dan `backend/.env.example` tetap **excluded** dari commit 01E-B sesuai guardrails.

**(2) Inventaris UI baru yang sudah ada (belum terintegrasi routing):**
File: `frontend/src/pages/EmployeeMigrationPage.jsx` (untracked).
- Stepper flow: **Unduh template → Unggah file → Analisis & validasi → Preview → Commit**.
- Download template via `/employee-import/template`.
- Upload/analyze via `POST /employee-import/batches`.
- Batch detail:
  - status badge batch
  - counts per klasifikasi (NEW/UPDATE/UNCHANGED/CONFLICT/ERROR)
  - preview table dengan:
    - nomor karyawan, nama
    - badge klasifikasi
    - daftar perubahan (diff old→new)
    - errors + warnings + commit_error
    - status commit per baris
  - download hasil validasi via `/employee-import/batches/{id}/validation-result`
  - commit dialog:
    - wajib re-select file
    - ack untuk duplicate hash (berdasarkan warnings batch)
    - kirim `confirm_duplicate` sesuai ack
- Tab Riwayat:
  - list batch (filename, waktu upload/uploader, status, counts, commit summary)
  - open detail batch.
- RBAC UI: gate `can("employee","import")`.

**(3) Gap terhadap requirement 01E-B (masih harus dikerjakan):**
- Routing/wiring:
  - Belum di-wire ke `App.js` (masih route `/employees/import` → `EmployeeImportPage`).
  - Tombol di `EmployeesPage` masih navigasi ke `/employees/import`.
  - Harus menghindari duplikasi flow lama bila bisa reuse route existing.
- Read-only history:
  - Saat membuka batch lama via History, komponen `BatchDetail` saat ini **masih menampilkan aksi Commit/Cancel** bila status memenuhi (karena komponen sama). Ini harus diubah: **batch dari Riwayat harus read-only**.
- Duplicate hash warning visibility:
  - Sudah ada toast warning saat analyze; perlu pastikan warning juga **jelas terlihat di halaman** (banner/panel) agar tidak “hilang”.
- Handling error 409 detail object:
  - `errorMessage()` hanya mengambil string/array; untuk `HTTPException(409, {message: ...})` perlu ditangani agar pesan duplicate/409 terbaca jelas.
- Masking sensitif:
  - UI bergantung pada masking yang disimpan backend di row. Wajib diverifikasi tidak ada full sensitive values di preview & download.

**Status bucket:**
- DONE: ✅ Review page baru + kontrak endpoint + git diff.
- IN PROGRESS: UI wiring & penyempurnaan sesuai gaps.
- TODO/BLOCKED: lihat daftar berikut.

---

### 13.B.1 UI Import & Migrasi + Preview + Riwayat + Download (DONE — agent-tested, STOP menunggu review)
**Hasil aktual (sesi ini):**
- Route baru `/employees/migration` → `EmployeeMigrationPage` (App.js). Route lama `/employees/import` + endpoint legacy TIDAK diubah.
- Data Karyawan: tombol "Impor & Migrasi" untuk user ber-`employee:import`; user tanpa izin tsb (mis. HR Manager) tetap melihat "Impor Excel" (legacy). Halaman migrasi punya link "Impor sederhana (format lama)" bila `employee:create`.
- Riwayat → detail batch **read-only** (tanpa Commit/Batalkan, ada catatan mode baca saja).
- Banner duplicate hash persisten (`duplicate-hash-warning`) + ack checkbox di dialog commit; 409 duplicate dari server juga memunculkan ack; pesan 409 object (`detail.message`) tampil.
- Stepper mengikuti status batch (preview → commit selesai).
- Backend: hanya perubahan additive yang sudah ada di working tree (field pada error, `q` search, endpoint validation-result). Tidak ada perubahan logic klasifikasi/commit/status/assignment.
**Test:**
- esbuild compile: OK.
- `/root/tenant_tests/test_01e_ui.py` (targeted kontrak UI): **31/31 PASS** (masking preview + file validasi, kolom file validasi, search, 403 HRM/MGR, 404 cross-tenant KBS untuk detail/rows/validation/commit, history, commit eksplisit, 409 re-commit/cancel batch committed, dup hash warning + 409 tanpa confirm, UPDATE diff, blank=UNCHANGED, filter).
- `/root/tenant_tests/test_01e.py` rerun: **63/63 PASS**.
- Browser (desktop 1920): E2E template→upload→analyze→preview→commit PASS; dup banner PASS; UPDATE diff PASS; riwayat read-only PASS; HR Manager: halaman migrasi forbidden + legacy import tetap bisa dibuka PASS.
- Fixture baru: ZT01E-U*/ZT01E-V* (akan dibersihkan di fase cleanup ZT01E).

#### (arsip) rencana awal 13.B.1
**Target:** UI end-to-end sesuai alur 01E tanpa mengubah backend stabil (kecuali additive endpoint yang benar-benar diperlukan).

**DONE**
- Halaman draft `EmployeeMigrationPage.jsx` sudah ada (belum masuk routing).
- Backend additive endpoint untuk kebutuhan download validasi sudah tersedia di working tree (belum di-commit).

**IN PROGRESS**
1) **Routing & reuse flow**
   - Putuskan strategi:
     - opsi A (preferred): route `/employees/import` menunjuk ke `EmployeeMigrationPage` (menggantikan UI lama, tapi **endpoint legacy tetap ada**).
     - opsi B: route baru `/employees/migration` dan tombol diarahkan ke sana (risiko duplikasi user flow).
   - Pastikan tidak ada duplikasi membingungkan bagi user.

2) **Riwayat batch harus read-only**
   - Saat membuka detail batch dari tab Riwayat: sembunyikan tombol Commit/Cancel, dan pastikan tidak ada aksi mutasi.

3) **Duplicate file hash warning yang jelas**
   - Jika backend mengembalikan `duplicate_committed_batch` atau batch warnings mengandung “pernah di-commit”, tampilkan banner peringatan yang persist.
   - Tidak boleh silent repeat commit.

4) **Error handling yang user-friendly**
   - Tangani error `409` dengan detail object: tampilkan `detail.message` bila ada.
   - State yang wajib: loading / empty / error / retry pada tiap tahap.

5) **Tenant isolation check di UI**
   - Pastikan UI tidak menyimpan batch_id lintas tenant; semua akses batch/rows dilakukan via API tenant-scoped.

**TODO**
- Verify masking sensitif via UI preview & file hasil validasi.
- Tambahkan `data-testid` untuk elemen yang belum unik (audit cepat saat compile/QA).
- Tambahkan guard: download hasil validasi untuk batch COMMITTED/PARTIAL juga tetap aman (read-only) dan tetap masking.

**BLOCKED**
- —

**Acceptance checks (targeted) setelah 13.B.1 selesai:**
- Flow: Template → Upload → Analyze → Validate → Preview → Commit (eksplisit).
- Badge klasifikasi: NEW/UPDATE/UNCHANGED/CONFLICT/ERROR tampil jelas.
- UPDATE menampilkan field diff.
- Batch warning duplicate hash muncul jelas + butuh ack sebelum confirm_duplicate.
- History: batch lama read-only.
- Download hasil validasi/error sesuai kolom: Sheet, Row, Employee Number, Field, Status, Error/Warning, Message.
- Unauthorized user: UI deny + API 403.
- Cross-tenant batch: 404/denied.

**STOP POINT:** setelah UI scope ini selesai + targeted tests, **STOP dan laporkan hasil** sebelum lanjut ke performance/QA/regression.

---

### 13.B.2 Compile/Build + Visual QA desktop/tablet/mobile (TODO)
**TODO**
- Compile/build frontend (yarn build) untuk memastikan wiring benar.
- QA visual end-to-end di:
  - Desktop
  - Tablet
  - Mobile

**Catatan QA wajib:**
- Tidak ada tombol terpotong di mobile; touch targets ≥44px.
- Tabel preview/history tetap usable (overflow horizontal wajar/scroll area bila perlu).
- Loading/error/empty states jelas.

**STOP POINT:** setelah visual QA selesai, **STOP dan laporkan hasil** sebelum lanjut ke performance.

---

### 13.B.3 Correction baru: Future-dated assignment (SCHEDULED) — 01D + 01E integration (TODO)
**Koreksi requirement dari user (baru):** rule tanggal penempatan masa depan harus configurable per tenant.

**TODO (additive, tenant-aware, audited):**
1) Tenant setting:
   - `allow_future_assignment`: Ya/Tidak (default **Tidak**, mempertahankan behavior existing: tanggal efektif ≤ hari ini).
   - `max_future_assignment_days`: default **30**.

2) Model assignment:
   - Jika tanggal efektif di masa depan dan tenant mengizinkan:
     - simpan sebagai **SCHEDULED/PLANNED** (bukan ACTIVE)
     - assignment aktif saat ini tetap **ACTIVE**
     - `employees.project_id` tetap menunjuk penempatan aktif saat ini
   - Pada tanggal efektif:
     - assignment terjadwal menjadi ACTIVE
     - assignment sebelumnya menjadi ENDED
     - tetap maksimal 1 ACTIVE.

3) UI (Profile 360 / Penempatan):
   - Bedakan:
     - **Penempatan Saat Ini**
     - **Penempatan Terjadwal**
   - Riwayat menampilkan: proyek tujuan, tanggal efektif, status Terjadwal, created_by, created_at.
   - Sebelum tanggal efektif: HR bisa edit/batalkan scheduled (berdasarkan permission).

4) Import 01E (assignment dari Excel):
   - Jika tanggal assignment future dan tenant allow:
     - buat SCHEDULED
   - Jika melebihi batas `max_future_assignment_days`: validation error.
   - Jika setting disable: future date ditolak.
   - Jangan langsung mengganti current project bila future.

5) Targeted regression:
   - 01D rules (ACTIVE uniqueness, history correctness)
   - Integrasi 01E assignment

**STOP POINT:** setelah koreksi ini selesai + targeted regression, **STOP dan laporkan hasil** sebelum lanjut ke performance/regression final.

---

### 13.B.4 Performance tests ZT01E only (500/1000/5000) (TODO)
**TODO**
- Jalankan performance test nyata untuk:
  - 500 rows
  - 1.000 rows
  - 5.000 rows
- Ukur terpisah:
  - upload
  - analyze
  - validate
  - preview/load result
  - commit
- Optimasi hanya bila ada bukti bottleneck:
  - bulk lookup/chunk/index (additive)
  - hilangkan N+1
  - tetap **1 employee = 1 transaction** saat commit.

**STOP POINT:** setelah performance selesai (angka nyata), **STOP dan laporkan hasil**.

---

### 13.B.5 Clean-state internal regression + data integrity + testing_agent_v3 (TODO)
**TODO**
- Internal regression dari state fixture yang bersih:
  - legacy import
  - 01B, 01C, 01D
  - Payroll, Attendance, Recruitment, Contracts, Documents, Certifications, Tenant Foundation
- Pastikan perbaikan tidak mengubah modul unrelated hanya agar test pass.
- Jalankan `testing_agent_v3` **hanya setelah** internal regression stabil.
- Laporkan hasil numerik apa adanya (PASS/FAIL/manual).

**STOP POINT:** setelah regression + testing_agent_v3, **STOP dan laporkan hasil**.

---

### 13.B.6 Cleanup ZT01E only + restart x2 + final report + local commit (TODO)
**DONE**
- Policy: cleanup hanya prefix `ZT01E`; tenant `ZT01B170909` **tidak disentuh**.

**TODO**
1) Cleanup aman:
   - hapus hanya data fixture ZT01E (DB + storage staging lokal bila ada)
   - verifikasi tidak ada baseline/PT REAL/01B–01D/legacy yang berubah.

2) Restart backend minimal 2x:
   - `m0006` tetap **SKIP**
   - tidak ada duplicated seed/batches
   - tidak ada mutasi data bisnis.

3) Final report:
   - Buat `/app/UPGRADE_01E_EMPLOYEE_MIGRATION_REPORT.md`
   - wajib mencantumkan: scope, backend summary, UI yang selesai, performance figures, regression/testing-agent/visual/restart/cleanup results, known limitations/issues, dan `Production Changed: NO`.
   - Hanya bila critical tests benar-benar pass: tulis `UPGRADE 01E — READY FOR REVIEW / LOCK`.

4) Local commit (DIIZINKAN hanya setelah restart x2 + final report selesai):
   - scope commit: hanya perubahan valid upgrade 01E.
   - **exclude**: `.env`/`.env.example`, credential/token, test_reports sementara, fixtures/scripts, artefak perf.
   - Tidak push/PR/merge/deploy.

**STOP POINT:** setelah final report + local commit, **STOP untuk review user**. Jangan mulai 01F.

---

## PR GitHub (atas instruksi user)
- Draft **PR #13** `[WIP] Upgrade 01B–01E` : branch `feature/upgrade-01b-01e-employee-core` → `main` (dibuat dari origin/main + tree 01B–01E; exclude .env.example, test_reports/, memory/; host server disensor). Belum di-merge; tidak ada deploy.
- Branch kerja lokal tetap `feature/upgrade-01e-employee-migration`. Jika ada perubahan 01E-B lanjutan, push ke branch PR #13 hanya atas instruksi user.

## Phase 14 — Upgrade 01F: Data Completeness (STATUS: LOCKED ✅ — 2026-09-26, final decision by user)
- Dimulai atas instruksi user (01E-B masih punya item terbuka: visual QA, scheduled assignment, perf, regression final, testing_agent_v3, cleanup, restart, report final).
- Output: `/app/UPGRADE_01F_DATA_COMPLETENESS_AUDIT.md` (inventaris field 9 tab, master reuse, mapping kandidat terpusat, gap G1–G11, proposal schema m0007 [DESAIN SAJA], rule engine, integration points, risiko, urutan).
- Tidak ada perubahan kode/schema/data. Tidak ada migration. Staging only, no push/PR/merge/deploy, no 01G.
- Insiden lingkungan: MariaDB FATAL setelah container restart → start ulang via supervisor, data utuh (65 tabel, m0003–m0006).
- KEPUTUSAN USER (dikunci): buat langsung 3 tabel (completeness_rules, completeness_rule_scopes, employee_completeness) via m0007 additive; default §4 = default awal configurable per tenant; sertifikasi wajib TIDAK otomatis berlaku semua bila butuh scope (tanpa scope -> tidak menyebabkan mass incomplete); PTKP = ANJURAN, TK/0 bukan bukti konfirmasi, payroll tidak diubah; view = employee:view (+ tenant scope), permission baru hanya employee_completeness:configure (tenant_admin, company_owner via wildcard, hr_admin); formula = WAJIB terpenuhi / WAJIB applicable x100, ANJURAN tidak menurunkan skor, OFF/N/A di luar denominator, 100%=LENGKAP else BELUM_LENGKAP; snapshot tanpa nilai sensitif; trigger: profile/family/document/contract/certification/status/assignment/import 01E (bulk setelah commit); gagal evaluasi tidak menggagalkan transaksi (tandai stale + log aman); daily reevaluation via scheduler existing.
- Urutan coding: katalog/validator -> m0007 -> engine -> API -> trigger -> UI -> test/perf/regresi -> report. STATUS: IN PROGRESS (lihat 14.R untuk status aktual).
- (arsip) DONE: audit. TODO awal: keputusan user (rule table bertahap/langsung, daftar requirement+level, PTKP G3, permission) → validator bersama → mapping+engine → m0007 → API → hooks → UI → QA/regresi/report. BLOCKED: menunggu review user.

### 14.R — Environment check + code review 01F (DONE — STOP, waiting for user review)
Environment check (read-only): supervisor backend/frontend/mariadb/s3 RUNNING; DB = `hris_staging` @127.0.0.1; APP_ENV=staging, AUTO_SEED=false, READ_ONLY=false, ENABLE_SCHEDULER=false; health `healthy / mariadb:connected`; 68 tables; ledger m0003–m0007 (m0007 recorded once, 2026-09-26 00:43 UTC); m0007 rerun dry-run = **SKIP**; baseline: employees 33 (NEP 30, KBS 3), family 11, contracts 8, documents 6, certifications 6, assignments 18 active, status_history 36, import_batches 26; employee_completeness 30 (NEP; 0 mismatch tenant/employee); completeness_rules 0, scopes 0; no ZT* tenants/fixtures (ZT01B170909 no longer present — not touched). esbuild PASS. No commits/pushes.

Status per part (based on the actual code, not the plan):
| Part | Status | Notes |
|---|---|---|
| Catalog `completeness_mapping.py` | DONE (small gap) | 30 static requirements + dynamic DOC./CERT. from masters; levels REQUIRED/RECOMMENDED/OFF. Gap: no scope for a **specific 01B employee status** (only the ACTIVE/STANDBY/INACTIVE category). |
| Validators `field_validators.py` | DONE | Reuses 01E DIGIT_RULES/ENUMS (single source); only flags INVALID, never blocks saves. |
| m0007 + db.py registry/index | DONE (agent-tested) | 3 additive tables; unique (company_id, employee_id); rerun SKIP. |
| RBAC `employee_completeness:configure` | DONE (backend enforced) | tenant_admin + hr_admin; excluded from hr_manager; company_owner wildcard NOT yet tested. |
| Engine `completeness.py` | PARTIAL | Formula/OFF/NA/ANJURAN/PTKP TK/0=UNVERIFIED/CERT scoped_only/EXCLUDED for inactive all present; bulk loader without N+1. Risks: refresh = delete→insert (not atomic; concurrent triggers can collide on the unique index → caught, marked stale); employees loaded without chunking in a full refresh; `load_context` limit 200000. |
| API `routers/completeness.py` | PARTIAL | catalog, detail (on-read refresh if stale/rules changed/different day), summary, list, rules PUT/DELETE, scopes POST/DELETE, reevaluate — all tenant-scoped + audited. Gaps: list/summary load ALL snapshots into Python (not DB pagination) → performance risk at 6,000+; no project/department/division/employee status/score range filters; list lacks project/department/status/evaluated columns; reevaluate needs configure only (no per-employee path for users with edit rights). |
| Trigger profile/create/delete/status (employees.py) | PARTIAL (code wired, not tested) | inline `await safe_refresh` after log_action (never raises). |
| Trigger family + photo (employee_profile.py) | PARTIAL (not tested) | family CRUD ×3, photo ×2. |
| Trigger documents / contracts / certifications | PARTIAL (not tested) | docs ×3 (employee owner only), contracts ×6 incl. approve/status/renew, certs ×4. |
| Trigger 01B status (employee_status.py) | PARTIAL (not tested) | after the transaction commits. |
| Trigger 01D assignment | PARTIAL (not tested) | assign/transfer/end. |
| Integrasi 01E | PARTIAL (not tested) | after commit + log, bulk once for COMMITTED rows, try/except; 01E logic unchanged. Small fix needed: rows query has no projection (loads source_rows/changes JSON). |
| Trigger legacy import | PARTIAL | bulk once after commit (a new employee = new source). |
| Trigger payroll (upsert_salary) | PARTIAL — **keep (justified)** | employee_salaries is the source for TAX.PTKP, NPWP applicability (has_npwp), and BPJS (enrolled). |
| Trigger recruitment conversion | PARTIAL — **keep (justified)** | creates a new employee → first snapshot. |
| Master changes (document/certification type is_mandatory, status category) | GAP | rules_hash changes → detail refreshes on read; list/summary only update on the daily job/manual reevaluation. |
| Scheduler daily job | PARTIAL | registered in the existing scheduler (01:30 WIB, coalesce, max_instances=1); **ENABLE_SCHEDULER=false on staging** → not active at runtime; must be tested by calling `daily_reevaluation()` directly; not yet chunked per employee. |
| UI Profile 360 card | PARTIAL | score, badge, fulfilled/total required, missing items per category + "Lengkapi" link to the right tab (keys verified), separate recommended section, evaluated time, loading/error. Gaps: no "Evaluasi Ulang" button (only reload), missing count not shown explicitly. |
| UI Monitoring | PARTIAL | 4 summary cards, top missing, status filter, search, server pagination (25), empty/error/loading. Gaps: project/dept/division/employee status/evaluated columns; filters for project/dept/employee status/score range; missing-items detail (drawer). |
| UI Master Kelengkapan | PARTIAL | level per requirement, reset to default, scope dialog INCLUDE/EXCLUDE, read-only mode. Gaps: HR-friendly wording ("Berlaku untuk" / "Dikecualikan untuk"), specific employee status scope, effective dates not in the UI. |
| Test `/root/tenant_tests/test_01f.py` | PARTIAL — NOT RUN | 45 behavioral checks (formula, ANJURAN, OFF, cert scope, PTKP, triggers create/update/family/cert/contract/doc, sensitive, cross-tenant, 01E bulk, safe failure, audit). Gaps: no status 01B / assignment 01D trigger tests, scheduler idempotency, company_owner; check #44 will FAIL because the scheduler is disabled on staging (needs to be redesigned); no ZT01F cleanup. |
| Performance / regression / testing_agent / report | TODO | — |

Code to tidy up (no behavior changes before approval): (1) 01E rows query → projection `employee_id` only; (2) refresh → per-employee upsert (or ignore unique collisions) to avoid races; (3) list/summary → DB-level filter/pagination + projection without `items`.

### 14.T — T1 foundation + T2 trigger/scheduler (DONE — agent-tested 79/79, STOP waiting for user review)
- Branch: `feature/upgrade-01f-data-completeness` (from HEAD 68352a2). NOTE: the platform auto-commits local commits when each stage finishes (author emergent-agent-e1): 2a9f590 (01F audit) & 68352a2 (01F code before T1) are also on `feature/upgrade-01e-employee-migration`. No push. `.env.example` files stay uncommitted.
- T1: snapshot saved via `INSERT … ON DUPLICATE KEY UPDATE` on the EXISTING unique index `ux_employee_completeness_emp` (no m0008; m0007 untouched); updated only when `evaluated_at` of the new result >= the stored one (old results never overwrite new ones); refresh per chunk of 500 (full tenant too) + orphan purge via 1 SQL; per-tenant coalesced background refresh after rule/scope changes (mark stale in 1 UPDATE, no synchronous recalculation); rules_hash covers dynamic masters + 01B status categories + requires_contract → master changes are detected as `pending`. List = SQL JOIN employees with filters project/department/division/employee status 01B/completeness status/score range/search (LIKE escaped)/missing (JSON_CONTAINS)/pending + server pagination; summary = aggregate GROUP BY + JSON_TABLE (no loading rows into memory). New endpoint `POST /api/employees/{id}/completeness/reevaluate` (employee:edit). Scope `employee_status` (specific 01B status) via the existing scope mechanism (no new schema).
- 01E: post-commit query = `DISTINCT employee_id` only; classification/validation/preview/commit/per-employee transactions unchanged.
- Payroll: trigger only if ptkp_status/has_npwp/bpjs_*_enrolled/ptkp_confirmed_at change or salary data is newly created.
- Test `/root/tenant_tests/test_01f.py`: run 1 = 77/79 (2 FAILs = test issues: #19 false positive on the top-level `items` key; #69 TestClient using a different event loop per request) → test fixed → fixture cleanup → run 2 (clean state) **79/79 PASS** (RUN=012500). Covered: m0007 SKIP, unique index, RBAC (owner wildcard, hr_manager 403, manager view), DB-level list/summary, triggers create/profile/family/photo/document/contract/certification/assignment(assign/transfer/end + project scope)/status 01B (category + specific status)/payroll narrow/01E bulk (identical evaluated_at)/legacy import/recruitment conversion, e2e failure injection (business 200/201, snapshot stale), on-read recovery, concurrency 6x + 2x full (no duplicates), old result doesn't overwrite, scheduler job registered (runtime ENABLE_SCHEDULER=false = correct), daily 2x idempotent + no business mutation, cross-tenant, sensitive values not stored.
- Cleanup `cleanup_01f.py --apply`: ZT01F employees/candidates/batches/storage object removed; baseline back: employees 33, family 11, contracts 8, docs 6, certs 6, assignments 18, status_history 36, batches 26, 68 tables. Residue: 24 audit_logs `completeness_*` from tests (to be tidied in final cleanup). employee_completeness now 33 (NEP 30 + KBS 3, result of the daily test).
- Known limitation: PTKP has no confirmation flow yet (`ptkp_confirmed_at` is never set) → TK/0 is always UNVERIFIED (ANJURAN, does not lower the score).

### 14.U — UI 01F (DONE — agent-tested, STOP waiting for user review)
- Backend NOT changed in this stage (the T1 API contract was enough). Files: `components/employees/CompletenessCard.jsx` (card + shared: CompletenessBreakdown, badges, PendingBadge, formatEvaluated), `pages/EmployeeCompletenessPage.jsx` (Monitoring + Master), `pages/EmployeeDetailPage.jsx` (`?tab=` support).
- Profile 360: %, LENGKAP/BELUM LENGKAP badge, fulfilled/total required, missing count, list of missing required items per category + "Buka tab …", separate Anjuran section (does not affect the score; PTKP TK/0 = "Belum dikonfirmasi" in Anjuran), last evaluation, "Menunggu evaluasi" badge if stale, Evaluasi Ulang button (POST /employees/{id}/completeness/reevaluate, employee:edit; without edit → "Muat ulang").
- Monitoring: 5 KPIs (Total/Lengkap/Belum/Menunggu/Rata-rata) from the aggregate API; pending banner + "Evaluasi Ulang Sekarang" (configure); top-missing chips; FilterBar: search + Proyek/Departemen/Divisi/Status Karyawan 01B/Kelengkapan/Rentang %/Data yang kurang/Menunggu evaluasi; DataTable (columns: number+name, project, department, division, employee status, %, status+pending, missing count, last evaluation); server-side pagination; detail drawer (category, requirement, Wajib/Anjuran, fulfilled/not, "Buka tab" → `/employees/{id}?tab=`, Buka Profil, Evaluasi Ulang).
- Master: legend Wajib/Anjuran/Nonaktif, read-only code, level select (configure) / badge (read-only), "Cakupan" column = "Berlaku untuk: … / Dikecualikan untuk: …", scope dialog with Berlaku untuk / Dikecualikan untuk sections, types incl. Status karyawan (01B) spesifik; after save → toast + light polling of the summary for 60 s / while the background refresh runs (no synchronous recalculation from the browser).
- Build: esbuild PASS; `yarn build` PASS (exit 0, 2x). The only warning is legacy `EmployeeMigrationPage.jsx` (01E, not touched).
- Targeted UI test (screenshot automation, agent-tested): KPIs = API (30/0/26/0/32.4%); pagination 1–20/21–30; 0–49% range filter, project filter, EXCLUDED filter, NEP-0002 search, pending filter; drawer; card score 66.7% "14 dari 21", "7 kurang"; Evaluasi Ulang updates the time without a refresh; "Buka tab" → tab-personal; `?tab=documents`; level change + reset; scope EXCLUDE specific 01B status add/delete; pending banner 30 → Evaluasi Ulang Sekarang → 0 + empty state (via temporary ZT01F-UI master document type, deleted); HR Manager read-only Master (35 badges, no form/reevaluate-all) but can reevaluate per employee; Manager view without reevaluate; mobile 390/tablet 820 without page overflow, mobile list, full-width drawer. Console: no errors from the 01F pages.
- Note: DataTable (existing component) renders cells twice (mobile list + desktop table) → testids inside cells appear twice (one hidden per breakpoint); row testids stay unique (`data-table-row-*` / `data-table-mobile-row-*`).
- Rules/scopes/ZT01F master back to 0 after the UI test. Additional audit_logs residue from the UI test (rule/scope/reevaluate) → final cleanup 01F.
- Platform auto-commit: 47b0c87 (T1+T2) is also local on this branch; no push.

### 14.P — Performance + Final Regression + testing_agent_v3 (DONE — agent-tested, STOP waiting for user review)
- **Performance** (ZT01F fixtures only, NEP tenant; `perf_01f.py` → `perf_01f_results.jsonl`; fixtures cleaned up afterwards via `cleanup_01f.py` dry-run→apply). ms per scale 530 / 1,030 / 6,030 / 10,030 employees:
  - bulk engine eval 406 / 746 / 4,131 / 7,358 · bulk reevaluate API 400 / 847 / 4,607 / 7,743 · daily reevaluation 438 / 765 / 4,341 / 7,381
  - summary 19 / 25 / 77 / 141 · list first page 21 / 25 / 57 / 80 (20 rows, payload 7.9 KB) · filters (project/dept/division/01B/status/score/search/missing/combined) 17–23 / 22–25 / 45–61 / 58–115
  - backend RSS 24 / 211 / 211 / 211 MB. At 10k during the bulk run: GET /employees median 144 / p95 240 ms, single reevaluate 27 ms, profile PUT 33 ms (non-blocking). No bottleneck found, so no optimization in this stage.
- **Regression (final, clean state)**: scoped cleanup `cleanup_rerun_scoped.py` (dry-run→apply; only ZT01B/ZT01C + ZT01B<HHMMSS> tenant + tenant-regression tenants in final_state.json) → rerun full suites: **01B 43/43**, **01C (test_01c_on01d) 43/43**, **tenant regression 134/134 + 1 SKIP** (branding-audit check marked REGR-SKIP: it depends on the platform-branding PUT/DELETE, which the regression variant intentionally skips; the test was minimally fixed, backup `final_test_regr.py.pre01f_close.bak`). After the rerun: same scoped cleanup → counts IDENTICAL to the pre-rerun state. Before that (earlier batch): 01D 48/48, 01E 63/63, 01E UI 31/31, 01F 79/79 (RUN=021853), recruitment 43/43, sub T12–T14 PASS, pytest tenant isolation 1 passed. Domain GET smoke 46: 44×2xx + 2×422 = **EXPECTED VALIDATION** (`/leave/ledger` without employee_id; `/schedules` without period/date range; both 200 with valid params).
- **Integrity** (read-only `integrity_01f_close.py`): all duplicate/orphan/tenant-mismatch checks = 0, sensitive values in snapshots = 0, active employees without snapshot = 0, stale = 0, rules/scopes = 0.
- **testing_agent_v3** (iteration_26.json): backend 15/15, frontend 10/10, critical_bugs [], ui_bugs [] (no duration/metadata in the file). `backend_test.py` (+314 lines by the agent) → reverted to HEAD; a copy is kept in `/root/tenant_tests/backend_test_iter26_agent_copy.py`.
- **VALID PRODUCT FINDING (not fixed yet, no code changes in this stage)**: `DELETE /api/completeness/scopes/{id}` → HTTP 500 (MariaDB deadlock 1213) 3x, all during test_01f runs (the 3rd delete in a row while the background tenant refresh from the previous scope change was running). Cause: `engine.mark_stale(company, None)` = 1 tenant-wide UPDATE colliding with `_refresh_chunk` upserts. The scope row + audit are already committed, but the response is 500 and no new background refresh gets scheduled. Proposed fix: retry deadlock (1213/1205) in mark_stale + make the failure non-fatal (still 200 + schedule refresh), or chunked UPDATE; plus a regression test for sequential scope delete/create during a refresh. Same pattern exists in create_scope/update_rule/reset_rule.
- Residue (for final cleanup): audit `completeness_*` 82; fixtures ZT01D 5, ZT01E 31, ZT01F 6 (RUN 021853), SMOKE 3; tenants ZTEST Sub SA077F/SB077F/Default Grace/Legacy (from sub/autoseed tests, outside the rerun scope); NEP employee counter 49. `ZT01B170909` NOT PRESENT (not created/deleted).


### 14.D — Fix deadlock rule/scope completeness (DONE — agent-tested, STOP waiting for user review)
- **Final root cause** (reproduced before the fix with `repro_01f_deadlock.py`: 500s on create scope, delete scope, update rule, reset rule, AND POST /completeness/reevaluate): the tenant-wide `UPDATE employee_completeness SET is_stale=1 WHERE company_id=…` (1 large transaction, locks thousands of rows in random scan order) vs `INSERT … ON DUPLICATE KEY UPDATE` snapshot per chunk (refresh) + 2 full refreshes of the same tenant running at once (manual + background) → MariaDB 1213. The scope/rule mutation + audit were already committed (separate statements) before the 500.
- **Fix** (`app/core/completeness.py`, `app/routers/completeness.py`, `app/core/db.py` +`_TxWriter.delete`):
  1. Main mutation (create/delete scope, update/reset rule) + audit in ONE transaction (`transaction()`), dup/existence check `SELECT … FOR UPDATE` inside the transaction; retry max 5x only for 1213/1205 (the server rolls back fully → no duplicates); still failing → `ConfigBusyError` → **HTTP 503** "Perubahan belum tersimpan … Silakan coba lagi." (not disguised as 200, no DB detail).
  2. Post-commit side effect `after_config_change`: stale marking with retry; if it still fails → warning log (error type only), response stays success; `schedule_tenant_refresh` (existing coalescing) is ALWAYS scheduled; different rules_hash still reads as pending.
  3. Deadlock prevention: stale marking in chunks of 500 in `employee_id` order via the unique index (short locks), snapshot upsert sorted by `employee_id` (same lock order), full tenant refresh serialized per tenant (asyncio.Lock per event loop; employee list + rules read AFTER acquiring the lock = always the latest config); upsert/delete/purge snapshot (idempotent) with retry. Retry: 5 attempts, backoff 0.05·2^i·(1+jitter) s (max ~1.5 s). No new queue/infrastructure, evaluator/list/summary queries unchanged.
- **Tests**: new `/root/tenant_tests/test_01f_concurrency.py` (fixture `c01f_fixture.py` 3,000 ZT01F-C employees) **34/34 PASS, 2x in a row** — real concurrency (create during reevaluate, delete sequentially during background refresh, update/reset rule during refresh, burst 3 scope threads + rule + reevaluate loop with 0 5xx, eventual consistency, no duplicate snapshots, exact audit, final result follows the latest rule, explicit delete-scope checks) + deadlock injection (stale transient/permanent, main transaction transient → exactly 1 row + 1 audit, main permanent → 503 without row/audit, safe log) + tenant isolation (KBS identical) + 0 HTTP 5xx / 0 deadlock tracebacks. Repro after the fix: 0 500s (4 runs).
- Full `test_01f.py`: run 1 72/79 → 7 FAILs = FIXTURE ISSUE (#26 PUT NIK "123" → 409 01C duplicate-NIK check because leftover employee ZT01F-021853-01 already has NIK "123"; #27–29/42/45/47 cascade) → minimal test fix (invalid NIK is now unique per RUN, backup `test_01f.py.pre_deadlockfix.bak`) → **79/79 PASS** (RUN=031749). pytest tenant isolation 1 passed. Targeted UI (preview): level change/reset + scope add/delete via Master → success toasts, Monitoring pending 0.
- Perf smoke ~10k (10,053 employees): bulk reevaluate API 7,415 ms (before 7,743), PUT rule 1,157 ms / reset 1,348 ms (chunked stale 365–419 ms vs single UPDATE 177–587 ms), background refresh after rule change 9.0 s; reads during refresh: /employees median 38 / p95 232 ms, monitoring list 287/361, summary 296/479; 20 scope calls burst 2.8 s all 2xx; 0 5xx. ZT01F-C fixtures cleaned up (only my own fixtures) → counts identical to before.
- Residue for final cleanup: ZT01F 18 employees (RUN 021853/031441/031749), audit completeness_* 600, ZT01D 5, ZT01E 31, SMOKE 3, ZTEST Sub/Default Grace/Legacy tenants, NEP counter 51. Platform auto-commit 9e227cd (plan + iteration_26.json). No push.

### 14.F — Final cleanup + verification + final report (DONE — agent-tested, STOP waiting for user review)
- testing_agent_v3 after the deadlock fix: `iteration_27.json` backend 34/34, frontend N/A (backend-only). Separate from `iteration_26.json` (backend 15/15, frontend 10/10). Not combined.
- Scoped cleanup (dry-run → apply → dry-run = 0): 18 ZT01F employees + descendants, 3 candidates, 3 import batches, 3 storage objects; 688 provenance-proven `completeness_*` audit rows → 0. Preserved: ZT01D 5, ZT01E 31, SMOKE 3, ZTEST Sub/Default Grace/Legacy tenants, baseline NEP/KBS/REAL. NEP counter 51 (NOT reset). `ZT01B170909` NOT PRESENT.
- Git (read-only): branch `feature/upgrade-01f-data-completeness`, last commit `03a29ba` (deadlock fix committed locally by the platform), no staged changes, `M .env.example`, `M backend/.env.example`, `?? test_reports/iteration_27.json`; no upstream, no push/PR/merge/deploy.
- Integrity (read-only session + rollback): PASS for duplicates/orphans/tenant mismatch/sensitive values (0 out of 88 values)/stale (0)/ZT01F residue (0)/baseline. Exception: 2 old orphan documents (`71f57afe…` CV owner_id empty, 2026-09-20; `fd5203c5…` KTP applicant SMOKE-B, 2026-09-21) = pre-existing / non-01F / non-blocker, no action (approved by user).
- m0007 rerun via existing runner (dry-run + `--apply`) → SKIP; before/after fingerprint identical (68 tables, schema hash, rows 3,742, ledger, permission/grants) → no mutation.
- Deadlock code verification: retry 5x (1213/1205 only, backoff 0.05·2^i·(1+jitter)), permanent main failure → 503 safe message, main + audit atomic, side effect non-blocking + refresh always scheduled → all CONFIRMED.
- Final report: `/app/UPGRADE_01F_DATA_COMPLETENESS_REPORT.md` → **UPGRADE 01F — READY FOR FINAL VERIFICATION / LOCK**. NOT LOCKED. No 01G. Production Changed: NO.

### 14.V — Final verification (DONE — agent-tested) → **UPGRADE 01F — FINAL VERIFICATION PASS / READY TO LOCK** (NOT LOCKED yet)
- Pre-condition found: the container had restarted; supervisor `payroll-dev-mariadb` was FATAL ("can't find command /usr/sbin/mariadbd" at boot; binary present afterwards) and the backend startup had failed after 30 DB attempts (no fallback). Action: `supervisorctl start payroll-dev-mariadb` (existing config; config/data untouched) → InnoDB crash recovery OK, CHECK TABLE 68/68 OK. The "change buffer is corrupted…" log ERROR is pre-existing since 2026-09-26 00:27 (runtime moved from MariaDB 11.8.9 to 10.11.18 on the same datadir), before m0007 → environment note, non-01F.
- Restart 1 + 2 (`supervisorctl restart backend`): healthy, mariadb:connected, read_only false, environment staging, auto_seed false, storage s3-staging-local, no crash loop, 0 startup tracebacks.
- Migration: m0007 1 row (00:43:17.135834), runner → SKIP after both restarts, permission 1, grants hr_admin/tenant_admin 1 each, 0 duplicate permission/grant, schema hash 0e688e5fd8e659a5 unchanged (68 tables).
- Counts before restart 1 = after restart 2 (identical): employees 54, family 14, documents 6, contracts 12, certifications 9, assignments 27, status history 59, import batches 34 (rows 211), snapshots 52, rules 0, scopes 0; NEP counter 51.
- Integrity: dup snapshot 0, stale 0, active without snapshot 0, tenant mismatch 0, sensitive 0/88, ZT01F 0; 2 old orphan documents (71f57afe, fd5203c5) = PRE-EXISTING / NON-01F / NON-BLOCKER.
- Sanity after restart 2: API summary/list/catalog/detail/reevaluate-one 200, KBS→NEP employee 404, KBS list without NEP; UI Monitoring + summary (47/0/42/0/30.3%), Master tab, Profile 360 card OK; 60 requests after restart 1 = 59×200 + 1×404 (intended), 0 5xx. The only data change: evaluated_at of 1 snapshot (ZT01E-LEG-021254) from the sanity reevaluation.
- Git: platform auto-commit 27d92a7 (report + plan + `test_reports/iteration_27.json`) created automatically by the platform (not by the agent), local only; not rewritten. `.env.example` files still uncommitted. No push/PR/merge/deploy.

### 14.L — FINAL DECISION: UPGRADE 01F — DATA COMPLETENESS LOCKED ✅ (2026-09-26)
- Basis: final verification restart 2x PASS; m0007 SKIP without mutation; integrity PASS; tenant isolation PASS; no sensitive-data leaks; full 01F 79/79; concurrency/deadlock 34/34 twice; testing agent iteration_26 backend 15/15 + frontend 10/10 (before the fix), iteration_27 backend 34/34 (after the fix); regression 01B–01E PASS; performance up to ~10k employees within target; deadlock fixed + verified; UI/API normal after restarts; no remaining 01F blockers.
- **Rule: NO further 01F business-logic changes** unless a new regression/blocker is found.
- **Deferred known limitations (NOT blockers):**
  1. PTKP TK/0 has no confirmation mechanism yet (stays Anjuran, does not affect the score).
  2. Existing ESLint warning `EmployeeMigrationPage.jsx` belongs to 01E.
  3. 2 pre-existing orphan documents (`71f57afe…`, `fd5203c5…`), non-01F.
  4. Concurrency performance discrepancy: plan says ~10,053 vs `rr_perf_conc.json` `tenant_total` 3,053 — documented as-is, NOT the official 10k benchmark (reference = clean benchmark `perf_01f.py` 530/1,030/6,030/10,030).
- Git: local commits NOT rewritten/rebased/reset. `test_reports/iteration_27.json` was included in platform auto-commit `27d92a7` → **tidy up during PR preparation** (git cleanup). `.env.example` & `backend/.env.example` stay out of commits. No push / PR / merge / deploy.
- Production Changed: NO.

Next order (after review): T1 tidy engine/01E projection → T2 trigger + scheduler tests (targeted) → STOP → UI completion (monitoring filters/columns/detail, Evaluasi Ulang, Master wording + employee status scope) + esbuild/yarn build → STOP → full test/regression/perf/testing_agent → STOP → report → STOP.

## Phase 15 — Upgrade 01G: Public Employee Form (STATUS: **UPGRADE 01G — PUBLIC EMPLOYEE FORM: LOCKED ✅** (final gate agent-tested, awaiting user review) · 01H NOT STARTED)
**Official 01G flow (adjustment 2026-09-26):** PRIMARY = Public Portal per tenant (`/public/{CODE}/update-data`) + Nomor Karyawan + NIK + Tanggal Lahir → limited session → draft → submit → PENDING_HR_VERIFICATION. OPTIONAL/EXCEPTION = unique HR invitation (existing infrastructure, kept). Fallback for employees without NIK/DOB = design only (not implemented).
Goal: employees without an HRIS login open an HR-generated link → verify identity (Employee Number + NIK + DOB) → fill/correct their own data (mobile-first) → Save Draft → Submit → PENDING_HR_VERIFICATION. **Does NOT overwrite Employee Profile 360.** Approval/apply = 01H.

### 15.1 Audit (DONE — read-only, agent-inspected)
- Document: `/app/UPGRADE_01G_PUBLIC_EMPLOYEE_FORM_AUDIT.md`.
- Key findings: no public token/invitation mechanism exists; the only public route is `/api/public/branding`; auth = JWT Bearer (no cookies/CSRF); rate limit only login lockout per user; audit (`build_audit_entry`, `mask_for_audit`) + masking (`sensitive.py`) reusable; storage tenant-prefixed + proxy download reusable; SMTP per-tenant exists (not configured), WhatsApp does not exist; 01F `evaluate()` is pure (draft estimate possible without touching snapshots).
- Verification data (staging): 9 of 47 active employees (19%) can use the 3 factors; NEP active 6/42 (35 without DOB, 20 without NIK, 1 duplicate NIK with a deleted employee); KBS 3/3; SA077F/SB077F 0/1. Fallback must be decided.
- Main risks: token in access log (→ URL fragment + body), PostHog + session recording in `index.html` on the public page, spoofable X-Forwarded-For (→ per-link counter as primary control).

### 15.2 Design proposal (waiting for review)
- Schema m0008 (additive, 3 tables): `employee_public_links` (hash-only token, status ACTIVE/EXPIRED/REVOKED/SUBMITTED, expiry, per-link counter/lock), `employee_update_submissions` (DRAFT → PENDING_HR_VERIFICATION, `open_slot` unique = 1 open submission per employee, proposed/baseline JSON, version), `employee_submission_files` (private attachments, separate from `documents` so they don't count in 01F / appear in the HR registry). Stateless public session (JWT audience `public-employee-form`, re-checks the link on every request). Permission `employee_public_form:manage`.
- Decisions D1–D11 (see audit §14): fallback (F3 + F1), show-once token, link/session expiry, identity changes, employee statuses, analytics on the public page, pre-verification view, sensitive storage, RBAC, draft retention, post-submit behaviour.
- Implementation order (after review): G0 branch → G1 m0008 → G2 HR links backend → G3 public verify/session/form → G4 draft/submit → G5 upload → G6 backend + security + regression tests → G7 design_agent + HR/public UI → G8 build/screenshot/testing_agent → G9 report → STOP.

Constraints: staging only; no push/PR/merge/deploy; no production changes; 01B–01F LOCKED (no changes to their business logic); 01H (inbox/approve/apply) is out of scope.

### 15.3 — 01G-A Backend Foundation (STATUS: first checkpoint DONE — history below; continued in 15.3b)
Status legend: DONE / PASS / IN PROGRESS / PARTIAL / TODO / BLOCKED / DEFERRED. All results are **agent-tested** (not yet user-confirmed).
- Branch: `feature/upgrade-01g-public-employee-form` (local). Last commit `6a4a759` (platform auto-commit, audit 01G). 01G-A files not yet committed: M `backend/app/core/db.py` (+46, 4 table definitions), M `backend/server.py` (+4, router wiring), ?? `backend/app/core/public_form.py`, ?? `backend/app/routers/public_employee_form.py`, ?? `backend/migrations/m0008_public_employee_form.py`. Inherited (NOT ours, not committed): M `.env.example`, M `backend/.env.example`. No push/PR/merge/deploy. Production Changed: NO.
- Preflight/health: **PASS** — backend RUNNING, `/api/health` healthy, `mariadb:connected`, APP_ENV=staging, AUTO_SEED=false, READ_ONLY=false, DB 127.0.0.1/hris_staging (no production fallback), no crash loop (last traceback = old preflight DB-down before the MariaDB restart). 18 old HTTP 500s on `/completeness/reevaluate` appear in the log BEFORE the first 01G call (suspected: the 01F era before the deadlock fix; the log has no timestamps → note, not a blocker).
- Migration/schema m0008: **DONE · PASS** — existing runner: DRY-RUN/`--apply`/`--apply` rerun = SKIP; ledger exactly 1 row; fingerprint (72 tables, ledger, 170 permissions, 509 role_permissions, row counts) IDENTICAL; 0 duplicate permissions; columns of the 4 tables = ORM (MATCH). Note: the 4 tables had already been created by the startup `create_all(checkfirst)` before m0008 `--apply` recorded the ledger (`tables_created: []`).
- Invitation/public token (create/status/revoke/regenerate, 256-bit token, hash-only, URL fragment `/isi-data#…`): **DONE / PASS**.
- Identity verification (Employee Number + NIK + DOB, bound to the link's employee, generic message): **DONE / PASS**. Fallback for employees without NIK/DOB: **TODO (not agreed)** — currently link creation is rejected with 422 + a list of missing data.
- Rate limit/brute force (per link 5x → 15 min lock; per IP 20/15 min, DB-backed, IP hash): **DONE / PASS**.
- Public session (opaque token, hash in the link, idle 30 min, absolute 2 hours, 1 session/link, logout, revoke takes effect immediately): **DONE / PASS**.
- Editable/view-only/HR-only whitelist (server-side, HR-only injection → 422): **DONE / PASS**.
- Prefill endpoint (masked sensitive values, 01F completeness from the master snapshot): **DONE / PASS**.
- Draft (versioning, 409 on stale version, 1 draft/employee, does not touch master): **DONE / PASS**.
- Submit → PENDING_HR_VERIFICATION (link SUBMITTED, form READ_ONLY, 2nd pending blocked by DB unique): **DONE / PASS**.
- Pending document upload (ext/magic/size, private `employee-submissions/` prefix, proxy download no-store, not in `documents`): **DONE / PASS**.
- Audit/logging (events complete, no raw token/session/NIK/NPWP/bank account/BPJS; `token_hint` = last 4 characters): **DONE / PASS**.
- 01F integration (display the master score; draft/submit does not change the snapshot): **DONE / PASS**.
- Tests (agent-tested, 2026-09-26): `test_01g.py` **77/77 PASS** (run 074220 & rerun 085257); `test_01g_security.py` (targeted RBAC/auth/public session/documents) **35/35 PASS** (run 085242; run 1 34/35 → D10 = TEST ISSUE: local S3 rclone rejects unsigned requests with 400 UnsupportedAlgorithm, not 401/403; the assertion was fixed to non-2xx + no file content).
- Tenant isolation: `pytest /app/backend/tests/test_tenant_isolation.py` **1 passed (12/12 sub-checks)**; 01G cross-tenant (A08, F01–F04, R04) PASS.
- RBAC/auth/documents: **PASS** (R01–R06, U01–U11, D00–D12, L01–L02, S01–S03).
- Regression after 01G: 01E **63/63**, 01F **79/79**, tenant regression **134/134** PASS. **01C: 43/43 PASS** (`test_01c_on01d.py`, clean state). The earlier 36/43 = **TEST ISSUE** (the regression loop mistakenly ran the old pre-01D variant `test_01c.py`; 13/14/15 = 01D rule "project only via Placement" (employees.py:482-489), 16 = the 01D `employee_assignments` table, 27/30 = cascade from the rejected employment edit, 31 = additive 01D/01F lines in the import block). Not a product regression; 01G does not touch those code paths (01G only writes to its 4 new tables).
- Cleanup 01C (scoped, ownership = IDs in `state_01c.json` + run window): **DONE** — 2x (the old-variant run + the rerun), baseline unchanged, NEP counter not reset manually (55→58 from natural increments). 4 generic login audits kept.
- Design deviations vs 15.2 (to review): RBAC reuses `employee:view`/`employee:edit` (no new permission `employee_public_form:manage`); session = opaque token + hash (not a JWT audience); 4 tables (added `public_rate_limits`).
- Step 5: **DONE** — m0008 verified (above) · ZT01G cleanup v2 (ownership-based, dry-run → apply): employees 13, links 16, submissions 8, files 8, family 3, status_history 13, completeness 13, master documents 2, audit 108, rate limit 9, storage 10 → the 4 01G tables = 0, idempotent; baseline NEP 13/KBS 3 unchanged; counter not reset · report `/app/UPGRADE_01G_PUBLIC_EMPLOYEE_FORM_PROGRESS.md` written → **STOP for user review**.
- Regression NOT run after 01G: 01B, 01D, 01F concurrency (latest evidence = the 01F close).
- Open decisions: fallback verification for employees without NIK/DOB (BELUM DIKERJAKAN); design deviations (RBAC reuse, opaque session, 4 tables); 01G-B requirement: strip the URL fragment before PostHog/Emergent read the URL.
- Remaining fixtures outside this step's scope (not cleaned): tenant regression tenants `ZTA3AU0`/`ZTB3AU0` (final_state.json) + artifacts from the 01E/01F runs at 07:43 → final cleanup (later).

### 15.3b — 01G-A Adjustment: Public Portal as Primary Entry (STATUS: DONE · PASS — **01G-A BACKEND — READY FOR 01G-B UI**, awaiting user review)
- Portal resolve reuses `companies.code` (globally unique, immutable, pattern `^[A-Za-z0-9_-]{2,20}$`); no internal ID in the URL; unknown/inactive/expired → identical generic 404. **DONE · PASS**
- Endpoints: `GET /api/public/employee-form/portal/{code}`, `POST …/portal/{code}/verify`; HR `GET /api/employees/public-form/readiness` (employee:view). **DONE**
- 3-factor verification scoped to the tenant (exactly 1 active employee), identical generic message, no-short-circuit comparison + dummy compare when the number is not found. **DONE · PASS**
- Rate limit: per target (tenant + number, 5x/15 minutes → 15-minute lock, the same for existing/non-existing numbers) + per IP (20/15 minutes) + per link (invitation, unchanged); DB-backed, hashed. **DONE · PASS**
- Portal session: reuses `employee_public_links` (`verification_mode=PORTAL_3F`, `token_hash NULL`, hash-only session), 1 portal session/employee, idle 30 minutes/absolute 2 hours, cannot reach internal endpoints, not shown in the HR invitation list. **DONE · PASS**
- Invitation = OPTIONAL/EXCEPTION, infrastructure unchanged (no schema rewrite). **DONE · PASS**
- Employees without NIK/DOB: standard verification safely rejected (generic), internal audit `needs_fallback`, listed in HR readiness, no link-only bypass/mass PIN. Fallback implementation **TODO (decision required)** — design: exception invitation `HR_ASSISTED` + one-time code per exception employee, or complete master data.
- Schema/migration: **no change** (72 tables, 6 migrations; m0008 unchanged).
- Tests (agent-tested): `test_01g_portal.py` **59/59**, `test_01g.py` **77/77**, `test_01g_security.py` **35/35**, tenant isolation pytest **1 passed (12/12)**, 01C `test_01c_on01d.py` **43/43**, 01F `test_01f.py` **79/79**. Interim portal failures = TEST ISSUE (test IP exceeded the IP limit; relationship key `spouse`→`ISTRI`; key `mode` vs `read_only`). One test output printed a fixture session token into a local log → redacted, session deleted, the test now auto-redacts.
- Cleanup: ZT01G (v3, ownership + recorded IPs/targets) and scoped 01C **DONE**; 01G tables & `public_rate_limits` = 0; baseline NEP 13/KBS 3 unchanged. Other suites' fixtures (12 ZT01F, 5 ZT01E, tenant regression tenants) → final cleanup (TODO).
- 01G-B requirement: PostHog (`session_recording` + autocapture) & `emergent-main.js` must NOT be active on `/public/*` / `/isi-data`; no NIK/DOB/form values/session token to analytics.
- Report: `/app/UPGRADE_01G_PUBLIC_EMPLOYEE_FORM_PROGRESS.md` (updated). Production Changed: NO. No push/PR/merge/deploy.

### 15.4 — 01G-B Public Employee Form UI (STATUS: DONE · PASS — agent-tested, STOP waiting for user review; 01G NOT LOCKED)
- Preflight PASS (branch 01G, staging, AUTO_SEED=false, READ_ONLY=false, ENABLE_SCHEDULER=false, health OK).
- Route `/public/:companyCode/update-data` (+ `/public/*` generic "not available" page) outside BrandingProvider/AuthProvider/ProtectedRoute; the internal app is unchanged (`InternalApp` on `/*`). Invitation `/isi-data` = backend-only (no UI, not removed).
- 6 steps: Data Pribadi (Identitas + Kontak & Alamat) · Keluarga · Bank & Pajak · BPJS · Dokumen · Review → Submit → Pending. 01F = master snapshot (not recomputed in the frontend).
- Token: sessionStorage `kk_pef_session:<CODE>` only; removed on expiry/logout/submit. No console logging of sensitive data.
- Analytics: flag set in `<head>` BEFORE analytics → PostHog/emergent-main.js are **not loaded or initialised** on all `/public/*`; CSP only on public routes (blocks third-party beacons); layer 2: opt-out + full reload after SPA navigation. Static 9/9 PASS; browser 0 PostHog requests on public routes; internal routes still load PostHog.
- Minimal backend support: `_restore_masked` + `GET /portal/{code}/logo` + `has_logo` (no 01G-A/01B–01F refactor).
- Tests (agent-tested): testing_agent_v3 iteration_28 + iteration_29 + direct retest → **18/18 scenarios PASS**; responsive 360/390/430/768/1366 PASS; backend rerun `test_01g` 77/77, `security` 35/35, `portal` 59/59, tenant isolation 1 passed; HR-only injection 422; public token → 401 on internal endpoints.
- Cleanup ZT01G: dry-run → apply → 0 remaining; baseline unchanged; 141 `public_form.*` audit rows with record_id NULL retained (no sensitive data).
- Report: `/app/UPGRADE_01G_PUBLIC_EMPLOYEE_FORM_PROGRESS.md` (section B). Production Changed: NO. No push/PR/merge/deploy.
- BELUM DIKERJAKAN: final performance/load 01G, final verification/LOCK 01G, UI for the fallback/invitation exception (needs a decision).
### 15.4b — 01G Final Verification & Lock (STATUS: COMPLETED · LOCKED ✅ — agent-tested, STOP for user review)
- Regression (final gate): 01G main 77/77 · security 35/35 · portal 59/59 · analytics static 9/9 · tenant isolation pytest 1 passed · 01B 43/43 + 21/21 · 01C_on01d 43/43 + carry 34/34 · 01D 48/48 (first run = FIXTURE collision) · 01E 63/63 + UI 31/31 · 01F 79/79 · 01F concurrency 34/34 (3,000 fixtures, 0 5xx/deadlock).
- Browser: testing_agent_v3 iteration_30 PASS; "1366x768 partial" = INCOMPLETE TEST COVERAGE → full 1366 walkthrough retest PASS; expired-session 1366 retest PASS (earlier timeout = TEST: Next without edits makes no server call). No product code change.
- Performance: 6,106 and 10,106 NEP employees; 0 % errors (seq + 25-worker concurrency, 250 flows); verify p95 ≈ 28 ms seq / ≈ 350 ms conc; prefill conc p95 ≈ 1.08 s (≈35 SELECT constant — optimisation candidate); EXPLAIN 108 SELECTs, 0 full scans; query count constant 6k→10k.
- Cleanup `cleanup_01g_final_v4.py` (ZT01G only): 10,018 employees (10,000 perf) + dependents, 116 rate-limit rows, 8 storage objects; baseline non-ZT01G unchanged; counters unchanged; ZT01B–F kept; 0 01G orphans (13 pre-existing non-01G objects untouched).
- Environment event: container recycle → MariaDB FATAL at autostart → started via supervisor (no datadir re-init) + one backend recovery restart (ENVIRONMENT, not 01G).
- Restart sanity: backend restarted once → healthy, staging, AUTO_SEED=false, m0008 SKIP, 0 table deltas, portal smoke PASS (verify/session/logout, PostHog absent), smoke fixture cleaned → 0 deltas.
- Report: `/app/UPGRADE_01G_PUBLIC_EMPLOYEE_FORM_PROGRESS.md` section F. Production Changed: NO. No push/PR/merge/deploy.
### 15.4c — PR #14 (01F + 01G) (STATUS: OPEN, ready for review — NOT merged, NOT deployed)
- https://github.com/akuntakitatech-design/Payroll/pull/14 · branch `feature/upgrade-01f-01g-completeness-public-form` → `main` (base `af266c9`, after PR #13). 3 commits (01F, 01G, docs plan), 39 files +6040/−15, GitHub mergeable = clean.
- Built from origin/main in a separate worktree (the local branch history was not rewritten). Excluded: `.env.example`, `backend/.env.example`, `.gitignore`, `UPGRADE_01A` (production IP), `memory/`, `test_reports/`. Product code is identical to the tested code.
- Token used only for push + PR creation (not stored in git config; temp files deleted). The user must revoke it. Production Changed: NO.
### 15.4d — ENHANCEMENT 01G: Flexible Employee Form Builder (STATUS: AUDIT DONE · schema proposal — STOP for review, NO migration/code yet)
- Audit: 01F completeness_rules + scopes reusable as the source of truth for core field levels (REQUIRED/RECOMMENDED/OFF; 11 scope types incl. project/department/job_grade/position/status). There is no custom-field infrastructure (no JSON column on employees).
- Proposal m0009 (additive): employee_form_sections, employee_form_fields (CORE config + CUSTOM definitions), employee_form_field_scopes, employee_custom_field_values; employee_submission_files.field_key; proposed.custom + meta.form_version.
- Open decisions: custom field levels Option 1 (form-only, no 01F change — recommended) vs Option 2 (CUSTOM.* in 01F); permission employee_form:configure vs reuse; @dnd-kit; git (stacked PR on PR #14); custom file fields = pending attachment.
- Document: `/app/UPGRADE_01G_FORM_BUILDER_AUDIT.md`. Production Changed: NO.
- PR #14 was MERGED into main (`bb73dbe`). This audit doc + plan note were submitted as **PR #15** (docs only, branch `docs/01g-form-builder-audit`, open, mergeable clean): https://github.com/akuntakitatech-design/Payroll/pull/15
### 15.4e — ENHANCEMENT 01G: Flexible Employee Form Builder — IMPLEMENTATION (STATUS: **LOCKED ✅** — per the user's FINAL CLOSING instruction)
Module status: 01F — Data Completeness: **LOCKED ✅** · 01G — Public Employee Form: **LOCKED ✅** · Enhancement 01G — Flexible Employee Form Builder: **LOCKED ✅** · 01H — HR Verification: **NOT STARTED**.
Branch `feature/upgrade-01g-form-builder` (from main `bb73dbe`; PR #15 not reused). Local commits `c083e42` + `a8a6e9c` (platform auto-commit; NOT pushed). No push/PR/merge/deploy. Production Changed: NO.
Locked decisions: core level = 01F (OFF = Tidak Dinilai, not Optional); 01F REQUIRED > builder hidden (backend); custom REQUIRED/RECOMMENDED/OPTIONAL outside the 01F score; `employee_form:configure`; prefix `cf_`/`cs_`; no hard delete (inactive); custom files = pending until 01H; no columns on `employees`.
| Item | Status |
|---|---|
| Audit/design · architecture decisions | DONE |
| Migration m0009 | DONE — PASS (ledger 1×, rerun SKIP, clean-DB PASS, no schema drift; warning Note 1050 informational) |
| Backend Form Builder (reserved denylist, DB-side monitoring, hidden-core rule) | DONE — PASS (suite 88/88) |
| Dynamic public form | DONE — PASS (backend + browser) |
| Backoffice page + menu Data Karyawan → Form Pembaruan Data | DONE — PASS |
| Share Link / QR / PNG download | DONE — PASS (QR decoded = public URL only) |
| Monitoring (DB-side + UI + filters) | DONE — PASS |
| Custom fields · scope · confirmations · forced badge · preview mobile/desktop · drag & drop (field+section, mouse+keyboard) | DONE — PASS |
| **Custom Field E2E** | **PASS ✅** (browser 24/24, fixture ZT01G-E2E-085945) |
| RBAC employee_form:configure · tenant isolation | PASS |
| Responsive 360/390/430/768/1366 (public + backoffice) | PASS |
| Regression: 01F 79/79 + isolation 4/4 · 01G 77/77 · security 35/35 · portal 59/59 · analytics 9/9 · tenant pytest · expired browser | PASS (01F concurrency not rerun: 01F engine diff = 0 lines) |
| Compile + `yarn build` | PASS |
| **Regression & Restart Verification** | **PASS** (restart delta NONE, m0009 SKIP) |
| Drag & Drop E2E (targeted, iteration_15 + agent verification) | PASS |
| Scoped ZT cleanup | APPLIED · PASS — 40 employees + 96 cf_zt + 9 cs_zt + 18 scopes + dependents + 22 storage objects; integrity 17/17; G5 OUT OF SCOPE / PROTECTED (unchanged); counter NEP 83 unchanged; 10 old orphans untouched |
| LOCK | **YES — LOCKED ✅** |
- 15.4e.1 Code review + m0009 investigation: DONE → `/app/UPGRADE_01G_FORM_BUILDER_CODE_REVIEW.md`.
- 15.4e.2 Blockers (reserved key/label, DB-side monitoring, hidden-core rule, backoffice reachable, UX): DONE — PASS.
- 15.4e.3 Final verification (E2E, responsive, regression, restart, cleanup dry-run): DONE — details `/app/UPGRADE_01G_FORM_BUILDER_PROGRESS.md` §D–§H.
- Environment event: container reset → MariaDB binary missing → reinstalled per `/app/ops/README.md` (datadir not re-initialized).
- 15.4e.4 FINAL CLOSING: targeted DnD PASS → cleanup apply → integrity 17/17 → post-cleanup smoke PASS → **LOCKED ✅** (details `/app/UPGRADE_01G_FORM_BUILDER_PROGRESS.md` §L). Known non-blockers: core REQUIRED server-side at submit = existing 01G behavior; G5 cleanup deferred (cross-module/01F); 10 old storage orphans not owned by the FB. Hygiene: `a8a6e9c` holds an unredacted iteration_14.json (synthetic, local, not pushed; working copy redacted).
- Next: STOP for review. Do not start 01H. No push/PR/merge/deploy.
- 15.4e.5 PR hygiene: local commit cleaned (`.gitignore` + test reports removed; sensitive scan 0) → pushed (force-with-lease back to clean `70634e7` after a platform auto-commit) → **PR #16 open** (1 commit, 22 files; not merged). PR #15 closed as superseded (not merged).

## Phase 16 — Upgrade 01H: HR Verification (STATUS: **LOCKED ✅** — implementation, staging E2E incl. real staging storage, final regression 70/70 + 12/12, cleanup DONE; push/PR pending user approval)
Report: `/app/UPGRADE_01H_HR_VERIFICATION_AUDIT.md` (read-only code audit + 1 read-only staging count query; agent-inspected, no functional tests yet).
Local branch: `feature/upgrade-01h-hr-verification` (from local HEAD with platform auto-commit `9b54a61`; must be cleaned before any 01H PR). Local 01G ref reset to `70634e7` (= remote PR #16). Nothing pushed.
### 16.1 Audit findings (summary)
- REUSE: `employee_update_submissions` (proposed + baseline + version + open_slot unique), `employee_custom_field_values` (official, written only by 01H; 0 rows), `employee_submission_files`, `documents` (owner_type/owner_id), photo pattern, `TenantRepository.update`, `EDITABLE_FIELDS`/validators/`FamilyInput`/`FB.validate_custom`, `transaction()` + `build_audit_entry` + `mask_for_audit`, `completeness.safe_refresh`, tenant `ctx.tdb`, `can_view_sensitive`.
- GAP: no APPROVED/REJECTED/REVISION_REQUESTED statuses, no reviewer columns, no HR review/decision endpoints, no apply logic, no conflict detection, no verify permission, no diff UI.
- NOT reused: `approval_workflows` (metadata-only multi-step for other modules) → DEFER. No new tables proposed.
### 16.2 Proposed design (awaiting review — open questions Q1–Q8 in the report §13)
- Decision per submission (Approve all / Reject / Request Revision) + explicit resolution only for CONFLICT items; no HR editing of proposed values.
- Revision reuses the same submission row (REVISION_REQUESTED stays open; resubmit recaptures baseline).
- Conflict = baseline vs current official data; approve blocked (409) until each conflict gets use_proposed/keep_current.
- Files: DOCUMENT → new `documents` row (object copied to official path); PHOTO → photo prefix; CUSTOM file → reference in `employee_custom_field_values`; reject → file REJECTED.
- `no_npwp` → info only (touches payroll `employee_salaries.has_npwp`) → DEFER.
- Schema: m0010, additive NULL columns on `employee_update_submissions` (reviewed_by/_name/_at, review_note, revision_count, review_history, apply_result, completeness_after) + `employee_submission_files` (document_id, review_status_at); new permission `employee_form:verify` (hr_admin, hr_manager; tenant_admin/company_owner implicit).
- API `/api/employees/update-verifications` (summary, list, detail, file, approve, reject, request-revision); UI Kepegawaian → Verifikasi Pembaruan Data.
### 16.3 Implementation steps
1 m0010 + specs → 2 core/hr_verification.py (diff/conflict/apply) → 3 HR router → 6 backend tests → 4 public revision banner/last decision → 5 monitoring counts → 7 UI → 8 public UI banner → 9 testing agent → 10 docs.
- Superseded note: implementation was later approved by the user (see 16.4).

### 16.4 Step 2 — Implementation + targeted verification (STATUS: **PARTIAL** — implementation DONE, targeted checks PASS; E2E/regression/cleanup/PR NOT STARTED) — 2026-09-27
| Item | Status | Evidence (agent-tested, NOT user-confirmed) |
|---|---|---|
| Branch/base | DONE | `feature/upgrade-01h-hr-verification` rebased on `origin/main` `7c0460a` (PR #16); 0 behind main. Local only — remote branch NOT rewritten, nothing pushed. |
| Local MariaDB (dev only, `hris_dev` @127.0.0.1) | DONE | Supervisor `payroll-dev-mariadb` was FATAL (binary not found at pod start); binary present again → `supervisorctl restart` → RUNNING. Existing data intact (76 tables, ledger m0003–m0010; m0001/m0002 do not use the ledger). No reinit/reset/reseed. AUTO_SEED=false, ENABLE_SCHEDULER=false, R2 not configured. Production MariaDB/R2 NOT touched. |
| Backend `/api/health` | PASS | `{"status":"healthy","database":"mariadb:connected","read_only":false}` (storage: R2 not configured — expected for dev). |
| m0010_hr_verification | DONE | Additive/idempotent; apply OK, rerun SKIP; grants `employee_form:verify` (tenant_admin, hr_admin, hr_manager). |
| Backend scope | DONE | RBAC `verify`; `core/hr_verification.py` (diff, conflict detection/resolution, transactional apply incl. family, custom official values/files, document/photo promotion via `storage.copy_object`, completeness refresh, audit); router `/api/employees/update-verifications` (summary, list, detail, file, approve, reject, request-revision) registered before `/api/employees/{employee_id}`, no duplicate routes; public form revision flow (REVISION_REQUESTED editable, resubmit, last decision, `photo_version` baseline); Form Builder monitoring counts (revision/approved/rejected). |
| Minimal 01G touch | NOTE | Public form prefill of custom official values now uses the DB-decoded value directly (previous `_json()` re-decode turned plain strings into `None`). Only affects values written by 01H. |
| Frontend scope | DONE | Pages `EmployeeUpdateVerificationPage` / `EmployeeUpdateVerificationDetailPage`, `ChangeCompareTable`, routes `/employees/update-verifications[/:id]`, sidebar item (employee_form:verify), public revision/last-decision banner. |
| `tests/test_hr_verification_01h.py` | PASS | **66/66 PASS** (in-process ASGI + local MariaDB; R2 stubbed in-memory because dev R2 is not available). |
| Frontend compile/build | PASS | esbuild bundle OK; webpack "Compiled successfully"; smoke render of list page OK. |
| Local checkpoint commit | DONE (local only) | 1 commit on the 01H branch in `/app/.repo_work/Payroll`; no push/PR. |

Remaining gaps before E2E / regression / cleanup / PR:
- Browser E2E (testing agent) of list/detail/approve/reject/revision + public revision banner: NOT STARTED.
- Broad regression: NOT STARTED. Known env issues from an earlier attempt: `aiosqlite` missing (tenant isolation test); `test_development_core.py` expects a clean DB but `hris_dev` now holds T01H test data → needs a fresh dev DB, not a code fix.
- Real R2 copy path (`copy_object`) not exercised against a real dev bucket (no dev R2).
- Remote branch history must be handled (force-with-lease after rebase) when the user approves a push; PR body/docs report not written.
- Final cleanup (test data, artifacts) NOT STARTED.
- Production Changed: NO.

### 16.5 Staging environment for 01H testing (STATUS: **DONE — setup verified; 01H browser E2E NOT STARTED**) — 2026-09-27
- Where: Emergent Live Preview (separate service from production `hris.akuntakita.com`, which was NOT modified/stopped/redeployed; no DNS changes). A dedicated `staging.hris.akuntakita.com` subdomain was NOT created (DNS/infra out of agent scope).
- DB: separate database `hris_staging` + dedicated user on the local MariaDB (127.0.0.1); schema from startup `ensure_schema` + migrations m0001–m0010 `--apply` (ledger m0003–m0010; m0010 rerun SKIP); 76 tables, 0 column difference vs baseline; `employee_form:verify` granted to tenant_admin/hr_admin/hr_manager. `hris_dev` left intact (dev env backup: `backend/dev.env.bak`, gitignored).
- Runtime: APP_ENV=staging, READ_ONLY=false, AUTO_SEED=false, ENABLE_SCHEDULER=false, new JWT secret, no R2 keys. Synthetic data only: tenant STG + 1 staging platform admin + 1 HR user; 0 employees.
- Storage: **Staging R2 integration: NOT CONFIGURED** (uploads/promotion will fail at runtime until a staging bucket exists).
- Staging HR account: `hr.verifier.staging@kelolakita.dev`, role `hr_admin` (narrowest built-in role with `employee_form:verify`), created via `POST /api/users` (bcrypt), first-login password change completed, password rotated once after a test script hardcoded it (script deleted, never committed). Credential only in gitignored `memory/test_credentials.md`.
- Verification (testing agent iteration_14 + iteration_15, 100%): health healthy; system mode staging; HR login 200; `/api/auth/me` hr_admin, not super admin, has employee_form:verify; verification list/summary 200; sidebar "Verifikasi Pembaruan Data" visible; page renders empty state.
- Note: the UI environment badge only shows for APP_ENV=development, so staging shows no badge (no code change made).

### 16.6 Targeted staging E2E (STATUS: **PASS for all non-storage scenarios; storage promotion PARTIAL; 01H NOT LOCKED**) — 2026-09-27
Fixtures (synthetic, via authorized admin/HR APIs; scripts in /root/t01h, not in repo): masters T01H-OPS/T01H-PRJ/T01H-PKWT/T01H-STAF/T01H-SITE; employees T01H-STG-E1..E8 (E1..E4 API run, E5..E8 browser run); custom field `cf_t01h_ukuran_baju` (dropdown); user without verify (role manager); tenant B `T01HB` (employee_core enabled) with 1 pending submission (left undecided).
| Scenario | Result | Evidence |
|---|---|---|
| 1 APPROVE | PASS | Browser E5: compare HP 081200000005→081377770005, address, custom —→L; approve; master + custom official value written; portal "telah disetujui HR". 01F re-evaluation: E1 93.8%→100% immediately after approve (completeness_after + evaluated_at). |
| 2 REQUEST REVISION | PASS | Browser E6: note shown in portal banner; previous proposal kept; same submission id, status back to PENDING, revision_count 1, baseline/submitted_at recaptured; history keeps revision entry. |
| 3 REJECT | PASS | Browser E6: master unchanged (081200000006); portal "ditolak" + reason. |
| 4 CONFLICT | PASS | Browser E7 after HR PUT: conflict alert, approve disabled ("2 konflik belum diputuskan"), API approve w/o resolutions 409 (iter 18); use_proposed phone + keep_current address applied exactly. |
| 5 IDENTITY | PASS | Browser E8: identity alert; confirm disabled until checkbox; API approve w/o confirm_identity 422 (iter 18); name updated. |
| 6 SECURITY | PASS | No-verify user: menu hidden, page denied, API 403; portal session token → 401; tenant B submission → 404 (detail + approve). |
| Document/photo promotion | PARTIAL | Real staging storage integration not yet tested (Staging R2 NOT CONFIGURED); covered only by mocked-storage unit test (66/66, dev). |
- Product bug fixed (low, UI): identity confirmation label showed raw key "(full_name)" → now shows field label ("Nama lengkap (sesuai KTP)"). File: EmployeeUpdateVerificationDetailPage.jsx (frontend only; esbuild OK; verified by testing agent iteration_20). Synced to repo working tree, NOT committed.
- Not bugs (automation errors by testing agent): "phone not updated after approve" (E5 first submission only proposed marital_status) and "0 changes detected" (fields filled on wrong step).
- Fixture/env notes: E1 has a leftover empty DRAFT from a testing-agent retry; testing agent hardcoded passwords in scratch scripts 3×; scripts deleted (never committed) and passwords rotated each time.
- Ready for: final regression + cleanup once staging storage is tested (or the user accepts PARTIAL). 01H NOT LOCKED. Production Changed: NO.

### 16.7 Storage gap closed + final verification (STATUS: **DONE — 01H — HR Verification: LOCKED ✅**) — 2026-09-27
- Staging storage: dedicated bucket `payroll-hris-staging` (prefix `staging`) with a separate bucket-scoped token (same Cloudflare account, different keys from production — verified by comparison, no values printed). Guard checked before any write: bucket == payroll-hris-staging, != media-akunkita. Credentials only in gitignored `backend/.env`; local temp copies deleted. Production R2 never used.
| Storage scenario (browser, synthetic E9–E11) | Result |
|---|---|
| Document pending → approve → new official `documents` row, object copied to documents area; previous same-type document kept; pending file PROMOTED | PASS |
| Photo pending → approve → `employees.photo_path` points to new staging photo object (served 200 image/png) | PASS |
| Custom-field file → approve → retained official custom attachment (`employee_custom_field_values.files`), NO `documents` row | PASS |
| REJECT → files REJECTED, nothing promoted, no photo/doc | PASS |
| REQUEST REVISION → file stays active on same submission; replaced file `removed` (not promoted); only resubmitted file PROMOTED | PASS |
| All objects exist in staging bucket only (11/11 paths under `staging/`) | PASS |
- Product bug found + fixed (medium, display only): detail of an already DECIDED submission re-evaluated against live data → approved photo shown as "Konflik", other rows "Akan diterapkan". Fix: `hr_verification.decided_view()` + router `_detail()` derive states from the decision (`Diterapkan` / `Data saat ini dipertahankan` / `Tidak diterapkan`); `ChangeCompareTable` styles. Apply logic untouched. Verified by testing agent iteration_21 (100%).
- Also included: identity checkbox label fix (`full_name` → "Nama lengkap (sesuai KTP)", iteration_20).
- Final targeted regression: `test_hr_verification_01h.py` **70/70 PASS** (66 + 4 new decided-view assertions; covers 01G revision/public form + prefill, 01F re-evaluation, docs/photo/custom-file with mocked storage, security + cross-tenant 404, race, atomic rollback) on `hris_dev` (env override, storage stub); `tests/test_tenant_isolation.py` **12/12 PASS** (aiosqlite installed temporarily then removed — ENVIRONMENT); frontend esbuild OK. Not run: `test_stage3_rbac_tenant.py` (needs live backend with APP_ENV=development — EXPECTED); no separate 01F/01G suites exist in repo. Unrelated payroll/recruitment/attendance suites not run.
- Cleanup (dry-run → apply, hris_staging + bucket): 266 unique DB rows + 38 portal-verify audit rows + 11 objects removed (E1–E11 incl. leftover E1 draft, submissions/history, files, custom values, documents, masters T01H-*, fields cf_t01h_*, no-verify user, tenant T01HB). Integrity: 0 orphans, 0 T01H traces, bucket 0 objects, ledger m0003–m0010 intact, STG tenant + staging admin + HR verifier kept. 1 anonymous `public_rate_limits` row left (not attributable; expires).
- Credential hygiene: all browser E2E run with passwords read at runtime; HR verifier password rotated after E2E; automation artifacts containing passwords purged; no credential in repo/commit.
- Observation (pre-existing, not 01H): `GET /api/documents` list includes `storage_path` field.
- Production Changed: NO.



## Phase 18 — Phase 2A: Manajemen Aset (STATUS: **CP0 DONE · CP1 DONE — agent-tested, STOP waiting for user review** · CP2+ NOT STARTED) — 2026-09-28
Acuan wajib: `ASSET_BAST_FINAL_BLUEPRINT.md` (SHA256 `2d750349…8f67`). Canonical worktree `/app/.repo_work/Payroll`,
branch `feature/hrga-phase2a-asset-management` (basis `c93012c` = origin/main saat branch dibuat). Belum commit/push/PR.
Dev/test HANYA di `hris_dev` lokal via `backend/tests/dev_env_run.sh`. `/app/backend` & `/app/frontend` TIDAK dimirror.

### 18.0 CP0 — Worktree & blueprint (DONE)
- Canonical worktree + branch disetujui user; blueprint final dibaca penuh & disalin ke repo.

### 18.1 CP1 — Manajemen Aset (DONE — agent-tested, BELUM direview/di-lock user)
- Backend: modul `asset` ("Manajemen Aset"); permission `asset:{view,create,edit,delete}`, `asset_master:{view,create,edit,delete}`,
  `asset_value:{view,edit}`; preset GA Admin / GA Staff (tanpa logic berbasis nama role); master Kategori/Satuan/Kondisi/Status
  via generic master engine (7 kategori sistem tetap + validator mapping); CRUD aset + detail, status manual, relokasi,
  histori dasar (CREATED/UPDATED/STATUS_CHANGE/RELOCATION); kode otomatis `AST-{SEQ:6}` per company (alokasi + insert dalam
  satu transaksi, tanpa COUNT+1); `acquisition_value` DECIMAL(18,2) + redaksi backend; scope 01I di level SQL (reuse
  `core/data_scope.py`); audit log.
- Migration `m0012_asset_management`: dry-run/apply di hris_dev; rerun = SKIP (idempoten, tanpa duplikat, row count tetap).
- Frontend: grup sidebar top-level "Manajemen Aset" → hanya Daftar Aset + Pengaturan. Tanpa screenshot/Preview (instruksi user).
- Verifikasi (agent-tested): CP1 146/146 (+1 assertion AST-000001 company baru) · 01I 176/176 · 01H 70/70 · esbuild + `yarn build` PASS (warning pre-existing) ·
  `git diff --check` bersih · CP2 boundary scan PASS.
- Cleanup residue fixture 01H di hris_dev (marker T01H-/`PT Lain {RUN}`/`t01h.*@`); 30 audit public_form anonim tanpa marker dibiarkan.
- Known staging residue: 8 tabel aset kosong (0 row) di hris_staging — tidak disentuh; keputusan cleanup/retensi setelah review.
- Next (menunggu user): review CP1 → keputusan commit/push/PR, mirror/staging, cleanup residue staging; CP2 BELUM dimulai.

## Phase 17 — Upgrade 01I: Role & Data Scope (STATUS: **LOCKED ✅** — gap closing + targeted + staging m0011 + staging E2E + final regression DONE) — 2026-09-28

### 17.3 Gap closing + staging + final regression (2026-09-28) — 01I: LOCKED ✅
- **Non-Core-HR fail-closed** (`deps.require_permission` terpusat, `UNSCOPED_MODULES` = attendance, leave_overtime, payroll,
  recruitment, performance, mobilization, finance_request, accounting + resource `audit_log`): SELECTED_PROJECTS -> **403**
  ("Cakupan Data") untuk list/detail/write/approval operasional. Mencakup Attendance, Cuti, Lembur, Payroll, Recruitment
  (+pipeline/konversi), Schedules/Shift/kalender/periode (`/time/*`, `/schedules`), Audit Logs; digest pengingat
  `/mail/reminder/preview|send-now` -> full scope. ALL_TENANT tidak berubah. **Approval Workflow** (konfigurasi company-level)
  tetap RBAC.
  - Pengecualian **self-service** eksplisit (`require_permission(..., self_service=True)`): absen mandiri (`/attendance/me/today`,
    `/check-in`, `/check-out`, `/attendance/me`, koreksi milik sendiri), cuti/lembur milik sendiri (`mine=true`, ajukan untuk diri
    sendiri, batalkan milik sendiri), saldo `mine=true`, master Jenis Cuti (read). Cabang yang menyentuh karyawan lain di handler
    tetap `require_full_scope` -> 403. `/payroll/my/*` tidak berubah.
  - UI: Cuti & Lembur memaksa "Hanya pengajuan saya" ON + disabled untuk user restricted.
- **Atasan di luar scope**: `GET /employees/{id}` tidak mengirim nama/ID atasan bila di luar scope caller -> `supervisor_out_of_scope: true`
  + label "Di luar cakupan akses" (jabatan master tetap). Profil utama tetap 200. ALL_TENANT tetap melihat nama.
- **Revoke/re-add**: cabut akses company -> semua item `(company,user)` dihapus + baris scope jadi tombstone `status=revoked`,
  mode SELECTED_PROJECTS (company lain tidak disentuh; juga via Platform cabut Tenant Admin bila keanggotaan habis). Re-add
  (grant akses company / Platform tambah peran dari Tenant Detail) -> **SELECTED_PROJECTS tanpa project = "Tidak ada akses data"**
  sampai admin mengatur ulang. ALL_TENANT otomatis hanya untuk user existing saat m0011.
- Karyawan tanpa ACTIVE assignment: tetap hanya ALL_TENANT (tidak berubah).
- **Tests (agent-run):** `test_data_scope_01i.py` **176/176 PASS** (dev `hris_dev`, cleanup 0 sisa) · `test_hr_verification_01h.py`
  **70/70 PASS** · `test_tenant_isolation.py` **1 passed** (aiosqlite sementara lalu dihapus; requirements tidak berubah) ·
  frontend esbuild OK + webpack compiled (1 warning lama di EmployeeMigrationPage, tidak terkait).
- **m0011 di `hris_staging`** (lokal): DRY-RUN -> APPLY (tabel/index sudah ada; 1 default ALL_TENANT untuk 1 keanggotaan aktif)
  -> RERUN SKIP. Hitungan companies/users/memberships/employees/assignments tidak berubah; orphan item 0.
- **Staging E2E** (Live Preview, fixture sintetis T01ISTG): API smoke 14/14; browser: restricted list hanya Proyek Alpha, UUID luar
  scope -> "Data karyawan tidak ditemukan", atasan "Di luar cakupan akses (Pos Atasan …)", modul non-Core-HR 403, switch
  "Hanya pengajuan saya" terkunci; ALL_TENANT melihat 5 karyawan + nama atasan; UsersPage kolom Cakupan, dialog ubah ke
  Proyek Beta lalu kembali ke Semua Data; cabut akses -> baris hilang; re-add -> "Tidak ada akses data"; halaman 01H OK.
  Testing agent iteration_22: tanpa bug produk (route Cuti yang dicoba agen salah; diverifikasi ulang manual).
- **Cleanup**: fixture T01ISTG dihapus (0 sisa; scan teks seluruh tabel staging 0 residu); kredensial uji dihapus dari memory;
  skrip sementara dihapus. Staging kembali ke baseline + 1 baris scope m0011.
- Known (bukan blocker): DataTable merender kolom aksi di tabel desktop + list mobile sehingga `data-testid` aksi ganda (pola lama,
  bukan dari 01I). Modul non-Core-HR akan dibuat scope-aware di fase berikutnya (saat ini fail-closed).
- Production Changed: **NO**. Tidak ada push/PR/merge/deploy. 01J belum dimulai.

### 17.2 Implementation checkpoint (2026-09-27) — history (superseded by §17.3)
- Branch `feature/upgrade-01i-role-data-scope` in `/app/.repo_work/Payroll`, based on 01H `630ce8b`. Changes are synced into the working tree and **NOT committed** (per user). No push, PR, merge, deploy, or 01J.
- **Model** (`db.py`): `user_data_scopes` stores company_id + user_id + mode (unique `(company_id,user_id)`). `user_data_scope_items` stores company_id + scope_id + user_id + dimension='project' + ref_id (unique `(company_id,scope_id,dimension,ref_id)`). New indexes: `employees(company_id,project_id)` and `employee_assignments(company_id,assignment_status,project_id,employee_id)`. The adapter supports a server-built `$sql` filter key.
- **m0011** `migrations/m0011_role_data_scope.py` (additive, idempotent, ledger). Run on `hris_dev` only:
  - DRY-RUN, then APPLY: 2 tables + 2 indexes created; 10 ALL_TENANT defaults, exactly one per active membership (company,user); 0 cross-company rows.
  - RERUN: SKIP, 0 duplicates.
  - Employee and assignment checksums unchanged.
  - NOT run on staging. Staging tables are auto-created empty by startup `ensure_schema`; a missing row = ALL_TENANT, so staging behaviour is unchanged. The empty draft tables created by hot-reload were dropped (0 rows) and recreated with the final schema.
- **Engine** `app/core/data_scope.py`:
  - Scope is computed per (company, user) on every request and memoized on the request AuthContext only.
  - super_admin, tenant_admin and company_owner always get full scope.
  - A missing row = ALL_TENANT.
  - SELECTED_PROJECTS uses a SQL subquery on ACTIVE `employee_assignments` (the `employees.project_id` mirror is NOT used).
  - Fail-closed on empty items, invalid or foreign projects, or an unknown mode.
  - Helpers: `get_scope`, `with_scope`/`scope_filter`, `employee_scope_clause`, `ensure_employee_in_scope` (generic 404), `allowed_project_ids`, `has_all_tenant`, `require_full_scope`/`full_scope_dependency` (403), `ensure_target_project_allowed`, `set_user_scope` (transactional; validates projects belong to the same company).
- **Scope-aware endpoints:**
  - employees: list, stats, catalog projects, detail, PUT, PATCH status, DELETE, and create (target project must be in scope).
  - Profile 360: family, photo, timeline.
  - 01D: assignments list, assign, transfer (target in scope), end.
  - 01B: status-history, status-change.
  - Documents: list, detail, preview, download, PUT, DELETE, upload. Restricted users only get employee documents in scope; company and applicant documents return 404/403.
  - Contracts and certifications: list and all detail/write routes.
  - 01F completeness: employee detail, reevaluate, summary, list.
  - 01G monitoring (SQL) and its filter options.
  - 01H: summary (SQL count), list (SQL), detail, file, approve, reject, request-revision. Scope uses the employee's current project at review time.
  - Dashboard summary (employee-based counts; recent tenant activity hidden for restricted users).
  - Expiry calendar (`/reminders/expiry`).
- **Deliberately 403 for restricted users (full scope only):**
  - Employee import: `/employees/import/*` and all of `/employee-import/*`.
  - Config: 01F config (`employee_completeness:configure`, including bulk reevaluate) and 01G Form Builder config/preview.
  - Exports: attendance recap, leave, overtime, audit-log, payroll run export, statutory export.
  - Managing Cakupan Data (create user with scope / PUT scope).
- **API:**
  - `GET /api/users/data-scope/options`, `GET /api/users/me/data-scope`, `GET/PUT /api/users/{id}/data-scope` (audit `data_scope_update`; editing your own scope → 403).
  - `/users` list includes `data_scope`.
  - `POST /users` accepts optional `data_scope_mode` / `data_scope_project_ids`, validated before the account is created.
  - `/auth/me`, login and switch-company include `data_scope`.
- **UI:**
  - New components: `components/access/DataScopeBadge|DataScopePicker|DataScopeDialog.jsx`.
  - UsersPage: "Cakupan" column; "Atur Cakupan Data" action and dialog (mode + searchable multi-select + selected chips); scope picker in Tambah Pengguna; scope summary in the Edit dialog.
  - Topbar: pill shown for restricted or no-access users; the user menu always shows "Cakupan Data".
  - Restricted with no valid project is shown as "Tidak ada akses data".
  - No role rename and no master Project rename.
- **Tests (agent-run, dev `hris_dev`, R2 stub):**
  - `tests/test_data_scope_01i.py`: **101/101 PASS**, cleanup verified (0 leftover).
  - `tests/test_hr_verification_01h.py`: **70/70 PASS** (no 01H regression).
  - `tests/test_tenant_isolation.py`: **PASS** (aiosqlite installed temporarily, then removed; requirements unchanged).
  - Frontend: esbuild bundle OK and CRA "Compiled successfully".
- **Remaining gaps before LOCKED (all closed in §17.3):**
  1. Staging E2E: browser UI flow for Cakupan Data plus restricted-user journeys on the Live Preview.
  2. Final regression (broad suites, plus testing agent with strict credential hygiene).
  3. Run m0011 on staging (`hris_staging`) with dry-run → apply → rerun.
  4. Non-Core-HR list and detail endpoints (attendance/leave/overtime/payroll/recruitment views) are NOT scope-aware yet. Only their exports are blocked, so restricted users with those permissions can still see tenant-wide rows there. Decide: block or scope in a later phase.
  5. Employee detail supervisor name may reference an out-of-scope holder (org info only).
  6. Scope rows are not removed when access is revoked (re-grant reuses the old scope; fail-closed direction).
  7. Legacy employees without an ACTIVE assignment are visible only to ALL_TENANT users (by design).
- Production Changed: **NO**.

### 17.1 Audit (history)
- Audit document: `/app/UPGRADE_01I_ROLE_DATA_SCOPE_AUDIT.md`. Baseline: 01H LOCKED (local commit `630ce8b`, unpushed).
- Findings: RBAC = action-only (roles/permissions/user_company_roles, `require_permission`); **no data scope exists**. All Core HR employee routes (list, detail, profile, 01B, 01D, 01F, 01G links/monitoring, 01H, documents, contracts, certifications, dashboard) are TENANT + PERMISSION only, so any `employee:view/edit` holder can read and modify any tenant employee through a direct UUID. Exports (attendance/leave/overtime/payroll/audit) are unscoped.
- Authoritative placement: 01D ACTIVE `employee_assignments`; `employees.project_id` etc. are mirrors synced in the same transaction (direct edits blocked). STANDBY (01B) does not end the assignment. Future assignments are not supported.
- Recommended model: per user × company scope `ALL | PROJECTS(1..n)`. tenant_admin, company_owner and super_admin are forced ALL. Fail-closed (PROJECTS with no valid project → nothing visible). A missing row means ALL (keeps existing users unchanged; shown explicitly). Department/division/site: DEFER, with a dimension-generic schema.
- Proposed additive schema (not implemented): `m0011_data_scope` → `user_data_scopes`, `user_data_scope_items(dimension='project')`, index `employees(company_id, project_id)`.
- Enforcement: resolve scope once per request in AuthContext. SQL predicate for lists/counts/joins (01H in-Python filter becomes SQL). `get_scoped_employee()` returns a generic 404 on detail/sub-routes/writes/01H decisions. ALL-only guard for import/config/bulk. Restricted users get 403 on non-Core-HR exports (fail-closed). A route-coverage test is added.
- Critical cases: transfer A→B means access moves at commit. Standby with no assignment is visible to ALL-scope users only. A restricted user sees full history only while the employee is in scope. 01H follows the employee's current project and approve re-checks scope.
- UI: UsersPage "Cakupan Data" (Semua Data Perusahaan / Project Tertentu with searchable multi-select), "Cakupan" column, Topbar scope indicator, list banners.
- Sequence (6 steps). Risk: MEDIUM-HIGH (breadth). Next: STOP for review. No code, push, PR, merge, deploy, or 01J. Production Changed: NO.



## 3) Next Actions (immediate)
**Current status (2026-09-27): 01F LOCKED ✅ · 01G PUBLIC EMPLOYEE FORM LOCKED ✅ · 01G FORM BUILDER LOCKED ✅ (PR #16 merged) · 01H — HR Verification: LOCKED ✅ (see §16.7) — final local commit, push/PR pending user approval · 01I — Role & Data Scope: **LOCKED ✅** (01I 176/176, 01H 70/70, staging m0011 + E2E done; local clean commit on branch `feature/upgrade-01i-role-data-scope`, push/PR pending user approval; see §17.3) · Production Changed: NO.**

**Update 2026-09-28: Phase 2A — Manajemen Aset: CP0 DONE · CP1 DONE (agent-tested, STOP waiting for user review; see §18.1) · CP2+ NOT STARTED · Production Changed: NO · Staging Changed: NO additional changes.**

Status 01E (history): **01E-A DONE (checkpoint)** + **01E-B IN PROGRESS**.

Next actions yang aktif sekarang (sesuai instruksi user):
1) Review & update plan/todo: DONE.
2) 13.B.1 UI: DONE (agent-tested) — STOP, menunggu review user.
3) Berikutnya (setelah review): 13.B.2 compile/yarn build + visual QA desktop/tablet/mobile → STOP.

---

## 4) Success Criteria
- Runtime aman dan benar-benar staging:
  - DB `hris_staging` @ `127.0.0.1:3306`
  - `AUTO_SEED=false`
  - storage endpoint lokal (`s3-staging-local`)

- Upgrade 01C (LOCKED): sesuai laporan 01C.
- Upgrade 01D (COMPLETED): sesuai laporan 01D.

- Upgrade 01E (FINAL, hanya bila 01E-B selesai):
  - UI Import & Migrasi end-to-end sesuai flow (template → upload → analyze → validate → preview → commit eksplisit).
  - Badge klasifikasi NEW/UPDATE/UNCHANGED/CONFLICT/ERROR + diff field untuk UPDATE.
  - Riwayat impor + detail batch lama read-only.
  - Download hasil validasi/error tanpa nilai sensitif full.
  - Duplicate file hash: warning jelas + tidak ada silent re-commit.
  - Performance nyata tercatat (500/1000/5000) per tahap.
  - Visual QA desktop/tablet/mobile.
  - Regression lintas modul stabil + `testing_agent_v3` dilaporkan jujur.
  - Cleanup hanya ZT01E.
  - Restart x2: m0006 skip, tidak ada mutasi.
  - Final report `/app/UPGRADE_01E_EMPLOYEE_MIGRATION_REPORT.md` dengan `Production Changed: NO`.

**Catatan:** Jangan menandai 01E “complete/lock” sebelum seluruh success criteria di atas benar-benar dicapai dan direview.

---

## Appendix — Cleanup & Open Notes

### Cleanup yang harus dipastikan
- Upgrade 01E: cleanup final hanya fixture/batch/file **ZT01E**.
- Tenant `ZT01B170909`: **outside scope** → jangan dihapus/diubah. (Cek 2026-09-26: NOT PRESENT.)
- 01F final cleanup: DONE (scoped, 2026-09-26) — ZT01F fixtures + provenance-proven audit `completeness_*` removed; other fixtures kept. **01F status: LOCKED ✅ (2026-09-26).**
- PR preparation (later, separate task): git cleanup — remove `test_reports/iteration_27.json` (and other testing artifacts, e.g. iteration_26.json from auto-commit 9e227cd) from the product commits/PR; keep `.env.example` files out.

### Infrastructure / Pre-Production Issues (separate from 01F — NOT part of 01F scope)
- **MariaDB staging: log "InnoDB: The change buffer is corrupted or has been removed on upgrade to MariaDB 11.0 or later"** at every start since 2026-09-26 00:27, after the runtime changed from **MariaDB 11.8.9** (mariadb.org binary) to **10.11.18** (Debian package) on the same datadir `/app/.local-data/mariadb/data` (version downgrade). At the moment CHECK TABLE 68/68 OK and the app runs normally. Related: after a container restart, supervisor `payroll-dev-mariadb` can go FATAL ("can't find command /usr/sbin/mariadbd" at boot) → the backend fails to start until MariaDB is started manually.
- Must be resolved **before production deployment**, through a **separate task + backup first**. Do NOT upgrade/downgrade/rebuild the database as part of 01F or without explicit approval.

### Catatan terbuka / guardrails
- `.env.example` dan `backend/.env.example` memiliki perubahan dokumentasi `AUTO_SEED=false`; **tetap dikecualikan** dari commit 01E.
- Tidak ada push/PR/merge/deploy untuk 01E (default: local-only).
- Endpoint import lama wajib dipertahankan.
- Jangan menghapus data baseline/PT REAL/01B–01D/legacy.
- Setelah final report 01E selesai: **STOP** dan tunggu review user (jangan mulai 01F).
