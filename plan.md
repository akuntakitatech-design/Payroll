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
- Menjaga UI **elegan & profesional**, konsisten dengan design system proyek (tanpa kesan “dibuat AI”).

> Status saat ini: seluruh fitur bundle (Payroll Run + Renewal Kontrak + Email Reminder + Import Excel) **sudah terimplementasi dan lulus E2E** (backend core & smoke & UI flows). Satu hal yang masih *environment-dependent*: pengiriman email via SMTP kantor harus diuji oleh user dengan kredensial SMTP nyata dari menu **Email & Pengingat**.

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
    - stat tiles (bruto/bpjs/pph21/potongan/net)
    - riwayat approval
    - tabel slip per karyawan (badge TER/Pasal 17)
    - dialog penyesuaian (hari kerja, unpaid days, overtime, extra earning/deduction)
    - aksi submit/approve/reject/mark-paid/recalculate
    - unduh slip PDF, unduh rekap Excel
  - `PayrollComponentsPage` (CRUD) ✅
  - `EmployeeSalariesPage` + `SalaryEditorDialog` ✅
  - `PayrollConfigPage` ✅ (BPJS & PPh21 statutory config per perusahaan)

- Employee self-service:
  - `MyPayslipsPage` ✅ (lihat daftar slip sendiri dan download PDF)

- Contract renewal:
  - `ContractRenewDialog` ✅
  - Integrasi tombol **Perpanjang** pada `ExpiryCalendarPage` untuk item kontrak ✅
  - Integrasi aksi **Perpanjang kontrak** pada dropdown aksi kontrak di `EmployeeDetailPage` ✅

- Employee detail:
  - Tab baru **“Gaji & Pajak”** ✅
    - ringkasan gaji pokok + komponen
    - PTKP/TER category + NPWP + BPJS flags + rekening
    - riwayat perubahan gaji
    - tombol buka `SalaryEditorDialog`

- Excel import:
  - `EmployeeImportPage` ✅ (stepper 4 langkah: template → unggah → validasi → commit)
  - `EmployeesPage` tombol “Impor Excel” ✅

- SMTP & reminders:
  - `MailSettingsPage` ✅
    - SMTP (password write-only) + email test
    - pengingat: windows H-, penerima, jam kirim, toggle include
    - preview digest, send-now, logs

- Utilities:
  - `frontend/src/lib/download.js` ✅ untuk download PDF/XLSX via axios agar Authorization header terbawa.

**Quality gates (done)**
- Compile check: `esbuild` bundle test clean.
- Visual check: screenshot preview untuk PayrollRuns, PayrollRunDetail, MailSettings, Import, MyPayslips, Renewal dialog.

---

### Phase 4 — Harden · Regression · Security ✅ **Completed (E2E + fix loop + cleanup)**
**User stories**
1. Sebagai admin multi-perusahaan, saya ingin tenant isolation payroll/reminder/import tetap aman.
2. Sebagai auditor, saya ingin setiap perubahan payroll/salary/reminder/renewal terekam audit log.
3. Sebagai HR, saya ingin histori reminder terlihat agar bisa membuktikan email terkirim.
4. Sebagai pengguna, saya ingin error message jelas (Bahasa) saat validasi Excel gagal.
5. Sebagai karyawan, saya ingin dijamin tidak bisa mengakses slip gaji orang lain.
6. Sebagai user, saya ingin UX rapi: loading/empty/error state konsisten, label konsisten, tanpa teks debug.

**E2E coverage (testing agent iterations 5–7 + verifikasi manual)**
- Payroll lifecycle lengkap:
  - create run → adjustment → recalculate → submit → reject (catatan wajib) → submit ulang → approve → mark paid.
  - download slip PDF + export Excel.
- Self-service:
  - employee hanya melihat & mengunduh slip sendiri; sidebar employee tidak menampilkan menu HR payroll.
- Excel import:
  - template → upload (2 valid + 1 invalid) → validasi row-level → commit valid rows.
- Contract renewal:
  - dari kalender expiry dan dari detail karyawan.
- Mail settings:
  - SMTP tersimpan (password tidak pernah ditampilkan)
  - windows H-* tersimpan & ditampilkan
  - pratinjau digest tampil tanpa crash.
- Tenant isolation:
  - cross-tenant access diblokir (404) dengan JWT yang benar.

**Bugs found & fixed (all resolved)**
1. **CRITICAL** PayrollConfigPage crash
   - Root cause: `GET /api/payroll/config` mengembalikan `jkk_risk_classes` sebagai object.
   - Fix:
     - Backend `/api/payroll/config` kini mengembalikan **array** (selaras dengan `/api/payroll/catalog`).
     - Frontend `PayrollConfigPage` toleran menerima array/object.
2. **CRITICAL** MailSettingsPage crash saat “Pratinjau isi”
   - Root cause: backend `preview.items` berbentuk dict per-kind, frontend menganggap array.
   - Fix: frontend flatten `preview.items` → array + label jenis Bahasa Indonesia + format H-/kedaluwarsa.
3. **HIGH** Logout tidak bisa diklik saat E2E
   - Root cause: toast Sonner posisi **top-right** menutupi tombol menu pengguna.
   - Fix: Toaster dipindah ke **bottom-right**.
4. **LOW** Hydration warning `<div>` di dalam `<p>` pada PageHeader subtitle
   - Fix: subtitle detail payroll dibuat teks biasa, badge status dipindah ke area actions.
5. **UX/Data** Komponen gaji di tab “Gaji & Pajak” tampil UUID / nilai “-”
   - Fix: backend `GET /api/payroll/salaries/{employee_id}` enrich komponen dengan `name/code/kind/calc/percent/effective_amount/uses_default`.
   - Catatan: `amount` mentah tetap `null` untuk menjaga editor tidak “membekukan” nilai default.
6. **Stability** DOM detach setelah refresh
   - Fix: `PayrollConfigPage` dan `MailSettingsPage` memakai **silent reload** agar tidak unmount input saat refresh.
7. **UX** Riwayat approval payroll
   - Fix: label aksi riwayat dibuat Bahasa Indonesia (Diajukan/Ditolak/Disetujui/Ditandai dibayar).

**Cleanup & demo data state (restored)**
- Data uji dibersihkan.
- Dataset demo saat ini:
  - 8 karyawan demo
  - 14 komponen payroll demo
  - 2 payroll run demo: **Mei 2026 (paid)**, **Desember 2026 (draft)**
  - 8 kontrak demo
  - reminder_logs dikosongkan
  - SMTP/reminder demo dipulihkan: windows **H-30/14/7/1**, jadwal **07:00** WIB.

**Known note (pre-existing, not a regression)**
- `DataTable` merender varian mobile + desktop sehingga `data-testid` row bisa muncul dua kali (salah satu hidden). Tidak mempengaruhi fungsi.

---

## 3) Next Actions (immediate)
1. **UAT / konfigurasi SMTP nyata oleh user**:
   - Buka **Pengaturan → Email & Pengingat**.
   - Isi host/port/security/username/password SMTP perusahaan.
   - Klik **Kirim email tes**.
   - Setelah valid, aktifkan pengingat otomatis dan atur recipients + windows H-* sesuai kebijakan.
2. Jika diperlukan, tambah enhancement pasca-UAT:
   - bank transfer file format tertentu (jika dibutuhkan)
   - tambahan laporan (rekap BPJS, pajak)
   - opsi template Excel tambahan (kontrak/sertifikasi/dokumen) di fase berikutnya.

---

## 4) Success Criteria
- `python backend/test_core.py` passes (**186/186**).
- Backend smoke `python backend/smoke_api.py` passes (**137/137**).
- Payroll run dapat dibuat, dihitung ulang, disubmit, diapprove/reject, ditandai dibayar; slip PDF & rekap Excel dapat diunduh (E2E verified).
- Employee hanya dapat mengakses **slip gaji sendiri**; tidak dapat mengakses slip orang lain (E2E verified).
- Tenant isolation enforced untuk semua endpoint by-id (E2E verified).
- Contract renewal 1-klik bekerja dari kalender expiry dan dari tab kontrak employee (E2E verified).
- SMTP configurable per company; password tidak pernah returned oleh API; reminder preview/log bekerja (E2E verified). Pengiriman email nyata menunggu kredensial SMTP kantor.
- Excel import: template → validate → commit, error baris jelas, baris invalid tidak merusak data (E2E verified).
- UI konsisten, profesional, dan stabil (tidak ada crash runtime; logout/login lancar; hydration warning diselesaikan).