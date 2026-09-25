# TENANT FOUNDATION FINAL — KelolaKita — HRIS & Payroll

Tanggal: 25 Sep 2026 · Lingkungan: **STAGING / Live Preview saja** (`https://repo-clone-deploy-1.preview.emergentagent.com`)
Branch kerja: `feature/tenant-foundation-minimal` · Semua status di bawah **diuji agent**, **belum dikonfirmasi user**.
Revisi review final (25 Sep 2026 ±10:56 UTC): bagian Cleanup (8) dan Remaining Issues (11) diperbarui dari inventaris read-only DB & storage staging. Tidak ada perubahan code, DB, atau storage.

---

## Ringkasan Status

| Area | Status |
|---|---|
| Runtime Safety | **PASS** |
| Test 1–14 | **PASS** |
| Regression | **PASS** (Attendance memakai fixture jadwal sementara, lalu dibersihkan) |
| Visual QA | **PASS** (6 temuan kecil, semuanya diperbaiki) |
| Secret Scan | **PASS** (0 temuan) |
| git diff --check | **PASS** |
| Frontend Build | **PASS** (`yarn build`: Compiled successfully, tanpa warning) |
| Backend Compile | **PASS** (py_compile + import `server` OK) |
| testing_agent_v3 | **PASS** (Putaran 1: 51/51 backend + UI, 1 temuan LOW yang ternyata *false positive*. Putaran 2: 11/11 UI, 0 temuan) |
| Platform Branding | **PASS** |
| Login UI | **PASS** |
| Tenant Provisioning | **PASS** |
| Tenant Admin Pertama | **PASS** |
| Tenant Registry | **PASS** |
| Tenant Detail | **PASS** |
| Subscription / Renewal | **PASS** |
| Tenant Logo Upload max 10 MB | **PASS** |
| Platform vs Tenant Branding | **PASS** |
| Tenant Isolation | **PASS** |
| Permission/API Security | **PASS** |
| Cleanup Final | **PARTIAL**: semua data dummy/test Tenant Foundation sudah dihapus, dan PT REAL punya tepat 1 Tenant Admin. Target "hanya PT REAL" **tidak tercapai**: masih ada tenant baseline KBS & NEP serta CONTOHJASA buatan user (total 4 tenant, 15 user). Semuanya dipertahankan atas keputusan user, termasuk legacy storage. Lihat bagian 8. |

**Production Changed: NO**

---

## 1. Runtime Safety — PASS
Diverifikasi di awal, sebelum testing agent dijalankan, dan sekali lagi sebelum laporan ini ditulis:
- DB aktif `hris_staging`, host `127.0.0.1:3306`, MariaDB 11.8.9. Log backend: `Terhubung ke MariaDB 127.0.0.1:3306/hris_staging`.
- `AUTO_SEED=false`. `/api/system/mode` mengembalikan `environment=staging, storage=s3-staging-local, auto_seed=false`.
- Storage `R2_ENDPOINT_URL=http://127.0.0.1:5010` (supervisor `hris-staging-s3`), bucket `hris-staging-media`, prefix `hris-payroll`, account `staging-local`.
- Tidak ada endpoint `cloudflarestorage` di `.env`. `R2_PUBLIC_BASE_URL` kosong.
- Hanya ada satu `DATABASE_URL`, mengarah ke 127.0.0.1. Env proses backend tidak meng-override DB/R2.
- Key storage staging tidak cocok dengan artefak kredensial produksi mana pun (dicek dengan membandingkan nilai, tanpa mencetaknya).

## 2. Test 1–14 — PASS
Log lengkap: `/app/test_reports/tenant_final/`.

| Suite | Hasil |
|---|---|
| Test 1–7 Tenant Foundation (`t01_07_tenant_foundation.log`) | **7/7 PASS** |
| Test 8–14 Subscription + UNIT/SETUP/VAL (`t08_14_subscription.log`) | **71/71 PASS** (UNIT 8, SETUP 10, VAL 8, T8 5, T9 5, T10 13, T11 5, T12 8, T13 5, T14 4) |
| Suite fitur final (`final_feature_suite.log`) | **143/143 PASS** |

Rincian suite final: T1 4/4 · T2 7/7 · T3 3/3 · Provisioning 24/24 · First Login A 9/9 · First Login B 9/9 · Tenant Detail 7/7 · Reset Password 18/18 · Platform Dashboard 1/1 · T8 1/1 · T9 2/2 · T10 4/4 · T14 1/1 · T11 3/3 · T12 2/2 · T13 2/2 · T6 4/4 · Platform Branding 19/19 · Tenant Logo 17/17 · Platform vs Tenant Branding 2/2 · No Password Leak 4/4.

Test tambahan yang diminta user (semua lulus sesuai target):

| Test | Hasil |
|---|---|
| create tenant → Tenant Admin pertama otomatis tercipta | PASS |
| Email Utama dipakai sebagai login admin | PASS |
| password sementara di-generate (server) | PASS |
| password hanya ditampilkan satu kali (tidak ada di list users / GET mana pun; hilang setelah dialog ditutup) | PASS |
| login pertama dengan password sementara | PASS |
| wajib ganti password sebelum masuk aplikasi (UI redirect + API 403 `X-Password-Change-Required`) | PASS |
| password lama tidak berlaku setelah diganti (401) | PASS |
| reset password dari Tenant Detail → Users | PASS |
| setelah reset, wajib ganti password kembali | PASS |
| Tenant Admin akses tenant lain → DENIED (403/404) | PASS (DENIED) |
| password tidak muncul di log/audit (dicek di `audit_logs` DB + log backend) | PASS |

File test yang berubah (di luar repo, `/root/tenant_tests/`, hanya payload/alur test):
- `sub_test.py`: field PIC sudah ada. Ditambah langkah login pertama → ganti password untuk admin dengan password sementara, plus assert API 403 sebelum ganti.
- `tenant_foundation_test.py`: `login()` otomatis menjalankan alur ganti password saat `must_change_password=true`. TEST 5 memakai password baru, karena password sementara lama memang sudah 401.
- `final_test.py`: grup baru F (First Login), R (Reset Password), S (No Password Leak).
- Skrip cleanup baru: `cleanup_smoke_payroll.py`, `cleanup_smoke_time_side_effects.py`.

## 3. Regression — PASS
| Modul | Hasil | Log |
|---|---|---|
| Payroll / BPJS / PPh 21 TER / slip / Excel (`test_core.py`) | **186/186** | `reg_core_payroll.log` |
| API MariaDB smoke: Employee, Master, Documents, Payroll run, Users (`smoke_mariadb.py`) | **45/45** | `reg_mariadb.log` |
| ESS (`smoke_ess.py`) | **111 OK / 0 FAIL** | `reg_ess.log` |
| Attendance / Cuti / Lembur (`smoke_time.py`) | **45 OK / 0 FAIL** (fixture jadwal sementara lalu dibersihkan) | `reg_attendance_time.log` |
| Recruitment → konversi karyawan (`recr_c_unique.py`) | **43/43** | `reg_recruitment.log` |
| Tenant isolation pytest | **1/1** | `reg_tenant_isolation_pytest.log` |
| UI ringan (Employees, detail karyawan tab Kontrak/Dokumen, Payroll runs, Attendance, Cuti & Lembur, Recruitment, Documents, Reminder) | Semua halaman terbuka, 0 page error | screenshot agent |

Catatan jujur:
- Percobaan pertama `smoke_mariadb` hasilnya **44/45**. Penyebabnya artefak payroll run "Januari 2031" (status pending, tidak bisa dihapus lewat API) yang tertinggal dari smoke run sebelumnya. Artefak itu dihapus dari staging, lalu rerun **45/45**. Ini bukan bug aplikasi.
- `reset_ess_today.py` hanya berjalan di `APP_ENV=development`, jadi tidak dieksekusi di staging. Reset state absensi memakai `time_fixture.py`.

## 4. Visual QA — PASS
Area yang diverifikasi lewat screenshot (desktop 1920 px, plus mobile 390 px untuk login):
Login (desktop + mobile, dengan logo default dan logo upload user) · Platform Dashboard · Tenant Registry · Branding Platform · Wizard Tambah Tenant (langkah 1, langkah 2 dengan toggle ON/OFF) · Tenant Detail (Ringkasan, Users, Aktivitas, dialog Reset Password + kredensial sekali tampil, dialog Perpanjang layanan, status Nonaktif / Aktifkan kembali) · Dialog Ubah Tenant (tanpa field password) · Halaman Ganti Password Sementara · Dashboard Tenant · Profil Perusahaan + upload logo tenant · Sidebar tenant berlogo · Blok login tenant nonaktif (mobile) · Halaman "Khusus Platform Admin" untuk Tenant Admin.

Checklist: branding KelolaKita — HRIS & Payroll ✔ · tidak ada kata Procurement ✔ · tidak ada kata Trial ✔ · tidak ada login Google/Microsoft ✔ · logo platform tampil benar ✔ · favicon K ✔ · logo tenant tidak tertukar dengan logo platform ✔ · pesan expired/inactive profesional ✔ · responsive ✔ · tidak ada dummy credential ✔.

Temuan visual dan perbaikannya:
1. Favicon `favicon.ico` tidak ada (404) → dibuat `frontend/public/favicon.svg` (ikon "K" teal) dan dijadikan default. `theme-color` diubah jadi teal. `<html lang="id">`.
2. Header kolom registry masih "Action" → diganti "Aksi".
3. Teks bantuan toggle wizard tetap berbunyi "dibuat dengan email utama" saat toggle OFF → teks sekarang menyesuaikan kondisi toggle.
4. Toast "Selamat datang" muncul di halaman wajib ganti password → toast tidak ditampilkan saat user diarahkan ke `/change-password`.
5. Logo platform upload user (wordmark gelap) kontrasnya buruk di hero login yang gelap → logo custom di hero sekarang ditaruh di atas *chip* putih.
6. Komentar HTML template CRA (yang menyebut developers.google.com) dihapus dari `index.html`. Ini sumber false positive "Google" di testing agent.

Catatan: kegagalan otomasi screenshot sebelumnya ("element not visible") bukan bug. `DataTable` merender daftar mobile tersembunyi dengan link yang sama, jadi selector harus memakai elemen yang terlihat.

## 5. Secret Scan — PASS
- Ruang lingkup: `git diff HEAD` (baris tambahan) + semua file untracked (termasuk log di `test_reports/tenant_final`).
- Pola yang dicek: AWS key, private key, JWT, URL DB berkredensial, GitHub PAT, endpoint akun R2, `sk-` key. Nilai rahasia dari `.env` backend/frontend dan file kredensial staging juga dicocokkan secara eksak, tanpa dicetak.
- Hasil **0 temuan**. JWT di log regresi disensor (`<JWT-REDACTED>`).
- Tidak ada demo credential di `frontend/src` maupun bundle hasil build.

## 6. testing_agent_v3 — PASS
- **Putaran awal (iteration_21): FINDINGS (1, LOW).** Backend 51/51 PASS. UI Login/Dashboard/Registry/Wizard PASS.
  - Temuan: "Teks 'Google' di halaman login". Hasil verifikasi: **false positive**. Kata itu hanya ada di URL `<link>` Google Fonts dan komentar HTML, bukan teks yang terlihat user. Komentar sudah dihapus. Font tetap dipakai.
- **Fixes Applied:** penghapusan komentar HTML + chip putih untuk logo custom di hero login.
- **Retest (iteration_22): PASS.** 11/11 UI, 0 temuan. Cakupan: teks login, logo di chip (desktop/mobile), alur Reset Password UI, UX Ganti Password (validasi, show/hide, Keluar, redirect paksa), tab Ringkasan/Aktivitas, dialog Ubah Tenant, halaman Branding (ubah tagline lalu dipulihkan).
- Item yang tidak sempat diuji testing agent di UI (renew/nonaktif/aktifkan, halaman forbidden, regresi UI) sudah diverifikasi sendiri lewat screenshot: semua PASS (bagian 4 dan 3).

## 7. Fitur

**Platform Branding — PASS.** Nama, subtitle, tagline, headline, teks login, dan kontak bantuan bisa dikonfigurasi. Logo dan favicon platform bisa di-upload/ganti/hapus (PNG/JPG/JPEG/WEBP ≤10 MB). Hanya Platform Admin: Tenant Admin mendapat 403. Endpoint publik `/api/public/branding` dipakai halaman login. File disimpan di `{prefix}/platform/branding/…` pada storage staging lokal.

**Login UI — PASS.** Dua kolom (hero + form). Isi form: email, password, Ingat Saya, Lupa Password, Masuk. Tanpa social login dan tanpa demo credential. Redirect: Platform Admin ke `/platform`, user tenant ke `/`, akun dengan password sementara ke `/change-password`.

**Tenant Provisioning + Tenant Admin Pertama — PASS.** Wizard 3 langkah. Toggle "Gunakan Email Utama Tenant sebagai Tenant Admin pertama" default ON.
- Jika OFF: isi Nama Tenant Admin, Email Login Tenant Admin, dan field Password sementara yang terisi "Dibuat otomatis oleh sistem" (read-only). Password sengaja selalu di-generate server, tidak diketik Platform Admin.
- Tenant, user, dan membership `tenant_admin` dibuat dalam satu proses. Jika gagal, semua perubahan dibatalkan (kompensasi).
- Kode duplikat → 409. Email admin sudah terdaftar → 409, tanpa meninggalkan tenant yatim.
- Password disimpan sebagai hash bcrypt. Ditampilkan sekali dengan tombol Salin. Audit mencatat create tenant/user/assign tanpa password.
- Tidak butuh SMTP atau aktivasi email.

**Wajib ganti password (baru) — PASS.**
- Backend `deps._base_auth` menolak semua API (403 + `X-Password-Change-Required: true`) selama `must_change_password=true`. Pengecualian: `/api/auth/me`, `/api/auth/change-password`, `/api/auth/logout`.
- Frontend punya halaman `/change-password`. `ProtectedRoute` dan interceptor API memaksa redirect ke sana.
- Password baru harus berbeda dari password sementara. Setelah diganti, flag dimatikan dan password lama langsung tidak berlaku.

**Reset Password (baru) — PASS.** `POST /api/platform/tenants/{tid}/users/{uid}/reset-password`, khusus Platform Admin.
- Menghasilkan password sementara baru, hanya ditampilkan sekali. Hash saja yang disimpan. `must_change_password` di-set true dan hitungan gagal login di-reset.
- Audit `reset_password` tanpa nilai password.
- User bukan anggota tenant → 404. Akun Platform Admin → 403.
- UI: tombol kunci per user → konfirmasi → dialog kredensial sekali tampil.

**Tenant Registry — PASS.** KPI, pencarian, filter status operasional dan masa layanan, kolom PIC/Email Utama/Tenant Admin/Jumlah User, logo tenant.

**Tenant Detail — PASS.** Tab Ringkasan, Users (tambah user, reset password, cabut Tenant Admin), dan Aktivitas. Tombol Ubah (tanpa password, kode permanen), Perpanjang layanan, Nonaktifkan/Aktifkan kembali. Minimal satu Tenant Admin wajib ada (409).

**Subscription / Renewal — PASS.** Status Active/Grace/Expired dihitung. Grace tetap bisa login dengan peringatan. Expired atau nonaktif → 403 + `X-Tenant-Status`. Renewal memulihkan akses. Platform Admin bypass. Tenant Admin tidak bisa mengubah masa layanan (403).

**Tenant Logo Upload max 10 MB — PASS.** PNG/JPG/JPEG/WEBP diterima. PNG ~9.99 MB diterima lewat ingress. >10 MB → 413. GIF atau PNG palsu → 415. Path `companies/{company_id}/branding/logo/…`. URL logo manual diabaikan. Bisa ganti/hapus. Audit upload/replace/delete tercatat.

**Platform vs Tenant Branding — PASS.** Path storage terpisah. Upload logo tenant tidak mengubah logo platform. Sidebar tenant menampilkan logo tenant + "Powered by KelolaKita". Konsol Platform menampilkan logo platform.

**Tenant Isolation — PASS.** Tenant B tidak bisa membaca logo/user/data tenant A. Switch ke tenant lain → 403. Reset/assign lintas tenant ditolak. Tenant lain tidak terdampak saat tenant A expired atau nonaktif.

**Permission/API Security — PASS.** Semua `/api/platform/*` untuk Tenant Admin → 403. `POST /companies` legacy → 403. Role `super_admin` tidak bisa diberikan dari tenant (403). Kode tenant tidak bisa diubah (400). Anonim ubah branding → 401/403.

## 8. Cleanup Final — PARTIAL (jujur)
Dihapus dari staging (hanya data yang dibuat agent untuk pengujian):
- Semua tenant uji `ZT*` / `ZTEST*` / `S*` beserta user `@zt-staging.co.id` / `@ztest-staging.co.id`, membership, modul, settings, audit, dan objek logo di storage.
- Artefak smoke: payroll run 2031-01; 3 karyawan "Smoke Tester" (soft-deleted); kandidat `SMOKE-C*`; 4 pengajuan cuti, 4 lembur, 1 absensi, 20 approval waktu, dan 88 jadwal kerja buatan smoke hari ini di NEP. Saldo cuti dihitung ulang (pending/used total = 0). 2 baris saldo cuti yatim juga dihapus.
- Fixture jadwal absensi: 0 tersisa. File sementara (password UI uji, logo uji) dihapus.

### 8.1 Target vs kondisi aktual
| Target user | Kondisi aktual | Status |
|---|---|---|
| Tenant: hanya PT REAL | **4 tenant**: REAL, KBS, NEP, CONTOHJASA | **Tidak sesuai target** |
| Tenant Admin PT REAL: 1 user | **1 user** (`hrcorp.staging@akuntakita.com`, satu-satunya membership di REAL, role `tenant_admin`, aktif) | Sesuai |
| Data dummy/test Tenant Foundation dihapus | Tidak ada lagi tenant/user uji (`ZT*`, `ZTEST*`, `@zt-staging`, `@ztest-staging` = 0) | Sesuai |

Target "hanya PT REAL + 1 Tenant Admin" **tidak tercapai secara literal**. Sisa data adalah data baseline lama dan data buatan user. Sesuai keputusan user (review 25 Sep 2026), data itu **dipertahankan** dan tidak dihapus hanya demi membuat laporan PASS. Karena itu status Cleanup Final tetap **PARTIAL**.

### 8.2 Inventaris aktual (dicek langsung ke DB `hris_staging` dan storage staging lokal, 25 Sep 2026 ±10:56 UTC, read-only)
Runtime saat pengecekan: DB `hris_staging` @ `127.0.0.1:3306`, `AUTO_SEED=false`, storage `s3-staging-local` (`127.0.0.1:5010`, bucket `hris-staging-media`, prefix `hris-payroll`), `APP_ENV=staging`. Tidak ada koneksi atau fallback ke produksi.

**Tenant tersisa (4):**
| Kode | Nama | Status | Dibuat (UTC) | Asal | Alasan dipertahankan |
|---|---|---|---|---|---|
| REAL | PT RAJAWALI EMAS ANCORA LESTARI | active (layanan s/d 2027-09-30) | 25 Sep 07:12 | Tenant target | Target kondisi akhir |
| KBS | PT Karya Bangun Sejahtera | active | 20 Sep 03:27 | Baseline existing (clone produksi) | Sudah ada sebelum task, keputusan user: pertahankan |
| NEP | PT Nusantara Energi Prima | active | 20 Sep 03:27 | Baseline existing (clone produksi) | Sudah ada sebelum task, keputusan user: pertahankan |
| CONTOHJASA | PT CONTOH JASA SELALU | active (layanan s/d 2026-09-30) | 25 Sep 10:35 | Dibuat user saat review manual di preview | Bukan data uji agent, keputusan user: pertahankan |

**User tersisa (15):**
| Email | Membership | Asal |
|---|---|---|
| `platform.admin@akuntakita.com` | Platform Admin (`super_admin`, global) | Akun staging, dibuat 25 Sep 07:12 |
| `superadmin@hris.id` | Platform Admin (`super_admin`, global) | Baseline (akun demo lama) |
| `hrcorp.staging@akuntakita.com` | REAL: `tenant_admin` | **Tenant Admin PT REAL** |
| `cs.akuntakita@gmail.com` | CONTOHJASA: `tenant_admin` | Dibuat user saat review |
| `owner@nep.co.id` | NEP: `company_owner` | Baseline |
| `hr.admin@nep.co.id` | NEP: `hr_admin` | Baseline |
| `hr.manager@nep.co.id` | NEP: `hr_manager` | Baseline |
| `finance@nep.co.id` | NEP: `finance` | Baseline |
| `manager@nep.co.id` | NEP: `manager` | Baseline |
| `supervisor@nep.co.id` | NEP: `supervisor` | Baseline |
| `karyawan@nep.co.id` | NEP: `employee` | Baseline |
| `owner@kbs.co.id` | KBS: `company_owner` | Baseline |
| `hr.admin@kbs.co.id` | KBS: `hr_admin` | Baseline |
| `karyawan@kbs.co.id` | KBS: `employee` | Baseline |
| `hr.multi@hris.id` | NEP: `hr_admin`, KBS: `hr_manager` | Baseline |

Rincian: 12 baseline (20 Sep) + 2 akun staging PT REAL/Platform (25 Sep 07:12) + 1 admin CONTOHJASA buatan user. Tidak ada user yang masih `must_change_password=true`.

**Tenant Admin PT REAL:** 1 user, `hrcorp.staging@akuntakita.com` (aktif). Tidak ada membership lain di tenant REAL.

### 8.3 Data dummy/test yang sudah dihapus
(Dihapus pada tahap cleanup sebelumnya. Review ini tidak menghapus apa pun.)
- Semua tenant uji `ZT*` / `ZTEST*` / `S*` beserta user `@zt-staging.co.id` / `@ztest-staging.co.id`, membership, modul, settings, audit, dan objek logo uji di storage.
- Artefak smoke: payroll run 2031-01; 3 karyawan "Smoke Tester" (soft-deleted); kandidat `SMOKE-C*`; 4 cuti, 4 lembur, 1 absensi, 20 approval waktu, 88 jadwal kerja buatan smoke di NEP. Saldo cuti dihitung ulang. 2 baris saldo cuti yatim dihapus.
- Fixture jadwal absensi (0 tersisa) dan file sementara (password UI uji, logo uji).

### 8.4 Data/storage lain yang dipertahankan (PRESERVE / DO NOT DELETE)
Isi storage staging (`hris-payroll/…`) = **19 object**. Status referensi DB dicek dengan mencari key object di semua kolom teks/JSON DB staging (read-only):

| Path | Tenant | Object | Direferensikan DB | Waktu file (UTC) | Keterangan |
|---|---|---|---|---|---|
| `platform/branding/logo` + `favicon` | Platform | 2 | Ya (`platform_settings`, audit) | 25 Sep 10:14 | Upload user. Keputusan: pertahankan |
| `companies/<NEP id>/branding/logo` | NEP | 1 | Ya (`companies.logo_path`) | 25 Sep 10:15 | Upload user. Keputusan: pertahankan |
| `companies/<CONTOHJASA id>/branding/logo` | CONTOHJASA | 1 | Ya (`companies.logo_path`) | 25 Sep 10:37 | Upload user. Keputusan: pertahankan |
| `companies/<NEP id>/documents` | NEP | 9 | 5 ya (`documents.storage_path`), 4 tidak | 5 file 03:15; 4 file (67 B) 03:56–03:59 | Baseline / sebelum sesi ini. 4 object tanpa referensi kemungkinan sisa smoke dokumen fase sebelumnya (belum dipastikan). Tidak diubah |
| `companies/<KBS id>/documents` | KBS | 1 | Ya (`documents.storage_path`) | 25 Sep 03:15 | Baseline. Tidak diubah |
| **`companies/351fedf6-…/documents`** | **UNKNOWN**: ID tidak ada di tabel `companies` staging | **3** (total 2.040 B) | **Tidak** (key object dan company ID tidak ditemukan di DB) | 25 Sep 03:15 | **Legacy storage existing**, sudah ada sebelum sesi ini (waktunya sama dengan snapshot clone 03:14). Tenant tidak bisa dipetakan dengan aman |
| **`companies/8d0df488-…/documents`** | **UNKNOWN**: ID tidak ada di tabel `companies` staging | **1** (1.146 B) | **Tidak** | 25 Sep 03:15 | Sama seperti di atas |

Ketentuan untuk legacy storage `companies/UNKNOWN:<id>/documents`: **PRESERVE / DO NOT MODIFY / DO NOT DELETE / DO NOT MOVE / DO NOT REMAP.** "UNKNOWN" atau tanpa referensi **tidak** berarti file tidak terpakai (bisa milik tenant produksi yang tidak ikut ter-clone). Jika kelak ingin dirapikan ke struktur baru (mis. `tenant/{tenant_id}/documents/...`), kerjakan sebagai **task migrasi storage terpisah**, lengkap dengan mapping DB, backup, validasi, dan rollback plan.

### 8.5 Perubahan selama review ini
Tidak ada perubahan code, database, maupun storage. Yang dilakukan hanya query dan listing read-only (skrip bantu di luar repo: `/root/tenant_tests/inventory_readonly.py`, `/root/tenant_tests/storage_refs_readonly.py`), lalu pembaruan laporan ini.

## 9. Files Changed (belum di-commit)
Backend (modified): `backend/app/core/audit.py`, `backend/app/core/db.py`, `backend/app/core/deps.py`, `backend/app/core/rbac.py`, `backend/app/routers/auth.py`, `backend/app/routers/companies.py`, `backend/app/routers/platform.py`, `backend/app/routers/users.py`, `backend/server.py`
Backend (new): `backend/app/core/branding_assets.py`, `backend/app/routers/branding.py`
Frontend (modified): `frontend/public/index.html`, `frontend/src/App.css`, `frontend/src/App.js`, `frontend/src/components/layout/AppShell.jsx`, `frontend/src/components/layout/Sidebar.jsx`, `frontend/src/components/layout/Topbar.jsx`, `frontend/src/lib/api.js`, `frontend/src/lib/auth.jsx`, `frontend/src/lib/nav.js`, `frontend/src/pages/CompanyProfilePage.jsx`, `frontend/src/pages/LoginPage.jsx`, `frontend/src/pages/ProfilePage.jsx`, `frontend/src/pages/platform/TenantsPage.jsx`
Frontend (new): `frontend/public/favicon.svg`, `frontend/src/components/common/TenantLogo.jsx`, `frontend/src/lib/branding.jsx`, `frontend/src/pages/ChangePasswordRequiredPage.jsx`, `frontend/src/pages/platform/PlatformBrandingPage.jsx`, `frontend/src/pages/platform/PlatformDashboardPage.jsx`, `frontend/src/pages/platform/TenantCreateWizard.jsx`, `frontend/src/pages/platform/TenantDetailPage.jsx`
Lainnya: `plan.md`, laporan ini, `test_reports/tenant_final/*` (log + test milik testing agent).
Migrations (sudah ada dari fase sebelumnya): `backend/migrations/m0001_tenant_foundation.py`, `backend/migrations/m0002_tenant_subscription.py`.

## 10. DB Schema Changes (Staging)
Semua additive dan nullable, tanpa drop atau rename:
- `companies`: `subscription_start_date` (varchar 32), `subscription_end_date` (varchar 32), `grace_period_days` (int), `subscription_notes` (text), `pic_name` (varchar), `pic_phone` (varchar 64), `logo_path` (varchar 512).
- Tabel baru `platform_settings` (`key` varchar 64 unik, `value` JSON): branding platform global.
- Data (m0001): role `super_admin` diberi label Platform Admin. Role sistem `tenant_admin` ditambahkan beserta izinnya (tanpa `company:create/delete`).
- Tidak ada kolom baru untuk fitur wajib ganti password. Kolom existing `users.must_change_password` dipakai ulang.

## 11. Findings, Fixes Applied, Remaining Issues
**Findings & fixes sesi ini:**
- Flow Tenant Admin pertama belum memaksa ganti password (hanya banner) dan belum ada Reset Password → diimplementasikan (backend guard, halaman `/change-password`, endpoint + UI reset).
- Change-password menerima password baru yang sama dengan yang lama → sekarang ditolak (400).
- 6 perbaikan visual (bagian 4).
- Temuan testing agent (false positive "Google") → diverifikasi, sumber komentar HTML dihapus.

**Remaining Issues (tidak dikerjakan, di luar scope atau butuh keputusan user):**
1. **Target cleanup tidak tercapai secara literal:** staging berisi 4 tenant (REAL, KBS, NEP, CONTOHJASA) dan 15 user, bukan hanya PT REAL + 1 Tenant Admin. Atas keputusan user, KBS/NEP/CONTOHJASA beserta usernya, logo/favicon platform, dan logo NEP **dipertahankan** (bagian 8).
1a. **Legacy storage tanpa referensi DB:** `companies/351fedf6-…/documents` (3 object) dan `companies/8d0df488-…/documents` (1 object). Company ID-nya tidak ada di staging. Ada juga 4 object kecil tanpa referensi di `companies/<NEP>/documents`. Semua **dipertahankan tanpa perubahan**. Merapikannya harus lewat task migrasi storage terpisah (mapping, backup, validasi, rollback).
2. **Akun demo baseline masih aktif di staging:** user me-review memakai `superadmin@hris.id`, akun demo dengan password publik (temuan 01A). Untuk staging tidak diubah. Untuk produksi tetap wajib rotasi password (lihat 01A).
3. Temuan 01A lain yang masih berlaku untuk produksi: dokumen R2 publik tanpa auth, dan risiko `AUTO_SEED` produksi. Tidak disentuh di task ini.
4. Atomicity provisioning memakai kompensasi (hapus balik jika gagal), bukan transaksi DB tunggal. Sudah teruji tanpa tenant yatim, tetapi secara teori belum setara transaksi.
5. `smoke_mariadb.py` meninggalkan payroll run 2031-01 (tidak bisa dihapus lewat API setelah submit). Perlu cleanup manual setiap run. Skrip bantu: `/root/tenant_tests/cleanup_smoke_payroll.py`.
6. Lint legacy (sudah ada sebelumnya, tidak diperbaiki): import `NO_ID` tak terpakai di `audit.py`, serta beberapa pelanggaran ruff lama di `auth.py`.
7. `DataTable` merender duplikat mobile tersembunyi dengan `data-testid` yang sama. Pola lama, tidak diubah.
8. Git: HEAD `4c54b85` dan `7c1164c` adalah **checkpoint otomatis platform** (lokal, tidak di-push). Tidak ada commit manual baru, tidak ada push/PR/merge.

---

**Production Changed: NO** · Deploy: NO · Commit manual/Push/PR/Merge: NO · Upgrade 01B: BELUM DIMULAI

**STOP. Menunggu review dan approval user.**
