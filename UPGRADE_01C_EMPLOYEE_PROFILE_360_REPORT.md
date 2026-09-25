# UPGRADE 01C — EMPLOYEE PROFILE 360

Environment: **STAGING ONLY** (MariaDB `hris_staging` @ localhost, local S3 staging storage, `AUTO_SEED=false`).
Branch: `feature/upgrade-01c-employee-profile-360` (lokal, dibuat dari commit lokal 01B `2198b7e`).
Belum ada commit, push, PR, merge, atau deploy untuk 01C.

## Ringkasan Hasil

| Item | Hasil |
|---|---|
| Runtime Safety | **PASS** (`/api/system/mode`: environment staging, mariadb, s3-staging-local, auto_seed false) |
| Migration | **PASS** (m0004 diterapkan sekali; dijalankan ulang → SKIP; ledger 1 baris) |
| Profile 360 | **PASS** |
| Ringkasan | **PASS** |
| Data Pribadi | **PASS** |
| Keluarga | **PASS** |
| Kepegawaian | **PASS** |
| Penempatan Saat Ini | **PASS** (hanya penempatan saat ini, tanpa riwayat) |
| Bank & Pajak | **PASS** |
| BPJS | **PASS** |
| Dokumen | **PASS** (modul existing dipakai ulang) |
| Kontrak | **PASS** (modul existing dipakai ulang) |
| Sertifikasi | **PASS** (modul existing dipakai ulang) |
| Riwayat | **PASS** (riwayat status 01B + aktivitas dari audit log) |
| Foto Profil | **PASS** (upload/ganti/hapus, JPG/PNG/WEBP, maks 10 MB, fallback inisial; carry-over: editor crop 1:1 + zoom/drag + preview lingkaran) |
| Tenant Isolation | **PASS** |
| Permission / Sensitive Data | **PASS** (carry-over: NIK KTP ikut dimasking; payroll murni permission-based, lihat bagian 21) |
| Audit | **PASS** |
| Import Regression | **PASS** |
| Payroll / Attendance / Recruitment Regression | **PASS** (ESS run pertama 110/1 karena urutan fixture; rerun 111/0, lihat Findings) |
| Tenant Foundation Regression | **PASS** |
| 01B Regression | **PASS** (43/43 + 21/21) |
| Existing Modules Regression | **PASS** |
| Restart Safety (x2) | **PASS** (fingerprint semua tabel identik r0 = r1 = r2) |
| Visual QA (desktop/tablet/mobile) | **PASS** |
| Backend Compile | **PASS** |
| Frontend Build | **PASS** (`yarn build` → "Compiled successfully.") |
| `git diff --check` | **PASS** |
| Secret Scan | **PASS** (0 temuan di 12 file) |
| Testing Agent | **PASS** (iteration_24: backend 38/38; frontend 19/20, satu langkah tidak diselesaikan harness agent, lihat Findings) |
| Cleanup ZT01C | **PASS** (semua data ZT01C terhapus; lihat Remaining Issues untuk data non-ZT01C) |
| **01C Carry-over** (NIK, payroll, crop foto) | **PASS** (34/34 + UI crop, lihat bagian 21) |
| **01C Locked** | **YES** |
| **Production Changed** | **NO** |

---

## 1. Runtime Safety — PASS
- `/api/system/mode` → `environment=staging`, `database=mariadb`, `storage=s3-staging-local`, `auto_seed=false`, `read_only=false`.
- Semua skrip uji punya pengaman: berhenti bila DB bukan `hris_staging` di localhost.
- Backup staging sebelum 01C: `.local-data/snapshots/staging_pre_01c.sql` (tidak di-track git).

## 2. Migration — PASS
- File: `backend/migrations/m0004_employee_profile_360.py` (additive, sekali jalan, dicatat di ledger `schema_migrations`).
- Isi migrasi:
  - tabel baru `employee_family_members` (tenant-scoped `company_id`, index `(company_id, employee_id)`);
  - kolom nullable baru di `employees`: `domicile_address`, `province`, `postal_code`, `photo_path`, `photo_version`.
- Tidak ada DROP, RENAME, atau perubahan tipe kolom.
- Tidak ada backfill data keluarga. Field legacy `emergency_contact_*` tidak memuat hubungan keluarga yang pasti, jadi dibiarkan apa adanya.
- Test 38 (ledger 1 baris, tabel dan 5 kolom ada) PASS. Test 39 (rerun `--apply` → SKIP, ledger tetap 1 baris) PASS.

## 3. Profile 360 dan 11 Tab — PASS
Halaman `/employees/{id}` sekarang punya:
- **Header profil**: foto atau avatar inisial, nama, nomor karyawan, badge Status Karyawan 01B beserta kategorinya, Jabatan, Divisi/Departemen, dan Project/Site. Tombol Unggah/Ganti/Hapus Foto hanya muncul untuk `employee:edit`.
- **11 tab**:

| Tab | Isi |
|---|---|
| Ringkasan | Status Karyawan, Status Hubungan Kerja, Project/Site, Posisi, Tanggal Bergabung, Kontak, ringkasan Dokumen dan Kontrak |
| Data Pribadi | Identitas, kontak, alamat KTP/domisili, provinsi, kode pos, kontak darurat. Edit per bagian |
| Keluarga | CRUD anggota keluarga |
| Kepegawaian | Hubungan kerja, Atasan/Supervisor, kartu Status Karyawan (hanya tampil), organisasi. Edit per bagian |
| Penempatan Saat Ini | Hanya penempatan saat ini, dengan catatan bahwa riwayat penempatan masuk 01D |
| Bank & Pajak | Rekening, NPWP, PTKP (hanya baca, dari payroll) |
| BPJS | Nomor kepesertaan saja |
| Dokumen / Kontrak / Sertifikasi | Modul existing, tidak diubah |
| Riwayat | Riwayat status 01B + timeline aktivitas dari audit log |

- Tab existing **Gaji & Payroll** tetap ada, dan hanya tampil untuk pengguna yang punya akses payroll.
- Setiap form edit per bagian mengirim `?section=` sehingga audit mencatat keterangan seperti "Data pribadi diubah" atau "Data BPJS diubah".
- Form edit tidak punya field Status Karyawan.
- **Atasan/Supervisor**: diambil hanya dari relasi existing `positions.reports_to_position_id`. Nama atasan ditampilkan bila tepat satu karyawan aktif memegang jabatan atasan itu; kalau tidak ada, tampil `-`. Tidak ada schema atau relasi baru. Uji SV dan SV2 PASS.

## 4. Foto Profil — PASS
- Memakai helper existing `read_image_upload` (cek ekstensi, MIME, dan signature isi berkas; maks 10 MB) dan `core/storage` (`put_object`, `get_object`, `delete_object`).
- Path tenant-aware: `<app>/companies/{company_id}/employees/{employee_id}/photo/{uuid}.{ext}`.
- Foto disajikan lewat endpoint API yang memeriksa hak akses. `photo_path` tidak pernah dikirim ke klien; klien hanya menerima `photo_url`.
- Saat foto diganti, objek lama dihapus. Saat foto dihapus, objeknya ikut dihapus dan tampilan kembali ke avatar inisial.
- Validasi: GIF → 415, PNG palsu → 415, lebih dari 10 MB → 413, token tenant lain → 404, user view-only → 403.
- Diuji lewat API (P1) dan lewat UI (upload melalui input berkas, lalu foto langsung tampil).

## 5. Keluarga — PASS
- Endpoint `GET/POST/PUT/DELETE /api/employees/{id}/family[/{family_id}]`.
- Validasi: hubungan harus salah satu dari SUAMI/ISTRI/ANAK/AYAH/IBU/SAUDARA/LAINNYA; nama minimal 2 karakter; NIK opsional tetapi harus 16 digit; tanggal lahir tidak boleh di masa depan.
- Baris keluarga harus cocok dengan `company_id` dan `employee_id`. Mengakses baris keluarga lewat karyawan lain, atau lewat tenant lain, menghasilkan 404.
- Setiap perubahan tercatat di audit (`family_create`, `family_update`, `family_delete`).

## 6. Masking Data Sensitif — PASS
- `core/sensitive.py`: field sensitif adalah `bank_account_number`, `npwp`, `bpjs_kesehatan_number`, `bpjs_tk_number`.
- Pengguna `employee:edit` melihat nilai penuh. Pengguna yang hanya `employee:view` melihat nilai tersamar (mis. `*********9887`) dan menerima `sensitive_masked: true`.
- Masking dilakukan di backend pada `GET /employees` (list) dan `GET /employees/{id}`. NIK anggota keluarga juga disamarkan untuk user view-only.
- `PUT /employees/{id}` menolak nilai yang mengandung karakter `*` (422), supaya nilai tersamar tidak tersimpan menggantikan data asli.
- Tidak ada permission baru.
- Di halaman profil, tab Gaji & Payroll kini menampilkan NPWP dan rekening dari data profil yang sudah dimasking, bukan dari respons payroll.

## 7. Tenant Isolation — PASS
Token KBS terhadap karyawan NEP: detail, family (GET/POST/PUT/DELETE), photo (GET/POST), timeline, status-history, dan PUT karyawan semuanya menghasilkan **404**. List KBS tidak memuat nilai sensitif NEP.

## 8. Audit — PASS
- Saat ditulis (`core/audit.py`), `before_value` dan `after_value` dimasking untuk bank, NPWP, BPJS, dan NIK.
- Saat dibaca (`routers/audit_logs.py`), masking juga diterapkan pada list dan export. Jadi log lama pun tidak membuka nilai penuh lewat API.
- Uji S6: nilai penuh tidak ada di DB audit untuk record uji dan tidak ada di respons `/api/audit-logs`.
- Timeline tidak mengembalikan before/after, hanya aksi, label, pengguna, waktu, dan jumlah field yang berubah.

## 9. Hasil 40 Test Wajib + Tambahan
Suite: `/root/tenant_tests/test_01c.py`, hasil **43/43 PASS**; `test_01c_extra.py` (SV2), hasil **PASS**.

| No | Test | Hasil |
|---|---|---|
| 01 | Buka profil 360 tenant yang sama | PASS |
| 02 | Akses karyawan tenant lain → DENIED | PASS |
| 03 | Ringkasan menampilkan data saat ini | PASS |
| 04 | Status Karyawan 01B tampil | PASS |
| 05 | Status tidak bisa dibypass lewat edit profil | PASS |
| 06 | Edit Data Pribadi | PASS |
| 07 | Validasi NIK unik tetap berlaku (duplikat → 409) | PASS |
| 08 | `employee_number` tetap sama | PASS |
| 09 | Tambah anggota keluarga (+ validasi) | PASS |
| 10 | Edit anggota keluarga | PASS |
| 11 | Hapus anggota keluarga | PASS |
| 12 | Keluarga dari tenant lain / karyawan lain → DENIED | PASS |
| 13 | Employment Status terpisah dari Status Karyawan | PASS |
| 14 | Edit data kepegawaian | PASS |
| 15 | Project saat ini tampil benar | PASS |
| 16 | Tidak ada tabel riwayat penempatan yang dibuat | PASS |
| 17 | Tampil + edit data bank | PASS |
| 18 | Akses data bank sesuai permission/masking | PASS |
| 19 | Tampil + edit BPJS | PASS |
| 20 | Dokumen existing tampil | PASS |
| 21 | Operasi dokumen existing (update/download/tenant/hapus) | PASS |
| 22 | Kontrak existing tampil | PASS |
| 23 | Operasi kontrak existing | PASS |
| 24 | Sertifikasi existing tampil | PASS |
| 25 | Operasi sertifikasi existing | PASS |
| 26 | Riwayat status 01B tampil + alur Ubah Status tercermin | PASS |
| 27 | Audit perubahan profil (bagian, keluarga, foto) | PASS |
| 28 | Buat karyawan (existing) | PASS |
| 29 | Edit karyawan (existing, tanpa `section`) | PASS |
| 30 | List/search/filter/pagination | PASS |
| 31 | Template import Excel tidak berubah (git diff terhadap `2198b7e` bersih untuk `excel.py`, `EmployeeImportPage.jsx`, dan blok route import) | PASS |
| 32 | Import Excel tetap berjalan | PASS |
| 33 | Payroll regression (`test_core.py`, `smoke_mariadb` 45/45, S5 payroll membaca nilai penuh) | PASS |
| 34 | Attendance regression (`smoke_time` 45/0, `smoke_ess` rerun 111/0) | PASS |
| 35 | Recruitment regression (43/43) | PASS |
| 36 | Tenant Foundation regression (pytest isolation 1/1, tenant_foundation_test 7/7) | PASS |
| 37 | 01B regression (43/43 + 21/21) | PASS |
| 38 | Migrasi diterapkan sekali | PASS |
| 39 | Rerun migrasi di-skip | PASS |
| 40 | Restart backend 2x tanpa mutasi data bisnis | PASS |

Uji sensitif tambahan:

| Kode | Test | Hasil |
|---|---|---|
| S1 | `employee:edit` melihat nilai penuh | PASS |
| S2 | `employee:view` melihat nilai tersamar (detail, list, NIK keluarga) | PASS |
| S3 | Percobaan bypass langsung lewat API oleh user view-only (query `full`/`unmask`, list, timeline, audit, PUT/POST/foto) → masked/403; nilai tersamar tidak bisa disimpan balik → 422 | PASS |
| S4 | Akses sensitif lintas tenant → DENIED | PASS |
| S5 | Endpoint payroll tetap membaca nilai penuh | PASS |
| S6 | Audit tidak menyimpan atau membuka nilai penuh | PASS |

Uji lain: P1 (foto) PASS, T1 (timeline) PASS, SV/SV2 (supervisor) PASS.

## 10. Restart Safety x2 — PASS
Fingerprint read-only (COUNT + CHECKSUM untuk 62 tabel) diambil sebelum dan sesudah setiap `supervisorctl restart backend`. Hasil r0 = r1 = r2 identik, dan `/api/health` 200 setelah tiap restart.

## 11. Visual QA — PASS
- **Desktop 1920**: semua 11 tab diperiksa (Ringkasan, Data Pribadi, Keluarga, Kepegawaian, Penempatan, Bank & Pajak, BPJS, Dokumen, Kontrak, Sertifikasi, Riwayat), dengan foto, dialog edit Data Pribadi, dialog Tambah Keluarga, toast, empty state keluarga/timeline, dan avatar inisial.
- **View-only (finance)**: Bank, BPJS, dan NIK keluarga tampil tersamar dengan catatan masking. Tidak ada tombol edit, unggah, atau tambah.
- **Tablet 820 dan mobile 390**: tab bisa digeser horizontal, tidak ada overflow halaman (`scrollWidth` 390), kartu bertumpuk rapi, nama panjang dibungkus.
- Perbaikan visual yang dilakukan:
  - tinggi header kartu diseragamkan;
  - angka memakai `tabular-nums`, bukan font mono sistem;
  - grid Kepegawaian memakai `items-start`;
  - fakta header 2 kolom di tablet;
  - nama di header mobile 2 baris, tidak dipotong;
  - "N field berubah" hanya muncul untuk aksi update;
  - `<div>` di dalam `<p>` (peringatan hydration) diperbaiki.

## 12. Technical Checks
- Backend compile (`py_compile` untuk server, core, routers, migrations): **PASS**.
- Frontend: esbuild bundle OK; `yarn build` "Compiled successfully." **PASS**.
- `git diff --check`: **PASS**. Tidak ada trailing whitespace di file baru.
- Secret scan (nilai `.env`, DEMO_PASSWORD, pola token/kunci/connection string) pada 12 file yang berubah atau baru: **0 temuan**.
- Tidak ada mass formatting; tidak memakai `ruff --fix` atau npm.
- ESLint v9 tidak punya `eslint.config.*` di project, jadi tidak dipakai sebagai gate.

## 13. Testing Agent — PASS
Laporan: `test_reports/iteration_24.json`.
- Backend 38/38 PASS: masking, permission, tenant, validasi, keluarga, foto, timeline, audit.
- Frontend 19/20: login, 11 tab, foto, dialog edit, Ubah Status, tambah keluarga, list/search.
- Satu langkah (login ulang sebagai finance di sesi browser yang sama) tidak diselesaikan oleh harness agent. Ini bukan bug aplikasi. Skenario finance/view-only sudah saya verifikasi sendiri lewat screenshot (masked, tanpa tombol edit).
- Tidak ada bug yang dilaporkan.
- Skrip agent `backend_test_01c.py` yang sempat dibuat di `/app` dipindahkan ke `/root/tenant_tests/backend_test_01c_agent.py` agar tidak ikut diff.

## 14. Cleanup ZT01C — PASS
- `cleanup_01c.py` (dry-run lalu `--apply`) menghapus hanya data uji yang dibuat setelah awal sesi 01C:
  - karyawan ZT01C beserta turunannya (keluarga, kontrak, sertifikat, riwayat status, dokumen milik karyawan uji, objek storage foto dan dokumen uji);
  - jabatan uji ZT01C;
  - audit yang merujuk record uji;
  - artefak regression (karyawan/kandidat SMOKE, status uji ZT01B, efek samping smoke ESS/Time);
  - counter nomor NEP dikembalikan ke 17.
- Tenant uji ZTA/ZTB/ZT01B* dari tenant_foundation_test dan test_01b dihapus dengan `cleanup_zt_tenants_01c.py`. Ini varian `cleanup_final.py` tanpa sapuan orphan branding, supaya storage di luar tenant uji tidak tersentuh.
- Tabel `time_periods`, `leave_balances`, `work_locations` sempat diubah oleh smoke regression. Ketiganya dipulihkan dari dump pra-01C dan checksum-nya cocok 100%.
- Verifikasi akhir: 0 karyawan ZT01*, 0 baris keluarga, 0 objek foto uji, tenant tersisa CONTOHJASA/KBS/NEP/REAL.
- Data baseline, data PT REAL, data 01B, dan legacy storage tidak disentuh.

## 15. Migration File
`backend/migrations/m0004_employee_profile_360.py`

## 16. Files Changed
**Diubah:**
- `backend/app/core/audit.py`: masking sensitif saat audit ditulis.
- `backend/app/core/db.py`: spesifikasi tabel `employee_family_members`, kolom baru `employees`, index.
- `backend/app/routers/audit_logs.py`: masking saat audit dibaca/diekspor.
- `backend/app/routers/employees.py`: masking list/detail, `photo_url`, `?section=`, penolakan nilai tersamar, supervisor dari relasi existing.
- `backend/app/schemas.py`: `domicile_address`, `province`, `postal_code`.
- `backend/server.py`: registrasi router `employee_profile`.
- `frontend/src/pages/EmployeeDetailPage.jsx`: 11 tab, header profil, dialog edit per bagian, tab payroll memakai nilai profil yang sudah dimasking.

**Baru:**
- `backend/app/core/sensitive.py`
- `backend/app/routers/employee_profile.py` (keluarga, foto, timeline)
- `backend/migrations/m0004_employee_profile_360.py`
- `frontend/src/components/employees/ProfileSections.jsx`

**Lainnya:**
- `plan.md` diperbarui.
- `test_reports/iteration_24.json` baru, dari testing agent (mengikuti konvensi iteration_23).
- `.env.example` dan `backend/.env.example` tetap sebagai perubahan working tree era foundation. Tidak disentuh dan tidak termasuk 01C.
- **Carry-over:** `backend/app/core/sensitive.py` (NIK + masking audit rekursif), `frontend/src/components/employees/PhotoCropDialog.jsx` (baru), `frontend/src/components/employees/ProfileSections.jsx` (alur pilih → crop → simpan), `frontend/package.json` + `yarn.lock` (`react-easy-crop`, via `yarn add`).

## 17. Findings
1. ESS smoke run pertama 110/1 ("shift hari ini SHIFT-P 08:00"). Penyebabnya sama seperti di 01B: `time_fixture --ensure-schedule` dijalankan sebelum smoke ESS, sehingga jadwal bulk smoke tidak menimpanya. Ini bukan bug aplikasi. Setelah fixture jadwal dihapus, rerun 111/0.
2. **Insiden cleanup (kesalahan skrip saya):** versi pertama `restore_reg_tables_01c.py` memakai regex yang salah (dump menaruh `VALUES` lalu baris baru). Akibatnya `time_periods` (1 baris), `leave_balances` (8), dan `work_locations` (5) sempat kosong beberapa detik di staging. Ketiganya langsung dipulihkan dari dump pra-01C dengan checksum cocok, dan skrip kini berhenti tanpa perubahan bila INSERT tidak ditemukan.
3. Temuan visual kecil sudah diperbaiki (lihat bagian 11).
4. Tab Gaji & Payroll di profil sebelumnya menampilkan NPWP dan rekening penuh dari respons payroll ke pengguna yang punya akses payroll tetapi hanya `employee:view`. Sekarang tab itu memakai nilai profil yang sudah dimasking.

## 18. Fixes Applied
- Masking audit juga saat dibaca (log lama ikut aman).
- `photo_path` tidak dikirim dalam respons update.
- Supervisor diambil dari `positions.reports_to_position_id` (sebelumnya selalu `-`).
- Tab payroll di profil memakai nilai yang sudah dimasking.
- Perbaikan visual dan HTML nesting (bagian 11).
- Skrip restore diberi pengaman.

## 19. Deferred
- **01D**: riwayat penempatan/assignment, mutasi/transfer, standby pool, roster/mobilisasi, tanggal mulai penempatan (field "Tanggal Mulai" di tab Penempatan tampil `-`).
- **01E**: redesign import Excel. Field baru (domisili, provinsi, kode pos, keluarga, foto) belum ada di template, sesuai instruksi.
- **01F**: ESS / Public Form, verifikasi data.
- **01G/01H**: Data Completeness engine dan scope lanjutan lainnya.

## 20. Remaining Issues
1. ~~Endpoint payroll~~ **Selesai di carry-over (bagian 21):** nilai rekening/NPWP penuh hanya keluar lewat permission payroll existing (`employee_salary:view`, `payroll:view/export`), tanpa hardcode nama role. Pengguna yang hanya `employee:view` mendapat 403 di endpoint payroll.
2. Baris audit lama sebelum 01C di DB bisa masih berisi nilai sensitif penuh. API audit (list/export) sekarang memaskingnya saat dibaca, tetapi DB tidak ditulis ulang.
3. ~~NIK KTP tidak dimasking~~ **Selesai di carry-over:** NIK KTP termasuk data sensitif (lihat bagian 21).
4. Foto baseline **Bambang Setiawan (NEP-0002)**: sesuai keputusan Anda, dicek dulu lewat audit. Aksi pertama tercatat `photo_upload` (bukan `photo_replace`), dan kolom foto baru ada sejak 01C, jadi sebelumnya memang tidak ada foto. Foto dihapus lewat API resmi (`DELETE /photo`, tercatat di audit), sehingga kembali ke avatar inisial. Objek storage-nya juga sudah terhapus.
5. Audit log otomatis dari regression dan login (+115 baris) serta `users.last_login` tetap disimpan, sama seperti 01B. Tidak dihapus agresif.
6. Select wajib di `FormDialog` existing (mis. "Hubungan" di dialog keluarga) menampilkan placeholder kosong. Ini komponen bersama existing, jadi tidak diubah di 01C.
7. Nama dan status tampil di page header existing dan juga di kartu profil. Redundansi kecil, dibiarkan.
8. Timeline menampilkan maksimal 200 peristiwa terbaru.
9. ESLint v9 tidak dikonfigurasi di project, jadi lint tidak menjadi gate.

## 21. 01C Carry-over — PASS

### A. NIK KTP sebagai data sensitif
- `nik` masuk `EMPLOYEE_SENSITIVE_FIELDS` (`backend/app/core/sensitive.py`). Masking dilakukan di API (list + detail); NIK anggota keluarga sudah dimasking sejak 01C.
- User tanpa `employee:edit` tidak bisa mencari berdasarkan NIK, jadi pencarian tidak bisa dipakai untuk menebak nilai yang dimasking. `employee:edit` tetap bisa mencari.
- Aturan NIK unik tetap sama (create/update duplikat ditolak). Nilai yang dimasking (`*`) ditolak saat disimpan.
- Masking audit sekarang rekursif (dict/list bersarang), jadi item payroll di before/after juga aman.

### B. Payroll tanpa bypass
- `GET /api/payroll/salaries/{id}` mengembalikan rekening/NPWP penuh hanya lewat permission existing `employee_salary:view`. Endpoint run/bank-file memakai `payroll:view/export`. Tidak ada hardcode nama role. Respons payroll tidak memuat NIK.
- Pengguna yang hanya `employee:view` (mis. `manager`) mendapat 403 di `/payroll/salaries`, `/payroll/salaries/{id}`, `/payroll/runs`, `/payroll/summary`. Akses lintas tenant mendapat 404.
- Finance (payroll + `employee:view`) tetap melihat nilai yang dimasking di Profil Karyawan; akses payroll tidak melonggarkan masking profil.

### C. Editor crop foto profil (tambahan permintaan Anda)
- Alur: Pilih Foto → Atur Posisi Wajah (drag) → Zoom (slider + tombol −/+) → Preview lingkaran → **Simpan Foto**. Komponen: `frontend/src/components/employees/PhotoCropDialog.jsx` (dependensi baru ringan `react-easy-crop@5`).
- Hasil crop 1:1 dari piksel asli (tanpa stretch), output JPEG maksimal 800 px. Latar putih untuk PNG/WEBP transparan.
- Posisi awal: memakai `FaceDetector` bawaan browser bila tersedia (hanya posisi awal, bukan identifikasi). Kalau tidak tersedia, foto portrait diarahkan ke sepertiga atas (area kepala + sedikit ruang di atas kepala) dan landscape di tengah. Semuanya tetap bisa digeser/zoom manual.
- Validasi JPG/PNG/WEBP dan maksimal 10 MB tetap berlaku di frontend dan backend. Foto lama baru diganti setelah upload baru berhasil.

### Bukti uji carry-over
| Uji | Hasil |
|---|---|
| `test_01c_carry.py` (C01–C34: NIK edit/view/list/search/cross-tenant/403, NIK unik, tolak nilai masking, audit DB+API tanpa nilai penuh, audit rekursif, payroll authorized/unauthorized/bypass/cross-tenant, audit payroll, foto format/ukuran ditolak, foto lama tetap bila upload gagal) | **34/34 PASS** |
| UI crop portrait: zoom 1.0x→1.4x, drag mengubah preview, simpan → avatar tampil; hasil 429×429 JPEG berisi area kepala | **PASS** |
| UI crop landscape (mobile 390 px): dialog 366 px, tombol zoom 44×44, tanpa scroll horizontal, simpan OK | **PASS** |
| Upload gagal (500 disimulasikan) → dialog tetap terbuka, foto lama tetap tampil, toast "Foto lama tetap dipakai" | **PASS** |
| Orientasi EXIF 6 (foto HP): blok merah di atas raw tampil di KANAN hasil crop (rotasi benar), output 600×600 | **PASS** |
| File >10 MB / GIF → ditolak sebelum editor terbuka (toast) | **PASS** |
| Payroll regression `test_core.py` | **186/186 PASS** |
| `smoke_mariadb.py` (termasuk payroll run) | **45/45 PASS** (artefak payroll smoke dibersihkan) |
| Backend compile / `yarn build` / `git diff --check` | **PASS** / **PASS (Compiled successfully)** / **PASS** |
| Secret scan (21 file berubah/untracked) | **PASS**. Satu kandidat adalah label storage staging lokal `s3-<nilai placeholder R2_ACCOUNT_ID staging>` di `server.py` (sudah ada sebelumnya) dan laporan ini. Itu nama placeholder lokal, bukan kredensial. |
| Cleanup | Fixture `ZT01C Carry*` (4 karyawan) + `Smoke Tester` dihapus. Counter NEP dikembalikan ke 17. Fingerprint setelah cleanup sama dengan pra-uji, kecuali `audit_logs` (+22 baris login/aksi uji) dan `users.last_login`. |

Catatan: warning console `width(-1)/height(-1) of chart` berasal dari chart Dashboard saat login, bukan dari Profile 360. Warning HTML nesting 01C tidak muncul lagi.

**01C LOCKED: YES**

## Production Changed: **NO**
Tidak ada akses, penulisan, atau deploy ke production (DB maupun R2). Tidak ada commit, push, PR, atau merge untuk 01C.

**STOP — menunggu review.**
