# Blueprint Modul Rekrutmen V1 — HRIS & Payroll Suite

Status: BLUEPRINT (belum ada perubahan source code). Menunggu persetujuan user.
Aturan: tanpa PR/push/merge/deploy, tanpa sentuh DB produksi, hanya DB development lokal.

## 0. Prasyarat sebelum coding
- `/app/backend/.env` saat ini `DATABASE_URL` menunjuk host REMOTE (bukan loopback), `READ_ONLY=false`.
  Wajib dikembalikan ke MariaDB dev lokal (`payroll-dev-mariadb` supervisor RUNNING) sebelum implementasi.
  Tabel baru akan dibuat otomatis oleh `ensure_indexes()` saat boot -> hanya boleh terjadi di DB dev.

## 1. Hasil audit struktur Recruitment existing
Yang SUDAH ada (hanya fondasi):
- RBAC: `app/core/rbac.py:51` resource `recruitment` actions [view, create, edit, delete, approve, export]; modul `recruitment` status `planned` (rbac.py:68); default matrix: hr_admin CRUD (:123), hr_manager approve (:138).
- Aktivasi modul per company: tabel `company_modules` + gate `require_permission(resource, action, module_key)` (`app/core/deps.py:238-256`) -> fail-closed bila modul belum aktif.
- Approval: `app/routers/approvals.py:14` DOCUMENT_KINDS sudah punya `recruitment`.
- Dokumen: `app/routers/documents.py:18-30` OWNER_TYPES sudah punya `applicant`; index `ix_documents_owner (company_id, owner_type, owner_id)`.
- Frontend: nav `src/lib/nav.js:125` (`/modules/recruitment`, label "Rekrutmen", resource recruitment, module recruitment); route catch-all `/modules/:moduleKey` -> `ModulePlaceholderPage` (`App.js:103`); metadata `moduleFoundation.js:3-13`.
Yang BELUM ada: tabel, router, endpoint, halaman operasional. Tidak ada engine approval-request runtime (lihat §3).

## 2. Komponen existing yang DIREUSE (tanpa modifikasi logic)
| Kebutuhan | Reuse | Cara pakai |
|---|---|---|
| Tenant isolation | `get_tenant_db`, `TenantRepository`, `AuthContext.company_id` | company_id hanya dari JWT; tabel baru otomatis tenant (fail-closed `is_tenant_collection`) |
| RBAC | `require_permission("recruitment", action, "recruitment")` | tanpa ubah matrix; lihat §7 |
| Audit | `log_action(ctx, action, resource, ...)` (`app/core/audit.py:27`) | resource baru `candidate`, `candidate_interview`, `candidate_offering` -> perlu mapping module di `resource_module` (lewat RESOURCES) |
| Dokumen kandidat | `POST /documents` dengan `owner_type="applicant"`, `owner_id=candidate_id` | tab Dokumen kandidat = DocumentsPage komponen dengan filter owner; tanpa tabel dokumen baru |
| Master data | departments, positions, work_locations, projects, employment_statuses | FK di kandidat/offering; validasi via pola `_validate_refs` |
| Interviewer | `users` + `user_company_roles` per company | dropdown user aktif perusahaan; simpan `interviewer_user_id` (+ snapshot nama) |
| Approval config | `approval_workflows` + `approval_steps` (document_kind=`recruitment`) | dipakai untuk MENENTUKAN urutan approver; instance/aksi disimpan di tabel baru (§3) |
| Employee creation | `TenantRepository("employees").create`, `_next_employee_number`, `_validate_refs`, `ensure_unique(nik)` dari `app/routers/employees.py` | dipanggil in-process saat "Jadikan Karyawan"; tidak ada tabel karyawan alternatif |
| Excel | pola `app/core/excel.py` + `EmployeeImportPage.jsx` (template -> validate -> commit) | fungsi baru khusus kandidat di excel.py (tidak ubah fungsi employee) |
| UI | `DataTable`, `Pagination`, `FormDialog`, `ConfirmDialog`, `StatusBadge`, shadcn Tabs, `api`, `can()`/`hasModule()` | konsisten dengan EmployeesPage/EmployeeDetailPage |

## 3. Keputusan arsitektur: approval
Temuan: modul Approval existing HANYA menyimpan definisi workflow (`approval_workflows`, `approval_steps`).
Tidak ada tabel `approval_requests/actions`, tidak ada endpoint submit/approve/reject, tidak ada helper in-process.
Modul lain (kontrak: `approval_state`; payroll_runs: submitted/approved_at) menyimpan state sendiri.
Keputusan V1: TIDAK membuat approval engine generik kedua. Rekrutmen:
- Membaca `approval_workflows` (document_kind=`recruitment`, is_default/scope company) + `approval_steps` untuk membangun daftar langkah.
- Menyimpan instance langkah di tabel baru `candidate_approvals` (satu baris per step per kandidat), mengikuti pola state modul kontrak.
- Bila perusahaan belum punya workflow `recruitment`: fallback 1 langkah "HR Approval" (role hr_manager) — fleksibel per perusahaan tanpa hardcode.
Ini konsisten dengan arsitektur existing dan dapat dimigrasikan ke engine generik bila kelak dibangun.

## 4. Tabel baru (semua TENANT_COLLECTIONS, id UUID string36 + COMMON: company_id, status, created_at/by, updated_at/by, extra JSON)
1. `candidates`
   identitas: full_name, nik(s32), birth_place, birth_date(d), gender, phone, email, address, city
   lamaran: candidate_number (auto, unik per company), position_id(fk), department_id(fk), work_location_id(fk), project_id(fk), applied_position_title(snapshot), source(s32: manual|excel_import|referral|job_portal|other), source_detail, applied_at(d), expected_salary(dec), available_from(d)
   pendidikan: education_level, education_major, education_institution, graduation_year(i)
   pengalaman: last_employer, last_position, experience_years(dec)
   pipeline: stage_status (lihat §6), stage_changed_at, rejection_reason
   screening: screening_result(pass|fail|hold), screening_score(i), screening_notes, screening_recommendation, screened_by(fk user), screened_at
   konversi: employee_id(fk, NULL) UNIQUE bila terisi, converted_at, converted_by(fk user)
   flags: is_demo_data(b)
   index: (company_id, stage_status), (company_id, position_id), (company_id, nik), (company_id, email), unique (company_id, candidate_number), unique (company_id, employee_id)
2. `candidate_status_history`
   candidate_id(fk), from_status, to_status, reason/notes, changed_by(fk user), changed_at
3. `candidate_interviews`
   candidate_id(fk), interview_type(s32: hr|user|manager|final|other), sequence(i), scheduled_date(d), scheduled_time(s8), interviewer_user_id(fk), interviewer_name(snapshot), mode(s16: onsite|online), location_or_link, interviewer_notes, score(i), recommendation(s16: hire|consider|reject), result(s16: scheduled|done|cancelled|no_show), completed_at
4. `candidate_approvals`
   candidate_id(fk), workflow_id(fk nullable), step_order(i), step_name, approver_type(role|user|position), approver_role_key, approver_user_id, approver_position_id, decision(pending|approved|rejected), decided_by(fk user), decided_at, notes; unique (candidate_id, step_order)
5. `candidate_offerings`
   candidate_id(fk) (1 aktif per kandidat), offering_number, position_id, department_id, work_location_id, project_id, employment_status_id(fk), start_date(d), basic_salary(dec), allowances(JSON [{name, amount}]), probation_months(i), notes, offer_status(draft|sent|accepted|declined|expired), sent_at, responded_at, response_notes, created/approved by
   Catatan: TIDAK menyentuh payroll_components/employee_salaries; data offering hanya disalin ke `employee_salaries` bila HR memilih saat konversi (opsional, pakai repo existing seperti import commit employees.py:600-630).
Tidak ada tabel dokumen baru (reuse `documents`). Tidak ada tabel karyawan baru.

## 5. Endpoint/API baru — router `app/routers/recruitment.py`, prefix `/api/recruitment`
Dashboard & kandidat
- GET  /recruitment/summary                         (recruitment:view) ringkasan per status
- GET  /recruitment/candidates                      (view) filter: q, stage_status, position_id, department_id, source, date_from/to, page/size
- POST /recruitment/candidates                      (create)
- GET  /recruitment/candidates/{id}                 (view) + expand: interviews, approvals, offering, history, documents(count)
- PUT  /recruitment/candidates/{id}                 (edit)
- DELETE /recruitment/candidates/{id}               (delete) soft-delete, hanya status Draft/Ditolak
- POST /recruitment/candidates/{id}/status          (edit) transisi manual terbatas + alasan -> history + audit
Screening
- POST /recruitment/candidates/{id}/screening       (edit) hasil, skor, catatan, rekomendasi, keputusan -> Lolos/Tidak Lolos
Interview
- GET  /recruitment/candidates/{id}/interviews      (view)
- POST /recruitment/candidates/{id}/interviews      (edit) jadwal -> status Interview Dijadwalkan
- PUT  /recruitment/interviews/{iid}                (edit) hasil/skor/rekomendasi -> jika semua done: Interview Selesai
- DELETE /recruitment/interviews/{iid}              (edit) batalkan
- GET  /recruitment/interviewers                    (view) users aktif perusahaan
Approval
- POST /recruitment/candidates/{id}/submit-approval (edit) buat langkah dari approval_workflows -> Menunggu Approval
- POST /recruitment/candidates/{id}/approvals/{step}/decide (approve) cek approver cocok (role/user/position) -> Disetujui/Ditolak
Offering
- POST /recruitment/candidates/{id}/offering        (create) -> Offering
- PUT  /recruitment/offerings/{oid}                 (edit)
- POST /recruitment/offerings/{oid}/respond         (edit) accepted|declined -> Offering Diterima (=Siap Onboarding) / Offering Ditolak
Konversi
- POST /recruitment/candidates/{id}/convert         (recruitment:create + employee:create) -> Menjadi Karyawan
- GET  /recruitment/candidates/{id}/convert-preview (view) menampilkan mapping data yang akan dibuat
Import Excel
- GET  /recruitment/import/template, GET /import/columns, POST /import/validate, POST /import/commit (create)
Dokumen: reuse `GET/POST /documents?owner_type=applicant&owner_id={id}` (tanpa endpoint baru)
Ekspor: GET /recruitment/candidates/export (export) — opsional V1

## 6. Status kandidat (state machine V1) — key internal | label
draft | Draft
screening | Screening
screening_passed | Lolos Screening
screening_failed | Tidak Lolos            (terminal)
interview_scheduled | Interview Dijadwalkan
interview_done | Interview Selesai
awaiting_approval | Menunggu Approval
approved | Disetujui
rejected | Ditolak                         (terminal; dari approval/aksi HR)
offering | Offering
offering_accepted | Offering Diterima (= Siap Onboarding)
offering_declined | Offering Ditolak       (terminal; bisa dibuka kembali ke `approved` oleh HR)
hired | Menjadi Karyawan                   (terminal; terkunci)
Penyederhanaan: "Siap Onboarding" digabung ke `offering_accepted` (menghindari langkah kosong).
Transisi diizinkan (server-side enforce):
draft->screening; screening->screening_passed|screening_failed; screening_passed->interview_scheduled;
interview_scheduled->interview_done|interview_scheduled(tambah interview); interview_done->awaiting_approval|interview_scheduled;
awaiting_approval->approved|rejected; approved->offering; offering->offering_accepted|offering_declined;
offering_declined->approved (reopen); offering_accepted->hired (hanya via /convert).
Semua transisi dicatat ke `candidate_status_history` + audit_logs.

## 7. Permission
Struktur existing = `resource:action`, action tetap dari ACTIONS (view, create, edit, delete, approve, export, config, view_own).
Permintaan user (recruitment.screening/interview/offering/convert_employee) dipetakan ke action existing agar TIDAK mengubah matrix/ACTIONS:
- recruitment:view    -> dashboard, daftar, detail, interviewers, convert-preview
- recruitment:create  -> tambah kandidat, import commit, buat offering
- recruitment:edit    -> ubah kandidat, screening, interview, submit approval, respond offering, status manual
- recruitment:delete  -> hapus draft/ditolak
- recruitment:approve -> decide approval step (ditambah cek approver cocok)
- recruitment:export  -> template/ekspor
- convert -> recruitment:create DAN employee:create (dua-duanya wajib; memakai permission employee existing, tidak ada permission baru)
Tidak ada perubahan RESOURCES/ACTIONS/default_role_permissions di V1. Bila user ingin granular (mis. screening terpisah), tambahan action di rbac.py bisa dipertimbangkan di V1.1 setelah matrix existing dinilai.
Audit mapping: resource baru `candidate`, `candidate_interview`, `candidate_offering` -> agar `resource_module()` mengembalikan `recruitment`, perlu satu entri kecil di RESOURCES atau pass `module="recruitment"` eksplisit ke `log_action` (dipilih: pass eksplisit -> zero perubahan rbac.py).

## 8. Rancangan UI (Bahasa Indonesia, Plus Jakarta Sans, token existing)
Route existing `/modules/recruitment` diganti isinya (bukan menu baru): nav.js tidak berubah; App.js menambah route spesifik SEBELUM catch-all:
- `/modules/recruitment`            RecruitmentDashboardPage — 6 kartu ringkasan (Kandidat aktif, Screening, Interview, Menunggu Approval, Offering, Diterima) dari /summary; kandidat terbaru; interview mendatang. Empty state bila 0 (tanpa dummy).
- `/modules/recruitment/candidates` CandidatesPage — DataTable, search, filter posisi/departemen/status/sumber/periode, pagination, tombol Tambah (FormDialog) & Import.
- `/modules/recruitment/candidates/:id` CandidateDetailPage — header (nama, nomor, StatusBadge, aksi kontekstual sesuai status & permission); Tabs: Profil | Lamaran | Screening | Interview | Approval | Offering | Dokumen (reuse komponen dokumen owner applicant) | Riwayat (timeline history + audit).
  Aksi kontekstual: Mulai Screening, Simpan Screening, Jadwalkan Interview, Ajukan Approval, Setujui/Tolak (jika approver), Buat Offering, Catat Respons, "Jadikan Karyawan" (hanya offering_accepted & belum hired; ConfirmDialog dengan preview mapping).
- `/modules/recruitment/import`     CandidateImportPage — stepper 4 langkah: Unduh template -> Pilih file -> Preview & validasi (tabel baris valid/error) -> Commit (hanya jika error=0). File dibaca client/validate endpoint dry-run; tidak menulis DB sebelum commit.
Semua elemen penting ber-`data-testid` (`recruitment-*`, `candidate-*`).

## 9. Mekanisme "Jadikan Karyawan" (POST /convert)
1. Guard: kandidat milik ctx.company_id (TenantRepository), stage `offering_accepted`, `employee_id IS NULL`, offering aktif berstatus accepted, permission recruitment:create + employee:create, modul employee_core aktif.
2. Idempotensi: UPDATE bersyarat `SET stage_status='hired', employee_id=? WHERE id=? AND employee_id IS NULL AND stage_status='offering_accepted'` -> rowcount 0 = sudah dikonversi -> 409. Plus unique index (company_id, employee_id).
3. Mapping kandidat+offering -> EmployeeCreate: full_name, nik, birth_place/date, gender, email, phone, address, city, education, job_title (posisi offering), position_id, department_id, work_location_id, project_id, employment_status_id, join_date=start_date, notes ("Dikonversi dari kandidat {candidate_number}").
4. Reuse helper employees.py: `_validate_refs`, `ensure_unique("nik")` (jika NIK sudah ada -> 409 dengan pesan, tidak membuat duplikat), `_next_employee_number`, `TenantRepository("employees").create`.
5. Opsional (checkbox di ConfirmDialog): salin basic_salary/allowances offering ke `employee_salaries` memakai pola import commit existing (tanpa ubah engine payroll).
6. Set candidate.converted_at/by; history `offering_accepted -> hired`; `log_action(ctx,"convert","candidate", ..., after={employee_id}, module="recruitment")` + `log_action(ctx,"create","employee", ...)`.
7. Response: {candidate, employee_id, employee_number}; UI menampilkan tautan ke `/employees/{id}`. Setelah hired, kandidat read-only.
Tidak ada tabel karyawan alternatif; dokumen kandidat tetap owner_type=applicant (opsi V1.1: re-link ke employee).

## 10. Risiko & mitigasi
| Risiko | Mitigasi |
|---|---|
| Kebocoran lintas tenant | Semua tabel di TENANT_COLLECTIONS; hanya TenantRepository/get_tenant_db; tak ada param company_id di body/query; test iterasi RBAC/tenant diperluas (A tidak lihat B) |
| Schema sync membuat tabel di DB yang salah | Pastikan DATABASE_URL loopback dev sebelum restart backend; `ensure_indexes` additive saja |
| Konversi ganda | UPDATE bersyarat + unique (company_id, employee_id) + 409 |
| Duplikasi karyawan (NIK sama) | ensure_unique nik -> 409, HR diarahkan cek Data Karyawan |
| Menyentuh modul existing | employees.py/documents.py/approvals.py/payroll tidak diubah; hanya import helper. Perubahan minimal: App.js (route), rbac MODULES status planned->available (agar modul bisa diaktifkan), server.py include_router |
| Approver bypass | decide step memvalidasi approver_type vs ctx (role_key di company, user_id, position) selain recruitment:approve |
| Import massal salah | validate dry-run wajib; commit hanya baris valid yang dikirim ulang; audit agregat |
| Data dummy | tidak ada seed kandidat; dashboard empty state |

## 11. Daftar file
BARU (backend): app/routers/recruitment.py; app/core/recruitment_workflow.py (state machine + transisi); app/core/excel.py: fungsi kandidat baru (build_candidate_template, parse/validate_candidate_rows) — tambahan fungsi, bukan ubah fungsi employee; backend/test_stage4_recruitment.py
UBAH (backend, minimal): app/core/db.py (+5 entri TENANT_COLLECTIONS, TABLE_SPECS, INDEX_SPECS); app/schemas.py (+ schema Candidate*, Interview*, Offering*, Screening*, Convert*); server.py (include_router); app/core/rbac.py (MODULES recruitment status planned->available saja — bila diperlukan agar aktivasi modul di UI diizinkan; cek ModuleActivationPage)
BARU (frontend): src/pages/recruitment/RecruitmentDashboardPage.jsx, CandidatesPage.jsx, CandidateDetailPage.jsx, CandidateImportPage.jsx; src/lib/recruitment.js (status label/warna/transisi UI)
UBAH (frontend, minimal): src/App.js (4 route sebelum catch-all); src/lib/nav.js (tidak wajib; opsional sub-item "Kandidat" & "Import" di bawah Rekrutmen); src/lib/moduleFoundation.js (opsional: tandai recruitment sudah operasional)
TIDAK DIUBAH: employees.py, documents.py, approvals.py, payroll*, bpjs, pph21, contracts, certifications, auth, deps.py, tenancy.py, default_role_permissions.

## 12. Urutan implementasi (setelah persetujuan)
0. Kembalikan runtime ke MariaDB dev lokal; verifikasi `system-mode`.
1. Backend: db.py specs + schemas + state machine + router kandidat/screening/history + tests tenant.
2. Backend: interview, approval (baca workflow), offering, convert.
3. Backend: import Excel kandidat.
4. Frontend: Dashboard + Daftar + Detail (tab bertahap) + Import.
5. Testing agent (backend + frontend) di DB dev; laporan ke user; STOP menunggu instruksi GitHub.

---
## Status implementasi Tahap A (selesai, belum di-commit)
File baru: backend/app/routers/recruitment.py, backend/app/core/recruitment_workflow.py, frontend/src/lib/recruitment.js,
frontend/src/components/recruitment/{StageBadge,CandidateFormDialog,ScreeningDialog}.jsx,
frontend/src/pages/recruitment/{RecruitmentDashboardPage,CandidatesPage,CandidateDetailPage}.jsx
File diubah: backend/app/core/db.py (+2 tabel), backend/app/schemas.py (+Candidate*), backend/server.py (include_router),
backend/app/routers/audit_logs.py (+2 label aksi), frontend/src/App.js (+3 route sebelum catch-all)
