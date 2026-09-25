# Upgrade 01B — Master Status Karyawan + Riwayat Status: Laporan

Branch lokal: `feature/upgrade-01b-employee-status` (base `a53cc40`, HEAD Tenant Foundation / PR #12)
Lingkungan: **STAGING SAJA**. Tidak ada commit, push, PR, merge, atau deploy. 01C tidak dikerjakan. Import Excel tidak didesain ulang.

**Production Changed: NO**

---

## Ringkasan hasil

| Area | Hasil |
|---|---|
| Runtime Safety | **PASS** |
| Migration (m0003) | **PASS** |
| System Categories | **PASS** |
| Master Status | **PASS** |
| Existing Employee Backfill | **PASS** |
| Current Status | **PASS** |
| Status History | **PASS** |
| Legacy Compatibility | **PASS** |
| Future effective date ditolak (FE + BE) | **PASS** |
| Archived / soft-deleted dipertahankan | **PASS** (lihat catatan: staging tidak punya data arsip/terhapus asli, diuji lewat simulasi terkontrol) |
| Tenant Isolation | **PASS** |
| Permission (`employee_status:manage` / `employee_status:change` + direct API / bypass) | **PASS** |
| Audit | **PASS** |
| Import Regression | **PASS** |
| Existing Modules Regression | **PASS** (ESS: run pertama 110/1 karena fixture saya, rerun 111/0; lihat Findings) |
| Restart Safety (2x) | **PASS** |
| Visual QA | **PASS** |
| Backend Compile | **PASS** |
| Frontend Build | **PASS** |
| `git diff --check` | **PASS** |
| Secret Scan | **PASS** |
| Testing Agent (iteration_23) | **PASS** (backend 39/39, frontend semua lulus, 0 bug) |
| Cleanup data uji ZT01B + artefak regression | **PASS** (audit log otomatis tetap disimpan; lihat Remaining Issues) |

---

## 1. Runtime Safety — PASS
- `/api/system/mode` → `environment=staging`, `database=mariadb`, `storage=s3-staging-local`, `auto_seed=false`, mode baca-tulis.
- DB `hris_staging` di `127.0.0.1:3306`. Storage: S3 staging lokal. `APP_ENV=staging`, `AUTO_SEED=false`.
- Tidak ada koneksi atau fallback ke DB/R2 produksi. Setiap skrip uji dan cleanup menolak jalan (assert) kalau DB bukan `127.0.0.1/hris_staging`.
- Backup sebelum migrasi: `.local-data/snapshots/staging_pre_01b.sql` (sudah di-gitignore, permission 600).

## 2. Migration — PASS
File: `backend/migrations/m0003_employee_status_foundation.py`. Hanya additive dan idempotent. Default dry-run, menulis hanya dengan `--apply`.
- Isi migrasi: ledger `schema_migrations`, tabel `employee_business_statuses` dan `employee_status_history`, kolom nullable `employees.current_employee_status_id` + index, permission baru + grant role, 3 status default per tenant, backfill karyawan.
- Tidak ada DROP, RENAME, atau perubahan tipe kolom. `employment_status_id` tidak disentuh.
- Urutan eksekusi: dry-run → apply (12:56 UTC) → run ulang `SKIP`. Sesi ini diulang lagi, dry-run maupun `--apply` sama-sama `SKIP (sudah diterapkan … dilewati)`.
- Hasil backfill: NEP 5 active + 1 inactive, KBS 3 active. REAL dan CONTOHJASA tidak punya karyawan.
- Setelah migrasi (dibandingkan dengan dump pra-01B, setelah cleanup): `permissions` +2, `role_permissions` +4, `employee_business_statuses` 12 (4 tenant × 3), `employee_status_history` 9 (baseline), `schema_migrations` 1.

## 3. System Categories — PASS
- `GET /api/employee-statuses/categories` → `ACTIVE/STANDBY/INACTIVE` dengan label `AKTIF/STANDBY/TIDAK AKTIF`, `locked=true`.
- Tidak ada endpoint untuk mengubah kategori: POST/PUT/DELETE → 404/405.
- Kategori selain tiga itu (`OTHER`, `AKTIF`, kosong) → 422.

## 4. Master Status — PASS
- CRUD per tenant (`company_id`): create 201, kode duplikat 409, edit nama/deskripsi 200.
- Kode dan kategori terkunci begitu status pernah dipakai (409). Status default tidak bisa dinonaktifkan atau dihapus (409).
- Hard delete ditolak untuk status yang sudah dipakai (409). Status yang belum pernah dipakai boleh dihapus (200).
- Status nonaktif tidak muncul sebagai pilihan dan tidak bisa di-assign (422). Riwayat lama tetap terbaca.
- UI Master HR → **Status Karyawan** (`/setup/employee-statuses`): tabel, filter, dialog tambah/edit, aksi aktif/nonaktif/hapus, jumlah penggunaan.

## 5. Existing Employee Backfill — PASS
- active → Aktif/AKTIF, inactive → Tidak Aktif/TIDAK AKTIF. Riwayat `source=LEGACY_BASELINE`, `effective_date=NULL` (tidak ada tanggal historis yang dikarang), `changed_by=NULL`.
- Status legacy seluruh 9 karyawan pra-01B identik dengan dump pra-migrasi (tes B4).

## 6. Current Status / 7. Status History — PASS
- `POST /api/employees/{id}/status-change` bersifat atomik dalam satu transaksi: update status bisnis, sync `employees.status`, tulis riwayat, tulis audit.
- Riwayat mencatat status sebelum/sesudah, tanggal efektif, alasan, catatan, source (`MANUAL/SYSTEM/IMPORT/LEGACY_BASELINE`), aktor, dan waktu pencatatan. Urutan terbaru di atas.
- Alasan wajib diisi. Status yang sama dengan status saat ini ditolak (422).
- UI: badge di daftar dan detail karyawan, aksi **Ubah Status** (dialog + konfirmasi + toast), kartu **Riwayat Status** di detail karyawan.

## 8. Legacy Compatibility — PASS
- AKTIF → `active`, STANDBY → `active` (tetap dihitung aktif di modul lain), TIDAK AKTIF → `inactive`.
- `archived` tetap status teknis. Pulihkan dari arsip mengikuti kategori bisnis terakhir, contohnya TIDAK AKTIF dipulihkan menjadi `inactive`.
- Form Edit tidak bisa lagi mengubah status (`status` berbeda → 422; status sama diabaikan).
- `PATCH /employees/{id}/status` sekarang hanya untuk arsip/pulihkan. Active ↔ inactive lewat endpoint ini → 409.

## 9. Future effective date (FE + BE) — PASS
- Backend: +1 hari, +365 hari, format salah, atau kosong → 422, termasuk bila dikirim Tenant Admin. Status dan riwayat tidak berubah (tes 15, A1). Tanggal hari ini diterima (A2).
- Frontend (browser): input tanggal punya `max=<hari ini>`. Tanggal masa depan memunculkan pesan "Tanggal efektif tidak boleh melebihi hari ini." dan dialog konfirmasi tidak terbuka (screenshot `m1_modal_future`).

## 10. Archived / soft-deleted legacy — PASS
- Backfill (fungsi yang sama dengan m0003) memberi archived/deleted status bisnis Tidak Aktif. `employees.status`, `updated_at`, `updated_by`, dan `employment_status_id` tidak berubah. Riwayat `LEGACY_BASELINE`. Backfill yang dijalankan dua kali tidak menambah apa pun (B1, tes 10).
- Karyawan arsip tidak bisa diaktifkan lewat Ubah Status (409), PUT (422), maupun PATCH active↔inactive (409). Karyawan terhapus: Ubah Status 404, PATCH 404, PUT 422. Tidak pernah teraktivasi (B2).
- Karyawan terhapus tidak tampil di daftar. Archived dan deleted tidak masuk filter aktif (B3).
- Catatan jujur: staging **tidak punya** karyawan archived/deleted asli sebelum 01B (dump pra-01B: 8 active, 1 inactive). Verifikasi ini memakai data uji ZT01B yang dikondisikan seperti data legacy pra-01B.

## 11. Tenant Isolation — PASS
- Tenant KBS tidak melihat status NEP. Edit/nonaktif status NEP dari KBS → 404.
- Assign status tenant lain → 422. Ubah status atau lihat riwayat karyawan tenant lain → 404.
- Spoof header/query `company_id` dengan token KBS tetap tidak bisa menyentuh karyawan NEP (C14).
- `pytest tests/test_tenant_isolation.py` 1/1. Provisioning tenant baru otomatis membuat 3 status default (tes PROV).

## 12. Permission — PASS
- `employee_status:manage` dan `employee_status:change` diberikan ke tenant_admin dan hr_admin. company_owner/super_admin sudah tercakup lewat mekanisme existing. hr_manager, finance, manager, supervisor, dan employee **tidak** mendapatkannya.
- Direct API:
  - hr_manager (punya `employee:edit`): create/edit/deactivate/activate/delete status → 403, status-change → 403.
  - finance: tulis → 403, lihat → 200.
  - karyawan (ESS): lihat daftar status → 403.
  - Tanpa login → 401.
  - Tenant Admin REAL: mengelola status di tenantnya sendiri 201/200, mengubah karyawan NEP → 404.
- Percobaan bypass:
  - PUT `/employees` dengan `current_employee_status_id` → diabaikan, tanpa riwayat.
  - PUT `status=inactive` → 422.
  - PATCH active→inactive → 409.
  - POST `/employees` dengan `current_employee_status_id`/`status` → diabaikan, tetap default Aktif.
  - ID status tidak dikenal → 404/422.
- UI: login hr_manager tidak memunculkan tombol Tambah Status, aksi Ubah Status di baris tabel, maupun tombol Ubah Status di detail (dicek lewat browser).

## 13. Audit — PASS
- Ubah status menulis audit `status_change` dengan before/after (status karyawan, tanggal efektif) di transaksi yang sama.
- Create/edit/aktif/nonaktif/hapus master status juga tercatat (tes 19).

## 14. Import Regression — PASS
- `backend/app/core/excel.py` dan `EmployeeImportPage.jsx` tidak berubah dibanding base. Kolom template tidak bertambah.
- Validasi + commit impor berjalan. Karyawan hasil impor mendapat default Aktif dengan riwayat `IMPORT` (tes 25, 26).

## 15. Existing Modules Regression — PASS
| Modul | Hasil | Log (`/root/tenant_tests/`) |
|---|---|---|
| Payroll / BPJS / PPh 21 TER / slip / Excel (`test_core.py`) | 186/186 | `reg01b_core_payroll.log` |
| API smoke: Employee, Master, Documents, Payroll run, Users (`smoke_mariadb.py`) | 45/45 | `reg01b_mariadb.log` |
| ESS / Absensi (`smoke_ess.py`) | run 1: 110/1 (fixture), **rerun 111/0** | `reg01b_ess.log`, `reg01b_ess_rerun.log` |
| Absensi / Cuti / Lembur (`smoke_time.py`) | 45/0 | `reg01b_time.log` |
| Rekrutmen → konversi karyawan (`recr_c_unique.py`) | 43/43 (hasil konversi mendapat default Aktif, riwayat `SYSTEM`) | `reg01b_recruitment.log` |
| Kontrak + detail karyawan | PASS (tes 30a) | `test_01b.py` |
| Tenant isolation pytest | 1/1 | `reg01b_tenant_isolation.log` |

## 16. Restart Safety — PASS
- Fingerprint seluruh tabel (CHECKSUM + COUNT, 61 tabel) diambil sebelum restart, setelah restart 1, dan setelah restart 2. Tidak ada tabel yang berubah (r0→r1: 0 tabel, r1→r2: 0 tabel).
- Mode tetap `auto_seed=false`. Migrasi tidak jalan ulang saat startup; ledger menjaga agar hanya sekali.

## 17. Visual QA — PASS
Desktop 1920 px + mobile 390 px, bahasa Indonesia, mengikuti pola desain yang ada (tanpa redesign):
- Master Status: tabel, badge kategori, jumlah penggunaan, dialog tambah, dialog edit dengan kode/kategori terkunci.
- Daftar Karyawan: kolom dan badge Status Karyawan, filter Status Karyawan / Kategori Status / Status Sistem (filter TIDAK AKTIF menampilkan 2 baris yang benar), badge "Diarsipkan".
- Dialog Ubah Status: status saat ini, pilihan status baru, validasi tanggal masa depan, konfirmasi, toast sukses, badge langsung terupdate.
- Detail karyawan: kartu Riwayat Status.
- Mobile: Master Status dan dialog Ubah Status.
- Perbaikan selama QA: warning React "Select uncontrolled → controlled" di dialog Ubah Status sudah diperbaiki dan dicek ulang (0 warning).

## 18. Backend Compile — PASS
`py_compile` untuk semua file yang diubah + `compileall app migrations server.py`: OK. `ruff --select F` untuk file baru 01B: bersih (3 import tak terpakai dihapus). Tidak ada format global atau `ruff --fix`.

## 19. Frontend Build — PASS
`esbuild` bundle OK. `yarn build` → "Compiled successfully." (exit 0).

## 20. `git diff --check` — PASS
Tidak ada error whitespace di file yang dimodifikasi. File baru: 0 trailing whitespace.

## 21. Secret Scan — PASS
Pola token/PAT/AKIA/private key/password/connection string/endpoint R2 di seluruh diff 01B (24 file): 0 temuan. Tidak ada email atau IP internal. Snapshot DB ada di `.local-data/` yang di-gitignore.

## 22. Testing Agent — PASS
`/app/test_reports/iteration_23.json`: backend 39/39, frontend semua fitur lulus, 0 bug kritis/UI/integrasi. File uji buatannya dipindahkan dari `/app` ke `/root/tenant_tests/backend_test_01b_agent.py` supaya tidak ikut ter-commit.

## 23. Migration File
`backend/migrations/m0003_employee_status_foundation.py`. Cara menjalankan: `python -m migrations.m0003_employee_status_foundation [--apply]` dari folder backend.

## 24. Files Changed
Dimodifikasi (01B):
- `backend/app/core/audit.py`: `build_audit_entry` agar audit bisa ditulis di dalam transaksi.
- `backend/app/core/db.py`: skema 2 tabel baru + kolom + index + helper transaksi.
- `backend/app/core/rbac.py`: resource `employee_status` (manage/change) + grant.
- `backend/app/routers/employees.py`: enrich, filter, default status saat create/import, blokir bypass status.
- `backend/app/routers/platform.py`: 3 status default saat provisioning tenant (+ kompensasi).
- `backend/app/routers/recruitment_conversion.py`: default status untuk hasil konversi.
- `backend/app/seed.py`: status default + baseline, hanya saat seed dijalankan eksplisit.
- `backend/server.py`: registrasi router.
- `frontend/src/App.js`, `frontend/src/lib/nav.js`: route dan menu.
- `frontend/src/components/common/FormDialog.jsx`: prop `disabled` untuk Select.
- `frontend/src/pages/EmployeesPage.jsx`, `frontend/src/pages/EmployeeDetailPage.jsx`, `frontend/src/pages/RolesPage.jsx`.

Baru (01B):
- `backend/app/core/employee_status.py`
- `backend/app/routers/employee_status.py`
- `backend/migrations/m0003_employee_status_foundation.py`
- `frontend/src/lib/employeeStatus.js`
- `frontend/src/components/employees/EmployeeStatusBadge.jsx`
- `frontend/src/components/employees/ChangeStatusDialog.jsx`
- `frontend/src/components/employees/StatusHistoryCard.jsx`
- `frontend/src/pages/EmployeeStatusMasterPage.jsx`

Di luar scope 01B tapi ada di working tree: `.env.example` dan `backend/.env.example` (dokumentasi `AUTO_SEED=false`, dimodifikasi 11:08 UTC sebelum sesi 01B dan tidak ada di PR #12). Tidak saya ubah; lihat Remaining Issues.

## 25. Findings
1. ESS smoke run pertama 110/1 ("shift hari ini SHIFT-P 08:00"). Penyebabnya fixture saya sendiri yang membuat jadwal hari ini dengan shift aktif pertama, sehingga bulk jadwal milik smoke (`overwrite_existing=false`) tidak menimpanya. Ini bukan bug aplikasi. Setelah fixture dihapus, rerun 111/0.
2. Warning React Select uncontrolled → controlled di dialog Ubah Status. Sudah diperbaiki.
3. Import `lucide-react` di `nav.js` sempat ditulis tidak rapi (`Gauge, UserCheck }`). Sudah dirapikan.
4. Uji tambahan C14 versi awal salah desain: token NEP dipakai ke karyawan NEP sendiri, jadi request-nya sah. Skenario diganti menjadi token KBS + spoof header/query NEP, hasilnya PASS. B2 awalnya mengharapkan PUT karyawan terhapus → 404, padahal perilaku existing 422. Tidak ada reaktivasi, jadi ekspektasi disesuaikan dan dicatat di bawah.
5. Selama sesi, pengguna mengubah Branding Platform (kontak support) lewat browser dengan akun super admin. Itu aktivitas pengguna, bukan otomasi tes, jadi **tidak dikembalikan**.

## 26. Fixes Applied
- `ChangeStatusDialog.jsx`: Select sekarang selalu controlled (`value=""` → placeholder).
- `nav.js`: format import dirapikan.
- `routers/employee_status.py`, `m0003`: import tak terpakai dihapus.
- Cleanup data uji (staging): 16 karyawan uji (ZT01B / SMOKE-C / Smoke Tester) + turunannya (riwayat 24, kontrak 1, saldo cuti 5), 4 kandidat SMOKE-C + turunannya, 5 status uji ZT01B, tenant uji `ZT01B130411` (user, membership, modul, settings, 3 status), efek samping smoke absensi/cuti/lembur/jadwal (88 jadwal, 3 absensi, 1 cuti, 1 lembur, 9 approval, 5 ledger), 72 audit log yang merujuk record uji.
- Pemulihan ke nilai pra-01B (dari dump): counter nomor karyawan NEP 33→17, `time_periods` 2026-08, `updated_at` LOC-WH, 5 baris `leave_balances` (angka identik, timestamp dipulihkan).
- Sisa row yang dibuat setelah migrasi: hanya `audit_logs`. Jumlah baris per tabel lain sama dengan dump pra-01B, kecuali tambahan migrasi 01B yang memang diharapkan.

## 27. Remaining Issues
1. `.env.example` dan `backend/.env.example` (AUTO_SEED default false) berubah di working tree dari sesi sebelum 01B, tidak termasuk PR #12. Perlu diputuskan sebelum commit 01B: dikeluarkan dari commit 01B, atau dijadikan perubahan terpisah.
2. Sekitar 109 audit log dari otomasi tes (login/logout akun demo, aksi regression) dan `users.updated_at` (login terakhir 13 akun) tetap disimpan sebagai jejak audit. Tidak dihapus.
3. Staging tidak punya karyawan archived/soft-deleted asli. Perilaku migrasi untuk kasus ini diverifikasi lewat simulasi terkontrol (fungsi backfill yang sama). Ulangi pengecekan saat menjalankan m0003 di produksi (dry-run dulu).
4. Perilaku existing (bukan dari 01B): PUT ke karyawan soft-deleted mengembalikan 422, bukan 404. Tetap tidak bisa diaktifkan kembali.
5. Pola existing DataTable merender salinan desktop + mobile, jadi sebagian `data-testid` baris muncul dua kali (satu tersembunyi). Tidak diubah (di luar scope).
6. Riwayat awal karyawan hasil konversi rekrutmen memakai `source=SYSTEM` (tidak ada source khusus RECRUITMENT). Alasan riwayatnya "Status awal dari konversi kandidat".
7. m0001/m0002 tidak tercatat di ledger `schema_migrations`, karena ledger baru diperkenalkan m0003. Keduanya tetap idempotent by design.
8. Peringatan ruff gaya (UP006/UP045/B008) di file baru mengikuti gaya codebase (`Optional`/`Depends`). F401 pre-existing di `audit.py` dan `db.py` tidak disentuh.
9. `test_reports/iteration_23.json` masih untracked. Putuskan saat commit nanti.
10. 01B belum di-commit, push, atau dibuatkan PR, sesuai instruksi. Setelah PR #12 merge ke `main`, 01B perlu di-rebase/cherry-pick agar hanya berisi perubahan 01B.

---
**Production Changed: NO**
STOP — menunggu review.
