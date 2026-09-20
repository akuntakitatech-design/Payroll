# Audit Kesiapan SaaS Multi-Company — HRIS/Payroll Akuntakita

**Repository:** `akuntakitatech-design/Payroll`
**Tanggal audit:** 20 September 2026
**Sifat:** AUDIT ONLY — tidak ada perubahan source code, commit, database, migration, auth, role, deployment, domain, maupun environment variable.
**Status aplikasi existing:** tetap berjalan normal (`/api/health` → `mariadb:connected`, `read_only: true`).

---

## A. CURRENT ARCHITECTURE

### A.1 Frontend (pertanyaan 1)

| Aspek | Temuan | Referensi |
|---|---|---|
| Library UI | **React 19.0.0** | `frontend/package.json:48-50` |
| Build tool | **CRA + CRACO 7.1.0** (bukan Vite) | `package.json:64-66, 82` |
| Routing | **react-router-dom 7.15.0** | `package.json:53` |
| Data fetching | **@tanstack/react-query 5.56.2** + **SWR 2.3.8** (keduanya ada) | `package.json:34, 57` |
| State global | Tidak ada Redux/Zustand — hanya React Context | `frontend/src/lib/auth.jsx` |
| Styling | **Tailwind CSS 3.4.17** + tailwindcss-animate, CVA, clsx, tailwind-merge | `package.json:96` |
| Komponen | **Radix UI primitives** dengan pola **shadcn/ui** | `package.json:7-33`, `src/components/ui/*` |
| Chart | **Recharts 3.6.0** | `package.json:55` |
| HTTP client | **Axios 1.18.0** | `package.json:35` |

### A.2 Backend / API (pertanyaan 2)

| Aspek | Temuan | Referensi |
|---|---|---|
| Framework | **FastAPI 0.110.1** + Starlette 0.37.2 + Uvicorn 0.25.0 | `backend/requirements.txt` |
| Validasi | **Pydantic 2.13.5** | `backend/requirements.txt` |
| Prefix API | Semua router dimount di bawah `APIRouter(prefix="/api")` | `backend/server.py:41, 100` |
| Jumlah router | **15 router** | `backend/app/routers/` |
| Penjadwal | APScheduler (reminder email), nonaktif saat READ_ONLY | `backend/app/core/scheduler.py` |
| Storage | Cloudflare R2 via boto3 (S3-compatible) | `backend/app/core/storage.py` |

**Daftar router & prefix** (`server.py:84-98`):

| File | Prefix | Fungsi |
|---|---|---|
| `auth.py` | `/api/auth` | login, refresh, me, switch-company |
| `companies.py` | `/api/companies` | CRUD perusahaan |
| `master.py` | `/api/master` | master data |
| `users.py` | `/api/users`, `/api/roles` | pengguna & peran |
| `employees.py` | `/api/employees` | karyawan + import Excel |
| `contracts.py` | `/api/contracts` | kontrak + renewal |
| `certifications.py` | `/api/certifications` | sertifikasi |
| `documents.py` | `/api/documents` | dokumen (R2) |
| `payroll.py` | `/api/payroll` | payroll run, komponen, slip gaji |
| `approvals.py` | `/api/approval-workflows` | alur persetujuan |
| `policies.py` | `/api/policies` | kebijakan perusahaan |
| `reminders.py` | `/api/reminders` | pengingat masa berlaku |
| `settings_mail.py` | `/api/mail` | SMTP & reminder settings |
| `audit_logs.py` | `/api/audit-logs` | jejak audit |
| `dashboard.py` | `/api/dashboard` | agregasi dashboard |

### A.3 Database (pertanyaan 3)

- **MariaDB / MySQL**, driver **asyncmy** (`mysql+asyncmy://`) — `backend/app/core/config.py:11-36`
- MongoDB **sudah tidak dipakai** sebagai datastore aplikasi.
- Pool async lewat `create_async_engine` (`db.py:410-427`), dengan `warm_pool()` (`db.py:437-462`) karena database berada jauh (latensi tinggi).

### A.4 ORM / Database Client (pertanyaan 4) — **TEMUAN PENTING**

Aplikasi **tidak memakai ORM konvensional**. `backend/app/core/db.py` adalah **adapter custom buatan sendiri** yang:

- Meniru API **Motor/PyMongo** (`find`, `find_one`, `insert_one`, `update_one`, `$set`, `$inc`, `$push`, `$or`, `$in`, `$regex`, `Cursor`, `ReturnDocument`) — `db.py:1-16`
- Berjalan di atas **SQLAlchemy Core (async)**, bukan declarative ORM — murni `Table`/`select`/`insert`
- Menerjemahkan filter Mongo-style ke SQL lewat `compile_filter()` (`db.py:678-748`) dan kelas `_Field` (`db.py:590-660`)

**Skema tabel** dideklarasikan dalam dict `TABLE_SPECS` (`db.py:152-298`), bukan Alembic. Sinkronisasi skema dilakukan oleh `ensure_indexes()` → `_sync_schema()` (`db.py:1256-1289`) pada setiap startup:

1. `metadata.create_all(checkfirst=True)` — membuat tabel yang belum ada
2. Deteksi kolom/index yang belum ada lalu `ALTER TABLE ADD COLUMN` / `ADD UNIQUE` / `CREATE INDEX`

> **Implikasi positif untuk rencana SaaS:** mekanisme ini bersifat **additive-only** (tidak pernah `DROP`). Menambahkan **tabel baru** atau **kolom baru** relatif aman dan tidak memerlukan tool migration terpisah. Ini sangat menguntungkan rencana Platform Console.

Setiap tabel otomatis mendapat kolom umum dari dict `COMMON` (`db.py:141-148`):
`id` (CHAR(36) UUID, PK) · `company_id` · `status` · `created_at` · `updated_at` · `created_by` · `updated_by` · `extra` (JSON catch-all)

### A.5 Sistem Autentikasi Existing (pertanyaan 5)

| Aspek | Temuan | Referensi |
|---|---|---|
| Mekanisme | **JWT** via PyJWT, algoritma HS dari `settings.JWT_ALGORITHM` | `core/security.py:29, 45` |
| Payload access token | `{sub: user_id, active_company_id, exp, iat, typ:"access"}` | `core/security.py:32-37` |
| Payload refresh token | `{sub, exp, iat, typ:"refresh"}` | `core/security.py:40-41` |
| Password hashing | **bcrypt**, rounds = 11 | `core/security.py:9-17` |
| Lockout | Terkunci `LOGIN_LOCK_MINUTES` setelah `LOGIN_MAX_ATTEMPTS` gagal | `routers/auth.py:93-113` |
| Refresh | `POST /api/auth/refresh`, validasi `typ=="refresh"` | `routers/auth.py:148-162` |
| Revocation | **TIDAK ADA** blacklist/rotation — refresh token lama tetap valid sampai kedaluwarsa | — |
| Penyimpanan token (FE) | **localStorage** (`hris_access_token`, `hris_refresh_token`, `hris_session`) | `frontend/src/lib/api.js:8-9`, `src/lib/auth.jsx:6, 20-41` |
| Interceptor | Request menyisipkan `Bearer`; response 401 → paksa logout. **Tidak ada auto-refresh** | `src/lib/api.js:13-34` |

**Catatan penting:** token access berisi klaim `active_company_id`, **bukan** daftar seluruh company. Company aktif **diverifikasi ulang ke database setiap request** (`core/deps.py:142-181`), bukan dipercaya buta dari token. Ini desain yang baik.

### A.6 Struktur Role & Permission Existing (pertanyaan 6)

**8 role bawaan** (`core/rbac.py:78-87`):

| Key | Nama | Scope |
|---|---|---|
| `super_admin` | Super Admin | **global** |
| `company_owner` | Pemilik Perusahaan | company |
| `hr_admin` | HR Admin | company |
| `hr_manager` | HR Manager | company |
| `finance` | Finance | company |
| `manager` | Manager | company |
| `supervisor` | Supervisor | company |
| `employee` | Karyawan | company |

Mekanisme:
- Tabel `roles` **sudah memiliki kolom `scope`** (`db.py:165`) → nilai `global` vs `company`.
- Permission disimpan di DB (`role_permissions`), dapat diedit lewat UI; kode hanya menyediakan seed awal (`seed.py:708-787`).
- `super_admin` dan `company_owner` mendapat wildcard `*:*`.
- Pemeriksaan: dependency factory `require_permission(resource, action, module_key)` (`core/deps.py:218-236`) — memeriksa **modul aktif** dulu (`has_module`) lalu **permission**. Tersedia juga `require_super_admin()` (`core/deps.py:239-245`).
- Frontend: menu difilter ganda oleh permission **dan** modul aktif lewat `filterNav()` (`src/lib/nav.js:239-248`). **Tidak ada route guard berbasis permission** — `ProtectedRoute` hanya memeriksa "sudah login atau belum" (`src/App.js:44-50`).

---

## B. CURRENT MULTI-TENANT READINESS

### B.1 Sudah multi-company atau single-company? (pertanyaan 8)

**Jawaban: SUDAH MULTI-COMPANY secara fungsional, tetapi BELUM multi-tenant SaaS.**

Bukti kesiapan multi-company:
- Relasi **N-N** user ↔ company ↔ role lewat tabel `user_company_roles` (`db.py:171`)
- Endpoint **ganti perusahaan**: `POST /api/auth/switch-company` (`routers/auth.py:198-219`)
- UI **company selector** di topbar (`src/components/layout/CompanySwitcher.jsx:18-36`, dipasang di `Topbar.jsx:68-70`)
- **31 tabel tenant** yang semuanya berkolom `company_id`
- Aktivasi modul **per perusahaan** lewat tabel `company_modules` (`db.py:236`)
- Pengaturan **per perusahaan**: `company_settings`, `smtp_settings`, `reminder_settings`
- Data demo sudah membuktikan: user `hr.multi@hris.id` memiliki role di 2 perusahaan berbeda (`seed.py:65-71`)

Yang **belum** ada sehingga masih bukan SaaS:
- Tidak ada lisensi/subscription/trial/kuota
- Tidak ada level "platform" di atas tenant
- Tidak ada UI untuk membuat perusahaan baru
- Isolasi tenant belum ditegakkan di lapisan data

### B.2 Bagaimana pemisahan data antar perusahaan saat ini? (pertanyaan 9) — **RISIKO UTAMA**

Pemisahan dilakukan melalui **kolom discriminator `company_id`** pada satu database bersama (*shared database, shared schema*). Rantai pengamanannya:

1. Saat login/switch, keanggotaan user divalidasi ke `user_company_roles`
2. `ctx.company_id` (company aktif) diverifikasi ulang ke DB pada **setiap request** (`core/deps.py:142-181`)
3. Setiap query di router **harus menambahkan `{"company_id": ctx.company_id}` secara manual**

**Temuan kritis:** **TIDAK ADA `TenantRepository` atau enforcement otomatis.** Kelas `Collection`/`Cursor` di `db.py:885-1219` **tidak menyisipkan filter `company_id` secara otomatis**. Isolasi sepenuhnya bergantung pada disiplin developer.

Contoh pola yang benar: `routers/companies.py:153` → `{"company_id": ctx.company_id, "status": "active"}`

> **Risiko:** jika satu saja query baru lupa menyertakan filter `company_id`, terjadi **kebocoran data lintas tenant** tanpa ada jaring pengaman di lapisan database. Ini pola *"trust the developer"*, bukan *enforced isolation*. Untuk aplikasi internal dengan beberapa perusahaan risikonya terkendali; untuk **SaaS yang dijual**, ini adalah gap keamanan paling serius yang harus ditutup.

### B.3 Apakah transaksi utama sudah punya company_id? (pertanyaan 10)

**Ya — semua transaksi utama sudah memiliki `company_id`.**

Kolom `company_id` di-*inject* otomatis ke setiap tabel lewat dict `COMMON` (`db.py:141-148`, `_build_tables()` db.py:352-358), sehingga mencakup:

`payroll_runs` · `payroll_items` · `employee_salaries` · `employee_salary_history` · `payroll_components` · `employees` · `employee_contracts` · `employee_certifications` · `documents` · `audit_logs` · `approval_workflows` · `approval_steps` · `config_overrides` · `company_modules` · `company_settings` · `smtp_settings` · `reminder_settings` · `reminder_logs` · `payslip_email_logs` · seluruh tabel master (branches, departments, divisions, positions, job_grades, cost_centers, projects, work_locations, employment_statuses, contract_types, certification_types, document_types)

**Tabel global tanpa `company_id` bermakna** (`db.py:78-86`):
`companies` (tabel tenant master itu sendiri) · `users` · `roles` · `permissions` · `modules` · `role_permissions`

Pengecualian: `user_company_roles` terdaftar sebagai global **tetapi memiliki `company_id`** karena ia adalah tabel pemetaan user↔company↔role (`db.py:171`). Nilai `company_id = NULL` pada tabel ini berarti **role global** (dipakai `super_admin`).

---

## C. EXISTING DATABASE STRUCTURE TERKAIT KEBUTUHAN SaaS

### C.1 Model Company (pertanyaan 7)

Tabel **`companies`** (`db.py:153-158`) + kolom `COMMON`:

```
id, company_id(tidak dipakai), status, created_at, updated_at, created_by, updated_by, extra(JSON)
code, name, legal_name, npwp, industry
address, city, province, postal_code, phone, email, website, logo_url
timezone, currency, fiscal_year_start_month
```

Observasi untuk kebutuhan Platform Console:
- **Sudah tersedia:** nama perusahaan, `code` (dapat berfungsi sebagai kode tenant), `industry` (bidang usaha), `email`, `phone`, `created_at` (tanggal dibuat), `status`
- **Belum tersedia:** PIC, nomor WhatsApp, catatan internal Akuntakita, status lisensi, tanggal trial, tanggal subscription, paket, maksimum karyawan, maksimum user
- Kolom `status` existing dipakai untuk siklus hidup data (`active`/`archived`) — **jangan dicampur** dengan status lisensi

### C.2 Model User (pertanyaan 11) & hubungan dengan Company (pertanyaan 12)

Tabel **`users`** (`db.py:159-164`):

```
id, status, created_at, updated_at, created_by, updated_by, extra(JSON)
email, full_name, password_hash, phone, job_title, employee_number
default_company_id, last_login_at, failed_login_attempts, locked_until
must_change_password, is_demo_account
```

Hubungan user ↔ company:

```
users (1) ────< user_company_roles >──── (1) companies
                      │
                      └── role_key ──> roles ──< role_permissions >── permissions
```

- Tabel penghubung **`user_company_roles`**: `user_id`, `company_id`, `role_key`, `status` (`db.py:171`)
- Satu user **dapat memiliki role berbeda di beberapa perusahaan** → sudah SaaS-friendly
- `users.default_company_id` hanya menyimpan perusahaan terakhir/awal yang dipilih
- **`company_id = NULL` pada `user_company_roles` = role lintas perusahaan** (dipakai `super_admin`, `seed.py:883-888`)
- `accessible_companies()` (`core/deps.py:113-123`): jika user super admin → mengembalikan **semua** perusahaan; jika tidak → hanya perusahaan hasil keanggotaan

### C.3 Struktur database per domain yang diminta (pertanyaan 13)

**Company**
- `companies` — data perusahaan
- `company_settings` — preferensi (prefix ID karyawan, format tanggal, `payroll_statutory` JSON)
- `company_modules` — aktivasi modul per perusahaan (`module_key`, `is_active`, `activated_at`, `deactivated_at`)
- `config_overrides` — override konfigurasi bertingkat (`config_key`, `scope_type`, `scope_id`, `value` JSON) — **scope-nya tenant, bukan platform**

**User / Role / Permission**
- `users` · `roles` (punya kolom `scope`) · `permissions` (`resource`, `action`, `module_key`) · `role_permissions` · `user_company_roles` · `modules` (katalog modul global)

**Employee**
- `employees` — `full_name`, `nik`, `npwp`, `employment_status_id`, `department_id`, `bank_account`, `is_demo_data`
- `employee_contracts` — `contract_type_id`, `basic_salary`, `approval_state`
- `employee_certifications` — `certification_type_id`, `expiry_date`
- `documents` — `document_type_id`, `owner_type`/`owner_id`, `storage_path` (R2), `is_deleted`
- Master pendukung: `departments`, `divisions`, `positions`, `job_grades`, `branches`, `work_locations`, `cost_centers`, `projects`, `employment_statuses`, `contract_types`, `certification_types`, `document_types`

**Payroll**
- `payroll_components` — `code`, `kind`, `calc`, `taxable`, `prorate`, `include_in_bpjs_base`
- `employee_salaries` — `basic_salary`, `ptkp_status`, flag BPJS, `components` (JSON)
- `employee_salary_history` — riwayat perubahan gaji
- `payroll_runs` — `year`, `month`, `run_status`, `totals` (JSON), jejak approval (submitted/approved/rejected/paid)
- `payroll_items` — per karyawan: `earnings`, `deductions`, `bpjs`, `tax`, `attendance` (JSON), `payslip_email_status`

**Attendance — TIDAK ADA TABEL TERSENDIRI**
- Tidak ditemukan tabel `attendance` di `TABLE_SPECS`
- `attendance` hanya ada sebagai **kolom JSON di dalam `payroll_items`** (`db.py:282`) untuk menampung hari kerja/absen yang dipakai perhitungan payroll
- Konsekuensi: modul absensi belum ada — inilah sebab kartu "Hadir Hari Ini" di dashboard menampilkan *empty state* jujur

**Audit**
- `audit_logs` — `user_id`, `module`, `resource`, `action`, `before_value`/`after_value` (JSON), `ip_address`, **ber-`company_id` (tenant-scoped)**

### C.4 Apakah ada konsep subscription/license existing? (pertanyaan 14)

**TIDAK ADA — sama sekali.**

Pencarian kata kunci `subscription`, `license`, `trial`, `plan`, `package`, `quota`, `max_employees`, `expired` di seluruh backend hanya menemukan `expired` dalam konteks **masa berlaku dokumen/kontrak/sertifikasi karyawan** (fitur bisnis HRIS), **bukan** lisensi SaaS.

Artinya seluruh lapisan monetisasi adalah **greenfield** — dapat dirancang bersih tanpa perlu membongkar apa pun.

---

## D. GAP ANALYSIS

| # | Kebutuhan SaaS | Status Existing | Gap | Tingkat |
|---|---|---|---|---|
| 1 | Satu aplikasi banyak perusahaan | ✅ Ada (`user_company_roles`, switch-company) | — | — |
| 2 | Kolom `company_id` di transaksi | ✅ Ada di seluruh 31 tabel tenant | — | — |
| 3 | Isolasi data ditegakkan sistem | ⚠️ Manual per query | Tidak ada guard otomatis di lapisan DB | **TINGGI** |
| 4 | Level platform di atas tenant | ❌ Tidak ada | Perlu role `PLATFORM_OWNER` + area terpisah | **TINGGI** |
| 5 | Lisensi / subscription | ❌ Tidak ada | Perlu tabel + status + tanggal | **TINGGI** |
| 6 | Trial (default 14 hari, editable) | ❌ Tidak ada | Perlu `platform_settings` + tanggal per tenant | **TINGGI** |
| 7 | Histori perubahan status lisensi | ❌ Tidak ada | Perlu `subscription_history` | SEDANG |
| 8 | Audit log level platform | ⚠️ `audit_logs` ada tapi tenant-scoped | Perlu `platform_audit_logs` global | SEDANG |
| 9 | Kuota (maks karyawan / user) | ❌ Tidak ada | Perlu kolom + pemeriksaan saat create | SEDANG |
| 10 | UI membuat perusahaan baru | ❌ Tidak ada di frontend | `POST /api/companies` sudah ada di backend, tanpa UI | SEDANG |
| 11 | Data PIC / WhatsApp / catatan internal | ❌ Tidak ada | Perlu profil tenant | SEDANG |
| 12 | Penegakan akses saat expired/suspended | ❌ Tidak ada | Perlu guard + **pertimbangkan masa hidup token** | **TINGGI** |
| 13 | Pencabutan sesi saat tenant disuspend | ❌ Tidak ada revocation | Token lama tetap valid s/d kedaluwarsa | **TINGGI** |
| 14 | Route guard berbasis role di frontend | ⚠️ Hanya cek login | Perlu guard untuk area Console | SEDANG |
| 15 | Modul absensi | ❌ Tidak ada tabel | Di luar cakupan SaaS, tapi memengaruhi kuota/dashboard | RENDAH |
| 16 | Tool migration formal | ⚠️ Auto-sync additive | Aman untuk tambah tabel/kolom; belum ada versioning | RENDAH |

---

## E. RECOMMENDED ARCHITECTURE

### E.1 Prinsip: **tambah lapisan, jangan bongkar inti**

```
┌─────────────────────────────────────────────────────────────┐
│  LAPISAN PLATFORM (BARU — milik Akuntakita)                 │
│  Role: PLATFORM_OWNER (scope = "platform")                  │
│  API:  /api/platform/*        UI: /console/*                │
│  Data: tenant_subscriptions, subscription_history,          │
│        platform_settings, platform_audit_logs,              │
│        tenant_profiles                                      │
└───────────────────────────┬─────────────────────────────────┘
                            │ mengelola (tidak menyentuh data HR tenant)
┌───────────────────────────▼─────────────────────────────────┐
│  LAPISAN TENANT (EXISTING — TIDAK DIUBAH)                   │
│  Role: super_admin(global) / company_owner / hr_admin /     │
│        hr_manager / finance / manager / supervisor /        │
│        employee                                             │
│  API:  /api/auth, /api/employees, /api/payroll, ...         │
│  Data: companies + 31 tabel tenant ber-company_id           │
└─────────────────────────────────────────────────────────────┘
```

Semua penambahan bersifat **aditif**: tabel baru, prefix API baru, route frontend baru, role baru. Nol perubahan pada tabel, endpoint, dan role existing.

### E.2 PLATFORM_OWNER: tabel `users` existing atau mekanisme tersendiri? (pertanyaan 17)

**Rekomendasi: HYBRID — pakai tabel `users` existing, tetapi dengan pemisahan tegas.**

Rancangan:
1. Tambah role baru di `roles` dengan `key = "platform_owner"` dan **`scope = "platform"`**
   → kolom `scope` **sudah ada** (`db.py:165`), jadi **nol perubahan skema**
2. Keanggotaan dicatat di `user_company_roles` dengan `company_id = NULL` (pola yang sudah dipakai `super_admin`)
3. Tambah **penanda** pembeda, misalnya kolom `is_platform_user` pada `users` (atau simpan dalam kolom `extra` JSON yang sudah tersedia sehingga benar-benar nol perubahan skema)
4. Dependency baru **`require_platform_owner()`** untuk seluruh `/api/platform/*`
5. **Guard tambahan:** role `platform_owner` **tidak boleh** muncul/di-assign dari UI tenant (`UsersPage`/`RolesPage`) — hanya lewat Console

**Alasan memilih hybrid:**

| Pendekatan | Kelebihan | Kekurangan |
|---|---|---|
| **Tabel `users` existing + role scope platform** ✅ | Reuse bcrypt, lockout, JWT, refresh, audit login yang sudah teruji. Tidak ada dua sistem auth untuk dirawat. Pola `company_id = NULL` sudah terbukti jalan | Perlu guard disiplin agar user platform tidak tercampur ke daftar user tenant |
| Tabel `platform_users` terpisah | Isolasi paling tegas, tidak mungkin tercampur | Duplikasi seluruh logika auth (hashing, lockout, JWT, refresh, reset password) → permukaan bug dan biaya rawat berganda |

Untuk skala Akuntakita saat ini (onboarding manual, jumlah platform user sangat sedikit), **duplikasi sistem auth adalah over-engineering**. Hybrid memberi keamanan yang memadai dengan biaya paling rendah. Jika kelak Akuntakita butuh SSO/2FA khusus internal, pemisahan dapat dilakukan belakangan tanpa mengubah tenant.

### E.3 Perlakuan `super_admin` existing

`super_admin` saat ini **sudah de-facto dapat melihat semua perusahaan** (`core/deps.py:113-123`, `routers/companies.py:76`). Rekomendasi:

- **JANGAN** mengubah atau menghapus `super_admin` — akun dan permission existing harus tetap berfungsi
- Posisikan `super_admin` sebagai **peran operasional teknis** existing
- `platform_owner` adalah role **baru dan terpisah** yang memegang kewenangan **komersial/lisensi** (trial, aktivasi, suspend, paket)
- Pemisahan ini penting: mengelola *lisensi* berbeda dari mengelola *data HR*

### E.4 Rekomendasi URL/Route Platform Console (pertanyaan 19)

**Sebelum** `console.hris.akuntakita.com` tersedia — pakai path pada aplikasi yang sama:

| Lapisan | Route sementara | Catatan |
|---|---|---|
| Backend API | **`/api/platform/*`** | Prefix baru, tidak bertabrakan dengan router mana pun. Contoh: `/api/platform/dashboard`, `/api/platform/tenants`, `/api/platform/tenants/{id}`, `/api/platform/tenants/{id}/trial`, `/api/platform/settings` |
| Frontend UI | **`/console/*`** | Contoh: `/console`, `/console/tenants`, `/console/tenants/:id`, `/console/settings`. Dilindungi guard `RequirePlatformOwner` |

Mengapa `/console` dan bukan `/platform` atau `/admin`:
- `/admin` berisiko membingungkan dengan "HR Admin" milik tenant
- `/console` konsisten dengan rencana subdomain `console.hris.akuntakita.com` sehingga migrasi nanti hanya soal routing Nginx, tanpa ubah kode

**Jalur migrasi ke subdomain (tahap paling akhir, tanpa ubah kode aplikasi):**
```
hris.akuntakita.com          → landing page (static, terpisah)
app.hris.akuntakita.com      → React app, route /console diblok di Nginx
console.hris.akuntakita.com  → React app yang sama, root diarahkan ke /console
                               keduanya proxy /api → backend:8001
```
Karena `REACT_APP_BACKEND_URL` kosong di produksi menghasilkan `/api` relatif (`src/lib/api.js:3-6`), pemisahan subdomain **tidak memerlukan perubahan environment variable frontend**.

---

## F. DATABASE CHANGES YANG NANTINYA DIPERLUKAN (pertanyaan 18)

> Semua di bawah ini adalah **tabel BARU**. Tidak ada tabel existing yang diubah, tidak ada kolom dihapus, tidak ada data disentuh. Karena `_sync_schema()` bersifat additive (`create_all(checkfirst=True)` + `ADD COLUMN`), penambahan ini tidak memerlukan migration tool.

**Catatan teknis penting:** dict `COMMON` menyuntikkan `company_id` ke **semua** tabel. Tabel platform yang bersifat global harus didaftarkan di `GLOBAL_COLLECTIONS` (`db.py:78-86`) agar tidak diperlakukan sebagai tabel tenant.

### F.1 `tenant_subscriptions` — lisensi per tenant (1 baris aktif per company)

| Kolom | Tipe | Keterangan |
|---|---|---|
| `id` | CHAR(36) | PK (otomatis dari COMMON) |
| `company_id` | CHAR(36) | FK → `companies.id`, **unique** |
| `license_status` | VARCHAR(32) | `TRIAL` / `ACTIVE` / `EXPIRED` / `SUSPENDED` / `INACTIVE` |
| `plan_code` | VARCHAR(64) | mis. `basic`, `pro`, `enterprise` (paket) |
| `trial_start` | DATETIME(6) | tanggal mulai trial |
| `trial_end` | DATETIME(6) | tanggal akhir trial |
| `trial_days` | INT | durasi efektif (hasil default platform atau override manual) |
| `subscription_start` | DATETIME(6) | tanggal mulai langganan |
| `subscription_end` | DATETIME(6) | tanggal akhir langganan |
| `max_employees` | INT | kuota karyawan, `NULL` = tanpa batas |
| `max_users` | INT | kuota user, `NULL` = tanpa batas |
| `grace_period_days` | INT | masa tenggang setelah kedaluwarsa |
| `suspended_at` | DATETIME(6) | waktu suspend |
| `suspend_reason` | TEXT | alasan suspend |
| `internal_notes` | TEXT | catatan internal Akuntakita |
| `created_at`/`updated_at`/`created_by`/`updated_by` | — | dari COMMON |

### F.2 `subscription_history` — jejak perubahan status (append-only)

| Kolom | Tipe | Keterangan |
|---|---|---|
| `id` | CHAR(36) | PK |
| `company_id` | CHAR(36) | FK → `companies.id`, ber-index |
| `action` | VARCHAR(48) | `START_TRIAL` / `EXTEND_TRIAL` / `ACTIVATE` / `EXTEND_SUBSCRIPTION` / `CHANGE_PACKAGE` / `SUSPEND` / `REACTIVATE` / `DEACTIVATE` |
| `from_status` | VARCHAR(32) | status sebelum |
| `to_status` | VARCHAR(32) | status sesudah |
| `from_plan_code` / `to_plan_code` | VARCHAR(64) | perubahan paket |
| `previous_end_date` / `new_end_date` | DATETIME(6) | perubahan tanggal akhir |
| `effective_date` | DATETIME(6) | tanggal berlaku |
| `reason` | TEXT | alasan |
| `actor_user_id` | CHAR(36) | siapa yang melakukan |
| `snapshot` | JSON | salinan penuh baris subscription sebelum perubahan |
| `created_at` | DATETIME(6) | — |

> Prinsip **append-only**: baris histori tidak pernah di-update atau dihapus. Ini memenuhi permintaan "histori perubahan status dapat dilacak".

### F.3 `platform_settings` — pengaturan global platform (key-value)

| Kolom | Tipe | Keterangan |
|---|---|---|
| `id` | CHAR(36) | PK |
| `key` | VARCHAR(128) | **unique**, mis. `default_trial_days` |
| `value` | JSON | nilai, mis. `14` |
| `value_type` | VARCHAR(32) | `int` / `string` / `bool` / `json` |
| `label` / `description` | VARCHAR / TEXT | untuk UI |
| `group_key` | VARCHAR(64) | pengelompokan di UI |
| `is_editable` | BOOLEAN | pengaman setting sistem |
| `updated_by` / `updated_at` | — | jejak perubahan |

Seed awal yang disarankan:
```
default_trial_days          = 14      (editable oleh PLATFORM_OWNER)
default_plan_code           = "basic"
default_max_employees       = NULL    (tanpa batas)
default_max_users           = NULL
default_grace_period_days   = 0
expiry_warning_days         = 7       (untuk kartu "segera berakhir" di dashboard Console)
license_enforcement_enabled = false   (FEATURE FLAG — lihat H.5)
```

> **Mengapa tabel baru dan bukan `config_overrides` existing?** Karena `config_overrides` bersifat **tenant-scoped** (`db.py:247-250`) dan berkolom `company_id`. Pengaturan platform harus global dan tidak boleh bisa dijangkau/diubah dari konteks tenant mana pun.

### F.4 `platform_audit_logs` — audit level platform

| Kolom | Tipe | Keterangan |
|---|---|---|
| `id` | CHAR(36) | PK |
| `actor_user_id` | CHAR(36) | PLATFORM_OWNER pelaku |
| `actor_email` | VARCHAR(255) | disimpan denormal agar tetap terbaca bila user dihapus |
| `action` | VARCHAR(64) | mis. `TENANT_SUSPEND`, `SETTING_UPDATE` |
| `target_type` | VARCHAR(48) | `company` / `subscription` / `platform_setting` / `platform_user` |
| `target_id` | CHAR(36) | id objek |
| `target_label` | VARCHAR(255) | nama perusahaan agar mudah dibaca |
| `before_value` / `after_value` | JSON | perubahan |
| `ip_address` / `user_agent` | VARCHAR | konteks |
| `created_at` | DATETIME(6) | — |

> **Dipisah dari `audit_logs` existing** karena `audit_logs` ber-`company_id` dan tampil di UI tenant. Aksi komersial Akuntakita **tidak boleh** terlihat oleh pelanggan.

### F.5 `tenant_profiles` — data komersial/CRM tenant

Dipisah agar tabel `companies` **tidak perlu diubah sama sekali**:

| Kolom | Tipe | Keterangan |
|---|---|---|
| `id` | CHAR(36) | PK |
| `company_id` | CHAR(36) | FK → `companies.id`, **unique** |
| `pic_name` | VARCHAR(255) | nama PIC |
| `pic_email` | VARCHAR(255) | email PIC |
| `pic_whatsapp` | VARCHAR(64) | nomor WhatsApp |
| `pic_position` | VARCHAR(128) | jabatan PIC |
| `business_field` | VARCHAR(255) | bidang usaha (melengkapi `companies.industry`) |
| `onboarding_source` | VARCHAR(64) | mis. `referral`, `direct`, `marketing` |
| `onboarded_at` | DATETIME(6) | tanggal onboarding |
| `internal_notes` | TEXT | catatan internal Akuntakita |
| `account_manager_id` | CHAR(36) | PIC internal Akuntakita |

### F.6 Opsional — `platform_plans` (katalog paket)

Untuk tahap awal, `plan_code` berupa string sudah cukup. Bila kelak butuh katalog paket terstruktur: `code`, `name`, `max_employees`, `max_users`, `included_modules` (JSON), `price`, `billing_cycle`, `is_active`, `sort_order`.

### F.7 Ringkasan dampak

| Jenis perubahan | Jumlah | Risiko |
|---|---|---|
| Tabel baru | 5 (+1 opsional) | Rendah — additive, `create_all(checkfirst=True)` |
| Tabel existing diubah | **0** | — |
| Kolom existing diubah/dihapus | **0** | — |
| Data existing disentuh | **0** | — |
| Baris role baru | 1 (`platform_owner`) | Rendah — kolom `scope` sudah ada |

---

## G. SECURITY / TENANT ISOLATION RISKS (pertanyaan 15)

### G.1 Risiko yang sudah ada sekarang (terlepas dari Platform Console)

| # | Risiko | Dampak | Bukti | Mitigasi disarankan |
|---|---|---|---|---|
| G1 | **Filter `company_id` manual** — tidak ada enforcement di lapisan DB | Kebocoran data lintas tenant bila satu query lupa filter | `db.py:885-1219` tidak menyisipkan filter otomatis | Tambahkan **lapisan pembungkus tenant-aware** yang menolak/menyuntikkan filter; plus tes otomatis anti-kebocoran |
| G2 | **Refresh token tanpa revocation** | Suspend tenant tidak langsung berlaku; sesi lama tetap hidup | Tidak ada blacklist di `routers/auth.py:148-162` | Cek status lisensi **setiap request** (bukan hanya saat login) + opsi daftar sesi yang dicabut |
| G3 | **Masa hidup access token panjang** (`ACCESS_TOKEN_EXPIRE_MINUTES`, default lingkungan 720 menit) | Perubahan hak/lisensi tertunda hingga token kedaluwarsa | `core/security.py:35` | Validasi lisensi di dependency request, bukan hanya di token |
| G4 | **Token di localStorage** | Rentan XSS | `src/lib/api.js:8-9` | Terima untuk MVP; pertimbangkan cookie `HttpOnly` saat SaaS publik |
| G5 | **Tidak ada route guard permission di frontend** | Halaman bisa diakses langsung lewat URL meski menu disembunyikan | `src/App.js:44-50` | Backend sudah menjadi penegak utama; tambahkan guard untuk area Console |
| G6 | **`company_owner` memegang wildcard `*:*`** | Bila kelak ada endpoint lintas tenant tanpa filter, pemilik tenant bisa menjangkaunya | `seed.py:708-787` | Jangan pernah mengandalkan permission untuk isolasi; selalu andalkan `company_id` |
| G7 | **Permission dapat diedit dari UI** | Perubahan matriks bisa membuka akses tak terduga | `RolesPage.jsx` | Lindungi role bawaan; catat perubahan di audit |

### G.2 Risiko BARU yang muncul bila Platform Console ditambahkan

| # | Risiko | Dampak | Mitigasi wajib |
|---|---|---|---|
| G8 | **Endpoint platform tidak sengaja terjangkau tenant** | Pelanggan bisa melihat/mengubah data pelanggan lain → pelanggaran paling fatal | Semua `/api/platform/*` **wajib** melewati `require_platform_owner()` yang memeriksa `scope == "platform"`; tulis tes otomatis: user tenant mengakses setiap endpoint platform harus dapat **403** |
| G9 | **Query platform yang sah sengaja lintas tenant** bercampur dengan query tenant | Developer keliru memakai helper platform di router tenant | Pisahkan **fisik**: folder `routers/platform/` + helper repository terpisah yang secara eksplisit bernama lintas-tenant |
| G10 | **Role `platform_owner` ter-assign ke user pelanggan** | Eskalasi hak penuh ke seluruh platform | Sembunyikan `platform_owner` dari daftar role di UI tenant; tolak assignment di backend bila pemberi bukan platform owner |
| G11 | **Penegakan lisensi mematikan HRIS yang sedang berjalan** | Pelanggan existing tiba-tiba terblokir karena belum punya baris subscription | **Feature flag** `license_enforcement_enabled = false` sebagai default; tenant tanpa baris subscription diperlakukan **ACTIVE tanpa batas** (fail-open) sampai Akuntakita sengaja mengisinya |
| G12 | **Penegakan kuota memblokir operasi payroll** | Payroll gagal di tengah bulan | Terapkan kuota **hanya** pada operasi *create* (tambah karyawan/user), **jangan** pada operasi baca atau proses payroll |
| G13 | **Aksi komersial terekspos ke tenant** | Pelanggan melihat catatan internal/harga | `platform_audit_logs` dan `tenant_profiles.internal_notes` **tidak boleh** memiliki endpoint di router tenant mana pun |
| G14 | **Platform Console menambah beban query ke DB produksi jauh** | Dashboard Console lambat (latensi DB tinggi ~240 ms) | Pakai pola paralel `asyncio.gather` seperti yang sudah diterapkan pada dashboard tenant; agregasi berbasis `COUNT` |
| G15 | **Perluasan `TABLE_SPECS` keliru** → tabel platform dianggap tenant | Data platform terfilter `company_id` dan tampak kosong/salah | Daftarkan tabel platform di `GLOBAL_COLLECTIONS` (`db.py:78-86`) dan verifikasi di lingkungan uji, bukan produksi |

### G.3 Penilaian risiko keseluruhan penambahan Platform Console

**Risiko: RENDAH sampai SEDANG**, dengan syarat urutan pengerjaan dijaga.

Alasan risiko relatif rendah:
- Seluruh perubahan bersifat **aditif** (tabel baru, prefix API baru, route baru, role baru)
- `_sync_schema()` additive-only, tidak pernah `DROP`
- Sudah ada `READ_ONLY` guard untuk menguji dengan data produksi secara aman (`db.py:778-801`)
- `company_id` sudah ada di seluruh tabel tenant, jadi tidak ada backfill data
- Lapisan lisensi adalah greenfield sehingga tidak ada logika lama yang perlu dibongkar

Sumber risiko sebenarnya bukan pada penambahan tabel/Console, melainkan pada **tahap penegakan lisensi (Tahap 5)**. Karena itu tahap tersebut ditaruh **paling akhir** dan **di balik feature flag**.

---

## H. IMPLEMENTATION PLAN PER TAHAP (pertanyaan 16 & 20)

Prinsip: **setiap tahap harus dapat dirilis sendiri, tidak mengubah perilaku HRIS existing, dan dapat dibatalkan.** Setiap tahap = **satu Pull Request** sesuai `AGENTS.md`.

### Tahap 0 — Audit (SELESAI, dokumen ini)
Tanpa perubahan kode.

### Tahap 1 — Fondasi Data Platform · risiko: **sangat rendah**
- Tambah 5 tabel baru ke `TABLE_SPECS`; daftarkan di `GLOBAL_COLLECTIONS`
- Seed `platform_settings` (termasuk `default_trial_days = 14` dan `license_enforcement_enabled = false`)
- **Tidak ada endpoint, tidak ada UI, tidak ada penegakan**
- Verifikasi: HRIS berjalan 100% identik; tabel baru terbentuk dan kosong
- Rollback: tabel baru dibiarkan kosong — nol dampak

### Tahap 2 — Role & Guard PLATFORM_OWNER · risiko: **rendah**
- Tambah role `platform_owner` (`scope = "platform"`) ke `rbac.py` + seed
- Buat dependency `require_platform_owner()` (baru, tidak menyentuh `require_permission` existing)
- Sembunyikan role ini dari UI tenant; tolak assignment dari konteks tenant
- Buat akun PLATFORM_OWNER pertama secara manual/terkontrol
- Verifikasi: 8 role existing tidak berubah; login semua role existing normal

### Tahap 3 — API Platform (HANYA BACA) · risiko: **rendah**
- Folder baru `routers/platform/` dengan prefix `/api/platform`
- Endpoint baca: `GET /dashboard`, `GET /tenants`, `GET /tenants/{id}`, `GET /settings`
- Tenant tanpa baris subscription ditampilkan sebagai "Belum diatur" (bukan error)
- Agregasi paralel (`asyncio.gather`) mengikuti pola dashboard tenant
- Verifikasi wajib: user tenant (setiap role) mengakses setiap endpoint platform → **403**

### Tahap 4 — Aksi Lisensi + Histori + Audit · risiko: **sedang**
- Endpoint aksi: Start Trial, Extend Trial, Activate, Extend Subscription, Change Package, Suspend, Reactivate, Deactivate
- Setiap aksi menulis `subscription_history` (append-only) + `platform_audit_logs`
- Endpoint `PUT /api/platform/settings` untuk mengubah `default_trial_days` dan kawan-kawan
- **Penting: masih belum ada penegakan** — status hanya dicatat, belum memblokir siapa pun
- Aturan yang ditegakkan: **tidak ada endpoint yang boleh menghapus data tenant** — Deactivate hanya mengubah status

### Tahap 5 — UI Platform Console · risiko: **rendah**
- Route `/console/*` + guard `RequirePlatformOwner`
- Halaman: Dashboard (jumlah tenant per status + yang segera berakhir), Daftar Tenant, Detail Tenant, Global Settings
- **Plus mengisi gap existing:** form membuat perusahaan baru (memakai `POST /api/companies` yang sudah ada namun belum punya UI)
- Bahasa Indonesia, mengikuti `design_guidelines.md` (teal/emerald), setiap elemen ber-`data-testid`
- Console dibedakan secara visual dari aplikasi tenant agar operator tidak keliru konteks

### Tahap 6 — Penegakan Lisensi · risiko: **TINGGI — paling akhir, di balik feature flag**
- Dependency `check_license()` disisipkan pada jalur auth tenant
- Default `license_enforcement_enabled = false` → perilaku identik dengan sekarang
- Kebijakan **fail-open**: tenant tanpa baris subscription = ACTIVE tanpa batas
- Pemetaan perilaku yang disarankan:

| Status | Perilaku aplikasi tenant |
|---|---|
| `TRIAL` (belum lewat) | Akses penuh + banner sisa hari |
| `TRIAL` (lewat) | Diperlakukan seperti `EXPIRED` |
| `ACTIVE` | Akses penuh |
| `EXPIRED` | **Boleh login, hanya-baca**, banner jelas, ekspor data tetap diizinkan |
| `SUSPENDED` | Login diblokir dengan pesan jelas + kontak Akuntakita |
| `INACTIVE` | Login diblokir |

- **Data pelanggan tetap utuh pada semua status** — sesuai persyaratan Anda
- Validasi lisensi dilakukan **per request** (bukan hanya saat login) untuk mengatasi risiko G2/G3
- Diuji pada tenant uji terlebih dahulu, bukan langsung ke pelanggan
- Rollback: matikan flag → seluruh penegakan nonaktif seketika

### Tahap 7 — Penegakan Kuota · risiko: **sedang**
- Periksa `max_employees` / `max_users` **hanya** saat *create*
- `NULL` = tanpa batas; pesan ramah berbahasa Indonesia saat kuota tercapai
- Tidak pernah memblokir operasi baca maupun proses payroll

### Tahap 8 — Pengerasan Isolasi Tenant · risiko: **sedang** (perbaikan G1)
- Tambahkan lapisan tenant-aware di atas adapter `db.py` untuk **menyuntikkan/memverifikasi** `company_id`
- Tambahkan suite tes anti-kebocoran lintas tenant
- Dapat dikerjakan bertahap per router tanpa mengubah perilaku
- *Boleh didahulukan sebelum Tahap 6 bila Anda ingin memprioritaskan keamanan sebelum monetisasi*

### Tahap 9 — Pemisahan Domain · risiko: **rendah** (hanya infrastruktur)
- `hris.akuntakita.com` (landing) · `app.hris.akuntakita.com` (tenant) · `console.hris.akuntakita.com` (Console)
- Murni konfigurasi Nginx/Coolify — **tanpa perubahan kode aplikasi**
- Blok route `/console` pada host aplikasi tenant sebagai lapisan pertahanan tambahan

### Urutan yang direkomendasikan

```
Tahap 1 → 2 → 3 → 4 → 5   ← Console fungsional, HRIS existing NOL perubahan perilaku
                 ↓
              Tahap 8       ← keamanan isolasi (disarankan sebelum monetisasi)
                 ↓
              Tahap 6 → 7   ← penegakan (di balik feature flag)
                 ↓
              Tahap 9       ← pemisahan domain
```

Setelah Tahap 5, Akuntakita **sudah dapat mengelola tenant, trial, dan lisensi secara operasional** meski penegakan teknis belum menyala. Untuk model bisnis Anda saat ini (onboarding manual, belum ada payment gateway), ini sudah memenuhi kebutuhan — dan merupakan titik berhenti yang aman.

---

## I. FILE-FILE YANG KEMUNGKINAN PERLU DIUBAH NANTINYA

### I.1 Backend — file existing yang disentuh (semuanya bersifat **penambahan**)

| File | Perubahan | Tahap | Risiko |
|---|---|---|---|
| `backend/app/core/db.py` | Tambah 5 entri di `TABLE_SPECS`; tambah nama tabel ke `GLOBAL_COLLECTIONS` | 1 | Rendah — additive |
| `backend/app/core/rbac.py` | Tambah satu entri role `platform_owner` (scope `platform`) | 2 | Rendah |
| `backend/app/seed.py` | Seed role baru + seed `platform_settings` | 1-2 | Rendah — pola `_upsert` sudah ada |
| `backend/app/core/deps.py` | Tambah `require_platform_owner()`; (Tahap 6) tambah `check_license()` | 2, 6 | Rendah → Sedang |
| `backend/server.py` | Mount router platform baru | 3 | Rendah |
| `backend/app/schemas.py` | Skema Pydantic baru untuk subscription/settings | 3-4 | Rendah |
| `backend/app/routers/users.py` | Guard agar `platform_owner` tak dapat di-assign dari konteks tenant | 2 | Rendah |
| `backend/app/routers/employees.py` | (Tahap 7) pemeriksaan kuota saat *create* saja | 7 | Sedang |
| `backend/app/routers/auth.py` | (Tahap 6) pemeriksaan lisensi saat login | 6 | **Sedang-Tinggi** — jalur kritis, wajib feature flag |
| `backend/app/core/config.py` | (Opsional) flag lisensi bila ingin lewat env, bukan `platform_settings` | 6 | Rendah |

### I.2 Backend — file BARU

```
backend/app/routers/platform/__init__.py
backend/app/routers/platform/dashboard.py     # ringkasan per status lisensi
backend/app/routers/platform/tenants.py       # daftar & detail tenant
backend/app/routers/platform/licenses.py      # 8 aksi lisensi
backend/app/routers/platform/settings.py      # global settings
backend/app/core/platform_service.py          # logika trial/subscription + histori
backend/app/core/license.py                   # evaluasi status + guard (Tahap 6)
```

### I.3 Frontend — file existing yang disentuh

| File | Perubahan | Tahap | Risiko |
|---|---|---|---|
| `frontend/src/App.js` | Tambah route `/console/*` + guard | 5 | Rendah |
| `frontend/src/lib/auth.jsx` | Ekspos flag `isPlatformOwner` dari sesi | 5 | Rendah |
| `frontend/src/lib/nav.js` | Navigasi khusus Console (terpisah dari `NAV_GROUPS` tenant) | 5 | Rendah |
| `frontend/src/components/layout/AppShell.jsx` | Cabang layout Console vs tenant | 5 | Rendah |
| `frontend/src/pages/UsersPage.jsx` | Sembunyikan role `platform_owner` dari daftar | 2 | Rendah |
| `frontend/src/pages/RolesPage.jsx` | Sembunyikan role scope `platform` dari matriks tenant | 2 | Rendah |

### I.4 Frontend — file BARU

```
frontend/src/pages/console/ConsoleDashboardPage.jsx
frontend/src/pages/console/TenantListPage.jsx
frontend/src/pages/console/TenantDetailPage.jsx
frontend/src/pages/console/PlatformSettingsPage.jsx
frontend/src/pages/console/CreateTenantPage.jsx        # mengisi gap: belum ada UI buat perusahaan
frontend/src/components/console/ConsoleShell.jsx
frontend/src/components/console/LicenseStatusBadge.jsx
frontend/src/components/console/LicenseActionDialog.jsx
frontend/src/components/console/SubscriptionHistoryTable.jsx
frontend/src/components/console/RequirePlatformOwner.jsx
frontend/src/lib/consoleApi.js
```

### I.5 Dokumentasi

- `README.md` — bagian arsitektur platform vs tenant
- `AGENTS.md` — aturan tambahan: larangan mencampur endpoint platform dan tenant
- `docker-compose.yml` / konfigurasi Nginx — hanya pada Tahap 9

---

## J. HAL-HAL YANG SEBAIKNYA **TIDAK** DIUBAH

### J.1 Jangan diubah sama sekali

| Objek | Alasan |
|---|---|
| **Bentuk payload JWT** (`core/security.py:32-41`) | Menambah klaim baru boleh; **mengubah/menghapus** `sub`, `active_company_id`, `typ` akan membatalkan semua sesi aktif pelanggan |
| **Skema `users`, `companies`, `roles`, `permissions`, `role_permissions`, `user_company_roles`** | Seluruh auth & RBAC bergantung padanya; kebutuhan baru dipenuhi lewat tabel baru |
| **8 role existing** dan key-nya (`core/rbac.py:78-87`) | Mengubah/menghapus akan mencabut hak akses pelanggan yang berjalan |
| **Semantik `company_id = NULL` di `user_company_roles`** | Ini fondasi role global; `platform_owner` justru akan memanfaatkan pola yang sama |
| **API adapter Mongo-style di `db.py`** (`Collection`, `Cursor`, `compile_filter`, `ReturnDocument`, `ASCENDING`) | **31 tabel dan 15 router bergantung padanya.** Mengganti ke ORM konvensional = penulisan ulang total. Adapter ini bekerja — biarkan |
| **Sifat additive `_sync_schema()`** (`db.py:1256-1289`) | Justru inilah yang membuat rencana ini aman. Jangan tambahkan logika `DROP` apa pun |
| **`READ_ONLY` guard** (`db.py:778-801`, `config.py:57`) | Satu-satunya pengaman preview terhadap data produksi |
| **`REACT_APP_BACKEND_URL`** dan **`MONGO_URL`** di `.env` | Dilarang oleh constraint platform Emergent |
| **Prefix `/api`** pada seluruh endpoint | Routing ingress bergantung pada prefix ini |
| **`ProtectedRoute`** existing (`src/App.js:44-50`) | Tambahkan guard **baru** untuk Console; jangan ubah guard tenant |
| **Logika `require_permission` / `has_module`** (`core/deps.py:218-236`) | Seluruh RBAC tenant bergantung padanya; buat dependency baru yang berdiri sendiri |
| **Mesin payroll** (`core/payroll.py`, `core/ter.py`, `core/pdf.py`, `core/excel.py`) | Sudah lulus 186/186 pemeriksaan dan menyangkut kepatuhan pajak. Tidak ada hubungannya dengan SaaS layer |
| **Struktur `audit_logs` existing** | Tenant-scoped dan tampil di UI pelanggan; audit platform memakai tabel terpisah |
| **Mekanisme seed & `AUTO_SEED`** | Dipakai untuk demo/onboarding; tambah seed baru, jangan ubah yang ada |

### J.2 Jangan dilakukan pada tahap ini

- ❌ Jangan buat **self-registration publik** — model bisnis Anda masih onboarding manual
- ❌ Jangan integrasikan **payment gateway** — belum dibutuhkan
- ❌ Jangan buat **billing/invoice otomatis** — over-engineering
- ❌ Jangan ubah **domain atau deployment** — sampai Tahap 9 dan dengan persetujuan Anda
- ❌ Jangan **hapus data tenant** pada kondisi apa pun — `SUSPENDED`/`EXPIRED`/`INACTIVE` hanya mengubah status
- ❌ Jangan pasang **penegakan lisensi tanpa feature flag**
- ❌ Jangan pindah ke **database per tenant** — shared-schema + `company_id` sudah tepat untuk skala Anda
- ❌ Jangan adopsi **Alembic/tool migration** sekarang — auto-sync additive sudah memadai dan mengurangi risiko
- ❌ Jangan **refactor** router existing "sekalian" — satu PR satu tujuan (sesuai `AGENTS.md`)

---

## RINGKASAN EKSEKUTIF

**Kabar baik:** fondasi aplikasi ini **jauh lebih siap SaaS daripada yang biasa ditemukan**. Seluruh 31 tabel tenant sudah berkolom `company_id`, relasi user↔company↔role sudah N-N, pergantian perusahaan sudah berfungsi lengkap dengan UI, aktivasi modul sudah per perusahaan, kolom `scope` pada tabel `roles` bahkan sudah tersedia untuk menampung role platform, dan mekanisme skema bersifat *additive-only* sehingga penambahan tabel tidak berisiko.

**Yang benar-benar kosong** hanyalah lapisan komersial: lisensi, trial, kuota, level platform, dan Console. Karena greenfield, ini justru dapat dirancang bersih **tanpa membongkar apa pun**.

**Dua hal yang perlu perhatian serius:**

1. **Isolasi tenant masih bergantung pada disiplin developer** (G1). Untuk aplikasi internal ini terkendali; untuk software yang dijual, ini gap keamanan terpenting. Disarankan dikerjakan (Tahap 8) sebelum monetisasi berjalan.
2. **Penegakan lisensi adalah satu-satunya bagian berisiko tinggi** karena menyentuh jalur login pelanggan existing. Solusinya: taruh paling akhir, di balik feature flag, dengan kebijakan *fail-open*.

**Total perubahan yang diperlukan:** 5 tabel baru, 1 baris role baru, 1 prefix API baru, 1 area UI baru. **Nol** tabel existing diubah, **nol** kolom dihapus, **nol** data disentuh, **nol** role existing dimodifikasi.

**Rekomendasi langkah berikutnya:** mulai dari **Tahap 1** (fondasi data saja — tanpa endpoint, tanpa UI, tanpa penegakan). Ini perubahan paling aman yang mungkin dilakukan dan dapat diverifikasi bahwa HRIS existing berjalan 100% identik sebelum melanjutkan.

---

*Dokumen ini adalah hasil audit read-only. Tidak ada source code, database, konfigurasi, atau data yang diubah selama audit. Menunggu persetujuan Anda sebelum implementasi apa pun.*
