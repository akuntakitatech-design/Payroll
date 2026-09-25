# UPGRADE 01E — EMPLOYEE MIGRATION PROGRESS (CHECKPOINT BACKEND-FIRST)

> Status keseluruhan 01E: **BELUM SELESAI**. Yang selesai baru checkpoint backend. UI, performance test, QA visual,
> testing_agent_v3 final, cleanup final ZT01E, dan laporan final **BELUM DIKERJAKAN**.
> Semua hasil di bawah ini diuji oleh agent di staging, **belum dikonfirmasi user**.
> Production Changed: **NO**. Tidak ada push / PR / merge / deploy. 01F tidak dimulai.

## Ringkasan status

| Item | Status |
|---|---|
| Runtime Safety | **PASS** — DB `hris_staging` @ `127.0.0.1`, `AUTO_SEED=false`, storage `s3-staging-local`, tidak ada fallback ke DB/R2 produksi |
| Audit Import Lama | **DONE** — 8 FINDING tercatat (bagian A). Endpoint lama dipertahankan tanpa perubahan |
| Migration m0006 | **DONE** — `backend/migrations/m0006_employee_import_migration.py` (additive saja) |
| employee:import Permission | **DONE / PASS** — grant hanya ke `tenant_admin`, `hr_admin` (`company_owner` sudah wildcard); `hr_manager` dikecualikan |
| Mapping 6 Sheet | **DONE** — terpusat di `backend/app/core/employee_import_mapping.py` (versi `01E-draft-1`, belum final sampai file sensus PT REAL diterima) |
| Template Foundation | **DONE / PASS** — `GET /api/employee-import/template` (6 sheet, dropdown, kolom sensitif diformat teks) |
| Upload | **DONE / PASS** — `POST /api/employee-import/batches` (.xlsx, maks 10 MB, maks 5.000 karyawan) |
| Analyze | **DONE / PASS** — tidak mengubah data bisnis (checksum 11 tabel bisnis identik) |
| Validate | **DONE / PASS** — header/sheet wajib, format, master, tanggal, NIK/rekening/NPWP/BPJS |
| Preview | **DONE / PASS** — `GET /batches/{id}` + `/rows` (filter kelas/status), nilai sensitif dimasking |
| NEW | **PASS** |
| UPDATE | **PASS** |
| UNCHANGED | **PASS** |
| CONFLICT | **PASS** |
| ERROR | **PASS** |
| Blank Preserve Rule | **PASS** |
| NIK Conflict | **PASS** |
| Commit per Employee | **PASS** (transaksi per karyawan, rollback terbukti, partial batch tercatat) |
| Status 01B Integration | **PASS** |
| Assignment 01D Integration | **PASS** |
| Family Matching | **PASS** |
| Sensitive Data Masking | **PASS** |
| Batch History | **PASS** (backend saja) |
| Duplicate File Hash Warning | **PASS** |
| Audit | **PASS** |
| Tenant Isolation | **PASS** |
| Core Backend Tests | **PASS** — `test_01e.py` **63/63** (run final) |
| Legacy Import Regression | **PASS** (template/validate/commit import lama tetap jalan) |
| 01B Regression | **FAIL (3 butir, penyebab = artefak uji, bukan regresi kode)** — `test_01b.py` 42/43, `test_01b_extra.py` 19/21 (lihat bagian D) |
| 01C Regression | **PASS** — `test_01c_on01d.py` 43/43, `test_01c_carry.py` 34/34, `test_01c_extra.py` exit 0 |
| 01D Regression | **PASS** — `test_01d.py` 48/48 |
| Migration Apply Once | **PASS** |
| Migration Rerun Skip | **PASS** |
| Restart backend 2x tanpa mutasi | **PASS** — fingerprint seluruh tabel r0 = r1 = r2 |
| UI Import & Migrasi | **BELUM DIKERJAKAN** |
| UI Riwayat Import | **BELUM DIKERJAKAN** |
| Download Hasil Validasi | **BELUM DIKERJAKAN** |
| Performance 500 Rows | **BELUM DIKERJAKAN** |
| Performance 1.000 Rows | **BELUM DIKERJAKAN** |
| Performance 5.000 Rows | **BELUM DIKERJAKAN** |
| Visual QA | **BELUM DIKERJAKAN** |
| testing_agent_v3 Final | **BELUM DIKERJAKAN** |
| Cleanup Final ZT01E | **BELUM DIKERJAKAN** — fixture ZT01E masih ada (15 karyawan, 6 project, 15 batch). Script `/root/tenant_tests/cleanup_01e.py` sudah disiapkan (default dry-run), belum dijalankan dengan `--apply` |
| Regresi payroll / absensi / rekrutmen / kontrak-dokumen-sertifikasi / Tenant Foundation | **BELUM DIKERJAKAN** untuk 01E (gate final sesi berikutnya) |
| Laporan final 01E | **BELUM DIKERJAKAN** |
| Production Changed | **NO** |

---

## Source control (lokal saja)
- Checkpoint 01C + 01D: commit **`1b63ba5`** sudah ada saat sesi dimulai. Commit ini dibuat **otomatis oleh platform** (bukan oleh agent),
  **gabungan 01C+01D**, dan ikut memuat `plan.md`, `test_reports/iteration_24/25.json`, serta laporan 01C/01D (pola yang sama dengan commit
  sebelumnya). Tidak ada `.env`, kredensial, atau token di commit itu (dicek dengan scan pola). History **tidak ditulis ulang**
  (rebase/amend dihindari untuk mencegah risiko).
- `a4c5fa4` — `Upgrade 01C - Employee Profile 360 (yarn.lock untuk dependency react-easy-crop)`: lockfile dependency 01C yang tertinggal.
- Branch lokal **`feature/upgrade-01e-employee-migration`** dibuat dari `a4c5fa4`.
- `d66bbe9` — checkpoint kode backend 01E (commit lokal, **BELUM FINAL**).
- Sengaja **tidak di-commit**: `.env.example`, `backend/.env.example` (perubahan lama yang diwarisi), `plan.md`, laporan ini, skrip uji di `/root/tenant_tests`.
- Tidak ada push / PR / merge / deploy.

---

## A. Audit Import Lama — DONE
Lokasi: `backend/app/routers/employees.py` (±baris 575–785), `backend/app/core/excel.py`, UI `frontend/src/pages/EmployeeImportPage.jsx`.

| Aspek | Perilaku saat ini | Status |
|---|---|---|
| Template | 1 sheet `Data Karyawan` (33 kolom, header baris 1, petunjuk baris 2, data mulai baris 3) + sheet `Referensi` | DONE |
| Endpoint | `GET /api/employees/import/template`, `GET /import/columns`, `POST /import/validate` (dry-run), `POST /import/commit` (klien mengirim ulang payload hasil validasi) | DONE |
| Validasi header | Cocok persis, atau toleran berdasarkan nama kolom; hanya `Nama Lengkap*` yang wajib | DONE |
| Validasi field | Nama, KTP 16 digit, email, tanggal, angka, PTKP, gender L/P, pernikahan, agama (warning), master nama/kode/id | DONE |
| Duplikat nomor karyawan / NIK | Duplikat di file atau di DB → baris ERROR | DONE |
| Create vs update | **Hanya create**; karyawan yang sudah ada tidak bisa di-update | FINDING |
| Transaksi | Per baris **tanpa** transaksi DB (karyawan, assignment, riwayat status, gaji ditulis terpisah) → bisa tersisa data parsial | FINDING |
| Lookup master saat commit | ID master dari payload klien **tidak divalidasi ulang** → ID dari luar tenant bisa lolos bila payload dimanipulasi | FINDING |
| Payload commit | `rows[].payload` = dict bebas → field lain (mis. `photo_path`, `user_id`, `candidate_id`) bisa ikut tersimpan (mass-assignment) | FINDING |
| Permission | Semua endpoint `employee:create`; kolom Gaji/PTKP membuat `employee_salaries` tanpa cek `employee_salary:create` | FINDING |
| Data sensitif | Pesan duplikat memuat **NIK KTP lengkap**; respons validate memuat KTP/rekening/NPWP/BPJS penuh | FINDING |
| Kode nilai | Gender `L/P` & pernikahan `belum_kawin/kawin/...` ≠ kode UI Profile (`male/female`, `single/married/divorced`) | FINDING |
| Audit | Hanya 1 entri ringkasan per commit; tidak ada audit per karyawan | FINDING |
| Tenant isolation | company dari token; query tenant-scoped | PASS (baca kode) |
| Batas / error / rerun | 500 baris, 5 MB; pesan per baris; rerun file sama → semua ERROR duplikat (tidak menggandakan) | DONE |
| Integrasi 01B/01D | Sudah memanggil helper status awal 01B dan assignment awal 01D | DONE |

Keputusan: **reuse** helper `_clean/_parse_date` (excel.py), pola lookup master, helper 01B (`history_doc`, `legacy_for`, `default_status`)
dan 01D (`new_assignment_doc`, `PLACEMENT_FIELDS`, aturan tanggal akhir pindah). Engine baru dibuat sebagai **layer terpisah**.
Endpoint lama **tetap dan tidak diubah**; FINDING di atas **tidak diperbaiki** (di luar scope, menunggu keputusan user).
Regresi import lama: **PASS**.

## B. Implementasi backend 01E (DONE)
File baru: `app/core/employee_import_mapping.py`, `app/core/employee_import.py`, `app/routers/employee_import.py`,
`migrations/m0006_employee_import_migration.py`. Perubahan additive: `app/core/db.py` (2 tabel), `app/core/rbac.py` (aksi `import`),
`server.py` (router).

Endpoint (semua `employee:import`, tenant-scoped):
`GET /api/employee-import/template` · `GET /mapping` · `POST /batches` (upload+analyze+validate) · `GET /batches` (riwayat) ·
`GET /batches/{id}` · `GET /batches/{id}/rows` (preview) · `POST /batches/{id}/commit` · `POST /batches/{id}/cancel`.

Keputusan desain penting:
- **File Excel mentah tidak disimpan** di DB maupun storage. Saat commit, file yang sama diunggah ulang; hash SHA-256 wajib sama,
  lalu dianalisis ulang terhadap kondisi DB terbaru. Baris yang klasifikasi/perubahannya berbeda dari preview → `FAILED` ("data berubah sejak analisis").
- Tabel impor hanya menyimpan metadata + perubahan versi **masking**; tidak ada nilai sensitif penuh.
- Status Karyawan & penempatan ditulis dalam **satu transaksi per karyawan** memakai helper & aturan 01B/01D yang sama
  (bukan memanggil endpoint 01B/01D, karena masing-masing membuka transaksi sendiri sehingga atomisitas per karyawan tidak terjamin).
- Perubahan project = Pindah Penempatan (assignment lama ENDED sehari sebelum mulai baru, riwayat tetap, `employees.project_id` sinkron).
  Tanggal mulai wajib bila karyawan sudah punya penempatan aktif; bila tidak ada → disimpan **NULL + warning** (tidak dikarang).
  Karyawan baru tanpa tanggal mulai: pakai Tanggal Masuk (aturan 01D) bila ada, selain itu NULL + warning.
- Perubahan Status Karyawan wajib Tanggal Efektif (tidak boleh masa depan); riwayat `source=IMPORT`; legacy `status` disinkronkan.
- NIK: milik karyawan lain / dipakai >1 karyawan di file / berbeda dengan NIK tersimpan → **CONFLICT** (tidak pernah merge otomatis).
- Nomor karyawan = business key; import tidak pernah mengubahnya. Nomor milik karyawan terhapus/diarsipkan → CONFLICT.
- Keluarga: cocok via NIK, lalu hubungan+nama(+tgl lahir). Ambigu / NIK beda / nama sama beda hubungan → **warning review**, tidak diubah.
- Re-upload file yang sudah pernah di-commit → warning; commit ulang ditolak kecuali `confirm_duplicate=true`.
- Gaji/PTKP **tidak** termasuk mapping draft 01E (butuh izin payroll; di luar scope).

## C. Hasil uji inti backend — `/root/tenant_tests/test_01e.py` → **63/63 PASS** (run final)
Nomor mengikuti daftar 51 gate user bila relevan. Fixture hanya `ZT01E`.

| # | Uji | Hasil |
|---|---|---|
| 1 / 2 / 2b | Template terunduh; 6 sheet; mapping terpusat bermetadata | PASS |
| 3 / 4 | Header invalid ditolak (422); sheet wajib hilang ditolak (422) | PASS |
| 5 / 5b | NEW terdeteksi; field tersimpan & dinormalisasi | PASS |
| 6 / 7 | UPDATE; UNCHANGED | PASS |
| 8 / 9 / 9b | Nomor duplikat di Excel = ERROR; NIK duplikat antar karyawan = CONFLICT; pesan NIK invalid tanpa nilai | PASS |
| 10 / 10b | Nomor existing + NIK milik karyawan lain = CONFLICT; karyawan tidak berubah | PASS |
| 11 / 12 | Sel kosong tidak menimpa; nilai terisi mengubah field | PASS |
| 13 / 14 / 14b / 15 | Status Kepegawaian terpisah; status 01B valid + riwayat IMPORT; ubah status via 01B (legacy sinkron); status tidak ada = ERROR | PASS |
| 16 / 17 / 17a / 18 / 19 / 19a | Assignment baru via 01D; riwayat pindah project; pindah tanpa tanggal = ERROR; `project_id` legacy sinkron; tanpa tanggal karangan (NULL + warning) | PASS |
| 20 / 21 / 22 / 22a | Rekening/NPWP; BPJS; tidak bocor ke audit/log/hasil analisis; preview termasking | PASS |
| 23 / 24 / 24a / 24b | Keluarga multi-baris; rerun tidak dobel; identitas ragu = warning; rerun tidak dianggap NEW | PASS |
| 25 / 25b | Keluarga orphan = ERROR; baris tanpa nomor = ERROR | PASS |
| 26–29 | Validasi master perusahaan / project / jabatan / lokasi kerja | PASS |
| 30 / 30b / 31 | Analyze & Preview tidak mengubah data bisnis (checksum identik) | PASS |
| 32 / 32b / 32c | Commit mengubah data; commit UPDATE; batch terproses tidak bisa di-commit ulang | PASS |
| 33 | Gagal di tengah transaksi (setelah insert karyawan+riwayat+assignment) → rollback total | PASS |
| 34 / 34b | Partial batch (1 sukses, 1 gagal) tercatat; karyawan gagal tidak berubah | PASS |
| 35 / 35a / 35b | Riwayat batch; hitungan klasifikasi; audit analyze/commit/create/update/status/assignment/keluarga | PASS |
| 36 / 37 / 37b | Isolasi batch, karyawan, dan master antar tenant (NEP ↔ KBS) | PASS |
| 38 / 38b | Tanpa `employee:import` = 403 (termasuk HR Manager yang punya create/edit); tidak diberikan ke hr_manager | PASS |
| 39 / 39c | Re-upload file ter-commit → warning + commit ulang butuh konfirmasi; file berbeda ditolak (hash) | PASS |
| 40 | Import lama tetap jalan | PASS |
| 49 / 50 | m0006 tercatat sekali; rerun = SKIP | PASS |

Riwayat jujur: run pertama **54/62** — 8 FAIL disebabkan desain file uji (NIK karyawan 01 sengaja dipakai juga oleh karyawan 02,
sehingga keduanya benar menjadi CONFLICT sesuai aturan). File uji diperbaiki (bukan kode) → **62/62**. Lalu ditemukan bug kode:
baris tanpa Nomor Karyawan menyebabkan error saat menyimpan hasil analisis → diperbaiki + uji `25b` ditambah → **63/63**.

## D. Regresi & keamanan migrasi
- m0006: dry-run → **APPLY** (2 tabel dibuat, 1 permission, 2 grant, ledger) → rerun **SKIP**. Fingerprint sebelum/sesudah: hanya
  `employee_import_batches`, `employee_import_rows` (baru), `permissions` +1, `role_permissions` +2, `schema_migrations` +1. Tidak ada data bisnis berubah.
- Restart backend 2x: fingerprint seluruh tabel r0 = r1 = r2 (**PASS**).
- `test_01c_on01d.py` 43/43, `test_01c_carry.py` 34/34, `test_01c_extra.py` exit 0, `test_01d.py` 48/48: **PASS**.
- `test_01b.py` **42/43 — FAIL #08**: uji mengasumsikan semua karyawan aktif NEP non-ZT01B berstatus AKTIF. Dicek via query: yang
  tidak AKTIF adalah fixture uji (`ZT01D Satu` dari suite 01D yang baru dijalankan, dan `ZT01E Dua` berstatus Standby dari uji 01E).
  Kegagalan yang sama tercatat pada regresi 01D (42/43, lalu 43/43 setelah cleanup). Akan hilang setelah cleanup final ZT01E.
- `test_01b_extra.py` **19/21 — FAIL A1, A2**: dijalankan pukul 17:09 UTC = 00:09 WIB (tanggal WIB sudah +1). Uji menghitung "besok"
  dengan tanggal UTC sehingga di server (WIB) nilainya = hari ini → diterima; A2 gagal berantai. Artefak waktu uji, bukan regresi.
  Perlu dijalankan ulang antara 00:00–17:00 UTC.
- Fixture yang dibuat suite regresi (ZT01B/ZT01C/ZT01D + tenant uji `ZT01B…`) dibersihkan dengan skrip cleanup masing-masing.
  Tabel bisnis kembali identik dengan fingerprint pra-regresi; sisa perbedaan hanya `audit_logs` (+25 event login) dan `users.last_login_at`.
- Compile Python OK, `git diff --check` bersih, ruff (F/E9) bersih pada file baru. Satu peringatan lama di `server.py` (sudah ada sebelum 01E).

## Remaining Issues
1. 01E **belum selesai**: UI, riwayat UI, download hasil validasi, visual QA, performance 500/1.000/5.000, testing_agent_v3, regresi
   payroll/absensi/rekrutmen/kontrak-dokumen-sertifikasi/Tenant Foundation, cleanup final ZT01E, laporan final.
2. Regresi 01B perlu dijalankan ulang setelah cleanup ZT01E dan pada jam 00:00–17:00 UTC.
3. FINDING import lama (bagian A) belum diperbaiki, menunggu keputusan user.
4. Mapping `01E-draft-1` belum final; perlu disesuaikan dengan file sensus PT REAL aktual.
5. Commit dijalankan sinkron (satu request). Untuk 5.000 karyawan waktunya belum diukur (bagian dari performance test berikutnya).
6. `employee:import` belum tampil di UI matriks peran (UI di luar scope sesi ini); grant diatur lewat m0006.
7. Commit checkpoint 01C+01D (`1b63ba5`) dibuat otomatis oleh platform dan ikut memuat laporan/test_reports (lihat Source control).
8. Nilai gender/pernikahan lama dari import lama (`L/P`, `kawin`) akan terdeteksi sebagai UPDATE bila karyawan itu diimpor ulang
   lewat 01E (dinormalisasi ke kode UI). Perlu diketahui saat migrasi.

Production Changed: **NO**
