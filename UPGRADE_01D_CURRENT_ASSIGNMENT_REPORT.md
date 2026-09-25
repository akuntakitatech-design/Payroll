# UPGRADE 01D — CURRENT ASSIGNMENT / PENEMPATAN KARYAWAN

Environment: **STAGING ONLY** (MariaDB `hris_staging` @ localhost, local S3 staging, `AUTO_SEED=false`).
Branch lokal: `feature/upgrade-01c-employee-profile-360` (dari commit lokal 01B `2198b7e`). Belum ada commit, push, PR, merge, atau deploy untuk 01C/01D.
`.env.example` dan `backend/.env.example` tetap sebagai perubahan working tree lama. Tidak disentuh dan tidak termasuk 01C/01D.

## Ringkasan Hasil

| Item | Hasil |
|---|---|
| 01C Carry-over | **PASS** (NIK sensitif, payroll berbasis permission, editor crop foto; detail di laporan 01C bagian 21) |
| 01C Locked | **YES** |
| Migration | **PASS** (m0005 diterapkan sekali, dijalankan ulang → SKIP, ledger 1 baris) |
| Current Assignment | **PASS** |
| Assignment History | **PASS** |
| Transfer | **PASS** |
| End Assignment | **PASS** |
| Legacy Compatibility | **PASS** (`employees.project_id` tetap, disinkronkan; berakhir tanpa pengganti → NULL; modul lama aman saat NULL) |
| 01B Integration | **PASS** (opsi Standby lewat flow 01B; tanpa Standby otomatis) |
| Profile 360 Integration | **PASS** |
| Tenant Isolation | **PASS** |
| Regression | **PASS** (dengan catatan urutan fixture dan penyesuaian suite 01C, lihat Findings 1–3) |
| Restart Safety | **PASS** (fingerprint 63 tabel r0 = r1 = r2) |
| Visual QA | **PASS** (desktop 1920, tablet 820, mobile 390) |
| Technical Checks | **PASS** |
| Testing Agent | **PASS** (iteration_25: backend 27/27, frontend 100%). Catatan: agent sempat mengubah data baseline, sudah dipulihkan (Findings 4) |
| Production Changed | **NO** |

---

## 1. 01C Carry-over — PASS, 01C LOCKED
- **NIK KTP** masuk daftar data sensitif. `employee:edit` melihat nilai penuh; `employee:view` melihat nilai yang dimasking di API (list + detail). View-only tidak bisa mencari berdasarkan NIK. Aturan NIK unik tidak berubah. Audit tidak menyimpan NIK penuh; masking audit kini rekursif.
- **Payroll:** rekening/NPWP penuh hanya keluar lewat permission existing (`employee_salary:view`, `payroll:view/export`), tanpa hardcode nama role. `employee:view`-only mendapat 403 di API payroll; akses lintas tenant mendapat 404. Audit payroll tanpa nilai penuh.
- **Foto profil:** alur Pilih Foto → Atur Posisi → Zoom/Crop → Preview lingkaran → Simpan Foto. Rasio 1:1, orientasi EXIF benar, dan foto lama tetap dipakai bila upload baru gagal.
- **Foto baseline Bambang Setiawan (NEP-0002)** dihapus sesuai keputusan Anda, setelah audit memastikan sebelumnya memang tidak ada foto.
- Bukti: `test_01c_carry.py` 34/34, uji UI crop (portrait/landscape/EXIF/gagal-upload/mobile/format & ukuran ditolak), payroll 186/186, smoke 45/45, compile/build/diff-check/secret scan PASS. Laporan 01C diperbarui dengan **01C LOCKED: YES**.

## 2. Model & Migration — PASS
Tabel tenant-scoped `employee_assignments`: `id` (UUID), `company_id`, `employee_id`, `project_id`, `work_location_id`, `branch_id`, `department_id`, `division_id`, `position_id`, `cost_center_id`, `start_date`, `end_date`, `assignment_status` (`ACTIVE` | `ENDED`), `source` (`LEGACY_BASELINE` | `MANUAL` | `TRANSFER` | `EMPLOYEE_CREATE` | `IMPORT` | `RECRUITMENT`), `reason`, `notes`, `end_reason`, `end_notes`, `ended_by`, `previous_assignment_id`, `created_by/at`, `updated_by/at`. Index `(company_id, employee_id, assignment_status)`. Semua referensi memakai master existing (tidak ada master baru).

`backend/migrations/m0005_employee_assignment.py` bersifat additive (tanpa DROP/RENAME) dan memakai ledger `schema_migrations`:
- DRY-RUN → APPLY (15:58 UTC): **3 assignment `LEGACY_BASELINE`** (NEP-0002, NEP-0004, KBS-0003). Hanya karyawan yang punya `project_id`. `start_date = NULL` (tanggal lama tidak dikarang). Field organisasi disalin dari data karyawan.
- Rerun → `SKIP`; tanpa duplikat (diuji ulang di suite: tetap 3 baris).
- Catatan: tabel fisik sudah dibuat oleh schema-ensure saat backend start (pola yang sama dengan tabel lain). Migrasi melakukan backfill dan mencatat ledger.

## 3. Alur & Aturan — PASS
API (RBAC existing: lihat `employee:view`, ubah `employee:edit`; tanpa permission baru):
- `GET /api/employees/{id}/assignments` → `{current, items}` (+ nama master).
- `POST /api/employees/{id}/assignments` — **Tetapkan Penempatan**. Hanya bila belum ada ACTIVE (selain itu 409).
- `POST /api/employees/{id}/assignments/transfer` — **Pindah Penempatan**. Dalam **satu transaksi DB** (row-lock karyawan): assignment lama → `ENDED` dengan `end_date` = sehari sebelum mulai baru (atau sama dengan tanggal mulai baru bila itu jatuh sebelum mulai lama), assignment baru `ACTIVE` dengan `previous_assignment_id`, sinkron legacy, dan audit. Gagal di tengah jalan = rollback semua.
- `POST /api/employees/{id}/assignments/end` — **Akhiri Penempatan**. Setelahnya tidak ada ACTIVE, `employees.project_id = NULL`, riwayat tetap. Tidak ada assignment pengganti otomatis.

Aturan tambahan:
- Tanggal efektif hanya hari ini atau tanggal lampau (penempatan terjadwal tidak didukung). Tidak boleh sebelum mulai penempatan saat ini.
- Maksimal satu ACTIVE per karyawan, dijaga dengan row-lock dan pengecekan ulang di dalam transaksi (409 bila berubah bersamaan).
- Validasi master: semua ID wajib milik tenant aktif. Site harus cocok dengan lokasi tetap project (bila project punya lokasi). Divisi harus bagian dari departemen terpilih (bila keduanya diisi).
- Field organisasi yang tidak dikirim mewarisi data karyawan saat ini. Field yang dikirim `null` = dikosongkan. Dialog UI mengisi nilai awal dari data karyawan.
- Karyawan diarsipkan: aksi penempatan ditolak (409).
- **Edit Karyawan tidak bisa mengubah project** (422, field project dinonaktifkan dengan petunjuk). Koreksi departemen/divisi/jabatan/lokasi lewat Edit dicerminkan ke assignment ACTIVE (koreksi data, bukan perpindahan).
- Karyawan baru dengan project (form Tambah, Impor Excel, konversi rekrutmen) → assignment ACTIVE pertama (`EMPLOYEE_CREATE` / `IMPORT` / `RECRUITMENT`). Tanggal mulai = tanggal masuk; bila kosong atau di masa depan, dipakai tanggal pencatatan (hari ini).

## 4. Legacy Compatibility — PASS
- `employees.project_id` tidak dihapus dan selalu mengikuti assignment ACTIVE. Assign/transfer juga menyinkronkan field organisasi yang dipilih.
- Berakhir tanpa pengganti → `project_id = NULL`. Lokasi kerja/departemen/jabatan dibiarkan agar modul lama (mis. geofence absensi) tetap jalan. Riwayat tetap tersimpan.
- Modul yang membaca `employees.project_id` diuji saat nilainya NULL: daftar & statistik karyawan, `policies/effective`, absensi (list/recap/dashboard/exceptions), payroll salaries, dashboard. Semua 200, tanpa 5xx.
- Pengecekan global: tidak ada karyawan dengan >1 ACTIVE, dan `project_id` setiap karyawan = project assignment ACTIVE-nya (atau NULL).

## 5. 01B Integration — PASS
- Standby tetap Status Karyawan 01B, bukan jenis penempatan. Mengakhiri penempatan **tidak** mengubah status secara otomatis (diuji: status + riwayat status tidak berubah).
- Opsi "Status Karyawan setelah penempatan berakhir" (default: *Tetap: status saat ini*) memanggil `change_employee_status` 01B, sehingga riwayat status dan audit `status_change` tercatat. Opsi ini butuh `employee_status:change`; `hr.manager` tanpa izin itu mendapat 403 dan assignment tetap aktif.
- Validasi status tujuan dilakukan sebelum assignment ditutup. Perubahan status berjalan di transaksi 01B tersendiri setelah assignment ditutup. Bila tetap gagal, penempatan sudah berakhir dan respons berisi `status_change_error` (UI menampilkan peringatan agar HR mengulang lewat "Ubah Status").

## 6. Profile 360 Integration — PASS
- Tab **Penempatan Saat Ini** membaca assignment ACTIVE: Project, Site/Lokasi, Perusahaan, Cabang, Departemen, Divisi, Jabatan, Cost Center, **Mulai Penempatan** ("Tidak diketahui (data lama)" untuk baseline), dan Sumber. Ada empty state saat belum/tidak ada penempatan aktif.
- **Riwayat Penempatan**: Project, Site, Jabatan, Mulai, Berakhir, Alasan, Status (tabel di desktop/tablet, kartu di mobile).
- Tombol **Tetapkan / Pindah / Akhiri Penempatan** hanya untuk `employee:edit` dan karyawan yang tidak diarsipkan. View-only hanya melihat.
- Kartu Ringkasan menampilkan tanggal mulai penempatan. Timeline Riwayat memberi label aksi penempatan.
- Daftar karyawan: kolom/filter project sudah memakai project saat ini (hasil sinkron legacy). Tidak ada redesign.
- Perbaikan UX: sebelumnya halaman kembali ke tab Ringkasan setelah menyimpan. Sekarang tab aktif tetap dan data dimuat ulang tanpa skeleton penuh.

## 7. Tenant Isolation & Audit — PASS
- Tenant lain tidak bisa membaca/menetapkan/memindahkan/mengakhiri assignment (404). Project tenant lain ditolak (422). Tenant diambil dari konteks auth, bukan dari klien.
- Audit per aksi (`assignment_create`, `assignment_transfer`, `assignment_end`) berisi penempatan lama/baru, tanggal efektif, alasan, aktor, dan waktu. Riwayat assignment tidak pernah ditimpa. Masking data sensitif 01C tetap berlaku.

## 8. Hasil Uji `test_01d.py` — 48/48 PASS
| # | Gate | Hasil |
|---|---|---|
| 1 | current assignment created | PASS |
| 2 | only one ACTIVE (+ tanggal masa depan ditolak, cek global) | PASS |
| 3 | history retained | PASS |
| 4 | transfer creates new assignment | PASS |
| 5 | previous assignment ended (end_date = H-1) | PASS |
| 6 | legacy `employees.project_id` synchronized (A → B → NULL) | PASS |
| 7 | initial legacy project backfill (3 LEGACY_BASELINE) | PASS |
| 8 | no invented legacy dates (start_date NULL) | PASS |
| 9 | end assignment works (+ tanggal sebelum mulai ditolak, akhiri ganda 409) | PASS |
| 10 | optional STANDBY via 01B flow (+ tanpa izin → 403) | PASS |
| 11 | status history intact | PASS |
| 12 | cross-tenant employee denied (baca/tetapkan/pindah/akhiri) | PASS |
| 13 | cross-tenant project denied | PASS |
| 14 | invalid project/site combination rejected (+ sama/mundur/masa depan/view-only) | PASS |
| 15 | Profile 360 current placement correct (sebelum & sesudah akhir) | PASS |
| 16 | Profile 360 history correct (3 baris setelah tetapkan ulang) | PASS |
| 17 | employee list current project correct (+ filter per project) | PASS |
| 20 | import regression (template tidak berubah; project → assignment IMPORT) | PASS |
| 25 | migration applied once | PASS |
| 26 | migration rerun skipped | PASS |
| — | Edit tidak bisa ubah project; mirror koreksi departemen; karyawan baru ber-project; arsip ditolak; NULL-safety modul lama; audit | PASS |

## 9. Regression (gate 18–24) — PASS
| Suite | Hasil |
|---|---|
| Payroll core `test_core.py` | 186/186 |
| `smoke_mariadb.py` (kontrak/dokumen/master/payroll) | 45/45 |
| Absensi `smoke_time.py` | 45/45 |
| ESS `smoke_ess.py` | run pertama 110/1 (urutan fixture), rerun **111/0** |
| Rekrutmen `recr_c_unique.py` (termasuk konversi → karyawan) | 43/43 |
| Tenant isolation pytest / tenant foundation | 1 passed / 7/7 |
| 01B suite / 01B extra | run pertama 42/43 (fixture ZT01D Standby masih ada), rerun setelah cleanup **43/43** / 21/21 |
| 01C suite (varian pasca-01D) / 01C extra / 01C carry-over | **43/43** / PASS / 34/34 |
| Kontrak & dokumen | tercakup di 01C suite (tab Dokumen/Kontrak/Sertifikasi) + smoke_mariadb |

## 10. Restart Safety — PASS
Backend di-restart 2x lewat supervisor, `/api/system/mode` 200. Fingerprint (CHECKSUM + COUNT) 63 tabel identik r0 = r1 = r2. Tidak ada migrasi/backfill otomatis saat startup.

## 11. Visual QA — PASS
- Desktop 1920: empty state → Tetapkan (dialog, nilai awal dari data karyawan) → tampil Project/Site/Mulai → Pindah (tanggal 2099 ditolak di form) → riwayat 2 baris (lama "Berakhir 31 Jul 2025") → Akhiri (opsi status: *Tetap: Aktif* / Standby / Tidak Aktif) → empty state + riwayat. Tab tetap di Penempatan setelah setiap aksi.
- Mobile 390: Tetapkan → Akhiri dengan **Standby** → badge header "Standby", riwayat dalam bentuk kartu, `scrollWidth` 390 (tanpa scroll horizontal).
- Tablet 820: tabel riwayat tampil, `scrollWidth` 820.
- Baseline (read-only): NEP-0002 menampilkan assignment `LEGACY_BASELINE`, "Tidak diketahui (data lama)".
- Console: hanya warning chart Dashboard `width(-1)/height(-1)` (existing, bukan Profile 360).

## 12. Technical Checks — PASS
- Backend compile (`compileall app migrations`): PASS.
- Frontend: esbuild bundle PASS; `yarn build` → "Compiled successfully." (exit 0).
- `git diff --check`: PASS.
- Secret scan (23 file berubah/untracked, pola token/kunci + nilai `.env` nyata): PASS. Satu-satunya kandidat adalah label placeholder storage lokal staging (`s3-<R2_ACCOUNT_ID staging>`) di `server.py` (sudah ada sebelum 01C) dan di laporan 01C. Itu bukan kredensial.

## 13. Testing Agent — PASS
`/app/test_reports/iteration_25.json`: backend 27/27, frontend 100%, tanpa bug. Ada dua pelanggaran aturan oleh agent, keduanya sudah ditangani (Findings 4 & 5). File uji agent dipindah dari root repo ke `/root/tenant_tests/backend_test_01cd_agent.py`.

## 14. Cleanup ZT01D — PASS
`/root/tenant_tests/cleanup_01d.py` (default DRY-RUN; pengaman: berhenti bila ada assignment non-ZT01D memakai project ZT01D) menghapus hanya:
- karyawan `ZT01D%` beserta baris turunannya (assignment, riwayat status, saldo/ledger cuti otomatis),
- project uji `ZT01D-*` (NEP + KBS),
- audit berlabel/merujuk data uji,
- counter nomor karyawan NEP dikembalikan ke 17.

Artefak regression (ZT01C, SMOKE-C, tenant uji ZT*, efek samping smoke) dibersihkan dengan skrip 01C/foundation yang sama seperti sebelumnya. Tabel `time_periods`, `leave_balances`, `work_locations` dipulihkan dari dump pra-uji 01D dengan checksum cocok.

Dry-run akhir: 0 kandidat. Fingerprint akhir vs pra-uji 01D: hanya `employee_assignments` (+3 baseline dari migrasi), `schema_migrations` (+1), `audit_logs` (log login/aksi uji dipertahankan), dan `users.last_login`. `employees` / `employee_assignments` identik dengan fingerprint restart.

## 15. Files Changed (01D)
- Baru: `backend/app/core/assignment.py`, `backend/app/routers/employee_assignment.py`, `backend/migrations/m0005_employee_assignment.py`, `frontend/src/components/employees/AssignmentSection.jsx`.
- Ubah: `backend/app/core/db.py` (spec + index tabel), `backend/server.py` (router), `backend/app/routers/employees.py` (guard project di Edit, mirror, assignment awal saat create/impor, `current_assignment` di detail), `backend/app/routers/recruitment_conversion.py` (assignment awal), `frontend/src/components/employees/ProfileSections.jsx` (PlacementTab lama diganti; field project dinonaktifkan; ringkasan; label timeline), `frontend/src/pages/EmployeeDetailPage.jsx` (AssignmentTab; tab terkontrol), `frontend/src/pages/EmployeesPage.jsx` (project dinonaktifkan saat edit), `plan.md`.
- Template import Excel (`core/excel.py`, `EmployeeImportPage.jsx`) tidak berubah.
- 01C carry-over: lihat laporan 01C bagian 16/21.

## 16. Findings
1. **ESS 110/1 pada run pertama**: penyebabnya urutan `time_fixture --ensure-schedule` (sama seperti di 01B/01C), bukan bug. Rerun 111/0.
2. **01B test 08 gagal di run pertama**: fixture `ZT01D Satu` (sudah diubah ke Standby oleh test_01d) masih ada saat regression berjalan, sedangkan test 08 mengharuskan semua karyawan aktif non-ZT01B berstatus AKTIF. Setelah cleanup ZT01D, rerun 43/43.
3. **Suite 01C asli: 36/43 setelah 01D.** Tujuh kegagalan adalah perubahan perilaku yang disengaja oleh 01D, bukan regresi:
   - 13/14/15/27/30: suite lama mengubah project lewat Edit, yang kini ditolak;
   - 16: suite lama memastikan tabel assignment tidak ada;
   - 31: blok impor kini membuat assignment awal, tetapi template tidak berubah.

   Saya membuat varian `test_01c_on01d.py`: project dipindah lewat Pindah Penempatan, tabel roster/mobilisasi/standby tetap dilarang, dan baris assignment dikecualikan dari perbandingan blok impor. Hasilnya **43/43**. Mohon konfirmasi penyesuaian ini.
4. **Testing agent mengubah data baseline** meski sudah dilarang: memindahkan **Bambang Setiawan (NEP-0002)** pukul 16:18 UTC. Sudah dipulihkan (`restore_bambang_01d.py`, satu transaksi): assignment TRANSFER buatan agent dihapus, `LEGACY_BASELINE` diaktifkan kembali, baris karyawan dipulihkan dari dump pra-uji, dan audit transfer uji dihapus. Checksum `employees` dan `employee_assignments` kini identik dengan fingerprint sebelum agent. Tidak ada foto/storage baseline yang berubah.
5. Laporan agent sempat memuat satu NIK baseline penuh. Nilainya sudah dimasking di `iteration_25.json`.
6. Bug UX existing diperbaiki: setelah simpan (juga untuk edit bagian profil), halaman kembali ke tab Ringkasan.

## 17. Remaining Issues / Keputusan untuk Anda
1. Mengarsipkan karyawan **tidak** mengakhiri assignment aktif secara otomatis (di luar scope). Assignment tetap tercatat; aksi penempatan diblok selama diarsipkan.
2. Batas "satu ACTIVE per karyawan" dijaga aplikasi (row-lock + cek ulang di transaksi), bukan unique constraint DB, karena MariaDB tidak punya partial unique index tanpa kolom tambahan.
3. Ubah status opsional saat mengakhiri penempatan berjalan di transaksi 01B terpisah (sudah divalidasi sebelumnya; bila gagal ada peringatan jelas). Menyatukan keduanya perlu refactor service 01B, yang tidak saya lakukan.
4. Karyawan baru ber-project tanpa tanggal masuk (atau tanggal masuk di masa depan) memakai tanggal pencatatan sebagai mulai penempatan. Backfill data lama tetap NULL.
5. Mengakhiri penempatan hanya mengosongkan `project_id`; lokasi kerja/departemen/jabatan dibiarkan (demi absensi/geofence). Header profil tetap menampilkan site terakhir.
6. Field organisasi yang tidak dikirim ke API assign/transfer mewarisi data karyawan (dokumentasi di bagian 3).
7. Log audit otomatis (login/aksi uji) dan `users.last_login` dipertahankan, sama seperti 01B/01C.

## Production Changed: **NO**
Tidak ada akses, penulisan, atau deploy ke production (DB maupun R2). Tidak ada commit, push, PR, atau merge. Tidak ada pekerjaan 01E.

**STOP — menunggu review Anda.**
