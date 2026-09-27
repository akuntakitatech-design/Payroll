# UPGRADE 01F — Data Completeness — Final Report

- Environment: **STAGING only** (DB `hris_staging` @ 127.0.0.1:3306, local S3 storage `hris-staging-media`)
- Branch: `feature/upgrade-01f-data-completeness`
- Tanggal laporan: 2026-09-26
- **Production Changed: NO**
- Push / PR / merge / deploy: **TIDAK ADA**
- Status verifikasi: seluruh hasil di bawah **diuji oleh agent** (script, testing_agent_v3, screenshot automation). Belum ada acceptance/LOCK dari user.

---

## 1. Scope

**Tujuan.** Kelengkapan Data karyawan yang tenant-aware, additive, dan **non-blocking**: HR melihat skor/status kelengkapan per karyawan (Profile 360) dan per tenant (Monitoring), serta dapat mengatur requirement per tenant (Master Kelengkapan). Fitur ini tidak memblokir transaksi HR apa pun.

**Level requirement**
- **Wajib** — masuk hitungan skor.
- **Anjuran** — ditampilkan sebagai saran, **tidak mengurangi skor**.
- **Nonaktif** — tidak dievaluasi.
- Requirement yang tidak berlaku (N/A) untuk karyawan tertentu dikeluarkan dari penyebut.

**Formula**
- `skor = wajib terpenuhi / wajib yang berlaku × 100`
- `100% = LENGKAP`, `< 100% = BELUM_LENGKAP`; karyawan di luar cakupan evaluasi = `EXCLUDED`.

**Applicability / scope.** Rule dapat diatur per tenant (default katalog bukan kebijakan permanen). Scope INCLUDE (berlaku untuk) / EXCLUDE (dikecualikan dari) mendukung: perusahaan, status kepegawaian, status bisnis 01B spesifik maupun kategori (ACTIVE/STANDBY/INACTIVE), grade/level, jabatan, project, lokasi kerja, departemen, divisi, dengan tanggal efektif opsional. Requirement sertifikasi tidak menandai staf "belum lengkap" secara luas bila scope tidak jelas.

**PTKP.** `TK/0` tetap **Anjuran**, belum ada mekanisme konfirmasi, tidak mempengaruhi skor maupun default payroll (lihat Known Limitations).

---

## 2. Backend

| Komponen | Lokasi | Ringkasan |
|---|---|---|
| Katalog requirement | `app/core/completeness_mapping.py` | 35 requirement dalam 9 kategori; mapping terpusat ke field/tab Profile 360 |
| Validator field | `app/core/field_validators.py` | Validasi format (NIK, NPWP, dll.) dipakai evaluator |
| Evaluator + engine | `app/core/completeness.py` | Evaluasi per karyawan, refresh per chunk 500, stale marking, coalesced tenant refresh, daily job |
| Snapshot | tabel `employee_completeness` | Satu snapshot per `(company_id, employee_id)` (unique index `ux_employee_completeness_emp`), UPSERT idempotent dengan guard `evaluated_at`; hanya menyimpan kode/status/skor/missing codes/metadata — **tanpa nilai sensitif** |
| Migration | `migrations/m0007_data_completeness.py` | Membuat `completeness_rules`, `completeness_rule_scopes`, `employee_completeness`; permission `employee_completeness:configure` (grant `tenant_admin`, `hr_admin`; `company_owner` wildcard). Tanpa DROP/ALTER tabel lama, tanpa backfill |
| RBAC | `app/core/rbac.py` | View = `employee:view`; reevaluate per karyawan = `employee:edit`; konfigurasi rule/scope + reevaluate semua = `employee_completeness:configure` |
| Router | `app/routers/completeness.py` | lihat daftar API |
| Scheduler | `app/core/scheduler.py` (existing) | Job `employee_completeness_daily` → `daily_reevaluation()`; tidak ada scheduler/queue baru |

**API**
- `GET /api/completeness/catalog`
- `GET /api/completeness/summary`
- `GET /api/completeness/employees` (server-side pagination + filter status/skor/project/departemen/divisi/status 01B/pencarian/missing requirement/pending)
- `GET /api/employees/{id}/completeness`
- `POST /api/employees/{id}/completeness/reevaluate`
- `PUT /api/completeness/rules/{code}`, `DELETE /api/completeness/rules/{code}` (reset ke default)
- `POST /api/completeness/scopes`, `DELETE /api/completeness/scopes/{id}`
- `POST /api/completeness/reevaluate` (seluruh tenant)

**Trigger non-blocking.** Transaksi HR utama commit terlebih dahulu; refresh kelengkapan dijalankan setelahnya via `safe_refresh` (tidak pernah melempar error ke pemanggil; bila gagal → snapshot ditandai stale). Perubahan rule/scope tidak menghitung ribuan karyawan secara sinkron — evaluasi ulang tenant dijadwalkan di latar belakang (coalesced).

**Integrasi**
- **01B** status karyawan (perubahan status bisnis) · **01C** Profile 360 (profil, keluarga, foto, dokumen, kontrak, sertifikasi) · **01D** assignment aktif · **01E** import: ID terdampak dikumpulkan setelah commit lalu bulk refresh (tanpa kalkulasi per baris, import tidak di-rollback bila refresh gagal) · **Payroll** trigger sempit hanya bila field sumber berubah (`ptkp_status`, `has_npwp`, enrolment BPJS, `ptkp_confirmed_at`) · **Recruitment** konversi kandidat → karyawan.

**Scheduler di staging.** `ENABLE_SCHEDULER=false` di staging disengaja. Scheduler divalidasi lewat registrasi job, pemanggilan langsung, coalescing, dan idempotency rerun — bukan run otomatis.

---

## 3. UI

- **Profile 360 — kartu Kelengkapan** (`components/employees/CompletenessCard.jsx`): skor/status, wajib terpenuhi/total, daftar kekurangan, pembeda Wajib vs Anjuran, status stale/pending, waktu evaluasi terakhir, evaluasi ulang individual, tautan ke tab Profile 360 terkait.
- **Monitoring** (`pages/EmployeeCompletenessPage.jsx`): kartu ringkasan, list server-side + paginasi, filter/pencarian/missing requirement, banner stale/pending, aksi Evaluasi Ulang Semua.
- **Detail drawer**: rincian requirement per karyawan tanpa nilai sensitif.
- **Master Kelengkapan**: level per requirement, manajemen scope (termasuk status 01B spesifik), wording "berlaku untuk / dikecualikan dari", visibilitas pending; mode read-only untuk role tanpa izin konfigurasi.
- **Responsif**: desktop, tablet 820px, mobile 390px (tanpa overflow halaman, list mobile, drawer full-width).
- Build: `esbuild` PASS, `yarn build` EXIT 0.

---

## 4. Perbaikan Deadlock Rule/Scope

**Gejala.** `DELETE /api/completeness/scopes/{id}` (dan pola yang sama pada tambah scope, ubah rule, reset rule, serta reevaluate semua) dapat mengembalikan HTTP 500 (MariaDB 1213) padahal scope/rule + audit sudah tersimpan.

**Root cause.** UPDATE stale se-tenant dalam satu transaksi besar (mengunci ribuan baris dalam urutan scan acak) bertabrakan dengan UPSERT snapshot per chunk dari refresh latar belakang; ditambah dua evaluasi penuh untuk tenant yang sama dapat berjalan bersamaan. Mutasi konfigurasi dan side-effect tidak terpisah dengan jelas.

**Perbaikan** (`app/core/completeness.py`, `app/routers/completeness.py`, `app/core/db.py` +`_TxWriter.delete`; ter-commit lokal di `03a29ba`). Diverifikasi langsung di kode (langkah verifikasi 4) — seluruh poin **CONFIRMED**:

1. **Transaksi utama terpisah dari side-effect.** Mutasi rule/scope + audit dalam **satu** `transaction()`; cek duplikat/eksistensi via `SELECT … FOR UPDATE` di dalam transaksi. Gagal → seluruh transaksi di-rollback (tidak ada data/audit setengah tersimpan).
2. **Retry maksimal 5 kali** (`LOCK_RETRY_ATTEMPTS = 5`, loop `for i in range(attempts)`), hanya untuk error 1213 (deadlock) / 1205 (lock wait timeout); error lain tidak di-retry. Backoff `0.05 × 2^i × (1 + jitter)` detik di antara percobaan (4 jeda, total ±0,75–1,5 detik). Tidak ada retry bersarang maupun retry tak terbatas.
3. **Gagal permanen pada transaksi utama → HTTP 503** dengan pesan tetap: "Perubahan belum tersimpan karena server sedang memproses data kelengkapan. Silakan coba lagi." Tidak ada detail MariaDB/stack trace di response; log hanya mencatat nama tipe error. Tidak pernah disamarkan sebagai sukses.
4. **Side-effect non-blocking.** Setelah commit, `after_config_change` menandai stale (dengan retry) dan tidak pernah melempar error; endpoint tetap 200/201. `schedule_tenant_refresh` **selalu** dijadwalkan.
5. **Stale marking per chunk 500** berurutan `employee_id` (urutan kunci sama dengan UPSERT snapshot yang juga diurutkan `employee_id`).
6. **Satu evaluasi penuh per tenant pada satu waktu** (lock per tenant; daftar karyawan + rules dibaca setelah lock → selalu konfigurasi terbaru). Permintaan beruntun digabung (coalesced), bukan N evaluasi paralel.
7. **Eventual reevaluation.** Walau stale marking gagal, refresh tenant tetap dijadwalkan; snapshot dengan `rules_hash` berbeda tetap terbaca "menunggu evaluasi"; job harian ikut menutup celah.

Catatan (di luar scope perbaikan deadlock, bukan mismatch): error DB non-konflik-kunci tetap menjadi 500 standar Starlette ("Internal Server Error", tanpa stack trace).

---

## 5. Hasil Test

Setiap baris adalah run terpisah; angka tidak digabung.

| Suite | Hasil | Catatan |
|---|---|---|
| Full 01F `test_01f.py` | **79/79 PASS** (RUN=031749, setelah fix deadlock) | Run pertama pasca-fix 72/79 = FIXTURE ISSUE (NIK uji "123" bentrok dengan sisa fixture → 409), test diperbaiki minimal (NIK unik per RUN). Sebelum fix: 79/79 (RUN=012500, RUN=021853) |
| Concurrency `test_01f_concurrency.py` | **34/34 PASS, dua kali berturut-turut** | Operasi bersamaan nyata + injeksi deadlock + isolasi tenant; 0 HTTP 5xx, 0 traceback deadlock |
| 01B | **43/43 PASS** | |
| 01C | **43/43 PASS** | |
| Tenant regression | **134/134 PASS + 1 SKIP** | SKIP: audit branding platform (mutasi branding sengaja tidak dijalankan pada varian regresi) |
| 01D | **48/48 PASS** | |
| 01E backend | **63/63 PASS** | |
| 01E UI | **31/31 PASS** | |
| Recruitment conversion | **43/43 PASS** | |
| Tenant isolation (pytest) | **PASS** (1 passed, 2 warnings) | |

**testing_agent_v3 — dua run terpisah**

| Report | Backend | Frontend | Catatan |
|---|---|---|---|
| `iteration_26.json` (testing agent sebelumnya) | **15/15** | **10/10** | API completeness, RBAC, isolasi tenant, tanpa nilai sensitif; UI KPI, tabel, pencarian, drawer, Master, Profile 360, Anjuran, mobile 390px, tablet 820px. `backend_test.py` yang diubah agent sudah dikembalikan ke HEAD |
| `iteration_27.json` (validasi lanjutan setelah perbaikan deadlock/concurrency) | **34/34** | **N/A (backend-only testing)** | C00, R01–R18, I01–I10 (termasuk I07: deadlock permanen → 503, retry 5x; I08: tanpa scope/audit tersimpan; I09: pesan aman), T01–T03, L01–L02 |

`iteration_27` adalah validasi lanjutan, **bukan pengganti otomatis** seluruh hasil `iteration_26`. Pada kedua file, SKIP, manual verification, dan durasi keseluruhan **tidak tercantum** (iteration_27 hanya mencantumkan durasi di item R09 7,7 dtk dan R11 2,8 dtk). Critical bugs/UI bugs pada kedua file: kosong.

**HTTP 422 — EXPECTED VALIDATION (bukan product failure)**
- `GET /api/leave/ledger` tanpa `employee_id` → 422 `employee_id: Field required`; dengan `employee_id` → 200.
- `GET /api/schedules` tanpa periode/rentang tanggal → 422 "Tentukan Periode atau rentang Tanggal Mulai dan Tanggal Selesai."; dengan `period` atau `date_from`+`date_to` → 200.

---

## 6. Performance (angka tercatat, tidak diubah)

**Benchmark utama** (`perf_01f.py`, fixture ZT01F, tenant NEP; hasil di `perf_01f_results.jsonl`). ms per skala karyawan tenant:

| Metrik | 530 | 1.030 | 6.030 | 10.030 |
|---|---:|---:|---:|---:|
| Seed fixture | 0,2 s | 0,2 s | 1,4 s | 1,0 s |
| Bulk evaluator (engine) | 406 | 746 | 4.131 | 7.358 |
| Bulk reevaluate API | 400 | 847 | 4.607 | 7.743 |
| Evaluasi harian | 438 | 765 | 4.341 | 7.381 |
| Monitoring summary | 19 | 25 | 77 | 141 |
| List halaman pertama (20 baris, payload 7,9 KB) | 21 | 25 | 57 | 80 |
| Filter/pencarian (project/dept/divisi/01B/status/skor/search/missing/kombinasi) | 17–23 | 22–25 | 45–61 | 58–115 |
| Backend RSS | 24 MB | 211 MB | 211 MB | 211 MB |

Pada ±10k: filter skor 104 ms (total 7.682), cari nomor 59 ms, cari nama 58 ms, missing requirement 115 ms (total 6.538), kombinasi 95 ms (total 661) — semua HTTP 200, 20 baris per halaman (bukan full set). Selama bulk reevaluate 10k: `GET /employees` n=23 median 144 / p95 240 / max 256 ms; reevaluate tunggal 27 ms; PUT profil 33 ms (non-blocking). Evaluasi penuh ±10k ≈ 7,4 detik; tidak ada 5xx teramati. Catatan: satu wrapper perintah benchmark keluar dengan exit code 1 karena perilaku output/grep, sementara body benchmark selesai dan menghasilkan angka di atas.

**Smoke konkurensi pasca-fix** (`perf_01f_conc_smoke.py`, fixture ZT01F-C; hasil `rr_perf_conc.json`) — **bukan pengganti benchmark bersih di atas**:
- bulk reevaluate API 7.415 ms (200); PUT rule 1.157 ms (200); reset rule 1.348 ms (200); refresh latar belakang setelah ubah rule 9,0 s; burst 20 panggilan scope 2,8 s (10×201 + 10×200); settle setelah burst 14,1 s.
- Baca selama refresh latar belakang: `/employees` median 37,5 / p95 232 ms; monitoring list 287 / 361 ms; summary 295,5 / 479 ms; 0 non-200. 0 HTTP 5xx, 0 traceback deadlock.
- Stale marking: chunked 365–419 ms vs UPDATE tunggal lama 177–587 ms (10.053 baris).
- Perbedaan angka tercatat apa adanya: plan mencatat smoke ini pada ±10.053 karyawan, sedangkan field `tenant_total` di `rr_perf_conc.json` (diambil dari `/completeness/summary` di awal run) bernilai **3.053**. Tidak direkonsiliasi.

---

## 7. Cleanup Final (scoped, disetujui user)

- Cleanup berbasis kepemilikan/provenance saja (dry-run → apply → dry-run ulang = 0):
  - 18 karyawan ZT01F + seluruh baris turunannya, 3 kandidat ZT01F (+ status history 30, interview 3, offering 3), 3 batch impor ZT01F, 3 objek storage staging milik fixture ZT01F.
  - 688 audit `completeness_*` yang terbukti berasal dari test → sisa **0**. Provenance per baris (`cleanup_01f_audit.py`): dibuat setelah m0007 diterapkan **dan** berasal dari dalam container (`ip_address` 127.0.0.1/testclient), atau HeadlessChrome dalam jendela screenshot automation, atau python-requests dalam jendela testing agent iteration_26. Baris yang tidak memenuhi syarat akan dibiarkan (dry-run: 688 dari 688 memenuhi).
- **Dipertahankan:** ZT01D 5, ZT01E 31, SMOKE 3, tenant ZTEST Sub (SA077F/SB077F) / Default Grace / Legacy, serta seluruh data baseline NEP/KBS/PT REAL.
- Counter karyawan NEP **tidak di-reset**: nilai saat ini **51**.
- Tenant `ZT01B170909`: NOT PRESENT (tidak dibuat/diubah).

## 8. Verifikasi Pasca-Cleanup

**Integritas 01F (read-only, sesi READ ONLY + rollback) — PASS**, dengan satu pengecualian pre-existing:

| Kategori | Status | Hasil |
|---|---|---|
| Duplikat (snapshot, assignment aktif, status history, family, nomor karyawan, rule) | PASS | semua 0 |
| Orphan (snapshot, family, kontrak, sertifikasi, assignment, status history, project, rule/scope, import rows) | PASS | semua 0 |
| Orphan dokumen | **FOUND — pre-existing / non-01F / non-blocker** | 2 dokumen, lihat Known Limitations |
| Tenant mismatch | PASS | semua 0; rule/scope = 0 |
| Nilai sensitif di snapshot | PASS | 88 nilai unik (NIK, NPWP, rekening, BPJS, telepon, email, alamat, NIK keluarga) → 0 ditemukan |
| Snapshot stale / menunggu evaluasi | PASS | stale 0; karyawan aktif tanpa snapshot 0 |
| Sisa data ZT01F (semua tabel, audit, rule/scope, storage) | PASS | semua 0 |
| Baseline | PASS | NEP 49 karyawan (42 aktif; 47 snapshot = 42 BELUM_LENGKAP + 5 EXCLUDED; 2 tanpa snapshot berstatus archived/deleted), KBS 3 (3 snapshot), SA077F 1, SB077F 1 |

**m0007 rerun — PASS.** Ledger: `m0007_data_completeness` applied `2026-09-26 00:43:17.135834`. Runner existing (dry-run dan jalur normal `--apply`) → **SKIP** ("sudah diterapkan … dilewati"). Fingerprint sebelum/sesudah identik: 68 tabel, schema hash (kolom + index) sama, jumlah baris seluruh 68 tabel sama (total 3.742), ledger tidak bertambah, permission 1 + grant `hr_admin`/`tenant_admin` tidak berubah. **Tidak ada mutation.**

**Layanan.** Health `{"status":"healthy","database":"mariadb:connected","read_only":false}`; backend, frontend, `hris-staging-s3` RUNNING. Halaman Monitoring terbuka normal lewat preview: tanpa banner pending, tanpa baris ZT01F.

---

## 9. Known Limitations (non-blocker)

1. **PTKP `TK/0`** — belum ada mekanisme konfirmasi; tetap **Anjuran**, tidak mempengaruhi skor maupun default payroll. Ditunda (deferred).
2. **Warning ESLint `EmployeeMigrationPage.jsx`** (dependency Hook) — issue **existing 01E**, bukan 01F. Build tetap PASS; tidak diubah di scope 01F.
3. **2 dokumen orphan lama (pre-existing / non-01F / non-blocker, tanpa tindakan):**
   - `71f57afe…` (NEP, tipe CV, owner_type employee, owner_id kosong) — dibuat 2026-09-20 04:38.
   - `fd5203c5…` (NEP, tipe KTP, owner_type applicant, label "SMOKE-B Belum Approved", kandidat tidak ada) — dibuat 2026-09-21 03:42.
   Keduanya dibuat sebelum m0007 (2026-09-26 00:43), tidak terkait ZT01F; tidak dihapus/diperbaiki dalam scope 01F.
4. Error DB non-konflik-kunci pada endpoint konfigurasi tetap 500 standar (tanpa stack trace) — di luar scope perbaikan deadlock.
5. Scheduler otomatis tidak berjalan di staging (`ENABLE_SCHEDULER=false`, disengaja).

---

## 10. Git / Environment

- Branch: `feature/upgrade-01f-data-completeness` (tanpa upstream; di remote hanya `origin/main` dan `origin/feature/upgrade-01b-01e-employee-core`).
- Commit lokal terakhir: `03a29ba` (perbaikan deadlock — 3 file fix sudah ter-commit lokal). Commit lokal dibuat otomatis oleh platform (`emergent-agent-e1`); tidak di-rewrite/rebase/reset.
- Working tree saat verifikasi: `M .env.example`, `M backend/.env.example` (sengaja dikecualikan dari commit), `?? test_reports/iteration_27.json`; tidak ada staged changes. File laporan ini dan update `plan.md` menambah perubahan lokal.
- Tidak ada push, PR, merge, atau deploy.
- **Production Changed: NO**

---

## 11. Kesimpulan

Seluruh fungsionalitas 01F (backend, UI, integrasi, scheduler, perbaikan deadlock) terverifikasi oleh agent; cleanup scoped selesai; integritas, m0007 rerun, dan kesehatan layanan PASS (dengan 2 dokumen orphan lama yang dicatat sebagai pre-existing non-blocker). Menunggu verifikasi final dan keputusan LOCK dari user.

**UPGRADE 01F — READY FOR FINAL VERIFICATION / LOCK**
