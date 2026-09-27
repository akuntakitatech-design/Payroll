# UPGRADE 01F — Data Completeness: Audit & Preflight (TAHAP 1)

- Status: **AUDIT SELESAI, BELUM ADA CODING 01F**. Menunggu review user.
- Lingkungan: staging (`hris_staging` @ 127.0.0.1, `AUTO_SEED=false`, `READ_ONLY=false`). Audit dilakukan read-only.
- Tidak ada perubahan business behavior, schema, migration, atau data. Tidak ada push/PR/merge/deploy. 01G tidak dimulai.
- Production Changed: **NO**

> Catatan lingkungan: saat audit dimulai, service `payroll-dev-mariadb` berstatus FATAL setelah container restart (binary MariaDB belum siap saat boot). Service dinyalakan lagi lewat supervisor (`supervisorctl start`), lalu backend di-restart. Data utuh: 65 tabel, ledger `schema_migrations` = m0003–m0006. Tidak ada data yang diubah.

> Catatan scope: pekerjaan 01E-B yang masih terbuka tetap tercatat di plan.md. Audit 01F ini dimulai atas instruksi user.

---

## 1. Fakta arsitektur penting

| Fakta | Dampak untuk 01F |
|---|---|
| Semua kolom DB **nullable** (layer kompatibilitas mongo-like di `core/db.py`). "Wajib" hanya ditegakkan di Pydantic (`schemas.py`) atau validator router. | Kelengkapan tidak bisa dibaca dari DDL. Kelengkapan harus diukur dengan rule. |
| Field profil karyawan ada di **kolom nyata** tabel `employees`, bukan di `extra` JSON. | Mudah dievaluasi secara bulk dengan satu query. |
| Data sensitif: `nik, bank_account_number, npwp, bpjs_kesehatan_number, bpjs_tk_number` (`core/sensitive.py:12`). Nilai penuh hanya terlihat dengan `employee:edit`. Audit selalu memakai nilai yang dimasking. | Hasil completeness **hanya boleh menyimpan status/kode**, tidak pernah nilai. |
| Validator format NIK (16 digit), NPWP (15/16 digit), BPJS (8–20 digit), dan rekening (5–30 digit) **hanya ada di mapping impor 01E** (`core/employee_import_mapping.py:178-181`) dan NIK keluarga (`routers/employee_profile.py:65-67`). `EmployeeCreate/Update` (`schemas.py:181-261`) **tidak** memvalidasi format NIK/NPWP/BPJS/birth_date. | 01F harus membedakan status **MISSING** dan **INVALID**. Validator dipusatkan agar dipakai bersama, tanpa mengubah perilaku simpan saat ini. |
| Flag master `document_types.is_mandatory/has_expiry`, `certification_types.is_mandatory/validity_months`, dan `employment_statuses.requires_contract` **sudah ada dan terisi**, tetapi **tidak pernah ditegakkan** di logic mana pun (hanya metadata di UI master). | Flag ini bisa langsung dipakai sebagai sumber rule. Tidak perlu master baru. |
| Resolver konfigurasi bertingkat sudah ada: `core/policy.resolve_config` + tabel `config_overrides`. Scope: company, branch, division, project, employee. Mendukung `effective_from/to`. | Bisa dipakai untuk parameter numerik atau boolean (misalnya ambang skor), tetapi **tidak** punya scope position atau employment_status. |
| Scheduler APScheduler sudah berjalan (`core/scheduler.py:241-288`, cron reminder per company). | Bisa dipakai untuk evaluasi ulang berkala. Ini perlu karena kedaluwarsa dokumen, kontrak, dan sertifikasi berubah seiring waktu. |
| Belum ada fitur kelengkapan profil karyawan. Hasil grep "kelengkapan" hanya ditemukan pada setup payroll dan checklist master perusahaan. | 01F adalah fitur baru, tanpa risiko bentrok dengan logic lama. |

---

## 2. Inventaris field Employee Profile 360

Legenda. **Wajib-Skema**: required di Pydantic. **Sens**: sensitif/dimasking. **Rep**: repeatable. **Master**: punya master/reference. **Reuse**: siap dipakai untuk completeness (Y = langsung, V = perlu validator terpusat, R = perlu rule applicability).

### 2.1 Data Pribadi — tabel `employees`
| Field | Kolom | Wajib-Skema | Validator existing | Sens | Master | Reuse |
|---|---|---|---|---|---|---|
| Nama lengkap | `full_name` | Ya (min 2) | panjang | – | – | Y |
| NIK KTP | `nik` | Tidak | unik per tenant (01C); format **tidak** divalidasi di skema karyawan | **Ya** | – | V |
| Jenis kelamin | `gender` | Tidak | enum hanya di sisi klien | – | katalog | Y |
| Tempat lahir | `birth_place` | Tidak | – | – | – | Y |
| Tanggal lahir | `birth_date` (str) | Tidak | **tidak ada** validator format di skema karyawan | – | – | V |
| Status pernikahan | `marital_status` | Tidak | enum di klien / impor | – | katalog | Y (juga menjadi pemicu rule Keluarga) |
| Agama | `religion` | Tidak | enum di klien | – | katalog | Y |
| Pendidikan | `education` | Tidak | enum di klien | – | katalog | Y |
| No. HP | `phone` | Tidak | – | – | – | V |
| Email | `email` | Tidak | EmailStr | – | – | Y |
| Alamat KTP | `address` | Tidak | – | – | – | Y |
| Alamat domisili | `domicile_address` | Tidak | – | – | – | Y |
| Kota / Provinsi / Kode pos | `city`, `province`, `postal_code` | Tidak | – | – | – | Y |
| Kontak darurat | `emergency_contact_name/phone` **atau** anggota keluarga dengan `is_emergency_contact=1` | Tidak | – | – | – | R (salah satu dari dua sumber) |
| Foto profil | `photo_path` | Tidak | tipe/ukuran (01C) | – | – | Y |

### 2.2 Kepegawaian — `employees` + 01B
| Field | Sumber | Validator | Master | Reuse |
|---|---|---|---|---|
| Nomor karyawan | `employee_number` | unik | – | Y |
| Tanggal bergabung | `join_date` | – | – | V (format tanggal) |
| Status kepegawaian | `employment_status_id` | FK valid | `employment_statuses` (`is_permanent`, `requires_contract`) | Y |
| Status karyawan bisnis (01B) | `current_employee_status_id` + `employee_status_history` | via layanan 01B | `employee_business_statuses` (`system_category` ACTIVE/STANDBY/INACTIVE) | Y (juga menjadi dasar applicability) |
| Jabatan | `position_id` / `job_title` (teks) | FK valid | `positions` | Y |
| Grade/Level | `job_grade_id` | FK valid | `job_grades` (level, min/max salary) | Y |
| Departemen / Divisi | `department_id`, `division_id` | FK valid (`master._validate_relations`) | `departments`, `divisions` | Y |
| Cost center / Cabang | `cost_center_id`, `branch_id` | FK valid | `cost_centers`, `branches` | Y |

### 2.3 Penempatan — 01D
| Field | Sumber | Catatan | Reuse |
|---|---|---|---|
| Penempatan aktif | `employee_assignments` (`assignment_status=ACTIVE`, maksimal 1) | `core/assignment.py:68 active_assignment` | Y |
| Proyek | `employee_assignments.project_id` (bridge `employees.project_id`) | Setelah assignment diakhiri, nilainya **boleh NULL** (Standby) | R (wajib hanya untuk kategori ACTIVE, bukan STANDBY) |
| Lokasi kerja / site | `work_location_id` | FK valid | Y |
| Tanggal mulai | `employee_assignments.start_date` | Baris `LEGACY_BASELINE` boleh bertanggal NULL (01D, tidak dikarang) | R (jangan dihitung sebagai kekurangan untuk baris LEGACY_BASELINE) |

### 2.4 Bank & Pajak
| Field | Sumber | Sens | Validator | Reuse |
|---|---|---|---|---|
| Nama bank | `employees.bank_name` | – | – | Y |
| No. rekening | `employees.bank_account_number` | **Ya** | tidak ada di skema (hanya digit di impor) | V |
| Nama pemilik rekening | `employees.bank_account_name` | – | – | Y |
| NPWP | `employees.npwp` | **Ya** | 15/16 digit hanya di impor | V + R (wajib bila `employee_salaries.has_npwp=1`) |
| Status PTKP | `employee_salaries.ptkp_status` (default `TK/0`) | – | enum payroll | R (lihat Gap G3) |
| Punya NPWP | `employee_salaries.has_npwp` | – | bool | sumber applicability |

### 2.5 BPJS
| Field | Sumber | Sens | Reuse |
|---|---|---|---|
| No. BPJS Kesehatan | `employees.bpjs_kesehatan_number` | **Ya** | V + R (wajib bila `employee_salaries.bpjs_kesehatan_enrolled=1`) |
| No. BPJS Ketenagakerjaan | `employees.bpjs_tk_number` | **Ya** | V + R (wajib bila `bpjs_jht_enrolled` atau `bpjs_jp_enrolled`) |

### 2.6 Keluarga — `employee_family_members` (repeatable)
Field: `relationship` (enum), `full_name`, `nik` (16 digit, **sensitif**), `birth_place`, `birth_date` (ISO, tidak boleh di masa depan), `gender`, `occupation`, `is_emergency_contact`, `phone`. Validator lengkap ada di `FamilyInput` (`employee_profile.py:33-88`).
Reuse: **R**. Pasangan wajib bila `marital_status=married`. Konsistensi jumlah anak dengan PTKP `K/n` / `TK/n` cukup sebagai **warning**, bukan wajib.

### 2.7 Dokumen — `documents` (repeatable, `owner_type='employee'`, `owner_id=employee.id`)
- Upload `routers/documents.py:101`, update `:295`, delete `:312` (**soft delete**: `is_deleted=1`, `status=archived`). Ada kolom `version`, tetapi tidak ada riwayat versi.
- Master `document_types`: `category`, `owner_scope`, `is_mandatory`, `has_expiry`, `reminder_days`, `allowed_extensions`, `max_size_mb`.
- Data staging: NEP → KTP (mandatory), IJAZAH (mandatory), MCU (expiry, opsional); KONTRAK (`owner_scope=contract`, mandatory); SERTIF (`owner_scope=certification`). KBS → KTP, KONTRAK, SERTIF.
- Reuse: **Y**. Setiap `document_types` dengan `owner_scope='employee' AND is_mandatory=1` menjadi satu requirement. Jika `has_expiry=1`, dokumen yang kedaluwarsa dihitung **EXPIRED**.

### 2.8 Kontrak — `employee_contracts` (repeatable)
- Endpoint: create `contracts.py:117`, update `:153`, approve `:177`, status `:201`, delete `:227`, renew `:343`. Status kedaluwarsa dihitung oleh `core/expiry.expiry_state` + `resolve_config("contract.expiry_reminder_days")`.
- Reuse: **R**. Kontrak aktif yang belum kedaluwarsa wajib ada bila `employment_statuses.requires_contract=1` (PKWT, Magang, Harian di NEP). Tidak wajib untuk PKWTT/Tetap.
- Dokumen kontrak (`document_types` `owner_scope=contract`, mandatory) → requirement turunan opsional: kontrak aktif punya file.

### 2.9 Sertifikasi — `employee_certifications` (repeatable)
- Endpoint: create `certifications.py:111`, update `:136`, status `:161`, delete `:187`.
- Master `certification_types`: `is_mandatory` (NEP: SIO-CRANE, K3-UMUM; KBS: SKA), `validity_months`, `reminder_days`.
- Reuse: **R**. Flag `is_mandatory` berlaku untuk seluruh tenant, padahal SIO-Crane jelas hanya relevan untuk jabatan/proyek tertentu. **Butuh rule applicability** (lihat Gap G1).

### 2.10 Di luar 9 tab, tetapi relevan
- Gaji & Payroll: `employee_salaries` (`basic_salary`, `ptkp_status`, `has_npwp`, `bpjs_*_enrolled`, `effective_date`). Endpoint `PUT /payroll/salaries/{employee_id}` (`payroll.py:328`). Bersifat sensitif payroll (diatur permission payroll). 01F cukup **membaca flag applicability**, tidak menilai nominal gaji.

---

## 3. Master yang bisa direuse (tanpa master baru)

| Master | Tabel / router | Tenant-scoped | Flag yang dipakai 01F |
|---|---|---|---|
| Employment status/type | `employment_statuses` (generic master `masters.py`) | Ya | `requires_contract`, `is_permanent` |
| Grade/Level | `job_grades` | Ya | scope applicability (opsional) |
| Project | `projects` | Ya | scope applicability + scope `config_overrides` |
| Work location/site | `work_locations` | Ya | scope applicability |
| Department / Division | `departments`, `divisions` | Ya | scope applicability (division juga scope `config_overrides`) |
| Branch | `branches` | Ya | scope `config_overrides` |
| Position | `positions` | Ya | scope applicability (utama untuk sertifikasi) |
| Status karyawan 01B | `employee_business_statuses` (router khusus `employee_status.py`) | Ya | `system_category` untuk applicability (INACTIVE → dikecualikan, STANDBY → proyek tidak wajib) |
| Document type | `document_types` | Ya | `owner_scope`, `is_mandatory`, `has_expiry` |
| Certification master | `certification_types` | Ya | `is_mandatory`, `validity_months` |
| Contract type | `contract_types` | Ya | informasi saja |
| Konfigurasi bertingkat | `config_overrides` + `core/policy.resolve_config` | Ya | parameter (misalnya ambang "lengkap", grace days) |

**Kesimpulan: tidak perlu master baru** untuk jenis dokumen, jenis sertifikasi, status, grade, proyek, lokasi, departemen, atau divisi.

---

## 4. Kandidat mapping completeness terpusat

Satu modul: `backend/app/core/completeness_mapping.py`, dengan pola yang sama seperti `employee_import_mapping.py`. Isinya katalog requirement **sistem** (code, versioned). Requirement dinamis dibentuk dari master: dokumen dan sertifikasi. Logic tidak disebar ke router.

Format: `requirement_code → kategori → sumber → validator → sens → applicability default → level default`

| requirement_code | Kategori | Sumber | Validator | Sens | Applicability default | Level default |
|---|---|---|---|---|---|---|
| `PERSONAL.FULL_NAME` | Data Pribadi | employees.full_name | len≥2 | – | semua | REQUIRED |
| `PERSONAL.NIK` | Data Pribadi | employees.nik | `nik` (16 digit) | Ya | semua | REQUIRED |
| `PERSONAL.GENDER` | Data Pribadi | employees.gender | enum | – | semua | REQUIRED |
| `PERSONAL.BIRTH` | Data Pribadi | birth_place + birth_date | `date` (tidak di masa depan) | – | semua | REQUIRED |
| `PERSONAL.MARITAL` | Data Pribadi | marital_status | enum | – | semua | REQUIRED |
| `PERSONAL.RELIGION` | Data Pribadi | religion | enum | – | semua | RECOMMENDED |
| `PERSONAL.EDUCATION` | Data Pribadi | education | enum | – | semua | RECOMMENDED |
| `PERSONAL.PHONE` | Data Pribadi | phone | `phone` | – | semua | REQUIRED |
| `PERSONAL.EMAIL` | Data Pribadi | email | email | – | semua | RECOMMENDED |
| `PERSONAL.ADDRESS_KTP` | Data Pribadi | address (+city/province) | non-empty | – | semua | REQUIRED |
| `PERSONAL.DOMICILE` | Data Pribadi | domicile_address | non-empty | – | semua | RECOMMENDED |
| `PERSONAL.EMERGENCY_CONTACT` | Data Pribadi | emergency_contact_* **OR** family.is_emergency_contact | salah satu | – | semua | REQUIRED |
| `PERSONAL.PHOTO` | Data Pribadi | photo_path | – | – | semua | RECOMMENDED |
| `EMPLOYMENT.JOIN_DATE` | Kepegawaian | join_date | `date` | – | semua | REQUIRED |
| `EMPLOYMENT.STATUS_TYPE` | Kepegawaian | employment_status_id | FK aktif | – | semua | REQUIRED |
| `EMPLOYMENT.BUSINESS_STATUS` | Kepegawaian | current_employee_status_id | FK aktif (01B) | – | semua | REQUIRED |
| `EMPLOYMENT.POSITION` | Kepegawaian | position_id | FK | – | semua | REQUIRED |
| `EMPLOYMENT.GRADE` | Kepegawaian | job_grade_id | FK | – | semua | RECOMMENDED |
| `EMPLOYMENT.ORG_UNIT` | Kepegawaian | department_id (+division_id) | FK | – | semua | REQUIRED |
| `EMPLOYMENT.COST_CENTER` | Kepegawaian | cost_center_id | FK | – | semua | RECOMMENDED |
| `PLACEMENT.ACTIVE` | Penempatan | employee_assignments ACTIVE | ada 1 | – | kategori 01B = ACTIVE | REQUIRED |
| `PLACEMENT.WORK_LOCATION` | Penempatan | work_location_id | FK | – | kategori ACTIVE | REQUIRED |
| `BANK.ACCOUNT` | Bank & Pajak | bank_name + bank_account_number + bank_account_name | `bank_account` (5–30 digit, sama dengan 01E) | Ya | semua | REQUIRED |
| `TAX.NPWP` | Bank & Pajak | employees.npwp | `npwp` (15/16) | Ya | `employee_salaries.has_npwp=1` | REQUIRED |
| `TAX.PTKP` | Bank & Pajak | employee_salaries.ptkp_status | enum PTKP | – | punya baris salary | REQUIRED (lihat G3) |
| `BPJS.KESEHATAN` | BPJS | bpjs_kesehatan_number | `bpjs` | Ya | `bpjs_kesehatan_enrolled=1` | REQUIRED |
| `BPJS.TK` | BPJS | bpjs_tk_number | `bpjs` | Ya | `bpjs_jht_enrolled OR bpjs_jp_enrolled` | REQUIRED |
| `FAMILY.SPOUSE` | Keluarga | family relationship ∈ {SUAMI, ISTRI} | FamilyInput | Ya (NIK) | marital_status=married | REQUIRED |
| `FAMILY.PTKP_CONSISTENCY` | Keluarga | jumlah anak vs PTKP /n | – | – | punya PTKP | WARNING |
| `DOC.<document_type.code>` (dinamis) | Dokumen | documents owner_type=employee, is_deleted=0 | kedaluwarsa bila has_expiry | – | document_types.owner_scope=employee & is_mandatory=1 | REQUIRED |
| `CONTRACT.ACTIVE` | Kontrak | employee_contracts aktif & belum lewat end_date | expiry_state | – | employment_statuses.requires_contract=1 | REQUIRED |
| `CONTRACT.FILE` | Kontrak | documents owner_type=contract untuk kontrak aktif | – | – | ada CONTRACT.ACTIVE & doc type KONTRAK mandatory | RECOMMENDED |
| `CERT.<certification_type.code>` (dinamis) | Sertifikasi | employee_certifications | expiry (validity_months) | – | is_mandatory=1 **dan** cocok rule applicability (G1) | REQUIRED |

Status per item: `COMPLETE | MISSING | INVALID | EXPIRED | EXPIRING_SOON | NOT_APPLICABLE` (+ `WARNING`).
Karyawan dengan kategori 01B `INACTIVE` atau yang diarsipkan/dihapus **dikecualikan** dari evaluasi.

---

## 5. Gap

| # | Gap | Dampak | Usulan |
|---|---|---|---|
| G1 | `certification_types.is_mandatory` berlaku untuk seluruh tenant. Tidak ada relasi sertifikasi ↔ jabatan/proyek/lokasi. | Sertifikasi seperti SIO-Crane akan dianggap wajib untuk semua karyawan (false negative massal). | Tabel rule applicability (lihat §6). Default: `is_mandatory=1` tanpa rule = **wajib untuk semua** (sesuai flag saat ini). Admin bisa mempersempit per jabatan/proyek. |
| G2 | Validator format NIK/NPWP/BPJS/rekening/tanggal tidak ada di skema karyawan (hanya di impor 01E). | Data lama bisa berformat salah tanpa ketahuan. | Pindahkan fungsi validator ke modul bersama (`core/field_validators.py`). Dipakai oleh 01E dan 01F. **Save existing tidak diubah**; 01F hanya menandai status INVALID. |
| G3 | `employee_salaries.ptkp_status` berdefault `TK/0`, sehingga tidak bisa dibedakan antara "belum diisi" dan "benar TK/0". | `TAX.PTKP` akan selalu terlihat lengkap. | Fase 1: anggap lengkap bila baris salary ada, disertai catatan. Opsi lanjutan (butuh keputusan user): tambahkan penanda `ptkp_confirmed_at` di `employee_salaries.extra` tanpa kolom baru. |
| G4 | Tidak ada field "jumlah tanggungan" terpisah. PTKP `K/n` menyiratkan jumlahnya. | Hanya bisa dicek sebagai WARNING konsistensi dengan data keluarga. | Tanpa schema baru. |
| G5 | Dokumen dengan `owner_scope=certification/contract` terhubung ke record sertifikasi/kontrak, bukan langsung ke karyawan. | Butuh join dua langkah untuk "sertifikasi punya file". | Loader bulk. Level RECOMMENDED. |
| G6 | Tidak ada tanggal kedaluwarsa KTP (KTP seumur hidup). MCU sudah `has_expiry`. | – | Cukup memakai `has_expiry` dari master. |
| G7 | Kelengkapan berubah seiring waktu (kedaluwarsa) tanpa ada event tulis. | Snapshot bisa basi. | Evaluasi ulang harian via scheduler existing + evaluasi on-read untuk halaman detail. |
| G8 | Baris assignment `LEGACY_BASELINE` bisa punya `start_date` NULL (aturan 01D: tidak boleh dikarang). | Tidak boleh dihitung sebagai kekurangan. | Rule `PLACEMENT.ACTIVE` hanya memeriksa keberadaan assignment ACTIVE, bukan tanggal. |
| G9 | Level wajib/anjuran per tenant belum bisa dikonfigurasi. | Kebutuhan PT REAL bisa berbeda dari default. | Tabel rule tenant (§6). |
| G10 | `config_overrides` tidak punya scope position atau employment_status. | Tidak cukup untuk applicability sertifikasi. | Tabel applicability sendiri (§6). `config_overrides` tetap dipakai untuk parameter numerik. |
| G11 | Jalur pembuatan karyawan yang lain: impor lama (`employees.py:689`), konversi rekrutmen (`recruitment_conversion.py:309`). | Karyawan dari jalur ini juga perlu dievaluasi. | Masukkan ke daftar hook (§7). |

---

## 6. Proposal schema 01F (DESAIN SAJA — BELUM DIIMPLEMENTASI)

Migration additive `m0007_data_completeness.py`, mengikuti pola m0006: dry-run default, `--apply`, ledger `schema_migrations`, idempotent, dan rerun menghasilkan SKIP.

1. **`completeness_rules`** (override per tenant atas katalog sistem; boleh kosong = pakai default)
   `id, company_id, requirement_code, level (REQUIRED|RECOMMENDED|OFF), weight (int, default 1), is_active, notes, audit fields, extra`
   Unik: (`company_id`, `requirement_code`).
2. **`completeness_rule_scopes`** (applicability; opsional per rule)
   `id, company_id, requirement_code, scope_type (position|project|work_location|department|division|job_grade|employment_status|business_status_category), scope_id, mode (INCLUDE|EXCLUDE), effective_from, effective_to, audit fields`
   Semantik: tanpa baris scope = berlaku sesuai applicability default. Ada INCLUDE = hanya berlaku untuk scope tersebut. EXCLUDE = dikecualikan.
3. **`employee_completeness`** (snapshot, 1 baris per karyawan)
   `id, company_id, employee_id (unik per company), score_pct, required_total, required_complete, recommended_total, recommended_complete, missing_codes (JSON, hanya kode), items (JSON: code → status + tanggal kedaluwarsa bila ada), catalog_version, rules_hash, evaluated_at, evaluated_trigger, is_stale`
   **Tidak menyimpan nilai field sama sekali**, termasuk nilai sensitif.
4. **Permission**: `completeness:view` (atau reuse `employee:view`) dan `completeness:configure` (tenant_admin, hr_admin; company_owner lewat wildcard).
5. Index: (`company_id`, `employee_id`), (`company_id`, `score_pct`), (`company_id`, `requirement_code`).
6. **Tidak** ada kolom baru di tabel existing. **Tidak** ada backfill yang mengubah data bisnis. Snapshot awal dibuat oleh job evaluasi, bukan oleh migration.

Alternatif lebih ringan (bila user ingin tanpa tabel rule di fase awal): fase 1 hanya membuat tabel snapshot, dan rule memakai flag master (`is_mandatory`, `requires_contract`) + default katalog. Tabel rule/scope ditambahkan di fase 2.

---

## 7. Proposal rule engine

- `core/completeness_mapping.py`: katalog requirement sistem (code, kategori, label ID, sumber, validator key, sensitive, applicability default, level default) + `CATALOG_VERSION`.
- `core/field_validators.py`: validator bersama (nik, npwp, bpjs, digits, date, phone, email). 01E di-refactor minimal untuk mengimpor dari sini, **dengan hasil identik** (diverifikasi dengan `test_01e.py`).
- `core/completeness.py`:
  - `load_context(company_id, employee_ids)`: **bulk loader** tanpa N+1. Satu query per tabel: employees, assignments ACTIVE, family, documents (owner employee/contract/certification), contracts, certifications, salaries, masters, rules, scopes.
  - `evaluate(employee, ctx) -> items`: **fungsi murni**, tanpa I/O, mudah dites.
  - `summarize(items) -> score`: skor = selesai / total untuk REQUIRED (berbobot). RECOMMENDED dilaporkan terpisah.
  - `refresh(company_id, employee_ids, trigger)`: evaluasi lalu upsert snapshot.
- **Trigger**:
  - Setelah write sukses (§8): `refresh(...)` dipanggil **setelah transaksi bisnis selesai**, best-effort (try/except + log tipe error). **Tidak pernah membatalkan atau mengubah hasil operasi bisnis.**
  - 01E commit: **satu refresh bulk di akhir batch** untuk semua employee_id yang ter-commit, bukan per karyawan di dalam transaksi.
  - Harian: job di scheduler existing (per company) untuk kedaluwarsa dan perubahan master/rule.
  - Perubahan master/rule: tandai `is_stale` lalu refresh async/terjadwal.
  - On-demand: tombol "Evaluasi ulang" (per karyawan / per tenant), permission `completeness:configure`.
- **Output API (fase coding)**: `GET /employees/{id}/completeness`, `GET /completeness/summary` (per kategori/proyek), `GET /completeness/employees?filter=missing:DOC.KTP`, `GET/PUT /completeness/rules`. Semua tenant-scoped dan hanya berisi kode/status.

---

## 8. Integration points (tanpa perubahan sekarang)

| Event | Lokasi | Catatan hook |
|---|---|---|
| Edit profil 01C (field inti) | `routers/employees.py:450` PUT | setelah update sukses |
| Tambah karyawan | `routers/employees.py:326` POST | setelah create (termasuk initial 01B/01D) |
| Keluarga | `routers/employee_profile.py:119/138/150` | setelah create/update/delete |
| Foto | `routers/employee_profile.py:179/202` | setelah upload/delete |
| Status 01B | `routers/employee_status.py:287` status-change; `routers/employees.py:511` PATCH legacy status | applicability berubah |
| Penempatan 01D | `routers/employee_assignment.py:154/169/193` | create/transfer/end |
| Commit impor 01E | `routers/employee_import.py` `commit_batch` (setelah loop, sebelum respons) memakai `core/employee_import.py:667 apply_entity` | satu refresh bulk per batch |
| Impor lama | `routers/employees.py:689` | refresh bulk untuk karyawan yang dibuat |
| Konversi rekrutmen | `routers/recruitment_conversion.py:309` | setelah karyawan dibuat |
| Dokumen | `routers/documents.py:101/295/312` (hanya owner_type employee/contract/certification) | upload/update/soft delete |
| Kontrak | `routers/contracts.py:117/153/177/201/227/343` | create/update/approve/status/delete/renew |
| Sertifikasi | `routers/certifications.py:111/136/161/187` | create/update/status/delete |
| Salary/PTKP/BPJS enrolment | `routers/payroll.py:328` PUT salaries | applicability NPWP/BPJS berubah |
| Master (doc type, cert type, employment status) | generic master router (`masters.py`) | tandai stale + refresh terjadwal |
| Arsip/hapus karyawan | `routers/employees.py:552` | hapus/abaikan snapshot |

Implementasi hook diusulkan lewat **satu helper** (`completeness.schedule_refresh(ctx, employee_ids, trigger)`), dipanggil satu baris di tiap titik. Tidak ada logic completeness di router.

---

## 9. Snapshot kondisi data staging (hitungan saja, tanpa nilai)

Karyawan NEP non-fixture (tanpa prefix ZT): **9**. Jumlah terisi: nik 9, npwp **0**, domicile_address **0**, province/postal_code **0**, emergency_contact **0**, photo **0**, address 1, bank 3, BPJS Kesehatan/TK 1, project 3.
Karyawan dengan: keluarga 4, kontrak 8, sertifikasi 5, baris salary 8 (seluruh tenant).
Artinya: skor awal akan **rendah**. Ini wajar dan informatif, karena 01F hanya **melaporkan**, tidak memblokir.

---

## 10. Risiko / dampak regresi

| Risiko | Mitigasi |
|---|---|
| Hook di jalur tulis membuat save existing gagal atau lambat | best-effort setelah commit, try/except, tidak mengubah respons; regresi 01B/01C/01D/01E |
| Impor 5.000 baris melambat | satu refresh bulk di akhir batch + bulk loader; ukur di tes performa 01E |
| Kebocoran data sensitif lewat snapshot/log | snapshot hanya kode/status; tes grep nilai sensitif di API/log/audit |
| Kebocoran lintas tenant | semua query memakai company_id; tes lintas tenant (KBS vs NEP) |
| False negative massal (sertifikasi global) | default applicability + rule scope; preview dampak sebelum aktif |
| Refactor validator 01E mengubah hasil impor | refactor pure move + `test_01e.py` 63/63 wajib tetap PASS |
| Scheduler dobel di multi-worker | pakai pola guard scheduler existing; job idempotent (upsert) |
| Snapshot basi | kolom `evaluated_at` + `is_stale` + job harian + evaluasi on-read di halaman detail |
| Baseline/PT REAL terlihat "buruk" | UI membingkai hasil sebagai "perlu dilengkapi", bukan error; tanpa blokir |

---

## 11. Urutan implementasi yang diusulkan (setelah review)

1. Keputusan user: (a) tabel rule/scope langsung atau bertahap, (b) daftar requirement + level default (tabel §4), (c) perlakuan PTKP (G3), (d) permission `completeness:view/configure` atau reuse `employee:view`.
2. `core/field_validators.py` + refactor minimal 01E (hasil identik) → `test_01e.py`.
3. `core/completeness_mapping.py` + `core/completeness.py` (evaluate murni + bulk loader) + unit test dengan fixture ZT01F.
4. Migration `m0007_data_completeness` (dry-run → apply → rerun SKIP).
5. API read-only (detail karyawan, ringkasan, daftar filter) + refresh on-demand.
6. Hook best-effort di titik §8 + refresh bulk 01E + job harian scheduler.
7. UI: kartu "Kelengkapan Data" di Profile 360 (per kategori, tautan ke tab), dashboard ringkasan, halaman konfigurasi rule.
8. Regresi 01B/01C/01D/01E + legacy + domain lain, tes performa, visual QA, testing_agent_v3, cleanup ZT01F, restart x2, laporan final. STOP untuk review.

**STOP — menunggu review sebelum coding 01F.**
