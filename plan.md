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

**Objective baru (governing request saat ini): Foundation Penguatan Tenant Isolation (Tahap 1 SaaS) — WAJIB**
- Menghilangkan ketergantungan pada developer menulis filter manual `{"company_id": ctx.company_id}` untuk setiap query.
- Membuat **tenant-aware enforcement** di data access layer agar semua operasi ke tabel tenant otomatis terikat ke `active company` dari authenticated context.
- Prinsip:
  - **Tidak** mengganti adapter Mongo-style existing.
  - **Tidak** mengganti SQLAlchemy Core / menambah ORM baru.
  - **Tidak** menambah Alembic.
  - **Tidak** mengubah struktur 31 tabel tenant existing.
  - **Tidak** mengubah bentuk JWT, auth, role, semantics `company_id`.
  - Tetap kompatibel dengan pola Mongo-style (`find`, `find_one`, `update_one`, `$or`, `$regex`, dsb).
  - **Fail-safe**: akses tenant-scoped tanpa company context harus ditolak.
  - Platform bypass hanya lewat mekanisme internal eksplisit yang tidak bisa dipakai role tenant biasa.

**Larangan eksplisit (untuk tahap ini)**
- Jangan membuat/menambah: `tenant_subscriptions`, `subscription_history`, `platform_settings`, `platform_audit_logs`, `tenant_profiles`.
- Jangan membuat: role `PLATFORM_OWNER`, Platform Console, subscription/trial.
- Jangan mengubah domain/deployment/env/UI.

**Catatan status terbaru (berdasarkan sesi ini)**
- Preview Emergent: backend/frontend berjalan, `/api/health` mengembalikan `mariadb:connected` dan `read_only: true`.
- GitHub:
  - PR #1–#5: **merged**.
  - PR #6 (redesign dashboard premium): **merged**.
  - **PR #7 (Tenant Isolation Foundation / Tahap 1 SaaS): OPEN, mergeable clean (6 file, +949/-43).**
- Audit SaaS readiness telah selesai (dokumen lokal `/app/AUDIT_SAAS_READINESS.md`, belum di-commit).

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
(**Tetap, tidak ada perubahan untuk Tahap 1 SaaS**)

---

### Phase 3 — Frontend V1 (UI parity + UX) ✅ **Completed (agent-tested)**
(**Tetap, tidak ada perubahan untuk Tahap 1 SaaS**)

---

### Phase 4 — Harden · Regression · Security ✅ **Completed (E2E)**
(**Tetap, tidak ada perubahan untuk Tahap 1 SaaS**)

---

### Phase 4B — Preview Produksi Aman (READ_ONLY) ✅ **Completed (merged via PR #4)**
(**Tetap. Ini menjadi constraint untuk pengujian: tes tulis tidak boleh menyentuh DB produksi.**)

---

### Phase 4C — Aturan Kerja Repo (Manusia + AI) ✅ **Completed (merged via PR #5)**
(**Tetap. Semua perubahan Tahap 1 SaaS harus melalui PR.**)

---

### Phase 4D — Redesign Dashboard Premium (Desktop) ✅ **Completed (merged via PR #6)**
(**Di luar scope Tahap 1 SaaS; sudah selesai dan merged.**)

---

### Phase 5 — SaaS Tahap 1: Tenant Isolation Foundation ✅ **IMPLEMENTED — PR #7 OPEN (menunggu review/merge)**

#### 5.1 Latar masalah
Saat ini isolasi tenant terjadi karena developer menambahkan filter manual:
```json
{"company_id": ctx.company_id}
```
Risiko: 1 query lupa filter ⇒ data lintas perusahaan dapat terbaca/terubah.

#### 5.2 Temuan analisis (Step A) ✅
- **Choke point tunggal terbaik** ada di `Collection._where()` (`backend/app/core/db.py:891`) karena dipakai oleh:
  - `find/find_one` via `_select`
  - `count_documents`
  - `distinct`
  - `_find_ids` → dipakai oleh `update_one/update_many/replace_one/find_one_and_update/delete_one`
  - `delete_many`
  ⇒ Mengikat `_where()` berarti mengikat seluruh read + matching update/delete.
- `compile_filter()` menggabungkan top-level key dengan `and_()`, sehingga injeksi filter `company_id` pada top-level aman meskipun query memiliki `$or/$and/$nor`.
- Jalur insert tidak melewati `_where()` ⇒ perlu enforcement khusus untuk insert/upsert.
- Koreksi audit: sudah ada `TenantRepository` (`backend/app/core/repo.py`) yang melakukan scoping untuk sebagian master data, namun banyak router masih memakai `db = get_db()` langsung. Gap utama ada pada akses DB yang tidak melalui repository.

#### 5.3 Desain solusi (Step B) ✅ **Dibuat (additive, minimal)**
**Tujuan desain:** menambah lapisan tenant-aware tanpa merombak `core/db.py`.

**Deliverables yang sudah dibuat (PR #7):**
1. **File baru** `backend/app/core/tenancy.py` (303 baris)
   - `TenantContextMissing(HTTPException 400)` — fail-safe jika tabel tenant diakses tanpa company context.
   - `CrossTenantDenied(HTTPException 403)` — jika client mencoba memaksa/override company_id atau mengakses record tenant lain.
   - `TenantCollection(Collection)`:
     - override `_where()` untuk menyuntik filter `company_id` sebagai enforcement tunggal.
     - defense-in-depth: bila filter sudah memuat `company_id` dan nilainya berbeda dari context ⇒ **403**.
     - override `insert_one/insert_many/_upsert_doc/replace_one` untuk memaksa `doc["company_id"]` dari context.
     - update/delete cross-tenant terblok karena `_find_ids` selalu ter-scope.
   - `TenantDatabase`:
     - mengembalikan `TenantCollection` untuk tabel tenant dan `Collection` biasa untuk `GLOBAL_COLLECTIONS`.
     - **Fail-closed:** nama tabel yang tidak dikenal diperlakukan sebagai tenant (tetap ter-scope).
     - `unscoped_db(reason)` sebagai satu-satunya bypass eksplisit + logging (tidak terjangkau dari request).

2. **Perubahan additive** di `backend/app/core/deps.py`
   - Property baru pada `AuthContext`: `ctx.tdb` (tenant db accessor) yang memanggil `get_tenant_db(ctx.company_id)`.

**Catatan penting:** `backend/app/core/db.py` **TIDAK DIUBAH SAMA SEKALI** (hanya diturunkan/subclass).

#### 5.4 Migrasi bertahap (Step C + D) ✅ **POC selesai, defense-in-depth dipertahankan**
**Scope POC migrasi (sudah diterapkan, PR #7):**
1. **Employees** (`backend/app/routers/employees.py`)
   - 6 endpoint + 5 helper: `db = ctx.tdb` atau `db = get_tenant_db(company_id)`.
2. **Payroll** (`backend/app/routers/payroll.py`)
   - 22 endpoint + 4 helper + 1 pemanggilan khusus: `db = ctx.tdb` atau `db = get_tenant_db(cid)`.
3. **Master data** (`backend/app/routers/master.py`)
   - 2 helper yang dipakai untuk seluruh entitas master: `db = get_tenant_db(company_id)`.

**Defense-in-depth:** filter manual `{"company_id": ctx.company_id}` yang sudah ada **tidak dihapus**.

#### 5.5 Automated tests (Step E) ✅
Constraint: preview terhubung ke MariaDB produksi dengan `READ_ONLY=true`, sehingga tes tulis **tidak boleh** dilakukan ke produksi.

**Test baru (PR #7):** `backend/tests/test_tenant_isolation.py`
- Berjalan di **SQLite + aiosqlite** pada file DB temporer.
- Tidak menambah dependency baru (menggunakan `asyncio.run`, bukan `pytest-asyncio`).
- **Hasil:** 12/12 lulus.

**Cakupan test utama:**
1. Tenant A bisa membaca data sendiri.
2. Tenant A tidak bisa membaca data Tenant B.
3. Tenant A tidak bisa update data Tenant B.
4. Tenant A tidak bisa delete data Tenant B.
5. Insert/upsert tenant otomatis mendapat company_id yang benar.
6. Akses tenant-scoped tanpa company context ditolak (HTTP 400).
7. GLOBAL_COLLECTIONS tetap bekerja seperti existing.
8. switch-company (simulasi scope A ↔ B) tetap bekerja.
9. super_admin existing tidak rusak (semantik `company_id = NULL` tetap utuh) + bypass eksplisit `unscoped_db(reason)`.
10. payroll flow minimal tetap bekerja.
11. Regression keamanan: `company_id` dari klien tidak boleh mengalahkan context (ditolak 403).
12. SQL selalu memuat batasan company_id pada tabel tenant dan TIDAK memuat batasan pada tabel global.

#### 5.6 Validation & verification ✅
- Backend compile OK.
- Aplikasi preview tetap sehat (`/api/health` OK; `read_only: true`).
- **Wajib testing agent**: sudah dipenuhi.
  - testing_agent report: **20/20 regresi lulus** (auth login/me/switch-company; employees; payroll; master; dashboard; global tables; UI load + company switcher).
  - Tidak ada kebocoran data lintas tenant terdeteksi.
  - Data produksi tidak berubah.

#### 5.7 Deliverables tahap ini ✅
- **PR #7 (OPEN)**: tenant isolation enforcement foundation.
- Ringkasan implementasi, test, dan hasil verifikasi ada pada deskripsi PR.

**Stop condition:** berhenti setelah Tahap 1 selesai dan menunggu review/merge PR #7. **Tidak lanjut ke Tahap SaaS lain**.

---

## 3) Next Actions (immediate)
1. **User review PR #7**: https://github.com/akuntakitatech-design/Payroll/pull/7
2. Jika disetujui, **merge PR #7** ke `main`.
3. Setelah merge, berhenti (sesuai instruksi). Tahap berikutnya (migrasi router lain, subscription/trial/platform console/platform owner/domain) hanya dilakukan bila ada persetujuan eksplisit dan dalam PR terpisah.

---

## 4) Success Criteria

### 4.1 Tenant Isolation Foundation (Tahap 1 SaaS) — wajib ✅
- Semua operasi tenant-scoped secara default terikat `ctx.company_id`.
- Akses tenant-scoped tanpa company context ditolak (fail-safe).
- Insert/upsert tenant selalu memaksa `company_id` dari context.
- Update/delete tidak dapat menyentuh record tenant lain.
- GLOBAL_COLLECTIONS tetap berfungsi seperti existing.
- `switch-company` tetap bekerja.
- `super_admin` existing tidak rusak.
- Payroll existing tidak rusak.
- Tidak ada perubahan contract response endpoint.
- Regression test mencakup upaya override company_id dari client (ditolak).
- **Verified oleh testing_agent** (wajib) — 20/20 lulus.

### 4.2 Constraint keamanan & operasional ✅
- Tidak ada `.env`/secret ter-commit.
- Tidak ada write ke MariaDB produksi (preview tetap `READ_ONLY=true`).
- Tidak ada perubahan deployment/domain/env/UI.
- `backend/app/core/db.py` tidak disentuh.

### 4.3 Open items (ditunda)
- Migrasi router tenant yang tersisa (dashboard, documents, contracts, certifications, approvals, policies, reminders, audit_logs, settings_mail, dll) **ditunda** sampai PR #7 di-merge dan user memberi persetujuan tahap berikutnya.
- Seluruh Tahap SaaS lainnya (subscription/trial/platform_console/platform_owner + domain) **ditunda** sampai Tahap 1 diterima user.
- Dokumen audit `/app/AUDIT_SAAS_READINESS.md` belum di-commit; bila ingin dimasukkan ke repo, buat PR dokumentasi terpisah (1 PR = 1 tujuan).

---

# Log Pengembangan (Emergent)

## Phase: Pull Request ke GitHub (Status: COMPLETED)
- Branch `feature/stage1-module-foundations-demo-login` di-push ke origin (commit 17428a8, 22 file).
- PR #8 dibuat ke `main`: https://github.com/akuntakitatech-design/Payroll/pull/8 (melanjutkan PR #7).
- Tidak ada `.env` / `memory/test_credentials.md` yang ikut commit. Token GitHub dipakai sekali, tidak disimpan.
- Pemilih akun demo di login diverifikasi via esbuild + screenshot preview (klik akun mengisi email & kata sandi).
- Belum dijawab user: apakah MariaDB/R2 remote adalah staging/demo atau production (catatan ada di deskripsi PR).

## Phase: Rekrutmen V1 — Tahap A (Status: COMPLETED, menunggu review user di preview)
Lingkungan: APP_ENV=development; MariaDB DEVELOPMENT remote `default` + R2 DEVELOPMENT bucket `media-akunkita` — dikonfirmasi user. Scheduler off, AUTO_SEED off.
Dibangun: tabel `candidates`, `candidate_status_history`; router `/api/recruitment` (catalog, summary, candidates CRUD, status, screening, history);
state machine `app/core/recruitment_workflow.py` (draft -> screening -> screening_passed|screening_failed, fail-closed);
UI: /modules/recruitment (dashboard), /modules/recruitment/candidates (daftar+form), /modules/recruitment/candidates/:id (tab Profil/Lamaran/Screening/Dokumen/Riwayat).
Dokumen kandidat reuse modul Documents (owner_type=applicant). Audit: create/update/status_change/screening/delete resource `candidate` module `recruitment`.
Delete policy: soft-delete hanya untuk draft & screening_failed; screening/screening_passed -> 409.
Test: iteration_8 backend 31/32 (1 salah endpoint harness), tenant isolation & RBAC lulus; frontend flow lulus, temuan "loading" = latensi DB remote (login 10-24 dtk saat uji). Query rekrutmen dioptimalkan dengan asyncio.gather.
Data contoh DEVELOPMENT (NEP): 6 kandidat. Modul recruitment diaktifkan untuk KBS (dev) untuk uji isolasi.
TIDAK: commit/push/PR/merge/deploy. Belum: interview, approval, offering, konversi karyawan, import Excel (Tahap B+).


## Phase: Rekrutmen V1 — Tahap B: Interview, Approval, Offering (Status: COMPLETED — menunggu review user di preview)
Lingkungan sama dengan Tahap A (APP_ENV=development, MariaDB DEVELOPMENT `default`, R2 `media-akunkita`, scheduler off). Diverifikasi ulang via /api/system/mode.
Backend (sudah ada, ditinjau ulang + 1 bug diperbaiki):
- Tabel `candidate_interviews`, `candidate_approvals`, `candidate_offerings`; kolom `candidates.approval_round`. Unique aktif: (company, candidate, active_flag) => satu offering aktif.
- Router `app/routers/recruitment_pipeline.py`: interviewers, interviews (list/create/update/complete/cancel/delete), approvals (get/submit/decide), offerings (list/create/update/send/respond/cancel), pipeline agregat.
- Approval memakai `approval_workflows`/`approval_steps` existing (document_kind=recruitment); snapshot langkah saat submit; sequential; approver harus match role/user/position + permission recruitment:approve; tanpa workflow => 422 fail-closed.
- BUG DIPERBAIKI: `create_offering` tidak menyimpan `candidate_id` (offering hilang dari kandidat, unique aktif tidak berlaku). Data orphan dibersihkan.
- Keputusan: role `manager` default tidak punya `recruitment:approve` -> jika dikonfigurasi sebagai approver akan 403 (fail closed). Workflow dev NEP `WF-REKRUT` diubah ke 2 tahap (HR Manager -> Direksi) via API Alur Persetujuan existing.
Frontend:
- Baru: `components/recruitment/OfferingTab.jsx`; integrasi InterviewTab/ApprovalTab/OfferingTab ke `CandidateDetailPage` (tab: Profil | Lamaran | Screening | Interview | Approval | Offering | Dokumen | Riwayat) via GET .../pipeline; dashboard baris KPI Tahap B (Interview Dijadwalkan, Menunggu Approval, Approved, Offering Aktif, Offering Diterima).
Test: `tests/smoke_recruitment_b.py` 79/79 PASS; testing agent iteration_9 backend 12/12, frontend lulus (1 catatan LOW: locator Batal generik -> ditambah data-testid) (validasi, urutan, RBAC approver, konkurensi, tenant isolation 404, versi offering, cancel->approved). Data SMOKE-B dibersihkan (`tests/_cleanup_recruitment_test_data.py`).
Data preview (NEP, `tests/seed_preview_recruitment_b.py`): Bagus (offering diterima), Andini (interview berjalan), Dimas (menunggu Direksi), Raka (ditolak), Maya (offering v1 ditolak, v2 draft).
Backlog Tahap B: resubmit approval setelah rejected; approver_type=supervisor; Tahap C (konversi karyawan).
TIDAK: commit/push/PR/merge/deploy; Payroll/BPJS/PPh21/Auth tidak disentuh.
