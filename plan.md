# Development Plan — Payroll Run + Renewal Kontrak + Email Reminder (SMTP) + Import Excel (Karyawan)

## 1) Objectives
- Menyediakan **Payroll bulanan per perusahaan** yang patuh regulasi Indonesia:
  - Basic salary + allowances + overtime
  - Potongan BPJS (Kes 1%/4%, JHT 2%/3.7%, JP 1%/2% + cap)
  - PPh 21 metode **TER (PMK 168/2023)** + rekonsiliasi Pasal 17 pada masa pajak terakhir (Desember)
  - Alur **calculate → submit → approval → mark paid → payslip PDF + export Excel**
- Menyediakan **Perpanjang Kontrak 1 klik** dari **Kalender Masa Berlaku** dan dari aksi di tab kontrak detail karyawan.
- Menyediakan **Email reminder otomatis** masa berlaku kontrak/sertifikasi/dokumen lewat **SMTP perusahaan**, termasuk:
  - konfigurasi SMTP per perusahaan (password write-only)
  - reminder windows (H-*)
  - jadwal pengiriman WIB (Asia/Jakarta)
  - pratinjau digest, send-now, dan log histori
- Menyediakan **Impor karyawan dari Excel** (template → validasi → commit) termasuk opsi basic salary + PTKP.
- Menjaga UI **elegan & profesional**, konsisten dengan design system proyek.

> Status fitur aplikasi: bundle fitur (Payroll Run + Renewal Kontrak + Email Reminder + Import Excel) **sudah terimplementasi** dan sebelumnya **agent-tested** pada environment Emergent.

**Objective baru (governing request): Productionization untuk Coolify**
- Migrasi stack menjadi **1 repo** (root) dengan base directory `./backend` dan `./frontend`.
- Deploy di Coolify memakai **Docker build strategy** (bukan Emergent supervisor).
- **Database FULL MariaDB** menggantikan MongoDB (Motor) sepenuhnya.
- Tambahkan **phpMyAdmin** sebagai GUI service.
- Storage file/dokumen pindah dari Emergent object storage ke **Cloudflare R2 (S3-compatible)** via boto3.
- Target domain aplikasi: **`hris.akuntakita.com`**.
- Seed/demo data tetap dipertahankan (via `AUTO_SEED`).

---

## 2) Implementation Steps

### Phase 1 — Core POC (isolated, mandatory: `/app/backend/test_core.py` overwrite) ✅ **Completed (agent-tested)**
**User stories**
1. Sebagai HR, saya ingin kalkulasi BPJS+PPh21 TER akurat agar slip gaji sesuai regulasi.
2. Sebagai Finance, saya ingin rekonsiliasi pajak Desember sesuai Pasal 17 agar total setahun tepat.
3. Sebagai Admin, saya ingin template Excel + validasi jelas agar impor massal tidak merusak data.
4. Sebagai HR, saya ingin slip gaji bisa dibuat PDF agar bisa dibagikan/diarsipkan.
5. Sebagai HR, saya ingin reminder expiry bisa dibangun dan dikirim via SMTP agar tidak ada kontrak/dokumen terlewat.

**Steps (POC must be green before Phase 2)**
- Implement POC di `backend/test_core.py` (tanpa FastAPI/DB) untuk:
  - (a) **TER integrity**: hardcoded tables A/B/C; assert counts 44/40/41, contiguous, spot-check rate.
  - (b) **Monthly payslip calc**: multiple skenario (threshold 0 tax, mid TK/0, K/3, high earner w caps, overtime, proration unpaid absence, ad-hoc earning/deduction).
  - (c) **December annual recalc**: simulasi Jan–Nov TER withholding lalu compute Pasal 17 annual dan delta.
  - (d) **Excel roundtrip**: generate template, write sample rows, parse+validate; assert error messages Bahasa Indonesia.
  - (e) **Payslip PDF**: render PDF bytes; assert `%PDF` dan ukuran non-trivial.
  - (f) **SMTP send**: dummy SMTP (aiosmtpd), kirim HTML digest.
  - (g) **Expiry selection logic**: pilih item berdasarkan windows hari.
- Exit criteria: `python backend/test_core.py` lulus end-to-end.

**Result**
- `test_core.py`: **186/186** pemeriksaan lulus.

---

### Phase 2 — Backend V1 (build around proven core) ✅ **Completed (agent-tested)**
**User stories**
1. Sebagai HR, saya ingin menjalankan payroll per periode (bulan/tahun) agar gaji bisa diproses massal.
2. Sebagai HR, saya ingin mengubah lembur/absen/adjustment per karyawan agar hasil payroll sesuai kondisi aktual.
3. Sebagai Approver, saya ingin menyetujui payroll run via workflow yang sama dengan modul lain.
4. Sebagai Karyawan, saya ingin melihat dan mengunduh **slip gaji saya sendiri**.
5. Sebagai Admin, saya ingin mengatur SMTP + jadwal reminder per perusahaan dan menguji kirim email.

**Core modules (new/updated)**
- `app/core/ter.py`: bracket tables (A/B/C) + resolver kategori dari PTKP.
- `app/core/payroll.py`: engine murni (proration, overtime, BPJS caps, TER bulanan, Pasal 17 annual/Dec, non-NPWP toggle default OFF).
- `app/core/pdf.py`: renderer slip gaji PDF (reportlab).
- `app/core/excel.py`: template + parse + validate employee rows (openpyxl).
- `app/core/mailer.py`: SMTP client (TLS/SSL/none), password write-only, never logged.
- `app/core/scheduler.py`: APScheduler AsyncIOScheduler on startup; schedule WIB + idempotency via reminder_logs.

**DB collections (tenant-scoped via `TenantRepository`)**
- `payroll_components`, `employee_salaries`, `employee_salary_history`, `payroll_runs`, `payroll_items`, `smtp_settings`, `reminder_settings`, `reminder_logs`.

**Routers**
- `app/routers/payroll.py`:
  - payroll catalog/config, komponen gaji CRUD, struktur gaji karyawan, payroll run lifecycle (create/recalculate/submit/approve/reject/mark-paid/delete), export excel, payslip pdf.
  - self-service: `/api/payroll/my/payslips` + `/api/payroll/my/payslips/{item_id}/payslip`.
- `app/routers/contracts.py`:
  - `GET /contracts/{id}/renew-preview`, `POST /contracts/{id}/renew`.
- `app/routers/employees.py`:
  - `GET /employees/import/template`, `GET /employees/import/columns`, `POST /employees/import/validate`, `POST /employees/import/commit`.
- `app/routers/settings_mail.py`:
  - SMTP settings, test email, reminder settings, preview, send-now, logs.

**RBAC / Modules / Seed**
- Permissions payroll/payroll_component/employee_salary + employee own payslip access.
- Seed top-up mekanisme agar role lama mendapat permission baru tanpa reset.

**Deps**
- `reportlab`, `openpyxl`, `apscheduler`, `aiosmtpd`.

**Phase exit**
- Backend smoke: `/app/backend/smoke_api.py` green.

**Result**
- `smoke_api.py`: **137/137** lulus.
- UI-level backend testing (testing agent): **109/111** lulus.

---

### Phase 3 — Frontend V1 (UI parity + UX) ✅ **Completed (agent-tested via compile + preview screenshots)**
**User stories**
1. Sebagai HR, saya ingin melihat daftar payroll run per periode dan statusnya.
2. Sebagai HR, saya ingin membuka detail payroll run dan mengedit adjustment per karyawan lalu recalculation.
3. Sebagai Approver, saya ingin approve/reject payroll dari halaman detail dengan feedback.
4. Sebagai Karyawan, saya ingin halaman “Slip Gaji Saya” untuk download PDF.
5. Sebagai Admin, saya ingin UI setting SMTP + reminder windows + jadwal + log agar pengingat dapat diaudit.
6. Sebagai HR, saya ingin perpanjang kontrak dari kalender masa berlaku tanpa input berulang.
7. Sebagai HR Admin, saya ingin impor karyawan dari Excel dengan validasi baris yang jelas.

**Pages/UX (reuse tokens + shared components)**
- Routing + nav:
  - Update `frontend/src/App.js` menambahkan routes:
    - `/payroll/runs`, `/payroll/runs/:runId`, `/payroll/components`, `/payroll/salaries`, `/payroll/config`, `/payroll/my-payslips`, `/employees/import`, `/settings/mail`.
  - Update `frontend/src/lib/nav.js`:
    - Grup baru **“Payroll & Pajak”**.
    - Item **“Slip Gaji Saya”** ditampilkan tanpa permission (resource `null`), dan `filterNav` mendukung `resource=null`.
    - Entry placeholder modul payroll disembunyikan.

- Payroll:
  - `PayrollRunsPage` (list + create period dialog) ✅
  - `PayrollRunDetailPage` ✅
  - `PayrollComponentsPage` (CRUD) ✅
  - `EmployeeSalariesPage` + `SalaryEditorDialog` ✅
  - `PayrollConfigPage` ✅

- Employee self-service:
  - `MyPayslipsPage` ✅

- Contract renewal:
  - `ContractRenewDialog` ✅
  - Integrasi tombol **Perpanjang** pada `ExpiryCalendarPage` ✅
  - Integrasi aksi **Perpanjang kontrak** pada dropdown aksi kontrak di `EmployeeDetailPage` ✅

- Excel import:
  - `EmployeeImportPage` ✅
  - `EmployeesPage` tombol “Impor Excel” ✅

- SMTP & reminders:
  - `MailSettingsPage` ✅

- Utilities:
  - `frontend/src/lib/download.js` ✅

**Quality gates (done)**
- Compile check: `esbuild` bundle test clean.
- Visual check: screenshot preview.

---

### Phase 4 — Harden · Regression · Security ✅ **Completed (E2E + fix loop + cleanup)**
**User stories**
1. Sebagai admin multi-perusahaan, saya ingin tenant isolation payroll/reminder/import tetap aman.
2. Sebagai auditor, saya ingin setiap perubahan payroll/salary/reminder/renewal terekam audit log.
3. Sebagai HR, saya ingin histori reminder terlihat agar bisa membuktikan email terkirim.
4. Sebagai pengguna, saya ingin error message jelas (Bahasa) saat validasi Excel gagal.
5. Sebagai karyawan, saya ingin dijamin tidak bisa mengakses slip gaji orang lain.
6. Sebagai user, saya ingin UX rapi: loading/empty/error state konsisten.

**E2E coverage**
- Payroll lifecycle lengkap, self-service, import excel, contract renewal, mail settings, tenant isolation.

**Bugs found & fixed (all resolved)**
- PayrollConfigPage crash → response normalization.
- MailSettingsPage crash → flatten preview items.
- Logout tertutup toaster → pindah posisi.
- Hydration warning → perapihan markup.
- Enrich komponen gaji → backend enrich.
- Silent reload untuk stability.

**Cleanup & demo data state (restored)**
- Dataset demo dipulihkan.

---

### Phase 5 — Coolify Productionization (Docker + MariaDB + phpMyAdmin + R2) 🟨 **In Progress (new)**
**Tujuan fase**
1. Aplikasi dapat di-build dan di-deploy di Coolify dengan **Docker build strategy** dalam **1 project**.
2. Backend memakai **MariaDB** (bukan MongoDB) untuk semua modul.
3. `phpMyAdmin` tersedia sebagai service GUI.
4. Upload/download dokumen memakai **Cloudflare R2** (S3-compatible) dan tidak bergantung pada Emergent.
5. Tetap mempertahankan seed/demo data (`AUTO_SEED=true`).

#### Phase 5A — Repo layout & Docker build baseline
- Root repo tetap 1, dengan:
  - `./backend` untuk FastAPI
  - `./frontend` untuk React (craco)
- Tambahkan file:
  - `docker-compose.yml` di root (4 services: `mariadb`, `phpmyadmin`, `backend`, `frontend`)
  - `backend/Dockerfile` (Python 3.11, install deps, run uvicorn)
  - `frontend/Dockerfile` (multi-stage: Node build → Nginx static)
  - `frontend/nginx.conf` (serve React + reverse-proxy `/api` → `backend:8001`)
  - `.dockerignore` (root, backend, frontend) untuk build cepat & aman
- Frontend:
  - Pastikan build output CRA ada di `/frontend/build`.
  - Nginx fallback `try_files $uri /index.html`.

#### Phase 5B — Database migration: MongoDB (Motor) → MariaDB (FULL)
**Keputusan yang dikunci**: FULL MariaDB menggantikan MongoDB.

**Langkah implementasi**
- Ubah `app/core/config.py`:
  - Ganti `MONGO_URL` menjadi `DATABASE_URL` atau komponen `DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME`.
- Ganti `app/core/db.py`:
  - Implementasi adapter async berbasis SQLAlchemy Core + asyncmy, namun **menyediakan API kompatibel** dengan pemakaian existing code:
    - `get_db()` mengembalikan object `DB` yang mendukung `db.<collection>` / `db[collection]`.
    - Collection API: `find/find_one/insert_one/insert_many/update_one/update_many/delete_one/delete_many/count_documents/distinct/find_one_and_update/replace_one`.
    - Cursor API: `sort/skip/limit/to_list`.
  - Dukungan filter ops yang dipakai codebase:
    - `$ne,$in,$nin,$regex/$options,$or,$gt,$gte,$lt,$lte,$exists`
    - khusus: dotted key `components.component_id` (query JSON)
  - Dukungan update ops yang dipakai:
    - `$set,$inc,$push,$setOnInsert`, `upsert=True`
  - Ekspor konstanta kompatibilitas:
    - `ASCENDING=1`, `DESCENDING=-1`
    - `ReturnDocument` (enum minimal: BEFORE/AFTER)
    - `NO_ID` (ignored, tapi diterima untuk kompat)
  - Datetime disimpan `DATETIME(6)` UTC naive (mimic behavior sebelumnya).
- Skema MariaDB:
  - Buat tabel per collection (≈38), minimal kolom:
    - `id CHAR(36) PK`, `company_id CHAR(36)`, `status VARCHAR`, `created_at`, `updated_at`, `created_by`, `updated_by`
  - Kolom spesifik per collection dibuat sesuai field yang sudah diekstrak dari code.
  - Field kompleks disimpan sebagai JSON:
    - `payroll_items` (earnings/deductions/bpjs/tax/totals/adjustments/attendance/period)
    - `payroll_runs` (totals/history/skipped/statutory_snapshot)
    - `employee_salaries.components`, `audit_logs.before_value/after_value/changed_fields`, `config_overrides.value`
  - Index/unique constraints disesuaikan dari `ensure_indexes()` (migrasi menjadi DDL index MariaDB).
- Perubahan router yang mengimpor pymongo:
  - `employees.py` (ReturnDocument), `dashboard.py` (ASC/DESC), `audit_logs.py`.
  - Ganti import dari `pymongo` menjadi import dari `app.core.db`.
- Update `server.py`:
  - `health` ping ke MariaDB.
  - `ensure_indexes()` menjadi `ensure_schema()` / `ensure_indexes_sql()`.

**Validation**
- Jalankan backend lokal menggunakan MariaDB (compose) dan pastikan:
  - login, list master, employees, payroll run list/detail, import validate/commit, reminder preview/log.
  - seed sukses tanpa duplikasi.

#### Phase 5C — Storage migration: Emergent → Cloudflare R2
- Ganti `app/core/storage.py`:
  - Implementasi R2 via boto3:
    - `put_object(path, data, content_type)`: upload ke bucket
    - `get_object(path)`: download bytes + content-type
    - (opsional) `delete_object(path)` untuk hard delete (tetap boleh soft delete di DB)
  - Env placeholders (Coolify env):
    - `R2_ACCOUNT_ID`
    - `R2_ACCESS_KEY_ID`
    - `R2_SECRET_ACCESS_KEY`
    - `R2_BUCKET_NAME` (**perlu nilai final dari user**)
    - `R2_ENDPOINT_URL` (atau derive dari account id)
    - `R2_PUBLIC_BASE_URL` (opsional bila butuh direct URL; default tetap streaming via API)
  - Tetap gunakan namespace path eksisting: `hris-payroll/companies/{company_id}/documents/{file_id}.{ext}`.

**Catatan**
- Kredensial dari `CredProduction.txt` tidak boleh di-commit atau di-print ke log.
- Token/key yang terlanjur dishare via chat sebaiknya direvoke/rotate setelah deploy stabil.

#### Phase 5D — Coolify networking: single domain + reverse-proxy
- Service `frontend` (Nginx) menjadi entrypoint HTTP.
- Nginx config:
  - `/` → React static
  - `/api` → proxy_pass ke `http://backend:8001` (tanpa mengubah prefix `/api`)
- CORS:
  - Untuk production single domain, `CORS_ORIGINS` bisa diset `*` atau domain tunggal.
  - Backend tetap support list origins (comma-separated) untuk fleksibilitas.

#### Phase 5E — Seed preservation
- Pastikan `AUTO_SEED=true` tetap bekerja di MariaDB.
- Porting seed:
  - Port fungsi `_upsert` dan semua insert demo agar menggunakan adapter SQL.
  - Pastikan behavior `upsert` dan uniqueness (roles/permissions/modules, company_settings unique per company, dsb).

#### Phase 5F — Documentation update (README)
- Tambahkan section Deploy to Coolify:
  - Arsitektur 4 service
  - Env vars backend/frontend
  - Setup domain `hris.akuntakita.com`
  - phpMyAdmin access
  - R2 config

#### Phase 5G — Final verification
- Smoke test endpoints (curl) dan UI flows utama.
- Minimal acceptance:
  - `/api/health` healthy
  - login berhasil
  - daftar payroll runs muncul
  - create payroll run + recalc tidak error
  - dokumen upload/download bekerja via R2
  - reminder preview & send-now tidak crash

---

## 3) Next Actions (immediate)
1. **Implement Phase 5A–5C** (Docker + MariaDB adapter + R2 storage) di repo `akuntakitatech-design/Payroll`.
2. Setelah perubahan jalur backend selesai dan Docker build sudah green, user mengisi final env di Coolify:
   - MariaDB credentials (Coolify service vars)
   - R2 env vars (bucket name belum diinformasikan)
3. UAT:
   - SMTP nyata (menu Pengaturan → Email & Pengingat)
   - Upload dokumen (verifikasi R2)

---

## 4) Success Criteria
**Fitur aplikasi (sudah ada)**
- `python backend/test_core.py` passes (**186/186**).
- Backend smoke `python backend/smoke_api.py` passes (**137/137**).
- Payroll run lifecycle lengkap; slip PDF & rekap Excel dapat diunduh (agent-tested).
- Employee hanya dapat mengakses slip gaji sendiri; tenant isolation enforced (agent-tested).
- Contract renewal 1-klik dan Excel import berjalan (agent-tested).

**Productionization (baru, harus dicapai di Phase 5)**
- `docker compose build` sukses (backend + frontend).
- Coolify deploy 1 project sukses dengan 4 services: `mariadb`, `phpmyadmin`, `backend`, `frontend`.
- Backend menggunakan MariaDB (tidak ada dependency MongoDB yang diperlukan saat runtime).
- phpMyAdmin dapat diakses (domain/subdomain sesuai Coolify).
- Upload/download dokumen bekerja via Cloudflare R2.
- Seed/demo data berhasil di MariaDB saat `AUTO_SEED=true`.

**Open item yang dibutuhkan dari user**
- Nama bucket R2 untuk dokumen (nilai final `R2_BUCKET_NAME`).