# UPGRADE 01A — AUDIT & BASELINE EXISTING HRGA

| | |
|---|---|
| **Sistem** | HRIS & Payroll SaaS (existing) → target: Sistem HRGA PT REAL berbasis proyek |
| **Repository** | `akuntakitatech-design/Payroll` |
| **Tanggal audit** | 2026-09-25 (UTC) |
| **Sifat audit** | READ-ONLY terhadap produksi. Tidak ada deploy, migration, seed, perubahan data/credential/DNS, commit, push, atau PR. |
| **Lokasi laporan** | `/app/UPGRADE_01A_AUDIT_BASELINE.md` (belum di-commit, sesuai instruksi) |

> Semua nilai secret ditulis sebagai `CONFIGURED`. Tidak ada password, token, atau key di laporan ini.

---

## 1. Executive Summary

1. **Baseline source = MATCH.** Produksi menjalankan kode yang sama dengan `main @ 9107807` (PR #11, Time Management V1). Buktinya: 108/108 route GET ada di produksi, 326/384 string UI unik PR #11 ada di bundle produksi, dan startup auto-sync tidak mendeteksi selisih skema pada clone.
2. **Database produksi saat ini adalah data DEMO/UAT, bukan data operasional PT REAL.** Hanya ada 2 perusahaan demo (NEP, KBS), 12 user yang semuanya akun demo, dan 12 baris karyawan (8 ditandai demo, 3 hasil konversi rekrutmen, 1 lainnya).
3. **Tiga risiko keamanan kritis ada di produksi saat ini** (lihat bagian 13 dan 19):
   - (a) Ke-12 akun produksi, termasuk `super_admin`, masih memakai **password demo default**. Password itu tertulis di source (repo **PUBLIC**) dan tampil di halaman login.
   - (b) Semua dokumen di R2 (KTP, dokumen pelamar, dokumen perusahaan) **bisa diunduh tanpa login** lewat URL publik `r2.dev`.
   - (c) **AUTO_SEED=true** di produksi menjalankan UPDATE ke data bisnis setiap kali backend start, termasuk menautkan karyawan ke user demo **berdasarkan nama tanpa filter perusahaan**.
4. **Regression baseline:** fitur inti berfungsi. Hasilnya: API 126/128 + 15/15 tulis, UI 40/41 dan 9/10, smoke suite 45/45, 111/111, 45/45 (smoke_time 43/45 karena data jadwal), recruitment E2E 14/14, core payroll 186/186, tenant isolation PASS. Tidak ada bug kritis fungsional. Ada 3 temuan fungsional minor/menengah (bagian 12).
5. **Arsitektur staging (production-clone)** sudah disiapkan sesuai arahan: clone DB identik (MariaDB 11.8.9, 57 tabel, 324 index, baris 100% sama) dan clone storage lokal. Live Preview sekarang memakai clone ini, dan produksi tidak disentuh.
6. **Rekomendasi: CONDITIONAL GO untuk 01B.** Development 01B di staging boleh dimulai. **Deploy 01B ke produksi harus ditahan** sampai 3 risiko kritis ditangani dan AUTO_SEED di produksi dimatikan (bagian 21–22).

---

## 2. Source Baseline

```
Repository              : akuntakitatech-design/Payroll (visibility: PUBLIC)
Default branch          : main
Branch lain di remote   : tidak ada (git ls-remote hanya main)
Production branch       : main (disimpulkan; konfigurasi Coolify tidak dapat diakses dari audit ini)
Production commit       : 9107807 (Merge PR #11 feature/time-management-v1, 2026-09-21 20:19 +07)
Audit date              : 2026-09-25
Source snapshot dibandingkan dengan : clone git main @ 9107807 (bukan ZIP)
Status                  : MATCH
```

**Metode verifikasi.** Seluruhnya read-only dan hanya request GET tanpa autentikasi:

| Uji | Hasil |
|---|---|
| 108 route GET di OpenAPI kode HEAD diuji ke `hris.akuntakita.com/api/*` | 105 → 401 (route ada, butuh login), 3 → 200 (public), **0 → 404** |
| Kontrol negatif (`/api/zzz-tidak-ada`, `/api/time/zzz`) | 404, jadi pembeda 401 vs 404 valid |
| String UI unik yang ditambahkan PR #11, dicari di bundle produksi `main.55636d8b.js` | 326/384 ditemukan. Sisanya fragmen JSX yang ter-minify atau karakter unicode (`…`, `—`) yang ter-escape |
| Skema: auto-sync startup backend HEAD terhadap clone DB produksi | 0 kolom/index ditambahkan, jadi skema produksi = skema kode HEAD |

Catatan: `pushed_at` repo (2026-09-23) lebih baru dari commit HEAD (2026-09-21). Kemungkinan ada push ke branch lain yang kemudian dihapus. Tidak ada branch lain saat audit. **Konfirmasi final branch/commit di Coolify tetap disarankan** (Coolify → Application → Source).

---

## 3. Infrastructure Map

| Komponen | Implementasi existing |
|---|---|
| **Frontend** | React 19 (CRA/craco) + shadcn/ui + Tailwind. Produksi: image Nginx (`frontend/Dockerfile`, `nginx/default.conf.template`) yang menyajikan SPA dan mem-proxy `/api/` → `BACKEND_UPSTREAM` |
| **Backend/API** | FastAPI (Python 3.11), `server.py` + `app/routers/*` (23 router), `app/core/*` (26 modul) |
| **Database** | MariaDB **11.8.9**, DB `default`, 57 tabel, ±4,6 MB. Akses lewat **adapter bergaya Mongo di atas SQLAlchemy Core + asyncmy** (`app/core/db.py`, 1.617 baris: `db.collection.find_one/update_one/...`). Tabel relasional dengan kolom eksplisit + kolom JSON `extra` |
| **Object storage** | Cloudflare R2 (S3 API, boto3), bucket `media-akunkita`, prefix `hris-payroll/`, `R2_PUBLIC_BASE_URL` diisi (akses publik r2.dev aktif) |
| **Authentication** | Email + password (bcrypt), JWT access + refresh token, lockout setelah N percobaan (`LOGIN_MAX_ATTEMPTS`/`LOGIN_LOCK_MINUTES`). Token disimpan di `localStorage` frontend |
| **Multi-company / tenant** | Kolom `company_id` di semua tabel bisnis. `user_company_roles` (user ↔ company ↔ role). `TenantRepository` memaksa filter `company_id`. Header company aktif lewat `deps.get_auth` |
| **Role/Permission** | RBAC `resource:action` (`app/core/rbac.py`). 8 role sistem, 166 permission, tabel `roles`, `permissions`, `role_permissions`, `user_company_roles` |
| **Migration** | **Tidak ada migration berversi.** Saat startup (`ensure_indexes` → `_sync_schema`): `metadata.create_all` + `ALTER TABLE ADD COLUMN` untuk kolom yang hilang + buat index/unique. Hanya additive, tapi implisit, tanpa ledger, dan **berjalan otomatis di produksi setiap redeploy** |
| **Seed** | `app/seed.py` + `app/seed_time.py`, dipanggil saat startup bila `AUTO_SEED=true` (lihat bagian 4) |
| **Scheduler** | APScheduler in-process (`app/core/scheduler.py`), untuk pengingat email kedaluwarsa. Aktif jika `ENABLE_SCHEDULER` true dan tidak read-only |
| **Deployment** | Coolify (server `<server-redacted>`). Frontend & backend container terpisah + MariaDB service. `docker-compose.yml` di root sebagai referensi |
| **Domain** | `https://hris.akuntakita.com` (frontend + `/api` di origin yang sama) |

**Konfigurasi produksi** (nilai disamarkan):

```
DATABASE_URL: CONFIGURED (2 entri di file kredensial: hostname internal Coolify + IP publik:port)
JWT_SECRET: CONFIGURED            CORS_ORIGINS: https://hris.akuntakita.com
R2_STORAGE: CONFIGURED            R2_PUBLIC_BASE_URL: CONFIGURED (public r2.dev)
AUTO_SEED: true   <-- RISIKO      MAX_UPLOAD_MB: 15        CLIENT_MAX_BODY_SIZE (nginx): 25m
ACCESS_TOKEN_EXPIRE_MINUTES: 720  ENABLE_SCHEDULER: (default on)
phpMyAdmin (PMA_*): CONFIGURED, port DB publik terbuka ke internet
```

**Lingkungan staging (dibuat pada audit ini, sesuai arahan production-clone):**

```
PRODUKSI (read-only) --mariadb-dump --single-transaction--> STAGING DB  hris_staging (MariaDB 11.8.9 lokal)
R2 produksi (list/get saja) --------------------------------> STAGING S3  (rclone serve s3, lokal)
Live Preview backend  -> staging (READ_ONLY=false, AUTO_SEED=false, scheduler off, JWT_SECRET berbeda)
Kredensial produksi TIDAK ada di backend/.env preview (disimpan terpisah di /root, di luar repo)
Refresh clone : /root/staging_refresh_clone.sh     Pemulihan runtime setelah pod restart: /root/staging_restore_runtime.sh
Snapshot      : /app/.local-data/snapshots/prod_default_20260925T031446Z.sql (gitignored, chmod 600)
```

Kondisi awal ("Database Development Kosong"): sempat dibuat DB dev lokal dan di-seed. Atas instruksi user, DB itu **dihentikan dan di-drop**, lalu digantikan pendekatan production-clone di atas.

---

## 4. Audit AUTO_SEED

Diuji **secara empiris di DB lokal** (bukan produksi): snapshot → simulasi perubahan admin → restart backend → diff.

```
AUTO_SEED behaviour : Menjalankan run_seed() (app/seed.py) + seed_time_management() (app/seed_time.py)
Trigger             : server.py @app.on_event("startup") -> setiap backend start / restart / redeploy / crash-restart,
                      bila AUTO_SEED=true dan READ_ONLY=false
Tables affected     : companies, company_settings, company_modules, modules, roles, permissions, role_permissions,
                      users, user_company_roles, branches, work_locations, departments, divisions, positions,
                      job_grades, cost_centers, projects, employment_statuses, contract_types, certification_types,
                      document_types, employees, employee_contracts, employee_certifications, documents (+ objek R2),
                      approval_workflows(+steps), payroll_components, payroll_configs, employee_salaries,
                      time_policies, leave_types, leave_balances/ledger, work_shifts, work_schedules, holidays, ...
Insert              : YA. Membuat ulang perusahaan demo NEP/KBS + seluruh data demo bila hilang (dicek per code/email).
                      Membuat saldo cuti untuk SETIAP karyawan aktif (termasuk karyawan riil baru).
                      Mengunggah file demo ke R2.
Update              : YA. Terbukti di uji empiris:
                      - company_modules payroll dipaksa is_active=1 (menimpa penonaktifan manual admin)
                      - employees.user_id ditautkan ke user demo BERDASARKAN full_name, TANPA filter company_id
                        (uji: karyawan KBS bernama "Rina Kusuma" tertaut ke user karyawan@nep.co.id = LINTAS TENANT)
                      - work_locations: kolom geofence yang NULL diisi default (radius, policy)
                      - departments.head_user_id yang kosong diisi user supervisor (perusahaan demo)
Delete              : TIDAK ditemukan DELETE di seed.
Idempotent          : SEBAGIAN / NO. Tidak menduplikasi data demo, tetapi TIDAK bebas efek samping:
                      menimpa konfigurasi manual dan menulis ke data non-demo di setiap start.
Production risk     : HIGH
Recommendation      : 1) Set AUTO_SEED=false di Coolify SEBELUM deploy apa pun berikutnya (keputusan owner).
                      2) Seed demo hanya boleh jalan lewat perintah manual eksplisit, tidak saat startup.
                      3) Setelah migration berversi ada, seed tidak boleh menyentuh tabel/kolom baru Upgrade 01.
                      4) Perbaiki (di fase terpisah) update_many berbasis nama -> wajib filter company_id + is_demo_data.
```

Risiko terkait: `reset_ess_today.py` memakai default `APP_ENV="development"` bila variabel tidak di-set. Kalau dijalankan dengan `.env` produksi (yang tidak memiliki `APP_ENV`), skrip ini bisa DELETE data absensi produksi. **Jangan jalankan di server produksi.**

---

## 5. Database Baseline (Produksi, read-only)

| Item | Nilai |
|---|---|
| Server | MariaDB 11.8.9, collation server `utf8mb4_uca1400_ai_ci`, tabel `utf8mb4_unicode_ci` |
| Tabel / index / kolom | 57 / 324 / 1.230 |
| **Foreign key constraint DB** | **0**. Integritas referensial hanya dijaga di level API |
| Perusahaan | 2: `NEP` (PT Nusantara Energi Prima), `KBS`. **Keduanya demo.** PT REAL belum ada |
| User | 12 (semua `is_demo_account=1`, semua aktif). Role terpakai: super_admin 1, company_owner 2, hr_admin 3, hr_manager 2, finance 1, manager 1, supervisor 1, employee 2 |
| Karyawan | 12 baris (lihat bagian 6) |
| Kontrak / Sertifikasi / Dokumen | 8 / 6 / 6 (employee 4, applicant 1, company 1). Objek R2: 10 |
| Kandidat | 15 |
| Payroll run | 0 |
| Absensi / cuti / lembur | 0 / 0 / 0 (baru dirilis di PR #11) |

Hasil query lengkap: `/app/memory/audit_01a/db_audit_result.json`. Skrip: `/app/memory/audit_01a/db_audit_readonly.py`, dijalankan dengan `SET SESSION TRANSACTION READ ONLY`.

---

## 6. Employee Data Quality

| Metrik | Hasil |
|---|---|
| Total baris employee | **12** (NEP 9, KBS 3) |
| Active | **10** (NEP 7, KBS 3) |
| Inactive | **1** |
| Archived | **0** (status `archived` didukung kode, tapi belum ada datanya) |
| Deleted (soft delete, `status='deleted'`) | 1 |
| Employee number kosong | 0 |
| Duplicate employee number | 1 grup (`NEP-0007`: 1 `deleted` + 1 `active`). **Di antara data non-deleted: 0** |
| NIK (No. KTP) kosong | 0 |
| NIK format ≠ 16 digit | 0 |
| Duplicate NIK | 1 grup, pasangan yang sama dengan `NEP-0007` (baris deleted + baris aktif hasil konversi ulang). Non-deleted: 0. Lintas perusahaan: 0 |
| Employee tanpa project | **9** (non-deleted: 8 dari 11) |
| Project reference invalid (ID tidak ada / beda company / project nonaktif) | 0 / 0 / 0 |
| FK invalid lain (status kepegawaian, cabang, lokasi, dept, divisi, jabatan, grade, cost center, user) | semuanya 0 |
| Kosong: employment_status 1, department 1, position 1, work_location 3, branch 4, grade 4, cost_center 4, division 5, join_date 1 | — |
| Tertaut ke user (ESS) | 3 |
| Berasal dari rekrutmen | 3 |

Kesimpulan: kualitas referensi baik, tapi **kelengkapan data rendah** (proyek, cabang, grade kosong). Duplikasi terjadi karena soft-delete menyimpan baris lama. Pengecekan unik di API mengecualikan baris `deleted`, sementara DB tidak punya unique constraint.

---

## 7. Existing Master

Semua master: tabel per tenant (`company_id`), status `active/inactive/archived`, CRUD generik (`app/masters.py` + `app/routers/master.py`). Hasil cek: **0 duplikat code per perusahaan, 0 baris tanpa company**.

| Master | Table/Model | Used by | Status | Potential issue |
|---|---|---|---|---|
| Company | `companies`, `company_settings`, `company_modules` | Semua modul | ACTIVE | Hanya perusahaan demo. PT REAL belum ada |
| Branch | `branches` (5) | work_locations, departments, projects, employees | ACTIVE | — |
| Work Location | `work_locations` (5) | employees, projects, absensi (geofence), time policy | ACTIVE | Seed mengisi ulang kolom geofence NULL |
| Department | `departments` (6) | employees, divisions, positions, approval (head_user_id) | ACTIVE | Seed mengisi head_user_id |
| Division | `divisions` (6) | employees, positions | ACTIVE | — |
| Position | `positions` (7) | employees, offering rekrutmen | ACTIVE | — |
| Grade | `job_grades` (8) | employees, positions | ACTIVE | — |
| Cost Center | `cost_centers` (5) | employees, projects, departments | ACTIVE | Payroll belum memakai cost center/proyek |
| Project | `projects` (3) — code, name, client_name, branch, work_location, cost_center, start/end, contract_value, PM | employees.project_id, policy resolver (`time_policies`), offering rekrutmen, filter UI | ACTIVE | **Hard delete tidak mengecek employees** (lihat catatan di bawah). Tidak ada histori penugasan |
| Employment Status | `employment_statuses` (6) — code, name, is_permanent, requires_contract | employees, offering, kontrak | ACTIVE | Ini **jenis hubungan kerja** (PKWT/PKWTT/Harian/Magang), **bukan** status keaktifan. Jangan disamakan dengan Master Status Karyawan baru |
| Contract Type | `contract_types` (4) | employee_contracts | ACTIVE | — |
| Certification Type | `certification_types` (4) | employee_certifications, reminder | ACTIVE | — |
| Document Type | `document_types` (12) — allowed_extensions, max_size_mb, has_expiry | documents | ACTIVE | Tipe tanpa `allowed_extensions` menerima ekstensi apa pun |

**Temuan integritas (terbukti di staging):** `DELETE /api/master/{resource}/{id}` hanya mengecek referensi yang terdaftar di `masters.py` (`refs`). Tabel **employees tidak termasuk**, dan DB tidak punya foreign key. Uji: proyek yang dipakai 2 karyawan aktif **berhasil di-hard-delete (HTTP 200)**, sehingga 2 karyawan tertinggal dengan `project_id` menggantung. Hal yang sama berlaku untuk status kepegawaian, jabatan, grade, cost center, cabang, lokasi, dan divisi yang dipakai karyawan.

---

## 8. Audit Employee Model

**Kolom tabel `employees`** (45 kolom + JSON `extra`):

| Kelompok | Field |
|---|---|
| Identitas | `full_name`, `employee_number`, `nik` (No. KTP), `npwp`, `gender`, `birth_place`, `birth_date`, `marital_status`, `religion`, `education` |
| Kontak | `email`, `phone`, `address`, `city`, `emergency_contact_name`, `emergency_contact_phone` |
| Kepegawaian | `job_title`, `join_date`, `employment_status_id`, `candidate_id` (asal rekrutmen), `user_id` (akun ESS), `notes` |
| Organization | `branch_id`, `work_location_id`, `department_id`, `division_id`, `position_id`, `job_grade_id`, `cost_center_id` |
| Project | `project_id` (single value, tanpa histori) |
| Payroll/Bank | `bank_name`, `bank_account_number`, `bank_account_name`. Gaji di tabel `employee_salaries` |
| BPJS/Tax | `bpjs_kesehatan_number`, `bpjs_tk_number`, `npwp`. Status PTKP di `employee_salaries`/payroll config |
| Status | `status` (`active`/`inactive`/`archived`/`deleted`), `is_demo_data` |
| Audit | `created_at/by`, `updated_at/by` |

**Audit khusus:**

| Topik | Temuan |
|---|---|
| `employee_number` | VARCHAR, index **non-unik** `(company_id, employee_number)`. **Keunikan hanya dicek di API** (`TenantRepository.ensure_unique`, mengecualikan `deleted`). Rawan race condition. Nomor otomatis `app/core/employee_numbering.py` (`<KODE>-0001`). **Label UI menyebut field ini "NIK Karyawan"**, sedangkan `nik` = Nomor KTP. Ada potensi kebingungan terminologi |
| `nik` (KTP) | Divalidasi 16 digit dan unik per perusahaan **hanya di API**. Tidak ada index/unique di DB. Tidak dimasking: siapa pun dengan `employee:view` melihat NIK, rekening, dan BPJS |
| `project_id` | Satu proyek per karyawan, dapat diubah via PUT tanpa histori. Dipakai filter list, resolver kebijakan absensi/cuti, dan offering → konversi |
| `employment_status_id` | Referensi ke master jenis hubungan kerja. Dipakai untuk display, filter, kontrak, dan offering. **Tidak** menentukan aktif/nonaktif |
| `status` | `PATCH /employees/{id}/status` menerima `active/inactive/archived`. `DELETE` = soft delete (`deleted`, ditolak bila masih punya kontrak). **Celah: `PUT /employees/{id}` menerima field `status` bebas tanpa validasi nilai.** List & stats memperlakukan `deleted`/`archived` sebagai tidak aktif. Tidak ada alasan, tanggal efektif, atau histori perubahan status (hanya audit_log before/after) |

> Target 01B, yaitu **Master Status Karyawan configurable** dengan kategori sistem AKTIF / STANDBY / TIDAK AKTIF, **belum ada** dan harus dibuat sebagai entitas baru. Konsepnya berbeda dari `employment_statuses` (jenis kontrak) dan dari kolom teknis `employees.status`.

---

## 9. Existing Module Status (berdasarkan CURRENT SOURCE + uji)

| MODULE | BACKEND | FRONTEND | DB | OPERASIONAL | CATATAN |
|---|---|---|---|---|---|
| Core Employee | ✔ `employees.py` | ✔ list/detail/form/import | ✔ | **ACTIVE** | CRUD, status, import (create-only), nomor otomatis |
| Contract | ✔ `contracts.py` | ✔ tab detail karyawan + approval | ✔ | **ACTIVE** | Approval workflow, renewal, reminder |
| Document | ✔ `documents.py` + R2 | ✔ `/documents` | ✔ | **ACTIVE** | Upload/preview/download/soft-delete. Privasi bermasalah (bagian 13) |
| Certification | ✔ `certifications.py` | ✔ tab detail + `/reminders` | ✔ | **ACTIVE** | Kedaluwarsa + email reminder |
| Recruitment | ✔ `recruitment*.py` (3 router) | ✔ dashboard/kandidat/detail | ✔ | **ACTIVE** | E2E: screening → interview → approval 2 langkah → offering → konversi (14/14). Katalog `modules` masih berstatus `planned` (stale) |
| Attendance | ✔ `attendance.py`, `schedules.py`, `time_core.py`, `timekeeping.py` | ✔ 9 halaman | ✔ | **ACTIVE** (baru, 0 data produksi) | ESS GPS/geofence, koreksi, rekap, periode, import/export |
| Leave | ✔ `leave.py` | ✔ | ✔ | **ACTIVE** (0 data) | Saldo/ledger, approval |
| Overtime | ✔ `overtime.py` | ✔ | ✔ | **ACTIVE** (0 data) | Approval, perhitungan menit |
| Payroll | ✔ `payroll.py`, `core/payroll*.py` | ✔ runs/komponen/gaji/config | ✔ | **ACTIVE** | Lifecycle lengkap: draft → hitung → submit → approve → paid. 0 run di produksi. **Belum terintegrasi absensi/lembur/proyek/cost center** |
| Payslip | ✔ `core/pdf.py` | ✔ `/payroll/my-payslips` | ✔ | **ACTIVE** | PDF |
| BPJS / PPh 21 | ✔ `core/payroll.py`, `core/ter.py` | (via payroll) | ✔ config | **ACTIVE** | TER PP 58/2023. Core test 186/186 |
| Approval | ✔ `approvals.py`, `recruitment_workflow.py`, `time_approval.py` | ✔ `/settings/approval-workflows` | ✔ | **ACTIVE** | Workflow per jenis dokumen (rekrutmen, kontrak, payroll, time) |
| Audit | ✔ `core/audit.py`, `audit_logs.py` | ✔ `/audit-logs` | ✔ | **ACTIVE** | before/after JSON per aksi |
| User/Role/Permission | ✔ `users.py`, `core/rbac.py` | ✔ `/users`, `/roles` | ✔ | **ACTIVE** | 8 role, 166 permission, multi-company |
| Mobilization, Performance, Finance Request, Accounting | — | `ModulePlaceholderPage` | — | **PLACEHOLDER** | Hanya kartu modul |
| Employee Family / Timeline / Status History / Assignment / Data Submission | — | — | — | **NOT IMPLEMENTED** | Target Upgrade 01 |

---

## 10. Import Existing Analysis

| Aspek | Existing |
|---|---|
| Endpoint | `GET /api/employees/import/template`, `GET /import/columns`, `POST /import/validate` (upload xlsx), `POST /import/commit` |
| Service/parser | `app/core/excel.py` (openpyxl): `COLUMNS` (label, field, required, hint, lookup master), parser workbook, `validate_rows` |
| Template | XLSX dengan sheet data + sheet referensi master (lookup by code/nama) |
| Validation | Wajib isi, format tanggal/KTP 16 digit, lookup master, duplikat **di dalam file** (No. KTP & nomor karyawan), duplikat terhadap DB |
| Row limit | 500 baris, 5 MB |
| Commit | Frontend mengirim ulang baris JSON hasil validasi → server `repo.create` per baris. **Payload commit dipercaya dari klien**: tidak ada re-parse file, dan referensi master tidak divalidasi ulang (hanya `ensure_unique`) |
| Duplicate control | API-level saja (tanpa unique constraint DB) |
| Mode | **CREATE only.** UPDATE tidak didukung |
| Conflict handling | Tidak ada. Baris duplikat = error/skip |
| Import batch/audit | Tidak ada tabel batch. Hanya audit_log per karyawan |

**Gap terhadap target** `Upload → Analyze → Validate → Preview → NEW/UPDATE/CONFLICT → Commit → Import Batch`:

| Target | Status |
|---|---|
| Upload + Analyze | ADA sebagian: parse & validasi. Belum ada deteksi kolom fleksibel/mapping |
| Preview | ADA (tabel valid/invalid di UI) |
| Klasifikasi NEW / UPDATE / CONFLICT | **BELUM**. Semua baris dianggap NEW |
| UPDATE existing (match by employee_number/NIK) | **BELUM** |
| Conflict resolution (field-level diff, pilih nilai) | **BELUM** |
| Commit atomik server-side dari file tersimpan | **BELUM** (payload dari klien, per-baris, tanpa transaksi batch) |
| Import Batch + Item (siapa, kapan, file, hasil per baris, rollback) | **BELUM** |
| Permission import terpisah | **BELUM** (memakai `employee:create`) |

Rekomendasi: **REUSE** `excel.py` (COLUMNS, lookup master, validasi) sebagai mesin validasi. Tambahkan lapisan batch baru secara additive. Jangan rewrite parser.

---

## 11. Project Dependency Analysis (`employee.project_id`)

| File / Module | Usage | R/W | Impact bila `employee.project_id` berubah | Compatibility recommendation |
|---|---|---|---|---|
| `backend/app/routers/employees.py` | create/update (validasi ref), filter list `?project_id=`, stats, detail (nama proyek) | R/W | Filter & tampilan berubah | Tetap tulis `project_id` sebagai **proyek aktif utama**, disinkronkan dari assignment |
| `backend/app/core/excel.py` | kolom import "Proyek" (lookup `projects`) | W | Import mengisi proyek | Import tetap mengisi `project_id`, lalu membuat assignment |
| `backend/app/core/policy.py` + `routers/policies.py` | resolver kebijakan berlapis (company → branch → project → work_location) | R | Kebijakan absensi/cuti/lembur karyawan berubah | Resolver tetap membaca `project_id`. Nanti bisa diganti ke "assignment aktif per tanggal" tanpa mengubah API |
| `backend/app/routers/attendance.py`, `core/time_service.py` | konteks proyek untuk policy & filter rekap/data (12 referensi) | R | Rekap absensi per proyek | Sama seperti di atas. Untuk rekap historis, gunakan assignment per tanggal |
| `backend/app/routers/recruitment_pipeline.py` / `recruitment_conversion.py` | offering → `project_id` karyawan baru | W | Karyawan hasil rekrutmen | Konversi tetap mengisi `project_id` + membuat assignment awal |
| `backend/app/masters.py` / `routers/master.py` | master proyek (refs tidak mencakup employees) | R/W | Hapus proyek membuat referensi menggantung | Tambahkan pengecekan employees/assignment sebelum hard delete (fix terpisah) |
| `backend/app/seed.py` | data demo | W | — | Jangan dijalankan di produksi |
| Frontend `EmployeesPage.jsx`, `EmployeeDetailPage.jsx`, `EmployeeForm`, `PoliciesPage.jsx`, `OfferingTab.jsx`, `lib/moduleFoundation.js`, halaman absensi | filter, form, tampilan, pemilihan scope policy | R/W | UI | Tetap berjalan bila `project_id` dipertahankan |
| Payroll (`core/payroll*.py`, `routers/payroll.py`) | **tidak memakai project_id** | — | Tidak ada | Alokasi biaya per proyek adalah fitur baru, bukan perubahan |
| Leave / Overtime | tidak langsung (via policy resolver) | R | Via policy | — |
| Export (time_excel, payroll excel) | nama proyek di beberapa export absensi | R | Kolom export | Pertahankan |

---

## 12. Baseline Regression Result — **BASELINE BEFORE UPGRADE 01**

Lingkungan: **staging clone produksi** (bukan produksi). Setiap suite dijalankan pada clone yang di-restore dari snapshot yang sama. Laporan testing agent: `/app/test_reports/iteration_14.json`, `iteration_15.json`, `iteration_16.json`. Log smoke: `/app/memory/audit_01a/regression/`.

| TEST | RESULT | NOTES |
|---|---|---|
| Automated: `tests/test_tenant_isolation.py` | PASS | SQLite sementara |
| Automated: `test_core.py` (payroll, BPJS, PPh 21 TER, payslip PDF, excel, mail) | PASS 186/186 | Murni fungsi |
| Smoke `smoke_mariadb.py` (CRUD lintas modul, payroll run) | PASS 45/45 | |
| Smoke `smoke_ess.py` (absensi ESS GPS, geofence, approval lokasi, scope, audit) | PASS 111/111 | |
| Smoke `smoke_time.py` (jadwal, absensi, koreksi, cuti, lembur, periode, isolasi, export) | 43/45 | 2 gagal di check-in/out: data produksi tidak punya jadwal kerja user uji untuk tanggal hari ini (aturan bisnis benar). Di DB dev dengan jadwal: 45/45 |
| Authentication – Login | PASS | Semua role. Password salah → 401. `/auth/me`, logout |
| Employee – List / Detail | PASS | API + UI, filter, search |
| Employee – Create / Edit / Status | PASS | API (+ duplikat nomor & NIK → 409, ref invalid → 422). UI form terbuka, submit via API |
| Employee – Import | PASS | Template, kolom, validasi |
| Contract – existing flow | PASS | CRUD, approval berbasis role, renewal, validasi tanggal |
| Document – upload/read | PASS | Upload PNG 201, preview/download byte identik, `.exe` → 422, soft delete. Storage = clone lokal |
| Certification – existing flow | PASS | CRUD, validasi tanggal, reminder |
| Recruitment – main flow | PASS 14/14 | Kandidat → screening → interview → approval HR Manager → Direksi → offering → accept → konversi (nomor otomatis) |
| Attendance – main flow | PASS | Via smoke_ess/smoke_time. UI halaman tampil |
| Leave / Overtime – main flow | PASS | Pengajuan + approval (smoke_time). UI halaman tampil |
| Payroll – basic regression | PASS | Komponen, struktur gaji, run lifecycle, submitter ≠ approver, reject, PDF, Excel, self-service, isolasi tenant |
| Permission – existing RBAC | PASS | employee 403 ke data admin, finance tidak bisa create employee, isolasi KBS↔NEP |
| UI page coverage (40 halaman/aksi) | PASS 40/41 | |

**Temuan fungsional existing (tidak diperbaiki, hanya dicatat):**

1. **MEDIUM:** Hard delete master tidak mengecek pemakaian oleh karyawan (bagian 7).
2. **LOW:** `PUT /employees/{id}` menerima `status` bebas (bypass validasi PATCH).
3. **LOW (UX):** Role karyawan bisa membuka URL `/employees` dan `/payroll/runs`. Backend menolak (403), tapi UI tampil kosong tanpa pesan "akses ditolak".
4. Perilaku existing: `finance` tidak punya izin hapus payroll run (403).
5. Katalog `modules` menandai attendance, leave_overtime, dan recruitment sebagai `planned`, padahal sudah aktif.

**Kesimpulan regression: PASS** (fungsional). Isu di atas bukan regresi, melainkan kondisi baseline.

---

## 13. Storage / Security Analysis

**Dokumen & R2**

```
Employee document privacy : Objek disimpan di bucket media-akunkita, key hris-payroll/companies/<company_id>/documents/<uuid>.<ext>
                            (nama file asli tidak dipakai di key; UUID sulit ditebak)
Public access possible    : YES. Semua 6/6 dokumen (employee, applicant, company) HTTP 200 tanpa autentikasi via R2_PUBLIC_BASE_URL (r2.dev).
                            Listing root bucket ditolak (tidak bisa dienumerasi).
Backend authorization     : YES untuk jalur aplikasi (/api/documents/{id}/preview|download: require_permission + filter company_id,
                            file di-stream oleh backend). Tetapi URL publik mem-bypass pengecekan ini.
Signed URL                : NO. Fungsi presigned_url() & public_url() ada di storage.py, tetapi tidak dipakai router.
Bucket/prefix sharing     : Nama bucket "media-akunkita" (kesan media publik). Saat audit hanya berisi prefix hris-payroll/
                            (10 objek). Dokumen privat berada di bucket yang akses publiknya aktif.
Tenant isolation storage  : Prefix per company_id + filter company_id di DB. Tidak ada pemisahan kredensial per tenant.
Risk                      : HIGH. URL yang bocor (log, riwayat browser, screenshot) memberi akses permanen ke KTP/dokumen
                            pribadi tanpa bisa dicabut.
Recommendation            : (keputusan owner, tidak dilakukan di 01A)
                            1) Nonaktifkan "Public Development URL (r2.dev)" pada bucket, atau pisahkan bucket privat untuk HRIS.
                            2) Kosongkan R2_PUBLIC_BASE_URL untuk dokumen HR. Tetap stream lewat backend atau presigned URL
                               berumur pendek.
                            3) Rotasi R2 access key (lihat bagian 17).
```

**File upload**

| Lapisan | Existing |
|---|---|
| Frontend limit | Menampilkan batas (`max_size_mb`) dan atribut `accept` per tipe dokumen. Tidak memblokir ukuran di klien |
| Backend limit | `MAX_UPLOAD_MB=15` (global) + `document_types.max_size_mb`. Import karyawan 5 MB / 500 baris |
| Proxy limit | Nginx `client_max_body_size 25m` (Coolify `CLIENT_MAX_BODY_SIZE`). Ingress Coolify/Traefik: default |
| Allowed extensions | Per `document_types.allowed_extensions`. **Tipe tanpa daftar menerima semua ekstensi** |
| MIME validation | **Tidak ada.** MIME diambil dari header `Content-Type` klien (fallback: tebakan dari ekstensi). Tidak ada deteksi magic-bytes |
| Filename sanitization | Nama asli tidak dipakai di storage key (UUID). Nama asli disimpan di DB dan dipakai di header `Content-Disposition` |
| Preview | Disajikan **inline** dengan MIME dari klien, di origin yang sama dengan aplikasi (token JWT di `localStorage`). Ada potensi XSS tersimpan bila tipe dokumen tanpa whitelist menerima `.html`/`.svg`. **Perlu verifikasi lanjutan** |
| Malware scanning | Tidak ada |

---

## 14. Role & Permission Analysis

| Kemampuan | Existing |
|---|---|
| Role | 8 role sistem (super_admin, company_owner, hr_admin, hr_manager, finance, manager, supervisor, employee), per company |
| Permission | 166, format `resource:action` (view, create, update, delete, approve, export, dll.) |
| Tenant/company isolation | ADA dan teruji (TenantRepository + test_tenant_isolation + uji API KBS↔NEP) |
| Self-service scope | ADA untuk absensi/cuti/lembur/payslip (`scope_employee_id`: role employee hanya data sendiri) |
| Supervisor/department scope | Terbatas: approval berdasarkan `head_user_id` departemen / approver role |
| **Project scope** | **TIDAK ADA** |
| **Site/work location scope** | **TIDAK ADA** |
| **Multiple project scope per user** | **TIDAK ADA** |
| **Sensitive field permission** (NIK, rekening, gaji, BPJS) | **TIDAK ADA** untuk data karyawan. Gaji dipisah ke permission payroll/salary. NIK & rekening terlihat oleh semua yang punya `employee:view` |
| Export permission | ADA (`:export` pada beberapa resource) |
| Verify permission | **TIDAK ADA** |
| Import permission | **TIDAK ADA** (memakai `employee:create`) |

Target Upgrade 01: **ROLE/PERMISSION** (boleh melakukan apa) sudah ada dan harus di-reuse. **DATA SCOPE** (terhadap data siapa) perlu dibangun baru dan additive, sebagai filter tambahan di `TenantRepository`/query list, tanpa mengganti RBAC.

---

## 15. Protected Modules — **PROTECTED — DO NOT REWRITE IN UPGRADE 01**

Integrasi additive (hook, kolom baru opsional, pemanggilan fungsi) diperbolehkan. Redevelopment tidak diperbolehkan.

| Modul | File/service utama |
|---|---|
| Payroll | `backend/app/routers/payroll.py`, `app/core/payroll.py`, `app/core/payroll_service.py`; FE `PayrollRuns*`, `PayrollComponents`, `PayrollConfig`, `EmployeeSalaries` |
| BPJS | `app/core/payroll.py` (komponen BPJS), payroll config |
| PPh 21 | `app/core/ter.py`, `app/core/payroll.py` |
| Payslip | `app/core/pdf.py`; FE `MyPayslipsPage.jsx` |
| Attendance | `routers/attendance.py`, `routers/schedules.py`, `routers/time_core.py`, `core/timekeeping.py`, `core/time_service.py`, `core/time_excel.py`; FE `pages/attendance/*` |
| Leave | `routers/leave.py`; FE `pages/leave/*` |
| Overtime | `routers/overtime.py` |
| Recruitment | `routers/recruitment.py`, `recruitment_pipeline.py`, `recruitment_conversion.py`, `core/recruitment_workflow.py`; FE `pages/recruitment/*`, `components/recruitment/*` |
| Contract | `routers/contracts.py`, `core/expiry.py` |
| Certification | `routers/certifications.py`, `routers/reminders.py`, `core/reminder_mail.py` |
| Document | `routers/documents.py`, `core/storage.py`, `core/demo_files.py`; FE `DocumentsPage.jsx` |
| Approval | `routers/approvals.py`, `core/time_approval.py`, `core/recruitment_workflow.py` |
| Audit | `core/audit.py`, `routers/audit_logs.py` |
| Authentication | `routers/auth.py`, `core/security.py`, `core/deps.py` |
| Tenant isolation | `core/tenancy.py`, `core/repo.py` (`TenantRepository`), `core/deps.py`, `core/rbac.py` |
| Data layer | `core/db.py` (adapter Mongo-style ↔ MariaDB, schema catalogue & sync). Hanya tambah entri katalog, jangan ubah perilaku |

---

## 16. Gap Against Upgrade 01

| Kebutuhan Upgrade 01 | Existing | Gap |
|---|---|---|
| Master Status Karyawan configurable (AKTIF/STANDBY/TIDAK AKTIF) | `employees.status` teknis + `employment_statuses` (jenis kontrak) | **Baru** (01B) |
| Employee Status History (tanggal efektif, alasan, oleh) | audit_log saja | **Baru** (01B) |
| Employee Assignment (proyek/site historis, multi) | `employees.project_id` tunggal | **Baru**, dengan kompatibilitas `project_id` |
| Employee Timeline/Event | audit_log (teknis) | **Baru** (bisa membaca audit/status/assignment) |
| Employee Family | tidak ada | **Baru** |
| Import Batch NEW/UPDATE/CONFLICT | import create-only | **Baru** di atas `excel.py` |
| Employee Data Submission / Pending Change (ESS usul, HR verifikasi) | tidak ada | **Baru** (butuh permission `verify`) |
| Completeness config | tidak ada (kelengkapan rendah, lihat bagian 6) | **Baru** |
| User Data Scope (project/site) | hanya company + self | **Baru** |
| Sensitive field permission | tidak ada | **Baru** |
| Migration berversi | auto-sync startup | **Baru** (prasyarat 01B) |
| Integritas: unique DB employee_number / FK | API-level | Disarankan (additive, setelah data bersih) |

---

## 17. Proposed Additive Schema (PROPOSAL, tanpa migration)

Konvensi existing yang diikuti: PK `id` UUID CHAR(36), `company_id`, `status`, `created_at/by`, `updated_at/by`, JSON `extra`. Didaftarkan di katalog `db.py`.

| Struktur target | Sudah ada? | Keputusan |
|---|---|---|
| `employee_status_master` | Tidak (`employment_statuses` ≠ status keaktifan) | **NEW**: `employee_statuses` (code, name, system_category ENUM AKTIF/STANDBY/TIDAK_AKTIF, is_default, sort_order, color, requires_reason, status) |
| `employee_status_history` | Tidak | **NEW**: `employee_status_histories` (employee_id, from_status_id, to_status_id, effective_date, reason, source [manual/import/system], ref_id) |
| `employee_assignment` | Tidak (`project_id` tunggal) | **NEW**: `employee_assignments` (employee_id, project_id, work_location_id, position_id, start_date, end_date, is_primary, assignment_type) |
| `employee_timeline/event` | Sebagian (`audit_logs`) | **NEW (ringan)**: `employee_events`, atau view gabungan audit + status + assignment. Audit log tetap dipakai |
| `employee_family` | Tidak | **NEW**: `employee_family_members` |
| `employee_import_batch` / `_item` | Tidak | **NEW**: `employee_import_batches`, `employee_import_batch_items` (action NEW/UPDATE/CONFLICT/SKIP, diff JSON, result) |
| `employee_data_submission` / `employee_pending_change` | Tidak | **NEW**: `employee_change_requests` (+ item field-level). Satu struktur untuk dua kebutuhan |
| `employee_completeness_config` | Tidak | **NEW**: `employee_completeness_rules` (field, required_for_category, weight) |
| `user_data_scope` | Tidak | **NEW**: `user_data_scopes` (user_id, company_id, scope_type [all/project/work_location/department], scope_ref_id) |
| Kolom `employees.employee_status_id` | Tidak | **ADD COLUMN NULL**. `employees.status` tetap dipertahankan dan disinkronkan |
| Ledger migration | Tidak | **NEW**: `schema_migrations` (version, name, checksum, applied_at, applied_by) |
| REUSE | — | `projects`, `work_locations`, `positions`, `employment_statuses`, `documents`, `audit_logs`, `approval_workflows`, RBAC, `excel.py` |

---

## 18. Compatibility Plan — ADDITIVE FIRST, NO DESTRUCTIVE MIGRATION

1. **Arsitektur rilis (sesuai arahan user):** develop sekali di staging clone → migration berversi additive dijalankan di staging → UAT → backup produksi → deploy kode (AUTO_SEED=false) → jalankan **file migration yang sama** di produksi. Tidak ada setup DB ulang.
2. **Mekanisme migration (usulan 01B):** `backend/migrations/NNNN_*.sql|py` + ledger `schema_migrations` + perintah `migrate status | up --dry-run | up`. Aturan: hanya `CREATE TABLE IF NOT EXISTS`, `ADD COLUMN NULL`, `ADD INDEX`, backfill idempotent. Dilarang `DROP`, `RENAME`, dan ubah tipe. Auto-sync startup diberi flag env (mis. `SCHEMA_AUTO_SYNC=false` di produksi), supaya DDL produksi hanya lewat migration yang terkontrol.
3. **`employees.project_id` dipertahankan.** Nilainya = proyek dari assignment primer aktif. Setiap perubahan assignment memperbarui `project_id` (satu arah, di service baru). Modul lama (policy resolver, filter, rekrutmen, export) tetap bekerja tanpa diubah. Backfill: 1 assignment awal per karyawan yang punya `project_id`.
4. **`employees.status` dipertahankan.** Master status baru memetakan `system_category` ke nilai teknis: AKTIF → `active`, STANDBY → `active` (atau `inactive` sesuai keputusan bisnis), TIDAK AKTIF → `inactive`/`archived`. Modul payroll/absensi yang memfilter `status` tetap benar. Backfill history awal dari status saat ini.
5. **`employment_statuses` tidak diubah** dan tetap bermakna jenis hubungan kerja.
6. **Import:** endpoint lama `/import/validate|commit` tetap ada. Alur batch baru memakai endpoint baru dan me-reuse `excel.py`.
7. **Data scope:** default `all` dalam perusahaan untuk semua user existing, jadi perilaku tidak berubah sampai scope dikonfigurasi.
8. **Unique/FK DB:** baru ditambahkan setelah pembersihan duplikat soft-delete, lewat unique index yang mengabaikan baris `deleted` (mis. kolom generated), sebagai migration terpisah.
9. **Rollback:** karena semua perubahan additive, rollback kode tidak merusak DB. Restore snapshot hanya sebagai jalan terakhir.

---

## 19. Security Audit (repo + konfigurasi), tanpa nilai secret

| Secret type | Location | Tracked by Git | Risk | Rotation recommended |
|---|---|---|---|---|
| **Password akun demo** (dipakai 12/12 akun produksi termasuk super_admin, diverifikasi dengan bcrypt lokal terhadap hash, tanpa login) | `backend/app/seed.py` (`DEMO_PASSWORD`), `frontend/src/pages/LoginPage.jsx` (ditampilkan di halaman login), `memory/test_credentials.md`, beberapa test | **YES** (repo PUBLIC) | **CRITICAL**: siapa pun bisa login sebagai super_admin | **YES**: ganti password semua akun, sembunyikan panel demo di produksi |
| Password fixture uji | `backend/smoke_api.py`, `backend_test.py` | YES | Low (bukan kredensial produksi) | NO |
| JWT secret default `change-me-in-production` | `backend/app/core/config.py` (fallback) | YES | Medium bila env kosong. Produksi: CONFIGURED | NO (pastikan env selalu diisi) |
| DB password produksi | Coolify env, file kredensial chat | NO (tidak ada di tree/history) | Medium: port MariaDB **terbuka publik** + dibagikan lewat chat | **YES** |
| R2 access key / secret | Coolify env, file kredensial chat | NO | High bersama akses publik r2.dev | **YES** |
| JWT_SECRET produksi | Coolify env, file kredensial chat | NO | Medium | **YES** (semua sesi akan logout) |
| GitHub PAT (2 token) | Pesan chat + file kredensial | NO | High: akses repo | **YES** |
| `.env` ter-commit | — | NO (hanya `.env.example`, `backend/.env.example`, `frontend/.env.example` berisi placeholder) | — | — |
| Nilai secret produksi di git history | dicek dengan `git log -S` untuk DB password, JWT, R2 key/secret, PAT, account id | NO | — | — |
| IP:port DB publik | dokumen/chat | NO | Medium: DB & phpMyAdmin terekspos ke internet | Batasi firewall ke IP tepercaya |

---

## 20. Risks

| # | Risiko | Level |
|---|---|---|
| R1 | Login super_admin produksi memakai password publik (repo public + tampil di login) | **CRITICAL** |
| R2 | Dokumen pribadi (KTP dll.) dapat diunduh tanpa login via r2.dev | **HIGH** |
| R3 | AUTO_SEED=true: update data bisnis setiap start, penautan user lintas tenant berdasarkan nama, konfigurasi admin ditimpa | **HIGH** |
| R4 | Tidak ada migration berversi. DDL implisit otomatis di produksi setiap redeploy | HIGH (untuk Upgrade 01) |
| R5 | Tidak ada FK/unique DB. Hard delete master meninggalkan referensi karyawan menggantung | MEDIUM |
| R6 | MIME dari klien + preview inline same-origin + token di localStorage | MEDIUM (perlu verifikasi) |
| R7 | Port MariaDB & phpMyAdmin terbuka ke internet | MEDIUM |
| R8 | Kredensial produksi dibagikan lewat chat (belum dirotasi) | MEDIUM |
| R9 | Produksi berisi data demo. Onboarding PT REAL butuh keputusan: bersihkan data demo vs perusahaan baru | MEDIUM (bisnis) |
| R10 | Staging di environment preview bersifat sementara: pod restart menghapus paket MariaDB (data aman, runtime dipulihkan dengan skrip). Sudah terjadi 1× saat audit | LOW–MEDIUM |
| R11 | Terminologi "NIK Karyawan" (employee_number) vs "NIK" (KTP) | LOW |

---

## 21. Recommendation

**Sebelum deploy apa pun ke produksi** (keputusan & tindakan owner, bukan scope 01A):
1. Ganti password ke-12 akun produksi dan sembunyikan panel akun demo di halaman login produksi (butuh keputusan: perubahan data produksi).
2. Set `AUTO_SEED=false` di Coolify.
3. Matikan akses publik r2.dev (atau buat bucket privat HRIS) dan kosongkan `R2_PUBLIC_BASE_URL`.
4. Rotasi: DB password, R2 key, JWT secret, 2 GitHub PAT. Batasi firewall port DB/phpMyAdmin.
5. Pertimbangkan menjadikan repo **private**.
6. Konfirmasi di Coolify bahwa aplikasi di-build dari `main @ 9107807`.

**Untuk 01B (development di staging):**
1. Mulai dengan kerangka **migration berversi + ledger** (prasyarat), lalu `employee_statuses` + `employee_status_histories` + `employees.employee_status_id` (NULL) + backfill.
2. Jangan sentuh Protected Modules. Jangan ubah `employees.status`/`project_id`.
3. Pertimbangkan staging permanen di Coolify (DB `hris_staging`), supaya tidak bergantung pada environment preview.

---

## 22. GO / NO-GO for 01B

> **CONDITIONAL GO**
> - **GO** untuk mulai development 01B **di staging clone** (Live Preview), memakai migration additive berversi.
> - **NO-GO untuk deploy 01B ke produksi** sampai R1–R3 ditangani (password demo, AUTO_SEED=false, akses publik dokumen) dan owner menyetujui mekanisme migration.
> - 01B **tidak dimulai** sebelum ada approval tertulis dari owner.

---

### Lampiran — Artefak audit (lokal, tidak di-commit)
- `/app/memory/audit_01a/db_audit_readonly.py`, `db_audit_result.json`
- `/app/memory/audit_01a/regression/*.log`
- `/app/test_reports/iteration_14.json`, `iteration_15.json`, `iteration_16.json`
- Snapshot DB: `/app/.local-data/snapshots/` (gitignored)
