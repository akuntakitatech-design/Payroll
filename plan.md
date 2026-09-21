# Time Management V1 (HRIS & Payroll) — Plan

## 1) Objectives
- Deliver Time Management V1 terintegrasi untuk **Absensi**, **Jadwal/Shift/Kalender**, **Cuti/Izin/Sakit**, **Lembur**, **Approval**, **Period Lock**, **Audit Log**, **Tenant Isolation**, siap integrasi Payroll (tanpa ubah engine Payroll/BPJS/PPh21).
- Semua UI user-facing **Bahasa Indonesia**, reuse menu existing **`attendance`** dan **`leave_overtime`** (tanpa modul/menu duplikat).
- Bekerja **hanya** di DEVELOPMENT:
  - **MariaDB lokal `hris_payroll_dev`** (jangan buat DB baru; **remote `<host-produksi>` dianggap PRODUCTION dan tidak disentuh**).
  - R2 DEVELOPMENT existing (kredensial diisi user; jangan tampilkan secret).
- Ikuti alur: **Coding DEV → Test → Preview → User Uji → Revisi → User Approve → baru PR**.
  - Untuk saat ini: **stop sebelum GitHub action** (tanpa commit/push/PR/merge/deploy).

### Update fokus (fase baru)
- Fokus saat ini sesuai instruksi user: **MODUL ABSENSI — Alur Operasional Karyawan (Employee Self Service/ESS)**.
- Batas scope untuk pekerjaan lanjutan ini:
  - **Hanya Absensi** (ESS check-in/out GPS + approval lokasi).
  - **Jangan masuk** cuti/izin/sakit, lembur, payroll, BPJS, PPh21, refactor besar tenant, recruitment.

## 2) Implementation Steps

### Phase 1 — Environment & Core Workflow POC (Isolation) (COMPLETED)
Core = “Time events + policy + approval + period lock + tenant isolation”
- Environment DEV diverifikasi:
  - MariaDB lokal `hris_payroll_dev` **connected & writable**.
  - Remote MariaDB `<host-produksi>` **tidak disentuh**.
- POC API + schema + seed + smoke test `backend/smoke_time.py`.

**User stories (POC)**
1. Sebagai HR, saya bisa menutup periode agar semua perubahan time data pada periode itu tertolak.
2. Sebagai karyawan, saya bisa absen masuk/pulang dengan GPS dan sistem menghitung status (hadir/telat/pulang cepat).
3. Sebagai karyawan, saya bisa mengajukan cuti dan saldo terhitung berbasis ledger.
4. Sebagai supervisor/HR, saya bisa melihat daftar pending approval dan mengambil keputusan.
5. Sebagai admin multi-tenant, saya tidak bisa mengakses data tenant lain (404/isolasi).

**Status:** COMPLETED.

---

### Phase 2 — V1 App Development (Backend) (COMPLETED)
#### 2.1 Backend (COMPLETED)
- Schema: **14 tabel Time Management + indexes**.
- Router terdaftar: `time_core`, `schedules`, `attendance`, `leave`, `overtime`.
- Shared services: `timekeeping.py`, `time_service.py`, `time_approval.py`, `time_excel.py`.
- Seed: `seed_time.py` (shift, kalender, leave types, **geofence di lokasi existing**, workflow approval tambahan, saldo cuti, top-up RBAC aditif).
- RBAC: perubahan **aditif** untuk permission Time Management.
- Smoke API: **45/45 PASS**.

**Catatan audit Absensi (backend) — sudah ada & berfungsi (REUSE)**
- Check-in/out self-service: `POST /attendance/check-in`, `POST /attendance/check-out`.
  - Waktu **server** sebagai sumber waktu (`tk.now_utc()`), timestamp frontend tidak dijadikan sumber final.
  - Proteksi double: unique index `(company_id, employee_id, work_date)` + atomic update pada checkout.
- Perhitungan: shift normal, toleransi telat/pulang cepat, istirahat, overnight shift 23:00–07:00.
- GPS/geofence: Haversine backend + 4 policy: `inside_required`, `outside_requires_approval`, `gps_only`, `disabled`.
- Status user-facing Bahasa Indonesia tersedia via katalog (Hadir/Terlambat/Pulang Cepat/Terlambat & Pulang Cepat/Belum Absen Pulang/Menunggu Persetujuan Lokasi/Lokasi Ditolak/OFF/Libur/Tidak Ada Jadwal/Alfa).
- Approval lokasi: reuse approval engine bersama (`time_approval.py`, sequential, fail-closed jika workflow tidak ada).
- Audit log: `check_in`, `check_out`, `geofence_approved`, `geofence_rejected` sudah dicatat.
- Tenant scoping: seluruh query memakai `ctx.company_id` (company_id dari payload tidak jadi otoritas).

**Backend follow-ups (gate sebelum final handover)**
- **R2 integration gate:** upload lampiran (sakit/izin/koreksi) hanya setelah R2 DEV configured.

**Status:** COMPLETED.

---

### Phase 3 — V1 App Development (Frontend) (COMPLETED)
Target: menu existing **Absensi** dan **Cuti & Lembur** menampilkan V1 flows end-to-end.

**Attendance module (menu existing `attendance`)**
- Implementasi halaman: Ringkasan, Absensi Saya, Daftar Absensi, Jadwal Kerja, Rekap, Persetujuan, Impor (wizard), Pengaturan + layout & tab.
- UI Bahasa Indonesia, memakai design system existing.

**Leave & Overtime module (menu existing `leave_overtime`)**
- Implementasi halaman ringkasan/pengajuan/saldo/persetujuan.
- Lampiran: UI upload hanya jika R2 configured; kalau belum, tampilkan pesan “Storage belum terkonfigurasi”.

**Build/quality gates**
- Compile `esbuild` OK.
- Bahasa Indonesia untuk UI Time Management.
- Screenshot awal disetujui user.

**Status:** COMPLETED.

---

### Phase 4 — Testing & Validation (agent + regression) (COMPLETED)
Semua pengujian berbasis report di `/app/test_reports/`.

- **Iterasi 9** (`/app/test_reports/iteration_9.json`)
  - Cakupan: fitur inti backend + sebagian frontend.
  - Hasil: backend 42/45, frontend 10/11 (temuan minor/non-blocking).

- **Iterasi 10** (`/app/test_reports/iteration_10.json`)
  - Prioritas: **Impor Kehadiran E2E** (analyze → preview → commit + verifikasi DB).
  - Regression modul existing: **8/8 PASS**.

- **Iterasi 11** (`/app/test_reports/iteration_11.json`)
  - Edge cases import + RBAC + lock + tenant + audit: **43/43 PASS**.

- **Iterasi 12** (`/app/test_reports/iteration_12.json`)
  - Empty-state Absensi aman.
  - Smoke ulang **45/45 PASS**.

**Status:** COMPLETED.

---

### Phase 5 — R2 DEVELOPMENT (Attachment) (BLOCKED — Menunggu User)
- Status runtime storage: **not-configured** karena `R2_*` di `backend/.env` masih kosong.
- Upload lampiran (sakit/izin/koreksi) **belum bisa divalidasi** sampai user mengisi credential R2 DEV.
- Perilaku saat storage belum configured: pesan jelas Bahasa Indonesia (bukan 500 crash).

**Status:** BLOCKED.

---

### Phase 6 — Preview + Handover + STOP (IN PROGRESS)
- Preview DEVELOPMENT siap diuji user:
  - URL: `https://repo-clone-setup-1.preview.emergentagent.com`
- Tidak ada aksi GitHub:
  - **tanpa** commit/push/PR/merge/deploy.
- Setelah laporan akhir, agent **STOP** dan menunggu uji & approval user.

**Status:** IN PROGRESS.

---

### Phase 7 — Absensi ESS (Alur Operasional Karyawan) — Audit → Lengkapi → TEST → Publish Preview → STOP (COMPLETED — menunggu uji & approval user)
Fase ini mengikuti instruksi user: **jangan mengulang fitur yang sudah selesai**; audit dulu; lengkapi yang belum lengkap/terhubung.

#### 7.1 Audit hasil (faktual)
**SUDAH ADA & BERFUNGSI (REUSE, tidak dibuat ulang)**
- Master Shift (backend `time_core`, seeded; shift P/S/M/OFF).
- Jadwal Kerja (backend `schedules.py`, UI SchedulesPage).
- Lokasi Kerja (master `work_locations` sudah punya kolom geofence di DB).
- Absen Masuk/Pulang (GPS + server-time authoritative).
- GPS/geofence (Haversine + 4 policy).
- Perhitungan telat/pulang cepat/overnight/break.
- ESS “Absensi Saya” (MyAttendancePage) + histori sederhana.
- Approval lokasi (router `/attendance/approvals` + decide endpoint; frontend AttendanceApprovalsPage).
- Audit log untuk check-in/out dan approval.

**SUDAH ADA TAPI BELUM LENGKAP (target pekerjaan fase 7)**
1) **Master Lokasi Kerja — konfigurasi geofence belum muncul di UI**
   - DB sudah punya `geofence_enabled`, `attendance_location_policy`, `gps_accuracy_max_meter`, tapi master form (`masterConfig.js`/`masters.py`) belum mengekspos.

2) **RBAC data scope untuk Karyawan (self-service only) belum enforced di API**
   - Role `employee` punya `attendance:view` + `attendance:create`.
   - Endpoint `attendance:view` saat ini juga membuka akses ke list/dashboard/exceptions/recap dan schedules list.
   - Perlu pemisahan scope: karyawan hanya bisa akses endpoint/rows miliknya (tanpa menambah modul/menu baru).

3) **Approval untuk check-out luar radius (dan alasan pulang) belum lengkap**
   - Saat check-out berada di luar radius, jika sebelumnya status lokasi sudah `approved`, sistem tidak membuat approval baru.
   - Alasan check-out belum disimpan terpisah (masih memakai field reason tunggal).

4) **Idempotensi retry**
   - Proteksi double sudah ada (unique index + atomic update), tetapi retry request yang sama masih bisa berakhir 409.
   - Target: jika client mengirim request-id yang sama, server mengembalikan record yang sama (200) dan tidak membuat transaksi ganda.

5) **/me/today & /me**
   - `/attendance/me/today` belum menyediakan ringkasan status harian kanonik dari backend (“Belum Absen / OFF / Libur / Jadwal kerja belum tersedia”).
   - `/attendance/me` belum menyertakan `work_location_name` (baru tersedia di list HR via decorate helper).

6) **UI Approvals & MyAttendance (mobile-first) perlu dipoles untuk alur operasional**
   - Approvals: perlu tampilkan jenis absen (Masuk/Pulang), shift, jam, GPS aktual, akurasi, jarak, radius, alasan, map link yang relevan.
   - MyAttendancePage: action utama besar & hanya tampil yang relevan (jangan menampilkan tombol yang tidak bisa dipakai), teks “Jadwal kerja belum tersedia.” sesuai instruksi, dan riwayat menampilkan Shift/Lokasi.

7) **Audit labels**
   - Perlu action spesifik untuk outside-radius check-in/out (mis. `check_in_outside_radius`, `check_out_outside_radius`) dan labelnya.

8) **Data DEVELOPMENT siap pakai untuk user test ESS**
   - Seed tidak membuat jadwal; saat ini hanya ada 3 schedule row untuk satu employee pada tanggal berjalan.
   - Perlu membuat jadwal bulan berjalan untuk karyawan yang ter-link via **API existing** `/schedules/bulk` sebagai HR (tanpa membuat DB baru).

9) **Cleanup: orphan approval rows**
   - Ditemukan `time_approvals` pending untuk `attendance_correction` yang sudah tidak punya record koreksi (orphan). Perlu dibersihkan dengan aman di DEV.

**BELUM ADA:** tidak ada fitur inti ESS Absensi yang benar-benar belum ada; fokus fase 7 adalah *melengkapi & menghubungkan*.

#### 7.2 Implementation steps (fase 7)
1) **Master Lokasi Kerja (UI)**
   - Update master config (`frontend/src/lib/masterConfig.js`) untuk menambah fields:
     - `geofence_enabled` (boolean)
     - `attendance_location_policy` (select: 4 policy)
     - `gps_accuracy_max_meter` (number)
   - Update backend master registry (`backend/app/masters.py`) agar field tersebut diizinkan untuk CRUD (tanpa membuat master baru).
   - Pastikan boolean/numeric coercion di backend mendukung field baru (tambahkan ke `BOOLEAN_FIELDS` / `NUMERIC_FIELDS` bila perlu).

2) **RBAC scope enforcement untuk Karyawan (tanpa memperluas matrix permission)**
   - Implement helper (mis. `svc.self_employee_id(ctx)` / `attendance.self_scope(ctx)`):
     - Jika role employee tanpa `attendance:approve|edit|export|delete`:
       - Endpoint list/dashboard/exceptions/recap/import/manual/schedules list/bulk → tolak (403) atau scope ketat.
       - Endpoint `/attendance/me*` tetap boleh.
       - Endpoint `/attendance/check-in|check-out` tetap boleh.
       - Endpoint `/attendance/corrections` untuk `mine=true` tetap boleh.
     - Enforcement ada di backend (bukan hanya hide tab di UI).

3) **Check-in/out outside radius (approval per event)**
   - Tambahkan kolom attendance untuk alasan check-out terpisah:
     - `check_out_reason_code`, `check_out_reason` (atau penamaan yang konsisten dengan existing).
   - Tambahkan kolom untuk membedakan approval target:
     - `location_approval_for` = `check_in` / `check_out` (atau field serupa).
   - Pastikan:
     - check-in outside radius → approval `attendance_location` untuk check-in.
     - check-out outside radius → approval baru (approval_round increment) untuk check-out **meski check-in sudah approved**.
   - Update approval detail payload `/attendance/approvals` agar memuat informasi check-in/check-out yang relevan.

4) **Idempotensi request**
   - Tambahkan kolom:
     - `check_in_request_id` & `check_out_request_id` (string)
   - Jika request_id sama sudah pernah diproses:
     - check-in: return 200 dengan row yang sama (bukan membuat row baru / bukan 409).
     - check-out: return 200 dengan row hasil update yang sama.

5) **API enhancements untuk ESS**
   - `/attendance/me/today`: tambahkan `today_status_key` + `today_status_label` yang kanonik dari backend (termasuk “Belum Absen”, “Jadwal kerja belum tersedia”, “OFF”, “Libur”).
   - `/attendance/me`: tambahkan `work_location_name` dan `shift_name` bila belum ada di item.

6) **UI/UX ESS**
   - MyAttendancePage:
     - Mobile-first: hanya tampilkan 1 action utama yang relevan; tombol besar.
     - Pastikan pesan GPS gagal sesuai instruksi (“Lokasi belum dapat diperoleh…”) dan tidak membuat absensi palsu.
     - Ubah copy untuk no-schedule jadi persis “Jadwal kerja belum tersedia.”
     - Riwayat: tambah kolom Shift & Lokasi.
   - AttendanceApprovalsPage:
     - Tampilkan jenis absen (Masuk/Pulang), shift, jam, akurasi, GPS, jarak, radius, alasan, map link.

7) **Audit log & label**
   - Tambahkan audit action spesifik untuk outside radius (check-in/out), dan tambahkan labelnya di katalog action audit log (agar tampil rapi di filter/view).

8) **Data DEV untuk uji user**
   - Buat jadwal bulan berjalan untuk user karyawan yang ter-link, via `/schedules/bulk` menggunakan akun HR/Owner (tanpa seed otomatis, tanpa DB baru).

9) **Cleanup orphan approvals (DEV-only)**
   - Hapus/mark `time_approvals` pending yang record-nya tidak ada lagi (khusus `attendance_correction` orphan yang ditemukan).
   - Pastikan tidak menyentuh data perusahaan lain (tenant isolation).

#### 7.3 Test plan (wajib sebelum publish preview)
- Jalankan testing agent untuk minimal 15 skenario user:
  1) Jadwal normal → check-in dalam radius sukses.
  2) Terlambat → `late_minutes` benar.
  3) Check-out normal → `actual_work_minutes` benar.
  4) Pulang cepat → `early_leave_minutes` benar.
  5) Double check-in → tidak duplikat.
  6) Check-out tanpa check-in → ditolak.
  7) GPS dalam radius → valid.
  8) GPS luar radius policy approval → “Menunggu Persetujuan Lokasi”.
  9) HR approve → attendance valid.
  10) HR reject → status “Lokasi Ditolak” dan histori tetap ada.
  11) Policy GPS Saja → diterima tanpa cek radius.
  12) GPS permission ditolak → tidak buat attendance palsu, pesan jelas.
  13) Overnight 23:00–07:00 → dihitung benar.
  14) Tenant isolation A tidak bisa akses data B.
  15) Employee hanya bisa lihat riwayat dirinya.
- Regression minimal: login, demo login, company switcher, dashboard, recruitment, employees, contracts, certifications, documents, approval config, payroll, BPJS, PPh21, master data.

#### 7.4 Publish preview & STOP
- Setelah semua test internal pass → pastikan preview updated dan laporkan URL.
- **STOP** menunggu user uji & approval. Tidak ada GitHub action.

**Status:** COMPLETED (development-tested; belum user-accepted).

#### 7.5 Hasil (ringkas)
- Backend: scope self-service (`time_service.self_service_only/scope_employee_id/require_hr_scope`), idempotensi `client_request_id`, approval per peristiwa (masuk/pulang, `approval_round`), pre-check `ta.ensure_ready`, gate decide = penyetuju tahap ATAU `attendance:approve`, `/me/today.today_status`, timezone lokasi pada list/detail/approval, master Lokasi Kerja ekspos geofence fields, label audit.
- Frontend: MyAttendancePage mobile-first (satu aksi relevan, jam server, banner jadwal/OFF/pending/ditolak, timeline approval, riwayat + Lokasi/Shift), AttendanceApprovalsPage detail lengkap, tab berdasarkan scope + redirect, AttendanceListPage detail (masuk & pulang, peta, histori putaran), form Lokasi Kerja.
- Test: `backend/smoke_ess.py` 81/81 (unit menit + API E2E), testing agent iterasi 13 backend 77/78 (1 "minor" = ekspektasi tester salah; `GET /attendance/{id}` memang `{attendance, approval}`), frontend 100%; regresi API/UI existing normal, tanpa console error.
- Data DEV: jadwal Sep–Okt 2026 (Shift Pagi, Sen–Jum) untuk NEP-0001 & NEP-0002 via `/schedules/bulk`; absensi uji hari ini direset (`backend/reset_ess_today.py`); 4 approval koreksi orphan dibersihkan.
- Env: paket MariaDB hilang saat pod restart (di luar /app) → dipasang ulang, datadir `/app/.local-data/mariadb` utuh (lihat ops/README.md).

## 3) Next Actions (immediate)
1) Implement Phase 7.2 (Absensi ESS gap fixes) secara incremental (mulai dari Master Lokasi Kerja config UI + RBAC scope enforcement).
2) Internal test + testing agent skenario 1–15 + regression.
3) Publish/update preview DEVELOPMENT + laporkan URL.
4) **STOP** menunggu uji & approval user.

## 4) Success Criteria
- UI Absensi ESS nyaman dipakai di HP (action utama jelas dan kontekstual).
- ESS flow end-to-end: Login → Absensi Saya → Jadwal Hari Ini → Lokasi Kerja → Absen Masuk (GPS) → Absen Pulang (GPS) → status dihitung backend.
- GPS/geofence policy per lokasi kerja bisa diatur dari Master Lokasi Kerja (tanpa master baru).
- Outside radius (policy approval): transaksi tetap tersimpan + alasan wajib + status “Menunggu Persetujuan Lokasi”, dan approval HR bisa approve/reject dengan audit log.
- Proteksi transaksi: no double check-in/out; idempotent retry tidak membuat transaksi ganda.
- Tenant isolation: Company A tidak dapat akses data Company B.
- Karyawan hanya dapat melihat data absensinya sendiri (API enforcement, bukan hanya UI hide).
- Regression modul existing tetap normal.
- Setelah publish preview: agent berhenti dan menunggu approval user sebelum tindakan GitHub apa pun.

## Appendix — Cleanup & Open Notes
### Cleanup yang sudah dilakukan
- Pembersihan data uji DB dev (historis fase sebelumnya): attendance/import/corrections dibersihkan; empty state diverifikasi.
- `.gitignore` ditambah (aditif) untuk mencegah kebocoran.

### Catatan terbuka (non-blocking)
- Console warning recharts `width(-1) height(-1)` berasal dari file existing `frontend/src/components/dashboard/DepartmentChart.jsx` dan **bukan** regression Time Management; tidak diubah tanpa izin user.
- R2 DEV masih belum configured; upload lampiran tidak divalidasi (di luar scope fase Absensi ESS saat ini, kecuali user meminta).
- Ditemukan orphan approvals pending untuk `attendance_correction` (DEV) → akan dibersihkan pada Phase 7.2 langkah 9.