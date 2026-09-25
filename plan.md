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

### Update fokus (fase saat ini)
Fokus aktif saat ini:
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

## 3) Next Actions (immediate)
Status saat ini: **01E-A DONE (checkpoint)** + **01E-B IN PROGRESS**.

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
- Tenant `ZT01B170909`: **outside scope** → jangan dihapus/diubah.

### Catatan terbuka / guardrails
- `.env.example` dan `backend/.env.example` memiliki perubahan dokumentasi `AUTO_SEED=false`; **tetap dikecualikan** dari commit 01E.
- Tidak ada push/PR/merge/deploy untuk 01E (default: local-only).
- Endpoint import lama wajib dipertahankan.
- Jangan menghapus data baseline/PT REAL/01B–01D/legacy.
- Setelah final report 01E selesai: **STOP** dan tunggu review user (jangan mulai 01F).
